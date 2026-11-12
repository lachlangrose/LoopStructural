"""Write a standalone ``build_model.py`` for one benchmark case.

The script makes the same LoopStructural calls as the generator, written out
with literal parameters, and reads the same observations from ``data/``. It
needs only LoopStructural, numpy and pandas (and pyvista for the support
export).
"""

from __future__ import annotations

import textwrap

HEADER = '''"""Build the LoopStructural model of benchmark case "{name}".

{description}

This script needs only LoopStructural, numpy and pandas (pyvista for
--export-support). It reads the observations in data/ and makes the same
LoopStructural calls as the benchmark generator (fault_mesh_benchmarks).

    python build_model.py                         # build, then check against data/check_points.csv
    python build_model.py --export-support support

Coordinates: unit cube [0, 1]^3, z up. A fault normal points into the hanging
wall; ``fault_slip_vector`` is the restoration direction (LoopStructural
convention), the opposite of the geological hanging-wall movement.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def fault_function(profile):
    """Displacement profile of a fault (see the benchmark README)."""
    from LoopStructural.modelling.features.fault._fault_function import (
        BaseFault,
        Composite,
        FaultDisplacement,
        Ones,
        Zeros,
        smooth_peak,
    )

    if profile == "constant":  # hanging wall moves rigidly, footwall fixed
        return FaultDisplacement(gx=Composite(Ones(), Zeros()), gy=Ones(), gz=Ones(), scale=1.0)
    if profile == "tip":  # hanging wall only, decays away from the fault, tip loop
        return FaultDisplacement(
            gx=Composite(BaseFault.hw, Zeros()), gy=smooth_peak, gz=smooth_peak, scale=1.0
        )
    if profile == "base":
        return "BaseFault"
    if profile == "base3d":
        return "BaseFault3D"
    raise ValueError(profile)


@contextmanager
def frame_faults_disabled(fault):
    frame = [fault[i] for i in range(3)]
    previous = [f.faults_enabled for f in frame]
    try:
        for f in frame:
            f.faults_enabled = False
        yield
    finally:
        for f, p in zip(frame, previous):
            f.faults_enabled = p


def restore_once(fault):
    """Apply a displaced fault once to points already restored through its parents.

    Without this, LoopStructural restores a series point through the younger
    fault and then again inside the older fault's frame (double restoration).
    """

    def apply_to_points(points, reverse=False, precomputed_gx=None, _f=fault):
        with frame_faults_disabled(_f):
            return type(_f).apply_to_points(_f, points, reverse=reverse)

    fault.apply_to_points = apply_to_points


def use_restored_slip_direction(fault):
    """Slip direction of a displaced fault: frame gradient at the restored point (fast)."""
    feat = fault[1]

    def gradient(pos, ignore_regions=False, element_scale_parameter=None, _f=feat):
        if _f.builder is not None:
            _f.builder.up_to_date()
        return _f.interpolator.evaluate_gradient(_f._apply_faults(np.asarray(pos, dtype=float)))

    feat.evaluate_gradient = gradient


def observations(table, name):
    return table[table["feature_name"] == name].reset_index(drop=True)


def build_model():
    """Return (model, faults, series) with LoopStructural features by name."""
    from LoopStructural import GeologicalModel

    fault_obs = pd.read_csv(HERE / "data" / "fault_observations.csv")
    series_obs = pd.read_csv(HERE / "data" / "series_observations.csv")
    model = GeologicalModel(np.zeros(3), np.ones(3))
    faults = {{}}
    series = {{}}
'''

