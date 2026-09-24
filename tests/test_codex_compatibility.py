"""Coding-client wire requests, compaction, structured output and image regression tests."""

import base64
import gzip
import json
import stat
from compression import zstd
from dataclasses import replace

import httpx
import pytest
from openai import AsyncOpenAI

from cursor_gateway.auth import Account, write_accounts
from cursor_gateway.compaction import PREFIX
from cursor_gateway.config import Config
from cursor_gateway.server import create_app
from cursor_gateway.session import TurnEvent

BODY = {"model": "cursor-auto", "input": "write code"}
TOOL = {"type": "function", "name": "check", "parameters": {"type": "object"}}
SEARCH = {
    "type": "tool_search",
    "execution": "client",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5e8AAAAASUVORK5CYII="
IMAGE = {"type": "input_image", "image_url": "data:image/png;base64," + PNG}
SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


class Catalog:
    async def list_ids(self, token):
        return ["auto"]


@pytest.fixture
def config(tmp_path):
    file = tmp_path / "accounts.json"
    write_accounts(file, [Account("test", "fake-cursor-token")])
    return Config(auth_file=file)


def application(config, events=None, runner=None):
    seen = []
    if runner is None:

        async def runner(**kwargs):
            seen.append(kwargs["turn"])
            for item in (
                events
                if events is not None
                else [
                    TurnEvent("text", delta="done"),
                    TurnEvent("done"),
                ]
            ):
                yield item

    return create_app(config, catalog=Catalog(), runner=runner), seen


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


def events(response):
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("zstd", zstd.compress)])
async def test_compressed_json_and_decoded_limit(config, encoding, compress):
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post(
            "/v1/responses",
            content=compress(json.dumps(BODY).encode()),
            headers={"content-encoding": encoding, "content-type": "application/json"},
        )
    assert response.status_code == 200 and len(seen) == 1
    limited, seen = application(replace(config, max_body_bytes=100))
    async with client(limited) as http:
        response = await http.post(
            "/v1/responses",
            content=compress(json.dumps({"input": "x" * 10000}).encode()),
            headers={"content-encoding": encoding},
        )
    assert response.status_code == 413 and not seen


@pytest.mark.parametrize("encoding", ["gzip", "zstd"])
async def test_invalid_or_truncated_compression_is_a_client_error(config, encoding):
    app, seen = application(config)
    compress = gzip.compress if encoding == "gzip" else zstd.compress
    async with client(app) as http:
        for body in (b"broken", compress(b"{}")[:-1], compress(b"{}") + b"junk"):
            response = await http.post(
                "/v1/responses", content=body, headers={"content-encoding": encoding}
            )
            assert response.status_code == 400
    assert not seen


async def test_unknown_content_encoding(config):
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post(
            "/v1/responses", content=b"x", headers={"content-encoding": "br"}
        )
    assert response.status_code == 415 and not seen


async def test_codex_reasoning_controls_and_phase_are_accepted(config):
    app, _ = application(config)
    body = {
        **BODY,
        "reasoning": {"effort": "high", "summary": "none", "context": "all_turns"},
        "stream_options": {"reasoning_summary_delivery": "sequential_cutoff"},
        "input": [
            {"role": "assistant", "phase": "commentary", "content": "working"},
            {"role": "user", "content": "continue"},
        ],
    }
    async with client(app) as http:
        response = await http.post("/v1/responses", json=body)
        assert response.status_code == 200
        stored = await http.get(f"/v1/responses/{response.json()['id']}/input_items?order=asc")
    assert stored.json()["data"][0]["phase"] == "commentary"


@pytest.mark.parametrize("stream", [False, True])
async def test_structured_final_answer_validated(config, stream):
    for text, valid in [('{"ok":true}', True), ('{"ok":"yes"}', False), ("not json", False)]:
        app, _ = application(config, [TurnEvent("text", delta=text), TurnEvent("done")])
        async with client(app) as http:
            response = await http.post(
                "/v1/responses",
                json={
                    **BODY,
                    "stream": stream,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "answer",
                            "strict": True,
                            "schema": SCHEMA,
                        }
                    },
                },
            )
        if stream:
            final = events(response)[-1]
            assert final["type"] == ("response.completed" if valid else "response.failed")
        else:
            assert response.status_code == (200 if valid else 502)
        if not valid:
            assert "did not match" in response.text


