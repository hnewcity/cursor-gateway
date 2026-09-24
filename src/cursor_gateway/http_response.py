"""Shared ASGI generation lifetime, upstream selection, errors, and cancellation."""

import asyncio
import contextlib
from collections.abc import Callable

from fastapi import Response
from starlette.requests import ClientDisconnect

from .auth import Account, AccountError, AccountPool
from .config import Config
from .diagnostics import event, failure, protect_secret, set_stage, unexpected
from .models import ModelCatalog, client_name, upstream_id
from .protocol import json_bytes
from .session import TurnEvent
from .translate import RequestError, build_turn_input

STATUS_BY_CODE = {
    "resource_exhausted": 429,
    "unauthenticated": 401,
    "permission_denied": 403,
    "invalid_argument": 400,
    "not_found": 404,
    "unimplemented": 501,
    "unavailable": 503,
    "deadline_exceeded": 504,
}


def error_body(message: str, kind: str = "invalid_request_error", code: str | None = None) -> dict:
    error = {"message": message, "type": kind}
    if code:
        error["code"] = code
    return {"error": error}


def context_window_error(event: TurnEvent) -> bool:
    message = (event.error or "").lower()
    return event.code == "context_length_exceeded" or any(
        phrase in message
        for phrase in (
            "maximum context length",
            "context window exceeded",
            "context length exceeded",
            "prompt is too long",
            "input exceeds the context",
        )
    )


def upstream_error(event: TurnEvent) -> tuple[int, dict]:
    if context_window_error(event):
        return 400, error_body(
            event.error or "context window exceeded",
            "invalid_request_error",
            "context_length_exceeded",
        )
    status = STATUS_BY_CODE.get(event.code or "", 502)
    return status, error_body(
        event.error or "upstream error",
        "rate_limit_exceeded" if status == 429 else "upstream_error",
        event.code,
    )


class GenerationResponse(Response):
    """Own the complete request lifetime, including pre-stream network operations."""

    def __init__(
        self,
        body: dict,
        config: Config,
        pool: AccountPool,
        catalog: ModelCatalog,
        runner: Callable,
        *,
        custom_tool_formats: dict[str, dict] | None = None,
    ) -> None:
        super().__init__()
        self.request_body = body
        self.config = config
        self.pool = pool
        self.catalog = catalog
        self.runner = runner
        self.custom_tool_formats = custom_tool_formats or {}
        self.opened = False

    async def __call__(self, scope, receive, send) -> None:
        async def disconnected() -> None:
            while True:
                if (await receive())["type"] == "http.disconnect":
                    return

        work = asyncio.create_task(
            self._respond(scope, receive, send), name="cursor-generation-response"
        )
        watch = asyncio.create_task(disconnected(), name="cursor-client-disconnect")
        try:
            done, _ = await asyncio.wait({work, watch}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                await work
        finally:
            for task in (work, watch):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, watch, return_exceptions=True)

    async def _json(self, send, status: int, value: dict) -> None:
        payload = json_bytes(value)
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            }
        )
        self.opened = True
        await send({"type": "http.response.body", "body": payload})

    async def _respond(self, scope, receive, send) -> None:
        try:
            set_stage("account")
            account = await self._select_account()
            protect_secret(account.access_token, account.refresh_token)
            set_stage("model_discovery")
            known = await self.catalog.list_ids(account.access_token)
            model = self.request_body.get("model") or client_name("auto", self.config.model_prefix)
            model = model.strip()
            resolved = upstream_id(model, self.config.model_prefix, known)
            set_stage("translation")
            turn = build_turn_input(self.request_body, self.config)
            turn.custom_tool_formats = {
                tool.name: self.custom_tool_formats[tool.name]
                for tool in turn.tools
                if tool.name in self.custom_tool_formats
            }
            set_stage("upstream")
            event(
                "generation_started",
                account=account.label,
                upstream_model=resolved,
                history_count=len(turn.root_messages),
                tool_count=len(turn.tools),
                stream=bool(self.request_body.get("stream")),
            )
            async with contextlib.aclosing(self._events(account, resolved, turn)) as events:
                if self.request_body.get("stream"):
                    await self._stream(send, events, model, account)
                else:
                    await self._buffer(send, events, model, account)
        except AccountError as exc:
            failure(str(exc), status=503, stream_started=self.opened)
            if not self.opened:
                await self._json(send, 503, error_body(str(exc), "service_unavailable"))
        except RequestError as exc:
            failure(
                str(exc),
                status=exc.status,
                param=exc.param,
                code=exc.code,
                stream_started=self.opened,
            )
            payload = error_body(str(exc), code=exc.code)
            if exc.param is not None:
                payload["error"]["param"] = exc.param
            if not self.opened:
                await self._json(send, exc.status, payload)
            elif self.request_body.get("stream"):
                await self._stream_error(send, payload)
        except ClientDisconnect, OSError:
            raise
        except Exception as exc:
            unexpected(exc)
            payload = error_body("upstream request failed", "upstream_error")
            if not self.opened:
                await self._json(send, 502, payload)
            elif self.request_body.get("stream"):
                await self._stream_error(send, payload)

    async def _select_account(self):
        return await self.pool.next()

    async def _events(self, account, model, turn):
        async with contextlib.aclosing(
            self.runner(token=account.access_token, model=model, turn=turn, config=self.config)
        ) as events:
            async for item in events:
                yield item

    def _record(self, account: Account, event: TurnEvent) -> None:
        if event.reason == "error":
            status, _ = upstream_error(event)
            failure(
                event.error or "upstream error",
                status=status,
                code=event.code,
                account=account.label,
                stream_started=self.opened,
            )
        if event.reason != "error":
            self.pool.mark_success(account)
        elif not context_window_error(event) and event.code in {
            "resource_exhausted",
            "unauthenticated",
            "permission_denied",
        }:
            self.pool.mark_failure(account, event.code)

    async def _stream_error(self, send, payload: dict) -> None:
        raise NotImplementedError

    async def _buffer(self, send, events, model: str, account: Account) -> None:
        raise NotImplementedError

    async def _stream(self, send, events, model: str, account: Account) -> None:
        raise NotImplementedError
