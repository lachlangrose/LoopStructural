"""Structured starting mesh and explicit, lossless ASCII Medit IO."""

from dataclasses import dataclass, field
from itertools import permutations
from pathlib import Path

import numpy as np


@dataclass
class Mesh:
    points: np.ndarray
    tets: np.ndarray
    refs: np.ndarray
    triangles: np.ndarray = field(default_factory=lambda: np.empty((0, 3), dtype=int))
    tri_refs: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))
    required_triangles: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))
    orientation_corrections: int = 0
    required_tets: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))
    required_vertices: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))

    @property
    def centers(self):
        return self.points[self.tets].mean(axis=1)

    def volumes(self):
        p = self.points[self.tets]
        return (
            np.einsum("ij,ij->i", np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), p[:, 3] - p[:, 0])
            / 6
        )

    def orient(self):
        """Convert negative ordering; never remove or repair degenerate elements."""
        negative = self.volumes() < 0
        self.tets[negative, :2] = self.tets[negative, 1::-1]
        self.orientation_corrections += int(negative.sum())
        return self


def cube(cells=11):
    if cells < 2:
        raise ValueError("At least two cells per axis are needed")
    # Odd number of x cells avoids initially fitting the fault; for even inputs,
    # move just the central x plane, retaining the exact cube boundary.
    axes = [np.linspace(-1, 1, cells + 1) for _ in range(3)]
    if cells % 2 == 0:
        axes[0][cells // 2] += 0.31 * 2 / cells
    points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)

    def index(q):
        return np.ravel_multi_index(tuple(q), (cells + 1,) * 3)

    tets = []
    for base in np.ndindex((cells,) * 3):
        for order in permutations(range(3)):
            q = np.array(base)
            chain = [index(q)]
            for axis in order:
                q = q.copy()
                q[axis] += 1
                chain.append(index(q))
            tets.append(chain)
    mesh = Mesh(points, np.array(tets), np.ones(len(tets), dtype=int)).orient()
    from .interfaces import exterior_references, face_table

    faces, counts, _, _ = face_table(mesh)
    mesh.triangles = faces[counts == 1]
    mesh.tri_refs = exterior_references(mesh.points[mesh.triangles])
    return mesh


def write_mesh(path, mesh):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="\n") as f:
        f.write("MeshVersionFormatted 2\nDimension 3\nVertices\n" + str(len(mesh.points)) + "\n")
        np.savetxt(
            f, np.c_[mesh.points, np.zeros(len(mesh.points), dtype=int)], fmt=["%.17g"] * 3 + ["%d"]
        )
        f.write("Tetrahedra\n" + str(len(mesh.tets)) + "\n")
        np.savetxt(f, np.c_[mesh.tets + 1, mesh.refs], fmt="%d")
        if len(mesh.triangles):
            f.write("Triangles\n" + str(len(mesh.triangles)) + "\n")
            np.savetxt(f, np.c_[mesh.triangles + 1, mesh.tri_refs], fmt="%d")
        if len(mesh.required_triangles):
            f.write("RequiredTriangles\n" + str(len(mesh.required_triangles)) + "\n")
            np.savetxt(f, mesh.required_triangles + 1, fmt="%d")
        if len(mesh.required_tets):
            f.write("RequiredTetrahedra\n" + str(len(mesh.required_tets)) + "\n")
            np.savetxt(f, mesh.required_tets + 1, fmt="%d")
        if len(mesh.required_vertices):
            f.write("RequiredVertices\n" + str(len(mesh.required_vertices)) + "\n")
            np.savetxt(f, mesh.required_vertices + 1, fmt="%d")
        f.write("End\n")


def read_mesh(path):
    # Fail on unknown sections instead of silently losing volume cells.
    widths = {
        "Vertices": 4,
        "Tetrahedra": 5,
        "Triangles": 4,
        "Edges": 3,
        "Corners": 1,
        "RequiredVertices": 1,
        "RequiredTriangles": 1,
        "RequiredTetrahedra": 1,
        "RequiredEdges": 1,
        "Ridges": 1,
        "Normals": 3,
        "NormalAtVertices": 2,
        "Tangents": 3,
        "TangentAtVertices": 2,
    }
    words = " ".join(line.split("#")[0] for line in Path(path).read_text().splitlines()).split()
    data = {}
    i = 0
    while i < len(words):
        key = words[i]
        i += 1
        if key == "End":
            break
        if key in ("MeshVersionFormatted", "Dimension"):
            if key == "Dimension" and words[i] != "3":
                raise ValueError("Only 3D Medit files are supported")
            i += 1
            continue
        if key not in widths:
            raise ValueError(f"Unsupported Medit section {key}")
        n = int(words[i])
        i += 1
        width = widths[key]
        dtype = float if key in ("Vertices", "Normals", "Tangents") else int
        data[key] = np.array(words[i : i + n * width], dtype=dtype).reshape(n, width)
        i += n * width
    vertices, tets = data["Vertices"], data["Tetrahedra"]
    tri = data.get("Triangles", np.empty((0, 4), dtype=int))
    return Mesh(
        vertices[:, :3],
        tets[:, :4] - 1,
        tets[:, 4],
        tri[:, :3] - 1,
        tri[:, 3],
        data.get("RequiredTriangles", np.empty((0, 1), dtype=int)).ravel() - 1,
        required_tets=data.get("RequiredTetrahedra", np.empty((0, 1), dtype=int)).ravel() - 1,
        required_vertices=data.get("RequiredVertices", np.empty((0, 1), dtype=int)).ravel() - 1,
    ).orient()


def extract_block(mesh, block):
    selected = (mesh.centers[:, 0] < 0) if block == 1 else (mesh.centers[:, 0] > 0)
    ids, inverse = np.unique(mesh.tets[selected], return_inverse=True)
    result = Mesh(mesh.points[ids].copy(), inverse.reshape(-1, 4), mesh.refs[selected].copy())
    from .interfaces import exterior_references, face_table

    faces, counts, _, _ = face_table(result)
    result.triangles = faces[counts == 1]
    result.tri_refs = exterior_references(result.points[result.triangles])
    on_fault = np.max(abs(result.points[result.triangles, 0]), axis=1) < 1e-9
    result.tri_refs[on_fault] = 100
    return result
