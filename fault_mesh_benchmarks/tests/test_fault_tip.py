"""A finite fault: the fault ends on a tip loop inside the volume.

Expected topology: the fault surface is bounded by a tip curve; every horizon
is one connected surface; a horizon that the fault cuts has a slit (two
cut-off curves) and a horizon that the fault does not reach has no internal
boundary at all.
"""

import pytest

from fault_benchmarks.builder import build_case
from fault_benchmarks.cases import get_case
from fault_benchmarks.generate import Options, generate_case


@pytest.fixture(scope="module")
def tip(tmp_path_factory):
    out = tmp_path_factory.mktemp("bench")
    built = build_case(get_case("fault_tip"))
    return generate_case(built, out, Options(resolution=41, volume_resolution=17, formats=("vtp",)))


def test_qa_passes(tip):
    assert tip["qa"]["passed"], tip["qa"]


def test_fault_surface_ends_on_tip_loop(tip):
    fault = next(s for s in tip["surfaces"] if s["kind"] == "fault")
    tags = fault["boundary_length_by_tag"]
    assert set(tags) == {"tip:f1"}  # no domain boundary: the fault is inside the cube
    lo, hi = tip["faults"][0]["surface_bbox"]
    assert lo[1] == pytest.approx(0.15, abs=0.03) and hi[1] == pytest.approx(0.85, abs=0.03)


def test_horizons_are_single_surfaces(tip):
    horizons = [s for s in tip["surfaces"] if s["kind"] == "horizon"]
    assert len(horizons) == 4
    for s in horizons:
        assert s["connected_pieces"] == 1, s["id"]


def test_uncut_horizon_has_no_internal_boundary(tip):
    top = next(s for s in tip["surfaces"] if s["id"] == "horizon_strat_3")  # z = 0.8, above tip
    assert all(k.startswith("domain") for k in top["boundary_length_by_tag"])


def test_cut_horizon_has_slit_with_offset(tip):
    s = next(s for s in tip["surfaces"] if s["id"] == "horizon_strat_2")
    tags = s["boundary_length_by_tag"]
    assert tags["cutoff:f1"] > 1.0  # hanging-wall and footwall cut-offs
    assert tags.get("seam:f1", 0.0) < 0.1 * tags["cutoff:f1"]
