"""Cell-wise tetrahedron quality measurements, independent of MMG's log."""

from itertools import combinations

import numpy as np

from .interfaces import LOCAL_FACES
from .two_faults import mmg_isotropic_quality


def cell_quality(mesh):
    xyz = mesh.points[mesh.tets[:, LOCAL_FACES]]
    normals = np.cross(xyz[:, :, 1] - xyz[:, :, 0], xyz[:, :, 2] - xyz[:, :, 0])
    normals /= np.linalg.norm(normals, axis=2)[..., None]
    pairs = np.array(list(combinations(range(4), 2)))
    cosine = -np.einsum("ijk,ijk->ij", normals[:, pairs[:, 0]], normals[:, pairs[:, 1]])
    angles = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
    return {
        "mmg_quality": mmg_isotropic_quality(mesh) * 12 * np.sqrt(3),
        "minimum_dihedral_degrees": angles.min(axis=1),
        "maximum_dihedral_degrees": angles.max(axis=1),
        "tetra_volume": mesh.volumes(),
    }


def quality_report(mesh):
    arrays = cell_quality(mesh)
    quality, angles = arrays["mmg_quality"], arrays["minimum_dihedral_degrees"]
    return {
        "vertices": len(mesh.points),
        "tetrahedra": len(mesh.tets),
        "mmg_quality": {
            "minimum": float(quality.min()),
            "percentile_1": float(np.percentile(quality, 1)),
            "percentile_5": float(np.percentile(quality, 5)),
            "median": float(np.median(quality)),
            "below_0_01": int((quality < 0.01).sum()),
            "below_0_1": int((quality < 0.1).sum()),
        },
        "minimum_dihedral_degrees": {
            "minimum": float(angles.min()),
            "percentile_1": float(np.percentile(angles, 1)),
            "median": float(np.median(angles)),
            "below_5_degrees": int((angles < 5).sum()),
        },
    }
