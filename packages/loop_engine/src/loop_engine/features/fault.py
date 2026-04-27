from __future__ import annotations

import numpy as np

from .basebuilder import BaseBuilder, MergedLinkedInput, PreparedConstraints


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
        normal_constraints = self._normalize_xyz_vectors(normal_constraints)

        slip_tangents = self.coords_vectors_from_linked_observations(by_role.get("slip_vector", []))
        if slip_tangents.shape[0] > 0 and linked_data.tangent_constraints.shape[0] > 0:
            tangent_constraints = np.vstack([linked_data.tangent_constraints, slip_tangents])
        elif slip_tangents.shape[0] > 0:
            tangent_constraints = slip_tangents
        else:
            tangent_constraints = linked_data.tangent_constraints
        tangent_constraints = self._normalize_xyz_vectors(tangent_constraints)

        inferred_normal, inferred_slip = self._infer_geometry_from_trace(trace_points, params)
        trace_anchor = self._trace_anchor(trace_points)
        if (
            normal_constraints.shape[0] == 0
            and inferred_normal is not None
            and trace_anchor is not None
        ):
            normal_constraints = np.hstack([trace_anchor, inferred_normal]).reshape(1, 6)
        if (
            tangent_constraints.shape[0] == 0
            and inferred_slip is not None
            and trace_anchor is not None
        ):
            tangent_constraints = np.hstack([trace_anchor, inferred_slip]).reshape(1, 6)

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
            build_params=params,
        )

    def _build_interpolator_from_constraints(
        self,
        linked_data,
        value_constraints: np.ndarray,
        normal_constraints: np.ndarray,
        tangent_constraints: np.ndarray,
        build_params: dict,
    ) -> object:
        prepared = PreparedConstraints(
            value_constraints=value_constraints,
            normal_constraints=normal_constraints,
            tangent_constraints=tangent_constraints,
        )
        return self.build_from_constraints(
            linked_data=linked_data,
            prepared=prepared,
            build_params=build_params,
        )

    @staticmethod
    def _trace_anchor(trace_points: np.ndarray) -> np.ndarray | None:
        if trace_points.shape[0] == 0:
            return None
        return np.mean(trace_points, axis=0)

    def _infer_geometry_from_trace(self, trace_points: np.ndarray, params: dict):
        if trace_points.shape[0] < 2:
            return None, None

        direction = self._principal_direction(trace_points)
        if direction is None:
            return None, None

        vertical = np.array([0.0, 0.0, 1.0])
        dip_direction = np.cross(direction, vertical)
        dip_direction_norm = np.linalg.norm(dip_direction)
        if dip_direction_norm < 1e-12:
            return None, direction
        dip_direction = dip_direction / dip_direction_norm

        dip_degrees = float(params.get("fault_dip", 90.0))
        dip_radians = np.deg2rad(np.clip(dip_degrees, 0.0, 90.0))

        inferred_normal = np.cos(dip_radians) * vertical + np.sin(dip_radians) * dip_direction
        inferred_normal = inferred_normal / np.linalg.norm(inferred_normal)

        inferred_slip = direction / np.linalg.norm(direction)
        return inferred_normal, inferred_slip

    @staticmethod
    def _principal_direction(points: np.ndarray) -> np.ndarray | None:
        centered = points - np.mean(points, axis=0)
        if centered.shape[0] < 2:
            return None
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        direction = vh[0]
        norm = np.linalg.norm(direction)
        if norm < 1e-12:
            return None
        return direction / norm
