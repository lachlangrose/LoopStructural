"""Affine two-fault models with exact, independently clipped interface geometry.

The secondary fault is y - 0.35*z - 0.1 = 0. In the terminating case it
exists only where x >= 0, meeting the x=0 primary along an oblique line.
"""

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from .geometry import HORIZONS
from .interfaces import edges, face_table, triangle_area
from .validation import AREA_TOL, GEOMETRIC_TOL, validate_topology

PRIMARY_NORMAL = np.array([1.0, 0.0, 0.0])
SECONDARY_NORMAL = np.array([0.0, 1.0, -0.35])
STRAT_NORMAL = np.array([-0.2, 0.1, 1.0])
CUBE_A = np.concatenate([np.eye(3), -np.eye(3)])
CUBE_B = np.ones(6)


def mmg_isotropic_quality(mesh):
    """Unnormalised quality used by MMG5_caltet_iso_4pt in MMG 5.8.0."""
    p = mesh.points[mesh.tets]
    delta = p[:, [0, 0, 0, 1, 1, 2]] - p[:, [1, 2, 3, 2, 3, 3]]
    squared_lengths = np.einsum("ijk,ijk->i", delta, delta)
    return 6 * mesh.volumes() / squared_lengths**1.5


def scalar_prepass_diagnostic(mesh, values):
    """Predict the documented poor-tet sign prepass; never alter input scalars.

    This emulates only the poor-quality loop of MMG3D_snpval_ls, not the
    subsequent zero snapping or manifold checks. It is a version-specific
    diagnostic explaining why a successful exit may change geological geometry.
    """
    quality = mmg_isotropic_quality(mesh)
    values = np.asarray(values)
    predicted = values.copy()
    poor = quality < 1e-6
    for tet in mesh.tets[poor]:
        if np.any(predicted[tet] < 1e-3):
            predicted[tet] = -1e-3
    changed = predicted != values
    return {
        "minimum_internal_quality": float(quality.min()),
        "minimum_normalized_quality": float(quality.min() * 12 * np.sqrt(3)),
        "tets_below_internal_threshold_1e_minus_6": int(poor.sum()),
        "predicted_changed_vertices": int(changed.sum()),
        "predicted_positive_to_negative_vertices": int(((values > 0) & (predicted < 0)).sum()),
        "maximum_predicted_scalar_change": float(np.max(abs(predicted - values))),
    }


def clipped_polygon(normal, offset, inequalities=None):
    """Exact plane/convex-polytope section, computed from half-space constraints."""
    a, b = (CUBE_A, CUBE_B) if inequalities is None else inequalities
    vertices = []
    for i, j in combinations(range(len(b)), 2):
        matrix = np.array([normal, a[i], a[j]])
        if abs(np.linalg.det(matrix)) < 1e-12:
            continue
        point = np.linalg.solve(matrix, [offset, b[i], b[j]])
        if np.all(a @ point <= b + 1e-10):
            if not any(np.linalg.norm(point - q) < 1e-10 for q in vertices):
                vertices.append(point)
    if len(vertices) < 3:
        return np.empty((0, 3))
    vertices = np.array(vertices)
    center = vertices.mean(axis=0)
    unit_normal = normal / np.linalg.norm(normal)
    u = vertices[0] - center
    u /= np.linalg.norm(u)
    v = np.cross(unit_normal, u)
    angle = np.arctan2((vertices - center) @ v, (vertices - center) @ u)
    return vertices[np.argsort(angle)]


def polygon_area(polygon):
    if len(polygon) < 3:
        return 0.0
    return float(np.linalg.norm(np.cross(polygon, np.roll(polygon, -1, axis=0)).sum(axis=0)) / 2)


