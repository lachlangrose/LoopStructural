from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import yaml

from loop_common.geometry import BoundingBox
from loop_engine import Model
from loop_model.manager import GeologicalSchema, LoopProject

from .diagnostics import DiagnosticCollector, LoopApiValidationError
from .observations import load_observation
from .registry import ExtensionRegistry, create_default_registry, would_create_cycle

_ALLOWED_ROLES_BY_FEATURE = {
    "unit": {"basal", "top", "orientation", "thickness", "inside", "outside"},
    "fault": {"trace", "hanging_wall", "footwall", "orientation", "slip_vector"},
}


class YAMLAssembly:
    def __init__(
        self,
        source: str | Path | dict[str, Any],
        validation_mode: str = "strict",
        registry: ExtensionRegistry | None = None,
    ):
        self.registry = registry or create_default_registry()
        # Default observation adapter is shared across observation types and dispatches by type.
        for obs_type in ("pointset", "orientation", "lineset"):
            self.registry.register_observation_adapter(obs_type, load_observation)

        self.collector = DiagnosticCollector(mode=validation_mode)
        self.raw_payload, self.source_dir = self._read_source(source)
        self.spec = self._normalize(self.raw_payload)
        self._validate_and_filter_in_place()

    @property
    def diagnostics(self) -> list[dict[str, Any]]:
        return self.collector.as_dicts()

    def _read_source(self, source: str | Path | dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
        if isinstance(source, dict):
            return source, None

        if isinstance(source, Path):
            path = source
        elif isinstance(source, str):
            candidate = Path(source)
            if candidate.exists():
                path = candidate
            else:
                parsed = yaml.safe_load(source)
                if not isinstance(parsed, dict):
                    raise ValueError("YAML payload must deserialize to a dictionary")
                return parsed, None
        else:
            raise TypeError("source must be a path, YAML string, or dictionary")

        with path.open("r", encoding="utf-8") as f:
            payload = yaml.safe_load(f) or {}
        if not isinstance(payload, dict):
            raise ValueError("YAML file must deserialize to a dictionary")
        return payload, path.parent

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        spec = {
            "metadata": payload.get("metadata", {}) or {},
            "bounding_box": payload.get("bounding_box", {}) or {},
            "solve": payload.get("solve", {}) or {},
            "observations": payload.get("observations", []) or [],
            "features": payload.get("features", []) or [],
            "topology": payload.get("topology", []) or [],
        }
        self.collector.require(
            isinstance(spec["observations"], list),
            code="invalid-observations",
            message="observations must be a list",
        )
        self.collector.require(
            isinstance(spec["features"], list),
            code="invalid-features",
            message="features must be a list",
        )
        self.collector.require(
            isinstance(spec["topology"], list),
            code="invalid-topology",
            message="topology must be a list",
        )
        return spec

    def _validate_and_filter_in_place(self):
        self._validate_bounds()

        observation_ids: set[str] = set()
        filtered_observations = []
        for obs in self.spec["observations"]:
            if not isinstance(obs, dict):
                self.collector.require(False, "invalid-observation", "observation entries must be objects")
                continue

            obs_id = obs.get("id")
            obs_type = str(obs.get("type", "")).lower()
            self.collector.require(bool(obs_id), "missing-observation-id", "observation id is required")
            self.collector.require(
                obs_type in self.registry.observation_adapters,
                "unsupported-observation-type",
                f"Unsupported observation type: {obs_type}",
                context={"id": obs_id, "type": obs_type},
            )
            has_inline = "inline" in obs
            has_file = "file" in obs
            self.collector.require(
                has_inline ^ has_file,
                "invalid-observation-payload",
                "observation must provide exactly one of inline or file",
                context={"id": obs_id},
            )
            if not obs_id or obs_type not in self.registry.observation_adapters or not (has_inline ^ has_file):
                continue
            if obs_id in observation_ids:
                self.collector.require(False, "duplicate-observation-id", f"Duplicate observation id: {obs_id}")
                continue
            observation_ids.add(obs_id)
            filtered_observations.append(obs)
        self.spec["observations"] = filtered_observations

        feature_ids: set[str] = set()
        filtered_features = []
        for feature in self.spec["features"]:
            if not isinstance(feature, dict):
                self.collector.require(False, "invalid-feature", "feature entries must be objects")
                continue

            feature_id = feature.get("id")
            feature_name = feature.get("name")
            feature_type = str(feature.get("type", "")).lower()

            self.collector.require(bool(feature_id), "missing-feature-id", "feature id is required")
            self.collector.require(bool(feature_name), "missing-feature-name", "feature name is required")
            self.collector.require(
                feature_type in self.registry.feature_adapters,
                "unsupported-feature-type",
                f"Unsupported feature type: {feature_type}",
                context={"id": feature_id, "type": feature_type},
            )
            if not feature_id or not feature_name or feature_type not in self.registry.feature_adapters:
                continue
            if feature_id in feature_ids:
                self.collector.require(False, "duplicate-feature-id", f"Duplicate feature id: {feature_id}")
                continue

            links = feature.get("data_links", {}) or {}
            self.collector.require(
                isinstance(links, dict),
                "invalid-data-links",
                "feature data_links must be a map of role -> list[observation_id]",
                context={"feature": feature_id},
            )
            if not isinstance(links, dict):
                continue

            allowed_roles = _ALLOWED_ROLES_BY_FEATURE.get(feature_type, set())
            normalized_links = {}
            for role, linked_obs_ids in links.items():
                role_name = str(role)
                is_supported = role_name in allowed_roles
                self.collector.require(
                    is_supported,
                    "unsupported-role",
                    f"Unsupported role '{role_name}' for feature type '{feature_type}'",
                    context={"feature": feature_id, "role": role_name},
                )
                if not is_supported:
                    continue

                if isinstance(linked_obs_ids, list):
                    linked_ids_list = [str(obs_id) for obs_id in linked_obs_ids]
                else:
                    linked_ids_list = [str(linked_obs_ids)]

                missing = [obs_id for obs_id in linked_ids_list if obs_id not in observation_ids]
                self.collector.require(
                    len(missing) == 0,
                    "missing-observation-link",
                    "feature references missing observation ids",
                    context={"feature": feature_id, "missing": missing},
                )
                normalized_links[role_name] = [obs_id for obs_id in linked_ids_list if obs_id in observation_ids]

            feature["type"] = feature_type
            feature["data_links"] = normalized_links
            feature_ids.add(feature_id)
            filtered_features.append(feature)
        self.spec["features"] = filtered_features

        filtered_topology = []
        graph = nx.DiGraph()
        graph.add_nodes_from(feature_ids)

        for rel in self.spec["topology"]:
            if not isinstance(rel, dict):
                self.collector.require(False, "invalid-relation", "topology entries must be objects")
                continue

            relation_type = str(rel.get("type", "")).lower()
            master = rel.get("master")
            slave = rel.get("slave")

            self.collector.require(bool(master and slave), "invalid-relation-ends", "relation must provide master and slave ids")
            self.collector.require(
                relation_type in self.registry.relation_adapters,
                "unsupported-relation-type",
                f"Unsupported relation type: {relation_type}",
            )
            self.collector.require(
                master in feature_ids and slave in feature_ids,
                "unknown-relation-feature",
                "relation references unknown feature ids",
                context={"master": master, "slave": slave},
            )
            if not (master and slave):
                continue
            if relation_type not in self.registry.relation_adapters:
                continue
            if master not in feature_ids or slave not in feature_ids:
                continue

            if would_create_cycle(graph, master, slave):
                self.collector.require(
                    False,
                    "invalid-dag",
                    "topology introduces a cycle",
                    context={"master": master, "slave": slave, "type": relation_type},
                )
                continue

            graph.add_edge(master, slave)
            rel["type"] = relation_type
            filtered_topology.append(rel)

        self.spec["topology"] = filtered_topology

    def _validate_bounds(self):
        bounds = self.spec.get("bounding_box", {})
        if not bounds:
            return

        origin = bounds.get("origin")
        maximum = bounds.get("maximum")
        nsteps = bounds.get("nsteps")

        def _is_vec3(value):
            return isinstance(value, (list, tuple)) and len(value) == 3

        self.collector.require(_is_vec3(origin), "invalid-bounds-origin", "bounding_box.origin must be length-3")
        self.collector.require(_is_vec3(maximum), "invalid-bounds-maximum", "bounding_box.maximum must be length-3")
        if _is_vec3(origin) and _is_vec3(maximum):
            origin_arr = np.asarray(origin, dtype=float)
            max_arr = np.asarray(maximum, dtype=float)
            self.collector.require(
                bool(np.all(max_arr > origin_arr)),
                "invalid-bounds-order",
                "bounding_box.maximum must be greater than origin in all dimensions",
            )

        if nsteps is not None:
            self.collector.require(_is_vec3(nsteps), "invalid-bounds-nsteps", "bounding_box.nsteps must be length-3")
            if _is_vec3(nsteps):
                nsteps_arr = np.asarray(nsteps, dtype=int)
                self.collector.require(
                    bool(np.all(nsteps_arr > 0)),
                    "invalid-bounds-nsteps-values",
                    "bounding_box.nsteps values must be positive",
                )

    def to_project(self) -> LoopProject:
        schema_name = self.spec.get("metadata", {}).get("name", "YAMLAssembly")
        schema = GeologicalSchema(name=schema_name)
        project = LoopProject(schema=schema)

        bounds = self.spec.get("bounding_box", {})
        if bounds and all(k in bounds for k in ("origin", "maximum")):
            try:
                schema.bounding_box = BoundingBox(
                    origin=np.asarray(bounds["origin"], dtype=float),
                    maximum=np.asarray(bounds["maximum"], dtype=float),
                    nsteps=np.asarray(bounds.get("nsteps", [50, 50, 25]), dtype=int),
                )
            except Exception as exc:
                self.collector.require(
                    False,
                    "invalid-bounds-runtime",
                    f"Could not create BoundingBox: {exc}",
                )

        observations_by_id: dict[str, Any] = {}
        for obs_spec in self.spec["observations"]:
            obs_id = str(obs_spec["id"])
            adapter = self.registry.observation_adapters[str(obs_spec["type"]).lower()]
            try:
                obs = adapter(obs_spec, {"source_dir": self.source_dir})
                obs.uuid = obs_id
                if obs_spec.get("name"):
                    obs.name = str(obs_spec["name"])
                project.add_observation(obs)
                observations_by_id[obs_id] = obs
            except Exception as exc:
                self.collector.require(
                    False,
                    "observation-load-failed",
                    f"Failed to load observation '{obs_id}': {exc}",
                    context={"observation": obs_id},
                )

        feature_uuid_by_key: dict[str, str] = {}
        for feature_spec in self.spec["features"]:
            feature_type = str(feature_spec["type"]).lower()
            adapter = self.registry.feature_adapters[feature_type]
            try:
                adapter(schema, feature_spec, observations_by_id, feature_uuid_by_key)
            except Exception as exc:
                self.collector.require(
                    False,
                    "feature-assembly-failed",
                    f"Failed to assemble feature '{feature_spec.get('id')}': {exc}",
                    context={"feature": feature_spec.get("id")},
                )

        for relation_spec in self.spec["topology"]:
            relation_type = str(relation_spec["type"]).lower()
            master_uuid = feature_uuid_by_key.get(str(relation_spec["master"]))
            slave_uuid = feature_uuid_by_key.get(str(relation_spec["slave"]))
            self.collector.require(
                bool(master_uuid and slave_uuid),
                "missing-relation-target",
                "relation references a feature that failed to assemble",
                context=relation_spec,
            )
            if not (master_uuid and slave_uuid):
                continue

            if would_create_cycle(schema.dag, master_uuid, slave_uuid):
                self.collector.require(
                    False,
                    "invalid-dag",
                    "relation would create cycle in schema",
                    context=relation_spec,
                )
                continue

            rel_adapter = self.registry.relation_adapters[relation_type]
            try:
                rel_adapter(schema, master_uuid, slave_uuid)
            except Exception as exc:
                self.collector.require(
                    False,
                    "relation-assembly-failed",
                    f"Failed to assemble relation {relation_type}: {exc}",
                    context=relation_spec,
                )

        try:
            schema.validate()
        except Exception as exc:
            self.collector.require(False, "invalid-dag", f"Schema validation failed: {exc}")

        return project

    def to_model(self) -> Model:
        project = self.to_project()
        solve_options = self.spec.get("solve", {})
        return Model(
            schema=project.schema,
            interpolatortype=solve_options.get("interpolatortype", "FDI"),
            nelements=int(solve_options.get("nelements", 1000)),
            interpolation_strategy=solve_options.get("interpolation_strategy", "independent"),
        )

    def solve(self) -> dict[str, Any]:
        project = self.to_project()
        solve_options = self.spec.get("solve", {})
        model = Model(
            schema=project.schema,
            interpolatortype=solve_options.get("interpolatortype", "FDI"),
            nelements=int(solve_options.get("nelements", 1000)),
            interpolation_strategy=solve_options.get("interpolation_strategy", "independent"),
        )
        state = model.solve()
        return {
            "project": project,
            "model": model,
            "state": state,
            "diagnostics": self.diagnostics,
        }


def from_yaml(
    source: str | Path | dict[str, Any],
    validation_mode: str = "strict",
    registry: ExtensionRegistry | None = None,
) -> YAMLAssembly:
    return YAMLAssembly(source=source, validation_mode=validation_mode, registry=registry)


def to_project(
    source: str | Path | dict[str, Any],
    validation_mode: str = "strict",
    registry: ExtensionRegistry | None = None,
) -> LoopProject:
    return from_yaml(source, validation_mode=validation_mode, registry=registry).to_project()


def to_model(
    source: str | Path | dict[str, Any],
    validation_mode: str = "strict",
    registry: ExtensionRegistry | None = None,
) -> Model:
    return from_yaml(source, validation_mode=validation_mode, registry=registry).to_model()


def solve(
    source: str | Path | dict[str, Any],
    validation_mode: str = "strict",
    registry: ExtensionRegistry | None = None,
) -> dict[str, Any]:
    return from_yaml(source, validation_mode=validation_mode, registry=registry).solve()
