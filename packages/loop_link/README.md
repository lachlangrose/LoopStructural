# loop-link

A link between Python and other Loop software. A script, a notebook or a QGIS
plugin uses it to send data to a program that listens, for example the GeoViewer 3D viewer.

The package depends on numpy only. It has no QGIS, pyvista or LoopStructural
import, and it is MIT licensed, so GPL code (for example a QGIS plugin) can use it.

## Layers

| Layer | Module | What it does |
|---|---|---|
| Frame | `loop_link.frame` | One binary message: a JSON header and numpy buffers. It does not say what a message means. |
| Transport and session | `loop_link.websocket_client`, `loop_link.Link` | A WebSocket on the local machine with a bearer token. A short session: connect, send, receive, close. |
| GeoViewer | `loop_link.geoviewer` | The scene messages of GeoViewer (surfaces, groups) and `GeoViewerLink.push`. |

A program that wants to be a target of the link defines its own messages on top of the
first two layers.

## Send a surface to GeoViewer

Start GeoViewer, and copy the port and the token from its link popup.

```python
import numpy as np
from loop_link.geoviewer import GeoViewerLink, protocol

vertices = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 5]], dtype=float)
triangles = np.array([[0, 1, 2]])


def build(origin):
    yield 'demo/surface', protocol.surface_message(
        'demo/surface', 'Demo surface', vertices, triangles, origin=origin
    )


link = GeoViewerLink(port=47615, token='token from the viewer')
result = link.push('EPSG:28350', vertices.mean(axis=0), build, replace_prefix='demo/')
print(result.summary())
```

`push` makes the connection, says `hello`, sends the objects, and closes the
connection. The viewer keeps the scene. The GeoViewer message format is in
`docs/protocol.md` of the GeoViewer repository.

## Use the base layer

```python
from loop_link import Link

link = Link(port=12345, token='...', peer='My program')
with link.session() as session:
    session.send({'type': 'hello', 'crs': 'EPSG:28350', 'origin': [0, 0, 0]})
    answer = session.read_until(('hello',), timeout=5.0)
```
