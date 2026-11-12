Mexico Basin meshing demonstration suite
========================================

Run ``plot_2_mexico_basin.py --zone North_2`` for the default model or
``--all`` for ten separate domains: Extra, North_1 through North_5,
Middle_1, Middle_2, South_1 and South_2. These published domains overlap;
they are not stitched into a single basin-wide model.

Install ``pyshp tifffile matplotlib pyvista`` alongside LoopStructural.
The first run caches a 30 MB source archive. ``--offline`` forbids network
access; importing the script never downloads or builds anything.
``--data`` selects the cache and ``--output`` selects the output root.
``--nelements`` controls interpolation resolution, while ``--dimensions``
controls the exported grid, independently. For example::

    python examples/5_case_studies/plot_2_mexico_basin.py --all --nelements 8000 --dimensions 41 41 25

Fault displacements
-------------------

Each fault has one interpolated geometry and a separate restoration event
for each affected horizon. Matching horizon cutoffs are recovered from
the original interpreted sections. Endpoints may be extrapolated to their
section fault line along the adjacent contact segment by at most 200 m.
Continuous contacts and synthetic fault extensions have zero offset.
Missing pairs are explicitly labelled ``unresolved`` and assigned zero
slip; this is an assumption, not evidence of zero displacement. Pairs with
less than 2 m inferred slip are treated as continuous.

The inferred signed restoration slip is::

    slip = dot(bedding_normal, negative_cutoff - positive_cutoff) / dot(bedding_normal, updip)

This accounts for horizontal heave rather than equating throw with net
slip. Bedding slope comes from the adjoining section segments, with no
transverse dip inferred. Strike slip is not constrained. Local vertical
throws are converted to a common mean up-dip direction for each fault;
signed slip is linearly interpolated along strike, tapering to zero over
5 km beyond the last section. Only the positive wall is restored, using
an explicit displacement-function ``scale=1``. Positive signed slip means
upward restoration of the positive wall; forward movement is opposite.
Geometry-only faults in ``model.faults`` have zero displacement. Effective
events are attached to each basal feature and returned in
``horizon_faults``. Faults do not offset each other; multiple restorations
follow their listed order. These inputs do not establish a unique history.

Each source horizon is interpreted as its named unit's base, independently
of other horizons, avoiding fabricated unit thicknesses. Younger surfaces
truncate older ones in source-notebook order. Below the deepest modelled
base is ``Older_substrate``, with no fabricated lower boundary. Source
orientations come from interpreted sections, not independent field data.
The DEM masks air. Coordinates remain WGS84 / UTM 14N (EPSG:32614), in metres.

Outputs
-------

* ``implicit_fields.vts`` contains ``base_<unit>`` and ``fault_<name>``
  scalars, ``restoration_<unit>`` vectors in metres, terrain clearance,
  cell unit IDs and fault-block bit masks. Unit IDs agree with
  ``model.evaluate_model``; their names and bit definitions are in JSON.
* ``geological_block.vtu`` contains cells whose centres lie below terrain.
  It is a labelled hexahedral reference grid, not a conforming tetrahedral
  mesh; the terrain boundary is a stair-step approximation.
* ``base_<unit>.vtp`` and ``fault_<name>.vtp`` are triangular surfaces,
  clipped at terrain. Older contacts are also clipped below younger units.
  Contact contouring excludes cells crossing an active fault, preventing
  triangles bridging its displacement. This leaves grid-sized gaps that
  narrow with finer sampling. ``surface_inventory.csv`` identifies empty
  surfaces as well as those exported.
* ``fault_displacement_picks.csv`` includes section names, cutoff
  coordinates, evidence categories, signed slip and inferred vertical throw.
* ``fault_displacement_checks.csv`` checks the actual two-wall net
  restoration vectors against the intended profiles at fault-surface probes.
  These are numerical checks, not independent geological validation.
* ``contact_fit.csv`` reports fitted scalar residuals, not geometric
  distances or independent validation. ``sections_and_throws.png`` shows
  two sections and the inferred throws.
  ``model_preview.png`` shows the terrain-clipped block in three dimensions.
* ``model.json`` records the pinned source, coordinate system, bounds,
  unit IDs, fault-block bits, every slip profile and modelling assumptions.

The script exposes ``load_inputs``, ``build_model``, ``sample_fields`` and
``run_example``. Load it by path with ``importlib.util`` (register the
module in ``sys.modules`` before ``exec_module``). ``build_model`` returns
``model, picks, horizon_faults``; the model can be evaluated at arbitrary
UTM points, independently of the exported grid. Keep geology resolution
and slip profiles fixed when comparing meshing resolutions. The custom
events are rebuilt from the pinned inputs; JSON is a provenance manifest,
not a generic LoopStructural model serialisation.

Sources
-------

* Montaño-Caro and Morales-Casique, *Implicit 3D structural geological
  modeling of the Mexico Basin: a scalable and reproducible open-source
  workflow*, `paper <https://doi.org/10.1007/s12145-025-02064-9>`_.
* `Dataset <https://doi.org/10.5281/zenodo.16423799>`_ and
  `pinned source <https://github.com/Nauj29/GemPy_Model_Mexico_Basin/tree/32e1ee55a656690150c3a1cce399e809611e263d>`_.

The source archive is verified by SHA-256 each time it is loaded. It is
read without extracting or executing upstream code. LICENSE and Zenodo
state CC BY 4.0, but the README also says noncommercial and the paper says
MIT for code. Source data stay in the local cache; resolve those conflicting
statements before redistributing them. This example is a new interpretation
of their inputs, not a reproduction or independent validation of GemPy.
