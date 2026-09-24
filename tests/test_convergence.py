import pytest

from cursor_gateway.config import Config
from cursor_gateway.history_diagnostics import repeated_tool_result
from cursor_gateway.reasoning_replay import summary_notes
from cursor_gateway.tool_validation import custom_input_error

PATCH_FORMAT = {
    "type": "grammar",
    "syntax": "lark",
    "definition": (
        "start: begin_patch hunk+ end_patch\n"
        'begin_patch: "*** Begin Patch" LF\n'
        'end_patch: "*** End Patch" LF?\n'
    ),
}
PATCH = "*** Begin Patch\n*** Add File: hello.txt\n+hello\n*** End Patch"


def reasoning(text):
    return {"type": "reasoning", "summary": [{"type": "summary_text", "text": text}]}


def test_reasoning_budget_keeps_recent_notes_with_their_original_positions():
    items = [reasoning("old " * 1000), {"type": "message"}, reasoning("LATEST_MARKER")]
    notes = summary_notes(items, 300)
    assert sum(map(len, notes.values())) <= 300
    assert "LATEST_MARKER" in notes[2]
    assert "Earlier portion omitted" in notes[0]
    assert notes[0].endswith("old")
    assert "not a new instruction" in notes[2]
    assert 1 not in notes


def test_empty_reasoning_and_too_small_budget_do_not_create_empty_messages():
    assert summary_notes([reasoning("")], 1000) == {}
    assert summary_notes([reasoning("notes")], 1) == {}


@pytest.mark.parametrize("value", [PATCH, PATCH + "\n"])
def test_patch_input_is_validated_without_changing_it(value):
    args = {"input": value}
    assert custom_input_error(args, PATCH_FORMAT) is None
    assert args == {"input": value}


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({}, "input string"),
        ({"input": 12}, "input string"),
        ({"input": PATCH, "extra": True}, "exactly one argument"),
        ({"input": PATCH.replace("*** Begin Patch", "*** Begin Patch ***")}, "first line"),
        ({"input": PATCH.replace("*** End Patch", "*** End Patch ***")}, "last line"),
        ({"input": "*** Begin Patch\n*** End Patch"}, "at least one"),
        ({"input": "*** Begin Patch\nhello\n*** End Patch"}, "must start"),
    ],
)
def test_invalid_patch_feedback_is_precise(args, error):
    assert error in custom_input_error(args, PATCH_FORMAT)


def test_other_custom_grammars_and_functions_are_not_treated_as_patches():
    assert custom_input_error({"input": "not a patch"}, {"type": "text"}) is None
    assert (
        custom_input_error(
            {"input": "not a patch"},
            {"type": "grammar", "syntax": "lark", "definition": 'start: "hello"'},
        )
        is None
    )
    assert custom_input_error({"command": "echo hello"}, None) is None


def test_convergence_config_from_env(monkeypatch):
    monkeypatch.setenv("CURSOR_DIRECT_REPLAY_REASONING", "true")
    monkeypatch.setenv("CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS", "6000")
    monkeypatch.setenv("CURSOR_DIRECT_TOOL_INPUT_RETRIES", "2")
    config = Config.from_env(dotenv=False)
    assert config.replay_reasoning
    assert config.reasoning_replay_max_chars == 6000
    assert config.tool_input_retries == 2


@pytest.mark.parametrize(
    "options",
    [{"reasoning_replay_max_chars": 0}, {"tool_input_retries": -1}, {"tool_input_retries": 4}],
)
def test_convergence_options_are_bounded(options):
    with pytest.raises(ValueError):
        Config(**options)


def tool_round(index, output="same", *, namespace=None, args='{"cmd":"cat README.md"}', code=0):
    return [
        {
            "type": "function_call",
            "name": "exec_command",
            "namespace": namespace,
            "arguments": args,
            "call_id": str(index),
        },
        {
            "type": "function_call_output",
            "call_id": str(index),
            "output": (
                f"Chunk ID: {index}\nWall time: {index}.0 seconds\n"
                f"Process exited with code {code}\nOutput:\n{output}"
            ),
        },
    ]


def test_repeated_reads_are_diagnostic_only_and_ignore_volatile_terminal_headers():
    items = [item for index in range(3) for item in tool_round(index)]
    assert repeated_tool_result(items) == {
        "same_call_and_result_count": 3,
        "observed_tool_results": 3,
    }
    assert repeated_tool_result(items[:4]) is None
    # Once a new result arrives, earlier repetition must not keep triggering the signal.
    assert repeated_tool_result(items + tool_round(3, output="changed")) is None


@pytest.mark.parametrize(
    "options",
    [{"namespace": "other"}, {"args": '{"cmd":"cat other.md"}'}, {"code": 1}],
)
def test_repetition_distinguishes_tool_identity_input_and_exit_status(options):
    items = tool_round(1) + tool_round(2) + tool_round(3, **options)
    assert repeated_tool_result(items) is None
