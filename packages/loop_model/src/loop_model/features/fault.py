from .base import GeologicalFeatureSpec
from typing import Any

from pydantic import Field


class Fault(GeologicalFeatureSpec):
    """Represents a fault in the geological model."""

    name: str | None = None
    displacement: float | None = None
    build_params: dict[str, Any] = Field(default_factory=dict)
