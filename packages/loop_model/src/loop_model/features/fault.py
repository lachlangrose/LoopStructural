from .base import GeologicalFeature
from typing import Any, Literal

from pydantic import Field


class Fault(GeologicalFeature):
    """Represents a stratigraphic layer or an intrusion."""

    name: str | None = None
    displacement: float | None = None
    build_strategy: Literal["fault_surface"] = "fault_surface"
    build_params: dict[str, Any] = Field(default_factory=dict)
