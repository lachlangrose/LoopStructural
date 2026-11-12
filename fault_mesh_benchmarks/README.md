# Fault meshing benchmark suite

A reproducible set of faulted implicit models, built with LoopStructural, for
testing a fault-aware surface mesher and corefinement engine. Each case gives
the implicit fields, a reference triangulation of every fault and horizon
patch with **no smearing across faults**, and the sharp-feature curves that a
mesher must preserve.

```sh
# from this folder, with the LoopStructural repository environment
python generate_benchmarks.py --list
python generate_benchmarks.py --case planar_fault
python generate_benchmarks.py --case all --resolution 129 --out outputs/suite
python generate_benchmarks.py --category edge-case --method marching_tetrahedra
python -m pytest -q
```

To make the shareable benchmark folder (one self-contained folder per model,
with the surfaces, the interpolation support of each implicit field, and a
standalone `build_model.py`), run after the generator:

```sh
python make_benchmark_folder.py --outputs outputs --dest benchmark
```

The tool runs each `build_model.py`: the script rebuilds the model from its
`data/` folder, writes `support/`, and checks the result against values saved
by the generator (tolerance 1e-4; the differences are iterative-solver
round-off, at most about 2e-5, against a reference cell of 0.0104). See `benchmark/README.md`.

All cases use the unit cube `[0,1]^3` (z up), a fixed seed per case, and a
regular grid with `resolution` nodes per axis for the reference isosurfaces
(default 97, cell 1/96) and `volume_resolution` nodes per axis for the field
volume (default 49).

## Cases

| Case | Category | What it tests |
| --- | --- | --- |
| `planar_fault` | idealised | One planar fault, constant slip vector: a pure step. Has an analytic solution (see `tests/test_planar_fault.py`). |
| `fault_tip` | idealised | Finite BaseFault3D fault: tip loop inside the volume, displacement goes smoothly to zero. Horizons are single surfaces with a slit. |
| `fault_tip_step` | idealised | Same tip loop, but only the hanging wall moves: the full offset is a one-sided step. |
| `listric_fault` | idealised | Dip changes from 72 to 22 deg with depth, bowed trace, throw varies along strike and dip. |
| `y_junction` | idealised | Antithetic fault abutting the main fault: three blocks and a junction curve. |
| `crossing_faults` | idealised | Younger fault cuts and offsets an older fault: four blocks, split fault surface. |
| `graben` | idealised | Two facing faults converging just below the base. |
| `folded_faulted` | pseudo-real | Oblique folds cut by a normal and a reverse fault with variable throw and drag. |
| `restraining_bend` | pseudo-real | Vertical dextral strike-slip fault with a smooth 40 deg left step (restraining bend); two reverse splays abut it at depth and die out along strike (positive flower). Curved fault with horizontal slip, abutment on a curved host, tips of abutting faults. |
| `unconformity_faulted` | pseudo-real | Tilted basement with an early fault, angular unconformity, flat cover, late fault through all. |
| `displacement_gradient_{sharp,medium,broad}` | uncertainty | Same offset at the fault; displacement decays over 0.06, 0.2 or 0.6. |
| `fault_uncertainty_{0,1,2}` | uncertainty | Seeded realisations of dip, displacement, decay width and position. |
| `squeezed_wedge` | edge-case | Two faults that meet at 20 deg: a wedge that thins to zero, acute junction. |
| `narrow_horst` | edge-case | A horst 0.02-0.06 wide between two near-vertical faults. |

## Outputs per case

```
<case>/
  metadata.json                  everything below, machine readable
  README.md                      generated summary tables
  surfaces/fault_<f>.{vtp,obj,stl}          one file per fault, cell data block
  surfaces/horizon_<series>_<k>.{vtp,obj,stl} one file per horizon, cell data block
  constraints/constraint_curves.vtp   one polyline set, cell data constraint_id, sharp
  volume/implicit_fields.vtu     the field grid (hexahedra) with point data
  volume/implicit_fields.npz     the same arrays, ':' in names replaced by '__'
  data/contacts_and_orientations.csv  contact points, values, unit normals, dip/dip direction
  data/fault_observations.csv    the fault points and normals given to LoopStructural
  data/markers.vtp
outputs/index.json               status and options of every generated case
```

### Implicit field data (`volume/implicit_fields.vtu`)

