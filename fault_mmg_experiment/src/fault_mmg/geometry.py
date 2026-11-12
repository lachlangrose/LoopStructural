"""Exact, block-local geological fields. Fault values are deliberately two-valued."""

import numpy as np

HORIZONS = np.array([-0.5, 0.0, 0.5])
THROW = 0.4


def fault(points):
    return np.asarray(points)[..., 0]


def stratigraphy(points, block):
    """block=1 (A) or 2 (B), including either trace at x=0."""
    if np.any(~np.isin(block, [1, 2])):
        raise ValueError("Specify fault block 1 or 2 explicitly")
    return np.asarray(points)[..., 2] - THROW * (np.asarray(block) == 2)


def labels(points):
    blocks = np.where(fault(points) < 0, 1, 2)
    units = np.searchsorted(HORIZONS, stratigraphy(points, blocks), side="right")
    return blocks, units


def horizon_height(block, horizon):
    return float(horizon + (THROW if block == 2 else 0.0))
