"""Per-account model discovery with bounded caching and a fallback catalogue."""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from uuid import uuid4

from .config import Config
from .proto import agent_pb2 as pb
from .transport import h2_request

log = logging.getLogger(__name__)
FALLBACK_MODEL_IDS = (
    "auto",
    "claude-opus-5-thinking-high",
    "claude-sonnet-5-thinking-high",
    "claude-fable-5-thinking-high",
    "claude-opus-4-8-thinking-high",
    "composer-2.5",
    "gpt-5.6-sol-high",
    "gpt-5.6-luna-high",
    "gpt-5.3-codex",
    "gpt-5.2",
    "cursor-grok-4.6-high",
    "cursor-grok-4.6-medium",
    "gemini-3.7-flash-high",
)


def client_name(model: str, prefix: str) -> str:
    """Hide Cursor's native prefix while honoring an optional gateway prefix."""
    if prefix and model.startswith(prefix):
        return model
    return prefix + model.removeprefix("cursor-")


def upstream_id(name: str, prefix: str, known: list[str] | tuple[str, ...]) -> str:
    name = name.strip()
    if name in known:
        return name
    if prefix and name.startswith(prefix):
        name = name[len(prefix) :] or name
    if name in known:
        return name
    # Accept old gateway names and map bare names back to native Cursor IDs.
    name = name.removeprefix("cursor-") or name
    if name in known:
        return name
    if f"cursor-{name}" in known:
        return f"cursor-{name}"
    return name


def to_model_list(ids: list[str], prefix: str) -> list[dict]:
    created = int(time.time())
    names = dict.fromkeys(client_name(model, prefix) for model in ids)
    return [
        {"id": name, "object": "model", "created": created, "owned_by": "cursor"} for name in names
    ]


def rpc_headers(token: str, config: Config, *, streaming: bool = False) -> dict[str, str]:
    headers = {
        "content-type": "application/connect+proto" if streaming else "application/proto",
        "connect-protocol-version": "1",
        "authorization": f"Bearer {token}",
        "x-ghost-mode": "true",
        "x-cursor-client-version": config.client_version,
        "x-cursor-client-type": "cli",
        "x-request-id": str(uuid4()),
    }
    if streaming:
        headers["te"] = "trailers"
        headers["connect-accept-encoding"] = "gzip"
        if config.allowed_native_tools:
            headers["x-cursor-agent-allowed-tools"] = ",".join(config.allowed_native_tools)
    return headers


class ModelCatalog:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._cache: OrderedDict[bytes, tuple[list[str], float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def list_ids(self, token: str) -> list[str]:
        key = hashlib.sha256(token.encode()).digest()
        async with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() < cached[1]:
                self._cache.move_to_end(key)
                return cached[0].copy()
            try:
                response = await h2_request(
                    self.config.cursor_base_url,
                    "/agent.v1.AgentService/GetUsableModels",
                    headers=rpc_headers(token, self.config),
                    body=pb.GetUsableModelsRequest().SerializeToString(),
                    proxy_url=self.config.proxy_url,
                    timeout=min(20, self.config.request_timeout_ms / 1000),
                )
                if response.status != 200:
                    raise ValueError(f"model discovery returned HTTP {response.status}")
                models = pb.GetUsableModelsResponse.FromString(response.body)
                ids = list(
                    dict.fromkeys(model.model_id for model in models.models if model.model_id)
                )
                if not ids:
                    raise ValueError("upstream returned an empty model list")
                ttl = 600
            except Exception as exc:
                log.warning(
                    "model discovery failed (%s); using cached/fallback models", type(exc).__name__
                )
                ids = cached[0] if cached else list(FALLBACK_MODEL_IDS)
                ttl = 30
            self._cache[key] = (ids, time.monotonic() + ttl)
            self._cache.move_to_end(key)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
            return ids.copy()
