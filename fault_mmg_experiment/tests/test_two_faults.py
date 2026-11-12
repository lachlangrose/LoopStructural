"""Checks for fault termination, analytic surface coverage and real MMG junctions."""

import numpy as np
import pytest

from fault_mmg.mesh import Mesh, cube
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset
from fault_mmg.two_faults import (
    STRAT_NORMAL,
    TwoFaultModel,
    clipped_polygon,
    edge_coverage,
    horizon_fault_segment,
    mmg_isotropic_quality,
    polygon_area,
    validate_two_faults,
)


def test_secondary_fault_has_no_block_boundary_on_primary_negative_side():
    model = TwoFaultModel("terminating")
    points = np.array([[-0.5, -0.8, 0.2], [-0.5, 0.8, 0.2], [0.5, -0.8, 0.2], [0.5, 0.8, 0.2]])
    np.testing.assert_array_equal(model.block_labels(points), [1, 1, 2, 3])
    assert horizon_fault_segment(model, 1, 0.0, 2) is None


def test_crossing_control_partitions_both_sides():
    model = TwoFaultModel("crossing")
    points = np.array([[-0.5, -0.8, 0.2], [-0.5, 0.8, 0.2], [0.5, -0.8, 0.2], [0.5, 0.8, 0.2]])
    np.testing.assert_array_equal(model.block_labels(points), [1, 2, 3, 4])


def test_three_distinct_one_sided_traces_exist_at_junction():
    model = TwoFaultModel("terminating")
    junction = np.array([[0.0, 0.1, 0.0]])
    traces = [model.restored(junction, b)[0] for b in model.blocks]
    np.testing.assert_allclose(traces, [0.01, -0.24, -0.39])


@pytest.mark.parametrize("case", ["terminating", "crossing"])
def test_half_space_partition_preserves_exact_plane_section_area(case):
    model = TwoFaultModel(case)
    area = sum(
        polygon_area(clipped_polygon(STRAT_NORMAL, 0.0, model.constraints(b))) for b in model.blocks
    )
    # z=0.2*x-0.1*y spans the whole [-1,1]^2 footprint inside the cube.
    assert area == pytest.approx(4 * np.sqrt(1 + 0.2**2 + 0.1**2))


@pytest.mark.parametrize("case, width", [("terminating", 1), ("crossing", 2)])
def test_exact_fault_areas(case, width):
    model = TwoFaultModel(case)
    assert polygon_area(model.fault_polygon(1)) == pytest.approx(4)
    assert polygon_area(model.fault_polygon(2)) == pytest.approx(width * 2 * np.sqrt(1 + 0.35**2))
    assert all(
        polygon_area(model.horizon_polygon(b, h)) > 0
        for b in model.blocks
        for h in [-0.5, 0.0, 0.5]
    )


def test_edge_chain_rejects_gap_even_when_total_length_is_correct():
    # Two segments have total length 2, but overlap and leave part uncovered.
    m = Mesh(
        np.array([[0.0, 0, 0], [0, 0, 1.5], [0, 0, 0.25], [0, 0, 0.75]]),
        np.empty((0, 4), dtype=int),
        np.empty(0, dtype=int),
    )
    result = edge_coverage(m, [(0, 1), (2, 3)], [[0.0, 0, 0], [0, 0, 2]])
    assert result["length"] == pytest.approx(2)
    assert not result["passed"]


def test_mmg_quality_normalization_on_regular_tetrahedron():
    p = np.array(
        [[0.0, 0, 0], [1, 0, 0], [0.5, np.sqrt(3) / 2, 0], [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]]
    )
    m = Mesh(p, np.array([[0, 1, 2, 3]]), np.array([1]))
    assert mmg_isotropic_quality(m)[0] * 12 * np.sqrt(3) == pytest.approx(1.0)


@pytest.mark.parametrize("case", ["terminating", "crossing"])
def test_real_mmg_fault_junction_is_a_shared_edge_chain(tmp_path, case):
    try:
        executable = find_mmg()
    except FileNotFoundError:
        pytest.skip("MMG executable unavailable")
    model = TwoFaultModel(case)
    mesh = cube(3)
    mesh, _ = run_levelset(mesh, mesh.points[:, 0], tmp_path / "primary", {1: (11, 12)}, executable)
    retag_interfaces(mesh, 100)
    if case == "terminating":
        mapping = {11: None, 12: (21, 22)}
        lineage = {11: (1, 0), 21: (2, 0), 22: (3, 0)}
    else:
        mapping = {11: (21, 22), 12: (23, 24)}
        lineage = {21: (1, 0), 22: (2, 0), 23: (3, 0), 24: (4, 0)}
    mesh, _ = run_levelset(
        mesh, model.secondary(mesh.points), tmp_path / "secondary", mapping, executable
    )
    result = validate_two_faults(mesh, model, lineage=lineage)
    assert result["passed"], [k for k, passed in result["checks"].items() if not passed]
    expected = 3 if case == "terminating" else 4
    assert result["metrics"]["junction"]["observed_sheet_incidence"] == [expected]
    # A mere visual T is insufficient: removing one tetrahedron opens a crack.
    mesh.tets = mesh.tets[1:]
    mesh.refs = mesh.refs[1:]
    assert not validate_two_faults(mesh, model, full_scan=False)["passed"]
