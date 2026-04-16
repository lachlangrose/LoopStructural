from loop_common.base import LoopEntity

from ..featurespec import GeologicalFeature

from ..featurespec import FeatureSpec
from typing import Dict, List
import networkx as nx
from pydantic import ConfigDict, Field
from enum import Enum


class RelationType(str, Enum):
    FAULTS = "faults"
    OVERLIES = "overlies"
    FOLDS = "folds"
    ERODE = "erode"
    ONLAP = "onlap"
    INTRUDE = "intrude"


class GeologicalSchema(LoopEntity):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )
    features: dict[str, GeologicalFeature] = Field(default_factory=dict)
    dag: nx.DiGraph = Field(default_factory=nx.DiGraph)

    def add_feature(self, feature: GeologicalFeature):
        self.features[feature.uuid] = feature
        self.dag.add_node(feature.uuid)

    def add_relation(self, master_uuid: str, slave_uuid: str, relation_type: str):
        self.dag.add_edge(master_uuid, slave_uuid, relation=relation_type)

    def get_execution_order(self) -> List[str]:
        """Returns the order in which the Engine should solve features."""
        return list(nx.topological_sort(self.dag))

    def get_kinematic_chain(self, feature_name: str) -> List[str]:
        """Returns all faults/operators that affect this feature's geometry."""
        # We look for all ancestors connected by a 'displaces' edge
        # This is what the Engine uses for coordinate warping.
        return [
            n
            for n in nx.ancestors(self.dag, feature_name)
            if self.dag.edges[n, feature_name].get("relation") == "displaces"
        ]

    def validate(self):
        """Checks for cycles and other schema issues."""
        if not nx.is_directed_acyclic_graph(self.dag):
            raise ValueError("Schema has cycles! Check feature relations.")
