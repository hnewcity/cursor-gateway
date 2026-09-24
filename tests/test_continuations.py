"""A tool boundary must suspend the model, not reset its unobservable work state."""

import asyncio
from dataclasses import replace

import httpx
import pytest

from cursor_gateway.auth import Account, write_accounts
from cursor_gateway.config import Config
from cursor_gateway.continuations import history_digest
from cursor_gateway.server import create_app
from cursor_gateway.session import TurnEvent

TOOLS = [{"type": "function", "name": "read", "parameters": {"type": "object"}}]
BODY = {"model": "default", "tools": TOOLS, "input": "Finish the original task.", "store": False}


class Protocol:
    def __init__(self):
        self.runs = []
        self.results = []
        self.closed = 0
        self.mode = "tools"
        self.parallel = False
        self.delay = 0
        self.started = asyncio.Event()
        self.fail_on_resume = False
        self.text_before_failure = False

    async def run(self, token, model, turn, config, tool_exchange=None):
        self.runs.append((token, model, turn))
        self.started.set()
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.mode == "tools":
                yield TurnEvent("thinking", delta="Remember the hidden native work state.")
                yield TurnEvent("text", delta="Checking the original task.")
                for step in range(3):
                    ids = (
                        [f"call_{step}_a", f"call_{step}_b"] if self.parallel else [f"call_{step}"]
                    )
                    for call_id in ids:
                        yield TurnEvent("tool_call", name="read", id=call_id, args={"step": step})
                    yield TurnEvent("done", reason="tool_calls")
                    if tool_exchange is None:
                        return
                    self.results.append(await tool_exchange(tuple(ids)))
                    if self.fail_on_resume:
                        if self.text_before_failure:
                            yield TurnEvent("text", delta="Partial new output.")
                        raise OSError("upstream closed while the tool was running")
            yield TurnEvent("text", delta="Finished from the original native work state.")
            yield TurnEvent("done")
        finally:
            self.closed += 1


@pytest.fixture
def protocol(monkeypatch):
    value = Protocol()
    monkeypatch.setattr("cursor_gateway.continuations._run_protocol", value.run)
    monkeypatch.setattr("cursor_gateway.session._run_protocol", value.run)
    return value


@pytest.fixture
def config(tmp_path):
    file = tmp_path / "accounts.json"
    write_accounts(file, [Account("one", "secret-one"), Account("two", "secret-two")])
    return Config(auth_file=file)


def application(config):
    class Catalog:
        async def list_ids(self, token):
            return ["default"]

    return create_app(config, catalog=Catalog())


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


def continuation(body, response, *, result="unchanged evidence"):
    history = body["input"]
    if isinstance(history, str):
        history = [{"role": "user", "content": history}]
    calls = [item for item in response["output"] if item["type"] == "function_call"]
    return {
        **body,
        "input": [
            *history,
            *response["output"],
            *[
                {"type": "function_call_output", "call_id": c["call_id"], "output": result}
                for c in calls
            ],
        ],
    }


@pytest.mark.parametrize("parallel", [False, True])
async def test_three_tool_rounds_keep_native_state_and_account(config, protocol, parallel):
    protocol.parallel = parallel
    app = application(config)
    body = {**BODY, "parallel_tool_calls": parallel}
    async with client(app) as http:
        for step in range(3):
            result = await http.post("/v1/responses", json=body)
            assert result.status_code == 200
            response = result.json()
            calls = [i for i in response["output"] if i["type"] == "function_call"]
            assert calls[0]["arguments"] == f'{{"step":{step}}}'
            assert len(app.state.continuations.waiting) == 1
            body = continuation(body, response, result=str(step))
        result = await http.post("/v1/responses", json=body)
        final = result.json()["output"][-1]
        assert final["phase"] == "final_answer"
        assert "Finished" in final["content"][0]["text"]
    assert len(protocol.runs) == 1
    assert protocol.runs[0][0] == "secret-one"
    assert [list(r.values()) for r in protocol.results] == (
        [["0", "0"], ["1", "1"], ["2", "2"]] if parallel else [["0"], ["1"], ["2"]]
    )
    assert not app.state.continuations.live
    assert protocol.closed == 1
    # Execution state must not make a store=false response retrievable.
    async with client(app) as http:
        assert (await http.get("/v1/responses/" + response["id"])).status_code == 404


@pytest.mark.parametrize("change", ["instructions", "tools", "history", "new_user", "reasoning"])
async def test_changed_context_cannot_consume_a_pending_native_run(config, protocol, change):
    app = application(config)
    try:
        async with client(app) as http:
            response = (await http.post("/v1/responses", json=BODY)).json()
            body = continuation(BODY, response)
            if change == "history":
                body["input"][0] = {"role": "user", "content": "A different task."}
            elif change == "new_user":
                body["input"].append(
                    {"role": "user", "content": "Stop and answer my new question."}
                )
            else:
                body[change] = {
                    "instructions": "New instructions.",
                    "tools": [{"type": "function", "name": "new_tool"}],
                    "reasoning": {"effort": "high"},
                }[change]
            protocol.mode = "final"
            result = await http.post("/v1/responses", json=body)
            assert result.status_code == 200
            assert len(protocol.runs) == 2
            assert not protocol.results
    finally:
        await app.state.continuations.close()
    assert not app.state.continuations.live


