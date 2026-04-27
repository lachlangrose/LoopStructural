# LoopStructural 2.0 Design Document

**Version:** 1.0  
**Date:** April 2026  
**Purpose:** Reference guide for developers and agents extending the LoopStructural library

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Responsibilities](#module-responsibilities)
3. [Data Flow and Processing Pipeline](#data-flow-and-processing-pipeline)
4. [Core Abstractions](#core-abstractions)
5. [Key Classes and Interfaces](#key-classes-and-interfaces)
6. [Integration Patterns](#integration-patterns)
7. [Extension Points](#extension-points)
8. [Development Guidelines](#development-guidelines)

---

## Architecture Overview

LoopStructural 2.0 is built on a **modular, layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│              User Applications / APIs                    │
├─────────────────────────────────────────────────────────┤
│ loop_model       (Geological Schema & Features)         │
│ ├── GeologicalSchema (feature relationships)            │
│ └── GeologicalFeature, Unit, Fault, Fold, ...          │
├─────────────────────────────────────────────────────────┤
│ loop_engine      (Model Compilation & Execution)        │
│ ├── Model (solve orchestration)                         │
│ ├── ObservationLinker (data → constraints)              │
│ └── Task (execution unit)                               │
├─────────────────────────────────────────────────────────┤
│ loop_interpolation (Constraint Solving)                 │
│ ├── GeologicalInterpolator (base)                       │
│ ├── FiniteDifferenceInterpolator                        │
│ ├── P1Interpolator (Piecewise Linear)                   │
│ └── Other specialized interpolators                     │
├─────────────────────────────────────────────────────────┤
│ loop_common      (Shared Utilities & Foundations)       │
│ ├── BoundingBox, Point, Surface                         │
│ ├── Supports (grids, meshes, interpolation domains)     │
│ ├── Observations (PointSet, LineSet, Orientation)       │
│ └── Math, Geometry, I/O, Logging                        │
└─────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Single Responsibility**: Each module has a clear, focused purpose
2. **Layered Dependencies**: Upper layers depend on lower layers; no circular dependencies
3. **Data-Centric**: The schema defines *what* is being modeled; other modules define *how*
4. **Pluggable**: Interpolators and builders are extensible without modifying core code
5. **Pydantic-Based**: Models use Pydantic for validation, serialization, and introspection
6. **Numpy-Oriented**: Numerical data flows as numpy arrays through the pipeline

---

## Module Responsibilities

### `loop_model`: The Schema Layer

**Purpose**: Define the *what*—the geological features, their relationships, and observations.

**Key Entities**:
- **`GeologicalFeature`**: Base class for all geological entities (abstract)
  - `data_links: List[str | DataRole]` — references to observations
  - `enabled: bool` — whether the feature is active in the solve

- **`Unit`** (aka `GeologicalUnit`): Stratigraphic rock body
  - Represents an isochron (surface of constant age)
  - Defined by basal and top surfaces

- **`Fault`**: Displacement surface
  - Defined by slip vectors, hanging wall/footwall observations
  - Can displace other units

- **`Fold`**: Curved structure
  - Defined by fold-related observations and constraints
  - Links folded surfaces to fold geometry

- **`GeologicalSchema`**: Relationship graph
  - `features: Dict[str, GeologicalFeature]` — registry of all features
  - `dag: nx.DiGraph` — directed acyclic graph of feature dependencies
  - `bounding_box: BoundingBox` — 3D bounds of the model
  - Methods: `add_unit()`, `add_fault()`, `add_fold()`, `get_execution_order()`

- **`LoopProject`**: Top-level container
  - `schema: GeologicalSchema` — the "brain" (logic, relationships, metadata)
  - `observations: Dict[str, LoopEntity]` — the "vault" (raw data: PointSets, etc.)
  - Methods: `add_observation()`, `link_observation_to_feature()`

- **`DataRole`**: Semantic tag for how data relates to a feature
  - Values: `"basal"`, `"top"`, `"orientation"`, `"trace"`, `"hanging_wall"`, `"footwall"`, `"slip_vector"`, `"thickness"`, `"inside"`, `"outside"`
  - Used to guide interpretation during interpolation

**Dependencies**: `loop_common` (for `LoopEntity`, `BoundingBox`)

**Key Design Decisions**:
- Features are **loosely coupled** via the schema graph
- Data links use **semantic roles** to guide downstream processing (not just raw data pointers)
- The DAG **topological order** determines solve sequence
- Schema is **immutable in structure** during solve (features and edges don't change mid-solve)

---

### `loop_engine`: The Orchestration Layer

**Purpose**: Compile the schema into a sequence of tasks, execute them, and manage the result state.

**Key Classes**:

- **`Model`**: Main orchestrator
  - `schema: GeologicalSchema` — the model definition
  - `grid: StructuredGrid | None` — spatial discretization
  - `interpolatortype: str` — default interpolator (e.g., `"FDI"`)
  - `current_state: ModelState` — results of the most recent solve
  - Key methods:
    - `solve()` — "The Big Green Button": compile → execute → store results
    - `get_solved_feature(feature_id | feature_name)` — retrieve a solved result
    - `evaluate_scalar_field(positions, feature_id)` — evaluate the implicit function
    - `extract_unit_basal_surface(unit_id, value=0.0)` — extract an isosurface

- **`ObservationLinker`**: Schema → Interpolator data bridge
  - `build_inputs_by_feature(feature_ids)` → `Dict[feature_id, InterpolatorInput]`
  - Resolves data_links (DataRole or raw strings) → Numpy constraint arrays
  - Roles determine array destination (point_constraints, gradient_constraints, etc.)
  - Handles missing observation IDs gracefully

- **`InterpolatorInput`**: Struct holding constraint arrays + metadata
  - `feature_id`, `feature_name`, `feature_type`
  - `point_constraints: (N, 3)` — XYZ for isovalue constraints
  - `gradient_constraints: (M, 6)` — [X, Y, Z, Gx, Gy, Gz]
  - `tangent_constraints: (K, 6)` — [X, Y, Z, Tx, Ty, Tz]
  - `by_role: Dict[role, List[LinkedObservation]]` — grouped observations
  - `missing_observation_ids: List[str]` — unresolved links (warnings)

- **`LinkedObservation`**: Atomic observation reference
  - `obs_uid` — unique identifier in project
  - `role` — semantic role (DataRole)
  - `observation` — the actual observation object (or None if not found)

- **`Task`**: Execution unit
  - `id` (feature_id)
  - `dependencies` / `predecessors` — upstream features
  - `linked_data: InterpolatorInput` — constraint arrays + metadata
  - `feature: GeologicalFeature` — the feature being built
  - `execute(dependency_results)` → payload dict for builder

- **`ModelState`**: Snapshot of results
  - `grid` — shared discretization
  - `results: Dict[feature_id, GeologicalFeature | dict]` — solved features
  - `version` — state version (for change tracking)
  - `get_feature(feature_id)` — retrieve a result

**Data Flow** (within `Model.solve()`):
1. `_compile_tasks()` → topologically sorted task list
2. For each task:
   - `task.execute(upstream_results)` → payload (feature_id, dependencies, linked_data, etc.)
   - `_builder_dispatcher.build(payload)` → GeologicalInterpolator (solved)
   - `_coerce_solved_feature(...)` → wrap in loop_engine.GeologicalFeature
   - Store in state.results
3. Return new ModelState

**Dependencies**: `loop_model`, `loop_common`, `loop_interpolation`

**Key Design Decisions**:
- **Lazy execution**: Tasks only run if `is_dirty` (extensible for caching)
- **Kinematic chain**: Each task receives upstream results as inputs (faults can constrain units)
- **Payload-driven**: Tasks emit dicts; builders interpret payloads (decoupled from interpolator details)
- **Representation normalization**: `get_solved_feature()` wraps raw interpolators in loop_engine.GeologicalFeature for consistency

---

### `loop_interpolation`: The Solver Layer

**Purpose**: Fit mathematical representations (interpolators) to constraint data.

**Key Classes**:

- **`GeologicalInterpolator`** (abstract base)
  - `data: Dict[str, np.ndarray]` — constraint arrays
  - `n_g`, `n_i`, `n_n`, `n_t` — counts of gradient, interface, normal, tangent constraints
  - Key methods:
    - `add_interface_constraint(xyz, value)` — point on isosurface
    - `add_gradient_constraint(xyz, gradient)` — normal/direction constraints
    - `add_tangent_constraint(xyz, tangent)` — tangent constraints
    - `fit()` → solve the inverse problem
    - `evaluate_value(positions)` → scalar field values
    - `evaluate_gradient(positions)` → gradient vectors
    - `surfaces(value)` → isosurface extraction
  - `type: InterpolatorType` — classifies the interpolator

- **Concrete Interpolators**:
  - `FiniteDifferenceInterpolator` (FDI)
    - Grid-based; solves on StructuredGrid
    - Efficient for large domains; requires structured mesh
  - `P1Interpolator` (PiecewiseLinearInterpolator)
    - Tetrahedral mesh; linear basis functions
    - Good general-purpose choice
  - `P2Interpolator`
    - Quadratic basis on tetrahedral mesh
    - Higher accuracy, higher cost
  - `DiscreteFoldInterpolator`, `FDFoldInterpolator`
    - Specialized for fold-like structures
  - `SurfeRBFInterpolator`
    - Optional RBF-based solver (requires Surfe library)
  - `ConstantNormP1Interpolator`, `ConstantNormFDIInterpolator`
    - Variants enforcing constant normal magnitudes

- **Constraint Validation** (`_validation.py`)
  - `validate_value_constraint()`, `validate_gradient_constraint()`, etc.
  - NaN/Inf handling: data is dropped with warnings; weights are replaced with 1.0
  - Magnitude checking: ensures normal vectors have expected magnitude (default weight 100.0)

- **Diagnostics** (`_diagnostics.py`)
  - `ConstraintDiagnosticsReport` — overall constraint analysis
  - `ConstraintFamilyDiagnostics` — per-role statistics (count, distribution)
  - `RegionCoverageDiagnostics` — spatial coverage analysis

- **Regularisation Config** (`_regularisation.py`)
  - `DirectionalRegularisation` — anisotropic smoothing guidance
  - `RegularisationConfig` — solver tuning parameters

**Supports** (from `loop_common.supports`):
- `StructuredGrid` (3D) / `StructuredGrid2D` — regular rectilinear grid
- `TetMesh` — unstructured tetrahedral mesh
- `P1Unstructured2d`, `P2Unstructured2d` — 2D unstructured
- `P2UnstructuredTetMesh` — higher-order tetrahedral
- Each interpolator declares compatible supports

**Dependencies**: `loop_common`

**Key Design Decisions**:
- **Constraint-driven**: All interpolators accept the same constraint types (value, gradient, tangent, normal)
- **Support abstraction**: Interpolators don't care about underlying mesh details; they work via the Support interface
- **Validation gating**: Invalid constraints are dropped early, with diagnostics
- **Default weights**: Normal constraints weighted 100.0× higher than gradients (tunable)

---

### `loop_common`: The Foundation Layer

**Purpose**: Provide shared data structures, utilities, and abstractions.

**Key Modules**:

#### `geometry`
- **`BoundingBox`**: Defines model extent and discretization
  - `origin, maximum: np.ndarray` — world-space corners
  - `nsteps: np.ndarray` — cells/elements in each direction
  - `local_origin, local_rotation` — local coordinate frame
  - Methods: `fit()`, `project()`/`reproject()` (world ↔ local conversion)
  - Design: origin/maximum are always in world space; local frame is optional

- **`Point`**, **`Surface`**: Geometric primitives (minimal implementations)

#### `supports`
- Base class `BaseSupport` defining the mesh/grid interface
- Concrete classes:
  - `StructuredGrid`, `StructuredGrid2D` — regular grids
  - `UnStructuredTetMesh`, `TetMesh` — tetrahedral
  - `P1Unstructured2d`, `P2Unstructured2d` — 2D variants
  - `P2UnstructuredTetMesh` — higher-order
- Key methods: `cell_centre()`, `nodes()`, `evaluate_shape_functions()`, `extract_isosurface()`

#### `observations`
- **`PointSet`**: Collection of points with values
  - `vertices: (N, 3)` — locations
  - `values: (N,)` — scalar values (optional)

- **`LineSet`**: Collection of line segments
  - `vertices: (N, 3)` — line points
  - `segments` — connectivity

- **`Orientation`**: Strike/dip measurements
  - `coords: (N, 3)` — measurement locations
  - `vector: (N, 3)` — normal or direction vector
  - `type` — e.g., "bedding", "cleavage"

#### `interfaces`
- **`BaseRepresentation`** (abstract)
  - `evaluate_value(position)` → float
  - `evaluate_gradient(position)` → array
  - `surfaces(value)` → isosurface geometry
  - Implemented by interpolators; used for post-solve evaluation

#### `math`
- Linear algebra, interpolation utilities
- Random number generation (seeded for reproducibility)

#### `io`
- Serialization, file I/O
- GeoJSON, other geology-standard formats

#### `logging`
- `get_logger(name)` — scoped logging with Loop conventions
- Controls verbosity, formats messages

#### `base`
- **`LoopEntity`** (Pydantic BaseModel)
  - `uuid: str` — persistent unique ID (factory-generated UUID)
  - `name: Optional[str]` — human-readable label
  - `last_modified: str` — ISO timestamp
  - `mark_modified()` — trigger timestamp update
  - Config: `arbitrary_types_allowed=True`, `validate_assignment=True`, `extra="forbid"`
  - Serialization: numpy arrays ↔ lists (transparent)

**Dependencies**: None (foundation layer)

**Key Design Decisions**:
- **Numpy-first**: Geometry and observations use numpy arrays for vectorized ops
- **Pydantic validation**: All entities validate on assignment; strong typing
- **Serialization-ready**: JSON serialization via field validators/serializers (numpy arrays as lists)
- **UUID-based identity**: Allows features/observations to survive across serialize/deserialize cycles

---

## Data Flow and Processing Pipeline

### End-to-End Example: Building a Simple Model

```python
# 1. SETUP (loop_model)
from loop_model.manager import LoopProject
from loop_common.observations import PointSet, Orientation

project = LoopProject()
schema = project.schema

# 2. ADD OBSERVATIONS (loop_model)
basal_contacts = PointSet(vertices=[[0, 0, 100], [10, 10, 90]], name="Top basal")
project.add_observation(basal_contacts)

top_contacts = PointSet(vertices=[[0, 0, 200], [10, 10, 210]], name="Top surface")
project.add_observation(top_contacts)

orientations = Orientation(coords=[[5, 5, 150]], vector=[[0, 0, 1]], name="Vertical dip")
project.add_observation(orientations)

# 3. BUILD SCHEMA (loop_model)
unit = schema.add_unit(
    name="TopUnit",
    basal_contacts=[DataRole(obs_uid=basal_contacts.uuid, role="basal")],
    top_contacts=[DataRole(obs_uid=top_contacts.uuid, role="top")],
    orientations=[DataRole(obs_uid=orientations.uuid, role="orientation")],
)

# 4. INITIALIZE GRID (loop_common + loop_engine)
from loop_common.geometry import BoundingBox
from loop_engine import Model

bbox = BoundingBox(origin=[0, 0, 0], maximum=[100, 100, 300], nsteps=[10, 10, 30])
model = Model(schema, grid=bbox, interpolatortype="FDI", nelements=1000)

# 5. SOLVE (loop_engine + loop_interpolation)
state = model.solve()

# 6. EVALUATE (loop_engine + loop_interpolation)
positions = [[50, 50, 150], [50, 50, 200]]
field_values = model.evaluate_scalar_field(positions, feature_id=unit.uuid)
print(field_values)  # e.g., [0.0, 1.0] (below/above basal contact)
```

### Detailed Data Flow: `Model.solve()`

```
1. _compile_tasks()
   ├─ schema.get_execution_order()
   │  └─ Topological sort of DAG → [feature_1, feature_2, ...]
   ├─ _linker.build_inputs_by_feature(execution_order)
   │  └─ For each feature_id:
   │     ├─ Resolve data_links → observations
   │     ├─ Group by DataRole
   │     └─ Populate constraint arrays → InterpolatorInput
   └─ Create Task(feature_id, dependencies, linked_data)

2. For each task:
   ├─ task.execute(upstream_results)
   │  └─ Return {"feature_id", "feature", "linked_data", "dependencies", ...}
   │
   ├─ _builder_dispatcher.build(payload)
   │  └─ Interpolator-specific builder:
   │     ├─ Create GeologicalInterpolator instance
   │     ├─ Add constraints from linked_data
   │     ├─ fit()
   │     └─ Return solved interpolator
   │
   ├─ _coerce_solved_feature(task.id, build_result)
   │  └─ Wrap interpolator in loop_engine.GeologicalFeature(name, representation=interpolator)
   │
   └─ new_state.results[task.id] = solved_feature

3. self.current_state = new_state
```

### Constraint Role → Array Mapping

The `ObservationLinker` maps DataRoles to constraint types:

| DataRole | Observation Type | Destination Array | Semantics |
|----------|------------------|------------------|-----------|
| `"basal"` / `"top"` | PointSet | `point_constraints` | Interface (isovalue 0) |
| `"orientation"` | Orientation | `gradient_constraints` | Bedding normal |
| `"hanging_wall"` / `"footwall"` | PointSet | `point_constraints` | Inside/outside constraint |
| `"slip_vector"` | Orientation | `gradient_constraints` | Fault slip direction |
| `"thickness"` | PointSet or scalar | Custom | Isopach constraints |
| `"inside"` / `"outside"` | PointSet | Inequality arrays | Inequality constraints |
| `"trace"` | LineSet | `point_constraints` | Map trace → points |

---

## Core Abstractions

### 1. Feature Hierarchy (loop_model)

```
GeologicalFeature (abstract)
├── Unit (stratigraphic unit)
├── Fault (displacement surface)
├── Fold (curved structure)
└── [Future: Contact, Unconformity, Intrusion, ...]
```

Each feature:
- Is identified by a UUID
- Has semantic data_links (DataRole-tagged observations)
- Is governed by a feature_type (interpolator selection)
- May have build_params (interpolator-specific tuning)

### 2. Data Link Resolution (loop_engine)

```
data_link (string | DataRole)
  ↓
_parse_data_link() → (obs_uid: str, role: str)
  ↓
_lookup_observation(obs_uid) → Observation object
  ↓
_append_observation_constraints() → update constraint arrays
  ↓
InterpolatorInput (feature_id, arrays, by_role)
```

Key: The role *guides* constraint placement. Missing observations are tracked but don't fail the build.

### 3. Interpolator Dispatch (loop_engine + loop_interpolation)

```
Model
  ├─ interpolatortype: str = "FDI"
  ├─ _builder_dispatcher: FeatureBuilderDispatcher
  │  └─ Can override per-feature via GeologicalFeature.feature_type
  └─ solve()
     └─ For each feature:
        └─ builder_dispatcher.build(payload) → GeologicalInterpolator
```

The dispatcher allows:
- Default interpolator per model
- Per-feature overrides
- Custom builders for specialty features (Folds, etc.)

### 4. Representation Interface (loop_interpolation)

All interpolators implement `BaseRepresentation`:

```python
class MyInterpolator(GeologicalInterpolator):
    def evaluate_value(self, position: np.ndarray) -> np.ndarray:
        """Evaluate scalar field at positions (N, 3) → (N,)"""
        ...
    
    def evaluate_gradient(self, position: np.ndarray) -> np.ndarray:
        """Evaluate gradient at positions (N, 3) → (N, 3)"""
        ...
    
    def surfaces(self, value: float) -> dict | None:
        """Extract isosurface at field value → geometry dict"""
        ...
```

This allows `Model.evaluate_scalar_field()` to work generically with any interpolator.

---

## Key Classes and Interfaces

### Class Diagram: Core Relationships

```
┌────────────────────────────────────────┐
│  loop_model.manager.LoopProject        │
│  ├─ schema: GeologicalSchema           │
│  └─ observations: Dict[uuid, Entity]   │
└────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────┐
│  loop_model.manager.GeologicalSchema   │
│  ├─ features: Dict[id, Feature]        │
│  ├─ dag: nx.DiGraph (dependencies)     │
│  └─ bounding_box: BoundingBox          │
└────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────┐
│  loop_engine.core.Model                │
│  ├─ schema: GeologicalSchema           │
│  ├─ grid: StructuredGrid               │
│  ├─ _linker: ObservationLinker         │
│  └─ current_state: ModelState          │
└────────────────────────────────────────┘
        │                    │
        ▼                    ▼
  ┌──────────┐        ┌──────────────────────┐
  │ObserveLinker     │FeatureBuilderDispatcher│
  │                 │                        │
  │InterpolatorInput  │→ Interpolator factory │
  └──────────┘        └──────────────────────┘
                              │
                              ▼
                   ┌─────────────────────────┐
                   │GeologicalInterpolator   │
                   │(FDI, P1, P2, Fold, ...) │
                   └─────────────────────────┘
```

### Method Signatures: Critical Flows

```python
# loop_model
class GeologicalSchema:
    def add_unit(name: str, basal_contacts: List[DataRole], ...): Unit
    def add_fault(...): Fault
    def add_fold(...): Fold
    def get_execution_order() -> List[str]  # Topological sort of DAG

# loop_engine
class Model:
    def solve() -> ModelState  # Compile + execute + return results
    def get_solved_feature(feature_id | feature_name) -> GeologicalFeature | dict
    def evaluate_scalar_field(positions: (N,3), feature_id: str) -> (N,)
    def extract_unit_basal_surface(unit_id: str, value: float = 0.0) -> dict

class ObservationLinker:
    def build_inputs_by_feature(feature_ids: List[str]) -> Dict[str, InterpolatorInput]
    def build_feature_input(feature_id: str) -> InterpolatorInput

# loop_interpolation
class GeologicalInterpolator(abstract):
    def add_value_constraint(xyz: (N,3), value: (N,)): None
    def add_gradient_constraint(xyz: (N,3), gradient: (N,3)): None
    def add_tangent_constraint(xyz: (N,3), tangent: (N,3)): None
    def add_normal_constraint(xyz: (N,3), normal: (N,3), weight: (N,)): None
    def fit(): None  # Solve the inverse problem
    def evaluate_value(position: (N,3)) -> (N,): np.ndarray
    def evaluate_gradient(position: (N,3)) -> (N,3): np.ndarray
    def surfaces(value: float) -> dict | None

# loop_common
class BoundingBox:
    origin: np.ndarray  # (3,) world-space min
    maximum: np.ndarray  # (3,) world-space max
    nsteps: np.ndarray  # (3,) discretization
    local_origin: np.ndarray  # Local frame origin (in world space)
    local_rotation: np.ndarray  # (3,3) rotation matrix
    def fit(points: (N,3), local_coordinate: bool = False): None
    def project(points: (N,3)) -> (N,3)  # World → Local
    def reproject(points: (N,3)) -> (N,3)  # Local → World

class LoopEntity(BaseModel):
    uuid: str  # Unique ID
    name: Optional[str]  # Human label
    last_modified: str  # ISO timestamp
    def mark_modified(): None
```

---

## Integration Patterns

### Pattern 1: Schema-First Workflow (Recommended)

```python
# 1. Define schema independently
schema = GeologicalSchema()
schema.add_unit("Top", basal_contacts=[...], ...)
schema.add_unit("Middle", basal_contacts=[...], ...)
schema.add_fault("MainFault", ...)

# 2. Attach observations via project
project = schema.initialize_project()
for obs in observations:
    project.add_observation(obs)
    # Then link via DataRole objects in schema

# 3. Build and solve model
model = Model(schema, grid=bbox, interpolatortype="FDI")
state = model.solve()
```

**Advantages**: Clean separation; schema can be reviewed/versioned separately.

### Pattern 2: Project-First Workflow

```python
# 1. Create project with observations
project = LoopProject()
for obs in observations:
    project.add_observation(obs)

# 2. Build schema interactively
schema = project.schema
unit = schema.add_unit(
    "TopUnit",
    basal_contacts=[DataRole(obs_uid=basal.uuid, role="basal")],
    ...
)

# 3. Solve
model = Model(schema, grid=bbox)
state = model.solve()
```

**Advantages**: Interactive; observations are always available.

### Pattern 3: Custom Interpolator for Specialty Features

```python
from loop_engine.features.dispatch import FeatureBuilderDispatcher
from loop_interpolation import FiniteDifferenceInterpolator

class CustomFoldBuilder:
    def build(self, payload):
        linked_data = payload["linked_data"]
        fold = FiniteDifferenceInterpolator()
        fold.add_gradient_constraint(linked_data.gradient_constraints[:, :3],
                                     linked_data.gradient_constraints[:, 3:])
        fold.fit()
        return fold

dispatcher = model._builder_dispatcher
dispatcher.register_builder("Fold", CustomFoldBuilder())
state = model.solve()  # Uses custom builder for Fold features
```

**Use Case**: When standard interpolators don't fit the feature type.

### Pattern 4: Constraint Diagnostics

```python
state = model.solve()
feature_id = schema.features["TopUnit"].uuid
interpolator = state.results[feature_id]

# Access diagnostics from most recent build
if hasattr(interpolator, "latest_diagnostics_report"):
    report = interpolator.latest_diagnostics_report
    print(f"Total constraints: {report.total_constraints}")
    print(f"By role: {report.family_diagnostics}")
```

---

## Extension Points

### 1. Custom Geological Features

**File**: `packages/loop_model/src/loop_model/features/`

Create a new feature class:

```python
from loop_model.features.base import GeologicalFeature
from pydantic import Field

class Unconformity(GeologicalFeature):
    """An erosional surface with angular discordance."""
    
    # Define feature-specific fields
    dips_above: List[DataRole] = Field(default_factory=list)
    dips_below: List[DataRole] = Field(default_factory=list)
    contact_points: List[DataRole] = Field(default_factory=list)
```

Register in schema:

```python
def add_unconformity(self, name, dips_above, dips_below, contact_points, ...):
    unc = Unconformity(name=name, ...)
    self.features[unc.uuid] = unc
    self.dag.add_node(unc.uuid)
    # Link to predecessors (e.g., units below unconformity)
    return unc
```

### 2. Custom Interpolator

**File**: `packages/loop_interpolation/src/loop_interpolation/`

Create a new interpolator class:

```python
from loop_interpolation._geological_interpolator import GeologicalInterpolator
from loop_interpolation._interpolatortype import InterpolatorType
import numpy as np

class MyCustomInterpolator(GeologicalInterpolator):
    def __init__(self, data={}, up_to_date=False):
        super().__init__(data, up_to_date)
        self.type = InterpolatorType.CUSTOM
        self.my_solver = MySolverClass()
    
    def fit(self):
        """Solve the inverse problem using custom logic."""
        # Extract constraint arrays
        points = self.data["interface"]
        gradients = self.data["gradient"]
        
        # Solve
        self.my_solver.build(points, gradients)
        self.up_to_date = True
    
    def evaluate_value(self, position):
        return self.my_solver.evaluate(position)
    
    def evaluate_gradient(self, position):
        return self.my_solver.evaluate_grad(position)
```

Register in `loop_interpolation/__init__.py`:

```python
interpolator_map[InterpolatorType.CUSTOM] = MyCustomInterpolator
```

### 3. Custom Feature Builder

**File**: `packages/loop_engine/src/loop_engine/features/`

Create a builder that interprets payloads in domain-specific ways:

```python
class SpecializedFoldBuilder:
    def build(self, payload):
        """Build a fold interpolator with domain-specific constraints."""
        linked_data = payload["linked_data"]
        fold_feature = payload["feature"]
        
        # Domain logic: specialized constraint handling
        interpolator = FiniteDifferenceInterpolator()
        
        # Custom: prioritize fold-axis constraints
        if linked_data.by_role.get("fold_axis"):
            for axis_obs in linked_data.by_role["fold_axis"]:
                # Special handling...
                pass
        
        # Standard constraints
        interpolator.add_interface_constraint(
            linked_data.point_constraints[:, :3],
            np.zeros(len(linked_data.point_constraints))
        )
        
        interpolator.fit()
        return interpolator
```

Register in Model or FeatureBuilderDispatcher:

```python
model._builder_dispatcher.register_builder("Fold", SpecializedFoldBuilder())
```

### 4. Custom Constraint Validator

**File**: `packages/loop_interpolation/src/loop_interpolation/_validation.py`

Extend the validation module to add domain-specific checks:

```python
def validate_fold_constraints(gradient_constraints, tangent_constraints):
    """Ensure fold constraints satisfy geometric validity."""
    if gradient_constraints is None or len(gradient_constraints) == 0:
        raise ValidationError("Fold requires at least one gradient constraint")
    
    # Domain rule: tangent and gradient must be perpendicular
    for grad, tan in zip(gradient_constraints[:, 3:], tangent_constraints[:, 3:]):
        dot = np.dot(grad, tan)
        if not np.isclose(dot, 0.0, atol=1e-6):
            raise ValidationError(f"Fold gradient and tangent not orthogonal: dot={dot}")
    
    return True
```

---

## Development Guidelines

### General Principles

1. **Type Hints**: All public functions/methods must have type hints
   ```python
   def add_observation(self, obs: LoopEntity) -> None:
       ...
   ```

2. **Docstrings**: Use NumPy-style docstrings for public APIs
   ```python
   def evaluate_scalar_field(self, positions: np.ndarray, feature_id: str) -> np.ndarray:
       """Evaluate scalar field at positions.
       
       Parameters
       ----------
       positions : np.ndarray
           Shape (N, 3) array of XYZ coordinates
       feature_id : str
           UUID of the feature to evaluate
       
       Returns
       -------
       np.ndarray
           Shape (N,) array of scalar values
       """
       ...
   ```

3. **Error Handling**: Use specific exception types; provide context
   ```python
   if feature_id not in self.schema.features:
       raise ValueError(f"Feature {feature_id!r} not found in schema")
   ```

4. **Logging**: Use module-level logger from loop_common.logging
   ```python
   from loop_common.logging import get_logger
   logger = get_logger(__name__)
   logger.debug("Processing feature %s", feature_id)
   ```

5. **Testing**: Every public API and critical path should have tests
   - Use pytest
   - Mock external dependencies
   - Test happy path + error cases

### Module-Specific Guidelines

#### loop_model (Schema & Features)

- Feature classes should be minimal data holders (Pydantic models)
- Use `@field_validator` for semantic validation (e.g., circular dependencies)
- Schema.add_*() methods should:
  - Create feature instances
  - Register in `self.features`
  - Add DAG nodes/edges
  - Return the feature object
- The DAG must remain acyclic; validate in `add_*()` before committing

#### loop_engine (Orchestration)

- Model.solve() is the entry point; keep it simple and readable
- Delegate specialization to helper classes (ObservationLinker, builders, etc.)
- Task.execute() should be pure (no side effects beyond returning payload)
- Caching decisions (dirty flag, state reuse) should be explicit

#### loop_interpolation (Solvers)

- GeologicalInterpolator subclasses must implement all abstract methods
- Constraint arrays are Nx3 or Nx6; validate shapes early
- fit() can raise ConvergenceError, NotImplementedError, etc. (document in docstring)
- evaluate_*() methods should handle edge cases (positions outside domain, NaN values)

#### loop_common (Utilities)

- Keep it stateless and functional where possible
- Use numpy for vectorized ops (avoid loops)
- Serialization should be symmetric (to_dict / from_dict)
- BoundingBox methods should preserve the invariant: origin < maximum (element-wise)

### Code Style

- Follow PEP 8
- Use Black for formatting (if configured)
- Max line length: 100 characters (or project standard)
- Class names: PascalCase
- Function/variable names: snake_case
- Constants: UPPER_SNAKE_CASE
- Private attributes: _leading_underscore

### Testing Strategy

```
packages/
├── loop_model/tests/
│   ├── test_schema.py          # Schema graph operations
│   ├── test_features.py        # Feature classes
│   └── test_project.py         # LoopProject operations
├── loop_engine/tests/
│   ├── test_model_compile.py   # Task compilation
│   ├── test_model_solve.py     # End-to-end solve
│   ├── test_linker.py          # Observation linking
│   └── test_builders.py        # Feature builders
├── loop_interpolation/tests/
│   ├── test_interpolators.py   # Interpolator fitting
│   ├── test_validation.py      # Constraint validation
│   └── test_diagnostics.py     # Diagnostics
└── loop_common/tests/
    ├── test_bounding_box.py
    ├── test_observations.py
    └── test_supports.py
```

### Test Template

```python
import pytest
from loop_engine import Model
from loop_model import GeologicalSchema
from loop_common.observations import PointSet

def test_model_compile_tasks_respects_dag_order(sample_schema):
    """Model._compile_tasks() should output tasks in topological order."""
    model = Model(sample_schema)
    tasks = model._compile_tasks()
    
    # Verify ordering
    feature_ids = [t.id for t in tasks]
    for task in tasks:
        for pred in task.predecessors:
            assert feature_ids.index(pred) < feature_ids.index(task.id)

def test_observation_linker_missing_obs(schema_with_missing_links):
    """ObservationLinker should track missing observations without failing."""
    linker = ObservationLinker(schema_with_missing_links)
    inputs = linker.build_inputs_by_feature()
    
    # Check missing IDs are recorded
    assert "missing_obs_id" in inputs["TopUnit"].missing_observation_ids
    # Check constraints are still populated (just incomplete)
    assert inputs["TopUnit"].point_constraints.shape[0] >= 0
```

### Common Pitfalls

1. **Circular Dependencies**: The schema DAG must be acyclic. Validate after `add_*()`.
   ```python
   if nx.is_directed_acyclic_graph(self.dag):
       raise ValueError("Adding this edge would create a cycle")
   ```

2. **UUID vs. UID vs. String ID**: Be consistent.
   - `LoopEntity.uuid` → persistent UUID4 string
   - `DataRole.obs_uid` → UUID of observation
   - Feature ID in schema → UUID of feature
   - Keys in `observations` dict → UUIDs

3. **Numpy Array Shapes**: Validate early.
   ```python
   points = np.asarray(points)
   if points.ndim != 2 or points.shape[1] != 3:
       raise ValueError(f"Points must be (N, 3); got {points.shape}")
   ```

4. **Missing Observations**: Don't crash; log and continue.
   ```python
   observation = self._lookup_observation(obs_uid)
   if observation is None:
       logger.warning(f"Observation {obs_uid} not found; skipping")
       payload.missing_observation_ids.append(obs_uid)
       return
   ```

5. **State Immutability**: After `Model.solve()`, `current_state` is read-only (or changes require calling `solve()` again).

---

## Glossary

| Term | Definition |
|------|-----------|
| **DAG** | Directed Acyclic Graph; schema dependency structure |
| **Topological Order** | Execution sequence respecting task dependencies |
| **DataRole** | Semantic tag linking observation to feature (e.g., "basal", "orientation") |
| **InterpolatorInput** | Struct bundling constraint arrays + metadata for a feature |
| **GeologicalFeature** | Domain object representing a geological entity (Unit, Fault, Fold, ...) |
| **Representation** | Mathematical model (interpolator) that can evaluate scalar/gradient fields |
| **Support** | Spatial discretization (grid, mesh) where interpolator is defined |
| **Constraint** | Data point guiding interpolator (value, gradient, tangent, normal) |
| **Kinematic Chain** | Upstream results feeding into downstream tasks (fault displacing units) |
| **Solver** | Interpolator.fit(); solves inverse problem from constraints |
| **Isosurface** | Contour of constant scalar field; extracted via interpolator.surfaces() |

---

## References and Further Reading

- **Graph Theory**: NetworkX documentation (https://networkx.org/)
- **Geology**: Structural geology texts on faults, folds, stratigraphy
- **Interpolation**: Finite difference methods, piecewise polynomial bases, RBF theory
- **Pydantic**: Validation and serialization (https://docs.pydantic.dev/)
- **NumPy**: Array operations and linear algebra (https://numpy.org/)

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-27 | Copilot | Initial design document |

---

## Appendix: Quick Reference for Common Tasks

### Add a New Geological Feature Type

1. Create `loop_model/src/loop_model/features/mynewfeature.py`:
   ```python
   from .base import GeologicalFeature
   class MyFeature(GeologicalFeature):
       pass
   ```

2. Export from `loop_model/src/loop_model/features/__init__.py`

3. Add to `GeologicalSchema`:
   ```python
   def add_myfeat(self, name, ...):
       feat = MyFeature(name=name, ...)
       self.features[feat.uuid] = feat
       self.dag.add_node(feat.uuid)
       return feat
   ```

4. (Optional) Create a custom builder in `loop_engine/src/loop_engine/features/builders/`

### Add a New Interpolator Type

1. Create `loop_interpolation/src/loop_interpolation/_myinterpolator.py`:
   ```python
   from ._geological_interpolator import GeologicalInterpolator
   class MyInterpolator(GeologicalInterpolator):
       def fit(self): ...
       def evaluate_value(self, pos): ...
   ```

2. Register in `loop_interpolation/__init__.py`:
   ```python
   from ._myinterpolator import MyInterpolator
   interpolator_map[InterpolatorType.MY_TYPE] = MyInterpolator
   ```

3. Add support mapping (which grids/meshes are compatible)

### Evaluate a Feature After Solve

```python
state = model.solve()
feature = model.get_solved_feature(feature_id="unit_uuid")

# Evaluate at positions
positions = np.array([[10, 20, 30], [15, 25, 35]])
values = model.evaluate_scalar_field(positions, feature_id="unit_uuid")

# Extract surface
surface_geometry = feature.representation.surfaces(value=0.0)
```

### Debug: Check What Observations Were Linked

```python
linker = model._linker
inputs = linker.build_inputs_by_feature()

for feature_id, interp_input in inputs.items():
    print(f"Feature: {feature_id}")
    print(f"  Point constraints: {interp_input.point_constraints.shape}")
    print(f"  Gradient constraints: {interp_input.gradient_constraints.shape}")
    print(f"  By role: {list(interp_input.by_role.keys())}")
    print(f"  Missing: {interp_input.missing_observation_ids}")
```

