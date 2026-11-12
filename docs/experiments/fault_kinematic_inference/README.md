# Fault kinematic inference: experiment plan and success tests

Status: proposed research protocol, 12 November 2026. An initial dataset bundle is
available in [datasets/README.md](datasets/README.md), with independent analytic
synthetic generators and survey extracts. Stage A now has a conditional Gate A pass; see [HANDOFF.md](HANDOFF.md) for measured results and uncertainty limits.
The numerical thresholds below are proposed acceptance targets, not findings
from the literature. Freeze them before scoring the confirmatory experiments.

For execution, read [INSTRUCTIONS.md](INSTRUCTIONS.md) and follow the staged
checklist in [TASKS.md](TASKS.md), beginning with the simple synthetic benchmark.

## Objective and scope

Determine which combinations of fault slip direction, magnitude and displacement
profile are supported by Australian geological survey maps, bedding observations,
a DEM and constraints supplied by a geologist, and identify the least expensive
method that preserves that information. The main workflow is geology-guided;
map-only inference is an ablation that measures the value of those constraints.
The primary experiments exclude boreholes and geophysical inversion. A separate
mine-scale extension adds boreholes after the map-based study.

Success has three separate meanings:

1. Recover slip when the observations identify it.
2. Preserve ambiguity when the observations do not identify it.
3. Predict withheld geology at a useful computational cost.

A method may pass the third test without passing the first two. Report those
outcomes separately. Real maps provide predictive checks, not known slip truth.

## Hypotheses

| ID | Hypothesis | Evidence required |
|---|---|---|
| H1 | Geometric conditioning exposes the constrained components of slip and reduces unnecessary full-model evaluations. | Correct rank/null-space behaviour on analytical toys; useful feasible sets on map windows; lower cost to reach the reference predictive quality. |
| H2 | A small displacement profile improves predictions where constant slip is inadequate, without requiring a highly flexible profile. | At least 20% lower median blocked contact error on the designated variable-slip toy and at least one eligible real pilot window, without worse predictive interval score. |
| H3 | Explicit contact-correlation and history alternatives prevent false precision. | Retain supported modes in ambiguous toys; suppress a false alternative only after discriminating evidence is added; correctly preserve observationally equivalent histories. |
| H4 | Ensemble smoothing or corrected surrogate sampling can provide useful acceleration. | At least 3x lower total elapsed cost at the declared quality target on two real windows; pass the applicable accuracy and uncertainty gates. |
| H5 | A small set of geologist-supplied constraints reduces the effective search dimension and cost while preserving valid scenarios. | Paired map-only and geology-guided runs show the information/cost change. A constrained single-marker toy recovers its identifiable scalar displacement; incorrect constraints are tested separately. |
| H6 | An LLM/agent can use geological constraints and numerical diagnostics to select useful scenarios/evaluations more efficiently than a fixed search policy. | Paired agent/non-agent workflows use identical inputs and numerical tools. Require better cost-quality results, correct constraint handling and supported-mode retention; include LLM cost and human review. This is an untested hypothesis. |

Failure of H2 on real data is a useful result: retain the simpler profile. Failure
of H4 means that acceleration did not repay its setup cost on this workload.

## Methods and controlled comparisons

| ID | Method | Intended output |
|---|---|---|
| B0 | Transparent geological baseline: estimate separation from manually checked contact matches and convert under a declared pure dip-slip assumption. | A simple estimate or bound, with its assumptions. |
| B1 | Original-style Bayesian baseline: planar fault, pitch and scalar magnitude, fixed profile and fixed correlations. | Reference for the earlier problem formulation. Reproduce the formulation if the earlier implementation is unavailable. |
| M1 | Geometric constraint ensembles: perturb uncertain observations/geometry and solve small constrained slip problems, conditional on a short list of profile shapes and correlations. | Feasible slip regions, sensitivity and an inexpensive scenario ensemble. |
| M2 | Hierarchical Bayesian restoration with tempered sequential Monte Carlo (SMC). | A posterior conditional on the stated forward model, errors, priors and geological alternatives. |
| M3 | Ensemble smoother with multiple data assimilation (ES-MDA), separately within each discrete interpretation. | Rapid parameter adjustment and an approximate uncertainty ensemble. |
| M4 | Surrogate-assisted sampling with full-model correction; initially delayed-acceptance moves within the M2 sampler, retaining full-model SMC weights. | Acceleration of the same posterior target as M2. |
| M5 | LLM/agent-assisted scenario search and experiment selection, using the constraint card and the same validated numerical tools as a non-agent control. | A proposed/searchable scenario set, selected evaluations and evidence-linked interpretation. Posterior claims require a qualifying numerical inference stage. |

