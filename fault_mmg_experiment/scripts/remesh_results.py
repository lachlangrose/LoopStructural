"""Remesh existing two-fault results, preserving and revalidating interfaces."""

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv

from fault_mmg.mesh import read_mesh, write_mesh
from fault_mmg.mmg import find_mmg, run_remesh
from fault_mmg.quality import cell_quality, quality_report
from fault_mmg.two_fault_visualization import export_two_faults, volume_grid
from fault_mmg.two_faults import TwoFaultModel, validate_two_faults


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def grid_with_quality(mesh, model):
    data = volume_grid(mesh, model)
    for name, values in cell_quality(mesh).items():
        data.cell_data[name] = values
    return data


def comparison_figures(before, after, model, directory):
    first, second = cell_quality(before), cell_quality(after)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), constrained_layout=True)
    for data, color, label in ((first, "#8c9197", "Cut only"), (second, "#007b91", "Remeshed")):
        for ax, metric in zip(axes, ("mmg_quality", "minimum_dihedral_degrees")):
            values = np.sort(data[metric])
            ax.plot(
                values,
                100 * np.arange(1, len(values) + 1) / len(values),
                color=color,
                label=label,
                lw=2,
            )
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Normalized MMG quality (1 = regular tetrahedron)")
    axes[1].set_xlabel("Minimum dihedral angle per tetrahedron (degrees)")
    axes[1].set_xlim(0, 75)
    for ax in axes:
        ax.set_ylabel("Cumulative percentage of tetrahedra")
        ax.set_ylim(0, 100)
        ax.grid(alpha=0.2)
        ax.legend()
    fig.suptitle(f"{model.case.title()} faults: element quality before and after remeshing")
    fig.savefig(directory / "quality_comparison.png", dpi=160)
    plt.close(fig)
    plotter = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(1900, 950), border=False)
    for i, (mesh, title) in enumerate(((before, "Cutting only"), (after, "MMG remeshed"))):
        plotter.subplot(0, i)
        plotter.set_background("white")
        section = volume_grid(mesh, model).slice(normal=(0, 1, 0), origin=(0, 0, 0))
        plotter.add_mesh(
            section,
            scalars="stratigraphy",
            cmap=["#c5dfeb", "#ecd2aa", "#c7dfb6", "#d7c4e4"],
            clim=(0, 3),
            n_colors=4,
            show_scalar_bar=False,
            show_edges=True,
            edge_color="#677079",
            line_width=0.6,
            lighting=False,
        )
        q = quality_report(mesh)
        plotter.add_text(
            f"{title}\n{len(mesh.tets):,} tets; minimum Q = {q['mmg_quality']['minimum']:.4g}",
            position="upper_left",
            color="#172b3a",
            font_size=14,
        )
        plotter.view_xz()
        plotter.enable_parallel_projection()
        plotter.show_bounds(
            grid=False,
            location="outer",
            show_yaxis=False,
            xtitle="x",
            ztitle="z",
            color="#172b3a",
            font_size=10,
        )
    plotter.show(screenshot=str(directory / "mesh_comparison_y0.png"))


def markdown(report):
    lines = [
        f"# Actual MMG remeshing: {report['case']}",
        "",
        f"Outcome: **{report['outcome']}**.",
        "",
        "The input was generated with level-set cutting and ordinary adaptation disabled.",
        "These passes use MMG3D's standard adaptation mode, without -ls, -noinsert, -nomove or -noswap.",
        "",
    ]
    if "after" in report:
        a, b = report["before"], report["after"]
        lines += [
            "| Metric | Cut only | Remeshed |",
            "| --- | --- | --- |",
            f"| Tetrahedra | {a['tetrahedra']} | {b['tetrahedra']} |",
            f"| Minimum normalized quality | {a['mmg_quality']['minimum']:.8g} | {b['mmg_quality']['minimum']:.8g} |",
            f"| Quality, 1st percentile | {a['mmg_quality']['percentile_1']:.6g} | {b['mmg_quality']['percentile_1']:.6g} |",
            f"| Median quality | {a['mmg_quality']['median']:.6g} | {b['mmg_quality']['median']:.6g} |",
            f"| Tets with quality < 0.1 | {a['mmg_quality']['below_0_1']} | {b['mmg_quality']['below_0_1']} |",
            f"| Smallest dihedral angle | {a['minimum_dihedral_degrees']['minimum']:.6g} degrees | {b['minimum_dihedral_degrees']['minimum']:.6g} degrees |",
            f"| Tets with minimum angle < 5 degrees | {a['minimum_dihedral_degrees']['below_5_degrees']} | {b['minimum_dihedral_degrees']['below_5_degrees']} |",
            "",
            f"Selected pass: {report['selected_pass']}. All {len(report['validation']['checks'])} geometry/topology/material checks passed.",
            "",
            "Quality is reported separately from conformity. A regular tetrahedron has quality 1; residual bad angles are not hidden.",
            "",
            "VTU cell properties include stratigraphy, stratigraphic_coordinate, fault_block, geological_unit, material_reference, mmg_quality, minimum_dihedral_degrees, maximum_dihedral_degrees and tetra_volume.",
            "",
            "![Mesh comparison](mesh_comparison_y0.png)",
            "",
            "![Quality distributions](quality_comparison.png)",
        ]
    if "error" in report:
        lines += ["", "Error: " + report["error"]]
    return "\n".join(lines) + "\n"


