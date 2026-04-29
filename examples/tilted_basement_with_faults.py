"""
Tilted Basement with Normal Faults and Flat Sedimentary Series
===============================================================

This example demonstrates:
- A tilted basement unit
- Two parallel normal faults cutting through the basement
- A flat, younger sedimentary series that unconformably overlies the faulted basement
"""

from __future__ import annotations

import numpy as np

from loop_common.observations import PointSet
from loop_engine.core.model import Model
from loop_model.manager import GeologicalSchema


def build_model() -> Model:
    """
    Build a geological model with:
    - Tilted basement tilted 30° towards the northeast
    - Two normal faults displacing the basement (60m each)
    - Flat younger sedimentary series above basement
    """
    schema = GeologicalSchema(name="Tilted Basement with Normal Faults")
    schema.initialize_project()

    # ==========================================
    # 1. Create the Tilted Basement Unit
    # ==========================================
    # The basement is tilted 30° towards NE (azimuth 45°)
    # We'll create points that represent the base of the basement
    # at different elevations to show the tilt
    
    basement_points = np.array([
        # Western edge (lower elevation)
        [0.0, 0.0, -2.0],
        [0.2, 0.0, -2.0],
        [0.0, 0.2, -1.8],
        [0.2, 0.2, -1.8],
        # Central area
        [0.5, 0.5, -0.5],
        [0.7, 0.5, -0.3],
        [0.5, 0.7, -0.3],
        [0.7, 0.7, -0.1],
        # Eastern edge (higher elevation)
        [1.0, 1.0, 1.0],
        [1.2, 1.0, 1.2],
        [1.0, 1.2, 1.2],
        [1.2, 1.2, 1.4],
    ], dtype=float)
    
    basement = schema.add_unit(
        name="Basement",
        basal_contacts=[PointSet(name="basement_base", coords=basement_points)],
        metadata={"description": "Tilted metamorphic basement"},
    )

    # ==========================================
    # 2. Create the Flat Sedimentary Series
    # ==========================================
    # This unconformably overlies the basement
    # We create a flat series at a constant elevation above the basement
    
    sediment_points = np.array([
        [0.0, 0.0, 2.5],
        [0.3, 0.0, 2.5],
        [0.6, 0.0, 2.5],
        [0.9, 0.0, 2.5],
        [1.2, 0.0, 2.5],
        [0.0, 0.3, 2.5],
        [0.3, 0.3, 2.5],
        [0.6, 0.3, 2.5],
        [0.9, 0.3, 2.5],
        [1.2, 0.3, 2.5],
        [0.0, 0.6, 2.5],
        [0.3, 0.6, 2.5],
        [0.6, 0.6, 2.5],
        [0.9, 0.6, 2.5],
        [1.2, 0.6, 2.5],
        [0.0, 0.9, 2.5],
        [0.3, 0.9, 2.5],
        [0.6, 0.9, 2.5],
        [0.9, 0.9, 2.5],
        [1.2, 0.9, 2.5],
    ], dtype=float)
    
    sediment = schema.add_unit(
        name="Sediments",
        basal_contacts=[PointSet(name="sediment_base", coords=sediment_points)],
        metadata={"description": "Flat sedimentary series"},
    )

    # ==========================================
    # 3. Define Fault 1 (Western Normal Fault)
    # ==========================================
    # Dips steeply to the east (70°), striking N-S
    # Displacement: 60m (hanging wall down)
    
    fault1_trace = np.array([
        [0.3, -0.2, 0.0],
        [0.3, 0.0, 0.0],
        [0.3, 0.2, 0.0],
        [0.3, 0.4, 0.0],
        [0.3, 0.6, 0.0],
        [0.3, 0.8, 0.0],
        [0.3, 1.0, 0.0],
    ], dtype=float)
    
    fault1_orientation = np.array([
        [0.3, 0.5, 0.0, 0.9397, 0.0, -0.342],  # x, y, z, gx, gy, gz (70° dip to east)
    ], dtype=float)
    
    fault1 = schema.add_fault(
        name="Fault_1_West",
        displacement=0.6,  # 60m in our coordinate system
        trace=[PointSet(name="fault1_trace", coords=fault1_trace)],
        orientations=[PointSet(name="fault1_orientation", coords=fault1_orientation)],
    )

    # ==========================================
    # 4. Define Fault 2 (Eastern Normal Fault)
    # ==========================================
    # Parallel to Fault 1, also dips steeply east
    # Displacement: 60m (hanging wall down)
    
    fault2_trace = np.array([
        [0.8, -0.2, 0.0],
        [0.8, 0.0, 0.0],
        [0.8, 0.2, 0.0],
        [0.8, 0.4, 0.0],
        [0.8, 0.6, 0.0],
        [0.8, 0.8, 0.0],
        [0.8, 1.0, 0.0],
    ], dtype=float)
    
    fault2_orientation = np.array([
        [0.8, 0.5, 0.0, 0.9397, 0.0, -0.342],  # Same dip as Fault 1
    ], dtype=float)
    
    fault2 = schema.add_fault(
        name="Fault_2_East",
        displacement=0.6,  # 60m in our coordinate system
        trace=[PointSet(name="fault2_trace", coords=fault2_trace)],
        orientations=[PointSet(name="fault2_orientation", coords=fault2_orientation)],
    )

    # ==========================================
    # 5. Define Stratigraphic Relationships
    # ==========================================
    # Sediments unconformably overlie basement
    # (Note: In real models, you might use an unconformable relation)
    schema.add_conformable_overlies_relation(
        master_uuid=sediment.uuid,
        slave_uuid=basement.uuid
    )

    # ==========================================
    # 6. Define Fault Relationships
    # ==========================================
    # Both faults displace the basement (basement exists before faults cut it)
    schema.add_faulted_by_relation(
        master_uuid=fault1.uuid,
        slave_uuid=basement.uuid
    )
    schema.add_faulted_by_relation(
        master_uuid=fault2.uuid,
        slave_uuid=basement.uuid
    )
    
    # Note: Sediments were deposited after faulting, so they don't get faulted

    # ==========================================
    # 7. Create and return the model
    # ==========================================
    model = Model(
        schema=schema,
        interpolatortype="FDI",
        nelements=50000,
        interpolation_strategy="shared_scalar_field",
    )
    
    return model


def main() -> None:
    """Build and solve the geological model."""
    print("Building tilted basement with normal faults model...")
    model = build_model()
    
    print("Model schema created with features:")
    for feature in model.schema.features.values():
        print(f"  - {feature.name} (type: {type(feature).__name__})")
    
    print("\nSolving model...")
    state = model.solve()
    
    print(f"Model solved with {len(state.results)} result(s)")
    print("Model is ready for visualization or export!")


if __name__ == "__main__":
    main()
