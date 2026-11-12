"""Narrow-band selection must capture crossings and preserve the complete bulk."""

import copy

import numpy as np
import pytest

from fault_mmg.local_remesh import freeze_outside, interface_band, verify_frozen_region
from fault_mmg.mesh import Mesh, cube
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset, run_remesh
from fault_mmg.two_faults import STRAT_NORMAL, TwoFaultModel, validate_two_faults


def test_band_detects_crossed_tet_even_when_no_vertex_is_near_isovalue():
    xy = np.array([[-0.8, -0.2], [-0.6, -0.2], [-0.7, 0.2], [-0.7, 0]])
    scalar = np.array([-0.2, 0.2, -0.2, 0.2])
    z = scalar + 0.2 * xy[:, 0] - 0.1 * xy[:, 1]
    mesh = Mesh(np.c_[xy, z], np.array([[0, 1, 2, 3]]), np.array([1])).orient()
    assert np.all(abs(mesh.points @ STRAT_NORMAL) > 0.03 * np.linalg.norm(STRAT_NORMAL))
    active, _ = interface_band(
        mesh,
        TwoFaultModel(),
        width=0.03,
        halo=0,
        quality_cutoff=0,
        horizon_pairs=[(1, 0.0)],
        include_faults=False,
    )
    assert active[0]


def test_one_sided_horizon_band_excludes_other_fault_block():
    mesh = cube(5)
    active, _ = interface_band(
        mesh,
        TwoFaultModel(),
        width=0.03,
        halo=0,
        quality_cutoff=0,
        horizon_pairs=[(1, 0.0)],
        include_faults=False,
    )
    assert active.any()
    assert np.all(TwoFaultModel().block_labels(mesh.centers[active]) == 1)


def test_vertex_halo_keeps_seed_vertices_out_of_frozen_tetrahedra():
    mesh = cube(5)
    options = dict(width=0.03, quality_cutoff=0, horizon_pairs=[(1, 0.0)], include_faults=False)
    seed, _ = interface_band(mesh, TwoFaultModel(), halo=0, **options)
    active, _ = interface_band(mesh, TwoFaultModel(), halo=1, halo_kind='vertex', **options)
    seed_vertices = np.unique(mesh.tets[seed])
    frozen_vertices = np.unique(mesh.tets[~active])
    assert len(np.intersect1d(seed_vertices, frozen_vertices)) == 0
    assert np.all(active[seed])


def test_frozen_region_tracks_renumbering_and_detects_vertex_movement():
    original = cube(3)
    output = copy.deepcopy(original)
    permutation = np.arange(len(original.points))[::-1]
    inverse = np.argsort(permutation)
    output.points = output.points[permutation]
    output.tets = inverse[output.tets][::-1]
    output.refs = output.refs[::-1]
    mask = np.zeros(len(original.tets), dtype=bool)
    mask[:6] = True
    report, matched = verify_frozen_region(original, output, mask)
    assert report['passed'] and report['frozen_tets'] == 6 and len(matched) == 6
    output.points[inverse[original.tets[0, 0]], 0] += 0.001
    assert not verify_frozen_region(original, output, mask)[0]['passed']


def test_real_local_adaptation_preserves_bulk_and_three_sheet_junction(tmp_path):
    try:
        executable = find_mmg()
    except FileNotFoundError:
        pytest.skip('MMG executable unavailable')
    model = TwoFaultModel()
    mesh = cube(5)
    mesh, _ = run_levelset(mesh, mesh.points[:, 0], tmp_path / 'primary', {1: (11, 12)}, executable)
    retag_interfaces(mesh, 100)
    mesh, _ = run_levelset(
        mesh,
        model.secondary(mesh.points),
        tmp_path / 'secondary',
        {11: None, 12: (21, 22)},
        executable,
    )
    active, _ = interface_band(
        mesh,
        model,
        width=0.03,
        halo=1,
        quality_cutoff=0,
        horizon_pairs=[(1, 0.0)],
        include_faults=False,
    )
    assert 0 < active.sum() < len(mesh.tets)
    frozen = freeze_outside(mesh, active)
    output, _ = run_remesh(frozen, tmp_path / 'local', executable, size=0.3)
    check, _ = verify_frozen_region(mesh, output, ~active)
    assert check['passed'] and check['frozen_tets'] == int((~active).sum())
    assert validate_two_faults(output, model, lineage={11: (1, 0), 21: (2, 0), 22: (3, 0)})[
        'passed'
    ]
