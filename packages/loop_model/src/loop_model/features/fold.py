from .base import GeologicalFeatureSpec


class Fold(GeologicalFeatureSpec):
    """Represents a stratigraphic layer or an intrusion."""

    name: str | None = None