The local map2loop ThrowCalculatorAlpha currently supplies a default value when
displacement is missing; do not interpret that fallback as a measured B0 estimate.

Use three comparison tracks to separate modelling, sampling and agent assistance:

- **Formulation track:** change one of geometry, profile, correspondence,
  stratigraphic treatment or error model at a time, using M2 where feasible.
- **Algorithm track:** compare M2, M3 and M4 using the same physical priors,
  observations, parameter freedom, discrete scenarios and prediction operator.
  Begin with Gaussian observation errors; robust errors are a separate ablation.
  M3's treatment of a non-Gaussian target must be labelled approximate.
- **Agent track:** compare M5 with the same numerical workflow controlled by a
  fixed search/acquisition policy. Use an identical scenario library first; test
  agent-proposed new interpretations separately as a formulation experiment.

M1 uses a cheaper geometric approximation and is scored as such. Its ensemble
frequencies and M3's scenario counts are not Bayesian scenario probabilities.
B0 is not required to produce probabilities or calibrated credible intervals.
Compare M1's geometric prediction error, explicitly defined set coverage and cost
separately. Do not calculate a proper probabilistic score from an unweighted
feasible set or declare it equivalent to a posterior without a probability model.

Initially freeze M4's emulator before each scored sampling run and count its full
training cost. Adaptive emulator variants require separate checks that their
updates preserve the intended inference target.

## Geologist constraints are primary inputs

Do not require inference of parameters that the geologist can reasonably fix,
bound or restrict to a few alternatives. Before each experiment, prepare a short
constraint card and eliminate fixed quantities from the sampled parameter vector.
Use the same card across methods in a comparison. The geologist may supply only
some entries; unspecified entries remain uncertain.

| Constraint | Example | Computational use |
|---|---|---|
| Slip sense | Normal sense, reverse sense, dextral or sinistral, or two alternatives. | Restrict signs or enumerate the supported kinematic families. |
| Slip direction | Pure dip slip; pitch 70-100 degrees; a measured lineation with angular uncertainty. | Fix pitch or sample within a justified distribution. A lineation must represent the displacement event being modelled; incremental motion need not equal finite net slip. |
| Fault geometry | Dip 55-65 degrees; effectively planar in this window; known curvature or a detachment. | Fix geometry, bound its variation, or select a short list of geometries. |
| Displacement scale | A trusted marker suggests 100-300 m, or at least 80 m of stratigraphic separation. | Use the correct displacement component as an equality, range or one-sided bound; convert separation to slip using the stated geometry. |
| Profile | Approximately constant in the window; taper near a genuine tip; maximum near a specified region. | Remove unsupported profile parameters and constrain shape/maximum location. A concealed continuation is not a zero-slip tip. |
| Contact correspondence | These two cutoffs are the same horizon; this alternative correlation is plausible. | Fix trusted matches and enumerate only unresolved alternatives. |
| Event order and stratigraphy | Fault postdates folding; an unconformity predates reactivation; selected units are unaffected. | Remove impossible histories and attach events only to affected features. |
| Geometric boundary conditions | Known continuation, fault linkage, or a pinned region under a stated restoration interpretation. | Limit geometry and restoration alternatives where the assumption is justified. |

For every entry record value/range, units, affected fault/event, source, confidence
and whether it is fixed, bounded, probabilistic or a discrete alternative. Fixed
and bounded statements exclude scenarios; soft statements express preference.
Do not turn a qualitative suggestion into an exact constraint automatically.

For example, if the geologist fixes geometry and pure dip slip and trusts two
contact correlations, begin with only displacement amplitude and, if supported,
one profile-shape parameter. Do not sample a free pitch, dip, contact permutation
and event sequence in that experiment. If a full prior-predictive map cannot
honour trusted observations, investigate the constraint/model conflict before
spending the inference budget.

Run three paired input conditions on designated toys and pilot windows:

- **E0, map-based inputs:** minimal declared kinematic priors and map/bedding/DEM
  constraints. This diagnoses what those inputs alone can identify.
- **E1, practical expert constraints:** the geologist's initial constraint card,
  supplied before seeing inference results. This is the primary operating case.
- **E2, one additional constraint:** add one independently available constraint
  directed at the largest remaining ambiguity. This measures the benefit of the
  next geological decision or observation, without assuming it always exists.

Compare sampled dimension, surviving scenarios, parameter/profile uncertainty,
held-out predictions and total cost between E0/E1/E2. Report elicitation/review time
separately from computer time. Tighter intervals caused by additional knowledge
are an expected conditional result, not evidence that the maps alone resolved slip.

