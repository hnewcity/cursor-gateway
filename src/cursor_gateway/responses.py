"""Responses JSON and typed SSE events over the shared Cursor generation lifetime."""

import contextlib
import copy
import time

from .diagnostics import event as diagnostic_event
from .http_response import GenerationResponse, upstream_error
from .protocol import json_bytes
from .response_store import ResponseStore
from .responses_input import ResponsesRequest, new_id
from .responses_tools import ToolBinding
from .session import TurnEvent, run_turn
from .token_estimate import estimate_input_tokens
from .translate import RequestError


def response_usage(usage: dict) -> dict:
    input_tokens, output_tokens = usage.get("input", 0), usage.get("output", 0)
    value = {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": input_tokens + output_tokens,
    }
    if usage.get("input_estimated"):
        value["input_tokens_details"]["estimated"] = True
    return value


class ResponseState:
    """Produce the same output items for buffered responses and streaming clients."""

    def __init__(
        self,
        body: dict,
        model: str,
        max_bytes: int,
        tool_bindings: dict[str, ToolBinding] | None = None,
    ) -> None:
        self.tool_bindings = tool_bindings or {}
        self.value = {
            "id": new_id("resp"),
            "object": "response",
            "created_at": int(time.time()),
            "completed_at": None,
            "status": "in_progress",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": [],
            "instructions": body.get("instructions"),
            "previous_response_id": body.get("previous_response_id"),
            "store": body["store"],
            "background": False,
            "parallel_tool_calls": body["parallel_tool_calls"],
            "tools": body["tools"],
            "tool_choice": body["tool_choice"],
            "metadata": body["metadata"],
            "temperature": body.get("temperature", 1),
            "top_p": body.get("top_p", 1),
            "max_output_tokens": body.get("max_output_tokens"),
            "max_tool_calls": body.get("max_tool_calls"),
            "reasoning": body.get("reasoning"),
            "text": body.get("text") or {"format": {"type": "text"}},
            "truncation": "disabled",
            "usage": None,
        }
        self.max_bytes, self.size = max_bytes, len(json_bytes(self.value))
        self.current: dict | None = None
        self.chunks: list[str] = []
        self.usage: dict = {}

    def event(self, event_type: str, **fields) -> dict:
        event = {"type": f"response.{event_type}", **fields}
        # Later item mutations must not change previously emitted event snapshots.
        return copy.deepcopy(event)

    def start(self) -> list[dict]:
        return [
            self.event("created", response=self.value),
            self.event("in_progress", response=self.value),
        ]

    def coordinates(self) -> dict:
        return {"item_id": self.current["id"], "output_index": len(self.value["output"]) - 1}

    def close_item(self, *, failed: bool = False, phase: str = "commentary") -> list[dict]:
        if self.current is None:
            return []
        item, events = self.current, []
        at = self.coordinates()
        if item["type"] in {"message", "reasoning"}:
            reasoning = item["type"] == "reasoning"
            part = item["summary" if reasoning else "content"][0]
            part["text"] = "".join(self.chunks)
            if reasoning:
                fields = {**at, "summary_index": 0}
                events.append(
                    self.event("reasoning_summary_text.done", **fields, text=part["text"])
                )
                events.append(self.event("reasoning_summary_part.done", **fields, part=part))
            else:
                # Cursor reveals whether text preceded a tool or ended the turn only
                # after streaming it. Finalize phase on output_item.done, not a guess.
                item["phase"] = phase
                fields = {**at, "content_index": 0}
                events.append(
                    self.event("output_text.done", **fields, text=part["text"], logprobs=[])
                )
                events.append(self.event("content_part.done", **fields, part=part))
        elif item["type"] == "tool_search_call":
            pass
        elif item["type"] == "custom_tool_call":
            events.append(self.event("custom_tool_call_input.done", **at, input=item["input"]))
        else:
            events.append(
                self.event(
                    "function_call_arguments.done",
                    **at,
                    name=item["name"],
                    arguments=item["arguments"],
                )
            )
        if item["type"] != "custom_tool_call":
            item["status"] = "incomplete" if failed else "completed"
        events.append(self.event("output_item.done", output_index=at["output_index"], item=item))
        self.current, self.chunks = None, []
        return events

    def add(self, event: TurnEvent) -> list[dict]:
        if event.type == "usage":
            if event.input_tokens is not None:
                self.usage["input"] = event.input_tokens
                self.usage.pop("input_estimated", None)
            if event.output_tokens is not None:
                self.usage["output"] = event.output_tokens
            return []
        if event.type == "web_search":
            events = self.close_item()
            item = {
                "id": event.id or new_id("ws"),
                "type": "web_search_call",
                "status": "in_progress",
                "action": {"type": "search", **event.args},
            }
            self.size += len(json_bytes(item))
            if self.size > self.max_bytes:
                raise RequestError("completion size limit exceeded", status=502)
            index = len(self.value["output"])
            self.value["output"].append(item)
            at = {"output_index": index, "item_id": item["id"]}
            events.append(self.event("output_item.added", output_index=index, item=item))
            events.append(self.event("web_search_call.in_progress", **at))
            events.append(self.event("web_search_call.searching", **at))
            item["status"] = "completed"
            events.append(self.event("web_search_call.completed", **at))
            events.append(self.event("output_item.done", output_index=index, item=item))
            return events
        if event.type not in {"text", "thinking", "tool_call"}:
            return []
        if event.type != "tool_call" and not event.delta:
            return []
        kind = {"text": "message", "thinking": "reasoning", "tool_call": "function_call"}[
            event.type
        ]
        is_call = event.type == "tool_call"
        binding = self.tool_bindings.get(event.name, ToolBinding(event.name))
        if is_call and binding.kind == "tool_search":
            kind = "tool_search_call"
        if is_call and binding.kind == "custom":
            kind = "custom_tool_call"
            arguments = event.args.get("input")
            if not isinstance(arguments, str):
                raise RequestError("upstream custom tool call requires string input", status=502)
        else:
            arguments = json_bytes(event.args).decode() if is_call else ""
        extra = (
            len(arguments.encode()) + len(event.name.encode())
            if is_call
            else len(event.delta.encode())
        )
        if self.current is None or self.current["type"] != kind or is_call:
            extra += 256
        if self.size + extra > self.max_bytes:
            raise RequestError("completion size limit exceeded", status=502)
        self.size += extra
        events = []
        if self.current is not None and (self.current["type"] != kind or is_call):
            events.extend(self.close_item())
        if self.current is None:
            if kind == "message":
                item = {
                    "id": new_id("msg"),
                    "type": kind,
                    "status": "in_progress",
                    "role": "assistant",
                    "content": [],
                }
            elif kind == "reasoning":
                item = {"id": new_id("rs"), "type": kind, "status": "in_progress", "summary": []}
            else:
                item = {
                    "id": new_id("ctc" if kind == "custom_tool_call" else "fc"),
                    "type": kind,
                    "status": "in_progress",
                    "call_id": event.id or new_id("call"),
                    "name": binding.name,
                }
                item["input" if kind == "custom_tool_call" else "arguments"] = ""
                if kind == "custom_tool_call":
                    item.pop("status")
                if binding.namespace is not None:
                    item["namespace"] = binding.namespace
                if kind == "tool_search_call":
                    item.pop("name")
                    item.update(execution="client", arguments={})
            self.current = item
            self.value["output"].append(item)
            at = self.coordinates()
            events.append(
                self.event("output_item.added", output_index=at["output_index"], item=item)
            )
            if kind == "message":
                part = {"type": "output_text", "text": "", "annotations": [], "logprobs": []}
                item["content"].append(part)
                events.append(self.event("content_part.added", **at, content_index=0, part=part))
            elif kind == "reasoning":
                part = {"type": "summary_text", "text": ""}
                item["summary"].append(part)
                events.append(
                    self.event("reasoning_summary_part.added", **at, summary_index=0, part=part)
                )
        at = self.coordinates()
        if is_call:
            if kind == "tool_search_call":
                self.current["arguments"] = event.args
            else:
                self.current["input" if kind == "custom_tool_call" else "arguments"] = arguments
                prefix = (
                    "custom_tool_call_input"
                    if kind == "custom_tool_call"
                    else "function_call_arguments"
                )
                events.append(self.event(f"{prefix}.delta", **at, delta=arguments))
            events.extend(self.close_item())
        else:
            self.chunks.append(event.delta)
            if kind == "message":
                events.append(
                    self.event(
                        "output_text.delta", **at, content_index=0, delta=event.delta, logprobs=[]
                    )
                )
            else:
                events.append(
                    self.event(
                        "reasoning_summary_text.delta", **at, summary_index=0, delta=event.delta
                    )
                )
        return events

    def finish(self, terminal: TurnEvent) -> list[dict]:
        failed = terminal.reason == "error"
        events = self.close_item(
            failed=failed,
            phase="final_answer" if terminal.reason == "stop" else "commentary",
        )
        self.value["status"] = "failed" if failed else "completed"
        self.value["completed_at"] = None if failed else int(time.time())
        self.value["usage"] = response_usage(self.usage)
        if failed:
            _, payload = upstream_error(terminal)
            code = payload["error"].get("code")
            self.value["error"] = {
                "code": {
                    "resource_exhausted": "rate_limit_exceeded",
                    "invalid_argument": "invalid_prompt",
                    "context_length_exceeded": "context_length_exceeded",
                }.get(code, "server_error"),
                "message": terminal.error or "upstream request failed",
            }
        events.append(self.event("failed" if failed else "completed", response=self.value))
        return events


