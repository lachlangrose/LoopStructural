# Combining fold constraints with gradient-normalised FDI smoothness

**The combination works: it retains the V-shaped fold above while keeping the
lower contact much flatter.** Normalised smoothness alone already avoids the
arch, but bends the lower contact. Adding the fold model improves that trade-off;
ordinary smoothness with the same fold model also avoids the arch. At the primary weights,
normalised smoothness produces a broader, shallower fold and smaller mean
vertical spacing; ordinary smoothness produces more uniform spacing. Stronger
fold weights make the normalised combination more competitive. There is no
weight-independent winner demonstrated here.

![Four-way comparison](four_way_n48_a0.png)

Top row: no fold constraints. Bottom: exactly the same fold constraints supplied
to both methods. Yellow is the zero contact, magenta the unit contact. Colours
are actual FDI gradient magnitudes on one shared logarithmic scale. The
comparison uses the same contact points, grid, domain, boundary treatment and
lambda within each column pair. No production FDI implementation was changed.

## Geological information supplied

The contacts and domain are the same as the previous case: 21 samples at zero
on z=-0.25 and 21 samples at one on
g(x)=1.1-0.95 exp(-(x/0.35)^2), with observed x in [-1,1] and model domain
[-4,4] x [-4,4]. The field is exactly extruded in the third direction on the
real FDI structured support. Two isovalues retain the nonzero field scale.

The new information is an explicit direction model. Let
s=(z+0.25)/(g(x)+0.25). Its bedding tangent is proportional to

`t = (1, 0, clip(s, 0, 1) * g'(x))`.

This means horizontal bedding below zero, a transition through the interval,
and V-shaped bedding directions persisting above the unit contact. The fold
axis a is local y and the reference fold-normal direction d is local +z.
All vectors rotate with the geometry for the 23-degree cases.

![Input direction prior](fold_direction_prior.png)

These arrows are **model assumptions, not independently observed directions**.
The fold model already contains the desired continuation of fold sense.
Improvement after adding it is not independent evidence that the smoothness
regulariser discovered that geometry. It was fixed before the comparison and
is identical for ordinary and normalised smoothness.

The existing FDI helper used by `FDFoldInterpolator` assembles three families:

- Bedding orientation: gradient dot t = 0.
- Fold axis: gradient dot a = 0; redundant under this exact extrusion.
- Signed fold normalisation: gradient dot d = c.

The primary c is the inverse median observed gap, 0.8152793, **not a unit
gradient magnitude target**. Its sign follows increasing values in local +z.
It is deliberately soft: a constant vertical derivative cannot exactly fit
both contacts everywhere, since their gap varies from 0.4 to about 1.35.

Fold equations are sampled at world-grid cell centres, using physical
trilinear derivative coefficients. FDI's numerical row normalisation is
undone, then unit-thickness area quadrature is applied. This keeps confidence
independent of cell count and does not scale the target when its weight changes.
The orientation and axis energy coefficients are 0.1 and the projection energy
coefficient is 0.01. FDI's residual weights are their square roots times the
quadrature factor. A separate multiplier is used only in sensitivity checks.

The existing anisotropic fold second-derivative penalty is not added: doing so
would change the regulariser being compared. The smoothness operators remain
the verified physical finite-difference gradient and full Frobenius Hessian
from the earlier experiment. The fold terms use the actual existing FDI
interpolation-gradient rows, not substituted central differences.

## Four-way result

This is a 2 x 2 comparison: ordinary/normalised smoothness, each without/with
the same fold constraints. The main sweep has 48 fits: 32- and 48-cell grids,
0- and 23-degree geometry angles, three lambdas (1e-4, 1e-3, 1e-2), and the
four combinations. Main epsilon is 0.03 times the reference gradient.

The representative case below is the finer aligned grid at lambda=1e-3,
selected in advance. Positive level-2 relief means its centre rises above the
shoulders at x=+-1, reversing the sense of the observed V; negative means it
retains a depression. Spacing is measured from level 1 to level 2 over |x|<=1.

| Smoothness | Fold constraints | Contact RMS | Level-2 relief | Lower flatness RMS outside data | Mean vertical spacing, 1 to 2 | Spacing CV |
|---|---|---:|---:|---:|---:|---:|
| Ordinary | No | 0.001671 | +0.063 | 0.1281 | 2.425 | 14.5% |
| Normalised | No | 0.003562 | -0.119 | 0.3232 | 1.313 | 22.8% |
| Ordinary | Yes | 0.002539 | -0.564 | 0.0344 | 1.823 | 7.9% |
| Normalised | Yes | 0.002646 | -0.442 | 0.0361 | 1.585 | 11.9% |

With the fold model, the two contact RMS values differ by about 4%, giving a
comparison at similar data fit. Both retain the right fold sense and improve
lower flatness substantially. Normalisation brings mean vertical spacing
closer to the projection target's 1/c=1.227, but gives greater spatial variation
and a shallower depression at these weights. Neither mean spacing nor fold
amplitude is an independently observed truth in the extrapolated region.
Spacing along d is **not** perpendicular stratigraphic thickness.

![Fold sense, spacing and flatness](layer_diagnostics_n48_a0.png)

At the main epsilon across all 12 grid/angle/lambda cases per combination:

- Ordinary without folds develops a level-2 arch and a negative central
  curvature in 12/12 cases.
- Normalised without folds has no arch in 11 assessable cases; one coarse,
  weakly regularised rotated result has missing/ambiguous upper crossings and
  is unassessable, not credited as a success.
- Both fold-constrained methods have no level-2 arch or curvature reversal in
  all 12 cases where the central diagnostic is assessable.
