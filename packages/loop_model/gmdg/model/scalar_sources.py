from __future__ import annotations

from typing import Annotated, Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from .parametric_fields import FlatFieldParams, FoldedFieldParams, VariogramFieldParams


class ParametricScalarSource(BaseModel):
    kind: Literal["parametric"] = "parametric"
    field_type: Literal["flat", "folded", "variogram"] = "flat"
    params: Union[FlatFieldParams, FoldedFieldParams, VariogramFieldParams] = Field(
        default_factory=FlatFieldParams
    )
    # Deprecated compatibility fields retained for legacy payloads.
    function: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    gradient_function: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_parametric_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        has_new_shape = "field_type" in data or "params" in data
        if has_new_shape:
            return data

        has_function_key = "function" in data
        function = (data.get("function") or "").strip()
        if has_function_key and not function:
            raise ValueError("Parametric scalar source function must be non-empty when provided")
        parameters = data.get("parameters") or {}
        migrated: Dict[str, Any] = dict(data)

        if "field_type" not in migrated:
            migrated["field_type"] = "flat"

        if "params" not in migrated:
            params: Dict[str, Any] = {
                "origin": parameters.get("origin", (0.0, 0.0, 0.0)),
                "normal": parameters.get("normal", (0.0, 0.0, 1.0)),
                "amplitude": parameters.get("amplitude", 1.0),
            }

            if function.lower().replace(" ", "") == "z":
                params["normal"] = (0.0, 0.0, 1.0)

            migrated["params"] = params

        return migrated


class InterpolatedScalarSource(BaseModel):
    kind: Literal["interpolated"] = "interpolated"
    method: str
    constraints: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ExternalScalarSource(BaseModel):
    kind: Literal["external"] = "external"
    uri: str
    adapter: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


ScalarSource = Annotated[
    Union[ParametricScalarSource, InterpolatedScalarSource, ExternalScalarSource],
    Field(discriminator="kind"),
]
