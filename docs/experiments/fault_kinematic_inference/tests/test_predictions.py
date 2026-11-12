"""Frozen prediction geometry and mixture-interval checks."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from docs.experiments.fault_kinematic_inference.experiment.data import load_training
from docs.experiments.fault_kinematic_inference.experiment.evaluate import point_curve_distance
from docs.experiments.fault_kinematic_inference.experiment.geometry import Plane, fit_plane
from docs.experiments.fault_kinematic_inference.experiment.run import (
    mixture_interval,
    plane_sensitivity,
)
from docs.experiments.fault_kinematic_inference.tests.test_inputs import configuration


def test_fixed_predictive_mixture_matches_gaussian():
    interval = mixture_interval(np.zeros(2001), 10)
    np.testing.assert_allclose(interval, norm.ppf([0.05, 0.95]) * 10, atol=1e-7)


def test_contact_distance_and_missing_segments():
    line = pd.DataFrame({"X": [0, 10], "Y": [0, 10]})
    assert point_curve_distance(np.array([0, 10]), line) == pytest.approx(np.sqrt(50))
    broken = pd.DataFrame({"X": [0, np.nan, 10], "Y": [0, 5, 10]})
    assert point_curve_distance(np.array([5, 5]), broken) is None


def test_plane_uncertainty_is_measured_separately():
    data = load_training(configuration("E1"), 0)
    plane = fit_plane(data)
    settings = {"plane_seed": 1701, "plane_draws": 40}
    first = plane_sensitivity(data, plane, settings)
    wider = Plane(plane.normal, plane.slope_covariance * 4, plane.horizons)
    second = plane_sensitivity(data, wider, settings)
    assert first["sd_from_plane_perturbation"] > 0
    assert second["sd_from_plane_perturbation"] > first["sd_from_plane_perturbation"] * 1.8
