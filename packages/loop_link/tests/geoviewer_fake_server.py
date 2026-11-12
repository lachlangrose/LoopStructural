"""A fake GeoViewer for the tests: a WebSocket server on 127.0.0.1.

It does what the link of the viewer does (see ``docs/protocol.md`` of the
GeoViewer repository): it checks the bearer token, answers ``hello`` with a
``hello`` and a ``scene.inventory``, and keeps the frames it receives.
"""

import base64
import hashlib
import socket
import struct
import threading

from loop_link.geoviewer import protocol

_GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def _read(conn, count, buffer):
    while len(buffer) < count:
        chunk = conn.recv(65536)
        if not chunk:
            raise ConnectionError
        buffer += chunk
    return buffer[:count], buffer[count:]


class FakeViewer:
    def __init__(self, token='secret', origin=(10.0, 20.0, 0.0), inventory=(), reply_errors=None):
        self.token = token
        self.origin = list(origin)
        self.inventory = list(inventory)
        # object id -> error text; the viewer refuses these objects
        self.reply_errors = dict(reply_errors or {})
        self.received = []  # (header, frame bytes)
        self.pings = 0
        self._server = socket.socket()
        self._server.bind(('127.0.0.1', 0))
        self._server.listen(1)
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self):
        self._server.close()

    # -- server -------------------------------------------------------------

    def _serve(self):
        try:
            conn, _ = self._server.accept()
        except OSError:
            return
        with conn:
            try:
                self._connection(conn)
            except (ConnectionError, OSError):
                pass

    def _connection(self, conn):
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = conn.recv(4096)
            if not chunk:
                return
            data += chunk
        head, _, buffer = data.partition(b'\r\n\r\n')
        lines = head.decode().split('\r\n')[1:]
        headers = {k.strip().lower(): v.strip() for k, _, v in (l.partition(':') for l in lines)}
        if headers.get('authorization') != f'Bearer {self.token}':
            conn.sendall(b'HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n')
            return
        accept = base64.b64encode(
            hashlib.sha1(headers['sec-websocket-key'].encode() + _GUID).digest()
        ).decode()
        conn.sendall(
            (
                'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                f'Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n'
            ).encode()
        )
        while True:
            opcode, payload, buffer = self._read_frame(conn, buffer)
            if opcode == 0x8:
                conn.sendall(bytes([0x88, 0]))
                return
            if opcode != 0x2:
                continue
            header = protocol.decode_header(payload)
            self.received.append((header, payload))
            if header['type'] == 'hello':
                self._send(
                    conn,
                    protocol.encode_frame(
                        {
                            'type': 'hello',
                            'application': {'name': 'fake', 'version': '0'},
                            'crs': header['crs'],
                            'origin': self.origin,
                        }
                    ),
                )
                self._send(
                    conn,
                    protocol.encode_frame(
                        {
                            'type': 'scene.inventory',
                            'entries': [
                                {'id': i, 'object_type': 'Surface', 'revision': 1}
                                for i in self.inventory
                            ],
                        }
                    ),
                )
                # a ping, to see that the client answers
                conn.sendall(bytes([0x89, 0]))
            elif header.get('id') in self.reply_errors:
                self._send(
                    conn,
                    protocol.encode_frame(
                        {
                            'type': 'error',
                            'code': 'invalid_object',
                            'object': header['id'],
                            'message': self.reply_errors[header['id']],
                        }
                    ),
                )

    @staticmethod
    def _read_frame(conn, buffer):
        head, buffer = _read(conn, 2, buffer)
        opcode, length = head[0] & 0x0F, head[1] & 0x7F
        assert head[1] & 0x80, 'a client frame must be masked'
        if length == 126:
            raw, buffer = _read(conn, 2, buffer)
            (length,) = struct.unpack('>H', raw)
        elif length == 127:
            raw, buffer = _read(conn, 8, buffer)
            (length,) = struct.unpack('>Q', raw)
        key, buffer = _read(conn, 4, buffer)
        payload, buffer = _read(conn, length, buffer)
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
        return opcode, payload, buffer

    @staticmethod
    def _send(conn, payload):
        length = len(payload)
        if length < 126:
            head = bytes([0x82, length])
        elif length < 1 << 16:
            head = bytes([0x82, 126]) + struct.pack('>H', length)
        else:
            head = bytes([0x82, 127]) + struct.pack('>Q', length)
        conn.sendall(head + payload)

    # -- helpers for the tests ---------------------------------------------

    def types(self):
        return [header['type'] for header, _ in self.received]

    def headers(self, kind):
        return [header for header, _ in self.received if header['type'] == kind]
