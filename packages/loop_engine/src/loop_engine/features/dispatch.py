from __future__ import annotations

from .basebuilder import BaseBuilder
from .fault import FaultBuilder
from .stratigraphy import StratigraphyBuilder


class FeatureBuilderDispatcher:
    """Route task payloads to class-based feature builders."""

    def __init__(self, model):
        self.model = model
        self.generic_builder = BaseBuilder(model)
        self.stratigraphy_builder = StratigraphyBuilder(model)
        self.fault_builder = FaultBuilder(model)

    @staticmethod
    def _normalize_feature_type(feature, payload_feature_type: str | None = None) -> str:
        if feature is not None:
            return type(feature).__name__.strip().lower()
        if payload_feature_type is not None:
            return str(payload_feature_type).strip().lower()
        return ""

    def build(self, task_payload: dict) -> object | None:
        feature = task_payload.get("feature")
        linked_data = task_payload.get("linked_data")
        payload_feature_type = getattr(linked_data, "feature_type", None)
        feature_type = self._normalize_feature_type(feature, payload_feature_type)

        if feature_type in {"unit", "geologicalunit"}:
            return self.stratigraphy_builder.build(task_payload)
        if feature_type == "fault":
            return self.fault_builder.build(task_payload)
        return self.generic_builder.build(task_payload)


def create_default_feature_builder_dispatcher(model) -> FeatureBuilderDispatcher:
    return FeatureBuilderDispatcher(model)
