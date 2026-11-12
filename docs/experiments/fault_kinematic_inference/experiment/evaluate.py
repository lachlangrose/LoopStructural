"""Score fixed predictions. This module is never imported by the fitting worker."""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .data import Terrain, validate_table
from .geometry import surface_gradient
from .schema import BASE, digest, load_config, write_json


def load_evaluation(config, fold):
    root = BASE / "datasets" / config["dataset"]
    names = [f"splits/fold_{fold}/{layer}_test.csv" for layer in ["contacts", "bedding"]]
    expected = json.loads((root / "SHA256SUMS.json").read_text())
    hashes = {name: digest(root / name) for name in names}
    if any(hashes[name] != expected[name] for name in names):
        raise ValueError("Evaluation source hash mismatch")
    tables = [pd.read_csv(root / name) for name in names]
    bounds = json.loads((root / "manifest.json").read_text())["bounds_xy_m"]
    for layer, table in zip(["contacts", "bedding"], tables):
        validate_table(table, layer, bounds)
    return *tables, hashes


def point_curve_distance(point, curve):
    """Distance to matching saved polyline segments, never bridging missing predictions."""
    xy = curve[["X", "Y"]].to_numpy()
    good = np.isfinite(xy).all(axis=1)
    valid = good[1:] & good[:-1]
    start, end = xy[:-1][valid], xy[1:][valid]
    if len(start) == 0:
        return None
    segment = end - start
    fraction = np.clip(np.sum((point - start) * segment, axis=1) / np.sum(segment**2, axis=1), 0, 1)
    return float(np.min(np.linalg.norm(point - (start + fraction[:, None] * segment), axis=1)))


def evaluate(config_path, output):
    from .report import make_report
    from .run import mixture_interval

    config = load_config(config_path)
    output = Path(output)
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["status"] != "predictions_frozen" or config != json.loads(
        (output / "configuration.json").read_text()
    ):
        raise ValueError("Evaluation requires frozen predictions and identical configuration")
    started = time.perf_counter()
    all_metrics = []
    try:
        for entry in manifest["folds"]:
            fold = entry["fold"]
            directory = output / f"fold_{fold}"
            frozen = json.loads((directory / "prediction_hashes.json").read_text())
            for name, expected in frozen.items():
                if digest(directory / name) != expected:
                    raise ValueError(f"Frozen prediction changed: {name}")
            contacts, bedding, hashes = load_evaluation(config, fold)
            state = json.loads((directory / "prediction_state.json").read_text())
            predictions = pd.read_csv(directory / "predictions.csv")
            terrain = Terrain(BASE / "datasets" / config["dataset"] / "dem.tif")
            normal = np.array(state["normal"])
            qnodes = np.array(state["q_quadrature"])
            rows = []
            for row in contacts.itertuples():
                curve = predictions[
                    (predictions.contact_id == row.contact_id) & (predictions.wall == row.wall)
                ]
                distance = point_curve_distance(np.array([row.X, row.Y]), curve)
                target = state["contact_targets"].get(f"{row.contact_id}:{int(row.wall > 0)}")
                if distance is None or target is None:
                    rows.append(
                        {
                            "observation_id": row.observation_id,
                            "source_group": row.source_group,
                            "X": row.X,
                            "Y": row.Y,
                            "contact_id": row.contact_id,
                            "wall": row.wall,
                            "error_m": config["prediction"]["missing_penalty_m"],
                            "missing": True,
                        }
                    )
                    continue
                gradient = np.linalg.norm(
                    surface_gradient(terrain, normal, np.array([row.X]), np.array([row.Y]))[0]
                )
                if gradient < 1e-8:
                    raise ValueError("Predicted trace has weak/undefined surface sensitivity")
                centres = target["horizon_intercept"] + target["q_coefficient"] * qnodes
                # XY noise and DEM-derived Z enter once, through the surface gradient.
                sigma = np.sqrt(
                    target["gaussian_horizon_sd"] ** 2
                    + (row.position_sigma_m * gradient) ** 2
                    + 0.05**2
                )
                lower, upper = mixture_interval(centres, sigma)
                value = float(np.array([row.X, row.Y, row.Z]) @ normal)
                score = upper - lower + 20 * max(lower - value, 0) + 20 * max(value - upper, 0)
                rows.append(
                    {
                        "observation_id": row.observation_id,
                        "source_group": row.source_group,
                        "X": row.X,
                        "Y": row.Y,
                        "contact_id": row.contact_id,
                        "wall": row.wall,
                        "error_m": distance,
                        "missing": False,
                        "signed_surface_normal_residual_m": (value - target["mean"]) / gradient,
                        "covered90": lower <= value <= upper,
                        "interval_score90_m": score / gradient,
                        "interval_width90_m": (upper - lower) / gradient,
                    }
                )
            table = pd.DataFrame(rows)
            table.to_csv(directory / "scored_predictions.csv", index=False)
            # Equal source-group weight; vertices do not dominate aggregate scores.
            grouped = table.groupby("source_group").agg(error_m=("error_m", "median"))
            valid = table[~table.missing]
            grouped_scores = valid.groupby("source_group")[
                ["covered90", "interval_score90_m", "interval_width90_m"]
            ].mean()
            poles = bedding[["nx", "ny", "nz"]].to_numpy()
            angles = np.degrees(
                np.arccos(np.clip(abs(poles @ normal / np.linalg.norm(normal)), 0, 1))
            )
            metrics = {
                "fold": fold,
                "test_count": len(table),
                "source_groups": len(grouped),
                "missing_count": int(table.missing.sum()),
                "median_group_contact_error_m": float(grouped.error_m.median()),
                "p90_group_contact_error_m": float(grouped.error_m.quantile(0.9)),
                "coverage90_group_mean": (
                    float(grouped_scores.covered90.mean()) if len(valid) else None
                ),
                "interval_score90_group_mean_m": (
                    float(grouped_scores.interval_score90_m.mean()) if len(valid) else None
                ),
                "interval_width90_group_mean_m": (
                    float(grouped_scores.interval_width90_m.mean()) if len(valid) else None
                ),
                "bedding_median_angle_degrees": float(np.median(angles)),
                "evaluation_input_hashes": hashes,
                "interval_scope": "conditional, first-order DEM surface-normal predictive intervals",
            }
            write_json(directory / "evaluation.json", metrics)
            all_metrics.append(metrics)
        write_json(
            output / "evaluation.json",
            {
                "status": "scored",
                "folds": all_metrics,
                "mean_fold_median_contact_error_m": float(
                    np.mean([m["median_group_contact_error_m"] for m in all_metrics])
                ),
                "elapsed_seconds": time.perf_counter() - started,
                "truth_parameter_recovery": "not scored; independent analytical recovery tests are reported separately",
            },
        )
        manifest["status"] = "complete_conditional"
        manifest["evaluation_seconds"] = time.perf_counter() - started
        write_json(output / "manifest.json", manifest)
        make_report(output)
    except Exception as error:
        manifest["status"] = "evaluation_failed"
        manifest["failure"] = {"type": type(error).__name__, "message": str(error)}
        write_json(output / "manifest.json", manifest)
        raise
