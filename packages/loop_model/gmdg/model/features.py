from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field, model_validator

from .common import Id
from .scalar_sources import ScalarSource


class Feature(BaseModel):
    id: Id
    name: str
    type: Literal["unit", "fault", "fold", "unconformity", "intrusion", "region", "scalar_feature"]
    tags: List[str] = Field(default_factory=list)
    attrs: Dict[str, Any] = Field(default_factory=dict)
    age: Optional[Tuple[float, float]] = None
    observation_ids: List[Id] = Field(default_factory=list)


class ScalarFeature(Feature):
    type: Literal["scalar_feature"] = "scalar_feature"
    role: Literal[
        "stratigraphic",
        "axial_surface",
        "fold_frame",
        "fault_indicator",
        "unconformity_surface",
        "custom",
    ] = "custom"
    source: ScalarSource
    hints: Dict[str, Any] = Field(default_factory=dict)


class UnitRepresentation(BaseModel):
    scalar_feature_id: Id
    isovalue: Optional[Union[float, str]] = None
    interval: Optional[Tuple[float, float]] = None
    polarity: Optional[Literal["inside_if_less", "inside_if_greater"]] = None
    membership_function: Optional[str] = None


class Unit(Feature):
    type: Literal["unit"] = "unit"
    lithology: Optional[str] = None
    representation: Optional[UnitRepresentation] = None


class Fault(Feature):
    type: Literal["fault"] = "fault"
    sense: Optional[Literal["normal", "reverse", "strike-slip", "oblique"]] = None
    throw_prior: Optional[Dict[str, float]] = None
    indicator_scalar_id: Optional[Id] = None


class Fold(Feature):
    type: Literal["fold"] = "fold"
    axis: Optional[Tuple[float, float, float]] = None
    plunge: Optional[float] = None
    wavelength: Optional[float] = None
    frame_scalar_ids: List[Id] = Field(default_factory=list)


class Unconformity(Feature):
    type: Literal["unconformity"] = "unconformity"
    unconformity_type: Literal["erosional", "angular", "onlap", "disconformity"] = "erosional"
    # Deprecated compatibility alias.
    kind: Optional[Literal["erosional", "angular", "onlap", "disconformity"]] = None
    scalar_feature_id: Optional[Id] = None
    geometry_params: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sync_kind_alias(self) -> "Unconformity":
        if self.kind is not None:
            self.unconformity_type = self.kind
        self.kind = self.unconformity_type
        return self


class Intrusion(Feature):
    type: Literal["intrusion"] = "intrusion"


class Region(Feature):
    type: Literal["region"] = "region"
    geometry: Dict[str, Any] = Field(default_factory=dict)


FeatureNode = Annotated[
    Union[Unit, Fault, Fold, Unconformity, Intrusion, Region, ScalarFeature],
    Field(discriminator="type"),
]
