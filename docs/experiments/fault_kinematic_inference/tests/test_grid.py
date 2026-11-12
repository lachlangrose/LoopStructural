"""Numerical same-target verification; the polar and Cartesian priors differ."""

import numpy as np
import pytest
from scipy.stats import norm

from docs.experiments.fault_kinematic_inference.experiment.constraints import compile_constraints
from docs.experiments.fault_kinematic_inference.experiment.grid import (
    cartesian_gaussian_grid,
    moments,
    polar_grid,
    refine_grid,
)
from docs.experiments.fault_kinematic_inference.experiment.likelihood import LinearGaussian
from docs.experiments.fault_kinematic_inference.experiment.schema import BASE
from docs.experiments.fault_kinematic_inference.tests.test_inputs import configuration


@pytest.mark.parametrize("angle", [90, 60, 20, 5, 0])
def test_gaussian_reference_A01_A02_A03(angle):
    rad = np.deg2rad(angle)
    matrix = np.array([[1, 0], [np.cos(rad), np.sin(rad)]])
    problem = LinearGaussian(matrix, matrix @ [100, 100], [10, 10])
    prior_mean, prior_cov = np.zeros(2), np.eye(2) * 200**2
    mean, covariance = problem.posterior(prior_mean, prior_cov)
    sd = np.sqrt(np.diag(covariance))
    axes = [np.linspace(mean[j] - 7 * sd[j], mean[j] + 7 * sd[j], 401) for j in range(2)]
    vectors, weights = cartesian_gaussian_grid(problem, prior_mean, prior_cov, axes)
    actual_mean, actual_cov = moments(vectors, weights)
    assert np.max(np.abs(actual_mean - mean) / sd) < 0.1
    assert np.max(np.abs(np.sqrt(np.diag(actual_cov)) / sd - 1)) < 0.1
    if angle == 0:
        assert np.sqrt(actual_cov[1, 1]) / 200 == pytest.approx(1, abs=0.01)
        cdf = np.array([weights[vectors[:, 1] <= value].sum() for value in [-200, 0, 200]])
        assert np.max(abs(cdf - norm.cdf(np.array([-200, 0, 200]) / 200))) < 0.1


def test_fixed_direction_matches_truncated_scalar_A06():
    import json

    from scipy.stats import truncnorm

    config = configuration("E1")
    card = json.loads((BASE / "datasets" / config["dataset"] / "constraints.json").read_text())
    constraints = compile_constraints(config, card)
    problem = LinearGaussian([[0.2, -1]], [-70], [5])
    vectors, weights, diagnostics = refine_grid(problem, constraints, config["grid"])
    d = np.linalg.norm(vectors, axis=1)
    u = np.array(
        [
            np.cos(constraints["fixed"]["pitch_radians"]),
            np.sin(constraints["fixed"]["pitch_radians"]),
        ]
    )
    mu, sd = -70 / (problem.matrix[0] @ u), abs(5 / (problem.matrix[0] @ u))
    target = truncnorm(-mu / sd, (600 - mu) / sd, loc=mu, scale=sd)
    assert abs(weights @ d - target.mean()) / target.std() < 0.1
    assert abs(np.sqrt(weights @ (d - weights @ d) ** 2) / target.std() - 1) < 0.1
    assert diagnostics["status"] == "converged"


def test_polar_prior_measure_and_bounds_A07():
    problem = LinearGaussian([[0, 0]], [0], [1])
    constraints = {"fixed": {}, "pitch_bounds": [-np.pi, np.pi]}
    vectors, weights = polar_grid(problem, constraints, 100, 200)
    assert weights @ np.linalg.norm(vectors, axis=1) == pytest.approx(300)
    constraints["pitch_bounds"] = [0.2, 0.4]
    vectors, weights = polar_grid(problem, constraints, 100, 200)
    angles = np.arctan2(vectors[:, 1], vectors[:, 0])
    assert angles.min() > 0.2 and angles.max() < 0.4
    assert weights @ np.linalg.norm(vectors, axis=1) == pytest.approx(300)


def test_insufficient_grid_budget_is_failure():
    config = configuration()
    budget = dict(config["grid"], max_nodes=1)
    with pytest.raises(RuntimeError, match="did not converge"):
        refine_grid(
            LinearGaussian([[1, 0]], [100], [10]),
            {"fixed": {}, "pitch_bounds": [-np.pi, np.pi]},
            budget,
        )


def test_bounded_pitch_matches_independent_adaptive_quadrature():
    import json

    from scipy.integrate import quad
    from scipy.stats import truncnorm

    config = configuration("E2")
    card = json.loads((BASE / "datasets" / config["dataset"] / "constraints.json").read_text())
    constraints = compile_constraints(config, card)
    problem = LinearGaussian([[0.2, -1]], [-70], [5])
    vectors, weights, _ = refine_grid(problem, constraints, config["grid"])
    lo, hi = constraints["pitch_bounds"]

    def integrand(theta, component=None, power=1):
        unit = np.array([np.cos(theta), np.sin(theta)])
        sensitivity = problem.matrix[0] @ unit
        mu, sd = -70 / sensitivity, abs(5 / sensitivity)
        left, right = -mu / sd, (600 - mu) / sd
        mass = (norm.cdf(right) - norm.cdf(left)) * sd * np.sqrt(2 * np.pi)
        if component is None:
            return mass
        distribution = truncnorm(left, right, loc=mu, scale=sd)
        moment = (
            distribution.mean() if power == 1 else distribution.var() + distribution.mean() ** 2
        )
        return mass * unit[component] ** power * moment

    total = quad(integrand, lo, hi, epsabs=1e-8)[0]
    reference_mean = np.array(
        [quad(lambda t, j=j: integrand(t, j), lo, hi)[0] / total for j in range(2)]
    )
    reference_sd = np.sqrt(
        [
            quad(lambda t, j=j: integrand(t, j, 2), lo, hi)[0] / total - reference_mean[j] ** 2
            for j in range(2)
        ]
    )
    mean, covariance = moments(vectors, weights)
    assert np.max(abs(mean - reference_mean) / reference_sd) < 0.1
    assert np.max(abs(np.sqrt(np.diag(covariance)) / reference_sd - 1)) < 0.1