async def test_structured_output_accepts_local_refs_and_blocks_remote_refs(config):
    for schema, status in [
        ({"$defs": {"value": SCHEMA}, "$ref": "#/$defs/value"}, 200),
        ({"$ref": "http://127.0.0.1:1/never-fetch-this"}, 502),
        ({"type": "invalid-type"}, 400),
    ]:
        app, _ = application(config, [TurnEvent("text", delta='{"ok":true}'), TurnEvent("done")])
        async with client(app) as http:
            response = await http.post(
                "/v1/responses",
                json={
                    **BODY,
                    "text": {"format": {"type": "json_schema", "schema": schema}},
                },
            )
        assert response.status_code == status


@pytest.mark.parametrize("stream", [False, True])
async def test_client_tool_search_discovers_and_calls_namespaced_tools(config, stream):
    turns = []

    async def runner(**kwargs):
        turn = kwargs["turn"]
        turns.append(turn)
        if len(turns) == 1:
            yield TurnEvent(
                "tool_call", id="search_1", name=turn.tools[0].name, args={"query": "check"}
            )
            yield TurnEvent("done", reason="tool_calls")
        else:
            selected = next(tool for tool in turn.tools if "editor_check" in tool.name)
            yield TurnEvent("tool_call", id="check_1", name=selected.name, args={})
            yield TurnEvent("done", reason="tool_calls")

    app, _ = application(config, runner=runner)
    async with client(app) as http:
        first = await http.post("/v1/responses", json={**BODY, "tools": [SEARCH], "stream": stream})
        value = events(first)[-1]["response"] if stream else first.json()
        call = value["output"][0]
        assert call["type"] == "tool_search_call"
        assert call["arguments"] == {"query": "check"}
        assert call["execution"] == "client"
        second = await http.post(
            "/v1/responses",
            json={
                "model": BODY["model"],
                "previous_response_id": value["id"],
                "tools": [SEARCH],
                "input": [
                    {
                        "type": "tool_search_output",
                        "execution": "client",
                        "status": "completed",
                        "call_id": "search_1",
                        "tools": [
                            {
                                "type": "namespace",
                                "name": "editor",
                                "description": "editor",
                                "tools": [TOOL],
                            }
                        ],
                    }
                ],
            },
        )
    assert second.status_code == 200
    assert second.json()["output"][0]["namespace"] == "editor"
    assert second.json()["output"][0]["name"] == "check"
    assert "tool_search" in turns[1].root_messages[1]["content"][0]["toolName"]


async def test_hosted_tool_search_loads_declared_tools_eagerly(config):
    app, seen = application(config)
    async with client(app) as http:
        response = await http.post(
            "/v1/responses",
            json={
                **BODY,
                "tools": [{"type": "tool_search"}, {**TOOL, "defer_loading": True}],
            },
        )
    assert response.status_code == 200
    assert [tool.name for tool in seen[0].tools] == ["check"]


@pytest.mark.parametrize(
    "endpoint,stream",
    [
        ("/v1/responses/compact", False),
        ("/v1/responses", False),
        ("/v1/responses", True),
    ],
)
async def test_compaction_checkpoint_survives_new_app_and_keeps_pending_calls(
    config, endpoint, stream
):
    history = [
        {"role": "user", "content": "Implement the parser"},
        {
            "type": "function_call",
            "call_id": "pending",
            "name": "check",
            "namespace": "editor",
            "arguments": "{}",
        },
    ]
    app, seen = application(
        config, [TurnEvent("text", delta="Parser implemented; tests remain."), TurnEvent("done")]
    )
    async with client(app) as http:
        response = await http.post(
            endpoint,
            json={
                "input": history
                + ([{"type": "compaction_trigger"}] if endpoint == "/v1/responses" else []),
                "stream": stream,
                "store": False,
            },
        )
    assert response.status_code == 200
    value = events(response)[-1]["response"] if stream else response.json()
    assert len(seen[0].tools) == 0
    checkpoint = value["output"][-1]
    assert checkpoint["type"] == "compaction"
    assert checkpoint["encrypted_content"].startswith(PREFIX)
    assert "Parser implemented" not in checkpoint["encrypted_content"]
    assert stat.S_IMODE((config.auth_file.parent / "compaction.key").stat().st_mode) == 0o600
    new_app, continued = application(config)
    async with client(new_app) as http:
        followup = await http.post(
            "/v1/responses",
            json={
                "input": [
                    *value["output"],
                    {"type": "function_call_output", "call_id": "pending", "output": "passed"},
                ],
            },
        )
    assert followup.status_code == 200
    roots = json.dumps(continued[0].root_messages)
    assert "Parser implemented" in roots and "passed" in roots and "editor_check" in roots


