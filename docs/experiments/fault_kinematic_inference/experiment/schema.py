"""Frozen Stage A configuration and serialisation contract."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
OUTPUT_ROOT = ROOT / "validation" / "fault_kinematic_inference"
DATASET = "synthetic_01_parallel_markers"
CONVENTION = {
    "units": "metres",
    "fault": "x=0; positive wall x>0",
    "strike": [0, 1, 0],
    "down_dip": [0, 0, -1],
    "forward": "s=(0,a,-b), positive wall relative to negative wall",
    "restoration": "p_restored=p-s on positive wall",
    "pitch": "atan2(b,a) radians, [-pi,pi)",
}
OUTPUTS = [
    "manifest.json",
    "configuration.json",
    "posterior.npz",
    "summary.json",
    "geometric_ensemble.npz",
    "prediction_state.json",
    "predictions.csv",
    "prediction_hashes.json",
    "evaluation.json",
    "report.md",
    "diagnostics.png",
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config["version"] != 1 or config["dataset"] != DATASET:
        raise ValueError("Only the frozen Stage A dataset and schema version 1 are supported")
    if config["conventions"] != CONVENTION:
        raise ValueError("Coordinate/slip conventions differ from the implemented operator")
    if config["case"] not in ("E0", "E1", "E2"):
        raise ValueError("Unknown evidence case")
    if config["folds"] != list(range(5)):
        raise ValueError("Stage A requires all five buffered folds")
    if config["prior"] != {"D_m": [0, 600], "density": "uniform_D_uniform_allowed_pitch"}:
        raise ValueError("The physical prior must be declared in D,pitch coordinates")
    if config["model"] != {
        "family": "shared_parallel_planes",
        "horizon_levels": "training_fitted_categories",
        "plane": "training_contacts_and_bedding_conditional",
        "terrain": "known_bilinear_DEM",
        "fault_geometry": "known_fixed",
    }:
        raise ValueError("Unsupported nuisance model")
    if config["errors"] != {
        "contact": "Gaussian_trace_mean",
        "source_grouping": "one_effective_observation_per_trace",
        "sigma": "reported_XY_sigma_times_DEM_surface_gradient",
        "bedding": "Gaussian_slope_delta_method",
        "dem_interpolation_floor_m": 0.05,
    }:
        raise ValueError("Unsupported observation model")
    grid = config["grid"]
    if (
        grid["initial_D"] < 16
        or grid["initial_pitch"] < 32
        or grid["max_levels"] < 2
        or grid["max_nodes"] < 1000
        or grid["seconds_per_fold"] <= 0
        or not 0 < grid["mean_tolerance_sd"] <= 0.1
        or not 0 < grid["sd_relative_tolerance"] <= 0.1
    ):
        raise ValueError("Invalid numerical budget or reference tolerance")
    if config["ensemble"]["seeds"] != [17, 29, 43] or config["ensemble"]["size"] < 100:
        raise ValueError("Declare three inference seeds and an adequate ensemble")
    if config["prediction"]["y_samples"] < 201:
        raise ValueError("Prediction curves require at least 201 declared transects")
    return config


def direction_summary(vectors, weights, error_scale=10.0):
    """Suppress direction when the 90% joint component region includes zero."""
    mean = weights @ vectors
    delta = vectors - mean
    cov = (delta * weights[:, None]).T @ delta
    radius = float(mean @ np.linalg.pinv(cov) @ mean)
    resolved_motion = radius > 4.605 and np.linalg.norm(mean) > error_scale
    angles = np.arctan2(vectors[:, 1], vectors[:, 0])
    resultant = np.sum(weights * np.exp(1j * angles))
    return {
        "motion_resolved": bool(resolved_motion),
        "pitch_mean_radians": float(np.angle(resultant)) if resolved_motion else None,
        "pitch_resultant": float(abs(resultant)) if resolved_motion else None,
    }
