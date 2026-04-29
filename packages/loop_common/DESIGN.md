# loop_common Design Document

## Overview

`loop_common` is the foundational layer of the LoopStructural 2.0 framework. It provides geology-agnostic utilities, data structures, and abstract interfaces that are shared across all higher-level packages. Nothing in `loop_common` knows about geological features, model building, or interpolation algorithms — it exists purely to provide the primitives those layers are built on.

**Package:** `loop-common`  
**Location:** `packages/loop_common/`  
**Dependencies:** `numpy`, `pandas`, `pydantic`

---

## Position in the Loop Framework

LoopStructural 2.0 is structured as a strict dependency hierarchy. Each layer depends only on layers below it; no lower layer knows about those above it.

```
┌──────────────────────────────────────────────────────┐
│            User Applications / APIs                   │
├──────────────────────────────────────────────────────┤
│  loop_model        Geological schema, features, DAG  │
├──────────────────────────────────────────────────────┤
│  loop_engine       Model compilation & execution     │
├──────────────────────────────────────────────────────┤
│  loop_interpolation  Constrained implicit functions  │
├──────────────────────────────────────────────────────┤
│  loop_common       Shared foundations (this package) │
└──────────────────────────────────────────────────────┘
```

`loop_common` sits at the base. Every other package in the framework imports from it; it imports from none of them. This means:

- Types defined here (e.g. `BoundingBox`, `PointSet`, `BaseRepresentation`) are safe to pass across package boundaries without creating circular dependencies.
- Interfaces defined here (e.g. `BaseSupport`, `BaseRepresentation`) are the contracts that interpolators and supports must satisfy, making higher layers polymorphic with respect to mesh type and solver type.
- Utilities defined here (e.g. `strikedip2vector`, `get_logger`) are available to all layers without duplication.

---

## Design Principles

1. **No geological knowledge.** `loop_common` does not know what a fault, fold, or stratigraphic unit is. It knows about points, vectors, grids, meshes, and mathematical operations.

2. **Stable interfaces.** Abstract base classes and Pydantic models defined here are the API contract for the whole framework. They should change rarely and only with care.

3. **Serialization by default.** All domain objects support round-trip serialization (JSON, YAML, dict). This is enforced at the base level via `LoopEntity` and `NumpyArray`.

4. **Vectorized operations.** Mathematical functions accept both scalars and arrays. Batch processing is the expected use case.

5. **Plug-in support types.** The `BaseSupport` interface allows new discretization schemes to be added without modifying interpolation code. The `SupportFactory` dispatches construction by `SupportType` enum.

---

## Modules

### `base` — Entity Foundation

**File:** `base.py`

All persistent domain objects in the Loop framework inherit from `LoopEntity`. It provides:

- A stable `uuid` (auto-generated) for identity across serialization boundaries.
- A human-readable `name`.
- An ISO-8601 `last_modified` timestamp that updates via `mark_modified()`.
- Round-trip serialization: `to_json()`, `to_yaml()`, `to_dict()`, `from_json()`.

`LoopEntity` is a Pydantic `BaseModel` with `validate_assignment=True` and `extra="forbid"`, which means fields are validated on every assignment and typo-fields are rejected at construction time.

The `NumpyArray` annotated type enables Pydantic to transparently accept lists and tuples as numpy arrays and serialize them back to lists for JSON output.

**What belongs here:** Any object that needs identity, timestamps, and JSON-safe serialization as its primary concerns.

---

### `geometry` — Spatial Primitives

**File:** `geometry/`  
**Exports:** `BoundingBox`, `ValuePoints`, `VectorPoints`, `Surface`

#### `BoundingBox`

The central spatial domain object for the framework. Every interpolation problem is defined within a `BoundingBox`. It holds:

- The world-space extent (`origin`, `maximum`).
- The discretization resolution (`nsteps` — cell counts per axis).
- An optional local coordinate frame (`set_local_transform`) defined by a world-space origin and a rotation matrix. This allows interpolation to be performed in a rotated frame (e.g., aligned with a fold axis) while world-space coordinates are preserved.

The `fit(locations)` method initializes the bounding box from a point cloud. `with_buffer(buffer)` returns a new box with a fractional margin applied, which is the standard construction path in model building.

All affine transformations are handled by `_apply_affine` using homogeneous 4×4 matrices.

#### `ValuePoints` and `VectorPoints`

Lightweight dataclasses for transporting computed field results (isovalues, gradients) between layers. They are not observation types — they represent output data ready for visualization or export. Both support VTK/PyVista output and multiple serialization formats.

#### `Surface`

A triangulated mesh representing an extracted isosurface or any other geological surface. Contains vertices, triangle connectivity, optional normals, and optional scalar/vector properties. Automatically removes NaN vertices on construction. Computes triangle areas and face normals on demand. The primary output type of `BaseRepresentation.surfaces()`.

