import pytest

from cursor_gateway.config import Config
from cursor_gateway.models import FALLBACK_MODEL_IDS, to_model_list, upstream_id


def test_model_prefix_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("CURSOR_DIRECT_MODEL_PREFIX", raising=False)
    assert Config().model_prefix == ""
    assert Config.from_env(dotenv=False).model_prefix == ""
    monkeypatch.setenv("CURSOR_DIRECT_MODEL_PREFIX", "gateway-")
    assert Config.from_env(dotenv=False).model_prefix == "gateway-"
    monkeypatch.setenv("CURSOR_DIRECT_MODEL_PREFIX", "")
    assert Config.from_env(dotenv=False).model_prefix == ""


@pytest.mark.parametrize(
    ("prefix", "expected", "gpt_upstream"),
    [
        ("", ["auto", "gpt-5.2", "grok-4.6-medium"], "gpt-5.2"),
        (
            "cursor-",
            ["cursor-auto", "cursor-gpt-5.2", "cursor-grok-4.6-medium"],
            "cursor-gpt-5.2",
        ),
        ("gateway-", ["gateway-auto", "gateway-gpt-5.2", "gateway-grok-4.6-medium"], "gpt-5.2"),
    ],
)
def test_listed_models_deduplicate_aliases_and_resolve_to_upstream(prefix, expected, gpt_upstream):
    known = ["auto", "gpt-5.2", "cursor-grok-4.6-medium", "gpt-5.2", "cursor-gpt-5.2"]
    models = to_model_list(known, prefix)
    assert [model["id"] for model in models] == expected
    assert [upstream_id(model["id"], prefix, known) for model in models] == [
        "auto",
        gpt_upstream,
        "cursor-grok-4.6-medium",
    ]
    assert all(model["object"] == "model" and model["owned_by"] == "cursor" for model in models)


@pytest.mark.parametrize(
    ("name", "prefix", "known", "expected"),
    [
        ("grok", "", ["cursor-grok"], "cursor-grok"),
        ("cursor-grok", "", ["cursor-grok"], "cursor-grok"),
        ("cursor-auto", "", ["auto"], "auto"),
        (" auto ", "", ["auto"], "auto"),
        ("gateway-grok", "gateway-", ["cursor-grok"], "cursor-grok"),
        ("gateway-cursor-grok", "gateway-", ["cursor-grok"], "cursor-grok"),
        ("cursor-grok", "gateway-", ["grok"], "grok"),
        ("grok", "cursor-", ["cursor-grok"], "cursor-grok"),
        ("cursor-auto", "cursor-", ["auto"], "auto"),
        ("grok", "", ["cursor-grok", "grok"], "grok"),
        ("cursor-grok", "", ["grok", "cursor-grok"], "cursor-grok"),
        ("new-model", "", [], "new-model"),
        ("cursor-new-model", "", [], "new-model"),
        ("gateway-new-model", "gateway-", [], "new-model"),
    ],
)
def test_model_alias_resolution(name, prefix, known, expected):
    assert upstream_id(name, prefix, known) == expected


def test_fallback_models_are_prefix_free_and_keep_native_upstream_ids():
    models = to_model_list(list(FALLBACK_MODEL_IDS), "")
    assert all(not model["id"].startswith("cursor-") for model in models)
    assert upstream_id("grok-4.6-medium", "", FALLBACK_MODEL_IDS) == "cursor-grok-4.6-medium"
