# Two faults, including one that terminates on another

**Both 11-cell-per-axis experiments passed the geometric and topological checks.**
The terminating case has three fault blocks; the crossing control has four.
Each also contains three inclined horizons, displaced independently by block.
The new combined test suite passed **27/27 tests**, including real MMG tests of
both junction types. No MMG C source was modified.

There is also a reproducible **coarse-mesh failure**: MMG returns success and a
watertight volume mesh, but distorts a horizon. The validator rejects that run.
The successful meshes contain slivers, so these are conformity proofs rather
than simulation-ready quality meshes.

These original results used **level-set cutting with ordinary adaptation
disabled**. A subsequent experiment enables actual MMG remeshing and markedly
improves element quality while preserving the interfaces. See
[REMESHING.md](REMESHING.md) for the new result files and before/after metrics.

## Geometry and block fields

The cube is still [-1,1]^3. The primary fault is x=0. The secondary fault is

```text
g2 = y - 0.35*z - 0.1 = 0.
```

In the **terminating** case, the secondary fault exists only for x>=0. Thus its
boundary is the line `(x,y,z)=(0, 0.1+0.35*t, t)`, -1<=t<=1, on the primary.
The primary continues through that line; the secondary stops there. The union
of the two surfaces has a T junction with three incident fault sheets. This
intentional sheet junction is distinct from an unintended volume-mesh T-junction
or hanging node: every volume face must still have one or two incident tets.

| Block | Region | Stratigraphic displacement |
| --- | --- | --- |
| 1 | x<0 | 0 |
| 2 | x>0, g2<0 | 0.25 |
| 3 | x>0, g2>0 | 0.40 |

The restored coordinate within a chosen block is
`f_b = z - 0.2*x + 0.1*y - displacement_b`.
The three horizons are f_b=-0.5, 0, 0.5. These are inclined planes whose traces
are allowed to differ on the shared fault vertices. Values from different
blocks are evaluated in different MMG calls, with no smoothing across a fault.
This is a synthetic compartment model, not a full fault-kinematic restoration.

The **crossing control** extends g2=0 across the whole cube. Four blocks have
displacements 0, 0.15, 0.25 and 0.40, ordered as left/lower, left/upper,
right/lower and right/upper. Four fault sheets meet along the junction.

## Method and executed results

Insert x=0 first. For the terminating fault, split only the right-hand material
with g2, while the left material is `nosplit`. The important observation is that
MMG refines the shared primary interface while preserving a single left block.
It does not create a geological secondary fault on the left. Next insert each
inclined horizon one block at a time, preserving the other material references.
The terminating run uses 11 level-set calls; the crossing run uses 14.

