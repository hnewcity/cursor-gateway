"""The standalone exporter is tested with synthetic credentials, never a real keychain."""

import base64
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cursor_gateway.auth import read_accounts

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export_cursor_credentials.py"
spec = importlib.util.spec_from_file_location("credential_export", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def jwt(expiry):
    claims = base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


def desktop_file(home, platform, env=None, *, access="desktop-access", refresh="desktop-refresh"):
    path = exporter.desktop_path(home, platform, env or {})
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
        db.executemany(
            "INSERT INTO ItemTable VALUES (?, ?)",
            [
                ("cursorAuth/accessToken", json.dumps(access)),
                ("cursorAuth/refreshToken", refresh),
                ("unrelatedSecret", "do-not-export"),
            ],
        )
    return path


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
async def test_cli_auth_file_all_platforms_and_gateway_format(tmp_path, platform, monkeypatch):
    monkeypatch.setattr(exporter, "keychain_token", lambda _: "")
    env = {"APPDATA": str(tmp_path / "roaming"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    file = exporter.cli_paths(tmp_path, platform, env)[0]
    file.parent.mkdir(parents=True)
    file.write_text(
        json.dumps(
            {
                "accessToken": "cli-access",
                "refreshToken": "cli-refresh",
                "apiKey": "do-not-export",
                "bedrockCredentials": {"secret": "do-not-export"},
            }
        )
    )
    account, label, _ = exporter.discover(source="auto", home=tmp_path, platform=platform, env=env)
    out = tmp_path / "accounts.json"
    exporter.save(out, account)
    assert "CLI" in label
    assert read_accounts(out)[0].access_token == "cli-access"
    assert read_accounts(out)[0].refresh_token == "cli-refresh"
    assert "do-not-export" not in out.read_text()
    if os.name != "nt":
        assert out.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_desktop_fallback_is_readonly(tmp_path, platform, monkeypatch):
    monkeypatch.setattr(exporter, "keychain_token", lambda _: "")
    path = desktop_file(tmp_path, platform)
    before = path.read_bytes()
    account, label, _ = exporter.discover(
        source="auto",
        home=tmp_path,
        platform=platform,
        env={},
    )
    assert account == {
        "label": "cursor-desktop",
        "accessToken": "desktop-access",
        "refreshToken": "desktop-refresh",
    }
    assert label == "Cursor 桌面版"
    assert before == path.read_bytes()


def test_macos_keychain_only_requests_cursor_login_tokens(tmp_path, monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert kwargs["capture_output"]
        value = "cli-access" if command[-2] == "cursor-access-token" else "cli-refresh"
        return subprocess.CompletedProcess(command, 0, value + "\n", "")

    monkeypatch.setattr(exporter.subprocess, "run", run)
    account, _, _ = exporter.discover(source="cli", home=tmp_path, platform="darwin", env={})
    assert account["refreshToken"] == "cli-refresh"
    assert commands == [
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            "cursor-user",
            "-s",
            "cursor-access-token",
            "-w",
        ],
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            "cursor-user",
            "-s",
            "cursor-refresh-token",
            "-w",
        ],
    ]


def test_keychain_denial_does_not_block_desktop_or_print_secret(tmp_path, monkeypatch):
    desktop_file(tmp_path, "darwin")

    def denied(_):
        raise OSError("private-keychain-detail")

    monkeypatch.setattr(exporter, "keychain_token", denied)
    account, _, notes = exporter.discover(source="auto", home=tmp_path, platform="darwin", env={})
    assert account["accessToken"] == "desktop-access"
    assert notes and "private-keychain-detail" not in str(notes)


def test_expired_login_falls_back_to_valid_desktop(tmp_path):
    path = exporter.cli_paths(tmp_path, "linux", {})[0]
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"accessToken": jwt(time.time() - 3600)}))
    desktop_file(tmp_path, "linux", access=jwt(time.time() + 3600))
    account, label, _ = exporter.discover(source="auto", home=tmp_path, platform="linux", env={})
    assert label == "Cursor 桌面版" and account["expiresAt"].endswith("Z")


def test_expired_token_requires_refresh_to_export(tmp_path):
    path = desktop_file(tmp_path, "linux", access=jwt(0), refresh="")
    account, _, notes = exporter.discover(source="desktop", home=tmp_path, platform="linux", env={})
    assert account is None and any("过期" in note for note in notes)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE ItemTable SET value = ? WHERE key = ?", ("refresh", "cursorAuth/refreshToken")
        )
    account, _, _ = exporter.discover(source="desktop", home=tmp_path, platform="linux", env={})
    assert account["refreshToken"] == "refresh"


def test_invalid_cli_json_falls_back_and_file_store_does_not_read_keychain(tmp_path, monkeypatch):
    path = exporter.cli_paths(tmp_path, "darwin", {})[0]
    path.parent.mkdir(parents=True)
    path.write_text("invalid-json")
    desktop_file(tmp_path, "darwin")

    def unexpected(_):
        pytest.fail("explicit file store must not read the keychain")

    monkeypatch.setattr(exporter, "keychain_token", unexpected)
    account, _, _ = exporter.discover(
        source="auto",
        home=tmp_path,
        platform="darwin",
        env={"AGENT_CLI_CREDENTIAL_STORE": "file"},
    )
    assert account["label"] == "cursor-desktop"


def test_standalone_process_export_is_simple_and_never_prints_tokens(tmp_path):
    # Copy just the script into an unrelated directory; project imports are unavailable.
    copied = tmp_path / SCRIPT.name
    copied.write_bytes(SCRIPT.read_bytes())
    db = desktop_file(tmp_path, "linux")
    result = subprocess.run(
        [sys.executable, "-I", str(copied), "--db", str(db)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "导出成功" in result.stdout
    assert "desktop-access" not in result.stdout + result.stderr
    assert "desktop-refresh" not in result.stdout + result.stderr
    out = tmp_path / "accounts.json"
    assert read_accounts(out)[0].access_token == "desktop-access"
    before = out.read_bytes()
    again = subprocess.run(
        [sys.executable, "-I", str(copied), "--db", str(db)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert again.returncode == 1 and "未覆盖" in again.stderr
    assert out.read_bytes() == before


def test_no_login_does_not_create_an_empty_export(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(exporter.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(exporter, "keychain_token", lambda _: "")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    out = tmp_path / "accounts.json"
    assert exporter.main(["--out", str(out)]) == 1
    assert not out.exists()
    assert "未找到可导出" in capsys.readouterr().out
