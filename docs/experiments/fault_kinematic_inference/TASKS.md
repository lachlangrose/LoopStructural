# Tasks: simple benchmark through real survey examples

Read [INSTRUCTIONS.md](INSTRUCTIONS.md) first. Numerical thresholds refer to the
[experiment protocol](README.md); they are proposed acceptance targets, not results.
All code and output paths below are relative to this experiment directory unless
stated otherwise. Files listed under open tasks are to be created, not existing
commands or features. This list does not start implementation.

## Existing prerequisite

- [x] **T000 — Prepare and validate the initial data bundle.**
  - Output: three synthetic and two real datasets in `datasets/`, source/licence
    records, review aids, buffered splits and file hashes.
  - Evidence: `datasets/validation_report.json` reports data-integrity and analytic
    generator checks passed. This prerequisite report does not assess inference;
    Stage A results are recorded in [HANDOFF.md](HANDOFF.md).

## Stage A: first benchmark on the simplest synthetic dataset

- [x] **T001 — Freeze the first benchmark configuration and output contract.**
  - Depends on: T000.
  - Files: `experiment/__init__.py`, `experiment/schema.py`,
    `configs/simple_e0.json`, `configs/simple_e1.json`, `configs/simple_e2.json`.
  - Define coordinate/slip conventions, units, physical priors, observation errors,
    five folds, seeds, numerical tolerances, run budgets and mandatory outputs.
  - Declare the planar stratigraphic model and which nuisance quantities are fixed,
    learned from training data or uncertain. Keep the E0/E1/E2 differences explicit.
  - Acceptance: each configuration is unambiguous and serialisable; no truth value
    is supplied as an inferred parameter or an unlabelled modelling assumption.

- [x] **T002 — Implement the training-data and constraint loaders.**
  - Depends on: T001.
  - Files: `experiment/data.py`, `experiment/constraints.py`, `tests/test_inputs.py`.
  - Load a chosen fold's contacts and bedding, DEM, known fault geometry and
    reviewed constraints. Expose evaluation data through a separate interface.
  - Validate units, IDs, normals, bounds, missing values and source hashes. Remove
    fixed parameters; normalise expert direction vectors. Reject contradictory
    hard inputs with a diagnostic rather than silently repairing them.
  - Acceptance: tests demonstrate that training loads neither test observations
    nor truth; an E1 vector's length cannot become a displacement observation.

- [x] **T003 — Implement the small geometric slip problem.**
  - Depends on: T002.
  - Files: `experiment/geometry.py`, `tests/test_geometry.py`.
  - Estimate the shared bedding/plane description from training data. Reconstruct
    compatible separations with signed, consistent wall and restoration conventions.
  - Implement `n dot s = c`, weighted constrained solutions, rank/conditioning
    diagnostics, and prediction at arbitrary declared observations.
  - Acceptance: the exact two-marker equations recover a=b=100 m; repeated parallel
    markers give rank one. Translation, rotation and metre/kilometre conversion
    preserve the physical result. Known-direction reduction removes a dimension.
  - Protocol tests: A01-A03, A05-A07, with their stated assumptions.

- [x] **T004 — Define and check the observation model.**
  - Depends on: T003.
  - Files: `experiment/likelihood.py`, `tests/test_likelihood.py`.
  - Start with the simplest declared Gaussian measurement model. Respect the
    surface position error and DEM-derived elevation relationship.
  - Use geometric distances or correctly scaled residuals. Handle weak sensitivity,
    source grouping, missing predictions and prior support explicitly.
  - Acceptance: verify against a closed-form linear-Gaussian problem; fit quantities
    do not acquire arbitrary scale dependence. Results conditional on an estimated
    plane are clearly labelled, with its uncertainty left for T007.

- [x] **T005 — Implement the grid reference and geometric ensemble.**
  - Depends on: T003, T004.
  - Files: `experiment/grid.py`, `experiment/geometric_ensemble.py`,
    `tests/test_grid.py`.
  - Evaluate the two-parameter E0/E2 problem and the one-parameter E1 problem.
    Refine the grid until the important probabilities/predictions stabilise.
  - Preserve the configured physical prior and integration weights. A finite grid
    boundary must not masquerade as data-constrained uncertainty. Do not interpret
    counts from an unweighted feasible ensemble as posterior probabilities.
  - Acceptance: reference means agree within 0.1 posterior SD and uncertainty
    scales within 10% of the exact analytical target. Verify the independent-prior
    null-space test separately from the polar-prior dataset benchmark.

