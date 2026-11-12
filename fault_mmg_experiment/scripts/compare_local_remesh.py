"""Compare matched global and frozen-bulk MMG adaptation on existing cut meshes."""

import argparse
import copy
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pyvista as pv

from fault_mmg.local_remesh import freeze_outside, interface_band, verify_frozen_region
from fault_mmg.mesh import read_mesh, write_mesh
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset, run_remesh
from fault_mmg.quality import cell_quality, quality_report
from fault_mmg.two_fault_visualization import volume_grid
from fault_mmg.two_faults import TwoFaultModel, validate_two_faults


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + '\n')


def vtk_grid(mesh, model):
    data = volume_grid(mesh, model)
    for name, value in cell_quality(mesh).items():
        data.cell_data[name] = value
    return data


def compare(args, case):
    source = args.source / case
    directory = args.output / case
    if directory.exists():
        raise FileExistsError(f"Choose a fresh output: {directory}")
    directory.mkdir(parents=True)
    original = read_mesh(source / 'final.mesh')
    source_report = json.loads((source / 'report.json').read_text())
    lineage = {int(k): tuple(state) for k, state in source_report['material_lineage'].items()}
    model = TwoFaultModel(case)
    horizons = [(b, float(h)) for b in model.blocks for h in (-0.5, 0, 0.5)]
    preparation = None
    current_pair = None
    if args.prepare_last_cut:
        started = time.perf_counter()
        targets = [(s['target']['block'], s['target']['horizon']) for s in source_report['stages']]
        block, horizon = targets[-1]
        last = source / f"{len(targets)+2:02d}_block{block}_horizon{horizon:g}"
        rows = [line.split() for line in (last / 'input.mmg3d').read_text().splitlines()]
        parent, negative, positive = next(tuple(map(int, row)) for row in rows if len(row) == 3)
        previous_lineage = lineage.copy()
        unit = previous_lineage.pop(negative)[1]
        previous_lineage.pop(positive)
        previous_lineage[parent] = (block, unit)
        before_last = read_mesh(last / 'input.mesh')
        clean, prep_invocation = run_remesh(
            before_last, directory / 'prepare_background', args.mmg, size=args.size
        )
        check = validate_two_faults(clean, model, horizons=targets[:-1], lineage=previous_lineage)
        save(directory / 'prepare_background/validation.json', check)
        if not check['passed']:
            raise RuntimeError('Clean-background preparation failed geometry validation')
        quality_before_cut = quality_report(clean)
        retag_interfaces(clean, 500)
        mapping = {int(ref): None for ref in np.unique(clean.refs)}
        mapping[parent] = (negative, positive)
        original, cut_invocation = run_levelset(
            clean,
            model.restored(clean.points, block) - horizon,
            directory / 'insert_last_horizon',
            mapping,
            args.mmg,
        )
        check = validate_two_faults(original, model, horizons=targets, lineage=lineage)
        save(directory / 'insert_last_horizon/validation.json', check)
        if not check['passed']:
            raise RuntimeError('New level-set cut failed geometry validation')
        current_pair = [(block, horizon)]
        preparation = {
            'purpose': 'Compare repair after one new cut in a previously adapted mesh',
            'shared_seconds': time.perf_counter() - started,
            'before_new_cut': quality_before_cut,
            'preparation_invocation': prep_invocation,
            'new_cut_invocation': cut_invocation,
            'comparison_excludes_shared_preparation': True,
        }
    t = time.perf_counter()
    pairs = current_pair or (
        [(args.current_block, args.current_horizon)] if args.current_block is not None else None
    )
    active, band = interface_band(
        original,
        model,
        args.width,
        args.halo,
        args.quality_cutoff,
        horizon_pairs=pairs,
        include_faults=pairs is None,
        halo_kind=args.halo_kind,
    )
    band['horizon_pairs'] = pairs if pairs is not None else horizons
    band['include_faults'] = pairs is None
    selection_seconds = time.perf_counter() - t
    frozen_ids = np.flatnonzero(~active)
    report = {
        'case': case,
        'outcome': 'running',
        'source': str(source),
        'band': band,
        'selection_seconds': selection_seconds,
        'before': quality_report(original),
        'variants': {},
        'preparation': preparation,
    }
    initial = vtk_grid(original, model)
    initial.cell_data['local_remesh_active'] = active.astype(np.int32)
    initial.save(directory / 'band_selection.vtu')
    try:
        for mode in ('global', 'local'):
            folder = directory / mode
            folder.mkdir()
            current = copy.deepcopy(original)
            current.required_tets = np.empty(0, dtype=int)
            current.required_vertices = np.empty(0, dtype=int)
            current.required_triangles = np.empty(0, dtype=int)
            result = {
                'passes': [],
                'mmg_seconds': 0.0,
                'validation_seconds': 0.0,
                'frozen_check_seconds': 0.0,
                'driver_seconds': 0.0,
                'wall_seconds': 0.0,
            }
            if mode == 'local':
                current = freeze_outside(current, active)
            selected = None
            best = -1.0
            t0 = time.perf_counter()
            for step in range(args.passes):
                print(
                    f"{case}: {mode} pass {step+1}; active fraction {band['active_fraction']:.1%}",
                    flush=True,
                )
                t = time.perf_counter()
                candidate, invocation = run_remesh(
                    current,
                    folder / f'pass_{step+1}',
                    args.mmg,
                    size=args.size,
                    optimize_only=step > 0,
                )
                result['driver_seconds'] += time.perf_counter() - t
                result['mmg_seconds'] += invocation['elapsed_seconds']
                t = time.perf_counter()
                validation = validate_two_faults(
                    candidate, model, horizons=horizons, lineage=lineage
                )
                result['validation_seconds'] += time.perf_counter() - t
                t = time.perf_counter()
                frozen, output_frozen = verify_frozen_region(original, candidate, frozen_ids)
                result['frozen_check_seconds'] += time.perf_counter() - t
                q = quality_report(candidate)
                record = {
                    'step': step + 1,
                    'quality': q,
                    'validation': validation,
                    'frozen_region': frozen,
                    'invocation': invocation,
                }
                result['passes'].append(record)
                save(folder / f'pass_{step+1}/validation.json', record)
                if not validation['passed']:
                    raise RuntimeError(
                        f"{mode} geometry failure: {[k for k,v in validation['checks'].items() if not v]}"
                    )
                if mode == 'local' and not frozen['passed']:
                    raise RuntimeError('Local adaptation modified the frozen outer region')
                if q['mmg_quality']['minimum'] > best:
                    best = q['mmg_quality']['minimum']
                    selected = copy.deepcopy(candidate)
                    result['selected_pass'] = step + 1
                    result['quality'] = q
                    result['validation'] = validation
                    result['frozen_region'] = frozen
                current = candidate
                if mode == 'local':
                    current.required_tets = output_frozen
                    current.required_vertices = np.unique(current.tets[output_frozen])
                    current.required_triangles = np.empty(0, dtype=int)
            result['wall_seconds'] = time.perf_counter() - t0
            report['variants'][mode] = result
            write_mesh(folder / 'final.mesh', selected)
            data = vtk_grid(selected, model)
            if mode == 'local':
                checked, indices = verify_frozen_region(original, selected, frozen_ids)
                assert checked['passed']
                frozen_cells = np.zeros(len(selected.tets), dtype=np.int32)
                frozen_cells[indices] = 1
                data.cell_data['frozen_bulk'] = frozen_cells
            data.save(folder / 'final_mesh.vtu')
            reopened = pv.read(folder / 'final_mesh.vtu')
            assert reopened.n_cells == len(selected.tets)
            if mode == 'local':
                local_match, _ = verify_frozen_region(original, selected, frozen_ids)
                assert local_match['passed']
            save(directory / 'report.json', report)
        report['mmg_speedup'] = (
            report['variants']['global']['mmg_seconds'] / report['variants']['local']['mmg_seconds']
        )
        report['measured_remesh_speedup'] = (
            report['variants']['global']['wall_seconds']
            / report['variants']['local']['wall_seconds']
        )
        report['outcome'] = 'validated_comparison'
        print(
            'COMPARISON',
            case,
            'MMG speedup',
            report['mmg_speedup'],
            'wall speedup',
            report['measured_remesh_speedup'],
            flush=True,
        )
    except Exception as error:
        report.update(
            {'outcome': 'failed', 'error': str(error), 'traceback': traceback.format_exc()}
        )
        raise
    finally:
        save(directory / 'report.json', report)
        lines = [
            f"# Local versus global remeshing: {case}",
            '',
            f"Outcome: {report['outcome']}",
            '',
            f"Interface band half-width {args.width}; {args.halo} {args.halo_kind}-neighbor halo; active {band['active_fraction']:.2%}; frozen {band['frozen_tets']} tets.",
            '',
            '| Variant | MMG seconds | Remesh + checks seconds | Min quality | Median quality | Min dihedral |',
            '| --- | --- | --- | --- | --- | --- |',
        ]
        for mode, result in report['variants'].items():
            q = result['quality']
            lines.append(
                f"| {mode} | {result['mmg_seconds']:.3f} | {result['wall_seconds']:.3f} | {q['mmg_quality']['minimum']:.6g} | {q['mmg_quality']['median']:.6g} | {q['minimum_dihedral_degrees']['minimum']:.6g} |"
            )
        (directory / 'results.md').write_text('\n'.join(lines) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=ROOT / 'outputs/two_faults')
    p.add_argument('--output', type=Path, default=ROOT / 'outputs/local_remesh_comparison')
    p.add_argument('--case', choices=['terminating', 'crossing', 'both'], default='both')
    p.add_argument('--width', type=float, default=0.03)
    p.add_argument('--halo', type=int, default=1)
    p.add_argument('--halo-kind', choices=['face', 'vertex'], default='face')
    p.add_argument(
        '--prepare-last-cut',
        action='store_true',
        help='Adapt the mesh before its final cut, insert that one horizon, then compare repair',
    )
    p.add_argument('--quality-cutoff', type=float, default=0.1)
    p.add_argument('--current-block', type=int)
    p.add_argument('--current-horizon', type=float)
    p.add_argument('--size', type=float, default=0.18)
    p.add_argument('--passes', type=int, default=2, choices=[1, 2])
    p.add_argument('--mmg')
    args = p.parse_args()
    args.source = args.source.resolve()
    args.output = args.output.resolve()
    if (args.current_block is None) != (args.current_horizon is None):
        p.error('Provide both --current-block and --current-horizon')
    args.mmg = find_mmg(args.mmg)
    for case in (['terminating', 'crossing'] if args.case == 'both' else [args.case]):
        compare(args, case)


if __name__ == '__main__':
    main()
