"""Responses wire compatibility, SDK consumption, storage and continuation behavior."""

import asyncio
import json
import logging
import socket
from dataclasses import replace
from typing import get_args

import httpx
import pytest
import uvicorn
from openai import AsyncOpenAI, BadRequestError, NotFoundError
from openai.types.responses import Response, ResponseStreamEvent

from cursor_gateway.auth import Account, write_accounts
from cursor_gateway.config import Config
from cursor_gateway.response_store import ResponseStore
from cursor_gateway.server import create_app
from cursor_gateway.session import TurnEvent
from cursor_gateway.translate import RequestError

EVENT_TYPES = {
    get_args(cls.model_fields["type"].annotation)[0]: cls
    for cls in get_args(get_args(ResponseStreamEvent)[0])
}
BODY = {"model": "cursor-auto", "input": "你好"}
TOOL = {
    "type": "function",
    "name": "weather",
    "description": "天气",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
}


class Catalog:
    async def list_ids(self, token):
        return ["auto"]


@pytest.fixture
def config(tmp_path):
    file = tmp_path / "accounts.json"
    write_accounts(file, [Account("test", "fake-token")])
    return Config(auth_file=file)


def application(config, events=None, **options):
    seen = []
    if events is None:
        events = [TurnEvent("text", delta="你好"), TurnEvent("done")]

    async def runner(**kwargs):
        seen.append(kwargs)
        for event in events:
            yield event

    return create_app(config, catalog=Catalog(), runner=runner, **options), seen


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


def sdk(app):
    return AsyncOpenAI(
        api_key="key",
        base_url="http://test/v1",
        http_client=client(app),
        max_retries=0,
        _strict_response_validation=True,
    )


def sse_events(response):
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "[DONE]" not in response.text
    events = []
    for block in response.text.strip().split("\n\n"):
        event_line, data_line = block.splitlines()
        event = json.loads(data_line.removeprefix("data: "))
        assert event_line == "event: " + event["type"]
        EVENT_TYPES[event["type"]].model_validate(event, strict=True)
        events.append(event)
    assert [e["sequence_number"] for e in events] == list(range(len(events)))
    return events


