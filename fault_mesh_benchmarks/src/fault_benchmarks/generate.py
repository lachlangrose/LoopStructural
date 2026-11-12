"""Generate all benchmark outputs for one built case."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyvista as pv

from .builder import BuiltCase, restore
from .fields import (
    SideFunctions,
    actual_pattern,
    block_label,
    clip_order,
    fault_displacement_sides,
    force_map,
    forced_sides,
    own_displacement,
    raw_frame,
    sign_patterns,
)
from .spec import profile_tip_axes
from .surfaces import (
    Constraint,
    boundary_edges,
    clip,
    contour,
    domain_constraints,
    edges_to_polylines,
    mesh_quality,
    tag_boundary,
    triangle_normals,
    triangles,
    unit_grid,
)

FORMAT_VERSION = "1.0"


@dataclass
class Options:
    resolution: int = 97
    """Grid nodes per axis for the reference isosurfaces."""
    volume_resolution: int = 49
    """Grid nodes per axis for the exported implicit field volume."""
    method: str = "marching_cubes"
    formats: tuple[str, ...] = ("vtp", "obj", "stl")
    displacement_samples: int = 256


@dataclass
class Patch:
    """One reference surface. ``mesh.cell_data['block']`` indexes ``blocks``."""

    surface_id: str
    kind: str  # horizon | fault
    owner: str  # series or fault name
    iso: float | None
    mesh: pv.PolyData
    blocks: list[dict]
    constraints: list[list[Constraint]]
    files: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Constraint / clip construction
# --------------------------------------------------------------------------


def _fault_side_constraints(built: BuiltCase, sides: SideFunctions, pattern: dict) -> list:
    out = []
    for n in clip_order(built, list(pattern)):
        s = pattern[n]
        out.append(
            Constraint(
                tag=f"fault:{n}",
                fn=(lambda p, n=n, s=s: s * sides(n, p)),
                kind="fault",
                meta={"fault": n, "block_side": int(s)},
            )
        )
    return out


def _younger_unconformities(built: BuiltCase, series_name: str) -> list:
    out = []
    for ss in built.spec.series:
        if ss.name == series_name:
            break
        if ss.unconformity is not None:
            feat = built.series[ss.name]
            out.append(
                Constraint(
                    tag=f"unconformity:{ss.name}",
                    fn=(
                        lambda p, f=feat, v=ss.unconformity: v
                        - np.asarray(f.evaluate_value(p, ignore_regions=True), dtype=float)
                    ),
                    kind="unconformity",
                    meta={"series": ss.name, "value": ss.unconformity},
                )
            )
    return out


def _fault_geometry_constraints(built: BuiltCase, name: str) -> list:
    fs = built.spec.fault(name)
    fault = built.faults[name]
    out = []
    if fs.abuts is not None:
        other, side = fs.abuts
        out.append(
            Constraint(
                tag=f"fault:{other}",
                fn=(lambda p, o=built.faults[other], s=side: s * raw_frame(o, p)),
                kind="fault",
                meta={"fault": other, "relation": "abutment", "side": int(side)},
            )
        )
    tip_y, tip_z = profile_tip_axes(fs.profile)
    for coord, has_tip, label in ((1, tip_y, "gy"), (2, tip_z, "gz")):
        if has_tip:
            out.append(
                Constraint(
                    tag=f"tip:{name}",
                    fn=(lambda p, c=coord: 1.0 - np.abs(raw_frame(fault, p, c))),
                    kind="tip",
                    meta={"fault": name, "frame_coordinate": label},
                )
            )
    if fs.truncated_by is not None:
        sname, value = fs.truncated_by
        feat = built.series[sname]
        out.append(
            Constraint(
                tag=f"unconformity:{sname}",
                fn=(
                    lambda p, f=feat, v=value: v
                    - np.asarray(f.evaluate_value(p, ignore_regions=True), dtype=float)
                ),
                kind="unconformity",
                meta={"series": sname, "value": value},
            )
        )
    return out


# --------------------------------------------------------------------------
# Surface extraction
# --------------------------------------------------------------------------


def _extract(grid, values, iso, constraints, method) -> pv.PolyData:
    """Contour, then clip exactly by every non-domain constraint (no snapping)."""
    surf = contour(grid, values, iso, method)
    for c in constraints:
        if c.kind == "domain":
            continue
        surf = clip(surf, c.fn)
        if surf.n_points == 0:
            return surf
    return surf


def _finish(surf: pv.PolyData, cell: float) -> pv.PolyData:
    """Merge vertices closer than 1e-3 cell and keep triangles only.

    This removes needles made where a clip zero set passes very near an
    existing vertex; points move by at most 1e-3 cell. Cell data is kept.
    """
    surf = surf.clean(tolerance=1e-3 * cell, absolute=True)
    if surf.faces.size == 0:
        return pv.PolyData()
    first = surf.n_verts + surf.n_lines  # cell data order: verts, lines, polys
    out = pv.PolyData(np.asarray(surf.points), faces=surf.faces)
    for k in surf.cell_data.keys():
        out.cell_data[k] = np.asarray(surf.cell_data[k])[first : first + out.n_cells]
    out = out.clean(tolerance=0.0)
    out.point_data.clear()
    return out


def _merge_blocks(parts: list[tuple[dict, pv.PolyData]], cell: float) -> pv.PolyData:
    """Join the block pieces of one surface.

    Where two blocks have equal fields (beyond a fault tip) their pieces have
    identical triangles along the common clip, so the merge joins them into
    one connected surface. Across an active fault the pieces stay separate.
    """
    meshes = []
    for b, (_pattern, m) in enumerate(parts):
        m = m.copy()
        m.point_data.clear()
        m.cell_data.clear()
        m.cell_data["block"] = np.full(m.n_cells, b, dtype=np.int32)
        meshes.append(m)
    merged = pv.merge(meshes, merge_points=True) if len(meshes) > 1 else meshes[0]
    if isinstance(merged, pv.UnstructuredGrid):
        merged = merged.extract_surface(algorithm="dataset_surface")
    return _finish(merged, cell)


def _make_patch(surface_id, kind, owner, iso, parts, cons, cell) -> Patch | None:
    if not parts:
        return None
    mesh = _merge_blocks(parts, cell)
    if mesh.n_cells == 0:
        return None
    return Patch(
        surface_id=surface_id, kind=kind, owner=owner, iso=iso, mesh=mesh,
        blocks=[pat for pat, _ in parts], constraints=list(cons),
    )


def extract_fault_patches(built: BuiltCase, sides: SideFunctions, opts: Options) -> list[Patch]:
    grid = unit_grid(opts.resolution)
    cell = float(np.min(grid.spacing))
    pts = np.asarray(grid.points)
    patches = []
    for fs in built.spec.fault_build_order():
        fault = built.faults[fs.name]
        parts, cons_list = [], []
        for pattern in sign_patterns(built, list(fs.faulted_by)):
            with forced_sides(force_map(built, pattern)):
                gx = raw_frame(fault, pts)
                cons = _fault_side_constraints(built, sides, pattern)
                cons += _fault_geometry_constraints(built, fs.name)
                surf = _extract(grid, gx, 0.0, cons, opts.method)
            if surf.n_cells:
                parts.append((pattern, surf))
                cons_list.append(cons + domain_constraints())
        patch = _make_patch(f"fault_{fs.name}", "fault", fs.name, 0.0, parts, cons_list, cell)
        if patch is not None:
            patches.append(patch)
    return patches


def extract_horizon_patches(built: BuiltCase, sides: SideFunctions, opts: Options) -> list[Patch]:
    grid = unit_grid(opts.resolution)
    cell = float(np.min(grid.spacing))
    pts = np.asarray(grid.points)
    patches = []
    for ss in built.spec.series:
        feat = built.series[ss.name]
        parts: dict[int, list] = {k: [] for k in range(len(ss.isovalues))}
        cons_by_k: dict[int, list] = {k: [] for k in range(len(ss.isovalues))}
        for pattern in sign_patterns(built, list(ss.faults)):
            with forced_sides(force_map(built, pattern)):
                v = np.asarray(feat.evaluate_value(pts, ignore_regions=True), dtype=float)
                cons = _fault_side_constraints(built, sides, pattern)
                cons += _younger_unconformities(built, ss.name)
                for k, iso in enumerate(ss.isovalues):
                    surf = _extract(grid, v, iso, cons, opts.method)
                    if surf.n_cells:
                        parts[k].append((pattern, surf))
                        cons_by_k[k].append(cons + domain_constraints())
        for k, iso in enumerate(ss.isovalues):
            patch = _make_patch(f"horizon_{ss.name}_{k}", "horizon", ss.name, float(iso),
                                parts[k], cons_by_k[k], cell)
            if patch is not None:
                patches.append(patch)
    return patches


# --------------------------------------------------------------------------
# Boundary classification and displacement on fault patches
# --------------------------------------------------------------------------


def classify_patch(built: BuiltCase, patch: Patch, tol: float) -> list[dict]:
    """Tag the boundary of one surface; one record per (block, constraint curve)."""
    mesh = patch.mesh
    edges = boundary_edges(mesh)
    if len(edges) == 0:
        return []
    pts = np.asarray(mesh.points)
    tris = triangles(mesh)
    tn = triangle_normals(mesh)
    e_all = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e_all.sort(axis=1)
    owner_of = np.tile(np.arange(len(tris)), 3)
    key = {tuple(e): owner_of[i] for i, e in enumerate(e_all)}
    owner = np.array([key[tuple(e)] for e in edges])
    eblock = np.asarray(mesh.cell_data["block"])[owner]
    records = []
    for b in np.unique(eblock):
        pattern = patch.blocks[b]
        label = block_label(pattern)
        eb = edges[eblock == b]
        enorm_b = tn[owner[eblock == b]]
        mid = 0.5 * (pts[eb[:, 0]] + pts[eb[:, 1]])
        with forced_sides(force_map(built, pattern)):
            _, tags, dist, cnormal = tag_boundary(mesh, patch.constraints[b], tol, edges=eb)
            tags = np.array(tags, dtype=object)
            for tag in sorted(set(tags)):
                sel = tags == tag
                kind = tag.split(":")[0]
                if kind == "fault" and patch.kind == "horizon":
                    fname = tag.split(":", 1)[1]
                    dh, dfw = fault_displacement_sides(built, fname, mid[sel])
                    jump = np.linalg.norm(dh - dfw, axis=1)
                    active = jump > 1e-3 * abs(built.spec.fault(fname).displacement)
                    # Active cut-off, or a seam with no offset (beyond a tip line).
                    for flag, sub in ((True, f"cutoff:{fname}"), (False, f"seam:{fname}")):
                        m = np.zeros(len(eb), dtype=bool)
                        m[np.where(sel)[0][active == flag]] = True
                        if m.any():
                            records.append(_record(patch, label, sub, eb[m], pts, enorm_b[m],
                                                   cnormal[m], dist[m], jump[active == flag],
                                                   sharp=flag))
                    continue
                sharp = kind in ("fault", "unconformity", "domain")
                rec_tag = tag
                if kind == "fault" and patch.kind == "fault":
                    rec_tag = f"junction:{tag.split(':', 1)[1]}"
                records.append(_record(patch, label, rec_tag, eb[sel], pts, enorm_b[sel],
                                       cnormal[sel], dist[sel], None, sharp))
    return records


def _record(patch, block, tag, edges, pts, enorm, cnormal, dist, jump, sharp) -> dict:
    seg = pts[edges[:, 1]] - pts[edges[:, 0]]
    length = float(np.linalg.norm(seg, axis=1).sum())
    cosang = np.abs(np.sum(enorm * cnormal, axis=1))
    angle = np.degrees(np.arccos(np.clip(cosang, 0, 1)))
    rec = {
        "surface": patch.surface_id,
        "block": block,
        "tag": tag,
        "kind": tag.split(":")[0],
        "with": tag.split(":", 1)[1] if ":" in tag else None,
        "sharp": bool(sharp),
        "n_edges": int(len(edges)),
        "length": length,
        "dihedral_deg": {
            "min": float(angle.min()),
            "mean": float(angle.mean()),
            "max": float(angle.max()),
        },
        "max_distance_to_constraint": float(np.max(dist)),
        "_edges": edges,
        "_points": pts,
    }
    if jump is not None and len(jump):
        rec["slip_jump"] = {"min": float(jump.min()), "max": float(jump.max())}
    return rec


def fault_patch_displacements(built: BuiltCase, patch: Patch) -> dict:
    pts = np.asarray(patch.mesh.points)
    dh = np.zeros_like(pts)
    dfw = np.zeros_like(pts)
    tris = triangles(patch.mesh)
    block = np.asarray(patch.mesh.cell_data["block"])
    for b, pattern in enumerate(patch.blocks):
        ids = np.unique(tris[block == b])
        if len(ids) == 0:
            continue
        with forced_sides(force_map(built, pattern)):
            h, f = fault_displacement_sides(built, patch.owner, pts[ids])
        dh[ids], dfw[ids] = h, f
    patch.mesh.point_data["displacement_hanging_wall"] = dh
    patch.mesh.point_data["displacement_footwall"] = dfw
    patch.mesh.point_data["slip_jump"] = dh - dfw
    patch.mesh.point_data["slip_jump_magnitude"] = np.linalg.norm(dh - dfw, axis=1)
    return {"hanging_wall": dh, "footwall": dfw}


# --------------------------------------------------------------------------
# Volume fields
# --------------------------------------------------------------------------


def volume_fields(built: BuiltCase, sides: SideFunctions, n: int) -> tuple[pv.ImageData, dict]:
    grid = unit_grid(n)
    pts = np.asarray(grid.points)
    h = 1.0 / (n - 1)
    arrays: dict[str, np.ndarray] = {}
    qa: dict = {"series": {}, "faults": {}}
    for fs in built.spec.faults:
        f = built.faults[fs.name]
        arrays[f"gx:{fs.name}"] = raw_frame(f, pts, 0)
        arrays[f"gy:{fs.name}"] = raw_frame(f, pts, 1)
        arrays[f"gz:{fs.name}"] = raw_frame(f, pts, 2)
        arrays[f"side:{fs.name}"] = np.where(sides(fs.name, pts) >= 0, 1, -1).astype(np.int8)
        own = own_displacement(built, fs.name, pts)
        arrays[f"displacement:{fs.name}"] = own
        dh, dfw = fault_displacement_sides(built, fs.name, pts)
        arrays[f"displacement_hanging_wall:{fs.name}"] = dh
        arrays[f"displacement_footwall:{fs.name}"] = dfw
        mag = np.linalg.norm(own, axis=1)
        active = mag > 1e-4 * max(abs(fs.displacement), 1e-12)
        if active.any():
            lo, hi = pts[active].min(axis=0), pts[active].max(axis=0)
            qa["faults"][fs.name] = {
                "influence_bbox": [lo.tolist(), hi.tolist()],
                "max_displacement": float(mag.max()),
                "active_fraction": float(active.mean()),
            }
        else:
            qa["faults"][fs.name] = {"influence_bbox": None, "max_displacement": 0.0}

    unit = np.full(len(pts), -1, dtype=np.int32)
    unit_offset = 0
    unit_table = []
    for ss in built.spec.series:
        feat = built.series[ss.name]
        names = list(ss.faults)
        pat = actual_pattern(built, sides, names, pts)
        patterns = sign_patterns(built, names)
        block = np.full(len(pts), -1, dtype=np.int32)
        v = np.full(len(pts), np.nan)
        grad = np.full((len(pts), 3), np.nan)
        block_info = []
        for b, pattern in enumerate(patterns):
            want = np.array([pattern[nm] for nm in names], dtype=int)
            inside = np.all(pat == want[None, :], axis=1) if names else np.ones(len(pts), bool)
            with forced_sides(force_map(built, pattern)):
                ext = np.asarray(feat.evaluate_value(pts, ignore_regions=True), dtype=float)
            g = np.gradient(ext.reshape(n, n, n), h)  # d/dz, d/dy, d/dx
            gvec = np.stack([g[2].ravel(), g[1].ravel(), g[0].ravel()], axis=1)
            label = block_label(pattern)
            arrays[f"v_ext:{ss.name}:{label}"] = ext
            block[inside] = b
            v[inside] = ext[inside]
            grad[inside] = gvec[inside]
            block_info.append({"id": b, "label": label, "sides": pattern,
                               "n_nodes": int(inside.sum())})
        truth = np.asarray(feat.evaluate_value(pts, ignore_regions=True), dtype=float)
        near = np.zeros(len(pts), dtype=bool)
        for nm in names:
            s_val = sides(nm, pts)
            gs = np.gradient(s_val.reshape(n, n, n), h)
            gnorm = np.sqrt(sum(c**2 for c in gs)).ravel()
            near |= np.abs(s_val) < 2.0 * h * gnorm
        diff = np.abs(v - truth)
        visible = ~np.isnan(np.asarray(feat.evaluate_value(pts), dtype=float))
        arrays[f"v:{ss.name}"] = v
        arrays[f"grad:{ss.name}"] = grad
        arrays[f"block:{ss.name}"] = block
        arrays[f"visible:{ss.name}"] = visible.astype(np.int8)
        arrays[f"displacement_total:{ss.name}"] = pts - restore(pts, built.series_faults(ss.name))
        isos = np.sort(np.asarray(ss.isovalues))
        k = np.digitize(v, isos)
        free = visible & (unit < 0)
        unit[free] = unit_offset + k[free]
        for i in range(len(isos) + 1):
            unit_table.append({"unit": unit_offset + i, "series": ss.name,
                               "lower": float(isos[i - 1]) if i > 0 else None,
                               "upper": float(isos[i]) if i < len(isos) else None})
        unit_offset += len(isos) + 1
        qa["series"][ss.name] = {
            "blocks": block_info,
            "max_abs_diff_block_composite_vs_loopstructural_away_from_faults": float(
                np.nanmax(diff[~near])) if (~near).any() else 0.0,
            "visible_fraction": float(visible.mean()),
        }
    arrays["unit"] = unit
    qa["units"] = unit_table
    for k, a in arrays.items():
        grid.point_data[k] = a.astype(np.float32) if a.dtype == np.float64 else a
    return grid, qa


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def _write_surface(mesh: pv.PolyData, base: Path, formats) -> dict:
    files = {}
    base.parent.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        path = base.with_suffix(f".{fmt}")
        if fmt == "vtp":
            mesh.save(path)
        elif fmt == "stl":
            mesh.save(path, binary=True)
        elif fmt == "obj":
            _write_obj(mesh, path)
        files[fmt] = path.name
    return files


def _write_obj(mesh: pv.PolyData, path: Path) -> None:
    p = np.asarray(mesh.points)
    t = triangles(mesh) + 1
    with open(path, "w", encoding="ascii") as fh:
        fh.write(f"# {path.stem}\n")
        np.savetxt(fh, p, fmt="v %.9f %.9f %.9f")
        np.savetxt(fh, t, fmt="f %d %d %d")


def _markers(built: BuiltCase, sides: SideFunctions) -> pd.DataFrame:
    rows = []
    for ss in built.spec.series:
        df = built.contact_data[ss.name]
        pts = df[["X", "Y", "Z"]].to_numpy()
        feat = built.series[ss.name]
        names = list(ss.faults)
        pat = actual_pattern(built, sides, names, pts)
        normals = np.full((len(pts), 3), np.nan)
        blocks = np.empty(len(pts), dtype=object)
        for pattern in sign_patterns(built, names):
            want = np.array([pattern[n] for n in names], dtype=int)
            sel = np.all(pat == want[None, :], axis=1) if names else np.ones(len(pts), bool)
            if not sel.any():
                continue
            h = 1e-4
            with forced_sides(force_map(built, pattern)):
                g = np.zeros((sel.sum(), 3))
                for a in range(3):
                    d = np.zeros(3)
                    d[a] = h
                    g[:, a] = (feat.evaluate_value(pts[sel] + d, ignore_regions=True)
                               - feat.evaluate_value(pts[sel] - d, ignore_regions=True)) / (2 * h)
            normals[sel] = g / np.linalg.norm(g, axis=1)[:, None]
            blocks[sel] = block_label(pattern)
        nz = np.clip(normals[:, 2], -1, 1)
        dip = np.degrees(np.arccos(np.abs(nz)))
        sgn = np.where(nz < 0, -1.0, 1.0)
        dipdir = (np.degrees(np.arctan2(sgn * normals[:, 0], sgn * normals[:, 1])) + 360) % 360
        out = df[["X", "Y", "Z", "val"]].copy()
        out["nx"], out["ny"], out["nz"] = normals[:, 0], normals[:, 1], normals[:, 2]
        out["dip"], out["dip_direction"] = dip, dipdir
        out["series"] = ss.name
        out["block"] = blocks
        rows.append(out)
    return pd.concat(rows, ignore_index=True)


def generate_case(built: BuiltCase, out_dir: Path, opts: Options) -> dict:
    spec = built.spec
    t0 = time.perf_counter()
    case_dir = out_dir / spec.name
    for sub in ("surfaces", "constraints", "volume", "data"):
        (case_dir / sub).mkdir(parents=True, exist_ok=True)
    h_ref = 1.0 / (opts.resolution - 1)
    sides = SideFunctions(built, cell=h_ref)
    timings = {"build_model": built.build_seconds}

    t = time.perf_counter()
    fault_patches = extract_fault_patches(built, sides, opts)
    horizon_patches = extract_horizon_patches(built, sides, opts)
    timings["extract_surfaces"] = time.perf_counter() - t

    t = time.perf_counter()
    surfaces_meta = []
    constraint_records = []
    disp_samples = {}
    rng = np.random.default_rng(spec.seed)
    for patch in fault_patches + horizon_patches:
        recs = classify_patch(built, patch, tol=0.75 * h_ref)
        constraint_records.extend(recs)
        if patch.kind == "fault":
            d = fault_patch_displacements(built, patch)
            p = np.asarray(patch.mesh.points)
            k = min(opts.displacement_samples, len(p))
            idx = np.sort(rng.choice(len(p), size=k, replace=False))
            disp_samples.setdefault(patch.owner, []).extend(
                {"xyz": p[i].round(9).tolist(),
                 "hanging_wall": d["hanging_wall"][i].round(9).tolist(),
                 "footwall": d["footwall"][i].round(9).tolist()}
                for i in idx
            )
        patch.mesh.field_data["surface_id"] = np.array([patch.surface_id])
        files = _write_surface(patch.mesh, case_dir / "surfaces" / patch.surface_id, opts.formats)
        bnd = {}
        for r in recs:
            bnd[r["tag"]] = bnd.get(r["tag"], 0.0) + r["length"]
        tri_area = _triangle_areas(patch.mesh)
        cblock = np.asarray(patch.mesh.cell_data["block"])
        surfaces_meta.append({
            "id": patch.surface_id,
            "kind": patch.kind,
            "owner": patch.owner,
            "isovalue": patch.iso,
            "blocks": [{"id": b, "label": block_label(pat),
                        "sides": {k: int(v) for k, v in pat.items()},
                        "area": float(tri_area[cblock == b].sum())}
                       for b, pat in enumerate(patch.blocks)],
            "connected_pieces": int(
                patch.mesh.connectivity().cell_data["RegionId"].max() + 1),
            "files": files,
            "quality": mesh_quality(patch.mesh),
            "boundary_length_by_tag": bnd,
        })
    timings["classify_and_write_surfaces"] = time.perf_counter() - t

    # Constraint polylines in one file, with integer ids per curve.
    curves = []
    meshes = []
    for cid, r in enumerate(constraint_records):
        poly = edges_to_polylines(r.pop("_points"), r.pop("_edges"))
        poly.cell_data["constraint_id"] = np.full(poly.n_cells, cid, dtype=np.int32)
        poly.cell_data["sharp"] = np.full(poly.n_cells, int(r["sharp"]), dtype=np.int8)
        meshes.append(poly)
        curves.append({"id": cid, **r})
    if meshes:
        merged = pv.merge(meshes, merge_points=False)
        merged.save(case_dir / "constraints" / "constraint_curves.vtp")

    t = time.perf_counter()
    vol, vol_qa = volume_fields(built, sides, opts.volume_resolution)
    vol.cast_to_unstructured_grid().save(case_dir / "volume" / "implicit_fields.vtu")
    np.savez_compressed(
        case_dir / "volume" / "implicit_fields.npz",
        origin=np.zeros(3), spacing=np.array(vol.spacing), dimensions=np.array(vol.dimensions),
        **{k.replace(":", "__"): np.asarray(vol.point_data[k]) for k in vol.point_data.keys()},
    )
    timings["volume_fields"] = time.perf_counter() - t

    markers = _markers(built, sides)
    markers.to_csv(case_dir / "data" / "contacts_and_orientations.csv", index=False)
    pd.concat(built.fault_data.values()).to_csv(case_dir / "data" / "fault_observations.csv",
                                                index=False)
    mk = pv.PolyData(markers[["X", "Y", "Z"]].to_numpy())
    mk.point_data["normal"] = markers[["nx", "ny", "nz"]].to_numpy()
    mk.point_data["value"] = markers["val"].to_numpy()
    mk.save(case_dir / "data" / "markers.vtp")

    meta = {
        "format_version": FORMAT_VERSION,
        "case": spec.name,
        "category": spec.category,
        "description": spec.description,
        "tags": spec.tags,
        "variant_of": spec.variant_of,
        "seed": spec.seed,
        "domain": {"bbox": [[0, 0, 0], [1, 1, 1]], "units": "normalised"},
        "options": {"resolution": opts.resolution, "volume_resolution": opts.volume_resolution,
                    "method": opts.method, "reference_cell_size": h_ref},
        "faults": [_fault_meta(built, fs, vol_qa, fault_patches, disp_samples)
                   for fs in spec.faults],
        "series": [_series_meta(built, ss, vol_qa) for ss in spec.series],
        "units": vol_qa["units"],
        "surfaces": surfaces_meta,
        "constraints": curves,
        "files": {
            "volume_vtu": "volume/implicit_fields.vtu",
            "volume_npz": "volume/implicit_fields.npz",
            "constraint_curves": "constraints/constraint_curves.vtp",
            "contacts": "data/contacts_and_orientations.csv",
            "fault_observations": "data/fault_observations.csv",
            "markers": "data/markers.vtp",
        },
        "qa": _qa(built, surfaces_meta, curves, vol_qa),
        "timings_seconds": timings,
    }
    timings["total"] = time.perf_counter() - t0 + built.build_seconds
    with open(case_dir / "metadata.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, default=_json_default)
    with open(case_dir / "README.md", "w", encoding="utf-8") as fh:
        fh.write(case_readme(meta))
    return meta


def _triangle_areas(mesh: pv.PolyData) -> np.ndarray:
    tris = triangles(mesh)
    p = np.asarray(mesh.points)
    return 0.5 * np.linalg.norm(
        np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]]), axis=1)


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _fault_meta(built, fs, vol_qa, patches, disp_samples) -> dict:
    mine = [p for p in patches if p.owner == fs.name]
    bbox = None
    if mine:
        allp = np.concatenate([np.asarray(p.mesh.points) for p in mine])
        bbox = [allp.min(axis=0).tolist(), allp.max(axis=0).tolist()]
    jumps = np.concatenate([np.asarray(p.mesh.point_data["slip_jump"]) for p in mine]) if mine \
        else np.zeros((0, 3))
    mag = np.linalg.norm(jumps, axis=1) if len(jumps) else np.zeros(0)
    return {
        "name": fs.name,
        "profile": fs.profile,
        "center": list(fs.center),
        "normal_into_hanging_wall": list(map(float, fs.normal)),
        "slip_direction_forward": list(map(float, fs.slip)),
        "displacement": fs.displacement,
        "axes": {"major": fs.major_axis, "intermediate": fs.intermediate_axis,
                 "minor": fs.minor_axis},
        "faulted_by": list(fs.faulted_by),
        "abuts": {"fault": fs.abuts[0], "side": fs.abuts[1]} if fs.abuts else None,
        "truncated_by": {"series": fs.truncated_by[0], "value": fs.truncated_by[1]}
        if fs.truncated_by else None,
        "surface_bbox": bbox,
        "influence": vol_qa["faults"][fs.name],
        "slip_jump_on_surface": {
            "max": float(mag.max()) if len(mag) else 0.0,
            "mean": float(mag.mean()) if len(mag) else 0.0,
            "mean_vector": jumps.mean(axis=0).tolist() if len(jumps) else None,
        },
        "displacement_samples": disp_samples.get(fs.name, []),
        "observations": int(len(built.fault_data[fs.name])),
    }


def _series_meta(built, ss, vol_qa) -> dict:
    return {
        "name": ss.name,
        "restored_field": ss.expression,
        "isovalues": list(ss.isovalues),
        "faults": list(ss.faults),
        "unconformity_value": ss.unconformity,
        "observations": int(len(built.contact_data[ss.name])),
        "interpolation_misfit": built.misfit[ss.name],
        **vol_qa["series"][ss.name],
    }


def _qa(built, surfaces, curves, vol_qa) -> dict:
    free = [c for c in curves if c["kind"] == "free"]
    nonmanifold = sum(s["quality"].get("nonmanifold_edges", 0) for s in surfaces)
    composite = max(
        (v["max_abs_diff_block_composite_vs_loopstructural_away_from_faults"]
         for v in vol_qa["series"].values()),
        default=0.0,
    )
    checks = {
        "no_untagged_open_boundaries": len(free) == 0,
        "no_nonmanifold_edges": nonmanifold == 0,
        "block_fields_match_loopstructural": composite < 1e-6,
        "series_fit_relative_rms_below_2pct": all(
            m["relative_rms"] < 0.02 for m in built.misfit.values()),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "free_boundary_length": float(sum(c["length"] for c in free)),
        "max_block_composite_difference": composite,
    }


def case_readme(meta: dict) -> str:
    lines = [f"# {meta['case']}", "", meta["description"], "",
             f"Category: **{meta['category']}**. Tags: {', '.join(meta['tags']) or '-'}.", "",
             "## Faults", "",
             "| Fault | Profile | Displacement | Faulted by | Abuts | Max slip jump on surface |",
             "| --- | --- | --- | --- | --- | --- |"]
    for f in meta["faults"]:
        ab = f"{f['abuts']['fault']} ({'+' if f['abuts']['side'] > 0 else '-'})" if f["abuts"] \
            else "-"
        lines.append(f"| {f['name']} | {f['profile']} | {f['displacement']} | "
                     f"{', '.join(f['faulted_by']) or '-'} | {ab} | "
                     f"{f['slip_jump_on_surface']['max']:.4f} |")
    lines += ["", "## Series", "", "| Series | Restored field | Isovalues | Faults | Blocks | "
              "Fit rel. RMS |", "| --- | --- | --- | --- | --- | --- |"]
    for s in meta["series"]:
        nb = sum(1 for b in s["blocks"] if b["n_nodes"] > 0)
        lines.append(f"| {s['name']} | `{s['restored_field']}` | {s['isovalues']} | "
                     f"{', '.join(s['faults']) or '-'} | {nb} | "
                     f"{s['interpolation_misfit']['relative_rms']:.2e} |")
    lines += ["", "## Reference surfaces", "",
              "| Surface | Triangles | Area | Min angle | Boundary tags |",
              "| --- | --- | --- | --- | --- |"]
    for s in meta["surfaces"]:
        q = s["quality"]
        tags = ", ".join(f"{k} ({v:.3f})" for k, v in sorted(s["boundary_length_by_tag"].items()))
        lines.append(f"| {s['id']} | {q['n_triangles']} | {q['area']:.4f} | "
                     f"{q['min_angle_deg']:.2f} | {tags} |")
    sharp = [c for c in meta["constraints"] if c["sharp"] and c["kind"] != "domain"]
    lines += ["", "## Sharp feature curves (non-domain)", "",
              "| Id | Surface | Tag | Length | Dihedral mean (deg) | Slip jump max |",
              "| --- | --- | --- | --- | --- | --- |"]
    for c in sharp:
        sj = c.get("slip_jump", {}).get("max")
        lines.append(f"| {c['id']} | {c['surface']} | {c['tag']} | {c['length']:.4f} | "
                     f"{c['dihedral_deg']['mean']:.1f} | {'-' if sj is None else f'{sj:.4f}'} |")
    qa = meta["qa"]
    lines += ["", "## QA", "", f"Passed: **{qa['passed']}**", ""]
    lines += [f"- {k}: {v}" for k, v in qa["checks"].items()]
    lines += [""]
    return "\n".join(lines)
