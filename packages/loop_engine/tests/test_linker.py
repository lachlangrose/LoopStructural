from __future__ import annotations

import numpy as np

from loop_common.observations import Orientation, PointSet
from loop_engine.core.linker import ObservationLinker
from loop_model.manager import GeologicalSchema


def test_linker_builds_constraints_from_feature_data_links():
    schema = GeologicalSchema(name="LinkerSchema")
    project = schema.initialize_project()

    contact = PointSet(name="contact", coords=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]))
    orientation = Orientation(
        name="orientation",
        coords=np.array([[0.5, 0.5, 0.0]]),
        vector=np.array([[0.0, 0.0, 1.0]]),
        magnitude=np.array([1.0]),
        polarity=np.array([1.0]),
        type="plane",
    )

    unit = schema.add_unit(
        "U1",
        basal_contacts=[contact],
        orientations=[orientation],
    )

    linker = ObservationLinker(schema)
    linked = linker.build_feature_input(unit.uuid)

    assert linked.feature_id == unit.uuid
    assert linked.feature_name == "U1"
    assert linked.point_constraints.shape == (2, 3)
    assert linked.gradient_constraints.shape == (1, 6)
    assert linked.tangent_constraints.shape == (0, 6)
    assert linked.missing_observation_ids == []

    roles = set(linked.by_role)
    assert roles == {"basal", "orientation"}

    basal_obs = linked.by_role["basal"][0]
    assert basal_obs.obs_uid in project.observations


def test_linker_collects_missing_observation_links():
    schema = GeologicalSchema(name="MissingObs")
    schema.initialize_project()

    unit = schema.add_unit("U1")
    unit.data_links.append("does-not-exist")

    linked = ObservationLinker(schema).build_feature_input(unit.uuid)

    assert linked.missing_observation_ids == ["does-not-exist"]
    assert linked.point_constraints.shape == (0, 3)
    assert linked.gradient_constraints.shape == (0, 6)


def test_linker_preserves_inside_outside_roles():
    schema = GeologicalSchema(name="InsideOutsideRoles")
    schema.initialize_project()

    inside = PointSet(name="inside", coords=np.array([[0.0, 0.0, 0.0]]))
    outside = PointSet(name="outside", coords=np.array([[1.0, 0.0, 0.0]]))
    unit = schema.add_unit("U1", inside=[inside], outside=[outside])

    linked = ObservationLinker(schema).build_feature_input(unit.uuid)

    assert "inside" in linked.by_role
    assert "outside" in linked.by_role
    assert linked.by_role["inside"][0].obs_uid == inside.uuid
    assert linked.by_role["outside"][0].obs_uid == outside.uuid


def test_linker_builds_fault_slip_vector_role_without_uid_attribute():
    schema = GeologicalSchema(name="FaultSlipRole")
    schema.initialize_project()

    orientation = Orientation(
        name="slip",
        coords=np.array([[0.5, 0.5, 0.0]]),
        vector=np.array([[1.0, 0.0, 0.0]]),
        magnitude=np.array([1.0]),
        polarity=np.array([1.0]),
        type="plane",
    )
    fault = schema.add_fault("F1", displacement=10.0, slip_vector=[orientation])

    linked = ObservationLinker(schema).build_feature_input(fault.uuid)

    assert "slip_vector" in linked.by_role
    assert linked.by_role["slip_vector"][0].obs_uid == orientation.uuid