Prevent information reuse: a bound or correlation inferred from a contact is not
an independent second measurement of that contact. Record whether it is replacing
the raw observation, summarising it, or expressing independent knowledge. For a
blind validation claim, elicit data-dependent constraints from training material;
full-region expert knowledge must be declared and the validation claim qualified
where it reveals the held-out geology. Freeze the card before scoring each run.

Include deliberately overconfident or wrong cards in synthetic stress tests.
When the observations can discriminate, detect conflict using the same predictive
checks as for an incorrect forward model. When they cannot, state the result is
conditional on expert assumptions; no method can guarantee detection. Relax a
constraint only through a documented revised scenario, not silently during fitting.

## M5: LLM/agent-assisted workflow

The agent is an experimental decision-maker around the geological and numerical
tools. It is not assumed to know the true slip or to generate calibrated posterior
samples from prose. Give it the same training maps, observations, constraint card,
scenario library and diagnostics available to the non-agent control. Supply a
standardised evidence summary first; direct interpretation of raw map images is
a later, separately scored extension.

Permit a bounded action set:

1. Translate the geologist's statements into a proposed constraint card, retaining
   provenance and uncertainty. The geologist reviews that card before use.
2. Select from admissible contact correlations, geometry/profile families and event
   histories; propose a new explicit alternative in the scenario-discovery track.
3. Select the next numerical evaluation or allocation of the remaining budget,
   using constraint compatibility, predictive error and uncertainty diagnostics.
4. Request a specific missing geological constraint when it would resolve a
   remaining ambiguity. In scored runs, use a predeclared answer bank or record
   the additional human input; do not compare against an uninformed control.
5. Explain why a scenario survives, fails or remains unresolved, linking each
   numerical claim to a saved evaluator result and each geological claim to input.

The agent may orchestrate M1 screening plus M2/M3/M4 evaluations, but the non-agent
control receives the same underlying tools. Use both a space-filling policy and
a simple numerical acquisition policy where applicable; an advantage over random
search alone is insufficient. Count every nested computation and unsuccessful
proposal. Record model/provider/version, prompts, tool definitions, token usage,
LLM charges, latency, proposals, rejected constraints and human corrections.

The primary M5 comparison holds the geological model space fixed and tests which
evaluations to perform. Scenario discovery is scored separately against a known
toy scenario universe and reviewed real-case alternatives. If an agent explores
only a selected subset, its subsequent numerical posterior is conditional on that
subset; do not present it as covering all possible histories. Verbal confidence
and uncorrected agent proposal frequencies are not posterior probabilities.

Require hard constraints to be checked by the numerical workflow. A proposed
relaxation creates a clearly labelled scenario for geologist review; it cannot
silently replace the constraint card. Cache and identify actual evaluations so
failed, stale or unevaluated candidates cannot be described as successful fits.
After scenario selection, retain numerical inference/verification costs in the
comparison. Perform at least three independent agent runs per scored case and
report variability even if the chosen model settings are nominally deterministic.

## Shared physical and observational definitions

For a planar fault use orthonormal strike and down-dip directions. Relative
two-wall slip is s = a e_strike + b e_dip. Report magnitude sqrt(a^2+b^2) and
signed pitch atan2(b,a), with an explicit forward-slip/restoration convention.
For a correlated planar marker with unit normal n_i, reconstructed signed normal
separation obeys c_i = n_i dot s + error. Raw map-cutoff distance is not c_i.

Use vector components for conditioning and pitch/magnitude for interpretation.
Changing coordinates must preserve the same physical prior, including its
Jacobian. Suppress pitch summaries near zero slip, where direction is undefined.
For curved faults distinguish the integrated restoration trajectory from an
endpoint slip vector; declare which quantity is being reported.

Use three nested model families, increasing complexity only when justified:

1. Constant direction and magnitude on a planar fault.
2. Constant direction and a low-order along-strike magnitude profile: a symmetric
   taper, one asymmetric taper and a smooth profile with at most four coefficients.
3. Curved geometry or a small number of explicit event-history alternatives.

Normalise profile shapes consistently so amplitude cannot trade arbitrarily with
profile scale. Do not impose zero displacement at a mapped endpoint unless it is
a geological termination; map edges, concealment and unmapped continuation are
different cases. Initially fix down-dip decay within alternative declared models,
then perform sensitivity tests. Do not infer deep profile detail from surface
data simply because the model accepts those parameters.

For each observation preserve its source, feature ID, unit/contact identity,
position, orientation, uncertainty, exposure/confidence class and provenance of
any interpretation. Use projected metric coordinates, reconciled elevation
datums and the present-day DEM for surface observations. A restored DEM is not
assumed to be an ancient common surface.

