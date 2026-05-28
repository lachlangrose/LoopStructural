"""PyVista debug plot for interpolation isosurface and inequality constraints.

Creates a small model, solves with ADMM, and saves a screenshot with:
- interpolated scalar field isosurface (value=0)
- value constraints and normal constraints
- inequality points, colored by violation magnitude
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pyvista as pv

from loop_common.geometry import BoundingBox
from loop_interpolation import InterpolatorBuilder

from interpolation import (
    make_x0_initializer,
    make_constraints,
    make_inequality_constraints,
)


def _parse_int_list(spec: str | None) -> list[int] | None:
    if spec is None:
        return None
    vals = [s.strip() for s in str(spec).split(",") if s.strip()]
    if not vals:
        return None
    return [int(v) for v in vals]


def _default_levels(final_nelements: int) -> list[int]:
    candidates = [
        max(2000, final_nelements // 8),
        max(4000, final_nelements // 4),
        max(8000, final_nelements // 2),
        final_nelements,
    ]
    levels = sorted(set(int(v) for v in candidates if int(v) > 0))
    if levels[-1] != int(final_nelements):
        levels.append(int(final_nelements))
    return levels


def _default_nmajor_by_level(total_nmajor: int, nlevels: int) -> list[int]:
    if nlevels <= 0:
        raise ValueError("nlevels must be positive")
    if total_nmajor < nlevels:
        raise ValueError("nmajor must be >= number of multilevel stages")
    weights = np.arange(1, nlevels + 1, dtype=float)
    scaled = weights / np.sum(weights) * float(total_nmajor)
    alloc = np.floor(scaled).astype(int)
    alloc = np.maximum(alloc, 1)
    while int(np.sum(alloc)) < int(total_nmajor):
        frac = scaled - np.floor(scaled)
        idx = int(np.argmax(frac))
        alloc[idx] += 1
        frac[idx] = -1.0
    while int(np.sum(alloc)) > int(total_nmajor):
        idx = int(np.argmax(alloc))
        if alloc[idx] <= 1:
            break
        alloc[idx] -= 1
    return alloc.tolist()


def _element_gradient_data(interpolator):
    support = interpolator.support
    if not hasattr(support, "elements") or not hasattr(support, "barycentre"):
        return None

    element_indices = np.arange(support.elements.shape[0], dtype=int)
    _, gradient, elements, inside = support.get_element_gradient_for_location(
        support.barycentre[element_indices]
    )
    inside = np.asarray(inside, dtype=bool)
    if inside.shape[0] != gradient.shape[0]:
        inside = np.ones(gradient.shape[0], dtype=bool)
    if not np.any(inside):
        return None

    element_ids = np.asarray(elements, dtype=int)[inside]
    gradient = np.asarray(gradient, dtype=float)[inside]
    idc = np.asarray(support.elements[element_ids], dtype=int)
    values = np.asarray(interpolator.c[idc], dtype=float)
    grad_vec = np.einsum("ijk,ik->ij", gradient, values)
    grad_norm = np.linalg.norm(grad_vec, axis=1)
    valid = np.isfinite(grad_norm) & (grad_norm > 1e-10)
    if not np.any(valid):
        return None

    volume = np.ones(np.sum(valid), dtype=float)
    if hasattr(support, "element_size"):
        raw_volume = np.asarray(support.element_size, dtype=float)
        if raw_volume.ndim == 0:
            volume = np.full(np.sum(valid), float(raw_volume), dtype=float)
        else:
            volume = raw_volume[element_ids][valid]
        volume = np.maximum(volume, 1e-12)

    return {
        "gradient": gradient[valid],
        "grad_vec": grad_vec[valid],
        "grad_norm": grad_norm[valid],
        "idc": idc[valid],
        "volume": volume,
    }


def _apply_constant_norm_polish(
    interpolator,
    solver_kwargs: dict,
    iterations: int,
    base_weight: float,
    target_norm: float | None = None,
):
    if iterations <= 0 or base_weight <= 0.0:
        return interpolator

    stable_solver_kwargs = dict(solver_kwargs)
    stable_solver_kwargs.pop("x0", None)

    for i in range(iterations):
        grad_data = _element_gradient_data(interpolator)
        if grad_data is None:
            print("Constant-norm polish skipped: gradient rows unavailable.")
            break

        grad_norm = grad_data["grad_norm"]
        if target_norm is None:
            norm_target = float(np.median(grad_norm))
        else:
            norm_target = float(target_norm)

        unit_grad = grad_data["grad_vec"] / grad_norm[:, None]
        A = np.einsum("ij,ijk->ik", unit_grad, grad_data["gradient"])
        A = A / grad_data["volume"][:, None]
        b = np.full(A.shape[0], norm_target, dtype=float) / grad_data["volume"]
        iter_weight = float(base_weight) * float(i + 1)

        interpolator.add_constraints_to_least_squares(
            A,
            b,
            grad_data["idc"],
            w=np.full(A.shape[0], iter_weight, dtype=float),
            name=f"constant_norm_{i}",
        )

        x0_seed = np.asarray(interpolator.c[interpolator.region], dtype=float).copy()
        polish_kwargs = dict(stable_solver_kwargs)
        polish_kwargs["x0"] = lambda _support, x0=x0_seed: np.array(x0, copy=True)
        interpolator.solve_system("admm", solver_kwargs=polish_kwargs)

        updated = _element_gradient_data(interpolator)
        if updated is not None:
            print(
                "Constant-norm iter {}: target={:.3e}, grad_norm mean={:.3e}, std={:.3e}".format(
                    i + 1,
                    norm_target,
                    float(np.mean(updated["grad_norm"])),
                    float(np.std(updated["grad_norm"])),
                )
            )

    return interpolator


def build_interpolator(
    nelements: int,
    nmajor: int,
    model_update_tol: float = 0.0,
    inner_rtol_start: float | None = None,
    inner_rtol_end: float | None = None,
    inner_maxiter_start: int | None = None,
    inner_maxiter_end: int | None = None,
    inner_maxiter_schedule: str = "linear",
    constant_norm_iterations: int = 0,
    constant_norm_weight: float = 0.0,
    constant_norm_target: float | None = None,
    multilevel: bool = False,
    levels: list[int] | None = None,
    nmajor_by_level: list[int] | None = None,
):
    value_constraints, normal_constraints = make_constraints(seed=7)
    inequality_constraints = make_inequality_constraints(seed=17, n_points=250)

    solver_kwargs = {
        "admm_weight": 0.05,
        "linsys_solver": "cg",
        "rtol": 1e-3,
        "atol": 1e-4,
        "reuse_inner_solve": True,
        "active_set": False,
        "admm_abs_tol": 5e-4,
        "admm_rel_tol": 5e-3,
        "min_iterations": 4,
        "model_update_tol": model_update_tol,
    }
    if inner_rtol_start is not None:
        solver_kwargs["inner_rtol_start"] = float(inner_rtol_start)
    if inner_rtol_end is not None:
        solver_kwargs["inner_rtol_end"] = float(inner_rtol_end)
    if inner_maxiter_start is not None:
        solver_kwargs["inner_maxiter_start"] = int(inner_maxiter_start)
    if inner_maxiter_end is not None:
        solver_kwargs["inner_maxiter_end"] = int(inner_maxiter_end)
    if inner_maxiter_start is not None or inner_maxiter_end is not None:
        solver_kwargs["inner_maxiter_schedule"] = inner_maxiter_schedule
    if constant_norm_iterations > 0:
        solver_kwargs["constant_norm_iterations"] = int(constant_norm_iterations)
        solver_kwargs["constant_norm_weight"] = float(constant_norm_weight)
        if constant_norm_target is not None:
            solver_kwargs["constant_norm_target"] = float(constant_norm_target)

    if multilevel:
        levels = levels if levels is not None else _default_levels(nelements)
        levels = sorted(set(int(v) for v in levels if int(v) > 0))
        if not levels or levels[-1] != int(nelements):
            levels.append(int(nelements))
        if nmajor_by_level is None:
            nmajor_by_level = _default_nmajor_by_level(int(nmajor), len(levels))
        if len(nmajor_by_level) != len(levels):
            raise ValueError("nmajor_by_level must match number of levels")

        previous_interpolator = None
        interpolator = None
        print(f"Multilevel ADMM levels: {levels}")
        print(f"Multilevel ADMM nmajor by level: {nmajor_by_level}")

        for i, (lvl_nelements, lvl_nmajor) in enumerate(zip(levels, nmajor_by_level)):
            bbox = BoundingBox(origin=[0, 0, 0], maximum=[10, 10, 10])
            builder = InterpolatorBuilder(
                interpolatortype="FDI",
                bounding_box=bbox,
                nelements=int(lvl_nelements),
                buffer=0.2,
            )
            builder.add_value_constraints(value_constraints)
            builder.add_normal_constraints(normal_constraints)
            builder.add_inequality_constraints(inequality_constraints)
            builder.setup_interpolator(cpw=1.0, npw=1.0, gpw=0.0)
            interpolator = builder.build()

            level_kwargs = dict(solver_kwargs)
            level_kwargs["nmajor"] = int(lvl_nmajor)
            if previous_interpolator is not None:
                level_kwargs["x0"] = make_x0_initializer(previous_interpolator)
            print(
                f"Level {i}: nelements={int(lvl_nelements)} nmajor={int(lvl_nmajor)}"
            )
            interpolator.solve_system("admm", solver_kwargs=level_kwargs)
            previous_interpolator = interpolator
        assert interpolator is not None
    else:
        bbox = BoundingBox(origin=[0, 0, 0], maximum=[10, 10, 10])
        builder = InterpolatorBuilder(
            interpolatortype="FDI",
            bounding_box=bbox,
            nelements=nelements,
            buffer=0.2,
        )
        builder.add_value_constraints(value_constraints)
        builder.add_normal_constraints(normal_constraints)
        builder.add_inequality_constraints(inequality_constraints)
        builder.setup_interpolator(cpw=1.0, npw=1.0, gpw=0.0)
        interpolator = builder.build()
        solver_kwargs["nmajor"] = int(nmajor)
        interpolator.solve_system("admm", solver_kwargs=solver_kwargs)

    return interpolator, value_constraints, normal_constraints, inequality_constraints


def inequality_violation(values: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    return np.maximum(lower - values, 0.0) + np.maximum(values - upper, 0.0)


def make_plot(
    output_png: Path,
    nelements: int,
    nmajor: int,
    interactive: bool = False,
    violations_only: bool = False,
    model_update_tol: float = 0.0,
    inner_rtol_start: float | None = None,
    inner_rtol_end: float | None = None,
    inner_maxiter_start: int | None = None,
    inner_maxiter_end: int | None = None,
    inner_maxiter_schedule: str = "linear",
    constant_norm_iterations: int = 0,
    constant_norm_weight: float = 0.0,
    constant_norm_target: float | None = None,
    multilevel: bool = False,
    levels: list[int] | None = None,
    nmajor_by_level: list[int] | None = None,
):
    interpolator, value_constraints, normal_constraints, inequality_constraints = build_interpolator(
        nelements=nelements,
        nmajor=nmajor,
        model_update_tol=model_update_tol,
        inner_rtol_start=inner_rtol_start,
        inner_rtol_end=inner_rtol_end,
        inner_maxiter_start=inner_maxiter_start,
        inner_maxiter_end=inner_maxiter_end,
        inner_maxiter_schedule=inner_maxiter_schedule,
        constant_norm_iterations=constant_norm_iterations,
        constant_norm_weight=constant_norm_weight,
        constant_norm_target=constant_norm_target,
        multilevel=multilevel,
        levels=levels,
        nmajor_by_level=nmajor_by_level,
    )

    mesh = interpolator.support.vtk({"c": interpolator.c})
    contour = mesh.contour([1,0.0,-1], scalars="c")

    value_pts = pv.PolyData(value_constraints[:, :3])
    value_pts["field_value"] = value_constraints[:, 3]

    normal_pts = pv.PolyData(normal_constraints[:, :3])

    ineq_xyz = inequality_constraints[:, :3]
    ineq_lower = inequality_constraints[:, 3]
    ineq_upper = inequality_constraints[:, 4]
    flag = (ineq_lower > 0)
    ineq_pred = np.asarray(interpolator.evaluate_value(ineq_xyz), dtype=float)
    ineq_violation = inequality_violation(ineq_pred, ineq_lower, ineq_upper)

    ineq_pts = pv.PolyData(ineq_xyz)
    ineq_pts["violation"] = ineq_violation
    violating_mask = ineq_violation > 1e-6
    violating_pts = pv.PolyData(ineq_xyz[violating_mask]) if np.any(violating_mask) else None

    pv.global_theme.smooth_shading = True
    plotter = pv.Plotter(off_screen=not interactive, window_size=(1400, 1000))
    plotter.set_background("#f5f7fa")

    plotter.add_mesh(
        contour,
        color="#4f46e5",
        opacity=0.55,
        smooth_shading=True,
        specular=0.3,
        label="Isosurface c=0",
    )

    plotter.add_points(
        value_pts,
        scalars="field_value",
        cmap="coolwarm",
        point_size=10,
        render_points_as_spheres=True,
        label="Value constraints",
    )

    plotter.add_points(
        normal_pts,
        color="#111827",
        point_size=7,
        render_points_as_spheres=True,
        label="Normal constraints",
    )

    if violations_only:
        if violating_pts is not None and violating_pts.n_points > 0:
            plotter.add_points(
                violating_pts,
                color="#dc2626",
                point_size=11,
                render_points_as_spheres=True,
                label="Violating inequality points",
            )
    else:
        
        plotter.add_points(
            ineq_pts,
            scalars=flag,
            cmap="viridis",
            clim=[0.0, max(float(np.max(ineq_violation)), 1e-9)],
            point_size=9,
            render_points_as_spheres=True,
            label="Inequality points",
        )
        if violating_pts is not None and violating_pts.n_points > 0:
            plotter.add_points(
                violating_pts,
                color="#dc2626",
                point_size=12,
                render_points_as_spheres=True,
                label="Violating points",
            )

    n_violating = int(np.sum(ineq_violation > 1e-6))
    msg = (
        f"nelements={nelements}, nmajor={nmajor}\n"
        f"ineq points={ineq_xyz.shape[0]}, violating={n_violating}, "
        f"max violation={float(np.max(ineq_violation)):.3e}\n"
        f"model_update_tol={model_update_tol:.3e}, "
        f"inner_rtol=({inner_rtol_start if inner_rtol_start is not None else 'default'}, "
        f"{inner_rtol_end if inner_rtol_end is not None else 'default'})\n"
        f"constant_norm=(iters={constant_norm_iterations}, w={constant_norm_weight:.3e}, "
        f"target={constant_norm_target if constant_norm_target is not None else 'auto'})"
    )
    plotter.add_text(msg, font_size=10, position="upper_left", color="black")
    plotter.add_axes()
    plotter.add_legend(bcolor="white")

    output_png.parent.mkdir(parents=True, exist_ok=True)
    if interactive:
        try:
            plotter.show()
        except Exception as exc:
            print(f"Interactive plot failed ({exc}). Saving screenshot instead.")
            plotter.screenshot(str(output_png))
            print(f"Saved debug plot: {output_png}")
    else:
        plotter.screenshot(str(output_png))
        print(f"Saved debug plot: {output_png}")



def main():
    parser = argparse.ArgumentParser(description="Generate PyVista interpolation debug plot")
    parser.add_argument("--nelements", type=int, default=30000)
    parser.add_argument("--nmajor", type=int, default=8)
    parser.add_argument("--output", type=str, default="examples/interpolation_debug_plot.png")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open an interactive PyVista window (default saves screenshot).",
    )
    parser.add_argument(
        "--violations-only",
        action="store_true",
        help="Only render inequality points that violate bounds.",
    )
    parser.add_argument(
        "--model-update-tol",
        type=float,
        default=0.0,
        help="Stop ADMM early when the model update norm falls below this relative threshold.",
    )
    parser.add_argument(
        "--inner-rtol-start",
        type=float,
        default=None,
        help="Initial inner linear-solver relative tolerance per ADMM major step.",
    )
    parser.add_argument(
        "--inner-rtol-end",
        type=float,
        default=None,
        help="Final inner linear-solver relative tolerance per ADMM major step.",
    )
    parser.add_argument(
        "--inner-maxiter-start",
        type=int,
        default=None,
        help="Initial inner linear-solver max iterations per ADMM major step.",
    )
    parser.add_argument(
        "--inner-maxiter-end",
        type=int,
        default=None,
        help="Final inner linear-solver max iterations per ADMM major step.",
    )
    parser.add_argument(
        "--inner-maxiter-schedule",
        type=str,
        default="linear",
        choices=["linear", "geometric"],
        help="Schedule type for inner max iterations when start/end are provided.",
    )
    parser.add_argument(
        "--constant-norm-iterations",
        type=int,
        default=0,
        help="Experimental number of constant-norm polish iterations after each ADMM solve.",
    )
    parser.add_argument(
        "--constant-norm-weight",
        type=float,
        default=0.0,
        help="Experimental base weight for constant-norm polish constraints.",
    )
    parser.add_argument(
        "--constant-norm-target",
        type=float,
        default=None,
        help="Experimental target gradient norm for constant-norm polish; default uses median current norm.",
    )
    parser.add_argument(
        "--multilevel",
        action="store_true",
        help="Run ADMM on progressively finer supports with warm-start transfer.",
    )
    parser.add_argument(
        "--levels",
        type=str,
        default=None,
        help="Comma-separated nelements levels for multilevel mode, e.g. 10000,30000,100000.",
    )
    parser.add_argument(
        "--nmajor-by-level",
        type=str,
        default=None,
        help="Comma-separated major iterations per level, e.g. 20,40,80.",
    )
    args = parser.parse_args()

    levels = _parse_int_list(args.levels)
    nmajor_by_level = _parse_int_list(args.nmajor_by_level)

    make_plot(
        output_png=Path(args.output),
        nelements=args.nelements,
        nmajor=args.nmajor,
        interactive=args.interactive,
        violations_only=args.violations_only,
        model_update_tol=args.model_update_tol,
        inner_rtol_start=args.inner_rtol_start,
        inner_rtol_end=args.inner_rtol_end,
        inner_maxiter_start=args.inner_maxiter_start,
        inner_maxiter_end=args.inner_maxiter_end,
        inner_maxiter_schedule=args.inner_maxiter_schedule,
        constant_norm_iterations=args.constant_norm_iterations,
        constant_norm_weight=args.constant_norm_weight,
        constant_norm_target=args.constant_norm_target,
        multilevel=args.multilevel,
        levels=levels,
        nmajor_by_level=nmajor_by_level,
    )


if __name__ == "__main__":
    main()
