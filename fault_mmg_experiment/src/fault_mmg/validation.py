"""Independent topology, geometric coverage and label validation.

No face-count-only claim of conformity: also check every mesh vertex against
every candidate face geometrically, using a conservative KD-tree broad phase.
"""

import numpy as np
from scipy.spatial import cKDTree

from .geometry import HORIZONS, horizon_height, labels
from .interfaces import edges, exterior_references, face_table, geological_interfaces, triangle_area

GEOMETRIC_TOL = 1e-8
VOLUME_TOL = 1e-8
MIN_VOLUME = 1e-14
AREA_TOL = 1e-7


def hanging_vertices(mesh, faces, tol=GEOMETRIC_TOL):
    """Find nonincident vertices lying on face interiors OR edges (T junctions)."""
    tree = cKDTree(mesh.points)
    hits = 0
    examples = []
    for start in range(0, len(faces), 2048):
        batch = faces[start : start + 2048]
        xyz = mesh.points[batch]
        centers = xyz.mean(axis=1)
        radius = np.linalg.norm(xyz - centers[:, None], axis=2).max(axis=1) + tol
        candidates = tree.query_ball_point(centers, radius)
        lengths = np.array([len(c) for c in candidates])
        fi = np.repeat(np.arange(len(batch)), lengths)
        vi = np.concatenate([np.asarray(c, dtype=int) for c in candidates])
        keep = ~np.any(batch[fi] == vi[:, None], axis=1)
        fi, vi = fi[keep], vi[keep]
        if not len(fi):
            continue
        a, b, c = xyz[fi, 0], xyz[fi, 1], xyz[fi, 2]
        u, v, w = b - a, c - a, mesh.points[vi] - a
        normal = np.cross(u, v)
        norm = np.linalg.norm(normal, axis=1)
        coplanar = abs(np.einsum("ij,ij->i", w, normal)) <= tol * norm
        fi, vi, u, v, w = fi[coplanar], vi[coplanar], u[coplanar], v[coplanar], w[coplanar]
        if not len(fi):
            continue
        uu = np.einsum("ij,ij->i", u, u)
        uv = np.einsum("ij,ij->i", u, v)
        vv = np.einsum("ij,ij->i", v, v)
        wu = np.einsum("ij,ij->i", w, u)
        wv = np.einsum("ij,ij->i", w, v)
        det = uu * vv - uv * uv
        safe = det > 0
        s = np.divide(wu * vv - wv * uv, det, out=np.full(len(det), np.inf), where=safe)
        t = np.divide(wv * uu - wu * uv, det, out=np.full(len(det), np.inf), where=safe)
        # Barycentric tolerance scaled using triangle altitudes.
        eps = tol * np.sqrt(np.maximum(uu, vv) / np.maximum(det, 1e-300))
        inside = safe & (s >= -eps) & (t >= -eps) & (s + t <= 1 + eps)
        hits += int(inside.sum())
        for face_id, vertex in zip(
            fi[inside][: max(0, 5 - len(examples))], vi[inside][: max(0, 5 - len(examples))]
        ):
            examples.append({"face": int(start + face_id), "vertex": int(vertex)})
    return {"incidences": hits, "examples": examples}


def validate_topology(mesh, *, full_scan=True, cube_domain=True):
    """Validate the volume mesh independently of a geological field model."""
    tol = GEOMETRIC_TOL
    faces, counts, left, right = face_table(mesh)
    p = mesh.points[faces]
    volumes = mesh.volumes()
    checks, metrics = {}, {}
    checks["positive_volumes"] = bool(np.all(volumes > MIN_VOLUME))
    checks["finite_coordinates"] = bool(np.all(np.isfinite(mesh.points)))
    checks["face_multiplicity"] = bool(np.all((counts == 1) | (counts == 2)))
    checks["no_duplicate_tetrahedra"] = len(np.unique(np.sort(mesh.tets, axis=1), axis=0)) == len(
        mesh.tets
    )
    checks["no_duplicate_vertices"] = not bool(cKDTree(mesh.points).query_pairs(tol))
    boundary_refs = exterior_references(p[counts == 1], tol)
    if cube_domain:
        checks["external_faces_on_cube"] = bool(np.all(boundary_refs != 99))
        checks["inside_cube"] = bool(np.all(abs(mesh.points) <= 1 + tol))
        checks["cube_volume"] = bool(abs(volumes.sum() - 8) <= VOLUME_TOL)
        checks["external_area"] = bool(abs(triangle_area(p[counts == 1]).sum() - 24) <= AREA_TOL)
    # Adjacent positive tets must occupy opposite sides of every shared face.
    interior = counts == 2
    normal = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    centers = mesh.centers
    s0 = np.einsum("ij,ij->i", centers[left] - p[:, 0], normal)
    s1 = np.einsum("ij,ij->i", centers[right] - p[:, 0], normal)
    checks["internal_opposite_sides"] = bool(np.all(s0[interior] * s1[interior] < 0))
    face_lookup = {tuple(f): int(c) for f, c in zip(faces, counts)}
    checks["exported_triangles_are_tet_faces"] = all(
        tuple(sorted(t)) in face_lookup for t in mesh.triangles
    )
    scan = hanging_vertices(mesh, faces) if full_scan else {"incidences": None, "examples": []}
    if full_scan:
        checks["no_hanging_nodes_or_t_junctions"] = scan["incidences"] == 0
    metrics.update(
        {
            "vertices": len(mesh.points),
            "tetrahedra": len(mesh.tets),
            "orientation_corrections": mesh.orientation_corrections,
            "min_volume": float(volumes.min()),
            "total_volume": float(volumes.sum()),
            "external_faces": int((counts == 1).sum()),
            "internal_faces": int((counts == 2).sum()),
            "nonmanifold_faces": int((counts > 2).sum()),
            "hanging_vertices": scan,
        }
    )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": metrics,
        "tolerances": {
            "geometry_absolute": tol,
            "total_volume_absolute": VOLUME_TOL,
            "minimum_tet_volume": MIN_VOLUME,
            "area_or_length_absolute": AREA_TOL,
        },
    }


