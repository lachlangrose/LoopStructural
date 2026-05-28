# ADMM Implementation Details in loop_interpolation

This document describes the current ADMM implementation used for inequality-constrained interpolation in `loop_interpolation`.

## Scope

The ADMM path is used when:

- the interpolator is solved through `DiscreteInterpolator.solve_system("admm", solver_kwargs=...)`
- inequality constraints are present and assembled into matrix form

Primary implementation files:

- `src/loop_interpolation/_discrete_interpolator.py`
- `src/loop_interpolation/loopsolver/admm_solver.py`
- `src/loop_interpolation/loopsolver/admm_method.py`

## Problem Formulation

The solver starts from a least-squares interpolation objective with inequality constraints:

- data-fit system: `A x ~= b`
- inequality system: `xmin <= Q x <= xmax`

`A` stacks value/gradient/regularization rows from the interpolation setup.
`Q` is assembled from inequality constraints.
`bounds` stores per-row lower and upper bounds.

In ADMM form, an auxiliary variable `z` enforces box constraints on `Qx`:

- `z` is constrained to `[xmin, xmax]`
- dual variable `u` tracks consistency between `Qx` and `z`

The implementation follows scaled-form ADMM with penalty parameter `rho`.

## Entry Point: DiscreteInterpolator Integration

`DiscreteInterpolator.solve_system` dispatches to ADMM in the `solver == "admm"` branch.

High-level flow:

1. Build interpolation matrix and RHS:
   - `A, b = self.build_matrix()`
2. Optionally add ridge regularization and column scaling.
3. Build inequality matrix and bounds:
   - `Q, bounds = self.build_inequality_matrix()`
4. Extract ADMM options from `solver_kwargs` into two groups:
   - outer ADMM controls (`nmajor`, `admm_weight`, schedules, stopping)
   - inner linear solver controls (`linsys_solver`, `rtol`, `atol`, `maxiter`, etc.)
5. Call `admm_solve(A, b, Q, bounds, ...)`.
6. Store solution in `self.c` and optional iteration history in `self.solver_history`.

Notes:

- `x0` can be supplied as a callable seed initializer from support.
- ADMM kwargs are filtered against `inspect.signature(admm_solve)` so older/newer versions fail gracefully.

## admm_solve: Core Algorithm

Function: `loopsolver.admm_solver.admm_solve`

### 1) Input validation and normalization

Key checks include:

- dimensions of `A`, `Q`, `x0`, and `b` are consistent
- `bounds` has 2 or 3 columns; if 2, a third column is appended for compatibility
- `nmajor > 0`
- `model_update_tol >= 0`
- schedule names and endpoints are valid

### 2) State initialization

- `model` is initialized from `x0`
- `ADMM` helper object is created with:
  - `z = zeros(n_ie)`
  - `u = zeros(n_ie)`
- `b0` stores original data RHS
- concatenated working RHS `b` has length `A_rows + Q_rows`

### 3) Penalty and inner-solver schedules

The implementation supports scheduled controls over major iterations:

- `rho` schedule:
  - constant (`admm_weight`)
  - linear/geometric transition to `admm_weight_final`
- inner tolerance schedules:
  - `inner_rtol_start/end` (mapped to `rtol` or `btol`)
  - `inner_atol_start/end`
- inner iteration schedule:
  - `inner_maxiter_start/end` with linear or geometric interpolation

Schedules are expanded to per-major-iteration lists and injected into `linsys_solver_kwargs`.

### 4) System assembly for each rho

For each `rho`, solver builds:

- scaled inequality block: `Q_scaled = rho * Q_base`
- stacked system: `matrix = vstack([A, Q_scaled])`

For CG + full system mode (`active_set=False`), it precomputes:

- normal equations matrix `L = M^T M`
- optional diagonal preconditioner `diag(L)^{-1}`

to avoid repeating expensive products every major iteration.

### 5) Major iteration loop

Each ADMM major iteration does:

1. Update `rho` if schedule changes, with dual rescaling:
   - `u <- u * (rho_old / rho_new)`
2. Compute current stacked product:
   - `Mx = matrix @ model`
3. Build RHS for linear correction solve:
   - data part: `b_data = b0 - Mx_data`
   - inequality part:
     - `qx = Mx_ineq / rho`
     - use ADMM projection helper to update `z` and `u`
     - set RHS from `(qx - z + u)` equivalent term in scaled form
4. Solve linear correction `dx` using selected inner solver.
5. Update model: `model += dx`.
6. Compute stopping metrics and optional adaptive-rho update.

## ADMM Projection Step (z, u update)

