"""Regression tests for the review findings of the fault block fields PR."""

import numpy as np
import pytest

from LoopStructural import GeologicalModel
from LoopStructural.modelling.features.fault._fault_function import (
    Composite,
    CubicFunction,
    FaultDisplacement,
    Ones,
    block_displacement,
)
from LoopStructural.utils._fault_block import force_side
from LoopStructural.utils.regions import NegativeRegion
from tests.fixtures.fault_models import add_fault, add_layers, interior_points


@pytest.fixture(scope="module")
def displaced_abutting():
    """G displaces H and F; F abuts H on its negative side."""
    model = GeologicalModel([0, 0, 0], [1, 1, 1])
    g = add_fault(model, "G", (0.65, 0.5, 0.5), 65, 270, 0.12)
    h = add_fault(model, "H", (0.5, 0.5, 0.5), 80, 0, 0.1, faults=[g])
    f = add_fault(model, "F", (0.4, 0.3, 0.5), 70, 90, 0.1, faults=[g])
    region = f.add_abutting_fault(h, positive=False)
    return model, g, h, f, region


def test_unconformity_truncation_keeps_the_abutting_region():
    model = GeologicalModel([0, 0, 0], [1, 1, 1])
    host = add_fault(model, "host", (0.5, 0.5, 0.5), 80, 0, 0.1)
    fault = add_fault(model, "abutting", (0.4, 0.3, 0.5), 70, 90, 0.1)
    region = fault.add_abutting_fault(host, positive=False)
    series = add_layers(model, [], n=200)
    uc = model.add_unconformity(series, 0.5)
    gx_regions = fault[0].regions
    assert any(r is uc for r in gx_regions)
    assert any(r is region for r in gx_regions)
    # the coordinates that had no abutting region get only the unconformity
    assert not any(r is region for r in fault[1].regions)
    assert any(r is uc for r in fault[1].regions)
    # adding the same region again does not add it twice
    fault.add_region(uc)
    assert sum(r is uc for r in fault[0].regions) == 1
    assert sum(r is uc for r in fault.regions) == 1


def test_abutting_region_does_not_restore_twice(displaced_abutting):
    _, g, h, _, region = displaced_abutting
    assert isinstance(region, NegativeRegion)
    restored = g.apply_to_points(interior_points(2000))
    expected = h[0].evaluate_value(restored, restored_through=(g,))
    ok = ~np.isnan(expected)
    got = region(restored, restored_through=(g,))
    np.testing.assert_array_equal(got[ok], expected[ok] < 0)


def test_gradient_side_test_does_not_restore_twice(displaced_abutting, monkeypatch):
    model, g, _, f, _ = displaced_abutting
    series = add_layers(model, [f, g], n=300)
    calls = []
    gx = f[0]
    original = gx.evaluate_value

    def spy(pos, *args, **kwargs):
        calls.append(kwargs.get("restored_through", ()))
        return original(pos, *args, **kwargs)

    monkeypatch.setattr(gx, "evaluate_value", spy)
    restored = g.apply_to_points(interior_points(50))
    series.evaluate_gradient(restored, restored_through=(g,))
    assert calls, "the side test did not evaluate the fault"
    assert all(any(r is g for r in c) for c in calls)


def overdetermined_cubic():
    c = CubicFunction()
    for x, y in ((-1, 0), (0, 1), (1, 0), (0.5, 0.9)):
        c.add_cstr(x, y)
    c.add_grad(0, 0)
    c.add_min(-1)
    c.add_max(1)
    return c


def test_cubic_is_continuous_at_its_limits():
    c = overdetermined_cubic()
    for end in (1.0, -1.0):
        inside, at, beyond = c(np.array([end * (1 - 1e-9), end, end * 2]))
        assert at == pytest.approx(inside, abs=1e-7)
        assert beyond == at


def test_cubic_that_fits_a_zero_end_is_exactly_zero_beyond_it():
    c = CubicFunction()
    for x, y in ((-1, 0), (0, 1), (1, 0)):
        c.add_cstr(x, y)
    c.add_grad(0, 0)
    c.add_min(-1)
    c.add_max(1)
    assert np.all(c(np.array([1.0, 1.5, -1.0, -3.0])) == 0.0)
    assert c.tip_ends == (1, -1)


def bump(end):
    c = CubicFunction()
    c.add_cstr(0, 1)
    c.add_cstr(end, 0)
    c.add_grad(0, 0)
    c.add_grad(end, 0)
    c.add_min(-1)
    c.add_max(1)
    return c


def test_composite_tip_ends_come_from_its_parts():
    assert Composite(bump(1), bump(-1)).tip_ends == (1, -1)
    assert Composite(bump(1), Ones()).tip_ends == (1,)
    assert Composite(Ones(), Ones()).tip_ends == ()
    fd = FaultDisplacement(gx=Ones(), gy=Composite(bump(1), bump(-1)), gz=Ones())
    assert fd.tip_ends[1] == (1, -1)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("offset", [0.1, -0.1])
def test_block_displacement_with_an_offset_is_continuous(side, offset):
    prof = CubicFunction()
    for x, y in ((-1, 0), (0, 1), (1, 0)):
        prof.add_cstr(x, y)
    prof.add_grad(0, 0.5)
    prof.add_min(-1)
    prof.add_max(1)
    ff = FaultDisplacement(gx=prof, gy=Ones(), gz=Ones())
    gx = np.linspace(-0.3, 0.3, 6001)
    one = np.ones_like(gx)
    d = block_displacement(ff, gx, force_side(gx, side), one, one, side, offset=offset)
    assert np.max(np.abs(np.diff(d))) < 1e-3
    # on the block's own side the profile is the shifted profile itself
    own = side * gx > 1e-6
    np.testing.assert_allclose(d[own], ff(gx[own] + offset, one[own], one[own]))


def test_relations_do_not_list_the_series_as_truncated_by_its_own_unconformity():
    model = GeologicalModel([0, 0, 0], [1, 1, 1])
    series = add_layers(model, [], n=100)
    model.add_unconformity(series, 0.5)
    rel = model.get_feature_relations()
    (uc,) = rel["unconformities"].values()
    assert series.name not in uc["truncates"]
