from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, PrivateAttr

from .common import Id, ModelSpace, UncertaintySpec
from .features import FeatureNode, Fault, Fold, Intrusion, Region, ScalarFeature, Unconformity, Unit, UnitRepresentation
from .observations import GeologicalObservationSet
from .relations import Event, Relation


class GeologicalModelGraph(BaseModel):
    schema_version: str = "0.3.0"
    name: str
    space: ModelSpace
    features: Dict[Id, FeatureNode] = Field(default_factory=dict)
    geo_observations: Dict[Id, GeologicalObservationSet] = Field(default_factory=dict)
    relations: List[Relation] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    basement: Optional[Id] = None

    _auto_overlies_units: bool = PrivateAttr(default=True)
    _validate_on_edit: bool = PrivateAttr(default=True)
    _strat_add_order: list[str] = PrivateAttr(default_factory=list)
    _active_faults: list[str] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        self._sync_node_observations()

    @classmethod
    def create(
        cls,
        name: str,
        crs: str,
        bbox: list[float],
        units: str = "m",
        auto_overlies_units: bool = True,
        validate_on_edit: bool = True,
    ) -> "GeologicalModelGraph":
        g = cls(name=name, space=ModelSpace(crs=crs, bbox=tuple(bbox), units=units))
        g._auto_overlies_units = auto_overlies_units
        g._validate_on_edit = validate_on_edit
        return g

    def set_edit_options(
        self,
        *,
        auto_overlies_units: bool | None = None,
        validate_on_edit: bool | None = None,
    ) -> None:
        if auto_overlies_units is not None:
            self._auto_overlies_units = auto_overlies_units
        if validate_on_edit is not None:
            self._validate_on_edit = validate_on_edit

    def _snapshot(self) -> dict[str, Any]:
        return {
            "features": deepcopy(self.features),
            "geo_observations": deepcopy(self.geo_observations),
            "relations": deepcopy(self.relations),
            "events": deepcopy(self.events),
            "basement": deepcopy(self.basement),
            "_strat_add_order": deepcopy(self._strat_add_order),
            "_active_faults": deepcopy(self._active_faults),
        }

    def _restore(self, snapshot: dict[str, Any]) -> None:
        self.features = snapshot["features"]
        self.geo_observations = snapshot["geo_observations"]
        self.relations = snapshot["relations"]
        self.events = snapshot["events"]
        self.basement = snapshot["basement"]
        self._strat_add_order = snapshot["_strat_add_order"]
        self._active_faults = snapshot["_active_faults"]

    def _mutate(self, op):
        snapshot = self._snapshot()
        try:
            result = op()
            if self._validate_on_edit:
                from .. import validation

                validation.validate_all(self, enforce_unconformity_scalar_separation=False)
            return result
        except Exception:
            self._restore(snapshot)
            raise

    def _get_node(self, node_id: str) -> FeatureNode | None:
        return self.features.get(node_id)

    def _sync_node_observations(self) -> None:
        for node in self.features.values():
            node.observation_ids = []

        for obs_id, observation in self.geo_observations.items():
            node = self._get_node(observation.target)
            if node is not None and obs_id not in node.observation_ids:
                node.observation_ids.append(obs_id)

    def _unique(self, base: str) -> str:
        i = 1
        new = base
        while new in self.features or new in self.geo_observations:
            i += 1
            new = f"{base}_{i}"
        return new

    def _ensure_relation(self, kind: str, src: str, dst: str, **attrs) -> None:
        relation_param_keys = {
            "erosion_params",
            "angular_unconformity_params",
            "onlap_params",
            "disconformity_params",
        }
        relation_kwargs = {k: attrs.pop(k) for k in relation_param_keys if k in attrs}

        for rel in self.relations:
            if rel.kind == kind and rel.src == src and rel.dst == dst:
                if attrs:
                    rel.attrs.update(attrs)
                for key, value in relation_kwargs.items():
                    setattr(rel, key, value)
                return
        self.relations.append(
            Relation(kind=kind, src=src, dst=dst, attrs=attrs, **relation_kwargs)
        )

    def _apply_active_faults(self, feature_id: str) -> None:
        if not self._auto_overlies_units:
            return
        for fault_id in self._active_faults:
            self._ensure_relation("displaces", fault_id, feature_id, generated_by="auto_fault_order")

    def _summary(self) -> str:
        feature_counts = {
            "unit": 0,
            "fault": 0,
            "fold": 0,
            "unconformity": 0,
            "intrusion": 0,
            "region": 0,
            "scalar_feature": 0,
        }
        for feature in self.features.values():
            if feature.type in feature_counts:
                feature_counts[feature.type] += 1

        basement = self.basement if self.basement is not None else "None"
        return (
            f"GeologicalModelGraph(name='{self.name}', crs='{self.space.crs}', auto_overlies_units={self._auto_overlies_units}, validate_on_edit={self._validate_on_edit})\n"
            f"  features: {len(self.features)} "
            f"(units={feature_counts['unit']}, faults={feature_counts['fault']}, folds={feature_counts['fold']}, "
            f"unconformities={feature_counts['unconformity']}, intrusions={feature_counts['intrusion']}, "
            f"regions={feature_counts['region']}, scalar_features={feature_counts['scalar_feature']})\n"
            f"  geo_observations: {len(self.geo_observations)}\n"
            f"  relations: {len(self.relations)}\n"
            f"  events: {len(self.events)}\n"
            f"  basement: {basement}"
        )

    def __str__(self) -> str:
        return self._summary()

    def __repr__(self) -> str:
        return self._summary()

    def scalar_features(self, role: str | None = None) -> Dict[Id, ScalarFeature]:
        out = {fid: feat for fid, feat in self.features.items() if isinstance(feat, ScalarFeature)}
        if role is None:
            return out
        return {fid: feat for fid, feat in out.items() if feat.role == role}

    def add_scalar_feature(
        self,
        name: str,
        *,
        role: str = "custom",
        source: Dict[str, Any] | None = None,
        hints: Dict[str, Any] | None = None,
        **attrs,
    ) -> str:
        def op() -> str:
            sid = self._unique(name)
            source_payload = source or {
                "kind": "parametric",
                "field_type": "flat",
                "params": {
                    "origin": (0.0, 0.0, 0.0),
                    "normal": (0.0, 0.0, 1.0),
                    "amplitude": 1.0,
                },
            }
            sf = ScalarFeature(
                id=sid,
                name=name,
                role=role,
                source=source_payload,
                hints=hints or {},
                attrs=attrs,
                type="scalar_feature",
            )
            self.features[sid] = sf
            return sid

        return self._mutate(op)

    def add_unit(self, name: str, representation: Dict[str, Any] | None = None, **attrs) -> str:
        def op() -> str:
            uid = self._unique(name)
            rep = UnitRepresentation(**representation) if representation is not None else None

            unit = Unit(id=uid, name=name, representation=rep, attrs=attrs, type="unit")
            self.features[uid] = unit
            if self._auto_overlies_units and self._strat_add_order:
                previous_strat_id = self._strat_add_order[-1]
                self._ensure_relation("overlies", previous_strat_id, uid, generated_by="auto_strat_order")
            self._apply_active_faults(uid)
            self._strat_add_order.append(uid)

            if rep is not None:
                self._ensure_relation("uses_scalar", uid, rep.scalar_feature_id)
            return uid

        return self._mutate(op)

    def add_fault(self, name: str, indicator_scalar_id: str | None = None, **attrs) -> str:
        def op() -> str:
            fid = self._unique(name)
            self.features[fid] = Fault(
                id=fid,
                name=name,
                indicator_scalar_id=indicator_scalar_id,
                attrs=attrs,
                type="fault",
            )
            if indicator_scalar_id is not None:
                self._ensure_relation("uses_scalar", fid, indicator_scalar_id)
            if self._auto_overlies_units:
                self._active_faults.append(fid)
            return fid

        return self._mutate(op)

    def add_fold(self, name: str, frame_scalar_ids: List[str] | None = None, **attrs) -> str:
        def op() -> str:
            fid = self._unique(name)
            frame_ids = frame_scalar_ids or []
            self.features[fid] = Fold(id=fid, name=name, frame_scalar_ids=frame_ids, attrs=attrs, type="fold")
            for scalar_id in frame_ids:
                self._ensure_relation("uses_scalar", fid, scalar_id)
            return fid

        return self._mutate(op)

    def add_unconformity(
        self,
        name: str,
        kind: str = "erosional",
        unconformity_type: str | None = None,
        scalar_feature_id: str | None = None,
        geometry_params: Dict[str, Any] | None = None,
        **attrs,
    ) -> str:
        def _create_unconformity(unconformity_name: str, final_type: str) -> str:
            uid = self._unique(unconformity_name)
            self.features[uid] = Unconformity(
                id=uid,
                name=unconformity_name,
                unconformity_type=final_type,
                kind=final_type,
                scalar_feature_id=scalar_feature_id,
                geometry_params=geometry_params or {},
                attrs=attrs,
                type="unconformity",
            )
            if scalar_feature_id is not None:
                self._ensure_relation("uses_scalar", uid, scalar_feature_id)
            if self._auto_overlies_units and self._strat_add_order:
                previous_strat_id = self._strat_add_order[-1]
                self._ensure_relation("overlies", previous_strat_id, uid, generated_by="auto_strat_order")
            self._apply_active_faults(uid)
            self._strat_add_order.append(uid)
            return uid

        def op() -> str:
            final_type = unconformity_type or kind
            return _create_unconformity(name, final_type)

        return self._mutate(op)

    def add_angular_unconformity(
        self,
        name: str,
        *,
        below_unit_id: str,
        above_unit_id: str,
        angle_degrees: float,
        younging_direction: str = "up",
        tilt_phase: str = "post",
        scalar_feature_id: str | None = None,
        **attrs,
    ) -> str:
        def op() -> str:
            unconformity_id = self._unique(name)
            self.features[unconformity_id] = Unconformity(
                id=unconformity_id,
                name=name,
                unconformity_type="angular",
                kind="angular",
                scalar_feature_id=scalar_feature_id,
                geometry_params={
                    "angle_degrees": angle_degrees,
                    "younging_direction": younging_direction,
                    "tilt_phase": tilt_phase,
                },
                attrs=attrs,
                type="unconformity",
            )
            if scalar_feature_id is not None:
                self._ensure_relation("uses_scalar", unconformity_id, scalar_feature_id)

            self._ensure_relation(
                "erodes",
                unconformity_id,
                below_unit_id,
                angular_unconformity_params={
                    "angle_degrees": angle_degrees,
                    "younging_direction": younging_direction,
                    "tilt_phase": tilt_phase,
                },
                generated_by="add_angular_unconformity",
            )
            self._ensure_relation(
                "overlies",
                above_unit_id,
                unconformity_id,
                generated_by="add_angular_unconformity",
            )
            self._strat_add_order.append(unconformity_id)
            return unconformity_id

        return self._mutate(op)

    def add_erosional_unconformity(
        self,
        name: str,
        *,
        eroded_unit_ids: List[str],
        depth_range: tuple[float, float] | None = None,
        style: str = "truncation",
        dip_angle: float | None = None,
        scalar_feature_id: str | None = None,
        **attrs,
    ) -> str:
        def op() -> str:
            unconformity_id = self._unique(name)
            self.features[unconformity_id] = Unconformity(
                id=unconformity_id,
                name=name,
                unconformity_type="erosional",
                kind="erosional",
                scalar_feature_id=scalar_feature_id,
                geometry_params={
                    "depth_range": depth_range,
                    "style": style,
                    "dip_angle": dip_angle,
                },
                attrs=attrs,
                type="unconformity",
            )
            if scalar_feature_id is not None:
                self._ensure_relation("uses_scalar", unconformity_id, scalar_feature_id)

            for unit_id in eroded_unit_ids:
                self._ensure_relation(
                    "erodes",
                    unconformity_id,
                    unit_id,
                    erosion_params={
                        "depth_range": depth_range,
                        "style": style,
                        "dip_angle": dip_angle,
                    },
                    generated_by="add_erosional_unconformity",
                )
            self._strat_add_order.append(unconformity_id)
            return unconformity_id

        return self._mutate(op)

    def add_intrusion(self, name: str, **attrs) -> str:
        def op() -> str:
            iid = self._unique(name)
            self.features[iid] = Intrusion(id=iid, name=name, attrs=attrs, type="intrusion")
            return iid

        return self._mutate(op)

    def add_region(self, name: str, geometry: Dict[str, Any], **attrs) -> str:
        def op() -> str:
            rid = self._unique(name)
            self.features[rid] = Region(id=rid, name=name, geometry=geometry, attrs=attrs, type="region")
            return rid

        return self._mutate(op)

    def add_geological_observation_set(
        self,
        *,
        kind: str,
        target: str,
        uri: str,
        columns: Dict[str, str] | None = None,
        uncertainty: Dict[str, Any] | None = None,
        weight: float = 1.0,
        region: str | None = None,
        count: int | None = None,
        **meta,
    ) -> str:
        def op() -> str:
            node = self._get_node(target)
            if node is None:
                raise ValueError(f"Observation target '{target}' not found in model nodes")

            oid = self._unique(f"gobs_{kind}")
            obs = GeologicalObservationSet(
                id=oid,
                kind=kind,
                target=target,
                uri=uri,
                columns=columns or {},
                uncertainty=UncertaintySpec(**uncertainty) if uncertainty else None,
                weight=weight,
                region=region,
                count=count,
                meta=meta,
            )
            self.geo_observations[oid] = obs
            node.observation_ids.append(oid)
            return oid

        return self._mutate(op)

    def node_observations(self, node_id: str) -> Dict[Id, GeologicalObservationSet]:
        node = self._get_node(node_id)
        if node is None:
            raise KeyError(f"Node '{node_id}' not found in model")

        return {
            obs_id: self.geo_observations[obs_id]
            for obs_id in node.observation_ids
            if obs_id in self.geo_observations
        }

    def overlies(self, younger: str, older: str, **attrs) -> None:
        def op() -> None:
            explicit_attrs = {"generated_by": "manual"}
            explicit_attrs.update(attrs)
            self._ensure_relation("overlies", younger, older, **explicit_attrs)

        self._mutate(op)

    def relate(self, kind: str, src: str, dst: str, **attrs) -> None:
        def op() -> None:
            relation_param_keys = {
                "erosion_params",
                "angular_unconformity_params",
                "onlap_params",
                "disconformity_params",
            }
            relation_kwargs = {k: attrs.pop(k) for k in relation_param_keys if k in attrs}
            self.relations.append(Relation(kind=kind, src=src, dst=dst, attrs=attrs, **relation_kwargs))

        self._mutate(op)

    def remove_relation(self, kind: str, src: str, dst: str) -> int:
        def op() -> int:
            before = len(self.relations)
            self.relations = [
                rel
                for rel in self.relations
                if not (rel.kind == kind and rel.src == src and rel.dst == dst)
            ]
            return before - len(self.relations)

        return self._mutate(op)

    def remove_overlies(self, younger: str, older: str) -> int:
        return self.remove_relation("overlies", younger, older)

    def edit_relation(
        self,
        kind: str,
        src: str,
        dst: str,
        *,
        new_src: str | None = None,
        new_dst: str | None = None,
        attrs: Dict[str, Any] | None = None,
    ) -> bool:
        def op() -> bool:
            for rel in self.relations:
                if rel.kind == kind and rel.src == src and rel.dst == dst:
                    if new_src is not None:
                        rel.src = new_src
                    if new_dst is not None:
                        rel.dst = new_dst
                    if attrs is not None:
                        rel.attrs = attrs
                    return True
            return False

        return self._mutate(op)

    def edit_overlies(
        self,
        younger: str,
        older: str,
        *,
        new_younger: str | None = None,
        new_older: str | None = None,
        attrs: Dict[str, Any] | None = None,
    ) -> bool:
        return self.edit_relation(
            "overlies",
            younger,
            older,
            new_src=new_younger,
            new_dst=new_older,
            attrs=attrs,
        )

    def add_event(self, *, feature: str, order: int, scope: Dict[str, list[str]] | None = None) -> str:
        def op() -> str:
            eid = self._unique("ev")
            self.events.append(Event(id=eid, feature=feature, order=order, scope=scope or {}))
            return eid

        return self._mutate(op)

    def add_fold_event(
        self,
        *,
        fold: str,
        order: int,
        units: List[str] | None = None,
        scalar_features: List[str] | None = None,
        regions: List[str] | None = None,
        attrs: Dict[str, Any] | None = None,
    ) -> str:
        def op() -> str:
            fold_node = self.features.get(fold)
            if fold_node is None:
                raise ValueError(f"Fold '{fold}' not found in model")
            if not isinstance(fold_node, Fold):
                raise ValueError(f"Feature '{fold}' is not a fold")

            scope: Dict[str, List[str]] = {}
            if units:
                scope["units"] = list(units)
            if scalar_features:
                scope["scalar_features"] = list(scalar_features)
            if regions:
                scope["regions"] = list(regions)

            event_id = self._unique("ev")
            self.events.append(Event(id=event_id, feature=fold, order=order, scope=scope))

            rel_attrs = {"event_id": event_id, "event_order": order}
            if attrs:
                rel_attrs.update(attrs)

            targets: list[str] = []
            for key in ("units", "scalar_features", "regions"):
                targets.extend(scope.get(key, []))

            for target in targets:
                self._ensure_relation("folds", fold, target, **rel_attrs)

            return event_id

        return self._mutate(op)

    def fold_history(self, node_id: str, as_names: bool = True) -> List[str]:
        node = self._get_node(node_id)
        if node is None:
            raise KeyError(f"Node '{node_id}' not found in model")

        target_ids = {node_id}
        if isinstance(node, Unit) and node.representation is not None:
            target_ids.add(node.representation.scalar_feature_id)

        fold_order: Dict[str, int | None] = {}

        for rel in self.relations:
            if rel.kind != "folds" or rel.dst not in target_ids:
                continue
            fold_node = self.features.get(rel.src)
            if not isinstance(fold_node, Fold):
                continue
            rel_order = rel.attrs.get("event_order")
            rel_order = rel_order if isinstance(rel_order, int) else None
            prev = fold_order.get(rel.src)
            if prev is None or (rel_order is not None and rel_order < prev):
                fold_order[rel.src] = rel_order

        for event in self.events:
            fold_node = self.features.get(event.feature)
            if not isinstance(fold_node, Fold):
                continue

            scoped_ids: set[str] = set()
            for key in ("units", "scalar_features", "regions", "features"):
                scoped_ids.update(event.scope.get(key, []))

            if scoped_ids.intersection(target_ids):
                prev = fold_order.get(event.feature)
                if prev is None or event.order < prev:
                    fold_order[event.feature] = event.order

        ordered = sorted(
            fold_order.items(),
            key=lambda item: (item[1] if item[1] is not None else 10**9, item[0]),
        )
        fold_ids = [fid for fid, _ in ordered]
        if as_names:
            return [self.features[fid].name for fid in fold_ids]
        return fold_ids

    def set_basement(self, unit_id: str) -> None:
        def op() -> None:
            if unit_id not in self.features:
                raise ValueError(f"Unit '{unit_id}' not found in model")
            if not isinstance(self.features[unit_id], Unit):
                raise ValueError(f"Feature '{unit_id}' is not a unit")
            self.basement = unit_id

        self._mutate(op)

    def validate_all(self) -> None:
        from .. import validation

        validation.validate_all(self, enforce_unconformity_scalar_separation=True)

    def build(self) -> "GeologicalModelGraph":
        self.validate_all()
        return self

    def save(self, path: str) -> None:
        import json

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)

    def save_yaml(self, path: str) -> None:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required for YAML support. Install with: pip install pyyaml") from exc

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.model_dump(mode="json"), f, sort_keys=False)

    @classmethod
    def load(cls, path: str) -> "GeologicalModelGraph":
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)

    @classmethod
    def load_yaml(cls, path: str) -> "GeologicalModelGraph":
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required for YAML support. Install with: pip install pyyaml") from exc

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required for YAML support. Install with: pip install pyyaml") from exc
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_text: str) -> "GeologicalModelGraph":
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required for YAML support. Install with: pip install pyyaml") from exc
        data = yaml.safe_load(yaml_text)
        return cls.model_validate(data)

    def visualize(self, **kwargs):
        from .. import visualization

        return visualization.visualize_topology(self, **kwargs)

    def to_networkx(self, **kwargs):
        from .. import visualization

        return visualization.to_networkx(self, **kwargs)

    def print_summary(self) -> None:
        from .. import visualization

        visualization.print_topology_summary(self)

    def stratigraphic_order(self, as_names: bool = True, include_unconformities: bool = False) -> list[str]:
        keep_types = {"unit"}
        if include_unconformities:
            keep_types.add("unconformity")

        nodes = {fid for fid, feat in self.features.items() if feat.type in keep_types}

        adj = {n: set() for n in nodes}
        indeg = {n: 0 for n in nodes}

        for rel in self.relations:
            if rel.kind != "overlies":
                continue
            if rel.src in nodes and rel.dst in nodes and rel.dst not in adj[rel.src]:
                adj[rel.src].add(rel.dst)
                indeg[rel.dst] += 1

        queue = [n for n, degree in indeg.items() if degree == 0]
        order: list[str] = []

        while queue:
            n = queue.pop()
            order.append(n)
            for v in adj[n]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    queue.append(v)

        if len(order) != len(nodes):
            raise ValueError("Cannot compute stratigraphic order because 'overlies' contains a cycle")

        if as_names:
            return [self.features[fid].name for fid in order]
        return order

    def print_stratigraphic_column(self, include_unconformities: bool = False) -> None:
        order_ids = self.stratigraphic_order(as_names=False, include_unconformities=include_unconformities)
        print("\nStratigraphic Column (youngest -> oldest)")
        print("-" * 44)
        if not order_ids:
            print("(no stratigraphic features)")
            return
        i = 1
        for fid in order_ids:
            feat = self.features[fid]
            if feat.type == "unconformity":
                marker = "~" * 11
                print(f"{marker} {feat.name} {marker}")
                continue
            print(f"{i:>2}. {feat.name} [{feat.type}] ({fid})")
            i += 1
