"""Exercise real TCP + HTTP/2 + Connect + protobuf, without using paid credentials."""

import asyncio
import base64
import contextlib
import gzip
import hashlib
import json
import shutil
import ssl
import subprocess
from contextlib import asynccontextmanager
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import h2.config
import h2.connection
import h2.events
import httpx
import pytest
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value
from openai import AsyncOpenAI

from cursor_gateway.auth import Account, exchange_refresh_token, write_accounts
from cursor_gateway.cli import login
from cursor_gateway.config import Config
from cursor_gateway.models import ModelCatalog
from cursor_gateway.proto import agent_pb2 as pb
from cursor_gateway.protocol import FrameDecoder, connect_frame, json_bytes
from cursor_gateway.server import create_app
from cursor_gateway.session import run_turn
from cursor_gateway.translate import TurnInput
from cursor_gateway.transport import h2_request

PATCH_FORMAT = {
    "type": "grammar",
    "syntax": "lark",
    "definition": 'begin_patch: "*** Begin Patch" LF\nend_patch: "*** End Patch" LF?',
}
PATCH = "*** Begin Patch\n*** Add File: hello.txt\n+hello\n*** End Patch"


class Upstream:
    def __init__(self, mode="text"):
        self.mode = mode
        self.headers = []
        self.runs = []
        self.histories = []
        self.contexts = []
        self.closed = asyncio.Event()
        self.started = asyncio.Event()
        self.errors = []
        self.connections = set()
        self.tasks = set()
        self.unary_calls = 0
        self.interactions = []
        self.mcp_rejections = []
        self.mcp_results = []

    async def connection(self, reader, writer):
        self.connections.add(writer)
        self.tasks.add(asyncio.current_task())
        connection = h2.connection.H2Connection(
            config=h2.config.H2Configuration(client_side=False, header_encoding="utf-8"),
        )
        connection.initiate_connection()
        writer.write(connection.data_to_send())
        frame_decoder, raw_body = FrameDecoder(), bytearray()
        path, ready, answered, roots, pending, delivered = "", False, False, [], {}, False

        def emit(payload, *, end=False):
            # Deliberately fragment Connect envelopes across HTTP/2 DATA frames.
            for start in range(0, len(payload), 127):
                end_stream = end and start + 127 >= len(payload)
                connection.send_data(1, payload[start : start + 127], end_stream=end_stream)

        def message(value, *, compressed=False):
            payload = value.SerializeToString()
            emit(connect_frame(gzip.compress(payload) if compressed else payload, int(compressed)))

        def patch_call(valid, attempt):
            value = PATCH if valid else PATCH.replace("*** Begin Patch", "*** Begin Patch ***")
            message(
                pb.AgentServerMessage(
                    exec_server_message=pb.ExecServerMessage(
                        id=50 + attempt,
                        exec_id=f"patch-exec-{attempt}",
                        mcp_args=pb.McpArgs(
                            name="patch",
                            args={
                                "input": json_format.ParseDict(value, Value()).SerializeToString()
                            },
                            tool_call_id=f"patch-{attempt}",
                        ),
                    )
                )
            )

        def respond():
            nonlocal delivered
            delivered = True
            self.histories.append([json.loads(pending[key]) for key in roots])
            if self.mode == "stall":
                return
            if self.mode == "trailer-error":
                emit(
                    connect_frame(
                        json_bytes(
                            {
                                "error": {
                                    "code": "resource_exhausted",
                                    "message": "quota exhausted",
                                },
                            }
                        ),
                        2,
                    ),
                    end=True,
                )
                return
            if self.mode == "truncated":
                emit(b"\x00\x00", end=True)
                return
            if self.mode == "empty-end":
                emit(connect_frame(b"{}", 2), end=True)
                return
            if self.mode == "search":
                message(
                    pb.AgentServerMessage(
                        interaction_query=pb.InteractionQuery(
                            id=37,
                            web_search_request_query=pb.WebSearchRequestQuery(
                                args=pb.WebSearchArgs(search_term="Python TaskGroup")
                            ),
                        )
                    )
                )
                return
            if self.mode in ("patch-repair", "patch-invalid"):
                patch_call(False, 0)
                return
            if self.mode in ("tool", "parallel-tools", "parallel-invalid"):
                args = {
                    "city": json_format.ParseDict("北京", Value()).SerializeToString(),
                    "options": json_format.ParseDict(
                        {"days": [1, 2], "metric": True},
                        Value(),
                    ).SerializeToString(),
                }
                message(
                    pb.AgentServerMessage(
                        exec_server_message=pb.ExecServerMessage(
                            id=42,
                            mcp_args=pb.McpArgs(
                                name="weather",
                                args=args,
                                tool_call_id="call-a\nfc_b",
                            ),
                        )
                    )
                )
                if self.mode == "parallel-tools":
                    message(
                        pb.AgentServerMessage(
                            exec_server_message=pb.ExecServerMessage(
                                id=43,
                                mcp_args=pb.McpArgs(
                                    name="weather", args=args, tool_call_id="call-second"
                                ),
                            )
                        )
                    )
                if self.mode == "parallel-invalid":
                    patch_call(False, 0)
                return
            message(
                pb.AgentServerMessage(
                    interaction_update=pb.InteractionUpdate(
                        thinking_delta=pb.ThinkingDeltaUpdate(text="thinking"),
                    )
                ),
                compressed=True,
            )
            message(
                pb.AgentServerMessage(
                    interaction_update=pb.InteractionUpdate(
                        text_delta=pb.TextDeltaUpdate(text="你好"),
                    )
                )
            )
            message(
                pb.AgentServerMessage(
                    interaction_update=pb.InteractionUpdate(
                        token_delta=pb.TokenDeltaUpdate(tokens=12),
                    )
                )
            )
            message(
                pb.AgentServerMessage(
                    interaction_update=pb.InteractionUpdate(
                        turn_ended=pb.TurnEndedUpdate(),
                    )
                )
            )
            emit(connect_frame(b"{}", 2), end=True)

        try:
            while data := await reader.read(65536):
                for event in connection.receive_data(data):
                    if isinstance(event, h2.events.RequestReceived):
                        headers = dict(event.headers)
                        self.headers.append(headers)
                        path = headers[":path"]
                        status = "429" if self.mode == "http-error" else "200"
                        connection.send_headers(
                            1,
                            [
                                (":status", status),
                                ("content-type", headers.get("content-type", "application/json")),
                            ],
                        )
                        if status != "200":
                            connection.end_stream(1)
                    elif isinstance(event, h2.events.DataReceived):
                        connection.acknowledge_received_data(event.flow_controlled_length, 1)
                        if self.mode == "http-error":
                            continue
                        if path != "/agent.v1.AgentService/Run":
                            raw_body.extend(event.data)
                            continue
                        for frame in frame_decoder.feed(event.data):
                            client = pb.AgentClientMessage.FromString(frame.payload)
                            operation = client.WhichOneof("message")
                            if operation == "run_request":
                                self.runs.append(client.run_request)
                                self.started.set()
                                roots = list(
                                    client.run_request.conversation_state.root_prompt_messages_json,
                                )
                                for index, blob_id in enumerate(roots):
                                    message(
                                        pb.AgentServerMessage(
                                            kv_server_message=pb.KvServerMessage(
                                                id=index + 1,
                                                get_blob_args=pb.GetBlobArgs(blob_id=blob_id),
                                            )
                                        )
                                    )
                                # Also exercise server-created blobs and the acknowledgement.
                                message(
                                    pb.AgentServerMessage(
                                        kv_server_message=pb.KvServerMessage(
                                            id=900,
                                            set_blob_args=pb.SetBlobArgs(
                                                blob_id=b"server-blob",
                                                blob_data=b"server state",
                                            ),
                                        )
                                    )
                                )
                                message(
                                    pb.AgentServerMessage(
                                        exec_server_message=pb.ExecServerMessage(
                                            id=901,
                                            exec_id="context-exec",
                                            request_context_args=pb.RequestContextArgs(),
                                        )
                                    )
                                )
                            elif operation == "kv_client_message":
                                kv = client.kv_client_message
                                if kv.WhichOneof("message") == "get_blob_result":
                                    blob = kv.get_blob_result.blob_data
                                    assert hashlib.sha256(blob).digest() == roots[kv.id - 1]
                                    pending[roots[kv.id - 1]] = blob
                                elif kv.id == 900:
                                    assert kv.WhichOneof("message") == "set_blob_result"
                                    answered = True
                            elif operation == "interaction_response":
                                reply = client.interaction_response
                                self.interactions.append(reply)
                                assert reply.id == 37
                                if (
                                    reply.web_search_request_response.WhichOneof("result")
                                    == "approved"
                                ):
                                    message(
                                        pb.AgentServerMessage(
                                            interaction_update=pb.InteractionUpdate(
                                                tool_call_completed=pb.ToolCallCompletedUpdate(
                                                    call_id="search_37",
                                                    tool_call=pb.ToolCall(
                                                        web_search_tool_call=pb.WebSearchToolCall(
                                                            args=pb.WebSearchArgs(
                                                                search_term="Python TaskGroup"
                                                            ),
                                                            result=pb.WebSearchResult(
                                                                success=pb.WebSearchSuccess(
                                                                    references=[
                                                                        pb.WebSearchReference(
                                                                            title="Python docs",
                                                                            url="https://docs.python.org",
                                                                            chunk="TaskGroup docs",
                                                                        )
                                                                    ]
                                                                )
                                                            ),
                                                        )
                                                    ),
                                                )
                                            )
                                        )
                                    )
                                message(
                                    pb.AgentServerMessage(
                                        interaction_update=pb.InteractionUpdate(
                                            turn_ended=pb.TurnEndedUpdate()
                                        )
                                    )
                                )
                            elif operation == "exec_client_message":
                                reply = client.exec_client_message
                                if reply.WhichOneof("message") == "mcp_result":
                                    if reply.mcp_result.WhichOneof("result") == "success":
                                        self.mcp_results.append(reply)
                                        # Resume on the existing HTTP/2 connection after
                                        # the client supplies its result in a second request.
                                        respond()
                                        continue
                                    attempt = len(self.mcp_rejections)
                                    assert reply.id == 50 + attempt
                                    assert reply.exec_id == f"patch-exec-{attempt}"
                                    self.mcp_rejections.append(reply)
                                    patch_call(self.mode == "patch-repair", attempt + 1)
                                    continue
                                assert reply.id == 901 and reply.exec_id == "context-exec"
                                self.contexts.append(
                                    reply.request_context_result.success.request_context
                                )
                                ready = True
                            if (
                                ready
                                and answered
                                and len(pending) == len(set(roots))
                                and not delivered
                            ):
                                respond()
                    elif (
                        isinstance(event, h2.events.StreamEnded)
                        and path != "/agent.v1.AgentService/Run"
                    ):
                        self.unary_calls += 1
                        if path.startswith("/auth/poll") or path == "/auth/exchange_user_api_key":
                            if path == "/auth/exchange_user_api_key":
                                assert json.loads(raw_body) == {}
                            payload = json_bytes(
                                {
                                    "accessToken": "fake-login-token",
                                    "refreshToken": "fake-refresh",
                                    "authId": "provider|test-user",
                                }
                            )
                        else:
                            pb.GetUsableModelsRequest.FromString(raw_body)
                            payload = pb.GetUsableModelsResponse(
                                models=[
                                    pb.ModelDetails(model_id="auto"),
                                    pb.ModelDetails(model_id="cursor-grok"),
                                ],
                            ).SerializeToString()
                        emit(payload, end=True)
                    elif isinstance(event, (h2.events.StreamReset, h2.events.ConnectionTerminated)):
                        return
                writer.write(connection.data_to_send())
                await writer.drain()
        except ConnectionError, asyncio.CancelledError:
            pass
        except Exception as exc:
            self.errors.append(exc)
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            self.connections.discard(writer)
            self.tasks.discard(asyncio.current_task())
            self.closed.set()


