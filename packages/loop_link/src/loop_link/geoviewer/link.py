"""The connection of a Python client (a script or a plugin) to a running GeoViewer.

``GeoViewerLink.push`` makes the connection, says ``hello``, sends the objects
of the model and closes the connection. Nothing keeps the link open, so the
client has no state to repair when the viewer stops. The viewer keeps the scene.
"""

from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from ..link import HOST, Link, LinkError
from . import protocol

DEFAULT_PORT = 47615

# Time to wait for the answer to the hello message
_HELLO_TIMEOUT = 5.0
# Time to wait for the errors of the viewer after the last message
_SETTLE_TIMEOUT = 0.5

__all__ = ['DEFAULT_PORT', 'GeoViewerLink', 'LinkError', 'PushResult']


class PushResult:
    """What happened in one push."""

    def __init__(self):
        self.sent = 0
        self.removed = 0
        # (object id, text) of each error that the viewer sent about an object
        self.refused: List[Tuple[str, str]] = []
        self.other_errors: List[str] = []

    def summary(self) -> str:
        text = f"{self.sent} objects sent to GeoViewer"
        if self.removed:
            text += f", {self.removed} old objects removed"
        if self.refused or self.other_errors:
            text += f". The viewer refused {len(self.refused) + len(self.other_errors)} messages"
        return text + "."

    def _keep(self, errors) -> None:
        """Keep the error messages of the viewer."""
        for header in errors:
            text = header.get('message', header.get('code', 'error'))
            if header.get('object'):
                self.refused.append((header['object'], text))
            else:
                self.other_errors.append(text)


class GeoViewerLink(Link):
    """A short session with the viewer.

    Parameters
    ----------
    port, token : the port and the token of the link of the viewer. The viewer
        shows both in its link popup.
    application : the name that the client gives to the viewer in its hello message.
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        token: str = '',
        host: str = HOST,
        application: str = protocol.APPLICATION_NAME,
    ):
        super().__init__(
            port,
            token,
            host,
            application,
            peer='GeoViewer',
            version=protocol.PROTOCOL_VERSION,
        )

    def push(
        self,
        crs: str,
        origin: Sequence[float],
        build_messages: Callable[[Sequence[float]], Iterable[Tuple[str, bytes]]],
        *,
        replace_prefix: Optional[str] = None,
        progress: Optional[Callable[[str], None]] = None,
    ) -> PushResult:
        """Send objects to the viewer.

        Parameters
        ----------
        crs, origin : the CRS and the origin that the client proposes for the
            scene. If the scene of the viewer has an origin already, the viewer
            keeps it and says so in its ``hello`` answer.
        build_messages : called with the origin that the viewer uses. It yields
            ``(object id, frame)`` pairs. The coordinates must be relative to
            this origin.
        replace_prefix : after the push, remove the objects of the viewer whose
            id starts with this text and that were not sent again.
        progress : called with a text before each step.
        """
        say = progress or (lambda _text: None)
        say(f"Connecting to GeoViewer on port {self.port}...")
        hint = "Start GeoViewer, and check the port and the token in its link popup."
        with self.session(hint) as session:
            result = PushResult()
            session.send_frame(
                protocol.hello_message(crs, origin, application=self.application)
            )
            answer = session.read_until(('hello', 'scene.inventory'), _HELLO_TIMEOUT)
            scene_origin = [float(v) for v in answer['hello'].get('origin', origin)]
            existing = protocol.inventory_ids(answer['scene.inventory'])
            sent_ids = set()
            for object_id, frame in build_messages(scene_origin):
                say(f"Sending {object_id}...")
                session.send_frame(frame)
                sent_ids.add(object_id)
                result.sent += 1
                result._keep(session.drain_errors())
            if replace_prefix:
                for object_id in existing:
                    if object_id.startswith(replace_prefix) and object_id not in sent_ids:
                        session.send_frame(protocol.remove_message(object_id))
                        result.removed += 1
            result._keep(session.drain_errors(_SETTLE_TIMEOUT))
            return result
