"""Time a complete model: cut each interface, immediately repair only its band."""

import argparse
import copy
import json
import sys
import time
import traceback
from pathlib import Path

PROCESS_START = time.perf_counter()
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np
import pyvista as pv

from fault_mmg.geometry import HORIZONS
from fault_mmg.local_remesh import freeze_outside, interface_band, verify_frozen_region
from fault_mmg.mesh import cube, write_mesh
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset, run_remesh
from fault_mmg.quality import cell_quality, quality_report
from fault_mmg.two_fault_visualization import export_two_faults, volume_grid
from fault_mmg.two_faults import TwoFaultModel, validate_two_faults
from fault_mmg.validation import validate, validate_topology


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def clear_required(mesh):
    # A previous step's frozen bulk must be released before the next cut.
    mesh.required_tets = np.empty(0, dtype=int)
    mesh.required_vertices = np.empty(0, dtype=int)
    mesh.required_triangles = np.empty(0, dtype=int)


def stage_vtu(mesh, path):
    cells = np.c_[np.full(len(mesh.tets), 4), mesh.tets].ravel()
    data = pv.UnstructuredGrid(
        cells, np.full(len(mesh.tets), pv.CellType.TETRA, dtype=np.uint8), mesh.points
    )
    data.cell_data['material_reference'] = mesh.refs
    data.cell_data['mmg_quality'] = cell_quality(mesh)['mmg_quality']
    data.save(path)


def summary(report):
    lines = [
        f"# Complete local workflow: {report['case']}",
        '',
        f"Outcome: **{report['outcome']}**.",
        '',
    ]
    timing = report.get('timing', {})
    for label, key in [
        ('Workflow, including validation, I/O and figures', 'workflow_seconds'),
        ('Python/library startup', 'startup_import_seconds'),
        ('Total including startup', 'total_including_startup_seconds'),
        ('MMG level-set cutting', 'cut_mmg_seconds'),
        ('MMG local adaptation', 'repair_mmg_seconds'),
        ('Geological and topology validation', 'validation_seconds'),
        ('Band selection and freezing', 'selection_seconds'),
        ('Frozen-bulk verification', 'frozen_check_seconds'),
        ('Final VTK/PNG exports', 'final_export_seconds'),
    ]:
        if key in timing:
            lines.append(f"- {label}: {timing[key]:.3f} s")
    if 'final' in report:
        q = report['quality']
        v = report['final']
        lines += [
            '',
            f"Final tets: {q['tetrahedra']}; minimum quality: {q['mmg_quality']['minimum']:.6g}; median: {q['mmg_quality']['median']:.6g}.",
            f"Minimum dihedral: {q['minimum_dihedral_degrees']['minimum']:.6g} degrees; tets below 5 degrees: {q['minimum_dihedral_degrees']['below_5_degrees']}.",
            f"Final geometry/material checks: {sum(v['checks'].values())}/{len(v['checks'])}.",
            f"Completed cuts: {len(report['stages'])}; local adaptation calls: {report.get('repair_calls',0)}.",
            f"Every local repair preserved its frozen outer tets: {all(p['frozen_region']['passed'] for s in report['stages'] for p in s['repair_passes'])}.",
        ]
    if 'error' in report:
        lines += ['', 'Error: ' + report['error']]
    return '\n'.join(lines) + '\n'