This uses the existing [MMG material mapping mode](https://mmgtools.org/tutorials/tutorials_detailed_options.html).
Material and interface preservation are verified after each cut; neither MMG's
exit status nor its manifold message is used as proof of geological correctness.

| Result | Terminating secondary | Crossing control |
| --- | --- | --- |
| Vertices | 4,791 | 5,355 |
| Tetrahedra | 23,428 | 26,346 |
| Final checks passed | 61/61 | 76/76 |
| Fault blocks / geological regions | 3 / 12 | 4 / 16 |
| Tetrahedral volume | 8 | 8 |
| Hanging-node incidences | 0 | 0 |
| Primary fault area | 4 | 4 |
| Secondary fault area | 2.11896201004 | 4.23792402008 |
| Shared junction edges | 55 | 58 |
| Junction length | 2.11896201004 | 2.11896201004 |
| Fault sheets incident at each junction edge | 3 | 4 |
| Minimum normalized MMG element quality | 1.14401e-5 | 1.45377e-6 |

Quality 1 is a regular tetrahedron. The small minima matter: restricting
adaptation keeps exact planes but can accumulate very thin elements. The final
terminating/crossing meshes have 2/5 tets below MMG's internal unnormalised
level-set quality threshold. A later cut therefore needs renewed validation.

![Secondary fault ending on the primary](outputs/two_faults/terminating/fault_network.png)

![Horizontal section showing the T junction](outputs/two_faults/terminating/cross_section_z0.png)

![Inclined stratigraphy in vertical section](outputs/two_faults/terminating/cross_section_y0.png)

The geometric oracle is independent of the remeshed connectivity: plane sections
are computed by clipping against exact cube/block half-spaces. Each observed
horizon patch must match that polygon's area. Every fault/horizon intersection
must form a contiguous, non-overlapping chain of actual shared mesh edges with
the analytic endpoints. The fault junction must span its full analytic length,
have the correct sheet incidence, and be incident to all three/four blocks.
Raw MMG material references must match the model and the completed cut sequence.

Tolerances are unchanged: coordinates/planes 1e-8, cube volume 1e-8,
areas/lengths 1e-7, and accepted tet volumes strictly greater than 1e-14.
The full geometric vertex-on-face/edge search runs after every cut.

## Coarse-mesh failure and likely mechanism

At **five cells per axis**, the terminating example fails on the third block's
first horizon. The final failed cut returns MMG exit code 0, and the volume
remains watertight and positive. Nevertheless:

- 37 tetrahedra straddle the intended horizon plane.
- The exact-plane patch area is 0.869468272421 instead of 0.925690721369.
- Its intersection with the secondary fault is incomplete.
- Some MMG material labels disagree with the intended geological units.

The input to that call contains three tets below MMG's internal quality
threshold. The [MMG 5.8.0 preprocessing loop](https://github.com/MmgTools/mmg/blob/v5.8.0/src/mmg3d/mmg3d2.c#L691)
can force all four nodal scalar values negative around a sufficiently poor tet
connected to the negative domain. It applies before the actual cut. The threshold
is set by [MMG5_EPS=1e-6](https://github.com/MmgTools/mmg/blob/v5.8.0/src/common/mmgcommon_private.h#L87).

A diagnostic that emulates that loop predicts nine changed vertex values,
including two sign reversals. This is consistent with the observed failure;
we did not instrument MMG to trace the internal values, so it is evidence for
the mechanism rather than a direct runtime trace. The diagnostic never changes
the scalar values sent to MMG. Increasing to 11 cells succeeds for this exact
model; that does not establish monotonic improvement with resolution.

The next practical step is controlled quality improvement between cuts, with
the same junction and geometric checks repeated afterward. If exact affine cuts
must be guaranteed independently of element quality, MMG would need a supported
way to control this scalar-altering prepass. We have not changed its C source or
weakened validation to obtain the successful result.

## Reproduce and inspect

From this experiment directory, with the dependencies from README.md:

```sh
python scripts/run_two_faults.py --case both --cells 11 --output outputs/new-two-fault-run
python -m pytest -q -c pyproject.toml --basetemp outputs/new-test-run
```

To reproduce the expected geometry failure (the driver exits nonzero):

```sh
python scripts/run_two_faults.py --case terminating --cells 5 --no-pictures --output outputs/new-coarse-failure
```

Choose a fresh directory for every run. `--case terminating` or `--case crossing`
runs only one configuration. `--no-full-scan` is diagnostic-only and is never
reported as full success.

Saved results:

- [Terminating result](outputs/two_faults/terminating/results.md) and [full metrics](outputs/two_faults/terminating/report.json).
- [Crossing result](outputs/two_faults/crossing/results.md) and [full metrics](outputs/two_faults/crossing/report.json).
- [Expected coarse failure](outputs/two_fault_coarse_failure/terminating/results.md) and [failure metrics](outputs/two_fault_coarse_failure/terminating/report.json).

Each successful case contains `final_mesh.vtu`, separate primary/secondary fault
VTPs, `fault_junction.vtp`, stratigraphic faces, three section VTPs and seven PNGs.
The volume has cell arrays `fault_block`, `geological_unit`, `block_and_unit`,
`material_reference` and `stratigraphic_coordinate`. There is no globally smoothed
nodal stratigraphic field.

The cell array `stratigraphy` also gives the unit label 0–3 from bottom to top,
matching `geological_unit`, and is the default active colouring array.
`stratigraphic_coordinate` stores each cell centroid's field value within its
own fault block. Reload an already open VTU in ParaView to see updated arrays.

All intermediate input meshes, nodal scalar files, reference mappings, output
meshes, MMG logs and validation reports remain in numbered stage directories.
The small failure is in
`outputs/two_fault_coarse_failure/terminating/05_block3_horizon-0.5`.
Its input files and recorded command allow the problem to be rerun directly.
Large intermediates are ignored by Git; main summaries, metrics, screenshots
and final VTUs are retained as reviewable results.
