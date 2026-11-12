"""Draw a vertical cross-section of generated cases.

    python scripts/plot_sections.py outputs [--y 0.5] [--axis y]

Writes ``<case>/section_<axis>.png`` for every case folder with a
metadata.json, and ``sections.png`` with all cases in one figure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402

AXES = {"y": (1, (0, 2), "x", "z"), "x": (0, (1, 2), "y", "z")}


def draw(ax, case_dir: Path, axis: str, value: float) -> None:
    meta = json.loads((case_dir / "metadata.json").read_text())
    a, (i, j), xl, yl = AXES[axis]
    normal = np.zeros(3)
    normal[a] = 1
    origin = np.full(3, 0.5)
    origin[a] = value
    vol = pv.read(case_dir / meta["files"]["volume_vtu"])
    sl = vol.slice(normal=normal, origin=origin)
    if "unit" in sl.point_data and sl.n_points:
        p = np.asarray(sl.points)
        ax.tricontourf(p[:, i], p[:, j], np.asarray(sl.point_data["unit"]), levels=30,
                       cmap="Pastel1", alpha=0.6)
    for s in meta["surfaces"]:
        mesh = pv.read(case_dir / "surfaces" / s["files"]["vtp"])
        cut = mesh.slice(normal=normal, origin=origin)
        if cut.n_points == 0:
            continue
        lines = cut.lines.reshape(-1, 3)[:, 1:]
        pts = np.asarray(cut.points)
        style = dict(color="k", lw=1.6) if s["kind"] == "fault" else dict(color="C0", lw=0.9)
        for e in lines:
            ax.plot(pts[e, i], pts[e, j], **style)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.set_title(meta["case"], fontsize=8)
    ax.set_xlabel(xl, fontsize=7)
    ax.set_ylabel(yl, fontsize=7)
    ax.tick_params(labelsize=6)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--axis", default="y", choices=list(AXES))
    ap.add_argument("--value", type=float, default=0.5)
    args = ap.parse_args()
    root = Path(args.out)
    cases = sorted(p.parent for p in root.glob("*/metadata.json"))
    n = len(cases)
    cols = min(4, n)
    rows = int(np.ceil(n / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.2 * rows), squeeze=False)
    for k, c in enumerate(cases):
        draw(axs.flat[k], c, args.axis, args.value)
        f1, a1 = plt.subplots(figsize=(5, 5))
        draw(a1, c, args.axis, args.value)
        f1.savefig(c / f"section_{args.axis}.png", dpi=130, bbox_inches="tight")
        plt.close(f1)
    for ax in axs.flat[n:]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(root / "sections.png", dpi=110)
    print(f"wrote {root / 'sections.png'}")


if __name__ == "__main__":
    main()