@pytest.mark.parametrize("stream", [False, True])
async def test_codex_request_shape_accepts_include_namespaces_and_hosted_search(
    config, caplog, stream
):
    caplog.set_level(logging.INFO, logger="cursor_gateway.requests")
    tools = (
        [
            {"type": "function", "name": f"top_{i}", "parameters": {"type": "object"}}
            for i in range(12)
        ]
        + [
            {
                "type": "namespace",
                "name": f"domain_{i}",
                "description": "client tools",
                "tools": [{"type": "function", "name": "run", "parameters": {"type": "object"}}],
            }
            for i in range(12)
        ]
        + [{"type": "web_search"}]
    )
    app, seen = application(
        config,
        [TurnEvent("thinking", delta="考虑"), TurnEvent("text", delta="成功"), TurnEvent("done")],
    )
    body = {
        "model": "cursor-grok-4.6-high-fast",
        "instructions": "private instructions",
        "input": [
            {"role": role, "content": [{"type": "input_text", "text": "private content"}]}
            for role in ("developer", "user", "user")
        ],
        "tools": tools,
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "reasoning": {"effort": "high", "summary": "detailed"},
        "store": False,
        "stream": stream,
        "include": ["reasoning.encrypted_content"],
        "prompt_cache_key": "private-cache-key",
        "client_metadata": {"private": "private metadata"},
    }
    async with client(app) as http:
        response = await http.post("/v1/responses", json=body)
    assert response.status_code == 200
    value = sse_events(response)[-1]["response"] if stream else response.json()
    assert Response.model_validate(value).output_text == "成功"
    assert value["store"] is False
    assert len(value["tools"]) == 25
    assert value["tools"][-1]["type"] == "web_search"
    assert "encrypted_content" not in value["output"][0]
    assert len(seen[0]["turn"].tools) == 24
    assert len({tool.name for tool in seen[0]["turn"].tools}) == 24
    assert seen[0]["turn"].web_search
    records = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "cursor_gateway.requests"
    ]
    assert not any(record["event"] == "request_error" for record in records)
    notices = [record for record in records if record["event"] == "compatibility_notice"]
    assert {record["feature"] for record in notices} == {
        "web_search",
        "reasoning.encrypted_content",
    }
    assert records[-1]["outcome"] == "completed"
    assert records[-1]["request_id"] == response.headers["x-request-id"]
    for secret in (
        "private content",
        "private-cache-key",
        "private metadata",
        "private instructions",
    ):
        assert secret not in caplog.text


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("by_id", [False, True])
@pytest.mark.parametrize("kind", ["function", "custom"])
async def test_namespaced_tools_round_trip_through_sdk_history(config, stream, by_id, kind):
    raw_input = "*** Begin Patch\n*** End Patch\n"
    children = {"type": kind, "name": "run", "description": "client operation"}
    tools = [
        {"type": "function", "name": "run"},
        {
            "type": "namespace",
            "name": "shell",
            "description": "shell namespace",
            "tools": [children],
        },
        {
            "type": "namespace",
            "name": "files",
            "description": "files namespace",
            "tools": [children],
        },
    ]
    turns = []

    async def runner(**kwargs):
        turn = kwargs["turn"]
        turns.append(turn)
        if len(turns) == 1:
            yield TurnEvent(
                "tool_call",
                id="call_run",
                name=turn.tools[1].name,
                args={"input": raw_input} if kind == "custom" else {"path": "/tmp/example"},
            )
            yield TurnEvent("done", reason="tool_calls")
        else:
            yield TurnEvent("text", delta="done")
            yield TurnEvent("done")

    app = create_app(config, catalog=Catalog(), runner=runner)
    async with sdk(app) as api:
        if stream:
            async with api.responses.stream(
                **BODY, tools=tools, store=by_id, include=["reasoning.encrypted_content"]
            ) as streaming:
                received = [item async for item in streaming]
                first = await streaming.get_final_response()
            event_type = (
                "response.custom_tool_call_input.done"
                if kind == "custom"
                else "response.function_call_arguments.done"
            )
            assert any(item.type == event_type for item in received)
            added = next(item for item in received if item.type == "response.output_item.added")
            assert added.item.namespace == "shell" and added.item.name == "run"
        else:
            first = await api.responses.create(
                **BODY, tools=tools, store=by_id, include=["reasoning.encrypted_content"]
            )
        call = first.output[0]
        assert call.name == "run" and call.namespace == "shell"
        assert call.call_id == "call_run"
        if kind == "custom":
            assert call.type == "custom_tool_call"
            assert call.input == raw_input
        else:
            assert call.type == "function_call"
            assert json.loads(call.arguments) == {"path": "/tmp/example"}
        assert turns[0].tools[1].name not in first.model_dump_json()
        output = {
            "type": "custom_tool_call_output" if kind == "custom" else "function_call_output",
            "call_id": "call_run",
            "output": "client result",
        }
        params = {
            "model": BODY["model"],
            "tools": list(reversed(tools)),
            "include": ["reasoning.encrypted_content"],
        }
        if by_id:
            params.update(previous_response_id=first.id, input=[output])
        else:
            params["input"] = [
                {"role": "user", "content": BODY["input"]},
                *[item.model_dump(exclude_none=True) for item in first.output],
                output,
            ]
        second = await api.responses.create(**params)
        assert second.output_text == "done"
    assert len({tool.name for tool in turns[0].tools}) == 3
    assert {tool.name for tool in turns[0].tools} == {tool.name for tool in turns[1].tools}
    roots = turns[1].root_messages
    call_part = next(
        part
        for message in roots
        for part in message.get("content", [])
        if isinstance(part, dict) and part.get("type") == "tool-call"
    )
    assert call_part["toolName"] == "mcp_openai_" + turns[0].tools[1].name
    assert call_part["args"] == (
        {"input": raw_input} if kind == "custom" else {"path": "/tmp/example"}
    )
    assert roots[-1]["content"][0]["toolName"] == "mcp_openai_" + turns[0].tools[1].name
    assert roots[-1]["content"][0]["result"] == "client result"


@pytest.mark.parametrize("namespace", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_custom_tool_grammar_and_empty_input(config, namespace, stream):
    custom = {
        "type": "custom",
        "name": "apply_patch",
        "description": "Apply a patch",
        "format": {"type": "grammar", "syntax": "lark", "definition": 'start: "patch"'},
    }
    tools = [
        {"type": "namespace", "name": "files", "description": "file tools", "tools": [custom]}
        if namespace
        else custom
    ]
    seen = []

    async def runner(**kwargs):
        seen.append(kwargs["turn"])
        yield TurnEvent("tool_call", name=kwargs["turn"].tools[0].name, args={"input": ""})
        yield TurnEvent("done", reason="tool_calls")

    app = create_app(config, catalog=Catalog(), runner=runner)
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "stream": stream, "tools": tools})
    assert response.status_code == 200
    value = sse_events(response)[-1]["response"] if stream else response.json()
    assert value["output"][0]["type"] == "custom_tool_call"
    assert value["output"][0]["input"] == ""
    assert value["output"][0].get("namespace") == ("files" if namespace else None)
    assert 'start: "patch"' in seen[0].tools[0].description
    parameters = json.loads(seen[0].tools[0].input_schema_json)
    assert parameters["required"] == ["input"]


