"""Regression test: gradient of a feature that is displaced by a fault.

``GeologicalFeature.evaluate_gradient`` used to overwrite its (N, 3) result
array with the (N, 4) fault corner values, so any faulted feature (for
example the frame of a fault cut by a younger fault) raised a shape error.
"""

import numpy as np
import pandas as pd

from LoopStructural import GeologicalModel


def _model():
    rows = []
    for y in np.linspace(0.1, 0.9, 4):
        for z in np.linspace(0.1, 0.9, 4):
            rows.append([0.5, y, z, 0.0, 1.0, 0.0, 0.0, 0, "fault"])
    for x in np.linspace(0.05, 0.95, 6):
        for y in np.linspace(0.05, 0.95, 4):
            for z in (0.3, 0.6):
                rows.append([x, y, z, z, np.nan, np.nan, np.nan, np.nan, "strati"])
    data = pd.DataFrame(
        rows, columns=["X", "Y", "Z", "val", "nx", "ny", "nz", "coord", "feature_name"]
    )
    model = GeologicalModel(np.zeros(3), np.ones(3))
    model.data = data
    fault = model.create_and_add_fault(
        "fault",
        0.1,
        fault_slip_vector=[0, 0, 1],
        fault_center=[0.5, 0.5, 0.5],
        major_axis=4,
        minor_axis=4,
        intermediate_axis=4,
        nelements=2000,
    )
    strati = model.create_and_add_foliation("strati", nelements=2000, faults=[fault])
    return model, strati


def test_apply_to_points_with_undefined_frame_gradient_is_finite(monkeypatch):
    """A NaN slip direction (outside the frame support) must not make the point NaN."""
    model, _ = _model()
    fault = model["fault"]
    frame1 = fault[1]
    original = type(frame1).evaluate_gradient

    def gradient_with_hole(pos, *args, **kwargs):
        g = np.array(original(frame1, pos, *args, **kwargs), dtype=float)
        g[np.asarray(pos)[:, 1] > 0.7] = np.nan
        return g

    monkeypatch.setattr(frame1, "evaluate_gradient", gradient_with_hole)
    pts = np.array([[0.8, 0.5, 0.5], [0.8, 0.9, 0.5]])
    moved = fault.apply_to_points(pts)
    assert np.all(np.isfinite(moved))
    assert not np.allclose(moved[0], pts[0])  # normal point still moves
    assert np.allclose(moved[1], pts[1])  # undefined slip direction: no movement


def test_faulted_feature_gradient_shape_and_direction():
    _, strati = _model()
    pts = np.array([[0.2, 0.5, 0.5], [0.8, 0.5, 0.5]])
    g = strati.evaluate_gradient(pts)
    assert g.shape == (2, 3)
    assert np.all(np.isfinite(g))
    g /= np.linalg.norm(g, axis=1)[:, None]
    assert np.all(g[:, 2] > 0.9)
