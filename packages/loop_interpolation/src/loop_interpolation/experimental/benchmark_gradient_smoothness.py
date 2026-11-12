"""Reproducible small synthetic comparisons; run this module with --help."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from loop_common.supports import StructuredGrid
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from skimage.measure import marching_cubes

from .gradient_smoothness import GradientSmoothnessExperiment


@dataclass
class Geometry:
    """Smooth extruded patches, rotated relative to the Cartesian support."""

    name: str
    angle: float

    @property
    def rotation(self) -> np.ndarray:
        t = np.deg2rad(self.angle)
        return np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])

    def profile(self, x: np.ndarray) -> tuple:
        if self.name == "plane":
            return np.zeros_like(x), np.zeros_like(x), np.zeros_like(x)
        if self.name == "cylinder":
            r = 1.0
            root = np.sqrt(r * r - x * x)
            return root - r, -x / root, -r * r / root**3
        return 0.07 * np.cos(4.5 * x), -0.315 * np.sin(4.5 * x), -1.4175 * np.cos(4.5 * x)

    def surface(self, xy: np.ndarray) -> tuple:
        f, slope, second = self.profile(xy[:, 0])
        points = np.column_stack([xy, f]) @ self.rotation.T
        normals = np.column_stack([-slope, np.zeros(len(xy)), np.ones(len(xy))])
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        curvature = np.abs(second) / (1 + slope * slope) ** 1.5
        return points, normals @ self.rotation.T, curvature

    def distance_normal_curvature(self, points: np.ndarray) -> tuple:
        """Exact cylinder distance or unique closest-point graph projection."""
        local = points @ self.rotation
        x, _, z = local.T
        if self.name == "cylinder":
            radial = np.column_stack([x, np.zeros(len(x)), z + 1])
            norm = np.linalg.norm(radial, axis=1)
            return norm - 1, radial / norm[:, None] @ self.rotation.T, np.ones(len(x))
        t = x.copy()
        for _ in range(20):
            f, slope, second = self.profile(t)
            delta = (t - x + (f - z) * slope) / (1 + slope * slope + (f - z) * second)
            t -= delta
            if np.max(np.abs(delta)) < 1e-13:
                break
        closest, normal, curvature = self.surface(np.column_stack([t, local[:, 1]]))
        difference = points - closest
        distance = np.linalg.norm(difference, axis=1) * np.sign(np.sum(difference * normal, axis=1))
        return distance, normal, curvature


def make_problem(name: str, cells: int, angle: float, seed: int) -> tuple:
    geometry = Geometry(name, angle)
    grid = StructuredGrid(
        origin=np.array([-0.6, -0.55, -0.32]),
        nsteps_cells=np.array([cells] * 3),
        step_vector=np.array([1.2, 1.1, 0.64]) / cells,
    )
    rng = np.random.default_rng(seed)
    xy = np.array([(x, y) for x in (-0.4, 0, 0.4) for y in (-0.4, 0, 0.4)])
    xy += rng.uniform(-0.02, 0.02, xy.shape)
    contacts, _, _ = geometry.surface(xy)
    directions, normals, _ = geometry.surface(rng.uniform(-0.42, 0.42, (7, 2)))
    anchor, anchor_normal, _ = geometry.surface(np.array([[-0.29, -0.19]]))
    problem = GradientSmoothnessExperiment(
        grid,
        np.column_stack([contacts, np.zeros(len(contacts))]),
        np.column_stack([directions, normals]),
        anchor[0],
        anchor_normal[0],
        contact_weight=1,
        direction_weight=1,
    )
    return problem, geometry, contacts, directions, normals


def _angle(gradients: np.ndarray, normals: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(gradients, axis=1)
    # Signed normals: a reversed field is reported as 180 degrees.
    cos = np.sum(gradients * normals, axis=1) / np.maximum(norm, 1e-15)
    return np.rad2deg(np.arccos(np.clip(cos, -1, 1)))


def _correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def evaluate(
    problem: GradientSmoothnessExperiment,
    geometry: Geometry,
    u: np.ndarray,
    contacts: np.ndarray,
    directions: np.ndarray,
    normals: np.ndarray,
) -> tuple:
    """Separate extracted geometry, surface field amplitude, data, and artefacts."""
    grid = problem.grid
    shape = tuple(grid.nsteps)
    # Mesh extraction is over the same full domain in every method.
    volume = u.reshape(shape, order="F")
    vertices, faces, _, _ = marching_cubes(volume, 0, spacing=tuple(grid.step_vector))
    vertices += grid.origin
    triangles = vertices[faces]
    centroids = triangles.mean(axis=1)
    areas = (
        np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
        )
        / 2
    )
    distance, truth_normal, _ = geometry.distance_normal_curvature(centroids)
    lower, upper = grid.origin + 1e-10, grid.maximum - 1e-10
    gradients = grid.evaluate_gradient(np.clip(centroids, lower, upper), u)
    angular = _angle(gradients, truth_normal)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    adjacency = coo_matrix(
        (np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(vertices), len(vertices))
    )
    components, labels = connected_components(adjacency, directed=False)
    component_area = np.bincount(labels[faces[:, 0]], weights=areas, minlength=components)

    # Withheld, fixed true-surface locations. Search along known normals for
    # all zero crossings, then refine the nearest crossing by bisection.
    xy = np.array(
        [(x, y) for x in np.linspace(-0.36, 0.36, 17) for y in np.linspace(-0.36, 0.36, 13)]
    )
    truth, normal, curvature = geometry.surface(xy)
    offsets = np.linspace(-0.18, 0.18, 73)
    rays = truth[:, None, :] + offsets[None, :, None] * normal[:, None, :]
    valid = np.all((rays > lower) & (rays < upper), axis=2)
    values = grid.evaluate_value(np.clip(rays.reshape(-1, 3), lower, upper), u).reshape(valid.shape)
    # Assign exact zeros to the positive side, so a sampled root is counted
    # once rather than in both adjacent intervals. Tangential roots without
    # a sign change are outside this particular artefact diagnostic.
    crossings = ((values[:, :-1] < 0) != (values[:, 1:] < 0)) & valid[:, :-1] & valid[:, 1:]
    count = crossings.sum(axis=1)
    available = count > 0
    score = np.where(crossings, np.abs((offsets[:-1] + offsets[1:]) / 2), np.inf)
    chosen = score.argmin(axis=1)
    lo, hi = offsets[chosen].copy(), offsets[chosen + 1].copy()
    vlo = values[np.arange(len(truth)), chosen].copy()
    for _ in range(30):
        mid = (lo + hi) / 2
        v = grid.evaluate_value(np.clip(truth + mid[:, None] * normal, lower, upper), u)
        same = v * vlo > 0
        lo = np.where(same, mid, lo)
        vlo = np.where(same, v, vlo)
        hi = np.where(same, hi, mid)
    shift = (lo + hi) / 2
    reconstructed = truth[available] + shift[available, None] * normal[available]
    surface_gradient = grid.evaluate_gradient(reconstructed, u)
    magnitude = np.linalg.norm(surface_gradient, axis=1)
    anchor_distance = np.linalg.norm(reconstructed - problem.anchor_point, axis=1)
    node_gradient = np.column_stack([m @ u for m in problem.derivatives.gradient])
    q = np.linalg.norm(node_gradient, axis=1) / problem.anchor_magnitude
    data = problem.data_matrix @ u - problem.data_target
    contact_residual = grid.evaluate_value(contacts, u)
    anchor_residual = grid.evaluate_gradient(problem.anchor_point, u)[0] - problem.anchor_gradient
    direction_gradient = grid.evaluate_gradient(directions, u)
    signed_distance, _, _ = geometry.distance_normal_curvature(grid.nodes)
    field_error = u - signed_distance
    rms = lambda a: float(np.sqrt(np.mean(a * a))) if len(a) else None
    metrics = {
        "mesh_distance_rms": float(np.sqrt(np.average(distance**2, weights=areas))),
        "mesh_distance_p95": float(np.quantile(np.abs(distance), 0.95)),
        "withheld_normal_ray_rms": rms(shift[available]),
        "withheld_coverage": float(np.mean(available)),
        "mesh_angle_mean_deg": float(np.average(angular, weights=areas)),
        "withheld_angle_mean_deg": (
            float(np.mean(_angle(surface_gradient, normal[available])))
            if np.any(available)
            else None
        ),
        "surface_q_mean": float(np.mean(magnitude)) if len(magnitude) else None,
        "surface_q_p05": float(np.quantile(magnitude, 0.05)) if len(magnitude) else None,
        "surface_q_p95": float(np.quantile(magnitude, 0.95)) if len(magnitude) else None,
        "surface_q_unit_rmse": rms(magnitude - 1),
        "surface_q_below_0p1_fraction": float(np.mean(magnitude < 0.1)) if len(magnitude) else None,
        "surface_q_curvature_correlation": _correlation(magnitude, curvature[available]),
        "surface_q_anchor_distance_correlation": _correlation(magnitude, anchor_distance),
        "contact_rms": rms(contact_residual),
        "contact_max": float(np.max(np.abs(contact_residual))),
        "anchor_gradient_residual": float(np.linalg.norm(anchor_residual)),
        "direction_angle_mean_deg": float(np.mean(_angle(direction_gradient, normals))),
        "data_energy": float(data @ data),
        "node_distance_field_rmse": rms(field_error),
        "node_q_min": float(q.min()),
        "node_q_max": float(q.max()),
        "node_q_below_0p1_fraction": float(np.average(q < 0.1, weights=problem.derivatives.volume)),
        "node_q_below_0p03_fraction": float(
            np.average(q < 0.03, weights=problem.derivatives.volume)
        ),
        "mesh_components": int(components),
        "extra_component_area_fraction": float(1 - component_area.max() / component_area.sum()),
        "multiple_normal_crossing_fraction": float(np.mean(count > 1)),
    }
    samples = dict(
        magnitude=magnitude,
        curvature=curvature[available],
        anchor_distance=anchor_distance,
        points=reconstructed,
        angular_error=_angle(surface_gradient, normal[available]),
        normal_shift=shift[available],
        vertices=vertices,
        faces=faces,
        values=u,
    )
    return metrics, samples


def plot_results(rows: list, output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = {"baseline": "#2467a8", "normalised": "#d56725", "native": "#888888"}
    epsilon_choices = {r['epsilon_ratio'] for r in rows if r['epsilon_ratio'] is not None}
    primary_epsilon = min(epsilon_choices, key=lambda e: abs(e - 0.03))
    primary = [
        r for r in rows if r["epsilon_ratio"] in (None, primary_epsilon) and r["start"] == "native"
    ]
    names = [
        name
        for name in ("plane", "cylinder", "varying")
        if any(r['geometry'] == name for r in primary)
    ]
    fig, axes = plt.subplots(len(names), 3, figsize=(12, 3.4 * len(names)), squeeze=False)
    for i, name in enumerate(names):
        for j, (metric, label) in enumerate(
            (
                ("mesh_distance_rms", "Extracted surface RMS distance"),
                ("withheld_angle_mean_deg", "Withheld normal angle (degrees)"),
                ("surface_q_unit_rmse", "Surface gradient: RMSE from 1"),
            )
        ):
            ax = axes[i, j]
            for method in ("native", "baseline", "normalised"):
                selected = [r for r in primary if r["geometry"] == name and r["method"] == method]
                for cells in sorted({r["cells"] for r in selected}):
                    for angle in sorted({r["angle"] for r in selected}):
                        line = sorted(
                            [r for r in selected if r["cells"] == cells and r["angle"] == angle],
                            key=lambda r: r["strength"],
                        )
                        ax.plot(
                            [r["strength"] for r in line],
                            [r[metric] for r in line],
                            color=colours[method],
                            alpha=0.65,
                            marker="o",
                            ls="-" if angle == min(r['angle'] for r in selected) else "--",
                            lw=1 if cells == min(r["cells"] for r in selected) else 2,
                            label=(
                                method
                                if cells == min(r["cells"] for r in selected)
                                and angle == min(r['angle'] for r in selected)
                                else None
                            ),
                        )
            ax.set_xscale("log")
            ax.set_title(f"{name}: {label}", fontsize=10)
            ax.set_xlabel("lambda (native units differ)")
            ax.grid(alpha=0.2)
    axes[0, 0].legend()
    fig.suptitle(
        "Solid: smaller angle; dashed: larger angle. Thin: coarser grid; thick: finer grid.",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(output / "comparison.png", dpi=170)
    plt.close(fig)

    selected = [
        r
        for r in primary
        if r["geometry"] == "varying"
        and r["angle"] == max(a["angle"] for a in primary)
        and r["cells"] == max(a["cells"] for a in primary)
    ]
    if selected:
        strength = sorted({r["strength"] for r in selected})[
            len({r["strength"] for r in selected}) // 2
        ]
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
        for r in selected:
            if r["strength"] != strength:
                continue
            samples = np.load(output / r["samples"])
            for ax, xkey, label in zip(
                axes[:2],
                ("curvature", "anchor_distance"),
                ("Local absolute curvature", "Distance from full gradient anchor"),
            ):
                ax.scatter(
                    samples[xkey],
                    samples["magnitude"],
                    s=8,
                    alpha=0.45,
                    color=colours[r["method"]],
                    label=r["method"],
                )
                ax.set_xlabel(label)
                ax.set_ylabel("Surface gradient magnitude")
                ax.axhline(1, color="black", lw=0.5)
            if r["history"]:
                history = np.array(r["history"])
                axes[2].semilogy(history[:, 0], color=colours[r["method"]])
        axes[0].legend()
        axes[2].set_xlabel("Nonlinear objective evaluation (includes trials)")
        axes[2].set_ylabel("Actual normalised objective")
        fig.suptitle(f"Varying curvature, rotated grid, lambda={strength:g}")
        fig.tight_layout()
        fig.savefig(output / "field_behaviour.png", dpi=170)
        plt.close(fig)

    # Show the geometry separately from the amplitude scatter plots.
    curved = [name for name in names if name != 'plane']
    angles = sorted({r['angle'] for r in primary})
    if curved:
        fig, axes = plt.subplots(
            len(curved), len(angles), figsize=(5 * len(angles), 3.4 * len(curved)), squeeze=False
        )
        seed = json.loads((output / 'config.json').read_text())['seed']
        cells = max(r['cells'] for r in primary)
        strengths = sorted({r['strength'] for r in primary})
        strength = strengths[len(strengths) // 2]
        for i, name in enumerate(curved):
            for j, angle in enumerate(angles):
                ax = axes[i, j]
                problem, geometry, _, _, _ = make_problem(name, cells, angle, seed)
                x = np.linspace(-0.6 + 1e-9, 0.6 - 1e-9, 151)
                z = np.linspace(-0.32 + 1e-9, 0.32 - 1e-9, 151)
                xx, zz = np.meshgrid(x, z)
                points = np.column_stack([xx.ravel(), np.zeros(xx.size), zz.ravel()])
                truth, _, _ = geometry.surface(
                    np.column_stack([np.linspace(-0.85, 0.85, 500), np.zeros(500)])
                )
                ax.plot(truth[:, 0], truth[:, 2], color='black', label='known surface', lw=1.5)
                for method in ('native', 'baseline', 'normalised'):
                    row = next(
                        r
                        for r in primary
                        if r['geometry'] == name
                        and r['cells'] == cells
                        and r['angle'] == angle
                        and r['strength'] == strength
                        and r['method'] == method
                    )
                    u = np.load(output / row['samples'])['values']
                    values = problem.grid.evaluate_value(points, u).reshape(xx.shape)
                    ax.contour(xx, zz, values, levels=[0], colors=[colours[method]], linewidths=1)
                    ax.plot([], [], color=colours[method], label=method)
                ax.set(
                    xlim=(-0.6, 0.6),
                    ylim=(-0.32, 0.32),
                    xlabel='x',
                    ylabel='z',
                    title=f'{name}, {angle:g} degrees, {cells} cells, lambda={strength:g}',
                )
                ax.set_aspect('equal')
        axes[0, 0].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(output / 'geometry_sections.png', dpi=170)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/gradient_smoothness"))
    parser.add_argument("--config", type=Path, help="Replay a saved config.json")
    parser.add_argument(
        "--geometries",
        nargs="+",
        default=["plane", "cylinder", "varying"],
        choices=["plane", "cylinder", "varying"],
    )
    parser.add_argument("--resolutions", nargs="+", type=int, default=[8, 12])
    parser.add_argument("--angles", nargs="+", type=float, default=[0, 23])
    parser.add_argument("--strengths", nargs="+", type=float, default=[0.0001, 0.001, 0.01])
    parser.add_argument("--epsilon-ratios", nargs="+", type=float, default=[0.01, 0.03, 0.1])
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--max-evaluations", type=int, default=180)
    parser.add_argument("--skip-start-check", action="store_true")
    parser.add_argument(
        "--reanalyse",
        action="store_true",
        help="Recompute evaluation and plots from saved fields, without solving",
    )
    args = parser.parse_args()
    if args.config:
        for key, value in json.loads(args.config.read_text()).items():
            setattr(args, key, value)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "samples").mkdir(exist_ok=True)
    if args.reanalyse:
        saved_config = json.loads((output / "config.json").read_text())
        rows = json.loads((output / "metrics.json").read_text())
        for row in rows:
            problem, geometry, contacts, directions, normals = make_problem(
                row["geometry"], row["cells"], row["angle"], saved_config["seed"]
            )
            with np.load(output / row["samples"]) as samples:
                metrics, new_samples = evaluate(
                    problem, geometry, samples["values"], contacts, directions, normals
                )
            np.savez_compressed(output / row["samples"], **new_samples)
            row.update(metrics)
        save_results(rows, output)
        return
    config = {k: v for k, v in vars(args).items() if k not in ("config", "output", "reanalyse")}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    import scipy
    import skimage

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    environment = dict(
        python=sys.version,
        numpy=np.__version__,
        scipy=scipy.__version__,
        skimage=skimage.__version__,
        platform=platform.platform(),
        git_commit=commit,
    )
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    rows = []
    for name in args.geometries:
        for cells in args.resolutions:
            for angle in args.angles:
                problem, geometry, contacts, directions, normals = make_problem(
                    name, cells, angle, args.seed
                )
                # Save the actual observations as well as the generator seed.
                case = f"{name}_n{cells}_a{angle:g}"
                np.savez_compressed(
                    output / "samples" / f"{case}_observations.npz",
                    contacts=contacts,
                    directions=directions,
                    normals=normals,
                    anchor_point=problem.anchor_point,
                    anchor_gradient=problem.anchor_gradient,
                )
                for strength in args.strengths:
                    native = problem.solve_native(strength)
                    baseline = problem.solve_baseline(strength)
                    jobs = [
                        ("native", None, "native", native),
                        ("baseline", None, "native", baseline),
                    ]
                    for eps in args.epsilon_ratios:
                        jobs.append(
                            (
                                "normalised",
                                eps,
                                "native",
                                problem.solve_normalised(
                                    native.values, strength, eps, args.max_evaluations
                                ),
                            )
                        )
                    # Bounded alternative-start probe, without asserting uniqueness.
                    if (
                        not args.skip_start_check
                        and name != "plane"
                        and cells == max(args.resolutions)
                        and angle == max(args.angles)
                        and strength == args.strengths[len(args.strengths) // 2]
                    ):
                        jobs.append(
                            (
                                "normalised",
                                0.03,
                                "matched_baseline",
                                problem.solve_normalised(
                                    baseline.values, strength, 0.03, args.max_evaluations
                                ),
                            )
                        )
                    for method, eps, start, fit in jobs:
                        metrics, samples = evaluate(
                            problem, geometry, fit.values, contacts, directions, normals
                        )
                        label = f"{case}_l{strength:g}_{method}_eps{eps}_{start}"
                        sample_path = Path("samples") / f"{label}.npz"
                        np.savez_compressed(output / sample_path, **samples)
                        initial_energy = (
                            problem.energy_gradient(
                                native.values if start == "native" else baseline.values,
                                strength,
                                (eps or 0.03) * problem.anchor_magnitude,
                            )[0]
                            if method == "normalised"
                            else None
                        )
                        row = dict(
                            geometry=name,
                            cells=cells,
                            angle=angle,
                            strength=strength,
                            method=method,
                            epsilon_ratio=eps,
                            start=start,
                            success=fit.success,
                            first_order_1e6=fit.optimality < 1e-6,
                            message=fit.message,
                            runtime_seconds=fit.runtime,
                            evaluations=fit.evaluations,
                            objective=fit.objective,
                            initial_normalised_objective=initial_energy,
                            optimality=fit.optimality,
                            history=fit.history,
                            samples=sample_path.as_posix(),
                            **metrics,
                        )
                        rows.append(row)
                        print(
                            f"{label}: distance={metrics['mesh_distance_rms']:.5g}, q-error={metrics['surface_q_unit_rmse']:.5g}, success={fit.success}, gradient={fit.optimality:.3g}, {fit.runtime:.2f}s",
                            flush=True,
                        )
                    # Incremental saving keeps expensive partial runs reviewable.
                    (output / "metrics.json").write_text(
                        json.dumps(rows, indent=2, allow_nan=False) + "\n"
                    )
    save_results(rows, output)


def save_results(rows: list, output: Path) -> None:
    """Save all scalar metrics plus objective histories and comparison plots."""
    (output / "metrics.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
    fields = [k for k in rows[0] if k != "history"]
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in rows)
    plot_results(rows, output)


if __name__ == "__main__":
    main()
