"""A client connection to a program that listens for Loop link messages.

``Link`` knows the transport (a WebSocket with a bearer token) and the frame,
but not what the messages mean. A subclass or a caller adds that, for example
``loop_link.geoviewer.GeoViewerLink``.

A session is short: connect, send and receive, close. Nothing keeps the
connection open, so the client has no state to repair when the other program stops.
"""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import frame
from .websocket_client import WebSocketClient, WebSocketClosed, WebSocketError

HOST = '127.0.0.1'
APPLICATION_NAME = 'loop_link'


class LinkError(Exception):
    """The link failed. The text tells the user why."""


class Session:
    """An open connection. Get one from ``Link.session``."""

    def __init__(self, client: WebSocketClient, link: 'Link'):
        self._client = client
        self.link = link

    def send_frame(self, data: bytes):
        """Send a frame that is ready."""
        try:
            self._client.send_binary(data)
        except WebSocketError as error:
            raise LinkError(str(error)) from error

    def send(self, header: Dict[str, Any], buffers: Sequence[Tuple[str, np.ndarray]] = ()):
        """Make a frame from a header and buffers, and send it."""
        self.send_frame(frame.encode_frame(header, buffers, version=self.link.version))

    def receive(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Return the next frame, or None if none comes within ``timeout`` seconds."""
        try:
            return self._client.receive(timeout)
        except WebSocketClosed:
            return None
        except WebSocketError as error:
            raise LinkError(str(error)) from error

    def read_until(self, types: Sequence[str], timeout: float) -> Dict[str, Dict[str, Any]]:
        """Read messages until one of each type in ``types`` has come.

        Returns a map from type to header. Raises ``LinkError`` if the other
        program sends an ``error`` message, or if nothing comes in time.
        """
        wanted = set(types)
        found: Dict[str, Dict[str, Any]] = {}
        while wanted - set(found):
            data = self.receive(timeout)
            if data is None:
                raise LinkError(f"{self.link.peer} did not answer ({', '.join(sorted(wanted))}).")
            header = frame.decode_header(data)
            kind = header.get('type')
            if kind == 'error':
                raise LinkError(f"{self.link.peer} refused the link: {header.get('message', '')}")
            if kind in wanted:
                found[kind] = header
        return found

    def drain_errors(self, wait: float = 0.0) -> List[Dict[str, Any]]:
        """Read the messages that wait in the socket. Return the headers of the errors."""
        errors = []
        while True:
            data = self.receive(wait if wait > 0 else 0.001)
            if data is None:
                return errors
            header = frame.decode_header(data)
            if header.get('type') == 'error':
                errors.append(header)


class Link:
    """The address of a program that listens for link messages.

    Parameters
    ----------
    port, token : the port and the token that the other program shows.
    host : the host of the other program, by default the local machine.
    application : the name that the client gives in its hello message.
    peer : the name of the other program, for the error messages.
    version : the version dictionary that goes in every header, or None.
    """

    def __init__(
        self,
        port: int,
        token: str = '',
        host: str = HOST,
        application: str = APPLICATION_NAME,
        peer: str = 'The server',
        version: Optional[Dict[str, int]] = None,
    ):
        self.port = int(port)
        self.token = token or ''
        self.host = host
        self.application = application
        self.peer = peer
        self.version = version

    @contextmanager
    def session(self, hint: str = ''):
        """Open a connection, and close it at the end of the ``with`` block."""
        try:
            client = WebSocketClient.connect(self.host, self.port, token=self.token)
        except WebSocketError as error:
            raise LinkError(f"{error} {hint}".strip()) from error
        try:
            yield Session(client, self)
        except WebSocketError as error:
            raise LinkError(str(error)) from error
        finally:
            client.close()
