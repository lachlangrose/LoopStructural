"""
5a. Alès Basin: contacts, faults and an unconformity
===================================================
Build a geological model of the Alès area in southern France using the
contact points, clustered orientations and terrain published with GemPy.
The three labelled contacts are CARBO (Carboniferous), TRIAS (Triassic)
and LIAS (Early Jurassic). This is a LoopStructural interpretation of
those inputs, rather than a reproduction of GemPy's interpolation.

Sources
-------
* `GemPy Alès example <https://docs.gempy.org/examples/real/Alesmodel.html>`_.
* `Original input files <https://github.com/cgre-aachen/gempy_data/tree/master/data/input_data/AlesModel>`_.
* Heim et al. (2019), `Is it possible to capture epistemic uncertainty in
  geological models? <https://meetingorganizer.copernicus.org/EGU2019/EGU2019-17448.pdf>`_.

Downloads are pinned to a repository commit and checked against SHA-256
hashes. The upstream repository's LGPL-3.0 licence is cached alongside the
unaltered data; it is separate from this example's code licence. Coordinates
and elevations remain in the source coordinate system and metres. The
terrain file does not declare an EPSG code, so none is assigned here.

Modelling assumptions
---------------------
We interpret the labelled surfaces as the bases of their named units.
TRIAS and LIAS share one conformable scalar field, with an assumed 300 m
scalar interval. A pre-Triassic unconformity truncates an independently
interpolated Carboniferous group. Older, unspecified rocks are called
Basement. Orientation vectors set a unit gradient magnitude, so scalar
values have an approximate distance scale, but residuals are not geometric
distances.

The supplied files constrain fault geometry, not slip history. The three
faults are independent and younger than both groups. Displacements of
300, 400 and 200 m and down-dip slip are illustrative assumptions, exposed
in ``FAULT_DISPLACEMENTS``. They have not been calibrated against field
offsets. The source documentation also notes poorly constrained areas;
the resulting model is an educational interpretation.

Running the example
-------------------
Install :code:`matplotlib pyvista tifffile` alongside LoopStructural, then
run this script. Its first run downloads about 64 kB into a temporary cache;
subsequent runs work offline. Set ``LOOPSTRUCTURAL_ALES_DATA`` to choose
another cache directory. Set ``LOOPSTRUCTURAL_ALES_OUTPUT`` to save the
figures, a VTK block model, fault and stratigraphic surface meshes, its unit
legend and contact-fit statistics
without opening windows. These statistics measure fit to the input
contacts, rather than independent validation.
"""

import os
from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir
from urllib.request import urlopen

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyvista as pv
import tifffile
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from scipy.interpolate import RegularGridInterpolator

from LoopStructural import GeologicalModel

COMMIT = "cf00bc907d3e6962967da38ae2ad19d770df956e"
DATA_URL = f"https://raw.githubusercontent.com/cgre-aachen/gempy_data/{COMMIT}/"
FILES = {
    "2018_interf.csv": "350b0776a61ea33e96943054d6d99c25a7e4ad630cad9b5adb57bfa59555e6f1",
    "2018_orient_clust_n_init5_0.csv": "717944a8c1a1b6f0f40b18e330a917a5325113b49b7ff93f83503259c713870a",
    "_cropped_DEM_coarse.tif": "cf232ade6a73be9e70d2edf656664fe4594bee87e2a1dcc177574d1afdf9ba68",
    "LICENSE": "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118",
}
ORIGIN = np.array([729550.0, 1913500.0, -1800.0])
MAXIMUM = np.array([751500.0, 1923650.0, 800.0])
TRIASSIC_INTERVAL = 300.0
FAULT_DISPLACEMENTS = {"fault_left": 300.0, "fault_right": 400.0, "fault_lr": 200.0}
COLOURS = {"LIAS": "#015482", "TRIAS": "#9f0052", "CARBO": "#ffbe00", "Basement": "#b0b0b0"}
GROUPS = {"TRIAS": "mesozoic", "LIAS": "mesozoic", "CARBO": "carboniferous"}


