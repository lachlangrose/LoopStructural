"""Assemble the shareable benchmark folder: one self-contained folder per model.

    <dest>/<case>/
        README.md                 what the model is and what each file holds
        build_model.py            standalone LoopStructural code that builds the model
        data/                     the observations given to LoopStructural + check values
        support/                  the interpolation support of each implicit field (.vti)
        surfaces/                 reference fault and horizon surfaces (.vtp, .obj)
        constraints/              sharp-feature curves (.vtp)
        fields/                   the evaluated implicit model on a regular grid (.vtu)
        metadata.json, section_y.png
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .builder import build_case
from .cases import get_case
from .standalone import render

N_CHECK = 400


def _check_points(built, seed: int) -> pd.DataFrame:
    pts = np.random.default_rng(seed).uniform(0.0, 1.0, size=(N_CHECK, 3))
    out = pd.DataFrame(pts, columns=["X", "Y", "Z"])
    for name, feat in built.series.items():
        out[f"series:{name}"] = feat.evaluate_value(pts, ignore_regions=True)
    dist = np.full(len(pts), np.inf)
    for name, fault in built.faults.items():
        gx = fault[0].evaluate_value(pts, ignore_regions=True)
        out[f"fault:{name}"] = gx
        # gx = distance / (minor_axis / 2) near the fault (see spec.FaultSpec)
        d = np.abs(gx) * built.spec.fault(name).minor_axis / 2.0
        dist = np.minimum(dist, np.nan_to_num(d, nan=np.inf))
    out.insert(3, "fault_distance", dist)
    return out


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _readme(meta: dict, support: dict, check_log: str) -> str:
    faults = "\n".join(
        f"| `{f['name']}` | {f['profile']} | {f['displacement']} | "
        f"{', '.join(f['faulted_by']) or '-'} | "
        f"{(f['abuts']['fault'] + (' (+)' if f['abuts']['side'] > 0 else ' (-)')) if f['abuts'] else '-'} |"
        for f in meta["faults"]
    )
    series = "\n".join(
        f"| `{s['name']}` | `{s['restored_field']}` | {s['isovalues']} | "
        f"{', '.join(s['faults']) or '-'} | {s['unconformity_value']} |"
        for s in meta["series"]
    )
    surfaces = "\n".join(
        f"| `surfaces/{s['id']}.vtp` | {s['kind']} | {s['owner']} | "
        f"{'' if s['isovalue'] is None else s['isovalue']} | {s['connected_pieces']} | "
        f"{s['quality']['n_triangles']} | "
        + ", ".join(f"{k} {v:.3f}" for k, v in sorted(s["boundary_length_by_tag"].items())
                    if not k.startswith("domain"))
        + " |"
        for s in meta["surfaces"]
    )
    sup = "\n".join(
        f"| `support/{v['file']}` | {v['interpolator']} | "
        f"{'x'.join(str(n) for n in v['nodes_per_axis'])} | "
        f"{v['step_vector'][0]:.4f} | {v['coordinates']} |"
        for v in support.values()
    )
    return f"""# {meta['case']}

{meta['description']}

Category: **{meta['category']}**. Tags: {', '.join(meta['tags']) or '-'}.

![Section at y = 0.5](section_y.png)

## Rebuild the model

```sh
python build_model.py                          # build and check against data/check_points.csv
python build_model.py --export-support support # also write the support grids
```

`build_model.py` holds every LoopStructural call with its parameters. Result of
the check when this folder was made:

```
{check_log.strip()}
```

## Model

| Fault | Profile | Displacement | Displaced by | Abuts |
| --- | --- | --- | --- | --- |
{faults}

| Series (youngest first) | Restored field | Isovalues | Faults | Unconformity value |
| --- | --- | --- | --- | --- |
{series}

## Files

