from __future__ import annotations

import numpy as np

from loop_common.observations import Orientation, PointSet
from loop_engine.core.geological_feature import GeologicalFeature
from loop_engine.core.model import Model
from loop_engine.core.state import ModelState
from loop_model.manager import GeologicalSchema


def test_model_compiles_tasks_in_schema_order_and_links_data():
    schema = GeologicalSchema(name="CompileSchema")
    schema.initialize_project()

    older = schema.add_unit("Older", basal_contacts=[PointSet(coords=np.array([[0.0, 0.0, 0.0]]))])
    younger = schema.add_unit(
        "Younger", basal_contacts=[PointSet(coords=np.array([[1.0, 0.0, 0.0]]))]
    )

    schema.add_conformable_overlies_relation(master_uuid=younger.uuid, slave_uuid=older.uuid)

    model = Model(schema=schema)
    tasks = model._compile_tasks()

    assert [task.id for task in tasks] == [younger.uuid, older.uuid]
    assert tasks[0].predecessors == []
    assert tasks[1].predecessors == [younger.uuid]

    first_payload = tasks[0].execute([])
    linked_data = first_payload["linked_data"]
    assert "basal" in linked_data.by_role
    assert len(linked_data.by_role["basal"]) == 1
    assert linked_data.by_role["basal"][0].observation_type == "PointSet"


class _MockSolvedFeature:
    def evaluate_value(self, positions):
        positions = np.asarray(positions)
        return positions[:, 2] + 1.0

    def surfaces(self, value):
        return {"iso": value, "mesh": "mock"}


def test_model_evaluate_scalar_field_by_feature_name():
    schema = GeologicalSchema(name="EvaluateByName")
    schema.initialize_project()
    unit = schema.add_unit("Unit A")

    model = Model(schema=schema)
    model.current_state = ModelState(grid=None)
    model.current_state.results[unit.uuid] = _MockSolvedFeature()

    values = model.evaluate_scalar_field(
        positions=np.array([[0.0, 0.0, 2.0], [1.0, 0.0, 3.0]]),
        feature_name="Unit A",
    )

    assert np.allclose(values, np.array([3.0, 4.0]))


def test_model_extract_unit_basal_surface_defaults_to_zero():
    schema = GeologicalSchema(name="ExtractBasal")
    schema.initialize_project()
    unit = schema.add_unit("Unit A")

    model = Model(schema=schema)
    model.current_state = ModelState(grid=None)
    model.current_state.results[unit.uuid] = _MockSolvedFeature()

    basal = model.extract_unit_basal_surface(feature_name="Unit A")

    assert basal["iso"] == 0.0
    assert basal["mesh"] == "mock"


def test_model_solve_wires_schema_to_interpolator():
    """End-to-end: schema → Model.solve() → evaluate_scalar_field."""
    xy = np.random.default_rng(42).uniform(0, 1, (5, 2))

    schema = GeologicalSchema(name="WireTest")
    schema.initialize_project()

    bottom = schema.add_unit(
        "Bottom",
        basal_contacts=[PointSet(name="c0", coords=np.hstack([xy, np.zeros((5, 1))]))],
        orientations=[
            Orientation(
                name="o0",
                coords=np.array([[0.5, 0.5, 0.0]]),
                vector=np.array([[0.0, 0.0, 1.0]]),
                magnitude=np.array([1.0]),
                polarity=np.array([1.0]),
                type="plane",
            )
        ],
    )
    top = schema.add_unit(
        "Top",
        basal_contacts=[PointSet(name="c1", coords=np.hstack([xy, np.ones((5, 1))]))],
    )
    schema.add_conformable_overlies_relation(master_uuid=top.uuid, slave_uuid=bottom.uuid)

    model = Model(schema=schema, interpolatortype="FDI", nelements=200)
    state = model.solve()

    # Each unit should have a solved interpolator stored
    assert state.get_feature(bottom.uuid) is not None
    assert state.get_feature(top.uuid) is not None

    # Retrieval API returns a GeologicalFeature wrapper for downstream operations.
    solved_top_feature = model.get_solved_feature(feature_name="Top")
    assert isinstance(solved_top_feature, GeologicalFeature)

    # Scalar values should be evaluable at points inside each unit's domain.
    # "Bottom" contacts are at z=0, so query near those contacts.
    bottom_pts = np.array([[xy[0, 0], xy[0, 1], 0.0], [xy[1, 0], xy[1, 1], 0.0]])
    bottom_values = model.evaluate_scalar_field(feature_name="Bottom", positions=bottom_pts)
    assert bottom_values.shape == (2,)
    assert np.all(np.isfinite(bottom_values))

    # "Top" contacts are at z=1, so query near those contacts.
    top_pts = np.array([[xy[0, 0], xy[0, 1], 1.0], [xy[1, 0], xy[1, 1], 1.0]])
    top_values = model.evaluate_scalar_field(feature_name="Top", positions=top_pts)
    assert top_values.shape == (2,)
    assert np.all(np.isfinite(top_values))


