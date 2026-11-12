"""Protocol A01-A03, A05-A07 with independent analytical constructions."""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from docs.experiments.fault_kinematic_inference.experiment.data import load_training
from docs.experiments.fault_kinematic_inference.experiment.geometry import (
    BASIS,
    fit_plane,
    restore,
    solve_slip,
)
from docs.experiments.fault_kinematic_inference.tests.test_inputs import configuration


def test_exact_two_markers_A01():
    matrix = np.array([[1, 0], [0.6, 0.8]])
    normals = matrix @ BASIS.T
    result = solve_slip(normals, np.array([100, 140]), np.array([10, 10]))
    np.testing.assert_allclose(result["solution"], [100, 100], atol=1e-9)
    assert result["rank"] == 2
    assert np.linalg.norm(result["solution"]) == pytest.approx(np.sqrt(20000))


def test_repeated_parallel_markers_A02():
    result = solve_slip(np.tile([0, 1, 0], (25, 1)), np.full(25, 100), np.ones(25))
    assert result["rank"] == 1 and result["condition"] is None
    assert result["null_basis"].shape == (2, 1)


@pytest.mark.parametrize("angle", [60, 20, 5])
def test_conditioning_A03(angle):
    rad = np.deg2rad(angle)
    matrix = np.array([[1, 0], [np.cos(rad), np.sin(rad)]])
    result = solve_slip(matrix @ BASIS.T, matrix @ [100, 100], np.ones(2))
    assert result["condition"] == pytest.approx(1 / np.tan(rad / 2))


def test_rotation_translation_units_walls_A05():
    normals = np.array([[0, 1, 0], [0, 0.6, -0.8]])
    slip = np.array([100, 100])
    separation = normals @ BASIS @ slip
    rotation = Rotation.from_rotvec([0.3, -0.7, 0.1]).as_matrix()
    for scale in [1, 0.001]:
        fit = solve_slip(
            normals @ rotation.T, separation * scale, np.ones(2) * scale, basis=rotation @ BASIS
        )
        np.testing.assert_allclose(fit["solution"] / scale, slip, rtol=1e-6)
    points = np.array([[10, 20, 30], [-10, 40, 60]])
    moved = points + np.array([1, 0])[:, None] * (BASIS @ slip)
    shift = np.array([101, -400, 78])
    np.testing.assert_allclose(restore(moved + shift, slip, [1, 0]), points + shift)
    swapped = solve_slip(-normals, -separation, np.ones(2))
    np.testing.assert_allclose(swapped["solution"], slip)
    exchanged_walls = solve_slip(normals, -separation, np.ones(2))
    np.testing.assert_allclose(exchanged_walls["solution"], -slip)


def test_known_direction_elimination_A06_A07():
    direction = np.array([3, 2]) / np.sqrt(13)
    normals = np.array([[0, 0.2, 1]])
    scalar = 180.0
    result = solve_slip(
        normals, normals @ BASIS @ direction * scalar, np.array([10]), direction=direction
    )
    assert result["dimension"] == 1
    assert result["solution"][0] == pytest.approx(scalar)
    weak = solve_slip(
        np.array([[0, direction[1], direction[0]]]), np.array([0]), np.ones(1), direction=direction
    )
    assert weak["singular_values"][0] < 1e-8


def test_fitted_plane_does_not_use_numeric_horizon_labels():
    data = load_training(configuration(), 0)
    first = fit_plane(data)
    data.contacts["val"] = np.arange(len(data.contacts)) * 12345
    second = fit_plane(data)
    np.testing.assert_allclose(first.normal, second.normal)
    assert np.all(np.linalg.eigvalsh(first.slope_covariance) > 0)
