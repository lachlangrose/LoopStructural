# Sequential fault and horizon meshing with MMG3D

**Executed result: full success for the supplied planar synthetic model.** MMG
5.8.0 inserted the fault and all three offset horizons into one conforming mesh.
The 11-cell-per-axis run produced **4,238 vertices and 20,647 tetrahedra** and
passed **39/39 validation checks**. The independent test suite passed **16/16**
tests, including a real MMG invocation and deliberately defective meshes.

The useful workflow is global, sequential, **one fault block at a time**. It uses
MMG material mappings to keep inactive geological regions from being classified
by the active cut. Independent fault-block remeshing failed to preserve a common
fault triangulation, even when fault triangles were required.

This experiment does not import LoopStructural or change its production code.
No MMG C code was changed; all tetrahedron cutting is performed by MMG.

**Follow-up: two inclined fault surfaces, including a terminating secondary fault,
have now been executed.** See [TWO_FAULTS.md](TWO_FAULTS.md) for the three-block
T junction, four-block crossing control, inclined horizons, and a coarse-mesh
failure that demonstrates why checking geometry separately remains necessary.

The original meshes use MMG level-set cutting with ordinary adaptation disabled,
so they retain poor sliver elements. **Actual quality remeshing has now been run
separately**: see [REMESHING.md](REMESHING.md) for improved VTUs, element-quality
comparisons and revalidation of the geological interfaces.

**Local adaptation is also tested:** [LOCAL_REMESHING.md](LOCAL_REMESHING.md)
compares freezing the bulk against global adaptation. On a previously adapted
mesh with one new horizon cut, a 7.2% active patch gave faster repair while
preserving every frozen outer tetrahedron. Freezing around all interfaces at the
end gave no useful speed advantage in these small, interface-dense models.

The [complete local workflow](FULL_LOCAL_WORKFLOW.md), cutting and immediately
repairing all 11 interfaces, has now been timed: **116 seconds**, or **119 seconds
including startup**, with full validation and final figures. The previous global
workflow was also about two minutes; the isolated repair speedup did not carry
over to a substantial end-to-end improvement in this small model.

## Installation and execution

Python 3.11 or newer is required. From this directory:

```sh
python -m pip install -e ".[test]"
conda install -c conda-forge mmgsuite=5.8.0
python scripts/run_experiment.py --cells 11 --output outputs/run-01
python -m pytest -q -c pyproject.toml --basetemp outputs/pytest-run-01
```