@pytest.mark.parametrize(
    "tools",
    [
        [{"type": "namespace", "name": "ns", "tools": None}],
        [{"type": "namespace", "name": "ns", "description": 1, "tools": []}],
        [{"type": "namespace", "name": [], "tools": []}],
        [
            {
                "type": "namespace",
                "name": "ns",
                "tools": [{"type": "namespace", "name": "inner", "tools": []}],
            }
        ],
        [{"type": "namespace", "name": "ns", "tools": [{"type": "web_search"}]}],
        [{"type": "namespace", "name": "ns", "tools": [{"type": []}]}],
        [{"type": "namespace", "name": "ns", "tools": [TOOL, TOOL]}],
        [{"type": "namespace", "name": "ns", "tools": []}] * 2,
        [{"type": "function", "name": "duplicate"}, {"type": "custom", "name": "duplicate"}],
        [
            {
                "type": "custom",
                "name": "x",
                "format": {"type": "grammar", "syntax": "unknown", "definition": "x"},
            }
        ],
        [{"type": "custom", "name": "x", "format": {"type": "grammar", "syntax": "lark"}}],
        [{"type": "custom", "name": "x", "format": []}],
    ],
)
async def test_invalid_namespace_or_custom_definition_fails_before_upstream(config, tools):
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "tools": tools})
    assert response.status_code == 400
    assert response.json()["error"]["param"].startswith("tools[")
    assert not seen


@pytest.mark.parametrize("include", ["reasoning.encrypted_content", [None], [{}], ["unknown"]])
async def test_invalid_include_remains_an_error(config, include):
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "include": include})
    assert response.status_code == 400
    assert response.json()["error"]["param"] == "include"
    assert not seen


async def test_namespaced_history_replays_without_current_tool_definitions(config):
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post(
            "/v1/responses",
            json={
                "input": [
                    {
                        "type": "function_call",
                        "name": "run",
                        "namespace": "shell",
                        "arguments": "{}",
                        "call_id": "f",
                    },
                    {"type": "function_call_output", "call_id": "f", "output": "result"},
                    {
                        "type": "custom_tool_call",
                        "name": "run",
                        "namespace": "files",
                        "input": "patch",
                        "call_id": "c",
                    },
                    {"type": "custom_tool_call_output", "call_id": "c", "output": "applied"},
                ],
            },
        )
    assert response.status_code == 200
    assert len(seen[0]["turn"].tools) == 0
    roots = seen[0]["turn"].root_messages
    assert roots[0]["content"][0]["toolName"] == roots[1]["content"][0]["toolName"]
    assert roots[2]["content"][0]["toolName"] == roots[3]["content"][0]["toolName"]
    assert roots[0]["content"][0]["toolName"] != roots[2]["content"][0]["toolName"]


@pytest.mark.parametrize("stream", [False, True])
async def test_malformed_upstream_custom_input_is_an_error(config, stream):
    async def runner(**kwargs):
        yield TurnEvent("tool_call", name=kwargs["turn"].tools[0].name, args={"input": 123})
        yield TurnEvent("done", reason="tool_calls")

    app = create_app(config, catalog=Catalog(), runner=runner)
    async with client(app) as http:
        response = await http.post(
            "/v1/responses",
            json={
                **BODY,
                "stream": stream,
                "tools": [{"type": "custom", "name": "patch"}],
            },
        )
    if stream:
        assert sse_events(response)[-1]["type"] == "response.failed"
    else:
        assert response.status_code == 502


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("by_id", [False, True])
async def test_phase_and_reasoning_survive_real_client_history_paths(config, stream, by_id):
    turns = []

    async def runner(**kwargs):
        turns.append(kwargs["turn"])
        if len(turns) == 1:
            yield TurnEvent("thinking", delta="INSPECTION_FINISHED_NEXT_EDIT")
            yield TurnEvent("text", delta="The inspection is complete; editing next.")
            yield TurnEvent("tool_call", name="weather", id="call_w", args={})
            yield TurnEvent("done", reason="tool_calls")
        else:
            yield TurnEvent("text", delta="Finished.")
            yield TurnEvent("done")

    app = create_app(replace(config, replay_reasoning=True), catalog=Catalog(), runner=runner)
    async with sdk(app) as api:
        params = {**BODY, "tools": [TOOL], "store": by_id}
        if stream:
            async with api.responses.stream(**params) as streaming:
                events = [event async for event in streaming]
                first = await streaming.get_final_response()
            done = next(
                event.item
                for event in events
                if event.type == "response.output_item.done" and event.item.type == "message"
            )
            assert done.phase == "commentary"
        else:
            first = await api.responses.create(**params)
        message = next(item for item in first.output if item.type == "message")
        assert message.phase == "commentary"
        tool_output = {"type": "function_call_output", "call_id": "call_w", "output": "edited"}
        if by_id:
            params.update(previous_response_id=first.id, input=[tool_output])
        else:
            params["input"] = [
                {"role": "user", "content": BODY["input"]},
                *[item.model_dump(exclude_none=True) for item in first.output],
                tool_output,
            ]
        final = await api.responses.create(**params)
        assert final.output[0].phase == "final_answer"
    roots = turns[-1].root_messages
    notes = [message for message in roots if "INSPECTION_FINISHED_NEXT_EDIT" in str(message)]
    assert len(notes) == 1 and notes[0]["role"] == "assistant"
    assert "historical" in str(notes[0]).lower()
    assert any("phase=commentary" in str(message) for message in roots)
    assert roots[-1]["content"][0]["result"] == "edited"


