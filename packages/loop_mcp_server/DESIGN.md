# loop_mcp_server Design

## Purpose

`loop_mcp_server` provides a Model Context Protocol (MCP) server interface for LoopStructural, enabling agents and LLMs to interact with the geological modeling library through standardized tools and resources.

This module acts as the integration layer between LoopStructural's modeling capabilities and MCP-compatible clients (agents, Claude, etc.).

## Architecture

The server exposes three main categories of functionality:

### 1. Tools (RPC-style operations)

Tools are callable operations that agents can invoke:

- `load_model` - Load a model from YAML configuration
- `solve_model` - Execute geological model solver
- `export_model` - Export model to various formats (HDF5, VTK, etc.)
- `get_model_info` - Retrieve model metadata and statistics
- `create_feature` - Add geological features (units, faults) to model
- `add_observations` - Add observations (points, orientations, linesets) to model

### 2. Resources (RPC-style read-only access)

Resources provide information that can be queried:

- `model_schema` - JSON schema for valid model configurations
- `available_interpolators` - List of available interpolation strategies
- `feature_types` - Supported geological feature types and their properties

### 3. Server Lifecycle

- Server initialization and shutdown
- Error handling and diagnostics
- Validation mode configuration (strict/lenient/warnings)

## Integration Points

- **loop_api**: YAML assembly and project creation
- **loop_engine**: Model solving and interpretation
- **loop_model**: Geological schema and project contracts
- **loop_common**: Utility types and geometry

## Validation Modes

The server supports validation modes passed from clients:
- `strict`: Raise errors on any issues
- `warnings`: Log issues as warnings
- `lenient`: Silently skip problematic elements

## MCP Specification Compliance

This server implements the Model Context Protocol specification, providing:
- Standard request/response JSON-RPC format
- Error handling and diagnostics
- Resource and tool registration
- Version negotiation
