"""Run a Cursor turn, answering reverse KV/context RPCs and surfacing caller tools."""

import asyncio
import contextlib
import hashlib
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .config import Config
from .diagnostics import event as diagnostic_event
from .images import selected_image
from .models import rpc_headers
from .proto import agent_pb2 as pb
from .protocol import (
    MAX_FRAME_BYTES,
    FrameDecoder,
    ProtocolError,
    connect_frame,
    decode_arg_value,
    json_bytes,
)
from .search_scratch import SearchScratch
from .tool_validation import custom_input_error
from .translate import TurnInput, native_tool_name
from .transport import H2Stream

HTTP_CODES = {
    400: "invalid_argument",
    401: "unauthenticated",
    403: "permission_denied",
    404: "not_found",
    429: "resource_exhausted",
    501: "unimplemented",
    503: "unavailable",
    504: "deadline_exceeded",
}


@dataclass(slots=True)
class TurnEvent:
    type: str
    delta: str = ""
    id: str = ""
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    output_tokens: int | None = None
    input_tokens: int | None = None
    reason: str = "stop"
    error: str | None = None
    code: str | None = None


def safe_tool_call_id(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw) or f"call_{uuid4()}"


def end_stream_event(payload: bytes) -> TurnEvent:
    try:
        trailer = json.loads(payload)
    except ValueError, UnicodeError:
        raise ProtocolError("upstream returned an invalid Connect end-stream envelope") from None
    if not isinstance(trailer, dict):
        raise ProtocolError("Connect end-stream envelope must be an object")
    error = trailer.get("error")
    if error is not None:
        if not isinstance(error, dict):
            raise ProtocolError("invalid Connect error envelope")
        return TurnEvent(
            "done",
            reason="error",
            code=error.get("code") if isinstance(error.get("code"), str) else None,
            error=str(error.get("message") or "upstream error")[:2000],
        )
    return TurnEvent("done")


