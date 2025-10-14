"""
Tests for model serialization (to_dict/from_dict) functionality
"""
import pytest
import json
import numpy as np
from LoopStructural import GeologicalModel
from LoopStructural.datasets import load_claudius


def test_geological_model_to_dict():
    """Test that a geological model can be converted to a dictionary"""
    data, bb = load_claudius()
    model = GeologicalModel(bb[0, :], bb[1, :])
    model.set_model_data(data)
    
    model_dict = model.to_dict()
    
    # Check basic structure
    assert isinstance(model_dict, dict)
    assert "model" in model_dict
    assert "features" in model_dict["model"]
    assert "bounding_box" in model_dict["model"]
    assert isinstance(model_dict["model"]["features"], list)


def test_geological_model_with_feature_to_dict():
    """Test that a model with a feature can be serialized"""
    data, bb = load_claudius()
    model = GeologicalModel(bb[0, :], bb[1, :])
    model.set_model_data(data)
    
    # Create a simple feature
    strati = model.create_and_add_foliation(
        'strati', 
        interpolatortype='PLI', 
        nelements=500, 
        buffer=0.3
    )
    model.update()
    
    model_dict = model.to_dict()
    
    # Check that the feature is included
    assert len(model_dict["model"]["features"]) > 0
    feature_dict = model_dict["model"]["features"][0]
    
    # Check feature structure
    assert "name" in feature_dict
    assert feature_dict["name"] == "strati"
    assert "interpolator" in feature_dict
    assert "type" in feature_dict


def test_model_to_dict_json_serializable():
    """Test that the dictionary from to_dict can be serialized to JSON"""
    data, bb = load_claudius()
    model = GeologicalModel(bb[0, :], bb[1, :])
    model.set_model_data(data)
    
    strati = model.create_and_add_foliation(
        'strati', 
        interpolatortype='PLI', 
        nelements=500, 
        buffer=0.3
    )
    model.update()
    
    model_dict = model.to_dict()
    
    # This should not raise an exception
    json_str = json.dumps(model_dict)
    
    # Verify it's valid JSON by parsing it back
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    assert "model" in parsed


def test_interpolator_state_in_serialization():
    """Test that interpolator state including solution is serialized"""
    data, bb = load_claudius()
    model = GeologicalModel(bb[0, :], bb[1, :])
    model.set_model_data(data)
    
    strati = model.create_and_add_foliation(
        'strati', 
        interpolatortype='PLI', 
        nelements=500, 
        buffer=0.3
    )
    model.update()
    
    model_dict = model.to_dict()
    feature_dict = model_dict["model"]["features"][0]
    interpolator_dict = feature_dict["interpolator"]
    
    # Check that interpolator includes key state
    assert "type" in interpolator_dict
    assert "data" in interpolator_dict
    assert "c" in interpolator_dict  # solution coefficients
    assert "support" in interpolator_dict
    assert "up_to_date" in interpolator_dict
    
    # Verify solution coefficients are serialized as list
    assert isinstance(interpolator_dict["c"], list)
    assert len(interpolator_dict["c"]) > 0
    
    # Verify data arrays are serialized
    assert isinstance(interpolator_dict["data"], dict)
    for key in ["gradient", "value", "normal", "tangent", "interface"]:
        assert key in interpolator_dict["data"]
        assert isinstance(interpolator_dict["data"][key], list)


def test_support_serialization():
    """Test that support structure is properly serialized"""
    data, bb = load_claudius()
    model = GeologicalModel(bb[0, :], bb[1, :])
    model.set_model_data(data)
    
    strati = model.create_and_add_foliation(
        'strati', 
        interpolatortype='PLI', 
        nelements=500, 
        buffer=0.3
    )
    model.update()
    
    model_dict = model.to_dict()
    support_dict = model_dict["model"]["features"][0]["interpolator"]["support"]
    
    # Check support structure
    assert isinstance(support_dict, dict)
    assert "origin" in support_dict
    assert "nsteps" in support_dict
    assert "step_vector" in support_dict
    
    # Verify numpy arrays are converted to lists
    assert isinstance(support_dict["origin"], list)
    assert isinstance(support_dict["nsteps"], list)
    assert isinstance(support_dict["step_vector"], list)
    
    # Check dimensions
    assert len(support_dict["origin"]) == 3
    assert len(support_dict["nsteps"]) == 3
    assert len(support_dict["step_vector"]) == 3


def test_bounding_box_serialization():
    """Test that bounding box is properly serialized"""
    data, bb = load_claudius()
    model = GeologicalModel(bb[0, :], bb[1, :])
    
    model_dict = model.to_dict()
    bbox_dict = model_dict["model"]["bounding_box"]
    
    # Check bounding box structure
    assert isinstance(bbox_dict, dict)
    assert "origin" in bbox_dict
    assert "maximum" in bbox_dict
    assert "nsteps" in bbox_dict
    
    # Verify values are lists
    assert isinstance(bbox_dict["origin"], list)
    assert isinstance(bbox_dict["maximum"], list)
    assert isinstance(bbox_dict["nsteps"], list)


def test_empty_model_serialization():
    """Test serialization of a model without features"""
    model = GeologicalModel([0, 0, 0], [100, 100, 100])
    
    model_dict = model.to_dict()
    
    # Should have the basic structure even without features
    assert "model" in model_dict
    assert "features" in model_dict["model"]
    assert "bounding_box" in model_dict["model"]
    assert len(model_dict["model"]["features"]) == 0
    
    # Should be JSON serializable
    json_str = json.dumps(model_dict)
    assert isinstance(json_str, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
