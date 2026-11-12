"""Plot actual gradient magnitudes from the saved FDI experiment fields.

Run with the project's Python environment; no interpolation is refitted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from loop_interpolation.experimental.benchmark_gradient_smoothness import make_problem
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D

NAMES = ("plane", "cylinder", "varying")
TITLES = {"plane": "Plane", "cylinder": "Cylindrical cap", "varying": "Varying curvature"}
METHODS = ("native", "baseline", "normalised")
LABELS = {
    "native": "Native FDI reference",
    "baseline": "Matched ordinary Hessian",
    "normalised": "Gradient-normalised",
}
COLOURS = {"native": "#7f858d", "baseline": "#2467a8", "normalised": "#d56725"}


def save_figure(figure: plt.Figure, directory: Path, stem: str) -> None:
    """Save a preview and a scalable version of the same scientific plot."""
    figure.savefig(directory / f"{stem}.png", dpi=180, facecolor="white")
    figure.savefig(directory / f"{stem}.svg", facecolor="white")
    plt.close(figure)


def label_contours(ax: plt.Axes, contours: object) -> list:
    """Keep numeric contour labels inside the visible panel."""
    labels = []
    for level, segments in zip(contours.levels, contours.allsegs):
        points = np.concatenate([segment for segment in segments if len(segment)])
        safe = points[
            (points[:, 0] > -0.52)
            & (points[:, 0] < 0.52)
            & (points[:, 1] > -0.285)
            & (points[:, 1] < 0.285)
        ]
        if not len(safe):
            safe = points
        point = safe[np.argmin(np.abs(safe[:, 0]))]
        labels.extend(
            ax.clabel(
                contours,
                levels=[level],
                manual=[tuple(point)],
                fmt={level: "0" if level == 0 else f"{level:.2f}"},
                fontsize=7,
                inline_spacing=2,
            )
        )
    return labels


def plot_profiles(rows: list, directory: Path, cells: int, angles: list) -> None:
    """Plot magnitude on reconstructed zero surfaces, not a magnitude error."""
    figure, axes = plt.subplots(
        3,
        len(angles),
        figsize=(6 * len(angles), 8.5),
        sharex=True,
        sharey=True,
        squeeze=False,
        layout="constrained",
    )
    for i, name in enumerate(NAMES):
        for j, angle in enumerate(angles):
            ax = axes[i, j]
            for method in METHODS:
                row = next(
                    r
                    for r in rows
                    if r["geometry"] == name
                    and r["cells"] == cells
                    and r["angle"] == angle
                    and r["method"] == method
                )
                with np.load(directory / row["samples"]) as samples:
                    q = samples["magnitude"]
                    if q.size != 17 * 13:
                        raise ValueError("Surface profile requires complete withheld coverage")
                    q = q.reshape(17, 13)
                x = np.linspace(-0.36, 0.36, 17)
                ax.fill_between(x, q.min(axis=1), q.max(axis=1), color=COLOURS[method], alpha=0.12)
                ax.plot(x, q.mean(axis=1), color=COLOURS[method], lw=2.2, label=LABELS[method])
            ax.axhline(1, color="#222222", ls="--", lw=1, zorder=1)
            ax.axvline(-0.29, color="#555555", ls=":", lw=0.8, alpha=0.6)
            ax.set(title=f"{TITLES[name]} | {angle:g} degrees", ylim=(0, 1.15))
            ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
            ax.grid(alpha=0.2)
            if j == 0:
                ax.set_ylabel(r"Gradient magnitude $\|\nabla f\|$")
            if i == 2:
                ax.set_xlabel("Local surface x coordinate")
    handles = [Line2D([], [], color=COLOURS[m], lw=2.2, label=LABELS[m]) for m in METHODS]
    handles.append(Line2D([], [], color="#222222", ls="--", label="Distance-field reference = 1"))
    figure.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False, fontsize=9)
    figure.suptitle(
        "Gradient magnitude on the reconstructed zero surface\n"
        f"{cells} cells per axis | lambda = 0.001 | epsilon = 0.03 x anchor magnitude\n"
        "Lines: mean across y; shading: full range across y. Dotted line: anchor x coordinate.",
        fontsize=12,
    )
    save_figure(figure, directory, f"gradient_magnitude_surface_profiles_n{cells}")


def main() -> None:
    """Create profiles and spatial magnitude maps for both grids and angles."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument(
        "--extra-isosurfaces",
        action="store_true",
        help="Overlay five fixed nonzero isosurfaces in addition to the zero surface",
    )
    args = parser.parse_args()
    directory = args.directory
    config = json.loads((directory / "config.json").read_text())
    rows = [
        r
        for r in json.loads((directory / "metrics.json").read_text())
        if r["strength"] == 0.001 and r["start"] == "native" and r["epsilon_ratio"] in (None, 0.03)
    ]
    angles = sorted({r["angle"] for r in rows})
    cells_list = sorted({r["cells"] for r in rows})
    x = np.linspace(-0.6 + 1e-8, 0.6 - 1e-8, 241)
    z = np.linspace(-0.32 + 1e-8, 0.32 - 1e-8, 161)
    xx, zz = np.meshgrid(x, z)
    # Geometry rotates about y, so y=-0.19 passes through every exact anchor.
    query = np.column_stack([xx.ravel(), np.full(xx.size, -0.19), zz.ravel()])
    fields = {}
    global_max = 1.0
    for cells in cells_list:
        if not args.extra_isosurfaces:
            plot_profiles(rows, directory, cells, angles)
        for angle in angles:
            for name in NAMES:
                problem, _, _, _, _ = make_problem(name, cells, angle, config["seed"])
                for method in METHODS:
                    row = next(
                        r
                        for r in rows
                        if r["geometry"] == name
                        and r["cells"] == cells
                        and r["angle"] == angle
                        and r["method"] == method
                    )
                    with np.load(directory / row["samples"]) as samples:
                        values = samples["values"]
                    gradients = problem.grid.evaluate_gradient(query, values)
                    magnitude = np.linalg.norm(gradients, axis=1).reshape(xx.shape)
                    scalar = problem.grid.evaluate_value(query, values).reshape(xx.shape)
                    anchor_q = np.linalg.norm(
                        problem.grid.evaluate_gradient(problem.anchor_point, values)[0]
                    )
                    np.testing.assert_allclose(anchor_q, 1, atol=1e-12)
                    if name == "plane":
                        np.testing.assert_allclose(magnitude, 1, atol=1e-8)
                    if not np.all(np.isfinite(magnitude)):
                        raise ValueError("Non-finite gradients in a plotted section")
                    fields[cells, angle, name, method] = magnitude, scalar, problem.anchor_point[0]
                    global_max = max(global_max, float(magnitude.max()))
    # Keep equal colour distances below and above the unit reference. The
    # saved fields are all below 1.2, so [0, 2] shows them without clipping.
    upper = max(2.0, np.ceil(global_max * 10) / 10)
    colour_norm = TwoSlopeNorm(vmin=0, vcenter=1, vmax=upper)
    for cells in cells_list:
        for angle in angles:
            figure, axes = plt.subplots(
                3, 3, figsize=(12.5, 8), sharex=True, sharey=True, layout="constrained"
            )
            for i, name in enumerate(NAMES):
                for j, method in enumerate(METHODS):
                    magnitude, scalar, anchor = fields[cells, angle, name, method]
                    ax = axes[i, j]
                    display = ax.pcolormesh(
                        xx,
                        zz,
                        magnitude,
                        cmap="coolwarm",
                        norm=colour_norm,
                        shading="nearest",
                        rasterized=True,
                    )
                    zero = ax.contour(xx, zz, scalar, levels=[0], colors="black", linewidths=1.5)
                    if args.extra_isosurfaces:
                        levels = [-0.10, -0.05, 0.05, 0.10, 0.15]
                        if scalar.min() >= levels[0] or scalar.max() <= levels[-1]:
                            raise ValueError(
                                f"Some shared isosurfaces lie outside the {name}/{method} slice"
                            )
                        contours = ax.contour(
                            xx,
                            zz,
                            scalar,
                            levels=levels,
                            colors="#222222",
                            linewidths=0.85,
                            linestyles=["--", "--", "-", "-", "-"],
                        )
                        labels = label_contours(ax, contours)
                        for label in labels:
                            label.set_bbox(
                                dict(facecolor="white", edgecolor="none", alpha=0.75, pad=0.5)
                            )
                        label_contours(ax, zero)
                    ax.plot(
                        anchor[0],
                        anchor[2],
                        marker="*",
                        ms=10,
                        color="#f2c811",
                        markeredgecolor="black",
                        markeredgewidth=0.6,
                    )
                    ax.set_aspect("equal")
                    if i == 0:
                        ax.set_title(LABELS[method], fontsize=11)
                    if j == 0:
                        ax.set_ylabel(f"{TITLES[name]}\nz")
                    if i == 2:
                        ax.set_xlabel("x")
            colourbar = figure.colorbar(display, ax=axes, shrink=0.8, pad=0.02, aspect=30)
            colourbar.set_label(r"Gradient magnitude $\|\nabla f\|$ (neutral = 1)")
            colourbar.set_ticks(np.linspace(0, upper, 9))
            if args.extra_isosurfaces:
                title = (
                    f"Zero surface plus five extra isosurfaces | {cells} cells | {angle:g} degrees | y = -0.19\n"
                    "Identical scalar levels in every panel: -0.10, -0.05, 0, +0.05, +0.10, +0.15\n"
                    "Thick: zero | dashed: negative | thin solid: positive | star: exact gradient anchor | colour: gradient magnitude"
                )
                suffix = "_isosurfaces"
            else:
                title = (
                    f"Gradient magnitude in a slice through the exact anchor | {cells} cells | {angle:g} degrees\n"
                    "lambda = 0.001, epsilon = 0.03 x anchor magnitude | black: reconstructed zero surface | star: anchor\n"
                    "Same colour scale for every panel and every resolution/orientation; blue < 1, red > 1."
                )
                suffix = ""
            figure.suptitle(title, fontsize=11)
            save_figure(
                figure, directory, f"gradient_magnitude_sections_n{cells}_a{angle:g}{suffix}"
            )
    print(
        f"Saved section figures. Shared colour range: 0 to {upper:g}. Lambda=0.001, epsilon ratio=0.03."
    )


if __name__ == "__main__":
    main()
