# Remeshing near the current isovalue

**Yes: local repair can be faster when a previously adapted mesh receives one
new interface.** In the tested terminating-fault model, only **7.25%** of the
post-cut tets were active. Local MMG repair took **2.68 seconds versus 6.24
seconds globally**, with comparable element quality. With full validation and
file handling, repair took **7.68 versus 11.07 seconds**.

This is a measured incremental repair result, not a 2.3x speedup of the entire
90–120 second workflow. Initial preparation and inserting the new cut are shared
costs; in this benchmark they took another 13.38 seconds. The subsequent
[complete-workflow benchmark](FULL_LOCAL_WORKFLOW.md) took **115.98 seconds**,
or **118.65 seconds including startup**, for the terminating-fault model. The
single-repair speedup did not produce a meaningful overall speedup in that run.

## Band and buffer

For an affine block-local field f and isovalue c, use the exact plane distance
`|f-c|/||gradient(f)||`, rather than raw scalar magnitude. The fields here are
not signed-distance fields. For a nonlinear field this expression is only a
local distance estimate.

Select every tetrahedron whose nodal value interval intersects the band. Looking
only at centroid distance or the smallest absolute vertex value can miss an
element that straddles the isosurface. Evaluate the selected block's trace on
shared fault vertices; do not average traces across faults.

The tested band has half-width **0.03**, in the [-1,1] domain. It includes a
topological buffer and any existing tets with normalized quality below **0.1**.
For incremental repair the buffer expands to all tets sharing vertices with the
initial patch. This leaves the seed vertices mobile: freezing any adjacent tet
and its vertices would pin those same vertices and can prevent quality repair.

All outer tets and their vertices are marked `RequiredTetrahedra` and
`RequiredVertices` for **ordinary adaptation**, using MMG's existing
[required-entity API](https://mmgtools.github.io/libmmg3d_8h.html).
After remeshing, complete tetrahedron connectivity, vertex coordinates and
material references are matched geometrically, not by index. MMG can renumber
required elements, as explained in the [developer discussion](https://forum.mmgtools.org/t/relation-between-required-faces-or-elements-between-remeshes/520).
Every original frozen tet must remain intact, with vertex displacement at most
1e-12. The measured maximum displacement was **zero**.

The ordinary-adaptation result still undergoes all global geometric, topological,
material and hanging-node checks. Required tags are not accepted as proof of
preservation. We do not rely on those tags being respected by a crossed level-set
cutter: the new interface is cut first, then the outer region is frozen for its
quality-remeshing pass.

## Incremental benchmark

To reproduce a good starting state, adapt the model immediately before its last
stratigraphic cut. Then insert the last horizon, block 3 at f=0.5, and compare
global versus local repair of **that same post-cut mesh**. The geological model
still has the complete two-fault junction and all three horizons in every block.

| Quantity | Global repair | Local repair |
| --- | --- | --- |
| Active post-cut tets | 19,989 | 1,449 |
| Frozen original tets | 0 | 18,540 |
| MMG time, two attempted passes | 6.235 s | 2.683 s |
| Repair plus checks and I/O | 11.070 s | 7.677 s |
| Final tets, selected candidate | 19,429 | 19,541 |
| Minimum normalized quality | 0.10369 | 0.10157 |
| Median normalized quality | 0.80327 | 0.79875 |
| Minimum dihedral angle | 5.267 degrees | 5.322 degrees |
| Tets with minimum angle below 5 degrees | 0 | 0 |
| Geometry/topology/material checks | 61/61 | 61/61 |

Two passes were attempted with the same size target 0.18 and Hausdorff tolerance
1e-8. Both variants selected their first pass because it had the better minimum
quality. These are single paired timings, so the exact speed ratio will vary.
The ratios are 2.32x for MMG time and 1.44x for repair including checks and I/O;
the latter also excludes the 0.30-second band-selection cost.

MMG still reads and analyses the **whole** input mesh, including required tets,
and our independent validator still checks it globally. Therefore runtime does
not shrink in direct proportion to the active fraction. Avoiding whole-mesh
setup would require extracting a patch and reassembling it against an identical,
fixed outer triangulation; that extension has not been implemented here.

## Why some local trials did not help

We retained the less successful comparisons rather than treating locality as an
automatic speedup:

| Test | Active tets | Global MMG | Local MMG | Result |
| --- | --- | --- | --- | --- |
| All completed interfaces, terminating model | 87.7% | 19.71 s | 19.54 s | Essentially no time saving |
| All completed interfaces, crossing model | 89.9% | 21.81 s | 30.38 s | Local was slower |
| One isovalue plus old sliver cleanup, poor finished mesh | 40.2% | 14.39 s | 22.11 s | Slower, and poor resulting angles |
| One new cut in an adapted mesh, vertex buffer | 7.25% | 6.24 s | 2.68 s | Faster, with comparable quality |

The first two use the union around all faults and horizons, not a band around
one newly inserted level set. With this coarse starting grid and many inserted
interfaces, almost every tet touches an interface, so there is little bulk left
to freeze.

The third includes accumulated slivers from earlier cuts. Repairing them adds
disconnected regions to the current band. Its face-neighbor buffer leaves most
vertices pinned by frozen neighbors. It passes geometry checks but has minimum
dihedral angle **0.0368 degrees**, so it is rejected as a useful quality/speed
alternative. This is why the intended sequence is a good mesh, one cut, then
local repair with enough buffer, rather than accumulating cuts and restricting
the final repair to a small region.

## Reproduce

From the experiment directory, reproduce the successful incremental comparison:

```sh
python scripts/compare_local_remesh.py --case terminating --prepare-last-cut --halo-kind vertex --width 0.03 --output outputs/new-incremental-comparison
```

The script prepares and validates the shared background, inserts the last
horizon, and compares global and local repair. Preparation is recorded
separately from the repair timings.

For the complete finished-mesh interface union:

```sh
python scripts/compare_local_remesh.py --case both --output outputs/new-full-interface-comparison
```

For the unsuccessful current-isovalue/old-sliver trial:

```sh
python scripts/compare_local_remesh.py --case terminating --current-block 2 --current-horizon 0 --output outputs/new-old-sliver-comparison
```

Options include band width, buffer count and type (`face` or `vertex`), optional
poor-element inclusion, target size and one/two attempted remeshing passes.
Choose fresh output directories. The expanded suite passed **35 tests**,
including band crossings with no nearby vertices, one-sided fields, a vertex
buffer, required-entity IO, renumbering/movement detection and actual local MMG
adaptation preserving the three-sheet junction.

Saved artifacts:

- [Incremental comparison](outputs/local_incremental_comparison/terminating/results.md) and [timings, quality and validations](outputs/local_incremental_comparison/terminating/report.json).
- [Local final VTU](outputs/local_incremental_comparison/terminating/local/final_mesh.vtu) and [selected-band VTU](outputs/local_incremental_comparison/terminating/band_selection.vtu).
- [All-interface terminating comparison](outputs/local_remesh_comparison/terminating/results.md) and [crossing comparison](outputs/local_remesh_comparison/crossing/results.md).
- [Unsuccessful old-sliver comparison](outputs/local_current_isovalue/terminating/results.md).

The final local VTU retains stratigraphy and quality properties and adds
`frozen_bulk` (1 for unchanged outer tets). `band_selection.vtu` has
`local_remesh_active` on the shared post-cut input. Intermediate meshes,
reference mappings, MMG logs and complete validation reports are retained in
the pass directories.
