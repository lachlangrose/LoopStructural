from __future__ import annotations

import numpy as np

from loop_common.observations import PointSet
from loop_engine.core.model import Model
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
    assert first_payload["linked_data"].point_constraints.shape == (1, 3)
    assert first_payload["linked_data"].gradient_constraints.shape == (0, 6)
