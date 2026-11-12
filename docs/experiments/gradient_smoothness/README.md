# Gradient-normalised FDI smoothness experiment

Run on 6 November 2026. **The field-amplitude hypothesis is supported on these
small synthetic patches; a general geometric improvement is not supported.**
Normalisation reduced the surface gradient-magnitude RMSE from one by 65–96%
in all 24 curved comparisons. Extracted surface distance improved in only 8/24;
contact residuals increased in all 24. This is an opt-in research module, not a
change to the default interpolator.

## Reproduce

From an environment with this workspace's editable packages, NumPy, SciPy,
scikit-image and Matplotlib (the versions used are in `environment.json`):

```powershell
.venv/Scripts/python -m loop_interpolation.experimental.benchmark_gradient_smoothness --config docs/experiments/gradient_smoothness/config.json --output reports/gradient_smoothness_replay
```

The equivalent portable invocation starts with `python -m`. On this machine the
saved sweep took about four minutes, with 209 seconds spent inside the solvers.
Tests were also running, so timings are descriptive rather than isolated speed
measurements. To recompute metrics and figures from the saved fields, without
optimisation:

```powershell
.venv/Scripts/python -m loop_interpolation.experimental.benchmark_gradient_smoothness --output docs/experiments/gradient_smoothness --reanalyse
```

`config.json` saves the seed (20261106), geometries, resolutions, angles,
regularisation strengths, epsilon ratios and iteration budget. `metrics.csv`
contains all scalar results. `metrics.json` additionally contains actual
objective histories (including trial evaluations), optimiser messages and
first-order residuals. `samples/*.npz` saves the actual observations, all node
values, extracted meshes, withheld surface points, gradient magnitudes,
curvatures, anchor distances and angular errors. No favourable run was removed.
There are 182 runs: 36 native-row references, 36 matched baselines, 108
normalised fits and two alternative-start probes.

## Implementation and objective

The opt-in code lives in
`packages/loop_interpolation/src/loop_interpolation/experimental/gradient_smoothness.py`.
It is not imported by the default package initialiser. No production FDI,
tetrahedral, RBF or solver implementation was modified.

The unknowns are the values on the real three-dimensional `StructuredGrid`.
The exact same FDI-assembled contact and orientation rows form `E_data` in both
main objectives. Nine contacts all have isovalue zero (one surface), seven
orientations contribute two homogeneous tangent equations each, and one full
nonzero gradient fixes the field scale. Despite the production setter's
`set_gradient_constraints` name, FDI assembles these observations as directions;
`set_normal_constraints` supplies the full vector. We use those actual assembly
methods. FDI's existing data-row normalisation is retained.

The full gradient anchor has magnitude one and lies at local surface coordinates
(-0.29, -0.19). Its three equations come from FDI's full-gradient assembly and
are imposed exactly by sparse affine elimination of three unknowns. The maximum
measured physical anchor residual over all 182 runs was 5.17e-16. There is no
Eikonal term, target-magnitude loss, artificial field bound or scientific ridge.

Both main methods integrate over **all grid nodes**. First differences are
centred inside and second-order one-sided at the outer boundary. Pure second
differences use [1,-2,1]/h² inside and [2,-5,4,-1]/h² at a boundary (reversed at
the upper boundary). Mixed differences are tensor products of physical first
differences, with 1/(h_a h_b) scaling. Thus all gradient and Hessian components
are collocated; analytic second derivatives of individual trilinear cells are
never used as the regulariser. Tensor trapezoid weights supply `V_i`, including
half weights on faces. A supplied mask selects integration centres while
retaining complete stencils and all unknowns; these benchmarks use no mask.

The matched quadratic objective is

`||A_data u - b||² + lambda sum_i V_i (xx²+yy²+zz²+2xy²+2xz²+2yz²)`.

The nonlinear residual for Hessian component `k` at node `i` is

`sqrt(lambda V_i multiplicity_k) (H_k u)_i / sqrt(sum_j (G_j u)_i² + epsilon²)`.

Its Jacobian is the scaled Hessian row divided by the denominator **minus**
the denominator derivative, proportional to
`(H_k u)_i sum_j (G_j u)_i (G_j)_i / denominator³`. SciPy's trust-region
nonlinear least-squares solver uses this full sparse Jacobian and LSMR for its
linear steps. This is not frozen-weight iteration. Epsilon is 0.03 times the
gradient-anchor magnitude in the main comparison; 0.01 and 0.1 are also tested.