def remesh_case(args, case):
    source, out = args.source / case, args.output / case
    if out.exists():
        raise FileExistsError(f"Choose a fresh output directory: {out}")
    out.mkdir(parents=True)
    original = read_mesh(source / "final.mesh")
    metadata = json.loads((source / "report.json").read_text())
    model = TwoFaultModel(case)
    horizons = [(b, float(h)) for b in model.blocks for h in (-0.5, 0, 0.5)]
    lineage = {int(ref): tuple(state) for ref, state in metadata["material_lineage"].items()}
    report = {
        "case": case,
        "outcome": "running",
        "source": str(source),
        "before": quality_report(original),
        "passes": [],
        "material_lineage": lineage,
        "source_mmg_package": metadata.get("mmg_package"),
    }

    def checkpoint():
        save(out / "report.json", report)
        (out / "results.md").write_text(markdown(report))

    try:
        input_validation = validate_two_faults(original, model, horizons=horizons, lineage=lineage)
        if not input_validation["passed"]:
            raise RuntimeError("Original mesh fails geological or topology validation")
        grid_with_quality(original, model).save(out / "cut_mesh_with_quality.vtu")
        current, selected = original, None
        best_quality = report["before"]["mmg_quality"]["minimum"]
        for index in range(args.passes):
            title = "uniform_adaptation" if index == 0 else "quality_optimization"
            directory = out / f"{index+1:02d}_{title}"
            print(f"{case}: {title}", flush=True)
            candidate, invocation = run_remesh(
                current, directory, args.mmg, size=args.size, optimize_only=index > 0
            )
            validation = validate_two_faults(candidate, model, horizons=horizons, lineage=lineage)
            q = quality_report(candidate)
            record = {
                "pass": index + 1,
                "quality": q,
                "validation": validation,
                "invocation": invocation,
            }
            report["passes"].append(record)
            save(directory / "validation.json", validation)
            grid_with_quality(candidate, model).save(directory / "candidate.vtu")
            checkpoint()
            if not validation["passed"]:
                raise RuntimeError(
                    f"Remeshing changed geology or conformity: {[k for k,v in validation['checks'].items() if not v]}"
                )
            current = candidate
            if q["mmg_quality"]["minimum"] > best_quality:
                selected = candidate
                best_quality = q["mmg_quality"]["minimum"]
                report.update({"after": q, "selected_pass": index + 1, "validation": validation})
        if selected is None:
            raise RuntimeError("No geometrically valid candidate improved minimum element quality")
        write_mesh(out / "final.mesh", selected)
        export_two_faults(selected, model, out, pictures=args.pictures)
        data = grid_with_quality(selected, model)
        data.save(out / "final_mesh.vtu")
        reopened = pv.read(out / "final_mesh.vtu")
        for name in (
            "stratigraphy",
            "stratigraphic_coordinate",
            "mmg_quality",
            "minimum_dihedral_degrees",
        ):
            np.testing.assert_allclose(reopened.cell_data[name], data.cell_data[name])
        if args.pictures:
            comparison_figures(original, selected, model, out)
        report["outcome"] = "validated_quality_improvement"
        print(
            f"{case}: minimum quality {report['before']['mmg_quality']['minimum']:.6g} -> {best_quality:.6g}; geometry passes",
            flush=True,
        )
    except Exception as error:
        report.update(
            {"outcome": "failed", "error": str(error), "traceback": traceback.format_exc()}
        )
        raise
    finally:
        checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "outputs/two_faults")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/two_faults_remeshed")
    parser.add_argument("--case", choices=["terminating", "crossing", "both"], default="both")
    parser.add_argument("--passes", type=int, choices=[1, 2], default=2)
    parser.add_argument("--size", type=float, default=0.18)
    parser.add_argument("--mmg")
    parser.add_argument("--no-pictures", dest="pictures", action="store_false")
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.output = args.output.resolve()
    args.mmg = find_mmg(args.mmg)
    for case in (["terminating", "crossing"] if args.case == "both" else [args.case]):
        remesh_case(args, case)


if __name__ == "__main__":
    main()