class ResponsesResponse(GenerationResponse):
    def __init__(
        self,
        request: ResponsesRequest,
        config,
        pool,
        catalog,
        runner,
        store: ResponseStore,
        *,
        continuations=None,
    ) -> None:
        super().__init__(
            request.chat_body,
            config,
            pool,
            catalog,
            runner,
            custom_tool_formats={
                alias: binding.input_format
                for alias, binding in request.tool_bindings.items()
                if binding.input_format is not None
            },
        )
        self.responses_request = request
        self.store = store
        self.state: ResponseState | None = None
        self.sequence = 0
        self.continuations = continuations if config.reuse_sessions and runner is run_turn else None
        self.session = None
        self.retained = False
        self.delivered = False
        self.resumed = False

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            if self.session is not None and not (self.retained and self.delivered):
                await self.session.close()

    async def _select_account(self):
        if self.continuations is not None:
            self.session = self.continuations.take(self.responses_request)
        if self.session is not None:
            self.resumed = True
            return self.session.account
        return await super()._select_account()

    async def _events(self, account, model, turn):
        if self.continuations is not None and self.session is None:
            self.session = await self.continuations.start(account=account, model=model, turn=turn)
        source = (
            self.session.events()
            if self.session is not None
            else super()._events(account, model, turn)
        )
        async with contextlib.aclosing(source) as events:
            visible = False
            async for item in events:
                # A parked upstream connection may have closed while the client
                # was running a tool. Replay once only before any new output;
                # never splice a second generation into a partially emitted one.
                if (
                    self.resumed
                    and not visible
                    and item.type == "done"
                    and item.reason == "error"
                    and item.code is None
                ):
                    await self.session.close()
                    self.session, self.resumed = None, False
                    diagnostic_event("cursor_session_fallback", reason="upstream_closed")
                    async for replayed in self._events(account, model, turn):
                        yield replayed
                    return
                visible |= item.type in {"thinking", "text", "tool_call", "web_search"}
                yield item

    def _save(self) -> None:
        if self.responses_request.body["store"]:
            self.store.put(self.state.value, self.responses_request.input_items)

    async def _emit_events(self, send, events: list[dict]) -> None:
        for event in events:
            event = {"sequence_number": self.sequence, **event}
            self.sequence += 1
            await send(
                {
                    "type": "http.response.body",
                    "body": b"event: "
                    + event["type"].encode()
                    + b"\ndata: "
                    + json_bytes(event)
                    + b"\n\n",
                    "more_body": True,
                }
            )

    @staticmethod
    async def _end(send) -> None:
        # Responses terminates with a typed terminal event, not a Chat [DONE] sentinel.
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def _stream_error(self, send, payload: dict) -> None:
        error = payload["error"]
        terminal = TurnEvent("done", reason="error", error=error["message"], code=error.get("code"))
        events = self.state.finish(terminal)
        try:
            self._save()
        except RequestError:
            self.state.value["store"] = False
            events[-1]["response"]["store"] = False
        await self._emit_events(send, events)
        await self._end(send)

    async def _buffer(self, send, events, model, account) -> None:
        await self._consume(send, events, model, account, stream=False)

    async def _stream(self, send, events, model, account) -> None:
        await self._consume(send, events, model, account, stream=True)

    async def _consume(self, send, events, model, account, *, stream: bool) -> None:
        self.state = ResponseState(
            self.responses_request.body,
            model,
            self.config.max_body_bytes,
            self.responses_request.tool_bindings,
        )
        # Cursor doesn't report input usage. Label the conservative estimate explicitly so
        # coding clients can trigger context compaction instead of always seeing zero.
        self.state.usage.update(
            input=estimate_input_tokens(self.request_body),
            input_estimated=True,
        )
        terminal = TurnEvent("done", reason="error", error="upstream ended without a result")

        async def open_stream():
            if not self.opened:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"content-type", b"text/event-stream; charset=utf-8"),
                            (b"cache-control", b"no-cache, no-transform"),
                            (b"x-accel-buffering", b"no"),
                        ],
                    }
                )
                self.opened = True
                await self._emit_events(send, self.state.start())

        async for event in events:
            if event.type == "done":
                terminal = event
                break
            # Create lifecycle events before adding output, but only after an actual output
            # arrives so that early upstream errors still retain their HTTP status.
            if stream and event.type in {"text", "thinking", "tool_call", "web_search"}:
                await open_stream()
            try:
                emitted = self.state.add(event)
            except RequestError as exc:
                terminal = TurnEvent("done", reason="error", error=str(exc))
                break
            if stream:
                await self._emit_events(send, emitted)
        self._record(account, terminal)
        if terminal.reason == "error" and (not stream or not self.opened):
            status, payload = upstream_error(terminal)
            await self._json(send, status, payload)
            return
        if stream:
            await open_stream()
        emitted = self.state.finish(terminal)
        if terminal.reason != "error" and self.responses_request.output_format is not None:
            self.responses_request.output_format.validate(self.state.value)
        if (
            terminal.reason != "error"
            and len(json_bytes(self.state.value)) > self.config.max_body_bytes
        ):
            raise RequestError("completion size limit exceeded", status=502)
        self._save()
        if terminal.reason == "tool_calls" and self.session is not None:
            self.retained = self.continuations.retain(
                self.session, self.responses_request, self.state.value["output"]
            )
        if stream:
            await self._emit_events(send, emitted)
            await self._end(send)
        else:
            await self._json(send, 200, self.state.value)
        self.delivered = True