def run(args, case, startup):
    started = time.perf_counter()
    out = args.output / case
    if out.exists():
        raise FileExistsError(f'Choose a fresh output directory: {out}')
    out.mkdir(parents=True)
    model = TwoFaultModel(case)
    timing = {
        'startup_import_seconds': startup,
        'cut_mmg_seconds': 0.0,
        'repair_mmg_seconds': 0.0,
        'validation_seconds': 0.0,
        'selection_seconds': 0.0,
        'frozen_check_seconds': 0.0,
        'final_export_seconds': 0.0,
    }
    report = {
        'case': case,
        'outcome': 'running',
        'cells_per_axis': args.cells,
        'method': 'cut, then frozen-bulk local adaptation after every fault and block-local horizon',
        'band_half_width': args.width,
        'halo_vertex_layers': args.halo,
        'minimum_quality_goal': args.minimum_quality,
        'minimum_angle_goal': args.minimum_angle,
        'maximum_repair_passes_per_cut': args.max_passes,
        'size': args.size,
        'pictures': args.pictures,
        'stages': [],
        'timing': timing,
        'repair_calls': 0,
    }
    provenance = ROOT / '.mmg-runtime/provenance.json'
    if provenance.exists():
        report['mmg_package'] = json.loads(provenance.read_text())

    def checkpoint():
        save(out / 'report.json', report)
        (out / 'results.md').write_text(summary(report))

    def checked(mesh, stage, horizons, lineage):
        t = time.perf_counter()
        if stage == 1:
            result = validate(mesh, horizons=[], full_scan=True)
        else:
            result = validate_two_faults(mesh, model, horizons=horizons, lineage=lineage)
        timing['validation_seconds'] += time.perf_counter() - t
        return result

    try:
        current = cube(args.cells)
        write_mesh(out / 'initial.mesh', current)
        t = time.perf_counter()
        report['initial'] = validate_topology(current)
        timing['validation_seconds'] += time.perf_counter() - t
        stage_vtu(current, out / 'initial_mesh.vtu')
        completed = []
        lineage = {1: (0, 0)}
        operations = [{'kind': 'fault', 'fault': 1}, {'kind': 'fault', 'fault': 2}]
        operations += [
            {'kind': 'horizon', 'block': b, 'horizon': float(h), 'unit': u}
            for u, h in enumerate(HORIZONS)
            for b in model.blocks
        ]
        next_ref = 1001
        for stage, operation in enumerate(operations, 1):
            clear_required(current)
            retag_interfaces(current, 100 + stage)
            folder = out / f'{stage:02d}_{operation["kind"]}'
            folder.mkdir()
            if stage == 1:
                mapping = {1: (11, 12)}
                next_lineage = {11: (1, 0), 12: (2, 0)}
                values = current.points[:, 0]
            elif stage == 2:
                if case == 'terminating':
                    mapping = {11: None, 12: (21, 22)}
                    next_lineage = {11: (1, 0), 21: (2, 0), 22: (3, 0)}
                else:
                    mapping = {11: (21, 22), 12: (23, 24)}
                    next_lineage = {21: (1, 0), 22: (2, 0), 23: (3, 0), 24: (4, 0)}
                values = model.secondary(current.points)
            else:
                block, horizon, unit = operation['block'], operation['horizon'], operation['unit']
                mapping = {int(ref): None for ref in np.unique(current.refs)}
                parent = next(
                    ref
                    for ref, state in lineage.items()
                    if state == (block, unit) and ref in mapping
                )
                pair = (next_ref, next_ref + 1)
                next_ref += 2
                mapping[parent] = pair
                next_lineage = lineage.copy()
                next_lineage.pop(parent)
                next_lineage[pair[0]] = (block, unit)
                next_lineage[pair[1]] = (block, unit + 1)
                values = model.restored(current.points, block) - horizon
            print(f'{case}: cut {stage}/{len(operations)} {operation}', flush=True)
            cut, invocation = run_levelset(current, values, folder / 'cut', mapping, args.mmg)
            timing['cut_mmg_seconds'] += invocation['elapsed_seconds']
            lineage = next_lineage
            if stage > 2:
                completed.append((operation['block'], operation['horizon']))
            validation = checked(cut, stage, completed, lineage)
            save(folder / 'cut/validation.json', validation)
            entry = {
                'operation': operation,
                'cut_invocation': invocation,
                'cut_validation': validation,
                'repair_passes': [],
                'post_cut_quality': quality_report(cut),
            }
            report['stages'].append(entry)
            if not validation['passed']:
                raise RuntimeError(
                    f'Cut {stage} changed geology: {[k for k,v in validation["checks"].items() if not v]}'
                )
            t = time.perf_counter()
            if stage <= 2:
                active, band = interface_band(
                    cut,
                    model,
                    width=args.width,
                    halo=args.halo,
                    quality_cutoff=args.minimum_quality,
                    horizon_pairs=[],
                    include_faults=True,
                    fault_ids=(stage,),
                    halo_kind='vertex',
                )
            else:
                active, band = interface_band(
                    cut,
                    model,
                    width=args.width,
                    halo=args.halo,
                    quality_cutoff=args.minimum_quality,
                    horizon_pairs=[(operation['block'], operation['horizon'])],
                    include_faults=False,
                    halo_kind='vertex',
                )
            frozen_ids = np.flatnonzero(~active)
            candidate_input = freeze_outside(cut, active)
            timing['selection_seconds'] += time.perf_counter() - t
            entry['band'] = band
            selected = None
            best = -1.0
            for attempt in range(args.max_passes):
                print(
                    f'{case}: local repair {stage}.{attempt+1}; active {band["active_fraction"]:.1%}',
                    flush=True,
                )
                candidate, invocation = run_remesh(
                    candidate_input,
                    folder / f'repair_{attempt+1}',
                    args.mmg,
                    size=args.size,
                    optimize_only=attempt > 0,
                )
                timing['repair_mmg_seconds'] += invocation['elapsed_seconds']
                report['repair_calls'] += 1
                validation = checked(candidate, stage, completed, lineage)
                t = time.perf_counter()
                frozen, ids = verify_frozen_region(cut, candidate, frozen_ids)
                timing['frozen_check_seconds'] += time.perf_counter() - t
                q = quality_report(candidate)
                repaired = {
                    'invocation': invocation,
                    'validation': validation,
                    'frozen_region': frozen,
                    'quality': q,
                }
                entry['repair_passes'].append(repaired)
                save(folder / f'repair_{attempt+1}/validation.json', repaired)
                if not validation['passed'] or not frozen['passed']:
                    raise RuntimeError(
                        f'Local repair {stage}.{attempt+1} failed geometry or frozen-region verification'
                    )
                if q['mmg_quality']['minimum'] > best:
                    best = q['mmg_quality']['minimum']
                    selected = copy.deepcopy(candidate)
                    entry['selected_pass'] = attempt + 1
                    entry['selected_quality'] = q
                    entry['selected_validation'] = validation
                if (
                    q['mmg_quality']['minimum'] >= args.minimum_quality
                    and q['minimum_dihedral_degrees']['minimum'] >= args.minimum_angle
                ):
                    break
                candidate_input = candidate
                candidate_input.required_tets = ids
                candidate_input.required_vertices = np.unique(candidate_input.tets[ids])
                candidate_input.required_triangles = np.empty(0, dtype=int)
            current = selected
            stage_vtu(current, folder / 'locally_repaired.vtu')
            report['material_lineage'] = lineage.copy()
            checkpoint()
        report['final'] = checked(current, len(operations), completed, lineage)
        report['quality'] = quality_report(current)
        clear_required(current)
        write_mesh(out / 'final.mesh', current)
        t = time.perf_counter()
        export_two_faults(current, model, out, pictures=args.pictures)
        data = volume_grid(current, model)
        for name, values in cell_quality(current).items():
            data.cell_data[name] = values
        data.save(out / 'final_mesh.vtu')
        reopened = pv.read(out / 'final_mesh.vtu')
        assert reopened.n_cells == len(current.tets)
        np.testing.assert_array_equal(
            reopened.cell_data['stratigraphy'], data.cell_data['stratigraphy']
        )
        timing['final_export_seconds'] += time.perf_counter() - t
        q = report['quality']
        report['outcome'] = (
            'validated_local_workflow'
            if q['mmg_quality']['minimum'] >= args.minimum_quality
            and q['minimum_dihedral_degrees']['minimum'] >= args.minimum_angle
            else 'validated_geometry_with_residual_quality_limits'
        )
    except Exception as error:
        report.update(
            {'outcome': 'failed', 'error': str(error), 'traceback': traceback.format_exc()}
        )
        raise
    finally:
        timing['workflow_seconds'] = time.perf_counter() - started
        timing['total_including_startup_seconds'] = timing['workflow_seconds'] + startup
        checkpoint()
        print('TOTAL', case, timing['workflow_seconds'], report['outcome'], flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=['terminating', 'crossing', 'both'], default='terminating')
    p.add_argument('--cells', type=int, default=11)
    p.add_argument('--output', type=Path, default=ROOT / 'outputs/full_local_workflow')
    p.add_argument('--width', type=float, default=0.03)
    p.add_argument('--halo', type=int, default=1)
    p.add_argument('--size', type=float, default=0.18)
    p.add_argument('--max-passes', type=int, choices=[1, 2], default=2)
    p.add_argument('--minimum-quality', type=float, default=0.1)
    p.add_argument('--minimum-angle', type=float, default=5.0)
    p.add_argument('--no-pictures', dest='pictures', action='store_false')
    p.add_argument('--mmg')
    args = p.parse_args()
    args.output = args.output.resolve()
    args.mmg = find_mmg(args.mmg)
    startup = time.perf_counter() - PROCESS_START
    for case in (['terminating', 'crossing'] if args.case == 'both' else [args.case]):
        run(args, case, startup)


if __name__ == '__main__':
    main()
