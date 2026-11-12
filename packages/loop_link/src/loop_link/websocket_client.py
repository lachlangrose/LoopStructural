"""A small WebSocket client for the link to GeoViewer.

It uses the standard library only, because QGIS does not ship a WebSocket
package for every platform. It does what the link needs: one connection to
``127.0.0.1`` with an ``Authorization`` header, binary messages in both
directions, and the control frames (ping, pong, close). It does not do TLS.
"""

import base64
import hashlib
import os
import socket
import struct
from typing import Optional, Tuple

_GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

# The viewer refuses a message of more than 256 MiB; refuse a reply of more than 16 MiB
MAX_INCOMING_BYTES = 16 * 1024 * 1024
_HANDSHAKE_MAX_BYTES = 16 * 1024
# Time for the rest of a frame after its first bytes arrived
_FRAME_TIMEOUT = 10.0


class WebSocketError(Exception):
    """The connection failed, or the server broke the protocol."""


class WebSocketClosed(WebSocketError):
    """The server closed the connection."""


def _mask(data: bytes, key: bytes) -> bytes:
    if not data:
        return data
    repeated = (key * (len(data) // 4 + 1))[: len(data)]
    value = int.from_bytes(data, 'little') ^ int.from_bytes(repeated, 'little')
    return value.to_bytes(len(data), 'little')


class WebSocketClient:
    """One client connection. Not thread safe: use it from one thread."""

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._buffer = b''
        self.closed = False

    @classmethod
    def connect(
        cls, host: str, port: int, *, token: str = '', timeout: float = 5.0, path: str = '/'
    ) -> 'WebSocketClient':
        """Open the connection and do the handshake.

        Raises ``WebSocketError`` if the server is not there, or refuses the token.
        """
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as error:
            raise WebSocketError(f"Cannot connect to {host}:{port}: {error}") from error
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client = cls(sock)
        try:
            client._handshake(host, port, token, path)
        except Exception:
            sock.close()
            raise
        return client

    def _handshake(self, host: str, port: int, token: str, path: str):
        key = base64.b64encode(os.urandom(16))
        lines = [
            f'GET {path} HTTP/1.1',
            f'Host: {host}:{port}',
            'Upgrade: websocket',
            'Connection: Upgrade',
            f'Sec-WebSocket-Key: {key.decode()}',
            'Sec-WebSocket-Version: 13',
        ]
        if token:
            lines.append(f'Authorization: Bearer {token}')
        try:
            self._sock.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode('ascii'))
            data = b''
            while b'\r\n\r\n' not in data:
                chunk = self._sock.recv(4096)
                if not chunk:
                    raise WebSocketError("The viewer closed the connection during the handshake.")
                data += chunk
                if len(data) > _HANDSHAKE_MAX_BYTES:
                    raise WebSocketError("The handshake answer is too long.")
        except OSError as error:
            raise WebSocketError(f"The handshake failed: {error}") from error
        head, _, rest = data.partition(b'\r\n\r\n')
        self._buffer = rest
        status_line, *header_lines = head.decode('latin-1').split('\r\n')
        parts = status_line.split(' ', 2)
        status = parts[1] if len(parts) > 1 else ''
        if status == '401':
            raise WebSocketError("The viewer refused the token. Check the token of the link.")
        if status != '101':
            raise WebSocketError(f"The viewer refused the connection: {status_line}")
        headers = {}
        for line in header_lines:
            name, _, value = line.partition(':')
            headers[name.strip().lower()] = value.strip()
        expected = base64.b64encode(hashlib.sha1(key + _GUID).digest()).decode()
        if headers.get('sec-websocket-accept') != expected:
            raise WebSocketError("The server did not answer as a WebSocket server.")

    # -- sending ------------------------------------------------------------

    def _send_frame(self, opcode: int, payload: bytes):
        length = len(payload)
        head = bytearray([0x80 | opcode])
        if length < 126:
            head.append(0x80 | length)
        elif length < 1 << 16:
            head.append(0x80 | 126)
            head += struct.pack('>H', length)
        else:
            head.append(0x80 | 127)
            head += struct.pack('>Q', length)
        key = os.urandom(4)
        try:
            self._sock.sendall(bytes(head) + key + _mask(payload, key))
        except OSError as error:
            self.closed = True
            raise WebSocketError(f"Cannot send to the viewer: {error}") from error

    def send_binary(self, payload: bytes):
        """Send one binary message."""
        self._send_frame(OP_BINARY, payload)

    # -- receiving ----------------------------------------------------------

    def _read_exactly(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self._sock.recv(65536)
            if not chunk:
                self.closed = True
                raise WebSocketClosed("The viewer closed the connection.")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def _read_frame(self, wait: Optional[float]) -> Tuple[bool, int, bytes]:
        # The wait applies to the start of a frame only. A frame that started
        # is read to the end, so a timeout cannot leave half a frame behind.
        self._sock.settimeout(wait)
        first, second = self._read_exactly(2)
        self._sock.settimeout(_FRAME_TIMEOUT)
        fin, opcode = bool(first & 0x80), first & 0x0F
        length = second & 0x7F
        if length == 126:
            (length,) = struct.unpack('>H', self._read_exactly(2))
        elif length == 127:
            (length,) = struct.unpack('>Q', self._read_exactly(8))
        if length > MAX_INCOMING_BYTES:
            raise WebSocketError("The viewer sent a message that is too large.")
        key = self._read_exactly(4) if second & 0x80 else None
        payload = self._read_exactly(length)
        return fin, opcode, _mask(payload, key) if key else payload

    def receive(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Return the next binary message, or None if nothing arrives in ``timeout`` seconds.

        Ping frames get a pong. A text message is skipped. If the server closes
        the connection, ``WebSocketClosed`` is raised.
        """
        message = bytearray()
        message_opcode = None
        try:
            while True:
                fin, opcode, payload = self._read_frame(timeout if not message else _FRAME_TIMEOUT)
                if opcode == OP_PING:
                    self._send_frame(OP_PONG, payload)
                elif opcode == OP_PONG:
                    continue
                elif opcode == OP_CLOSE:
                    self.closed = True
                    try:
                        self._send_frame(OP_CLOSE, payload[:2])
                    except WebSocketError:
                        pass
                    raise WebSocketClosed("The viewer closed the connection.")
                else:
                    if opcode != OP_CONTINUATION:
                        message_opcode = opcode
                        message = bytearray()
                    message += payload
                    if len(message) > MAX_INCOMING_BYTES:
                        raise WebSocketError("The viewer sent a message that is too large.")
                    if fin and message_opcode == OP_BINARY:
                        return bytes(message)
                    if fin:
                        message = bytearray()
        except (socket.timeout, TimeoutError):
            return None
        except OSError as error:
            self.closed = True
            raise WebSocketError(f"Cannot read from the viewer: {error}") from error

    def close(self):
        """Close the connection. It is safe to call it more than one time."""
        if not self.closed:
            self.closed = True
            try:
                self._send_frame(OP_CLOSE, struct.pack('>H', 1000))
            except WebSocketError:
                pass
        try:
            self._sock.close()
        except OSError:
            pass