######################################################################
# Read the original observations and terrain
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Only source X/Y/Z and pole vectors are used. GemPy's pre-rescaled
# coordinates and internal ordering columns are not LoopStructural inputs.


def load_inputs(directory=None):
    """Cache the unchanged, pinned source files and return both input tables."""
    if directory is None:
        directory = os.environ.get(
            "LOOPSTRUCTURAL_ALES_DATA",
            str(Path(gettempdir()) / "loopstructural-examples" / "ales" / COMMIT[:12]),
        )
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for filename, checksum in FILES.items():
        path = directory / filename
        if not path.exists():
            relative_path = (
                filename if filename == "LICENSE" else f"data/input_data/AlesModel/{filename}"
            )
            print(f"Downloading Alès input: {filename}")
            with urlopen(DATA_URL + relative_path, timeout=30) as response:
                content = response.read()
            if sha256(content).hexdigest() != checksum:
                raise ValueError(f"Unexpected checksum for downloaded {filename}")
            path.write_bytes(content)
        if sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Cached input {path} differs from the pinned source")
    contacts = pd.read_csv(directory / "2018_interf.csv")
    orientations = pd.read_csv(directory / "2018_orient_clust_n_init5_0.csv")
    return contacts, orientations, directory / "_cropped_DEM_coarse.tif"


def load_terrain(filename):
    """Interpolate terrain at pixel centres, retaining the raster footprint."""
    with tifffile.TiffFile(filename) as raster:
        page = raster.pages[0]
        elevation = page.asarray().astype(float)
        dx, dy, _ = page.tags["ModelPixelScaleTag"].value
        _, _, _, x0, y0, _ = page.tags["ModelTiepointTag"].value
        nodata = page.tags.get("GDAL_NODATA")
        if nodata is not None:
            elevation[elevation == float(nodata.value)] = np.nan
    rows, columns = elevation.shape
    x = x0 + (np.arange(columns) + 0.5) * dx
    y = y0 - (np.arange(rows) + 0.5) * dy
    interpolator = RegularGridInterpolator(
        (y[::-1], x), elevation[::-1], bounds_error=False, fill_value=np.nan
    )

    def terrain(xy):
        xy = np.asarray(xy)
        # Extend edge pixel values to their edges, but never beyond the raster.
        samples = np.column_stack([np.clip(xy[:, 1], y[-1], y[0]), np.clip(xy[:, 0], x[0], x[-1])])
        values = interpolator(samples)
        outside = (
            (xy[:, 0] < x0)
            | (xy[:, 0] > x0 + columns * dx)
            | (xy[:, 1] < y0 - rows * dy)
            | (xy[:, 1] > y0)
        )
        values[outside] = np.nan
        return values

    return terrain


######################################################################
# Translate contacts and orientations, then build youngest to oldest
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ``nx, ny, nz`` constrain both direction and magnitude of a gradient.
# Faults use their supplied pole vectors; the slip vector is the downward
# vertical projected into the mean fault plane. No fault cuts another.


