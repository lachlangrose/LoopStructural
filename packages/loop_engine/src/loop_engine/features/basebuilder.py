from __future__ import annotations

from dataclasses import dataclass
from abc import ABC, abstractmethod
import numpy as np
from loop_common.geometry import BoundingBox
from loop_interpolation.constraints import GradientConstraint, ValueConstraint, InequalityConstraint, InequalityPair

@dataclass
class MergedLinkedInput:
    feature_id: str
    feature_name: str | None
    feature_type: str
    by_role: dict
    missing_observation_ids: list[str]


@dataclass
class PreparedConstraints:
    value_constraints: ValueConstraint
    gradient_constraints: GradientConstraint
    normal_constraints: GradientConstraint
    tangent_constraints: GradientConstraint
    inequality_constraints: InequalityConstraint
    inequality_pair_constraints: InequalityPair

class BaseBuilder(ABC):
    """Base builder with common interpolation and data-extraction utilities."""

    def __init__(self, model):
        self.model = model

    def build(self, task_payload: dict) -> object | None:
        linked_data = task_payload.get("linked_data")
        feature = task_payload.get("feature")
        build_params = getattr(feature, "build_params", {}) or {}
        prepared = self.prepare_constraints(linked_data, build_params)
        return self.build_from_constraints(
            linked_data=linked_data,
            prepared=prepared,
            build_params=build_params,
        )

    def build_from_linked_data(self, linked_data) -> object | None:
        prepared = self.prepare_constraints(linked_data, {})
        return self.build_from_constraints(
            linked_data=linked_data,
            prepared=prepared,
            build_params={},
        )
    @abstractmethod
    def prepare_constraints(self, linked_data, build_params: dict | None = None) -> PreparedConstraints:
        raise NotImplementedError("Subclasses must implement prepare_constraints method")

    @staticmethod
    def _empty_prepared_constraints() -> PreparedConstraints:
        return PreparedConstraints(
            value_constraints=ValueConstraint(),
            gradient_constraints=GradientConstraint(),
            normal_constraints=GradientConstraint(is_normal=True),
            tangent_constraints=GradientConstraint(),
            inequality_constraints=InequalityConstraint(),
            inequality_pair_constraints=InequalityPair(),
        )

    @classmethod
    def _prepare_generic_constraints(cls, linked_data) -> PreparedConstraints:
        prepared = cls._empty_prepared_constraints()
        if linked_data is None:
            return prepared

        points, gradients, tangents = cls._extract_constraint_arrays(linked_data)
        if points.shape[0] > 0:
            prepared.value_constraints = ValueConstraint(
                points=points,
                values=np.zeros(points.shape[0], dtype=float),
            )

        # Default behaviour treats generic vector observations as normals.
        prepared.normal_constraints = cls._to_gradient_constraint(gradients, is_normal=True)
        prepared.tangent_constraints = cls._to_gradient_constraint(tangents)
        prepared.inequality_constraints = cls._coerce_inequality_constraints(
            getattr(linked_data, "inequality_constraints", None)
        )
        prepared.inequality_pair_constraints = cls._coerce_inequality_pair_constraints(
            getattr(linked_data, "inequality_pair_constraints", None)
        )
        return prepared

    @staticmethod
    def _coerce_inequality_constraints(value) -> InequalityConstraint:
        if isinstance(value, InequalityConstraint):
            return value
        if value is None:
            return InequalityConstraint()
        arr = np.asarray(value, dtype=float)
        if arr.ndim != 2 or arr.shape[0] == 0:
            return InequalityConstraint()
        return InequalityConstraint.from_array(arr)

    @staticmethod
    def _coerce_inequality_pair_constraints(value) -> InequalityPair:
        if isinstance(value, InequalityPair):
            return value
        if value is None:
            return InequalityPair()
        arr = np.asarray(value, dtype=float)
        if arr.ndim != 2 or arr.shape[0] == 0:
            return InequalityPair()
        return InequalityPair.from_array(arr)

    @classmethod
    def _extract_constraint_arrays(
        cls,
        linked_data,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        point_blocks: list[np.ndarray] = []
        gradient_blocks: list[np.ndarray] = []
        tangent_blocks: list[np.ndarray] = []

        by_role = getattr(linked_data, "by_role", {}) if linked_data is not None else {}
        for observations in by_role.values():
            for linked in observations:
                observation = getattr(linked, "observation", None)
                if observation is None:
                    continue

                vertices = cls.as_nx3(getattr(observation, "vertices", None))
                if vertices is not None:
                    point_blocks.append(vertices)

                    to_tangent_vectors = getattr(observation, "to_tangent_vectors", None)
                    if callable(to_tangent_vectors):
                        for tangent in to_tangent_vectors():
                            tangent_rows = cls._coords_and_vectors(tangent)
                            if tangent_rows is not None and tangent_rows.shape[0] > 0:
                                tangent_blocks.append(tangent_rows)
                    continue

                rows = cls._coords_and_vectors(observation)
                if rows is not None:
                    role_text = str(getattr(linked, "role", "")).strip().lower()
                    obs_type_name = str(getattr(observation, "type", "")).strip().lower()
                    if (
                        "tangent" in obs_type_name
                        or "tangent" in role_text
                        or "slip" in role_text
                    ):
                        tangent_blocks.append(rows)
                    else:
                        gradient_blocks.append(rows)
                    continue

                coords = cls.as_nx3(getattr(observation, "coords", None))
                if coords is not None:
                    point_blocks.append(coords)

        points = np.vstack(point_blocks) if point_blocks else np.empty((0, 3), dtype=float)
        gradients = (
            np.vstack(gradient_blocks) if gradient_blocks else np.empty((0, 6), dtype=float)
        )
        tangents = np.vstack(tangent_blocks) if tangent_blocks else np.empty((0, 6), dtype=float)
        return points, gradients, tangents

    @classmethod
    def _coords_and_vectors(cls, observation) -> np.ndarray | None:
        coords = cls.as_nx3(getattr(observation, "coords", None))
        vectors = cls.as_nx3(getattr(observation, "vector", None))
        if coords is None or vectors is None:
            return None
        if coords.shape[0] != vectors.shape[0]:
            return None
        return np.hstack((coords, vectors))

    def build_from_constraints(
        self,
        linked_data,
        prepared: PreparedConstraints,
        build_params: dict,
    ) -> object | None:
        from loop_interpolation import InterpolatorBuilder

        if (
            prepared.value_constraints.points.shape[0] == 0
            and prepared.gradient_constraints.points.shape[0] == 0
            and prepared.normal_constraints.points.shape[0] == 0
            and prepared.tangent_constraints.points.shape[0] == 0
            and prepared.inequality_constraints.points.shape[0] == 0
            and prepared.inequality_pair_constraints.points.shape[0] == 0
        ):
            return None

        builder = InterpolatorBuilder(
            interpolatortype=self.model.interpolatortype,
            bounding_box=self._resolve_bounding_box(linked_data),
            nelements=self.model.nelements,
        )
        self.configure_builder(builder, build_params)

        if prepared.value_constraints.points.shape[0] > 0:
            builder.add_value_constraints(prepared.value_constraints)
        if prepared.gradient_constraints.points.shape[0] > 0:
            builder.add_gradient_constraints(prepared.gradient_constraints)
        if prepared.normal_constraints.points.shape[0] > 0:
            builder.add_normal_constraints(prepared.normal_constraints)
        if prepared.tangent_constraints.points.shape[0] > 0:
            builder.add_tangent_constraints(prepared.tangent_constraints)
        if prepared.inequality_constraints.points.shape[0] > 0:
            builder.add_inequality_constraints(prepared.inequality_constraints)
        if prepared.inequality_pair_constraints.points.shape[0] > 0:
            builder.add_inequality_pair_constraints(prepared.inequality_pair_constraints)

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

    @classmethod
    def _to_gradient_constraint(
        cls,
        rows: np.ndarray,
        is_normal: bool = False,
    ) -> GradientConstraint:
        normalized = cls._normalize_xyz_vectors(rows)
        if normalized.shape[0] == 0:
            return GradientConstraint(is_normal=is_normal)
        return GradientConstraint.from_array(normalized, is_normal=is_normal)

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

        point_constraints, gradient_constraints, tangent_constraints = self._extract_constraint_arrays(
            linked_data
        )
        if point_constraints.shape[0] > 0:
            coordinate_blocks.append(point_constraints)
        if gradient_constraints.shape[0] > 0:
            coordinate_blocks.append(gradient_constraints[:, :3])
        if tangent_constraints.shape[0] > 0:
            coordinate_blocks.append(tangent_constraints[:, :3])

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
