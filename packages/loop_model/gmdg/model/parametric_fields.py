from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class BaseParametricFieldParams(BaseModel):
    coordinate_system: str = "cartesian"
    units: Optional[str] = None


class FlatFieldParams(BaseParametricFieldParams):
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    amplitude: float = 1.0

    @field_validator("amplitude")
    @classmethod
    def _validate_amplitude(cls, value: float) -> float:
        if value == 0:
            raise ValueError("Flat field amplitude must be non-zero")
        return value

    @field_validator("normal")
    @classmethod
    def _validate_normal(cls, value: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if abs(value[0]) + abs(value[1]) + abs(value[2]) == 0:
            raise ValueError("Flat field normal must be non-zero")
        return value


class FoldedFieldParams(BaseParametricFieldParams):
    wavelength: float
    amplitude: float
    axis: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    plunge: float = 0.0
    phase: float = 0.0

    @field_validator("wavelength")
    @classmethod
    def _validate_wavelength(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Folded field wavelength must be > 0")
        return value

    @field_validator("axis")
    @classmethod
    def _validate_axis(cls, value: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if abs(value[0]) + abs(value[1]) + abs(value[2]) == 0:
            raise ValueError("Folded field axis must be non-zero")
        return value


class VariogramFieldParams(BaseParametricFieldParams):
    base_value: float = 0.0
    nugget: float = 0.0
    sill: float = 1.0
    range: float = Field(default=100.0, alias="range_")
    model_type: Literal["exponential", "spherical", "gaussian", "linear"] = "spherical"
    direction_vector: Tuple[float, float, float] = (1.0, 0.0, 0.0)

    model_config = {
        "populate_by_name": True,
    }

    @field_validator("nugget")
    @classmethod
    def _validate_nugget(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Variogram nugget must be >= 0")
        return value

    @field_validator("sill")
    @classmethod
    def _validate_sill(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Variogram sill must be > 0")
        return value

    @field_validator("range")
    @classmethod
    def _validate_range(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Variogram range must be > 0")
        return value

    @field_validator("direction_vector")
    @classmethod
    def _validate_direction_vector(cls, value: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if abs(value[0]) + abs(value[1]) + abs(value[2]) == 0:
            raise ValueError("Variogram direction_vector must be non-zero")
        return value

    @field_validator("sill")
    @classmethod
    def _validate_sill_vs_nugget(cls, value: float, info) -> float:
        nugget = info.data.get("nugget")
        if nugget is not None and value < nugget:
            raise ValueError("Variogram sill must be >= nugget")
        return value