@dataclass(frozen=True)
class TwoFaultModel:
    case: str = "terminating"

    def __post_init__(self):
        if self.case not in ("terminating", "crossing"):
            raise ValueError("Case must be terminating or crossing")

    @property
    def offsets(self):
        return (
            {1: 0.0, 2: 0.25, 3: 0.4}
            if self.case == "terminating"
            else {1: 0.0, 2: 0.15, 3: 0.25, 4: 0.4}
        )

    @property
    def blocks(self):
        return tuple(self.offsets)

    def secondary(self, points):
        return np.asarray(points) @ SECONDARY_NORMAL - 0.1

    def block_labels(self, points):
        p = np.asarray(points)
        right, upper = p[..., 0] > 0, self.secondary(p) > 0
        if self.case == "terminating":
            return np.where(right, np.where(upper, 3, 2), 1)
        return 1 + 2 * right.astype(int) + upper.astype(int)

    def restored(self, points, block):
        """Evaluate a chosen block trace, also at either fault's shared vertices."""
        return np.asarray(points) @ STRAT_NORMAL - self.offsets[block]

    def labels(self, points):
        block = self.block_labels(points)
        offset = np.array([self.offsets[int(b)] for b in np.ravel(block)]).reshape(block.shape)
        value = np.asarray(points) @ STRAT_NORMAL - offset
        return block, np.searchsorted(HORIZONS, value, side="right")

    def constraints(self, block):
        """Return A,b defining that block as A*x <= b, including the cube."""
        a, b = list(CUBE_A), list(CUBE_B)
        if self.case == "terminating":
            a.append(PRIMARY_NORMAL if block == 1 else -PRIMARY_NORMAL)
            b.append(0.0)
            if block in (2, 3):
                sign = 1 if block == 2 else -1
                a.append(sign * SECONDARY_NORMAL)
                b.append(sign * 0.1)
        else:
            a.append(PRIMARY_NORMAL if block in (1, 2) else -PRIMARY_NORMAL)
            b.append(0.0)
            sign = 1 if block in (1, 3) else -1
            a.append(sign * SECONDARY_NORMAL)
            b.append(sign * 0.1)
        return np.array(a), np.array(b)

    def horizon_polygon(self, block, horizon):
        return clipped_polygon(STRAT_NORMAL, horizon + self.offsets[block], self.constraints(block))

    def fault_polygon(self, fault):
        if fault == 1:
            return clipped_polygon(PRIMARY_NORMAL, 0.0)
        a, b = CUBE_A.copy(), CUBE_B.copy()
        if self.case == "terminating":
            a = np.vstack([a, -PRIMARY_NORMAL])
            b = np.r_[b, 0.0]
        return clipped_polygon(SECONDARY_NORMAL, 0.1, (a, b))


def interfaces(mesh, model):
    faces, counts, left, right = face_table(mesh)
    block, unit = model.labels(mesh.centers)
    p = mesh.points[faces]
    internal = counts == 2
    fault = internal & (block[left] != block[right])
    primary = fault & (np.max(abs(p @ PRIMARY_NORMAL), axis=1) <= GEOMETRIC_TOL)
    secondary = fault & (np.max(abs(p @ SECONDARY_NORMAL - 0.1), axis=1) <= GEOMETRIC_TOL)
    horizon = internal & (block[left] == block[right]) & (unit[left] != unit[right])
    return {
        "faces": faces,
        "counts": counts,
        "left": left,
        "right": right,
        "block": block,
        "unit": unit,
        "primary": primary,
        "secondary": secondary,
        "fault": fault,
        "horizon": horizon,
    }


def edge_coverage(mesh, selected_edges, expected_endpoints, tol=GEOMETRIC_TOL):
    """Require a single, non-overlapping edge chain spanning the entire segment."""
    if not len(selected_edges):
        return {"passed": False, "length": 0.0, "edges": 0}
    selected_edges = np.array(sorted(selected_edges), dtype=int)
    endpoints = np.asarray(expected_endpoints)
    direction = endpoints[1] - endpoints[0]
    length = np.linalg.norm(direction)
    direction /= length
    p = mesh.points[selected_edges]
    t = (p - endpoints[0]) @ direction
    distance = np.linalg.norm((p - endpoints[0]) - t[..., None] * direction, axis=2)
    intervals = np.sort(t, axis=1)
    intervals = intervals[np.argsort(intervals[:, 0])]
    vertices, degree = np.unique(selected_edges, return_counts=True)
    vertex_degree_valid = int((degree == 1).sum()) == 2 and np.all((degree == 1) | (degree == 2))
    total = float(np.linalg.norm(p[:, 1] - p[:, 0], axis=1).sum())
    passed = (
        np.max(distance) <= tol
        and abs(intervals[0, 0]) <= tol
        and abs(intervals[-1, 1] - length) <= tol
        and np.all(abs(intervals[1:, 0] - intervals[:-1, 1]) <= tol)
        and abs(total - length) <= AREA_TOL
        and vertex_degree_valid
    )
    return {
        "passed": bool(passed),
        "length": total,
        "expected_length": float(length),
        "edges": len(selected_edges),
        "vertices": len(vertices),
    }


