"""Run inclined, terminating or crossing two-fault experiments with MMG3D."""

import argparse
import json
import platform
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pyvista
import scipy

from fault_mmg.geometry import HORIZONS
from fault_mmg.mesh import cube, write_mesh
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset
from fault_mmg.two_fault_visualization import export_two_faults, export_volume
from fault_mmg.two_faults import TwoFaultModel, scalar_prepass_diagnostic, validate_two_faults
from fault_mmg.validation import validate, validate_topology


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + "\n")


def summary(report):
    lines = [
        f"# Two faults: {report['case']}",
        "",
        f"Outcome: **{report['outcome']}**.",
        "",
        "Primary fault: x=0. Secondary: y-0.35z-0.1=0.",
        (
            "The secondary exists only at x>=0."
            if report["case"] == "terminating"
            else "The secondary spans both sides of x=0."
        ),
        "Restored stratigraphy in each block: f=z-0.2x+0.1y-displacement.",
        "",
    ]
    if "final" in report:
        v = report["final"]
        m = v["metrics"]
        lines += [
            f"{m['vertices']} vertices; {m['tetrahedra']} positive tetrahedra; volume {m['total_volume']:.16g}.",
            f"Validation: {sum(v['checks'].values())}/{len(v['checks'])} passed.",
            f"{m['fault_blocks']} fault blocks; {m['geological_regions']} geological regions.",
            f"Hanging-node incidences: {m['hanging_vertices']['incidences']}.",
            "",
            f"Minimum normalized MMG quality: {m['quality']['minimum_normalized']:.6g} (regular tetrahedron = 1).",
            "",
            f"Junction: {m['junction']['length']:.12g} long, {m['junction']['edges']} shared mesh edges; fault-sheet incidence {m['junction']['observed_sheet_incidence']}.",
            "",
            "| Fault | Triangles | Mesh area | Analytic area |",
            "| --- | --- | --- | --- |",
        ]
        for f in m["faults"]:
            lines.append(
                f"| {f['fault']} | {f['triangles']} | {f['area']:.12g} | {f['expected_area']:.12g} |"
            )
        lines += [
            "",
            "| Block | Horizon | Triangles | Mesh area | Analytic clipped area |",
            "| --- | --- | --- | --- | --- |",
        ]
        for h in m["horizons"]:
            lines.append(
                f"| {h['block']} | {h['horizon']:g} | {h['triangles']} | {h['area']:.12g} | {h['expected_area']:.12g} |"
            )
        lines += [
            "",
            "Tolerance: geometry 1e-8; volume 1e-8; areas and lengths 1e-7; tet volume >1e-14.",
            "Every fault and previously inserted horizon is checked after each cut.",
            "",
        ]
    if "error" in report:
        lines += ["Error: " + report["error"], ""]
        if report["stages"]:
            last = report["stages"][-1]
            lines += [
                "Failed checks: "
                + ", ".join(k for k, passed in last["checks"].items() if not passed),
                "",
                "Input quality diagnostic: `"
                + json.dumps(last.get("input_quality_diagnostic", {}))
                + "`.",
                "",
            ]
    return "\n".join(lines)