| Path | Content |
| --- | --- |
| `build_model.py` | Standalone code that builds this LoopStructural model. |
| `data/fault_observations.csv` | Fault points and normals given to LoopStructural (val 0, coord 0). |
| `data/series_observations.csv` | Stratigraphic value points given to LoopStructural. |
| `data/check_points.csv` | Random points with the expected field values (used by the check). |
| `support/*.vti`, `support/support.json` | Interpolation support of each implicit field: regular grid, solved node values. |
| `fields/implicit_fields.vtu` | The evaluated model on a 49^3 grid: fields, gradients, block fields, fault frames, displacements. |
| `surfaces/*.vtp`, `*.obj` | Reference surfaces, one file per fault or horizon (cell data `block`). |
| `constraints/constraint_curves.vtp` | Sharp-feature curves; ids match `metadata.json` `constraints`. |
| `metadata.json` | Full machine-readable description (faults, blocks, curves, QA). |

### Support grids

The node values are in **restored** coordinates for a feature that faults
displace: the value at a present-day point is the support value at that point
restored through the feature's faults.

| File | Interpolator | Nodes | Step | Coordinates |
| --- | --- | --- | --- | --- |
{sup}

### Surfaces

`pieces` is the number of connected pieces. Boundary lengths by tag:
`cutoff` (horizon on an active fault, sharp), `seam` (no offset), `junction`
(fault on fault), `tip` (fault tip line), `unconformity`.

| File | Kind | Owner | Isovalue | Pieces | Triangles | Boundary |
| --- | --- | --- | --- | --- | --- | --- |
{surfaces}
"""


def make_case_folder(case: str, outputs: Path, dest: Path, python: str = sys.executable) -> dict:
    t0 = time.perf_counter()
    src = outputs / case
    meta = json.loads((src / "metadata.json").read_text())
    folder = dest / case
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "data").mkdir(parents=True)

    built = build_case(get_case(case))
    fault_obs = pd.concat([built.fault_data[c["name"]] for c in built.calls if c["call"] == "fault"])
    fault_obs.to_csv(folder / "data" / "fault_observations.csv", index=False)
    series_obs = pd.concat([built.contact_data[c["name"]] for c in built.calls
                            if c["call"] == "series"])
    series_obs[["X", "Y", "Z", "val", "feature_name"]].to_csv(
        folder / "data" / "series_observations.csv", index=False)
    _check_points(built, built.spec.seed).to_csv(folder / "data" / "check_points.csv", index=False)
    (folder / "build_model.py").write_text(render(case, built.spec.description, built.calls))

    for s in meta["surfaces"]:
        for fmt in ("vtp", "obj"):
            if fmt in s["files"]:
                _copy(src / "surfaces" / s["files"][fmt], folder / "surfaces" / s["files"][fmt])
    _copy(src / "constraints" / "constraint_curves.vtp",
          folder / "constraints" / "constraint_curves.vtp")
    _copy(src / "volume" / "implicit_fields.vtu", folder / "fields" / "implicit_fields.vtu")
    _copy(src / "metadata.json", folder / "metadata.json")
    if (src / "section_y.png").exists():
        _copy(src / "section_y.png", folder / "section_y.png")

    # Run the standalone script: it exports the support and checks the model.
    run = subprocess.run([python, "build_model.py", "--export-support", "support"],
                         cwd=folder, capture_output=True, text=True)
    log = "\n".join(line for line in run.stdout.splitlines()
                    if line.startswith(("  ", "check", "wrote")))
    if run.returncode != 0:
        raise RuntimeError(f"build_model.py failed for {case}:\n{run.stdout}\n{run.stderr[-3000:]}")
    support = json.loads((folder / "support" / "support.json").read_text())
    (folder / "README.md").write_text(_readme(meta, support, log))
    return {"case": case, "category": meta["category"], "seconds": time.perf_counter() - t0,
            "check": log.splitlines()[-1] if log else "", "description": meta["description"]}


def write_index(dest: Path, rows: list[dict]) -> None:
    lines = ["# Fault meshing benchmark models", "",
             "One folder per model. Each folder is self-contained: `build_model.py` rebuilds",
             "the LoopStructural model from `data/`, `support/` holds the implicit fields on",
             "their interpolation grids, and `surfaces/` the reference fault and horizon",
             "surfaces. See each folder's README.md.", "",
             "Generator, method and conventions: `../README.md`.", "",
             "| Model | Category | Description |", "| --- | --- | --- |"]
    for r in rows:
        lines.append(f"| [{r['case']}]({r['case']}/README.md) | {r['category']} | "
                     f"{r['description']} |")
    (dest / "README.md").write_text("\n".join(lines) + "\n")
