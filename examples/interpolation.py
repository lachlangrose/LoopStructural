"""Build and solve interpolation examples with increasing model complexity.

This script sweeps multiple ``nelements`` values for the FDI interpolator,
uses a curved synthetic interface, and prints an assembly-vs-solve timing
breakdown from the interpolator diagnostics.
"""

from time import perf_counter

import numpy as np

from loop_common.geometry import BoundingBox
from loop_interpolation import InterpolatorBuilder


def curved_surface(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Curved implicit interface: z = g(x, y)."""
    return (
        5.0
        + 1.4 * np.sin(0.7 * x) * np.cos(0.6 * y)
        + 0.08 * (x - 5.0) ** 2
        - 0.06 * (y - 5.0) ** 2
    )


def curved_surface_normals(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Unit normals of f(x, y, z) = z - g(x, y) = 0."""
    dg_dx = 1.4 * 0.7 * np.cos(0.7 * x) * np.cos(0.6 * y) + 0.16 * (x - 5.0)
    dg_dy = -1.4 * 0.6 * np.sin(0.7 * x) * np.sin(0.6 * y) - 0.12 * (y - 5.0)
    n = np.column_stack([-dg_dx, -dg_dy, np.ones_like(dg_dx)])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    return n


def make_constraints(seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Generate value and normal constraints for a curved geometry."""
    rng = np.random.default_rng(seed)

    # On-surface points.
    n_surface = 260
    x = rng.uniform(1.0, 9.0, size=n_surface)
    y = rng.uniform(1.0, 9.0, size=n_surface)
    z = curved_surface(x, y)

    # Above/below points to anchor field polarity around the interface.
    n_offset = 120
    xo = rng.uniform(1.0, 9.0, size=n_offset)
    yo = rng.uniform(1.0, 9.0, size=n_offset)
    zo = curved_surface(xo, yo)
    dz = 0.35

    value_on_surface = np.column_stack([x, y, z, np.zeros(n_surface)])
    value_above = np.column_stack([xo, yo, zo + dz, np.full(n_offset, 0.6)])
    value_below = np.column_stack([xo, yo, zo - dz, np.full(n_offset, -0.6)])
    value_constraints = np.vstack([value_on_surface, value_above, value_below])

    normals = curved_surface_normals(x, y)
    normal_constraints = np.column_stack([x, y, z, normals])
    return value_constraints, normal_constraints


def make_inequality_constraints(seed: int = 123, n_points: int = 450) -> np.ndarray:
    """Generate inequality bounds consistent with the curved interface.

    Constraints are resolution-independent pointwise bounds and are designed
    to resemble physically meaningful sign constraints above/below the surface.
    """
    rng = np.random.default_rng(seed)
    xyz = rng.uniform(0.5, 9.5, size=(n_points, 3))
    dz = xyz[:, 2] - curved_surface(xyz[:, 0], xyz[:, 1])

    lower = np.empty(n_points, dtype=float)
    upper = np.empty(n_points, dtype=float)

    near = np.abs(dz) <= 0.35
    above = dz > 0.35
    below = dz < -0.35
    
    lower[near], upper[near] = -0.25, 0.25
    lower[above], upper[above] = 0.10, 2.50
    lower[below], upper[below] = -2.50, -0.10

    return np.column_stack([xyz[~near], lower[~near], upper[~near]])


def inequality_violation_stats(interpolator, inequality_constraints: np.ndarray) -> dict:
    """Return summary stats for inequality feasibility on provided points."""
    pts = inequality_constraints[:, :3]
    lower = inequality_constraints[:, 3]
    upper = inequality_constraints[:, 4]
    values = np.asarray(interpolator.evaluate_value(pts), dtype=float)
    violation = np.maximum(lower - values, 0.0) + np.maximum(values - upper, 0.0)
    return {
        "mean": float(np.mean(violation)),
        "max": float(np.max(violation)),
        "fraction_violating": float(np.mean(violation > 1e-6)),
    }


def make_x0_initializer(previous_interpolator):
    """Create an ADMM x0 callable that transfers coarse solution to fine support."""

    def _x0_for_support(support) -> np.ndarray:
        x0 = np.asarray(previous_interpolator.evaluate_value(support.nodes), dtype=float)
        if x0.ndim != 1:
            x0 = x0.reshape(-1)
        x0[~np.isfinite(x0)] = 0.0
        return x0

    return _x0_for_support


def run_single_case(nelements: int, value_constraints: np.ndarray, normal_constraints: np.ndarray):
    bbox = BoundingBox(origin=[0, 0, 0], maximum=[10, 10, 10])
    builder = InterpolatorBuilder(
        interpolatortype="FDI",
        bounding_box=bbox,
        nelements=nelements,
        buffer=0.2,
    )

    builder.add_value_constraints(value_constraints)
    builder.add_normal_constraints(normal_constraints)
    builder.setup_interpolator(cpw=1.0, npw=1.0, gpw=0.0)
    interpolator = builder.build()

    started = perf_counter()
    interpolator.solve_system("lsmr", solver_kwargs={"backend": "python"})
    wall = perf_counter() - started
    timing = interpolator.get_last_solve_timing()
    return interpolator, wall, timing


def run_with_solver(
    nelements: int,
    value_constraints: np.ndarray,
    normal_constraints: np.ndarray,
    solver: str,
    tol: float | None = None,
):
    bbox = BoundingBox(origin=[0, 0, 0], maximum=[10, 10, 10])
    builder = InterpolatorBuilder(
        interpolatortype="FDI",
        bounding_box=bbox,
        nelements=nelements,
        buffer=0.2,
    )

    builder.add_value_constraints(value_constraints)
    builder.add_normal_constraints(normal_constraints)
    builder.setup_interpolator(cpw=1.0, npw=1.0, gpw=0.0)
    interpolator = builder.build()

    solver_kwargs = {"backend": "python"}
    if tol is not None:
        started = perf_counter()
        interpolator.solve_system(solver, tol=tol, solver_kwargs=solver_kwargs)
        wall = perf_counter() - started
    else:
        started = perf_counter()
        interpolator.solve_system(solver, solver_kwargs=solver_kwargs)
        wall = perf_counter() - started
    timing = interpolator.get_last_solve_timing()
    return wall, timing


def run_nested_admm_with_inequalities(
    levels: list[int],
    value_constraints: np.ndarray,
    normal_constraints: np.ndarray,
    inequality_constraints: np.ndarray,
    nmajor_by_level: list[int] | None = None,
):
    """Run coarse-to-fine ADMM with inequality constraints and transferred x0."""
    previous_interpolator = None
    final_interpolator = None
    final_violation = None
    total_wall = 0.0
    if nmajor_by_level is None:
        nmajor_by_level = [20] * len(levels)
    if len(nmajor_by_level) != len(levels):
        raise ValueError("nmajor_by_level must have the same length as levels")

    print("\nNested ADMM with inequality constraints")
    for i, nelements in enumerate(levels):
        nmajor = int(nmajor_by_level[i])
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

        solver_kwargs = {
            "backend": "python",
            "nmajor": nmajor,
            "admm_weight": 0.05,
            "linsys_solver": "lsmr",
            "btol": 1e-4,
            "atol": 0.0,
        }
        if previous_interpolator is not None:
            solver_kwargs["x0"] = make_x0_initializer(previous_interpolator)

        started = perf_counter()
        ok = interpolator.solve_system("admm", solver_kwargs=solver_kwargs)
        wall = perf_counter() - started
        total_wall += wall
        timing = interpolator.get_last_solve_timing()
        violation = inequality_violation_stats(interpolator, inequality_constraints)
        final_violation = violation

        print(
            "level={} nelements={:>7d} nmajor={:>3d} | ok={} | wall={:7.3f}s | solve={:7.3f}s | v_mean={:.3e} | v_max={:.3e} | v_frac={:.3f}".format(
                i,
                nelements,
                nmajor,
                ok,
                wall,
                timing.get("solve_seconds", float("nan")),
                violation["mean"],
                violation["max"],
                violation["fraction_violating"],
            )
        )

        previous_interpolator = interpolator
        final_interpolator = interpolator

    return {
        "interpolator": final_interpolator,
        "total_wall": total_wall,
        "final_violation": final_violation,
        "final_nelements": levels[-1],
        "final_nmajor": nmajor_by_level[-1],
        "total_nmajor": int(np.sum(nmajor_by_level)),
    }


def run_single_level_admm_with_inequalities(
    nelements: int,
    nmajor: int,
    value_constraints: np.ndarray,
    normal_constraints: np.ndarray,
    inequality_constraints: np.ndarray,
):
    """Run one ADMM solve on a single support level with inequalities."""
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

    solver_kwargs = {
        "backend": "python",
        "nmajor": int(nmajor),
        "admm_weight": 0.05,
        "linsys_solver": "lsmr",
        "btol": 1e-4,
        "atol": 0.0,
    }
    started = perf_counter()
    ok = interpolator.solve_system("admm", solver_kwargs=solver_kwargs)
    wall = perf_counter() - started
    timing = interpolator.get_last_solve_timing()
    violation = inequality_violation_stats(interpolator, inequality_constraints)

    print("\nSingle-level ADMM baseline (matched total nmajor)")
    print(
        "nelements={:>7d} nmajor={:>3d} | ok={} | wall={:7.3f}s | solve={:7.3f}s | v_mean={:.3e} | v_max={:.3e} | v_frac={:.3f}".format(
            nelements,
            nmajor,
            ok,
            wall,
            timing.get("solve_seconds", float("nan")),
            violation["mean"],
            violation["max"],
            violation["fraction_violating"],
        )
    )

    return {
        "interpolator": interpolator,
        "wall": wall,
        "violation": violation,
        "nmajor": int(nmajor),
        "nelements": int(nelements),
    }


if __name__ == "__main__":
    value_constraints, normal_constraints = make_constraints(seed=7)
    inequality_constraints = make_inequality_constraints(seed=17, n_points=450)

    cases = [20_000, 50_000, 100_000, 200_000]
    print("Running curved-geometry interpolation sweep")
    print(f"value constraints: {value_constraints.shape[0]}")
    print(f"normal constraints: {normal_constraints.shape[0]}\n")

    last_interpolator = None
    for nelements in cases:
        last_interpolator, wall, timing = run_single_case(
            nelements, value_constraints, normal_constraints
        )
        print(
            "nelements={:>7d} | wall={:7.3f}s | assembly={:7.3f}s | solve={:7.3f}s | total={:7.3f}s | nnz={}".format(
                nelements,
                wall,
                timing.get("assembly_seconds", float("nan")),
                timing.get("solve_seconds", float("nan")),
                timing.get("total_seconds", float("nan")),
                timing.get("matrix_nnz", "n/a"),
            )
        )

    print("\nSolver/tolerance comparison on medium-large case")
    largest_case = 100_000
    solver_configs = [
        ("lsmr", None),
        ("lsmr", 1e-3),
        ("cg", None),
    ]
    for solver_name, tol in solver_configs:
        wall, timing = run_with_solver(
            largest_case,
            value_constraints,
            normal_constraints,
            solver=solver_name,
            tol=tol,
        )
        tol_text = "default" if tol is None else f"{tol:g}"
        print(
            "solver={:<4s} tol={:>8s} | wall={:7.3f}s | solve={:7.3f}s | total={:7.3f}s".format(
                solver_name,
                tol_text,
                wall,
                timing.get("solve_seconds", float("nan")),
                timing.get("total_seconds", float("nan")),
            )
        )

    if last_interpolator is not None:
        last_interpolator.to_yaml("interpolator_curved.yaml")
        print("\nWrote interpolator_curved.yaml for the largest case.")

    nested_levels = [20_000, 50_000]
    nested_nmajor = [20, 20]
    nested_result = run_nested_admm_with_inequalities(
        nested_levels,
        value_constraints,
        normal_constraints,
        inequality_constraints,
        nmajor_by_level=nested_nmajor,
    )
    admm_interpolator = nested_result["interpolator"]
    if admm_interpolator is not None:
        admm_interpolator.to_yaml("interpolator_curved_nested_admm.yaml")
        print("Wrote interpolator_curved_nested_admm.yaml for nested ADMM run.")

    baseline_result = run_single_level_admm_with_inequalities(
        nelements=nested_result["final_nelements"],
        nmajor=nested_result["total_nmajor"],
        value_constraints=value_constraints,
        normal_constraints=normal_constraints,
        inequality_constraints=inequality_constraints,
    )

    nested_wall = nested_result["total_wall"]
    baseline_wall = baseline_result["wall"]
    nested_violation = nested_result["final_violation"]
    baseline_violation = baseline_result["violation"]

    print("\nNested vs single-level baseline summary")
    print(
        "wall: nested={:.3f}s, single={:.3f}s, ratio(single/nested)={:.3f}".format(
            nested_wall,
            baseline_wall,
            baseline_wall / nested_wall if nested_wall > 0 else float("nan"),
        )
    )
    print(
        "violation mean: nested={:.3e}, single={:.3e}".format(
            nested_violation["mean"],
            baseline_violation["mean"],
        )
    )
    print(
        "violation max : nested={:.3e}, single={:.3e}".format(
            nested_violation["max"],
            baseline_violation["max"],
        )
    )
    print(
        "violation frac: nested={:.3f}, single={:.3f}".format(
            nested_violation["fraction_violating"],
            baseline_violation["fraction_violating"],
        )
    )