Treat a digitised contact as a spatially correlated observation, not thousands
of independent vertices. Uncertain matches are explicit alternatives constrained
by unit identity, stratigraphic order and local geometry. Do not equate missing
matches, absent outcrop or within-unit juxtaposition with zero slip. Do not count
topology, derived thickness and source contacts as independent evidence when
they encode the same observation.

Fault geometry, restored bedding and the displacement footprint must be handled
consistently. In particular, changing pitch can change fault-frame coordinates;
test whether an apparently improved fit is caused by an unintended footprint
change. Cache only quantities valid under the parameter change.

## Stage 0: freeze the protocol and measure cost

Deliver a short manifest before running scored experiments:

- Exact dataset versions, windows, licences, coordinate/elevation systems,
  observation filters and uncertainty assumptions.
- Geological alternatives, priors, profile families and stratigraphic
  regularisation/latent-field treatment.
- The geologist constraint card, its information sources, fixed versus sampled
  parameters, excluded scenarios and elicitation time.
- All splits and random seeds, hardware, worker count, package/repository
  versions, solver tolerances and mesh resolutions.
- Which observations are raw, interpreted, derived, conditioning or withheld.
- For M5, the fixed prompts, evidence available to the agent/control, numerical
  action set, LLM budget, model version and human-interaction protocol.
- A forward-evaluation timing pilot of 20 representative parameter settings,
  recording rebuild, prediction, geometry and interpolation costs separately.

Choose realistic data-error scales from map metadata and interpretation before
looking at held-out performance. Where metadata are insufficient, declare a low,
central and high uncertainty model. Tune choices using pilot data only. Freeze
them for later NT and Victorian confirmation windows, apart from documented
survey-specific measurement errors.

Start with evaluation ceilings of 256, 1,024 and 4,096 per run, taking checkpoints
from the same run where valid. These are resource ceilings, not equal-cost claims.
Count all full-model calls, including pilot, training, rejected proposals, tuning,
final verification and failed builds. Also report total elapsed time and core-hours;
cheap proxy calls and analytical work have nonzero costs. Fix the same worker
allocation for elapsed-time comparisons. Report cold-start and reused-work costs
separately. Set wall-time ceilings from the timing pilot before the main runs.

## Stage 1: analytical verification

These tests are cheap enough for 200 independent prior-predictive datasets for
coverage checks. First use Gaussian noise, known geometry and unbounded independent
Gaussian priors in a,b where needed for an exact posterior. Also include noiseless
geometric tests. Do not manufacture independent observations by resampling vertices.

| Test | Construction | Success criterion |
|---|---|---|
| A01: vector recovery | a=100 m; 0.6a+0.8b=140 m, with independent 10 m Gaussian errors and a declared weak Gaussian prior. | Exact noiseless geometry gives a=b=100 m, D=141.421 m and pitch=45 degrees. Bayesian outputs match the exact posterior under the declared prior: component mean errors <=0.1 posterior SD and SD errors <=10%. Compare pitch with circular statistics. |
| A02: null space | Replace the second constraint with another observation of a. | Detect rank one. The posterior marginal of independent, unobserved b remains its prior: SD ratio 0.9-1.1 and empirical CDF distance <=0.1. M1 reports an unresolved direction instead of selecting a unique vector. |
| A03: poor conditioning | Change the angle between projected marker normals from 60 to 20 to 5 degrees. | Match the exact posterior for each case; uncertainty grows in the weak direction. For equal-weight unit rows, the 5-degree matrix condition number is about 22.9. |
| A04: zero/near-zero slip | Zero slip and magnitudes below one observation-error scale. | Component posterior and joint uncertainty agree with the analytical target; do not infer significant motion merely because a continuous nonnegative magnitude has a positive interval. Pitch is not reported as resolved near zero. |
| A05: units and conventions | Translate/rotate coordinates; express identical observations in m and km; exchange wall labels and reverse conventions consistently. | After mapping back, exact geometry agrees to relative tolerance 1e-6 with an absolute floor 1e-8 of the domain size. Stochastic summaries agree within their verified Monte Carlo errors. |
| A06: geologist fixes direction | Use one marker with known slip direction u and nonzero n dot u; infer only D from c = D(n dot u) + error. Repeat with a bounded pitch and with n dot u near zero. | The fixed-direction scalar posterior matches its analytical target. A bounded pitch gives the correct remaining family. Near-zero sensitivity is reported as weak information even with known direction. No redundant direction parameter is sampled. |
| A07: constrained equivalence | Add correct sign, geometry, profile and correspondence constraints individually. Compare parameter elimination with the mathematically equivalent conditional model. | Same-target results agree to the A01 tolerances. Fixed parameters do not consume sampling dimensions, and sign/bound constraints are honoured. Explicitly record any excluded true synthetic scenario as a constraint failure. |

