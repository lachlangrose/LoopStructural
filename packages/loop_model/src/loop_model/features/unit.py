from .base import GeologicalFeature
from typing import Literal


class GeologicalUnit(GeologicalFeature):
    """Represents a stratigraphic layer or an intrusion."""

    name: str
    unit_type: Literal["stratigraphy", "intrusion", "basement"] = "stratigraphy"
    order: int = 0
    is_stop_surface: bool = False


Unit = GeologicalUnit


