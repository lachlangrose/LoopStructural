"""Verify the data-only extrusion and objective used by the two-contact case."""

import numpy as np
from loop_interpolation.experimental.benchmark_two_contacts import TwoContactExperiment
from loop_interpolation.experimental.gradient_smoothness import NodeDerivatives


def test_two_isovalues_no_added_gradient_constraints():
    problem = TwoContactExperiment(8)
    np.testing.assert_array_equal(np.unique(problem.observations[:, 3]), [0, 1])
    assert problem.data_matrix.shape[0] == 42
    assert problem.interpolator.get_gradient_constraints().shape[0] == 0
    assert problem.interpolator.get_norm_constraints().shape[0] == 0
    assert set(problem.interpolator.constraints) == {'value'}


def test_collapsed_quadrature_preserves_full_3d_extrusion_objective():
    problem = TwoContactExperiment(8)
    rng = np.random.default_rng(754)
    x = rng.normal(size=problem.transform.shape[1])
    u = problem.transform @ x
    original = NodeDerivatives.build(problem.grid)

    def energy(ops, normalised):
        q2 = sum((g @ u) ** 2 for g in ops.gradient) + 0.03**2 if normalised else 1
        return sum(
            np.sum(ops.volume * (h @ u) ** 2 / q2) * (1 if j < 3 else 2)
            for j, h in enumerate(ops.hessian)
        )

    for normalised in (False, True):
        np.testing.assert_allclose(
            energy(original, normalised), energy(problem.derivatives, normalised), rtol=2e-13
        )
    np.testing.assert_allclose(original.gradient[1] @ u, 0, atol=1e-13)
    np.testing.assert_allclose(original.hessian[1] @ u, 0, atol=1e-13)


def test_reduced_nonlinear_gradient_for_two_contact_field():
    problem = TwoContactExperiment(8)
    rng = np.random.default_rng(877)
    nodes = problem.grid.nodes[problem.free]
    x = (nodes[:, 2] + 0.25) / 1.35 + 0.1 * np.sin(nodes[:, 0])
    direction = rng.normal(size=len(x))
    direction /= np.linalg.norm(direction)
    _, gradient = problem.energy_gradient(
        problem.transform @ x, 0.001, 0.03 * problem.gradient_reference
    )
    reduced_gradient = problem.transform.T @ gradient
    step = 1e-6
    plus = problem.energy_gradient(
        problem.transform @ (x + step * direction), 0.001, 0.03 * problem.gradient_reference
    )[0]
    minus = problem.energy_gradient(
        problem.transform @ (x - step * direction), 0.001, 0.03 * problem.gradient_reference
    )[0]
    np.testing.assert_allclose(reduced_gradient @ direction, (plus - minus) / (2 * step), rtol=2e-7)


def test_preconditioned_optimisation_reduces_actual_energy_and_preserves_extrusion():
    problem = TwoContactExperiment(12)
    native = problem.solve_native(0.001)
    initial_energy = problem.energy_gradient(
        native.values, 0.001, 0.03 * problem.gradient_reference
    )[0]
    result = problem.solve_normalised(native.values, 0.001, max_evaluations=500)
    assert result.success
    assert result.objective < initial_energy
    assert result.optimality < 1e-5
    np.testing.assert_allclose(
        result.values, problem.transform @ result.values[problem.free], atol=1e-13
    )
