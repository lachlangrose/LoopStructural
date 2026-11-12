5. Real case studies
--------------------
Build complete geological models from published, openly accessible input
data. Each example identifies its sources and separates observations from
the assumptions needed to construct a model.

The Alès example downloads approximately 64 kB on its first run and caches
the original files, including their upstream licence. Install its plotting
and terrain dependencies with
:code:`pip install matplotlib pyvista tifffile`.

Set :code:`LOOPSTRUCTURAL_ALES_OUTPUT` to an output directory to save the
figures, :code:`ales_block.vtu`, three :code:`ales_fault_*.vtk` meshes and
the :code:`ales_base_CARBO.vtk`, :code:`ales_base_TRIAS.vtk` and
:code:`ales_base_LIAS.vtk` contacts. The mesh exports retain source
coordinates in metres. Contacts are clipped at terrain and the
unconformity; cells crossing a fault are omitted to avoid bridging its
displacement. A finer export grid reduces these gaps.

The Mexico Basin example provides ten separate, published submodel domains
for meshing experiments. It downloads a pinned archive (about 30 MB) once,
then runs offline. Install its additional dependencies with
:code:`pip install pyshp tifffile matplotlib pyvista`.

Run :code:`python examples/5_case_studies/plot_2_mexico_basin.py --zone North_2`
for the default case, or pass :code:`--all` to build all ten. Results go to
:code:`validation/mexico_basin/<zone>` unless :code:`--output` is specified.
The example's module documentation and :code:`mexico_basin.rst` describe
its displacement assumptions, reusable builder and exported implicit fields.