- [x] **T006 — Run the first end-to-end E0/E1/E2 benchmark.**
  - Depends on: T002-T005.
  - Files: `experiment/run.py`, `experiment/evaluate.py`, `experiment/report.py`.
  - Dataset: `synthetic_01_parallel_markers`; use all five spatial folds. Repeat
    stochastic methods with three inference seeds; deterministic grids need no
    redundant random repeats.
  - Outputs: configuration/input manifest, candidate vectors/weights or feasible
    sets, fixed predictions, errors, timing, and reports under the repository's
    `validation/fault_kinematic_inference/` output root.
  - Figures: slip-component compatibility, D/pitch uncertainty where meaningful,
    withheld contact predictions, and the change caused by expert constraints.
  - Acceptance: E0 preserves the likelihood ridge; E1 estimates a scalar magnitude;
    E2 retains the appropriate bounded family. Evaluation truth never feeds back
    into that scored fit. Grid truncation and wrong sign/scale are excluded.

- [x] **T007 — Test uncertainty and approve Gate A.**
  - Depends on: T006.
  - Files: `tests/test_calibration.py`, `configs/simple_sensitivity.json` and run
    reports. Use small generated analytical problems for 200 independent
    prior-predictive calibration trials; do not rebuild an expensive 3D model 200 times.
  - Check near-zero slip, uncertainty in the training-plane estimate, known versus
    bounded pitch, and the effect of repeated parallel observations.
  - Acceptance: analytical 90% intervals achieve the protocol's 85-95% screening
    coverage, with binomial uncertainty reported. Near-zero direction is not called
    resolved. Numerical approximations meet the same-target reference tolerances.
  - A conditional or feasible-set-only method must be labelled accordingly; it
    cannot acquire a full uncertainty claim from predictive fit alone.

**Gate A — first benchmark complete:** a repeatable report establishes numerical
correctness, useful E1/E2 constraints and honest E0 ambiguity. Resolve numerical or
data-leakage failures before upgrading. Report model/uncertainty limitations explicitly.

## Stage B: upgrade the synthetic geology

- [ ] **T010 — Add finite, variable displacement.**
  - Depends on: Gate A.
  - Files: `experiment/profiles.py`, `configs/variable_slip.json`,
    `tests/test_profiles.py`; extend the existing prediction/report interfaces.
  - Dataset: `synthetic_02_variable_slip`. Compare constant displacement, one
    symmetric taper and one low-order asymmetric taper, with shared direction.
  - Learn the pre-fault geometry from training data; do not import its truth field.
    Use a small frozen shape library plus component grids before increasing dimension.
  - Acceptance: demonstrate the designated >=20% withheld-contact improvement when
    justified, without worsening the proper interval score. Profile normalisation
    keeps amplitude interpretable; weakly observed tips/maximum remain uncertain.
  - Protocol tests: G01, G02 and the applicable physical checks in G07.

- [ ] **T011 — Test observationally equivalent reactivation histories.**
  - Depends on: Gate A; may proceed independently of T010.
  - Files: `experiment/scenarios.py`, `configs/reactivation.json`,
    `tests/test_scenarios.py`.
  - Dataset: `synthetic_03_reactivation`. Compare the upward/downward two-event
    history with the equivalent single upward event, using old surface markers only.
  - Acceptance: identical predictions and matched net-slip priors do not manufacture
    history information; numerical posterior odds follow the declared prior odds.
  - Keep the optional intermediate-age diagnostic out of the base run. If used,
    create a separate declared extra-evidence experiment and assess its support
    against a verified reference. It is not a surface-map observation.
  - Protocol tests: G03/G04 as applicable; label unsupported correlation tests as
    additional variants rather than claiming the packaged data already contain them.

