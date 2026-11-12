# Instructions for the fault kinematic experiment

Status: execution instructions prepared 12 November 2026. Dataset preparation and
integrity checks are complete. Stage A has a conditional Gate A pass; see
[HANDOFF.md](HANDOFF.md). Later stages remain open.
Use [TASKS.md](TASKS.md) as the work list and [README.md](README.md) for the research
protocol, hypotheses and detailed success tests. This is an experimental workflow,
not a production feature specification.

## Order of work

1. Establish a geometric baseline and dense-grid reference on
   `datasets/synthetic_01_parallel_markers`.
2. Extend the same workflow to `synthetic_02_variable_slip` and
   `synthetic_03_reactivation`.
3. Review one real Hamersley fault with a geologist and run a constrained pilot.
4. Apply the frozen workflow to a reviewed McArthur River subset.
5. Compare advanced inference and agent assistance after the numerical reference
   and real observation model work.

The geologist can prepare real-case constraints during the synthetic work. Real
inference starts after Gate B in TASKS.md; advanced methods must be checked on the
toys before being ranked on real data. A dataset integrity pass does not mean a
fault-inference experiment has passed.

## First benchmark

Use a vertical fault at x=0, with positive wall x>0. Define strike direction
e_s=(0,1,0) and downward in-plane direction e_d=(0,0,-1). The forward relative
slip is s=a e_s+b e_d=(0,a,-b); restoration reverses that motion. Report
D=sqrt(a^2+b^2) and signed pitch atan2(b,a). For this vertical limiting geometry,
use positive/negative wall terminology rather than assuming a unique hanging wall.

Fit a simple planar stratigraphic description using training contacts and bedding.
The algorithm may know the model family but must not read generating coefficients
or simulator code to obtain the fitted numerical values. Begin with a fixed
training-plane estimate and label the result conditional on that estimate; then
measure sensitivity to its uncertainty before claiming full uncertainty.

Run three explicitly configured input cases:

| Case | Information supplied | Expected result |
|---|---|---|
| E0 | Known fault geometry and contact identities; unknown pitch and magnitude. | A ridge/family of compatible slip vectors. Parallel markers cannot provide a unique vector. |
| E1 | E0 plus an independent expert direction. | Estimate the scalar displacement along that direction. |
| E2 | E0 plus a bounded pitch, initially five degrees either side of the E1 direction. | A bounded family showing the remaining trade-off. |

The packaged E1 direction is `[0,150,-100]`. **Normalise it before use. Its norm is
not an observed displacement magnitude.** Keep the synthetic truth outside the
fitting process. The initial E2 bound is a declared experimental assumption, not
another measured observation.

For the dataset benchmark, an initial proper prior is uniform D in [0,600] m and
uniform pitch over its allowed interval. Freeze its exact angular/sign convention
in configuration. Use an independent Gaussian prior on a,b for the separate
closed-form verification tests. These are different targets: preserve the physical
prior and the coordinate-change Jacobian when comparing algorithms. A rank-one
likelihood remains rank one even when prior coupling changes posterior marginals.

## Scientific and data rules

- Use only a selected fold's training CSVs, masked training map/curve layers,
  declared constraints and independently known fault geometry/terrain for fitting.
  Whole-map previews, complete source layers, test CSVs and `truth/` are evaluation
  inputs, not blind conditioning evidence. Retain source IDs and spatial error
  grouping; vertices are not independent geological measurements.
- Keep the existing buffered spatial splits. Learn contact matching, bedding or
  stratigraphic interpolation choices from training data only. Declare any expert
  knowledge of the held-out region when making a validation claim.
- Positions are metres. Synthetic heights are local; survey heights are sampled
  from the packaged DEM. Respect projected GeoJSON CRS declarations. Do not treat
  DEM-derived Z and noisy X,Y as independent observations.
- Score geometric contact error in metres. If a scalar residual is used, derive
  its scale/error from the geometry and measurement process; an arbitrary implicit
  field residual is not a distance. A map-normal distance residual must include
  the local DEM slope in the surface-trace geometry.
- Keep inference data and evaluation truth in separate loader interfaces. Use
  saved numerical predictions for scoring; never estimate errors by looking at
  the truth and then updating an unrecorded fitting choice.
- Fixed expert constraints remove parameters from the search. Bounds restrict
  support; soft beliefs need explicit distributions. Record source, confidence,
  event scope and units. Count information once. Unknown displacement is not zero.
- A real `contact_id` currently identifies a mapped unit pair, not an approved
  horizon correlation. Real CSVs deliberately contain no scalar `val`. Obtain a
  reviewed stratigraphic interpretation or explicitly infer the necessary nuisance
  quantities; do not convert category numbers into physical thicknesses.
- Keep alternative histories separate. When their predictions and induced
  net-slip priors are identical, old-marker likelihoods cannot distinguish them.
  Extra intermediate-age evidence is a separate experiment with its own inputs.
- Record unsuccessful builds, invalid predictions and unresolved parameters.
  Missing predicted contacts must not disappear from the error calculation.
  Numerical failure and geological non-identifiability are different outcomes.

## Implementation boundaries and run contract

Use an isolated `experiment/` package beside this file, with focused tests under
`tests/`. These are proposed locations; the runner does not exist yet. Use the
current NumPy/SciPy environment for the first implementation. Preserve the existing
datasets and generators; store variants with parent hashes and declared seeds.
Keep production LoopStructural code unchanged unless a separately evidenced
defect requires a focused fix.

Store run outputs under `validation/fault_kinematic_inference/<run_id>/` from the
repository root. Every run must save configuration, input hashes, training split,
constraints, priors, sampled/fixed parameters, seeds, software/hardware versions,
full/proxy evaluation counts, elapsed time and status. Preserve failed-run records.
Reusing outputs requires a matching input/configuration signature.

The target runner interface, to implement in T001-T006, is:

```powershell
.venv/Scripts/python.exe -m docs.experiments.fault_kinematic_inference.experiment.run --config <configuration.json> --output <run-directory>
```

It must produce predictions, a slip-component grid/feasible region, constraint
sensitivity, held-out errors and timing in machine-readable files plus a short
Markdown report. Inference processes must not receive truth-file paths. An
evaluation step may read them after predictions are fixed.

Run focused experiment checks, for example the future `tests/` directory with
pytest, and the existing `validate_datasets.py` when inputs/preprocessing change.
Use project checks appropriate to any production code changed. Do not run a large
benchmark sweep before the preceding gate passes.

## Reporting and decisions

Mark tasks complete only with their declared output and validation. Mark each
scientific test `pass`, `fail`, `inconclusive` or `not applicable`; unperformed
tests stay unperformed. Keep protocol thresholds fixed for confirmatory runs and
record any exploratory changes separately.

Report three conclusions independently: parameter recovery when identifiable,
preservation of genuine ambiguity, and prediction of withheld geology. A method
that fits well but lacks calibrated uncertainty may still be useful for exploration.
Claims of complete posterior uncertainty require supported-mode retention and a
verified same-target reference. Apply the protocol's cost-quality tests only once
that reference exists, including all tuning, training and agent overhead.

The first handoff is the Gate A report. It should establish what is learned with
E0, E1 and E2, what remains unresolved, and whether the next work belongs in the
geological interpretation, observation model or computation.
