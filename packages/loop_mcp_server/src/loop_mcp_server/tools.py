"""MCP Tools for LoopStructural modeling operations."""

from typing import Any, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass
class Tool:
    """Represents an MCP tool that can be called by agents."""

    name: str
    description: str
    handler: Callable
    input_schema: dict[str, Any]


class LoadModelInput(BaseModel):
    """Input schema for load_model tool."""

    source: str | dict = Field(
        description="YAML file path, YAML string, or configuration dictionary"
    )
    validation_mode: str = Field(
        default="strict",
        description="Validation mode: 'strict', 'warnings', or 'lenient'",
    )


class SolveModelInput(BaseModel):
    """Input schema for solve_model tool."""

    model_config: dict[str, Any] = Field(
        description="Model configuration or path to load from"
    )
    validation_mode: str = Field(
        default="strict",
        description="Validation mode: 'strict', 'warnings', or 'lenient'",
    )
    solver_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional keyword arguments to pass to solver",
    )


class ExportModelInput(BaseModel):
    """Input schema for export_model tool."""

    model_config: dict[str, Any] = Field(
        description="Model configuration to export"
    )
    output_format: str = Field(
        description="Export format: 'hdf5', 'vtk', 'csv', etc."
    )
    output_path: str = Field(description="Output file path")


class GetModelInfoInput(BaseModel):
    """Input schema for get_model_info tool."""

    model_config: dict[str, Any] = Field(
        description="Model configuration to analyze"
    )


class CreateFeatureInput(BaseModel):
    """Input schema for create_feature tool."""

    model_config: dict[str, Any] = Field(
        description="Existing model configuration"
    )
    feature_type: str = Field(
        description="Feature type: 'unit' or 'fault'"
    )
    feature_properties: dict[str, Any] = Field(
        description="Properties defining the feature"
    )


class AddObservationsInput(BaseModel):
    """Input schema for add_observations tool."""

    model_config: dict[str, Any] = Field(
        description="Model configuration to add observations to"
    )
    observations: list[dict[str, Any]] = Field(
        description="List of observations to add"
    )


def build_tool(
    name: str,
    description: str,
    handler: Callable,
    input_schema: type,
) -> Tool:
    """Build an MCP tool from a name, description, handler, and Pydantic schema."""
    schema_dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    
    if hasattr(input_schema, "model_json_schema"):
        # Use Pydantic v2 method
        full_schema = input_schema.model_json_schema()
        schema_dict["properties"] = full_schema.get("properties", {})
        schema_dict["required"] = full_schema.get("required", [])
    
    return Tool(
        name=name,
        description=description,
        handler=handler,
        input_schema=schema_dict,
    )


# Tool handlers are implemented in server.py
# These are placeholder definitions for schema building
