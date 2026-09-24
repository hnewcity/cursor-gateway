"""FastAPI endpoints with OpenAI-compatible errors, delayed SSE and cancellation."""

import hmac
import json
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api_schema import CHAT_REQUEST_BODY, ERROR_RESPONSES, RESPONSES_REQUEST_BODY
from .auth import Account, AccountError, AccountPool
from .compaction import CompactionCodec
from .config import Config
from .continuations import ContinuationStore
from .diagnostics import RequestLogMiddleware, failure, record_body, set_stage
from .http_response import GenerationResponse, error_body, upstream_error
from .models import ModelCatalog, to_model_list
from .protocol import json_bytes
from .request_body import decode_body
from .response_store import ResponseStore
from .responses import ResponsesResponse
from .responses_compaction import CompactionResponse
from .responses_input import prepare_request
from .session import TurnEvent, run_turn
from .translate import RequestError, validate_request


def usage_block(usage: dict) -> dict:
    prompt, completion = usage.get("input", 0), usage.get("output", 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


class ChatResponse(GenerationResponse):
    async def _stream_error(self, send, payload: dict) -> None:
        await self._emit(send, payload)
        await self._done(send)

    async def _buffer(self, send, events, model: str, account: Account) -> None:
        text, thinking, calls, usage = [], [], [], {}
        terminal = None
        size = 0
        async for event in events:
            if event.type == "text":
                text.append(event.delta)
                size += len(event.delta.encode())
            elif event.type == "thinking":
                thinking.append(event.delta)
                size += len(event.delta.encode())
            elif event.type == "tool_call":
                call = self._tool(event)
                calls.append(call)
                size += len(json_bytes(call))
            elif event.type == "usage":
                self._update_usage(usage, event)
            elif event.type == "done":
                terminal = event
                break
            if size > self.config.max_body_bytes:
                terminal = TurnEvent("done", reason="error", error="completion size limit exceeded")
                break
        if terminal is None:
            terminal = TurnEvent("done", reason="error", error="upstream ended without a result")
        self._record(account, terminal)
        if terminal.reason == "error":
            status, payload = upstream_error(terminal)
            await self._json(send, status, payload)
            return
        message = {"role": "assistant", "content": "".join(text) or None}
        if thinking:
            message["reasoning_content"] = "".join(thinking)
        if calls:
            message["tool_calls"] = calls
        await self._json(
            send,
            200,
            {
                "id": f"chatcmpl-{uuid4()}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if calls else "stop",
                    }
                ],
                "usage": usage_block(usage),
            },
        )

    @staticmethod
    def _tool(event: TurnEvent) -> dict:
        return {
            "id": event.id,
            "type": "function",
            "function": {"name": event.name, "arguments": json_bytes(event.args).decode()},
        }

    @staticmethod
    def _update_usage(usage: dict, event: TurnEvent) -> None:
        if event.input_tokens is not None:
            usage["input"] = event.input_tokens
        if event.output_tokens is not None:
            usage["output"] = event.output_tokens

    @staticmethod
    async def _emit(send, value: dict) -> None:
        await send(
            {
                "type": "http.response.body",
                "body": b"data: " + json_bytes(value) + b"\n\n",
                "more_body": True,
            }
        )

    @staticmethod
    async def _done(send) -> None:
        await send({"type": "http.response.body", "body": b"data: [DONE]\n\n"})

    async def _stream(self, send, events, model: str, account: Account) -> None:
        identity = {
            "id": f"chatcmpl-{uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
        }
        usage: dict = {}
        index = 0
        include_usage = (self.request_body.get("stream_options") or {}).get("include_usage", False)

        def chunk(delta: dict, finish=None) -> dict:
            return {
                **identity,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }

        async def open_stream() -> None:
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
                await self._emit(send, chunk({"role": "assistant", "content": ""}))

        async for event in events:
            if event.type == "usage":
                self._update_usage(usage, event)
                continue
            if event.type == "done":
                self._record(account, event)
                if event.reason == "error":
                    status, payload = upstream_error(event)
                    if not self.opened:
                        await self._json(send, status, payload)
                        return
                    await self._emit(send, payload)
                    await self._done(send)
                    return
                await open_stream()
                final = chunk({}, "tool_calls" if index or event.reason == "tool_calls" else "stop")
                if not include_usage:
                    final["usage"] = usage_block(usage)
                await self._emit(send, final)
                if include_usage:
                    await self._emit(send, {**identity, "choices": [], "usage": usage_block(usage)})
                await self._done(send)
                return
            if event.type in {"text", "thinking", "tool_call"}:
                await open_stream()
                if event.type == "tool_call":
                    delta = {"tool_calls": [{"index": index, **self._tool(event)}]}
                    index += 1
                else:
                    key = "content" if event.type == "text" else "reasoning_content"
                    delta = {key: event.delta}
                await self._emit(send, chunk(delta))
        self._record(
            account, TurnEvent("done", reason="error", error="upstream ended without a result")
        )
        payload = error_body("upstream ended without a result", "upstream_error")
        if self.opened:
            await self._emit(send, payload)
            await self._done(send)
        else:
            await self._json(send, 502, payload)


