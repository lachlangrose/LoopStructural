"""Prior-predictive screening and near-zero safeguards (T007 / A04)."""

import json

import numpy as np

from docs.experiments.fault_kinematic_inference.experiment.grid import (
    cartesian_gaussian_grid,
    moments,
)
from docs.experiments.fault_kinematic_inference.experiment.likelihood import LinearGaussian
from docs.experiments.fault_kinematic_inference.experiment.report import analytical_calibration
from docs.experiments.fault_kinematic_inference.experiment.schema import BASE, direction_summary


def test_200_independent_prior_predictive_trials():
    settings = json.loads((BASE / "configs" / "simple_sensitivity.json").read_text())
    result = analytical_calibration(settings)
    assert result["trials_per_problem"] == 200
    assert result["status"] == "pass", result
    for problem in result["results"].values():
        for component in problem["components"]:
            lo, hi = component["binomial95_interval"]
            assert lo < component["coverage90"] < hi
            assert sum(component["posterior_rank_histogram"]) == 200


def test_near_zero_is_not_resolved_A04():
    for value in [0, 1, 5]:
        problem = LinearGaussian(np.eye(2), [value, 0], [10, 10])
        prior_mean, prior_cov = np.zeros(2), np.eye(2) * 200**2
        exact_mean, exact_cov = problem.posterior(prior_mean, prior_cov)
        axes = [np.linspace(-100, 100, 201)] * 2
        vectors, weights = cartesian_gaussian_grid(problem, prior_mean, prior_cov, axes)
        actual_mean, actual_cov = moments(vectors, weights)
        np.testing.assert_allclose(actual_mean, exact_mean, atol=0.01)
        np.testing.assert_allclose(actual_cov, exact_cov, rtol=0.01, atol=1e-10)
        summary = direction_summary(vectors, weights)
        assert summary["motion_resolved"] is False
        assert summary["pitch_mean_radians"] is None


def test_repeated_parallel_data_leave_independent_null_prior():
    covariance = np.eye(2) * 200**2
    previous = 200
    for n in [1, 10, 100]:
        problem = LinearGaussian(np.tile([1, 0], (n, 1)), np.full(n, 100), np.full(n, 10))
        _, posterior = problem.posterior(np.zeros(2), covariance)
        assert np.sqrt(posterior[0, 0]) < previous
        assert posterior[1, 1] == covariance[1, 1]
        previous = np.sqrt(posterior[0, 0])