The ordinary FDI row solution, with the same exact anchor, initialises every
main nonlinear fit. The quadratic baseline and native reference use sparse
direct normal equations on the reduced variables. This small-system choice
is not intended as a scalable production solver.

### Why native FDI is a separate reference

Inspection covered `_finite_difference_interpolator.py`, `_operator.py`,
`_discrete_interpolator.py`, the structured support and its operator factory.
Native structured FDI does **not** implement the matched physical objective:

- `get_operators` applies an additional 1/4 residual weight to mixed families.
- `add_constraints_to_least_squares` divides every stencil row by its L2 norm,
  removing an overall physical derivative scale; structured masks do not
  include the required spacing factors or volume quadrature.
- Interior families use strictly interior centres. Separate border families
  extend pure curvature rows across faces and also overlap interior rows.

Consequently native lambda has different units and relative effects. In the
reference, `sqrt(lambda)` is passed as FDI's residual weight, including borders;
native results are contextual and are not used to claim the normalisation
effect. "Native" here means the ordinary Python FDI regularisation rows, not
the Rust solver. The reference uses an exact anchor and no ridge so the
initialisation shares the controlled experiment's nonzero scale.

## Benchmarks and evaluation

The fixed Cartesian domain is [-0.6,0.6] x [-0.55,0.55] x [-0.32,0.32]. Each
case has 8³ or 12³ cells (729 or 2197 nodes), with geometry rotated 0 or 23
degrees around y. All methods use the same observations, integration region
and boundaries within each case. Lambda is 1e-4, 1e-3 or 1e-2. Observations
are sparse and distinct from a fixed 17 x 13 withheld surface sample.

