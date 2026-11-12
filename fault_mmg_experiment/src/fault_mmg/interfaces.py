"""All interfaces are derived from actual tetrahedron faces and adjacency."""

import numpy as np

from .geometry import labels

LOCAL_FACES = np.array([[1, 2, 3], [0, 3, 2], [0, 1, 3], [0, 2, 1]])


def face_table(mesh):
    all_faces = np.sort(mesh.tets[:, LOCAL_FACES].reshape(-1, 3), axis=1)
    faces, first, inverse, counts = np.unique(
        all_faces, axis=0, return_index=True, return_inverse=True, return_counts=True
    )
    # first and last incident tetrahedron, valid for counts <= 2.
    last = np.zeros(len(faces), dtype=int)
    np.maximum.at(last, inverse, np.arange(len(all_faces)))
    return faces, counts, first // 4, last // 4


def exterior_references(face_points, tol=1e-9):
    refs = np.full(len(face_points), 99, dtype=int)
    for axis in range(3):
        for side, value in enumerate((-1, 1)):
            refs[np.max(abs(face_points[:, :, axis] - value), axis=1) < tol] = 1 + 2 * axis + side
    return refs


def geological_interfaces(mesh):
    faces, counts, left, right = face_table(mesh)
    blocks, units = labels(mesh.centers)
    internal = counts == 2
    fault = internal & (blocks[left] != blocks[right])
    horizons = internal & (blocks[left] == blocks[right]) & (units[left] != units[right])
    return {
        "faces": faces,
        "counts": counts,
        "left": left,
        "right": right,
        "fault": fault,
        "horizons": horizons,
        "blocks": blocks,
        "units": units,
    }


def edges(triangles):
    if not len(triangles):
        return np.empty((0, 2), dtype=int)
    return np.unique(np.sort(triangles[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1), axis=0)


def triangle_area(points):
    return (
        np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)
        / 2
    )


def interface_signature(mesh, tol=1e-9):
    """Compare full triangle geometry, not just coincident vertex sets."""
    faces, counts, _, _ = face_table(mesh)
    fault_faces = faces[(counts == 1) & (np.max(abs(mesh.points[faces, 0]), axis=1) < tol)]
    triangles = []
    for face in fault_faces:
        triangles.append(
            tuple(sorted(map(tuple, np.rint(mesh.points[face] / tol).astype(np.int64))))
        )
    return set(triangles)