def build_model(contacts, orientations, *, nelements=10000, fault_displacements=None):
    """Build two stratigraphic fields and three independently constrained faults."""
    if fault_displacements is None:
        fault_displacements = FAULT_DISPLACEMENTS
    contacts = contacts.copy()
    orientations = orientations.copy()
    contacts["feature_name"] = contacts["formation"].replace(GROUPS)
    contacts["val"] = contacts["formation"].map(
        {
            "CARBO": 0.0,
            "TRIAS": 0.0,
            "LIAS": TRIASSIC_INTERVAL,
            **dict.fromkeys(FAULT_DISPLACEMENTS, 0.0),
        }
    )
    orientations["feature_name"] = orientations["formation"].replace(GROUPS)
    orientations = orientations.rename(columns={"G_x": "nx", "G_y": "ny", "G_z": "nz"})
    data = pd.concat(
        [
            contacts[["X", "Y", "Z", "formation", "feature_name", "val"]],
            orientations[["X", "Y", "Z", "formation", "feature_name", "nx", "ny", "nz"]],
        ],
        ignore_index=True,
    )
    inside = ((data[["X", "Y", "Z"]] >= ORIGIN) & (data[["X", "Y", "Z"]] <= MAXIMUM)).all(axis=1)
    print(f"Using {inside.sum()} of {len(data)} observations inside the reference model extent.")
    data = data.loc[inside].copy()
    model = GeologicalModel(ORIGIN, MAXIMUM)
    model.data = data
    for name, displacement in fault_displacements.items():
        poles = data.loc[data["feature_name"] == name, ["nx", "ny", "nz"]].dropna()
        normal = poles.mean().to_numpy()
        normal = normal / np.linalg.norm(normal)
        slip = np.array([0.0, 0.0, -1.0])
        slip -= np.dot(slip, normal) * normal
        slip /= np.linalg.norm(slip)
        model.create_and_add_fault(
            name,
            displacement,
            faults=[],
            fault_slip_vector=slip,
            interpolatortype="FDI",
            nelements=4000,
            solver="lsmr",
            tol=1e-6,
        )
    options = dict(
        interpolatortype="FDI", nelements=nelements, solver="lsmr", tol=1e-6, cpw=10.0, npw=1.0
    )
    mesozoic = model.create_and_add_foliation("mesozoic", **options)
    model.add_unconformity(mesozoic, 0.0)
    model.create_and_add_foliation("carboniferous", **options)

    # The column is assembled oldest first, independently of feature creation.
    column = model.stratigraphic_column
    column.clear(basement=False)
    basement = column.add_unit("Basement", thickness=1.0, id=1, colour=COLOURS["Basement"])
    carboniferous = column.add_unit("CARBO", thickness=np.inf, id=0, colour=COLOURS["CARBO"])
    column.add_unconformity("Pre-Triassic unconformity")
    column.add_unit("TRIAS", thickness=TRIASSIC_INTERVAL, id=3, colour=COLOURS["TRIAS"])
    column.add_unit("LIAS", thickness=np.inf, id=2, colour=COLOURS["LIAS"])
    column.group_mapping.update({"Group_0": "mesozoic", "Group_1": "carboniferous"})
    # CARBO's observed base is zero. Neither CARBO's top nor Basement's
    # base is assigned a fabricated thickness; extend their ranges to infinity.
    basement.min_value, basement.max_value = -np.inf, 0.0
    carboniferous.min_value, carboniferous.max_value = 0.0, np.inf
    model.update(progressbar=False)
    return model, data


def contact_fit(model, data):
    """Report scalar residuals at fitted contacts, ignoring display masks."""
    records = []
    for formation, rows in data.loc[data["val"].notna()].groupby("formation"):
        name = rows["feature_name"].iloc[0]
        # Fault surfaces have their own normalised scalar scale.
        feature = model[name][0] if name in FAULT_DISPLACEMENTS else model[name]
        values = feature.evaluate_value(rows[["X", "Y", "Z"]].to_numpy(), ignore_regions=True)
        if not np.isfinite(values).all():
            raise RuntimeError(f"Non-finite model values at {formation} contacts")
        residual = values - rows["val"].to_numpy()
        records.append(
            {
                "formation": formation,
                "n": len(rows),
                "rms_scalar": np.sqrt(np.mean(residual**2)),
                "max_abs_scalar": np.max(np.abs(residual)),
            }
        )
    return pd.DataFrame(records)


######################################################################
# Compare terrain geology with the input contacts and inspect sections
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Colours follow the IDs returned by ``evaluate_model``. Blank areas are
# above terrain or beyond its coverage. The black section lines show the
# three zero-valued fault surfaces.