- Plane: local z=0.
- Cylinder: radius one, axis through local (x,z)=(0,-1), upper arc.
- Varying curvature: smooth extruded graph z=0.07 cos(4.5 x). Its absolute
  curvature is |f''|/(1+f'²)^(3/2), varying from near zero to 1.4175.

Cylinder distances are analytic. Graph distances are closest-point Euclidean
distances, solved to numerical precision, not vertical height differences.
The cylinder axis lies outside the full rotated domain. For the varying graph,
`(|z_local|_max + 0.07) * 1.4175 < 1`; hence the squared closest-point objective
has positive second derivative everywhere. The distance field has a unique
closest point throughout this box, avoiding a medial-axis singularity.

Geometry is measured in two ways. Marching cubes extracts the zero surface;
triangle-centroid distances to the known surface are area-weighted for the
reported mesh RMS. This is a sampled extracted-mesh metric, not an exact
Hausdorff distance or continuous surface integral. The second metric finds the
nearest zero crossing along each withheld true normal within ±0.18, then
bisects the root. This is a normal-projection distance, not a claim of exact
closest reconstructed-surface distance. Both directions of evaluation help
expose extrapolation and coverage failures.

Gradients for field/normal evaluation are the real support's trilinear
gradients. Normal errors use normalised gradients, with polarity retained.
Gradient magnitudes, local curvature and Euclidean anchor distance are measured
at the reconstructed withheld roots. Mesh normal error is also saved over the
full extracted patch. Critical-region fractions use the collocated physical
grid gradients with thresholds 0.1 and 0.03 times the anchor magnitude.

## Results

The following averages include **all** 12 curved cases per geometry at the
main epsilon, paired at the same lambda, grid and angle:

| Geometry | Metric | Matched baseline | Normalised |
|---|---|---:|---:|
| Cylinder | Extracted mesh RMS distance | 0.014370 | 0.014616 |
| Cylinder | Withheld normal-projection RMS distance | 0.007505 | 0.007839 |
| Cylinder | Withheld normal angular error, degrees | 2.483 | 2.508 |
| Cylinder | Surface gradient-magnitude RMSE from 1 | 0.2534 | 0.0317 |
| Cylinder | Mean surface gradient magnitude | 0.7530 | 0.9964 |
| Cylinder | Contact RMS residual | 0.001027 | 0.001476 |
| Varying | Extracted mesh RMS distance | 0.004042 | 0.004174 |
| Varying | Withheld normal-projection RMS distance | 0.003936 | 0.004290 |
| Varying | Withheld normal angular error, degrees | 2.020 | 2.080 |
| Varying | Surface gradient-magnitude RMSE from 1 | 0.2456 | 0.0251 |
| Varying | Mean surface gradient magnitude | 0.7618 | 1.0000 |
| Varying | Contact RMS residual | 0.000785 | 0.001141 |

Surface gradient-magnitude RMSE fell in all 24 curved pairs, with median
reductions of 87.9% (cylinder) and 89.8% (varying). Extracted geometry improved
in 8/24, withheld angular error in 10/24 and contact RMS in 0/24. The geometric
RMS ratio normalised/baseline ranged from 0.959 to 1.142; 23/24 pairs were
within 10%, so the amplitude reduction persists at similar **geometric** fit.
The contact fits are not equal: median contact RMS ratios are 1.438 and 1.455.
The modest lambda sweep does not bracket finely matched data energies; we do
not claim a matched-data-fit improvement. Both contact and direction residuals
can fall when field amplitude shrinks, so data energy alone is not geometry.

For the middle lambda (1e-3), the grid/orientation breakdown below reports
mesh distance and the distance-field amplitude diagnostic separately:

| Geometry | Cells | Angle | Mesh RMS, baseline -> normalised | Gradient RMSE, baseline -> normalised |
|---|---:|---:|---:|---:|
| Cylinder | 8 | 0 | 0.013653 -> 0.014439 | 0.1698 -> 0.0456 |
| Cylinder | 8 | 23 | 0.011899 -> 0.011703 | 0.2075 -> 0.0374 |
| Cylinder | 12 | 0 | 0.015191 -> 0.015569 | 0.3187 -> 0.0133 |
| Cylinder | 12 | 23 | 0.012884 -> 0.012558 | 0.3385 -> 0.0202 |
| Varying | 8 | 0 | 0.004539 -> 0.004501 | 0.1673 -> 0.0350 |
| Varying | 8 | 23 | 0.003906 -> 0.003899 | 0.1929 -> 0.0267 |
| Varying | 12 | 0 | 0.002775 -> 0.002957 | 0.3315 -> 0.0127 |
| Varying | 12 | 23 | 0.003108 -> 0.003198 | 0.3030 -> 0.0204 |

Refinement does not monotonically improve cylinder geometry. Baseline
amplitude suppression becomes stronger on the finer grid, whereas normalised
magnitudes remain close to one. Rotation changes both errors. FDI's data-row
normalisation also changes the effective physical weight of direction data
with spacing. These are fixed-grid comparisons of the two regularisers, not
a continuum convergence study or an orientation-invariant method.

### Curvature and anchor distance

The varying-curvature surface still has a negative correlation between gradient
magnitude and absolute curvature. Mean correlation becomes more negative
(-0.308 -> -0.633), despite the much smaller amplitude variation. Correlation
alone would therefore give a misleading claim about improvement. A descriptive
linear fit `q = intercept + b_curvature * curvature + b_distance * anchor_distance`
at each varying case, then averaged, gives curvature slope -0.0501 -> -0.0223
and distance slope -0.2441 -> +0.0043. This supports reduced deficits and reduced
anchor-distance decay, not elimination of curvature dependence or causation
from this regression. The geometry and anchor-distance distributions are not
independent. Cylinder curvature is constant, so its curvature correlation is
undefined and saved as null.

For the finer rotated varying case at lambda=1e-3, the surface magnitude's
5th–95th percentile is 0.654–0.847 for baseline and 0.968–1.031 for normalised.
Unit magnitude here is a **signed-distance-field diagnostic**, not an additional
observation or a direct geometric correctness criterion. One contact surface
allows many valid field parameterisations away from the exact anchor.

### Convergence, epsilon and artefacts

Every solve reported success. The maximum reduced actual-objective gradient
infinity norm was 4.63e-7; every run passed a separately recorded 1e-6 first-order
check. Nonlinear fits used at most nine objective evaluations. In curved cases
the actual objective fell at least 25% from the initial native-row field.
Curved nonlinear fits had median runtime 2.88 seconds, maximum 8.55 seconds;
linear fits took roughly 0.03–0.24 seconds. Plane runs terminated at their
already exact initial solution. Plane mesh RMS was at most 5.9e-9 (extraction
precision), and gradient RMSE at most 1.84e-11.

Changing epsilon/anchor magnitude from 0.01 to 0.1 changed mesh RMS by at most
2.37e-5 and the gradient RMSE by at most 0.00405 within a curved case. This
limited sensitivity is observed away from low gradients; epsilon still changes
the energy near zero and breaks exact field-scale invariance when held fixed.

The two alternative starts (matched baseline instead of native rows, finer
rotated cylinder/varying, lambda=1e-3) reached objectives agreeing to 3e-12
relative and node values to 1.7e-7 maximum absolute difference. This checks
two local basins, not uniqueness or global optimality of this nonconvex problem.

No extra connected mesh components or multiple sign-changing zeros along the
withheld normal rays were found. Coverage was 100%. The minimum grid gradient
magnitude across all native, baseline and normalised runs was respectively
0.283, 0.592 and 0.909. No node or evaluated surface point fell below the 0.1
or 0.03 thresholds. These discrete diagnostics cannot rule out subcell critical
points, tangential zeros without a sign change, or artefacts outside the domain.

## Figures

The actual gradient magnitude (rather than its error from one) is also plotted
for lambda=1e-3 and epsilon=0.03 times the anchor magnitude. Surface profiles
show the mean and full range across y at each local x, for both geometry angles.
The section maps show the full x-z slice at y=-0.19, through the exact anchor,
with a shared 0–2 colour scale centred at one across all grids, angles and methods. Gradients
are evaluated from the saved FDI fields; no interpolation was refitted.

![Surface gradient magnitudes, finer grid](gradient_magnitude_surface_profiles_n12.png)

![Spatial gradient magnitudes, finer rotated grid](gradient_magnitude_sections_n12_a23.png)

[Coarser-grid profiles](gradient_magnitude_surface_profiles_n8.png),
[finer aligned sections](gradient_magnitude_sections_n12_a0.png),
[coarser aligned sections](gradient_magnitude_sections_n8_a0.png), and
[coarser rotated sections](gradient_magnitude_sections_n8_a23.png) are also saved.
Every new figure has an SVG version alongside the PNG. Recreate these figures
from the saved fields with:

```powershell
.venv/Scripts/python docs/experiments/gradient_smoothness/plot_gradient_magnitude.py
```

The plotting pass verified finite gradients, unit gradients everywhere in the
plane slices, and unit magnitude at every exact anchor to 1e-12 absolute tolerance.

Five additional isosurfaces at -0.10, -0.05, +0.05, +0.10 and +0.15 are shown
alongside zero in the following cross-sections. All panels use the same scalar
levels and colour scale. Thick contours are zero, dashed contours negative,
and thin solid contours positive. Their spacing illustrates the scalar-field
parameterisation away from the observed contact; the nonzero levels are not
additional observed geological contacts. These use lambda=1e-3 and epsilon
ratio=0.03, as above. Every added level intersects every plotted slice.

![Zero plus five additional isosurfaces](gradient_magnitude_sections_n12_a23_isosurfaces.png)

[Aligned finer-grid view](gradient_magnitude_sections_n12_a0_isosurfaces.png),
[aligned coarser-grid view](gradient_magnitude_sections_n8_a0_isosurfaces.png), and
[rotated coarser-grid view](gradient_magnitude_sections_n8_a23_isosurfaces.png)
are also saved, with SVG copies. Regenerate with:

```powershell
.venv/Scripts/python docs/experiments/gradient_smoothness/plot_gradient_magnitude.py --extra-isosurfaces
```

![Sweep: geometry, normals and field amplitude](comparison.png)

![Curvature, anchor distance and actual objective](field_behaviour.png)

![Zero surfaces in the y=0 section](geometry_sections.png)

## Verification

`packages/loop_interpolation/tests/test_gradient_smoothness_experiment.py`
checks anisotropic physical derivative scaling, all mixed components, boundary
rows and the Frobenius multiplicities against analytic quadratic fields; the
full and reduced nonlinear Jacobian against finite differences; the
epsilon-dominated gradient; approximate fixed-epsilon scale invariance and
the expected epsilon-dependent failure; exact plane reconstruction and anchor;
direction-only data rows; mask semantics; preservation of default FDI rows;
analytic distance normals and the domain's medial-axis exclusion; and plane
zero-surface extraction without double-counting a sampled root. All ten tests
passed. The interpolation-package suite also passed (611 passed, 47 skipped,
2 expected failures, before the final five verification cases were added).

Only the experimental module and its tests were formatted. Scoped Ruff passed.
The repository-wide checks and their environment limitations are recorded in
`validation.md`.

## Interpretation

These results support an amplitude-suppression mechanism in ordinary Hessian
regularisation. For a distance-like field scaled by a local factor, the
surface's curvature contribution to the unnormalised Hessian energy carries
the squared gradient amplitude. Dividing by the squared gradient removes much
of that incentive where epsilon is small. However, this controlled experiment
does not establish better surface recovery: geometry and normal errors are
mixed and slightly worse on average, contact residuals increase, and curvature
dependence remains. It also does not establish uniqueness, performance on
closed surfaces, noisy observations, real geological data, other support types
or very low-gradient initialisations. There is one reproducible observation
seed, not repeated-sampling evidence or a statistical confidence interval.
Keeping this pathway experimental is
consistent with the evidence.
