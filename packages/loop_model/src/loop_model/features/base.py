from typing import List
from pydantic import Field
from loop_common.base import LoopEntity


class GeologicalFeature(LoopEntity):
    """Base class for all features in the schema."""

    # List of UIDs pointing to ObservationSets in the data registry
    data_links: List[str] = Field(default_factory=list)

    # Is the feature active in the current model solve?
    enabled: bool = True