@asynccontextmanager
async def upstream(mode="text", tls=None):
    state = Upstream(mode)
    server = await asyncio.start_server(state.connection, "127.0.0.1", 0, ssl=tls)
    port = server.sockets[0].getsockname()[1]
    origin = f"https://localhost:{port}" if tls else f"http://127.0.0.1:{port}"
    state.config = Config(cursor_base_url=origin, request_timeout_ms=2000)
    try:
        yield state
    finally:
        server.close()
        await server.wait_closed()
        for connection in list(state.connections):
            connection.close()
        if state.tasks:
            await asyncio.wait_for(asyncio.gather(*list(state.tasks)), 2)
        assert not state.errors, state.errors


async def collect(config, turn=None):
    return [
        event
        async for event in run_turn(
            token="fake-token",
            model="auto",
            config=config,
            turn=turn or TurnInput([], "hello", []),
        )
    ]


async def test_real_h2_bidi_history_context_compression_and_flow_control():
    # Far larger than the initial HTTP/2 stream window; requires WINDOW_UPDATE.
    history = {"role": "user", "content": [{"type": "text", "text": "历史" * 60_000}]}
    tool = pb.McpToolDefinition(
        name="weather", tool_name="weather", input_schema_json='{"type":"object"}'
    )
    async with upstream() as state:
        events = await collect(state.config, TurnInput([history], "active", [tool]))
        assert [(event.type, event.delta) for event in events[:2]] == [
            ("thinking", "thinking"),
            ("text", "你好"),
        ]
        assert events[-1].reason == "stop"
        assert events[-2].output_tokens == 12
        assert state.histories == [[history]]
        assert state.contexts[0].tools[0].name == "weather"
        assert state.contexts[0].env.time_zone == "UTC"
        assert state.runs[0].action.user_message_action.user_message.text == "active"
        assert state.headers[0]["x-cursor-agent-allowed-tools"] == "mcp_tool_call"
        assert state.headers[0]["content-type"] == "application/connect+proto"


