"""Bounded request diagnostics without logging bodies or authentication headers."""

import json
import logging
import re
import time
import traceback
from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass, field
from itertools import islice
from uuid import uuid4

from starlette.requests import ClientDisconnect

log = logging.getLogger("cursor_gateway.requests")


@dataclass
class RequestContext:
    request_id: str
    method: str
    path: str
    enabled: bool
    stage: str = "routing"
    summary: dict = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    failed: bool = False


current_request: ContextVar[RequestContext | None] = ContextVar("gateway_request", default=None)


def _clean(value):
    if isinstance(value, dict):
        return {_clean(str(k)): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if not isinstance(value, str):
        return value
    context = current_request.get()
    for secret in context.secrets if context else ():
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", value)
    value = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(
        r"""(?i)((?:access[_-]?token|refresh[_-]?token|api[_-]?key|password|authorization)"""
        r"""["']?\s*[:=]\s*["']?)[^\s"',;}\]]+""",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(r"(://)[^/\s@]+@", r"\1[REDACTED]@", value)
    return value[:1000] + ("..." if len(value) > 1000 else "")


def event(name: str, *, level: int = logging.INFO, **details) -> None:
    context = current_request.get()
    if context is None or (not context.enabled and level < logging.WARNING):
        return
    payload = {
        "event": name,
        "request_id": context.request_id,
        "method": context.method,
        "path": context.path,
        "stage": context.stage,
        **context.summary,
        **details,
    }
    # JSON escaping prevents multiline messages/control characters from forging log entries.
    log.log(level, "%s", json.dumps(_clean(payload), ensure_ascii=True, separators=(",", ":")))


def set_stage(stage: str) -> None:
    if context := current_request.get():
        context.stage = stage


def protect_secret(*values: str | None) -> None:
    if context := current_request.get():
        context.secrets.extend(value for value in values if value)


def failure(message: str, *, status: int, code=None, param=None, **details) -> None:
    if context := current_request.get():
        context.failed = True
    event(
        "request_error",
        level=logging.ERROR if status >= 500 else logging.WARNING,
        error_status=status,
        error_message=message,
        error_code=code,
        error_param=param,
        **details,
    )


def unexpected(exc: Exception, *, status: int = 502) -> None:
    # Keep frame locations, but omit source lines/locals, which may contain credentials.
    frames = [
        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(exc.__traceback__)[-12:]
    ]
    failure(str(exc), status=status, exception_type=type(exc).__name__, frames=frames)


def _option(value):
    """Only retain simple options; never recursively include arbitrary request objects."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _clean(value)[:160]
    return {"type": type(value).__name__}


def _types(items: list, key: str, default: str) -> dict:
    counts = Counter(
        str(_option(item.get(key, default))) if isinstance(item, dict) else type(item).__name__
        for item in items[:128]
    )
    return dict(counts)


def _content(value) -> dict:
    if isinstance(value, str):
        return {"type": "string", "characters": len(value)}
    if not isinstance(value, list):
        return {"type": type(value).__name__}
    return {
        "type": "array",
        "count": len(value),
        "sample_count": min(len(value), 128),
        "types": _types(value, "type", "message"),
        "roles": _types(value, "role", "absent"),
        "content_types": [
            _types(item["content"][:32], "type", "absent")
            for item in value[:32]
            if isinstance(item, dict) and isinstance(item.get("content"), list)
        ],
        "encrypted_reasoning_items": sum(
            isinstance(item, dict) and item.get("encrypted_content") is not None
            for item in value[:128]
        ),
    }


def record_body(body) -> None:
    context = current_request.get()
    if context is None:
        return
    summary = {"body_type": type(body).__name__}
    if isinstance(body, dict):
        summary["fields"] = [_clean(str(key))[:80] for key in islice(body, 48)]
        for key in (
            "model",
            "stream",
            "store",
            "background",
            "tool_choice",
            "truncation",
            "max_output_tokens",
            "max_tool_calls",
            "parallel_tool_calls",
        ):
            if key in body:
                summary[key] = _option(body[key])
        for key in ("input", "messages"):
            if key in body:
                summary[key] = _content(body[key])
        tools = body.get("tools")
        if isinstance(tools, list):
            summary["tools"] = {"count": len(tools), "types": _types(tools, "type", "function")}
            summary["tools"]["namespace_tools"] = [
                {"count": len(tool["tools"]), "types": _types(tool["tools"], "type", "absent")}
                for tool in tools[:32]
                if isinstance(tool, dict)
                and tool.get("type") == "namespace"
                and isinstance(tool.get("tools"), list)
            ]
        elif "tools" in body:
            summary["tools"] = {"type": type(tools).__name__}
        if "include" in body:
            value = body["include"]
            summary["include"] = (
                [_option(item) for item in value[:32]]
                if isinstance(value, list)
                else _option(value)
            )
        for key, children in (
            ("reasoning", ("effort", "summary")),
            ("stream_options", ("include_usage", "include_obfuscation")),
        ):
            if isinstance(body.get(key), dict):
                summary[key] = {
                    child: _option(body[key][child]) for child in children if child in body[key]
                }
        text = body.get("text")
        if isinstance(text, dict) and isinstance(text.get("format"), dict):
            summary["text_format"] = _option(text["format"].get("type"))
        summary["has_previous_response_id"] = body.get("previous_response_id") is not None
    # Keep even malformed requests with many distinct types from flooding the log.
    if len(json.dumps(summary, ensure_ascii=True)) > 8000:
        for key in ("input", "messages", "tools"):
            if isinstance(summary.get(key), dict):
                summary[key] = {
                    name: value
                    for name, value in summary[key].items()
                    if name in {"type", "count", "characters"}
                }
        summary["summary_truncated"] = True
    context.summary = summary
    event("request_parsed")


class RequestLogMiddleware:
    """Observe ASGI messages without consuming, buffering or delaying the stream."""

    def __init__(self, app, *, enabled: bool, api_key: str | None = None):
        self.app, self.enabled, self.api_key = app, enabled, api_key

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        context = RequestContext(
            uuid4().hex,
            scope["method"],
            scope["path"],
            self.enabled,
            secrets=[self.api_key] if self.api_key else [],
        )
        token = current_request.set(context)
        scope.setdefault("state", {})["request_id"] = context.request_id
        started = time.monotonic()
        http_status, received, sent = None, 0, 0
        completed, disconnected = False, False

        async def receive_message():
            nonlocal received, disconnected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
            elif message["type"] == "http.disconnect" and not completed:
                disconnected = True
            return message

        async def send_message(message):
            nonlocal http_status, sent, completed
            if message["type"] == "http.response.start":
                http_status = message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message = {
                    **message,
                    "headers": [
                        *headers,
                        (b"x-request-id", context.request_id.encode("ascii")),
                    ],
                }
            await send(message)
            if message["type"] == "http.response.body":
                sent += len(message.get("body", b""))
                completed = not message.get("more_body", False)

        headers = dict(scope.get("headers", []))
        event(
            "request_started",
            client=(scope.get("client") or (None,))[0],
            user_agent=_clean(headers.get(b"user-agent", b"").decode("latin-1"))[:200],
            content_type=_clean(headers.get(b"content-type", b"").decode("latin-1"))[:100],
            content_encoding=_clean(headers.get(b"content-encoding", b"").decode("latin-1"))[:100],
        )
        try:
            await self.app(scope, receive_message, send_message)
        except ClientDisconnect:
            disconnected = True
            raise
        except Exception as exc:
            if http_status is None:
                http_status = 500
            unexpected(exc, status=500)
            raise
        finally:
            try:
                failed = context.failed or (http_status is not None and http_status >= 400)
                event(
                    "request_finished",
                    level=logging.WARNING if failed else logging.INFO,
                    status=http_status,
                    outcome="disconnected"
                    if disconnected
                    else ("error" if failed else "completed" if completed else "cancelled"),
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    request_bytes=received,
                    response_bytes=sent,
                )
            finally:
                current_request.reset(token)
