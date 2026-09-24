#!/usr/bin/env python3.14
"""Start Codex with gateway-compatible model metadata; preserve the user's normal config."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def model_catalog(model: str, context_window: int = 65_536, *, images: bool = True) -> dict:
    """These are client capabilities/budgets, not claims about a model's native limits."""
    return {
        "models": [
            {
                "slug": model,
                "display_name": model,
                "description": "Cursor Gateway coding model",
                "default_reasoning_level": "medium",
                "supported_reasoning_levels": [
                    {"effort": level, "description": f"{level} (upstream model controls reasoning)"}
                    for level in ("low", "medium", "high")
                ],
                "shell_type": "unified_exec",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 0,
                "availability_nux": None,
                "upgrade": None,
                "base_instructions": (
                    "You are a coding assistant. Follow the user's instructions, "
                    "inspect the project, "
                    "use the provided tools to implement changes, and verify the results. "
                    "Preserve existing user work. Use apply_patch for file edits. "
                    "Respect the client's permissions and approval requirements."
                ),
                "supports_reasoning_summary_parameter": True,
                "support_verbosity": True,
                "default_verbosity": "medium",
                "apply_patch_tool_type": "freeform",
                "truncation_policy": {"mode": "tokens", "limit": 10000},
                "context_window": context_window,
                "auto_compact_token_limit": context_window * 3 // 4,
                "effective_context_window_percent": 95,
                "experimental_supported_tools": [],
                "input_modalities": ["text", "image"] if images else ["text"],
                "supports_search_tool": True,
            }
        ]
    }


def config_args(base_url: str, model: str, catalog: Path, *, api_key: bool) -> list[str]:
    values = {
        "model": model,
        "model_provider": "cursor_gateway",
        "model_catalog_json": str(catalog),
        "model_providers.cursor_gateway.name": "Cursor Gateway",
        "model_providers.cursor_gateway.base_url": base_url,
        "model_providers.cursor_gateway.wire_api": "responses",
        "model_providers.cursor_gateway.requires_openai_auth": False,
        "model_providers.cursor_gateway.supports_websockets": False,
        "model_providers.cursor_gateway.stream_idle_timeout_ms": 360000,
        "model_providers.cursor_gateway.request_max_retries": 2,
        "model_providers.cursor_gateway.stream_max_retries": 2,
        # Search runs through Cursor's native hosted search protocol.
        "web_search": "live",
    }
    if api_key:
        values["model_providers.cursor_gateway.env_key"] = "CURSOR_DIRECT_API_KEY"
    return [
        part
        for key, value in values.items()
        for part in ("-c", f"{key}={json.dumps(value, ensure_ascii=False)}")
    ]


def codex_command(codex: str, forwarded: list[str], overrides: list[str]) -> list[str]:
    """Put overrides on the innermost command, including `exec ... resume`."""
    value_options = {
        "-c",
        "--config",
        "-C",
        "--cd",
        "-s",
        "--sandbox",
        "-m",
        "--model",
        "-p",
        "--profile",
        "--color",
        "-o",
        "--output-last-message",
        "--output-schema",
        "--add-dir",
        "--thread-source",
        "--enable",
        "--disable",
    }
    index, insert = 0, 0
    while index < len(forwarded):
        arg = forwarded[index]
        if arg == "--":
            break
        if arg in value_options:
            index += 2
            continue
        if arg in ("-i", "--image"):
            index += 1
            while index < len(forwarded) and not forwarded[index].startswith("-"):
                index += 1
            continue
        if arg.startswith("-"):
            index += 1
            continue
        if arg in ("exec", "e", "resume", "fork", "review"):
            insert = index + 1
            index += 1
            if arg not in ("exec", "e"):
                break
            continue
        break  # A prompt or a non-generation subcommand.
    return [codex, *forwarded[:insert], *overrides, *forwarded[insert:]]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch Codex using Cursor Gateway. Pass Codex options after --."
    )
    parser.add_argument("--url", default=os.getenv("GATEWAY_URL", "http://127.0.0.1:8790"))
    parser.add_argument("--model", default=os.getenv("GATEWAY_MODEL", "default"))
    parser.add_argument(
        "--context-window",
        type=int,
        default=65_536,
        help="client context budget, not a verified model limit (default: 65536)",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="hide image tools for a model that does not support vision",
    )
    parser.add_argument("codex_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or (url.username or url.password or url.query or url.fragment)
    ):
        parser.error("--url must be an HTTP(S) URL without credentials, query or fragment")
    if not args.model.strip() or args.context_window < 4096:
        parser.error("--model must be non-empty and --context-window must be at least 4096")
    codex = shutil.which("codex")
    if codex is None:
        parser.error("codex was not found on PATH")
    base_url = args.url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    forwarded = args.codex_args
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    with tempfile.TemporaryDirectory(prefix="cursor-gateway-codex-") as directory:
        catalog = Path(directory) / "models.json"
        catalog.write_text(
            json.dumps(
                model_catalog(
                    args.model,
                    args.context_window,
                    images=not args.text_only,
                ),
                ensure_ascii=False,
            )
        )
        print(
            f"Gateway: {base_url}\nModel: {args.model}\n"
            f"Client context budget: {args.context_window}",
            file=sys.stderr,
            flush=True,
        )
        overrides = config_args(
            base_url, args.model, catalog, api_key=bool(os.getenv("CURSOR_DIRECT_API_KEY"))
        )
        # --ignore-user-config discards overrides parsed by a parent command.
        command = codex_command(codex, forwarded, overrides)
        try:
            return subprocess.call(command)
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
