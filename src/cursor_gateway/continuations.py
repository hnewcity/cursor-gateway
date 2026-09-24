"""Bounded, single-consumer continuations of Cursor runs waiting on client tools.

This is execution state, including for Responses store=false. A continuation can
only consume results for its complete pending batch and identical prior history,
instructions and tool definitions. Otherwise the normal stateless replay applies.
"""

import asyncio
import contextlib
import hashlib
import json
from collections import OrderedDict

from .diagnostics import current_request, event
from .session import TurnEvent, _run_protocol

OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output"}


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def history_digest(items: list[dict]) -> str:
    normalized = []
    for item in items:
        kind = item["type"]
        if kind == "message":
            value = {
                "type": kind,
                "role": item["role"],
                "content": [
                    {k: v for k, v in part.items() if k not in {"annotations", "logprobs"}}
                    for part in item["content"]
                ],
            }
            if item.get("phase"):
                value["phase"] = item["phase"]
        else:
            value = {k: v for k, v in item.items() if k not in {"id", "status"} and v is not None}
        normalized.append(value)
    return digest(normalized)


def request_scope(request) -> str:
    return digest(
        {
            key: request.body.get(key)
            for key in (
                "model",
                "instructions",
                "tools",
                "tool_choice",
                "parallel_tool_calls",
                "reasoning",
                "text",
                "temperature",
                "top_p",
                "max_output_tokens",
                "max_tool_calls",
            )
        }
    )


class NativeSession:
    def __init__(self, *, account, model, turn, config, on_close):
        self.account, self.model, self.config = account, model, config
        self.queue = asyncio.Queue(maxsize=32)
        self.pending: tuple[str, ...] = ()
        self.results: asyncio.Future | None = None
        self.timeout: asyncio.Timeout | None = None
        self.on_close = on_close
        self.request_context = current_request.get()
        self.task = asyncio.create_task(self._produce(turn), name="cursor-native-session")

    async def _exchange(self, pending):
        self.pending = pending
        self.results = asyncio.get_running_loop().create_future()
        # Tool execution/approval time belongs to the client, not the model's
        # generation timeout. The wait has its own bounded lifetime.
        self.timeout.reschedule(None)
        try:
            async with asyncio.timeout(self.config.session_keepalive_seconds):
                results = await self.results
        finally:
            self.pending, self.results = (), None
        self.timeout.reschedule(
            asyncio.get_running_loop().time() + self.config.request_timeout_ms / 1000
        )
        current_request.set(self.request_context)
        return results

    async def _produce(self, turn):
        try:
            async with asyncio.timeout(self.config.request_timeout_ms / 1000) as timeout:
                self.timeout = timeout
                async with contextlib.aclosing(
                    _run_protocol(
                        self.account.access_token, self.model, turn, self.config, self._exchange
                    )
                ) as events:
                    async for item in events:
                        await self.queue.put(item)
        except TimeoutError:
            await self.queue.put(
                TurnEvent(
                    "done",
                    reason="error",
                    code="deadline_exceeded",
                    error="Cursor session timed out",
                )
            )
        except Exception as exc:
            message = str(exc).replace(self.account.access_token, "[redacted]")
            await self.queue.put(TurnEvent("done", reason="error", error=message[:2000]))
        finally:
            self.on_close(self)

    @property
    def waiting(self):
        return (
            not self.task.done()
            and self.results is not None
            and not self.results.done()
            and bool(self.pending)
        )

    def deliver(self, results):
        self.request_context = current_request.get()
        self.results.set_result(results)

    async def events(self):
        while True:
            item = await self.queue.get()
            yield item
            if item.type == "done":
                return

    async def close(self):
        self.task.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        finally:
            # A task cancelled before its first instruction does not run its
            # own finally block.
            self.on_close(self)


class ContinuationStore:
    def __init__(self, config):
        self.config = config
        self.live: set[NativeSession] = set()
        self.waiting: OrderedDict[NativeSession, tuple[str, str]] = OrderedDict()

    def _closed(self, session):
        self.waiting.pop(session, None)
        self.live.discard(session)

    async def start(self, **kwargs):
        while len(self.live) >= self.config.session_max_entries and self.waiting:
            session, _ = self.waiting.popitem(last=False)
            await session.close()
        if len(self.live) >= self.config.session_max_entries:
            event("cursor_session_fallback", reason="capacity")
            return None
        session = NativeSession(config=self.config, on_close=self._closed, **kwargs)
        self.live.add(session)
        event("cursor_session_started")
        return session

    def take(self, request):
        items = request.input_items
        split = len(items)
        while split and items[split - 1]["type"] in OUTPUT_TYPES:
            split -= 1
        if split == len(items):
            return None
        outputs = items[split:]
        result_ids = {item["call_id"] for item in outputs}
        for session, (scope, prefix) in list(self.waiting.items()):
            if not session.waiting:
                self.waiting.pop(session, None)
                continue
            if result_ids != set(session.pending) or len(outputs) != len(session.pending):
                continue
            if request_scope(request) != scope or history_digest(items[:split]) != prefix:
                event("cursor_session_fallback", reason="history_or_configuration_changed")
                return None
            self.waiting.pop(session)
            session.deliver({item["call_id"]: item["output"] for item in outputs})
            event("cursor_session_resumed", tool_results=len(outputs))
            return session
        return None

    def retain(self, session, request, output):
        # Tool search changes the upstream catalogue; use full replay in that case.
        calls = [item for item in output if item["type"] in {"function_call", "custom_tool_call"}]
        if not session.waiting or {c["call_id"] for c in calls} != set(session.pending):
            return False
        self.waiting[session] = (
            request_scope(request),
            history_digest(request.input_items + output),
        )
        return True

    async def close(self):
        await asyncio.gather(*(session.close() for session in list(self.live)))
