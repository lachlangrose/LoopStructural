from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence
import webbrowser

import numpy as np
import pyvista as pv

from loop_visualization import Loop3DView

from . import initialize


def _add_demo_scene(plotter: Loop3DView, scene: str) -> None:
    """Populate the viewer with a small demo scene."""
    if scene == "sphere":
        mesh = pv.Sphere(theta_resolution=64, phi_resolution=64)
        mesh["radius"] = np.linalg.norm(mesh.points, axis=1)
        plotter.add_mesh(mesh, cmap="viridis", name="sphere")
    elif scene == "cube":
        mesh = pv.Cube().triangulate()
        mesh["z"] = mesh.points[:, 2]
        plotter.add_mesh(mesh, cmap="coolwarm", show_edges=True, name="cube")
    else:
        mesh = pv.Wavelet()
        contour = mesh.contour(isosurfaces=12)
        plotter.add_mesh(contour, cmap="plasma", opacity=0.85, name="wavelet")

    plotter.add_axes()
    plotter.view_isometric()


def _add_mesh_files(plotter: Loop3DView, mesh_paths: Sequence[str]) -> int:
    """Load mesh files and add each mesh with a stable UI label."""
    loaded = 0
    for mesh_path in mesh_paths:
        path = Path(mesh_path).expanduser().resolve()
        if not path.exists():
            print(f"Skipping missing mesh file: {path}")
            continue
        try:
            mesh = pv.read(path)
        except Exception as exc:  # pragma: no cover
            print(f"Skipping unreadable mesh file {path}: {exc}")
            continue

        plotter.add_mesh(mesh, name=path.stem)
        loaded += 1

    if loaded:
        plotter.add_axes()
        plotter.view_isometric()
    return loaded


def _add_test_spheres(plotter: Loop3DView) -> None:
    """Temporarily add two labeled spheres for UI toggle testing."""
    sphere_a = pv.Sphere(radius=0.25, center=(-0.4, 0.0, 0.0), theta_resolution=48, phi_resolution=48)
    sphere_b = pv.Sphere(radius=0.25, center=(0.4, 0.0, 0.0), theta_resolution=48, phi_resolution=48)
    plotter.add_mesh(sphere_a, color="tomato", name="a")
    plotter.add_mesh(sphere_b, color="royalblue", name="b")
    plotter.add_axes()
    plotter.view_isometric()


def _initialize_trame_widgets(server) -> None:
    """Register trame widget modules required by the PyVista UI."""
    from trame.widgets import html as html_widgets
    from trame.widgets import vtk as vtk_widgets

    html_widgets.initialize(server)
    vtk_widgets.initialize(server)

    if server.client_type == "vue2":  # pragma: no cover
        from trame.widgets import vuetify as vuetify2_widgets

        vuetify2_widgets.initialize(server)
    else:
        from trame.widgets import vuetify3 as vuetify3_widgets

        vuetify3_widgets.initialize(server)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-trame-app",
        description="Run a standalone trame app for Loop visualization.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind the trame server to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind the trame server to.",
    )
    parser.add_argument(
        "--mode",
        choices=("trame", "server", "client"),
        default="trame",
        help="Rendering mode for the viewer.",
    )
    parser.add_argument(
        "--scene",
        choices=("wavelet", "sphere", "cube"),
        default="wavelet",
        help="Built-in demo scene to show on startup when no mesh files are provided.",
    )
    parser.add_argument(
        "--mesh",
        action="append",
        default=[],
        help=(
            "Path to a mesh file to load (can be repeated). "
            "If any mesh files are provided, the demo scene is not added."
        ),
    )
    parser.add_argument(
        "--test-spheres",
        action="store_true",
        help="Temporarily load two spheres named 'a' and 'b' for menu toggle testing.",
    )
    parser.add_argument(
        "--collapse-menu",
        action="store_true",
        help="Start with the trame side menu collapsed.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser tab automatically.",
    )
    parser.add_argument(
        "--server-name",
        default="loop_visualization",
        help="Trame server instance name.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Launch the standalone loop visualization trame app."""
    try:
        from trame.app import get_server
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Trame is required to run this app. Install with: "
            "pip install loop-visualization[trame]"
        ) from exc

    args = _build_parser().parse_args(argv)

    plotter = Loop3DView(off_screen=True)
    if args.test_spheres:
        _add_test_spheres(plotter)
    elif args.mesh:
        loaded = _add_mesh_files(plotter, args.mesh)
        if loaded == 0:
            raise RuntimeError("No mesh files could be loaded from --mesh arguments")
    else:
        _add_demo_scene(plotter, args.scene)

    server = get_server(name=args.server_name)
    _initialize_trame_widgets(server)
    initialize(
        server,
        plotter,
        mode=args.mode,
        default_server_rendering=args.mode != "client",
        collapse_menu=args.collapse_menu,
    )

    access_host = args.host
    if access_host in {"0.0.0.0", "::"}:
        access_host = "localhost"

    app_url = (
        f"http://{access_host}:{args.port}/index.html"
        f"?ui={plotter._id_name}&reconnect=auto"
    )

    print(f"Starting loop-trame-app at {app_url}")
    if not args.no_browser:
        webbrowser.open(app_url)
    server.start(
        host=args.host,
        port=args.port,
        open_browser=False,
        exec_mode="main",
    )


if __name__ == "__main__":
    main()
