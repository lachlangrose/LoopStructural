"""Scientific verification of the opt-in gradient smoothness experiment."""

import numpy as np
import pytest
from loop_common.supports import StructuredGrid
from loop_interpolation import FiniteDifferenceInterpolator
from loop_interpolation.experimental.benchmark_gradient_smoothness import Geometry, evaluate
from loop_interpolation.experimental.gradient_smoothness import (
    GradientSmoothnessExperiment,
    NodeDerivatives,
)


def make_experiment(cells=4):
    grid = StructuredGrid(
        origin=np.array([-0.6, -0.5, -0.4]),
        nsteps_cells=np.array([cells] * 3),
        step_vector=np.array([1.2, 1.0, 0.8]) / cells,
    )
    contacts = np.array([[-0.3, -0.3, 0, 0], [0.3, 0.2, 0, 0], [0.1, -0.2, 0, 0]])
    directions = np.array([[0.23, 0.12, 0.0, 0, 0, 1], [-0.22, 0.1, 0, 0, 0, 1]])
    return GradientSmoothnessExperiment(
        grid, contacts, directions, np.array([0.07, 0.04, 0.03]), np.array([0, 0, 1])
    )


def test_polynomial_derivatives_spacing_mixed_and_boundaries():
    problem = make_experiment()
    x, y, z = problem.grid.nodes.T
    u = 2 * x * x + 3 * y * y + 5 * z * z + 7 * x * y + 11 * x * z + 13 * y * z + 17 * x
    ops = problem.derivatives
    truth = (4 * x + 7 * y + 11 * z + 17, 6 * y + 7 * x + 13 * z, 10 * z + 11 * x + 13 * y)
    for matrix, expected in zip(ops.gradient, truth):
        np.testing.assert_allclose(matrix @ u, expected, atol=2e-12)
    for matrix, expected in zip(ops.hessian, (4, 6, 10, 7, 11, 13)):
        np.testing.assert_allclose(matrix @ u, expected, atol=2e-11)
    energy = sum(
        (1 if j < 3 else 2) * np.sum(ops.volume * (m @ u) ** 2) for j, m in enumerate(ops.hessian)
    )
    np.testing.assert_allclose(
        energy, 1.2 * 1.0 * 0.8 * (4**2 + 6**2 + 10**2 + 2 * (7**2 + 11**2 + 13**2))
    )
    np.testing.assert_allclose(ops.volume.sum(), 1.2 * 1.0 * 0.8)


def test_full_nonlinear_gradient_and_reduced_jacobian():
    problem = make_experiment()
    rng = np.random.default_rng(345)
    u = problem.grid.nodes[:, 2] + rng.normal(0, 0.05, problem.grid.n_nodes)
    direction = rng.normal(size=len(u))
    direction /= np.linalg.norm(direction)
    _, grad = problem.energy_gradient(u, 0.007, 0.03)
    step = 2e-6
    numeric = (
        problem.energy_gradient(u + step * direction, 0.007, 0.03)[0]
        - problem.energy_gradient(u - step * direction, 0.007, 0.03)[0]
    ) / (2 * step)
    np.testing.assert_allclose(grad @ direction, numeric, rtol=1e-6, atol=1e-7)
    x = u[problem.free]
    v = direction[problem.free]
    r, jac = problem.residual_jacobian(problem.offset + problem.transform @ x, 0.007, 0.03)
    plus = problem.residual_jacobian(
        problem.offset + problem.transform @ (x + step * v), 0.007, 0.03
    )[0]
    minus = problem.residual_jacobian(
        problem.offset + problem.transform @ (x - step * v), 0.007, 0.03
    )[0]
    np.testing.assert_allclose(
        jac @ problem.transform @ v, (plus - minus) / (2 * step), rtol=2e-5, atol=2e-8
    )
    assert len(r) == problem.data_matrix.shape[0] + 6 * problem.grid.n_nodes


def test_scale_invariance_and_epsilon_limit():
    problem = make_experiment()
    x, y, z = problem.grid.nodes.T
    u = z + 0.2 * x * x + 0.1 * y * y

    # Compare the regulariser alone: data and an exact prescribed anchor are
    # deliberately not scale invariant. Hold epsilon fixed in both fields.
    def regularisation(v, eps):
        r, _ = problem.residual_jacobian(v, 1.0, eps)
        return r[problem.data_matrix.shape[0] :] @ r[problem.data_matrix.shape[0] :]

    np.testing.assert_allclose(regularisation(u, 1e-5), regularisation(3 * u, 1e-5), rtol=1e-8)
    assert abs(regularisation(u, 1) / regularisation(3 * u, 1) - 1) > 0.1
    np.testing.assert_allclose(regularisation(u, 0.03), regularisation(3 * u, 0.09), rtol=1e-12)