def validate(
    mesh, *, require_fault=True, horizons=None, full_scan=True, lineage=None, cube_domain=True
):
    horizons = [(b, float(h)) for b in (1, 2) for h in HORIZONS] if horizons is None else horizons
    result = validate_topology(mesh, full_scan=full_scan, cube_domain=cube_domain)
    checks, metrics = result["checks"], result["metrics"]
    tol = GEOMETRIC_TOL
    faces, counts, left, right = face_table(mesh)
    p = mesh.points[faces]
    centers = mesh.centers
    interior = counts == 2
    blocks, units = labels(centers)
    fault_mask = interior & (blocks[left] != blocks[right])
    if require_fault:
        x = mesh.points[mesh.tets, 0]
        checks["no_tet_crosses_fault"] = bool(
            np.all((x.min(axis=1) >= -tol) | (x.max(axis=1) <= tol))
        )
        checks["fault_internal_faces"] = bool(fault_mask.any())
        checks["fault_plane"] = bool(np.all(abs(p[fault_mask, :, 0]) <= tol))
        area = float(triangle_area(p[fault_mask]).sum())
        checks["fault_full_area"] = bool(abs(area - 4) <= AREA_TOL)
        metrics["fault_area"] = area
        metrics["fault_triangles"] = int(fault_mask.sum())
    details = []
    fault_edges = {tuple(e) for e in edges(faces[fault_mask])}
    for block, horizon in horizons:
        height = horizon_height(block, horizon)
        z = mesh.points[mesh.tets, 2] - height
        in_block = blocks == block
        crossing = in_block & (z.min(axis=1) < -tol) & (z.max(axis=1) > tol)
        # Both adjacency and exact plane membership are necessary.
        on_plane = np.max(abs(p[:, :, 2] - height), axis=1) <= tol
        mask = interior & (blocks[left] == block) & (blocks[right] == block) & on_plane
        area = float(triangle_area(p[mask]).sum())
        shared_edges = [e for e in edges(faces[mask]) if tuple(e) in fault_edges]
        length = (
            float(
                np.linalg.norm(
                    mesh.points[np.array(shared_edges)[:, 1]]
                    - mesh.points[np.array(shared_edges)[:, 0]],
                    axis=1,
                ).sum()
            )
            if shared_edges
            else 0.0
        )
        key = f"block_{block}_horizon_{horizon:g}"
        checks[key + "_no_crossing_tets"] = not bool(crossing.any())
        checks[key + "_area"] = bool(abs(area - 2) <= AREA_TOL)
        checks[key + "_fault_shared_edges"] = bool(abs(length - 2) <= AREA_TOL)
        details.append(
            {
                "block": block,
                "horizon": horizon,
                "height": height,
                "area": area,
                "triangles": int(mask.sum()),
                "crossing_tets": int(crossing.sum()),
                "intersection_length": length,
                "intersection_edges": len(shared_edges),
            }
        )
    # Do all six geological interfaces stay on the expected planes? Only apply
    # the complete-label checks once all six target block/horizon pairs exist.
    if len(horizons) == 6:
        d = geological_interfaces(mesh)
        horizon_mask = d["horizons"]
        on_target = np.zeros(len(faces), dtype=bool)
        for block, horizon in horizons:
            height = horizon_height(block, horizon)
            on_target |= (
                (blocks[left] == block)
                & (blocks[right] == block)
                & (np.max(abs(p[:, :, 2] - height), axis=1) <= tol)
            )
        checks["all_geological_interfaces_accurate"] = bool(np.all(on_target[horizon_mask]))
        checks["horizon_unit_adjacency"] = bool(
            np.all(abs(units[left[horizon_mask]] - units[right[horizon_mask]]) == 1)
        )
        checks["eight_geological_regions"] = len(np.unique(np.c_[blocks, units], axis=0)) == 8
        if lineage is not None:
            expected = np.array([lineage[int(r)] for r in mesh.refs])
            checks["mmg_material_labels_correct"] = bool(
                np.array_equal(expected, np.c_[blocks, units])
            )
    checks["one_block_and_unit_per_tet"] = bool(
        np.all(np.isin(blocks, [1, 2])) & np.all(np.isin(units, range(4)))
    )
    metrics["horizons"] = details
    result["passed"] = all(checks.values())
    return result
