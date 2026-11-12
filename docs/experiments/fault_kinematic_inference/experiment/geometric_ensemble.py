"""A geometric screen. Feasible-family frequencies are never posterior weights."""

import numpy as np


def geometric_ensemble(problem, constraints, seed, size=2000, maximum=600):
    rng = np.random.default_rng(seed)
    row = problem.matrix[0]
    precision = 1 / problem.sigma**2
    centre = float(precision @ problem.values / precision.sum())
    error = float(1 / np.sqrt(precision.sum()))
    separation = rng.normal(centre, error, size)
    if "pitch_radians" in constraints["fixed"]:
        pitch = constraints["fixed"]["pitch_radians"]
        unit = np.array([np.cos(pitch), np.sin(pitch)])
        sensitivity = row @ unit
        if abs(sensitivity) < 1e-8:
            raise ValueError("Known direction has weak/zero marker sensitivity")
        d = separation / sensitivity
        vectors = d[:, None] * unit
        valid = (d >= 0) & (d <= maximum)
    else:
        null = np.array([-row[1], row[0]]) / np.linalg.norm(row)
        particular = separation[:, None] * row / (row @ row)
        extent = np.sqrt(np.maximum(maximum**2 - np.sum(particular**2, axis=1), 0))
        vectors = particular + (rng.uniform(-1, 1, size) * extent)[:, None] * null
        pitch = np.arctan2(vectors[:, 1], vectors[:, 0])
        lo, hi = constraints["pitch_bounds"]
        valid = (np.linalg.norm(particular, axis=1) <= maximum) & (pitch >= lo) & (pitch <= hi)
    return vectors[valid], {
        "seed": seed,
        "proposals": size,
        "accepted": int(valid.sum()),
        "interpretation": "unweighted perturbed feasible families; no posterior probabilities",
    }