| Array | Meaning |
| --- | --- |
| `v:<series>` | Stratigraphic scalar field. Equal to the LoopStructural field. |
| `grad:<series>` | Gradient of `v`, by central differences of the block field (never across a fault). |
| `v_ext:<series>:<block>` | Smooth extension of one block's field over the whole domain (see below). |
| `block:<series>` | Index of the fault block (`metadata.series[].blocks`). |
| `visible:<series>` | 1 where the series exists (below younger unconformities). |
| `unit` | Stratigraphic unit id (`metadata.units`). |
| `gx:<f>`, `gy:<f>`, `gz:<f>` | Fault frame: gx = 0 is the fault, gx > 0 is the hanging wall. |
| `side:<f>` | +1 hanging wall, -1 footwall (abutment taken into account). |
| `displacement:<f>` | Forward displacement from this fault, `p - restore_f(p)`. |
| `displacement_hanging_wall:<f>`, `displacement_footwall:<f>` | The same, evaluated as if every point were on one side. Their difference at the fault is the slip vector. |
| `displacement_total:<series>` | Forward displacement from all faults of the series. |

### Reference meshes

Each horizon is extracted **per fault block** from that block's smooth
extension field `v_ext`, and then clipped exactly by the block's side
functions, the younger unconformities and the domain. Each fault is extracted
from its own frame coordinate gx = 0 and clipped by abutment, tip lines and
unconformities; a fault that a younger fault displaces is extracted per block
of the younger fault. Clips are evaluated exactly at the mesh vertices, and
cut points are placed by linear interpolation on each triangle edge. The
patch boundaries are therefore on the fault surface to O(h^2), and the offset
is a true discontinuity: no triangle spans the fault. The block pieces of each
surface are then merged into one file (cell data `block`); pieces join only
where their fields are equal (beyond a fault tip).

These meshes are geometric references, not quality targets: marching cubes
and clipping make small angles (`quality.min_angle_deg`,
`quality.triangles_min_angle_below_5deg`). Vertices closer than 1e-3 of a cell
are merged.

### Corefinement metadata (`metadata.json`)

* `faults[]`: centre, normal (into the hanging wall), forward slip direction,
  displacement, axes, `faulted_by`, `abuts`, `truncated_by`,
  `surface_bbox`, `influence.influence_bbox` (where this fault moves points by
  more than 1e-4 of its displacement), the slip jump on the fault surface, and
  `displacement_samples`: up to 256 points on the fault with the hanging-wall
  and footwall displacement vectors.
* `constraints[]`: one record per boundary curve of each patch. `kind` is
  `cutoff` (horizon meets a fault where the slip jump is non-zero: sharp),
  `seam` (horizon meets a fault beyond its tip: no offset, the two sides join
  smoothly, not sharp), `junction` (fault meets fault), `tip` (fault tip line,
  not sharp), `unconformity`, or `domain`. Each has `length`, the dihedral
  angle between the patch and the constraint surface (min, mean, max), the
  slip jump along cut-offs, and `max_distance_to_constraint`.
* `surfaces[]`: file names, block, isovalue, mesh quality and boundary
  length by tag.
* `series[]`: restored analytic field, isovalues, faults, blocks, and the
  interpolation misfit.
* `qa`: no untagged open boundary, no non-manifold edge, block fields equal to
  the LoopStructural field away from faults, series fit below 2 % RMS.

## Method

### Data that agrees with the LoopStructural kinematics

Each case is written as analytic geometry (`src/fault_benchmarks/cases.py`):
fault surfaces, fault parameters, and an analytic stratigraphic field in
**restored** coordinates. The builder:

1. builds each fault from samples of its surface (moved forward through any
   younger fault that displaces it), and
2. for each series, takes random present-day points, restores them through
   the built faults exactly as LoopStructural does, and uses the analytic
   restored field as the value at each point.

LoopStructural then reproduces the analytic field in restored space (relative
RMS misfit is in the metadata), and the faults are the only source of
discontinuity.

### Block fields without smearing

A faulted field contoured on a grid smears the offset over the cells that the
fault cuts. The suite instead evaluates, for each block, the field as if every
point were on that block's side of each fault. It replaces the frame
coordinate gx by `sign * |gx|` during evaluation (`fields.forced_sides`), so
the displacement profile is continuous across the fault (a mirror extension).
Inside its own block this extension is identical to the LoopStructural field;
the QA check `block_fields_match_loopstructural` tests this on the volume grid.
The same extension fields are exported (`v_ext`) because a corefinement mesher
needs exactly this input: one smooth field per block, with no jump to resolve.