def plot_sections(model, contacts, terrain, units):
    """Plot the predicted terrain geology and two east-west sections."""
    cmap = ListedColormap([COLOURS[name] for name in units])
    norm = BoundaryNorm(np.arange(len(units) + 1) - 0.5, len(units))
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), constrained_layout=True)
    x = np.linspace(ORIGIN[0], MAXIMUM[0], 180)
    y = np.linspace(ORIGIN[1], MAXIMUM[1], 90)
    xx, yy = np.meshgrid(x, y)
    xy = np.column_stack([xx.ravel(), yy.ravel()])
    height = terrain(xy)
    valid = np.isfinite(height)
    ids = np.full(len(xy), -1)
    ids[valid] = model.evaluate_model(np.column_stack([xy[valid], height[valid]]))
    axes[0].pcolormesh(
        xx / 1000,
        yy / 1000,
        np.ma.masked_less(ids.reshape(xx.shape), 0),
        cmap=cmap,
        norm=norm,
        shading="auto",
    )
    for fault in model.faults:
        fault_values = np.full(len(xy), np.nan)
        fault_values[valid] = fault[0].evaluate_value(np.column_stack([xy[valid], height[valid]]))
        axes[0].contour(
            xx / 1000,
            yy / 1000,
            fault_values.reshape(xx.shape),
            levels=[0],
            colors="black",
            linewidths=0.8,
        )
    for name, colour in COLOURS.items():
        rows = contacts.loc[contacts["formation"] == name]
        axes[0].scatter(
            rows["X"] / 1000, rows["Y"] / 1000, s=12, c=colour, edgecolors="white", linewidths=0.4
        )
    axes[0].set(
        xlabel="Source X (km)",
        ylabel="Source Y (km)",
        title="Predicted geology at terrain; dots are input contacts",
    )
    axes[0].set_aspect("equal")
    for ax, section_y in zip(axes[1:], [1916000.0, 1920000.0]):
        xx, zz = np.meshgrid(x, np.linspace(ORIGIN[2], MAXIMUM[2], 65))
        points = np.column_stack([xx.ravel(), np.full(xx.size, section_y), zz.ravel()])
        heights = terrain(points[:, :2])
        ids = model.evaluate_model(points)
        ids[(points[:, 2] > heights) | ~np.isfinite(heights)] = -1
        ax.pcolormesh(
            xx / 1000,
            zz,
            np.ma.masked_less(ids.reshape(xx.shape), 0),
            cmap=cmap,
            norm=norm,
            shading="auto",
        )
        for fault in model.faults:
            values = fault[0].evaluate_value(points).reshape(xx.shape)
            values[(zz > heights.reshape(xx.shape)) | ~np.isfinite(heights.reshape(xx.shape))] = (
                np.nan
            )
            ax.contour(xx / 1000, zz, values, levels=[0], colors="black", linewidths=0.8)
        ax.plot(
            x / 1000,
            terrain(np.column_stack([x, np.full(len(x), section_y)])),
            color="black",
            linewidth=1.5,
        )
        ax.set(
            xlabel="Source X (km)",
            ylabel="Elevation (m)",
            title=f"East-west section at source Y = {section_y / 1000:g} km (vertical scale exaggerated)",
        )
        axes[0].axhline(section_y / 1000, color="black", linestyle="--", linewidth=0.7)
    fig.legend(
        handles=[Patch(facecolor=COLOURS[name], label=name) for name in units],
        loc="outside lower center",
        ncol=len(units),
    )
    return fig


######################################################################
# Build a terrain-clipped 3D block and export reusable results
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# VTK cell centres are evaluated directly in world coordinates. The same
# model can therefore be sampled on another grid or exported for further
# work, without rerunning data preparation. Only the displayed meshes are
# shifted horizontally to the domain origin and converted to kilometres,
# keeping axis labels readable. Exported coordinates remain unchanged.