async def test_tool_argument_value_decoding_and_safe_id():
    async with upstream("tool") as state:
        events = await collect(
            state.config,
            TurnInput(
                [],
                "weather",
                [
                    pb.McpToolDefinition(name="weather"),
                ],
            ),
        )
        assert events[0].type == "tool_call"
        assert events[0].id == "call-a_fc_b"
        assert events[0].args == {"city": "北京", "options": {"days": [1, 2], "metric": True}}
        assert events[-1].reason == "tool_calls"


async def test_undeclared_tool_is_not_exposed_to_caller():
    async with upstream("tool") as state:
        events = await collect(state.config)
        assert len(events) == 1
        assert events[0].reason == "error"
        assert "undeclared tool" in events[0].error


@pytest.mark.parametrize("parallel,expected", [(False, 1), (True, 2)])
async def test_parallel_mcp_dispatch_does_not_drop_batched_calls(parallel, expected):
    async with upstream("parallel-tools") as state:
        events = await collect(
            state.config,
            TurnInput(
                [], "weather", [pb.McpToolDefinition(name="weather")], parallel_tools=parallel
            ),
        )
        calls = [event for event in events if event.type == "tool_call"]
        assert len(calls) == expected
        assert len({call.id for call in calls}) == expected
        assert type(calls[0].args["options"]["days"][0]) is int
        assert events[-1].reason == "tool_calls"


