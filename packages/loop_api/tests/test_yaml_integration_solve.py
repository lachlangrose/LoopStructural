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
