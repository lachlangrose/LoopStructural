"""Quality metrics distinguish regular tetrahedra from conforming slivers."""

import numpy as np
import pytest

from fault_mmg.mesh import Mesh, cube
from fault_mmg.mmg import find_mmg, retag_interfaces, run_levelset, run_remesh
from fault_mmg.quality import cell_quality, quality_report
from fault_mmg.two_faults import TwoFaultModel, validate_two_faults


def test_regular_tetrahedron_has_reference_quality_and_dihedral_angles():
    points = np.array(
        [[0.0, 0, 0], [1, 0, 0], [0.5, np.sqrt(3) / 2, 0], [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]]
    )
    mesh = Mesh(points, np.array([[0, 1, 2, 3]]), np.array([1]))
    q = cell_quality(mesh)
    assert q["mmg_quality"][0] == pytest.approx(1.0)
    assert q["minimum_dihedral_degrees"][0] == pytest.approx(np.degrees(np.arccos(1 / 3)))
    assert q["maximum_dihedral_degrees"][0] == pytest.approx(np.degrees(np.arccos(1 / 3)))
    assert q["tetra_volume"][0] == pytest.approx(np.sqrt(2) / 12)


def test_positive_volume_sliver_is_reported_as_poor_quality():
    mesh = Mesh(
        np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0.3, 0.3, 1e-6]]),
        np.array([[0, 1, 2, 3]]),
        np.array([1]),
    )
    assert mesh.volumes()[0] > 0
    q = quality_report(mesh)
    assert q["mmg_quality"]["minimum"] < 1e-4
    assert q["minimum_dihedral_degrees"]["minimum"] < 0.001
    assert q["minimum_dihedral_degrees"]["below_5_degrees"] == 1


def test_real_adaptation_improves_quality_without_destroying_fault_junction(tmp_path):
    try:
        executable = find_mmg()
    except FileNotFoundError:
        pytest.skip("MMG executable unavailable")
    model = TwoFaultModel()
    mesh = cube(3)
    mesh, _ = run_levelset(mesh, mesh.points[:, 0], tmp_path / "primary", {1: (11, 12)}, executable)
    retag_interfaces(mesh, 100)
    mesh, _ = run_levelset(
        mesh,
        model.secondary(mesh.points),
        tmp_path / "secondary",
        {11: None, 12: (21, 22)},
        executable,
    )
    before = quality_report(mesh)
    remeshed, record = run_remesh(mesh, tmp_path / "adaptation", executable, size=0.4)
    result = validate_two_faults(remeshed, model, lineage={11: (1, 0), 21: (2, 0), 22: (3, 0)})
    assert result["passed"], result
    assert not any(flag in record["command"] for flag in ("-ls", "-noinsert", "-nomove", "-noswap"))
    assert quality_report(remeshed)["mmg_quality"]["minimum"] > before["mmg_quality"]["minimum"]