def test_nonlinear_gradient_in_epsilon_dominated_region():
    problem = make_experiment()
    rng = np.random.default_rng(97)
    u = rng.normal(0, 1e-5, problem.grid.n_nodes)
    direction = rng.normal(size=len(u))
    direction /= np.linalg.norm(direction)
    _, gradient = problem.energy_gradient(u, 0.01, 0.03)
    step = 1e-8
    plus = problem.energy_gradient(u + step * direction, 0.01, 0.03)[0]
    minus = problem.energy_gradient(u - step * direction, 0.01, 0.03)[0]
    np.testing.assert_allclose(gradient @ direction, (plus - minus) / (2 * step), rtol=2e-7)


@pytest.mark.parametrize("name", ["plane", "cylinder", "varying"])
def test_truth_signed_distance_normals_and_no_medial_axis(name):
    geometry = Geometry(name, 23)
    rng = np.random.default_rng(89)
    surface, normals, _ = geometry.surface(rng.uniform(-0.4, 0.4, (40, 2)))
    offsets = rng.uniform(-0.15, 0.15, (40, 1))
    points = surface + offsets * normals
    distance, calculated_normals, _ = geometry.distance_normal_curvature(points)
    np.testing.assert_allclose(distance, offsets[:, 0], atol=1e-12)
    np.testing.assert_allclose(calculated_normals, normals, atol=1e-12)
    numerical = []
    for axis in np.eye(3):
        plus = geometry.distance_normal_curvature(points + 1e-6 * axis)[0]
        minus = geometry.distance_normal_curvature(points - 1e-6 * axis)[0]
        numerical.append((plus - minus) / 2e-6)
    np.testing.assert_allclose(np.array(numerical).T, normals, atol=1e-9)
    # Over the complete rotated box the cylinder axis is outside, and the
    # varying graph's closest-point squared distance is strictly convex.
    corners = (
        np.array([(x, y, z) for x in (-0.6, 0.6) for y in (-0.55, 0.55) for z in (-0.32, 0.32)])
        @ geometry.rotation
    )
    assert corners[:, 2].min() > -1
    assert (np.abs(corners[:, 2]).max() + 0.07) * 1.4175 < 1


def test_surface_evaluation_plane_has_single_zero_crossing():
    problem = make_experiment()
    fit = problem.solve_baseline(0.01)
    contacts = np.array([[-0.3, -0.3, 0], [0.3, 0.2, 0], [0.1, -0.2, 0]])
    directions = np.array([[0.23, 0.12, 0], [-0.22, 0.1, 0]])
    normals = np.tile([0, 0, 1], (2, 1))
    metrics, _ = evaluate(problem, Geometry("plane", 0), fit.values, contacts, directions, normals)
    assert metrics['mesh_distance_rms'] < 1e-7
    assert metrics['multiple_normal_crossing_fraction'] == 0
    assert metrics['withheld_coverage'] == 1


def test_plane_exact_anchor_and_direction_only_rows():
    problem = make_experiment()
    # Directions have zero RHS and two rows each; only the anchor fixes scale.
    assert np.count_nonzero(problem.data_target) == 0
    assert problem.data_matrix.shape[0] == 3 + 2 * 2
    baseline = problem.solve_baseline(0.01)
    native = problem.solve_native(0.01)
    normalised = problem.solve_normalised(native.values, 0.01, max_evaluations=12)
    for result in (baseline, native, normalised):
        np.testing.assert_allclose(result.values, problem.grid.nodes[:, 2], atol=1e-8)
        gradient = problem.grid.evaluate_gradient(problem.anchor_point, result.values)[0]
        np.testing.assert_allclose(gradient, [0, 0, 1], atol=1e-12)


def test_mask_and_default_fdi_untouched():
    problem = make_experiment()
    grid = problem.grid
    mask = grid.nodes[:, 0] > 0
    ops = NodeDerivatives.build(grid, mask)
    assert ops.gradient[0].shape == (np.sum(mask), grid.n_nodes)
    first = FiniteDifferenceInterpolator(grid)
    first.setup_interpolator()
    before = {k: (v['matrix'].copy(), v['w'].copy()) for k, v in first.constraints.items()}
    problem.solve_baseline(0.01)
    second = FiniteDifferenceInterpolator(grid)
    second.setup_interpolator()
    assert before.keys() == second.constraints.keys()
    for name, (matrix, weights) in before.items():
        assert (matrix != second.constraints[name]['matrix']).nnz == 0
        np.testing.assert_array_equal(weights, second.constraints[name]['w'])