### Conventions and LoopStructural notes

* `FaultSpec.slip` is the forward hanging-wall direction; LoopStructural is
  given `-slip` because its slip vector is the restoration direction.
* Measured frame scaling (LoopStructural 1.8.4): `gz = d / major_axis`,
  `gy = d / intermediate_axis`, but `gx = d / (minor_axis / 2)`. Major and
  intermediate are radii; minor is a full width.
* The `constant` profile moves the whole hanging-wall half-space. When that
  half-space contains another fault, the other fault must be declared
  `faulted_by` this one; otherwise LoopStructural evaluates the other fault at
  restored positions while its surface stays in present-day position, and the
  horizon offset does not lie on the fault surface. The `graben` and
  `folded_faulted` cases declare this.
* Faults displaced by other faults (`crossing_faults`, `graben`,
  `unconformity_faulted`, `folded_faulted`) needed two fixes in
  LoopStructural, with regression tests in
  `tests/unit/modelling/test_faulted_feature_gradient.py`:
  `GeologicalFeature.evaluate_gradient` overwrote its result array for any
  faulted feature, and `FaultSegment.apply_to_points` made a point NaN where
  the slip direction was undefined (NaN * 0).
* Speed: for a displaced fault, LoopStructural computes the slip direction
  with refined tetrahedra at every integration step (about 3 ms per point).
  The builder replaces it with the frame gradient at the restored point
  (`builder.use_restored_slip_direction`); this is exact where the younger
  fault translates rigidly (the `constant` profile) and approximate in the
  decay zone of `base` profiles (`folded_faulted`). Planar `constant` faults
  use one integration step (exact for a translation); other profiles use 10.
  These settings are part of the model, so the reference fields and the block
  fields use the same kinematics.

## Run time and size

On the development machine (Windows, one process), the default settings
(`--resolution 97 --volume-resolution 49`) generate the 17 cases in about
37 minutes and 490 MB. Most cases take 40-170 s; `folded_faulted`
takes about 11 minutes, because its `base` profiles use 10 integration
steps through two faults. Use `--formats vtp` to omit the OBJ and STL copies,
and `scripts/plot_sections.py outputs` to draw a y = 0.5 section of each case.

## Finite faults

A fault with a tip (profiles `base3d`, `tip`, and `base` along strike) moves
points only inside its tip loop. LoopStructural multiplies a profile in gy by
a profile in gz, so the loop is a rectangle in the fault frame (|gy| = 1 or
|gz| = 1) with rounded displacement contours inside. The generator:

* clips the fault surface at the tip loop (boundary tag `tip`);
* restricts the footwall block of a finite fault to its active region, plus a
  margin of two cell diagonals outside the tip. In that margin both block
  fields are exactly equal, so the two pieces of a horizon have identical
  triangles there and merge into one surface. A horizon that the fault cuts
  is one surface with a slit; one that the fault does not reach has no
  internal boundary (`tests/test_fault_tip.py`);
* tags a slit edge `cutoff` where the slip jump is above 1e-3 of the
  displacement and `seam` where it is below (short ends near the tip).

The cell array `block` on each surface gives the block of each triangle. For a
finite fault, the footwall block is the active region on the footwall side,
not a region closed by faults.

## Conforming surfaces (Loop CGAL, experimental)

The reference surfaces are clipped by the implicit fault functions. Their
cut-off lines are on the implicit fault to O(h^2), but they are not on the
fault triangles, and the fault mesh has no vertices on them.
`make_conforming.py` makes a second set of surfaces that share vertices and
edges along every cut-off and junction (`src/fault_benchmarks/conforming.py`):

```sh
pip install loop-cgal            # or: pip install -e .[conforming]
python make_conforming.py --case y_junction    # about 1 min at resolution 97
```

Supported cases (13 of 17): `planar_fault`, `fault_tip`, `fault_tip_step`,
`listric_fault`, `y_junction`, `displacement_gradient_*`,
`fault_uncertainty_*`, `squeezed_wedge`, `narrow_horst`. Not yet supported:
faults displaced by other faults and unconformities (`crossing_faults`,
`graben`, `folded_faulted`, `unconformity_faulted` raise
`NotImplementedError`).

1. Each fault is contoured from gx = 0. An abutting fault is cut by its host
   fault (CGAL corefinement, exact kernel).
