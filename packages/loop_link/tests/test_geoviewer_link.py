"""Tests for the WebSocket client and the push session (main/geoviewer/link.py).

A fake viewer on 127.0.0.1 plays the part of GeoViewer.
"""

import pytest

from loop_link.geoviewer import protocol
from loop_link.geoviewer.link import GeoViewerLink, LinkError
from loop_link.websocket_client import WebSocketClient, WebSocketError

from geoviewer_fake_server import FakeViewer


@pytest.fixture
def viewer():
    fake = FakeViewer()
    yield fake
    fake.close()


def triangle(object_id):
    return protocol.surface_message(
        object_id, object_id, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]]
    )


def test_wrong_token_is_refused(viewer):
    with pytest.raises(WebSocketError, match='token'):
        WebSocketClient.connect('127.0.0.1', viewer.port, token='wrong')


def test_nothing_listens():
    fake = FakeViewer()
    port = fake.port
    fake.close()
    with pytest.raises(LinkError, match='Cannot connect'):
        GeoViewerLink(port, 'secret').push('EPSG:1', (0, 0, 0), lambda origin: [])


def test_push_says_hello_and_sends_the_objects(viewer):
    seen_origin = []

    def build(origin):
        seen_origin.append(list(origin))
        yield 'a', triangle('a')
        yield 'b', triangle('b')

    result = GeoViewerLink(viewer.port, 'secret').push('EPSG:28350', (1, 2, 3), build)
    assert viewer.types() == ['hello', 'scene.upsert', 'scene.upsert']
    assert viewer.headers('hello')[0]['origin'] == [1.0, 2.0, 3.0]
    assert viewer.headers('hello')[0]['crs'] == 'EPSG:28350'
    # the viewer origin applies, not the origin that the client proposed
    assert seen_origin == [[10.0, 20.0, 0.0]]
    assert result.sent == 2 and result.removed == 0 and not result.refused


def test_push_removes_old_objects_with_the_prefix_only():
    fake = FakeViewer(inventory=['loopstructural/old', 'loopstructural/keep', 'other/file'])
    try:
        result = GeoViewerLink(fake.port, 'secret').push(
            'EPSG:1',
            (0, 0, 0),
            lambda origin: [('loopstructural/keep', triangle('loopstructural/keep'))],
            replace_prefix='loopstructural/',
        )
    finally:
        fake.close()
    assert [h['id'] for h in fake.headers('scene.remove')] == ['loopstructural/old']
    assert result.removed == 1


def test_refused_object_is_reported():
    fake = FakeViewer(reply_errors={'a': 'the surface is not valid'})
    try:
        result = GeoViewerLink(fake.port, 'secret').push(
            'EPSG:1', (0, 0, 0), lambda origin: [('a', triangle('a')), ('b', triangle('b'))]
        )
    finally:
        fake.close()
    assert result.sent == 2
    assert result.refused == [('a', 'the surface is not valid')]
    assert '1 messages' in result.summary()


def test_large_message_is_sent_whole(viewer):
    import numpy as np

    count = 40000
    vertices = np.random.default_rng(0).random((count, 3)) * 100
    triangles = np.arange(count - count % 3).reshape(-1, 3)
    frame = protocol.surface_message('big', 'big', vertices, triangles)
    GeoViewerLink(viewer.port, 'secret').push('EPSG:1', (0, 0, 0), lambda origin: [('big', frame)])
    assert viewer.received[-1][1] == frame
