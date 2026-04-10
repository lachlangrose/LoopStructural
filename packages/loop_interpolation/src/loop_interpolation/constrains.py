import numpy as np
from typing import Union
from dataclasses import dataclass, field
from abc import ABC


class BaseConstraint(ABC):
    pass


@dataclass(frozen=True)
class ValueConstraint(BaseConstraint):
    points: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))  # Shape (N, 3)
    values: np.ndarray = field(default_factory=lambda: np.empty((0,)))  # Shape (N,)
    weights: Union[float, np.ndarray] = 1.0  # Shape (N,) or scalar


@dataclass(frozen=True)
class GradientConstraint(BaseConstraint):
    points: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))  # Shape (N, 3)
    vectors: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))  # Shape (N, 3)
    weights: Union[float, np.ndarray] = 1.0  # Shape (N,) or scalar
    is_normal: bool = False


@dataclass(frozen=True)
class InequalityConstraint(BaseConstraint):
    points: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))  # Shape (N, 3)
    bounds: np.ndarray = field(default_factory=lambda: np.empty((0, 2)))  # Shape (N, 2)
    weights: Union[float, np.ndarray] = 1.0  # Shape (N,) or scalar


@dataclass(frozen=True)
class InequalityPair(BaseConstraint):
    point_a: np.ndarray = field(default_factory=lambda: np.empty((3,)))  # Shape (3,)
    point_b: np.ndarray = field(default_factory=lambda: np.empty((3,)))  # Shape (3,)
    weight: float = 1.0


@dataclass(frozen=True)
class InterfaceConstraint(BaseConstraint):
    points: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))  # Shape (N, 3)
    value: float = 0.0
    weights: Union[float, np.ndarray] = 1.0  # Shape (N,) or scalar
