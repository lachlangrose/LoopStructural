"""Stage A runner. Fit and evaluation run in separate interpreter processes."""

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from .data import load_training
from .geometric_ensemble import geometric_ensemble
from .geometry import fit_plane
from .grid import refine_grid, summarise, weighted_quantile
from .likelihood import contact_likelihood
from .schema import BASE, OUTPUT_ROOT, digest, direction_summary, load_config, signature, write_json


def mixture_interval(centres, sigma):
    """Equal-weight inverse-CDF quadrature of a saved scalar posterior plus Gaussian noise."""
    centres = np.asarray(centres)
    lo, hi = centres.min() - 10 * sigma, centres.max() + 10 * sigma
    return [
        float(brentq(lambda x, p=p: norm.cdf((x - centres) / sigma).mean() - p, lo, hi))
        for p in [0.05, 0.95]
    ]


def freeze_predictions(data, plane, nuisance, vectors, weights, config, directory):
    row = np.array([plane.normal[1], -plane.normal[2]])
    q = vectors @ row
    qmean = float(weights @ q)
    # Deterministic equal-probability quadrature; these are not new random samples.
    qnodes = weighted_quantile(q, weights, (np.arange(2001) + 0.5) / 2001)
    state = {
        "normal": plane.normal.tolist(),
        "q_mean": qmean,
        "q_sd": float(np.sqrt(weights @ (q - qmean) ** 2)),
        "q_quadrature": qnodes.tolist(),
        "horizons": nuisance,
        "uncertainty_scope": "conditional on training-estimated plane; conservative Gaussian trace errors",
        "prediction_contract": "fixed scalar target distributions and DEM-intersected contact curves",
        "contact_targets": {},
    }
    records = []
    # Known terrain is allowed throughout; no test locations determine these transects.
    ys = np.linspace(data.terrain.y.min(), data.terrain.y.max(), config["prediction"]["y_samples"])
    for horizon, values in nuisance.items():
        for wall in (0, 1):
            coefficient = wall - values["positive_fraction"]
            target = values["intercept"] + coefficient * qmean
            centres = values["intercept"] + coefficient * qnodes
            interval = mixture_interval(centres, np.sqrt(values["variance"]))
            state["contact_targets"][f"{horizon}:{wall}"] = {
                "mean": target,
                "latent_interval90": interval,
                "gaussian_horizon_sd": np.sqrt(values["variance"]),
                "q_coefficient": coefficient,
                "horizon_intercept": values["intercept"],
            }
            xmin, xmax = (
                (data.terrain.x.min(), -1e-6) if wall == 0 else (1e-6, data.terrain.x.max())
            )
            for y in ys:

                def residual(x, y=y, target=target):
                    return (
                        plane.normal[0] * x
                        + plane.normal[1] * y
                        + data.terrain.height(x, y)
                        - target
                    )

                if residual(xmin) * residual(xmax) > 0:
                    x = z = None
                else:
                    x = brentq(residual, xmin, xmax, xtol=config["prediction"]["root_tolerance_m"])
                    z = float(data.terrain.height(x, y))
                records.append(
                    {
                        "contact_id": horizon,
                        "wall": -1 if wall == 0 else 1,
                        "X": x,
                        "Y": y,
                        "Z": z,
                        "status": "valid" if x is not None else "outside_wall_window",
                    }
                )
    write_json(directory / "prediction_state.json", state)
    pd.DataFrame(records).to_csv(directory / "predictions.csv", index=False)
    write_json(
        directory / "prediction_hashes.json",
        {
            name: digest(directory / name)
            for name in ("prediction_state.json", "predictions.csv", "posterior.npz")
        },
    )
    return state


def plane_sensitivity(data, plane, settings):
    """Training-only delta/Monte Carlo sensitivity, not a marginal posterior claim."""
    from .geometry import Plane

    rng = np.random.default_rng(settings["plane_seed"])
    slopes = rng.multivariate_normal(
        plane.normal[:2], plane.slope_covariance, settings["plane_draws"]
    )
    values = []
    for slope in slopes:
        trial = Plane(np.r_[slope, 1.0], plane.slope_covariance, plane.horizons)
        problem, _, _ = contact_likelihood(data, trial)
        precision = 1 / problem.sigma**2
        q = float(precision @ problem.values / precision.sum())
        pitch = data.constraints["fixed"].get("pitch_radians")
        if pitch is None:
            values.append(q)
        else:
            sensitivity = problem.matrix[0] @ np.array([np.cos(pitch), np.sin(pitch)])
            if abs(sensitivity) < 1e-8:
                raise ValueError("Plane perturbation removes known-direction sensitivity")
            values.append(q / sensitivity)
    return {
        "draws": len(values),
        "seed": settings["plane_seed"],
        "quantity": "D_m" if pitch is not None else "signed_separation_m",
        "sd_from_plane_perturbation": float(np.std(values, ddof=1)),
        "interval90": np.quantile(values, [0.05, 0.95]).tolist(),
        "slope_covariance": plane.slope_covariance.tolist(),
        "interpretation": "local training-plane sensitivity; not a marginalised posterior or calibration proof",
    }