- Mean lower-contact flatness RMS is 0.145 ordinary and 0.332 normalised without
  folds, versus 0.0485 ordinary and 0.0527 normalised with folds.

The rotated middle-lambda results agree qualitatively: ordinary/normalised
with folds have level-2 relief -0.532/-0.436 and flatness RMS 0.0375/0.0387.
See [rotated contours](four_way_n48_a23.png) and
[rotated diagnostics](layer_diagnostics_n48_a23.png).

## What the normalisation constraint contributes

Fourteen additional fits check the normalisation target, fold confidence,
epsilon and initialisation, giving **62 saved fits** in total.

At the finer aligned middle-lambda case:

- **Directions alone:** the lower contact is nearly flat, but neither method
  supplies a unique level-2 crossing in the evaluated central interval. Good
  flatness alone would misleadingly look successful. The field amplitude away
  from the contacts remains poorly controlled.
- **Spatial target:** replacing c by 1/(g+0.25) between the contacts and c
  outside is compatible with a piecewise reference field. Ordinary/normalised
  flatness RMS improves from 0.0344/0.0361 to 0.0183/0.0214, while level-2 relief
  changes little (-0.563/-0.437). This target explicitly adds contact-spacing
  information; it is a sensitivity check, not new independent observations.
  The projection target changes at the contacts and is not a production
  prescription for arbitrary models.

Changing both fold energy coefficients by the same multiplier gives:

| Fold multiplier | Smoothness | Contact RMS | Level-2 relief | Mean spacing, 1 to 2 | Spacing CV |
|---:|---|---:|---:|---:|---:|
| 0.25 | Ordinary | 0.001720 | -0.258 | 2.256 | 10.9% |
| 0.25 | Normalised | 0.002908 | -0.178 | 1.823 | 15.2% |
| 1 | Ordinary | 0.002539 | -0.564 | 1.823 | 7.9% |
| 1 | Normalised | 0.002646 | -0.442 | 1.585 | 11.9% |
| 4 | Ordinary | 0.005217 | -0.805 | 1.463 | 4.2% |
| 4 | Normalised | 0.003916 | -0.841 | 1.271 | 3.4% |

At stronger fold confidence, normalisation gives a deeper fold, more uniform
spacing, mean spacing nearer 1/c, and a better contact fit than ordinary
smoothness at the same weights. This is evidence of a useful interaction, not
a universal optimum or validation of those weights for real data.

For the combined method, epsilon/reference ratios 0.01, 0.03 and 0.1 gave
level-2 relief -0.44179, -0.44182 and -0.44217, with flatness RMS about 0.0361.
The finer middle-lambda folded fits were also started from their own ordinary
solutions. Final energies agreed to 1.2e-13 relative, and node values to
1.7e-7 maximum absolute difference. Nonconvex uniqueness/global optimality is
not established by this limited start check.

## Metrics, convergence and limits

Contours at levels 0, 1, 1.25, 1.5, 2, 2.5 and 3 are evaluated at fixed x
locations, within the actual support and vertical search range [-3.8,3.8].
All sign-changing crossings are counted. A branch nearest the stated prior
is retained for plotting, but ambiguous crossings are excluded from relief,
curvature and spacing scores and their coverage is saved separately.

Relief compares the centre with shoulders at +-1. Central curvature is a
quadratic graph fit in the common [-0.6,0.6] window, requiring unique crossings
at 80% of locations. Positive graph curvature is V-like, negative is arch-like.
Relief >0.02 and curvature <-0.02 use declared tolerances to avoid interpreting
roundoff as a sign reversal. The primary spacing CV uses the same level-1 to
level-2 interval and x-window for every field; all four representative cases
have 100% coverage. Additional metrics cover higher intervals where present.

All 62 fits reported success and an actual reduced-objective gradient infinity
norm below 5e-7. Maximum evaluations were 174. Total solver time was 43.7 s,
maximum 2.40 s per fit; plots/evaluation add overhead. The nonlinear optimiser
uses the full numerator/denominator gradient and an invertible baseline
whitening, not frozen weights or an extra objective ridge.

Missing upper levels at high lambda, ambiguous contours in the coarse rotated
weak case, sampled low-gradient fractions, orientation angles and physical
projection residuals are saved. In particular, a missing upper surface is not
reported as having zero curvature error. Gradient checks at nodes and cell
centres do not rule out subcell critical regions. The V remains sharp relative
to these grids, and the fold-direction field is prescribed from the synthetic
contacts. This is a controlled demonstration, not independent geological
validation or a continuum convergence result.

## Reproduce and verify

```powershell
.venv/Scripts/python -m loop_interpolation.experimental.benchmark_fold_normalisation
```

Use `--output reports/fold_combination_replay` for a separate replay, or
`--plot-only` to redraw saved results. `config.json` records the deterministic
settings; no random seed is used. `metrics.csv` contains every scalar result,
and `metrics.json` adds actual-objective histories and solver messages.
`samples/*.npz` saves every field, contact observation, extracted contour
profile, crossing count and layer spacing. `environment.json` and
`source_manifest.json` record versions and source hashes.

There are 48 passing targeted tests, including the existing FDI fold tests,
the earlier smoothness/two-contact checks, and new checks for direction geometry,
physical derivative scaling of fold rows, invariance of the target under weight
changes, full nonlinear finite-difference gradients, curvature sign, spacing,
missing contours and unchanged contact/smoothness operators. Scoped Ruff and
Black pass. Existing production files and the earlier experiment's recorded
source remain unchanged; the earlier report's overly broad failure summary
has been clarified to distinguish flatness from geological fold sense.
