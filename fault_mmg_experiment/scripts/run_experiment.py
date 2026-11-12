"""Run from any directory; all MMG inputs and failures remain in outputs/."""

import argparse
import copy
import json
import platform
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from fault_mmg.geometry import HORIZONS, horizon_height, stratigraphy
from fault_mmg.interfaces import geological_interfaces, interface_signature
from fault_mmg.mesh import cube, extract_block, write_mesh
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset
from fault_mmg.validation import validate
from fault_mmg.visualization import export


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def progress(message):
    print(message, flush=True)


def global_pipeline(args, report):
    out = args.output
    initial = cube(args.cells)
    write_mesh(out / "initial.mesh", initial)
    report["initial"] = validate(
        initial, require_fault=False, horizons=[], full_scan=args.full_scan
    )
    # Explicitly establish that the input is not fault-conforming.
    x = initial.points[initial.tets, 0]
    report["initial"]["fault_crossing_tets"] = int(
        ((x.min(axis=1) < 0) & (x.max(axis=1) > 0)).sum()
    )
    export(initial, out / "initial_mesh", pictures=args.pictures)
    progress(f"Initial mesh: {len(initial.tets)} tets; inserting fault")
    fault, invocation = run_levelset(
        initial, initial.points[:, 0], out / "01_fault", {1: (11, 12)}, args.mmg
    )
    report["fault"] = validate(fault, horizons=[], full_scan=args.full_scan)
    report["fault"]["invocation"] = invocation
    export(fault, out / "fault_inserted", pictures=args.pictures)
    save_json(out / "fault_validation.json", report["fault"])
    if not report["fault"]["passed"]:
        raise RuntimeError("Fault validation failed; see fault_validation.json")
    current = copy.deepcopy(fault)
    # Map reference -> exact block and unit index. Only split the current upper
    # unit in the active block. The other block is nosplit, yet shared cut-edge
    # refinement propagates into its tets to preserve matching fault triangles.
    lineage = {11: (1, 0), 12: (2, 0)}
    completed, stages = [], []
    next_ref = 1001
    for unit, horizon in enumerate(HORIZONS):
        for block in (1, 2):
            stage = len(stages) + 2
            height = horizon_height(block, horizon)
            retag_interfaces(current, 100 + stage - 2)
            mapping = {int(ref): None for ref in np.unique(current.refs)}
            target = [
                ref for ref, info in lineage.items() if info == (block, unit) and ref in mapping
            ]
            if len(target) != 1:
                raise RuntimeError(f"Ambiguous active material: {target}")
            parent = target[0]
            pair = (next_ref, next_ref + 1)
            mapping[parent] = pair
            lineage.pop(parent)
            lineage[pair[0]] = (block, unit)
            lineage[pair[1]] = (block, unit + 1)
            next_ref += 2
            # Auxiliary continuous cutter is z-height, NOT a global assignment
            # of discontinuous f. Its values in nosplit regions are inactive.
            values = stratigraphy(current.points, block) - horizon
            directory = out / f"{stage:02d}_block{block}_horizon{horizon:g}"
            progress(f"Cut block {block}, f={horizon:g}, physical z={height:g}")
            current, invocation = run_levelset(current, values, directory, mapping, args.mmg)
            completed.append((block, float(horizon)))
            validation = validate(
                current, horizons=completed.copy(), full_scan=args.full_scan, lineage=lineage
            )
            validation["invocation"] = invocation
            validation["target"] = {"block": block, "horizon": float(horizon), "height": height}
            validation["lineage"] = lineage.copy()
            save_json(directory / "validation.json", validation)
            export(current, directory / "volume")
            stages.append(validation)
            report["stages"] = stages
            save_json(out / "report.json", report)
            if not validation["passed"]:
                raise RuntimeError(
                    f"Stage {stage} failed validation: "
                    + str([k for k, v in validation["checks"].items() if not v])
                )
    report["final"] = stages[-1]
    report["outcome"] = (
        "full_success" if args.full_scan else "geometry_and_adjacency_passed_scan_omitted"
    )
    report["material_lineage"] = lineage
    write_mesh(out / "final.mesh", current)
    export(current, out / "final_mesh", pictures=args.pictures, final=True)
    return fault


