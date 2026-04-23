from __future__ import annotations

import numpy as np

from .basebuilder import BaseBuilder, MergedLinkedInput


class StratigraphyBuilder(BaseBuilder):
    """Build stratigraphy features according to model interpolation strategy."""

    def build(self, task_payload: dict) -> object | None:
        if self._grouped_mode_enabled():
            return self._build_grouped_conformable(task_payload)
        linked_data = task_payload.get("linked_data")
        return self.build_from_linked_data(linked_data)

    def _grouped_mode_enabled(self) -> bool:
        strategy = getattr(self.model, "interpolation_strategy", "independent")
        return str(strategy).strip().lower() == "grouped_conformable"

    def _build_grouped_conformable(self, task_payload: dict) -> object | None:
        feature_id = task_payload.get("feature_id")
        if feature_id is None:
            return self.build_from_linked_data(task_payload.get("linked_data"))

        group_key, group_members = self._grouped_conformable_members(feature_id)
        if not group_members:
            return self.build_from_linked_data(task_payload.get("linked_data"))

        cache = getattr(self.model, "_grouped_unit_build_cache", None)
        if cache is None:
            cache = {}
            self.model._grouped_unit_build_cache = cache
        if group_key in cache:
            return cache[group_key]

        linked_by_feature = self.model._linker.build_inputs_by_feature(group_members)
        merged = self._merge_linked_inputs(group_members, linked_by_feature)
        result = self.build_from_linked_data(merged)
        cache[group_key] = result
        return result

    def _grouped_conformable_members(self, feature_id: str) -> tuple[str, list[str]]:
        dag = self.model.schema.dag
        features = getattr(self.model.schema, "features", {})

        stack = [feature_id]
        visited = set()
        grouped_members = set()

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)

            feature = features.get(current)
            if feature is None:
                continue
            if self._normalize_feature_type(feature) not in {"unit", "geologicalunit"}:
                continue
            grouped_members.add(current)

            neighbors = list(dag.predecessors(current)) + list(dag.successors(current))
            for neighbor in neighbors:
                edge = dag.get_edge_data(current, neighbor)
                if edge is None:
                    edge = dag.get_edge_data(neighbor, current)
                relation = self.normalize_relation(None if edge is None else edge.get("relation"))
                if relation == "overlies":
                    stack.append(neighbor)

        members = sorted(grouped_members)
        return ("grouped_conformable:" + "|".join(members), members)

    @staticmethod
    def _normalize_feature_type(feature) -> str:
        return type(feature).__name__.strip().lower()

    @staticmethod
    def _merge_linked_inputs(feature_ids: list[str], linked_by_feature: dict) -> MergedLinkedInput:
        first = linked_by_feature[feature_ids[0]]

        point_blocks: list[np.ndarray] = []
        gradient_blocks: list[np.ndarray] = []
        tangent_blocks: list[np.ndarray] = []
        by_role: dict[str, list] = {}
        missing_ids: list[str] = []

        for feature_id in feature_ids:
            linked = linked_by_feature[feature_id]
            if linked.point_constraints.shape[0] > 0:
                point_blocks.append(linked.point_constraints)
            if linked.gradient_constraints.shape[0] > 0:
                gradient_blocks.append(linked.gradient_constraints)
            if linked.tangent_constraints.shape[0] > 0:
                tangent_blocks.append(linked.tangent_constraints)

            for role, observations in linked.by_role.items():
                by_role.setdefault(role, []).extend(observations)

            missing_ids.extend(linked.missing_observation_ids)

        return MergedLinkedInput(
            feature_id=f"group:{'|'.join(feature_ids)}",
            feature_name=f"group:{'|'.join(feature_ids)}",
            feature_type=first.feature_type,
            point_constraints=(
                np.vstack(point_blocks) if point_blocks else np.empty((0, 3), dtype=float)
            ),
            gradient_constraints=(
                np.vstack(gradient_blocks) if gradient_blocks else np.empty((0, 6), dtype=float)
            ),
            tangent_constraints=(
                np.vstack(tangent_blocks) if tangent_blocks else np.empty((0, 6), dtype=float)
            ),
            by_role=by_role,
            missing_observation_ids=missing_ids,
        )
        pass