async def test_partial_failed_text_is_never_a_final_answer(config):
    app, _ = application(
        config, [TurnEvent("text", delta="Still checking"), TurnEvent("done", reason="error")]
    )
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "stream": True})
    events = sse_events(response)
    item = next(e["item"] for e in events if e["type"] == "response.output_item.done")
    assert item["phase"] == "commentary"
    assert item["status"] == "incomplete"
    assert events[-1]["type"] == "response.failed"


async def test_replayed_reasoning_is_not_written_to_request_logs(config, caplog):
    caplog.set_level(logging.INFO, logger="cursor_gateway.requests")
    app, seen = application(replace(config, replay_reasoning=True))
    async with client(app) as http:
        response = await http.post(
            "/v1/responses",
            json={
                **BODY,
                "input": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "PRIVATE_WORK_NOTES_741"}],
                    },
                    {"role": "user", "content": "Continue"},
                ],
            },
        )
    assert response.status_code == 200
    assert "PRIVATE_WORK_NOTES_741" in str(seen[0]["turn"].root_messages)
    assert "reasoning_replayed" in caplog.text
    assert "PRIVATE_WORK_NOTES_741" not in caplog.text


async def test_repeated_tool_diagnostic_does_not_stop_work_or_log_results(config, caplog):
    caplog.set_level(logging.INFO, logger="cursor_gateway.requests")
    items = [{"role": "user", "content": "Check the document"}]
    for index in range(3):
        items.extend(
            [
                {
                    "type": "function_call",
                    "call_id": f"read_{index}",
                    "name": "read",
                    "arguments": '{"path":"PRIVATE_FILE_92"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": f"read_{index}",
                    "output": "PRIVATE_FILE_CONTENT_48",
                },
            ]
        )
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "input": items})
    assert response.status_code == 200 and seen
    assert "repeated_tool_result" in caplog.text
    assert "PRIVATE_FILE_CONTENT_48" not in caplog.text
    assert "PRIVATE_FILE_92" not in caplog.text


@pytest.mark.parametrize("enabled", [False, True])
async def test_reasoning_replay_switch_and_current_user_priority(config, enabled):
    app, seen = application(replace(config, replay_reasoning=enabled))
    async with client(app) as http:
        response = await http.post(
            "/v1/responses",
            json={
                **BODY,
                "input": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "EARLIER_PLAN"}],
                    },
                    {"role": "assistant", "phase": "final_answer", "content": "Old task finished."},
                    {"role": "user", "content": "NEW_TASK"},
                ],
            },
        )
    assert response.status_code == 200
    turn = seen[0]["turn"]
    assert turn.user_text == "NEW_TASK"
    assert ("EARLIER_PLAN" in str(turn.root_messages)) is enabled
    assert any("phase=final_answer" in str(message) for message in turn.root_messages)
    assert all(message["role"] == "assistant" for message in turn.root_messages)


async def test_buffered_sdk_text_and_message_input(config):
    app, seen = application(
        config,
        [
            TurnEvent("thinking", delta="考虑一下"),
            TurnEvent("text", delta="你"),
            TurnEvent("text", delta="好"),
            TurnEvent("usage", input_tokens=3, output_tokens=7),
            TurnEvent("done"),
        ],
    )
    async with sdk(app) as api:
        response = await api.responses.create(
            **BODY,
            instructions="简洁回答",
            metadata={"source": "test"},
        )
        assert isinstance(response, Response)
        assert response.id.startswith("resp_")
        assert response.status == "completed"
        assert response.output_text == "你好"
        assert response.output[0].type == "reasoning"
        assert response.output[0].summary[0].text == "考虑一下"
        assert response.usage.total_tokens == 10
        assert response.usage.input_tokens_details.cached_tokens == 0
        assert response.metadata == {"source": "test"}
        assert seen[0]["model"] == "auto"
        assert seen[0]["turn"].user_text == "你好"
        assert "简洁回答" in seen[0]["turn"].root_messages[0]["content"][0]["text"]
        assert (await api.responses.retrieve(response.id)).model_dump() == response.model_dump()


