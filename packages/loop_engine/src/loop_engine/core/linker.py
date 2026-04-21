from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class LinkedObservation:
    obs_uid: str
    role: str
    observation: Any | None


@dataclass
class InterpolatorInput:
    feature_id: str
    feature_name: str | None
    feature_type: str
    point_constraints: np.ndarray = field(default_factory=lambda: np.empty((0, 3), dtype=float))
    gradient_constraints: np.ndarray = field(default_factory=lambda: np.empty((0, 6), dtype=float))
    tangent_constraints: np.ndarray = field(default_factory=lambda: np.empty((0, 6), dtype=float))
    by_role: dict[str, list[LinkedObservation]] = field(default_factory=dict)
    missing_observation_ids: list[str] = field(default_factory=list)


class ObservationLinker:
    """Compile feature data links into interpolator-ready constraint arrays."""

    def __init__(self, schema):
        self.schema = schema

    def build_inputs_by_feature(
        self, feature_ids: list[str] | None = None
    ) -> dict[str, InterpolatorInput]:
        ids = feature_ids if feature_ids is not None else self.schema.get_execution_order()
        return {feature_id: self.build_feature_input(feature_id) for feature_id in ids}

    def build_feature_input(self, feature_id: str) -> InterpolatorInput:
        feature = self.schema.features[feature_id]
        payload = InterpolatorInput(
            feature_id=feature_id,
            feature_name=getattr(feature, "name", None),
            feature_type=type(feature).__name__,
        )

        for data_link in getattr(feature, "data_links", []):
            obs_uid, role = self._parse_data_link(data_link)
            observation = self._lookup_observation(obs_uid)

            payload.by_role.setdefault(role, []).append(
                LinkedObservation(obs_uid=obs_uid, role=role, observation=observation)
            )

            if observation is None:
                payload.missing_observation_ids.append(obs_uid)
                continue

            self._append_observation_constraints(payload, observation)

        return payload

    def _lookup_observation(self, obs_uid: str) -> Any | None:
        project = getattr(self.schema, "project", None)
        if project is None:
            return None
        observations = getattr(project, "observations", {})
        return observations.get(obs_uid)

    @staticmethod
    def _parse_data_link(data_link) -> tuple[str, str]:
        if hasattr(data_link, "obs_uid"):
            obs_uid = data_link.obs_uid
            role = getattr(data_link, "role", "data")
            return obs_uid, role

        return str(data_link), "data"

    def _append_observation_constraints(self, payload: InterpolatorInput, observation: Any) -> None:
        if hasattr(observation, "vertices"):
            points = self._as_nx3(getattr(observation, "vertices", None))
            payload.point_constraints = self._append_rows(payload.point_constraints, points)

            to_tangent_vectors = getattr(observation, "to_tangent_vectors", None)
            if callable(to_tangent_vectors):
                for tangent in to_tangent_vectors():
                    tangent_rows = self._coords_and_vectors(tangent)
                    payload.tangent_constraints = self._append_rows(
                        payload.tangent_constraints,
                        tangent_rows,
                    )
            return

        rows = self._coords_and_vectors(observation)
        if rows is not None:
            obs_type = getattr(observation, "type", None)
            obs_type_name = str(obs_type).lower() if obs_type is not None else ""
            if "tangent" in obs_type_name:
                payload.tangent_constraints = self._append_rows(payload.tangent_constraints, rows)
            else:
                payload.gradient_constraints = self._append_rows(payload.gradient_constraints, rows)
            return

        coords = self._as_nx3(getattr(observation, "coords", None))
        payload.point_constraints = self._append_rows(payload.point_constraints, coords)

    def _coords_and_vectors(self, observation: Any) -> np.ndarray | None:
        coords = self._as_nx3(getattr(observation, "coords", None))
        vectors = self._as_nx3(getattr(observation, "vector", None))
        if coords is None or vectors is None:
            return None
        if coords.shape[0] != vectors.shape[0]:
            return None
        return np.hstack((coords, vectors))

    @staticmethod
    def _as_nx3(values: Any) -> np.ndarray | None:
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

    @staticmethod
    def _append_rows(base: np.ndarray, rows: np.ndarray | None) -> np.ndarray:
        if rows is None:
            return base
        if base.size == 0:
            return rows
        return np.vstack((base, rows))
