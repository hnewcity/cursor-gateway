"""Standalone and in-stream compaction over Cursor's existing generation transport."""

from .compaction import SUMMARY_LIMIT
from .diagnostics import event, set_stage
from .http_response import upstream_error
from .protocol import json_bytes
from .responses import ResponsesResponse, ResponseState
from .session import TurnEvent
from .token_estimate import estimate_input_tokens
from .translate import RequestError


class CompactionResponse(ResponsesResponse):
    async def _consume(self, send, events, model, account, *, stream: bool) -> None:
        set_stage("compaction")
        request = self.responses_request
        state = self.state = ResponseState(request.body, model, self.config.max_body_bytes)
        state.usage.update(input=estimate_input_tokens(self.request_body), input_estimated=True)
        text, size = [], 0
        terminal = TurnEvent(
            "done", reason="error", error="upstream ended before compaction completed"
        )
        async for item in events:
            if item.type == "text":
                text.append(item.delta)
                size += len(item.delta.encode())
                if size > min(SUMMARY_LIMIT, self.config.max_body_bytes):
                    raise RequestError("compaction summary size limit exceeded", status=502)
            elif item.type == "usage":
                state.add(item)
            elif item.type == "tool_call":
                raise RequestError("upstream attempted a tool call during compaction", status=502)
            elif item.type == "done":
                terminal = item
                break
        self._record(account, terminal)
        if terminal.reason == "error":
            status, payload = upstream_error(terminal)
            await self._json(send, status, payload)
            return
        checkpoint = request.compaction_codec.issue("".join(text), request.input_items)
        start = state.start()
        state.value["output"] = [checkpoint]
        finished = state.finish(terminal)
        event(
            "compaction_completed", summary_bytes=size, checkpoint_bytes=len(json_bytes(checkpoint))
        )
        if request.compact_endpoint:
            users = [
                item
                for item in request.input_items
                if item["type"] == "message" and item["role"] == "user"
            ]
            payload = {
                "id": checkpoint["id"],
                "object": "response.compaction",
                "created_at": state.value["created_at"],
                "output": [*users, checkpoint],
                "usage": state.value["usage"],
            }
            if len(json_bytes(payload)) > self.config.max_body_bytes:
                raise RequestError("compacted response size limit exceeded", status=413)
            await self._json(send, 200, payload)
            return
        self._save()
        if not stream:
            await self._json(send, 200, state.value)
            return
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
        await self._emit_events(
            send,
            [
                *start,
                state.event("output_item.added", output_index=0, item=checkpoint),
                state.event("output_item.done", output_index=0, item=checkpoint),
                *finished,
            ],
        )
        await self._end(send)