async def test_stream_event_order_snapshots_unicode_and_final_response(config):
    app, _ = application(
        config,
        [
            TurnEvent("thinking", delta="想"),
            TurnEvent("thinking", delta="一想"),
            TurnEvent("text", delta="你"),
            TurnEvent("text", delta="好👋"),
            TurnEvent("usage", output_tokens=12),
            TurnEvent("done"),
        ],
    )
    async with client(app) as http:
        wire = await http.post("/v1/responses", json={**BODY, "stream": True})
        events = sse_events(wire)
        assert [e["type"] for e in events] == [
            "response.created",
            "response.in_progress",
            "response.output_item.added",
            "response.reasoning_summary_part.added",
            "response.reasoning_summary_text.delta",
            "response.reasoning_summary_text.delta",
            "response.reasoning_summary_text.done",
            "response.reasoning_summary_part.done",
            "response.output_item.done",
            "response.output_item.added",
            "response.content_part.added",
            "response.output_text.delta",
            "response.output_text.delta",
            "response.output_text.done",
            "response.content_part.done",
            "response.output_item.done",
            "response.completed",
        ]
        assert events[0]["response"]["output"] == []
        assert events[0]["response"]["status"] == "in_progress"
        assert events[2]["item"]["summary"] == []
        assert events[9]["item"]["content"] == []
        assert events[9]["item"]["status"] == "in_progress"
        final = events[-1]["response"]
        assert Response.model_validate(final).output_text == "你好👋"
        assert final["output"][0]["summary"][0]["text"] == "想一想"
        assert final["usage"]["output_tokens"] == 12
        assert all(item["status"] == "completed" for item in final["output"])
        assert (await http.get("/v1/responses/" + final["id"])).json() == final


async def test_official_sdk_stream_helper_accumulates_text_and_tools(config):
    app, _ = application(
        config,
        [
            TurnEvent("thinking", delta="look"),
            TurnEvent("text", delta="查一下"),
            TurnEvent("tool_call", id="call_weather", name="weather", args={"city": "北京"}),
            TurnEvent("usage", output_tokens=9),
            TurnEvent("done", reason="tool_calls"),
        ],
    )
    async with sdk(app) as api:
        async with api.responses.stream(**BODY, tools=[TOOL]) as stream:
            events = [event async for event in stream]
            final = await stream.get_final_response()
        assert final.status == "completed"
        assert final.output_text == "查一下"
        call = final.output[-1]
        assert call.id.startswith("fc_") and call.id != call.call_id
        assert call.call_id == "call_weather"
        assert json.loads(call.arguments) == {"city": "北京"}
        assert final.usage.output_tokens == 9
        assert sum(e.type == "response.function_call_arguments.delta" for e in events) == 1
        assert any(e.type == "response.function_call_arguments.done" for e in events)
        assert events[-1].type == "response.completed"


@pytest.mark.parametrize("stream", [False, True])
async def test_empty_success_is_valid_and_saved(config, stream):
    app, _ = application(config, [TurnEvent("done")])
    async with client(app) as http:
        wire = await http.post("/v1/responses", json={**BODY, "stream": stream})
    value = sse_events(wire)[-1]["response"] if stream else wire.json()
    assert value["status"] == "completed" and value["output"] == []
    Response.model_validate(value)


@pytest.mark.parametrize("by_id", [False, True])
async def test_function_result_continuation_and_instructions_do_not_leak(config, by_id):
    turns = []

    async def runner(**kwargs):
        turns.append(kwargs["turn"])
        if len(turns) == 1:
            yield TurnEvent("tool_call", id="call_w", name="weather", args={"city": "北京"})
            yield TurnEvent("done", reason="tool_calls")
        else:
            yield TurnEvent("text", delta="晴天")
            yield TurnEvent("done")

    app = create_app(config, catalog=Catalog(), runner=runner)
    async with sdk(app) as api:
        first = await api.responses.create(
            **BODY,
            tools=[TOOL],
            instructions="old-instructions",
            store=by_id,
        )
        output = {"type": "function_call_output", "call_id": "call_w", "output": ""}
        params = {"model": "cursor-auto", "tools": [TOOL], "instructions": "new-instructions"}
        if by_id:
            params.update(previous_response_id=first.id, input=[output])
        else:
            params["input"] = [
                {"role": "user", "content": BODY["input"]},
                *[i.model_dump(exclude_none=True) for i in first.output],
                output,
            ]
        second = await api.responses.create(**params)
        assert second.output_text == "晴天"
        roots = turns[-1].root_messages
        assert turns[-1].user_text == config.continuation_prompt
        assert "new-instructions" in roots[0]["content"][0]["text"]
        assert "old-instructions" not in json.dumps(roots)
        assert roots[-1]["role"] == "tool"
        assert roots[-1]["content"][0] == {
            "type": "tool-result",
            "toolName": "mcp_openai_weather",
            "toolCallId": "call_w",
            "result": "",
        }
        assert turns[-1].tools[0].name == "weather"