- [ ] **T012 — Run robustness and numerical-consistency checks; approve Gate B.**
  - Depends on: T010, T011.
  - Files: `configs/synthetic_stress.json`, focused tests and comparative reports.
  - Test wrong expert constraints where independent evidence can reveal them,
    missing contacts, position/orientation error sensitivity, source-trace
    densification, and finer integration/interpolation where used.
  - Preserve frozen parent datasets; save each variant's seed and parent hashes.
  - Acceptance: duplicates do not create false independent information; supported
    alternatives survive; known numerical errors fall below 0.1 of the smallest
    observation-error scale. Record failure to detect observationally invisible
    wrong assumptions as a limit, not an algorithmic success.
  - Protocol tests: A04, G05-G07, E01-E03 to the extent the variants implement them.

**Gate B — ready for a real pilot:** the workflow handles constant and variable
slip, preserves unresolvable histories, and produces reliable held-out predictions
with documented uncertainty limits. Geologist constraints and failures are traceable.

## Stage C: upgrade to reviewed real survey data

- [ ] **T020 — Geologist reviews one Hamersley fault and prepares the constraint card.**
  - Depends on: T000; review can start during Stage A.
  - Inputs: `real_01_hamersley/fault_review_priority.csv`, `cutoff_candidates.csv`,
    unit catalogue, original mapping and bedding. These are candidates, not trusted matches.
  - Outputs: `configs/real/hamersley_constraints.json` and a short review note.
  - Record the selected fault/region, trusted contact correlations, stratigraphic
    series/unconformities, slip sense, dip/pitch bounds, displacement/profile bounds,
    event order and continuation/tip interpretation. Unknowns stay unknown.
  - Acceptance: each constraint has source, confidence and event scope. Identify
    whether expert information reveals the intended validation blocks. Confirm the
    coarse 1:500,000 mapping supports the proposed scale of the question.

- [ ] **T021 — Add the real observation/LoopStructural adapter.**
  - Depends on: Gate B, T020.
  - Files: `experiment/loop_adapter.py`, `configs/real/hamersley_pilot.json`,
    `tests/test_loop_adapter.py`.
  - Use the same load/constraint/predict/evaluate/report interfaces as the toys.
    Build stratigraphic constraints from reviewed contacts; explicitly represent
    unknown horizon levels/thickness or other necessary nuisance quantities.
  - Fit interpolation choices on training data. Changing restored constraints must
    rebuild affected interpolants; reuse only valid geometry/solver caches.
  - Acceptance: verify sign, physical units and actual two-wall displacement,
    including profile scaling. Test a synthetic planar case through this adapter
    against the independent geometric reference before using it on real inputs.
  - Measure forward-build cost before setting pilot budgets. Keep numerical
    adapter correctness separate from adequacy of the geological interpretation.

- [ ] **T022 — Run the constrained Hamersley pilot.**
  - Depends on: T021.
  - Begin with one fault, trusted matches, geologist-constrained geometry/direction
    and constant or very low-order displacement. Leave context faults at explicitly
    declared treatment; do not silently infer all eight mapped fault features.
  - Compare the simple geological baseline, map-based constraints and expert-guided
    constraints. Run the five buffered folds and record uncertainty sensitivity.
  - Acceptance: obtain valid spatial predictions and interpretable trade-offs.
    Report contact distance, unit juxtaposition, errors relative to declared map
    uncertainty and total cost. A useful model must predict withheld geology;
    real parameter recovery cannot be scored against unknown true slip.
  - If the forward interpretation fails, revise it using pilot/training evidence
    and document that change before freezing a confirmation setup.

- [ ] **T023 — Freeze choices and confirm on a reviewed McArthur subset.**
  - Depends on: T022; a geologist must also review the McArthur inputs.
  - Files: `configs/real/mcarthur_constraints.json`, `configs/real/mcarthur_confirmation.json`.
  - Select one fault/linked group rather than immediately solving the 150 mapped
    features. Retain the 1:100,000 survey's source/uncertainty distinctions and
    review repeated units, contact matches and reactivation alternatives.
  - Keep method choices fixed from the pilot. Use three spatial folds and three
    stochastic seeds initially; apply the packaged 500 m exclusion or document a
    justified wider correlation buffer before scoring.
  - Acceptance: the pipeline transfers without truth-based tuning, reports unresolved
    kinematics honestly, and yields reproducible predictive/cost comparisons. Treat
    inherited, same-map sections as secondary plausibility checks, not independent truth.

