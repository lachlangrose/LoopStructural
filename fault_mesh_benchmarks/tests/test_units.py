"""Fast unit tests that do not build a LoopStructural model."""

import numpy as np
import pytest

from fault_benchmarks.cases import CASES, get_case
from fault_benchmarks.fields import forced_sides
from fault_benchmarks.spec import dip_vectors
from fault_benchmarks.surfaces import (
    clip,
    contour,
    domain_constraints,
    mesh_quality,
    tag_boundary,
    unit_grid,
)


def test_dip_vectors_are_orthonormal_and_oriented():
    n, d, s = dip_vectors(60, 90)
    m = np.stack([n, d, s])
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)
    assert n[2] > 0 and d[2] < 0 and d[0] > 0  # dips toward +x
    assert np.isclose(np.degrees(np.arccos(n[2])), 60)


@pytest.mark.parametrize("name", sorted(CASES))
def test_cases_are_well_formed(name):
    case = get_case(name)
    order = [f.name for f in case.fault_build_order()]
    assert sorted(order) == sorted(f.name for f in case.faults)
    for f in case.faults:
        for dep in f.faulted_by:
            assert order.index(dep) < order.index(f.name)
        assert np.isclose(np.dot(f.normal, f.slip), 0, atol=1e-6), "slip must lie in the fault"
    for s in case.series:
        assert set(s.faults) <= set(order)
        assert list(s.isovalues) == sorted(s.isovalues)


class _Feature:
    def __init__(self, values):
        self.values = values

    def evaluate_value(self, pos, ignore_regions=False):
        return np.array(self.values, dtype=float)


class _Fault:
    def __init__(self, values):
        self.features = [_Feature(values)]

    def __getitem__(self, i):
        return self.features[i]


def test_forced_sides_mirrors_and_restores_nested():
    f = _Fault([-0.5, 0.25, np.nan])
    pts = np.zeros((3, 3))
    with forced_sides({f: 1}):
        assert np.allclose(f[0].evaluate_value(pts)[:2], [0.5, 0.25])
        assert np.isnan(f[0].evaluate_value(pts)[2])
        with forced_sides({f: -1}):
            assert np.allclose(f[0].evaluate_value(pts)[:2], [-0.5, -0.25])
        assert np.allclose(f[0].evaluate_value(pts)[:2], [0.5, 0.25])
    assert "evaluate_value" not in f[0].__dict__
    assert np.allclose(f[0].evaluate_value(pts)[:2], [-0.5, 0.25])


@pytest.mark.parametrize("method", ["marching_cubes", "marching_tetrahedra"])
def test_contour_clip_and_tag_plane(method):
    grid = unit_grid(21)
    z = np.asarray(grid.points)[:, 2]
    surf = contour(grid, z, 0.43, method)
    q = mesh_quality(surf)
    assert np.isclose(q["area"], 1.0, atol=1e-9)
    assert q["nonmanifold_edges"] == 0

    def cut(p):
        return 0.6 - p[:, 0] - 0.2 * p[:, 1]  # oblique "fault" trace

    part = clip(surf, cut)
    assert np.isclose(mesh_quality(part)["area"], 0.6 - 0.1, atol=1e-9)
    from fault_benchmarks.surfaces import Constraint

    cons = [Constraint("fault:test", cut, "fault")] + domain_constraints()
    edges, tags, dist, _ = tag_boundary(part, cons, tol=0.5 / 20)
    assert "free" not in tags
    assert set(tags) == {"fault:test", "domain:xmin", "domain:ymin", "domain:ymax"}
    assert dist.max() < 1e-6  # VTK stores float32 points
