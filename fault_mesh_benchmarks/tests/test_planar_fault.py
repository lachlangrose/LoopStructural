"""End-to-end check of the planar fault case against analytic geometry.

The case has an exact solution: a 60 deg fault through (0.5, 0.5, 0.5)
dipping toward +x, horizontal horizons z = c, and a rigid hanging-wall
movement of 0.15 down-dip (vertical throw 0.15 sin 60).
"""

import json

import numpy as np
import pytest

from fault_benchmarks.builder import build_case
from fault_benchmarks.cases import get_case
from fault_benchmarks.generate import Options, generate_case

DIP = np.radians(60)
D = 0.15


def fault_x(z):
    return 0.5 + (0.5 - z) / np.tan(DIP)


@pytest.fixture(scope="module")
def planar(tmp_path_factory):
    out = tmp_path_factory.mktemp("bench")
    built = build_case(get_case("planar_fault"))
    meta = generate_case(built, out, Options(resolution=41, volume_resolution=17, formats=("vtp",)))
    return out / "planar_fault", meta


def test_qa_passes(planar):
    _, meta = planar
    assert meta["qa"]["passed"], meta["qa"]


def test_metadata_round_trips(planar):
    path, meta = planar
    on_disk = json.loads((path / "metadata.json").read_text())
    assert on_disk["case"] == "planar_fault"
    assert (path / "volume" / "implicit_fields.vtu").exists()
    assert (path / "constraints" / "constraint_curves.vtp").exists()


def test_fault_area_and_slip(planar):
    _, meta = planar
    fault = next(s for s in meta["surfaces"] if s["kind"] == "fault")
    assert fault["quality"]["area"] == pytest.approx(1 / np.sin(DIP), rel=1e-6)
    f = meta["faults"][0]
    assert f["slip_jump_on_surface"]["max"] == pytest.approx(D, rel=1e-3)
    mv = np.array(f["slip_jump_on_surface"]["mean_vector"])
    assert np.allclose(mv, D * np.array([np.cos(DIP), 0, -np.sin(DIP)]), atol=1e-4)


@pytest.mark.parametrize("k,c", list(enumerate([0.25, 0.45, 0.65, 0.8])))
def test_horizon_patch_areas(planar, k, c):
    _, meta = planar
    surf = next(s for s in meta["surfaces"] if s["id"] == f"horizon_strat_{k}")
    area = {b["label"]: b["area"] for b in surf["blocks"]}
    assert surf["connected_pieces"] == 2  # an infinite fault separates the blocks
    fw, hw = area["f1-"], area["f1+"]
    assert fw == pytest.approx(fault_x(c), abs=2e-3)
    assert hw == pytest.approx(1 - fault_x(c - D * np.sin(DIP)), abs=2e-3)


def test_cutoffs_are_sharp_and_at_fault_dip(planar):
    _, meta = planar
    cut = [c for c in meta["constraints"] if c["kind"] == "cutoff"]
    assert len(cut) == 8  # 4 horizons x 2 blocks
    for c in cut:
        assert c["sharp"]
        assert c["length"] == pytest.approx(1.0, rel=1e-6)
        assert c["dihedral_deg"]["mean"] == pytest.approx(60, abs=0.5)
        assert c["slip_jump"]["min"] == pytest.approx(D, rel=1e-3)
