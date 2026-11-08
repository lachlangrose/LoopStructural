"""Tests for the command frames of the loop_link protocol."""

from __future__ import annotations

import pytest

from loop_link.encode import command_frame, commands_list_frame
from loop_link.protocol import ProtocolError, decode_frame


def test_commands_list_header():
    # The commands.list frame has the fixed header from the geoviewer fixtures.
    frame = decode_frame(commands_list_frame(1))
    assert frame.header == {
        "type": "commands.list",
        "version": {"major": 1, "minor": 11},
        "request": 1,
        "buffers": [],
    }


def test_command_frame_header():
    # The command.run frame carries the command name and the input.
    frame = decode_frame(command_frame(2, "object.set_visible", {"id": "p1", "visible": False}))
    assert frame.header == {
        "type": "command.run",
        "version": {"major": 1, "minor": 11},
        "request": 2,
        "command": "object.set_visible",
        "input": {"id": "p1", "visible": False},
        "buffers": [],
    }


def test_command_frames_have_no_buffers():
    # Neither frame carries binary buffers.
    assert decode_frame(commands_list_frame(1)).buffers == {}
    frame = decode_frame(command_frame(2, "object.set_visible", {"id": "p1", "visible": False}))
    assert frame.buffers == {}


def test_command_frame_does_not_change_input():
    # The caller's input mapping must keep its values after the call.
    input_ = {"id": "p1", "visible": False}
    before = dict(input_)
    command_frame(2, "object.set_visible", input_)
    assert input_ == before


def test_nested_input_round_trip():
    # A nested input comes back the same after encode and decode.
    input_ = {"object": "g", "edit": {"kind": "set_values", "array": "a", "values": [0, 2]}}
    frame = decode_frame(command_frame(3, "object.edit", input_))
    assert frame.header["input"] == input_


def test_nan_in_input_is_protocol_error():
    # JSON has no NaN. The encoder must refuse it.
    with pytest.raises(ProtocolError):
        command_frame(4, "object.set_visible", {"id": "p1", "value": float("nan")})
