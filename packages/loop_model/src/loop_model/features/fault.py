from .base import GeologicalFeature


class Fault(GeologicalFeature):
    """Represents a stratigraphic layer or an intrusion."""

    name: str | None = None
    displacement: float | None = None
    