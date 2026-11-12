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


def test_faulted_feature_gradient_shape_and_direction():
    _, strati = _model()
    pts = np.array([[0.2, 0.5, 0.5], [0.8, 0.5, 0.5]])
    g = strati.evaluate_gradient(pts)
    assert g.shape == (2, 3)
    assert np.all(np.isfinite(g))
    g /= np.linalg.norm(g, axis=1)[:, None]
    assert np.all(g[:, 2] > 0.9)
