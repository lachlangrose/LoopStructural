"""Tests of the generic layer: the frame and the Link, with no GeoViewer message."""

import struct

import numpy as np
import pytest

from geoviewer_fake_server import FakeViewer
from loop_link import Link, LinkError, ProtocolError, decode_header, encode_frame


@pytest.fixture
def server():
    fake = FakeViewer()
    yield fake
    fake.close()


def test_frame_has_header_and_buffers():
    data = encode_frame(
        {'type': 'demo'}, [('xyz', np.arange(6, dtype=np.float64).reshape(2, 3))]
    )
    header = decode_header(data)
    assert header['type'] == 'demo'
    assert header['buffers'] == [{'name': 'xyz', 'dtype': 'f64', 'shape': [2, 3]}]
    (length,) = struct.unpack_from('<I', data, 0)
    assert len(data) == 4 + length + 6 * 8


def test_frame_has_a_version_only_when_given():
    assert 'version' not in decode_header(encode_frame({'type': 'demo'}))
    version = {'major': 2, 'minor': 1}
    assert decode_header(encode_frame({'type': 'demo'}, version=version))['version'] == version


def test_frame_refuses_a_type_it_does_not_know():
    with pytest.raises(ProtocolError, match='unsupported'):
        encode_frame({'type': 'demo'}, [('x', np.zeros(2, dtype=np.int64))])


def test_frame_refuses_a_frame_over_the_limit():
    with pytest.raises(ProtocolError, match='at most'):
        encode_frame({'type': 'demo'}, [('x', np.zeros(100, dtype=np.uint8))], max_bytes=50)


def test_session_sends_and_reads_until_the_answers_come(server):
    link = Link(server.port, 'secret', application='my_script', peer='The server')
    with link.session() as session:
        session.send({'type': 'hello', 'crs': 'EPSG:28350', 'origin': [0, 0, 0]})
        answer = session.read_until(('hello', 'scene.inventory'), timeout=5.0)
    assert answer['hello']['origin'] == [10.0, 20.0, 0.0]
    assert 'entries' in answer['scene.inventory']
    assert server.types()[0] == 'hello'


def test_session_with_a_wrong_token_says_so(server):
    with pytest.raises(LinkError, match='token'):
        with Link(server.port, 'wrong').session(hint='Check the token.'):
            pass


def test_read_until_raises_when_nothing_answers(server):
    link = Link(server.port, 'secret', peer='The server')
    with link.session() as session:
        with pytest.raises(LinkError, match='did not answer'):
            session.read_until(('hello',), timeout=0.2)
