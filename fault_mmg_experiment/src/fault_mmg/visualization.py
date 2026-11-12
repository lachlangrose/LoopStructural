"""VTK exports and reproducible PyVista off-screen inspection figures."""

from pathlib import Path

import numpy as np
import pyvista as pv

from .geometry import labels, stratigraphy
from .interfaces import geological_interfaces


def add_stratigraphy_cell_data(data, unit, coordinate):
    """Store categorical units and block-local scalar values on volume cells."""
    data.cell_data["stratigraphy"] = np.asarray(unit, dtype=np.int32)
    data.cell_data["stratigraphic_coordinate"] = np.asarray(coordinate, dtype=float)
    # XML stores separate active point/cell arrays. Clear the point selection
    # so reopening a two-fault file selects the stratigraphy cell property.
    data.GetPointData().SetActiveScalars(None)
    data.set_active_scalars("stratigraphy", preference="cell")
    return data


def grid(mesh):
    cells = np.c_[np.full(len(mesh.tets), 4), mesh.tets].ravel()
    result = pv.UnstructuredGrid(
        cells, np.full(len(mesh.tets), pv.CellType.TETRA, dtype=np.uint8), mesh.points
    )
    block, unit = labels(mesh.centers)
    result.cell_data["fault_block"] = block
    result.cell_data["geological_unit"] = unit
    result.cell_data["material_reference"] = mesh.refs
    result.cell_data["block_and_unit"] = (block - 1) * 4 + unit
    return add_stratigraphy_cell_data(result, unit, stratigraphy(mesh.centers, block))


def surface(mesh, triangles):
    return pv.PolyData(mesh.points, np.c_[np.full(len(triangles), 3), triangles].ravel())


def screenshot(data, path, title, scalars=None, section=False, overlays=()):
    plotter = pv.Plotter(off_screen=True, window_size=(1400, 1000))
    plotter.set_background("white")
    plotter.add_mesh(
        data,
        scalars=scalars,
        show_edges=True,
        edge_color="#444444",
        cmap="tab10",
        color="#bbd9e8" if scalars is None else None,
        n_colors=len(np.unique(data[scalars])) if scalars else 1,
        scalar_bar_args={
            "title": scalars or "",
            "n_labels": len(np.unique(data[scalars])) if scalars else 0,
            "fmt": "%.0f",
        },
    )
    for overlay, width in overlays:
        plotter.add_mesh(overlay, color="#152735", line_width=width)
    plotter.add_text(title, color="#172b3a", font_size=16)
    plotter.add_axes()
    if section:
        plotter.view_xz()
        plotter.enable_parallel_projection()
        plotter.show_bounds(
            grid=False,
            location="outer",
            xtitle="x",
            ztitle="z",
            show_yaxis=False,
            color="#172b3a",
            font_size=12,
        )
    else:
        plotter.view_isometric()
    plotter.show(screenshot=str(path), auto_close=True)


def export(mesh, stem, *, pictures=False, final=False):
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    data = grid(mesh)
    data.save(str(stem) + ".vtu")
    if pictures:
        screenshot(data, str(stem) + ".png", stem.name.replace("_", " "), "material_reference")
    if final:
        d = geological_interfaces(mesh)
        fault = surface(mesh, d["faces"][d["fault"]])
        horizons = surface(mesh, d["faces"][d["horizons"]])
        horizon_blocks = d["blocks"][d["left"][d["horizons"]]]
        horizons.cell_data["fault_block"] = horizon_blocks
        horizons.cell_data["geological_unit_above"] = np.maximum(
            d["units"][d["left"][d["horizons"]]], d["units"][d["right"][d["horizons"]]]
        )
        fault.save(stem.parent / "fault_interface.vtp")
        horizons.save(stem.parent / "stratigraphic_interfaces.vtp")
        section = data.slice(normal=(0, 1, 0), origin=(0, 0, 0))
        section.save(stem.parent / "cross_section_y0.vtp")
        if pictures:
            screenshot(
                data,
                stem.parent / "final_fault_blocks.png",
                "Final mesh: fault blocks",
                "fault_block",
            )
            screenshot(
                data,
                stem.parent / "final_geological_units.png",
                "Final mesh: geological units",
                "geological_unit",
            )
            screenshot(
                fault,
                stem.parent / "fault_interface.png",
                "Fault: actual internal tetrahedron faces",
            )
            screenshot(
                horizons,
                stem.parent / "stratigraphic_interfaces.png",
                "Offset horizons: actual tetrahedron faces",
                "geological_unit_above",
            )
            screenshot(
                section,
                stem.parent / "cross_section_y0.png",
                "y = 0: fault and three horizons, throw = 0.4",
                "geological_unit",
                True,
                [
                    (fault.slice(normal=(0, 1, 0), origin=(0, 0, 0)), 4),
                    (horizons.slice(normal=(0, 1, 0), origin=(0, 0, 0)), 3),
                ],
            )
