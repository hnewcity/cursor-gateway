"""Request/error diagnostics, redaction, streaming and concurrent correlation."""

import asyncio
import json
import logging
from dataclasses import replace

import httpx
import pytest

from cursor_gateway.auth import Account, write_accounts
from cursor_gateway.config import Config
from cursor_gateway.diagnostics import current_request
from cursor_gateway.server import create_app
from cursor_gateway.session import TurnEvent

LOGGER = "cursor_gateway.requests"
BODY = {"model": "cursor-auto", "input": "private user prompt"}


class Catalog:
    async def list_ids(self, token):
        return ["auto"]


@pytest.fixture
def config(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    file = tmp_path / "accounts.json"
    write_accounts(file, [Account("test", "private-access-token")])
    return Config(auth_file=file)


def application(config, events=()):
    async def runner(**kwargs):
        for item in events:
            yield item

    return create_app(config, catalog=Catalog(), runner=runner)


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


def logs(caplog, event=None):
    records = [
        json.loads(record.getMessage()) for record in caplog.records if record.name == LOGGER
    ]
    return [record for record in records if event is None or record["event"] == event]


@pytest.mark.parametrize(
    "extra,param",
    [
        ({"include": ["unsupported.field"]}, "include"),
        ({"tool_choice": "required"}, "tool_choice"),
        ({"tools": [{"type": "file_search"}]}, "tools[0]"),
        ({"text": {"format": {"type": "json_schema"}}}, "text.format.schema"),
        ({"stream_options": {"include_usage": True}}, "stream_options"),
        (
            {"input": [{"type": "function_call_output", "call_id": "x", "output": "secret"}]},
            "input[0].call_id",
        ),
    ],
)
async def test_validation_error_explains_failure_and_correlates_response(
    config, caplog, extra, param
):
    async with client(application(config)) as http:
        response = await http.post(
            "/v1/responses",
            json={**BODY, **extra},
            headers={"user-agent": "diagnostic-test/1"},
        )
    assert response.status_code == 400
    (error,) = logs(caplog, "request_error")
    assert error["stage"] == "validation"
    assert error["error_param"] == param
    assert error["error_message"] == response.json()["error"]["message"]
    assert error["model"] == "cursor-auto"
    assert error["path"] == "/v1/responses"
    assert {entry["request_id"] for entry in logs(caplog)} == {response.headers["x-request-id"]}
    assert logs(caplog, "request_started")[0]["user_agent"] == "diagnostic-test/1"
    finished = logs(caplog, "request_finished")[0]
    assert finished["outcome"] == "error"
    assert finished["status"] == 400
    assert finished["request_bytes"] == len(response.request.content)
    assert finished["response_bytes"] == len(response.content)
    assert finished["duration_ms"] >= 0
    assert "private user prompt" not in caplog.text
    assert "generation_started" not in caplog.text
    assert current_request.get() is None


@pytest.mark.parametrize("body", [b'{\n "input": }', b'{"input":NaN}', b"\xff"])
async def test_invalid_json_has_safe_parse_diagnostics(config, caplog, body):
    async with client(application(config)) as http:
        response = await http.post("/v1/responses", content=body)
    assert response.status_code == 400
    (error,) = logs(caplog, "request_error")
    assert error["stage"] == "body"
    assert error["error_message"] == "bad JSON body"
    if body.startswith(b"{\n"):
        assert error["line"] == 2
        assert error["column"] == 11
        assert error["offset"] == 12


async def test_body_limit_and_auth_rejection_do_not_parse_or_dump_body(config, caplog):
    async with client(application(replace(config, max_body_bytes=10))) as http:
        response = await http.post("/v1/responses", content=b"private secret body")
    assert response.status_code == 413
    assert logs(caplog, "request_error")[0]["stage"] == "body"
    assert not logs(caplog, "request_parsed")
    caplog.clear()
    async with client(application(replace(config, api_key="private-gateway-key"))) as http:
        response = await http.post(
            "/v1/responses",
            content=b"private secret body",
            headers={
                "authorization": "Bearer private-invalid-credential",
                "cookie": "session=private-cookie",
                "x-api-key": "private-other-key",
            },
        )
    assert response.status_code == 401
    assert logs(caplog, "request_error")[0]["stage"] == "authentication"
    assert not logs(caplog, "request_parsed")
    assert logs(caplog, "request_finished")[0]["request_bytes"] == 0
    for secret in (
        "private secret body",
        "private-invalid-credential",
        "private-cookie",
        "private-other-key",
        "private-gateway-key",
    ):
        assert secret not in caplog.text


async def test_query_validation_reports_location_but_omits_input(config, caplog):
    async with client(application(config)) as http:
        response = await http.get(
            "/v1/responses/resp_x/input_items?limit=private-invalid-value&api_key=private-key"
        )
    assert response.status_code == 400
    (error,) = logs(caplog, "request_error")
    assert error["validation_errors"] == [{"location": ["query", "limit"], "type": "int_parsing"}]
    assert "private-invalid-value" not in json.dumps(logs(caplog))
    assert "private-key" not in json.dumps(logs(caplog))


@pytest.mark.parametrize("path", ["/v1/responses", "/v1/chat/completions"])
@pytest.mark.parametrize("mode", ["json", "early_sse", "late_sse"])
async def test_upstream_error_before_and_after_headers(config, caplog, path, mode):
    events = [] if mode != "late_sse" else [TurnEvent("text", delta="private output")]
    events.append(
        TurnEvent(
            "done",
            reason="error",
            code="invalid_argument",
            error="model unavailable; private-access-token",
        )
    )
    body = {
        **BODY,
        "stream": mode != "json",
        "messages": [{"role": "user", "content": "private user prompt"}],
    }
    async with client(application(config, events)) as http:
        response = await http.post(path, json=body)
    assert response.status_code == (200 if mode == "late_sse" else 400)
    (error,) = logs(caplog, "request_error")
    assert error["stage"] == "upstream"
    assert error["error_code"] == "invalid_argument"
    assert error["stream_started"] == (mode == "late_sse")
    assert error["error_message"] == "model unavailable; [REDACTED]"
    (finished,) = logs(caplog, "request_finished")
    assert finished["status"] == response.status_code
    assert finished["outcome"] == "error"
    assert finished["request_id"] == response.headers["x-request-id"]
    assert "private output" not in caplog.text
    assert "private-access-token" not in caplog.text
    assert "private user prompt" not in caplog.text


async def test_unexpected_error_includes_safe_frame_locations(config, caplog):
    async def runner(**kwargs):
        raise RuntimeError(
            "connection failed private-access-token Bearer private-bearer "
            "refresh_token=private-refresh socks5://private-user:private-pass@proxy:1080"
        )
        yield  # pragma: no cover

    app = create_app(config, catalog=Catalog(), runner=runner)
    async with client(app) as http:
        response = await http.post("/v1/responses", json=BODY)
    assert response.status_code == 502
    (error,) = logs(caplog, "request_error")
    assert error["exception_type"] == "RuntimeError"
    assert error["frames"][-1]["function"] == "runner"
    assert error["frames"][-1]["line"] > 0
    assert "connection failed" in error["error_message"]
    for secret in (
        "private-access-token",
        "private-bearer",
        "private-refresh",
        "private-user",
        "private-pass",
    ):
        assert secret not in caplog.text
    assert "connection failed" not in response.text


async def test_logging_off_retains_failure_diagnostics(config, caplog):
    events = [TurnEvent("text", delta="ok"), TurnEvent("done")]
    async with client(application(replace(config, log_requests=False), events)) as http:
        response = await http.post("/v1/responses", json=BODY)
        assert response.headers["x-request-id"]
        assert logs(caplog) == []
        response = await http.post("/v1/responses", json={**BODY, "tool_choice": "required"})
    assert response.status_code == 400
    assert {item["event"] for item in logs(caplog)} == {"request_error", "request_finished"}
    assert logs(caplog, "request_error")[0]["error_param"] == "tool_choice"


async def test_concurrent_requests_keep_independent_models_and_ids(config, caplog):
    ready = asyncio.Event()
    count = 0

    async def runner(**kwargs):
        nonlocal count
        count += 1
        if count == 2:
            ready.set()
        await ready.wait()
        yield TurnEvent("text", delta="ok")
        yield TurnEvent("done")

    app = create_app(config, catalog=Catalog(), runner=runner)
    async with client(app) as http:
        async with asyncio.timeout(2):
            responses = await asyncio.gather(
                *(
                    http.post("/v1/responses", json={**BODY, "model": model})
                    for model in ("cursor-first", "cursor-second")
                )
            )
    assert len({response.headers["x-request-id"] for response in responses}) == 2
    for response, model in zip(responses, ("cursor-first", "cursor-second"), strict=True):
        records = [
            item for item in logs(caplog) if item["request_id"] == response.headers["x-request-id"]
        ]
        assert all(item.get("model", model) == model for item in records)
        assert records[-1]["outcome"] == "completed"
    assert current_request.get() is None


async def test_summary_omits_content_and_bounds_adversarial_shapes(config, caplog):
    parts = [{"type": "a" * 150 + str(i), "text": "private content"} for i in range(32)]
    body = {
        **BODY,
        "input": [{"role": "user", "content": parts} for _ in range(64)],
        "instructions": "private instructions",
        "metadata": {"secret": "private metadata"},
        "tools": [
            {
                "type": "function",
                "name": "private tool name",
                "description": "private description",
                "parameters": {"type": "object", "default": "private schema"},
            }
        ],
    }
    async with client(application(config)) as http:
        response = await http.post("/v1/responses", json=body)
    assert response.status_code == 400
    (parsed,) = logs(caplog, "request_parsed")
    assert parsed["summary_truncated"] is True
    assert parsed["input"]["count"] == 64
    for record in logs(caplog):
        assert len(json.dumps(record)) < 16000
    for secret in (
        "private content",
        "private instructions",
        "private metadata",
        "private description",
        "private schema",
        "private tool name",
    ):
        assert secret not in caplog.text


async def test_long_credentials_redacted_before_truncation_and_log_lines_escaped(config, caplog):
    secret = "private-gateway-" + "secret" * 60
    body = {**BODY, "model": secret, "tool_choice": "invalid\nforged log"}
    async with client(application(replace(config, api_key=secret))) as http:
        response = await http.post(
            "/v1/responses",
            json=body,
            headers={"authorization": "Bearer " + secret, "user-agent": secret},
        )
    assert response.status_code == 400
    assert secret[:100] not in caplog.text
    assert logs(caplog, "request_parsed")[0]["model"] == "[REDACTED]"
    assert all(
        "\n" not in record.getMessage() for record in caplog.records if record.name == LOGGER
    )