Function: `ADMM.admm_method_iterate_admm_array` in `admm_method.py`.

Given current `x` (here represented by `qx`):

1. Form `arg = qx + u`.
2. Project `arg` into box bounds row-wise:
   - inside bounds: keep `arg`
   - below lower bound: clamp to `xmin`
   - above upper bound: clamp to `xmax`
3. Update scaled dual:
   - `u <- u + qx - z`
4. Return `z - u` helper quantity used by the caller when building RHS.

This is the proximal operator for box constraints.

## Inner Linear Solver Layer

Supported `linsys_solver` values:

- `"lsmr"`
- `"lsqr"`
- `"cg"`
- callable

The `_solve_linsys` helper handles solver-specific behavior:

- injects `x0` only if supported by the selected solver signature
- maps `btol -> rtol` for CG compatibility
- for CG:
  - uses normal equations (`M^T M dx = M^T rhs`)
  - accepts cached/precomputed LHS and RHS-normal terms
  - applies diagonal preconditioner when enabled

If `reuse_inner_solve=True`, the previous `dx` is reused as inner initial guess.

## Active-Set Mode

When `active_set=True`, ADMM can solve only a subset of inequality rows each major iteration.

Selection criteria combine:

- current violation magnitude
- distance to bounds (`active_set_padding`)
- optional hysteresis (keep previously active rows)
- min/max active set size clamps
- periodic refresh (`active_set_refresh_interval`)

Effect:

- reduces size of stacked linear system in difficult large problems
- can reduce per-iteration cost at risk of slower/less stable progress if too aggressive

## Convergence and Stopping

The implementation uses three possible stopping mechanisms.

### 1) Primal/Dual residual stopping (inequality case)

For `Q.shape[0] > 0`, each major iteration computes:

- primal residual norm: `||qx - z||`
- dual residual norm: `rho * ||z - z_prev||`
- thresholds:
  - `eps_pri = sqrt(n_ie)*admm_abs_tol + admm_rel_tol*max(||qx||, ||z||)`
  - `eps_dual = sqrt(n_ie)*admm_abs_tol + admm_rel_tol*||rho*u||`

Stop if both residual norms are below thresholds after `min_iterations`.

### 2) Model update stopping

If `model_update_tol > 0`, stop when:

- `||dx|| <= model_update_tol * max(||model||, 1.0)`

This is checked after `min_iterations`, both in inequality and no-inequality branches.

### 3) Max major iterations

If no stop criterion is met earlier, run to `nmajor`.

## Adaptive rho

If `adaptive_rho=True` and no explicit `admm_weight_final` schedule is active, `rho` is adapted by residual ratio:

- increase rho if primal residual dominates dual residual
- decrease rho if dual residual dominates primal residual
- bounded by `adaptive_rho_min` and `adaptive_rho_max`

When rho changes, dual variable is rescaled and system matrices are rebuilt.

## History Output

If `return_history=True`, `admm_solve` returns `(model, history)` where history contains per-iteration diagnostics:

- iteration index
- primal and dual norms
- stopping thresholds
- rho
- active row count (if active-set mode)
- model-update stop marker where relevant

`DiscreteInterpolator` stores this in `self.solver_history`.

## Constant-Norm Polish Interaction

After ADMM returns, `DiscreteInterpolator.solve_system` can optionally run a post-pass via:

- `constant_norm_iterations`
- `constant_norm_weight`
- `constant_norm_target`

This is not part of the ADMM inner loop itself. It adds temporary linearized gradient-magnitude constraints and calls ADMM again for polish iterations.

## Complexity and Performance Notes

Per major iteration cost is dominated by sparse linear solves.

Important levers for performance:

- `nmajor`
- inner tolerance schedules (`inner_rtol_*`, `inner_atol_*`)
- inner maxiter schedules (`inner_maxiter_*`)
- `reuse_inner_solve`
- active-set controls
- CG preconditioner toggle and shift

Observed practical behavior in this codebase:

- scheduling inner solve effort over major iterations gives large speedups
- algorithmic tuning has been more impactful than backend language experiments

## Typical Usage Pattern

Example solver kwargs:

```python
solver_kwargs = {
    "nmajor": 60,
    "admm_weight": 0.01,
    "model_update_tol": 5e-5,
    "linsys_solver": "lsmr",
    "inner_rtol_start": 2e-2,
    "inner_rtol_end": 5e-4,
    "inner_maxiter_start": 12,
    "inner_maxiter_end": 140,
    "inner_maxiter_schedule": "geometric",
    "reuse_inner_solve": True,
    "adaptive_rho": False,
    "return_history": True,
}
ok = interpolator.solve_system("admm", solver_kwargs=solver_kwargs)
```

