"""Environment configuration, compatible with cursor2api's CURSOR_DIRECT_* names."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    if value not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        raise ValueError(f"{name} must be a boolean")
    return value in {"1", "true", "yes", "on"}


def _integer(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    try:
        return int(value) if value else default
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None


@dataclass(frozen=True, slots=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 8790
    api_key: str | None = None
    cursor_base_url: str = "https://api2.cursor.sh"
    proxy_url: str | None = None
    client_version: str = "cli-2026.08.11-e8db854"
    allowed_native_tools: tuple[str, ...] = ("mcp_tool_call",)
    model_prefix: str = ""
    auth_file: Path = Path("accounts.json")
    request_timeout_ms: int = 300_000
    system_as_history: bool = True
    continuation_prompt: str = "Continue, using the tool results above."
    log_requests: bool = True
    max_body_bytes: int = 64 * 1024 * 1024
    response_cache_ttl: int = 3600
    response_cache_entries: int = 256
    response_cache_bytes: int = 128 * 1024 * 1024
    compaction_key_file: Path | None = None
    replay_reasoning: bool = True
    reasoning_replay_max_chars: int = 12_000
    tool_input_retries: int = 1
    reuse_sessions: bool = True
    session_keepalive_seconds: int = 300
    session_max_entries: int = 8

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("CURSOR_DIRECT_PORT must be between 1 and 65535")
        if self.request_timeout_ms <= 0 or self.max_body_bytes <= 0:
            raise ValueError("timeout and maximum body size must be positive")
        if self.reasoning_replay_max_chars <= 0:
            raise ValueError("CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS must be positive")
        if not 0 <= self.tool_input_retries <= 3:
            raise ValueError("CURSOR_DIRECT_TOOL_INPUT_RETRIES must be between 0 and 3")
        if self.session_keepalive_seconds <= 0 or self.session_max_entries <= 0:
            raise ValueError("Cursor session lifetime and entry count must be positive")
        if (
            min(self.response_cache_ttl, self.response_cache_entries, self.response_cache_bytes)
            <= 0
        ):
            raise ValueError("response cache TTL, entry count and maximum size must be positive")
        url = urlsplit(self.cursor_base_url)
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("CURSOR_DIRECT_BASE_URL must be an HTTP(S) origin")
        if self.proxy_url:
            proxy = urlsplit(self.proxy_url)
            if proxy.scheme not in {"socks5", "socks5h"} or not proxy.hostname:
                raise ValueError("CURSOR_DIRECT_PROXY_URL must be a SOCKS5 URL")

    @classmethod
    def from_env(cls, *, dotenv: bool = True) -> Config:
        if dotenv:
            load_dotenv(Path.cwd() / ".env", override=False)
        tools = os.getenv("CURSOR_ALLOWED_NATIVE_TOOLS", "mcp_tool_call").strip()
        return cls(
            host=os.getenv("CURSOR_DIRECT_HOST") or "127.0.0.1",
            port=_integer("CURSOR_DIRECT_PORT", 8790),
            api_key=os.getenv("CURSOR_DIRECT_API_KEY") or None,
            cursor_base_url=os.getenv("CURSOR_DIRECT_BASE_URL") or "https://api2.cursor.sh",
            proxy_url=os.getenv("CURSOR_DIRECT_PROXY_URL") or None,
            client_version=os.getenv("CURSOR_DIRECT_CLIENT_VERSION") or "cli-2026.08.11-e8db854",
            allowed_native_tools=(
                ()
                if tools == "*"
                else tuple(t.strip() for t in tools.split(",") if t.strip()) or ("mcp_tool_call",)
            ),
            # An explicitly empty prefix is meaningful.
            model_prefix=os.getenv("CURSOR_DIRECT_MODEL_PREFIX", ""),
            auth_file=Path(os.getenv("CURSOR_DIRECT_AUTH_FILE") or "accounts.json").expanduser(),
            request_timeout_ms=_integer("CURSOR_DIRECT_TIMEOUT_MS", 300_000),
            system_as_history=_boolean("CURSOR_DIRECT_SYSTEM_AS_HISTORY", True),
            continuation_prompt=os.getenv("CURSOR_DIRECT_CONTINUATION_PROMPT")
            or "Continue, using the tool results above.",
            replay_reasoning=_boolean("CURSOR_DIRECT_REPLAY_REASONING", True),
            reasoning_replay_max_chars=_integer("CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS", 12_000),
            tool_input_retries=_integer("CURSOR_DIRECT_TOOL_INPUT_RETRIES", 1),
            reuse_sessions=_boolean("CURSOR_DIRECT_REUSE_SESSIONS", True),
            session_keepalive_seconds=_integer("CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS", 300),
            session_max_entries=_integer("CURSOR_DIRECT_SESSION_MAX_ENTRIES", 8),
            log_requests=_boolean("CURSOR_DIRECT_LOG_REQUESTS", True),
            max_body_bytes=_integer("CURSOR_DIRECT_MAX_BODY_BYTES", 64 * 1024 * 1024),
            response_cache_ttl=_integer("CURSOR_DIRECT_RESPONSE_CACHE_TTL", 3600),
            response_cache_entries=_integer("CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES", 256),
            response_cache_bytes=_integer("CURSOR_DIRECT_RESPONSE_CACHE_BYTES", 128 * 1024 * 1024),
            compaction_key_file=(
                Path(os.environ["CURSOR_DIRECT_COMPACTION_KEY_FILE"]).expanduser()
                if os.getenv("CURSOR_DIRECT_COMPACTION_KEY_FILE")
                else None
            ),
        )
