"""Conforming surfaces: cut with the fault meshes themselves (Loop CGAL).

The reference surfaces (``generate.py``) are clipped by the implicit fault
functions. Their cut-off lines are on the implicit fault to O(h^2), but they
are not on the fault *triangles*, and the fault mesh has no vertices on them.
This module makes a second set of surfaces that share vertices and edges
along every cut-off and junction:

1. Each fault is contoured from its frame coordinate gx = 0. An abutting
   fault is cut by its host fault.
2. Each horizon is contoured per block (the smooth block fields of
   ``generate.py``) and cut by the faults that bound the block.
3. Each fault is split (both sides kept) by the block contours whose horizon
   piece touches it, so the cut-off and junction curves become fault edges.
4. One weld over all surfaces (1e-8) and a T-junction repair in both
   directions make the shared vertices bit-identical. ``check_conformity``
   checks the result.

Finite faults (a tip): a fault that ends inside the model cannot cut a
horizon itself, because Loop CGAL extends a clipper past its boundary. The
fault mesh is cut at the tip surface t = min(1 - |g|) = 1 - TIP_LEVEL, and a
"bowl" (the fault inside the tip plus the tip surface on the footwall side)
bounds the active footwall. The hanging-wall piece of a horizon is the part
outside the bowl, the footwall piece the part inside. Beyond the tip the two
block fields are equal, so the pieces share the seam on the tip surface and
the horizon is one surface with a slit (``_tip_band``, ``_weld_tip_seam``).

All cuts are CGAL corefinements with an exact kernel (loop_cgal). Three
conditions make them reliable (see ``build_conforming``, ``clean_contour``):
no zero-area contour triangles, each clipper larger than the surface it cuts,
and no extra intersection lines on a fault.

Optional, experimental: isotropic remeshing with Loop CGAL, with the shared
curves as fixed edges. With loop_cgal 0.1.8 the remesher still collapses some
short fixed edges, so the remeshed surfaces do not fully conform
(``conforming.json`` reports this).

Limits: no faults displaced by other faults, no unconformities, no chains of
abutments, and no fault with both a tip and an abutment.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyvista as pv

from .builder import BuiltCase
from .fields import (
    SideFunctions,
    block_label,
    clip_order,
    force_map,
    forced_sides,
    raw_frame,
    sign_patterns,
)
from .spec import profile_tip_axes
from .surfaces import boundary_edges, contour, edge_counts, mesh_quality

# CGAL export thresholds. Zero is a sentinel in loop_cgal (it removes all faces).
AREA_EPS = 1e-18
DUP_EPS = 1e-15


@dataclass
class Tri:
    """A triangle mesh as arrays (float64 points, int64 triangles)."""

    points: np.ndarray
    tris: np.ndarray
    block: np.ndarray | None = None

    @property
    def empty(self) -> bool:
        return len(self.tris) == 0

    @classmethod
    def from_pv(cls, surf: pv.PolyData) -> Tri:
        if surf.n_cells == 0:
            return cls(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
        return cls(np.asarray(surf.points, dtype=np.float64).copy(),
                   surf.faces.reshape(-1, 4)[:, 1:].astype(np.int64))

    def to_pv(self) -> pv.PolyData:
        if self.empty:
            return pv.PolyData()
        m = pv.PolyData.from_regular_faces(self.points, self.tris)
        if self.block is not None:
            m.cell_data["block"] = self.block.astype(np.int32)
        return m

    def reversed(self) -> Tri:
        return Tri(self.points, self.tris[:, ::-1].copy(), self.block)


def weld(points: np.ndarray, tris: np.ndarray, block: np.ndarray | None = None) -> Tri:
    """Merge bit-identical vertices; drop triangles that become degenerate."""
    uniq, inv = np.unique(points, axis=0, return_inverse=True)
    t = inv.reshape(-1)[tris]
    ok = (t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 2] != t[:, 0])
    return Tri(uniq, t[ok], None if block is None else block[ok])


def clean_contour(grid: pv.ImageData, values: np.ndarray, iso: float, method: str) -> Tri:
    """Contour with no zero-area triangles.

    Marching cubes puts several vertices on one grid node where the node value
    equals the isovalue, which makes zero-area triangles. CGAL corefinement
    fails on them ("Unauthorized intersections of constraints"). Node values
    within eps of the isovalue are moved to iso +/- eps, with eps 1e-4 of the
    median change of the field between two nodes, so no contour vertex is
    nearer than about 1e-4 cell to a node. The surface moves by less than that.
    """
    v = np.array(values, dtype=float)
    finite = np.isfinite(v)
    dims = tuple(int(n) for n in grid.dimensions)
    step = np.abs(np.diff(v.reshape(dims[::-1]), axis=2))
    eps = 1e-4 * float(np.nanmedian(step[np.isfinite(step)]))
    d = v - iso
    near = finite & (np.abs(d) < eps)
    v[near] = iso + np.where(d[near] >= 0.0, eps, -eps)
    m = Tri.from_pv(contour(grid, v, iso, method))
    if m.empty:
        return m
    m = weld(m.points, m.tris)
    p = m.points
    area2 = np.linalg.norm(np.cross(p[m.tris[:, 1]] - p[m.tris[:, 0]],
                                    p[m.tris[:, 2]] - p[m.tris[:, 0]]), axis=1)
    if np.any(area2 == 0.0):
        raise RuntimeError(f"contour has {int((area2 == 0).sum())} zero-area triangles")
    return m


def _to_cgal(m: Tri):
    from loop_cgal import TriMesh

    return TriMesh.from_vertices_and_triangles(m.points.astype(np.float64),
                                               m.tris.astype(np.int32))


def _from_cgal(tm) -> Tri:
    v, t = tm.get_vertices_and_triangles(AREA_EPS, DUP_EPS)
    if len(t) == 0:
        return Tri(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    return weld(np.asarray(v, dtype=np.float64), np.asarray(t, dtype=np.int64))


def orient(m: Tri, fn, h: float) -> Tri:
    """Flip triangles so that each normal points toward increasing ``fn``."""
    if m.empty:
        return m
    p = m.points
    a, b, c = p[m.tris[:, 0]], p[m.tris[:, 1]], p[m.tris[:, 2]]
    n = np.cross(b - a, c - a)
    ln = np.linalg.norm(n, axis=1)
    n = n / np.where(ln > 0, ln, 1.0)[:, None]
    cen = (a + b + c) / 3.0
    fp = np.asarray(fn(cen + h * n), dtype=float)
    fm = np.asarray(fn(cen - h * n), dtype=float)
    flip = fp < fm
    tris = m.tris.copy()
    tris[flip] = tris[flip][:, ::-1]
    return Tri(m.points, tris, m.block)


def cut_keep(target: Tri, clipper: Tri, keep_positive: bool, side_fn, tol: float) -> Tri:
    """Keep the part of ``target`` on one side of ``clipper`` (CGAL corefinement).

    ``clipper`` normals point toward its positive side. CGAL keeps the side
    opposite to the clipper normals, so the clipper is reversed to keep the
    positive side. ``side_fn`` (positive on the positive side) decides the
    result when the two meshes do not intersect.
    """
    if target.empty:
        return target
    if clipper.empty:
        s = np.asarray(side_fn(target.points), dtype=float) * (1.0 if keep_positive else -1.0)
        return target if np.median(s) >= 0 else Tri(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    tm = _to_cgal(target)
    # loop_cgal returns (faces before - faces after). A cut that removes a
    # small part but splits many triangles returns 0 or less, so compare the
    # meshes instead.
    removed = tm.cut_with_surface(_to_cgal(clipper.reversed() if keep_positive else clipper))
    if removed != 0 or tm.n_points != len(target.points):
        return _from_cgal(tm)
    s = np.asarray(side_fn(target.points), dtype=float) * (1.0 if keep_positive else -1.0)
    if np.all(s > -tol):
        return target
    if np.all(s < tol):
        return Tri(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    raise RuntimeError("CGAL cut removed nothing, but the target is on both sides of the clipper")


def split_both(target: Tri, clipper: Tri, side_fn, tol: float) -> Tri:
    """Insert the intersection with ``clipper`` into ``target`` and keep both sides."""
    a = cut_keep(target, clipper, True, side_fn, tol)
    b = cut_keep(target, clipper, False, side_fn, tol)
    if a.empty or b.empty:
        return target
    return weld(np.vstack([a.points, b.points]),
                np.vstack([a.tris, b.tris + len(a.points)]))


# --------------------------------------------------------------------------
# Conformity check
# --------------------------------------------------------------------------


def _edge_set(m: Tri) -> set:
    e = np.concatenate([m.tris[:, [0, 1]], m.tris[:, [1, 2]], m.tris[:, [2, 0]]])
    e.sort(axis=1)
    keys = [tuple(map(tuple, m.points[e[:, 0]])), tuple(map(tuple, m.points[e[:, 1]]))]
    return {frozenset((a, b)) for a, b in zip(*keys)}


def conformity(surface: Tri, fault: Tri, on_fault_fn, tol: float) -> dict:
    """Check that the boundary of ``surface`` on ``fault`` is made of fault edges.

    A boundary vertex is on the fault where |on_fault_fn| < tol (implicit
    distance). Each such vertex must be a fault vertex (bit-identical), and
    each boundary edge between two such vertices must be a fault edge.
    """
    if surface.empty:
        return {"cutoff_vertices": 0, "cutoff_edges": 0}
    be = boundary_edges(surface.to_pv())
    if len(be) == 0:
        return {"cutoff_vertices": 0, "cutoff_edges": 0}
    p = surface.points
    on = np.abs(np.asarray(on_fault_fn(p), dtype=float)) < tol
    on_domain = np.any((np.abs(p) < 1e-12) | (np.abs(p - 1.0) < 1e-12), axis=1)
    be = be[on[be[:, 0]] & on[be[:, 1]] & ~(on_domain[be[:, 0]] & on_domain[be[:, 1]])]
    verts = np.unique(be)
    fault_pts = {tuple(p) for p in fault.points}
    missing_v = sum(tuple(surface.points[v]) not in fault_pts for v in verts)
    fedges = _edge_set(fault)
    missing_e = sum(
        frozenset((tuple(surface.points[a]), tuple(surface.points[b]))) not in fedges for a, b in be
    )
    return {
        "cutoff_vertices": int(len(verts)),
        "cutoff_vertices_not_fault_vertices": int(missing_v),
        "cutoff_edges": int(len(be)),
        "cutoff_edges_not_fault_edges": int(missing_e),
        "max_distance_to_implicit_fault": float(
            np.max(np.abs(np.asarray(on_fault_fn(p[verts]), dtype=float)))) if len(verts) else 0.0,
    }


# --------------------------------------------------------------------------
# Remeshing
# --------------------------------------------------------------------------


def remesh(m: Tri, fixed_edges: np.ndarray, target: float, iterations: int) -> Tri:
    """Isotropic remeshing (Loop CGAL); ``fixed_edges`` are kept unchanged."""
    if m.empty:
        return m
    tm = _to_cgal(m)
    if len(fixed_edges):
        tm.add_fixed_edges(np.ascontiguousarray(fixed_edges, dtype=np.int32))
    tm.remesh(split_long_edges=False, target_edge_length=float(target),
              number_of_iterations=int(iterations), protect_constraints=True,
              relax_constraints=False)
    return _from_cgal(tm)


def _edges_matching(m: Tri, keys: set) -> np.ndarray:
    """Edges of ``m`` (vertex index pairs) whose end points form a key in ``keys``."""
    e = np.concatenate([m.tris[:, [0, 1]], m.tris[:, [1, 2]], m.tris[:, [2, 0]]])
    e.sort(axis=1)
    e = np.unique(e, axis=0)
    pts = [tuple(p) for p in m.points]
    sel = [frozenset((pts[a], pts[b])) in keys for a, b in e]
    return e[np.asarray(sel, dtype=bool)] if len(e) else e


def _boundary_keys(m: Tri) -> set:
    if m.empty:
        return set()
    be = boundary_edges(m.to_pv())
    return {frozenset((tuple(m.points[a]), tuple(m.points[b]))) for a, b in be}


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


@dataclass
class ConformingResult:
    faults: dict[str, Tri] = field(default_factory=dict)
    horizons: dict[str, Tri] = field(default_factory=dict)
    blocks: dict[str, list[str]] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    tip_band: dict = field(default_factory=dict)
    """Per finite fault: band width and the largest field change it made."""


def _check_supported(built: BuiltCase) -> None:
    spec = built.spec
    for fs in spec.faults:
        if fs.faulted_by:
            raise NotImplementedError(f"{spec.name}: fault {fs.name} is displaced by other faults")
        linked = fs.abuts is not None or any(o.abuts and o.abuts[0] == fs.name for o in spec.faults)
        if any(profile_tip_axes(fs.profile)) and linked:
            raise NotImplementedError(f"{spec.name}: fault {fs.name} has a tip and an abutment")
        if fs.truncated_by is not None:
            raise NotImplementedError(f"{spec.name}: fault {fs.name} ends on an unconformity")
    if any(ss.unconformity is not None for ss in spec.series):
        raise NotImplementedError(f"{spec.name}: unconformities are not supported yet")


def _touches(piece: Tri, gx_fn, tol: float) -> bool:
    """True if ``piece`` has boundary vertices on the fault (|gx| < tol).

    Only then does its block contour split the fault mesh: a contour that
    crosses the fault outside its block would add a line that is not a
    cut-off. In symmetric cases (narrow_horst) such a line can lie within
    1e-8 of a true cut-off and break the corefinement.
    """
    if piece.empty:
        return False
    be = np.unique(boundary_edges(piece.to_pv()))
    return bool(np.any(np.abs(np.asarray(gx_fn(piece.points[be]), dtype=float)) < tol))


def _absent(built: BuiltCase, name: str, pattern: dict) -> bool:
    """True if fault ``name`` does not exist in the block (abutment on the other side)."""
    fs = built.spec.fault(name)
    if fs.abuts is None:
        return False
    host, side = fs.abuts
    return host in pattern and pattern[host] != side


def _tip_surface(built: BuiltCase, name: str, resolution: int, method: str) -> tuple[Tri, object]:
    """The surface t = 1 - TIP_LEVEL of the tip function t = min(1 - |g|).

    One surface (a tube around the fault, open where the tip axes allow),
    oriented toward increasing t (into the active region). Using one surface,
    not one sheet per axis, means no corner where three surfaces meet; the
    corners of the tip rectangle are rounded within one cell. Contoured 5
    cells outside the cube, so it is larger than any target.
    """
    from .fields import tip_function

    cell = 1.0 / (resolution - 1)
    grid, pts = _padded_grid(resolution, 5)
    level = 1.0 - TIP_LEVEL

    def fn(p):
        return tip_function(built, name, p) - level

    m = clean_contour(grid, tip_function(built, name, pts), level, method)
    return orient(m, fn, 0.25 * cell), fn


def _bowl(fault: Tri, tube: Tri, tube_fn, gx_fn, cell: float) -> Tri:
    """Boundary of the active footwall of a finite fault, normals outward.

    The active footwall is {gx < 0} inside the tip surface. Its boundary is
    the fault surface inside the tip surface (the same triangles as the fault
    mesh) plus the tip surface on the footwall side. A finite fault cannot
    cut a horizon itself: Loop CGAL would extend it past the tip. The parts
    are trimmed 3 cells outside the cube; every clipper used here is larger.
    """
    f = cut_keep(clip_to_box(fault, -3 * cell, 1 + 3 * cell), tube, True, tube_fn, 1e-9)
    t = cut_keep(clip_to_box(tube, -3 * cell, 1 + 3 * cell), fault, False, gx_fn, 1e-9)
    parts = global_weld([f, t.reversed()], WELD_TOL)  # tube outward = decreasing t
    return weld(np.vstack([parts[0].points, parts[1].points]),
                np.vstack([parts[0].tris, parts[1].tris + len(parts[0].points)]))


def _tip_band(built: BuiltCase, feat, name: str, pattern: dict, grid: pv.ImageData,
              v: np.ndarray, cell: float, record: dict) -> np.ndarray:
    """Footwall block field with the hanging-wall values near the tip.

    The two block fields are equal beyond the tip, but a grid cell that
    crosses the tip has nodes inside it, where they differ. The two contours
    then differ in that cell (up to 0.4 cell for the ``tip`` profile) and do
    not meet on the tip surface. At nodes within two cell diagonals of the
    tip, the footwall field takes the hanging-wall values: these are the
    nodes of the cells that cross the tip surface. The contours are then
    identical near the tip, and the slit closes about one cell inside the tip.
    """
    from .fields import tip_function

    pts = np.asarray(grid.points)
    other = dict(pattern)
    other[name] = 1
    with forced_sides(force_map(built, other)):
        v_hw = np.asarray(feat.evaluate_value(pts, ignore_regions=True), dtype=float)
    t = tip_function(built, name, pts) - (1.0 - TIP_LEVEL)
    dims = tuple(int(n) for n in grid.dimensions)[::-1]  # (z, y, x), x fastest
    grad = np.gradient(t.reshape(dims), cell)
    gnorm = np.sqrt(sum(g**2 for g in grad)).ravel()
    dist = t / np.maximum(gnorm, 1e-12)  # distance into the tip region
    sel = dist < 1.01 * np.sqrt(3.0) * cell
    changed = sel & (t > 0)
    out = v.copy()
    out[sel] = v_hw[sel]
    r = record.setdefault(name, {"band_distance": float(1.01 * np.sqrt(3.0) * cell),
                                 "max_field_change": 0.0})
    if changed.any():
        r["max_field_change"] = max(r["max_field_change"],
                                    float(np.nanmax(np.abs(v[changed] - v_hw[changed]))))
    return out


def _weld_tip_seam(built: BuiltCase, name: str, h: Tri, labels: list[str], tol: float) -> Tri:
    """Join the footwall piece of ``h`` to the other pieces on the tip surface.

    The footwall vertices on the tip surface move onto the nearest vertex of
    the other pieces (< ``tol``). The cut-off end points (on the fault) do not
    move: they are fault vertices. So the slit ends with a notch narrower than
    ``tol`` that extends at most one edge past the tip line.
    """
    from scipy.spatial import cKDTree

    from .fields import tip_function

    if h.empty or h.block is None:
        return h
    fw = [i for i, lab in enumerate(labels) if f"{name}-" in lab.split("_")]
    be = boundary_edges(h.to_pv())
    if len(be) == 0 or not fw:
        return h
    v = np.unique(be)
    on_tip = np.abs(tip_function(built, name, h.points[v]) - (1.0 - TIP_LEVEL)) < 1e-6
    on_fault = np.abs(raw_frame(built.faults[name], h.points[v])) < 1e-6
    v = v[on_tip & ~on_fault]
    is_fw_tri = np.isin(h.block, fw)
    in_fw = np.zeros(len(h.points), dtype=bool)
    in_other = np.zeros(len(h.points), dtype=bool)
    in_fw[h.tris[is_fw_tri].ravel()] = True
    in_other[h.tris[~is_fw_tri].ravel()] = True
    src = v[in_fw[v] & ~in_other[v]]
    dst = v[in_other[v] & ~in_fw[v]]
    if len(src) == 0 or len(dst) == 0:
        return h
    d, i = cKDTree(h.points[dst]).query(h.points[src])
    ok = d < tol
    hp = h.points.copy()
    hp[src[ok]] = h.points[dst[i[ok]]]
    return weld(hp, h.tris, h.block)


def _padded_grid(resolution: int, pad: int) -> tuple[pv.ImageData, np.ndarray]:
    cell = 1.0 / (resolution - 1)
    grid = pv.ImageData(dimensions=(resolution + 2 * pad,) * 3, spacing=(cell,) * 3,
                        origin=(-pad * cell,) * 3)
    return grid, np.asarray(grid.points)


def build_conforming(built: BuiltCase, resolution: int = 97,
                     method: str = "marching_cubes") -> ConformingResult:
    """Build the conforming surfaces (see the module notes).

    Loop CGAL extends a clipper at its boundary by a tangent strip. Where two
    strips meet (corners) they cross, and a cut that reaches them fails. So
    each clipper is made larger than the surface it cuts: faults are
    contoured 4 cells outside the cube, abutting faults 3, horizons 2, and a
    fault is trimmed to 1 cell outside the cube before the curves are
    inserted. Every surface is clipped to the cube with exact planes.
    """
    _check_supported(built)
    spec = built.spec
    cell = 1.0 / (resolution - 1)
    h = 0.25 * cell
    res = ConformingResult()

    def gx(name):
        return lambda p, f=built.faults[name]: raw_frame(f, p)

    # 1. Faults: full contour, then the abutment cut or the tip cut.
    t0 = time.perf_counter()
    raw_fault: dict[str, Tri] = {}
    bowl: dict[str, Tri] = {}
    sides = SideFunctions(built)  # no tip margin: the bowl closes at the tip
    for fs in spec.fault_build_order():
        if fs.abuts is not None and spec.fault(fs.abuts[0]).abuts is not None:
            raise NotImplementedError(f"{spec.name}: chain of abutments at {fs.name}")
        grid, pts = _padded_grid(resolution, 3 if fs.abuts else 4)
        m = clean_contour(grid, raw_frame(built.faults[fs.name], pts), 0.0, method)
        m = orient(m, gx(fs.name), h)
        raw_fault[fs.name] = m
        if fs.abuts is not None:
            host, side = fs.abuts
            m = cut_keep(m, raw_fault[host], side > 0,
                         lambda p, s=side, g=gx(host): s * g(p), 1e-9)
        if any(profile_tip_axes(fs.profile)):
            tube, tube_fn = _tip_surface(built, fs.name, resolution, method)
            if not tube.empty:  # else the tip is outside the model: an infinite fault
                m = cut_keep(m, tube, True, tube_fn, 1e-9)
                bowl[fs.name] = _bowl(raw_fault[fs.name], tube, tube_fn, gx(fs.name), cell)
        res.faults[fs.name] = m
    res.timings["faults"] = time.perf_counter() - t0

    # 2. Horizons: one smooth field per block, cut by the bounding faults.
    #    Abutting faults cut first, with their full (raw) surface: inside the
    #    host's block this is the same half-space, and the triple point then
    #    lies inside the host clipper, not on a clipper boundary.
    t0 = time.perf_counter()
    grid, pts = _padded_grid(resolution, 2)
    cutters: dict[str, list[Tri]] = {n: [] for n in res.faults}
    for ss in spec.series:
        feat = built.series[ss.name]
        pieces: dict[int, list[Tri]] = {k: [] for k in range(len(ss.isovalues))}
        labels: list[str] = []
        order = sorted(clip_order(built, list(ss.faults)),
                       key=lambda n: spec.fault(n).abuts is None)
        for pattern in sign_patterns(built, list(ss.faults)):
            labels.append(block_label(pattern))
            with forced_sides(force_map(built, pattern)):
                v = np.asarray(feat.evaluate_value(pts, ignore_regions=True), dtype=float)
            for n in bowl:
                if pattern.get(n, 1) < 0:
                    v = _tip_band(built, feat, n, pattern, grid, v, cell, res.tip_band)
            with forced_sides(force_map(built, pattern)):
                raw = []
                for iso in ss.isovalues:
                    c = clean_contour(grid, v, iso, method)
                    c = orient(c, lambda p: np.asarray(
                        feat.evaluate_value(p, ignore_regions=True), dtype=float), h)
                    raw.append(c)
            active = [n for n in order if not _absent(built, n, pattern)]
            for k, c in enumerate(raw):
                piece = c
                for n in active:
                    if piece.empty:
                        break
                    if n in bowl:  # finite fault: outside / inside the active footwall
                        piece = cut_keep(piece, bowl[n], pattern[n] > 0,
                                         lambda p, n=n: sides(n, p), 1e-9)
                    else:
                        piece = cut_keep(piece, raw_fault[n], pattern[n] > 0, gx(n), 1e-9)
                piece = clip_to_domain(piece)
                for n in active:
                    if _touches(piece, gx(n), 1e-3 * cell / (spec.fault(n).minor_axis / 2)):
                        cutters[n].append(c)
                piece.block = np.full(len(piece.tris), len(labels) - 1, dtype=np.int32)
                pieces[k].append(piece)
        for k in range(len(ss.isovalues)):
            parts = [p for p in pieces[k] if not p.empty]
            if not parts:
                continue
            off = np.cumsum([0] + [len(p.points) for p in parts])
            sid = f"horizon_{ss.name}_{k}"
            res.horizons[sid] = Tri(np.vstack([p.points for p in parts]),
                                    np.vstack([p.tris + o for p, o in zip(parts, off)]),
                                    np.concatenate([p.block for p in parts]))
            res.blocks[sid] = labels
    res.timings["horizons"] = time.perf_counter() - t0

    # 3. Insert the shared curves into each fault (trimmed to 1 cell outside
    #    the cube, so every clipper is larger): junctions, then cut-offs.
    t0 = time.perf_counter()
    for fs in spec.fault_build_order():
        abutting = [raw_fault[o.name] for o in spec.faults
                    if o.abuts is not None and o.abuts[0] == fs.name]
        m = clip_to_box(res.faults[fs.name], -cell, 1.0 + cell)
        for c in abutting + cutters[fs.name]:
            m = split_both(m, c, lambda p: np.ones(len(p)), 1e-9)
        res.faults[fs.name] = clip_to_domain(m)
    res.timings["insert_curves"] = time.perf_counter() - t0

    # 4. One weld over all surfaces. The exact kernel rounds one point in
    #    different ways in different cuts (< 1e-13), and a cut near a vertex
    #    makes almost-duplicate vertices (1e-13 to 1e-8 apart). Vertices
    #    nearer than WELD_TOL become one vertex; a fault vertex is kept first.
    meshes = [res.faults[fs.name] for fs in spec.fault_build_order()]
    meshes += list(res.horizons.values())
    welded = global_weld(meshes, WELD_TOL)
    names = [fs.name for fs in spec.fault_build_order()]
    for name, m in zip(names, welded):
        res.faults[name] = m
    for sid, m in zip(list(res.horizons), welded[len(names):]):
        res.horizons[sid] = m
    # 4b. Finite faults: the hanging-wall and footwall pieces of a horizon
    #     meet on the tip sheets. The two block fields are equal there, but a
    #     grid cell that crosses the tip has nodes inside it, so the two
    #     contours differ by up to about 1e-3 cell. Move each footwall vertex
    #     on the tip surface onto the nearest hanging-wall vertex (< 0.01 cell).
    for n in bowl:
        for sid in res.horizons:
            res.horizons[sid] = _weld_tip_seam(built, n, res.horizons[sid], res.blocks[sid],
                                               0.01 * cell)
    # 5. T-junctions: where another curve crosses a cut-off line, the fault
    #    has a vertex inside a boundary edge of the surface. Split that edge.
    for fs in spec.fault_build_order():
        if fs.abuts is not None:
            res.faults[fs.name] = split_t_junctions(res.faults[fs.name], res.faults[fs.abuts[0]])
    for sid in res.horizons:
        for f in res.faults.values():
            res.horizons[sid] = split_t_junctions(res.horizons[sid], f)
    # 6. The other direction: a boundary vertex of a surface inside a fault
    #    edge. This happens where an earlier cut (another fault less than a
    #    cell away) added edges to a horizon triangle that the fault also
    #    crosses. Split the fault edge at that vertex.
    for fs in spec.fault_build_order():
        others = [res.horizons[sid] for sid in res.horizons]
        others += [res.faults[o.name] for o in spec.faults
                   if o.abuts is not None and o.abuts[0] == fs.name]
        pts = [m.points[np.unique(boundary_edges(m.to_pv()))] for m in others if not m.empty]
        if pts:
            res.faults[fs.name] = insert_points_on_edges(res.faults[fs.name], np.vstack(pts))
    return res


WELD_TOL = 1e-8
# A finite fault mesh (and the bowl) ends at |g| = TIP_LEVEL, a little beyond
# the tip |g| = 1, where the displacement is already zero. At exactly 1, a
# horizon designed to pass through the tip line (fault_tip, iso 0.25) meets
# the bowl crease, and CGAL fails ("Unauthorized intersections").
TIP_LEVEL = 1.0 + 1e-3


def global_weld(meshes: list[Tri], tol: float) -> list[Tri]:
    """Merge vertices nearer than ``tol`` over all meshes; the first mesh wins.

    Each cluster gets the coordinates of its vertex from the earliest mesh in
    ``meshes``. Triangles that become degenerate are removed.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree

    sizes = [len(m.points) for m in meshes]
    pts = np.vstack([m.points for m in meshes if len(m.points)])
    pairs = cKDTree(pts).query_pairs(tol, output_type="ndarray")
    n = len(pts)
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    _, label = connected_components(graph, directed=False)
    first = np.full(label.max() + 1, n, dtype=np.int64)
    np.minimum.at(first, label, np.arange(n))
    rep_pts = pts[first[label]]
    out, off = [], 0
    for m, k in zip(meshes, sizes):
        if m.empty:
            out.append(m)
        else:
            out.append(weld(rep_pts[off:off + k], m.tris, m.block))
        off += k
    return out


