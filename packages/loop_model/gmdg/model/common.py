from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import BaseModel, Field

Id = str


class ModelSpace(BaseModel):
    crs: str
    bbox: Tuple[float, float, float, float, float, float]
    units: Literal["m"] = "m"


class UncertaintySpec(BaseModel):
    kind: Literal["constant", "column", "expression", "function"] = "constant"
    value: Optional[float] = None
    column: Optional[str] = None
    expression: Optional[str] = None
    function: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