def preservation_probes(args, report):
    """Small reproducible cases; failure of a rejected approach is retained."""
    base = args.output / "probes"
    small = cube(3)
    fault, _ = run_levelset(small, small.points[:, 0], base / "fault", {1: (11, 12)}, args.mmg)
    retag_interfaces(fault, 100)
    fault_info = geological_interfaces(fault)
    original_count = int(fault_info["fault"].sum())
    probes = {"cells": 3, "initial_fault_triangles": original_count}
    for required in (False, True):
        title = "separate_required" if required else "separate_free"
        progress(f"Probe: {title}")
        parts = []
        details = []
        for block in (1, 2):
            part = extract_block(fault, block)
            before = interface_signature(part)
            if required:
                part.required_triangles = np.flatnonzero(part.tri_refs == 100)
            directory = base / title / f"block{block}"
            remeshed, invocation = run_levelset(
                part,
                stratigraphy(part.points, block),
                directory,
                {int(r): (201 + 10 * block, 202 + 10 * block) for r in np.unique(part.refs)},
                args.mmg,
            )
            after = interface_signature(remeshed)
            export(remeshed, directory / "volume")
            details.append(
                {
                    "block": block,
                    "original_fault_triangles": len(before),
                    "new_fault_triangles": len(after),
                    "unchanged": before == after,
                    "invocation": invocation,
                }
            )
            parts.append(remeshed)
        first, second = map(interface_signature, parts)
        probes[title] = {
            "matching_triangulations": first == second,
            "common_triangles": len(first & second),
            "unmatched_A": len(first - second),
            "unmatched_B": len(second - first),
            "reassembled": False,
            "reason": "Reject reassembly when full shared triangle geometry differs",
            "blocks": details,
        }
    progress("Probe: global preserved and remeshing-enabled interface")
    for frozen in (True, False):
        title = "global_frozen" if frozen else "global_adapted"
        try:
            output, invocation = run_levelset(
                copy.deepcopy(fault),
                fault.points[:, 2],
                base / title,
                {11: (301, 302), 12: None},
                args.mmg,
                frozen=frozen,
            )
            result = validate(output, horizons=[(1, 0.0)], full_scan=args.full_scan)
            result["invocation"] = invocation
            result["input_fault_triangles"] = original_count
            d = geological_interfaces(output)
            on_fault = np.unique(d["faces"][d["fault"]])
            result["output_fault_vertex_max_abs_x"] = float(abs(output.points[on_fault, 0]).max())
            export(output, base / title / "volume")
            probes[title] = result
        except Exception as error:
            probes[title] = {"passed": False, "error": str(error)}
    # Demonstrate default material reset rather than assuming old references
    # survive when there is no LSReferences map.
    progress("Probe: default reference reset")
    reset, invocation = run_levelset(
        copy.deepcopy(fault),
        fault.points[:, 2],
        base / "default_reference_reset",
        executable=args.mmg,
    )
    probes["default_reference_reset"] = {
        "input_material_refs": [11, 12],
        "output_material_refs": np.unique(reset.refs).tolist(),
        "original_materials_preserved": bool(np.isin([11, 12], reset.refs).all()),
        "invocation": invocation,
    }
    # Reserved tag reuse can change interface identity even when material
    # boundaries reconstruct the correct fault geometry in this Medit path.
    reused = copy.deepcopy(fault)
    reused.tri_refs[reused.tri_refs == 100] = 10
    output, invocation = run_levelset(
        reused,
        reused.points[:, 2] - 0.4,
        base / "reserved_reference_reuse",
        {11: None, 12: (401, 402)},
        args.mmg,
    )
    on_fault = np.max(abs(output.points[output.triangles, 0]), axis=1) < 1e-8
    probes["reserved_reference_reuse"] = {
        "passed": validate(output, horizons=[(2, 0.0)], full_scan=args.full_scan)["passed"],
        "input_fault_triangle_reference": 10,
        "output_fault_triangle_references": np.unique(output.tri_refs[on_fault]).tolist(),
        "invocation": invocation,
    }
    report["probes"] = probes


def markdown_results(report):
    final = report.get("final", {})
    lines = ["# Executed experiment results", "", f"Outcome: **{report['outcome']}**.", ""]
    if final:
        m = final["metrics"]
        lines += [
            f"Final mesh: {m['vertices']} vertices, {m['tetrahedra']} tetrahedra.",
            f"Volume: {m['total_volume']:.16g}; minimum tet volume: {m['min_volume']:.6g}.",
            f"Validation: {sum(final['checks'].values())}/{len(final['checks'])} checks passed.",
            "",
            "| Block | f | Physical z | Faces | Area | Shared fault-edge length |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for h in m["horizons"]:
            lines.append(
                f"| {h['block']} | {h['horizon']:g} | {h['height']:g} | {h['triangles']} | {h['area']:.12g} | {h['intersection_length']:.12g} |"
            )
        lines += [
            "",
            "Geometry tolerance 1e-8; total volume tolerance 1e-8; area/length tolerance 1e-7; minimum accepted tet volume 1e-14.",
            "The hanging-node scan tests all nonincident vertices against candidate triangle interiors and edges.",
            "",
        ]
    for name, probe in report.get("probes", {}).items():
        if isinstance(probe, dict) and "matching_triangulations" in probe:
            lines.append(
                f"- {name}: matching fault triangles = {probe['matching_triangulations']}; unmatched A/B = {probe['unmatched_A']}/{probe['unmatched_B']}. Reassembly rejected."
            )
        elif isinstance(probe, dict) and "passed" in probe:
            lines.append(f"- {name}: passed = {probe['passed']}.")
    if "error" in report:
        lines += ["", "Error: " + report["error"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=int, default=11)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    parser.add_argument("--mmg")
    parser.add_argument("--no-pictures", dest="pictures", action="store_false")
    parser.add_argument("--no-full-scan", dest="full_scan", action="store_false")
    parser.add_argument("--only-global", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    # Refuse to mix stale outputs from two runs. Choose another directory.
    if (args.output / "report.json").exists():
        parser.error("Output already contains a report; choose a fresh --output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    args.mmg = find_mmg(args.mmg)
    report = {
        "outcome": "running",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "cells_per_axis": args.cells,
        "mmg_executable": args.mmg,
        "method": "global block-local plane cutter with LSReferences split/nosplit",
        "full_hanging_node_scan": args.full_scan,
    }
    provenance = ROOT / ".mmg-runtime/provenance.json"
    if provenance.exists():
        report["mmg_package"] = json.loads(provenance.read_text())
    try:
        global_pipeline(args, report)
        if not args.only_global:
            preservation_probes(args, report)
    except Exception as error:
        report["outcome"] = "failed"
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        save_json(args.output / "report.json", report)
        (args.output / "results.md").write_text(markdown_results(report))
    progress(f"{report['outcome']}: {args.output / 'results.md'}")


if __name__ == "__main__":
    main()