def clip_to_box(m: Tri, lo: float, hi: float) -> Tri:
    """Clip to the cube [lo, hi]^3 with exact planes (loop_cgal keeps a x + ... + d <= 0)."""
    if m.empty:
        return m
    if np.all(m.points >= lo) and np.all(m.points <= hi):
        return m
    tm = _to_cgal(m)
    for axis in range(3):
        n = [0.0, 0.0, 0.0]
        n[axis] = -1.0
        tm.clip_with_plane(n[0], n[1], n[2], float(lo))      # -x + lo <= 0
        n[axis] = 1.0
        tm.clip_with_plane(n[0], n[1], n[2], -float(hi))     # x - hi <= 0
    return _from_cgal(tm)


def clip_to_domain(m: Tri) -> Tri:
    """Clip to the unit cube with exact planes."""
    return clip_to_box(m, 0.0, 1.0)


def split_t_junctions(m: Tri, master: Tri, tol: float = WELD_TOL) -> Tri:
    """Split each boundary edge of ``m`` at the ``master`` vertices that lie on it.

    The inserted vertices are copies of the master vertices (bit-identical).
    The triangle of the edge becomes a fan from its opposite vertex.
    """
    from scipy.spatial import cKDTree

    if m.empty or master.empty:
        return m
    tris = m.tris
    be = boundary_edges(m.to_pv())
    if len(be) == 0:
        return m
    tree = cKDTree(master.points)
    # Oriented edge -> triangle index, for the triangle that owns each boundary edge.
    owner = {}
    for t, (i, j, k) in enumerate(tris):
        for u, v, w in ((i, j, k), (j, k, i), (k, i, j)):
            owner[(u, v)] = (t, w)
    pts = list(map(np.asarray, m.points))
    new_pts: list[np.ndarray] = []
    replace: dict[int, list] = {}
    for a, b in be:
        pa, pb = m.points[a], m.points[b]
        d = pb - pa
        length2 = float(d @ d)
        if length2 == 0.0:
            continue
        cand = tree.query_ball_point((pa + pb) / 2.0, np.sqrt(length2) / 2.0 + tol)
        hits = []
        for i in cand:
            q = master.points[i]
            t = float((q - pa) @ d) / length2
            if 1e-9 < t < 1.0 - 1e-9 and np.linalg.norm(pa + t * d - q) < tol:
                hits.append((t, i))
        if not hits:
            continue
        hits.sort()
        if (a, b) in owner:
            u, v = a, b
        else:
            u, v = b, a
            hits = [(1.0 - t, i) for t, i in hits][::-1]
        tri, w = owner[(u, v)]
        chain = [u]
        for _, i in hits:
            new_pts.append(master.points[i])
            chain.append(len(pts) + len(new_pts) - 1)
        chain.append(v)
        replace.setdefault(tri, []).extend(
            [(chain[s], chain[s + 1], w) for s in range(len(chain) - 1)]
        )
    if not replace:
        return m
    # Two split edges in one triangle have two different opposite vertices.
    if any(len({x[2] for x in r}) > 1 for r in replace.values()):
        raise RuntimeError("a triangle has T-junctions on two edges; not supported")
    keep = np.ones(len(tris), dtype=bool)
    keep[list(replace)] = False
    add = np.array([x for r in replace.values() for x in r], dtype=np.int64)
    block = None
    if m.block is not None:
        add_block = np.concatenate([np.full(len(r), m.block[t]) for t, r in replace.items()])
        block = np.concatenate([m.block[keep], add_block])
    all_pts = np.vstack([m.points] + ([np.asarray(new_pts)] if new_pts else []))
    return weld(all_pts, np.vstack([tris[keep], add]), block)