def sampling_grid(dimensions=(91, 46, 27)):
    """Create an explicit, double-precision grid in source coordinates."""
    dimensions = np.asarray(dimensions)
    image = pv.ImageData(
        dimensions=dimensions, origin=ORIGIN, spacing=(MAXIMUM - ORIGIN) / (dimensions - 1)
    )
    # Explicit double-precision points prevent VTK threshold/export from
    # rounding large source coordinates when materialising an implicit grid.
    grid = pv.StructuredGrid()
    grid.points = image.points.astype(np.float64)
    grid.dimensions = dimensions
    return grid


def export_surfaces(model, terrain, output_directory, dimensions=(91, 46, 27)):
    """Export terrain-clipped fault surfaces and the bases of the three units.

    Stratigraphic contours omit cells straddling a fault, leaving grid-sized
    gaps instead of artificial triangles bridging its displacement. Increase
    ``dimensions`` to reduce these gaps. CARBO is also clipped below the
    pre-Triassic unconformity. Basement has no observed base to export.
    """
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    grid = sampling_grid(dimensions)
    volume = grid.cast_to_unstructured_grid()
    corners = volume.cell_connectivity.reshape(-1, 8)
    keep = np.ones(volume.n_cells, dtype=bool)
    meshes = {}

    def clip_to_terrain(surface):
        if surface.n_cells == 0:
            raise RuntimeError("Surface does not intersect the sampling grid")
        heights = terrain(surface.points[:, :2])
        surface.point_data["terrain_valid"] = np.isfinite(heights).astype(float)
        surface.point_data["terrain_clearance"] = heights - surface.points[:, 2]
        surface = surface.threshold(
            0.5,
            scalars="terrain_valid",
            all_scalars=True,
        ).extract_surface()
        return surface.clip_scalar(
            scalars="terrain_clearance",
            value=0.0,
            invert=False,
        ).triangulate()

    for fault in model.faults:
        values = fault[0].evaluate_value(grid.points)
        grid.point_data["fault"] = values
        surface = grid.contour([0.0], scalars="fault")
        meshes[f"ales_{fault.name}"] = clip_to_terrain(surface)
        # A scalar discontinuity must not become a connecting isosurface.
        cell_values = values[corners]
        crossing = (cell_values < 0.0).any(axis=1) & (cell_values >= 0.0).any(axis=1)
        keep &= ~crossing

    print("Sampling stratigraphic surfaces in source coordinates.", flush=True)
    for name in ("mesozoic", "carboniferous"):
        volume.point_data[name] = model[name].evaluate_value(grid.points, ignore_regions=True)
    fault_blocks = volume.extract_cells(keep)
    for unit, feature, value in (
        ("CARBO", "carboniferous", 0.0),
        ("TRIAS", "mesozoic", 0.0),
        ("LIAS", "mesozoic", TRIASSIC_INTERVAL),
    ):
        surface = fault_blocks.contour([value], scalars=feature)
        if unit == "CARBO":
            surface = surface.clip_scalar(scalars="mesozoic", value=0.0, invert=True)
        meshes[f"ales_base_{unit}"] = clip_to_terrain(surface)

    records = []
    for name, mesh in meshes.items():
        if mesh.n_cells == 0:
            raise RuntimeError(f"No triangles remain after clipping {name}")
        mesh.clear_data()
        mesh.field_data["surface_name"] = [name]
        mesh.field_data["coordinate_units"] = ["metres"]
        mesh.save(output_directory / f"{name}.vtk")
        records.append({"file": f"{name}.vtk", "points": mesh.n_points, "triangles": mesh.n_cells})
    pd.DataFrame(records).to_csv(output_directory / "ales_surfaces.csv", index=False)
    print(f"Exported {len(meshes)} surface meshes to {output_directory}", flush=True)
    return meshes


