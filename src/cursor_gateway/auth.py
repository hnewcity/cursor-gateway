"""Reloadable account pool, serialized token refresh and private atomic storage."""

import asyncio
import base64
import json
import logging
import math
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .transport import h2_request

log = logging.getLogger(__name__)
REFRESH_SKEW_SECONDS = 30 * 60


class AccountError(Exception):
    pass


def jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return value if isinstance(value, dict) else {}
    except IndexError, ValueError, UnicodeError:
        return {}


def jwt_expiry(token: str) -> float | None:
    value = jwt_claims(token).get("exp")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def iso_date(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def parse_date(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=UTC).timestamp() if dt.tzinfo is None else dt.timestamp()
    except ValueError, TypeError, OverflowError:
        return None


@dataclass(slots=True)
class Account:
    label: str
    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: str | None = None
    disabled_until: str | None = None
    last_error: str | None = None

    @property
    def disabled(self) -> bool:
        return (parse_date(self.disabled_until) or 0) > time.time()

    def to_dict(self) -> dict:
        value = {"label": self.label, "accessToken": self.access_token}
        for key, item in (
            ("refreshToken", self.refresh_token),
            ("expiresAt", self.expires_at),
            ("disabledUntil", self.disabled_until),
            ("lastError", self.last_error),
        ):
            if item is not None:
                value[key] = item
        return value


def read_accounts(file: Path) -> list[Account]:
    try:
        parsed = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except OSError, ValueError:
        raise AccountError(f"cannot read valid account JSON from {file}") from None
    rows = parsed.get("accounts", []) if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list):
        raise AccountError("account file must contain an array or an accounts array")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        token = row.get("accessToken")
        if not isinstance(token, str) or not token.strip():
            continue
        out.append(
            Account(
                label=str(row.get("label") or f"account-{len(out) + 1}"),
                access_token=token.strip(),
                refresh_token=row.get("refreshToken")
                if isinstance(row.get("refreshToken"), str)
                else None,
                expires_at=row.get("expiresAt") if isinstance(row.get("expiresAt"), str) else None,
                disabled_until=(
                    row.get("disabledUntil") if isinstance(row.get("disabledUntil"), str) else None
                ),
                last_error=row.get("lastError") if isinstance(row.get("lastError"), str) else None,
            )
        )
    return out


def write_accounts(file: Path, accounts: list[Account]) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{file.name}.", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump([a.to_dict() for a in accounts], stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_account(file: Path, account: Account, *, merge: bool = False) -> int:
    existing = read_accounts(file) if merge else []
    accounts = [item for item in existing if item.label != account.label] + [account]
    write_accounts(file, accounts)
    return len(accounts)


async def exchange_refresh_token(refresh: str, config: Config) -> tuple[str, str | None]:
    response = await h2_request(
        config.cursor_base_url,
        "/auth/exchange_user_api_key",
        proxy_url=config.proxy_url,
        body=b"{}",
        headers={
            "authorization": f"Bearer {refresh}",
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    if not 200 <= response.status < 300:
        raise AccountError(f"token refresh returned HTTP {response.status}")
    try:
        data = json.loads(response.body)
    except ValueError:
        raise AccountError("token refresh returned invalid JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("accessToken"), str):
        raise AccountError("token refresh response has no accessToken")
    if not data["accessToken"].strip():
        raise AccountError("token refresh returned an empty accessToken")
    return data["accessToken"], data.get("refreshToken")


class AccountPool:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.file = config.auth_file
        self.accounts: list[Account] = []
        self.cursor = 0
        self._signature: tuple[int, int, int] | None = None
        self._lock = asyncio.Lock()
        self.reload()

    def reload(self) -> None:
        try:
            stat = self.file.stat()
        except FileNotFoundError:
            self.accounts = []
            self._signature = None
            return
        signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        if signature == self._signature:
            return
        accounts = read_accounts(self.file)
        # Keep transient cooldowns while a token refresh writes the file.
        cooldowns = {a.access_token: a for a in self.accounts if a.disabled}
        for account in accounts:
            old = cooldowns.get(account.access_token)
            if old and not account.disabled_until:
                account.disabled_until, account.last_error = old.disabled_until, old.last_error
        self.accounts, self._signature = accounts, signature
        log.info("loaded %d Cursor account(s)", len(accounts))

    def size(self) -> int:
        self.reload()
        return sum(not account.disabled for account in self.accounts)

    async def next(self) -> Account:
        async with self._lock:
            self.reload()
            healthy = [account for account in self.accounts if not account.disabled]
            if not healthy:
                raise AccountError(
                    "all Cursor accounts are in cooldown"
                    if self.accounts
                    else "no Cursor account configured; run cursor-gateway login or import-local"
                )
            account = healthy[self.cursor % len(healthy)]
            self.cursor += 1
            return await self._ensure_fresh(account)

    async def _ensure_fresh(self, account: Account) -> Account:
        expiry = parse_date(account.expires_at) or jwt_expiry(account.access_token)
        if expiry and expiry - time.time() > REFRESH_SKEW_SECONDS:
            return account
        if not account.refresh_token:
            return account
        try:
            access, refresh = await exchange_refresh_token(account.refresh_token, self.config)
        except Exception as exc:
            # Do not log tokens or response bodies. The original token may still work.
            log.warning("token refresh failed for %s (%s)", account.label, type(exc).__name__)
            return account
        original_token = account.access_token
        # Respect edits made while the refresh network request was in progress.
        self.reload()
        target = next(
            (
                a
                for a in self.accounts
                if a.label == account.label and a.access_token == original_token
            ),
            None,
        )
        if target is None:
            raise AccountError("account file changed during refresh; retry the request")
        target.access_token = access
        if isinstance(refresh, str) and refresh:
            target.refresh_token = refresh
        target.expires_at = iso_date(jwt_expiry(access) or time.time() + 55 * 60)
        write_accounts(self.file, self.accounts)
        stat = self.file.stat()
        self._signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        log.info("refreshed account %s", target.label)
        return target

    def mark_failure(self, account: Account, error: str, cooldown: float = 60) -> None:
        for target in self.accounts:
            if target.access_token == account.access_token:
                target.disabled_until = iso_date(time.time() + cooldown)
                target.last_error = error

    def mark_success(self, account: Account) -> None:
        for target in self.accounts:
            if target.access_token == account.access_token:
                target.disabled_until = None
                target.last_error = None
