from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict
from typing import Any


@dataclass(frozen=True)
class LinkedObservation:
    obs_uid: str
    role: str
    observation_type: str
    observation: Any | None


@dataclass
class InterpolatorInput:
    feature_id: str
    feature_name: str | None
    feature_type: str
    by_role: DefaultDict[str, list[LinkedObservation]] = field(
        default_factory=lambda: defaultdict(list)
    )
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

            observation_type = "missing" if observation is None else type(observation).__name__
            payload.by_role[role].append(
                LinkedObservation(
                    obs_uid=obs_uid,
                    role=role,
                    observation_type=observation_type,
                    observation=observation,
                )
            )

            if observation is None:
                payload.missing_observation_ids.append(obs_uid)
                continue

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
