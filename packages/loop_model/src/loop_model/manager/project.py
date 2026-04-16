from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from loop_common.base import LoopEntity

if TYPE_CHECKING:
    from .geologicalschema import GeologicalSchema


def _create_schema() -> "GeologicalSchema":
    from .geologicalschema import GeologicalSchema

    return GeologicalSchema()


class LoopProject(LoopEntity):
    """A LoopProject represents a geological model project, containing a geological schema and associated data."""
    """The top-level container for a modeling session."""

    # The 'Brain': holds the logic, relationships, and metadata
    schema: "GeologicalSchema" = Field(default_factory=_create_schema)
    
    # The 'Vault': holds the heavy raw data (PointSets, etc.)
    # Map: UUID -> Observation object
    observations: dict[str, LoopEntity] = Field(default_factory=dict)

    def model_post_init(self, __context):
        if self.schema.project is None:
            self.schema.project = self

    def add_observation(self, obs: LoopEntity):
        obs_id = getattr(obs, "uuid", getattr(obs, "uid", None))
        if obs_id is None:
            raise AttributeError("Observation must define either 'uuid' or 'uid'.")
        self.observations[obs_id] = obs

    def link_observation_to_feature(self, obs_uid: str, feature_uid: str):
        if feature_uid in self.schema.features:
            self.schema.features[feature_uid].data_links.append(obs_uid)


from .geologicalschema import GeologicalSchema

LoopProject.model_rebuild(_types_namespace={"GeologicalSchema": GeologicalSchema})