**Gate C — real observation model established:** at least one reviewed pilot is
usable, a second region has been attempted under frozen choices, and inadequacy
of a geological model is distinguished from numerical/inference failure.

## Stage D: compare the remaining methods

- [ ] **T030 — Add the Bayesian SMC reference.**
  - Depends on: Gate B for toy testing; Gate C before real-case ranking.
  - Files: `experiment/smc.py`, `configs/methods/smc.json`, focused sampler tests.
  - Verify the same physical prior/likelihood against the low-dimensional grid;
    then support the necessary real nuisance parameters and discrete alternatives.
  - Acceptance: protocol tolerances on means, uncertainty and mode weights. Establish
    reference accuracy by independent seeds and further computation, not budget alone.

- [ ] **T031 — Add ES-MDA as a rapid fitting/approximate uncertainty method.**
  - Depends on: T030 or an adequate same-target grid reference.
  - Files: `experiment/esmda.py`, `configs/methods/esmda.json`, focused tests.
  - Keep discrete interpretations separate. Count final ensemble evaluations and
    all tuning. Use the same expert knowledge and prediction operator as the reference.
  - Acceptance: pass the relevant predictive gates; claim uncertainty only if it
    also passes calibration/reference checks. Otherwise label it fitting-only.

- [ ] **T032 — Add corrected surrogate-assisted sampling.**
  - Depends on: T030.
  - Files: `experiment/surrogate.py`, `configs/methods/surrogate.json`, correction tests.
  - Begin with a frozen emulator and full-model correction. Keep SMC weighting
    consistent with the full-model target; track proxy, training and rejected calls.
  - Acceptance: same-target accuracy plus the protocol's cost-quality comparison.
    Sparse final spot checks do not substitute for a valid correction.

- [ ] **T033 — Add LLM/agent-assisted scenario/evaluation selection.**
  - Depends on: verified numerical evaluators from Gate B; use available tested
    numerical methods. Real-case ranking additionally requires Gate C.
  - Files: `experiment/agent_policy.py`, `configs/methods/agent.json`, saved prompts,
    evidence/action schemas and evaluation logs.
  - Give agent and numerical controls the same constraints, evidence, scenario
    library and tools. First compare evaluation allocation; score proposals of new
    geological interpretations as a separate experiment.
  - Acceptance: L01-L05. No invented measurements/results or accepted hard-constraint
    violations. Count LLM latency/cost and human interventions. Numerical posterior
    and complete-scenario claims require their own reference checks.

## Stage E: final comparison and next decision

- [ ] **T040 — Produce the comparative research report.**
  - Depends on: T023 and whichever T030-T033 methods were implemented and verified.
    Explicitly list deferred/unperformed methods; do not assign them a verdict.
  - Outputs: a summary report, per-test status table, constraint-impact table,
    reproducible run index, calibration plots and cost-quality curves.
  - Report recovery, ambiguity and prediction separately. Separate benefits of
    additional geological knowledge, a better observation model and a faster algorithm.
  - Use the protocol's proposed 20% predictive improvement and 3x numerical
    acceleration targets where applicable; agent search has its separate 20%
    cost target. Show uncertainty and include unsuccessful runs.
  - Decision: recommend a method for uncertainty, for exploration/fitting, or as a
    geometric screen; otherwise record an inconclusive/negative result. Identify
    the next useful geological constraint. Boreholes, extra survey regions and
    production integration remain subsequent scoped experiments.

## Handoff for each completed stage

Record completed task IDs, changed files, exact reproduction commands, input and
configuration hashes, actual checks and outcomes, outstanding limitations, and
the gate decision. Update checkboxes only when their outputs and acceptance
evidence exist. Complete the first handoff at Gate A before launching the full
survey/method comparison.

Stage A implementation and validation evidence: [HANDOFF.md](HANDOFF.md).
