from typing import Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from loop_common.base import NumpyArray


class BaseConstraint(BaseModel):
    """Base pydantic model for interpolation constraints."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True, extra="forbid")


def _weights_to_column(weights: Union[float, np.ndarray], n_rows: int) -> np.ndarray:
    if n_rows == 0:
        return np.empty((0, 1), dtype=float)
    if np.isscalar(weights):
        return np.full((n_rows, 1), float(weights), dtype=float)

    arr = np.asarray(weights, dtype=float)
    if arr.ndim != 1 or arr.shape[0] != n_rows:
        raise ValueError(f"Weights must be scalar or shape ({n_rows},), got {arr.shape}")
    return arr.reshape(-1, 1)


class ValueConstraint(BaseConstraint):
    points: NumpyArray = Field(default_factory=lambda: np.empty((0, 3), dtype=float))
    values: NumpyArray = Field(default_factory=lambda: np.empty((0,), dtype=float))
    weights: Union[float, NumpyArray] = 1.0

    @model_validator(mode="after")
    def check_shapes(self):
        if self.points.ndim != 2:
            raise ValueError("points must have shape (N, D)")
        if self.values.ndim != 1:
            raise ValueError("values must have shape (N,)")
        if self.points.shape[0] != self.values.shape[0]:
            raise ValueError("points and values must contain the same number of rows")
        if not np.isscalar(self.weights):
            w = np.asarray(self.weights)
            if w.ndim != 1 or w.shape[0] != self.points.shape[0]:
                raise ValueError("weights must be scalar or shape (N,)")
        return self

    def to_array(self) -> np.ndarray:
        n_rows = self.points.shape[0]
        weights = _weights_to_column(self.weights, n_rows)
        return np.hstack([self.points, self.values.reshape(-1, 1), weights])

    @classmethod
    def from_array(cls, points: np.ndarray, dimensions: int = 3) -> "ValueConstraint":
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2:
            raise ValueError("Value constraint array must be 2D")
        if pts.shape[1] == dimensions + 1:
            return cls(points=pts[:, :dimensions], values=pts[:, dimensions], weights=1.0)
        if pts.shape[1] == dimensions + 2:
            return cls(
                points=pts[:, :dimensions],
                values=pts[:, dimensions],
                weights=pts[:, dimensions + 1],
            )
        raise ValueError(
            f"Value constraint array must have {dimensions + 1} or {dimensions + 2} columns"
        )


class GradientConstraint(BaseConstraint):
    points: NumpyArray = Field(default_factory=lambda: np.empty((0, 3), dtype=float))
    vectors: NumpyArray = Field(default_factory=lambda: np.empty((0, 3), dtype=float))
    weights: Union[float, NumpyArray] = 1.0
    is_normal: bool = False

    @model_validator(mode="after")
    def check_shapes(self):
        if self.points.ndim != 2:
            raise ValueError("points must have shape (N, D)")
        if self.vectors.ndim != 2:
            raise ValueError("vectors must have shape (N, D)")
        if self.points.shape != self.vectors.shape:
            raise ValueError("points and vectors must have matching shape")
        if not np.isscalar(self.weights):
            w = np.asarray(self.weights)
            if w.ndim != 1 or w.shape[0] != self.points.shape[0]:
                raise ValueError("weights must be scalar or shape (N,)")
        return self

    def to_array(self) -> np.ndarray:
        n_rows = self.points.shape[0]
        weights = _weights_to_column(self.weights, n_rows)
        return np.hstack([self.points, self.vectors, weights])

    @classmethod
    def from_array(
        cls, points: np.ndarray, dimensions: int = 3, is_normal: bool = False
    ) -> "GradientConstraint":
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2:
            raise ValueError("Gradient constraint array must be 2D")
        if pts.shape[1] == dimensions * 2:
            return cls(
                points=pts[:, :dimensions],
                vectors=pts[:, dimensions : 2 * dimensions],
                weights=1.0,
                is_normal=is_normal,
            )
        if pts.shape[1] == dimensions * 2 + 1:
            return cls(
                points=pts[:, :dimensions],
                vectors=pts[:, dimensions : 2 * dimensions],
                weights=pts[:, 2 * dimensions],
                is_normal=is_normal,
            )
        raise ValueError(
            "Gradient constraint array must have "
            f"{dimensions * 2} or {dimensions * 2 + 1} columns"
        )


class InequalityConstraint(BaseConstraint):
    points: NumpyArray = Field(default_factory=lambda: np.empty((0, 3), dtype=float))
    bounds: NumpyArray = Field(default_factory=lambda: np.empty((0, 2), dtype=float))
    weights: Union[float, NumpyArray] = 1.0

    @model_validator(mode="after")
    def check_shapes(self):
        if self.points.ndim != 2:
            raise ValueError("points must have shape (N, D)")
        if self.bounds.ndim != 2 or self.bounds.shape[1] != 2:
            raise ValueError("bounds must have shape (N, 2)")
        if self.points.shape[0] != self.bounds.shape[0]:
            raise ValueError("points and bounds must contain the same number of rows")
        if not np.isscalar(self.weights):
            w = np.asarray(self.weights)
            if w.ndim != 1 or w.shape[0] != self.points.shape[0]:
                raise ValueError("weights must be scalar or shape (N,)")
        return self

    def to_array(self) -> np.ndarray:
        n_rows = self.points.shape[0]
        weights = _weights_to_column(self.weights, n_rows)
        return np.hstack([self.points, self.bounds, weights])

    @classmethod
    def from_array(cls, points: np.ndarray, dimensions: int = 3) -> "InequalityConstraint":
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2:
            raise ValueError("Inequality constraint array must be 2D")
        if pts.shape[1] == dimensions + 2:
            return cls(points=pts[:, :dimensions], bounds=pts[:, dimensions : dimensions + 2])
        if pts.shape[1] == dimensions + 3:
            return cls(
                points=pts[:, :dimensions],
                bounds=pts[:, dimensions : dimensions + 2],
                weights=pts[:, dimensions + 2],
            )
        raise ValueError(
            "Inequality constraint array must have "
            f"{dimensions + 2} or {dimensions + 3} columns"
        )


class InequalityPair(BaseConstraint):
    """Represents pairwise ordering rows [x, y, z, pair_id, weight?]."""

    points: NumpyArray = Field(default_factory=lambda: np.empty((0, 3), dtype=float))
    pair_ids: NumpyArray = Field(default_factory=lambda: np.empty((0,), dtype=float))
    weights: Union[float, NumpyArray] = 1.0

    @model_validator(mode="after")
    def check_shapes(self):
        if self.points.ndim != 2:
            raise ValueError("points must have shape (N, D)")
        if self.pair_ids.ndim != 1:
            raise ValueError("pair_ids must have shape (N,)")
        if self.points.shape[0] != self.pair_ids.shape[0]:
            raise ValueError("points and pair_ids must contain the same number of rows")
        if not np.isscalar(self.weights):
            w = np.asarray(self.weights)
            if w.ndim != 1 or w.shape[0] != self.points.shape[0]:
                raise ValueError("weights must be scalar or shape (N,)")
        return self

    def to_array(self) -> np.ndarray:
        n_rows = self.points.shape[0]
        weights = _weights_to_column(self.weights, n_rows)
        return np.hstack([self.points, self.pair_ids.reshape(-1, 1), weights])

    @classmethod
    def from_array(cls, points: np.ndarray, dimensions: int = 3) -> "InequalityPair":
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2:
            raise ValueError("Inequality pair constraint array must be 2D")
        if pts.shape[1] == dimensions + 1:
            return cls(points=pts[:, :dimensions], pair_ids=pts[:, dimensions], weights=1.0)
        if pts.shape[1] == dimensions + 2:
            return cls(
                points=pts[:, :dimensions],
                pair_ids=pts[:, dimensions],
                weights=pts[:, dimensions + 1],
            )
        raise ValueError(
            "Inequality pair array must have "
            f"{dimensions + 1} or {dimensions + 2} columns"
        )


class InterfaceConstraint(BaseConstraint):
    points: NumpyArray = Field(default_factory=lambda: np.empty((0, 3), dtype=float))
    interface_ids: NumpyArray = Field(default_factory=lambda: np.empty((0,), dtype=float))
    weights: Union[float, NumpyArray] = 1.0

    @model_validator(mode="after")
    def check_shapes(self):
        if self.points.ndim != 2:
            raise ValueError("points must have shape (N, D)")
        if self.interface_ids.ndim != 1:
            raise ValueError("interface_ids must have shape (N,)")
        if self.points.shape[0] != self.interface_ids.shape[0]:
            raise ValueError("points and interface_ids must contain the same number of rows")
        if not np.isscalar(self.weights):
            w = np.asarray(self.weights)
            if w.ndim != 1 or w.shape[0] != self.points.shape[0]:
                raise ValueError("weights must be scalar or shape (N,)")
        return self

    def to_array(self) -> np.ndarray:
        n_rows = self.points.shape[0]
        weights = _weights_to_column(self.weights, n_rows)
        return np.hstack([self.points, self.interface_ids.reshape(-1, 1), weights])

    @classmethod
    def from_array(cls, points: np.ndarray, dimensions: int = 3) -> "InterfaceConstraint":
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2:
            raise ValueError("Interface constraint array must be 2D")
        if pts.shape[1] == dimensions + 1:
            return cls(points=pts[:, :dimensions], interface_ids=pts[:, dimensions], weights=1.0)
        if pts.shape[1] == dimensions + 2:
            return cls(
                points=pts[:, :dimensions],
                interface_ids=pts[:, dimensions],
                weights=pts[:, dimensions + 1],
            )
        raise ValueError(
            "Interface constraint array must have "
            f"{dimensions + 1} or {dimensions + 2} columns"
        )