async def _run_protocol(
    token: str,
    model: str,
    turn: TurnInput,
    config: Config,
    tool_exchange: Callable[[tuple[str, ...]], Awaitable[dict[str, Any]]] | None = None,
) -> AsyncIterator[TurnEvent]:
    blobs: dict[bytes, bytes] = {}
    root_ids = []
    for entry in turn.root_messages:
        data = json_bytes(entry)
        blob_id = hashlib.sha256(data).digest()
        blobs[blob_id] = data
        root_ids.append(blob_id)
    blob_size = sum(map(len, blobs.values()))
    if blob_size > MAX_FRAME_BYTES:
        raise ProtocolError("history blob store size limit exceeded")
    request = pb.AgentClientMessage()
    run = request.run_request
    run.conversation_state.root_prompt_messages_json.extend(root_ids)
    run.conversation_id = str(uuid4())
    run.model_details.model_id = model
    run.model_details.display_model_id = model
    run.model_details.display_name = model
    run.requested_model.model_id = model
    if turn.user_text.strip() or turn.images:
        run.action.user_message_action.user_message.text = turn.user_text
        run.action.user_message_action.user_message.message_id = str(uuid4())
        run.action.user_message_action.user_message.selected_context.selected_images.extend(
            turn.images
        )
    else:
        run.action.resume_action.SetInParent()
    if turn.tools:
        run.mcp_tools.mcp_tools.extend(turn.tools)
    decoder = FrameDecoder()
    search_scratch = SearchScratch(min(config.max_body_bytes, MAX_FRAME_BYTES))
    headers = rpc_headers(token, config, streaming=True)
    if turn.web_search and config.allowed_native_tools:
        headers["x-cursor-agent-allowed-tools"] = ",".join(
            dict.fromkeys((*config.allowed_native_tools, "web_search_tool_call", "read_tool_call"))
        )
    async with H2Stream(
        config.cursor_base_url,
        "/agent.v1.AgentService/Run",
        headers,
        proxy_url=config.proxy_url,
    ) as stream:

        async def send(message: pb.AgentClientMessage) -> None:
            await stream.send(connect_frame(message.SerializeToString()))

        await send(request)
        headers = await stream.response_headers()
        status = int(headers.get(":status", 0))
        if status != 200:
            yield TurnEvent(
                "done",
                reason="error",
                code=HTTP_CODES.get(status),
                error=f"upstream HTTP {status}",
            )
            return
        tool_deadline = None
        tool_ids: set[str] = set()
        pending: dict[str, pb.ExecServerMessage] = {}
        input_retries = 0

        async def resume_tools() -> None:
            nonlocal tool_deadline, input_retries
            results = await tool_exchange(tuple(pending))
            for call_id, execution in pending.items():
                reply = pb.AgentClientMessage()
                response = reply.exec_client_message
                response.id, response.exec_id = execution.id, execution.exec_id
                success = response.mcp_result.success
                success.SetInParent()
                output = results[call_id]
                if isinstance(output, str):
                    success.content.add().text.text = output
                else:
                    for part in output:
                        if part["type"] == "input_image":
                            image = selected_image(part)
                            content = success.content.add().image
                            content.data, content.mime_type = image.data, image.mime_type
                        else:
                            success.content.add().text.text = part["text"]
                await send(reply)
            pending.clear()
            tool_ids.clear()
            tool_deadline, input_retries = None, 0

        while True:
            try:
                # Cursor can dispatch several MCP executions before awaiting their
                # results. Drain that batch instead of dropping everything after
                # the first call. Never wait for results that only the client owns.
                async with asyncio.timeout_at(tool_deadline):
                    data = await anext(stream)
            except TimeoutError:
                yield TurnEvent("done", reason="tool_calls")
                if tool_exchange is None:
                    return
                await resume_tools()
                continue
            except StopAsyncIteration:
                break
            for frame in decoder.feed(data):
                if frame.end_stream:
                    terminal = end_stream_event(frame.payload)
                    if tool_ids and terminal.reason != "error":
                        terminal.reason = "tool_calls"
                    yield terminal
                    return
                message = pb.AgentServerMessage.FromString(frame.payload)
                kind = message.WhichOneof("message")
                if kind == "kv_server_message":
                    kv = message.kv_server_message
                    reply = pb.AgentClientMessage()
                    response = reply.kv_client_message
                    response.id = kv.id
                    operation = kv.WhichOneof("message")
                    if operation == "get_blob_args":
                        response.get_blob_result.SetInParent()
                        blob = blobs.get(kv.get_blob_args.blob_id)
                        if blob is not None:
                            response.get_blob_result.blob_data = blob
                    elif operation == "set_blob_args":
                        args = kv.set_blob_args
                        blob_size += len(args.blob_data) - len(blobs.get(args.blob_id, b""))
                        if blob_size > MAX_FRAME_BYTES:
                            raise ProtocolError("upstream blob store size limit exceeded")
                        blobs[args.blob_id] = args.blob_data
                        response.set_blob_result.SetInParent()
                    else:
                        continue
                    await send(reply)
                elif kind == "exec_server_message":
                    execution = message.exec_server_message
                    operation = execution.WhichOneof("message")
                    if operation == "request_context_args":
                        reply = pb.AgentClientMessage()
                        response = reply.exec_client_message
                        response.id, response.exec_id = execution.id, execution.exec_id
                        context = response.request_context_result.success.request_context
                        context.tools.extend(turn.tools)
                        context.web_search_enabled = turn.web_search
                        context.env.CopyFrom(
                            pb.RequestContextEnv(
                                os_version="linux",
                                shell="bash",
                                sandbox_enabled=False,
                                time_zone="UTC",
                            )
                        )
                        await send(reply)
                    elif turn.web_search and operation in ("write_args", "read_args"):
                        await send(search_scratch.handle(execution))
                    elif operation == "mcp_args":
                        args = execution.mcp_args
                        name = args.name or args.tool_name or "unknown"
                        available = {tool.name for tool in turn.tools}
                        native_names = {
                            native_tool_name(tool.name): tool.name for tool in turn.tools
                        }
                        name = native_names.get(name, name)
                        if name not in available and args.tool_name in available:
                            name = args.tool_name
                        if name not in available:
                            raise ProtocolError(f"upstream requested undeclared tool: {name}")
                        call_id = safe_tool_call_id(args.tool_call_id)
                        arguments = {key: decode_arg_value(raw) for key, raw in args.args.items()}
                        error = custom_input_error(arguments, turn.custom_tool_formats.get(name))
                        if error and not tool_ids:
                            diagnostic_event(
                                "tool_input_rejected",
                                tool=name,
                                attempt=input_retries + 1,
                                retry=input_retries < config.tool_input_retries,
                            )
                            if input_retries >= config.tool_input_retries:
                                yield TurnEvent(
                                    "done",
                                    reason="error",
                                    code="tool_input_invalid",
                                    error=f"custom tool input remained invalid: {error}",
                                )
                                return
                            input_retries += 1
                            reply = pb.AgentClientMessage()
                            response = reply.exec_client_message
                            response.id, response.exec_id = execution.id, execution.exec_id
                            response.mcp_result.error.error = (
                                "Input validation failed before client execution. "
                                "The tool was not executed. "
                                f"{error} Return a corrected call matching the tool definition."
                            )
                            await send(reply)
                            continue
                        if error:
                            # Preserve an already dispatched parallel batch; the client
                            # reports this validation failure alongside its other results.
                            diagnostic_event("tool_input_validation_deferred", tool=name)
                        if call_id not in tool_ids:
                            tool_ids.add(call_id)
                            pending[call_id] = execution
                            yield TurnEvent(
                                "tool_call",
                                id=call_id,
                                name=name,
                                args=arguments,
                            )
                        if not turn.parallel_tools or len(tool_ids) >= 32:
                            yield TurnEvent("done", reason="tool_calls")
                            if tool_exchange is None:
                                return
                            await resume_tools()
                            continue
                        if tool_deadline is None:
                            tool_deadline = asyncio.get_running_loop().time() + 0.075
                    elif operation is not None:
                        # There is deliberately no filesystem/shell executor in this gateway.
                        raise ProtocolError(
                            f"upstream requested unsupported native tool: {operation}"
                        )
                elif kind == "interaction_query":
                    query = message.interaction_query
                    operation = query.WhichOneof("query")
                    if operation == "web_search_request_query":
                        reply = pb.AgentClientMessage()
                        response = reply.interaction_response
                        response.id = query.id
                        if turn.web_search:
                            response.web_search_request_response.approved.SetInParent()
                        else:
                            response.web_search_request_response.rejected.reason = (
                                "Web search was not enabled by this request."
                            )
                        await send(reply)
                    else:
                        raise ProtocolError(
                            f"upstream requested unsupported interaction: {operation}"
                        )
                elif kind == "interaction_update":
                    update = message.interaction_update
                    operation = update.WhichOneof("message")
                    if operation == "text_delta" and update.text_delta.text:
                        yield TurnEvent("text", delta=update.text_delta.text)
                    elif operation == "thinking_delta" and update.thinking_delta.text:
                        yield TurnEvent("thinking", delta=update.thinking_delta.text)
                    elif operation == "token_delta":
                        yield TurnEvent("usage", output_tokens=max(0, update.token_delta.tokens))
                    elif operation == "tool_call_completed":
                        completed = update.tool_call_completed
                        if completed.tool_call.WhichOneof("tool") == "web_search_tool_call":
                            search = completed.tool_call.web_search_tool_call
                            outcome = search.result.WhichOneof("result")
                            if outcome == "success":
                                yield TurnEvent(
                                    "web_search",
                                    id=safe_tool_call_id(completed.call_id),
                                    args={
                                        "query": search.args.search_term,
                                        "sources": [
                                            {"type": "url", "url": ref.url}
                                            for ref in search.result.success.references
                                            if ref.url.startswith(("http://", "https://"))
                                        ],
                                    },
                                )
                            elif outcome == "error":
                                raise ProtocolError("Cursor web search failed")
                    elif operation == "turn_ended":
                        yield TurnEvent("done", reason="tool_calls" if tool_ids else "stop")
                        return
        if tool_ids:
            yield TurnEvent("done", reason="tool_calls")
            return
        decoder.finish()
        raise ProtocolError("upstream ended before turn_ended or a Connect end-stream envelope")


async def run_turn(
    *,
    token: str,
    model: str,
    turn: TurnInput,
    config: Config,
) -> AsyncIterator[TurnEvent]:
    queue: asyncio.Queue[TurnEvent] = asyncio.Queue(maxsize=32)

    async def produce() -> None:
        try:
            async with asyncio.timeout(config.request_timeout_ms / 1000):
                async with contextlib.aclosing(_run_protocol(token, model, turn, config)) as events:
                    async for event in events:
                        await queue.put(event)
        except TimeoutError:
            await queue.put(
                TurnEvent(
                    "done",
                    reason="error",
                    code="deadline_exceeded",
                    error="upstream timeout",
                )
            )
        except Exception as exc:
            message = str(exc).replace(token, "[redacted]") if token else str(exc)
            await queue.put(TurnEvent("done", reason="error", error=message[:2000]))

    producer = asyncio.create_task(produce(), name="cursor-turn")
    try:
        while True:
            event = await queue.get()
            yield event
            if event.type == "done":
                return
    finally:
        producer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer
