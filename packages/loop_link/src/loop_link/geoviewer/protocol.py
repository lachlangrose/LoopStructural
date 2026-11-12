"""The scene messages of GeoViewer (protocol 1.x).

No QGIS and no pyvista code, only the standard library and numpy. A message is
one binary frame (see ``loop_link.frame``). This module defines what the
messages mean. See
``docs/protocol.md`` in the GeoViewer repository for the full description.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .. import frame
from ..frame import ProtocolError, decode_header

PROTOCOL_VERSION = {'major': 1, 'minor': 8}

# The largest frame that the viewer accepts
MAX_FRAME_BYTES = 256 * 1024 * 1024
# Beyond this distance from the origin an f32 coordinate is not exact to 1 mm
F32_LIMIT = 4000.0

# The name that a client gives in its hello message, unless it sets its own
APPLICATION_NAME = 'loop_link'


def encode_frame(header: Dict[str, Any], buffers: Sequence[Tuple[str, np.ndarray]] = ()) -> bytes:
    """Return the frame for a header and its named buffers, with the protocol version.

    The function adds ``version`` and ``buffers`` to the header. A buffer is a
    ``(name, array)`` pair. The array must be f32, f64, u32, i32 or u8.
    """
    return frame.encode_frame(
        header, buffers, version=PROTOCOL_VERSION, max_bytes=MAX_FRAME_BYTES
    )


def hello_message(
    crs: str,
    origin: Sequence[float],
    version: str = '0',
    application: str = APPLICATION_NAME,
) -> bytes:
    """Return the ``hello`` frame. ``origin`` is the origin of the scene in ``crs``."""
    return encode_frame(
        {
            'type': 'hello',
            'application': {'name': application, 'version': version},
            'crs': crs,
            'origin': [float(v) for v in origin],
        }
    )


def clear_message() -> bytes:
    """Return the ``scene.clear`` frame."""
    return encode_frame({'type': 'scene.clear'})


def remove_message(object_id: str) -> bytes:
    """Return the ``scene.remove`` frame for an object or a group (with its children)."""
    return encode_frame({'type': 'scene.remove', 'id': object_id})


def _upsert_header(
    object_id: str,
    object_type: str,
    name: str,
    parent: Optional[str],
    revision: int,
    style: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        'type': 'scene.upsert',
        'id': object_id,
        'object_type': object_type,
        'name': name,
        'parent': parent,
        'revision': int(revision),
        'edit': [],
        'replaces': None,
        'geometry': {},
        'params': {},
        'data': [],
        'property_groups': [],
        'drape': None,
        'style': dict(style or {}),
    }


def group_message(
    object_id: str, name: str, parent: Optional[str] = None, revision: int = 1
) -> bytes:
    """Return the ``scene.upsert`` frame of a Group."""
    return encode_frame(_upsert_header(object_id, 'Group', name, parent, revision, None))


def surface_message(
    object_id: str,
    name: str,
    vertices,
    triangles,
    *,
    origin: Sequence[float] = (0.0, 0.0, 0.0),
    parent: Optional[str] = None,
    revision: int = 1,
    style: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Return the ``scene.upsert`` frame of a Surface.

    Parameters
    ----------
    vertices : array-like, shape (n, 3)
        The vertices in the coordinates of the CRS. The function subtracts
        ``origin`` in f64 and then writes f32, or f64 for a model that is more
        than 4 km from the origin.
    triangles : array-like, shape (m, 3)
        Vertex indices.
    """
    vertices = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if len(vertices) == 0 or len(triangles) == 0:
        raise ProtocolError(f"The surface {name!r} has no triangles.")
    if not np.isfinite(vertices).all():
        raise ProtocolError(f"The surface {name!r} has a vertex that is NaN or infinite.")
    if triangles.min() < 0 or triangles.max() >= len(vertices):
        raise ProtocolError(f"The surface {name!r} has a triangle index outside the vertices.")
    relative = vertices - np.asarray(origin, dtype=np.float64)
    if np.abs(relative).max() <= F32_LIMIT:
        relative = relative.astype(np.float32)
    header = _upsert_header(object_id, 'Surface', name, parent, revision, style)
    header['geometry'] = {'vertices': 'vertices', 'triangles': 'triangles'}
    return encode_frame(
        header,
        [('vertices', relative), ('triangles', triangles.astype(np.uint32))],
    )


def inventory_ids(header: Dict[str, Any]) -> List[str]:
    """Return the ids of a ``scene.inventory`` header."""
    return [entry['id'] for entry in header.get('entries', [])]