For identifiable components, the proposed screening gate is 85-95% empirical
coverage of nominal 90% credible intervals across 200 prior-predictive datasets.
Report binomial confidence intervals and rank diagnostics as well; do not describe
this screening band as a statistical guarantee. Apply coverage tests only to
methods claiming probabilistic intervals. M1 instead reports coverage of explicitly
defined feasible/confidence sets and their construction. Proper priors are required
for posterior comparisons, including in the unresolved direction.

Stage 1 gate: resolve analytical mismatches before moving a method to 3D.
M3 may continue as a fitting-only method if its uncertainty fails, but must retain
that designation. M4 must pass the same posterior checks as M2.

## Stage 2: controlled 3D geological toys

Use an initial 4 x 4 x 2 km domain, one fault and displacement scales of 100-300 m.
Begin with flat terrain; add approximately 300 m relief as a paired test. Initial
noise settings are 10 and 30 m positional uncertainty and 5-degree bedding error,
with sensitivity to 10-degree bedding error. These are synthetic stress settings,
not survey-wide accuracy assumptions. Limit the first inversions to roughly six
continuous parameters and two discrete interpretations.

Use an independent analytic or geological-history generator for misspecification
tests. Include three fixed observation realisations and three inference seeds.
Add only one complication at a time before combining them.

| Test | Construction and comparison | Success criterion |
|---|---|---|
| G01: useful profile complexity | Generate an asymmetric taper; fit constant, symmetric and low-order asymmetric profiles. Repeat with a different generating taper family. | Correct flexibility reduces median withheld contact error >=20% against the constant profile on the designated variable-slip case and does not worsen mean interval score. The method does not add unsupported oscillations. |
| G02: missing profile evidence | Remove observations near one tip, then hide the central maximum; retain a densely observed control. | Predictive and local-slip uncertainty agree with the numerical reference in gaps. The hidden maximum is labelled weakly constrained. Sampling success is not defined by recovering an unobserved Dmax. |
| G03: correlation ambiguity | Two explicit marker correlations have prior probability 0.5 each. Construct a symmetry case with equal likelihood, then add a distinctive marker. | In the symmetry case, posterior weights are within 0.05 of 0.5. With the marker, weights agree with a verified numerical reference within 0.05. Retain any reference mode with probability >=0.1. |
| G04: observationally equivalent histories | All markers predate collinear 300 m reverse and 200 m normal slip on one planar fault; compare a 100 m single event. Then add a marker deposited between events. | With prior-matched net-slip predictions, old markers alone do not create evidence for a unique history. The intermediate-age marker changes support in agreement with the numerical reference. Do not require unique recovery if the added evidence is still insufficient. |
| G05: incorrect geometry/history | Fit a planar fault to curved-fault observations, and a single event to geology with distinguishable multiple events. | Flag failure through predeclared held-out predictive checks; expanding the appropriate model family improves the proper predictive score. Wider noise alone must not be reported as successful parameter recovery. |
| G06: map error and duplication | Add 10% wrong matches/outlying observations; separately increase vertices along the same unchanged traces by 10x. Compare Gaussian and declared robust error models. | Robust treatment improves the contaminated-data proper predictive score against the Gaussian control. Densification alone changes posterior SDs and interval scores by <=10%; independent new traces may add information. |
| G07: physical consistency | Probe both walls, restore/forward-map locations, transform bedding consistently, refine integration and interpolation. | Intended two-wall vector agrees within 0.1% in the constant planar case. On curved cases, numerical discrepancies converge and become <0.1 of the smallest observation-error scale. Do not demand exact round trips from a finite-step integrator. |

References: exact analytical solutions where available; dense quadrature for
two-dimensional targets; otherwise multiple independently seeded high-budget M2
runs on three representative datasets. A high budget alone does not establish
reference accuracy. Check stable component/profile moments, mode weights,
predictive scores and uncertainty against further computation. If no stable
reference is obtained, label posterior-accuracy conclusions unresolved.

For a probabilistic approximation, require component and profile-probe mean
differences <=0.1 reference posterior SD, 90% interval-width differences <=10%,
and important scenario-probability errors <=0.05. First establish reference Monte
Carlo errors below those tolerances. Exact rank-deficient tests use their exact
targets. Monte Carlo diagnostics and parameter comparisons are conditional on
the same geological model, error model and prior.

