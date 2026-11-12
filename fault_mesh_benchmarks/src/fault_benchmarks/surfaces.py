"""Isosurface extraction, exact clipping and boundary-edge tagging."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pyvista as pv

ScalarFn = Callable[[np.ndarray], np.ndarray]

DOMAIN_FACES = ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")


def unit_grid(n: int) -> pv.ImageData:
    h = 1.0 / (n - 1)
    return pv.ImageData(dimensions=(n, n, n), spacing=(h, h, h), origin=(0.0, 0.0, 0.0))


def contour(grid: pv.ImageData, values: np.ndarray, iso: float, method: str) -> pv.PolyData:
    """Isosurface of point values. ``method``: marching_cubes or marching_tetrahedra."""
    g = grid.copy()
    g.point_data["v"] = np.nan_to_num(values, nan=np.nanmax(values) + 1e3)
    if method == "marching_tetrahedra":
        g = g.cast_to_unstructured_grid().triangulate()
        surf = g.contour([iso], scalars="v", method="contour")
    elif method == "marching_cubes":
        surf = g.contour([iso], scalars="v", method="marching_cubes")
    else:
        raise ValueError(f"unknown contour method {method!r}")
    surf = surf.extract_surface(algorithm="dataset_surface").triangulate().clean(tolerance=1e-12)
    surf.point_data.clear()
    surf.cell_data.clear()
    return surf


def clip(surface: pv.PolyData, fn: ScalarFn) -> pv.PolyData:
    """Keep the part where fn >= 0, cutting triangles on the linear zero set.

    ``fn`` is evaluated exactly at the existing vertices; the cut vertices are
    placed by linear interpolation along each triangle edge.
    """
    if surface.n_points == 0:
        return surface
    vals = np.nan_to_num(np.asarray(fn(np.asarray(surface.points)), dtype=float), nan=-1.0)
    if np.all(vals >= 0):
        return surface
    if np.all(vals < 0):
        return pv.PolyData()
    s = surface.copy()
    s.point_data["_c"] = vals
    out = s.clip_scalar(scalars="_c", value=0.0, invert=False)
    if isinstance(out, pv.UnstructuredGrid):
        out = out.extract_surface(algorithm="dataset_surface")
    out = out.triangulate().clean(tolerance=1e-12)
    out.point_data.clear()
    out.cell_data.clear()
    return out


def triangles(surface: pv.PolyData) -> np.ndarray:
    if surface.n_cells == 0:
        return np.zeros((0, 3), dtype=np.int64)
    return surface.faces.reshape(-1, 4)[:, 1:].astype(np.int64)


def edge_counts(tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e.sort(axis=1)
    uniq, counts = np.unique(e, axis=0, return_counts=True)
    return uniq, counts


def boundary_edges(surface: pv.PolyData) -> np.ndarray:
    tris = triangles(surface)
    if len(tris) == 0:
        return np.zeros((0, 2), dtype=np.int64)
    uniq, counts = edge_counts(tris)
    return uniq[counts == 1]


def triangle_normals(surface: pv.PolyData) -> np.ndarray:
    tris = triangles(surface)
    p = np.asarray(surface.points)
    n = np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]])
    with np.errstate(invalid="ignore", divide="ignore"):
        n = n / np.linalg.norm(n, axis=1)[:, None]
    return np.nan_to_num(n)  # degenerate triangles get a zero normal


def mesh_quality(surface: pv.PolyData) -> dict:
    tris = triangles(surface)
    if len(tris) == 0:
        return {"n_points": 0, "n_triangles": 0}
    p = np.asarray(surface.points)
    a, b, c = p[tris[:, 0]], p[tris[:, 1]], p[tris[:, 2]]
    la = np.linalg.norm(b - c, axis=1)
    lb = np.linalg.norm(c - a, axis=1)
    lc = np.linalg.norm(a - b, axis=1)
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)

    def ang(x, y, z):
        cosv = (y**2 + z**2 - x**2) / np.maximum(2 * y * z, 1e-300)
        return np.degrees(np.arccos(np.clip(cosv, -1, 1)))

    with np.errstate(invalid="ignore", divide="ignore"):
        min_angle = np.minimum(np.minimum(ang(la, lb, lc), ang(lb, lc, la)), ang(lc, la, lb))
    uniq, counts = edge_counts(tris)
    return {
        "n_points": int(surface.n_points),
        "n_triangles": int(len(tris)),
        "area": float(area.sum()),
        "min_edge": float(np.min(np.concatenate([la, lb, lc]))),
        "max_edge": float(np.max(np.concatenate([la, lb, lc]))),
        "min_angle_deg": float(min_angle.min()),
        "triangles_min_angle_below_5deg": int((min_angle < 5).sum()),
        "degenerate_triangles": int((area < 1e-14).sum()),
        "boundary_edges": int((counts == 1).sum()),
        "nonmanifold_edges": int((counts > 2).sum()),
    }


# --------------------------------------------------------------------------
# Boundary tagging
# --------------------------------------------------------------------------


@dataclass
class Constraint:
    """A function whose zero set may carry a patch boundary."""

    tag: str
    fn: ScalarFn
    kind: str
    """fault | unconformity | tip | truncation | domain"""
    meta: dict = field(default_factory=dict)


def domain_constraints() -> list[Constraint]:
    out = []
    for axis in range(3):
        for side, name in ((0.0, DOMAIN_FACES[2 * axis]), (1.0, DOMAIN_FACES[2 * axis + 1])):
            out.append(
                Constraint(
                    tag=f"domain:{name}",
                    fn=(lambda p, a=axis, s=side: p[:, a] - s),
                    kind="domain",
                    meta={"axis": axis, "value": side},
                )
            )
    return out


def _distance(fn: ScalarFn, pts: np.ndarray, h: float = 1e-3) -> np.ndarray:
    """|f| / |grad f|, gradient by central differences."""
    v = np.asarray(fn(pts), dtype=float)
    g = np.zeros((len(pts), 3))
    for a in range(3):
        d = np.zeros(3)
        d[a] = h
        g[:, a] = (np.asarray(fn(pts + d), dtype=float) - np.asarray(fn(pts - d), dtype=float)) / (
            2 * h
        )
    gn = np.linalg.norm(g, axis=1)
    out = np.abs(v) / np.maximum(gn, 1e-12)
    out[~np.isfinite(out)] = np.inf
    return out, g / np.maximum(gn, 1e-12)[:, None]


def tag_boundary(
    surface: pv.PolyData, constraints: list[Constraint], tol: float, edges=None
) -> tuple[np.ndarray, list[str], np.ndarray, np.ndarray]:
    """Classify each boundary edge by the constraint whose zero set it lies on.

    Returns (edges, tags, distance, constraint_normal) per edge. Edges farther
    than ``tol`` from every constraint are tagged ``free`` (an unexpected open
    boundary; they should not exist in a valid case). ``edges`` restricts the
    classification to a subset of the boundary edges.
    """
    if edges is None:
        edges = boundary_edges(surface)
    if len(edges) == 0:
        return edges, [], np.zeros(0), np.zeros((0, 3))
    p = np.asarray(surface.points)
    mid = 0.5 * (p[edges[:, 0]] + p[edges[:, 1]])
    dists = []
    normals = []
    for c in constraints:
        d, n = _distance(c.fn, mid)
        dists.append(d)
        normals.append(n)
    D = np.stack(dists, axis=1)
    best = np.argmin(D, axis=1)
    bestd = D[np.arange(len(mid)), best]
    tags = [constraints[i].tag if bestd[k] <= tol else "free" for k, i in enumerate(best)]
    nrm = np.stack(normals, axis=1)[np.arange(len(mid)), best]
    return edges, tags, bestd, nrm


def edges_to_polylines(points: np.ndarray, edges: np.ndarray) -> pv.PolyData:
    if len(edges) == 0:
        return pv.PolyData()
    lines = np.hstack([np.full((len(edges), 1), 2), edges]).ravel()
    poly = pv.PolyData(np.asarray(points), lines=lines)
    return poly.clean(tolerance=1e-12)
