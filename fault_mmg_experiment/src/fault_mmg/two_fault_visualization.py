"""Visualise the actual T or X junction and offset, inclined horizon faces."""

from pathlib import Path

import numpy as np
import pyvista as pv

from .interfaces import edges
from .two_faults import STRAT_NORMAL, interfaces
from .visualization import add_stratigraphy_cell_data, grid, surface


def volume_grid(mesh, model):
    data = grid(mesh)
    block, unit = model.labels(mesh.centers)
    data.cell_data["fault_block"] = block
    data.cell_data["geological_unit"] = unit
    data.cell_data["block_and_unit"] = (block - 1) * 4 + unit
    coordinate = mesh.centers @ STRAT_NORMAL - np.array([model.offsets[int(b)] for b in block])
    data.point_data["primary_fault_function"] = mesh.points[:, 0]
    data.point_data["secondary_fault_function"] = model.secondary(mesh.points)
    return add_stratigraphy_cell_data(data, unit, coordinate)


def export_volume(mesh, model, path):
    volume_grid(mesh, model).save(path)


def export_two_faults(mesh, model, directory, pictures=True):
    directory = Path(directory)
    data = volume_grid(mesh, model)
    data.save(directory / "final_mesh.vtu")
    d = interfaces(mesh, model)
    primary = surface(mesh, d["faces"][d["primary"]])
    secondary = surface(mesh, d["faces"][d["secondary"]])
    horizons = surface(mesh, d["faces"][d["horizon"]])
    horizons.cell_data["geological_unit_above"] = np.maximum(
        d["unit"][d["left"][d["horizon"]]], d["unit"][d["right"][d["horizon"]]]
    )
    horizons.cell_data["fault_block"] = d["block"][d["left"][d["horizon"]]]
    common = set(map(tuple, edges(d["faces"][d["primary"]]))) & set(
        map(tuple, edges(d["faces"][d["secondary"]]))
    )
    junction = pv.PolyData()
    junction.points = mesh.points
    junction.lines = np.c_[np.full(len(common), 2), np.array(sorted(common), dtype=int)].ravel()
    junction = junction.clean()
    for name, obj in (
        ("primary_fault", primary),
        ("secondary_fault", secondary),
        ("fault_junction", junction),
        ("stratigraphic_interfaces", horizons),
    ):
        obj.save(directory / f"{name}.vtp")
    sections = {}
    for name, normal, origin, view in (
        ("cross_section_y0", (0, 1, 0), (0, 0, 0), "xz"),
        ("cross_section_z0", (0, 0, 1), (0, 0, 0), "xy"),
        ("cross_section_x035", (1, 0, 0), (0.35, 0, 0), "yz"),
    ):
        section = data.slice(normal=normal, origin=origin)
        section.save(directory / f"{name}.vtp")
        sections[name] = (section, normal, origin, view)
    if not pictures:
        return

    def plotter(title):
        p = pv.Plotter(off_screen=True, window_size=(1440, 1080))
        p.set_background("white")
        p.add_text(title, color="#172b3a", font_size=17)
        p.add_axes()
        return p

    p = plotter(
        "Secondary fault terminates on primary"
        if model.case == "terminating"
        else "Two crossing faults: shared junction"
    )
    p.add_mesh(
        pv.Box(bounds=(-1, 1, -1, 1, -1, 1)).extract_all_edges(), color="#9aa9af", line_width=1
    )
    p.add_mesh(
        primary,
        color="#3694c3",
        opacity=0.55,
        show_edges=True,
        edge_color="#376174",
        label="Primary: x = 0",
    )
    p.add_mesh(
        secondary,
        color="#f39c35",
        opacity=0.85,
        show_edges=True,
        edge_color="#76522d",
        label="Secondary: y - 0.35z = 0.1",
    )
    p.add_mesh(junction, color="#102835", line_width=7, label="Shared junction edges")
    p.add_text(
        "Blue: primary fault   Orange: secondary fault   Black: shared junction",
        position="lower_left",
        color="#172b3a",
        font_size=12,
    )
    p.view_isometric()
    p.show(screenshot=str(directory / "fault_network.png"))
    for scalar in ("fault_block", "geological_unit"):
        p = plotter(f"{model.case.title()} faults: {scalar.replace('_', ' ')}")
        p.add_mesh(
            data,
            scalars=scalar,
            show_edges=True,
            edge_color="#555555",
            cmap="tab10",
            n_colors=len(np.unique(data[scalar])),
            scalar_bar_args={
                "title": scalar,
                "n_labels": len(np.unique(data[scalar])),
                "fmt": "%.0f",
            },
        )
        p.view_isometric()
        p.show(screenshot=str(directory / f"final_{scalar}.png"))
    p = plotter("Three inclined horizons: different traces in each fault block")
    p.add_mesh(
        horizons,
        scalars="geological_unit_above",
        n_colors=3,
        cmap="viridis",
        show_edges=True,
        scalar_bar_args={"title": "Horizon", "n_labels": 3, "fmt": "%.0f"},
    )
    p.add_mesh(junction, color="#102835", line_width=5)
    p.view_isometric()
    p.show(screenshot=str(directory / "stratigraphic_interfaces.png"))
    for name, (section, normal, origin, view) in sections.items():
        scalar = "fault_block" if view == "xy" else "geological_unit"
        p = plotter(f"{model.case.title()} faults: {name.replace('_', ' ')}")
        p.add_mesh(
            section,
            scalars=scalar,
            n_colors=len(np.unique(data[scalar])),
            cmap=(
                ["#b4d6e7", "#f3cca3", "#b4dca9", "#d7b6e4"][: len(model.blocks)]
                if scalar == "fault_block"
                else "tab10"
            ),
            show_edges=True,
            edge_color="#777777",
            scalar_bar_args={
                "title": scalar,
                "n_labels": len(np.unique(data[scalar])),
                "fmt": "%.0f",
            },
        )
        for obj, color in ((primary, "#154b72"), (secondary, "#bd5200"), (horizons, "#243137")):
            if view == "xy" and obj is horizons:
                continue
            trace = obj.slice(normal=normal, origin=origin)
            if trace.n_cells:
                p.add_mesh(trace, color=color, line_width=5 if obj is not horizons else 3)
        getattr(p, "view_" + view)()
        p.enable_parallel_projection()
        p.show_bounds(
            grid=False,
            location="outer",
            show_xaxis=view != "yz",
            show_yaxis=view != "xz",
            show_zaxis=view != "xy",
            font_size=12,
            color="#172b3a",
        )
        p.show(screenshot=str(directory / f"{name}.png"))