async def test_parallel_batch_is_not_partially_delivered(config, protocol):
    protocol.parallel = True
    app = application(config)
    try:
        async with client(app) as http:
            response = (await http.post("/v1/responses", json=BODY)).json()
            body = continuation(BODY, response)
            body["input"].pop()
            protocol.mode = "final"
            assert (await http.post("/v1/responses", json=body)).status_code == 200
        assert not protocol.results
        assert len(protocol.runs) == 2
    finally:
        await app.state.continuations.close()


async def test_expired_wait_closes_native_run_and_full_history_can_resume(config, protocol):
    app = application(replace(config, session_keepalive_seconds=0.02))
    async with client(app) as http:
        response = (await http.post("/v1/responses", json=BODY)).json()
        (session,) = app.state.continuations.live
        await asyncio.wait_for(session.task, 1)
        assert not app.state.continuations.live
        assert not app.state.continuations.waiting
        protocol.mode = "final"
        result = await http.post("/v1/responses", json=continuation(BODY, response))
        assert result.status_code == 200
    assert len(protocol.runs) == 2
    assert not protocol.results


async def test_capacity_evicts_waiting_runs_and_shutdown_closes_the_rest(config, protocol):
    app = application(replace(config, session_max_entries=1))
    async with client(app) as http:
        assert (await http.post("/v1/responses", json=BODY)).status_code == 200
        first = next(iter(app.state.continuations.live))
        assert (
            await http.post("/v1/responses", json={**BODY, "input": "Other task"})
        ).status_code == 200
        assert first.task.done()
        assert len(app.state.continuations.live) == 1
    await app.state.continuations.close()
    assert protocol.closed == 2
    assert not app.state.continuations.live


async def test_generation_timeout_does_not_leave_a_native_session(config, protocol):
    protocol.delay = 1
    app = application(replace(config, request_timeout_ms=20))
    async with client(app) as http:
        response = await http.post("/v1/responses", json=BODY)
        assert response.status_code == 504
    assert protocol.closed == 1
    assert not app.state.continuations.live


async def test_client_cancellation_stops_active_generation(config, protocol):
    protocol.delay = 10
    app = application(config)
    async with client(app) as http:
        task = asyncio.create_task(http.post("/v1/responses", json=BODY))
        async with asyncio.timeout(1):
            await protocol.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert protocol.closed == 1
    assert not app.state.continuations.live


async def test_failed_response_delivery_cannot_leave_a_resumable_run(config, protocol):
    app = application(config)

    async def send(message):
        if message["type"] == "http.response.body":
            raise OSError("client socket closed")

    import json

    body = json.dumps(BODY).encode()
    incoming = asyncio.Queue()
    incoming.put_nowait({"type": "http.request", "body": body, "more_body": False})
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/responses",
        "raw_path": b"/v1/responses",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    with pytest.raises(OSError, match="client socket closed"):
        await app(scope, incoming.get, send)
    assert protocol.closed == 1
    assert not app.state.continuations.live
    assert not app.state.continuations.waiting


async def test_same_result_history_has_only_one_native_consumer(config, protocol):
    app = application(config)
    try:
        async with client(app) as http:
            first = (await http.post("/v1/responses", json=BODY)).json()
            body = continuation(BODY, first)
            await http.post("/v1/responses", json=body)
            # Replaying the same HTTP request must not feed a second result into
            # the native run that is already waiting for its next, different call.
            protocol.mode = "final"
            await http.post("/v1/responses", json=body)
        assert len(protocol.results) == 1
        assert len(protocol.runs) == 2
    finally:
        await app.state.continuations.close()


@pytest.mark.parametrize("partial_output", [False, True])
async def test_dead_upstream_replays_once_only_before_new_output(config, protocol, partial_output):
    app = application(config)
    protocol.fail_on_resume = True
    protocol.text_before_failure = partial_output
    async with client(app) as http:
        first = (await http.post("/v1/responses", json=BODY)).json()
        protocol.mode = "final"
        result = await http.post("/v1/responses", json=continuation(BODY, first))
        assert result.status_code == (502 if partial_output else 200)
        assert len(protocol.runs) == (1 if partial_output else 2)
    assert not app.state.continuations.live


def test_history_fingerprint_ignores_transport_ids_but_preserves_evidence_and_phase():
    item = {
        "id": "generated",
        "type": "message",
        "role": "assistant",
        "phase": "commentary",
        "status": "completed",
        "content": [{"type": "output_text", "text": "Verified", "annotations": [], "logprobs": []}],
    }
    equivalent = {
        **item,
        "id": "client-generated",
        "status": "in_progress",
        "content": [{"type": "output_text", "text": "Verified"}],
    }
    assert history_digest([item]) == history_digest([equivalent])
    assert history_digest([item]) != history_digest([{**equivalent, "phase": "final_answer"}])
    changed = {**equivalent, "content": [{"type": "output_text", "text": "Not verified"}]}
    assert history_digest([item]) != history_digest([changed])