def test_schema_add_unit_sets_build_params_metadata():
    schema = GeologicalSchema(name="BuildParamsUnit")
    schema.initialize_project()

    unit = schema.add_unit(
        name="U1",
        build_params={"group_id": "stack-a"},
    )

    assert unit.build_params == {"group_id": "stack-a"}


def test_schema_add_fault_sets_build_params_metadata():
    schema = GeologicalSchema(name="BuildParamsFault")
    schema.initialize_project()

    fault = schema.add_fault(
        name="F1",
        displacement=100.0,
        build_params={"dip_direction": 135.0},
    )

    assert fault.build_params == {"dip_direction": 135.0}


def test_grouped_stratigraphy_strategy_solves_shared_representation():
    xy = np.random.default_rng(24).uniform(0, 1, (6, 2))

    schema = GeologicalSchema(name="GroupedStrategy")
    schema.initialize_project()
    older = schema.add_unit(
        "Older",
        basal_contacts=[PointSet(name="b0", coords=np.hstack([xy, np.zeros((6, 1))]))],
    )
    younger = schema.add_unit(
        "Younger",
        basal_contacts=[PointSet(name="b1", coords=np.hstack([xy, np.ones((6, 1))]))],
    )
    schema.add_conformable_overlies_relation(master_uuid=younger.uuid, slave_uuid=older.uuid)

    model = Model(
        schema=schema,
        interpolatortype="FDI",
        nelements=200,
        interpolation_strategy="grouped_conformable",
    )
    state = model.solve()

    younger_solved = state.get_feature(younger.uuid)
    older_solved = state.get_feature(older.uuid)

    assert younger_solved is not None
    assert older_solved is not None
    assert isinstance(younger_solved, GeologicalFeature)
    assert isinstance(older_solved, GeologicalFeature)
    assert younger_solved.representation is older_solved.representation

    pts = np.array([[xy[0, 0], xy[0, 1], 0.0], [xy[0, 0], xy[0, 1], 1.0]])
    values = model.evaluate_scalar_field(positions=pts, feature_name="Younger")
    assert values.shape == (2,)
    assert np.all(np.isfinite(values))


def test_independent_strategy_solves_units_separately():
    xy = np.random.default_rng(7).uniform(0, 1, (6, 2))

    schema = GeologicalSchema(name="IndependentStrategy")
    schema.initialize_project()
    older = schema.add_unit(
        "Older",
        basal_contacts=[PointSet(name="b0", coords=np.hstack([xy, np.zeros((6, 1))]))],
    )
    younger = schema.add_unit(
        "Younger",
        basal_contacts=[PointSet(name="b1", coords=np.hstack([xy, np.ones((6, 1))]))],
    )
    schema.add_conformable_overlies_relation(master_uuid=younger.uuid, slave_uuid=older.uuid)

    model = Model(
        schema=schema,
        interpolatortype="FDI",
        nelements=200,
        interpolation_strategy="independent",
    )
    state = model.solve()

    younger_solved = state.get_feature(younger.uuid)
    older_solved = state.get_feature(older.uuid)

    assert younger_solved is not None
    assert older_solved is not None
    assert isinstance(younger_solved, GeologicalFeature)
    assert isinstance(older_solved, GeologicalFeature)
    assert younger_solved.representation is not older_solved.representation
