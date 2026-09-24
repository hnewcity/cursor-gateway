import gzip
import json

import pytest
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value

from cursor_gateway.config import Config
from cursor_gateway.models import client_name, upstream_id
from cursor_gateway.protocol import (
    FrameDecoder,
    ProtocolError,
    connect_frame,
    decode_arg_value,
    json_bytes,
)
from cursor_gateway.session import safe_tool_call_id
from cursor_gateway.translate import build_turn_input, validate_request


def test_system_developer_and_active_user():
    body = validate_request(
        {
            "messages": [
                {"role": "system", "content": "speak Chinese"},
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "answer"},
                {"role": "user", "content": [{"type": "text", "text": "new"}]},
                {"role": "developer", "content": "be concise"},
            ]
        }
    )
    turn = build_turn_input(body, Config())
    assert turn.user_text == "new"
    assert len(turn.root_messages) == 6
    assert "speak Chinese" in turn.root_messages[0]["content"][0]["text"]
    assert "be concise" in turn.root_messages[-2]["content"][0]["text"]


def test_tool_result_replay_keeps_empty_result_and_recovers_name():
    body = validate_request(
        {
            "messages": [
                {"role": "user", "content": "weather"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "weather", "arguments": '{"city":"北京"}'},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": ""},
            ]
        }
    )
    turn = build_turn_input(body, Config())
    assert turn.user_text == Config().continuation_prompt
    assert turn.root_messages[1]["content"][0]["args"] == {"city": "北京"}
    result = turn.root_messages[-1]["content"][0]
    assert result == {
        "type": "tool-result",
        "toolName": "mcp_openai_weather",
        "toolCallId": "call_1",
        "result": "",
    }


def test_tool_choice_none_and_raw_system():
    body = validate_request(
        {
            "messages": [{"role": "system", "content": "hello"}, {"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "test"}}],
            "tool_choice": "none",
        }
    )
    turn = build_turn_input(body, Config(system_as_history=False))
    assert turn.tools == []
    assert turn.root_messages == [{"role": "system", "content": "hello"}]


def test_model_prefix_and_tool_ids(monkeypatch):
    monkeypatch.setenv("CURSOR_DIRECT_MODEL_PREFIX", "")
    assert Config.from_env(dotenv=False).model_prefix == ""
    assert client_name("cursor-grok", "cursor-") == "cursor-grok"
    assert upstream_id("cursor-grok", "cursor-", ["cursor-grok"]) == "cursor-grok"
    assert upstream_id("cursor-custom", "cursor-", []) == "custom"
    assert safe_tool_call_id("call-123\nfc_456") == "call-123_fc_456"


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        True,
        0,
        3.5,
        "",
        "你好",
        {"city": "北京", "flag": False, "x": [None, 1, {"nested": "yes"}]},
        [],
    ],
)
def test_real_protobuf_value(value):
    message = json_format.ParseDict(value, Value())
    assert decode_arg_value(message.SerializeToString()) == value


@pytest.mark.parametrize("timeout", [0, 120000, 180000])
def test_protobuf_tool_arguments_preserve_integer_json(timeout):
    value = {
        "timeoutMs": timeout,
        "targets": [{"threadId": "agent-1", "revision": 3}],
        "nested": [0, -2, 3.25, True, None, "180000"],
    }
    decoded = decode_arg_value(json_format.ParseDict(value, Value()).SerializeToString())
    assert json.loads(json_bytes(decoded)) == value
    assert type(decoded["timeoutMs"]) is int
    assert type(decoded["targets"][0]["revision"]) is int
    assert type(decoded["nested"][2]) is float
    assert type(decoded["nested"][3]) is bool


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_protobuf_tool_argument_is_rejected(number):
    with pytest.raises(ProtocolError, match="non-finite"):
        decode_arg_value(Value(number_value=number).SerializeToString())


def test_framing_fragmentation_and_compression():
    raw = json_bytes({"hello": "世界"})
    wire = connect_frame(gzip.compress(raw), 1) + connect_frame(b"{}", 2)
    decoder, frames = FrameDecoder(), []
    for byte in wire:
        frames.extend(decoder.feed(bytes([byte])))
    decoder.finish()
    assert json.loads(frames[0].payload) == {"hello": "世界"}
    assert frames[1].end_stream


@pytest.mark.parametrize("wire", [b"\x00\xff\xff\xff\xff", connect_frame(b"bad", 1)])
def test_invalid_frames_fail(wire):
    with pytest.raises(ProtocolError):
        FrameDecoder().feed(wire)


def test_truncated_frame_fails():
    decoder = FrameDecoder()
    decoder.feed(b"\x00\x00")
    with pytest.raises(ProtocolError, match="incomplete"):
        decoder.finish()
