from __future__ import annotations

import pytest

from loop_common.base import LoopEntity
from loop_model.manager import GeologicalSchema, LoopProject


class DummyObservation(LoopEntity):
    pass


def test_schema_initialize_project_creates_and_links_project():
    schema = GeologicalSchema(name="SchemaOnly")

    project = schema.initialize_project()

    assert isinstance(project, LoopProject)
    assert schema.project is project
    assert project.schema is schema


def test_add_unit_requires_project_before_registering_observations():
    schema = GeologicalSchema(name="SchemaOnly")
    obs = DummyObservation(name="o1")

    with pytest.raises(RuntimeError, match="Schema has no project"):
        schema.add_unit("U1", basal_contacts=[obs])


def test_add_unit_registers_observations_after_schema_initializes_project():
    schema = GeologicalSchema(name="SchemaOnly")
    project = schema.initialize_project()
    obs = DummyObservation(name="o1")

    unit = schema.add_unit("U1", top_contacts=[obs])

    assert obs.uuid in project.observations
    assert project.observations[obs.uuid] is obs
    assert unit.uuid in schema.features
