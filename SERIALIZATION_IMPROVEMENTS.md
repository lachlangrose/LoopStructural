# JSON Serialization Improvements

## Summary

This pull request implements comprehensive JSON serialization support for geological models in LoopStructural. The entire geological model, including the current state of interpolators and their solutions, can now be saved to a JSON data structure.

## Changes Made

### 1. Core Serialization Methods

#### GeologicalInterpolator (`_geological_interpolator.py`)
- Enhanced `to_dict()` method to properly convert numpy arrays to lists
- Added placeholder `from_dict()` classmethod for future deserialization
- Ensures all data arrays are JSON-serializable

#### DiscreteInterpolator (`_discrete_interpolator.py`)
- Updated `to_dict()` to include solution coefficients (`c` array)
- Includes support structure in serialization
- Added placeholder `from_dict()` classmethod

#### BaseStructuredSupport (`supports/_3d_base_structured.py`)
- Fixed `to_dict()` to convert all numpy arrays to lists
- Properly serializes origin, nsteps, step_vector, and rotation_xy

#### StructuredGrid (`supports/_3d_structured_grid.py`)
- Updated `to_dict()` to use proper type name serialization
- Inherits numpy array conversion from base class

### 2. Feature Serialization

#### BaseFeature (`_base_geological_feature.py`)
- Fixed `to_json()` to serialize FeatureType enum properly
- Added `to_dict()` method

#### GeologicalFeature (`_geological_feature.py`)
- Updated `to_json()` to call interpolator's `to_dict()` instead of `to_json()`
- Added `to_dict()` method
- Added placeholder `from_dict()` classmethod
- Removed debug print statement

### 3. Model Serialization

#### GeologicalModel (`core/geological_model.py`)
- Enhanced `to_dict()` to serialize complete feature state including interpolators
- Added error handling for feature serialization failures
- Added `save_to_json(filename)` convenience method
- Added `load_from_json(filename)` placeholder method
- Added placeholder `from_dict()` classmethod

## What's Serialized

The complete model serialization includes:

1. **Model Configuration**
   - Bounding box (origin, maximum, nsteps)
   - Stratigraphic column information

2. **Feature Information** (for each feature)
   - Feature name and type
   - Associated faults and regions

3. **Interpolator State** (for each feature)
   - Interpolator type (PLI, FDI, etc.)
   - All constraint data (gradient, value, normal, tangent, interface)
   - Solution coefficients (c array) - the actual solution to the interpolation
   - Build status (up_to_date, valid flags)

4. **Support Structure** (for each interpolator)
   - Support type and configuration
   - Grid/mesh parameters (origin, nsteps, step_vector, rotation)

## Usage

### Serialize to Dictionary
```python
model_dict = model.to_dict()
```

### Serialize to JSON String
```python
import json
json_string = json.dumps(model.to_dict())
```

### Save to File
```python
model.save_to_json('my_model.json')
```

### Load from File (Not Yet Implemented)
```python
# Future feature - currently raises NotImplementedError
model = GeologicalModel.load_from_json('my_model.json')
```

## Testing

Comprehensive test suite added in `tests/unit/modelling/test_model_serialization.py`:

- `test_geological_model_to_dict()` - Basic model serialization
- `test_geological_model_with_feature_to_dict()` - Model with feature
- `test_model_to_dict_json_serializable()` - JSON compatibility
- `test_interpolator_state_in_serialization()` - Interpolator state
- `test_support_serialization()` - Support structure
- `test_bounding_box_serialization()` - Bounding box
- `test_empty_model_serialization()` - Empty model
- `test_save_to_json_file()` - File saving functionality

All tests pass successfully.

## Documentation

Added comprehensive example in `examples/1_basic/plot_8_model_serialization.py` demonstrating:
- How to serialize a model
- What data is included in serialization
- How to save to a JSON file
- Verification of serialized data completeness

## Limitations

### Deserialization Not Yet Implemented
- `from_dict()` and `load_from_json()` methods are defined but raise `NotImplementedError`
- Full deserialization requires:
  - Interpolator factory support to reconstruct interpolators from type names
  - Support factory to reconstruct support structures
  - Feature factory to reconstruct features
  - Proper handling of circular references (model ↔ features)

### What This Means
- Models can be fully serialized and saved to JSON
- The serialized data captures the complete model state including solutions
- The serialized data can be inspected, analyzed, or shared
- Models cannot yet be reconstructed from serialized data (future feature)

## Backward Compatibility

- All changes are backward compatible
- Existing `to_json()` methods continue to work
- New `to_dict()` methods provide enhanced functionality
- No breaking changes to existing API

## Tested Interpolator Types

Serialization has been tested with:
- PLI (Piecewise Linear Interpolation)
- FDI (Finite Difference Interpolation)

Both interpolator types serialize successfully to JSON.

## File Changes

Modified files:
- `LoopStructural/interpolators/_geological_interpolator.py`
- `LoopStructural/interpolators/_discrete_interpolator.py`
- `LoopStructural/interpolators/supports/_3d_base_structured.py`
- `LoopStructural/interpolators/supports/_3d_structured_grid.py`
- `LoopStructural/modelling/features/_base_geological_feature.py`
- `LoopStructural/modelling/features/_geological_feature.py`
- `LoopStructural/modelling/core/geological_model.py`

New files:
- `tests/unit/modelling/test_model_serialization.py`
- `examples/1_basic/plot_8_model_serialization.py`

## Benefits

1. **Persistence**: Models can be saved for later analysis
2. **Sharing**: Models can be easily shared with collaborators
3. **Archiving**: Modeling results can be archived
4. **Inspection**: Serialized data can be inspected and analyzed
5. **Debugging**: Model state can be examined in detail
6. **Version Control**: JSON files can be stored in version control systems

## Future Work

- Implement full deserialization support (`from_dict` methods)
- Add support for more interpolator types
- Add support for fault features
- Add support for fold features
- Optimize JSON size (compression, sparse matrix storage)
- Add validation for deserialized data