async def test_compaction_receives_replayed_work_notes_and_phase(config):
    configured = replace(config, replay_reasoning=True)
    app, seen = application(
        configured,
        [TurnEvent("text", delta="Inspected files; editing remains."), TurnEvent("done")],
    )
    async with client(app) as http:
        response = await http.post(
            "/v1/responses/compact",
            json={
                "input": [
                    {"role": "user", "content": "Inspect and edit the documentation."},
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "FILES_ALREADY_INSPECTED"}],
                    },
                    {"role": "assistant", "phase": "commentary", "content": "Editing next."},
                ],
            },
        )
    assert response.status_code == 200
    roots = str(seen[0].root_messages)
    assert "FILES_ALREADY_INSPECTED" in roots and "phase=commentary" in roots
    new_app, resumed = application(configured)
    async with client(new_app) as http:
        followup = await http.post(
            "/v1/responses",
            json={"input": [*response.json()["output"], {"role": "user", "content": "Continue"}]},
        )
    assert followup.status_code == 200
    assert "Inspected files; editing remains." in str(resumed[0].root_messages)


async def test_compaction_does_not_accept_foreign_or_modified_state(config):
    app, _ = application(config, [TurnEvent("text", delta="summary"), TurnEvent("done")])
    async with client(app) as http:
        compact = (await http.post("/v1/responses/compact", json=BODY)).json()
        checkpoint = compact["output"][-1]
        for encrypted in ("foreign-state", checkpoint["encrypted_content"][:-4] + "AAAA"):
            response = await http.post(
                "/v1/responses",
                json={
                    "input": [{**checkpoint, "encrypted_content": encrypted}],
                },
            )
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "invalid_compaction_state"


async def test_compact_endpoint_sdk_and_no_plaintext_summary_in_logs(config, caplog):
    app, _ = application(
        config, [TurnEvent("text", delta="private checkpoint summary"), TurnEvent("done")]
    )
    async with AsyncOpenAI(
        api_key="test", base_url="http://test/v1", http_client=client(app)
    ) as api:
        response = await api.responses.compact(**BODY)
        assert response.object == "response.compaction"
        assert response.output[-1].type == "compaction"
    assert "private checkpoint summary" not in caplog.text


async def test_image_messages_and_tool_results_reach_cursor_attachments(config):
    app, seen = application(config)
    body = {
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Check the UI"}, IMAGE]},
            {"type": "function_call", "call_id": "image", "name": "screenshot", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "image", "output": [IMAGE]},
        ]
    }
    async with client(app) as http:
        response = await http.post("/v1/responses", json=body)
    assert response.status_code == 200
    assert len(seen[0].images) == 2
    image = seen[0].images[0]
    assert image.data == base64.b64decode(PNG)
    assert image.mime_type == "image/png"
    assert image.dimension.width == image.dimension.height == 1
    assert PNG not in json.dumps(seen[0].root_messages)
    assert response.json()["usage"]["input_tokens_details"]["estimated"] is True


@pytest.mark.parametrize("code", ["invalid_argument", "resource_exhausted"])
async def test_context_length_failure_is_recognizable_and_does_not_disable_account(config, code):
    app, _ = application(
        config,
        [
            TurnEvent(
                "done",
                reason="error",
                code=code,
                error="maximum context length exceeded",
            )
        ],
    )
    async with client(app) as http:
        response = await http.post("/v1/responses", json=BODY)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "context_length_exceeded"
    assert app.state.pool.size() == 1
