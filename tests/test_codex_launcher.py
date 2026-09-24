import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "gateway_launcher", Path(__file__).resolve().parents[1] / "scripts/run_codex.py"
)
LAUNCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHER)


@pytest.mark.parametrize(
    ("args", "at"),
    [
        (["exec", "--ignore-user-config", "hello"], 1),
        (["exec", "resume", "--ignore-user-config", "session", "hello"], 2),
        (
            [
                "exec",
                "-C",
                "/project",
                "--sandbox",
                "workspace-write",
                "resume",
                "--ignore-user-config",
                "session",
                "hello",
            ],
            6,
        ),
        (["-c", 'model="review"', "exec", "--ignore-user-config", "hello"], 3),
        (["exec", "review", "--uncommitted"], 2),
        (["exec", "--", "resume"], 1),
        (["--help"], 0),
    ],
)
def test_provider_overrides_survive_ignore_user_config(args, at):
    overrides = ["-c", 'model_provider="cursor_gateway"']
    command = LAUNCHER.codex_command("codex", args, overrides)
    assert command == ["codex", *args[:at], *overrides, *args[at:]]
