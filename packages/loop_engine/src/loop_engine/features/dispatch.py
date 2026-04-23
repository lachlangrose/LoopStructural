from __future__ import annotations

from typing import Callable

import numpy as np
from loop_common.geometry import BoundingBox


BuilderFn = Callable[[dict, object], object | None]


class FeatureBuilderDispatcher:
    """Route task payloads to feature-specific build strategies."""

    def __init__(self):
        self._strategies: dict[tuple[str, str], BuilderFn] = {}

    @staticmethod
    def _normalize(text: str | None) -> str:
        if text is None:
            return ""
        return str(text).strip().lower()

    def register(self, feature_type: str, strategy: str, builder: BuilderFn) -> None:
        key = (self._normalize(feature_type), self._normalize(strategy))
        self._strategies[key] = builder

    def resolve(self, feature, payload_feature_type: str | None = None) -> BuilderFn:
        feature_type = type(feature).__name__ if feature is not None else payload_feature_type
        feature_type_key = self._normalize(feature_type) or "default"
        strategy_key = self._normalize(getattr(feature, "build_strategy", None)) or "default"

        for key in (
            (feature_type_key, strategy_key),
            (feature_type_key, "default"),
            ("default", "default"),
        ):
            builder = self._strategies.get(key)
            if builder is not None:
                return builder

        raise NotImplementedError(
            f"No builder strategy is registered for feature_type='{feature_type_key}' "
            f"strategy='{strategy_key}'."
        )

    def build(self, task_payload: dict, model) -> object | None:
        feature = task_payload.get("feature")
        linked_data = task_payload.get("linked_data")
        payload_feature_type = getattr(linked_data, "feature_type", None)
        builder = self.resolve(feature=feature, payload_feature_type=payload_feature_type)
        return builder(task_payload, model)


def build_generic_interpolator(task_payload: dict, model) -> object | None:
    """Generic interpolation build path used as the default strategy."""
    from loop_interpolation import InterpolatorBuilder

    linked_data = task_payload.get("linked_data")
    if linked_data is None:
        return None

    has_points = linked_data.point_constraints.shape[0] > 0
    has_gradients = linked_data.gradient_constraints.shape[0] > 0
    has_tangents = linked_data.tangent_constraints.shape[0] > 0

    if not (has_points or has_gradients or has_tangents):
        return None

    bounding_box = getattr(model.schema, "bounding_box", None)
    if bounding_box is not None and not getattr(bounding_box, "valid", False):
        bounding_box = _infer_fallback_bounding_box(model, linked_data)
    builder = InterpolatorBuilder(
        interpolatortype=model.interpolatortype,
        bounding_box=bounding_box,
        nelements=model.nelements,
    )

    if has_points:
        value_constraints = np.hstack(
            [
                linked_data.point_constraints,
                np.zeros((linked_data.point_constraints.shape[0], 1)),
            ]
        )
        builder.add_value_constraints(value_constraints)

    if has_gradients:
        builder.add_normal_constraints(linked_data.gradient_constraints)

    if has_tangents:
        builder.add_tangent_constraints(linked_data.tangent_constraints)

    builder.setup_interpolator().solve()
    return builder.build()


def _as_nx3(values) -> np.ndarray | None:
    if values is None:
        return None
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        if arr.shape[0] != 3:
            return None
        arr = arr.reshape(1, 3)
    if arr.ndim != 2 or arr.shape[1] != 3:
        return None
    return arr


def _infer_fallback_bounding_box(model, linked_data) -> BoundingBox | None:
    coordinate_blocks: list[np.ndarray] = []

    project = getattr(model.schema, "project", None)
    observations = getattr(project, "observations", {}) if project is not None else {}
    for observation in observations.values():
        vertices = _as_nx3(getattr(observation, "vertices", None))
        if vertices is not None:
            coordinate_blocks.append(vertices)
            continue
        coords = _as_nx3(getattr(observation, "coords", None))
        if coords is not None:
            coordinate_blocks.append(coords)

    # Ensure the current task's already-linked coordinates are included.
    if linked_data.point_constraints.shape[0] > 0:
        coordinate_blocks.append(linked_data.point_constraints)
    if linked_data.gradient_constraints.shape[0] > 0:
        coordinate_blocks.append(linked_data.gradient_constraints[:, :3])
    if linked_data.tangent_constraints.shape[0] > 0:
        coordinate_blocks.append(linked_data.tangent_constraints[:, :3])

    if not coordinate_blocks:
        return None

    coordinates = np.vstack(coordinate_blocks)
    origin = coordinates.min(axis=0)
    maximum = coordinates.max(axis=0)

    axis_extent = maximum - origin
    collapsed_axes = axis_extent <= 1e-9
    if np.any(collapsed_axes):
        maximum = maximum.copy()
        maximum[collapsed_axes] = origin[collapsed_axes] + 1.0
        axis_extent = maximum - origin

    # Add a small buffer to reduce edge clipping in interpolator support setup.
    buffer = np.maximum(axis_extent * 0.05, 1e-3)
    return BoundingBox(origin=origin - buffer, maximum=maximum + buffer)


def build_unit_independent(task_payload: dict, model) -> object | None:
    """Unit strategy: solve each unit as an independent scalar field."""
    return build_generic_interpolator(task_payload, model)


def build_unit_grouped(task_payload: dict, model) -> object | None:
    """Planned grouped conformable stratigraphy strategy."""
    feature = task_payload.get("feature")
    feature_name = getattr(feature, "name", "<unknown>")
    raise NotImplementedError(
        "Stratigraphy strategy 'grouped_conformable_stack' is not implemented yet "
        f"for feature '{feature_name}'."
    )


def build_fault_surface(task_payload: dict, model) -> object | None:
    """Fault strategy placeholder using current generic interpolation path."""
    return build_generic_interpolator(task_payload, model)


def create_default_feature_builder_dispatcher() -> FeatureBuilderDispatcher:
    dispatcher = FeatureBuilderDispatcher()
    dispatcher.register("default", "default", build_generic_interpolator)

    # GeologicalUnit/Unit aliases.
    dispatcher.register("geologicalunit", "independent_per_unit", build_unit_independent)
    dispatcher.register("geologicalunit", "grouped_conformable_stack", build_unit_grouped)
    dispatcher.register("unit", "independent_per_unit", build_unit_independent)
    dispatcher.register("unit", "grouped_conformable_stack", build_unit_grouped)

    dispatcher.register("fault", "fault_surface", build_fault_surface)
    return dispatcher
