from typing import List, Optional, Literal
from pydantic import Field
from loop_common.base import LoopEntity


class Fault(GeologicalFeature):
    """Represents a displacement surface."""

    fault_type: Literal["normal", "reverse", "strike-slip", "unspecified"] = "unspecified"

    # The 'Engine' uses these to calculate the displacement field
    displacement: float = 0.0

    # Influence distance (how far from the fault the displacement reaches)
    buffer: float = 1000.0

    # Optional: For complex fault models (elliptical, etc.)
    model_type: str = "constant"


class Fold(GeologicalFeature):
    """Represents a folding event/geometry."""

    fold_type: str = "cylindrical"
    wavelength: Optional[float] = None
    amplitude: Optional[float] = None
