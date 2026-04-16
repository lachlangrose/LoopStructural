from .base import GeologicalFeature


class Fold(GeologicalFeature):
    """Represents a stratigraphic layer or an intrusion."""

    name: str | None = None