def horizon_fault_segment(model, block, horizon, fault):
    if model.case == "terminating" and block == 1 and fault == 2:
        return None
    normal = PRIMARY_NORMAL if fault == 1 else SECONDARY_NORMAL
    offset = 0.0 if fault == 1 else 0.1
    a, b = model.constraints(block)
    vertices = []
    for inequality, bound in zip(a, b):
        matrix = np.array([STRAT_NORMAL, normal, inequality])
        if abs(np.linalg.det(matrix)) < 1e-12:
            continue
        p = np.linalg.solve(matrix, [horizon + model.offsets[block], offset, bound])
        if np.all(a @ p <= b + 1e-10) and not any(np.linalg.norm(p - q) < 1e-10 for q in vertices):
            vertices.append(p)
    return np.array(vertices) if len(vertices) == 2 else None


def validate_two_faults(mesh, model, *, horizons=(), lineage=None, full_scan=True):
    result = validate_topology(mesh, full_scan=full_scan)
    checks, metrics = result["checks"], result["metrics"]
    d = interfaces(mesh, model)
    faces, block, unit = d["faces"], d["block"], d["unit"]
    left, right = d["left"], d["right"]
    p = mesh.points[faces]
    internal = d["counts"] == 2
    tol = GEOMETRIC_TOL
    for b in model.blocks:
        a, bound = model.constraints(b)
        xyz = mesh.points[mesh.tets[block == b]]
        checks[f"block_{b}_no_fault_crossing"] = bool(np.all(xyz @ a.T <= bound + tol))
    checks["all_fault_faces_on_intended_planes"] = bool(
        np.all((d["primary"] | d["secondary"])[d["fault"]])
    )
    fault_edges = {}
    fault_details = []
    for number, name in ((1, "primary"), (2, "secondary")):
        mask = d[name]
        observed = float(triangle_area(p[mask]).sum())
        expected = polygon_area(model.fault_polygon(number))
        checks[name + "_fault_full_area"] = abs(observed - expected) <= AREA_TOL
        fault_edges[number] = {tuple(e) for e in edges(faces[mask])}
        fault_details.append(
            {
                "fault": name,
                "area": observed,
                "expected_area": expected,
                "triangles": int(mask.sum()),
            }
        )
    if model.case == "terminating":
        checks["secondary_stops_at_primary"] = bool(np.all(p[d["secondary"], :, 0] >= -tol))
        # Block 1 has no partition by the secondary fault, even on its extension.
        checks["three_fault_blocks"] = set(block) == {1, 2, 3}
    else:
        checks["four_fault_blocks"] = set(block) == {1, 2, 3, 4}
    junction = fault_edges[1] & fault_edges[2]
    junction_report = edge_coverage(mesh, junction, [[0.0, -0.25, -1.0], [0.0, 0.45, 1.0]])
    checks["junction_is_complete_shared_edge_chain"] = junction_report["passed"]
    fault_faces = faces[d["fault"]]
    incidence = []
    block_incidence = []
    for edge in sorted(junction):
        incident = np.sum(np.isin(fault_faces, edge), axis=1) == 2
        incidence.append(int(incident.sum()))
        selected = np.flatnonzero(d["fault"])[incident]
        block_incidence.append(len(np.unique(np.r_[block[left[selected]], block[right[selected]]])))
    expected_degree = 3 if model.case == "terminating" else 4
    checks["junction_fault_sheet_incidence"] = bool(
        incidence and np.all(np.array(incidence) == expected_degree)
    )
    checks["junction_block_incidence"] = bool(
        block_incidence and np.all(np.array(block_incidence) == expected_degree)
    )
    junction_report.update(
        {
            "expected_sheet_incidence": expected_degree,
            "observed_sheet_incidence": sorted(set(incidence)),
            "observed_block_incidence": sorted(set(block_incidence)),
        }
    )
    horizon_details = []
    for b, h in horizons:
        residual = mesh.points @ STRAT_NORMAL - model.offsets[b] - h
        values = residual[mesh.tets]
        crossing = (block == b) & (values.min(axis=1) < -tol) & (values.max(axis=1) > tol)
        mask = (
            internal
            & (block[left] == b)
            & (block[right] == b)
            & (np.max(abs(residual[faces]), axis=1) <= tol)
        )
        area = float(triangle_area(p[mask]).sum())
        expected = polygon_area(model.horizon_polygon(b, h))
        key = f"block_{b}_horizon_{h:g}"
        checks[key + "_no_crossing_tets"] = not bool(crossing.any())
        checks[key + "_patch_area"] = abs(area - expected) <= AREA_TOL
        horizon_edges = {tuple(e) for e in edges(faces[mask])}
        intersections = []
        for f in (1, 2):
            segment = horizon_fault_segment(model, b, h, f)
            if segment is None:
                continue
            shared = horizon_edges & fault_edges[f]
            coverage = edge_coverage(mesh, shared, segment)
            checks[key + f"_shared_fault_{f}_edges"] = coverage["passed"]
            intersections.append({"fault": f, **coverage})
        horizon_details.append(
            {
                "block": b,
                "horizon": float(h),
                "area": area,
                "expected_area": expected,
                "triangles": int(mask.sum()),
                "crossing_tets": int(crossing.sum()),
                "intersections": intersections,
            }
        )
    # Raw MMG material labels must agree with the inserted subset of horizons,
    # not just with analytically generated centroid labels at the end.
    if lineage is not None:
        offsets = np.array([model.offsets[int(b)] for b in block])
        scalar = mesh.centers @ STRAT_NORMAL - offsets
        expected_unit = np.zeros(len(mesh.tets), dtype=int)
        for b, h in horizons:
            expected_unit += ((block == b) & (scalar > h)).astype(int)
        expected = np.c_[block, expected_unit]
        actual = np.array([lineage[int(ref)] for ref in mesh.refs])
        checks["mmg_material_lineage_matches_model"] = bool(np.array_equal(actual, expected))
    if len(horizons) == 3 * len(model.blocks):
        checks["all_expected_geological_regions_present"] = len(
            np.unique(np.c_[block, unit], axis=0)
        ) == 4 * len(model.blocks)
        on_target = np.zeros(len(faces), dtype=bool)
        for b, h in horizons:
            residual = p @ STRAT_NORMAL - model.offsets[b] - h
            on_target |= (
                (block[left] == b) & (block[right] == b) & (np.max(abs(residual), axis=1) <= tol)
            )
        checks["all_horizon_interfaces_geometrically_accurate"] = bool(
            np.all(on_target[d["horizon"]])
        )
        checks["horizon_adjacency_is_consecutive_units"] = bool(
            np.all(abs(unit[left[d["horizon"]]] - unit[right[d["horizon"]]]) == 1)
        )
    checks["one_valid_fault_block_and_unit_per_tet"] = bool(
        np.all(np.isin(block, model.blocks)) & np.all(np.isin(unit, range(4)))
    )
    metrics.update(
        {
            "faults": fault_details,
            "junction": junction_report,
            "horizons": horizon_details,
            "fault_blocks": len(np.unique(block)),
            "geological_regions": len(np.unique(np.c_[block, unit], axis=0)),
        }
    )
    quality = mmg_isotropic_quality(mesh)
    metrics["quality"] = {
        "minimum_normalized": float(quality.min() * 12 * np.sqrt(3)),
        "median_normalized": float(np.median(quality) * 12 * np.sqrt(3)),
        "below_mmg_internal_prepass_threshold": int((quality < 1e-6).sum()),
    }
    result["passed"] = all(checks.values())
    return result
