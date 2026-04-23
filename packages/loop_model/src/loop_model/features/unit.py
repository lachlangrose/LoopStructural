from .base import GeologicalFeature
from typing import Any, Literal

from pydantic import Field


class GeologicalUnit(GeologicalFeature):
    """Represents a stratigraphic layer or an intrusion."""

    name: str
    unit_type: Literal["stratigraphy", "intrusion", "basement"] = "stratigraphy"
    thickness: float | None = None
    build_params: dict[str, Any] = Field(default_factory=dict)


Unit = GeologicalUnit
