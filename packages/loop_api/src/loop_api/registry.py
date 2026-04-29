from __future__ import annotations

from typing import Any, Callable

import networkx as nx

from loop_model.manager.geologicalschema import GeologicalSchema


ObservationAdapter = Callable[[dict[str, Any], dict[str, Any]], Any]
FeatureAdapter = Callable[[GeologicalSchema, dict[str, Any], dict[str, Any], dict[str, str]], str | None]
RelationAdapter = Callable[[GeologicalSchema, str, str], None]


class ExtensionRegistry:
    def __init__(self):
        self.observation_adapters: dict[str, ObservationAdapter] = {}
        self.feature_adapters: dict[str, FeatureAdapter] = {}
        self.relation_adapters: dict[str, RelationAdapter] = {}

    def register_observation_adapter(self, obs_type: str, adapter: ObservationAdapter):
        self.observation_adapters[obs_type.lower()] = adapter

    def register_feature_adapter(self, feature_type: str, adapter: FeatureAdapter):
        self.feature_adapters[feature_type.lower()] = adapter

    def register_relation_adapter(self, relation_type: str, adapter: RelationAdapter):
        self.relation_adapters[relation_type.lower()] = adapter


def _default_add_unit(
    schema: GeologicalSchema,
    feature_spec: dict[str, Any],
    observations_by_id: dict[str, Any],
    feature_uuid_by_key: dict[str, str],
) -> str | None:
    links = feature_spec.get("data_links", {})

    def _collect(role: str):
        return [observations_by_id[obs_id] for obs_id in links.get(role, []) if obs_id in observations_by_id]

    unit = schema.add_unit(
        name=feature_spec["name"],
        basal_contacts=_collect("basal"),
        top_contacts=_collect("top"),
        orientations=_collect("orientation"),
        thicknesses=_collect("thickness"),
        inside=_collect("inside"),
        outside=_collect("outside"),
        build_params=feature_spec.get("build_params"),
    )
    feature_uuid_by_key[feature_spec["id"]] = unit.uuid
    return unit.uuid


def _default_add_fault(
    schema: GeologicalSchema,
    feature_spec: dict[str, Any],
    observations_by_id: dict[str, Any],
    feature_uuid_by_key: dict[str, str],
) -> str | None:
    links = feature_spec.get("data_links", {})

    def _collect(role: str):
        return [observations_by_id[obs_id] for obs_id in links.get(role, []) if obs_id in observations_by_id]

    fault = schema.add_fault(
        name=feature_spec["name"],
        displacement=float(feature_spec.get("displacement", 0.0)),
        trace=_collect("trace"),
        hanging_wall=_collect("hanging_wall"),
        footwall=_collect("footwall"),
        orientations=_collect("orientation"),
        slip_vector=_collect("slip_vector"),
        build_params=feature_spec.get("build_params"),
    )
    feature_uuid_by_key[feature_spec["id"]] = fault.uuid
    return fault.uuid


def _default_faults_relation(schema: GeologicalSchema, master_uuid: str, slave_uuid: str):
    schema.add_faulted_by_relation(master_uuid=master_uuid, slave_uuid=slave_uuid)


def _default_overlies_relation(schema: GeologicalSchema, master_uuid: str, slave_uuid: str):
    schema.add_conformable_overlies_relation(master_uuid=master_uuid, slave_uuid=slave_uuid)


def _default_abuts_relation(schema: GeologicalSchema, master_uuid: str, slave_uuid: str):
    schema.add_fault_abuts_relation(master_uuid=master_uuid, slave_uuid=slave_uuid)


def _default_erode_relation(schema: GeologicalSchema, master_uuid: str, slave_uuid: str):
    schema.add_erode_relation(master_uuid=master_uuid, slave_uuid=slave_uuid)


def _default_onlap_relation(schema: GeologicalSchema, master_uuid: str, slave_uuid: str):
    schema.add_onlap_relation(master_uuid=master_uuid, slave_uuid=slave_uuid)


def _default_folds_relation(schema: GeologicalSchema, master_uuid: str, slave_uuid: str):
    schema.add_fold_relation(master_uuid=master_uuid, slave_uuid=slave_uuid)


def would_create_cycle(graph: nx.DiGraph, master_uuid: str, slave_uuid: str) -> bool:
    graph_copy = graph.copy()
    graph_copy.add_edge(master_uuid, slave_uuid)
    return not nx.is_directed_acyclic_graph(graph_copy)


def create_default_registry() -> ExtensionRegistry:
    registry = ExtensionRegistry()

    registry.register_feature_adapter("unit", _default_add_unit)
    registry.register_feature_adapter("fault", _default_add_fault)

    registry.register_relation_adapter("faults", _default_faults_relation)
    registry.register_relation_adapter("overlies", _default_overlies_relation)
    registry.register_relation_adapter("abuts", _default_abuts_relation)
    registry.register_relation_adapter("erode", _default_erode_relation)
    registry.register_relation_adapter("onlap", _default_onlap_relation)
    registry.register_relation_adapter("folds", _default_folds_relation)

    return registry
