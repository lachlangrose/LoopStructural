from .base import GeologicalFeature
from typing import Literal


class GeologicalUnit(GeologicalFeature):
    """Represents a stratigraphic layer or an intrusion."""

    unit_type: Literal["stratigraphy", "intrusion", "basement"] = "stratigraphy"

    # Relative age: lower numbers are usually younger (top-down)
    order: int = 0

    # For unconformities or intrusive contacts
    is_stop_surface: bool = False
