"""
Model Serialization and Persistence
====================================

This example demonstrates how to save and potentially reload a geological model
using the to_dict() method for JSON serialization. The serialized model includes
the complete state of all features and their interpolators, including the solution
to the interpolation problem.
"""

import numpy as np
import json
from LoopStructural import GeologicalModel
from LoopStructural.datasets import load_claudius

# %%
# Load example data and create a model
# -------------------------------------
# First, we'll create a simple geological model with a foliation feature

data, bb = load_claudius()
model = GeologicalModel(bb[0, :], bb[1, :])
model.set_model_data(data)

# Create a foliation feature using piecewise linear interpolation
strati = model.create_and_add_foliation(
    'strati',
    interpolatortype='PLI',
    nelements=500,
    buffer=0.3
)

# Run the interpolation
model.update()

print(f"Model created with {len(model.features)} feature(s)")
print(f"Feature '{strati.name}' interpolator type: {strati.interpolator.type}")

# %%
# Serialize the model to a dictionary
# ------------------------------------
# The to_dict() method converts the entire model state into a dictionary
# that can be serialized to JSON. This includes:
# - All features and their properties
# - Interpolator configuration and constraints
# - Solution coefficients from the interpolation
# - Support structure (mesh/grid) configuration
# - Bounding box parameters

model_dict = model.to_dict()

print("\nModel dictionary structure:")
print(f"- Features: {len(model_dict['model']['features'])}")
print(f"- Bounding box: {model_dict['model']['bounding_box']['origin']} to {model_dict['model']['bounding_box']['maximum']}")

# %%
# Examine the serialized feature data
# ------------------------------------
# Each feature includes its complete state

feature_dict = model_dict['model']['features'][0]
print(f"\nFeature '{feature_dict['name']}' serialized data:")
print(f"- Type: {feature_dict['type']}")
print(f"- Interpolator type: {feature_dict['interpolator']['type']}")
print(f"- Number of solution coefficients: {len(feature_dict['interpolator']['c'])}")
print(f"- Interpolator up to date: {feature_dict['interpolator']['up_to_date']}")

# %%
# Examine the interpolator data
# ------------------------------
# The interpolator data includes all constraints used in the interpolation

interpolator_data = feature_dict['interpolator']['data']
print("\nInterpolator constraint data:")
for constraint_type, constraint_data in interpolator_data.items():
    if len(constraint_data) > 0:
        print(f"- {constraint_type}: {len(constraint_data)} constraints")

# %%
# Examine the support structure
# ------------------------------
# The support (mesh/grid) configuration is also serialized

support_dict = feature_dict['interpolator']['support']
print("\nSupport structure:")
print(f"- Type: {support_dict.get('type', 'N/A')}")
print(f"- Origin: {support_dict['origin']}")
print(f"- Number of steps: {support_dict['nsteps']}")
print(f"- Step vector: {support_dict['step_vector']}")

# %%
# Convert to JSON string
# ----------------------
# The dictionary can be serialized to a JSON string for storage

json_string = json.dumps(model_dict, indent=2)
print(f"\nJSON serialization successful!")
print(f"JSON string size: {len(json_string)} bytes ({len(json_string) / 1024:.1f} KB)")

# %%
# Save to file using save_to_json
# --------------------------------
# The model provides a convenient method to save directly to a JSON file

# Uncomment to save to file:
# model.save_to_json('geological_model.json')
# print("Model saved to 'geological_model.json'")

# Or you can use the dictionary directly:
# with open('geological_model.json', 'w') as f:
#     json.dump(model_dict, f, indent=2)
# print("Model saved to 'geological_model.json'")

print("\nTo save the model to a file, use:")
print("  model.save_to_json('my_model.json')")

# %%
# Verify the serialized data
# ---------------------------
# We can verify that the serialized model contains all the essential information

print("\nVerifying serialized model completeness:")

# Check bounding box
bbox = model_dict['model']['bounding_box']
assert len(bbox['origin']) == 3, "Bounding box origin should be 3D"
assert len(bbox['maximum']) == 3, "Bounding box maximum should be 3D"
print("✓ Bounding box serialized correctly")

# Check features
assert len(model_dict['model']['features']) > 0, "Should have at least one feature"
print("✓ Features serialized correctly")

# Check interpolator state
feature = model_dict['model']['features'][0]
assert 'interpolator' in feature, "Feature should have interpolator"
assert 'c' in feature['interpolator'], "Interpolator should have solution coefficients"
assert len(feature['interpolator']['c']) > 0, "Should have solution coefficients"
print("✓ Interpolator state (including solution) serialized correctly")

# Check support structure
assert 'support' in feature['interpolator'], "Interpolator should have support"
support = feature['interpolator']['support']
assert all(isinstance(support[key], list) for key in ['origin', 'nsteps', 'step_vector']), \
    "Support arrays should be serialized as lists"
print("✓ Support structure serialized correctly")

print("\n✓ Model serialization complete and verified!")

# %%
# What's included in the serialization?
# --------------------------------------
# The serialized model includes:
#
# 1. **Model Configuration**
#    - Bounding box (origin, maximum, nsteps)
#    - Stratigraphic column information
#
# 2. **Feature Information**
#    - Feature name and type
#    - Associated faults and regions
#
# 3. **Interpolator State**
#    - Interpolator type (PLI, FDI, etc.)
#    - All constraint data (gradient, value, normal, tangent, interface)
#    - Solution coefficients (c array)
#    - Build status (up_to_date, valid flags)
#
# 4. **Support Structure**
#    - Support type and configuration
#    - Grid/mesh parameters (origin, nsteps, step_vector, rotation)
#
# This complete state allows you to:
# - Save models for later analysis
# - Share models with collaborators
# - Archive modeling results
# - Potentially reconstruct models (deserialization support coming soon)

print("\n" + "="*70)
print("NOTE: Deserialization (from_dict/from_json) is not fully implemented yet.")
print("Currently, to_dict provides a complete snapshot of the model state that")
print("can be saved and inspected, but cannot yet be used to reconstruct a")
print("fully functional model.")
print("="*70)