async def test_previous_response_chain_pagination_delete_and_branching(config):
    app, seen = application(config)
    async with sdk(app) as api:
        first = await api.responses.create(**BODY, instructions="do not inherit")
        second = await api.responses.create(
            model="cursor-auto",
            input="第二轮",
            previous_response_id=first.id,
        )
        assert "do not inherit" not in json.dumps(seen[-1]["turn"].root_messages)
        page = await api.responses.input_items.list(second.id, order="asc", limit=1)
        assert page.has_more
        history = [item async for item in page]
        assert [item.role for item in history] == ["user", "assistant", "user"]
        assert history[-1].content[0].text == "第二轮"
        descending = await api.responses.input_items.list(second.id)
        assert descending.data[0].id == history[-1].id
        await api.responses.delete(first.id)
        with pytest.raises(NotFoundError):
            await api.responses.retrieve(first.id)
        # A child retains its own bounded history even after its parent is deleted.
        third = await api.responses.create(input="第三轮", previous_response_id=second.id)
        assert third.status == "completed"
        assert seen[-1]["turn"].user_text == "第三轮"
        assert "第二轮" in str(seen[-1]["turn"].root_messages)


async def test_parallel_branches_and_returned_snapshots_are_independent(config):
    app, seen = application(config)
    async with sdk(app) as api:
        first = await api.responses.create(**BODY)
        branches = await asyncio.gather(
            *[
                api.responses.create(input=f"branch-{i}", previous_response_id=first.id)
                for i in range(3)
            ]
        )
        assert len({b.id for b in branches}) == 3
        assert {turn["turn"].user_text for turn in seen[1:]} == {"branch-0", "branch-1", "branch-2"}
        assert all("branch-" not in str(turn["turn"].root_messages) for turn in seen[1:])
        assert (await api.responses.retrieve(first.id)).output_text == "你好"


async def test_store_false_and_cache_expiry_eviction(config):
    now = [0]
    store = ResponseStore(ttl=5, max_entries=1, clock=lambda: now[0])
    app, _ = application(config, response_store=store)
    async with sdk(app) as api:
        no_store = await api.responses.create(**BODY, store=False)
        with pytest.raises(NotFoundError):
            await api.responses.retrieve(no_store.id)
        with pytest.raises(NotFoundError):
            await api.responses.create(input="next", previous_response_id=no_store.id)
        first = await api.responses.create(**BODY)
        second = await api.responses.create(**BODY)
        with pytest.raises(NotFoundError):
            await api.responses.retrieve(first.id)
        now[0] = 6
        with pytest.raises(NotFoundError):
            await api.responses.retrieve(second.id)


def test_cache_byte_bound_lru_and_immutable_snapshots():
    store = ResponseStore(max_entries=5, max_bytes=150)
    store.put({"id": "a", "text": "a" * 25}, [])
    store.put({"id": "b", "text": "b" * 25}, [])
    snapshot = store.get("a")
    snapshot["response"]["text"] = "changed"
    store.put({"id": "c", "text": "c" * 25}, [])
    assert store.get("a")["response"]["text"] == "a" * 25
    with pytest.raises(RequestError) as error:
        store.get("b")
    assert error.value.status == 404
    with pytest.raises(RequestError) as error:
        store.put({"id": "big", "text": "x" * 200}, [])
    assert error.value.status == 413


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "code,status",
    [
        ("resource_exhausted", 429),
        ("unauthenticated", 401),
        ("permission_denied", 403),
        ("invalid_argument", 400),
        ("deadline_exceeded", 504),
        ("unavailable", 503),
    ],
)
async def test_early_errors_use_http_status(config, stream, code, status):
    app, _ = application(
        config,
        [
            TurnEvent("usage", output_tokens=1),
            TurnEvent("done", reason="error", error="failure", code=code),
        ],
    )
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "stream": stream})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    if status in {401, 403, 429}:
        assert app.state.pool.size() == 0


