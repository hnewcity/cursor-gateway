#!/usr/bin/env python3.14
"""单文件导出工具，只需 Python 标准库，无需安装 cursor-gateway。

macOS / Linux: python3.14 export_cursor_credentials.py
Windows:       py -3.14 export_cursor_credentials.py

自动读取当前用户的 Cursor CLI 或桌面版登录，保存到脚本旁的 accounts.json。
文件含账号访问凭据，接收人可使用该账号；脚本不会联网或自动发送文件。
"""

import argparse
import base64
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def token_text(value: object) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str):
        return ""
    value = value.strip()
    # Desktop SQLite values can be plain strings or JSON-encoded strings.
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
            value = decoded.strip() if isinstance(decoded, str) else ""
        except ValueError:
            return ""
    if value in {"null", "undefined", "None"}:
        return ""
    try:
        value.encode("utf-8")
    except UnicodeError:
        return ""
    return value


def expires_at(token: str) -> float | None:
    try:
        encoded = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        value = claims.get("exp") if isinstance(claims, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            datetime.fromtimestamp(value, UTC)
            return float(value)
    except ValueError, IndexError, OverflowError, OSError:
        pass
    return None


def make_account(access: object, refresh: object, label: str) -> dict | None:
    access, refresh = token_text(access), token_text(refresh)
    if not access:
        return None
    account = {"label": label, "accessToken": access}
    if refresh:
        account["refreshToken"] = refresh
    expiry = expires_at(access)
    if expiry is not None:
        account["expiresAt"] = (
            datetime.fromtimestamp(expiry, UTC).isoformat().replace("+00:00", "Z")
        )
    return account


def keychain_token(service: str) -> str:
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-a", "cursor-user", "-s", service, "-w"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode == 44:  # errSecItemNotFound
        return ""
    if result.returncode:
        raise OSError("keychain access unavailable")
    return result.stdout.strip()


def cli_paths(home: Path, platform: str, env: dict) -> list[Path]:
    if platform == "darwin":
        return [home / ".cursor/auth.json"]
    if platform == "win32":
        base = Path(env.get("APPDATA") or home / "AppData/Roaming")
        return [base / "Cursor/auth.json", home / ".cursor/auth.json"]
    base = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    return list(dict.fromkeys([base / "cursor/auth.json", home / ".cursor/auth.json"]))


def desktop_path(home: Path, platform: str, env: dict) -> Path:
    if platform == "darwin":
        base = home / "Library/Application Support"
    elif platform == "win32":
        base = Path(env.get("APPDATA") or home / "AppData/Roaming")
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    return base / "Cursor/User/globalStorage/state.vscdb"


def read_cli(path: Path) -> dict | None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return None
    return make_account(data.get("accessToken"), data.get("refreshToken"), "cursor-cli")


def read_desktop(path: Path) -> dict | None:
    # Read the live database, including its WAL; never change the login database.
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
        values = dict(
            db.execute(
                "SELECT key, value FROM ItemTable WHERE key IN (?, ?)",
                ("cursorAuth/accessToken", "cursorAuth/refreshToken"),
            ).fetchall()
        )
    return make_account(
        values.get("cursorAuth/accessToken"),
        values.get("cursorAuth/refreshToken"),
        "cursor-desktop",
    )


def discover(
    *, source: str, home: Path, platform: str, env: dict, db: Path | None = None
) -> tuple[dict | None, str, list[str]]:
    candidates = []
    notes = []
    if source != "desktop" and db is None:
        if platform == "darwin" and env.get("AGENT_CLI_CREDENTIAL_STORE") != "file":
            try:
                access = keychain_token("cursor-access-token")
                refresh = ""
                if access:
                    try:
                        refresh = keychain_token("cursor-refresh-token")
                    except OSError, subprocess.TimeoutExpired:
                        notes.append("CLI 刷新凭据未能读取，本次仅尝试使用访问凭据。")
                account = make_account(access, refresh, "cursor-cli")
                if account:
                    candidates.append((account, "Cursor CLI（macOS 钥匙串）"))
            except OSError, subprocess.TimeoutExpired:
                notes.append("未能读取 macOS 钥匙串；若系统弹出授权提示，请允许后重试。")
        for path in cli_paths(home, platform, env):
            if not path.is_file():
                continue
            try:
                account = read_cli(path)
                if account:
                    candidates.append((account, "Cursor CLI（登录文件）"))
            except OSError, ValueError:
                notes.append("CLI 登录文件无法读取，请重新登录 Cursor CLI 后再试。")
    if source != "cli" or db is not None:
        path = db or desktop_path(home, platform, env)
        if path.is_file():
            try:
                account = read_desktop(path)
                if account:
                    candidates.append((account, "Cursor 桌面版"))
            except OSError, ValueError, sqlite3.Error:
                notes.append("桌面版登录数据库无法读取，请退出 Cursor 后再运行一次。")

    # Prefer a currently valid login. An expired token with a refresh token remains exportable.
    def rank(item):
        account = item[0]
        expiry = expires_at(account["accessToken"])
        return (
            expiry is None or expiry > time.time(),
            bool(account.get("refreshToken")),
            expiry or 0,
        )

    candidates.sort(key=rank, reverse=True)
    for account, label in candidates:
        expiry = expires_at(account["accessToken"])
        if expiry is not None and expiry <= time.time() and not account.get("refreshToken"):
            notes.append(f"{label}的登录已过期且没有刷新凭据，请重新登录后再试。")
            continue
        return account, label, notes
    return None, "", notes


def save(path: Path, account: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # O_EXCL also rejects symlinks: never overwrite an existing credential or login file.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump([account], output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="导出自己的 Cursor CLI / 桌面版登录凭据到本地文件。"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().with_name("accounts.json"),
        help="输出文件，默认在脚本旁生成 accounts.json；不覆盖已有文件",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "cli", "desktop"],
        default="auto",
        help="默认自动选择一份可用登录；也可指定 cli 或 desktop",
    )
    parser.add_argument("--db", type=Path, help="桌面版使用自定义数据目录时，指定 state.vscdb 路径")
    args = parser.parse_args(argv)
    path = args.out.expanduser().absolute()
    print("Cursor 登录凭据导出工具")
    print("导出的文件包含账号凭据，接收人可使用你的 Cursor 账号；仅本地保存，不会自动发送。\n")
    if path.exists() or path.is_symlink():
        print("输出文件已存在，未覆盖。请移走旧文件，或用 --out 指定其他文件。", file=sys.stderr)
        return 1
    if args.db and args.source == "cli":
        parser.error("--db 只能用于桌面版，不能与 --source cli 一起使用")
    account, label, notes = discover(
        source=args.source,
        home=Path.home(),
        platform=sys.platform,
        env=dict(os.environ),
        db=args.db.expanduser() if args.db else None,
    )
    if not account:
        print("未找到可导出的登录。先登录 Cursor 桌面版或运行 cursor-agent login，再重试。")
        print("请在你登录 Cursor 的同一个系统用户下运行；自定义桌面目录可用 --db 指定。")
        for note in dict.fromkeys(notes):
            print(f"  {note}")
        return 1
    try:
        save(path, account)
    except FileExistsError:
        print("输出文件已存在，未覆盖。请用 --out 指定其他文件。", file=sys.stderr)
        return 1
    except OSError:
        print("无法写入文件，请将脚本放在下载或桌面目录后重试。", file=sys.stderr)
        return 1
    print(f"导出成功！来源：{label}")
    print(f"文件：{path}")
    print(
        "刷新凭据：" + ("已包含" if account.get("refreshToken") else "未找到，到期后需要重新导出")
    )
    print("\n将这个 accounts.json 文件交给你信任的接收人即可，不用复制终端内容。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        raise SystemExit(130) from None