Do not require narrow intervals for uncertain down-dip extent or decay. Repeat
those priors at wider plausible scales and identify which predictions change.
Explicitly report a prior-sensitive result as conditional, not data-resolved.

Stage 2 gate: M2/M4 must pass recovery, ambiguity, calibration and consistency
tests before being treated as reliable uncertainty methods. M3 passing prediction
but failing posterior checks remains eligible for interactive fitting only. M1
must preserve the supported feasible families and identify approximation failures.

Test the E0/E1/E2 conditions before moving to real confirmation:

| Test | Comparison | Success criterion |
|---|---|---|
| E01: practical constraint benefit | Supply a correct, realistic subset of pitch/sense, dip, matching or history constraints; do not give all true parameters. | Recover identifiable quantities with the applicable calibration gates and reduce cost to matched conditional predictive quality by at least 2x on one designated ambiguous toy and one real pilot window. Record dimension and scenario reductions separately from sampler gains. |
| E02: constraint conflict | Give a wrong narrow pitch, incorrect contact match or wrong event order, in a toy with independent discriminating evidence. | Flag conflict through the predeclared predictive check; a documented relaxation improves held-out predictive score. A tight but incompatible result fails. Include an observationally indistinguishable control where only a conditional conclusion is possible. |
| E03: next useful constraint | Add one available constraint aligned with the weak direction and compare with another observation of an already constrained parallel marker. | Match the analytical/reference change in uncertainty and prediction. Report which uncertainty remains. More parallel data must not be reported as resolving a truly unconstrained component. |

If E0 never reaches E1's predictive quality within its budget, report a bounded
cost-quality result, not a precise speedup. The conditional target differs when
knowledge is added; keep this effect distinct from a sampler comparison.

Agent-specific tests, after the numerical evaluators pass their own checks:

| Test | Construction | Success criterion |
|---|---|---|
| L01: constraint translation | Twenty short geological briefs with fixed, bounded, soft and unspecified statements, including units and event scope. | No invented measurements or silently strengthened constraints; zero errors in slip sense, units, fixed/bounded status or event assignment. Record review time and corrections. |
| L02: numerical grounding | Give saved successful, failed, stale and unevaluated candidate records and conflicting diagnostic outputs. | Every reported numerical result links to the correct evaluation; zero fabricated fits or accepted hard-constraint violations. An invalid proposal can be rejected and recorded without invalidating the whole run. |
| L03: useful evaluation selection | Same scenario library, numerical tools, expert card and information as the non-agent policies; three agent repetitions. | At least 20% lower median total elapsed cost to the same predictive-quality target on two designated pilot/toy cases, with comparable posterior quality where claimed. Include LLM time/cost and report uncertainty; otherwise make no efficiency claim. |
| L04: scenario coverage | Ambiguous and equivalent-history toys plus a case with a discriminating marker. | Retain all reference scenarios with posterior probability >=0.1 before claiming complete numerical uncertainty; verified weights agree within 0.05. If only a subset is explored, explicitly restrict the claim to it. |
| L05: expert interaction and unresolved cases | A missing useful constraint, a wrong constraint contradicted by independent evidence and an inherently unresolved control. | Identify the specific missing input or conflict; preserve hard constraints pending review; report remaining ambiguity. Count any new expert information and provide it to the paired control. Repeated runs must not replace non-identifiability with unsupported certainty. |

## Stage 3: two real pilot windows

Start with one GSWA Hamersley window and one SA Flinders Ranges window. Select
small exposed areas with 1-3 principal faults and several correlatable contacts.
Freeze boundaries before comparing methods. Record whether the projected marker
orientations provide independent directions, together with sensitivity to fault
dip. Classify a window as potentially informative or deliberately weakly
constrained using this audit, not its eventual fit.

Manually review contact pairing, unconformities, stratigraphic younging and
concealed fault segments. These reviewed relationships are shared inputs to all
methods through the E1 constraint card, with uncertainties retained. Use E0/E1
paired runs on the pilots to distinguish geologist assistance from algorithmic
performance; the full confirmation uses the practical E1 workflow. Keep stratigraphic interpolation flexibility
and regularisation comparable. If refitting the stratigraphy at every slip value,
use declared latent-field priors/marginalisation or training-only fitting and
held-out prediction. Training-contact residuals alone cannot validate slip.

Use five spatial folds per pilot window, withholding whole contact segments and
nearby bedding together, with a buffer based on the declared spatial error scale.
Keep all vertices and derived observations from a source feature in one partition.
Perform data-dependent interpolation, matching and hyperparameter fitting using
training data only. Define whether a separate known fault trace is conditioning
geometry; do not quietly use held-out contacts to estimate its dip.

