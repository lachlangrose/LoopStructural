"""Create a simple layer-cake geological model example."""

import numpy as np
from loop_common.observations import PointSet
from loop_model.features import GeologicalUnit
from loop_model.manager import GeologicalSchema
from loop_engine.core.model import Model
# Mock data for 4 layers (Basal contacts)
# Layer 0 is the bottom-most basal contact
xy = np.random.rand(10, 2)  # 10 random points in XY

contact_data = [
    PointSet(name="Base_L1", coords=np.hstack([xy, np.zeros((10, 1))])),
    PointSet(name="Base_L2", coords=np.hstack([xy, np.zeros((10, 1)) + 1.0])),
    PointSet(name="Base_L3", coords=np.hstack([xy, np.zeros((10, 1)) + 2.0])),
    PointSet(name="Base_L4", coords=np.hstack([xy, np.zeros((10, 1)) + 3.0])),
]

from loop_model.features import GeologicalUnit
from loop_model.manager import GeologicalSchema, LoopProject

project = LoopProject(name="Layer Cake Model")
schema = GeologicalSchema(name="Simple 4-Layer Model", project=project)
units = []
units.append(
    schema.add_unit(
        name="Unit_Bottom",
        basal_contacts=[contact_data[0]],
    )
)
units.append(
    schema.add_unit(
        name="Unit_Middle_Lower",
        basal_contacts=[contact_data[1]],
    )
)
units.append(
    schema.add_unit(
        name="Unit_Middle_Upper",
        basal_contacts=[contact_data[2]],
    )
)
units.append(
    schema.add_unit(
        name="Unit_Top",
        basal_contacts=[contact_data[3]],
    )
)


# Define the stratigraphic relationship (A overlies B)
for i in range(len(units) - 1):
    schema.add_conformable_overlies_relation(
        master_uuid=units[i + 1].uuid, slave_uuid=units[i].uuid
    )

# schema.model_validate()
print(schema.get_execution_order())

model = Model(schema=schema,interpolation_strategy='linked_scalar_fields')
model.solve()