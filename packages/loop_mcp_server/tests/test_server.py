"""Tests for LoopStructural MCP Server."""

import pytest
from loop_mcp_server import LoopStructuralMCPServer


@pytest.fixture
def server():
    """Create a test server instance."""
    return LoopStructuralMCPServer(validation_mode="strict")


def test_server_initialization(server):
    """Test server initializes correctly."""
    assert server is not None
    assert server.validation_mode == "strict"


def test_tools_registered(server):
    """Test that all tools are registered."""
    tools = server.get_tools()
    
    expected_tools = {
        "load_model",
        "solve_model",
        "export_model",
        "get_model_info",
        "create_feature",
        "add_observations",
    }
    
    assert set(tools.keys()) == expected_tools


def test_tool_schemas(server):
    """Test that tools have valid input schemas."""
    tools = server.get_tools()
    
    for tool_name, tool_def in tools.items():
        assert "description" in tool_def
        assert "inputSchema" in tool_def
        assert "type" in tool_def["inputSchema"]
        assert "properties" in tool_def["inputSchema"]


@pytest.mark.asyncio
async def test_get_model_info_with_simple_config(server):
    """Test get_model_info with a simple configuration."""
    config = {
        "metadata": {"name": "test_model"},
        "bounding_box": {"origin": [0, 0, 0], "maximum": [100, 100, 100]},
    }
    
    result = await server.get_model_info(config)
    
    assert result["status"] == "success"
    assert result["metadata"]["name"] == "test_model"
    assert result["num_observations"] == 0


@pytest.mark.asyncio
async def test_create_feature(server):
    """Test creating a geological feature."""
    config = {"features": []}
    
    result = await server.create_feature(
        model_config=config,
        feature_type="unit",
        feature_properties={"name": "Unit1"},
    )
    
    assert result["status"] == "success"
    assert len(result["config"]["features"]) == 1
    assert result["config"]["features"][0]["name"] == "Unit1"


@pytest.mark.asyncio
async def test_create_feature_invalid_type(server):
    """Test that creating feature with invalid type fails."""
    config = {"features": []}
    
    result = await server.create_feature(
        model_config=config,
        feature_type="invalid",
        feature_properties={},
    )
    
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_add_observations(server):
    """Test adding observations to model."""
    config = {"observations": []}
    observations = [
        {"type": "pointset", "data": [[0, 0, 0]]},
        {"type": "orientation", "data": [[1, 1, 1, 45, 30]]},
    ]
    
    result = await server.add_observations(
        model_config=config,
        observations=observations,
    )
    
    assert result["status"] == "success"
    assert result["total_observations"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
