from __future__ import annotations

import pytest

from gmdg.cli import main as cli_main
from gmdg.models import GeologicalModelGraph, GeologicalObservationSet, ScalarFeature


def _build_simple_model() -> tuple[GeologicalModelGraph, str, str]:
    g = GeologicalModelGraph.create("RegressionModel", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])
    scalar_id = g.add_scalar_feature(
        "Strati",
        role="stratigraphic",
        source={"kind": "interpolated", "method": "discrete", "constraints": {"gradient": "obs.csv"}},
    )
    unit_id = g.add_unit("UnitA", representation={"scalar_feature_id": scalar_id, "interval": [0.0, 10.0]})
    g.add_unit("UnitB", representation={"scalar_feature_id": scalar_id, "interval": [10.0, 20.0]})
    return g.build(), unit_id, scalar_id


def test_unit_representation_roundtrip_json_and_yaml(tmp_path):
    g, uid, sid = _build_simple_model()

    json_path = tmp_path / "model.json"
    yaml_path = tmp_path / "model.yaml"

    g.save(str(json_path))
    g.save_yaml(str(yaml_path))

    g_json = GeologicalModelGraph.load(str(json_path))
    g_yaml = GeologicalModelGraph.load_yaml(str(yaml_path))

    assert type(g_json.features[uid]).__name__ == "Unit"
    assert type(g_yaml.features[uid]).__name__ == "Unit"
    assert g_json.features[uid].representation is not None
    assert g_yaml.features[uid].representation is not None
    assert g_json.features[uid].representation.interval == (0.0, 10.0)
    assert g_yaml.features[uid].representation.interval == (0.0, 10.0)
    assert isinstance(g_json.features[sid], ScalarFeature)


def test_cli_validate_accepts_yaml(tmp_path, capsys):
    g, _, _ = _build_simple_model()
    yaml_path = tmp_path / "cli_model.yaml"
    g.save_yaml(str(yaml_path))

    with pytest.raises(SystemExit) as exc:
        cli_main(["validate", str(yaml_path)])

    out = capsys.readouterr()
    assert exc.value.code == 0
    assert "OK: model is valid" in out.out


def test_get_array_supports_csv(tmp_path):
    pd = pytest.importorskip("pandas")

    csv_path = tmp_path / "obs.csv"
    pd.DataFrame({"x": [0.0], "y": [0.0], "z": [0.0], "value": [1.0]}).to_csv(csv_path, index=False)

    obs = GeologicalObservationSet(id="o_csv", kind="gradient", target="scalar", uri=str(csv_path))
    arr = obs.get_array()

    assert arr is not None
    assert len(arr) == 1


def test_get_array_supports_parquet(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    pq_path = tmp_path / "obs.parquet"
    pd.DataFrame({"x": [1.0], "y": [2.0], "z": [3.0], "value": [4.0]}).to_parquet(pq_path, index=False)

    obs = GeologicalObservationSet(id="o_parquet", kind="gradient", target="scalar", uri=str(pq_path))
    arr = obs.get_array()

    assert arr is not None
    assert len(arr) == 1


def test_observation_sets_are_attached_to_target_nodes():
    g = GeologicalModelGraph.create("ObsTargets", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])
    sid = g.add_scalar_feature(
        "Strati",
        role="stratigraphic",
        source={"kind": "interpolated", "method": "discrete", "constraints": {"gradient": "obs.csv"}},
    )

    obs_id = g.add_geological_observation_set(
        kind="gradient",
        target=sid,
        uri="data/gradients.csv",
        columns={"x": "x", "y": "y", "z": "z", "value": "gz"},
        count=3,
    )

    assert g.features[sid].observation_ids == [obs_id]
    assert g.node_observations(sid)[obs_id].target == sid


def test_observation_sets_backfill_node_links_on_load():
    model = GeologicalModelGraph.model_validate(
        {
            "name": "BackfillObs",
            "space": {"crs": "EPSG:28355", "bbox": [0, 0, -100.0, 100.0, 100.0, 10.0], "units": "m"},
            "features": {
                "Strati": {
                    "id": "Strati",
                    "name": "Strati",
                    "type": "scalar_feature",
                    "role": "stratigraphic",
                    "source": {"kind": "parametric", "function": "z", "parameters": {}},
                }
            },
            "geo_observations": {
                "gobs_gradient": {
                    "id": "gobs_gradient",
                    "kind": "gradient",
                    "target": "Strati",
                    "uri": "data/gradients.csv",
                    "columns": {"x": "x", "y": "y", "z": "z", "value": "gz"},
                    "count": 3,
                }
            },
            "relations": [],
            "events": [],
            "basement": None,
        }
    )

    assert model.features["Strati"].observation_ids == ["gobs_gradient"]
    assert set(model.node_observations("Strati")) == {"gobs_gradient"}


