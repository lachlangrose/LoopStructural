"""Matched, physically scaled FD smoothness objectives for small experiments.

This module deliberately leaves the production FDI setup and solvers alone.
Contact and direction rows come from FDI, including its row normalisation.
The regulariser instead uses physical node derivatives without row scaling.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from loop_common.supports import StructuredGrid
from scipy import linalg, sparse
from scipy.optimize import least_squares
from scipy.sparse.linalg import spsolve

from .._finite_difference_interpolator import FiniteDifferenceInterpolator


def _axis_derivatives(n: int, h: float) -> tuple[sparse.csr_matrix, sparse.csr_matrix]:
    """Second order accurate node differences, including one-sided boundaries."""
    first = sparse.lil_matrix((n, n))
    second = sparse.lil_matrix((n, n))
    for i in range(n):
        if i == 0:
            first[i, :3] = np.array([-3, 4, -1]) / (2 * h)
            second[i, :4] = np.array([2, -5, 4, -1]) / h**2
        elif i == n - 1:
            first[i, -3:] = np.array([1, -4, 3]) / (2 * h)
            second[i, -4:] = np.array([-1, 4, -5, 2]) / h**2
        else:
            first[i, i - 1 : i + 2] = np.array([-1, 0, 1]) / (2 * h)
            second[i, i - 1 : i + 2] = np.array([1, -2, 1]) / h**2
    return first.tocsr(), second.tocsr()


@dataclass
class NodeDerivatives:
    """Collocated gradient and Hessian on a real axis-aligned FDI support.

    Hessian order is xx, yy, zz, xy, xz, yz. Mixed derivatives are the
    tensor products of first differences. V is tensor trapezoid quadrature.
    A mask selects integration nodes only; it does not remove unknowns or
    truncate any stencil. The default integrates the entire support.
    """

    gradient: tuple
    hessian: tuple
    volume: np.ndarray
    locations: np.ndarray

    @classmethod
    def build(cls, grid: StructuredGrid, mask: np.ndarray | None = None) -> NodeDerivatives:
        if type(grid) is not StructuredGrid:
            raise TypeError("This experiment supports only 3D StructuredGrid FDI")
        if not np.allclose(grid.rotation_xy, np.eye(3)):
            raise ValueError("Rotate the geometry, not the support, in this experiment")
        shape = np.asarray(grid.nsteps, dtype=int)
        spacing = np.asarray(grid.step_vector, dtype=float)
        if np.any(shape < 4) or np.any(spacing <= 0):
            raise ValueError("Need at least four nodes and positive spacing on every axis")
        operators = [_axis_derivatives(int(n), h) for n, h in zip(shape, spacing)]
        identity = [sparse.eye(int(n), format="csr") for n in shape]

        def tensor(parts: list) -> sparse.csr_matrix:
            # StructuredGrid node ordering is x fastest (Fortran order).
            return sparse.kron(parts[2], sparse.kron(parts[1], parts[0]), format="csr")

        gradient, hessian = [], []
        for axis in range(3):
            for target, derivative in ((gradient, 0), (hessian, 1)):
                parts = identity.copy()
                parts[axis] = operators[axis][derivative]
                target.append(tensor(parts))
        for a, b in ((0, 1), (0, 2), (1, 2)):
            parts = identity.copy()
            parts[a], parts[b] = operators[a][0], operators[b][0]
            hessian.append(tensor(parts))
        weights = []
        for n, h in zip(shape, spacing):
            w = np.full(n, h)
            w[[0, -1]] *= 0.5
            weights.append(w)
        volume = (
            weights[0][:, None, None] * weights[1][None, :, None] * weights[2][None, None, :]
        ).ravel(order="F")
        if mask is None:
            mask = np.ones(grid.n_nodes, dtype=bool)
        mask = np.asarray(mask)
        if mask.dtype != bool or mask.shape != (grid.n_nodes,) or not np.any(mask):
            raise ValueError("mask must be a nonempty boolean vector over support nodes")
        return cls(
            tuple(m[mask] for m in gradient),
            tuple(m[mask] for m in hessian),
            volume[mask],
            grid.nodes[mask].copy(),
        )


@dataclass
class FitResult:
    """Field plus actual objective and first-order convergence diagnostics."""

    values: np.ndarray
    success: bool
    message: str
    runtime: float
    evaluations: int
    objective: float
    optimality: float
    history: list


class GradientSmoothnessExperiment:
    """One exact full gradient anchor and shared FDI contact/direction rows.

    ``contacts`` is (n, 4): xyz and scalar isovalue. ``directions`` is
    (m, 6): xyz and direction. They retain FDI's two homogeneous tangent
    equations per direction; no target magnitude is introduced. The anchor
    is imposed by eliminating three unknowns, without a penalty or ridge.
    The objective is the sum of squared residuals (no implicit factor 1/2).
    """

    def __init__(
        self,
        grid: StructuredGrid,
        contacts: np.ndarray,
        directions: np.ndarray,
        anchor_point: np.ndarray,
        anchor_gradient: np.ndarray,
        contact_weight: float = 1.0,
        direction_weight: float = 1.0,
        mask: np.ndarray | None = None,
    ) -> None:
        self.derivatives = NodeDerivatives.build(grid, mask)
        self.grid = grid
        self.anchor_point = np.asarray(anchor_point, dtype=float).reshape(1, 3)
        self.anchor_gradient = np.asarray(anchor_gradient, dtype=float).reshape(3)
        self.anchor_magnitude = float(np.linalg.norm(self.anchor_gradient))
        if not np.isfinite(self.anchor_magnitude) or self.anchor_magnitude == 0:
            raise ValueError("A finite nonzero full gradient anchor is required")
        if not all(
            np.all(grid.inside(p)) for p in (contacts[:, :3], directions[:, :3], self.anchor_point)
        ):
            raise ValueError("All observations must lie strictly inside the support")
        interp = FiniteDifferenceInterpolator(grid)
        interp.set_value_constraints(contacts.copy())
        interp.set_gradient_constraints(directions.copy())
        interp.set_normal_constraints(
            np.column_stack([self.anchor_point, self.anchor_gradient[None]])
        )
        interp.reset()
        interp.add_value_constraints(contact_weight)
        interp.add_gradient_constraints(direction_weight)
        self.data_matrix, self.data_target = interp.build_matrix()
        self.data_matrix = self.data_matrix.tocsr()
        # Use the actual FDI full-gradient assembly for the exact anchor.
        interp.constraints = {}
        interp.add_norm_constraints(1.0)
        anchor, target = interp.build_matrix()
        anchor = anchor.tocsr()
        active = np.unique(anchor.indices)
        _, _, pivot_order = linalg.qr(anchor[:, active].toarray(), pivoting=True)
        pivots = active[pivot_order[:3]]
        block = anchor[:, pivots].toarray()
        if np.linalg.matrix_rank(block) != 3:
            raise ValueError("The full gradient anchor has rank less than three")
        self.free = np.setdiff1d(np.arange(grid.n_nodes), pivots)
        self.offset = np.zeros(grid.n_nodes)
        self.offset[pivots] = linalg.solve(block, target)
        transform = sparse.lil_matrix((grid.n_nodes, len(self.free)))
        transform[self.free, np.arange(len(self.free))] = 1
        transform[pivots, :] = -linalg.solve(block, anchor[:, self.free].toarray())
        self.transform = transform.tocsr()
        self.interpolator = interp
        self.contact_weight = contact_weight
        self.direction_weight = direction_weight

    def residual_jacobian(
        self, u: np.ndarray, strength: float, epsilon: float, normalised: bool = True
    ) -> tuple[np.ndarray, sparse.csr_matrix]:
        """Evaluate residuals and the full Jacobian, including the denominator."""
        if not np.isfinite(strength) or strength < 0 or not np.isfinite(epsilon) or epsilon <= 0:
            raise ValueError("strength must be nonnegative and epsilon strictly positive")
        ops = self.derivatives
        g = np.column_stack([m @ u for m in ops.gradient])
        q2 = np.sum(g**2, axis=1) + epsilon**2 if normalised else np.ones(len(g))
        root_q = np.sqrt(q2)
        # Multiplicity two for the off-diagonal terms in the Frobenius norm.
        factors = np.sqrt(strength * ops.volume)
        denom_derivative = sum(sparse.diags(g[:, j]) @ ops.gradient[j] for j in range(3))
        residuals = [self.data_matrix @ u - self.data_target]
        jacobians = [self.data_matrix]
        for k, h in enumerate(ops.hessian):
            scale = factors * (1 if k < 3 else np.sqrt(2))
            hu = h @ u
            residuals.append(scale * hu / root_q)
            jac = sparse.diags(scale / root_q) @ h
            if normalised:
                jac -= sparse.diags(scale * hu / (q2 * root_q)) @ denom_derivative
            jacobians.append(jac)
        return np.concatenate(residuals), sparse.vstack(jacobians, format="csr")

    def energy_gradient(
        self, u: np.ndarray, strength: float, epsilon: float, normalised: bool = True
    ) -> tuple[float, np.ndarray]:
        """Actual stated objective and its derivative with respect to all nodes."""
        r, jac = self.residual_jacobian(u, strength, epsilon, normalised)
        return float(r @ r), np.asarray(2 * (jac.T @ r)).ravel()

    def _linear_fit(self, matrix: sparse.spmatrix, target: np.ndarray) -> np.ndarray:
        reduced = matrix @ self.transform
        rhs = target - matrix @ self.offset
        x = spsolve((reduced.T @ reduced).tocsc(), reduced.T @ rhs)
        if not np.all(np.isfinite(x)):
            raise RuntimeError("Linear experiment is singular; no hidden ridge is added")
        return self.offset + self.transform @ x

    def solve_baseline(self, strength: float) -> FitResult:
        """Solve the matched quadratic objective with the exact anchor."""
        start = perf_counter()
        _, matrix = self.residual_jacobian(self.offset, strength, 1.0, False)
        target = np.concatenate(
            [self.data_target, np.zeros(matrix.shape[0] - len(self.data_target))]
        )
        u = self._linear_fit(matrix, target)
        energy, grad = self.energy_gradient(u, strength, 1.0, False)
        optimality = float(np.max(np.abs(self.transform.T @ grad)))
        return FitResult(
            u,
            optimality < 1e-7,
            "sparse direct normal equations",
            perf_counter() - start,
            1,
            energy,
            optimality,
            [],
        )

    def solve_native(self, strength: float) -> FitResult:
        """Ordinary FDI rows, solved with the same exact anchor and no ridge.

        This is the native *regulariser*, not the Rust solver. Native FDI
        weights multiply residuals, so sqrt(strength) is passed to setup.
        Its lambda is not physically comparable to the matched objective.
        """
        start = perf_counter()
        interp = self.interpolator
        w = np.sqrt(strength)
        interp.setup_interpolator(
            regularisation=w,
            dx=w,
            dy=w,
            dz=w,
            cpw=self.contact_weight,
            gpw=self.direction_weight,
            npw=0.0,
        )
        matrix, target = interp.build_matrix()
        u = self._linear_fit(matrix, target)
        r = matrix @ u - target
        grad = 2 * matrix.T @ r
        optimality = float(np.max(np.abs(self.transform.T @ grad)))
        return FitResult(
            u,
            optimality < 1e-7,
            "native FDI rows, exact anchor",
            perf_counter() - start,
            1,
            float(r @ r),
            optimality,
            [],
        )

    def solve_normalised(
        self,
        initial: np.ndarray,
        strength: float,
        epsilon_ratio: float = 0.03,
        max_evaluations: int = 250,
        tolerance: float = 1e-8,
    ) -> FitResult:
        """Minimise the nonlinear residuals with analytic sparse Jacobians.

        TRF/LSMR differentiates numerator and denominator. Epsilon is a
        fraction of the prescribed gradient magnitude. No magnitude loss,
        artificial bounds, or ridge is included in the scientific objective.
        """
        start = perf_counter()
        epsilon = epsilon_ratio * self.anchor_magnitude
        cache = {}
        history = []

        def evaluate(x: np.ndarray) -> tuple:
            if "x" not in cache or not np.array_equal(x, cache["x"]):
                r, jac = self.residual_jacobian(self.offset + self.transform @ x, strength, epsilon)
                reduced = jac @ self.transform
                cache.update(x=x.copy(), r=r, jac=reduced)
                history.append([float(r @ r), float(np.max(np.abs(2 * reduced.T @ r)))])
            return cache["r"], cache["jac"]

        result = least_squares(
            lambda x: evaluate(x)[0],
            initial[self.free],
            jac=lambda x: evaluate(x)[1],
            method="trf",
            tr_solver="lsmr",
            x_scale="jac",
            ftol=tolerance,
            xtol=tolerance,
            gtol=tolerance,
            max_nfev=max_evaluations,
            tr_options={"atol": 1e-10, "btol": 1e-10, "maxiter": 2000},
        )
        u = self.offset + self.transform @ result.x
        energy, grad = self.energy_gradient(u, strength, epsilon)
        optimality = float(np.max(np.abs(self.transform.T @ grad)))
        return FitResult(
            u,
            bool(result.success),
            result.message,
            perf_counter() - start,
            result.nfev,
            energy,
            optimality,
            history,
        )
