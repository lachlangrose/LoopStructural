import numpy as np


class BoundingBox:
    def __init__(self, origin: np.ndarray, maximum: np.ndarray, scale: bool = False):
        self.origin = np.array(origin)
        self.maximum = np.array(maximum)
        self._extent = self.maximum - self.origin
        self._centre = self.origin + self._extent / 2
        self._scale = scale

    @property
    def local_origin(self) -> np.ndarray:
        return self.origin - self.origin

    @property
    def local_maximum(self) -> np.ndarray:

        return (self.maximum - self.origin) / self.scale_factor

    @property
    def scale_factor(self) -> float:
        if self._scale:
            return np.max(self._extent)
        else:
            return 1.0

    def scale(self, points: np.ndarray) -> np.ndarray:
        return (points - self.origin) / self.scale_factor

    def rescale(self, points: np.ndarray) -> np.ndarray:
        return points * self.scale_factor + self.origin
