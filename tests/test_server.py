import asyncio
import json
import logging
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from cursor_gateway.auth import Account, write_accounts
from cursor_gateway.config import Config
from cursor_gateway.server import create_app
from cursor_gateway.session import TurnEvent


class Catalog:
    async def list_ids(self, token):
        return ["auto", "cursor-grok"]


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "accounts.json"
    write_accounts(path, [Account("test", "fake-token")])
    return Config(auth_file=path)


def application(config, events):
    async def runner(**kwargs):
        for event in events:
            yield event

    return create_app(config, catalog=Catalog(), runner=runner)


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


BODY = {"model": "cursor-auto", "messages": [{"role": "user", "content": "hi"}]}


async def test_fastapi_docs_describe_body_streaming_and_both_auth_methods(config):
    app = application(replace(config, api_key="key"), [])
    assert isinstance(app, FastAPI)
    async with client(app) as http:
        assert (await http.get("/docs")).status_code == 200
        assert (await http.get("/redoc")).status_code == 200
        response = await http.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
    assert schema["info"]["title"] == "Cursor Gateway"
    paths = schema["paths"]
    assert set(paths) == {
        "/health",
        "/v1/models",
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/responses/compact",
        "/v1/responses/{response_id}",
        "/v1/responses/{response_id}/input_items",
    }
    assert not paths["/health"]["get"].get("security")
    chat = paths["/v1/chat/completions"]["post"]
    assert chat["requestBody"]["required"]
    assert chat["requestBody"]["content"]["application/json"]["schema"]["required"] == ["messages"]
    assert "text/event-stream" in chat["responses"]["200"]["content"]
    assert "400" in chat["responses"] and "422" not in chat["responses"]
    assert {"BearerAuth": []} in chat["security"]
    assert {"ApiKeyAuth": []} in chat["security"]
    assert schema["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"
    assert schema["components"]["securitySchemes"]["ApiKeyAuth"]["name"] == "x-api-key"


@pytest.mark.parametrize("path", ["/", "/health", "/v1/models"])
async def test_head_routes_remain_compatible(config, path):
    async with client(application(config, [])) as http:
        response = await http.head(path)
    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.parametrize(
    "headers",
    [
        {"authorization": "Bearer key"},
        {"authorization": "bearer key"},
        {"x-api-key": "key"},
        {"authorization": "Bearer wrong", "x-api-key": "key"},
    ],
)
async def test_fastapi_security_dependencies_accept_either_key(config, headers):
    async with client(application(replace(config, api_key="key"), [])) as http:
        response = await http.get("/v1/models", headers=headers)
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/v1/chat/completions", "/v1/responses"])
async def test_unauthorized_chat_is_rejected_before_reading_request_body(config, path):
    app = application(replace(config, api_key="key", max_body_bytes=10), [])
    received = []
    sent = []

    async def receive():
        received.append(True)
        raise AssertionError("unauthenticated request body must not be read")

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "POST",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "http_version": "1.1",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 1234),
        },
        receive,
        send,
    )
    assert not received
    assert sent[0]["status"] == 401
    assert json.loads(sent[1]["body"])["error"]["message"] == "invalid api key"


async def test_framework_errors_keep_openai_error_shape(config):
    async with client(application(config, [])) as http:
        for method, path, status in [
            ("GET", "/missing", 404),
            ("GET", "/v1/chat/completions", 405),
        ]:
            response = await http.request(method, path)
            assert response.status_code == status
            assert response.json()["error"]["type"] == "invalid_request_error"


async def test_health_auth_models_and_empty_accounts(config, tmp_path):
    app = application(replace(config, api_key="key"), [])
    async with client(app) as http:
        assert (await http.get("/health")).json()["accounts"] == 1
        assert (await http.get("/v1/models")).status_code == 401
        result = await http.get("/v1/models", headers={"x-api-key": "key"})
        assert [model["id"] for model in result.json()["data"]] == ["auto", "grok"]
        assert (await http.post("/v1/chat/completions", json=BODY)).status_code == 401
    app = application(Config(auth_file=tmp_path / "missing.json"), [])
    async with client(app) as http:
        response = await http.post("/v1/chat/completions", json=BODY)
        assert response.status_code == 503
        assert "no Cursor account" in response.json()["error"]["message"]


