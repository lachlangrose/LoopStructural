from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import Id
from .topological_relations import (
    AngularUnconformityParams,
    DisconformityParams,
    ErosionParams,
    OnlapParams,
)


class Relation(BaseModel):
    kind: Literal[
        "overlies",
        "interfingers_with",
        "equivalent_to",
        "displaces",
        "folds",
        "erodes",
        "intrudes",
        "observes",
        "adjacent_to",
        "crosscuts",
        "splays_from",
        "relay_within",
        "represents",
        "uses_scalar",
    ]
    src: Id
    dst: Id
    attrs: Dict[str, Any] = Field(default_factory=dict)
    erosion_params: Optional[ErosionParams] = None
    angular_unconformity_params: Optional[AngularUnconformityParams] = None
    onlap_params: Optional[OnlapParams] = None
    disconformity_params: Optional[DisconformityParams] = None


class Event(BaseModel):
    id: Id
    feature: Id
    order: int
    scope: Dict[str, List[Id]] = Field(default_factory=dict)
