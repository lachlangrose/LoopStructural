from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loop_common.geometry import BoundingBox


@dataclass
class MergedLinkedInput:
    feature_id: str
    feature_name: str | None
    feature_type: str
    point_constraints: np.ndarray
    gradient_constraints: np.ndarray
    tangent_constraints: np.ndarray
    by_role: dict
    missing_observation_ids: list[str]


@dataclass
class PreparedConstraints:
    value_constraints: np.ndarray
    normal_constraints: np.ndarray
    tangent_constraints: np.ndarray


class BaseBuilder:
    """Base builder with common interpolation and data-extraction utilities."""

    def __init__(self, model):
        self.model = model

    def build(self, task_payload: dict) -> object | None:
        linked_data = task_payload.get("linked_data")
        feature = task_payload.get("feature")
        build_params = getattr(feature, "build_params", {}) or {}
        prepared = self.prepare_constraints(linked_data)
        return self.build_from_constraints(
            linked_data=linked_data,
            prepared=prepared,
            build_params=build_params,
        )

    def build_from_linked_data(self, linked_data) -> object | None:
        prepared = self.prepare_constraints(linked_data)
        return self.build_from_constraints(
            linked_data=linked_data,
            prepared=prepared,
            build_params={},
        )

    def prepare_constraints(self, linked_data) -> PreparedConstraints:
        if linked_data is None:
            return PreparedConstraints(
                value_constraints=np.empty((0, 4), dtype=float),
                normal_constraints=np.empty((0, 6), dtype=float),
                tangent_constraints=np.empty((0, 6), dtype=float),
            )

        if linked_data.point_constraints.shape[0] > 0:
            value_constraints = np.hstack(
                [
                    linked_data.point_constraints,
                    np.zeros((linked_data.point_constraints.shape[0], 1)),
                ]
            )
        else:
            value_constraints = np.empty((0, 4), dtype=float)

        normal_constraints = self._normalize_xyz_vectors(linked_data.gradient_constraints)
        tangent_constraints = self._normalize_xyz_vectors(linked_data.tangent_constraints)

        return PreparedConstraints(
            value_constraints=value_constraints,
            normal_constraints=normal_constraints,
            tangent_constraints=tangent_constraints,
        )

    def build_from_constraints(
        self,
        linked_data,
        prepared: PreparedConstraints,
        build_params: dict,
    ) -> object | None:
        from loop_interpolation import InterpolatorBuilder

        if (
            prepared.value_constraints.shape[0] == 0
            and prepared.normal_constraints.shape[0] == 0
            and prepared.tangent_constraints.shape[0] == 0
        ):
            return None

        builder = InterpolatorBuilder(
            interpolatortype=self.model.interpolatortype,
            bounding_box=self._resolve_bounding_box(linked_data),
            nelements=self.model.nelements,
        )
        self.configure_builder(builder, build_params)

        if prepared.value_constraints.shape[0] > 0:
            builder.add_value_constraints(prepared.value_constraints)
        if prepared.normal_constraints.shape[0] > 0:
            builder.add_normal_constraints(prepared.normal_constraints)
        if prepared.tangent_constraints.shape[0] > 0:
            builder.add_tangent_constraints(prepared.tangent_constraints)

        self.apply_optional_constraints(builder, linked_data)

        builder.setup_interpolator()
        tol = build_params.get("tol")
        if tol is None:
            builder.solve()
        else:
            builder.solve(tol=tol)
        return builder.build()

    def configure_builder(self, builder, build_params: dict) -> None:
        solver = build_params.get("solver")
        solver_kwargs = build_params.get("solver_kwargs", {})
        if solver is not None:
            builder.use_solver(solver, **solver_kwargs)

        if "use_regularisation_weight_scale" in build_params:
            builder.use_regularisation_weight_scale(
                bool(build_params.get("use_regularisation_weight_scale"))
            )
        if "regularisation_weight_sigma" in build_params:
            builder.regularisation_weight_sigma(
                float(build_params.get("regularisation_weight_sigma"))
            )

    @staticmethod
    def apply_optional_constraints(builder, linked_data) -> None:
        if linked_data is None:
            return
        inequality_constraints = getattr(linked_data, "inequality_constraints", None)
        if inequality_constraints is not None and len(inequality_constraints) > 0:
            builder.add_inequality_constraints(inequality_constraints)
        inequality_pair_constraints = getattr(linked_data, "inequality_pair_constraints", None)
        if inequality_pair_constraints is not None and len(inequality_pair_constraints) > 0:
            builder.add_inequality_pair_constraints(inequality_pair_constraints)

    @staticmethod
    def _normalize_xyz_vectors(rows: np.ndarray) -> np.ndarray:
        if rows is None or rows.shape[0] == 0:
            return np.empty((0, 6), dtype=float)
        coords = rows[:, :3]
        vectors = rows[:, 3:6]
        norms = np.linalg.norm(vectors, axis=1)
        valid = norms > 1e-12
        if not np.any(valid):
            return np.empty((0, 6), dtype=float)
        normalized = vectors[valid] / norms[valid][:, np.newaxis]
        return np.hstack([coords[valid], normalized])

    def _resolve_bounding_box(self, linked_data):
        bounding_box = getattr(self.model.schema, "bounding_box", None)
        if bounding_box is not None and not getattr(bounding_box, "valid", False):
            return self._infer_fallback_bounding_box(linked_data)
        return bounding_box

    def _infer_fallback_bounding_box(self, linked_data) -> BoundingBox | None:
        coordinate_blocks: list[np.ndarray] = []

        project = getattr(self.model.schema, "project", None)
        observations = getattr(project, "observations", {}) if project is not None else {}
        for observation in observations.values():
            vertices = self.as_nx3(getattr(observation, "vertices", None))
            if vertices is not None:
                coordinate_blocks.append(vertices)
                continue
            coords = self.as_nx3(getattr(observation, "coords", None))
            if coords is not None:
                coordinate_blocks.append(coords)

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

        buffer = np.maximum(axis_extent * 0.05, 1e-3)
        return BoundingBox(origin=origin - buffer, maximum=maximum + buffer)

    @staticmethod
    def as_nx3(values) -> np.ndarray | None:
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

    @classmethod
    def coords_from_linked_observations(cls, linked_observations) -> np.ndarray:
        blocks: list[np.ndarray] = []
        for linked in linked_observations:
            observation = getattr(linked, "observation", None)
            if observation is None:
                continue
            vertices = cls.as_nx3(getattr(observation, "vertices", None))
            if vertices is not None:
                blocks.append(vertices)
                continue
            coords = cls.as_nx3(getattr(observation, "coords", None))
            if coords is not None:
                blocks.append(coords)

        if not blocks:
            return np.empty((0, 3), dtype=float)
        return np.vstack(blocks)

    @classmethod
    def coords_vectors_from_linked_observations(cls, linked_observations) -> np.ndarray:
        blocks: list[np.ndarray] = []
        for linked in linked_observations:
            observation = getattr(linked, "observation", None)
            if observation is None:
                continue
            coords = cls.as_nx3(getattr(observation, "coords", None))
            vectors = cls.as_nx3(getattr(observation, "vector", None))
            if coords is None or vectors is None:
                continue
            if coords.shape[0] != vectors.shape[0]:
                continue
            blocks.append(np.hstack([coords, vectors]))

        if not blocks:
            return np.empty((0, 6), dtype=float)
        return np.vstack(blocks)

    @staticmethod
    def normalize_relation(value) -> str:
        text = "" if value is None else str(value).strip().lower()
        if text.startswith("relationtype."):
            return text.split(".", 1)[1]
        return text
