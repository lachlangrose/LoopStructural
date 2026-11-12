import numpy as np
import pytest

from fault_mmg.mesh import Mesh, cube, read_mesh, write_mesh
from fault_mmg.validation import validate


@pytest.mark.parametrize("cells", [3, 4, 11])
def test_initial_cube_is_positive_complete_and_not_fault_aligned(cells):
    m = cube(cells)
    assert len(m.tets) == 6 * cells**3
    assert np.all(m.volumes() > 0)
    assert m.volumes().sum() == pytest.approx(8)
    x = m.points[m.tets, 0]
    assert np.any((x.min(axis=1) < 0) & (x.max(axis=1) > 0))
    assert validate(m, require_fault=False, horizons=[], full_scan=False)["passed"]


def test_medit_roundtrip_preserves_required_entities_and_refs(tmp_path):
    m = cube(3)
    m.required_triangles = np.array([1, 4, 7])
    m.required_tets = np.array([0, 3, 8])
    m.required_vertices = np.array([0, 2, 4, 7])
    path = tmp_path / "case.mesh"
    write_mesh(path, m)
    other = read_mesh(path)
    for name in (
        "points",
        "tets",
        "refs",
        "triangles",
        "tri_refs",
        "required_triangles",
        "required_tets",
        "required_vertices",
    ):
        np.testing.assert_array_equal(getattr(other, name), getattr(m, name))


def test_ordering_correction_keeps_degenerate_elements():
    m = Mesh(
        np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0.2, 0.2, 0]]),
        np.array([[1, 0, 2, 3], [0, 1, 2, 4]]),
        np.ones(2, dtype=int),
    ).orient()
    assert len(m.tets) == 2
    assert m.orientation_corrections == 1
    assert m.volumes()[0] > 0
    assert m.volumes()[1] == 0
    assert not validate(m, require_fault=False, horizons=[], full_scan=False)["checks"][
        "positive_volumes"
    ]


def test_unknown_cells_are_rejected(tmp_path):
    path = tmp_path / "unsupported.mesh"
    path.write_text("MeshVersionFormatted 2\nDimension 3\nHexahedra\n1\n1 2 3 4 5 6 7 8 1\nEnd\n")
    with pytest.raises(ValueError, match="Hexahedra"):
        read_mesh(path)