def insert_points_on_edges(m: Tri, points: np.ndarray, tol: float = WELD_TOL) -> Tri:
    """Insert each of ``points`` that lies inside an edge of ``m`` (not at a vertex).

    The inserted vertices are copies of the points (bit-identical). Each
    changed triangle is split as a fan from its centroid, so no triangle is
    degenerate, whatever edges carry points.
    """
    from scipy.spatial import cKDTree

    if m.empty or len(points) == 0:
        return m
    vkeys = {tuple(p) for p in m.points}
    points = np.unique(points, axis=0)
    points = points[[tuple(p) not in vkeys for p in points]]
    if len(points) == 0:
        return m
    e = np.concatenate([m.tris[:, [0, 1]], m.tris[:, [1, 2]], m.tris[:, [2, 0]]])
    e.sort(axis=1)
    edges = np.unique(e, axis=0)
    a, b = m.points[edges[:, 0]], m.points[edges[:, 1]]
    half = 0.5 * np.linalg.norm(b - a, axis=1)
    tree = cKDTree(0.5 * (a + b))
    on_edge: dict[tuple, list] = {}
    for q_i, cand in enumerate(tree.query_ball_point(points, float(half.max()) + tol)):
        q = points[q_i]
        for ei in cand:
            d = b[ei] - a[ei]
            length2 = float(d @ d)
            t = float((q - a[ei]) @ d) / length2
            if 1e-9 < t < 1.0 - 1e-9 and np.linalg.norm(a[ei] + t * d - q) < tol:
                on_edge.setdefault(tuple(edges[ei]), []).append((t, q_i))
                break
    if not on_edge:
        return m
    new_pts = [m.points, points]
    base = len(m.points)
    centroids = []
    keep = np.ones(len(m.tris), dtype=bool)
    add = []
    for ti, tri in enumerate(m.tris):
        ring = []
        changed = False
        for u, v in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            ring.append(u)
            key = (min(u, v), max(u, v))
            hits = sorted(on_edge.get(key, []))
            if hits:
                changed = True
                if u > v:  # t is measured from the smaller index
                    hits = [(1.0 - t, q) for t, q in hits][::-1]
                ring += [base + q for _, q in hits]
        if not changed:
            continue
        keep[ti] = False
        c = base + len(points) + len(centroids)
        centroids.append(m.points[tri].mean(axis=0))
        add += [(ring[i], ring[(i + 1) % len(ring)], c) for i in range(len(ring))]
    new_pts.append(np.asarray(centroids))
    tris = np.vstack([m.tris[keep], np.asarray(add, dtype=np.int64)])
    return weld(np.vstack(new_pts), tris)


