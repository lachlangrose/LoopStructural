"""Two-contact extrapolation experiment using real 3D FDI, exactly extruded in y.

Run with ``python -m loop_interpolation.experimental.benchmark_two_contacts``.
The data consist only of a flat zero contact and a rounded V-shaped unit
contact. Two distinct values fix the nonzero field scale; no gradient anchor,
direction observation, Eikonal term, or target gradient magnitude is added.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import numpy as np
from loop_common.supports import StructuredGrid
from scipy import linalg, sparse
from scipy.optimize import minimize

from .._finite_difference_interpolator import FiniteDifferenceInterpolator
from .gradient_smoothness import FitResult, GradientSmoothnessExperiment, NodeDerivatives


def upper_contact(x: np.ndarray) -> np.ndarray:
    """Smooth V-like valley resembling the supplied illustration."""
    return 1.1 - 0.95 * np.exp(-((x / 0.35) ** 2))


def rotation(angle: float) -> np.ndarray:
    """Rotate the two-dimensional geometry about the extrusion axis."""
    theta = np.deg2rad(angle)
    return np.array(
        [[np.cos(theta), 0, np.sin(theta)], [0, 1, 0], [-np.sin(theta), 0, np.cos(theta)]]
    )


class TwoContactExperiment(GradientSmoothnessExperiment):
    """Reuse the verified objective/solvers with an exact extrusion reduction.

    Every depth plane has identical unknowns. This is a true 2D scalar field
    on the real 3D FDI support, with a unit-thickness integration region. FDI
    assembles the contact rows and native regularisation. The matched first
    and second derivatives are the same collocated physical operators used
    in the original experiment. No tetrahedral mesh is constructed.
    """

    def __init__(self, cells: int, angle: float = 0) -> None:
        self.grid = StructuredGrid(
            origin=np.array([-4.0, -0.5, -4.0]),
            nsteps_cells=np.array([cells, 3, cells]),
            step_vector=np.array([8 / cells, 1 / 3, 8 / cells]),
        )
        self.derivatives = NodeDerivatives.build(self.grid)
        self.rotation = rotation(angle)
        x = np.linspace(-1, 1, 21)
        lower = np.column_stack([x, np.zeros(len(x)), np.full(len(x), -0.25)])
        upper = np.column_stack([x, np.zeros(len(x)), upper_contact(x)])
        points = np.vstack([lower, upper]) @ self.rotation.T
        targets = np.repeat([0.0, 1.0], len(x))
        self.observations = np.column_stack([points, targets])
        self.interpolator = FiniteDifferenceInterpolator(self.grid)
        self.interpolator.set_value_constraints(self.observations)
        self.interpolator.reset()
        self.interpolator.add_value_constraints(1.0)
        self.data_matrix, self.data_target = self.interpolator.build_matrix()
        self.data_matrix = self.data_matrix.tocsr()
        nx, ny, nz = self.grid.nsteps
        index = self.grid.global_index_to_node_index(np.arange(self.grid.n_nodes))
        column = index[:, 0] + nx * index[:, 2]
        self.transform = sparse.csr_matrix(
            (np.ones(self.grid.n_nodes), (np.arange(self.grid.n_nodes), column)),
            shape=(self.grid.n_nodes, nx * nz),
        )
        self.free = (np.arange(nx)[:, None] + nx * ny * np.arange(nz)[None, :]).ravel(order="F")
        # On this exact extrusion, each depth plane has identical derivatives.
        # Collapse only the repeated integration rows, summing their quadrature
        # weights. This is the same restricted objective, with four times fewer
        # residual rows. Unknowns and all physical x/z boundary stencils stay.
        ops = self.derivatives
        volume = ops.volume.reshape((nx, ny, nz), order="F").sum(axis=1).ravel(order="F")
        self.derivatives = NodeDerivatives(
            tuple(m[self.free] for m in ops.gradient),
            tuple(m[self.free] for m in ops.hessian),
            volume,
            ops.locations[self.free],
        )
        self.offset = np.zeros(self.grid.n_nodes)
        self.contact_weight = self.direction_weight = 1.0
        self.gradient_reference = float(1 / np.median(upper_contact(x) + 0.25))
        # Inherited solver uses this attribute solely to scale epsilon. There
        # is no gradient constraint in this data-only, two-isovalue experiment.
        self.anchor_magnitude = self.gradient_reference
        self._whitening = {}

    def world(self, x: np.ndarray, z: np.ndarray) -> np.ndarray:
        return np.column_stack([x, np.zeros_like(x), z]) @ self.rotation.T

    def solve_normalised(
        self,
        initial: np.ndarray,
        strength: float,
        epsilon_ratio: float = 0.03,
        max_evaluations: int = 1000,
        tolerance: float = 1e-9,
    ) -> FitResult:
        """Optimise the full quotient objective in baseline-whitened variables.

        Cholesky is a change of variables using the matched linear Hessian,
        not an additional scientific penalty. L-BFGS differentiates both the
        numerator and denominator using the verified actual-objective gradient.
        No bounds, frozen weights, or objective ridge are introduced.
        """
        started = perf_counter()
        if strength not in self._whitening:
            _, matrix = self.residual_jacobian(self.offset, strength, 1.0, False)
            reduced = matrix @ self.transform
            self._whitening[strength] = linalg.cholesky((reduced.T @ reduced).toarray(), lower=True)
        factor = self._whitening[strength]
        epsilon = epsilon_ratio * self.gradient_reference
        history = []

        def objective(whitened: np.ndarray) -> tuple:
            x = linalg.solve_triangular(factor.T, whitened, lower=False, check_finite=False)
            u = self.transform @ x
            energy, gradient = self.energy_gradient(u, strength, epsilon)
            reduced_gradient = np.asarray(self.transform.T @ gradient).ravel()
            transformed_gradient = linalg.solve_triangular(
                factor, reduced_gradient, lower=True, check_finite=False
            )
            history.append([energy, float(np.max(np.abs(reduced_gradient)))])
            return energy, transformed_gradient

        initial_x = factor.T @ initial[self.free]
        result = minimize(
            objective,
            initial_x,
            method="L-BFGS-B",
            jac=True,
            options=dict(
                gtol=tolerance,
                ftol=1e-14,
                maxiter=max_evaluations,
                maxfun=max_evaluations * 3,
                maxls=50,
                maxcor=30,
            ),
        )
        x = linalg.solve_triangular(factor.T, result.x, lower=False, check_finite=False)
        u = self.transform @ x
        energy, gradient = self.energy_gradient(u, strength, epsilon)
        optimality = float(np.max(np.abs(self.transform.T @ gradient)))
        return FitResult(
            u,
            bool(result.success),
            str(result.message),
            perf_counter() - started,
            result.nfev,
            energy,
            optimality,
            history,
        )


def contour_roots(
    problem: TwoContactExperiment, values: np.ndarray, x: np.ndarray, level: float
) -> tuple:
    """Find the crossing nearest a declared reference extension, and count all."""
    z = np.linspace(-3.8, 3.8, 401)
    xx, zz = np.meshgrid(x, z, indexing="ij")
    points = problem.world(xx.ravel(), zz.ravel())
    valid = problem.grid.inside(points).reshape(xx.shape)
    safe = np.clip(points, problem.grid.origin + 1e-9, problem.grid.maximum - 1e-9)
    field = problem.grid.evaluate_value(safe, values).reshape(xx.shape) - level
    crossings = ((field[:, :-1] < 0) != (field[:, 1:] < 0)) & valid[:, :-1] & valid[:, 1:]
    count = crossings.sum(axis=1)
    target = np.full(len(x), -0.25) if level == 0 else upper_contact(x)
    middle = (z[:-1] + z[1:]) / 2
    score = np.where(crossings, np.abs(middle[None, :] - target[:, None]), np.inf)
    interval = score.argmin(axis=1)
    lo, hi = z[interval].copy(), z[interval + 1].copy()
    flo = field[np.arange(len(x)), interval].copy()
    for _ in range(30):
        mid = (lo + hi) / 2
        point = np.clip(
            problem.world(x, mid), problem.grid.origin + 1e-9, problem.grid.maximum - 1e-9
        )
        fmid = problem.grid.evaluate_value(point, values) - level
        same = flo * fmid > 0
        lo = np.where(same, mid, lo)
        flo = np.where(same, fmid, flo)
        hi = np.where(same, hi, mid)
    root = (lo + hi) / 2
    root[count == 0] = np.nan
    return root, count


def evaluate(problem: TwoContactExperiment, values: np.ndarray) -> tuple:
    x = np.linspace(-3.5, 3.5, 281)
    zero, zero_count = contour_roots(problem, values, x, 0.0)
    unit, unit_count = contour_roots(problem, values, x, 1.0)
    observed = np.abs(x) <= 1
    extrapolated = np.abs(x) >= 1.2
    residual = (
        problem.grid.evaluate_value(problem.observations[:, :3], values)
        - problem.observations[:, 3]
    )
    gradient = problem.grid.evaluate_gradient(problem.world(x, np.full_like(x, -0.25)), values)
    q_zero_reference = np.linalg.norm(gradient, axis=1)

    # The extension below is a declared benchmark reference, not the unique
    # geometry implied by the finite contact observations.
    def rms(v: np.ndarray) -> float | None:
        return float(np.sqrt(np.nanmean(v * v))) if np.any(np.isfinite(v)) else None

    q = np.linalg.norm(np.column_stack([g @ values for g in problem.derivatives.gradient]), axis=1)
    metrics = {
        "contact_rms": rms(residual),
        "contact_max": float(np.max(np.abs(residual))),
        "zero_interpolation_rms": rms((zero + 0.25)[observed]),
        "zero_extrapolation_rms": rms((zero + 0.25)[extrapolated]),
        "unit_interpolation_rms": rms((unit - upper_contact(x))[observed]),
        "unit_reference_extrapolation_rms": rms((unit - upper_contact(x))[extrapolated]),
        "zero_extrapolation_coverage": float(np.mean(np.isfinite(zero[extrapolated]))),
        "unit_extrapolation_coverage": float(np.mean(np.isfinite(unit[extrapolated]))),
        "zero_multiple_crossing_fraction": float(np.mean(zero_count > 1)),
        "unit_multiple_crossing_fraction": float(np.mean(unit_count > 1)),
        "grid_q_min": float(q.min()),
        "grid_q_max": float(q.max()),
        "grid_q_below_epsilon_fraction": float(
            np.average(q < 0.03 * problem.gradient_reference, weights=problem.derivatives.volume)
        ),
        "zero_reference_far_q_mean": float(np.mean(q_zero_reference[extrapolated])),
    }
    return metrics, dict(
        x=x,
        zero=zero,
        unit=unit,
        zero_crossings=zero_count,
        unit_crossings=unit_count,
        q_on_flat_reference=q_zero_reference,
    )


def plot(rows: list, output: Path, config: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from matplotlib.lines import Line2D

    methods = ("native", "baseline", "normalised")
    names = {
        "native": "Native FDI reference",
        "baseline": "Matched ordinary Hessian",
        "normalised": "Gradient-normalised",
    }
    colours = {"native": "#7f858d", "baseline": "#2467a8", "normalised": "#d56725"}
    cells = max(config["resolutions"])
    strength = 0.001
    for angle in config["angles"]:
        selected = [
            r
            for r in rows
            if r["cells"] == cells
            and r["angle"] == angle
            and r["strength"] == strength
            and r["start"] == "native"
            and r["epsilon_ratio"] in (None, 0.03)
        ]
        if len(selected) != 3:
            continue
        problem = TwoContactExperiment(cells, angle)
        xx, zz = np.meshgrid(
            np.linspace(-4 + 1e-8, 4 - 1e-8, 401), np.linspace(-4 + 1e-8, 4 - 1e-8, 401)
        )
        # Plot local geometry coordinates; rotate evaluation points into the
        # same fixed world support. White corners are outside the support.
        query = problem.world(xx.ravel(), zz.ravel())
        valid = problem.grid.inside(query).reshape(xx.shape)
        query = np.clip(query, problem.grid.origin + 1e-8, problem.grid.maximum - 1e-8)
        fig, axes = plt.subplots(2, 3, figsize=(13, 8.8), layout="constrained")
        levels = [-2, -1, 0, 0.25, 0.5, 0.75, 1, 2, 3]
        far_lines, far_q = [], []
        for j, method in enumerate(methods):
            row = next(r for r in selected if r["method"] == method)
            data = np.load(output / row["samples"])
            u = data["values"]
            field = problem.grid.evaluate_value(query, u).reshape(xx.shape)
            q = np.linalg.norm(problem.grid.evaluate_gradient(query, u), axis=1).reshape(xx.shape)
            field[~valid] = np.nan
            q[~valid] = np.nan
            for i, extent in enumerate(((-4, 4, -4, 4), (-1.5, 1.5, -0.8, 1.7))):
                ax = axes[i, j]
                image = ax.pcolormesh(
                    xx,
                    zz,
                    q,
                    cmap="viridis",
                    norm=LogNorm(0.05, 5),
                    shading="nearest",
                    rasterized=True,
                )
                contours = ax.contour(
                    xx, zz, field, levels=levels, colors="#333333", linewidths=0.7
                )
                ax.clabel(contours, fmt="%g", fontsize=7)
                ax.contour(xx, zz, field, levels=[0], colors="#f5d938", linewidths=2)
                ax.contour(xx, zz, field, levels=[1], colors="#e98af2", linewidths=2)
                local = problem.observations[:, :3] @ problem.rotation
                ax.scatter(
                    local[:21, 0],
                    local[:21, 2],
                    color="#f5d938",
                    edgecolors="black",
                    linewidths=0.25,
                    s=12,
                    zorder=5,
                )
                ax.scatter(
                    local[21:, 0],
                    local[21:, 2],
                    color="#e98af2",
                    edgecolors="black",
                    linewidths=0.25,
                    s=12,
                    zorder=5,
                )
                ax.axvline(-1, color="white", ls=":", lw=0.8, alpha=0.7)
                ax.axvline(1, color="white", ls=":", lw=0.8, alpha=0.7)
                ax.set(xlim=extent[:2], ylim=extent[2:], xlabel="local x", ylabel="local z")
                ax.set_aspect("equal")
            axes[0, j].set_title(names[method] + f"\ncontact RMS = {row['contact_rms']:.3g}")
            axes[1, j].set_title("Contact-region detail", fontsize=10)
            far_lines.append((method, data['x'], data['zero'], data['unit']))
            far_q.append((method, data['x'], data['q_on_flat_reference']))
        cb = fig.colorbar(image, ax=axes, shrink=0.75, pad=0.02)
        cb.set_label(r"Gradient magnitude $\|\nabla f\|$ (log scale)")
        cb.set_ticks([0.05, 0.1, 0.2, 0.5, 1, 2, 5])
        cb.set_ticklabels(["0.05", "0.1", "0.2", "0.5", "1", "2", "5"])
        fig.suptitle(
            f"Flat contact = 0, rounded V contact = 1 | {cells} cells | geometry angle {angle:g} degrees\n"
            "Contacts only, no prescribed gradient | lambda=0.001, epsilon=0.03 x reference gradient\n"
            "Yellow: level 0 | magenta: level 1 | dotted lines: observation extent",
            fontsize=11,
        )
        fig.savefig(output / f"two_contacts_n{cells}_a{angle:g}.png", dpi=170)
        fig.savefig(output / f"two_contacts_n{cells}_a{angle:g}.svg")
        plt.close(fig)

        fig, axes = plt.subplots(1, 3, figsize=(13, 3.7), layout="constrained")
        for method, x, zero, unit in far_lines:
            axes[0].plot(x, zero + 0.25, color=colours[method], label=names[method])
            axes[1].plot(x, unit - upper_contact(x), color=colours[method])
        for method, x, q in far_q:
            axes[2].plot(x, q, color=colours[method])
        reference_q = 1 / (upper_contact(x) + 0.25)
        axes[2].plot(x, reference_q, color="black", ls="--", lw=1, label="Declared reference field")
        for ax, title in zip(
            axes,
            (
                "Level 0: departure from flat extension",
                "Level 1: departure from chosen extension",
                "Gradient on the flat reference line",
            ),
        ):
            ax.axvspan(-1, 1, color="#cccccc", alpha=0.25)
            ax.set(xlabel="local x", title=title)
            ax.grid(alpha=0.2)
        axes[0].axhline(0, color="black", lw=0.7)
        axes[1].axhline(0, color="black", lw=0.7)
        axes[0].set_ylabel("Vertical displacement")
        axes[1].set_ylabel("Vertical displacement")
        axes[2].set_ylabel(r"$\|\nabla f\|$")
        handles = [Line2D([], [], color=colours[m], label=names[m]) for m in methods]
        handles.append(Line2D([], [], color="black", ls="--", label="Declared reference field"))
        fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False, fontsize=9)
        fig.suptitle(
            f"Extrapolation diagnostics | {cells} cells | {angle:g} degrees | shaded x-range contains contacts",
            fontsize=11,
        )
        fig.savefig(output / f"extrapolation_n{cells}_a{angle:g}.png", dpi=170)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/experiments/two_contact_extrapolation")
    )
    parser.add_argument("--resolutions", type=int, nargs="+", default=[32, 48])
    parser.add_argument("--angles", type=float, nargs="+", default=[0, 23])
    parser.add_argument("--strengths", type=float, nargs="+", default=[0.0001, 0.001, 0.01])
    parser.add_argument("--epsilon-ratios", type=float, nargs="+", default=[0.01, 0.03, 0.1])
    parser.add_argument("--max-evaluations", type=int, default=180)
    parser.add_argument("--plot-only", action="store_true")
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    if args.plot_only:
        plot(
            json.loads((output / 'metrics.json').read_text()),
            output,
            json.loads((output / 'config.json').read_text()),
        )
        return
    (output / 'samples').mkdir(exist_ok=True)
    config = {k: v for k, v in vars(args).items() if k not in ('output', 'plot_only')}
    config.update(
        domain=[[-4, 4], [-0.5, 0.5], [-4, 4]],
        zero_height=-0.25,
        upper_contact='1.1 - 0.95 * exp(-(x/0.35)**2)',
        observations_per_contact=21,
        observation_x_range=[-1, 1],
        extrusion='exact; all depth planes share unknowns',
        seed=None,
    )
    (output / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    import scipy

    (output / 'environment.json').write_text(
        json.dumps(
            dict(
                python=sys.version,
                numpy=np.__version__,
                scipy=scipy.__version__,
                platform=platform.platform(),
            ),
            indent=2,
        )
        + '\n'
    )
    rows = []
    for cells in args.resolutions:
        for angle in args.angles:
            problem = TwoContactExperiment(cells, angle)
            np.savez_compressed(
                output / 'samples' / f'observations_n{cells}_a{angle:g}.npz',
                contacts=problem.observations,
            )
            for strength in args.strengths:
                native = problem.solve_native(strength)
                baseline = problem.solve_baseline(strength)
                jobs = [('native', None, 'native', native), ('baseline', None, 'native', baseline)]
                for eps in args.epsilon_ratios:
                    jobs.append(
                        (
                            'normalised',
                            eps,
                            'native',
                            problem.solve_normalised(
                                native.values, strength, eps, args.max_evaluations
                            ),
                        )
                    )
                if cells == max(args.resolutions) and strength == 0.001:
                    jobs.append(
                        (
                            'normalised',
                            0.03,
                            'matched_baseline',
                            problem.solve_normalised(
                                baseline.values, strength, 0.03, args.max_evaluations
                            ),
                        )
                    )
                for method, eps, start, fit in jobs:
                    metrics, samples = evaluate(problem, fit.values)
                    label = f'n{cells}_a{angle:g}_l{strength:g}_{method}_eps{eps}_{start}'
                    relative = Path('samples') / f'{label}.npz'
                    np.savez_compressed(output / relative, values=fit.values, **samples)
                    result = asdict(fit)
                    result.pop('values')
                    if method == 'normalised':
                        initial = native.values if start == 'native' else baseline.values
                        result['initial_objective'] = problem.energy_gradient(
                            initial, strength, eps * problem.gradient_reference
                        )[0]
                    row = dict(
                        cells=cells,
                        angle=angle,
                        strength=strength,
                        method=method,
                        epsilon_ratio=eps,
                        epsilon_reference=problem.gradient_reference,
                        start=start,
                        samples=relative.as_posix(),
                        **result,
                        **metrics,
                    )
                    rows.append(row)
                    print(
                        f"{label}: contact={metrics['contact_rms']:.3g}, zero extrapolation={metrics['zero_extrapolation_rms']:.3g}, gradient={fit.optimality:.3g}, success={fit.success}, {fit.runtime:.2f}s",
                        flush=True,
                    )
                (output / 'metrics.json').write_text(
                    json.dumps(rows, indent=2, allow_nan=False) + '\n'
                )
    keys = sorted(set().union(*(r.keys() for r in rows)) - {'history'})
    with (output / 'metrics.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        writer.writerows({k: r.get(k) for k in keys} for r in rows)
    plot(rows, output, config)


if __name__ == '__main__':
    main()