The official [installation guide](https://mmgtools.org/install.html) describes
Conda and source builds. The package is named **mmgsuite**, not the unrelated
Python package named `mmg`. The executable is normally `mmg3d_O3` or `mmg3d`.
Supply `--mmg /absolute/path/to/mmg3d_O3` or set `MMG3D` when it is not on PATH.

On this Windows machine MMG was extracted into `.mmg-runtime/`, without changing
the existing Python environment. To reproduce that setup, run
`python scripts/bootstrap_mmg.py` using a Conda Python with
`conda-package-handling` installed. It downloads the exact non-VTK Windows build
`mmgsuite-5.8.0-h83b8f9d_15.conda`, verifies its SHA256 against package metadata,
and saves provenance and unmodified upstream source references locally.

The already available project environment can run the experiment from the
repository root:

```powershell
.\.venv\Scripts\python.exe fault_mmg_experiment/scripts/run_experiment.py --output fault_mmg_experiment/outputs/run-02
```

Use a fresh output directory for each run: the driver rejects a directory that
already contains a report. `--no-pictures` suppresses PNGs; VTU/VTP exports and
validation still run. `--only-global` skips the comparison probes.
`--no-full-scan` is a faster diagnostic option; its output is explicitly **not**
reported as full success. Defaults include all probes, screenshots and the full
geometric hanging-node scan. Typical runtime here was about a minute.

## What the research established

These conclusions apply to the tested MMG 5.8.0 implementation and CLI. They are
not a guarantee for arbitrary implicit fields or every MMG release.

| Research question | Finding and evidence |
| --- | --- |
| Preserve an existing internal interface during level-set discretisation? | **Yes in the tested mapped workflow.** Fault and earlier horizon faces remain actual tetrahedron faces after every later cut. Each intermediate mesh is validated. Without a material map, the probe resets input material references 11/12 to 2/3. |
| Can another level set split the existing fault interface conformingly? | **Yes.** The final fault has matching triangles across its two sides, and every target horizon meets it along shared edges of total length 2. The real-MMG test also checks that cutting the active block refines its `nosplit` neighbor without opening cracks. |
| Multiple level sets or isovalues in one operation? | **No such interface was found in the examined entry point.** `MMG3D_mmg3dls` takes one level-set solution; `MMG3D_DPARAM_ls` selects one isovalue. Multiple materials select reference mappings for that same cut. This experiment uses seven calls: one fault and six block-local horizon cuts. See the [5.8.0 public API](https://github.com/MmgTools/mmg/blob/v5.8.0/src/mmg3d/libmmg3d.h). |
| What do material references do? | `LSReferences` maps each input tetrahedron reference to a negative/positive pair, or `nosplit`. The [official detailed options](https://mmgtools.org/tutorials/tutorials_detailed_options.html) and [material-map implementation](https://github.com/MmgTools/mmg/blob/v5.8.0/src/common/mmg2.c) describe this. Fresh child references avoid inverse-map collisions. |
| Are required triangles immutable? | **No when crossed by the level set.** The separate-block probe logs `Required entity ignored` and changes the shared triangulation. The [cutter implementation](https://github.com/MmgTools/mmg/blob/v5.8.0/src/mmg3d/mmg3d2.c#L1026) explicitly permits this. |
| Can fault vertices move along the fault? | The main run disables relocation. A separate remeshing-enabled probe passes fault and one-horizon validation, with fault vertices remaining on x=0. It does not track individual vertex identity, so it establishes geometric preservation rather than a bound on tangential displacement. `requiredVertex` and `nomove` are the explicit freezing controls in the public API. |
| Can separate block runs preserve their common triangulation? | **Not by marking crossed faces required.** In the small probe, A/B have 72/96 fault triangles, only 60 of which match. Both free and required runs have 12/36 unmatched triangles. Reassembly is rejected. |

Interface references need care. The CLI uses reference 10 for the newly inserted
isosurface. Before another cut, the driver renames previous interface triangles
to persistent references 100, 101, etc. Region labels and actual adjacency remain
the source of truth. Reusing the reserved tag still preserved fault geometry in
the tested Medit path, but changed its exported triangle tag. Thus retagging is
an identity-management measure, not proof of conformity. The upstream
[`resetRef_ls` warning](https://github.com/MmgTools/mmg/blob/v5.8.0/src/mmg3d/mmg3d2.c#L303)
and [common format loader](https://github.com/MmgTools/mmg/blob/v5.8.0/src/common/inout.c#L783)
also show why behavior of old isosurface tags should not be assumed across
formats. The native Medit reader has a different path.

## Successful method

1. Generate a Freudenthal decomposition of the cube. With 11 cells per axis it
   contains 7,986 tets and crosses x=0. Even resolutions move the middle x plane
   off the fault so the input remains deliberately nonconforming.
2. Discretise `g=x` using `-ls 0`, mapping material 1 to block references 11/12.
3. For each horizon and each block, evaluate **that block's smooth field trace**.
   At x=0, A uses `z` and B uses `z-0.4`, in different MMG calls.
4. Split only the active block's current upper unit; mark every other material
   `nosplit`. MMG propagates necessary shared-edge subdivision into neighboring
   tetrahedra while retaining their material labels.
5. Preserve the material lineage, rename old interface tags, and validate every
   intermediate mesh. Earlier horizons remain interfaces between distinct
   material references.

For the first horizon the parameter file is:

```text
LSReferences
2
11 1001 1002
12 nosplit
```

The representative command is:

```sh
mmg3d_O3 -in input.mesh -sol input.sol -out output.mesh -ls 0 -f input.mmg3d -noinsert -nomove -noswap -hmin 0.015 -hmax 0.35 -hausd 1e-8 -v 5
```

The level-set cutter still inserts its necessary intersection vertices with
these flags; ordinary adaptation, movement and swapping are restricted. This is
an exact-plane conformity experiment, not an optimisation of element quality.
`hmin` does not prevent the cutter creating short edges near existing vertices.

Crucially, the scalar file is **not** the piecewise present-day field sampled
once on shared vertices. It is a smooth extension of the active block's field,
`z-height`, with classification disabled in inactive materials. Six physical
cuts occur at z=-0.5, -0.1, 0, 0.4, 0.5 and 0.9, in their corresponding blocks.
The inactive block can be subdivided for conformity without acquiring a false
geological horizon. There is no cross-fault averaging or smoothing.

## Executed results and inspection

The supplied results are in [`outputs/main/results.md`](outputs/main/results.md),
with full metrics and commands in [`outputs/main/report.json`](outputs/main/report.json).

| Quantity | Observed result |
| --- | --- |
| Final vertices / tetrahedra | 4,238 / 20,647 |
| Tetrahedral volume / target | 8 / 8 |
| Minimum positive tet volume | 1.25219e-7 |
| Hanging-node/face incidences | 0 |
| Nonmanifold faces | 0 |
| Fault area / target | 4 / 4 |
| Each of six horizon patch areas / target | 2 / 2 |
| Each horizon/fault intersection length / target | 2 / 2 |
| Geological regions | 8, with MMG material lineage matching block/unit labels |

![Cross-section through the faulted model](outputs/main/cross_section_y0.png)

Open `final_mesh.vtu` in ParaView or PyVista and select cell arrays `fault_block`,
`stratigraphy`, `geological_unit`, `block_and_unit`, or `material_reference`. Units are numbered
0–3 from bottom to top; fault blocks are 1=A and 2=B. The exported surfaces
`fault_interface.vtp` and `stratigraphic_interfaces.vtp` are derived from shared
volume faces, not independently extracted contour meshes.

`stratigraphy` is the integer unit label (0–3), also available as `geological_unit`.
`stratigraphic_coordinate` is the block-local field f evaluated at each tetrahedron
centroid. Both are **cell data**. `stratigraphy` is the default active colouring
array; reload an already open file in ParaView to see updated properties.

Also saved: `initial_mesh.vtu`, `fault_inserted.vtu`, `cross_section_y0.vtp` and
eight PNG screenshots. Each numbered cut directory contains `input.mesh`,
`input.sol`, `input.mmg3d`, `output.mesh`, `mmg.log`, `invocation.json`, a VTU, and
validation metrics. Large generated meshes and local executables are ignored by
Git; the main report, summary and PNGs are retained as reviewable results.

To reproduce the required-face failure without rerunning the complete pipeline,
open `outputs/main/probes/separate_required/block2`, then rerun the command in
its `invocation.json` (or the representative command above). That folder retains
the required-triangle input and the warning transcript. The paired block1
directory supplies the incompatible triangulation. Both comparison meshes are
retained; no invalid reassembly is labelled a final result.

## Validation and numerical tolerances

The final 39 checks cover signed volumes after explicit ordering correction,
face multiplicity, opposite-side adjacency, duplicate vertices/cells, cube
boundary location and area, volume conservation, fault and horizon geometry,
coverage area, shared intersection edges, unit adjacency, material lineage, and
geometric hanging-node detection. No failed/degenerate elements are dropped.

- Absolute coordinate/plane tolerance: **1e-8** in the [-1,1] cube.
- Absolute total-volume error: **1e-8**.
- Minimum accepted signed tetrahedron volume: **strictly greater than 1e-14**.
- Absolute patch-area and intersection-length error: **1e-7**.
- Fault-signature comparison in the separate-block probe: coordinate rounding
  to **1e-9** before comparing complete triangles, not only vertex sets.

Every face with one incident tet must lie on the exterior cube. This rejects
internal cracks rather than misclassifying them as valid external faces. Shared
faces must have exactly two incident tets on opposite sides. A conservative
KD-tree search then tests all nonincident vertices against triangle interiors
and edges; this catches hanging nodes that face counting alone can miss. These
checks are tailored to this convex cube and planar interfaces, not a general
arbitrary-mesh intersection certificate.

Geometric accuracy is checked separately: no tetrahedron may straddle a target
plane, interface patches must cover their full expected area, and all actual
geological unit interfaces must lie on the expected block-specific planes.
The test suite includes a topologically valid cube with incorrect geology to
ensure that topology alone does not pass the geological checks.

## Limits and smallest next step

No MMG extension is needed for this synthetic model. Directly submitting one
discontinuous nodal stratigraphic field remains incompatible with a shared
vertex's single scalar value. The small workflow change that avoids it is the
demonstrated **material-local cut plus conforming refinement in one global mesh**.

For LoopStructural, the next experiment should supply a chosen block's one-sided
field values at shared fault vertices and a smooth extension for that call,
while retaining inactive material references. Test curved horizons and faults,
then quality optimisation, before treating this as a general mesher. This run
does not establish success for fault tips, intersecting faults, pinch-outs,
triple junctions, or fields with difficult nonmanifold zero sets.

If separate block processing is required, it needs a synchronized fault-surface
refinement shared by both blocks, including traces from both sides. Freezing the
original surface cannot accommodate new intersecting horizons. If MMG were to
accept all traces in one call, the natural extension would be per-material or
per-cell-side scalar values with a shared intersection registry; that is a
possible future design, not an implemented or proven minimum C change.
