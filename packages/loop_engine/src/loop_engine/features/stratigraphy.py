from __future__ import annotations

from collections import defaultdict
import numpy as np
from loop_interpolation.constraints import GradientConstraint, InequalityConstraint, ValueConstraint

from .basebuilder import BaseBuilder, MergedLinkedInput, PreparedConstraints


class StratigraphyBuilder(BaseBuilder):
    """Build stratigraphy features according to model interpolation strategy."""

    def prepare_constraints(
        self, linked_data, build_params: dict | None = None
    ) -> PreparedConstraints:
        prepared = self._prepare_generic_constraints(linked_data)
        by_role = getattr(linked_data, "by_role", {}) if linked_data is not None else {}

        gradient_rows = self.coords_vectors_from_linked_observations(by_role.get("gradient", []))
        if gradient_rows.shape[0] > 0:
            prepared.gradient_constraints = self._to_gradient_constraint(
                gradient_rows,
                is_normal=False,
            )

            # When an explicit gradient role is present, normals come from orientation only.
            orientation_rows = self.coords_vectors_from_linked_observations(
                by_role.get("orientation", [])
            )
            if orientation_rows.shape[0] > 0:
                prepared.normal_constraints = self._to_gradient_constraint(
                    orientation_rows,
                    is_normal=True,
                )
            else:
                prepared.normal_constraints = GradientConstraint(is_normal=True)

        return prepared

    def build(self, task_payload: dict) -> object | None:
        interpretation = task_payload.get("interpretation") or {}
        mode = self._resolve_mode(interpretation)

        if mode == "shared_scalar_field":
            return self._build_shared_scalar_field(task_payload, interpretation)
        if mode == "linked_scalar_fields":
            return self._build_linked_scalar_fields(task_payload, interpretation)

        linked_data = task_payload.get("linked_data")
        return self.build_from_linked_data(linked_data)

    def _resolve_mode(self, interpretation: dict) -> str:
        if interpretation.get("mode") is not None:
            mode = str(interpretation.get("mode")).strip().lower()
        else:
            mode = self._legacy_mode()

        aliases = {
            "grouped_conformable": "shared_scalar_field",
            "grouped": "shared_scalar_field",
            "single": "shared_scalar_field",
            "single_scalar": "shared_scalar_field",
            "single_scalar_field": "shared_scalar_field",
            "linked": "linked_scalar_fields",
        }
        return aliases.get(mode, mode)

    def _legacy_mode(self) -> str:
        strategy = getattr(self.model, "interpolation_strategy", "independent")
        if isinstance(strategy, dict):
            return str(strategy.get("mode", "independent")).strip().lower()
        return str(strategy).strip().lower()

    def _build_shared_scalar_field(self, task_payload: dict, interpretation: dict) -> object | None:
        feature_id = task_payload.get("feature_id")
        if feature_id is None:
            return self.build_from_linked_data(task_payload.get("linked_data"))

        series_members = interpretation.get("series_members") or [feature_id]
        if not series_members:
            return self.build_from_linked_data(task_payload.get("linked_data"))
        series_key = interpretation.get("series_key") or ("series:" + "|".join(series_members))

        cache = getattr(self.model, "_grouped_unit_build_cache", None)
        if cache is None:
            cache = {}
            self.model._grouped_unit_build_cache = cache
        cache_key = f"shared_scalar_field:{series_key}"
        if cache_key in cache:
            return cache[cache_key]

        linked_by_feature = self.model._linker.build_inputs_by_feature(series_members)
        merged = self._merge_linked_inputs(series_members, linked_by_feature)
        prepared = self.prepare_constraints(merged, build_params={})

        value_constraints = self._series_value_constraints(
            series_members=series_members,
            linked_by_feature=linked_by_feature,
            interpretation=interpretation,
        )
        if value_constraints.points.shape[0] > 0:
            prepared.value_constraints = value_constraints

        feature = task_payload.get("feature")
        build_params = getattr(feature, "build_params", {}) or {}
        result = self.build_from_constraints(
            linked_data=merged,
            prepared=prepared,
            build_params=build_params,
        )
        cache[cache_key] = result
        return result

    def _build_linked_scalar_fields(self, task_payload: dict, interpretation: dict) -> object | None:
        linked_data = task_payload.get("linked_data")
        feature = task_payload.get("feature")
        build_params = getattr(feature, "build_params", {}) or {}

        prepared = self.prepare_constraints(linked_data, build_params)

        parallel_normals = self._parallelism_normal_constraints(interpretation)
        prepared.normal_constraints = self._merge_gradient_constraints(
            prepared.normal_constraints,
            parallel_normals,
            is_normal=True,
        )

        linked_constraints = self._linked_inequality_constraints(interpretation)
        prepared.inequality_constraints = self._merge_inequality_constraints(
            prepared.inequality_constraints,
            linked_constraints,
        )
        return self.build_from_constraints(
            linked_data=linked_data,
            prepared=prepared,
            build_params=build_params,
        )

    def _series_value_constraints(
        self,
        series_members: list[str],
        linked_by_feature: dict,
        interpretation: dict,
    ) -> ValueConstraint:
        basal_map = interpretation.get("series_basal_isovalues", {}) or {}
        top_map = interpretation.get("series_top_isovalues", {}) or {}
        scalar_increment = float(interpretation.get("scalar_increment", 1.0))

        points_blocks: list[np.ndarray] = []
        value_blocks: list[np.ndarray] = []

        for rank, member_id in enumerate(series_members):
            linked_data = linked_by_feature.get(member_id)
            if linked_data is None:
                continue

            basal_value = float(basal_map.get(member_id, rank * scalar_increment))
            top_value = float(top_map.get(member_id, basal_value + scalar_increment))

            basal_points = self.coords_from_linked_observations(
                getattr(linked_data, "by_role", {}).get("basal", [])
            )
            if basal_points.shape[0] > 0:
                points_blocks.append(basal_points)
                value_blocks.append(np.full(basal_points.shape[0], basal_value))

            top_points = self.coords_from_linked_observations(
                getattr(linked_data, "by_role", {}).get("top", [])
            )
            if top_points.shape[0] > 0:
                points_blocks.append(top_points)
                value_blocks.append(np.full(top_points.shape[0], top_value))

            if basal_points.shape[0] == 0 and top_points.shape[0] == 0:
                generic_points, _, _ = self._extract_constraint_arrays(linked_data)
                if generic_points.shape[0] > 0:
                    points_blocks.append(generic_points)
                    value_blocks.append(np.full(generic_points.shape[0], basal_value))

        if not points_blocks:
            return ValueConstraint()
        return ValueConstraint(points=np.vstack(points_blocks), values=np.concatenate(value_blocks))

    def _linked_inequality_constraints(self, interpretation: dict) -> InequalityConstraint:
        overlying_units = interpretation.get("overlying_units") or []
        underlying_units = interpretation.get("underlying_units") or []
        link_margin = float(interpretation.get("link_margin", 0.05))
        link_bound = float(interpretation.get("link_bound", 1.0e6))
        parallel_tolerance = interpretation.get("parallel_tolerance", None)
        bounded_upper = link_bound
        if parallel_tolerance is not None:
            bounded_upper = max(link_margin + float(parallel_tolerance), link_margin + 1.0e-6)

        points_blocks: list[np.ndarray] = []
        bounds_blocks: list[np.ndarray] = []

        for unit_id in underlying_units:
            neighbour_input = self.model._linker.build_feature_input(unit_id)
            basal_points = self.coords_from_linked_observations(
                getattr(neighbour_input, "by_role", {}).get("basal", [])
            )
            if basal_points.shape[0] == 0:
                continue
            points_blocks.append(basal_points)
            bounds_blocks.append(
                np.column_stack(
                    [
                        np.full(basal_points.shape[0], link_margin),
                        np.full(basal_points.shape[0], bounded_upper),
                    ]
                )
            )

        for unit_id in overlying_units:
            neighbour_input = self.model._linker.build_feature_input(unit_id)
            basal_points = self.coords_from_linked_observations(
                getattr(neighbour_input, "by_role", {}).get("basal", [])
            )
            if basal_points.shape[0] == 0:
                continue
            points_blocks.append(basal_points)
            bounds_blocks.append(
                np.column_stack(
                    [
                        np.full(basal_points.shape[0], -bounded_upper),
                        np.full(basal_points.shape[0], -link_margin),
                    ]
                )
            )

        if not points_blocks:
            return InequalityConstraint()
        return InequalityConstraint(points=np.vstack(points_blocks), bounds=np.vstack(bounds_blocks))

    def _parallelism_normal_constraints(self, interpretation: dict) -> GradientConstraint:
        enforce = bool(interpretation.get("enforce_parallelism", False))
        weight = float(interpretation.get("parallelism_weight", 1.0))
        if not enforce or weight <= 0.0:
            return GradientConstraint(is_normal=True)

        neighbour_ids = list(interpretation.get("overlying_units") or []) + list(
            interpretation.get("underlying_units") or []
        )
        if not neighbour_ids:
            return GradientConstraint(is_normal=True)

        neighbour_rows: list[np.ndarray] = []
        for unit_id in neighbour_ids:
            neighbour_input = self.model._linker.build_feature_input(unit_id)
            orientation_rows = self.coords_vectors_from_linked_observations(
                getattr(neighbour_input, "by_role", {}).get("orientation", [])
            )
            if orientation_rows.shape[0] > 0:
                neighbour_rows.append(orientation_rows)

        if not neighbour_rows:
            return GradientConstraint(is_normal=True)

        merged_rows = np.vstack(neighbour_rows)
        normalized = self._normalize_xyz_vectors(merged_rows)
        if normalized.shape[0] == 0:
            return GradientConstraint(is_normal=True)

        return GradientConstraint(
            points=normalized[:, :3],
            vectors=normalized[:, 3:6],
            weights=weight,
            is_normal=True,
        )

    @staticmethod
    def _merge_gradient_constraints(
        current: GradientConstraint,
        extra: GradientConstraint,
        is_normal: bool,
    ) -> GradientConstraint:
        if current.points.shape[0] == 0:
            return extra
        if extra.points.shape[0] == 0:
            return current
        return GradientConstraint(
            points=np.vstack([current.points, extra.points]),
            vectors=np.vstack([current.vectors, extra.vectors]),
            is_normal=is_normal,
        )

    @staticmethod
    def _merge_inequality_constraints(
        current: InequalityConstraint,
        extra: InequalityConstraint,
    ) -> InequalityConstraint:
        if current.points.shape[0] == 0:
            return extra
        if extra.points.shape[0] == 0:
            return current
        return InequalityConstraint(
            points=np.vstack([current.points, extra.points]),
            bounds=np.vstack([current.bounds, extra.bounds]),
        )

    @staticmethod
    def _merge_linked_inputs(feature_ids: list[str], linked_by_feature: dict) -> MergedLinkedInput:
        first = linked_by_feature[feature_ids[0]]

        by_role: dict[str, list] = defaultdict(list)
        missing_ids: list[str] = []

        for feature_id in feature_ids:
            linked = linked_by_feature[feature_id]
            for role, observations in linked.by_role.items():
                by_role[role].extend(observations)

            missing_ids.extend(linked.missing_observation_ids)

        return MergedLinkedInput(
            feature_id=f"group:{'|'.join(feature_ids)}",
            feature_name=f"group:{'|'.join(feature_ids)}",
            feature_type=first.feature_type,
            by_role=dict(by_role),
            missing_observation_ids=missing_ids,
        )