def run_case(args, case):
    out = args.output / case
    if (out / "report.json").exists():
        raise FileExistsError(f"Choose a fresh output directory: {out} already contains a report")
    out.mkdir(parents=True, exist_ok=True)
    model = TwoFaultModel(case)
    report = {
        "case": case,
        "outcome": "running",
        "cells_per_axis": args.cells,
        "block_displacements": model.offsets,
        "mmg_executable": args.mmg,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pyvista": pyvista.__version__,
        },
        "stages": [],
        "full_hanging_node_scan": args.full_scan,
    }
    provenance = ROOT / ".mmg-runtime/provenance.json"
    if provenance.exists():
        report["mmg_package"] = json.loads(provenance.read_text())

    def checkpoint():
        save(out / "report.json", report)
        (out / "results.md").write_text(summary(report))

    try:
        current = cube(args.cells)
        write_mesh(out / "initial.mesh", current)
        report["initial"] = validate_topology(current, full_scan=args.full_scan)
        export_volume(current, model, out / "initial_mesh.vtu")
        print(f"{case}: primary fault", flush=True)
        current, invocation = run_levelset(
            current, current.points[:, 0], out / "01_primary_fault", {1: (11, 12)}, args.mmg
        )
        first = validate(current, horizons=[], full_scan=args.full_scan)
        first["invocation"] = invocation
        report["primary_fault"] = first
        if not first["passed"]:
            raise RuntimeError("Primary fault validation failed")
        retag_interfaces(current, 100)
        print(f"{case}: secondary fault", flush=True)
        if case == "terminating":
            mapping = {11: None, 12: (21, 22)}
            lineage = {11: (1, 0), 21: (2, 0), 22: (3, 0)}
        else:
            mapping = {11: (21, 22), 12: (23, 24)}
            lineage = {21: (1, 0), 22: (2, 0), 23: (3, 0), 24: (4, 0)}
        current, invocation = run_levelset(
            current, model.secondary(current.points), out / "02_secondary_fault", mapping, args.mmg
        )
        v = validate_two_faults(current, model, lineage=lineage, full_scan=args.full_scan)
        v["invocation"] = invocation
        save(out / "02_secondary_fault/validation.json", v)
        report["two_faults"] = v
        export_volume(current, model, out / "faults_inserted.vtu")
        if not v["passed"]:
            raise RuntimeError(
                "Junction validation failed: " + str([k for k, p in v["checks"].items() if not p])
            )
        completed = []
        next_ref = 1001
        for unit, h in enumerate(HORIZONS):
            for block in model.blocks:
                step = len(completed) + 3
                print(f"{case}: horizon {h:g}, block {block}", flush=True)
                retag_interfaces(current, 100 + step)
                mapping = {int(ref): None for ref in np.unique(current.refs)}
                parents = [
                    ref
                    for ref, state in lineage.items()
                    if state == (block, unit) and ref in mapping
                ]
                if len(parents) != 1:
                    raise RuntimeError(f"Ambiguous active block material {parents}")
                parent = parents[0]
                pair = (next_ref, next_ref + 1)
                next_ref += 2
                mapping[parent] = pair
                lineage.pop(parent)
                lineage[pair[0]] = (block, unit)
                lineage[pair[1]] = (block, unit + 1)
                directory = out / f"{step:02d}_block{block}_horizon{h:g}"
                values = model.restored(current.points, block) - h
                diagnostic = scalar_prepass_diagnostic(current, values)
                current, invocation = run_levelset(current, values, directory, mapping, args.mmg)
                completed.append((block, float(h)))
                v = validate_two_faults(
                    current, model, horizons=completed, lineage=lineage, full_scan=args.full_scan
                )
                v["invocation"] = invocation
                v["target"] = {"block": block, "horizon": float(h)}
                v["input_quality_diagnostic"] = diagnostic
                save(directory / "validation.json", v)
                export_volume(current, model, directory / "volume.vtu")
                report["stages"].append(v)
                report["material_lineage"] = lineage.copy()
                checkpoint()
                if not v["passed"]:
                    raise RuntimeError(
                        f"Stage {step} validation failed: "
                        + str([k for k, p in v["checks"].items() if not p])
                    )
        report["final"] = v
        write_mesh(out / "final.mesh", current)
        export_two_faults(current, model, out, pictures=args.pictures)
        report["outcome"] = (
            "full_success" if args.full_scan else "geometry_and_adjacency_passed_scan_omitted"
        )
        print(f"{case}: {report['outcome']}; {len(current.tets)} tetrahedra", flush=True)
    except Exception as error:
        report["outcome"] = "failed"
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        checkpoint()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["terminating", "crossing", "both"], default="both")
    parser.add_argument("--cells", type=int, default=11)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/two_faults")
    parser.add_argument("--mmg")
    parser.add_argument("--no-pictures", dest="pictures", action="store_false")
    parser.add_argument("--no-full-scan", dest="full_scan", action="store_false")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.mmg = find_mmg(args.mmg)
    for case in (["terminating", "crossing"] if args.case == "both" else [args.case]):
        run_case(args, case)


if __name__ == "__main__":
    main()