def plot_block(model, terrain, units, output_directory=None):
    """Show or save a PyVista block model and its fault surfaces."""
    grid = sampling_grid()
    centres = grid.cell_centers().points
    height = terrain(centres[:, :2])
    ids = model.evaluate_model(centres)
    ids[(centres[:, 2] > height) | ~np.isfinite(height)] = -1
    grid.cell_data["unit_id"] = ids
    block = grid.threshold([-0.5, len(units) - 0.5], scalars="unit_id")

    def display_mesh(mesh):
        displayed = mesh.copy()
        displayed.points = (displayed.points - [ORIGIN[0], ORIGIN[1], 0.0]) / 1000
        return displayed

    viewer = pv.Plotter(off_screen=output_directory is not None, window_size=(1400, 850))
    viewer.set_background("white")
    viewer.add_mesh(
        display_mesh(block),
        scalars="unit_id",
        cmap=[COLOURS[name] for name in units],
        clim=(-0.5, len(units) - 0.5),
        show_scalar_bar=False,
    )
    for fault in model.faults:
        values = fault[0].evaluate_value(grid.points)
        grid.point_data["fault"] = values
        surface = grid.contour([0.0], scalars="fault")
        heights = terrain(surface.points[:, :2])
        surface.point_data["below_terrain"] = (
            (surface.points[:, 2] <= heights) & np.isfinite(heights)
        ).astype(float)
        viewer.add_mesh(
            display_mesh(surface.threshold(0.5, scalars="below_terrain")),
            color="black",
            opacity=0.45,
        )
    viewer.add_legend(
        [(name, COLOURS[name]) for name in units],
        bcolor="white",
        face="rectangle",
        size=(0.17, 0.18),
    )
    viewer.add_text("Alès Basin | illustrative fault displacements", color="black", font_size=12)
    viewer.show_grid(
        xtitle="X from origin (km)",
        ytitle="Y from origin (km)",
        ztitle="Elevation (km)",
        n_xlabels=3,
        n_ylabels=3,
        n_zlabels=3,
        fmt="%.1f",
        font_size=10,
        color="black",
    )
    viewer.view_isometric()
    if output_directory is None:
        viewer.show()
    else:
        block.save(output_directory / "ales_block.vtu")
        viewer.show(screenshot=str(output_directory / "ales_block.png"))
    return block


def run_example(data_directory=None, output_directory=None):
    """Run the full example, optionally saving results without opening windows."""
    contacts, orientations, terrain_path = load_inputs(data_directory)
    terrain = load_terrain(terrain_path)
    model, data = build_model(contacts, orientations)
    model.dtm = terrain
    units = [
        unit.name
        for group in reversed(model.stratigraphic_column.get_groups())
        for unit in group.units
    ]
    fit = contact_fit(model, data)
    print("Input contact fit (fault and stratigraphic scalars have different scales):")
    print(fit.to_string(index=False))
    fig = plot_sections(model, data.loc[data["val"].notna()], terrain, units)
    if output_directory is None:
        output_directory = os.environ.get("LOOPSTRUCTURAL_ALES_OUTPUT")
    if output_directory is not None:
        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_directory / "ales_map_sections.png", dpi=160)
        plt.close(fig)
        fit.to_csv(output_directory / "ales_contact_fit.csv", index=False)
        pd.DataFrame(
            {
                "unit_id": range(len(units)),
                "unit": units,
                "colour": [COLOURS[name] for name in units],
            }
        ).to_csv(output_directory / "ales_units.csv", index=False)
        data.to_csv(output_directory / "ales_loopstructural_inputs.csv", index=False)
    else:
        plt.show()
    block = plot_block(model, terrain, units, output_directory)
    if output_directory is not None:
        export_surfaces(model, terrain, output_directory)
    return model, data, block


if __name__ == "__main__":
    model, data, block = run_example()
