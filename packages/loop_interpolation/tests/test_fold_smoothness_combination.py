"""Physical fold-row scaling and geometric diagnostics for the four-way study."""

import numpy as np
from loop_interpolation.experimental.benchmark_fold_normalisation import (
    FoldConstraintExperiment,
    evaluate_layers,
    geological_directions,
)


def test_geological_prior_is_flat_below_and_persists_above():
    points = np.array([[0.2, 0, -1], [0.2, 0, 2], [0.2, 0, 3]])
    tangent, axis, across, _ = geological_directions(points, 0.8)
    np.testing.assert_allclose(tangent[0], [1, 0, 0])
    np.testing.assert_allclose(tangent[1], tangent[2])
    assert tangent[1, 2] > 0
    np.testing.assert_allclose(np.linalg.norm(tangent, axis=1), 1)
    np.testing.assert_allclose(np.sum(tangent * axis, axis=1), 0)
    np.testing.assert_allclose(across, np.tile([0, 0, 1], (3, 1)))


def test_fold_rows_are_actual_physical_directional_derivatives():
    problem = FoldConstraintExperiment(8, 23, 'constant', 0.25)
    rng = np.random.default_rng(87)
    values = problem.transform @ rng.normal(size=problem.transform.shape[1])
    gradient = problem.grid.evaluate_gradient(problem.fold_points, values)
    coefficients = {'fold orientation': 0.1, 'fold axis': 0.1, 'fold normalisation': 0.01}
    for name, (matrix, target) in problem.fold_blocks.items():
        expected = np.sum(gradient * problem.fold_vectors[name], axis=1)
        if name == 'fold normalisation':
            expected -= problem.gradient_reference
        expected *= np.sqrt(problem.fold_quadrature * coefficients[name] * 0.25)
        np.testing.assert_allclose(matrix @ values - target, expected, atol=2e-15)
    np.testing.assert_allclose(problem.fold_quadrature.sum(), 64)


def test_projection_target_does_not_change_with_fold_weight():
    for gain in (0.25, 4):
        problem = FoldConstraintExperiment(8, 23, 'constant', gain)
        local = problem.grid.nodes @ problem.rotation
        values = problem.gradient_reference * (local[:, 2] + 0.25)
        matrix, target = problem.fold_blocks['fold normalisation']
        np.testing.assert_allclose(matrix @ values - target, 0, atol=1e-14)


def test_fold_augmented_actual_gradient_matches_finite_differences():
    problem = FoldConstraintExperiment(8, 0, 'constant')
    rng = np.random.default_rng(977)
    nodes = problem.grid.nodes[problem.free]
    x = (nodes[:, 2] + 0.25) / 1.35 + 0.1 * np.sin(nodes[:, 0])
    direction = rng.normal(size=len(x))
    direction /= np.linalg.norm(direction)
    epsilon = 0.03 * problem.gradient_reference
    _, gradient = problem.energy_gradient(problem.transform @ x, 0.001, epsilon)
    step = 1e-6
    plus = problem.energy_gradient(problem.transform @ (x + step * direction), 0.001, epsilon)[0]
    minus = problem.energy_gradient(problem.transform @ (x - step * direction), 0.001, epsilon)[0]
    np.testing.assert_allclose(
        (problem.transform.T @ gradient) @ direction, (plus - minus) / (2 * step), rtol=1e-7
    )


def test_layer_relief_distinguishes_arch_from_valley():
    problem = FoldConstraintExperiment(8, 0, 'none')
    x, _, z = problem.grid.nodes.T
    for sign in (-1, 1):
        values = z - sign * 0.2 * np.exp(-x * x)
        metrics, samples = evaluate_layers(problem, values)
        assert np.sign(metrics['level_2_relief']) == sign
        assert np.sign(metrics['level_2_central_curvature_fit']) == -sign
        assert metrics['level_2_coverage'] == 1
        assert metrics['level_2_multiple_crossing_fraction'] == 0
        np.testing.assert_allclose(samples['vertical_spacing_per_isovalue'], 1, atol=3e-11)
        np.testing.assert_allclose(metrics['level_1_to_2_vertical_spacing_mean'], 1, atol=3e-11)
        assert metrics['level_1_to_2_vertical_spacing_cv'] < 1e-10


def test_no_fold_path_preserves_contact_rows_and_derivatives():
    plain = FoldConstraintExperiment(8, 0, 'none')
    folded = FoldConstraintExperiment(8, 0, 'constant')
    assert (plain.contact_matrix != folded.contact_matrix).nnz == 0
    np.testing.assert_array_equal(plain.contact_target, folded.contact_target)
    for original, new in zip(plain.derivatives.hessian, folded.derivatives.hessian):
        assert (original != new).nnz == 0
    for original, new in zip(plain.derivatives.gradient, folded.derivatives.gradient):
        assert (original != new).nnz == 0


def test_missing_overlying_layers_are_unassessable_not_successful():
    problem = FoldConstraintExperiment(8, 0, 'none')
    metrics, _ = evaluate_layers(problem, np.zeros(problem.grid.n_nodes))
    assert metrics['overlying_arch_assessable_count'] == 0
    assert metrics['overlying_arch_fraction'] is None
    assert metrics['overlying_arch_relief_max'] is None
    assert metrics['overlying_vertical_spacing_mean'] is None
    assert metrics['overlying_valid_spacing_fraction'] == 0
    assert metrics['level_2_central_curvature_fit'] is None
    assert metrics['overlying_curvature_assessable_count'] == 0
    assert metrics['level_1_to_2_vertical_spacing_cv'] is None
    assert metrics['level_1_to_2_vertical_spacing_coverage'] == 0
