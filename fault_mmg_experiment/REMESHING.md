# Cutting versus actual MMG remeshing

The original experiment primarily **cut the starting tetrahedra** to insert
interfaces. It used `-ls` together with `-noinsert -nomove -noswap`, disabling
ordinary insertion/collapse, vertex relocation and edge/face swapping. MMG's
level-set cutter still created intersection vertices and subdivided tets, but
ordinary adaptation could not clean up the resulting slivers. The original
geometric/topological success criteria did not certify element quality.

The [MMG 5.8.0 API](https://github.com/MmgTools/mmg/blob/v5.8.0/src/mmg3d/libmmg3d.h#L142)
documents these controls and distinguishes the level-set and adaptation entry
points. This follow-up uses ordinary MMG3D adaptation, with movement, insertion,
collapse and swapping enabled, on the previously validated two-fault meshes.
No level-set field is supplied to either remeshing pass.

See [LOCAL_REMESHING.md](LOCAL_REMESHING.md) for the subsequent local-adaptation
experiment, including the successful incremental band and unsuccessful attempts
to freeze most of an already poor final cut mesh.

## Executed workflow

1. Read the complete cut mesh, including actual internal interface triangles
   and tetrahedral material references.
2. Adapt to a uniform target edge size of **0.18**, with Hausdorff tolerance
   **1e-8** and gradation **1.3**.
3. Run an additional `-optim` pass using the first remeshed mesh's sizing.
4. Validate all faults, horizons, junction chains, material labels, face
   adjacency, hanging nodes and total volume after **each** pass.
5. Among valid candidates, retain the one with the best minimum normalized
   MMG element quality. Both cases selected the second pass.

Representative commands, each run in its own saved input/output directory:

```sh
mmg3d_O3 -in input.mesh -out output.mesh -hausd 1e-8 -hgrad 1.3 -v 5 -hsiz 0.18
mmg3d_O3 -in input.mesh -out output.mesh -hausd 1e-8 -hgrad 1.3 -v 5 -optim
```

These are global constrained remeshing operations. Internal triangles can change
their triangulation; the preserved object is the geological geometry and its
conforming, labelled volume partition. Geometry preservation is established by
the independent validators, not assumed from a command flag.

## Results

| Metric | Terminating: cut | Terminating: remeshed | Crossing: cut | Crossing: remeshed |
| --- | --- | --- | --- | --- |
| Tetrahedra | 23,428 | 21,585 | 26,346 | 21,609 |
| Minimum normalized MMG quality | 0.00001144 | 0.08381 | 0.000001454 | 0.10458 |
| Median normalized quality | 0.47358 | 0.79910 | 0.39012 | 0.78474 |
| Smallest internal dihedral angle | 0.01129 degrees | 3.89519 degrees | 0.01129 degrees | 4.87881 degrees |
| Tets with minimum angle below 5 degrees | 1,376 | 3 | 1,986 | 1 |
| Geometry/topology/material checks | 61/61 | 61/61 | 76/76 | 76/76 |

Quality 1 corresponds to a regular tetrahedron. In the terminating example,
the number of tets with normalized quality below 0.1 fell from **3,730 to 9**;
in the remeshed crossing example there are **none** below 0.1.

Both remeshed meshes retain volume 8, all expected stratigraphic regions, exact
planar interface coverage within the original tolerances, complete shared fault
junctions and zero hanging-node incidences. The combined test suite passed
**30 tests**, including reference dihedral angles and an actual constrained MMG
adaptation that improves quality without destroying the terminating junction.

Some bad angles remain: three terminating-case tets and one crossing-case tet
have minimum dihedral angles below 5 degrees. This is a substantial measured
improvement, not a claim that every application-specific mesh-quality criterion
has been met. The comparison sections below show cuts through tetrahedra; their
polygon shapes are not themselves the 3D tetrahedron quality measure.

![Terminating model before and after remeshing](outputs/two_faults_remeshed/terminating/mesh_comparison_y0.png)

![Terminating quality distributions](outputs/two_faults_remeshed/terminating/quality_comparison.png)

## Result files

- [Remeshed terminating-fault VTU](outputs/two_faults_remeshed/terminating/final_mesh.vtu), [summary](outputs/two_faults_remeshed/terminating/results.md), [full comparison](outputs/two_faults_remeshed/terminating/report.json).
- [Remeshed crossing-fault VTU](outputs/two_faults_remeshed/crossing/final_mesh.vtu), [summary](outputs/two_faults_remeshed/crossing/results.md), [full comparison](outputs/two_faults_remeshed/crossing/report.json).

Each VTU retains `stratigraphy`, `stratigraphic_coordinate`, `geological_unit`,
`fault_block`, `block_and_unit` and `material_reference` cell properties. Added
cell arrays `mmg_quality`, `minimum_dihedral_degrees`,
`maximum_dihedral_degrees` and `tetra_volume` allow inspecting the remaining
poor elements directly in ParaView. The stratigraphic scalar is reevaluated in
each tetrahedron's block; it is not averaged across faults.

The cut meshes remain at their original paths for comparison. In each remeshed
folder, `cut_mesh_with_quality.vtu` adds the same quality arrays to the original
mesh. Numbered pass directories retain every input, output, command, transcript
and validation report. No failed or poor cells were silently discarded.

## Reproduce

From the experiment directory:

```sh
python scripts/remesh_results.py --case both --size 0.18 --passes 2 --output outputs/new-remeshed-run
python -m pytest -q -c pyproject.toml --basetemp outputs/new-remeshing-tests
```

Use `--source` to select another completed `run_two_faults.py` output directory.
Choose a fresh output directory; original meshes are not overwritten.
`--passes 1` runs just uniform adaptation, and `--no-pictures` skips PNG generation.
The five-cell model whose geometry failed during cutting is deliberately not
used here: quality optimisation cannot be accepted as a repair for already
incorrect geological geometry.
