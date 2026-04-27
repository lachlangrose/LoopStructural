# Loop Interpolation Module Design Document

**Version:** 1.0  
**Date:** April 2026  
**Module:** `loop_interpolation`  
**Purpose:** Reference guide for implementing, extending, and using the constraint-solving interpolation system

---

## Table of Contents

1. [Introduction](#introduction)
2. [Design Philosophy](#design-philosophy)
3. [Module Architecture](#module-architecture)
4. [Constraint System](#constraint-system)
5. [Interpolator Types](#interpolator-types)
6. [Support Structures (Discretization)](#support-structures-discretization)
7. [The Solving Pipeline](#the-solving-pipeline)
8. [Validation and Diagnostics](#validation-and-diagnostics)
9. [Regularisation and Tuning](#regularisation-and-tuning)
10. [Builder Pattern](#builder-pattern)
11. [Extension Points](#extension-points)
12. [Best Practices](#best-practices)
13. [Examples and Use Cases](#examples-and-use-cases)

---

## Introduction

The interpolation module is responsible for the **inverse problem**: given observational constraints (values, gradients, tangents, etc.), fit a mathematical representation (interpolator) to the data and produce a scalar field that can be evaluated anywhere in the domain.

### Key Responsibilities

- **Constraint ingestion**: Accept geological observations and convert to mathematical constraints
- **Constraint validation**: Check constraints for consistency, validity, and geometric plausibility
- **System assembly**: Build sparse linear systems for least-squares solving
- **Solving**: Invoke solvers (conjugate gradient, LSMR, ADMM, etc.) to find optimal coefficients
- **Evaluation**: Compute field values and gradients at arbitrary positions
- **Post-processing**: Extract isosurfaces and evaluate surfaces

### Core Design Pattern

The module uses a **constraint-driven, support-parametric** design:

```
Observations (geological data)
    ↓
Constraints (mathematical objects: ValueConstraint, GradientConstraint, etc.)
    ↓
Constraint vectors (dense Nx3, Nx6 arrays)
    ↓
System matrix A (sparse, constraint equations)
    ↓
Solve: A·c = d (least-squares)
    ↓
Solution vector c (interpolator coefficients)
    ↓
GeologicalInterpolator (representation: can evaluate_value, evaluate_gradient, surfaces)
```

---

## Design Philosophy

### 1. Separation of Constraints from Solvers

**Principle**: Constraint definition should be independent of the solver algorithm.

- **Constraints** describe *what* is true (e.g., "field value = 0 at point X")
- **Interpolators** describe *how* to represent the field (e.g., piecewise linear on a mesh)
- **Solvers** describe *how* to fit (e.g., conjugate gradient, LSMR)

This separation allows:
- Adding new constraint types without changing interpolators
- Swapping solvers without touching constraint logic
- Testing constraints and solvers independently

### 2. Support Abstraction

**Principle**: Interpolators should not know or care about the specific mesh/grid structure.

- All spatial discretization goes through the `Support` interface
- Interpolators work via abstract methods: `evaluate_shape()`, `evaluate_shape_derivatives()`, `get_operators()`, etc.
- New mesh types (e.g., adaptive meshes, unstructured grids) can be added by implementing `Support`

### 3. Least-Squares as Lingua Franca

**Principle**: All discrete interpolators (P1, P2, FDI) solve via least-squares.

```
minimize: ||A·c - d||² + λ·||R·c||²
   c

where:
  A = constraint matrix (observations)
  d = right-hand side (constraint values)
  R = regularisation operator
  λ = regularisation weight
  c = solution (interpolator coefficients)
```

Benefits:
- Unified interface: all interpolators expose the same constraint methods
- Flexible regularisation: can modify R and λ without changing the core solver
- Composable: constraints and regularisation can be added incrementally

### 4. Validation-First Contract

**Principle**: Invalid constraints are rejected early with clear diagnostics.

- Input validation happens when constraints are added, not during solve
- Validation is modular: each constraint type has its own validator
- Validation produces diagnostics that can guide users (e.g., "100 points outside model domain")

### 5. Diagnostics as First-Class Objects

**Principle**: Solving is inherently uncertain; diagnostics should be explicit.

- Every solve produces a `ConstraintDiagnosticsReport`
- Reports track:
  - Constraint counts per family (role)
  - Effective weights (after defaults/adjustments)
  - Dropped rows and why
  - Region coverage (spatial distribution)
  - Points outside the model domain
- Diagnostics are stored on the interpolator for post-solve inspection

---

## Module Architecture

### File Organization

```
loop_interpolation/
├── __init__.py
│   ├── Exports public API
│   ├── InterpolatorType enum mapping
│   ├── interpolator_map (type → class)
│   └── support_interpolator_map (type + dims → support type)
│
├── constrains.py
│   ├── BaseConstraint (abstract)
│   ├── ValueConstraint
│   ├── GradientConstraint
│   ├── InequalityConstraint
│   ├── InequalityPair
│   └── InterfaceConstraint
│
├── _interpolatortype.py
│   └── InterpolatorType (enum)
│
├── _geological_interpolator.py
│   ├── GeologicalInterpolator (abstract base)
│   ├── Defines constraint API
│   ├── Defines evaluation API
│   └── Constraint validation flow
│
├── _discrete_interpolator.py
│   ├── DiscreteInterpolator (abstract, extends GeologicalInterpolator)
│   ├── Least-squares system assembly
│   ├── Constraint matrix building
│   ├── Region management
│   └── Solver integration
│
├── _finite_difference_interpolator.py
│   ├── FiniteDifferenceInterpolator (concrete, extends DiscreteInterpolator)
│   ├── Grid-based finite differences
│   ├── Custom derivative operators
│   └── Directional regularisation
│
├── _p1interpolator.py
│   ├── P1Interpolator / PiecewiseLinearInterpolator (concrete)
│   ├── Tetrahedral mesh, linear basis
│   └── Constant gradient regularisation
│
├── _p2interpolator.py
│   ├── P2Interpolator (concrete)
│   └── Quadratic basis on tetrahedral mesh
│
├── _discrete_fold_interpolator.py
│   ├── DiscreteFoldInterpolator (concrete)
│   └── Specialized for fold structures
│
├── _fd_fold_interpolator.py
│   ├── FDFoldInterpolator (concrete)
│   └── Finite difference fold solver
│
├── _constant_norm.py
│   ├── ConstantNormP1Interpolator
│   └── ConstantNormFDIInterpolator
│
├── _surfe_wrapper.py
│   ├── SurfeRBFInterpolator (optional, external dependency)
│   └── RBF solver (fallback if Surfe not installed)
│
├── _validation.py
│   ├── Shape and dtype checking
│   ├── NaN/Inf handling
│   ├── Constraint combination rules
│   ├── ValidationError exceptions
│   └── Field validators for each constraint type
│
├── _diagnostics.py
│   ├── ConstraintFamilyDiagnostics (per-role stats)
│   ├── RegionCoverageDiagnostics (spatial distribution)
│   ├── ConstraintDiagnosticsReport (full report)
│   └── Report.summary() for human-readable output
│
├── _regularisation.py
│   ├── DirectionalRegularisation (weight + direction)
│   ├── RegularisationConfig (isotropic + directional)
│   └── Coercion helpers (dict → config)
│
├── _interpolator_factory.py
│   ├── InterpolatorFactory (static methods)
│   ├── create_interpolator() → GeologicalInterpolator
│   └── Type/support mapping
│
├── _interpolator_builder.py
│   ├── InterpolatorBuilder (fluent interface)
│   ├── Convenience: setup → add constraints → solve
│   └── Solver selection and tuning
│
├── _operator.py
│   ├── Operator classes (finite difference stencils)
│   └── Mask-based kernel definitions
│
├── _builders.py
│   └── Feature-specific builders (Fold, etc.)
│
├── loopsolver/
│   ├── ADMM solver implementation
│   ├── Constant norm solver variants
│   └── Sparse system solving
│
└── tests/
    ├── test_interpolators.py
    ├── test_validation.py
    ├── test_diagnostics.py
    └── ...
```

### Class Hierarchy

```
BaseRepresentation (from loop_common.interfaces)
    ↓
GeologicalInterpolator (abstract)
    ├── Data management
    ├── Constraint interface
    ├── Evaluation interface
    ├── Validation gating
    └── Diagnostics attachment
    
    ↓
DiscreteInterpolator (abstract, extends GeologicalInterpolator)
    ├── Least-squares assembly
    ├── System matrix building
    ├── Solver integration
    ├── Region management
    └── Regularisation handling
    
    ├─→ FiniteDifferenceInterpolator (concrete)
    ├─→ P1Interpolator (concrete)
    ├─→ P2Interpolator (concrete)
    ├─→ DiscreteFoldInterpolator (concrete)
    ├─→ FDFoldInterpolator (concrete)
    ├─→ ConstantNormP1Interpolator (concrete)
    ├─→ ConstantNormFDIInterpolator (concrete)
    │
    └─→ GeologicalInterpolator (other implementations)
        └─→ SurfeRBFInterpolator (external solver)
```

---

## Constraint System

### Constraint Types

The module defines five constraint types (in `constrains.py`), each representing a different kind of geological observation:

#### 1. **ValueConstraint**

```python
@dataclass(frozen=True)
class ValueConstraint(BaseConstraint):
    points: np.ndarray        # Shape (N, 3) — XYZ coordinates
    values: np.ndarray        # Shape (N,) — scalar values at points
    weights: float | np.ndarray  # (N,) or scalar — per-point or global weight
```

**Semantics**: Field value equals a specific number at specific points.

**Interpretation**: 
- Interface constraints (field = 0 at basal contact)
- Value points (field = 1 inside unit, field = 0 outside)

**Usage**:
```python
interpolator.add_value_constraint(xyz, values=0.0, weights=1.0)
```

#### 2. **GradientConstraint**

```python
@dataclass(frozen=True)
class GradientConstraint(BaseConstraint):
    points: np.ndarray        # Shape (N, 3) — XYZ coordinates
    vectors: np.ndarray       # Shape (N, 3) — gradient direction
    weights: float | np.ndarray  # (N,) or scalar
    is_normal: bool           # Gradient is normal to a surface
```

**Semantics**: Field gradient (directional derivative) equals a direction at specific points.

**Interpretation**:
- **Bedding normal** (is_normal=True): Gradient points perpendicular to layering
- **Strike direction** (is_normal=False): Gradient points in a specific direction
- **Fold axis**: Gradient is folded linearly

**Usage**:
```python
interpolator.add_gradient_constraint(xyz, gradient_vectors, weights=1.0)
interpolator.add_normal_constraint(xyz, normals, weights=100.0)  # Higher weight for normals
```

#### 3. **TangentConstraint** (implicit)

Handled separately; constrains the field derivative perpendicular to a direction.

**Semantics**: Field gradient is *perpendicular* to a tangent vector.

**Interpretation**:
- Lineament constraints (field gradient perpendicular to fault trace)
- Fold limb constraints

#### 4. **InequalityConstraint**

```python
@dataclass(frozen=True)
class InequalityConstraint(BaseConstraint):
    points: np.ndarray        # Shape (N, 3)
    bounds: np.ndarray        # Shape (N, 2) — [lower, upper] per point
    weights: float | np.ndarray  # (N,) or scalar
```

**Semantics**: Field value at point is constrained to a range [lower, upper].

**Interpretation**:
- "Inside" constraints (field > 0 inside unit)
- "Outside" constraints (field < 0 outside unit)
- Inequality pairs (field(A) < field(B))

**Usage**:
```python
interpolator.add_value_inequality_constraint(xyz, lower, upper, weights=1.0)
```

#### 5. **InterfaceConstraint**

```python
@dataclass(frozen=True)
class InterfaceConstraint(BaseConstraint):
    points: np.ndarray        # Shape (N, 3)
    value: float              # Isovalue (default 0.0)
    weights: float | np.ndarray  # (N,) or scalar
```

**Semantics**: Field value equals a constant isovalue at specific points (canonical interface).

**Interpretation**:
- Basal contact surface (points on the bottom boundary of a unit)
- Top contact surface
- Fault surface

**Usage**:
```python
interpolator.add_interface_constraint(xyz, value=0.0, weights=1.0)
```

### Constraint Addition Flow

```python
# 1. User calls constraint method on interpolator
interpolator.add_value_constraint(
    xyz=np.array([[0, 0, 100], [10, 10, 90]]),
    value=0.0,
    weights=1.0
)

# 2. Validation gate (in base class)
#    ├─ Shape checks: xyz must be (N, 3)
#    ├─ Dtype checks: xyz must be numeric (coerce to float64)
#    ├─ NaN handling:
#    │  ├─ Data columns with NaN → drop row + warning
#    │  └─ Weight column with NaN → replace with 1.0 + warning
#    └─ Constraint combination checks: no conflicting roles

# 3. Constraint appended to internal storage
#    ├─ self.data["interface"] extended with new points
#    ├─ self.n_i (interface count) incremented
#    └─ self.up_to_date = False (solver invalidated)

# 4. Solver setup (called by interpolator.setup_interpolator())
#    ├─ Extract constraint arrays from data
#    ├─ Assemble constraint matrix rows
#    ├─ Build right-hand-side vector
#    └─ Prepare solver (factorization, scaling, etc.)

# 5. Solve
#    └─ Solve least-squares system → coefficients c
```

### NaN/Inf Handling Contract

The validation module implements a clear contract for missing/invalid data:

```python
# File: _validation.py

# RULE 1: Weight column NaN → silently replace with 1.0
# Rationale: Allows callers to use np.nan as "use default" sentinel
#           when assembling constraints from DataFrames

# RULE 2: Position/data column NaN or Inf → drop row with warning
# Rationale: Points outside model or with missing values are not usable;
#           drop silently to allow batch processing of uncertain data
```

**Example**:
```python
import numpy as np

# User provides constraint with some NaN values
xyz = np.array([
    [0, 0, 100],
    [10, 10, np.nan],      # Invalid: NaN in position
    [20, 20, 120],
], dtype=float)
weights = np.array([1.0, np.nan, 1.0])  # Invalid: NaN weight

# Validator drops row 1, replaces NaN weight with 1.0
# Result: xyz = [[0, 0, 100], [20, 20, 120]]
#         weights = [1.0, 1.0]
```

---

## Interpolator Types

### Overview

The module provides **11 interpolator types** (extensible), grouped by strategy:

| Type | Class | Basis | Support | Cost | Accuracy | Use Case |
|------|-------|-------|---------|------|----------|----------|
| **FDI** | `FiniteDifferenceInterpolator` | Finite differences | StructuredGrid | Low | Medium | Large 3D models, fast feedback |
| **FDI-CN** | `ConstantNormFDIInterpolator` | FD + const norm | StructuredGrid | Medium | Medium+ | FDI with magnitude constraints |
| **P1** | `P1Interpolator` | Linear (hat) | TetMesh | Medium | Medium | General unstructured, flexible |
| **P1-CN** | `ConstantNormP1Interpolator` | P1 + const norm | TetMesh | Medium | Medium+ | P1 with magnitude constraints |
| **P2** | `P2Interpolator` | Quadratic | TetMesh | High | High | Smooth fields, small models |
| **Fold-D** | `DiscreteFoldInterpolator` | Linear | TetMesh | Medium | Medium | Fold-like structures |
| **Fold-FD** | `FDFoldInterpolator` | FD | StructuredGrid | Low | Medium | Large fold models |
| **Surfe RBF** | `SurfeRBFInterpolator` | RBF (external) | Data-supported | High | High | Small, smooth fields (optional) |
| **Base** | `GeologicalInterpolator` | Abstract | N/A | N/A | N/A | Interface definition |
| **Base-Discrete** | `DiscreteInterpolator` | Abstract | Mesh/Grid | N/A | N/A | Least-squares base |
| **Base-DataSup** | `GeologicalInterpolator` | Abstract | None | N/A | N/A | Data-supported solvers |

### Detailed Descriptions

#### FiniteDifferenceInterpolator (FDI)

**Type**: `InterpolatorType.FINITE_DIFFERENCE`  
**Basis**: Finite difference stencils on a regular grid  
**Support**: `StructuredGrid`, `StructuredGrid2D`

**Characteristics**:
- Grid-aligned (axis-parallel)
- Efficient: sparse matrix, small system size
- Scalable: handles millions of grid points
- Discontinuous gradients at cell boundaries

**Key Methods**:
```python
fdi = FiniteDifferenceInterpolator(grid)

# Add constraints
fdi.add_interface_constraint(xyz, value=0.0, weights=1.0)
fdi.add_gradient_constraint(xyz, gradients, weights=1.0)
fdi.add_normal_constraint(xyz, normals, weights=100.0)  # Default

# Setup and solve
fdi.setup_interpolator(
    regularisation=0.1,
    directional_regularisation=[...],
    dxy=1.0, dxx=1.0, ...  # Derivative weights
)
fdi.fit()

# Evaluate
field = fdi.evaluate_value(positions)
grad = fdi.evaluate_gradient(positions)
```

**Regularisation Options**:
```python
# Isotropic smoothing (Laplacian)
fdi.setup_interpolator(regularisation=0.1)

# Directional smoothing (anisotropic)
fdi.setup_interpolator(
    directional_regularisation=[
        {"weight": 0.1, "direction": [1, 0, 0]},  # Smooth in X
        {"weight": 0.05, "direction": [0, 1, 0]},  # Less smooth in Y
    ]
)

# Custom derivative weights
fdi.setup_interpolator(
    dxx=1.0, dyy=1.0, dzz=1.0,  # Second derivatives
    dxy=0.5, dxz=0.5, dyz=0.5,  # Mixed derivatives
    cpw=1.0, gpw=1.0, npw=100.0  # Constraint weights
)
```

**Typical Use**:
```python
# Large continental-scale model
bbox = BoundingBox(origin=[0, 0, 0], maximum=[1000, 800, 500], nsteps=[50, 40, 25])
fdi = FiniteDifferenceInterpolator(bbox.as_structured_grid())
fdi.add_interface_constraint(basal_xyz, 0.0)
fdi.add_normal_constraint(orientation_xyz, orientation_vectors, weights=100)
fdi.setup_interpolator(regularisation=0.05)
fdi.fit()
values = fdi.evaluate_value(sample_points)
```

#### P1Interpolator (Piecewise Linear)

**Type**: `InterpolatorType.PIECEWISE_LINEAR`  
**Basis**: Piecewise linear hat functions on tetrahedral mesh  
**Support**: `TetMesh`, `P1Unstructured2d` (2D)

**Characteristics**:
- Mesh-based (unstructured)
- Continuous field, discontinuous gradients
- Flexible geometry (can handle complex domain shapes)
- Moderate computational cost

**Key Methods**:
```python
p1 = P1Interpolator(mesh)

# Add constraints
p1.add_interface_constraint(xyz, value=0.0, weights=1.0)
p1.add_normal_constraint(xyz, normals, weights=1.0)

# Setup and solve
p1.setup_interpolator(
    regularisation=0.01,  # Constant gradient penalty
    cgw=0.1,  # Constant gradient weight
    cpw=1.0,  # Point constraint weight
    npw=1.0,  # Normal weight
)
p1.fit()

# Evaluate
field = p1.evaluate_value(positions)
grad = p1.evaluate_gradient(positions)
```

**Key Differences from FDI**:
- No `dxx`, `dyy`, etc. weights (uses constant gradient regularisation)
- More flexible geometry (mesh adapts to domain boundary)
- Higher memory per element (tetrahedra > grid cells)

#### P2Interpolator (Piecewise Quadratic)

**Type**: `InterpolatorType.PIECEWISE_QUADRATIC`  
**Basis**: Piecewise quadratic basis on tetrahedral mesh  
**Support**: `P2UnstructuredTetMesh`, `P2Unstructured2d`

**Characteristics**:
- Higher-order basis (6 nodes per tetrahedron vs 4)
- Smooth gradients (continuous first derivative)
- More expensive to solve (larger system)
- Best accuracy for smooth fields

**Use Case**: Small to medium models where smoothness is important.

#### Fold Interpolators

**Types**: `DiscreteFoldInterpolator`, `FDFoldInterpolator`

**Purpose**: Specialized for fold structures where the field varies along and perpendicular to a fold axis.

**Characteristics**:
- Incorporates fold geometry constraints
- Penalizes deviations from fold-like shapes
- Useful when folds are dominant structural feature

**Example**:
```python
fold_interp = DiscreteFoldInterpolator(mesh)
fold_interp.add_fold_axis_constraint(...)  # Define fold axis
fold_interp.add_interface_constraint(xyz, 0.0)
fold_interp.setup_interpolator()
fold_interp.fit()
```

#### Constant Norm Interpolators

**Types**: `ConstantNormP1Interpolator`, `ConstantNormFDIInterpolator`

**Purpose**: Enforce that the gradient magnitude is constant everywhere (or varies smoothly).

**Use Case**: 
- Fault networks (faults should have sharp, consistent displacement)
- Where orientation constraints have known magnitude (e.g., cleavage)

**Example**:
```python
cn_p1 = ConstantNormP1Interpolator(mesh)
cn_p1.add_gradient_constraint(xyz, gradients, weights=1.0)
cn_p1.add_interface_constraint(xyz, 0.0, weights=1.0)
cn_p1.setup_interpolator()
cn_p1.fit()  # Gradient magnitude is enforced to be constant
```

#### SurfeRBFInterpolator (Optional)

**Type**: `InterpolatorType.SURFE`  
**Basis**: Radial basis functions (external Surfe library)  
**Support**: Data-supported (no mesh needed)

**Characteristics**:
- No discretization mesh
- Smooth everywhere
- Works directly from point constraints
- Requires external Surfe package

**Installation**:
```bash
pip install surfe
# or
conda install -c loop3d surfe
```

**Use Case**: Small models where smoothness everywhere is essential, and computation cost is acceptable.

### Interpolator Selection Guide

```
Choose interpolator based on:

1. Domain size?
   ├─ Large (>1M points) → FDI (fast, scalable)
   └─ Small (<100k points) → P2 or Surfe (smooth, accurate)

2. Domain geometry?
   ├─ Regular grid → FDI or FDI-CN
   ├─ Irregular / complex boundary → P1 or P2
   └─ Data-scattered only → Surfe RBF

3. Desired smoothness?
   ├─ Discontinuous gradients (fast) → FDI, P1
   └─ Smooth gradients (slow) → P2, Surfe

4. Gradient magnitude?
   ├─ Varies with direction → P1, P2
   └─ Constant (fault-like) → P1-CN, FDI-CN

5. Dominant structure?
   ├─ Layers, contacts → FDI, P1, P2
   ├─ Folds → Fold-D, Fold-FD
   └─ Smooth RBF-like → Surfe
```

---

## Support Structures (Discretization)

### What is a Support?

A **support** is the discrete spatial basis on which the interpolator is defined. All interpolators work through the Support interface; they don't know or care about underlying mesh topology.

### Support Hierarchy

```
BaseSupport (abstract)
├── Structured (grid-based)
│   ├── StructuredGrid (3D rectilinear)
│   └── StructuredGrid2D (2D rectilinear)
│
├── Unstructured (mesh-based)
│   ├── TetMesh (3D tetrahedral)
│   ├── UnStructuredTetMesh (3D tetrahedral, alt)
│   ├── P1Unstructured2d (2D linear)
│   ├── P2Unstructured2d (2D quadratic)
│   └── P2UnstructuredTetMesh (3D quadratic)
│
└── DataSupported (point-cloud-based)
    └── (Surfe uses this; no mesh structure)
```

### Support Interface (Key Methods)

All support types implement:

```python
class Support(ABC):
    # Mesh properties
    @property
    def n_nodes(self) -> int: ...          # Number of vertices
    
    @property
    def n_elements(self) -> int: ...       # Number of elements (cells/tetrahedra)
    
    @property
    def dimension(self) -> int: ...        # 2 or 3
    
    @property
    def nodes(self) -> np.ndarray: ...     # Shape (n_nodes, dimension)
    
    @property
    def elements(self) -> np.ndarray: ...  # Shape (n_elements, nodes_per_element)
    
    # Evaluation at arbitrary points
    def evaluate_shape(self, positions):
        """Evaluate shape function values at positions.
        
        Returns
        -------
        shape_function_values, element_ids, inside_mask
        """
        ...
    
    def evaluate_shape_derivatives(self, positions):
        """Evaluate shape function gradients (spatial derivatives).
        
        Returns
        -------
        gradient_values, element_ids, inside_mask
        """
        ...
    
    # Operators for finite difference / regularisation
    def get_operators(self, weights: dict) -> dict:
        """Return sparse matrix operators for regularisation.
        
        Returns
        -------
        {"dxx": (matrix, mask), "dyy": ..., ...}
        """
        ...
    
    # Isosurface extraction
    def extract_isosurface(self, field_values, value=0.0):
        """Extract geometry of field == value.
        
        Returns
        -------
        vertices, triangles (or None if no surface)
        """
        ...
```

### Support Creation

**Via BoundingBox**:
```python
from loop_common.geometry import BoundingBox
from loop_common.supports import SupportFactory

bbox = BoundingBox(origin=[0, 0, 0], maximum=[100, 80, 60], nsteps=[10, 8, 6])

# Automatically creates StructuredGrid
grid = SupportFactory.create_support_from_bbox(
    SupportType.StructuredGrid,
    bounding_box=bbox,
    buffer=0.1  # 10% padding
)

# Or manually
from loop_common.supports import StructuredGrid
grid = StructuredGrid(origin=bbox.origin, maximum=bbox.maximum, nsteps=bbox.nsteps)
```

**Via Factory**:
```python
from loop_interpolation import InterpolatorFactory, InterpolatorType
from loop_common.geometry import BoundingBox

bbox = BoundingBox(...)

# Factory automatically creates appropriate support
interp = InterpolatorFactory.create_interpolator(
    interpolatortype=InterpolatorType.PIECEWISE_LINEAR,
    boundingbox=bbox,
    nelements=1000
)
# Internally: creates TetMesh automatically
```

---

## The Solving Pipeline

### End-to-End Solve Sequence

```
1. Create Interpolator
   ├─ Specify support (mesh/grid)
   ├─ Initialize constraint arrays
   └─ Set default weights

2. Add Constraints (one or more calls)
   ├─ add_interface_constraint(...)
   ├─ add_gradient_constraint(...)
   ├─ add_normal_constraint(...)
   ├─ add_value_constraint(...)
   ├─ ... (constraint arrays grow)
   └─ up_to_date = False (solver invalidated)

3. Setup Interpolator
   └─ setup_interpolator(regularisation=..., weights=...)
      ├─ Validate constraint arrays (validation.py)
      ├─ Assemble constraint matrix A (sparse)
      ├─ Build right-hand side d
      ├─ Add regularisation terms (R matrix)
      └─ Prepare solver (scaling, factorization)

4. Fit (Solve)
   └─ fit()
      ├─ Solve least-squares: A·c ≈ d (+ λ·R·c penalty)
      ├─ Invoke solver (CG, LSMR, ADMM, etc.)
      ├─ Check convergence
      ├─ Generate diagnostics report
      └─ Store solution c in interpolator

5. Evaluate
   ├─ evaluate_value(positions) → shape (N,)
   ├─ evaluate_gradient(positions) → shape (N, 3)
   └─ surfaces(value=0.0) → isosurface geometry
```

### Detailed: System Assembly

The core of solving is assembling a sparse linear system from constraints and regularisation.

#### Constraint Matrix Assembly

For each constraint type, rows are added to the matrix A:

```python
# Pseudo-code for P1 interpolator assembly

# Interface constraint: field(x) = 0 at points
for point_xyz in interface_points:
    # Find containing tetrahedron
    element, shape_vals = mesh.evaluate_shape(point_xyz)
    # Add row to A: row[element_nodes] = shape_vals
    # Add entry to d: d[row_idx] = 0.0
    A[row_idx, element_nodes] = shape_vals
    d[row_idx] = 0.0

# Gradient constraint: grad(field) = direction at points
for point_xyz, direction in gradient_points:
    # Find containing tetrahedron
    element, grad_shape_vals = mesh.evaluate_shape_derivatives(point_xyz)
    # Add 3 rows (one per X, Y, Z component)
    for axis in [0, 1, 2]:
        A[row_idx, element_nodes] = grad_shape_vals[:, axis]
        d[row_idx] = direction[axis]
        row_idx += 1
```

#### Regularisation Terms

Regularisation penalizes non-smooth solutions:

```
Total cost: ||A·c - d||² + λ·||R·c||²

where R is a regularisation matrix (e.g., Laplacian operator):

R = [   0   1  -2   1        ]  (second derivative stencil)
    [   1  -4   6  -4   1   ]  (for each node)
    [ ...                    ]

High λ → smooth solution (high likelihood of oscillations)
Low λ → fits data exactly (may have noise amplification)
```

**Regularisation Types**:

1. **Isotropic** (smoothing equally in all directions):
   ```python
   interp.setup_interpolator(regularisation=0.1)
   ```

2. **Directional** (prioritize smoothing along certain directions):
   ```python
   interp.setup_interpolator(
       directional_regularisation=[
           {"weight": 0.1, "direction": [0, 0, 1]},  # Smooth vertically
           {"weight": 0.05, "direction": [1, 1, 0]},  # Less smooth laterally
       ]
   )
   ```

### Solving Strategies

#### 1. Conjugate Gradient (CG)

**Default solver for most interpolators**

```python
interp.solver = "cg"
interp.fit()
```

- Pros: Fast for large systems, memory-efficient
- Cons: Requires well-conditioned matrix
- Best for: FDI (grid-based), large problems

#### 2. LSMR

**Least-squares minimum-residual solver**

```python
interp.solver = "lsmr"
interp.fit()
```

- Pros: More robust for ill-conditioned systems
- Cons: Slightly slower than CG
- Best for: Unstructured meshes (P1, P2)

#### 3. ADMM

**Alternating Direction Method of Multipliers**

```python
interp.solver = "admm"
interp.fit(solver_kwargs={"max_iter": 100, "tol": 1e-5})
```

- Pros: Can handle inequality constraints and non-convex penalties
- Cons: Slower, requires tuning
- Best for: Constant norm interpolators, inequality constraints

### Solving with the Builder

The `InterpolatorBuilder` provides a fluent interface:

```python
from loop_interpolation import InterpolatorBuilder
from loop_common.geometry import BoundingBox

bbox = BoundingBox(origin=[0, 0, 0], maximum=[100, 100, 100], nsteps=[10, 10, 10])

builder = InterpolatorBuilder(
    interpolatortype="P1",
    bounding_box=bbox,
    nelements=1000
)

builder.use_solver("lsmr", tol=1e-4)
builder.solve()  # Solves with default constraints

result = builder.interpolator
values = result.evaluate_value(positions)
```

---

## Validation and Diagnostics

### Validation Pipeline

When constraints are added, they pass through validation:

```
User Input (xyz, values, weights, ...)
  ↓
Shape Check: ensure xyz is (N, 3), values is (N,), weights is (N,) or scalar
  ↓
Dtype Check: coerce to float64
  ↓
NaN Handling:
  ├─ Weight NaN → replace with 1.0 + warning
  └─ Data NaN → drop row + warning
  ↓
Range Check: values in expected range, etc.
  ↓
Combination Check: constraints don't conflict
  ↓
Append to internal storage (self.data)
```

### Validation Errors

If validation fails, a `ValidationError` (or subclass) is raised:

```python
class ValidationError(ValueError):
    """Base exception for constraint validation errors."""
    pass

class ShapeError(ValidationError):
    """Exception for shape mismatches."""
    pass

class DtypeError(ValidationError):
    """Exception for data type mismatches."""
    pass
```

**Example**:
```python
try:
    interp.add_interface_constraint(
        xyz=np.array([[0, 0]]),  # Wrong shape: (1, 2) not (N, 3)
        value=0.0
    )
except ShapeError as e:
    print(f"Validation failed: {e}")
    # "Points must have shape (N, 3); got (1, 2)"
```

### Diagnostics Report

After solve, a detailed diagnostics report is attached to the interpolator:

```python
interp.fit()

report = interp.latest_diagnostics_report

print(report.summary())
# Output:
# Constraint diagnostics for PIECEWISE_LINEAR
# Total rows: 250
# Active families:
#   - interface: rows=50, dropped=2, mean_weight=1.0
#   - gradient: rows=100, dropped=0, mean_weight=100.0
#   - normal: rows=100, dropped=0, mean_weight=100.0
# Region coverage: 500/1000 (50%)
# Outside-model points:
#   - interface: 2
```

### Report Structure

```python
@dataclass(frozen=True)
class ConstraintFamilyDiagnostics:
    name: str                      # "interface", "gradient", "normal", etc.
    active: bool                   # Was this family used in solve?
    row_count: int                 # Rows in final system
    dropped_rows: Optional[int]    # NaN/Inf rows removed
    effective_weight_mean: float   # Average weight after all adjustments
    effective_weight_min: float    # Min weight
    effective_weight_max: float    # Max weight
    source_point_count: int        # Original points (before dropping)
    outside_model_point_count: int # Points outside domain

@dataclass(frozen=True)
class RegionCoverageDiagnostics:
    total_support_nodes: int       # Total nodes in mesh/grid
    active_region_nodes: int       # Nodes with at least one constraint nearby
    inactive_region_nodes: int     # Nodes far from any constraint
    active_fraction: float         # active / total

@dataclass(frozen=True)
class ConstraintDiagnosticsReport:
    interpolator_type: str         # "FINITE_DIFFERENCE", "PIECEWISE_LINEAR", etc.
    families: Dict[str, ConstraintFamilyDiagnostics]
    region_coverage: Optional[RegionCoverageDiagnostics]
    outside_model_points: Dict[str, int]
    
    # Convenience properties
    @property
    def total_rows(self) -> int: ...
    
    @property
    def active_families(self) -> Dict[str, ...]: ...
    
    def to_dict(self) -> dict: ...
    def summary(self) -> str: ...
```

---

## Regularisation and Tuning

### Regularisation Concepts

**The Problem**: Constraints alone often don't uniquely determine a solution. There can be many fields that fit the data equally well.

**The Solution**: Add a regularisation term that penalizes non-smooth or unlikely solutions.

```
minimize: ||A·c - d||² + λ·Ω(c)

where:
  λ = regularisation weight (strength of penalty)
  Ω(c) = penalty function (e.g., ||R·c||² for smoothing)
```

### Regularisation Types

#### 1. Isotropic (Uniform Smoothing)

```python
interp.setup_interpolator(regularisation=0.1)
```

Penalizes second-order derivatives equally in all directions. Produces a Laplacian-smoothed field.

**Interpretation**: 
- λ = 0.0 → no smoothing, fits data exactly
- λ = 0.01 → light smoothing
- λ = 0.1 → moderate smoothing
- λ = 1.0 → strong smoothing, field becomes very smooth

**Tuning Guideline**: Increase λ if solution oscillates; decrease if solution is over-smoothed.

#### 2. Directional Regularisation

```python
interp.setup_interpolator(
    directional_regularisation=[
        {
            "weight": 0.1,
            "direction": [0, 0, 1],  # Vertical
            "name": "vertical smoothness"
        },
        {
            "weight": 0.02,
            "direction": [1, 0, 0],  # Horizontal
            "name": "horizontal smoothness"
        },
    ]
)
```

Applies different smoothing strengths along different directions.

**Use Case**: Geological structures have preferred directions:
- Layered deposits → smooth vertically, vary horizontally
- Fold axes → smooth perpendicular to axis
- Fault zones → smooth perpendicular to fault plane

**Syntax**:
```python
# Direction can be:
# 1. Explicit vector [x, y, z]
{"weight": 0.1, "direction": [0, 0, 1]}

# 2. Callable (direction varies with position)
def vertical_direction(positions):
    """Return unit vector [x, y, z] for each position."""
    return np.tile([0, 0, 1], (positions.shape[0], 1))

{"weight": 0.1, "direction": vertical_direction}

# 3. Multiple terms (build up penalty)
directional_regularisation=[
    {"weight": 0.1, "direction": [0, 0, 1]},
    {"weight": 0.05, "direction": [1, 1, 0]},
]
```

### Constraint Weights

**In addition to regularisation**, individual constraints can have weights:

```python
# High weight: "I really trust this data"
interp.add_interface_constraint(xyz, value=0.0, weights=10.0)

# Low weight: "This data is uncertain"
interp.add_gradient_constraint(xyz, gradients, weights=0.1)

# Per-point weights
weights = np.array([1.0, 5.0, 0.5])  # Different trust for each point
interp.add_normal_constraint(xyz, normals, weights=weights)
```

**Default Weights** (set in interpolator):
```python
# Finite Difference
self.interpolation_weights = {
    "cpw": 1.0,   # Contact point weight
    "gpw": 1.0,   # Gradient point weight
    "npw": 100.0, # Normal point weight (10x higher by default)
    "tpw": 1.0,   # Tangent point weight
    "ipw": 1.0,   # Interface point weight
}

# P1 Interpolator
self.interpolation_weights = {
    "cgw": 0.1,   # Constant gradient weight
    "cpw": 1.0,   # Contact point weight
    "npw": 1.0,   # Normal point weight
    "gpw": 1.0,   # Gradient point weight
    "tpw": 1.0,   # Tangent point weight
    "ipw": 1.0,   # Interface point weight
}
```

### Weight Scaling

**The Problem**: Different constraint families (contacts, normals, gradients) can have very different magnitudes.

**The Solution**: Use weight scaling to balance families.

```python
# Normalize constraint families by RMS magnitude
interp.apply_scaling_matrix = True

# After setup, the matrix A is scaled so each constraint family
# contributes roughly equally to the least-squares cost
```

---

## Builder Pattern

The `InterpolatorBuilder` class provides a convenient fluent interface for creating and solving interpolators:

### Basic Usage

```python
from loop_interpolation import InterpolatorBuilder
from loop_common.geometry import BoundingBox

# 1. Create builder
builder = InterpolatorBuilder(
    interpolatortype="FDI",           # or "P1", "P2", etc.
    bounding_box=BoundingBox(...),
    nelements=1000,
    buffer=0.1  # 10% padding
)

# 2. Configure solver
builder.use_solver("cg", tol=1e-4)

# 3. Solve
builder.solve()

# 4. Access result
interpolator = builder.interpolator
values = interpolator.evaluate_value(positions)
```

### Advanced Usage

```python
builder = InterpolatorBuilder(
    interpolatortype="P1",
    bounding_box=bbox,
    nelements=1000,
    regularisation=0.01,
    directional_regularisation=[
        {"weight": 0.05, "direction": [0, 0, 1]},
    ]
)

# Solve with custom parameters
builder.solve(
    solver="lsmr",
    tol=1e-5,
    max_iter=1000
)

# Inspect results
report = builder.interpolator.latest_diagnostics_report
print(report.summary())
```

### Builder Methods

```python
class InterpolatorBuilder:
    def __init__(self, interpolatortype, bounding_box, nelements=None, 
                 buffer=None, **kwargs): ...
    
    def use_solver(self, solver: str, **solver_kwargs) -> InterpolatorBuilder:
        """Set solver type and parameters."""
        ...
    
    def solve(self, solver=None, tol=None, **solver_kwargs) -> InterpolatorBuilder:
        """Solve the interpolator system."""
        ...
    
    @property
    def interpolator(self) -> GeologicalInterpolator:
        """Access the solved interpolator."""
        ...
```

---

## Extension Points

### 1. Custom Interpolator Class

**File**: `packages/loop_interpolation/src/loop_interpolation/_myinterpolator.py`

```python
from loop_interpolation import GeologicalInterpolator, InterpolatorType
import numpy as np

class MyCustomInterpolator(GeologicalInterpolator):
    """My custom interpolation method."""
    
    def __init__(self, support, data=None, **kwargs):
        super().__init__(data=data)
        self.support = support
        self.type = InterpolatorType.MY_CUSTOM_TYPE
        self.my_solver = MyInternalSolver()
    
    def set_nelements(self, nelements: int) -> int:
        """Set number of elements in the support."""
        return self.support.set_nelements(nelements)
    
    @property
    def n_elements(self) -> int:
        """Return number of elements."""
        return self.support.n_elements
    
    def fit(self):
        """Solve the inverse problem."""
        # Extract constraints
        points = self.data.get("interface", np.empty((0, 3)))
        gradients = self.data.get("gradient", np.empty((0, 3)))
        
        # Solve using custom logic
        self.my_solver.build(points, gradients)
        self.up_to_date = True
    
    def evaluate_value(self, position: np.ndarray) -> np.ndarray:
        """Evaluate scalar field at positions."""
        return self.my_solver.evaluate(position)
    
    def evaluate_gradient(self, position: np.ndarray) -> np.ndarray:
        """Evaluate gradient at positions."""
        return self.my_solver.evaluate_grad(position)
    
    def surfaces(self, value: float = 0.0) -> dict | None:
        """Extract isosurface."""
        # Custom isosurface logic
        return self.my_solver.extract_surface(value)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {"type": "MyCustomType", ...}
    
    @classmethod
    def from_dict(cls, data: dict):
        """Deserialize from dictionary."""
        return cls(...)
```

**Register in `__init__.py`**:
```python
from ._myinterpolator import MyCustomInterpolator

interpolator_map[InterpolatorType.MY_CUSTOM_TYPE] = MyCustomInterpolator

# Declare supported supports for factory
support_interpolator_map[InterpolatorType.MY_CUSTOM_TYPE] = {
    3: SupportType.TetMesh,
    2: SupportType.P1Unstructured2d,
}
```

### 2. Custom Validation

**File**: `packages/loop_interpolation/src/loop_interpolation/_validation.py`

Add custom validation for domain-specific constraints:

```python
def validate_fold_constraint(grad, tangent):
    """Ensure fold constraints are orthogonal."""
    if len(grad) == 0 or len(tangent) == 0:
        return
    
    # Fold axis must be perpendicular to layering
    dot = np.sum(grad * tangent, axis=1)
    if not np.allclose(dot, 0.0, atol=1e-6):
        raise ValidationError(f"Fold gradient and tangent must be orthogonal")
```

### 3. Custom Solver

**File**: `packages/loop_interpolation/src/loop_interpolation/loopsolver/`

Implement a custom sparse linear solver:

```python
class MyCustomSolver:
    def solve(self, A, d, x0=None, tol=1e-5, max_iter=1000):
        """Solve sparse system A·x = d."""
        # Custom algorithm
        return solution
```

Register in the interpolator:
```python
interp.solver = "my_custom_solver"
interp.my_custom_solver = MyCustomSolver()
interp.fit()
```

### 4. Custom Regularisation

The `RegularisationConfig` system is extensible. Add domain-specific regularisation:

```python
# In your application code
from loop_interpolation._regularisation import DirectionalRegularisation

# Create custom regularisation term
fold_reg = DirectionalRegularisation(
    weight=0.05,
    direction=lambda xyz: compute_fold_axis(xyz),
    name="fold_axis_regularisation"
)

interp.setup_interpolator(
    directional_regularisation=[fold_reg]
)
```

---

## Best Practices

### 1. Constraint Quality Before Quantity

```python
# DON'T: Add all data without checking
for obs in observations:
    interp.add_interface_constraint(obs.xyz, 0.0)

# DO: Validate and filter first
valid_obs = [obs for obs in observations if is_valid(obs)]
for obs in valid_obs:
    interp.add_interface_constraint(obs.xyz, 0.0, weights=obs.confidence)
```

### 2. Use Weights to Express Uncertainty

```python
# Express confidence as weights
high_confidence = 10.0
medium_confidence = 1.0
low_confidence = 0.1

interp.add_interface_constraint(basal_xyz, 0.0, weights=high_confidence)
interp.add_gradient_constraint(uncertain_xyz, grads, weights=low_confidence)
```

### 3. Check Diagnostics After Solve

```python
interp.fit()

report = interp.latest_diagnostics_report
print(report.summary())

# Check for warning signs:
if report.outside_model_points.get("interface", 0) > 0:
    print("WARNING: Some interface points are outside model bounds")

if report.region_coverage.active_fraction < 0.5:
    print("WARNING: Constraints only cover 50% of domain; expect high uncertainty")
```

### 4. Regularisation Tuning Workflow

```python
import matplotlib.pyplot as plt

# Solve with different regularisation strengths
regularisation_values = [0.001, 0.01, 0.1, 1.0]
solutions = []

for reg in regularisation_values:
    interp = FiniteDifferenceInterpolator(grid)
    interp.add_interface_constraint(...)
    interp.setup_interpolator(regularisation=reg)
    interp.fit()
    solutions.append(interp)

# Evaluate at test points
test_points = [[50, 50, 50]]
fig, axes = plt.subplots(1, 4, figsize=(12, 3))

for ax, sol, reg in zip(axes, solutions, regularisation_values):
    field = sol.evaluate_value(test_points)
    ax.set_title(f"λ = {reg}")
    # Plot field or other diagnostic
```

### 5. Memory Management for Large Models

```python
# FDI can handle large models efficiently
large_grid = StructuredGrid(origin=[0, 0, 0], maximum=[1000, 1000, 500], nsteps=[100, 100, 50])
fdi = FiniteDifferenceInterpolator(large_grid)

# Add constraints incrementally
for batch in constraint_batches:
    fdi.add_interface_constraint(batch.xyz, 0.0)

# Solve
fdi.setup_interpolator(regularisation=0.01)
fdi.fit()

# Evaluate in chunks (to avoid huge in-memory arrays)
for chunk in position_chunks:
    values = fdi.evaluate_value(chunk)
    process_results(values)
```

### 6. Handling Missing/Uncertain Data

```python
# Use NaN as sentinel for missing weight
constraints = np.array([
    [0, 0, 100, 0.5],     # Full precision
    [10, 10, np.nan, 1.0],  # Missing Z → validator will drop
    [20, 20, 110, np.nan],  # Missing weight → replaced with 1.0
], dtype=float)

# Validator automatically handles this:
# Row 1 is dropped (NaN position)
# Row 2 has weight replaced with 1.0
```

---

## Examples and Use Cases

### Example 1: Simple Unit Model

**Scenario**: Model a single stratigraphic unit defined by basal and top contacts.

```python
import numpy as np
from loop_model.manager import GeologicalSchema, DataRole, LoopProject
from loop_engine import Model
from loop_common.geometry import BoundingBox
from loop_common.observations import PointSet, Orientation

# 1. Create project
project = LoopProject()
schema = project.schema

# 2. Add observations
basal_points = PointSet(
    vertices=np.array([[0, 0, 100], [100, 100, 95]]),
    name="Basal_Top"
)
top_points = PointSet(
    vertices=np.array([[0, 0, 200], [100, 100, 205]]),
    name="Top_Top"
)
orientations = Orientation(
    coords=np.array([[50, 50, 150]]),
    vector=np.array([[0, 0, 1]]),
    name="Vertical"
)

project.add_observation(basal_points)
project.add_observation(top_points)
project.add_observation(orientations)

# 3. Build schema
unit = schema.add_unit(
    name="TopUnit",
    basal_contacts=[DataRole(obs_uid=basal_points.uuid, role="basal")],
    top_contacts=[DataRole(obs_uid=top_points.uuid, role="top")],
    orientations=[DataRole(obs_uid=orientations.uuid, role="orientation")],
)

# 4. Create model
bbox = BoundingBox(origin=[0, 0, 0], maximum=[100, 100, 250], nsteps=[10, 10, 25])
model = Model(schema, grid=bbox, interpolatortype="FDI", nelements=1000)

# 5. Solve
state = model.solve()

# 6. Evaluate
positions = np.array([[50, 50, 150], [50, 50, 200]])
field_values = model.evaluate_scalar_field(positions, feature_id=unit.uuid)
print(f"Field values: {field_values}")
# Expected: [0.0 (at basal), 1.0 (above top)] or similar
```

### Example 2: Faulted Model

**Scenario**: Model a fault displacing a unit.

```python
# After creating basal/top unit (from Example 1)...

# Add fault observations
fault_points = PointSet(
    vertices=np.array([[30, 50, 150], [70, 50, 120]]),
    name="FaultTrace"
)
slip_vector = Orientation(
    coords=np.array([[50, 50, 135]]),
    vector=np.array([[0, 0, 1]]),  # Vertical slip
    name="SlipVector"
)

project.add_observation(fault_points)
project.add_observation(slip_vector)

# Create fault
fault = schema.add_fault(
    name="MainFault",
    slip_vector=[DataRole(obs_uid=slip_vector.uuid, role="slip_vector")],
    # Can add more constraints: hanging_wall, footwall, etc.
)

# Make unit depend on fault (kinematic chain)
schema.dag.add_edge(fault.uuid, unit.uuid)

# Solve
state = model.solve()  # Fault solved first, then unit
```

### Example 3: Fold Model with Directional Regularisation

**Scenario**: Model a folded layer with anisotropic smoothing.

```python
from loop_interpolation import FiniteDifferenceInterpolator

# Create grid
bbox = BoundingBox(origin=[0, 0, 0], maximum=[100, 100, 100], nsteps=[10, 10, 10])
grid = bbox.as_structured_grid()

# Create interpolator
fdi = FiniteDifferenceInterpolator(grid)

# Add constraints (folded contacts)
fdi.add_interface_constraint(
    xyz=np.array([
        [0, 50, 40],    # Left limb
        [50, 50, 80],   # Hinge
        [100, 50, 40],  # Right limb
    ]),
    value=0.0,
    weights=10.0  # High confidence
)

# Setup with directional regularisation
# Smooth perpendicular to fold axis (X direction)
fdi.setup_interpolator(
    directional_regularisation=[
        {
            "weight": 0.01,
            "direction": [1, 0, 0],  # Perpendicular to fold axis
            "name": "perpendicular_smoothness"
        },
        {
            "weight": 0.001,  # Less smoothing along fold
            "direction": [0, 1, 1],
            "name": "fold_direction"
        }
    ]
)

# Solve
fdi.fit()

# Evaluate
sample_points = np.linspace([0, 50, 0], [100, 50, 100], 50)
values = fdi.evaluate_value(sample_points)
```

### Example 4: Diagnostics-Driven Workflow

**Scenario**: Build a model and iterate based on diagnostics.

```python
from loop_interpolation import InterpolatorFactory, InterpolatorType
from loop_common.geometry import BoundingBox

bbox = BoundingBox(...)

def build_and_diagnose(constraints, regularisation):
    """Build model and check diagnostics."""
    interp = InterpolatorFactory.create_interpolator(
        InterpolatorType.PIECEWISE_LINEAR,
        boundingbox=bbox,
        nelements=1000
    )
    
    # Add constraints
    for xyz, value in constraints:
        interp.add_interface_constraint(xyz, value)
    
    # Solve
    interp.setup_interpolator(regularisation=regularisation)
    interp.fit()
    
    # Diagnose
    report = interp.latest_diagnostics_report
    print(report.summary())
    
    return interp, report

# Iteration 1: Start with baseline
interp1, report1 = build_and_diagnose(constraints, regularisation=0.01)

# If diagnostics show under-smoothing, increase regularisation
if "oscillation" in report1.summary().lower():
    interp2, report2 = build_and_diagnose(constraints, regularisation=0.1)
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **Constraint** | A mathematical equation or inequality that the interpolator must satisfy (e.g., "field = 0 at point X") |
| **Support** | Spatial discretization (mesh or grid) on which the interpolator is defined |
| **Interpolator** | Mathematical function that fits constraints; produces evaluable scalar field |
| **Representation** | Interface-compliant object that can evaluate field value/gradient; implemented by interpolators |
| **Basis Function** | Fundamental building block of interpolator (e.g., hat functions for P1, finite difference stencil for FDI) |
| **Regularisation** | Penalty term added to optimization to prefer smooth or structured solutions |
| **Isotropic** | Uniform in all directions (contrast: anisotropic, directional) |
| **Least-Squares** | Optimization that minimizes sum of squared residuals ||A·x - d||² |
| **Discretisation** | Division of continuous domain into discrete mesh/grid |
| **Solver** | Numerical algorithm (CG, LSMR, ADMM) that solves linear system |
| **Fit** | Action of solving the optimization problem to find interpolator coefficients |
| **Evaluate** | Action of computing field value or gradient at arbitrary positions using solved coefficients |
| **Isosurface** | Contour where field value is constant (e.g., geological surface) |
| **Finite Difference** | Discretization method using grid; approximates derivatives with finite differences |
| **Finite Element** | Discretization method using mesh; approximates field with basis functions on elements |
| **Weight** | Multiplier on constraint; expresses confidence or importance of that constraint |
| **Directional Regularisation** | Penalty that varies along preferred directions (anisotropic smoothing) |

---

## References

- **Least Squares**: Boyd & Vandenberghe, *Convex Optimization* (online, free)
- **Finite Differences**: Fornberg, *A Practical Guide to Pseudospectral Methods*
- **Finite Elements**: Hughes, *The Finite Element Method*
- **Sparse Linear Algebra**: Davis, *Direct Methods for Sparse Linear Systems*
- **ADMM**: Boyd et al., *Distributed Optimization and Statistical Learning*

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-27 | Initial comprehensive design document |