---

### `interfaces` — Abstract Contracts

**File:** `interfaces/representation.py`  
**Exports:** `BaseRepresentation`

`BaseRepresentation` is the abstract interface that every interpolated implicit function must implement:

| Method | Contract |
|---|---|
| `evaluate_value(position)` | Return scalar field value at one or more positions |
| `evaluate_gradient(position)` | Return gradient vector (∇f) at one or more positions |
| `surfaces(value)` | Extract `Surface` at the given isovalue |
| `to_dict()` / `from_dict()` | Round-trip serialization |

Higher layers (`loop_engine`, `loop_model`) program against `BaseRepresentation` exclusively. They never interact with FDI, P1, RBF, or any other concrete solver type directly. This means interpolators in `loop_interpolation` can be replaced or extended without changing the model or engine layers.

Equality and hashing are implemented via `to_dict()`, so two representations with identical serialized state compare equal.

**What belongs here:** Contracts that define cross-package polymorphism boundaries.

---

### `observations` — Field Measurement Types

**File:** `observations/`  
**Exports:** `PointSet`, `Orientation` (`OrientationObservation`), `OrientationType`, `LineSet`

These classes represent raw geological field observations before they are converted into mathematical constraints.

#### `PointSet`

A set of XYZ coordinates (contacts, fold hinges, fault traces as points). Inherits `LoopEntity`. The simplest observation type — position only.

#### `OrientationObservation` (alias: `Orientation`)

Planar and linear orientation measurements (strike/dip, dip direction/dip, plunge/azimuth). Internally stores vectors, not angles — conversion from angles to vectors is performed once at construction via the math utilities in `loop_common.math`. The `type` field (`OrientationType.PLANE`, `LINEATION`, `TANGENT`) distinguishes how the vector should be interpreted as a constraint.

Factory class methods:
- `from_strike_dip()`
- `from_dip_direction_and_dip()`
- `from_plunge_and_plunge_direction()`

#### `LineSet`

An ordered set of polylines (fault traces, fold hinges) stored as concatenated vertices with offset indices. The `to_tangent_vectors()` method computes finite-difference tangent vectors at segment midpoints and returns them as `Orientation` objects with `type=TANGENT`. This is the primary mechanism for incorporating linear structural data as tangent constraints in the interpolation system.

**What belongs here:** Observation types that represent the geologist's raw input data. These are geometry-only — they carry no information about which interpolator or feature they belong to. That association is made by `loop_engine`.

---

### `supports` — Spatial Discretization

**File:** `supports/`  
**Exports:** `BaseSupport`, concrete grid/mesh classes, `SupportFactory`, `SupportType`

Supports are the discretized domains on which implicit functions are computed. They provide the mathematical basis for evaluating and assembling interpolation systems.

#### `BaseSupport`

Abstract interface requiring:

| Method / Property | Purpose |
|---|---|
| `evaluate_value(eval_points, property_array)` | Interpolate a nodal property to arbitrary positions |
| `evaluate_gradient(eval_points, property_array)` | Compute gradient of a nodal property at positions |
| `inside(pos)` | Test whether positions fall within the support |
| `get_element_for_location(pos)` | Find containing element and compute local coords + basis weights |
| `get_element_gradient_for_location(pos)` | Gradient-form basis data for constraint assembly |
| `set_nelements(nelements)` | Resize the mesh |
| `elements`, `n_elements`, `n_nodes`, `nodes`, `barycentre` | Mesh topology and geometry |

#### Concrete Implementations

| Class | Type | Basis | Notes |
|---|---|---|---|
| `StructuredGrid2D` | 2D Cartesian | Bilinear | Regular spacing |
| `StructuredGrid` | 3D Cartesian | Trilinear | Most common; used by FDI |
| `RectilinearGrid` | 3D Cartesian | Trilinear | Non-uniform spacing |
| `P1Unstructured2d` | 2D triangles | Linear | Unstructured |
| `P2Unstructured2d` | 2D triangles | Quadratic | Higher accuracy |
| `UnStructuredTetMesh` | 3D tetrahedra | Linear | Unstructured |
| `TetMesh` | 3D tetrahedra | Linear | Structured tet decomposition |
| `P2UnstructuredTetMesh` | 3D tetrahedra | Quadratic | Higher accuracy |

The `SupportFactory` dispatches construction by `SupportType` enum value, enabling supports to be created from serialized data without the caller importing concrete classes.

The AABB (axis-aligned bounding box) acceleration structure in `_aabb.py` is built for tetrahedral meshes to accelerate the point-in-element query from O(n_tets) to near-constant time using a sparse CSR overlay grid.

**What belongs here:** Any spatial discretization scheme that can satisfy the `BaseSupport` contract. The support is responsible for local geometry; it knows nothing about geological constraints or the interpolation objective.

---

