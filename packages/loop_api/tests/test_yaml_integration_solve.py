from __future__ import annotations

from pathlib import Path

import numpy as np

from loop_api import solve, to_model, to_project


FIXTURES = Path(__file__).parent / "fixtures"


def test_yaml_to_project_builds_units_faults_and_topology():
    project = to_project(FIXTURES / "model.yaml", validation_mode="strict")
    schema = project.schema

    feature_names = {feature.name for feature in schema.features.values()}
    assert {"Lower", "Upper", "Main Fault"}.issubset(feature_names)

    relations = list(schema.dag.edges(data=True))
    relation_types = {str(data.get("relation")).split(".")[-1].lower() for _, _, data in relations}
    assert "faults" in relation_types
    assert "overlies" in relation_types


def test_yaml_to_model_and_solve_runs_end_to_end():
    result = solve(FIXTURES / "model.yaml", validation_mode="strict")
    model = result["model"]
    state = result["state"]

    assert state is not None
    assert len(state.results) >= 2

    values = model.evaluate_scalar_field(
        positions=np.array([[0.25, 0.25, 0.0], [0.75, 0.75, 1.0]]),
        feature_name="Upper",
    )
    assert values.shape == (2,)
    assert np.all(np.isfinite(values))


def test_to_model_uses_solve_options():
    model = to_model(FIXTURES / "model.yaml", validation_mode="strict")
    assert model.interpolatortype == "FDI"
    assert model.nelements == 200


def test_to_model_supports_series_strategy_and_unit_metadata():
    payload = {
        "solve": {
            "interpolatortype": "FDI",
            "nelements": 120,
            "interpolation_strategy": {
                "mode": "shared_scalar_field",
                "series_config": {
                    "default": {
                        "series_band_mode": "cumulative_thickness",
                        "series_thickness_source": "unit_metadata",
                    }
                },
            },
        },
        "observations": [
            {"id": "o1", "type": "pointset", "inline": {"coords": [[0.0, 0.0, 0.0]]}},
            {"id": "o2", "type": "pointset", "inline": {"coords": [[1.0, 0.0, 1.0]]}},
        ],
        "features": [
            {
                "id": "u_old",
                "type": "unit",
                "name": "Old",
                "thickness": 15.0,
                "metadata": {"thickness": 20.0},
                "data_links": {"basal": ["o1"]},
            },
            {
                "id": "u_young",
                "type": "unit",
                "name": "Young",
                "metadata": {"thickness": 5.0},
                "data_links": {"basal": ["o2"]},
            },
        ],
        "topology": [{"type": "overlies", "master": "u_young", "slave": "u_old"}],
    }

    model = to_model(payload, validation_mode="strict")
    assert isinstance(model.interpolation_strategy, dict)
    assert model.interpolation_strategy["mode"] == "shared_scalar_field"

    old_feature = model.schema.get_feature_by_name("Old")
    assert old_feature is not None
    assert old_feature.thickness == 15.0
    assert old_feature.metadata["thickness"] == 20.0


def test_two_series_fixture_applies_distinct_series_overrides_and_solves():
    fixture = FIXTURES / "model_two_series.yaml"
    model = to_model(fixture, validation_mode="strict")

    tasks = model._compile_tasks()
    by_id = {task.id: task for task in tasks}

    a_older = model.schema.get_feature_by_name("A_Older")
    a_younger = model.schema.get_feature_by_name("A_Younger")
    b_older = model.schema.get_feature_by_name("B_Older")
    b_younger = model.schema.get_feature_by_name("B_Younger")

    assert a_older is not None
    assert a_younger is not None
    assert b_older is not None
    assert b_younger is not None

    a_old_interp = by_id[a_older.uuid].interpretation
    a_young_interp = by_id[a_younger.uuid].interpretation
    b_old_interp = by_id[b_older.uuid].interpretation
    b_young_interp = by_id[b_younger.uuid].interpretation

    assert a_old_interp["basal_isovalue"] == 0.0
    assert a_old_interp["top_isovalue"] == 10.0
    assert a_young_interp["basal_isovalue"] == 10.0
    assert a_young_interp["top_isovalue"] == 16.0

    assert b_old_interp["basal_isovalue"] == 100.0
    assert b_old_interp["top_isovalue"] == 104.0
    assert b_young_interp["basal_isovalue"] == 104.0
    assert b_young_interp["top_isovalue"] == 106.5

    result = solve(fixture, validation_mode="strict")
    solved_model = result["model"]
    state = result["state"]

    solved_a_older = solved_model.schema.get_feature_by_name("A_Older")
    solved_a_younger = solved_model.schema.get_feature_by_name("A_Younger")
    solved_b_older = solved_model.schema.get_feature_by_name("B_Older")
    solved_b_younger = solved_model.schema.get_feature_by_name("B_Younger")

    assert solved_a_older is not None
    assert solved_a_younger is not None
    assert solved_b_older is not None
    assert solved_b_younger is not None

    a_old_rep = state.get_feature(solved_a_older.uuid).representation
    a_young_rep = state.get_feature(solved_a_younger.uuid).representation
    b_old_rep = state.get_feature(solved_b_older.uuid).representation
    b_young_rep = state.get_feature(solved_b_younger.uuid).representation

    assert a_old_rep is a_young_rep
    assert b_old_rep is b_young_rep
    assert a_old_rep is not b_old_rep

    values_a = solved_model.evaluate_scalar_field(
        positions=np.array([[0.2, 0.2, 0.5], [0.3, 0.3, 1.0]]),
        feature_name="A_Younger",
    )
    values_b = solved_model.evaluate_scalar_field(
        positions=np.array([[0.7, 0.7, 2.5], [0.8, 0.8, 3.0]]),
        feature_name="B_Younger",
    )
    assert np.all(np.isfinite(values_a))
    assert np.all(np.isfinite(values_b))