def test_observation_target_must_exist():
    g = GeologicalModelGraph.create("ObsMissingTarget", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])

    with pytest.raises(ValueError, match="Observation target 'Missing' not found"):
        g.add_geological_observation_set(
            kind="gradient",
            target="Missing",
            uri="data/gradients.csv",
        )


def test_geological_model_graph_has_nice_print_output():
    g = GeologicalModelGraph.create("PrettyPrint", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])
    sid = g.add_scalar_feature(
        "Strati",
        role="stratigraphic",
        source={"kind": "interpolated", "method": "discrete", "constraints": {"gradient": "obs.csv"}},
    )
    uid = g.add_unit("UnitA", representation={"scalar_feature_id": sid, "interval": [0.0, 10.0]})
    g.set_basement(uid)

    text = str(g)

    assert "GeologicalModelGraph(" in text
    assert "PrettyPrint" in text
    assert "EPSG:28355" in text
    assert "features:" in text
    assert "relations:" in text
    assert "basement:" in text
    assert "scalar_features=" in text


def test_stratigraphic_order_youngest_to_oldest():
    g = GeologicalModelGraph.create("StratOrder", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])
    scalar_id = g.add_scalar_feature(
        "Strati",
        role="stratigraphic",
        source={"kind": "parametric", "function": "z", "parameters": {}},
    )
    g.add_unit("Sandstone", representation={"scalar_feature_id": scalar_id, "interval": [0.0, 10.0]})
    g.add_unit("Shale", representation={"scalar_feature_id": scalar_id, "interval": [10.0, 20.0]})
    g.add_unit("Basement", representation={"scalar_feature_id": scalar_id, "interval": [20.0, 30.0]})
    g = g.build()

    assert g.stratigraphic_order() == ["Sandstone", "Shale", "Basement"]


def test_unconformity_blocks_shared_stratigraphic_scalar():
    g = GeologicalModelGraph.create("StratUnc", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])

    sid = g.add_scalar_feature(
        "Strati",
        role="stratigraphic",
        source={"kind": "parametric", "function": "z", "parameters": {}},
    )

    u_young = g.add_unit("YoungUnit", representation={"scalar_feature_id": sid, "interval": [0.0, 10.0]})
    unc = g.add_unconformity("MajorUnconformity", kind="erosional")
    u_old = g.add_unit("OldUnit", representation={"scalar_feature_id": sid, "interval": [10.0, 20.0]})

    g.remove_overlies(u_young, u_old)
    g.overlies(u_young, unc)
    g.overlies(unc, u_old)

    with pytest.raises(ValueError, match="share scalar feature"):
        g.build()


def test_auto_fault_relationships_for_subsequent_features():
    g = GeologicalModelGraph.create("AutoFault", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])
    sid = g.add_scalar_feature(
        "Strati",
        role="stratigraphic",
        source={"kind": "interpolated", "method": "discrete", "constraints": {"gradient": "obs.csv"}},
    )

    u_before = g.add_unit("BeforeFault", representation={"scalar_feature_id": sid, "interval": [0.0, 10.0]})
    fault = g.add_fault("MainFault")
    u_after = g.add_unit("AfterFault", representation={"scalar_feature_id": sid, "interval": [10.0, 20.0]})
    unc_after = g.add_unconformity("AfterFaultUnc", kind="erosional")

    g = g.build()
    pairs = {(r.kind, r.src, r.dst) for r in g.relations}

    assert ("displaces", fault, u_before) not in pairs
    assert ("displaces", fault, u_after) in pairs
    assert ("displaces", fault, unc_after) in pairs


def test_fold_history_includes_scalar_level_folding_for_units():
    g = GeologicalModelGraph.create("FoldedField", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])
    scalar_id = g.add_scalar_feature(
        "S1",
        role="stratigraphic",
        source={"kind": "parametric", "function": "z", "parameters": {}},
    )
    unit_id = g.add_unit("UnitA", representation={"scalar_feature_id": scalar_id, "interval": [0.0, 10.0]})
    fold_id = g.add_fold("F_field")

    g.add_fold_event(fold=fold_id, order=5, scalar_features=[scalar_id])
    g = g.build()

    assert g.fold_history(scalar_id) == ["F_field"]
    assert g.fold_history(unit_id) == ["F_field"]


def test_invalid_parametric_scalar_source_fails_validation():
    g = GeologicalModelGraph.create("InvalidSource", "EPSG:28355", [0, 0, -100.0, 100.0, 100.0, 10.0])
    with pytest.raises(ValueError):
        g.add_scalar_feature(
            "BadParametric",
            source={"kind": "parametric", "function": "", "parameters": {}},
        )