Run all methods once per fold to screen cost and failure modes. Repeat M2 and at
most two promising alternatives with three inference seeds, reusing valid earlier
runs. Reserve a separate observation sector for final confirmation of choices
made from pilot cross-validation; do not use that sector for tuning.

## Stage 4: confirmatory Australian cases

Freeze modelling choices from the pilots, then test M2 and at most two qualifying
alternatives on three new regions, initially with three blocked folds and three
seeds. Expand only if uncertainty in method ranking warrants the additional cost.

| Region | Intended stress test | Selection constraint |
|---|---|---|
| Onshore Otway/Torquay, Victoria | Limited exposure, map uncertainty and competing fault interpretations. | Use detailed exposed surface mapping and bedding; no hidden seismic or well conditioning. Confirm marker availability before fixing the window. |
| Amadeus Basin, NT | Coupled folding/faulting and alternative event order; possible halotectonic complications. | Select an exposed detailed-map window. Use regional interpreted geology as documented history context, not independent slip truth. |
| McArthur River/Batten region, NT | Repeated units, uncertain correlation and fault reactivation. | Separate mapped outcrop, under-cover interpretation and event assumptions. |

Published sections may provide a secondary plausibility check. If they were
constructed from the same maps/bedding, do not call them independent validation.
All methods use map contacts, bedding and DEM only in the primary comparison.

## Measures and acceptance gates

Save measurements per feature group, fold, site, seed, budget and method. Aggregate
equally across sites/folds; do not allow a heavily digitised map to dominate.
Use paired spatial-block uncertainty estimates for method comparisons, not an
independent-vertex bootstrap. With few blocks, report the wide uncertainty.

| Measure | Definition | Proposed decision rule |
|---|---|---|
| Contact prediction | Median and 90th percentile geometric distance to a matching predicted contact at current terrain, in metres and relative to positional error. Also report missing/extra traces. | Scientific improvement: >=20% lower median error on eligible informative windows, supported by paired block comparisons. Report all weak-information windows separately. |
| Predictive calibration and sharpness | 50%, 80% and 90% predictive intervals for signed contact offset at predeclared transects; angular residuals for bedding. | Report coverage and mean interval score. Claimed improvements must not be obtained solely by making intervals wider. Real-data coverage is predictive consistency, not slip-truth coverage. |
| Unit prediction | Probabilities of observed exposed units on withheld transects/sites; proper categorical score such as Brier score. | No increased rate of contradictions with high-confidence observed juxtapositions; report ambiguous contacts separately. |
| Algorithmic equivalence | Component/profile summaries, important modes and predictive distributions against the verified same-target reference. | M4 and uncertainty claims from M3 must satisfy the Stage 2 reference tolerances. Small scalar-field residuals are insufficient. |
| Efficiency | Total elapsed time and core-hours to first meet a predeclared reference predictive-score band, followed separately by posterior-accuracy gates. | Acceleration target: >=3x lower median total cost on at least two real windows, including startup/training, with <=10% predictive-score degradation on other confirmation windows. Include comparison uncertainty. |
| Reliability | Build failures, invalid parameter proposals, missing predictions, sampler instability and rerun variability. | At least 95% of declared runs finish with valid outputs or an explicit scientific non-identifiability result. Computational/numerical failure is not non-identifiability. Never exclude failed runs from the denominator. |

For signed predictive errors, mean interval score at level 1-alpha is interval
width plus (2/alpha) times the distance of an observation outside the interval,
averaged over declared observations; lower is better. Use the same observation
error model when computing comparable predictive scores. Define numerical
contact-search radii and treat missing corresponding predictions as failures/
penalties fixed in advance, rather than silently dropping them.

For performance comparisons, use a provisional target within 10% of the verified
reference's mean interval score; a claim of equivalent uncertainty additionally
requires the posterior gates. If reference accuracy or timing is unresolved,
report a cost-quality curve and no speedup verdict. Effective sample size is a
diagnostic for appropriate samplers, not a common score for all ensemble methods.

## Required ablations

Use the small analytical/3D suite and pilot windows for these comparisons; avoid
an exhaustive cross-product on every real dataset:

1. Fixed geometry versus uncertain fault dip/position.
2. Fixed correspondence versus explicit alternatives.
3. Constant displacement versus small profile families.
4. Gaussian independent errors versus spatially correlated/robust errors.
5. Fixed stratigraphic interpolation choices versus their uncertainty.
6. One event versus a few geologically justified histories.
7. Surrogate without correction versus full-model correction, including cold cost.
8. Surface-only constraints versus the optional borehole extension.

## Optional mine-scale extension

