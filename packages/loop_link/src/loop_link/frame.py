"""The binary frame that the Loop link uses for every message.

A message is one frame:

    [u32 header_len][JSON header, UTF-8][buffer 0][buffer 1]...

All numbers are little-endian. The header is a JSON object. It lists the
buffers in order, each with a name, a dtype and a shape. The frame does not
say what a message means. The software on each end of a link defines that, for
example the GeoViewer scene messages in ``loop_link.geoviewer``.

The module uses the standard library and numpy only.
"""

import json
import struct
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

# The default limit for one frame
MAX_FRAME_BYTES = 256 * 1024 * 1024

_DTYPE_NAMES = {
    np.dtype('<f4').str: 'f32',
    np.dtype('<f8').str: 'f64',
    np.dtype('<u4').str: 'u32',
    np.dtype('<i4').str: 'i32',
    np.dtype('u1').str: 'u8',
}


class ProtocolError(Exception):
    """A frame cannot be written or read."""


def encode_frame(
    header: Dict[str, Any],
    buffers: Sequence[Tuple[str, np.ndarray]] = (),
    *,
    version: Optional[Dict[str, int]] = None,
    max_bytes: int = MAX_FRAME_BYTES,
) -> bytes:
    """Return the frame for a header and its named buffers.

    The function adds ``buffers`` to the header, and ``version`` if one is given.
    A buffer is a ``(name, array)`` pair. The array must be f32, f64, u32, i32 or u8.
    """
    descriptions = []
    payload = []
    for name, array in buffers:
        array = np.ascontiguousarray(array)
        dtype = _DTYPE_NAMES.get(array.dtype.newbyteorder('<').str)
        if dtype is None:
            raise ProtocolError(f"Buffer {name!r} has the unsupported type {array.dtype}.")
        descriptions.append({'name': name, 'dtype': dtype, 'shape': list(array.shape)})
        payload.append(array.astype(array.dtype.newbyteorder('<'), copy=False).tobytes())
    full = dict(header)
    if version is not None:
        full['version'] = version
    full['buffers'] = descriptions
    header_bytes = json.dumps(full, separators=(',', ':'), allow_nan=False).encode('utf-8')
    frame = b''.join([struct.pack('<I', len(header_bytes)), header_bytes, *payload])
    if len(frame) > max_bytes:
        raise ProtocolError(
            f"The message is {len(frame)} bytes. The receiver accepts {max_bytes} bytes at most."
        )
    return frame


def decode_header(frame: bytes) -> Dict[str, Any]:
    """Return the JSON header of a frame. The buffers are ignored."""
    if len(frame) < 4:
        raise ProtocolError("The frame is shorter than 4 bytes.")
    (length,) = struct.unpack_from('<I', frame, 0)
    if 4 + length > len(frame):
        raise ProtocolError("The frame stops inside the header.")
    try:
        return json.loads(frame[4 : 4 + length].decode('utf-8'))
    except ValueError as error:
        raise ProtocolError(f"The header is not valid JSON: {error}") from error