2. Each horizon is contoured per block (the same smooth block fields as the
   reference) and cut by the faults that bound the block, abutting faults
   first.
3. Each fault is split, with both sides kept, by the block contours whose
   horizon piece touches it, and by the faults that abut it. The cut-off
   and junction curves become fault edges.
4. Repair: one weld over all surfaces (vertices nearer than 1e-8 become one
   vertex; a fault vertex wins), then T-junctions are split in both
   directions (a fault vertex inside a horizon edge, and a horizon vertex
   inside a fault edge).

Finite faults (a tip inside the model):

* A fault that ends inside the model cannot cut a horizon itself, because
  Loop CGAL extends a clipper past its boundary. The fault mesh is cut at the
  tip surface, the contour of t = min(1 - |gy|, 1 - |gz|) at |g| = 1.001
  (`TIP_LEVEL`). The corners of the tip rectangle are rounded within one
  cell. The 0.001 avoids a degenerate cut: `fault_tip` has a horizon that
  passes exactly through the tip line.
* A "bowl" bounds the active footwall: the fault surface inside the tip plus
  the tip surface on the footwall side. The hanging-wall piece of a horizon
  is the part outside the bowl, the footwall piece the part inside.
* The two block fields are equal beyond the tip, but a grid cell that
  crosses the tip has nodes inside it, so the two contours can differ there
  by up to 0.4 cell (`fault_tip_step`). At the nodes within one cell
  diagonal of the tip, the footwall field takes the hanging-wall values.
  The seam on the tip surface is then identical in both pieces, the horizon
  is one surface, and the slit closes about one cell inside the tip.
  `conforming.json` gives the largest field change this makes
  (`tip_band.max_field_change`: 0.002 to 0.003 at resolution 97, 0.02 to
  0.03 at resolution 33).

What makes the CGAL cuts reliable (each one was a failure before it was
added):

* No zero-area contour triangles: grid values within 1e-4 of a node step
  from the isovalue are moved off it. Marching cubes otherwise puts several
  vertices on one node, and CGAL stops with "Unauthorized intersections of
  constraints".
* Each clipper is larger than the surface that it cuts (faults 4 cells
  outside the cube, abutting faults 3, horizons 2; a fault is trimmed to
  1 cell before curves are inserted). Loop CGAL extends a clipper at its
  boundary with a tangent strip, and the strips cross at the corners. All
  surfaces are clipped to the cube with exact planes at the end.
* A fault is split only by contours of blocks that touch it. In
  `narrow_horst` a contour of the other hanging wall crosses a fault within
  1e-8 of a true cut-off, which makes edges of 1e-9.
* `cut_with_surface` returns (faces before - faces after). A cut that
  removes a small part but splits many triangles returns 0 or less, so the
  code compares the meshes instead.

Output: `<out>/<case>/surfaces_conforming/corefined/*.vtp` (cell data
`block`) and `conforming.json`. For each pair (surface, fault), the QA
file gives the number of cut-off vertices that are not fault vertices, the
number of cut-off edges that are not fault edges (both must be 0), and the
largest distance from a cut-off vertex to the implicit fault.
`tests/test_conforming.py` checks `y_junction`, `narrow_horst` and
`fault_tip_step`. All 13 supported cases conform at resolution 49, with the
same connected pieces as the reference surfaces and areas within 2 %.

Limits of this version:

* Corefinement makes slivers where a cut passes near a vertex (minimum angle
  near 0; see `quality` in `conforming.json`). The T-junction repair adds
  more small triangles.
* `--remesh EDGE_LENGTH` runs the Loop CGAL isotropic remesher with the
  shared curves as fixed edges. With loop_cgal 0.1.8 the remesher still
  collapses some short fixed edges, so the remeshed surfaces do **not**
  fully conform (the QA file shows this).

## Limits

* In `displacement_gradient_sharp` the decay width (0.06) is less than the
  movement of each wall (0.075). The drag zone is strongly sheared, and the
  horizons are almost vertical within 0.06 of the fault. This is intended as
  a high-gradient stress case.

* Abutment is supported for one host fault per fault; chains of abutments and
  splays are not modelled.
* The tagging tolerance is 0.75 of a reference cell. Very acute junctions
  (`squeezed_wedge`) can put two constraints within this distance; the tag is
  then the nearer one.
* Reference surfaces approximate the implicit fields to O(h^2) away from
  constraints. For the exact geometry, use `planar_fault`, whose analytic
  solution is tested.
