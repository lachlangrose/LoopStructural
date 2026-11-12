"""A link between Python and other Loop software.

The package has two layers. The base layer is generic: the binary frame
(``frame``), the WebSocket transport with a token (``websocket_client``) and a
short client session (``Link``). The layers above it define what the messages
mean for one program. ``loop_link.geoviewer`` is the client for the GeoViewer
3D viewer.

The package needs numpy only, and it has no QGIS, pyvista or LoopStructural
import. It is MIT licensed, so GPL code (for example a QGIS plugin) can use it.
"""

from . import frame
from .frame import ProtocolError, decode_header, encode_frame
from .link import Link, LinkError, Session

__all__ = [
    'Link',
    'LinkError',
    'ProtocolError',
    'Session',
    'decode_header',
    'encode_frame',
    'frame',
]