@pytest.mark.parametrize("enabled", [False, True])
async def test_native_web_search_permission_and_results(enabled):
    async with upstream("search") as state:
        events = await collect(state.config, TurnInput([], "search", [], web_search=enabled))
        reply = state.interactions[0].web_search_request_response
        assert reply.WhichOneof("result") == ("approved" if enabled else "rejected")
        searches = [event for event in events if event.type == "web_search"]
        assert len(searches) == int(enabled)
        if enabled:
            assert searches[0].args["sources"] == [
                {"type": "url", "url": "https://docs.python.org"}
            ]
        assert state.contexts[0].web_search_enabled == enabled
        assert events[-1].reason == "stop"


@pytest.mark.parametrize(
    "mode,code",
    [
        ("http-error", "resource_exhausted"),
        ("trailer-error", "resource_exhausted"),
        ("stall", "deadline_exceeded"),
        ("truncated", None),
    ],
)
async def test_protocol_errors_are_not_silent_successes(mode, code):
    async with upstream(mode) as state:
        events = await collect(replace(state.config, request_timeout_ms=100))
        assert events[-1].reason == "error"
        assert events[-1].code == code
        await asyncio.wait_for(state.closed.wait(), 1)


async def test_consumer_cancellation_closes_h2_socket():
    async with upstream("stall") as state:
        task = asyncio.create_task(collect(state.config))
        await asyncio.wait_for(state.started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(state.closed.wait(), 1)


@pytest.mark.parametrize(
    ("mode", "retries"), [("patch-repair", 1), ("patch-invalid", 1), ("patch-invalid", 0)]
)
async def test_custom_input_repair_stays_in_the_original_cursor_run(mode, retries):
    async with upstream(mode) as state:
        turn = TurnInput(
            [],
            "Create hello.txt",
            [pb.McpToolDefinition(name="patch")],
            custom_tool_formats={"patch": PATCH_FORMAT},
        )
        events = [
            event
            async for event in run_turn(
                token="fake-token",
                model="auto",
                turn=turn,
                config=replace(state.config, tool_input_retries=retries),
            )
        ]
        assert len(state.runs) == 1
        assert len(state.mcp_rejections) == retries
        if retries:
            feedback = state.mcp_rejections[0].mcp_result.error.error
            assert "not executed" in feedback and "first line" in feedback
        calls = [event for event in events if event.type == "tool_call"]
        if mode == "patch-repair":
            assert len(calls) == 1
            assert calls[0].args == {"input": PATCH}
            assert events[-1].reason == "tool_calls"
        else:
            assert calls == []
            assert events[-1].reason == "error"
            assert events[-1].code == "tool_input_invalid"
        assert not state.errors


async def test_parallel_validation_preserves_already_dispatched_calls():
    async with upstream("parallel-invalid") as state:
        events = [
            event
            async for event in run_turn(
                token="fake-token",
                model="auto",
                turn=TurnInput(
                    [],
                    "Run tools",
                    [pb.McpToolDefinition(name="weather"), pb.McpToolDefinition(name="patch")],
                    parallel_tools=True,
                    custom_tool_formats={"patch": PATCH_FORMAT},
                ),
                config=state.config,
            )
        ]
        assert [event.name for event in events if event.type == "tool_call"] == ["weather", "patch"]
        assert events[-1].reason == "tool_calls"
        assert state.mcp_rejections == []
        assert not state.errors


async def test_unary_bare_protobuf_cache_and_account_isolation():
    async with upstream() as state:
        catalog = ModelCatalog(state.config)
        assert await catalog.list_ids("first") == ["auto", "cursor-grok"]
        assert await catalog.list_ids("first") == ["auto", "cursor-grok"]
        assert state.unary_calls == 1
        await catalog.list_ids("second")
        assert state.unary_calls == 2
        assert all(headers["content-type"] == "application/proto" for headers in state.headers)


@pytest.mark.parametrize(
    ("path", "stream"),
    [
        ("/v1/chat/completions", False),
        ("/v1/chat/completions", True),
        ("/v1/responses", False),
        ("/v1/responses", True),
        ("/v1/responses/compact", False),
    ],
)
@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (None, "auto"),
        ("auto", "auto"),
        ("cursor-auto", "auto"),
        ("grok", "cursor-grok"),
        ("cursor-grok", "cursor-grok"),
    ],
)
async def test_model_aliases_reach_real_h2_upstream(tmp_path, path, stream, model, expected):
    async with upstream() as state:
        file = tmp_path / "accounts.json"
        write_accounts(file, [Account("test", "fake-token")])
        app = create_app(replace(state.config, auth_file=file))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as http:
            listed = await http.get("/v1/models")
            assert [item["id"] for item in listed.json()["data"]] == ["auto", "grok"]
            body = {"stream": stream}
            if model is not None:
                body["model"] = model
            if path == "/v1/chat/completions":
                body["messages"] = [{"role": "user", "content": "hello"}]
            else:
                body["input"] = "hello"
            response = await http.post(path, json=body)
            assert response.status_code == 200, response.text
            if stream:
                events = [
                    json.loads(line.removeprefix("data: "))
                    for line in response.text.splitlines()
                    if line.startswith("data: ") and line != "data: [DONE]"
                ]
                returned = events[-1]["response"] if path == "/v1/responses" else events[-1]
                assert returned["model"] == (model or "auto")
            elif path == "/v1/responses/compact":
                assert response.json()["object"] == "response.compaction"
            else:
                assert response.json()["model"] == (model or "auto")
            assert len(state.runs) == 1
            assert state.runs[0].model_details.model_id == expected
            assert state.runs[0].requested_model.model_id == expected


