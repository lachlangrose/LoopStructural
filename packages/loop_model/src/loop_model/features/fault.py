from .base import GeologicalFeature
from typing import Any

from pydantic import Field


class Fault(GeologicalFeature):
    """Represents a fault in the geological model."""

    name: str | None = None
    displacement: float | None = None
    build_params: dict[str, Any] = Field(default_factory=dict)
