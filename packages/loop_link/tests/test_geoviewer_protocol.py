"""Tests for the frames of the GeoViewer link (main/geoviewer/protocol.py)."""

import json
import struct

import numpy as np
import pytest

from loop_link.geoviewer import protocol


def split(frame):
    """Return the header and the bytes after it."""
    (length,) = struct.unpack_from('<I', frame, 0)
    return json.loads(frame[4 : 4 + length]), frame[4 + length :]


def test_frame_has_the_layout_of_the_protocol():
    frame = protocol.encode_frame(
        {'type': 'x'},
        [
            ('a', np.array([1.0, 2.0], dtype=np.float32)),
            ('b', np.array([[1, 2, 3]], dtype=np.uint32)),
        ],
    )
    header, rest = split(frame)
    assert header['version'] == {'major': 1, 'minor': 8}
    assert header['buffers'] == [
        {'name': 'a', 'dtype': 'f32', 'shape': [2]},
        {'name': 'b', 'dtype': 'u32', 'shape': [1, 3]},
    ]
    assert rest == struct.pack('<ff', 1.0, 2.0) + struct.pack('<III', 1, 2, 3)


def test_unsupported_buffer_type_is_refused():
    with pytest.raises(protocol.ProtocolError):
        protocol.encode_frame({'type': 'x'}, [('a', np.array([1], dtype=np.int64))])


def test_decode_header_round_trip_and_errors():
    assert protocol.decode_header(protocol.clear_message())['type'] == 'scene.clear'
    with pytest.raises(protocol.ProtocolError):
        protocol.decode_header(b'\x01')
    with pytest.raises(protocol.ProtocolError):
        protocol.decode_header(struct.pack('<I', 100) + b'{}')


def test_hello_has_crs_and_origin():
    header = protocol.decode_header(protocol.hello_message('EPSG:28350', (1, 2, 3)))
    assert header['type'] == 'hello'
    assert header['crs'] == 'EPSG:28350'
    assert header['origin'] == [1.0, 2.0, 3.0]
    assert header['application']['name'] == 'loop_link'
    header = protocol.decode_header(
        protocol.hello_message('EPSG:28350', (1, 2, 3), application='plugin_loopstructural')
    )
    assert header['application']['name'] == 'plugin_loopstructural'


def test_group_has_no_geometry():
    header = protocol.decode_header(protocol.group_message('g', 'Group', 'p', revision=3))
    assert header['object_type'] == 'Group'
    assert header['parent'] == 'p'
    assert header['revision'] == 3
    assert header['geometry'] == {}


def test_surface_subtracts_the_origin_and_writes_f32():
    vertices = [
        [500000.0, 7000000.0, 10.0],
        [500010.0, 7000000.0, 10.0],
        [500000.0, 7000010.0, 10.0],
    ]
    frame = protocol.surface_message(
        's', 'S', vertices, [[0, 1, 2]], origin=(500000.0, 7000000.0, 0.0), parent='g'
    )
    header, rest = split(frame)
    assert header['object_type'] == 'Surface'
    assert header['geometry'] == {'vertices': 'vertices', 'triangles': 'triangles'}
    assert header['buffers'][0] == {'name': 'vertices', 'dtype': 'f32', 'shape': [3, 3]}
    assert header['buffers'][1] == {'name': 'triangles', 'dtype': 'u32', 'shape': [1, 3]}
    values = np.frombuffer(rest[:36], dtype='<f4').reshape(3, 3)
    assert values.tolist() == [[0, 0, 10], [10, 0, 10], [0, 10, 10]]
    assert np.frombuffer(rest[36:], dtype='<u4').tolist() == [0, 1, 2]


def test_surface_far_from_the_origin_is_written_as_f64():
    vertices = [[0.0, 0.0, 0.0], [9000.0, 0.0, 0.0], [0.0, 9000.0, 0.0]]
    header, _ = split(protocol.surface_message('s', 'S', vertices, [[0, 1, 2]]))
    assert header['buffers'][0]['dtype'] == 'f64'


def test_surface_keeps_a_style():
    header, _ = split(
        protocol.surface_message(
            's',
            'S',
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 1, 2]],
            style={'colour': [1, 2, 3, 255]},
        )
    )
    assert header['style'] == {'colour': [1, 2, 3, 255]}


@pytest.mark.parametrize(
    'vertices, triangles',
    [
        ([], []),
        ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], []),
        ([[0, 0, 0], [1, 0, np.nan], [0, 1, 0]], [[0, 1, 2]]),
        ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 3]]),
        ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, -1]]),
    ],
)
def test_bad_surface_is_refused(vertices, triangles):
    with pytest.raises(protocol.ProtocolError):
        protocol.surface_message('s', 'S', vertices, triangles)


def test_frame_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(protocol, 'MAX_FRAME_BYTES', 100)
    with pytest.raises(protocol.ProtocolError):
        protocol.encode_frame({'type': 'x'}, [('a', np.zeros(100, dtype=np.float32))])