async def test_end_to_end_api_and_stateless_tool_replay(tmp_path):
    async with upstream("tool") as state:
        file = tmp_path / "accounts.json"
        write_accounts(file, [Account("test", "fake-token")])
        app = create_app(replace(state.config, auth_file=file))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://test",
        ) as http:
            body = {
                "model": "cursor-auto",
                "messages": [{"role": "user", "content": "weather?"}],
                "tools": [{"type": "function", "function": {"name": "weather"}}],
            }
            response = await http.post("/v1/chat/completions", json=body)
            assert response.status_code == 200
            message = response.json()["choices"][0]["message"]
            assert message["tool_calls"][0]["id"] == "call-a_fc_b"
            state.mode = "text"
            body["messages"].extend(
                [
                    message,
                    {"role": "tool", "tool_call_id": "call-a_fc_b", "content": "sunny"},
                ]
            )
            response = await http.post("/v1/chat/completions", json={**body, "stream": True})
            assert response.status_code == 200 and "你好" in response.text
            assert state.runs[-1].action.user_message_action.user_message.text == (
                state.config.continuation_prompt
            )
            assert state.histories[-1][-1]["content"][0]["result"] == "sunny"
            assert state.histories[-1][-1]["content"][0]["toolName"] == "mcp_openai_weather"