async def test_midstream_failure_retains_partial_output_and_is_not_completed(config):
    app, _ = application(
        config,
        [
            TurnEvent("text", delta="partial"),
            TurnEvent("done", reason="error", code="resource_exhausted", error="quota"),
        ],
    )
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "stream": True})
        events = sse_events(response)
        assert events[-1]["type"] == "response.failed"
        assert not any(e["type"] == "response.completed" for e in events)
        final = events[-1]["response"]
        assert final["error"] == {"code": "rate_limit_exceeded", "message": "quota"}
        assert final["output"][0]["content"][0]["text"] == "partial"
        assert final["output"][0]["status"] == "incomplete"
        assert (await http.get("/v1/responses/" + final["id"])).json() == final
        followup = await http.post(
            "/v1/responses",
            json={
                "input": "continue",
                "previous_response_id": final["id"],
            },
        )
        assert followup.status_code == 400


@pytest.mark.parametrize("stream", [False, True])
async def test_eof_and_unexpected_runner_exception_are_failures(config, stream):
    app, _ = application(config, [TurnEvent("text", delta="partial")])
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "stream": stream})
    if stream:
        assert sse_events(response)[-1]["type"] == "response.failed"
    else:
        assert response.status_code == 502

    async def runner(**kwargs):
        yield TurnEvent("text", delta="partial")
        raise RuntimeError("private internal detail")

    app = create_app(config, runner=runner, catalog=Catalog())
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "stream": stream})
    assert "private internal detail" not in response.text
    if stream:
        assert sse_events(response)[-1]["type"] == "response.failed"
    else:
        assert response.status_code == 502


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"input": []},
        {"input": 1},
        {"input": [None]},
        {"input": [{"type": []}]},
        {"input": [{"role": [], "content": "bad"}]},
        {"input": [{"role": "user", "content": [{"type": "input_image", "image_url": "x"}]}]},
        {"input": [{"role": "user", "content": [{"type": "input_text", "text": 123}]}]},
        {"input": [{"role": "user", "id": {}, "content": "hi"}]},
        {"input": [{"type": "item_reference", "id": "msg_x"}]},
        {"input": [{"type": "function_call_output", "call_id": "missing", "output": "x"}]},
        {"input": [{"type": "reasoning", "summary": [], "encrypted_content": "opaque"}]},
        {**BODY, "stream": "true"},
        {**BODY, "store": 1},
        {**BODY, "instructions": {}},
        {**BODY, "background": True},
        {**BODY, "conversation": "conv_x"},
        {**BODY, "prompt": {"id": "pmpt_x"}},
        {**BODY, "include": ["unsupported.field"]},
        {**BODY, "tool_choice": "required"},
        {**BODY, "tool_choice": {"type": "function", "name": "x"}},
        {**BODY, "tools": [{"type": "file_search"}]},
        {**BODY, "tools": [None]},
        {**BODY, "tools": [{**TOOL, "strict": "true"}]},
        {**BODY, "tools": [{**TOOL, "description": False}]},
        {**BODY, "tools": [TOOL, TOOL]},
        {**BODY, "text": {"format": {"type": "json_schema"}}},
        {**BODY, "text": []},
        {**BODY, "truncation": "auto"},
        {**BODY, "metadata": []},
        {**BODY, "metadata": {"key": 2}},
        {**BODY, "reasoning": {"effort": {}}},
        {**BODY, "max_output_tokens": True},
        {**BODY, "max_output_tokens": 0},
        {**BODY, "temperature": 3},
        {**BODY, "top_p": []},
        {**BODY, "stream_options": {"include_usage": True}},
    ],
)
async def test_invalid_or_unsupported_input_fails_before_upstream(config, bad):
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post("/v1/responses", content=json.dumps(bad))
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert seen == []


async def test_auth_missing_accounts_and_invalid_body(config, tmp_path):
    app, _ = application(replace(config, api_key="key"))
    async with client(app) as http:
        for method, path in [
            ("POST", "/v1/responses"),
            ("GET", "/v1/responses/resp_missing"),
            ("DELETE", "/v1/responses/resp_missing"),
            ("GET", "/v1/responses/resp_missing/input_items"),
        ]:
            assert (await http.request(method, path, json=BODY)).status_code == 401
        assert (
            await http.post("/v1/responses", headers={"x-api-key": "key"}, json=BODY)
        ).status_code == 200
    app, _ = application(Config(auth_file=tmp_path / "missing"))
    async with client(app) as http:
        assert (await http.post("/v1/responses", json=BODY)).status_code == 503
        assert (await http.post("/v1/responses", content="{broken")).status_code == 400
        assert (await http.post("/v1/responses", content='{"input": NaN}')).status_code == 400


