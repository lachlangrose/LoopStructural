"""Conforming surfaces (Loop CGAL): cut-offs and junctions are shared fault edges."""

import numpy as np
import pytest

pytest.importorskip("loop_cgal")

from fault_benchmarks.builder import build_case  # noqa: E402
from fault_benchmarks.cases import get_case  # noqa: E402
from fault_benchmarks.conforming import (  # noqa: E402
    TIP_LEVEL,
    Tri,
    build_conforming,
    check_conformity,
    insert_points_on_edges,
    split_t_junctions,
)
from fault_benchmarks.fields import SideFunctions, sign_patterns  # noqa: E402

RES = 25
CELL = 1.0 / (RES - 1)


@pytest.fixture(scope="module", params=["y_junction", "narrow_horst", "fault_tip_step"])
def case(request):
    built = build_case(get_case(request.param))
    return built, build_conforming(built, resolution=RES)


def test_cutoffs_are_fault_edges(case):
    built, res = case
    report = check_conformity(built, res, CELL)
    n_faults = len(built.spec.faults)
    if built.spec.name != "fault_tip_step":  # there the fault reaches 3 of 4 horizons
        assert len(report) >= len(res.horizons) * min(n_faults, 2) - 1
    for key, r in report.items():
        assert r["cutoff_edges"] > 0, key
        assert r["cutoff_vertices_not_fault_vertices"] == 0, key
        assert r["cutoff_edges_not_fault_edges"] == 0, key
        assert r["max_distance_to_implicit_fault"] < 1e-3 * CELL, key


def test_y_junction_has_junction(case):
    built, res = case
    if built.spec.name != "y_junction":
        pytest.skip("no abutting fault")
    report = check_conformity(built, res, CELL)
    assert report["fault_f_branch|fault_f_main"]["cutoff_edges"] > 0


def test_horizon_pieces_are_in_their_blocks(case):
    built, res = case
    sides = SideFunctions(built)
    names = [f.name for f in built.spec.faults]
    patterns = sign_patterns(built, names)
    for sid, m in res.horizons.items():
        assert m.block is not None and len(m.block) == len(m.tris), sid
        if built.spec.name != "fault_tip_step":  # a horizon above a tip is not cut
            assert len(np.unique(m.block)) >= 2, sid
        for b in np.unique(m.block):
            centres = m.points[m.tris[m.block == b]].mean(axis=1)
            for name, s in patterns[b].items():
                half = built.spec.fault(name).minor_axis / 2
                v = s * sides(name, centres) * half
                # A finite fault: the tip surface is a contour of min(1 - |g|), so
                # its corners are cut within one cell; and the footwall reaches
                # |g| = TIP_LEVEL, a little past the tip.
                finite = built.spec.fault(name).profile != "constant"
                tol = 1e-6 * CELL + ((TIP_LEVEL - 1.0) * half + np.sqrt(3) * CELL if finite else 0)
                assert np.all(v > -tol), (sid, b, name, float(v.min()))


def test_finite_fault_horizons_are_single_surfaces(case):
    """A finite fault splits no horizon: one surface with a slit, or uncut."""
    built, res = case
    if built.spec.name != "fault_tip_step":
        pytest.skip("no finite fault")
    for sid, m in res.horizons.items():
        mesh = m.to_pv()
        assert mesh.connectivity().point_data["RegionId"].max() == 0, sid
        loops = mesh.extract_feature_edges(boundary_edges=True, feature_edges=False,
                                           manifold_edges=False, non_manifold_edges=False)
        n_loops = loops.connectivity().point_data["RegionId"].max() + 1
        assert n_loops in (1, 2), (sid, n_loops)  # domain boundary, plus the slit
    # the top horizon is above the tip: no slit
    top = res.horizons[sorted(res.horizons)[-1]].to_pv()
    edges = top.extract_feature_edges(boundary_edges=True, feature_edges=False,
                                      manifold_edges=False, non_manifold_edges=False)
    assert edges.connectivity().point_data["RegionId"].max() == 0


def test_unsupported_case_is_refused():
    with pytest.raises(NotImplementedError, match="displaced"):
        build_conforming(build_case(get_case("crossing_faults")), resolution=17)


def test_split_t_junctions_inserts_master_vertex():
    # one triangle; its boundary edge (0,1) has a master vertex at its middle
    m = Tri(np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0]]), np.array([[0, 1, 2]]))
    master = Tri(np.array([[0.5, 0, 0], [0.5, -1, 0], [0.5, 0, 1]]), np.array([[0, 1, 2]]))
    out = split_t_junctions(m, master)
    assert len(out.tris) == 2
    assert any(np.array_equal(p, [0.5, 0, 0]) for p in out.points)
    p = out.points
    area = 0.5 * np.linalg.norm(np.cross(p[out.tris[:, 1]] - p[out.tris[:, 0]],
                                         p[out.tris[:, 2]] - p[out.tris[:, 0]]), axis=1)
    assert np.isclose(area.sum(), 0.5)


def test_insert_points_on_interior_edge():
    # two triangles share the edge (1,2); a point at its middle splits both
    m = Tri(np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0], [1.0, 1, 0]]),
            np.array([[0, 1, 2], [1, 3, 2]]))
    out = insert_points_on_edges(m, np.array([[0.5, 0.5, 0.0], [0.0, 0.0, 0.0]]))
    assert any(np.array_equal(p, [0.5, 0.5, 0.0]) for p in out.points)
    assert len(out.points) == 4 + 1 + 2  # the point and one centroid per triangle
    p = out.points
    n = np.cross(p[out.tris[:, 1]] - p[out.tris[:, 0]], p[out.tris[:, 2]] - p[out.tris[:, 0]])
    assert np.all(n[:, 2] > 0)  # orientation kept, no degenerate triangle
    assert np.isclose(0.5 * n[:, 2].sum(), 1.0)