### `math` — Geological Coordinate Utilities

**File:** `math/`  
**Exports:** All from `_maths.py`, `EuclideanTransformation`

#### Angle ↔ Vector Conversions

All functions are vectorized (accept scalars or (N,) arrays):

| Function | Input | Output |
|---|---|---|
| `strikedip2vector(strike, dip)` | Strike (azimuth), dip | Normal vector (N, 3) |
| `dipdipdirection2vector(dip_dir, dip)` | Dip direction, dip | Normal vector (N, 3) |
| `plungeazimuth2vector(plunge, azimuth)` | Plunge angle, azimuth | Lineation vector (N, 3) |
| `normal_vector_to_strike_and_dip(normal)` | Normal vector | [strike, dip] (N, 2) |
| `normal_vector_to_dip_and_dip_direction(normal)` | Normal vector | [dip_dir, dip] (N, 2) |
| `get_vectors(normal)` | Normal vector | (strike_vec, dip_vec) |
| `get_strike_vector(strike)` | Strike angle | Unit strike vector |
| `rotation(axis, angle)` | Axis, angle | Rotation matrices (N, 3, 3) |
| `rotate(vector, axis, angle)` | Vector, axis, angle | Rotated vectors (N, 3) |

Angle conventions follow geological standards: strike measured clockwise from north, right-hand rule for dip direction.

#### `EuclideanTransformation`

Fits a rotation-and-translation transformation to a point cloud using PCA (scikit-learn). Used to normalize fold data into a local coordinate frame aligned with the fold axis. Supports `fit`, `transform`, `inverse_transform`, and `fit_transform`.

#### `Operator` (finite difference stencils)

Pre-computed 3×3×3 finite-difference masks for first derivatives (Dx, Dy, Dz), second derivatives (Dxx, Dyy, Dzz), cross-derivatives (Dxy, Dxz, Dyz), and the Laplacian. Used directly by `FiniteDifferenceInterpolator` in `loop_interpolation` to assemble constraint rows.

**What belongs here:** Mathematical operations that are purely numerical and could apply in any domain (not specific to geological modelling).

---

### `logging` — Unified Logger

**File:** `logging/logger.py`  
**Exports:** `get_logger`

A single function `get_logger(name, level, log_file, fmt, use_loguru)` that returns a logger object with `.debug()`, `.info()`, `.warning()`, `.error()`, and `.exception()` methods. It:

- Auto-detects and prefers `loguru` if installed; falls back to stdlib `logging`.
- Caches loggers by name to avoid duplicate handlers.
- Optionally writes to a file as well as stdout.

Usage across the framework is simply `log = get_logger(__name__)` at module top.

**What belongs here:** Any shared infrastructure concern (logging, configuration) that all packages need without depending on a specific logging library.

---

### `io` — Serialization Infrastructure (Stub)

**File:** `io/`

Currently a stub. Intended to centralize file format handlers (GeoJSON, GeoH5, OMF, etc.) as the framework matures. Individual geometry types (`ValuePoints`, `Surface`, etc.) currently implement their own `save()` methods; these should migrate here over time.

---

## What Falls Under loop_common

The following categories of code belong in `loop_common`:

| Category | Rationale |
|---|---|
| Base entity model (`LoopEntity`) | Used by objects in every layer |
| Spatial primitives (`BoundingBox`, `Surface`) | Geometry with no geological semantics |
| Raw observation types (`PointSet`, `Orientation`, `LineSet`) | Data before geological interpretation |
| Spatial discretization (`BaseSupport` and concrete grids/meshes) | Domain-agnostic numerical foundations |
| Cross-package interfaces (`BaseRepresentation`) | Polymorphism contracts between layers |
| Mathematical utilities (angle conversions, rotations, FD stencils) | Purely numerical, no geological knowledge |
| Logging infrastructure | Used by all packages uniformly |
| I/O format handling | Shared serialization concerns |

## What Does NOT Belong in loop_common

| Item | Where it belongs |
|---|---|
| Geological feature types (fault, fold, stratigraphy) | `loop_model` |
| Model builder logic, ObservationLinker | `loop_engine` |
| Interpolation objectives and solvers (FDI, P1, RBF) | `loop_interpolation` |
| Geological constraint types (`ValueConstraint`, `GradientConstraint`) | `loop_interpolation` |
| Feature relationship graphs (DAG) | `loop_model` |
| Visualization widgets or interactive UI | `visualization` |

---

## Dependency Rules

```
loop_common   →  numpy, pandas, pydantic  (external only)
loop_interpolation  →  loop_common
loop_engine         →  loop_common, loop_interpolation
loop_model          →  loop_common, loop_engine
visualization       →  loop_common, loop_model
```

Any proposed import from a lower package into `loop_common` is a design violation and should be resolved by moving the shared dependency further down or by introducing a new interface in `loop_common`.
