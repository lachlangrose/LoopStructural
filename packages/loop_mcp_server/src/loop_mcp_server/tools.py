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

    config: dict[str, Any] = Field(
        alias="model_config",
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

    config: dict[str, Any] = Field(
        alias="model_config",
        description="Model configuration to export"
    )
    output_format: str = Field(
        description="Export format: 'hdf5', 'vtk', 'csv', etc."
    )
    output_path: str = Field(description="Output file path")


class GetModelInfoInput(BaseModel):
    """Input schema for get_model_info tool."""

    config: dict[str, Any] = Field(
        alias="model_config",
        description="Model configuration to analyze"
    )


class CreateFeatureInput(BaseModel):
    """Input schema for create_feature tool."""

    config: dict[str, Any] = Field(
        alias="model_config",
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

    config: dict[str, Any] = Field(
        alias="model_config",
        description="Model configuration to add observations to"
    )
    observations: list[dict[str, Any]] = Field(
        description="List of observations to add"
    )


class BuildGeologicalModelInput(BaseModel):
    """Input schema for build_geological_model tool."""

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Model metadata (name, project tags, provenance)",
    )
    bounding_box: dict[str, Any] = Field(
        description="Bounding box with origin and maximum (and optional nsteps)"
    )
    features: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Feature list for units and faults",
    )
    observations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Observation list used to constrain the model",
    )
    topology: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Topological relationship list (overlies, faults, abuts, etc.)",
    )
    solve: bool = Field(
        default=False,
        description="If true, try to solve the model after building",
    )
    validation_mode: str = Field(
        default="strict",
        description="Validation mode: 'strict', 'warnings', or 'lenient'",
    )
    solver_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional kwargs passed to model.solve when solve=true",
    )


class EvaluateModelQualityInput(BaseModel):
    """Input schema for evaluate_model_quality tool."""

    config: dict[str, Any] = Field(
        alias="model_config",
        description="Model configuration to evaluate",
    )
    validation_mode: str = Field(
        default="strict",
        description="Validation mode: 'strict', 'warnings', or 'lenient'",
    )
    attempt_solve: bool = Field(
        default=False,
        description="If true, attempt a solve and include solve diagnostics",
    )
    solver_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional kwargs passed to model.solve when attempt_solve=true",
    )


class SuggestModelModificationsInput(BaseModel):
    """Input schema for suggest_model_modifications tool."""

    config: dict[str, Any] = Field(
        alias="model_config",
        description="Model configuration to improve",
    )
    objective: str = Field(
        default="improve geological plausibility",
        description="Optimization objective for modification suggestions",
    )
    max_suggestions: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum number of proposed modifications",
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