def check_conformity(built: BuiltCase, res: ConformingResult, cell: float) -> dict:
    out = {}
    # Cut-off vertices are within about 1e-6 of the implicit fault; the seam
    # vertices of a finite fault on the tip surface can be 1e-4 from it.
    tol = 1e-3 * cell
    for sid, m in res.horizons.items():
        for name, f in res.faults.items():
            fs = built.spec.fault(name)
            r = conformity(m, f, lambda p, g=built.faults[name], s=fs.minor_axis / 2:
                           raw_frame(g, p) * s, tol)
            if r["cutoff_edges"]:
                out[f"{sid}|fault_{name}"] = r
    for fs in built.spec.faults:
        if fs.abuts is not None:
            host = fs.abuts[0]
            hs = built.spec.fault(host)
            r = conformity(res.faults[fs.name], res.faults[host],
                           lambda p, g=built.faults[host], s=hs.minor_axis / 2:
                           raw_frame(g, p) * s, tol)
            out[f"fault_{fs.name}|fault_{host}"] = r
    return out


def remesh_all(built: BuiltCase, res: ConformingResult, target: float,
               iterations: int = 5) -> ConformingResult:
    """Remesh every surface; boundary edges and shared curves stay fixed."""
    shared: set = set()
    for m in list(res.horizons.values()) + list(res.faults.values()):
        shared |= _boundary_keys(m)
    out = ConformingResult(blocks=res.blocks)
    t0 = time.perf_counter()
    for sid, m in res.horizons.items():
        r = remesh(m, _edges_matching(m, _boundary_keys(m)), target, iterations)
        out.horizons[sid] = _transfer_block(m, r)
    for name, m in res.faults.items():
        out.faults[name] = remesh(m, _edges_matching(m, shared), target, iterations)
    out.timings["remesh"] = time.perf_counter() - t0
    return out


