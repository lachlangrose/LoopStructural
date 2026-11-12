# Whole-model timing with local repair after every insertion

**Measured runtime: 115.983 seconds**, or **118.647 seconds including Python and
library startup**, for the complete terminating two-fault model at 11 cells per
axis. This replaces the earlier limitation that only one incremental repair had
been benchmarked.

The run starts from the coarse cube, inserts both faults and all three inclined
horizons in each of three fault blocks, and repairs locally after every cut.
It includes full geometric validation, frozen-bulk verification, intermediate
meshes and final VTK exports and seven PNG figures. It does not reuse the
previously completed model or a pre-adapted background.

| Recorded work | Seconds |
| --- | --- |
| MMG level-set cutting, 11 calls | 15.692 |
| Local MMG adaptation, 13 calls | 28.225 |
| Geological/topological validation | 29.744 |
| Band selection and freezing | 2.183 |
| Checking unchanged frozen bulk | 2.395 |
| Final VTK/PNG generation | 23.945 |
| Remaining construction, I/O and bookkeeping | 13.799 |
| **Whole workflow** | **115.983** |
| Initial Python/library startup | 2.663 |
| **Total including startup** | **118.647** |

The prior cut-everything-then-remesh run took about 119 seconds excluding startup.
These are separate single-run measurements with different intermediate plotting
and checking work, not a controlled performance ranking. They show **no
substantial end-to-end speed improvement** from this implementation at this
model size. The 2.3x speedup reported previously applies to one repair step only.

## Implemented sequence

After each MMG level-set cut:

1. Verify the new interface and every interface already inserted.
2. Select the current fault/horizon's distance band, half-width 0.03, plus any
   tets with normalized quality below 0.1.
3. Expand the band by one vertex-neighbor layer to keep the core vertices free
   to move. The active fractions ranged from 7.6% to 45.5%; early whole faults
   need larger patches than the final small horizon patch.
4. Freeze all other tets and vertices and run ordinary MMG adaptation at target
   edge size 0.18. Check all geometry and frozen tets afterward.
5. If minimum quality is below 0.1 or a minimum dihedral angle is below 5 degrees,
   try one additional optimization pass. Retain the geometrically valid candidate
   with the better minimum quality.
6. Release the previous frozen tags before the next cut.

The first nine insertions needed one repair call each. The final two tried a
second pass, for 13 adaptation calls in total. MMG still reads and analyses the
whole mesh in each invocation. More calls and file round trips, plus repeated
global checks, offset the cheaper local repairs.

No global quality-repair fallback was used. Every local operation preserved its
frozen tets, vertices and material references. The final mesh has **17,041 tets**,
volume 8, all **61 geometry/topology/material checks passing**, and zero hanging
nodes. Its minimum normalized quality is **0.0970621**, median **0.742415**, and
minimum dihedral angle **5.2108 degrees**; no tets have angles below 5 degrees.
The minimum quality remains just below the requested 0.1 goal, so the report
explicitly records a residual quality limit instead of claiming all quality
targets were reached.

## Reproduce and inspect

```sh
python scripts/run_local_workflow.py --case terminating --cells 11 --output outputs/new-full-local-run
```

Use a fresh output directory. `--no-pictures` omits final PNGs. Other options
control band width, buffer layers, target size, maximum repair attempts and
quality goals. `--case crossing` selects the four-block model; the timing above
is specifically for the terminating three-block case.

- [Complete timing and stage report](outputs/full_local_workflow/terminating/report.json).
- [Generated summary](outputs/full_local_workflow/terminating/results.md).
- [Final VTU](outputs/full_local_workflow/terminating/final_mesh.vtu), including stratigraphy and cell-quality properties.

The report retains the active fractions, per-call timings, geometry checks,
quality statistics and frozen-region verification for every insertion. Numbered
directories retain all level-set and adaptation input/output meshes and logs.
