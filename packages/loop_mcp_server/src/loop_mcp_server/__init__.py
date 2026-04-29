"""LoopStructural MCP Server - Agent integration for geological modeling."""

from .server import LoopStructuralMCPServer
from .tools import (
    Tool,
    LoadModelInput,
    SolveModelInput,
    ExportModelInput,
    GetModelInfoInput,
    CreateFeatureInput,
    AddObservationsInput,
)

__version__ = "0.1.0"

__all__ = [
    "LoopStructuralMCPServer",
    "Tool",
    "LoadModelInput",
    "SolveModelInput",
    "ExportModelInput",
    "GetModelInfoInput",
    "CreateFeatureInput",
    "AddObservationsInput",
]