def fit(config_path, output):
    config = load_config(config_path)
    output = Path(output).resolve()
    if not output.is_relative_to(OUTPUT_ROOT.resolve()):
        raise ValueError(f"Run output must be under {OUTPUT_ROOT}")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "configuration.json").exists():
        raise FileExistsError("Run directory already has a configuration; use a new run ID")
    write_json(output / "configuration.json", config)
    settings = json.loads((BASE / "configs" / "simple_sensitivity.json").read_text())
    manifest = {
        "status": "running",
        "configuration_sha256": digest(output / "configuration.json"),
        "sensitivity_configuration": settings,
        "sensitivity_configuration_sha256": signature(settings),
        "software": {
            name: importlib.metadata.version(name)
            for name in ["numpy", "scipy", "pandas", "rasterio"]
        },
        "hardware": {
            "platform": sys.platform,
            "processor": os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        },
        "python": sys.version,
        "folds": [],
        "seeds": config["ensemble"]["seeds"],
        "code_hashes": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
        "prior": config["prior"],
        "inference_truth_access": False,
    }
    write_json(output / "manifest.json", manifest)
    started = time.perf_counter()
    try:
        for fold in config["folds"]:
            directory = output / f"fold_{fold}"
            directory.mkdir()
            fold_start = time.perf_counter()
            data = load_training(config, fold)
            plane = fit_plane(data)
            problem, nuisance, groups = contact_likelihood(data, plane)
            vectors, weights, numerical = refine_grid(problem, data.constraints, config["grid"])
            np.savez_compressed(
                directory / "posterior.npz", components_ab_m=vectors, weights=weights
            )
            summary = summarise(vectors, weights)
            summary.update(direction_summary(vectors, weights))
            summary.update(problem.diagnostics())
            summary["numerical"] = numerical
            summary["constraints"] = data.constraints
            summary["plane_normal_nz1"] = plane.normal.tolist()
            summary["effective_trace_count"] = len(groups)
            summary["matched_horizon_count"] = len(problem.values)
            summary["uncertainty_scope"] = (
                "conditional on training-estimated plane and declared working error model"
            )
            summary["pitch_information"] = (
                "fixed independent expert input"
                if config["case"] == "E1"
                else (
                    "bounded by experimental expert assumption"
                    if config["case"] == "E2"
                    else "unresolved likelihood null space; circular summaries are prior-dependent"
                )
            )
            ensemble_arrays, ensemble_records = {}, []
            for seed in config["ensemble"]["seeds"]:
                candidates, record = geometric_ensemble(
                    problem, data.constraints, seed, config["ensemble"]["size"]
                )
                ensemble_arrays[f"seed_{seed}"] = candidates
                ensemble_records.append(record)
            np.savez_compressed(directory / "geometric_ensemble.npz", **ensemble_arrays)
            summary["geometric_ensemble"] = ensemble_records
            state = freeze_predictions(data, plane, nuisance, vectors, weights, config, directory)
            summary["q_mean_m"] = state["q_mean"]
            summary["q_sd_m"] = state["q_sd"]
            summary["plane_sensitivity"] = plane_sensitivity(data, plane, settings)
            summary["elapsed_seconds"] = time.perf_counter() - fold_start
            write_json(directory / "summary.json", summary)
            entry = {
                "fold": fold,
                "input_hashes": data.hashes,
                "constraints": data.constraints,
                "signature": signature({"config": config, "inputs": data.hashes}),
                "status": "predictions_frozen",
                "elapsed_seconds": summary["elapsed_seconds"],
                "full_evaluations": numerical["full_evaluations"],
                "proxy_evaluations": 0,
                "geometric_proposals": sum(r["proposals"] for r in ensemble_records),
                "plane_perturbations": settings["plane_draws"],
            }
            manifest["folds"].append(entry)
            write_json(output / "manifest.json", manifest)
            print(
                f"{config['case']} fold {fold}: predictions frozen; rank {summary['likelihood_rank']}",
                flush=True,
            )
        manifest["status"] = "predictions_frozen"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["failure"] = {"type": type(error).__name__, "message": str(error), "fold": fold}
        raise
    finally:
        manifest["elapsed_seconds"] = time.perf_counter() - started
        write_json(output / "manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", choices=["fit", "evaluate", "all"], default="all")
    args = parser.parse_args()
    if args.phase == "fit":
        fit(args.config, args.output)
    elif args.phase == "evaluate":
        from .evaluate import evaluate

        evaluate(args.config, args.output)
    else:
        # Evaluation files and paths never enter the fitting interpreter.
        for phase in ["fit", "evaluate"]:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    __package__ + ".run",
                    "--config",
                    str(args.config),
                    "--output",
                    str(args.output),
                    "--phase",
                    phase,
                ],
                check=True,
            )


if __name__ == "__main__":
    main()
