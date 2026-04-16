"""Validation rules for Geological Model Description Graphs."""

from __future__ import annotations

from .model import (
    AngularUnconformityParams,
    DisconformityParams,
    ErosionParams,
    ExternalScalarSource,
    FlatFieldParams,
    FoldedFieldParams,
    GeologicalModelGraph,
    InterpolatedScalarSource,
    OnlapParams,
    ParametricScalarSource,
    Region,
    ScalarFeature,
    Unit,
    Unconformity,
    VariogramFieldParams,
)


def validate_stratigraphic_dag(g: GeologicalModelGraph) -> None:
    adj = {}
    for rel in g.relations:
        if rel.kind == "overlies":
            adj.setdefault(rel.src, set()).add(rel.dst)
            adj.setdefault(rel.dst, set())
    indeg = {u: 0 for u in adj.keys()}
    for u, succ in adj.items():
        for v in succ:
            indeg[v] = indeg.get(v, 0) + 1
    q = [u for u, d in indeg.items() if d == 0]
    out = []
    while q:
        n = q.pop()
        out.append(n)
        for v in adj.get(n, ()):  # type: ignore
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != len(indeg):
        raise ValueError("Stratigraphic 'overlies' relations contain a cycle")


def validate_scalar_source_configuration(g: GeologicalModelGraph) -> None:
    for feature in g.features.values():
        if not isinstance(feature, ScalarFeature):
            continue

        source = feature.source
        if isinstance(source, ParametricScalarSource):
            if source.field_type == "flat" and not isinstance(source.params, FlatFieldParams):
                raise ValueError(f"Scalar feature '{feature.id}' field_type=flat requires FlatFieldParams")
            if source.field_type == "folded" and not isinstance(source.params, FoldedFieldParams):
                raise ValueError(f"Scalar feature '{feature.id}' field_type=folded requires FoldedFieldParams")
            if source.field_type == "variogram" and not isinstance(source.params, VariogramFieldParams):
                raise ValueError(f"Scalar feature '{feature.id}' field_type=variogram requires VariogramFieldParams")
        elif isinstance(source, InterpolatedScalarSource):
            if not source.method.strip():
                raise ValueError(f"Scalar feature '{feature.id}' must define a non-empty interpolation method")
        elif isinstance(source, ExternalScalarSource):
            if not source.uri.strip():
                raise ValueError(f"Scalar feature '{feature.id}' must define a non-empty external uri")


def validate_topological_relation_params(g: GeologicalModelGraph) -> None:
    for rel in g.relations:
        if rel.kind == "erodes" and rel.erosion_params is not None and not isinstance(rel.erosion_params, ErosionParams):
            raise ValueError(f"Relation erodes({rel.src}->{rel.dst}) has invalid erosion_params")
        if rel.kind == "erodes" and rel.angular_unconformity_params is not None and not isinstance(
            rel.angular_unconformity_params, AngularUnconformityParams
        ):
            raise ValueError(f"Relation erodes({rel.src}->{rel.dst}) has invalid angular_unconformity_params")
        if rel.kind == "overlies" and rel.onlap_params is not None and not isinstance(rel.onlap_params, OnlapParams):
            raise ValueError(f"Relation overlies({rel.src}->{rel.dst}) has invalid onlap_params")
        if rel.kind == "overlies" and rel.disconformity_params is not None and not isinstance(
            rel.disconformity_params, DisconformityParams
        ):
            raise ValueError(f"Relation overlies({rel.src}->{rel.dst}) has invalid disconformity_params")


def validate_unit_representations(g: GeologicalModelGraph) -> None:
    for feature in g.features.values():
        if not isinstance(feature, Unit):
            continue

        rep = feature.representation
        if rep is None:
            continue

        target = g.features.get(rep.scalar_feature_id)
        if target is None:
            raise ValueError(
                f"Unit {feature.id} references unknown scalar_feature_id '{rep.scalar_feature_id}'"
            )
        if not isinstance(target, ScalarFeature):
            raise ValueError(
                f"Unit {feature.id} references '{rep.scalar_feature_id}', but it is not a scalar feature"
            )


