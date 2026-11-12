# Flat zero contact beneath a rounded V-shaped unit contact

**The result depends on the geological criterion.** Gradient-normalised
smoothness increased departures from the flat lower-contact extension, but
retained a depression above the V where ordinary FDI produced an arch. The
flatness score alone is not an overall geological-quality ranking. See the
[subsequent four-way fold-constraint comparison](../fold_normalisation_combination/README.md)
for separate curvature, spacing and flatness diagnostics.

This is a synthetic approximation to the supplied image, not a
digitisation of its points. It reproduces the local change in contact spacing
and the large region outside the observations.

![Full domain and contact-region detail](two_contacts_n48_a0.png)

Yellow is the reconstructed level zero; magenta is level one. Dots are the
actual observations. Background colour is gradient magnitude, on the same
logarithmic scale in every panel (values below 0.05 use the darkest colour;
the saved metrics retain their actual values). The top row shows the full
domain and the bottom row enlarges the contact region. Native FDI's lambda
has different units; the matched baseline versus normalised comparison is
the controlled same-objective comparison.

## Data and scientific comparison

- Domain: horizontal and vertical coordinates both [-4,4].
- Zero contact: z=-0.25, sampled at 21 equally spaced x positions in [-1,1].
- Unit contact: z=1.1-0.95 exp(-(x/0.35)^2), at the same 21 x positions.
- This rounded V has minimum z=0.15 and flattens near z=1.1. The contact gap
  changes from 0.4 near the centre to approximately 1.35 at the sides.
- The observations are deterministic; no random seed is needed.
- Both grid resolutions (32 and 48 cells per horizontal/vertical axis) and
  both geometry angles (0 and 23 degrees relative to the grid) are retained.
- Lambda is 1e-4, 1e-3 or 1e-2; epsilon/reference-gradient is 0.01, 0.03 or 0.1.

This uses actual structured-grid FDI and its observation/native regularisation
assembly, not the triangular mesh in the illustration. The two-dimensional
field is represented on a unit-thickness 3D grid with an exact extrusion
constraint: all depth planes share unknowns. Collapsing the repeated integration
rows sums their quadrature weights and leaves the original matched objective
unchanged on that subspace. There are 1089 or 2401 independent field values.

The three methods are the ordinary native FDI regularisation rows, the matched
physically scaled Frobenius Hessian objective, and its gradient-normalised
counterpart from the earlier experiment. The latter two share all operators,
data, domain and boundary treatment. The production interpolator is unchanged.

Unlike the original one-contact experiment, **two distinct contact values
already fix the field's nonzero scale**. These fits contain contact observations
only: no orientation observations, full-gradient constraint, target magnitude,
Eikonal term, artificial field bound or objective ridge was added. A unit
gradient is not an appropriate desired field here. A natural declared reference
field is

`f_reference(x,z) = (z + 0.25) / (upper_contact(x) + 0.25)`.

It has the two desired contours everywhere and a strictly positive vertical
derivative, avoiding a reference critical-point singularity. Along the flat
contact its gradient magnitude is 2.5 at the centre and approaches 0.7407 at
the sides. This is a chosen extension for diagnostics, not a unique field or
extrapolation implied by the finite observations.

Epsilon is scaled by the inverse median observed vertical contact gap:
q_reference=0.8152793. Main epsilon is therefore approximately 0.02446.

## Extrapolation results

At each horizontal position, the contour crossing nearest the declared
reference is found and refined by bisection. Extrapolation RMS uses
1.2 <= |x| <= 3.5. The zero-contour error is its vertical departure from
z=-0.25. Unit-contour error is departure from the chosen flattened V extension.
All crossings are also counted, and missing coverage is reported separately.
An RMS computed over existing crossings never implies successful coverage.

At lambda=1e-3 and epsilon ratio 0.03:

| Grid cells | Angle | Method | Contact RMS | Zero extrapolation RMS | Unit reference extrapolation RMS |
|---|---:|---|---:|---:|---:|
| 32 | 0 | Native FDI | 0.000128 | 0.1407 | 0.0917 |
| 32 | 0 | Matched ordinary | 0.002993 | 0.1489 | 0.0931 |
| 32 | 0 | Normalised | 0.004469 | 0.3197 | 0.1958 |
| 32 | 23 | Native FDI | 0.000959 | 0.1349 | 0.0856 |
| 32 | 23 | Matched ordinary | 0.005921 | 0.1282 | 0.0507 |
| 32 | 23 | Normalised | 0.003352 | 0.2595 | 0.1284 |
| 48 | 0 | Native FDI | 0.000026 | 0.1308 | 0.0624 |
| 48 | 0 | Matched ordinary | 0.001671 | 0.1281 | 0.0605 |
| 48 | 0 | Normalised | 0.003562 | 0.3232 | 0.1496 |
| 48 | 23 | Native FDI | 0.000090 | 0.1242 | 0.0164 |
| 48 | 23 | Matched ordinary | 0.004394 | 0.1538 | 0.0750 |
| 48 | 23 | Normalised | 0.003129 | 0.3322 | 0.1489 |

