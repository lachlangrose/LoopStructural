"""Reduced benchmark for interpolation solver performance.

This script is a fast alternative to examples/interpolation.py focused on:
- 100k unconstrained solves (LSMR vs CG)
- inequality-constrained ADMM on 20k support
- nested-vs-single ADMM comparison with small budgets
"""

from __future__ import annotations

from time import perf_counter

from loop_common.geometry import BoundingBox
from loop_interpolation import InterpolatorBuilder

from interpolation import (
    make_constraints,
    make_inequality_constraints,
    run_nested_admm_with_inequalities,
    run_single_level_admm_with_inequalities,
)


def build_interpolator(
    nelements: int,
    value_constraints,
    normal_constraints,
    inequality_constraints=None,
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
    if inequality_constraints is not None:
        builder.add_inequality_constraints(inequality_constraints)
    builder.setup_interpolator(cpw=1.0, npw=1.0, gpw=0.0)
    return builder.build()


def run_unconstrained_100k(value_constraints, normal_constraints):
    print("\n[Reduced] Unconstrained 100k (LSMR vs CG)")
    for solver in ("lsmr", "cg"):
        interpolator = build_interpolator(100_000, value_constraints, normal_constraints)
        started = perf_counter()
        interpolator.solve_system(solver, solver_kwargs={"backend": "python"})
        wall = perf_counter() - started
        timing = interpolator.get_last_solve_timing()
        print(
            "solver={:<4s} | wall={:7.3f}s | solve={:7.3f}s | total={:7.3f}s".format(
                solver,
                wall,
                timing.get("solve_seconds", float("nan")),
                timing.get("total_seconds", float("nan")),
            )
        )


def run_admm_single_20k(value_constraints, normal_constraints, inequality_constraints):
    print("\n[Reduced] ADMM single level 20k (quick config)")
    interpolator = build_interpolator(
        20_000,
        value_constraints,
        normal_constraints,
        inequality_constraints=inequality_constraints,
    )
    started = perf_counter()
    ok = interpolator.solve_system(
        "admm",
        solver_kwargs={
            "backend": "python",
            "nmajor": 12,
            "admm_weight": 0.05,
            "linsys_solver": "cg",
            "rtol": 1e-3,
            "atol": 1e-4,
            "admm_abs_tol": 5e-4,
            "admm_rel_tol": 5e-3,
            "min_iterations": 4,
            "return_history": True,
        },
    )
    wall = perf_counter() - started
    timing = interpolator.get_last_solve_timing()
    history_len = len(interpolator.solver_history) if interpolator.solver_history else 0
    print(
        "ok={} | wall={:7.3f}s | solve={:7.3f}s | total={:7.3f}s | history_len={}".format(
            ok,
            wall,
            timing.get("solve_seconds", float("nan")),
            timing.get("total_seconds", float("nan")),
            history_len,
        )
    )


def run_reduced_nested_vs_single(value_constraints, normal_constraints, inequality_constraints):
    print("\n[Reduced] Nested vs single ADMM baseline")
    nested_levels = [20_000, 50_000]
    nested_nmajor = [8, 8]

    nested = run_nested_admm_with_inequalities(
        levels=nested_levels,
        value_constraints=value_constraints,
        normal_constraints=normal_constraints,
        inequality_constraints=inequality_constraints,
        nmajor_by_level=nested_nmajor,
    )
    single = run_single_level_admm_with_inequalities(
        nelements=nested["final_nelements"],
        nmajor=nested["total_nmajor"],
        value_constraints=value_constraints,
        normal_constraints=normal_constraints,
        inequality_constraints=inequality_constraints,
    )

    nested_wall = nested["total_wall"]
    single_wall = single["wall"]
    n_v = nested["final_violation"]
    s_v = single["violation"]
    print("[Reduced] Summary")
    print(
        "wall: nested={:.3f}s, single={:.3f}s, ratio(single/nested)={:.3f}".format(
            nested_wall,
            single_wall,
            single_wall / nested_wall if nested_wall > 0 else float("nan"),
        )
    )
    print(
        "v_mean: nested={:.3e}, single={:.3e} | v_frac: nested={:.3f}, single={:.3f}".format(
            n_v["mean"],
            s_v["mean"],
            n_v["fraction_violating"],
            s_v["fraction_violating"],
        )
    )


def main():
    value_constraints, normal_constraints = make_constraints(seed=7)
    inequality_constraints = make_inequality_constraints(seed=17, n_points=180)

    print("Running reduced benchmark")
    print(f"value constraints: {value_constraints.shape[0]}")
    print(f"normal constraints: {normal_constraints.shape[0]}")
    print(f"inequality constraints: {inequality_constraints.shape[0]}")

    run_unconstrained_100k(value_constraints, normal_constraints)
    run_admm_single_20k(value_constraints, normal_constraints, inequality_constraints)
    run_reduced_nested_vs_single(value_constraints, normal_constraints, inequality_constraints)


if __name__ == "__main__":
    main()