def create_app(
    config: Config | None = None,
    *,
    pool: AccountPool | None = None,
    catalog: ModelCatalog | None = None,
    runner: Callable = run_turn,
    response_store: ResponseStore | None = None,
) -> FastAPI:
    config = config or Config.from_env()
    pool = pool or AccountPool(config)
    catalog = catalog or ModelCatalog(config)
    response_store = response_store or ResponseStore(
        ttl=config.response_cache_ttl,
        max_entries=config.response_cache_entries,
        max_bytes=config.response_cache_bytes,
    )
    continuations = ContinuationStore(config)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await continuations.close()

    app = FastAPI(
        title="Cursor Gateway",
        version=__version__,
        description="OpenAI-compatible Chat Completions and Responses backed by Cursor.",
        default_response_class=JSONResponse,
        lifespan=lifespan,
    )
    app.state.config, app.state.pool, app.state.catalog = config, pool, catalog
    app.state.response_store = response_store
    app.state.continuations = continuations
    compaction_codec = CompactionCodec(
        config.compaction_key_file or config.auth_file.parent / "compaction.key",
        config.max_body_bytes,
    )
    app.add_middleware(RequestLogMiddleware, enabled=config.log_requests, api_key=config.api_key)

    bearer_scheme = HTTPBearer(
        auto_error=False,
        scheme_name="BearerAuth",
        description="Gateway API key; required only when CURSOR_DIRECT_API_KEY is configured.",
    )
    api_key_scheme = APIKeyHeader(
        name="x-api-key",
        auto_error=False,
        scheme_name="ApiKeyAuth",
        description="Alternative to Authorization: Bearer <gateway API key>.",
    )

    async def require_api_key(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
        alternate: Annotated[str | None, Security(api_key_scheme)],
    ) -> None:
        set_stage("authentication")
        if not config.api_key:
            return
        bearer = credentials.credentials.strip() if credentials else ""
        expected = config.api_key.encode()
        if not (
            hmac.compare_digest(bearer.encode(), expected)
            or hmac.compare_digest((alternate or "").encode(), expected)
        ):
            raise HTTPException(
                status_code=401,
                detail="invalid api key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    api = APIRouter(
        prefix="/v1",
        dependencies=[Depends(require_api_key)],
        responses=ERROR_RESPONSES,
    )

    @app.get("/", include_in_schema=False)
    @app.get("/health", tags=["Health"], summary="Check service health")
    async def health() -> dict:
        return {"ok": True, "accounts": pool.size(), "models": "dynamic"}

    # Preserve HEAD support provided by the original GET routes.
    app.add_api_route("/", health, methods=["HEAD"], include_in_schema=False)
    app.add_api_route("/health", health, methods=["HEAD"], include_in_schema=False)

    @api.get("/models", tags=["Models"], summary="List available models")
    async def models() -> dict:
        set_stage("account")
        account = await pool.next()
        set_stage("model_discovery")
        ids = await catalog.list_ids(account.access_token)
        return {"object": "list", "data": to_model_list(ids, config.model_prefix)}

    api.add_api_route("/models", models, methods=["HEAD"], include_in_schema=False)

    async def read_json_request(request: Request):
        # Read after authentication and enforce the limit before buffering the body.
        # Using a Body parameter would let FastAPI eagerly read the entire payload.
        set_stage("body")
        raw = bytearray()
        async for part in request.stream():
            if len(raw) + len(part) > config.max_body_bytes:
                raise HTTPException(status_code=413, detail="request body too large")
            raw.extend(part)
        raw = decode_body(raw, request.headers.get("content-encoding", ""), config.max_body_bytes)
        try:

            def invalid_constant(value):
                raise ValueError("non-finite JSON number")

            body = json.loads(raw, parse_constant=invalid_constant)
        except json.JSONDecodeError as exc:
            request.state.json_error = {
                "json_error": exc.msg,
                "line": exc.lineno,
                "column": exc.colno,
                "offset": exc.pos,
            }
            raise HTTPException(status_code=400, detail="bad JSON body") from None
        except UnicodeError:
            request.state.json_error = {"json_error": "invalid JSON encoding"}
            raise HTTPException(status_code=400, detail="bad JSON body") from None
        except ValueError:
            request.state.json_error = {"json_error": "invalid JSON number"}
            raise HTTPException(status_code=400, detail="bad JSON body") from None
        record_body(body)
        set_stage("validation")
        return body

    async def read_chat_request(request: Request) -> dict:
        body = await read_json_request(request)
        if isinstance(body, dict):
            # This private routing flag is set only by the Responses adapter.
            body.pop("_cursor_web_search", None)
        return validate_request(body)

    @api.post(
        "/chat/completions",
        tags=["Chat"],
        summary="Create a chat completion",
        description=(
            "Returns JSON or an SSE stream when stream=true. Validation errors use HTTP 400. "
            "Upstream failures before the first output retain their HTTP status; failures after "
            "streaming starts are emitted as error events followed by [DONE]."
        ),
        response_model=None,
        responses={
            200: {
                "description": "Chat completion or stream of chat completion chunks",
                "content": {
                    "application/json": {"schema": {"type": "object"}},
                    "text/event-stream": {"schema": {"type": "string"}},
                },
            },
        },
        openapi_extra={"requestBody": CHAT_REQUEST_BODY},
    )
    async def chat(body: Annotated[dict, Depends(read_chat_request)]) -> Response:
        return ChatResponse(body, config, pool, catalog, runner)

    @api.post(
        "/responses",
        tags=["Responses"],
        summary="Create a response",
        description=(
            "Accepts text, inline images, history, function/custom tools and namespaces. "
            "Supports client tool search, Cursor native web search, JSON Schema output "
            "validation and encrypted compaction checkpoints. "
            "Returns a Response object or "
            "typed response.* SSE events, ending with response.completed or response.failed. "
            "Stored response history is bounded, process-local and expires; store=false "
            "disables response retrieval. Pending native runs are kept separately for bounded "
            "tool-result continuation, including when store=false. "
            "A previous_response_id replays history without inheriting top-level instructions."
        ),
        response_model=None,
        responses={
            200: {
                "description": "Response object or typed Responses SSE stream",
                "content": {
                    "application/json": {"schema": {"type": "object"}},
                    "text/event-stream": {"schema": {"type": "string"}},
                },
            },
        },
        openapi_extra={"requestBody": RESPONSES_REQUEST_BODY},
    )
    async def responses(body: Annotated[object, Depends(read_json_request)]) -> Response:
        request = prepare_request(body, response_store, config, compaction_codec=compaction_codec)
        if request.compaction:
            return CompactionResponse(request, config, pool, catalog, runner, response_store)
        return ResponsesResponse(
            request, config, pool, catalog, runner, response_store, continuations=continuations
        )

    @api.post(
        "/responses/compact",
        tags=["Responses"],
        summary="Compact a coding conversation",
        openapi_extra={"requestBody": RESPONSES_REQUEST_BODY},
    )
    async def compact(body: Annotated[object, Depends(read_json_request)]) -> Response:
        request = prepare_request(
            body,
            response_store,
            config,
            compaction_codec=compaction_codec,
            compact_endpoint=True,
        )
        return CompactionResponse(request, config, pool, catalog, runner, response_store)

    @api.get("/responses/{response_id}", tags=["Responses"], summary="Retrieve a stored response")
    async def retrieve_response(
        response_id: str,
        stream: bool = False,
        include: Annotated[list[str] | None, Query()] = None,
        starting_after: int | None = None,
    ) -> dict:
        set_stage("validation")
        if stream or include or starting_after is not None:
            raise RequestError("stored response retrieval supports JSON only, without include")
        set_stage("response_store")
        return response_store.get(response_id)["response"]

    @api.delete("/responses/{response_id}", tags=["Responses"], summary="Delete a stored response")
    async def delete_response(response_id: str) -> dict:
        set_stage("response_store")
        response_store.delete(response_id)
        return {"id": response_id, "object": "response.deleted", "deleted": True}

    @api.get(
        "/responses/{response_id}/input_items",
        tags=["Responses"],
        summary="List the input history used for a stored response",
    )
    async def response_input_items(
        response_id: str,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        order: Literal["asc", "desc"] = "desc",
        after: str | None = None,
        include: Annotated[list[str] | None, Query()] = None,
    ) -> dict:
        set_stage("validation")
        if include:
            raise RequestError("additional include fields are not supported", param="include")
        set_stage("response_store")
        items = response_store.get(response_id)["input"]
        if order == "desc":
            items.reverse()
        if after is not None:
            index = next((i for i, item in enumerate(items) if item["id"] == after), None)
            if index is None:
                raise RequestError("pagination cursor is not an input item ID", param="after")
            items = items[index + 1 :]
        page = items[:limit]
        return {
            "object": "list",
            "data": page,
            "first_id": page[0]["id"] if page else "",
            "last_id": page[-1]["id"] if page else "",
            "has_more": len(items) > limit,
        }

    @app.exception_handler(RequestError)
    async def request_error(request: Request, exc: RequestError) -> Response:
        failure(str(exc), status=exc.status, param=exc.param, code=exc.code)
        payload = error_body(str(exc), code=exc.code)
        if exc.param is not None:
            payload["error"]["param"] = exc.param
        return JSONResponse(payload, status_code=exc.status)

    @app.exception_handler(AccountError)
    async def account_error(request: Request, exc: AccountError) -> Response:
        set_stage("account")
        failure(str(exc), status=503)
        return JSONResponse(error_body(str(exc), "service_unavailable"), status_code=503)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        failure(
            str(exc.detail),
            status=exc.status_code,
            **getattr(request.state, "json_error", {}),
        )
        return JSONResponse(
            error_body(str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        # Keep the OpenAI error envelope and avoid reflecting request data or secrets.
        set_stage("validation")
        failure(
            "invalid request parameters",
            status=400,
            validation_errors=[
                {"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()[:20]
            ],
        )
        return JSONResponse(error_body("invalid request parameters"), status_code=400)

    app.include_router(api)
    default_openapi = app.openapi

    def openapi() -> dict:
        schema = default_openapi()
        # FastAPI documents 422 for path/query validation, but our handler returns 400.
        for path in schema["paths"].values():
            for operation in path.values():
                if isinstance(operation, dict):
                    operation.get("responses", {}).pop("422", None)
        return schema

    app.openapi = openapi
    return app
