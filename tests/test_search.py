import json

import pytest
from openai.types.responses import Response

from cursor_gateway.proto import agent_pb2 as pb
from cursor_gateway.protocol import ProtocolError
from cursor_gateway.responses import ResponseState
from cursor_gateway.responses_tools import tool_alias
from cursor_gateway.search_scratch import SearchScratch
from cursor_gateway.session import TurnEvent


def test_search_documents_stay_in_memory_and_cannot_write_workspace_paths(tmp_path):
    scratch = SearchScratch(1024)
    for path in (str(tmp_path / "private.txt"), "agent-tools/../private.txt", "hello.py"):
        result = scratch.handle(
            pb.ExecServerMessage(id=1, write_args=pb.WriteArgs(path=path, file_text="private"))
        ).exec_client_message.write_result
        assert result.WhichOneof("result") == "error"
    assert not list(tmp_path.iterdir())
    assert not scratch.files
    result = scratch.handle(
        pb.ExecServerMessage(
            id=2,
            exec_id="search",
            write_args=pb.WriteArgs(path="agent-tools/document.txt", file_text="one\ntwo\nthree\n"),
        )
    ).exec_client_message
    assert result.id == 2 and result.exec_id == "search"
    assert result.write_result.success.lines_created == 3
    result = scratch.handle(
        pb.ExecServerMessage(
            id=3, read_args=pb.ReadArgs(path="agent-tools/document.txt", offset=2, limit=1)
        )
    ).exec_client_message.read_result
    assert result.success.content == "two\n"
    assert result.success.total_lines == 3
    assert result.success.truncated
    with pytest.raises(ProtocolError, match="buffer limit"):
        scratch.handle(
            pb.ExecServerMessage(
                write_args=pb.WriteArgs(path="agent-tools/large.txt", file_text="x" * 1025)
            )
        )


def test_web_search_sse_items_are_sdk_compatible():
    state = ResponseState(
        {
            "store": False,
            "tools": [{"type": "web_search"}],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "metadata": {},
        },
        "cursor-test",
        100000,
    )
    source = {"type": "url", "url": "https://docs.python.org"}
    events = state.add(
        TurnEvent(
            "web_search", id="ws_test", args={"query": "Python TaskGroup", "sources": [source]}
        )
    )
    state.add(TurnEvent("text", delta="See Python docs."))
    state.finish(TurnEvent("done"))
    value = Response.model_validate(state.value)
    assert value.output[0].type == "web_search_call"
    assert value.output[0].status == "completed"
    assert value.output[0].action.query == "Python TaskGroup"
    assert value.output_text == "See Python docs."
    assert [event["type"] for event in events] == [
        "response.output_item.added",
        "response.web_search_call.in_progress",
        "response.web_search_call.searching",
        "response.web_search_call.completed",
        "response.output_item.done",
    ]
    assert json.loads(json.dumps(events))[0]["item"]["status"] == "in_progress"


def test_tool_aliases_leave_room_for_cursor_prefix_and_do_not_collide():
    names = [
        ("x" * 100 + suffix, namespace, kind)
        for suffix in ("a", "b")
        for namespace in (None, "very_long_namespace_" * 8)
        for kind in ("function", "custom")
    ]
    aliases = [tool_alias(*name) for name in names]
    aliases.extend(tool_alias("x" * length) for length in (49, 55, 64))
    assert len(set(aliases)) == len(aliases)
    assert all(len("mcp_openai_" + alias) < 64 for alias in aliases)
    assert aliases[: len(names)] == [tool_alias(*name) for name in names]


def test_common_tool_aliases_keep_full_names_without_random_suffixes():
    alias = tool_alias("wait_agent", "multi_agent_v1")
    assert alias.endswith("_multi_agent_v1_wait_agent")
    assert len("mcp_openai_" + alias) < 64
    assert tool_alias("c", "a_b") != tool_alias("b_c", "a")
    assert tool_alias(alias) != alias  # A literal function cannot steal an internal alias.