## Parameter Tuning Cheat Sheet

This section summarizes practical presets that have worked well in this repository for inequality-constrained interpolation.

### Recommended starting presets

Use these as initial profiles, then tune based on feasibility and runtime.

| Profile | Typical size | Goal | Key settings |
|---|---|---|---|
| Balanced-fast | ~30k elements | Good speed with stable quality | `nmajor=60`, `model_update_tol=5e-5`, `linsys_solver="lsmr"`, `inner_rtol_start=2e-2`, `inner_rtol_end=5e-4`, `inner_maxiter_start=12`, `inner_maxiter_end=120`, `inner_maxiter_schedule="geometric"`, `reuse_inner_solve=True` |
| Quality-safe | ~100k elements | Better feasibility margin | `nmajor=60`, `model_update_tol=5e-5`, `linsys_solver="lsmr"`, `inner_rtol_start=2e-2`, `inner_rtol_end=5e-4`, `inner_maxiter_start=12`, `inner_maxiter_end=140`, `inner_maxiter_schedule="geometric"`, `reuse_inner_solve=True`, `adaptive_rho=False` |
| Aggressive-speed | ~100k elements | Maximum throughput, lower safety margin | `nmajor=12 to 20`, same schedules as above but lower `nmajor`, then validate inequality violations before accepting |

### Suggested tuning order

Adjust parameters in this order to avoid confounded effects:

1. Set inner schedules first (`inner_rtol_*`, `inner_maxiter_*`, schedule type).
2. Tune `nmajor` with `model_update_tol` enabled.
3. Only then test `active_set` controls if runtime is still high.
4. Enable `adaptive_rho` last, and only if residual balancing is poor.

### Quick diagnosis guide

If you see this behavior, try these changes first.

| Symptom | Likely cause | First changes to try |
|---|---|---|
| Fast run but many inequality violations | Inner solves too loose and/or too few major iterations | Increase `nmajor` (for example +10 to +20), tighten `inner_rtol_end`, raise `inner_maxiter_end` |
| Slow run with little improvement near end | Too many late major iterations | Increase `model_update_tol` slightly (for example `5e-5` to `1e-4`) or reduce `nmajor` |
| Early oscillation in residuals | Poor rho balance | Try `adaptive_rho=True` with default bounds, keep `admm_weight_final=None` |
| CG path stalls | Weak preconditioning/conditioning | Keep `cg_preconditioner=True`, increase `cg_preconditioner_shift` slightly, or switch to `linsys_solver="lsmr"` |
| Active-set run unstable | Active set too aggressive | Increase `active_set_padding`, refresh more frequently, or disable `active_set` |

### Validation checklist after tuning

Always check both speed and solution quality:

1. Wall time at fixed seed and fixed data.
2. Inequality max violation and violating fraction.
3. Value-constraint fit quality (for example MAE at constrained points).
4. Visual sanity of isosurfaces and gradient behavior.

### Example profiles as dictionaries

```python
balanced_30k = {
   "nmajor": 60,
   "admm_weight": 0.01,
   "model_update_tol": 5e-5,
   "linsys_solver": "lsmr",
   "inner_rtol_start": 2e-2,
   "inner_rtol_end": 5e-4,
   "inner_maxiter_start": 12,
   "inner_maxiter_end": 120,
   "inner_maxiter_schedule": "geometric",
   "reuse_inner_solve": True,
}

quality_safe_100k = {
   "nmajor": 60,
   "admm_weight": 0.01,
   "model_update_tol": 5e-5,
   "linsys_solver": "lsmr",
   "inner_rtol_start": 2e-2,
   "inner_rtol_end": 5e-4,
   "inner_maxiter_start": 12,
   "inner_maxiter_end": 140,
   "inner_maxiter_schedule": "geometric",
   "reuse_inner_solve": True,
   "adaptive_rho": False,
}
```

If you also use constant-norm polishing, tune ADMM first and then add polish iterations conservatively (`constant_norm_iterations=1..3`) to avoid masking core ADMM behavior.

## Known Limitations and Extension Ideas

Current limitations:

- inequality constraints are box constraints only (`xmin <= Qx <= xmax`)
- ADMM helper currently assumes dense per-row projection logic
- active-set strategy is heuristic (works well in practice, not globally optimal)

Plausible extension points:

- richer proximal operators beyond box projection
- block-wise or multilevel ADMM updates
- improved preconditioners for CG beyond diagonal Jacobi
- specialized sparse updates when active set changes incrementally