FOOTER = '''
    return model, faults, series


def export_support(faults, series, out_dir):
    """Write the interpolation support of every interpolated feature.

    One .vti per feature: a regular grid with the solved node values. Node
    values are in RESTORED coordinates: the value at a present-day point p is
    the support value at the point restored through the feature's faults.
    """
    import pyvista as pv

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    feats = {{name: f for name, f in series.items()}}
    for name, fault in faults.items():
        for i, coord in enumerate(("gx", "gy", "gz")):
            feats[f"{{name}}_{{coord}}"] = fault[i]
    index = {{}}
    for name, feat in feats.items():
        feat.builder.up_to_date()
        sup = feat.interpolator.support
        grid = pv.ImageData(dimensions=tuple(int(n) for n in sup.nsteps),
                            spacing=tuple(float(s) for s in sup.step_vector),
                            origin=tuple(float(o) for o in sup.origin))
        if not np.allclose(np.asarray(grid.points), np.asarray(sup.nodes)):
            raise RuntimeError(f"support node order of {{name}} is not x-fastest")
        grid.point_data["value"] = np.asarray(feat.interpolator.c, dtype=float)
        grid.save(out / f"{{name}}.vti")
        index[name] = {{
            "file": f"{{name}}.vti",
            "interpolator": type(feat.interpolator).__name__,
            "origin": np.asarray(sup.origin).tolist(),
            "step_vector": np.asarray(sup.step_vector).tolist(),
            "nodes_per_axis": np.asarray(sup.nsteps).tolist(),
            "rotation_xy": np.asarray(sup.rotation_xy).tolist(),
            "faults": [f.name for f in feat.faults],
            "coordinates": "restored" if feat.faults else "present-day",
        }}
    (out / "support.json").write_text(json.dumps(index, indent=1))
    print(f"wrote {{len(index)}} support grids to {{out}}")


def check(faults, series, tol=1e-4, tol_near=1e-3, near=0.02):
    """Compare with the values the benchmark generator saved.

    Within ``near`` of a fault the field is steep and round-off from the
    iterative solver grows through the fault integration, so a looser
    tolerance applies there.
    """
    table = pd.read_csv(HERE / "data" / "check_points.csv")
    pts = table[["X", "Y", "Z"]].to_numpy()
    is_near = table["fault_distance"].to_numpy() < near
    ok = True
    for col in table.columns[4:]:
        kind, name = col.split(":", 1)
        if kind == "series":
            v = series[name].evaluate_value(pts, ignore_regions=True)
        else:
            v = faults[name][0].evaluate_value(pts, ignore_regions=True)
        diff = np.abs(v - table[col].to_numpy())
        far_max = float(np.nanmax(diff[~is_near])) if (~is_near).any() else 0.0
        near_max = float(np.nanmax(diff[is_near])) if is_near.any() else 0.0
        ok &= far_max <= tol and near_max <= tol_near
        print(f"  {{col:28s}} max |difference| = {{far_max:.2e}} (>= {{near}} from faults), "
              f"{{near_max:.2e}} (near)")
    print("check", "PASSED" if ok else "FAILED",
          f"(tolerance {{tol}}; {{tol_near}} within {{near}} of a fault)")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export-support", metavar="DIR")
    ap.add_argument("--no-check", action="store_true")
    args = ap.parse_args()
    model, faults, series = build_model()
    if args.export_support:
        export_support(faults, series, args.export_support)
    if not args.no_check and not check(faults, series):
        raise SystemExit(1)
'''


def _vec(v) -> str:
    return "[" + ", ".join(repr(float(x)) for x in v) + "]"


def _fault_block(c: dict) -> str:
    name = c["name"]
    parents = ", ".join(f'faults["{n}"]' for n in c["faults"])
    lines = [
        f'# Fault "{name}": profile {c["profile"]}'
        + (f', displaced by {", ".join(c["faults"])}' if c["faults"] else ""),
        f'faults["{name}"] = model.create_and_add_fault(',
        f'    "{name}",',
        f'    {c["displacement"]!r},',
        f'    data=observations(fault_obs, "{name}"),',
        f'    fault_slip_vector={_vec(c["fault_slip_vector"])},',
        f'    fault_normal_vector={_vec(c["fault_normal_vector"])},',
        f'    fault_center={_vec(c["fault_center"])},',
        f'    major_axis={c["major_axis"]!r},',
        f'    intermediate_axis={c["intermediate_axis"]!r},',
        f'    minor_axis={c["minor_axis"]!r},',
        f'    faultfunction=fault_function("{c["profile"]}"),',
        f"    faults=[{parents}],",
        f'    nelements={c["nelements"]!r},',
        f'    fault_buffer={c["fault_buffer"]!r},',
        ")",
        f'faults["{name}"].steps = {c["steps"]!r}  # integration steps',
    ]
    if c["faults"]:
        lines += [
            f'use_restored_slip_direction(faults["{name}"])',
            f'restore_once(faults["{name}"])',
        ]
    if c["abuts"]:
        other, side = c["abuts"]
        lines.append(
            f'faults["{name}"].add_abutting_fault(faults["{other}"], positive={side > 0})'
            f"  # exists only on the {'hanging-wall' if side > 0 else 'footwall'} side"
        )
    return "\n".join(lines)


def _series_block(c: dict) -> str:
    name = c["name"]
    flist = ", ".join(f'faults["{n}"]' for n in c["faults"])
    lines = [
        f'# Series "{name}" (faults listed oldest first; restored youngest first)',
        f'series["{name}"] = model.create_and_add_foliation(',
        f'    "{name}",',
        f'    data=observations(series_obs, "{name}"),',
        f"    faults=[{flist}],",
        f'    nelements={c["nelements"]!r},',
        f'    buffer={c["buffer"]!r},',
        ")",
    ]
    if c["unconformity"] is not None:
        lines.append(
            f'model.add_unconformity(series["{name}"], {c["unconformity"]!r})'
            "  # older series exist only below this value"
        )
    return "\n".join(lines)


def render(name: str, description: str, calls: list[dict]) -> str:
    desc = "\n".join(textwrap.wrap(description, 76))
    body = [HEADER.format(name=name, description=desc)]
    for c in calls:
        block = _fault_block(c) if c["call"] == "fault" else _series_block(c)
        body.append(textwrap.indent(block, "    ") + "\n")
    return "\n".join(body).rstrip() + "\n" + FOOTER.format()
