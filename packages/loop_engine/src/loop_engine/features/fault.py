from __future__ import annotations

import numpy as np

from .basebuilder import BaseBuilder, MergedLinkedInput


class FaultBuilder(BaseBuilder):
    """Build fault features with role-aware constraints."""

    def build(self, task_payload: dict) -> object | None:
        linked_data = task_payload.get("linked_data")
        if linked_data is None:
            return None

        feature = task_payload.get("feature")
        params = getattr(feature, "build_params", {}) or {}
        trace_iso = float(params.get("trace_iso", 0.0))
        hanging_wall_iso = float(params.get("hanging_wall_iso", 1.0))
        footwall_iso = float(params.get("footwall_iso", -1.0))

        by_role = getattr(linked_data, "by_role", {})

        trace_points = self.coords_from_linked_observations(by_role.get("trace", []))
        hanging_wall_points = self.coords_from_linked_observations(by_role.get("hanging_wall", []))
        footwall_points = self.coords_from_linked_observations(by_role.get("footwall", []))

        value_blocks = []
        if trace_points.shape[0] > 0:
            value_blocks.append(
                np.hstack([trace_points, np.full((trace_points.shape[0], 1), trace_iso)])
            )
        if hanging_wall_points.shape[0] > 0:
            value_blocks.append(
                np.hstack(
                    [
                        hanging_wall_points,
                        np.full((hanging_wall_points.shape[0], 1), hanging_wall_iso),
                    ]
                )
            )
        if footwall_points.shape[0] > 0:
            value_blocks.append(
                np.hstack([footwall_points, np.full((footwall_points.shape[0], 1), footwall_iso)])
            )

        if value_blocks:
            value_constraints = np.vstack(value_blocks)
        elif linked_data.point_constraints.shape[0] > 0:
            value_constraints = np.hstack(
                [
                    linked_data.point_constraints,
                    np.zeros((linked_data.point_constraints.shape[0], 1)),
                ]
            )
        else:
            value_constraints = np.empty((0, 4), dtype=float)

        role_normals = self.coords_vectors_from_linked_observations(by_role.get("orientation", []))
        normal_constraints = (
            role_normals if role_normals.shape[0] > 0 else linked_data.gradient_constraints
        )

        slip_tangents = self.coords_vectors_from_linked_observations(by_role.get("slip_vector", []))
        if slip_tangents.shape[0] > 0 and linked_data.tangent_constraints.shape[0] > 0:
            tangent_constraints = np.vstack([linked_data.tangent_constraints, slip_tangents])
        elif slip_tangents.shape[0] > 0:
            tangent_constraints = slip_tangents
        else:
            tangent_constraints = linked_data.tangent_constraints

        if (
            value_constraints.shape[0] == 0
            and normal_constraints.shape[0] == 0
            and tangent_constraints.shape[0] == 0
        ):
            return None

        fault_linked_data = MergedLinkedInput(
            feature_id=getattr(linked_data, "feature_id", "fault"),
            feature_name=getattr(linked_data, "feature_name", None),
            feature_type=getattr(linked_data, "feature_type", "Fault"),
            point_constraints=value_constraints[:, :3],
            gradient_constraints=normal_constraints,
            tangent_constraints=tangent_constraints,
            by_role=by_role,
            missing_observation_ids=getattr(linked_data, "missing_observation_ids", []),
        )

        return self._build_interpolator_from_constraints(
            linked_data=fault_linked_data,
            value_constraints=value_constraints,
            normal_constraints=normal_constraints,
            tangent_constraints=tangent_constraints,
        )

    def _build_interpolator_from_constraints(
        self,
        linked_data,
        value_constraints: np.ndarray,
        normal_constraints: np.ndarray,
        tangent_constraints: np.ndarray,
    ) -> object:
        from loop_interpolation import InterpolatorBuilder

        builder = InterpolatorBuilder(
            interpolatortype=self.model.interpolatortype,
            bounding_box=self._resolve_bounding_box(linked_data),
            nelements=self.model.nelements,
        )

        if value_constraints.shape[0] > 0:
            builder.add_value_constraints(value_constraints)
        if normal_constraints.shape[0] > 0:
            builder.add_normal_constraints(normal_constraints)
        if tangent_constraints.shape[0] > 0:
            builder.add_tangent_constraints(tangent_constraints)

        builder.setup_interpolator().solve()
        return builder.build()