@pytest.mark.parametrize("stream", [False, True])
async def test_request_history_output_and_storage_limits(config, stream):
    app, _ = application(
        replace(config, max_body_bytes=1100),
        [
            TurnEvent("text", delta="x" * 2000),
            TurnEvent("done"),
        ],
    )
    async with client(app) as http:
        assert (await http.post("/v1/responses", content=b"x" * 1101)).status_code == 413
        response = await http.post("/v1/responses", json={**BODY, "stream": stream})
        if stream:
            assert sse_events(response)[-1]["type"] == "response.failed"
        else:
            assert response.status_code == 502
    app, _ = application(config, response_store=ResponseStore(max_bytes=100))
    async with client(app) as http:
        response = await http.post("/v1/responses", json={**BODY, "stream": stream})
        if stream:
            assert sse_events(response)[-1]["type"] == "response.failed"
        else:
            assert response.status_code == 413
        response = await http.post("/v1/responses", json={**BODY, "store": False})
        assert response.status_code == 200


async def test_openapi_response_body_auth_and_pagination_errors(config):
    app, _ = application(config)
    async with client(app) as http:
        schema = (await http.get("/openapi.json")).json()
        endpoint = schema["paths"]["/v1/responses"]["post"]
        properties = endpoint["requestBody"]["content"]["application/json"]["schema"]["properties"]
        assert "input" in properties and "previous_response_id" in properties
        assert "text/event-stream" in endpoint["responses"]["200"]["content"]
        assert endpoint["security"] == [{"BearerAuth": []}, {"ApiKeyAuth": []}]
        assert "422" not in endpoint["responses"]
        for path, operations in schema["paths"].items():
            if path.startswith("/v1/responses"):
                assert all("422" not in operation["responses"] for operation in operations.values())
        response = (await http.post("/v1/responses", json=BODY)).json()
        path = "/v1/responses/" + response["id"]
        for query in ("limit=0", "limit=101", "order=wrong", "after=missing", "include=anything"):
            assert (await http.get(path + "/input_items?" + query)).status_code == 400
        assert (await http.get(path + "?stream=true")).status_code == 400
    async with sdk(app) as api:
        with pytest.raises(BadRequestError):
            await api.responses.create(**BODY, background=True)


async def test_text_parts_tool_choice_none_and_explicit_system_history(config):
    app, seen = application(config)
    async with sdk(app) as api:
        response = await api.responses.create(
            model="cursor-some-model",
            tools=[TOOL],
            tool_choice="none",
            input=[
                {"role": "developer", "content": "keep this instruction"},
                {"role": "user", "content": [{"type": "input_text", "text": "question"}]},
                {"role": "assistant", "content": [{"type": "input_text", "text": "answer"}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "part one"},
                        {"type": "input_text", "text": "part two"},
                    ],
                },
            ],
        )
        assert seen[0]["turn"].user_text == "part one\npart two"
        assert seen[0]["turn"].tools == []
        assert "answer" in str(seen[0]["turn"].root_messages)
        await api.responses.create(previous_response_id=response.id, input="next")
        assert seen[-1]["model"] == "some-model"
        assert "keep this instruction" in str(seen[-1]["turn"].root_messages)


async def test_tool_output_text_array_replay_and_duplicate_output_rejection(config):
    app, seen = application(config)
    call = {"type": "function_call", "call_id": "call_1", "name": "weather", "arguments": "{}"}
    output = {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": [{"type": "input_text", "text": "sunny"}],
    }
    async with sdk(app) as api:
        await api.responses.create(input=[call, output])
        assert seen[-1]["turn"].root_messages[-1]["content"][0]["result"] == "sunny"
        with pytest.raises(BadRequestError):
            await api.responses.create(input=[call, output, output])


async def test_combined_history_size_is_checked_before_generating(config):
    app, seen = application(replace(config, max_body_bytes=1800))
    async with client(app) as http:
        first = await http.post("/v1/responses", json={"input": "x" * 1100})
        assert first.status_code == 200
        second = await http.post(
            "/v1/responses",
            json={
                "input": "x" * 1100,
                "previous_response_id": first.json()["id"],
            },
        )
        assert second.status_code == 413
        assert second.json()["error"]["param"] == "input"
        assert len(seen) == 1


async def test_live_http_stream_delivers_before_completion_and_cancels_on_close(config):
    ready, closed = asyncio.Event(), asyncio.Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            ready.set()

    async def runner(**kwargs):
        try:
            yield TurnEvent("text", delta="first token")
            await asyncio.Event().wait()
        finally:
            closed.set()

    app = create_app(config, catalog=Catalog(), runner=runner)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    server = Server(uvicorn.Config(app, lifespan="off", log_level="error", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            await ready.wait()
            async with httpx.AsyncClient() as http:
                async with http.stream(
                    "POST",
                    f"http://127.0.0.1:{port}/v1/responses",
                    json={**BODY, "stream": True},
                ) as response:
                    assert response.status_code == 200
                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and "response.output_text.delta" in line:
                            assert json.loads(line[6:])["delta"] == "first token"
                            assert not closed.is_set()
                            break
                    else:
                        pytest.fail("stream ended without delivering the first token")
                await closed.wait()
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 3)
        listener.close()
