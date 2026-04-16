from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import BaseModel, field_validator


class ErosionParams(BaseModel):
    depth_range: Optional[Tuple[float, float]] = None
    style: Literal["truncation", "beveling", "scour"] = "truncation"
    dip_angle: Optional[float] = None

    @field_validator("depth_range")
    @classmethod
    def _validate_depth_range(cls, value: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
        if value is None:
            return None
        if value[0] > value[1]:
            raise ValueError("Erosion depth_range must be (min_depth, max_depth)")
        return value

    @field_validator("dip_angle")
    @classmethod
    def _validate_dip_angle(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if not (0.0 <= value <= 90.0):
            raise ValueError("Erosion dip_angle must be in [0, 90]")
        return value


class AngularUnconformityParams(BaseModel):
    angle_degrees: float
    younging_direction: Literal["up", "down"] = "up"
    tilt_phase: Literal["pre", "post"] = "post"

    @field_validator("angle_degrees")
    @classmethod
    def _validate_angle(cls, value: float) -> float:
        if not (0.0 <= value <= 180.0):
            raise ValueError("Angular unconformity angle must be in [0, 180]")
        return value


class OnlapParams(BaseModel):
    dip_angle: float
    depth_to_onlap: Optional[float] = None

    @field_validator("dip_angle")
    @classmethod
    def _validate_dip_angle(cls, value: float) -> float:
        if not (0.0 <= value <= 90.0):
            raise ValueError("Onlap dip_angle must be in [0, 90]")
        return value


class DisconformityParams(BaseModel):
    parallel_tolerance_degrees: float = 10.0
    missing_section: Optional[str] = None

    @field_validator("parallel_tolerance_degrees")
    @classmethod
    def _validate_tolerance(cls, value: float) -> float:
        if not (0.0 <= value <= 90.0):
            raise ValueError("Disconformity parallel_tolerance_degrees must be in [0, 90]")
        return value