def validate_references_exist(g: GeologicalModelGraph) -> None:
    all_ids = set(g.features.keys())

    for feature in g.features.values():
        if isinstance(feature, Unconformity) and feature.scalar_feature_id is not None:
            target = g.features.get(feature.scalar_feature_id)
            if target is None:
                raise ValueError(
                    f"Unconformity {feature.id} references unknown scalar_feature_id '{feature.scalar_feature_id}'"
                )
            if not isinstance(target, ScalarFeature):
                raise ValueError(
                    f"Unconformity {feature.id} scalar_feature_id '{feature.scalar_feature_id}' is not scalar"
                )

    for obs in g.geo_observations.values():
        if obs.target not in all_ids:
            raise ValueError(f"Observation set '{obs.id}' references unknown target '{obs.target}'")
        if obs.region is not None and obs.region not in g.features:
            raise ValueError(f"Observation set '{obs.id}' references unknown region '{obs.region}'")

    for rel in g.relations:
        if rel.src not in all_ids:
            raise ValueError(f"Relation src '{rel.src}' not found")
        if rel.dst not in all_ids:
            raise ValueError(f"Relation dst '{rel.dst}' not found")

    for ev in g.events:
        if ev.feature not in g.features:
            raise ValueError(f"Event '{ev.id}' references unknown feature '{ev.feature}'")
        for group, ids in ev.scope.items():
            for i in ids:
                if group == "units":
                    if i not in g.features or not isinstance(g.features[i], Unit):
                        raise ValueError(f"Event '{ev.id}' scope references unknown unit '{i}'")
                elif group == "regions":
                    if i not in g.features or not isinstance(g.features[i], Region):
                        raise ValueError(f"Event '{ev.id}' scope references unknown region '{i}'")
                elif group == "scalar_features":
                    if i not in g.features or not isinstance(g.features[i], ScalarFeature):
                        raise ValueError(f"Event '{ev.id}' scope references unknown scalar feature '{i}'")
                elif group == "features":
                    if i not in g.features:
                        raise ValueError(f"Event '{ev.id}' scope references unknown feature '{i}'")

    for node in g.features.values():
        for obs_id in node.observation_ids:
            obs = g.geo_observations.get(obs_id)
            if obs is None:
                raise ValueError(f"Node '{node.id}' references unknown observation set '{obs_id}'")
            if obs.target != node.id:
                raise ValueError(
                    f"Node '{node.id}' references observation set '{obs_id}' targeted at '{obs.target}'"
                )


def validate_basement(g: GeologicalModelGraph) -> None:
    if g.basement is not None:
        if g.basement not in g.features:
            raise ValueError(f"Basement unit '{g.basement}' not found in features")
        if not isinstance(g.features[g.basement], Unit):
            raise ValueError(f"Basement '{g.basement}' must be a unit")

        for rel in g.relations:
            if rel.kind == "overlies" and rel.src == g.basement:
                raise ValueError(
                    f"Basement unit '{g.basement}' cannot overlie anything (found basement overlies '{rel.dst}')"
                )


def validate_unconformities_and_scalar_features(g: GeologicalModelGraph) -> None:
    valid_unconformity_types = {"erosional", "angular", "onlap", "disconformity"}
    for feature in g.features.values():
        if isinstance(feature, Unconformity):
            if feature.unconformity_type not in valid_unconformity_types:
                raise ValueError(
                    f"Unconformity '{feature.id}' has unsupported unconformity_type '{feature.unconformity_type}'"
                )

    strat_graph = {}
    for rel in g.relations:
        if rel.kind == "overlies":
            if rel.attrs.get("generated_by") == "auto_strat_order":
                continue
            strat_graph.setdefault(rel.src, set()).add(rel.dst)
            strat_graph.setdefault(rel.dst, set())

    scalar_to_units = {}
    for fid, feature in g.features.items():
        if isinstance(feature, Unit):
            rep = feature.representation
            if rep is not None:
                scalar_to_units.setdefault(rep.scalar_feature_id, set()).add(fid)

    unconformities_in_graph = {
        fid for fid, feat in g.features.items() if isinstance(feat, Unconformity)
    }

    for scalar_id, unit_ids in scalar_to_units.items():
        if len(unit_ids) < 2:
            continue

        scalar = g.features.get(scalar_id)
        if isinstance(scalar, ScalarFeature) and scalar.role != "stratigraphic":
            continue

        for unit1 in unit_ids:
            for unit2 in unit_ids:
                if unit1 == unit2:
                    continue

                path = _find_stratigraphic_path(strat_graph, unit1, unit2)
                if not path:
                    continue

                for node in path:
                    if node in unconformities_in_graph:
                        unconformity = g.features[node]
                        scalar_name = scalar.name if isinstance(scalar, ScalarFeature) else scalar_id
                        raise ValueError(
                            f"Units '{unit1}' and '{unit2}' share scalar feature '{scalar_name}' "
                            f"but are separated by unconformity '{unconformity.name}'."
                        )


def _find_stratigraphic_path(graph: dict, start: str, end: str) -> list:
    if start not in graph or end not in graph:
        return []

    queue = [(start, [start])]
    visited = {start}

    while queue:
        node, path = queue.pop(0)
        if node == end:
            return path

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return []


def validate_all(g: GeologicalModelGraph, *, enforce_unconformity_scalar_separation: bool = True) -> None:
    validate_references_exist(g)
    validate_stratigraphic_dag(g)
    validate_scalar_source_configuration(g)
    validate_topological_relation_params(g)
    validate_unit_representations(g)
    validate_basement(g)
    if enforce_unconformity_scalar_separation:
        validate_unconformities_and_scalar_features(g)