@pytest.mark.parametrize("by_id", [False, True])
@pytest.mark.parametrize("reuse", [False, True])
async def test_responses_sdk_through_real_h2_tool_continuation(tmp_path, by_id, reuse):
    async with upstream("tool") as state:
        file = tmp_path / "accounts.json"
        write_accounts(file, [Account("test", "fake-token")])
        app = create_app(replace(state.config, auth_file=file, reuse_sessions=reuse))
        async with AsyncOpenAI(
            api_key="fake-key",
            base_url="http://test/v1",
            http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app)),
            _strict_response_validation=True,
            max_retries=0,
        ) as api:
            tools = [
                {
                    "type": "function",
                    "name": "weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                }
            ]
            first = await api.responses.create(
                model="cursor-auto",
                input="weather?",
                tools=tools,
                store=by_id,
            )
            assert first.status == "completed"
            call = first.output[0]
            assert call.call_id == "call-a_fc_b"
            assert json.loads(call.arguments) == {
                "city": "北京",
                "options": {"days": [1, 2], "metric": True},
            }
            tool_output = {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": "sunny",
            }
            state.mode = "text"
            params = {"model": "cursor-auto", "tools": tools}
            if by_id:
                params.update(previous_response_id=first.id, input=[tool_output])
            else:
                params["input"] = [
                    {"role": "user", "content": "weather?"},
                    call.model_dump(exclude_none=True),
                    tool_output,
                ]
            async with api.responses.stream(**params) as stream:
                events = [event async for event in stream]
                final = await stream.get_final_response()
            assert final.output_text == "你好"
            assert final.output[0].summary[0].text == "thinking"
            assert final.usage.output_tokens == 12
            assert events[-1].type == "response.completed"
            if reuse:
                assert len(state.runs) == 1
                assert state.runs[0].action.user_message_action.user_message.text == "weather?"
                assert len(state.mcp_results) == 1
                result = state.mcp_results[0]
                assert result.id == 42
                assert result.mcp_result.success.content[0].text.text == "sunny"
                assert not app.state.continuations.live
            else:
                assert len(state.runs) == 2
                assert state.runs[-1].action.user_message_action.user_message.text == (
                    state.config.continuation_prompt
                )
                assert state.histories[-1][-1]["content"][0]["toolName"] == "mcp_openai_weather"
                assert state.histories[-1][-1]["content"][0]["result"] == "sunny"
            assert state.contexts[-1].tools[0].name == "weather"
            assert all(h["authorization"] == "Bearer fake-token" for h in state.headers)


@asynccontextmanager
async def socks_proxy(destination, *, authenticated=False, reject=False):
    observed = []
    tasks = set()

    async def connection(reader, writer):
        tasks.add(asyncio.current_task())
        remote = None
        try:
            version, length = await reader.readexactly(2)
            assert version == 5
            methods = await reader.readexactly(length)
            assert (2 if authenticated else 0) in methods
            writer.write(b"\x05\x02" if authenticated else b"\x05\x00")
            await writer.drain()
            if authenticated:
                version, length = await reader.readexactly(2)
                username = await reader.readexactly(length)
                password = await reader.readexactly((await reader.readexactly(1))[0])
                assert version == 1 and username == b"user" and password == b"p@ss"
                writer.write(b"\x01\x00")
                await writer.drain()
            version, command, reserved, kind = await reader.readexactly(4)
            assert (version, command, reserved, kind) == (5, 1, 0, 3)
            host = await reader.readexactly((await reader.readexactly(1))[0])
            port = int.from_bytes(await reader.readexactly(2), "big")
            observed.append((host, port))
            if reject:
                writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                return
            remote_reader, remote = await asyncio.open_connection("127.0.0.1", destination)
            # Fragment the SOCKS reply too.
            for chunk in (b"\x05", b"\x00\x00\x01", b"\x00\x00\x00\x00\x00\x00"):
                writer.write(chunk)
                await writer.drain()

            async def relay(source, target):
                while data := await source.read(65536):
                    target.write(data)
                    await target.drain()
                target.close()

            await asyncio.gather(relay(reader, remote), relay(remote_reader, writer))
        except ConnectionError, asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            if remote:
                remote.close()
            tasks.discard(asyncio.current_task())

    server = await asyncio.start_server(connection, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        credentials = "user:p%40ss@" if authenticated else ""
        yield f"socks5://{credentials}127.0.0.1:{port}", observed
    finally:
        server.close()
        await server.wait_closed()
        if tasks:
            await asyncio.wait_for(asyncio.gather(*list(tasks)), 2)


@pytest.mark.parametrize("authenticated", [False, True])
async def test_socks_remote_dns_and_optional_auth(authenticated):
    async with upstream() as state:
        destination = int(state.config.cursor_base_url.rsplit(":", 1)[-1])
        async with socks_proxy(destination, authenticated=authenticated) as (proxy, observed):
            # This hostname does not resolve locally. The proxy routes it to our server.
            config = replace(
                state.config,
                cursor_base_url="http://cursor.invalid:8080",
                proxy_url=proxy,
            )
            assert (await collect(config))[-1].reason == "stop"
            response = await h2_request(
                config.cursor_base_url,
                "/agent.v1.AgentService/GetUsableModels",
                proxy_url=proxy,
            )
            assert response.status == 200
            assert observed == [(b"cursor.invalid", 8080)] * 2


@pytest.fixture
def tls_context(tmp_path, monkeypatch):
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl is required to generate the temporary localhost test certificate")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    context.set_alpn_protocols(["h2"])
    return context


async def test_direct_tls_and_tls_over_socks(tls_context):
    async with upstream(tls=tls_context) as state:
        assert (await collect(state.config))[-1].reason == "stop"
        destination = urlsplit(state.config.cursor_base_url).port
        async with socks_proxy(destination) as (proxy, observed):
            assert (await collect(replace(state.config, proxy_url=proxy)))[-1].reason == "stop"
            assert observed == [(b"localhost", destination)]


async def test_alpn_rejects_http1(tls_context):
    tls_context.set_alpn_protocols(["http/1.1"])
    async with upstream(tls=tls_context) as state:
        events = await collect(state.config)
        assert events[-1].reason == "error"
        assert "ALPN" in events[-1].error


async def test_login_pkce_poll_and_refresh_over_socks(capsys):
    async with upstream() as state:
        destination = urlsplit(state.config.cursor_base_url).port
        async with socks_proxy(destination) as (proxy, observed):
            config = replace(
                state.config, cursor_base_url="http://cursor.invalid:8080", proxy_url=proxy
            )
            account = await login(config, timeout=2)
            assert account.access_token == "fake-login-token"
            assert account.refresh_token == "fake-refresh"
            assert account.label == "test-user"
            output = capsys.readouterr().out
            url = next(
                line.strip() for line in output.splitlines() if line.strip().startswith("https:")
            )
            login_params = parse_qs(urlsplit(url).query)
            poll_params = parse_qs(urlsplit(state.headers[0][":path"]).query)
            challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(poll_params["verifier"][0].encode()).digest(),
                )
                .decode()
                .rstrip("=")
            )
            assert login_params["challenge"] == [challenge]
            assert login_params["uuid"] == poll_params["uuid"]
            assert "fake-login-token" not in output and "fake-refresh" not in output
            assert await exchange_refresh_token("refresh-input", config) == (
                "fake-login-token",
                "fake-refresh",
            )
            assert state.headers[-1]["authorization"] == "Bearer refresh-input"
            assert observed == [(b"cursor.invalid", 8080)] * 2
