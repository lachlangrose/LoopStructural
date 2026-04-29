# LoopStructural MCP Server

An MCP (Model Context Protocol) server implementation that exposes LoopStructural geological modeling capabilities to agents and LLMs.

## Overview

This module provides a standardized interface for agents and Claude to interact with the LoopStructural library through the Model Context Protocol. It enables:

- Loading geological models from YAML configurations
- Solving geological models with various interpolation strategies
- Creating and managing geological features (units, faults)
- Adding observations and constraints to models
- Exporting models in multiple formats

## Installation

Install from the workspace:

```bash
pip install -e packages/loop_mcp_server/
```

## Quick Start

### Python Usage

```python
from loop_mcp_server import LoopStructuralMCPServer

# Create server instance
server = LoopStructuralMCPServer(validation_mode="strict")

# Get available tools
tools = server.get_tools()
for tool_name, tool_def in tools.items():
    print(f"{tool_name}: {tool_def['description']}")

# Call a tool
result = await server.load_model(
    source="path/to/model.yaml",
    validation_mode="strict"
)
```

### Agent Integration

Configure your agent to use this MCP server by adding it to your tools configuration:

```yaml
tools:
  - type: mcp_server
    module: loop_mcp_server
    class: LoopStructuralMCPServer
    kwargs:
      validation_mode: strict
```

## Available Tools

### load_model
Load a geological model from YAML configuration.

**Input:**
- `source` (str|dict): YAML file path, YAML string, or configuration dictionary
- `validation_mode` (str): Optional validation mode override

**Output:**
```json
{
  "status": "success|error",
  "config": {...},
  "diagnostics": [...]
}
```

### solve_model
Solve a loaded geological model.

**Input:**
- `model_config` (dict): Model configuration
- `validation_mode` (str): Optional validation mode
- `solver_kwargs` (dict): Additional solver parameters

**Output:**
```json
{
  "status": "success|error",
  "message": "..."
}
```

### export_model
Export solved model to file.

**Input:**
- `model_config` (dict): Model configuration
- `output_format` (str): Format - 'hdf5', 'vtk', 'csv'
- `output_path` (str): Output file path

**Output:**
```json
{
  "status": "success|error",
  "path": "...",
  "format": "..."
}
```

### get_model_info
Get information about a model configuration.

**Input:**
- `model_config` (dict): Model configuration

**Output:**
```json
{
  "status": "success",
  "metadata": {...},
  "num_observations": 0,
  "num_features": 0,
  "num_topology_rules": 0,
  "bounding_box": {...},
  "diagnostics": [...]
}
```

### create_feature
Add a geological feature to the model.

**Input:**
- `model_config` (dict): Model configuration
- `feature_type` (str): 'unit' or 'fault'
- `feature_properties` (dict): Feature-specific properties

**Output:**
```json
{
  "status": "success",
  "config": {...}
}
```

### add_observations
Add observations to a model.

**Input:**
- `model_config` (dict): Model configuration
- `observations` (list): List of observation dictionaries

**Output:**
```json
{
  "status": "success",
  "total_observations": 0
}
```

## Validation Modes

- `strict`: Raise errors on any validation issues
- `warnings`: Log issues as warnings, continue processing
- `lenient`: Silently skip problematic elements

## Example: Building a Model with Agent

```python
import asyncio
from loop_mcp_server import LoopStructuralMCPServer

async def build_model():
    server = LoopStructuralMCPServer()
    
    # Create base configuration
    config = {
        "metadata": {"name": "My Model"},
        "bounding_box": {
            "origin": [0, 0, 0],
            "maximum": [1000, 1000, 1000]
        }
    }
    
    # Add a unit feature
    result = await server.create_feature(
        model_config=config,
        feature_type="unit",
        feature_properties={"name": "Basement"}
    )
    config = result["config"]
    
    # Add observations
    observations = [
        {"type": "pointset", "data": [[100, 100, 100]]},
    ]
    result = await server.add_observations(
        model_config=config,
        observations=observations
    )
    
    # Get model info
    info = await server.get_model_info(config)
    print(info)

asyncio.run(build_model())
```

## Testing

Run tests with pytest:

```bash
pytest packages/loop_mcp_server/tests/ -v
```

## Architecture

See [DESIGN.md](./DESIGN.md) for detailed architecture documentation.

## Dependencies

- `mcp>=0.1.0` - Model Context Protocol
- `loop-api>=0.1.0` - API layer
- `loop-engine>=0.1.0` - Solver engine
- `loop-model>=0.1.0` - Data models
- `loop-common>=0.1.0` - Common utilities
- `pydantic>=2.0` - Data validation

## License

See parent project LICENSE file.
