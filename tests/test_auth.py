import asyncio
import base64
import json
import os
import sqlite3
import time

import pytest

from cursor_gateway.auth import (
    Account,
    AccountError,
    AccountPool,
    iso_date,
    jwt_expiry,
    read_accounts,
    save_account,
    write_accounts,
)
from cursor_gateway.cli import import_local, main
from cursor_gateway.config import Config


def token(expiry):
    claims = base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


async def test_round_robin_hot_reload_and_cooldown(tmp_path):
    file = tmp_path / "accounts.json"
    write_accounts(file, [Account("a", "a"), Account("b", "b")])
    pool = AccountPool(Config(auth_file=file))
    assert [(await pool.next()).label for _ in range(3)] == ["a", "b", "a"]
    pool.mark_failure(pool.accounts[1], "quota")
    assert pool.size() == 1
    assert (await pool.next()).label == "a"
    pool.mark_failure(pool.accounts[0], "quota")
    with pytest.raises(AccountError, match="cooldown"):
        await pool.next()
    write_accounts(file, [Account("c", "c")])
    assert (await pool.next()).label == "c"


async def test_refresh_is_serialized_and_private(tmp_path, monkeypatch):
    file = tmp_path / "accounts.json"
    old, new = token(time.time() + 10), token(time.time() + 7200)
    write_accounts(file, [Account("test", old, "refresh")])
    calls = []

    async def exchange(refresh, config):
        calls.append(refresh)
        await asyncio.sleep(0.01)
        return new, "new-refresh"

    monkeypatch.setattr("cursor_gateway.auth.exchange_refresh_token", exchange)
    pool = AccountPool(Config(auth_file=file))
    selected = await asyncio.gather(*(pool.next() for _ in range(5)))
    assert calls == ["refresh"]
    assert all(account.access_token == new for account in selected)
    assert read_accounts(file)[0].refresh_token == "new-refresh"
    assert os.stat(file).st_mode & 0o777 == 0o600


async def test_refresh_preserves_concurrent_account_file_edits(tmp_path, monkeypatch):
    file = tmp_path / "accounts.json"
    write_accounts(file, [Account("a", token(time.time()), "refresh")])

    async def exchange(refresh, config):
        write_accounts(file, [Account("replacement", "other")])
        return token(time.time() + 7200), None

    monkeypatch.setattr("cursor_gateway.auth.exchange_refresh_token", exchange)
    pool = AccountPool(Config(auth_file=file))
    with pytest.raises(AccountError, match="changed"):
        await pool.next()
    assert read_accounts(file)[0].label == "replacement"


async def test_bad_file_does_not_silently_replace_pool(tmp_path):
    file = tmp_path / "accounts.json"
    write_accounts(file, [Account("a", "a")])
    pool = AccountPool(Config(auth_file=file))
    file.write_text("invalid")
    with pytest.raises(AccountError):
        await pool.next()
    assert pool.accounts[0].label == "a"


def test_store_merge_object_format_and_no_token_in_repr(tmp_path):
    file = tmp_path / "nested/accounts.json"
    save_account(file, Account("a", "secret-a"))
    save_account(file, Account("b", "secret-b"), merge=True)
    save_account(file, Account("a", "new-secret"), merge=True)
    assert [a.label for a in read_accounts(file)] == ["b", "a"]
    file.write_text(json.dumps({"accounts": [{"accessToken": "token"}]}))
    assert read_accounts(file)[0].label == "account-1"
    assert "secret" not in repr(Account("a", "secret-a", "secret-refresh"))
    assert jwt_expiry("broken") is None
    assert iso_date(0).startswith("1970")


def test_local_import_uses_sqlite_and_cli_never_prints_token(tmp_path, capsys):
    db = tmp_path / "state.vscdb"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        connection.executemany(
            "INSERT INTO ItemTable VALUES (?, ?)",
            [
                ("cursorAuth/accessToken", json.dumps("secret-access")),
                ("cursorAuth/refreshToken", "secret-refresh"),
                ("cursorAuth/cachedEmail", "example@example.com"),
            ],
        )
    assert import_local(db).access_token == "secret-access"
    out = tmp_path / "accounts.json"
    assert main(["import-local", "--db", str(db), "--out", str(out)]) == 0
    captured = capsys.readouterr()
    assert "secret-access" not in captured.out
    assert "secret-refresh" not in captured.out
    assert read_accounts(out)[0].label == "example@example.com"
