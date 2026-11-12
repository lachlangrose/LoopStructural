"""Check source-independent fault kinematics and cached Mexico Basin inputs."""

import importlib.util
import sys
from pathlib import Path
from tempfile import gettempdir
from types import SimpleNamespace

import numpy as np
import pytest

from LoopStructural.modelling.features import AnalyticalGeologicalFeature
from LoopStructural.modelling.features.fault import FaultDisplacement, FaultSegment


@pytest.fixture(scope="module")
def example():
    path = Path(__file__).parents[2] / "examples/5_case_studies/plot_2_mexico_basin.py"
    spec = importlib.util.spec_from_file_location("mexico_basin_example", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def line(label, points):
    return {"Uni": label}, np.asarray(points, dtype=float), [0]


@pytest.mark.parametrize("reverse", [False, True])
def test_cutoffs_are_independent_of_fault_digitisation_direction(example, reverse):
    fault = [(0, 1000), (200, -1000)]
    if reverse:
        fault.reverse()
    lines = [
        line("F", fault),
        line("U", [(-200, 100), (90, 100)]),
        line("U", [(110, -100), (300, -100)]),
    ]
    negative, positive, slope = example.cutoff_pair(lines, "F", "U")
    np.testing.assert_allclose(negative, [90, 100])
    np.testing.assert_allclose(positive, [110, -100])
    assert slope == 0


def test_continuous_contact_and_missing_original_fault_are_distinct(example):
    lines = [line("F", [(0, 1000), (0, -1000)]), line("U", [(-100, 100), (100, 100)])]
    negative, positive, _ = example.cutoff_pair(lines, "F", "U")
    np.testing.assert_allclose(negative, positive)
    assert example.cutoff_pair(lines, "synthetic", "U") is None


def test_estimates_preserve_zero_synthetic_and_unresolved_evidence(example):
    inputs = SimpleNamespace(
        zone="Extra",
        dips=[
            {
                "fault_id": "ToF",
                "section_id": "S",
                "distance": 0,
                "elevation": 0,
                "true_dip": 60,
                "dip_direct": 90,
            },
            {
                "fault_id": "F6",
                "section_id": "S",
                "distance": 100,
                "elevation": 0,
                "true_dip": 60,
                "dip_direct": 90,
            },
        ],
        traces={"S": np.array([[500000.0, 2100000], [501000.0, 2100000]])},
        sections={
            "S": [
                line("ToF", [(0, 1000), (0, -1000)]),
                line("Neogene_Volcanic", [(-100, 0), (100, 0)]),
            ]
        },
    )
    picks = example.estimate_displacements(inputs)
    assert set(picks.loc[picks.fault == "F6", "status"]) == {"synthetic_zero"}
    assert (
        picks.loc[(picks.fault == "ToF") & (picks.unit == "Neogene_Volcanic"), "status"].item()
        == "continuous"
    )
    assert (
        picks.loc[(picks.fault == "ToF") & (picks.unit == "Paleogene_Volcanic"), "status"].item()
        == "unresolved"
    )
    assert (picks.slip_m == 0).all()


def test_restoration_uses_dip_slip_and_accounts_for_heave(example):
    normal = example.pole([60], [90])[0]
    updip = np.array([0, 0, 1]) - normal[2] * normal
    updip /= np.linalg.norm(updip)
    np.testing.assert_allclose(np.dot(normal, updip), 0, atol=1e-12)
    negative = np.array([500000, 2100000, 1000.0])
    positive = negative - 200 * updip
    bedding_normal = np.array([-0.2, 0, 1])
    assert example.restoration_slip(negative, positive, bedding_normal, updip) == pytest.approx(200)
    assert example.restoration_slip(positive, negative, bedding_normal, updip) == pytest.approx(
        -200
    )
    assert 200 * updip[2] != pytest.approx(200)  # throw is not net slip


def test_profile_tapers_and_keeps_signed_zero_sections(example):
    profile = example.StrikeProfile(np.array([0.0, 1000, 2000]), np.array([-1.0, 0, 0.5]))
    np.testing.assert_allclose(
        profile([-6000, -5000, -2500, 0, 1000, 2000, 7000, 8000]), [0, 0, -0.5, -1, 0, 0.5, 0, 0]
    )


@pytest.mark.parametrize("signed_ratio", [-1.0, 0.0, 1.0])
@pytest.mark.parametrize("steps", [1, 10])
def test_actual_fault_operator_has_correct_direction_and_net_magnitude(
    example, signed_ratio, steps
):
    normal = example.pole([60], [90])[0]
    updip = np.array([0.0, 0, 1]) - normal[2] * normal
    updip /= np.linalg.norm(updip)
    strike = np.cross(normal, updip)
    origin = np.array([500000.0, 2100000.0, 1000])
    features = [
        AnalyticalGeologicalFeature("plane", normal, origin),
        AnalyticalGeologicalFeature("updip", updip, origin),
        AnalyticalGeologicalFeature("strike", strike, origin),
    ]
    event = FaultSegment("test", features, displacement=100, steps=steps)
    event.faultfunction = FaultDisplacement(
        gx=example.positive_wall,
        gz=example.StrikeProfile(np.array([-100, 100]), np.array([signed_ratio, signed_ratio])),
        scale=1.0,
    )
    points = origin + np.array([-1, 1])[:, None] * normal
    moved = event.apply_to_points(points) - points
    np.testing.assert_allclose(moved[0], 0, atol=1e-8)
    np.testing.assert_allclose(moved[1], signed_ratio * 100 * updip, atol=1e-8)
    np.testing.assert_allclose(
        event.apply_to_points(points, reverse=True) - points, -moved, atol=1e-8
    )


def test_offline_run_cannot_silently_download(example, tmp_path):
    with pytest.raises(FileNotFoundError, match="not cached"):
        example.load_inputs(directory=tmp_path, offline=True)


def test_corrupt_cached_archive_is_rejected(example, tmp_path):
    (tmp_path / f"{example.COMMIT}.zip").write_bytes(b"not the source archive")
    with pytest.raises(ValueError, match="differs from the pinned source"):
        example.load_inputs(directory=tmp_path, offline=True)


def test_cached_real_model_has_finite_fields_and_consistent_unit_ids(example):
    cache = Path(gettempdir()) / "loopstructural-examples/mexico-basin"
    if not (cache / f"{example.COMMIT}.zip").exists():
        pytest.skip("Optional real-data check: download the pinned dataset by running the example")
    pytest.importorskip("shapefile")
    pytest.importorskip("tifffile")
    inputs = example.load_inputs(offline=True)
    model, picks, events = example.build_model(inputs, nelements=3000)
    points = inputs.origin + np.random.default_rng(17).uniform(0.05, 0.95, (100, 3)) * (
        inputs.maximum - inputs.origin
    )
    fields, ids = example.sample_fields(
        model, points, example.ZONES[inputs.zone][0], mask_terrain=False
    )
    assert np.isfinite(np.column_stack(list(fields.values()))).all()
    np.testing.assert_array_equal(ids, model.evaluate_model(points))
    assert len(set(ids)) >= 3
    assert (picks.loc[picks.status == "synthetic_zero", "slip_m"] == 0).all()
    checks = example.displacement_checks(model, inputs, picks, events)
    assert len(checks) > 20
    assert checks.vector_error_m.max() < 1e-5
    assert checks.actual_throw_m.abs().max() > 100
    assert all(geometry.displacement == 0 for geometry in model.faults)
