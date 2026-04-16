import numpy as np

from loop_common.base import LoopEntity


class PointSet(LoopEntity):
    """A set of XYZ points representing a contact or fault trace."""

    coords: np.ndarray  # Shape (3,) or (N, 3)