async def test_buffered_response_tool_reasoning_usage(config):
    app = application(
        config,
        [
            TurnEvent("thinking", delta="think"),
            TurnEvent("text", delta="你好"),
            TurnEvent("tool_call", id="call_1", name="weather", args={"city": "北京"}),
            TurnEvent("usage", output_tokens=9),
            TurnEvent("done", reason="tool_calls"),
        ],
    )
    async with client(app) as http:
        response = await http.post("/v1/chat/completions", json=BODY)
    assert response.status_code == 200
    data = response.json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["reasoning_content"] == "think"
    assert choice["message"]["content"] == "你好"
    assert json.loads(choice["message"]["tool_calls"][0]["function"]["arguments"]) == {
        "city": "北京"
    }
    assert data["usage"] == {"prompt_tokens": 0, "completion_tokens": 9, "total_tokens": 9}


async def test_stream_tool_calls_and_standard_usage_chunk(config):
    app = application(
        config,
        [
            TurnEvent("text", delta="hello"),
            TurnEvent("tool_call", id="call_a", name="weather", args={"x": 1}),
            TurnEvent("usage", output_tokens=7),
            TurnEvent("done", reason="tool_calls"),
        ],
    )
    async with client(app) as http:
        response = await http.post(
            "/v1/chat/completions",
            json={
                **BODY,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        )
    assert response.headers["content-type"].startswith("text/event-stream")
    chunks = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[2]["choices"][0]["delta"]["tool_calls"][0]["index"] == 0
    assert chunks[-2]["choices"][0]["finish_reason"] == "tool_calls"
    assert chunks[-1]["choices"] == []
    assert chunks[-1]["usage"]["total_tokens"] == 7
    assert response.text.endswith("data: [DONE]\n\n")


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
        ("unknown", 502),
    ],
)
async def test_early_upstream_errors_keep_http_status(config, stream, code, status):
    app = application(
        config, [TurnEvent("done", reason="error", code=code, error="upstream failure")]
    )
    async with client(app) as http:
        response = await http.post("/v1/chat/completions", json={**BODY, "stream": stream})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    if status in {429, 401, 403}:
        assert app.state.pool.size() == 0


async def test_midstream_error_and_terminal_marker(config):
    app = application(
        config,
        [
            TurnEvent("text", delta="partial"),
            TurnEvent("done", reason="error", error="failure", code="unavailable"),
        ],
    )
    async with client(app) as http:
        response = await http.post("/v1/chat/completions", json={**BODY, "stream": True})
    assert response.status_code == 200
    assert '"code":"unavailable"' in response.text
    assert response.text.endswith("data: [DONE]\n\n")


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"messages": []},
        {"messages": [None]},
        {"messages": [{"role": []}]},
        {"messages": [{"role": "user", "content": [{"type": {}}]}]},
        {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {}}]}]},
        {**BODY, "tools": None},
        {**BODY, "stream": "yes"},
        {**BODY, "tool_choice": "required"},
        {**BODY, "n": 2},
        {**BODY, "model": {}},
    ],
)
async def test_validation_is_openai_400(config, body):
    async with client(application(config, [])) as http:
        response = await http.post("/v1/chat/completions", content=json.dumps(body))
    assert response.status_code == 400
    assert "message" in response.json()["error"]


async def test_body_limit_and_invalid_json(config):
    async with client(application(replace(config, max_body_bytes=10), [])) as http:
        response = await http.post("/v1/chat/completions", content=b"x" * 11)
        assert response.status_code == 413
        response = await http.post("/v1/chat/completions", content=b"{bad")
        assert response.status_code == 400


@pytest.mark.parametrize("stream,emit_first", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("path", ["/v1/chat/completions", "/v1/responses"])
async def test_disconnect_cancels_upstream_before_and_after_headers(
    config, stream, emit_first, path, caplog
):
    caplog.set_level(logging.INFO, logger="cursor_gateway.requests")
    started, closed = asyncio.Event(), asyncio.Event()

    async def runner(**kwargs):
        try:
            started.set()
            if emit_first:
                yield TurnEvent("text", delta="hello")
            await asyncio.Event().wait()
        finally:
            closed.set()

    app = create_app(config, catalog=Catalog(), runner=runner)
    incoming = asyncio.Queue()
    await incoming.put(
        {
            "type": "http.request",
            "body": json.dumps({**BODY, "input": "hi", "stream": stream}).encode(),
            "more_body": False,
        }
    )
    sent = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "http_version": "1.1",
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 1234),
    }
    task = asyncio.create_task(app(scope, incoming.get, send))
    async with asyncio.timeout(2):
        await started.wait()
        await incoming.put({"type": "http.disconnect"})
        await task
        await closed.wait()
    records = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "cursor_gateway.requests"
    ]
    assert records[-1]["event"] == "request_finished"
    assert records[-1]["outcome"] == "disconnected"
    assert len({record["request_id"] for record in records}) == 1
