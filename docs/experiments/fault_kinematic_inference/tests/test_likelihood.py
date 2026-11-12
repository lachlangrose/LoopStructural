"""Closed-form likelihood, geometry scaling and invalid-prediction checks."""

import numpy as np
import pytest

from docs.experiments.fault_kinematic_inference.experiment.data import load_training
from docs.experiments.fault_kinematic_inference.experiment.geometry import (
    fit_plane,
    surface_gradient,
)
from docs.experiments.fault_kinematic_inference.experiment.likelihood import (
    LinearGaussian,
    contact_likelihood,
)
from docs.experiments.fault_kinematic_inference.tests.test_inputs import configuration


def test_closed_form_and_scale_invariance():
    matrix = np.array([[1, 0], [0.6, 0.8]])
    base = LinearGaussian(matrix, [100, 140], [10, 10])
    target = base.posterior(np.zeros(2), np.eye(2) * 1e6)
    expected_covariance = np.linalg.inv(matrix.T @ matrix / 100 + np.eye(2) / 1e6)
    np.testing.assert_allclose(target[1], expected_covariance)
    for scale in [0.001, 700]:
        changed = LinearGaussian(
            matrix * scale, np.array([100, 140]) * scale, np.ones(2) * 10 * scale
        )
        actual = changed.posterior(np.zeros(2), np.eye(2) * 1e6)
        np.testing.assert_allclose(actual[0], target[0])
        np.testing.assert_allclose(actual[1], target[1])


def test_invalid_predictions_are_explicit():
    with pytest.raises(ValueError):
        LinearGaussian([[1, 0]], [np.nan], [10])
    with pytest.raises(ValueError):
        LinearGaussian([[1, 0]], [1], [0])
    problem = LinearGaussian([[1, 0]], [1], [1])
    with pytest.raises(ValueError, match="Nonfinite"):
        problem.log_likelihood([[np.nan, 0]])


def test_DEM_gradient_and_source_densification():
    data = load_training(configuration(), 0)
    plane = fit_plane(data)
    first, _, _ = contact_likelihood(data, plane)
    assert first.diagnostics()["likelihood_rank"] == 1
    gradient = surface_gradient(data.terrain, plane.normal, np.array([300]), np.array([400]))
    assert not np.allclose(gradient, plane.normal[:2])
    import pandas as pd

    data.contacts = pd.concat([data.contacts] * 10, ignore_index=True)
    second, _, _ = contact_likelihood(data, plane)
    np.testing.assert_allclose(first.precision, second.precision)
    np.testing.assert_allclose(first.information, second.information)
