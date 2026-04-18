import numpy as np
from loop_common.observations import PointSet

# Mock data for 4 layers (Basal contacts)
# Layer 0 is the bottom-most basal contact
contact_data = [
    PointSet(name="Base_L1", coords=np.random.rand(10, 3)),
    PointSet(name="Base_L2", coords=np.random.rand(10, 3)),
    PointSet(name="Base_L3", coords=np.random.rand(10, 3)),
    PointSet(name="Base_L4", coords=np.random.rand(10, 3)),
]

from loop_model.features import GeologicalUnit
from loop_model.manager import GeologicalSchema

schema = GeologicalSchema(name="Simple 4-Layer Model")

# We define the units from oldest to youngest
unit_names = ["Unit_Bottom", "Unit_Middle_Lower", "Unit_Middle_Upper", "Unit_Top"]
units = []

for i, name in enumerate(unit_names):
    unit = GeologicalUnit(
        name=name,
        unit_type="stratigraphy",
        order=i,  # 0 is oldest
        data_links=[contact_data[i].uuid],  # Link to the PointSet UID
    )
    schema.add_feature(unit)
    units.append(unit)

# Define the stratigraphic relationship (A overlies B)
for i in range(len(units) - 1):
    schema.add_relation(master_id=units[i + 1].uuid, slave_id=units[i].uuid, relation="overlies")

schema.visualize_graph(include_data=True)
