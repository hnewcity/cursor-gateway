"""Server, browser PKCE login and local Cursor SQLite token import."""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from .auth import Account, AccountError, iso_date, jwt_claims, jwt_expiry, save_account
from .config import Config
from .transport import TransportError, h2_request


def default_db() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
    if sys.platform == "win32":
        return Path(os.getenv("APPDATA") or Path.home() / "AppData/Roaming") / (
            "Cursor/User/globalStorage/state.vscdb"
        )
    return Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config") / (
        "Cursor/User/globalStorage/state.vscdb"
    )


def import_local(db: Path, *, label: str | None = None) -> Account:
    if not db.is_file():
        raise AccountError(f"Cursor database not found: {db}")
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as connection:

        def read(key: str) -> str:
            row = connection.execute("SELECT value FROM ItemTable WHERE key = ?", (key,)).fetchone()
            if not row:
                return ""
            value = row[0]
            try:
                parsed = json.loads(value)
                if isinstance(parsed, str):
                    value = parsed
            except ValueError, TypeError:
                pass
            return str(value or "")

        access = read("cursorAuth/accessToken")
        refresh = read("cursorAuth/refreshToken")
        email = read("cursorAuth/cachedEmail")
    if not access:
        raise AccountError("no Cursor access token found; sign in to the Cursor desktop app first")
    expiry = jwt_expiry(access)
    return Account(
        label=label or email or "local",
        access_token=access,
        refresh_token=refresh or None,
        expires_at=iso_date(expiry) if expiry else None,
    )


def pkce_challenge() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


async def login(config: Config, *, label: str | None = None, timeout: float = 300) -> Account:
    verifier, challenge = pkce_challenge()
    attempt = str(uuid4())
    login_url = "https://www.cursor.com/loginDeepControl?" + urlencode(
        {
            "challenge": challenge,
            "uuid": attempt,
            "mode": "login",
            "redirectTarget": "cli",
        }
    )
    print("\nOpen this URL in a browser and approve the Cursor login:\n", flush=True)
    print(f"  {login_url}\n", flush=True)
    print(f"Waiting for approval ({timeout:g}s timeout)...", flush=True)
    path = "/auth/poll?" + urlencode({"uuid": attempt, "verifier": verifier})
    deadline, interval = time.monotonic() + timeout, 1.0
    while time.monotonic() < deadline:
        try:
            response = await h2_request(
                config.cursor_base_url,
                path,
                method="GET",
                proxy_url=config.proxy_url,
                timeout=min(20, max(0.01, deadline - time.monotonic())),
                headers={"accept": "application/json", "user-agent": "cursor-gateway/login"},
            )
            if 200 <= response.status < 300:
                data = json.loads(response.body or b"{}")
                if not isinstance(data, dict):
                    raise AccountError("login poll returned an invalid response")
                token = data.get("accessToken") or data.get("apiKey")
                if isinstance(token, str) and token:
                    claims = jwt_claims(token)
                    account_label = (
                        label
                        or claims.get("email")
                        or (str(data.get("authId", "")).split("|")[-1])
                        or "cursor"
                    )
                    expiry = jwt_expiry(token)
                    refresh = data.get("refreshToken")
                    return Account(
                        label=str(account_label),
                        access_token=token,
                        refresh_token=refresh if isinstance(refresh, str) else None,
                        expires_at=iso_date(expiry) if expiry else None,
                    )
            elif response.status not in {404, 408, 429} and response.status < 500:
                raise AccountError(f"login poll returned HTTP {response.status}")
        except TimeoutError, OSError, TransportError, ValueError:
            # Transient failures are retried within the same overall deadline.
            pass
        await asyncio.sleep(min(interval, max(0, deadline - time.monotonic())))
        interval = min(5, interval * 1.2)
    raise AccountError("login timed out before approval")


def _print_saved(file: Path, account: Account, count: int) -> None:
    print(f"\nWrote {file} (mode 0600)")
    print(f"  label:    {account.label}")
    print(f"  expires:  {account.expires_at or 'unknown'}")
    print(f"  refresh:  {'present' if account.refresh_token else 'missing; no automatic renewal'}")
    print(f"  accounts: {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Python gateway for the Cursor agent API")
    parser.add_argument("--version", action="version", version="cursor-gateway 0.1.0")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="start the OpenAI-compatible server (default)")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    browser_login = commands.add_parser("login", help="sign in via the Cursor browser PKCE flow")
    browser_login.add_argument("--proxy", help="SOCKS5 egress for login polling")
    browser_login.add_argument("--timeout", type=float, default=300)
    local = commands.add_parser(
        "import-local", help="import tokens from Cursor's local SQLite store"
    )
    local.add_argument("--db", type=Path, default=default_db())
    for command in (browser_login, local):
        command.add_argument(
            "--out", type=Path, help="account JSON path (defaults to configured file)"
        )
        command.add_argument("--label")
        command.add_argument(
            "--merge", action="store_true", help="replace this label, keep other accounts"
        )
    args = parser.parse_args(argv)
    try:
        config = Config.from_env()
        if args.command in {"login", "import-local"}:
            if args.command == "login":
                if args.timeout <= 0:
                    raise ValueError("--timeout must be positive")
                if args.proxy:
                    config = replace(config, proxy_url=args.proxy)
                account = asyncio.run(login(config, label=args.label, timeout=args.timeout))
            else:
                account = import_local(args.db.expanduser(), label=args.label)
            file = (args.out or config.auth_file).expanduser()
            count = save_account(file, account, merge=args.merge)
            _print_saved(file, account, count)
        else:
            import uvicorn

            from .server import create_app

            level = getattr(args, "log_level", "info")
            logging.basicConfig(
                level=level.upper(),
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            )
            config = replace(
                config,
                host=getattr(args, "host", None) or config.host,
                port=getattr(args, "port", None) or config.port,
            )
            uvicorn.run(
                create_app(config),
                host=config.host,
                port=config.port,
                log_level=level,
                access_log=config.log_requests,
            )
    except KeyboardInterrupt:
        return 130
    except (AccountError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