In all 12 matched grid/angle/lambda pairs at the main epsilon, normalisation
increased both reported extrapolation RMS diagnostics. Its zero-contour RMS
was 2.02–2.76 times that of the matched ordinary penalty. This outcome persists
across both resolutions and angles; it is not a favourable run selection.

![Contour departures and gradient magnitudes](extrapolation_n48_a0.png)

The grey vertical band contains the contact observations. The dashed black
gradient curve is the declared reference field, not an optimisation target.

### At matched contact-data fit

To separate the extrapolation effect from looser data fit, lambda was tuned
separately for native and matched ordinary FDI until each matched the scalar
contact RMS of the finer normalised fit at lambda=1e-3, epsilon ratio 0.03.
The matched contact RMS values agree to approximately 3e-13 absolute.

| Angle | Method | Lambda | Contact RMS | Zero extrapolation RMS | Unit reference extrapolation RMS |
|---:|---|---:|---:|---:|---:|
| 0 | Native FDI | 0.261393 | 0.003562 | 0.1404 | 0.0755 |
| 0 | Matched ordinary | 0.002319 | 0.003562 | 0.1319 | 0.0665 |
| 0 | Normalised | 0.001 | 0.003562 | 0.3232 | 0.1496 |
| 23 | Native FDI | 0.061403 | 0.003129 | 0.1327 | 0.0359 |
| 23 | Matched ordinary | 0.000552 | 0.003129 | 0.1524 | 0.0696 |
| 23 | Normalised | 0.001 | 0.003129 | 0.3322 | 0.1489 |

The normalised method is still substantially worse at matched contact fit.
These controls match physical scalar contact RMS, rather than row-normalised
data energy. No observation, anchor or gradient constraint was changed.

## Convergence and artefacts

There are 62 saved sweep fits (including two alternative-start probes), plus
four retained matched-contact controls. Every sweep fit reported optimiser
success and had an actual reduced-objective gradient infinity norm below
9.33e-7. Nonlinear fits required at most 173 evaluations. Total sweep solver
time was approximately 50.2 seconds, with a maximum 2.94 seconds for one fit.
No required solve was abandoned. Preliminary unconditioned TRF solves reached
the same qualitative result more slowly and with larger first-order residuals;
they were superseded by the verified conditioned optimiser, not included as
the final reported sweep.

The nonlinear optimiser is L-BFGS in variables whitened by a Cholesky factor of
the matched quadratic Hessian. Whitening is an invertible variable change,
not a frozen-denominator surrogate or an extra scientific regulariser. The
actual quotient objective and its full analytic gradient are used, including
the denominator derivative. Initial values come from ordinary native FDI rows.
The 48-cell middle-lambda fits were also started from the matched quadratic
solution: energies agreed to 5e-13 relative, and node values to 3e-6 maximum
absolute difference. This does not prove uniqueness or global optimality.

Some converged solutions are geometrically poor. On the 32-cell rotated grid,
lambda=1e-4, normalised epsilon ratios 0.01 and 0.03 lost extrapolated crossings:
zero coverage was 62.7% and 68.6%, unit coverage 53.0% and 51.4%. They also
introduced multiple crossings. These fits are retained in the metrics and
fields. Epsilon sensitivity and orientation effects matter here, unlike the
earlier benign one-contact patches. The main illustrated middle-lambda cases
have full coverage. Across the sweep the minimum collocated grid gradient was
0.00438; low-gradient/critical regions are therefore a real diagnostic concern.

The rounded V is sharp relative to both grids: its minimum radius of curvature
is about 0.0645, whereas cell widths are 0.25 and 0.1667. These results compare
the penalties on finite grids; they are not a continuum convergence result.
The contour interpolation wiggles near the V and orientation dependence remain
visible. No claim is made that either method gives the correct extrapolation
from these finite contact observations alone.

## Reproduce and inspect

```powershell
.venv/Scripts/python -m loop_interpolation.experimental.benchmark_two_contacts --max-evaluations 1000
.venv/Scripts/python docs/experiments/two_contact_extrapolation/match_contact_fits.py
```

The first command runs the full deterministic sweep and saves plots, fields,
observations, histories, configuration and CSV/JSON metrics in this directory.
The second adds the contact-fit matched controls. To redraw the main figures
without solving, add `--plot-only` to the first command.

- `metrics.csv`, `metrics.json`: all sweep fits, messages and actual-objective histories.
- `matched_contact_metrics.json`: four additional matched-contact controls.
- `samples/*.npz`: real observations, every node value, contour-root profiles,
  crossing counts and gradients along the reference zero line.
- `config.json`, `environment.json`, `source_manifest.json`: deterministic
  inputs, package versions and source hashes.
- [Rotated main comparison](two_contacts_n48_a23.png) and
  [rotated extrapolation profiles](extrapolation_n48_a23.png).

The new tests check that there are exactly two scalar isovalues and no added
gradient constraints, that collapsed quadrature equals the full extruded 3D
objective, that the reduced nonlinear gradient matches finite differences,
and that the conditioned solve decreases the actual objective while preserving
the extrusion. All four new checks plus the ten original experiment checks
passed (14 total). Scoped Ruff passed. Existing production FDI code was not
modified, and the earlier experiment's files and recorded source hashes remain
unchanged.