Screen open-file Australian drillhole data for a distinctive correlatable marker,
usable lithological intervals, collars and downhole surveys. Select the dataset
only after that audit; no suitable specific mine dataset is assumed here. Use a
small faulted volume with a declared common stratigraphic interpretation.

First infer using the surface data, then add boreholes in batches chosen before
seeing outcomes. Hold out whole holes, not random depths. Compare predicted
contact depths, unit probabilities, uncertainty coverage and the reduction in
previously weak slip/depth-profile directions. Include logging/correlation and
trajectory errors. A depth marker improves identifiability only if its geometry
adds information; many parallel intersections need not resolve oblique slip.

Success: better held-out-hole interval score and correct synthetic recovery in a
matched mine-scale toy. Real drilling still does not establish complete slip truth.

## Deliverables and decisions

Retain the observation manifest and train/test partitions, exact parameter/prior
definitions, all run settings, full and proxy evaluation counts, samples or
feasible sets, predictions, failed-run records and per-test results. Produce:

- A slip-component plot showing constraints and unresolved directions.
- Along-strike slip/profile intervals, with observed and extrapolated portions.
- Held-out contact and unit predictions on the current topography.
- Calibration/interval-score plots and cost-quality curves.
- A scenario table showing assumptions, support, unresolved parameters and cost.
- A constraint-impact table showing the geologist's inputs, eliminated dimensions,
  excluded scenarios, remaining uncertainty, review time and computational savings.
- An agent comparison showing selected actions, evidence links, numerical and LLM
  costs, human interventions, scenario coverage and variability between runs.

Each test result is `pass`, `fail`, `inconclusive` or `not applicable`, with a
reason and supporting output. An unperformed test has no result. A failed
uncertainty gate cannot be offset by a good runtime or training fit.

Final decisions are per use case:

- **Recommended for uncertainty:** passes same-target accuracy, calibration,
  supported-mode retention and numerical-consistency tests.
- **Recommended for exploration/fitting:** predicts well and is efficient, but
  does not pass the uncertainty gates; uncertainty must be verified separately.
- **Useful geometric screen:** identifies feasible regions and weak directions
  cheaply, with its approximation limits demonstrated.
- **Useful agent assistance:** preserves expert constraints and numerical
  grounding, and improves review effort or scenario/evaluation selection. A claim
  of faster search requires L03; a claim of uncertainty additionally requires
  the numerical posterior gates and scenario coverage. Report interaction-only
  benefits separately when numerical search is not faster.
- **Inconclusive or unsuitable:** insufficient reference/data, numerical failure,
  or no useful cost-quality benefit. Preserve that result without forcing a winner.

The first execution milestone is A01-A07 plus G01/G03 and E01 on small domains,
followed by the two pilot data/constraint audits. This tests recovery, ambiguity,
geologist assistance and likely cost before committing to the basin comparisons.
Once the evaluators are verified, add L01/L02 and an L03 comparison using the small
toy evaluator before giving the agent an expensive 3D search budget.

## Research and data references

- Lisle and Walker (2013), separation-pitch constraints:
  https://doi.org/10.1016/j.tecto.2012.10.034
- Jessell et al. (2021), map2loop map deconstruction:
  https://gmd.copernicus.org/articles/14/5063/2021/
- Grose et al. (2021), LoopStructural fault representation:
  https://gmd.copernicus.org/articles/14/6197/2021/
- Del Moral, Doucet and Jasra (2006), SMC samplers:
  https://www.stats.ox.ac.uk/~doucet/delmoral_doucet_jasra_sequentialmontecarlosamplersJRSSB.pdf
- Emerick and Reynolds (2013), ES-MDA:
  https://doi.org/10.1016/j.cageo.2012.03.011
- Multilevel delayed-acceptance sampling:
  https://arxiv.org/abs/2202.03876
- GSWA mapping and spatial datasets:
  https://www.wa.gov.au/organisation/department-of-mines-petroleum-and-exploration/geological-survey-of-western-australia/state-maps-and-statewide-datasets
- SA maps and observation sources:
  https://www.energymining.sa.gov.au/industry/geological-survey/products-and-services/maps
- GeoVic geology and structural layers:
  https://resources.vic.gov.au/geology-and-data/maps-reports-data/geovic/geovic-layers
- NTGS maps and explanatory notes:
  https://resourcingtheterritory.nt.gov.au/data-and-publications/maps-and-explanatory-notes
- NTGS McArthur River Region map and GIS:
  https://geoscience.nt.gov.au/gemis/ntgsjspui/handle/1/81583
- SA Geodata, including potential borehole-extension inputs:
  https://dem-sdp.s3-ap-southeast-2.amazonaws.com/index.html