def _transfer_block(src: Tri, dst: Tri) -> Tri:
    """Block id of each remeshed triangle: the block of the nearest source triangle."""
    if src.block is None or dst.empty:
        return dst
    from scipy.spatial import cKDTree

    cs = src.points[src.tris].mean(axis=1)
    cd = dst.points[dst.tris].mean(axis=1)
    _, i = cKDTree(cs).query(cd)
    return Tri(dst.points, dst.tris, src.block[i])


def _quality(m: Tri) -> dict:
    """Mesh quality, plus connected pieces and boundary loops (a hole adds a loop)."""
    mesh = m.to_pv()
    q = mesh_quality(mesh)
    if not m.empty:
        _, counts = edge_counts(m.tris)
        q["nonmanifold_edges"] = int((counts > 2).sum())
        q["connected_pieces"] = int(mesh.connectivity().point_data["RegionId"].max() + 1)
        loops = mesh.extract_feature_edges(boundary_edges=True, feature_edges=False,
                                           manifold_edges=False, non_manifold_edges=False)
        q["boundary_loops"] = (int(loops.connectivity().point_data["RegionId"].max() + 1)
                               if loops.n_points else 0)
    return q


def write_conforming(built: BuiltCase, out_dir: Path, resolution: int = 97,
                     method: str = "marching_cubes", remesh_target: float = 0.0,
                     remesh_iterations: int = 5) -> dict:
    """Write ``<out_dir>/<case>/surfaces_conforming/corefined`` and ``conforming.json``.

    ``remesh_target > 0`` also writes ``remeshed/`` (experimental: see the
    module notes; its ``conforming`` flag in the QA file is usually false).
    """
    cell = 1.0 / (resolution - 1)
    folder = Path(out_dir) / built.spec.name / "surfaces_conforming"
    res = build_conforming(built, resolution, method)
    stages = {"corefined": res}
    if (folder / "remeshed").exists():
        import shutil

        shutil.rmtree(folder / "remeshed")
    if remesh_target > 0:
        stages["remeshed"] = remesh_all(built, res, remesh_target, remesh_iterations)
    report: dict = {"case": built.spec.name, "resolution": resolution, "method": method,
                    "remesh_target_edge_length": remesh_target, "stages": {}}
    for stage, r in stages.items():
        d = folder / stage
        d.mkdir(parents=True, exist_ok=True)
        surfaces = {}
        for name, m in r.faults.items():
            m.to_pv().save(d / f"fault_{name}.vtp")
            surfaces[f"fault_{name}"] = {"quality": _quality(m)}
        for sid, m in r.horizons.items():
            m.to_pv().save(d / f"{sid}.vtp")
            surfaces[sid] = {"quality": _quality(m), "blocks": r.blocks.get(sid, [])}
        conf = check_conformity(built, r, cell)
        report["stages"][stage] = {
            "timings_seconds": r.timings,
            "tip_band": r.tip_band,
            "surfaces": surfaces,
            "conformity": conf,
            "conforming": all(
                c.get("cutoff_edges_not_fault_edges", 0) == 0
                and c.get("cutoff_vertices_not_fault_vertices", 0) == 0 for c in conf.values()
            ),
        }
    (folder / "conforming.json").write_text(json.dumps(report, indent=1))
    return report
