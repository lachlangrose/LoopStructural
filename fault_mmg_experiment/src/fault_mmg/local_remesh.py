"""Select a physical interface band and verify that the outside remains fixed."""

import copy

import numpy as np
from scipy.spatial import cKDTree

from .interfaces import face_table
from .quality import cell_quality
from .two_faults import SECONDARY_NORMAL, STRAT_NORMAL


def interface_band(
    mesh,
    model,
    width=0.03,
    halo=1,
    quality_cutoff=0.1,
    horizon_pairs=None,
    include_faults=True,
    halo_kind="face",
    fault_ids=(1, 2),
):
    """Select intersected slabs using vertex intervals, with a face-neighbor halo.

    Division by gradient norm converts an affine implicit scalar into distance.
    This is essential when the function is not a signed distance field. The
    secondary fault's extension in the inactive block is deliberately excluded.
    """
    if width < 0 or halo < 0 or int(halo) != halo:
        raise ValueError("Width and integer halo must be nonnegative")
    if halo_kind not in ("face", "vertex"):
        raise ValueError("Halo kind must be face or vertex")
    points = mesh.points[mesh.tets]
    block = model.block_labels(mesh.centers)

    def intersects(values, threshold):
        return (values.min(axis=1) <= threshold) & (values.max(axis=1) >= -threshold)

    active = (
        intersects(points[:, :, 0], width)
        if include_faults and 1 in fault_ids
        else np.zeros(len(mesh.tets), dtype=bool)
    )
    secondary = points @ SECONDARY_NORMAL - 0.1
    secondary_band = intersects(secondary, width * np.linalg.norm(SECONDARY_NORMAL))
    if include_faults and 2 in fault_ids:
        active |= secondary_band & ((block != 1) if model.case == "terminating" else True)
    horizon_pairs = (
        [(b, h) for b in model.blocks for h in (-0.5, 0.0, 0.5)]
        if horizon_pairs is None
        else horizon_pairs
    )
    coordinate = points @ STRAT_NORMAL
    for b, horizon in horizon_pairs:
        active |= (block == b) & intersects(
            coordinate - model.offsets[b] - horizon, width * np.linalg.norm(STRAT_NORMAL)
        )
    slab_count = int(active.sum())
    bad = (
        cell_quality(mesh)["mmg_quality"] < quality_cutoff
        if quality_cutoff > 0
        else np.zeros(len(mesh.tets), dtype=bool)
    )
    active |= bad
    seed_count = int(active.sum())
    _, counts, left, right = face_table(mesh)
    interior = counts == 2
    left, right = left[interior], right[interior]
    for _ in range(halo):
        previous = active.copy()
        if halo_kind == "face":
            active[right[previous[left]]] = True
            active[left[previous[right]]] = True
        else:
            selected_vertices = np.zeros(len(mesh.points), dtype=bool)
            selected_vertices[np.unique(mesh.tets[previous])] = True
            active |= np.any(selected_vertices[mesh.tets], axis=1)
    return active, {
        "half_width": width,
        "halo_layers": halo,
        "halo_kind": halo_kind,
        "quality_cutoff": quality_cutoff,
        "slab_tets": slab_count,
        "poor_tets_included": int(bad.sum()),
        "seed_tets": seed_count,
        "active_tets": int(active.sum()),
        "frozen_tets": int((~active).sum()),
        "active_fraction": float(active.mean()),
        "mobile_vertices": int(len(mesh.points) - len(np.unique(mesh.tets[~active]))),
    }


def freeze_outside(mesh, active):
    frozen = copy.deepcopy(mesh)
    frozen.required_tets = np.flatnonzero(~active)
    frozen.required_vertices = np.unique(mesh.tets[~active])
    return frozen


def verify_frozen_region(original, output, frozen_tets, tolerance=1e-12):
    """Track full tetrahedron geometry and material refs despite MMG renumbering."""
    frozen_tets = np.asarray(frozen_tets)
    if frozen_tets.dtype == bool:
        frozen_tets = np.flatnonzero(frozen_tets)
    vertices = np.unique(original.tets[frozen_tets])
    if not len(vertices):
        return {
            "passed": True,
            "frozen_tets": 0,
            "matched_tets": 0,
            "maximum_vertex_displacement": 0.0,
        }, np.empty(0, dtype=int)
    distances, mapped = cKDTree(output.points).query(original.points[vertices])
    index = np.full(len(original.points), -1, dtype=int)
    index[vertices] = mapped
    lookup = {
        tuple(sorted(t)) + (int(ref),): i
        for i, (t, ref) in enumerate(zip(output.tets, output.refs))
    }
    matched = [
        lookup.get(tuple(sorted(index[t])) + (int(ref),), -1)
        for t, ref in zip(original.tets[frozen_tets], original.refs[frozen_tets])
    ]
    matches = np.array(matched, dtype=int)
    valid_vertices = np.all(distances <= tolerance) and len(np.unique(mapped)) == len(mapped)
    return {
        "passed": bool(valid_vertices and np.all(matches >= 0)),
        "frozen_tets": len(frozen_tets),
        "matched_tets": int((matches >= 0).sum()),
        "frozen_vertices": len(vertices),
        "maximum_vertex_displacement": float(distances.max()),
        "tolerance": tolerance,
    }, matches
