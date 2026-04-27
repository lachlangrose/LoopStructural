# loop_engine Design Document

**Version:** 1.0  
**Date:** April 2026  
**Scope:** The `loop_engine` package — the geological interpretation and orchestration layer of LoopStructural 2.0

This document is a deep-dive companion to the top-level [DESIGN.md](../../DESIGN.md). Where the project-level document gives a cross-module view, this document describes the internal design of `loop_engine` in full detail: responsibilities, class structure, internal data-flow, design decisions, and extension patterns.

> **Central thesis:** `loop_engine` is the only place in the system where geological knowledge is applied. `loop_model` describes geology in framework-agnostic terms (features, roles, relationships). `loop_interpolation` solves constrained implicit functions with no awareness of geology. `loop_engine` is the translation layer — it reads geological intent from the schema and expresses it as the mathematical constraints that interpolators understand.

---

## Table of Contents

1. [Module Role and Boundaries](#module-role-and-boundaries)
2. [The Geological Interpretation Layer](#the-geological-interpretation-layer)
3. [Package Structure](#package-structure)
4. [Class Reference](#class-reference)
   - [Model](#model)
   - [ObservationLinker and InterpolatorInput](#observationlinker-and-interpolatorinput)
   - [Task](#task)
   - [ModelState](#modelstate)
   - [GeologicalFeature (solved)](#geologicalfeature-solved)
   - [FeatureBuilderDispatcher](#featurebuilderdispatcher)
   - [BaseBuilder](#basebuilder)
   - [StratigraphyBuilder](#stratigraphybuilder)
   - [FaultBuilder](#faultbuilder)
5. [Internal Data Flow](#internal-data-flow)
6. [Interpolation Strategies](#interpolation-strategies)
7. [Bounding Box Resolution](#bounding-box-resolution)
8. [Constraint Preparation Pipeline](#constraint-preparation-pipeline)
9. [Extension Points](#extension-points)
10. [Design Decisions and Rationale](#design-decisions-and-rationale)
11. [Testing Conventions](#testing-conventions)

---

## Module Role and Boundaries

`loop_engine` is the **geological interpretation layer**. It sits between the schema layer (`loop_model`) and the solver layer (`loop_interpolation`), and it is the only module in the system that understands geology.

```
┌─────────────────────────────────────────────────────────────────┐
│  loop_model                                                     │
│  Geological schema — framework-agnostic                         │
│  Describes *what* the geology is (features, roles,              │
│  relationships) without reference to any modelling approach     │
└───────────────────────────────┬─────────────────────────────────┘
                                │ GeologicalSchema, DataRole, ...
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  loop_engine                               ← this module        │
│                                                                 │
│  Geological interpretation                                      │
│  Reads geological intent and translates it into the             │
│  mathematical language that interpolators understand            │
│                                                                 │
│  ├─ Compilation    (schema graph → ordered Task list)           │
│  ├─ Data linking   (observations + roles → constraint arrays)   │
│  ├─ Interpretation (DataRole semantics → isovalue, type)        │
│  ├─ Dispatch       (geological feature type → builder)          │
│  └─ State          (solved results)                             │
└───────────────────────────────┬─────────────────────────────────┘
                                │ value/normal/tangent constraints
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  loop_interpolation                                             │
│  Constrained implicit function solver — geology-agnostic        │
│  Accepts arrays of value/gradient/tangent constraints and       │
│  produces a scalar field. Has no concept of faults, units,      │
│  or any geological meaning.                                     │
└─────────────────────────────────────────────────────────────────┘
```

**What `loop_engine` does:**
- Orchestrate the solve in DAG order (kinematic chain)
- Resolve data_links from schema features to observation objects
- **Apply geological interpretation**: map `DataRole` semantics to constraint types and isovalues
- Dispatch each feature to the right builder class based on geological feature type
- Cache grouped-conformable feature groups to avoid redundant solves
- Wrap solved interpolators in a uniform `GeologicalFeature` representation

**What `loop_engine` does not do:**
- Define the geological schema or feature types (that is `loop_model`)
- Implement any interpolation mathematics (that is `loop_interpolation`)
- Hold or manage raw observation data (that lives in `LoopProject.observations`)
- Provide visualisation or export (that is the visualisation package)

---

## The Geological Interpretation Layer

This is the core design principle of `loop_engine` and the reason the module exists as a distinct layer.

### The Three Concerns are Separated by Design

| Layer | What it knows | What it does not know |
|-------|---------------|-----------------------|
| `loop_model` | Geology — features, relationships, observational roles | How any modelling method works |
| `loop_engine` | Both geology and mathematical constraints | The solver internals |
| `loop_interpolation` | Constrained implicit function mathematics | Geology |

This separation is intentional and strictly enforced through the dependency graph. `loop_model` has no dependency on `loop_interpolation`. `loop_interpolation` has no dependency on `loop_model`. Only `loop_engine` imports from both.

### The Schema is Framework-Agnostic

A `GeologicalSchema` from `loop_model` makes no assumptions about interpolation. It does not mention grids, basis functions, solvers, or constraint weights. It describes:
- **What features exist** — units, faults, folds, their names and UUIDs
- **How features relate** — the DAG edges (`overlies`, `displaces`, etc.)
- **What observations belong to each feature** — via `DataRole`-tagged data links

The same schema could, in principle, be consumed by a completely different modelling back-end — a voxel-based method, a process-based simulator, or a purely analytical approach. `loop_engine` is the adapter that makes it work with the implicit interpolation approach implemented in `loop_interpolation`.

### The Interpolator Knows No Geology

`loop_interpolation` receives only arrays of numbers:
- `(N, 4)` — positions with a scalar isovalue (the implicit function should equal this value here)
- `(M, 6)` — positions with a direction vector (the gradient of the implicit function should be parallel to this)
- `(K, 6)` — positions with a tangent vector (the gradient should be perpendicular to this)

None of these arrays carry any concept of fault, unit, bedding, or slip. The interpolator fits a scalar field that satisfies these constraints. It has no opinion on geological correctness.

### loop_engine Holds the Geological Knowledge

The translation from schema intent to constraint arrays is where all geological reasoning happens. Examples of geological decisions made entirely inside `loop_engine`:

**Isovalue assignment (FaultBuilder):**
```
trace observation (DataRole "trace")          → isovalue 0.0
hanging_wall observation (DataRole "hanging_wall") → isovalue +1.0
footwall observation (DataRole "footwall")    → isovalue −1.0
```
The interpolator simply fits a field that equals those numbers at those locations. The geological meaning — that the zero isosurface is the fault plane, and positive/negative identify the two blocks — is entirely a `loop_engine` convention.

**Gradient vs. tangent disambiguation (ObservationLinker):**
```
Orientation with type "bedding"    → gradient constraint (normal to bedding)
Orientation with type "lineation"  → tangent constraint (lies in the surface)
```
The interpolator accepts both. `loop_engine` decides which constraint type best represents each geological observation type.

**Conformable grouping (StratigraphyBuilder):**
```
Units connected by "overlies" edges → solve as a single shared scalar field
Units without conformable relationships → solve independently
```
The decision to share an interpolation domain for conformable units is a geological insight (conformable units have the same fold geometry) encoded as an engine-level strategy.

**Geometry inference from trace (FaultBuilder):**
When no orientation data is available, `loop_engine` infers a plausible fault normal and slip direction from the geometry of the map trace. This is domain knowledge about how fault traces relate to fault planes — not something the interpolator can know.

### Consequence: Adding New Geological Features Means Extending loop_engine

If a new geological feature type is added to `loop_model` (e.g. an unconformity, an intrusion, a dyke), the work to make it solvable belongs in `loop_engine`:
- A new builder in `features/` that interprets the feature's `DataRole` semantics into constraint arrays
- Registration in `FeatureBuilderDispatcher` to route the new feature type
- Any geological heuristics (inferred isovalues, constraint type disambiguation, grouping rules)

`loop_interpolation` requires no changes — it only needs valid constraint arrays.

---

## Package Structure

```
packages/loop_engine/src/loop_engine/
│
├── __init__.py                  # Public API: Model, ObservationLinker,
│                                #   InterpolatorInput, LinkedObservation
│
├── core/
│   ├── model.py                 # Model — the main orchestrator class
│   ├── linker.py                # ObservationLinker + InterpolatorInput + LinkedObservation
│   ├── state.py                 # ModelState — snapshot of solved results
│   ├── geological_feature.py    # GeologicalFeature — thin wrapper over a solved representation
│   └── representation.py       # ModelRepresentation — placeholder for output queries (WIP)
│
├── tasks/
│   └── base.py                  # Task — execution unit carrying feature + linked data
│
└── features/
    ├── dispatch.py              # FeatureBuilderDispatcher — routes payloads to builders
    ├── basebuilder.py           # BaseBuilder — common interpolator wiring utilities
    ├── stratigraphy.py          # StratigraphyBuilder — handles Unit features
    ├── fault.py                 # FaultBuilder — role-aware fault surface building
    └── fold.py                  # FoldBuilder — placeholder (not yet implemented)
```

### Public API

Only four symbols are exported from `loop_engine.__init__`:

| Symbol | Description |
|--------|-------------|
| `Model` | Main orchestrator; entry point for all solve operations |
| `ObservationLinker` | Converts schema data_links to `InterpolatorInput` structs |
| `InterpolatorInput` | Dataclass carrying per-feature constraint arrays |
| `LinkedObservation` | Frozen dataclass for one resolved (uid, role, observation) triple |

---

## Class Reference

### Model

**File:** `core/model.py`

The single entry point for all engine operations. Holds a reference to the schema, an `ObservationLinker`, and a `FeatureBuilderDispatcher`.

```python
class Model:
    schema: GeologicalSchema          # Source of features and DAG
    grid: BoundingBox | None          # Optional explicit spatial domain
    interpolatortype: str             # Default solver, e.g. "FDI"
    nelements: int                    # Default resolution hint
    interpolation_strategy: str       # "independent" | "grouped_conformable"
    current_state: ModelState | None  # Most recent solve result
```

#### Key Methods

| Method | Purpose |
|--------|---------|
| `solve()` | The main entry point. Compile → execute tasks → store ModelState |
| `_compile_tasks()` | Topological sort → link observations → create Task list |
| `_coerce_solved_feature(id, result)` | Wrap an interpolator in `GeologicalFeature` |
| `evaluate_scalar_field(positions, feature_id|name)` | Evaluate implicit function post-solve |
| `extract_unit_basal_surface(unit_id|name, value)` | Extract an isosurface |
| `get_solved_feature(feature_id|name)` | Retrieve a wrapped result from current_state |
| `_resolve_feature_id(id, name)` | Name → UUID lookup |
| `_validate_schema()` | Guard: ensures schema has required interface |

#### `solve()` in Detail

```
solve()
 ├─ _compile_tasks()
 │   ├─ schema.get_execution_order()         → [uuid, uuid, ...]
 │   ├─ linker.build_inputs_by_feature(ids)  → {uuid: InterpolatorInput}
 │   └─ Task(feature_id, predecessors, linked_data, feature) × N
 │
 ├─ new_state = ModelState(grid)
 │
 ├─ for each task:
 │   ├─ if task.is_dirty:
 │   │   ├─ inputs = [new_state.get_feature(p) for p in task.predecessors]
 │   │   ├─ payload = task.execute(inputs)
 │   │   ├─ build_result = _builder_dispatcher.build(payload)
 │   │   ├─ solved = _coerce_solved_feature(task.id, build_result)
 │   │   └─ new_state.results[task.id] = solved (or build_result if not wrappable)
 │   └─ else: reuse from previous state (cache hit)
 │
 └─ self.current_state = new_state → return state
```

The `dependency_results` fed to each `task.execute()` follow the **kinematic chain**: the solved representation of every predecessor (e.g. an already-solved fault) is available to downstream builders. Today builders receive this list but defer full kinematic interaction to future work.

---

### ObservationLinker and InterpolatorInput

**File:** `core/linker.py`

`ObservationLinker` is the bridge from schema intent to numerical constraints. It reads `feature.data_links`, resolves each link to an observation object from `schema.project.observations`, and fills a per-feature `InterpolatorInput`.

```python
@dataclass
class InterpolatorInput:
    feature_id: str
    feature_name: str | None
    feature_type: str
    point_constraints: np.ndarray       # shape (N, 3) — XYZ positions
    gradient_constraints: np.ndarray    # shape (M, 6) — XYZ + normalized direction
    tangent_constraints: np.ndarray     # shape (K, 6) — XYZ + normalized tangent
    by_role: dict[str, list[LinkedObservation]]  # observations grouped by DataRole
    missing_observation_ids: list[str]  # UIDs that could not be resolved

@dataclass(frozen=True)
class LinkedObservation:
    obs_uid: str
    role: str
    observation: Any | None    # None if lookup failed
```

#### Resolution Algorithm (`build_feature_input`)

For each `data_link` in `feature.data_links`:

1. **Parse the link** — extract `(obs_uid, role)`:
   - If the link has `.obs_uid` (a `DataRole` object): use its attributes directly
   - Otherwise: treat the link as a raw string uid with role `"data"`

2. **Lookup the observation** — `schema.project.observations.get(obs_uid)`:
   - On miss: add to `missing_observation_ids`, skip constraint extraction

3. **Append constraints** (`_append_observation_constraints`):
   - **Observations with `.vertices`** (PointSet, LineSet): extracted to `point_constraints`
     - If the observation also has a `to_tangent_vectors()` callable, those vectors are added to `tangent_constraints`
   - **Observations with `.coords` + `.vector`** (Orientation):
     - If observation type contains `"tangent"`: → `tangent_constraints`
     - Otherwise: → `gradient_constraints`
   - **Observations with `.coords` only**: → `point_constraints`

4. **Group by role** — every resolved observation is added to `by_role[role]` regardless of constraint type, for builders that need role-specific logic (e.g. `FaultBuilder`).

#### Vector Normalization

All direction vectors written to `gradient_constraints` and `tangent_constraints` are *not* normalized at this stage. Normalization happens inside `BaseBuilder._normalize_xyz_vectors()` as part of constraint preparation so that the linker remains a pure data-extraction step.

---

### Task

**File:** `tasks/base.py`

A `Task` is the minimal execution unit for one feature. It carries all information needed to produce a solve payload.

```python
class Task:
    id: str                          # feature UUID
    dependencies: list[str]          # upstream feature UUIDs (same as predecessors)
    predecessors: list[str]          # alias for dependencies
    linked_data: InterpolatorInput   # resolved constraints for this feature
    feature: GeologicalFeature       # the schema feature object
    is_dirty: bool = True            # whether this task needs re-solving
```

`Task.execute(dependency_results)` is intentionally thin — it just packages its attributes into a dict payload:

```python
{
    "feature_id": self.id,
    "feature": self.feature,
    "dependencies": self.predecessors,
    "dependency_results": dependency_results,   # list of solved upstream features
    "linked_data": self.linked_data,
}
```

This decoupled design means the builder (not the task) owns all solve logic. Tasks can be extended to carry dirty-tracking state, metadata, or caching hints without affecting builders.

---

### ModelState

**File:** `core/state.py`

A lightweight snapshot of results after a solve.

```python
class ModelState:
    grid: BoundingBox | None                      # Shared spatial domain
    results: dict[str, GeologicalFeature | Any]   # feature_id → solved result
    version: int                                  # Version counter (future use)

    def get_feature(self, feature_id: str) -> Any | None
```

`results` values are nominally `GeologicalFeature` instances (when `_coerce_solved_feature` succeeds), but can fall back to raw interpolators or payload dicts when wrapping is not possible. Callers should use `model.get_solved_feature()` rather than accessing `state.results` directly to benefit from name resolution and error handling.

---

### GeologicalFeature (solved)

**File:** `core/geological_feature.py`

A thin wrapper that exposes a solved `BaseRepresentation` through a stable interface, regardless of which concrete interpolator was used internally.

```python
class GeologicalFeature:
    name: str
    representation: BaseRepresentation

    def evaluate_value(self, position: np.ndarray) -> np.ndarray
    def evaluate_gradient(self, position: np.ndarray) -> np.ndarray
    def min(self) -> float
    def max(self) -> float
    def surfaces(self, value: float) -> dict | None
```

All method calls are delegated directly to `self.representation`. The wrapper adds only the `name` attribute and the uniform type identity — callers can use `isinstance(result, GeologicalFeature)` as a solved-feature check without knowing the solver type.

---

### FeatureBuilderDispatcher

**File:** `features/dispatch.py`

Routes task payloads to the correct builder based on the feature's Python type name.

```python
class FeatureBuilderDispatcher:
    generic_builder: BaseBuilder
    stratigraphy_builder: StratigraphyBuilder
    fault_builder: FaultBuilder

    def build(self, task_payload: dict) -> object | None
```

#### Routing Logic

Feature type is determined by `type(feature).__name__` (lowercased), falling back to `linked_data.feature_type`:

| Type name | Builder used |
|-----------|-------------|
| `"unit"` or `"geologicalunit"` | `StratigraphyBuilder` |
| `"fault"` | `FaultBuilder` |
| anything else | `BaseBuilder` (generic) |

The dispatcher is constructed once per `Model` instance by `create_default_feature_builder_dispatcher(model)`. To use a custom builder for a new feature type, subclass `FeatureBuilderDispatcher` and override `build()`, or monkeypatch the dispatcher on an existing `Model` instance.

---

### BaseBuilder

**File:** `features/basebuilder.py`

Provides common utilities for constraint preparation and interpolator wiring. All concrete builders inherit from this class.

```python
class BaseBuilder:
    model: Model

    # Entry point
    def build(self, task_payload: dict) -> object | None

    # Two-step helpers
    def prepare_constraints(self, linked_data) -> PreparedConstraints
    def build_from_constraints(self, linked_data, prepared, build_params) -> object | None

    # Convenience
    def build_from_linked_data(self, linked_data) -> object | None

    # Solver configuration
    def configure_builder(self, builder, build_params: dict) -> None
    def apply_optional_constraints(builder, linked_data) -> None

    # Geometry utilities
    @staticmethod
    def _normalize_xyz_vectors(rows: np.ndarray) -> np.ndarray
    def _resolve_bounding_box(self, linked_data) -> BoundingBox | None
    def _infer_fallback_bounding_box(self, linked_data) -> BoundingBox | None
```

#### `PreparedConstraints`

```python
@dataclass
class PreparedConstraints:
    value_constraints: np.ndarray     # shape (N, 4) — XYZ + isovalue
    normal_constraints: np.ndarray    # shape (M, 6) — XYZ + normalized normal
    tangent_constraints: np.ndarray   # shape (K, 6) — XYZ + normalized tangent
```

`prepare_constraints` transforms an `InterpolatorInput` into this form:
- `point_constraints` (N×3) → `value_constraints` (N×4) by appending a column of zeros (isovalue = 0.0 by default)
- `gradient_constraints` and `tangent_constraints` both pass through `_normalize_xyz_vectors`, which drops zero-magnitude vectors

#### `build_from_constraints` — Interpolator Wiring

This method is the bridge into `loop_interpolation`:

```
build_from_constraints()
 ├─ Guard: return None if all three constraint arrays are empty
 ├─ InterpolatorBuilder(interpolatortype, bounding_box, nelements)
 ├─ configure_builder(builder, build_params)   # solver, regularisation, etc.
 ├─ builder.add_value_constraints(...)
 ├─ builder.add_normal_constraints(...)
 ├─ builder.add_tangent_constraints(...)
 ├─ apply_optional_constraints(builder, linked_data)   # inequality constraints
 ├─ builder.setup_interpolator()
 ├─ builder.solve([tol=...])
 └─ return builder.build()                     # GeologicalInterpolator instance
```

`build_params` (sourced from `feature.build_params`) can carry:
- `"solver"` — override default solver name
- `"solver_kwargs"` — extra keyword arguments for the solver
- `"tol"` — convergence tolerance
- `"use_regularisation_weight_scale"` — bool flag
- `"regularisation_weight_sigma"` — regularisation scaling factor
- `"trace_iso"`, `"hanging_wall_iso"`, `"footwall_iso"` — used by `FaultBuilder`

---

### StratigraphyBuilder

**File:** `features/stratigraphy.py`

Handles `Unit` / `GeologicalUnit` features. Supports two interpolation strategies:

#### Strategy: `"independent"` (default)

Each unit is solved independently using only its own linked observations. Delegates directly to `BaseBuilder.build_from_linked_data()`.

#### Strategy: `"grouped_conformable"`

Units connected by `"overlies"` relations in the schema DAG are solved together as a single interpolation problem. All their constraint arrays are merged into one `MergedLinkedInput` and solved once. Subsequent units in the same group retrieve the cached result.

```
_build_grouped_conformable(task_payload)
 ├─ _grouped_conformable_members(feature_id)
 │   └─ BFS over DAG following "overlies" edges → set of unit UUIDs
 │      group_key = "grouped_conformable:" + sorted joined UUIDs
 │
 ├─ Check _grouped_unit_build_cache[group_key] → return if hit
 │
 ├─ linker.build_inputs_by_feature(group_members)
 ├─ _merge_linked_inputs(group_members, linked_by_feature)
 │   └─ Concatenate point/gradient/tangent arrays from all members
 │
 ├─ build_from_linked_data(merged)
 └─ store in cache[group_key] → return
```

The cache is stored on `model._grouped_unit_build_cache` (a plain dict, reset at the start of each `solve()`).

---

### FaultBuilder

**File:** `features/fault.py`

Handles `Fault` features with role-aware value constraint assignment. Unlike stratigraphy (where all point contacts get isovalue 0), faults assign distinct isovalues based on observation role:

| Role | Default isovalue | Source |
|------|-----------------|--------|
| `"trace"` | 0.0 | `build_params["trace_iso"]` |
| `"hanging_wall"` | 1.0 | `build_params["hanging_wall_iso"]` |
| `"footwall"` | -1.0 | `build_params["footwall_iso"]` |

The default isovalues can be overridden via `feature.build_params`.

#### Geometry Inference from Trace

When no explicit orientation (`"orientation"` role) or slip vector (`"slip_vector"` role) observations are provided, `FaultBuilder` infers approximate constraints from the trace geometry:

- **Strike direction**: PCA on trace point positions (`_principal_direction`)
- **Dip direction**: cross product of strike direction and vertical `[0, 0, 1]`
- **Normal**: cross product of strike and dip direction
- **Slip vector**: approximately along dip

These inferred constraints are added at the centroid of the trace points. They act as weak geometric guidance and are overridden whenever explicit observations are available.

---

## Internal Data Flow

### Complete Flow Diagram

```
LoopProject.observations           GeologicalSchema
 {uuid: PointSet|Orientation|...}   .features {uuid: Unit|Fault|...}
                │                              │
                │                   .dag: DiGraph
                │                   .get_execution_order()
                │                              │
                └──────────── ObservationLinker.build_inputs_by_feature()
                                               │
                               for each feature_id in topological order:
                                   InterpolatorInput(
                                       point_constraints,
                                       gradient_constraints,
                                       tangent_constraints,
                                       by_role,
                                       missing_observation_ids,
                                   )
                                               │
                                          Task(id, predecessors, linked_data, feature)
                                               │
                                          task.execute(upstream_results)
                                               │ → payload dict
                                               ▼
                                  FeatureBuilderDispatcher.build(payload)
                                   │
                                   ├─ Unit/GeologicalUnit → StratigraphyBuilder
                                   ├─ Fault              → FaultBuilder
                                   └─ other              → BaseBuilder
                                               │
                              BaseBuilder.prepare_constraints(linked_data)
                               → PreparedConstraints(value, normal, tangent)
                                               │
                              BaseBuilder.build_from_constraints(...)
                               → InterpolatorBuilder (loop_interpolation)
                                  .add_value_constraints(...)
                                  .add_normal_constraints(...)
                                  .add_tangent_constraints(...)
                                  .setup_interpolator()
                                  .solve()
                                  .build()
                               → GeologicalInterpolator (solved)
                                               │
                              Model._coerce_solved_feature(id, interpolator)
                               → GeologicalFeature(name, representation=interpolator)
                                               │
                              ModelState.results[feature_id] = GeologicalFeature
```

### Constraint Formats Summary

All constraint arrays are numpy `float64` with consistent column layouts:

| Array | Shape | Columns |
|-------|-------|---------|
| `point_constraints` | (N, 3) | X, Y, Z |
| `gradient_constraints` | (M, 6) | X, Y, Z, Gx, Gy, Gz |
| `tangent_constraints` | (K, 6) | X, Y, Z, Tx, Ty, Tz |
| `value_constraints` (PreparedConstraints) | (N, 4) | X, Y, Z, value |
| `normal_constraints` (PreparedConstraints) | (M, 6) | X, Y, Z, Nx, Ny, Nz (normalized) |

---

## Interpolation Strategies

The `interpolation_strategy` parameter on `Model` controls how stratigraphy features are solved:

### `"independent"` (default)

Each stratigraphic unit is solved as a separate scalar field using only its own observations. Units share the same spatial domain (bounding box) but have independent interpolation problems. This is the most general strategy and always produces a valid result.

**Use when:** Units have distinct observation sets; unconformable sequences; rapid prototyping.

### `"grouped_conformable"`

Conformable unit groups (units connected by `"overlies"` edges in the DAG) share a single interpolation problem. All their observations are pooled together. This enforces geometric consistency between conformable units at the cost of a larger (and slower) solve.

**Use when:** The stratigraphic sequence is conformable and you want globally consistent stratigraphy. Requires `"overlies"` edges in the schema DAG.

**Cache key format:** `"grouped_conformable:<uuid1>|<uuid2>|..."` (sorted UUIDs, `|`-joined).

---

## Bounding Box Resolution

Each call to `BaseBuilder.build_from_constraints()` needs a `BoundingBox` for the interpolator. The resolution order is:

1. **Schema bounding box** (`schema.bounding_box`): Used when `bounding_box.valid` is truthy
2. **Fallback inference** (`_infer_fallback_bounding_box`): Used when the schema bounding box is invalid or missing

The fallback collects all coordinate blocks from:
- All observations in `schema.project.observations` (vertices or coords)
- The current `linked_data` constraint arrays

It then computes a tight bounding box with a 5% buffer on each side (minimum buffer 1e-3 per axis). Collapsed axes (where `max - min < 1e-9`) are expanded to width 1.0 before buffering.

---

## Constraint Preparation Pipeline

### Step 1: Observation → Constraint Array (ObservationLinker)

```
data_link → (obs_uid, role) → observation object
observation → determine type by duck-typing:
  has .vertices     → point_constraints (+ tangent_constraints if to_tangent_vectors)
  has .coords+.vector, type contains "tangent" → tangent_constraints
  has .coords+.vector → gradient_constraints
  has .coords only → point_constraints
```

At this stage, all vectors are stored **as-is** (not normalized).

### Step 2: Role Specialization (FaultBuilder / StratigraphyBuilder)

Each builder interprets `by_role` to assign isovalues or merge inputs before the generic prepare step.

### Step 3: Normalization (BaseBuilder._normalize_xyz_vectors)

Direction vectors (in both `gradient_constraints` and `tangent_constraints`) are normalized to unit length. Zero-magnitude vectors are silently dropped. This ensures `loop_interpolation` receives only valid directional constraints.

### Step 4: Value Column Injection (BaseBuilder.prepare_constraints)

`point_constraints` (N×3) are extended to `value_constraints` (N×4) by appending a column of zeros. This sets the isovalue of all interface points to 0.0 — the implicit function surface that maps to the geological contact. `FaultBuilder` overrides this step to assign role-specific isovalues.

---

## Extension Points

### 1. Adding a New Feature Builder

Create a class in `features/` that implements `build(task_payload: dict) -> object | None`. Extend `FeatureBuilderDispatcher.build()` to route the new feature type:

```python
# features/intrusion.py
from .basebuilder import BaseBuilder

class IntrusionBuilder(BaseBuilder):
    def build(self, task_payload: dict) -> object | None:
        # Intrusion-specific role handling
        linked_data = task_payload["linked_data"]
        # e.g., roof and floor contacts get different isovalues
        ...
        return self.build_from_constraints(linked_data, prepared, build_params)
```

```python
# features/dispatch.py  (modified)
class FeatureBuilderDispatcher:
    def __init__(self, model):
        ...
        self.intrusion_builder = IntrusionBuilder(model)

    def build(self, task_payload):
        ...
        if feature_type == "intrusion":
            return self.intrusion_builder.build(task_payload)
        ...
```

### 2. Adding a New Interpolation Strategy

The `interpolation_strategy` string is currently checked only inside `StratigraphyBuilder._grouped_mode_enabled()`. To add a new strategy:

1. Add a check in `StratigraphyBuilder.build()` (or the relevant builder)
2. Implement the merging or batching logic following the pattern of `_build_grouped_conformable`
3. Document the new strategy name and semantics here and in the top-level DESIGN.md

### 3. Custom Bounding Box per Feature

To use a per-feature bounding box, add a `bounding_box` field to the schema feature or `build_params`. Override `BaseBuilder._resolve_bounding_box()` in a subclass:

```python
class MyBuilder(BaseBuilder):
    def _resolve_bounding_box(self, linked_data):
        schema_feature = self.model.schema.features.get(linked_data.feature_id)
        custom_bbox = getattr(schema_feature, "bounding_box", None)
        if custom_bbox is not None and custom_bbox.valid:
            return custom_bbox
        return super()._resolve_bounding_box(linked_data)
```

### 4. Extending Task with Dirty Tracking

`Task.is_dirty` is currently always `True`. To enable incremental re-solving, maintain a hash or version token of `linked_data` + observation checksums, and set `is_dirty = False` when they match the previous solve. The `Model.solve()` path already handles this — it falls back to `current_state.get_feature(task.id)` when `is_dirty` is False.

### 5. Kinematic Chain Consumers

`task.execute(dependency_results)` passes previously solved upstream features as `dependency_results` in the payload. Future builders can use these to:
- Apply fault displacement to unit contacts before building the unit's interpolation problem
- Use the hanging-wall/footwall distinction from a solved fault to create inequality constraints on units

---

## Design Decisions and Rationale

### Geological Knowledge Belongs in Builders, Nowhere Else

Every piece of geological reasoning — which isovalue a hanging-wall contact should receive, whether two units should share an interpolation domain, whether a trace implies a particular fault geometry — belongs in a builder class inside `features/`. It does not belong in the schema (which is framework-agnostic) and it does not belong in the interpolator (which is geology-agnostic).

This rule has a practical implication: **if you find yourself adding geological logic to `loop_interpolation`, stop and move it to a builder in `loop_engine`.** Conversely, if you find yourself adding interpolator-type decisions to `loop_model`, those decisions belong in `loop_engine` or a builder.

### Payload-Driven Dispatch

Builders receive a plain `dict` payload rather than being called with typed arguments. This makes it straightforward to add new fields to the payload (e.g., `upstream_results`, `metadata`) without changing builder signatures. The dict also flows across the boundary cleanly into `loop_interpolation` without circular type dependencies.

### Task is Thin; Builder Owns Logic

`Task.execute()` does nothing but assemble a dict. All solve logic lives in builders. This keeps the execution graph management (ordering, caching, dirty tracking) cleanly separated from interpolation details. It also makes tasks unit-testable without any interpolation machinery.

### ObservationLinker is a Pure Extraction Step

The linker does not normalize vectors, assign isovalues, or make any interpolator decisions. It extracts what the schema references. Builders then shape those extractions to their needs. This separation allows the same `InterpolatorInput` to be consumed by different builders with different roles interpretations (e.g., `FaultBuilder` vs `StratigraphyBuilder`).

### GeologicalFeature Wrapper

Returning a `GeologicalFeature` wrapper from every build (rather than the raw interpolator) gives callers a stable type to check. `model.get_solved_feature()` can guarantee a `GeologicalFeature` return type. It also allows future implementations to add post-processing (domain masking, scalar field offsets) inside the wrapper without changing the interpolation API.

### Grouped-Conformable Cache on Model

The cache for grouped-conformable builds (`_grouped_unit_build_cache`) lives on the `Model` instance, not the builder. This is intentional: it is reset at the beginning of each `solve()` call (a fresh dict is assigned), so there is no stale state between solves. The builder reads it via `getattr(self.model, ...)` to avoid a hard coupling.

### Missing Observations are Non-Fatal

When a `data_link` references an observation that cannot be found in `project.observations`, the linker records the UID in `missing_observation_ids` and continues. This allows partial schemas and in-progress models to compile and attempt a solve rather than raising at link time. Callers can inspect `InterpolatorInput.missing_observation_ids` for warnings.

---

## Testing Conventions

Tests live in `packages/loop_engine/tests/`. The test suite covers:

| File | Coverage area |
|------|--------------|
| `test_linker.py` | `ObservationLinker` — observation resolution, constraint extraction |
| `test_model_compile.py` | `Model._compile_tasks()`, `solve()`, `evaluate_scalar_field()`, `extract_unit_basal_surface()` |
| `test_fault_builder.py` | `FaultBuilder` — role-aware value assignment, trace inference |
| `conftest.py` | Shared fixtures |

### Testing Philosophy

- **Unit tests use mock schemas**: `GeologicalSchema` with `PointSet` and `Orientation` fixtures — no real interpolation.
- **Integration tests use `Model.solve()`**: small schemas with real `loop_interpolation` solvers to exercise the full path.
- **Builders are tested through the dispatcher**: do not call builder methods directly in tests; always go through `FeatureBuilderDispatcher.build()` to catch routing regressions.
- **Mock solved features**: tests that exercise `evaluate_scalar_field()` or `extract_unit_basal_surface()` inject a `_MockSolvedFeature` into `current_state.results` rather than running a full solve.

### Running Tests

```powershell
# From workspace root (with dev conda environment active)
pytest packages/loop_engine/tests/ -v
```
