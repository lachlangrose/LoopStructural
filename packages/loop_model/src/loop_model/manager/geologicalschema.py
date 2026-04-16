from __future__ import annotations

from loop_common.base import LoopEntity
from loop_common.geometry import BoundingBox

from ..features import GeologicalFeature, Unit, Fault, Fold
from .role import DataRole
from typing import TYPE_CHECKING, List
import networkx as nx
from pydantic import ConfigDict, Field
from enum import Enum

if TYPE_CHECKING:
    from .project import LoopProject


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
    bounding_box: BoundingBox = Field(default_factory=BoundingBox)
    project: "LoopProject | None" = None  # Back-reference to the parent project
    def add_unit(self, name: str, 
                 base_contacts: list[DataRole] | None = None, 
                 top_contacts: list[DataRole] | None = None, 
                 orientations: list[DataRole] | None = None, 
                 thicknesses: list[DataRole] | None = None,
                 inside: list[DataRole] | None = None,
                 outside: list[DataRole] | None = None
                 ):
        new_unit = Unit(name=name)
        for obs in base_contacts or []:
            # Process each base contact observation
            self.project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="base"))
        for obs in top_contacts or []:
            # Process each top contact observation
            self.project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="top"))
        for obs in orientations or []:
            # Process each orientation observation
            self.project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="orientation"))
        for obs in thicknesses or []:
            # Process each thickness observation
            self.project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="thickness"))
        for obs in inside or []:
            # Process each inside constraint observation
            self.project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="constraint"))
        for obs in outside or []:
            # Process each outside constraint observation
            self.project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="constraint"))
            
        
        self._add_feature(new_unit)
        return new_unit
    def add_fault(self, name: str, displacement: float, trace: list[DataRole] | None = None, hanging_wall: list[DataRole] | None = None, footwall: list[DataRole] | None = None, orientations: list[DataRole] | None = None, slip_vector: list[DataRole] | None = None):

        new_fault = Fault(name=name, displacement=displacement)
        for obs in trace or []:
            self.project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="trace"))
        for obs in hanging_wall or []:
            self.project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="hanging_wall"))
        for obs in footwall or []:
            self.project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="footwall"))
        for obs in orientations or []:
            self.project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="orientation"))
        for obs in slip_vector or []:
            self.project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uid, role="slip_vector"))
        self._add_feature(new_fault)
        return new_fault
            

    def add_foliation(self, name: str, observations: list[LoopEntity] | None = None):

        pass

    def add_fold(self, name: str, observations: list[LoopEntity] | None = None):
        pass

    def _add_feature(self, feature: GeologicalFeature):
        self.features[feature.uuid] = feature
        self.dag.add_node(feature.uuid)

    def add_feature(self, feature: GeologicalFeature):
        self._add_feature(feature)

    def _add_relation(self, master_uuid: str, slave_uuid: str, relation_type: str):
        self.dag.add_edge(master_uuid, slave_uuid, relation=relation_type)

    def add_relation(self, master_uuid: str, slave_uuid: str, relation_type: str):
        self._add_relation(master_uuid, slave_uuid, relation_type)

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


from .project import LoopProject

GeologicalSchema.model_rebuild(_types_namespace={"LoopProject": LoopProject})
