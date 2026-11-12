import copy

import numpy as np
import pytest

from fault_mmg.interfaces import face_table, interface_signature
from fault_mmg.mesh import Mesh, cube, extract_block
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset
from fault_mmg.validation import hanging_vertices, validate


def fitted_cube():
    m = cube(2)
    m.points[np.abs(m.points[:, 0]) < 0.5, 0] = 0
    return m


def test_fault_faces_have_two_incident_tetrahedra():
    m = fitted_cube()
    result = validate(m, horizons=[])
    assert result["passed"]
    assert result["metrics"]["fault_area"] == pytest.approx(4)
    a, b = extract_block(m, 1), extract_block(m, 2)
    assert interface_signature(a) == interface_signature(b)


def test_missing_tet_exposes_unintended_internal_boundary():
    m = fitted_cube()
    m.tets = m.tets[1:]
    m.refs = m.refs[1:]
    result = validate(m, horizons=[], full_scan=False)
    assert not result["checks"]["external_faces_on_cube"]
    assert not result["checks"]["cube_volume"]


@pytest.mark.parametrize("extra", [[0.25, 0.25, 0], [0.5, 0, 0]])
def test_geometric_hanging_node_scan_catches_face_and_edge_nodes(extra):
    m = Mesh(
        np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], extra]),
        np.array([[0, 1, 2, 3]]),
        np.ones(1, dtype=int),
    )
    result = hanging_vertices(m, face_table(m)[0])
    assert result["incidences"] > 0
    assert result["examples"][0]["vertex"] == 4


def test_topologically_valid_cube_can_have_incorrect_geology():
    m = cube(3)
    result = validate(m, horizons=[])
    assert result["checks"]["face_multiplicity"]
    assert result["checks"]["cube_volume"]
    assert not result["checks"]["no_tet_crosses_fault"]
    assert not result["passed"]


def test_existing_horizon_is_not_assumed_from_centroid_labels():
    result = validate(fitted_cube(), horizons=[(1, 0.5)], full_scan=False)
    assert not result["checks"]["block_1_horizon_0.5_area"]
    assert not result["checks"]["block_1_horizon_0.5_no_crossing_tets"]


def test_real_mmg_can_refine_a_nosplit_neighbor_conformingly(tmp_path):
    try:
        executable = find_mmg()
    except FileNotFoundError:
        pytest.skip("MMG executable unavailable; run the documented installer")
    m = cube(3)
    fault, _ = run_levelset(m, m.points[:, 0], tmp_path / "fault", {1: (11, 12)}, executable)
    retag_interfaces(fault, 100)
    before = copy.deepcopy(fault)
    # B's physical f=0 surface intersects x=0 at z=.4, cutting fault triangles.
    out, _ = run_levelset(
        fault, fault.points[:, 2] - 0.4, tmp_path / "horizon", {11: None, 12: (21, 22)}, executable
    )
    result = validate(out, horizons=[(2, 0.0)])
    assert result["passed"], result
    assert (
        result["metrics"]["fault_triangles"]
        > validate(before, horizons=[], full_scan=False)["metrics"]["fault_triangles"]
    )
    assert set(out.refs) == {11, 21, 22}
