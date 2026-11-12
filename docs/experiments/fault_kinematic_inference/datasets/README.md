# Fault kinematic test datasets

Three synthetic cases and two Australian survey extracts, prepared on 12 November
2026 for the [experiment plan](../README.md). No inference or success benchmark is
claimed by the creation of these data. See `validation_report.json` for the actual
dataset checks once validation has completed.

| Dataset | Purpose | Coordinate system |
|---|---|---|
| `synthetic_01_parallel_markers` | Oblique slip across parallel beds: map separation alone cannot resolve direction and magnitude independently. A hypothetical expert direction constraint makes the scalar problem tractable. | Local Cartesian metres |
| `synthetic_02_variable_slip` | Folded markers cut by a finite fault with an asymmetric displacement taper. | Local Cartesian metres |
| `synthetic_03_reactivation` | 300 m upward then 200 m downward wall-relative slip; old markers are identical to one 100 m upward event. | Local Cartesian metres |
| `real_01_hamersley` | GSWA geology, faults and bedding in a 20 x 20 km Rocklea/Hamersley window, using the existing map2loop snapshot. | GDA94 / MGA zone 50, EPSG:28350 |
| `real_02_mcarthur_river` | NTGS McArthur River Region geology, faults and bedding in a 20 x 20 km Batten-region window. Map 1991, GIS version 2018. | GDA94 / MGA zone 53, EPSG:28353 |

## Files and intended use

Every dataset contains `manifest.json`, `contacts.csv`, `bedding.csv`,
`contact_traces.geojson`, `faults.geojson`, `dem.tif`, `constraints.json`, a
`preview.png` and five spatial validation splits. Positions and elevations are in
metres. Bedding is provided as upward unit poles; the real examples do not establish
stratigraphic polarity. Dip direction is clockwise from north.

The real examples also retain clipped `geology.geojson` and
`source_structures.geojson` with source attributes. NTGS original mapped boundary
features are retained in `source_lithological_boundaries.geojson`. All GeoJSON files
use their declared projected/local coordinates, not RFC 7946 longitude/latitude;
respect the `crs` member when opening them in GIS.

Real examples include `unit_catalogue.csv`, `cutoff_candidates.csv` and
`fault_review_priority.csv`. Cutoff projections are geometric review candidates,
not measured slip or trusted matches. Each dataset has a `SHA256SUMS.json` inventory.

Synthetic `truth/` files contain the analytic generating parameters, exact contact
geometry and surface scalar fields. They are **evaluation-only**, not information
to give to an inference method or agent. The reactivation case's optional
intermediate-age marker is a subsurface/section diagnostic, deliberately outside
the surface-only inputs; it is not a fabricated surface survey observation.
The synthetic faults use a vertical limiting geometry, with explicitly labelled
positive and negative walls rather than a uniquely defined hanging wall.

Real contacts are **candidate boundaries between mapped unit pairs**, derived
from common polygon edges and excluded within 50 m of mapped fault traces and
5 m of the window edge. Neither a shared unit pair nor proximity to a fault proves
a basal-contact identity or a cross-fault correlation. A geologist must review
these before assigning a stratigraphic series, scalar level, contact correlation,
fault dip/sense or event order. None is invented here, and real slip truth is null.
`constraints.json` is a review template for real data and a labelled hypothetical
expert scenario for the synthetic experiments.

The GSWA snapshot is a 1:500,000 interpreted bedrock compilation. It is a deliberately
coarse regional example and should not be scored against a claim of metre-scale
mapping accuracy. The NTGS example is 1:100,000. Provisional positional errors
(150 m GSWA, 50 m NTGS) and 10-degree bedding errors are benchmark assumptions,
not published survey error estimates. Vary them during sensitivity analysis.

## Validation partitions

Each `splits/fold_N/` contains training and test contact/bedding CSVs and a
`mask.json`. The folds are contiguous northing/local-y strips. Training excludes
150 m around the held-out synthetic strip and 500 m around the held-out real strip.
These are spatial trace segments, not random withheld vertices. Long original
source features can span several spatial blocks: retain their source IDs and
treat errors as correlated rather than counting their vertices as independent.

The mask must also be applied to geological polygons, contact curves and any
derived matches/thicknesses used during inference. The complete source maps,
previews and truth files reveal the withheld geology; do not provide them as blind
training evidence. Known independent fault geometry and terrain can remain
conditioning inputs. `splits/counts.csv` records actual sample counts and exclusions.
Masked training map/curve GeoJSON files are included in each fold to make that
separation concrete; retain the same exclusion when deriving new constraints.

## Terrain and provenance

Real terrain is reprojected from zoom-11 Terrain Tiles on AWS, bilinearly sampled
onto a 401 x 401 grid (approximately 50 m spacing). This is not a claim of 50 m
survey accuracy. Contact and bedding elevations are sampled from that DEM, not
independently measured elevations. Absolute vertical-datum consistency with any
future boreholes must be checked before adding them.

Australia terrain data: copyright Commonwealth of Australia (Geoscience Australia)
2017. Terrain Tiles/Mapzen attribution and source-provider licence details are
retained in each real dataset's `TERRAIN_ATTRIBUTION.md`. See
[Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/).

Each real `manifest.json` records source URLs, source hashes, bounding box,
coordinate system, transforms and modifications. The original NTGS archive and
terrain tiles are cached under the repository's ignored
`.cache/fault_kinematic_downloads/` directory; the prepared datasets run offline.

## Licences

- Synthetic data/generators follow this repository's MIT licence.
- Hamersley: copyright State of Western Australia. The
  [DMIRS-016 bedrock compilation catalogue](https://catalogue.data.wa.gov.au/en/dataset/1-500-000-state-interpreted-bedrock-geology-dmirs-016)
  lists **CC BY-NC 4.0**. Preserve that non-commercial condition and attribution;
  the software's MIT licence does not replace it.
- McArthur River: copyright Northern Territory of Australia (Northern Territory
  Geological Survey), **CC BY 4.0**, as recorded in the
  [NTGS catalogue](https://geoscience.nt.gov.au/gemis/ntgsjspui/handle/1/81583).
  The original catalogue metadata are retained alongside the extract.
- Terrain retains its source-provider terms and the packaged attribution.

## Rebuild and check

Use the project Python environment with NumPy, pandas, scikit-image, Matplotlib,
requests, shapely, pyproj, rasterio and pyogrio. The geospatial readers were installed
in the local environment for this preparation; project dependency files were not
changed. Source downloads require internet access; generating synthetic datasets
or rebuilding from a populated cache does not.

From the repository root:

```powershell
.venv/Scripts/python.exe docs/experiments/fault_kinematic_inference/fetch_sources.py
.venv/Scripts/python.exe docs/experiments/fault_kinematic_inference/fetch_sources.py --terrain
.venv/Scripts/python.exe docs/experiments/fault_kinematic_inference/build_datasets.py
.venv/Scripts/python.exe docs/experiments/fault_kinematic_inference/build_datasets.py --finalize
.venv/Scripts/python.exe docs/experiments/fault_kinematic_inference/validate_datasets.py
```

For only the synthetic cases, pass `--synthetic-only` to the builder. The complete
validation command expects all five examples. Regeneration overwrites generated
files; retain original manifests/hashes when comparing a future source release.
