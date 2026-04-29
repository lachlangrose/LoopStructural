"""MCP Server implementation for LoopStructural."""

import json
import logging
from typing import Any, Optional

from loop_api import YAMLAssembly
from loop_engine import Model

from .tools import (
    Tool,
    LoadModelInput,
    SolveModelInput,
    ExportModelInput,
    GetModelInfoInput,
    CreateFeatureInput,
    AddObservationsInput,
    build_tool,
)

logger = logging.getLogger(__name__)


class LoopStructuralMCPServer:
    """MCP Server for LoopStructural geological modeling."""

    def __init__(self, validation_mode: str = "strict"):
        """Initialize the MCP server.

        Args:
            validation_mode: Validation mode ('strict', 'warnings', 'lenient')
        """
        self.validation_mode = validation_mode
        self.tools: dict[str, Tool] = {}
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all available tools."""
        self.tools["load_model"] = build_tool(
            name="load_model",
            description="Load a geological model from YAML configuration",
            handler=self.load_model,
            input_schema=LoadModelInput,
        )

        self.tools["solve_model"] = build_tool(
            name="solve_model",
            description="Solve a geological model",
            handler=self.solve_model,
            input_schema=SolveModelInput,
        )

        self.tools["export_model"] = build_tool(
            name="export_model",
            description="Export a solved model to file",
            handler=self.export_model,
            input_schema=ExportModelInput,
        )

        self.tools["get_model_info"] = build_tool(
            name="get_model_info",
            description="Get information about a model",
            handler=self.get_model_info,
            input_schema=GetModelInfoInput,
        )

        self.tools["create_feature"] = build_tool(
            name="create_feature",
            description="Create a new geological feature in the model",
            handler=self.create_feature,
            input_schema=CreateFeatureInput,
        )

        self.tools["add_observations"] = build_tool(
            name="add_observations",
            description="Add observations to a model",
            handler=self.add_observations,
            input_schema=AddObservationsInput,
        )

    def get_tools(self) -> dict[str, dict[str, Any]]:
        """Get all registered tools in MCP format.

        Returns:
            Dictionary mapping tool names to tool definitions
        """
        tools = {}
        for name, tool in self.tools.items():
            tools[name] = {
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a registered tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            JSON string result of the tool call

        Raises:
            ValueError: If tool not found
        """
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")

        tool = self.tools[tool_name]
        try:
            result = await tool.handler(**arguments)
            return json.dumps(result)
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return json.dumps({"error": str(e)})

    # Tool Implementations

    async def load_model(
        self,
        source: str | dict,
        validation_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """Load a model from YAML configuration.

        Args:
            source: YAML file path, YAML string, or configuration dict
            validation_mode: Override default validation mode

        Returns:
            Loaded model configuration with diagnostics
        """
        mode = validation_mode or self.validation_mode

        try:
            assembly = YAMLAssembly(source, validation_mode=mode)
            return {
                "status": "success",
                "config": assembly.spec,
                "diagnostics": assembly.diagnostics,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "diagnostics": [],
            }

    async def solve_model(
        self,
        model_config: dict[str, Any],
        validation_mode: Optional[str] = None,
        solver_kwargs: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Solve a geological model.

        Args:
            model_config: Model configuration
            validation_mode: Override default validation mode
            solver_kwargs: Additional solver arguments

        Returns:
            Solution results
        """
        mode = validation_mode or self.validation_mode
        kwargs = solver_kwargs or {}

        try:
            # Load and validate configuration
            assembly = YAMLAssembly(model_config, validation_mode=mode)

            # Create and solve model
            model = Model.from_yaml(model_config)
            model.solve(**kwargs)

            return {
                "status": "success",
                "message": "Model solved successfully",
            }
        except Exception as e:
            logger.error(f"Error solving model: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def export_model(
        self,
        model_config: dict[str, Any],
        output_format: str,
        output_path: str,
    ) -> dict[str, Any]:
        """Export a model to file.

        Args:
            model_config: Model configuration
            output_format: Export format (hdf5, vtk, csv, etc.)
            output_path: Output file path

        Returns:
            Export results
        """
        try:
            model = Model.from_yaml(model_config)

            if output_format.lower() == "hdf5":
                model.save(output_path)
            elif output_format.lower() == "vtk":
                model.to_vtk(output_path)
            else:
                raise ValueError(f"Unsupported export format: {output_format}")

            return {
                "status": "success",
                "message": f"Model exported to {output_path}",
                "format": output_format,
                "path": output_path,
            }
        except Exception as e:
            logger.error(f"Error exporting model: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def get_model_info(
        self,
        model_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Get information about a model.

        Args:
            model_config: Model configuration

        Returns:
            Model metadata and statistics
        """
        try:
            assembly = YAMLAssembly(model_config)

            info = {
                "status": "success",
                "metadata": assembly.spec.get("metadata", {}),
                "num_observations": len(assembly.spec.get("observations", [])),
                "num_features": len(assembly.spec.get("features", [])),
                "num_topology_rules": len(assembly.spec.get("topology", [])),
                "bounding_box": assembly.spec.get("bounding_box", {}),
                "diagnostics": assembly.diagnostics,
            }
            return info
        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def create_feature(
        self,
        model_config: dict[str, Any],
        feature_type: str,
        feature_properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new feature in the model.

        Args:
            model_config: Existing model configuration
            feature_type: Feature type ('unit' or 'fault')
            feature_properties: Feature properties

        Returns:
            Updated configuration with new feature
        """
        try:
            if feature_type not in ("unit", "fault"):
                raise ValueError(
                    f"Invalid feature type: {feature_type}. Must be 'unit' or 'fault'"
                )

            # Add feature to configuration
            updated_config = dict(model_config)
            if "features" not in updated_config:
                updated_config["features"] = []

            updated_config["features"].append({
                "type": feature_type,
                **feature_properties,
            })

            return {
                "status": "success",
                "message": f"Feature of type '{feature_type}' added",
                "config": updated_config,
            }
        except Exception as e:
            logger.error(f"Error creating feature: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def add_observations(
        self,
        model_config: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Add observations to the model.

        Args:
            model_config: Model configuration
            observations: List of observation dictionaries

        Returns:
            Updated configuration with observations
        """
        try:
            updated_config = dict(model_config)
            if "observations" not in updated_config:
                updated_config["observations"] = []

            updated_config["observations"].extend(observations)

            return {
                "status": "success",
                "message": f"Added {len(observations)} observations",
                "config": updated_config,
                "total_observations": len(updated_config["observations"]),
            }
        except Exception as e:
            logger.error(f"Error adding observations: {e}")
            return {
                "status": "error",
                "error": str(e),
            }
