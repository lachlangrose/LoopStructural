from typing import Any, List
from pydantic import Field

from loop_common.base import LoopEntity
from ..manager.role import DataRole

class GeologicalFeature(LoopEntity):
    """Base class for all features in the schema."""

    # List of UIDs pointing to ObservationSets in the data registry
    data_links: List[str | DataRole] = Field(default_factory=list)

    # Is the feature active in the current model solve?
    enabled: bool = True

    # Optional free-form metadata for feature-level modelling options.
    metadata: dict[str, Any] = Field(default_factory=dict)
