from __future__ import annotations

from loop_common.base import LoopEntity
from loop_common.geometry import BoundingBox

from ..features import GeologicalFeature, Unit, Fault
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
    ABUTS = "abuts"


class GeologicalSchema(LoopEntity):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )
    features: dict[str, GeologicalFeature] = Field(default_factory=dict)
    dag: nx.DiGraph = Field(default_factory=nx.DiGraph)
    bounding_box: BoundingBox = Field(default_factory=BoundingBox)
    project: "LoopProject | None" = None  # Back-reference to the parent project

    def initialize_project(self) -> "LoopProject":
        """Create and attach a LoopProject when working schema-first."""
        if self.project is None:
            from .project import LoopProject

            self.project = LoopProject(schema=self)
        return self.project

    def _require_project(self) -> "LoopProject":
        if self.project is None:
            raise RuntimeError(
                "Schema has no project. Use LoopProject(schema=...) or call schema.initialize_project()."
            )
        return self.project

    def add_unit(
        self,
        name: str,
        basal_contacts: list[DataRole] | None = None,
        top_contacts: list[DataRole] | None = None,
        orientations: list[DataRole] | None = None,
        thicknesses: list[DataRole] | None = None,
        inside: list[DataRole] | None = None,
        outside: list[DataRole] | None = None,
    ):
        project = self._require_project()
        new_unit = Unit(name=name)
        for obs in basal_contacts or []:
            # Process each basal contact observation
            project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="basal"))
        for obs in top_contacts or []:
            # Process each top contact observation
            project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="top"))
        for obs in orientations or []:
            # Process each orientation observation
            project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="orientation"))
        for obs in thicknesses or []:
            # Process each thickness observation
            project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="thickness"))
        for obs in inside or []:
            # Process each inside constraint observation
            project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="constraint"))
        for obs in outside or []:
            # Process each outside constraint observation
            project.observations[obs.uuid] = obs
            new_unit.data_links.append(DataRole(obs_uid=obs.uuid, role="constraint"))

        self._add_feature(new_unit)
        return new_unit

    def add_fault(
        self,
        name: str,
        displacement: float,
        trace: list[DataRole] | None = None,
        hanging_wall: list[DataRole] | None = None,
        footwall: list[DataRole] | None = None,
        orientations: list[DataRole] | None = None,
        slip_vector: list[DataRole] | None = None,
    ):
        project = self._require_project()

        new_fault = Fault(name=name, displacement=displacement)
        for obs in trace or []:
            project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="trace"))
        for obs in hanging_wall or []:
            project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="hanging_wall"))
        for obs in footwall or []:
            project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="footwall"))
        for obs in orientations or []:
            project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uuid, role="orientation"))
        for obs in slip_vector or []:
            project.observations[obs.uuid] = obs
            new_fault.data_links.append(DataRole(obs_uid=obs.uid, role="slip_vector"))
        self._add_feature(new_fault)
        return new_fault

    def add_foliation(
        self,
        name: str,
        axial_trace: list[DataRole] | None = None,
        orientations: list[DataRole] | None = None,
    ):

        pass

    def add_fold(self, name: str):

        pass

    def _add_feature(self, feature: GeologicalFeature):
        self.features[feature.uuid] = feature
        self.dag.add_node(feature.uuid)

    def add_feature(self, feature: GeologicalFeature):
        self._add_feature(feature)

    def _add_relation(self, master_uuid: str, slave_uuid: str, relation_type: str):
        self.dag.add_edge(master_uuid, slave_uuid, relation=relation_type)

    def add_faulted_by_relation(self, master_uuid: str, slave_uuid: str):
        if master_uuid == slave_uuid:
            raise ValueError("A feature cannot fault itself.")
        if self._validate_type(master_uuid, "Fault") and self._validate_type(
            slave_uuid, ["Unit", "Fault", "Foliation", "Intrusion"]
        ):
            self._add_relation(master_uuid, slave_uuid, RelationType.FAULTS)

    def add_fault_abuts_relation(self, master_uuid: str, slave_uuid: str):
        if master_uuid == slave_uuid:
            raise ValueError("A feature cannot abut itself.")
        if self._validate_type(master_uuid, "Fault") and self._validate_type(slave_uuid, "Fault"):
            self._add_relation(master_uuid, slave_uuid, RelationType.ABUTS)

    def add_conformable_overlies_relation(self, master_uuid: str, slave_uuid: str):
        if master_uuid == slave_uuid:
            raise ValueError("A feature cannot overlie itself.")
        if self._validate_type(master_uuid, "Unit") and self._validate_type(slave_uuid, "Unit"):
            self._add_relation(master_uuid, slave_uuid, RelationType.OVERLIES)

    def add_erode_relation(self, master_uuid: str, slave_uuid: str):
        if master_uuid == slave_uuid:
            raise ValueError("A feature cannot erode itself.")
        if self._validate_type(master_uuid, ["Unit"]) and self._validate_type(
            slave_uuid, ["Unit", "Fault", "Fold", "Intrusion"]
        ):
            self._add_relation(master_uuid, slave_uuid, RelationType.ERODE)

    def add_onlap_relation(self, master_uuid: str, slave_uuid: str):
        if master_uuid == slave_uuid:
            raise ValueError("A feature cannot onlap itself.")
        if self._validate_type(master_uuid, "Unit") and self._validate_type(
            slave_uuid, ["Unit", "Fault", "Fold", "Intrusion"]
        ):
            self._add_relation(master_uuid, slave_uuid, RelationType.ONLAP)

    def add_fold_relation(self, master_uuid: str, slave_uuid: str):
        if master_uuid == slave_uuid:
            raise ValueError("A feature cannot fold itself.")
        if self._validate_type(master_uuid, "Fold") and self._validate_type(
            slave_uuid, ["Unit", "Fault", "Fold", "Intrusion"]
        ):
            self._add_relation(master_uuid, slave_uuid, RelationType.FOLDS)

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

    def get_feature_by_name(self, name: str) -> GeologicalFeature | None:
        """Returns the feature with the given name, or None if not found."""
        for feature in self.features.values():
            if feature.name == name:
                return feature
        return None

    def get_feature_type(self, feature_uuid: str) -> str | None:
        """Returns the type of the feature (e.g. 'Unit', 'Fault') based on its class."""
        feature = self.features.get(feature_uuid)
        if feature is None:
            return None
        return type(feature).__name__

    def get_relations_of_type(self, relation_type: str) -> List[tuple[str, str]]:
        """Returns a list of (master_uuid, slave_uuid) tuples for the given relation type."""
        return [
            (u, v)
            for u, v, data in self.dag.edges(data=True)
            if data.get("relation") == relation_type
        ]

    def get_relationships(self, feature_uuid: str) -> dict[str, List[str]]:
        """Returns a dictionary of related features by relation type."""
        relationships = {}
        for neighbor in self.dag.successors(feature_uuid):
            relation = self.dag.edges[feature_uuid, neighbor].get("relation")
            relationships.setdefault(relation, []).append(neighbor)
        for neighbor in self.dag.predecessors(feature_uuid):
            relation = self.dag.edges[neighbor, feature_uuid].get("relation")
            relationships.setdefault(relation, []).append(neighbor)
        return relationships

    def _validate_type(self, feature_uuid: str, expected_type: list[str] | str) -> bool:
        actual_type = self.get_feature_type(feature_uuid)
        if isinstance(expected_type, list):
            if actual_type not in expected_type:
                raise TypeError(
                    f"Feature {feature_uuid} is of type {actual_type}, expected one of {expected_type}."
                )
        else:
            if actual_type != expected_type:
                raise TypeError(
                    f"Feature {feature_uuid} is of type {actual_type}, expected {expected_type}."
                )
        return True

    def pretty_graph(self):
        """Prints a human-readable representation of the DAG."""
        for u, v, data in self.dag.edges(data=True):
            relation = data.get("relation")
            print(f"{self.features[u].name} --[{relation}]--> {self.features[v].name}")

    def visualize_graph(
        self,
        layout: str = "spring",
        figsize: tuple[float, float] = (10, 8),
        seed: int = 42,
        with_uuid: bool = False,
        ax=None,
        show: bool = True,
    ):
        """Plot the schema DAG with feature-type node shapes and relation edge labels."""
        try:
            from importlib import import_module

            plt = import_module("matplotlib.pyplot")
        except ImportError as exc:
            raise ImportError("matplotlib is required to visualize the schema graph") from exc

        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        else:
            fig = ax.figure

        if layout == "spring":
            pos = nx.spring_layout(self.dag, seed=seed)
        elif layout == "kamada_kawai":
            pos = nx.kamada_kawai_layout(self.dag)
        elif layout == "shell":
            pos = nx.shell_layout(self.dag)
        elif layout == "spectral":
            pos = nx.spectral_layout(self.dag)
        else:
            raise ValueError(
                "Unknown layout. Expected one of: spring, kamada_kawai, shell, spectral."
            )

        shape_map = {
            "Unit": "o",
            "Fault": "s",
            "Fold": "D",
            "Foliation": "^",
            "Intrusion": "v",
            "Unknown": "h",
        }
        color_map = {
            "Unit": "#5DA5DA",
            "Fault": "#F15854",
            "Fold": "#60BD68",
            "Foliation": "#B276B2",
            "Intrusion": "#F17CB0",
            "Unknown": "#9C9C9C",
        }

        node_types = {node: (self.get_feature_type(node) or "Unknown") for node in self.dag.nodes()}

        for feature_type in sorted(set(node_types.values())):
            nodes = [node for node, t in node_types.items() if t == feature_type]
            nx.draw_networkx_nodes(
                self.dag,
                pos,
                nodelist=nodes,
                node_shape=shape_map.get(feature_type, "h"),
                node_color=color_map.get(feature_type, "#9C9C9C"),
                node_size=1200,
                edgecolors="black",
                linewidths=0.8,
                ax=ax,
                label=feature_type,
            )

        nx.draw_networkx_edges(
            self.dag,
            pos,
            ax=ax,
            arrows=True,
            arrowstyle="-|>",
            arrowsize=18,
            width=1.5,
            edge_color="#666666",
        )

        node_labels = {
            node: (
                f"{self.features[node].name}\n{node[:8]}" if with_uuid else self.features[node].name
            )
            for node in self.dag.nodes()
        }
        nx.draw_networkx_labels(
            self.dag,
            pos,
            labels=node_labels,
            font_size=9,
            font_weight="bold",
            ax=ax,
        )

        edge_labels = {(u, v): data.get("relation", "") for u, v, data in self.dag.edges(data=True)}
        nx.draw_networkx_edge_labels(
            self.dag,
            pos,
            edge_labels=edge_labels,
            font_size=8,
            font_color="#333333",
            label_pos=0.5,
            ax=ax,
        )

        ax.set_title("Geological Schema Graph")
        ax.set_axis_off()
        ax.legend(title="Feature Type", loc="best")
        fig.tight_layout()

        if show:
            plt.show()
        return fig, ax


from .project import LoopProject

GeologicalSchema.model_rebuild(_types_namespace={"LoopProject": LoopProject})
