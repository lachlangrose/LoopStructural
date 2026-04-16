from loop_common.interfaces.representation import BaseRepresentation

import numpy as np


class GeologicalFeature:
    def __init__(self, name, representation: BaseRepresentation):
        self.name = name
        self.representation = representation

    def evaluate_value(self, position: np.ndarray):
        return self.representation.evaluate_value(position)

    def evaluate_gradient(self, position: np.ndarray):
        return self.representation.evaluate_gradient(position)

    def min(self):
        return self.representation.min()

    def max(self):
        return self.representation.max()

    def surfaces(self, value):
        return self.representation.surfaces(value)
