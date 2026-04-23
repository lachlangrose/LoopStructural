from .base import GeologicalFeature
from typing import Any, Literal

from pydantic import Field


class GeologicalUnit(GeologicalFeature):
    """Represents a stratigraphic layer or an intrusion."""

    name: str
    unit_type: Literal["stratigraphy", "intrusion", "basement"] = "stratigraphy"
    build_strategy: Literal["independent_per_unit", "grouped_conformable_stack"] = (
        "independent_per_unit"
    )
    build_params: dict[str, Any] = Field(default_factory=dict)
    order: int = 0
    is_stop_surface: bool = False


Unit = GeologicalUnit
