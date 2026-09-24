"""Normalize Responses inputs and tools for the existing Cursor turn translator."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .compaction import COMPACTION_PROMPT, CompactionCodec
from .config import Config
from .diagnostics import event
from .history_diagnostics import repeated_tool_result
from .images import image_url, selected_image
from .output_format import OutputFormat, prepare_output_format
from .protocol import json_bytes
from .reasoning_replay import summary_notes
from .response_store import ResponseStore
from .responses_tools import (
    ToolBinding,
    merge_discovered_tools,
    normalize_tools,
    tool_alias,
)
from .translate import RequestError, validate_request


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def invalid(param: str, message: str) -> RequestError:
    return RequestError(message, param=param)


def string(value: Any, param: str, *, empty: bool = True) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise invalid(param, f"{param} must be a {'non-empty ' if not empty else ''}string")
    return value


def text_parts(value: Any, param: str, *, assistant: bool = False) -> list[dict]:
    kind = "output_text" if assistant else "input_text"
    if isinstance(value, str):
        value = [{"type": kind, "text": value}]
    if not isinstance(value, list):
        raise invalid(param, f"{param} must be a string or an array of text parts")
    parts = []
    for index, part in enumerate(value):
        path = f"{param}[{index}]"
        if not assistant and isinstance(part, dict) and part.get("type") == "input_image":
            selected_image(part)
            normalized = {"type": "input_image", "image_url": image_url(part)}
            if part.get("detail") is not None:
                if part["detail"] not in ("auto", "low", "high", "original"):
                    raise invalid(path, "unsupported image detail")
                normalized["detail"] = part["detail"]
            parts.append(normalized)
            continue
        allowed = ("input_text", "output_text") if assistant else ("input_text",)
        if not isinstance(part, dict) or part.get("type") not in allowed:
            raise invalid(path, f"only {kind} content is supported here")
        text = string(part.get("text"), f"{path}.text")
        normalized = {"type": kind, "text": text}
        if assistant:
            normalized["annotations"] = []
            normalized["logprobs"] = []
        parts.append(normalized)
    return parts


def normalize_item(item: Any, param: str) -> dict:
    if not isinstance(item, dict):
        raise invalid(param, "each input item must be an object")
    if "id" in item:
        string(item["id"], f"{param}.id", empty=False)
    kind = item.get("type", "message")
    if kind == "message":
        role = item.get("role")
        if role not in ("user", "assistant", "system", "developer"):
            raise invalid(f"{param}.role", "unsupported message role")
        normalized = {
            "type": "message",
            "id": item.get("id") or new_id("msg"),
            "role": role,
            "status": "completed",
            "content": text_parts(
                item.get("content"), f"{param}.content", assistant=role == "assistant"
            ),
        }
        if item.get("phase") is not None:
            if item["phase"] not in ("commentary", "final_answer"):
                raise invalid(f"{param}.phase", "phase must be commentary or final_answer")
            normalized["phase"] = item["phase"]
    elif kind in ("function_call", "custom_tool_call"):
        normalized = {
            "type": kind,
            "id": item.get("id") or new_id("ctc" if kind == "custom_tool_call" else "fc"),
            "call_id": string(item.get("call_id"), f"{param}.call_id", empty=False),
            "name": string(item.get("name"), f"{param}.name", empty=False),
            "status": "completed",
        }
        field = "arguments" if kind == "function_call" else "input"
        normalized[field] = string(item.get(field), f"{param}.{field}")
        if item.get("namespace") is not None:
            normalized["namespace"] = string(item["namespace"], f"{param}.namespace", empty=False)
    elif kind in ("function_call_output", "custom_tool_call_output"):
        output = item.get("output")
        if not isinstance(output, str):
            output = text_parts(output, f"{param}.output")
        normalized = {
            "type": kind,
            "id": item.get("id") or new_id("fco"),
            "call_id": string(item.get("call_id"), f"{param}.call_id", empty=False),
            "output": output,
            "status": "completed",
        }
    elif kind in ("tool_search_call", "tool_search_output"):
        execution = item.get("execution", "client")
        if execution not in ("client", "server"):
            raise invalid(f"{param}.execution", "tool search execution must be client or server")
        call_id = item.get("call_id")
        if execution == "client" or call_id is not None:
            call_id = string(call_id, f"{param}.call_id", empty=False)
        normalized = {
            "type": kind,
            "id": item.get("id") or new_id("tsc" if kind.endswith("call") else "tso"),
            "execution": execution,
            "call_id": call_id,
            "status": item.get("status", "completed"),
        }
        if normalized["status"] not in ("completed", "failed", "in_progress", "incomplete"):
            raise invalid(f"{param}.status", "invalid tool search status")
        field, expected = ("arguments", dict) if kind == "tool_search_call" else ("tools", list)
        if not isinstance(item.get(field), expected):
            raise invalid(f"{param}.{field}", f"invalid tool search {field}")
        normalized[field] = item[field]
    elif kind in ("compaction", "compaction_summary", "context_compaction"):
        normalized = {
            "id": item.get("id") or new_id("cmp"),
            "type": "compaction",
            "encrypted_content": string(
                item.get("encrypted_content"), f"{param}.encrypted_content", empty=False
            ),
        }
    elif kind == "configuration_update":
        if not isinstance(item.get("reasoning"), dict):
            raise invalid(f"{param}.reasoning", "configuration_update requires reasoning options")
        normalized = {
            "id": item.get("id") or new_id("cfg"),
            "type": kind,
            "reasoning": item["reasoning"],
        }
    elif kind == "web_search_call":
        action = item.get("action")
        if not isinstance(action, dict) or action.get("type") != "search":
            raise invalid(f"{param}.action", "only search actions can be replayed")
        normalized = {
            "id": item.get("id") or new_id("ws"),
            "type": kind,
            "status": item.get("status", "completed"),
            "action": action,
        }
    elif kind == "reasoning":
        if item.get("encrypted_content") is not None:
            raise invalid(param, "encrypted reasoning cannot be replayed by this gateway")
        if item.get("content") not in (None, []):
            raise invalid(param, "reasoning replay only supports summary text")
        summary = item.get("summary", [])
        if not isinstance(summary, list):
            raise invalid(param, "reasoning.summary must be an array")
        parts = []
        for part in summary:
            if not isinstance(part, dict) or part.get("type") != "summary_text":
                raise invalid(param, "reasoning.summary only supports summary_text")
            parts.append({"type": "summary_text", "text": string(part.get("text"), param)})
        normalized = {
            "type": kind,
            "id": item.get("id") or new_id("rs"),
            "summary": parts,
            "status": "completed",
        }
    else:
        raise invalid(
            param,
            "only messages, function/custom calls, tool outputs and reasoning "
            "summaries are supported; item references and built-in tools are unsupported",
        )
    string(normalized["id"], f"{param}.id", empty=False)
    return normalized


def message_content(parts: list[dict]):
    if all(part["type"] != "input_image" for part in parts):
        return "\n".join(part["text"] for part in parts)
    return [
        part if part["type"] == "input_image" else {"type": "text", "text": part["text"]}
        for part in parts
    ]


def items_to_messages(
    items: list[dict], *, reasoning_notes: dict[int, str] | None = None
) -> list[dict]:
    messages, calls, answered = [], {}, set()
    for index, item in enumerate(items):
        kind = item["type"]
        if kind == "message":
            message = {"role": item["role"], "content": message_content(item["content"])}
            if item["role"] == "assistant" and item.get("phase") is not None:
                message["phase"] = item["phase"]
            messages.append(message)
        elif kind == "reasoning" and reasoning_notes and index in reasoning_notes:
            messages.append({"role": "assistant", "content": reasoning_notes[index]})
        elif kind in ("function_call", "custom_tool_call", "tool_search_call"):
            if kind == "tool_search_call" and item["execution"] == "server":
                continue
            if item["call_id"] in calls:
                raise invalid(f"input[{index}].call_id", "duplicate function call ID in history")
            calls[item["call_id"]] = kind
            if kind == "tool_search_call":
                name = tool_alias("tool_search", kind="tool_search")
                arguments = json_bytes(item["arguments"]).decode()
            else:
                tool_kind = "function" if kind == "function_call" else "custom"
                name = tool_alias(item["name"], item.get("namespace"), tool_kind)
                arguments = (
                    item["arguments"]
                    if kind == "function_call"
                    else json_bytes({"input": item["input"]}).decode()
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "type": "function",
                            "id": item["call_id"],
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            )
        elif kind in ("function_call_output", "custom_tool_call_output", "tool_search_output"):
            if kind == "tool_search_output" and item["execution"] == "server":
                continue
            call_id = item["call_id"]
            expected_call = (
                "tool_search_call" if kind == "tool_search_output" else kind.removesuffix("_output")
            )
            if calls.get(call_id) != expected_call or call_id in answered:
                raise invalid(
                    f"input[{index}].call_id",
                    "function output must match an earlier, unanswered function call; "
                    "supply previous_response_id or the full input/output history",
                )
            answered.add(call_id)
            output = (
                json_bytes({"tools": item["tools"], "status": item["status"]}).decode()
                if kind == "tool_search_output"
                else item["output"]
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": output if isinstance(output, str) else message_content(output),
                }
            )
        elif kind == "web_search_call":
            # Search executes upstream; retain its provenance during stateless replay.
            messages.append(
                {
                    "role": "assistant",
                    "content": "Web search performed: " + json_bytes(item["action"]).decode(),
                }
            )
        # Reasoning replay is opt-in, bounded, and remains historical assistant content.
    return messages


@dataclass(slots=True)
class ResponsesRequest:
    body: dict
    chat_body: dict
    input_items: list[dict]
    tool_bindings: dict[str, ToolBinding]
    output_format: OutputFormat | None = None
    compaction: bool = False
    compact_endpoint: bool = False
    compaction_codec: CompactionCodec | None = None


def prepare_request(
    raw: Any,
    store: ResponseStore,
    config: Config,
    *,
    compaction_codec: CompactionCodec | None = None,
    compact_endpoint: bool = False,
) -> ResponsesRequest:
    if not isinstance(raw, dict):
        raise invalid("body", "request body must be a JSON object")
    body = dict(raw)
    for name, default in (
        ("stream", False),
        ("store", True),
        ("parallel_tool_calls", False),
        ("background", False),
    ):
        value = body.get(name)
        if value is not None and not isinstance(value, bool):
            raise invalid(name, f"{name} must be a boolean")
        body[name] = default if value is None else value
    if body["background"]:
        raise invalid("background", "background responses are not supported")
    for name in ("conversation", "prompt"):
        if body.get(name) is not None:
            raise invalid(name, f"{name} is not supported; send explicit input/instructions")
    include = body.get("include")
    if include is not None and (
        not isinstance(include, list)
        or any(value != "reasoning.encrypted_content" for value in include)
    ):
        raise invalid("include", "only reasoning.encrypted_content is accepted in include")
    if include:
        event(
            "compatibility_notice",
            feature="reasoning.encrypted_content",
            action="not_produced",
            reason="Cursor exposes reasoning text but no OpenAI encrypted reasoning state",
        )
    if body.get("truncation") not in (None, "disabled"):
        raise invalid("truncation", "automatic context truncation is not supported")
    if body.get("tool_choice") not in (None, "auto", "none"):
        raise invalid("tool_choice", "only tool_choice='auto' or 'none' is supported")
    body["tool_choice"] = body.get("tool_choice") or "auto"
    instructions = body.get("instructions")
    if instructions is not None:
        string(instructions, "instructions")
    if body.get("model") is not None:
        string(body["model"], "model", empty=False)
    metadata = body.get("metadata")
    if metadata is None:
        metadata = {}
    if (
        not isinstance(metadata, dict)
        or len(metadata) > 16
        or any(
            not isinstance(k, str) or len(k) > 64 or not isinstance(v, str) or len(v) > 512
            for k, v in metadata.items()
        )
    ):
        raise invalid("metadata", "metadata must have at most 16 string pairs (64/512 characters)")
    body["metadata"] = metadata
    text = body.get("text")
    if text is not None:
        if not isinstance(text, dict):
            raise invalid("text", "text must be an object")
        if text.get("verbosity") not in (None, "low", "medium", "high"):
            raise invalid("text.verbosity", "invalid text verbosity")
    output_format = prepare_output_format(text)
    reasoning = body.get("reasoning")
    if reasoning is not None and (
        not isinstance(reasoning, dict)
        or reasoning.get("effort")
        not in (None, "none", "minimal", "low", "medium", "high", "xhigh", "max")
        or reasoning.get("summary") not in (None, "auto", "concise", "detailed", "none")
        or reasoning.get("context") not in (None, "auto", "current_turn", "all_turns")
    ):
        raise invalid("reasoning", "invalid reasoning options")
    for name, lower, upper in (("temperature", 0, 2), ("top_p", 0, 1)):
        value = body.get(name)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not lower <= value <= upper
        ):
            raise invalid(name, f"{name} must be between {lower} and {upper}")
    for name in ("max_output_tokens", "max_tool_calls"):
        value = body.get(name)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise invalid(name, f"{name} must be a positive integer")
    stream_options = body.get("stream_options")
    if stream_options is not None and (
        not isinstance(stream_options, dict)
        or any(
            not (
                (k == "include_obfuscation" and isinstance(v, bool))
                or (k == "reasoning_summary_delivery" and v == "sequential_cutoff")
            )
            for k, v in stream_options.items()
        )
    ):
        raise invalid(
            "stream_options",
            "supported options are boolean include_obfuscation and "
            "reasoning_summary_delivery='sequential_cutoff'",
        )

    previous = body.get("previous_response_id")
    history = []
    if previous is not None:
        string(previous, "previous_response_id", empty=False)
        saved = store.get(previous, param="previous_response_id")
        if saved["response"]["status"] != "completed":
            raise invalid("previous_response_id", "only completed responses can be continued")
        if body.get("model") is None:
            body["model"] = saved["response"]["model"]
        # Top-level instructions are intentionally not stored in conversational input.
        history = saved["input"] + saved["response"]["output"]
    raw_input = body.get("input")
    if isinstance(raw_input, str):
        raw_input = [{"role": "user", "content": raw_input}]
    if raw_input is None and (previous is not None or instructions is not None):
        raw_input = []
    if not isinstance(raw_input, list):
        raise invalid("input", "input must be a string or an array of input items")
    compact = compact_endpoint
    if (
        raw_input
        and isinstance(raw_input[-1], dict)
        and raw_input[-1].get("type") == "compaction_trigger"
    ):
        compact = True
        raw_input = raw_input[:-1]
    if compact_endpoint and body["stream"]:
        raise invalid("stream", "the compact endpoint returns JSON only")
    items = history + [normalize_item(item, f"input[{i}]") for i, item in enumerate(raw_input)]
    if len({item["id"] for item in items}) != len(items):
        raise invalid("input", "input item IDs must be unique")
    if len(json_bytes(items)) > config.max_body_bytes:
        raise RequestError("combined response history is too large", status=413, param="input")
    codec = compaction_codec or CompactionCodec(
        config.compaction_key_file or config.auth_file.parent / "compaction.key",
        config.max_body_bytes,
    )
    expanded = codec.expand(items)
    discovered = [
        item["tools"]
        for item in expanded
        if item["type"] == "tool_search_output" and item["status"] == "completed"
    ]
    raw_tools = (
        merge_discovered_tools(body.get("tools"), discovered) if discovered else body.get("tools")
    )
    tools, chat_tools, bindings, hosted_search = normalize_tools(raw_tools)
    body["tools"] = tools
    notes = (
        summary_notes(expanded, config.reasoning_replay_max_chars)
        if config.replay_reasoning
        else {}
    )
    messages = items_to_messages(expanded, reasoning_notes=notes)
    repetition = repeated_tool_result(expanded)
    if repetition:
        event("repeated_tool_result", **repetition)
    if notes:
        event(
            "reasoning_replayed",
            summary_count=len(notes),
            characters=sum(map(len, notes.values())),
        )
    if instructions is not None:
        messages.insert(0, {"role": "system", "content": instructions})
    if hosted_search and not compact and body["tool_choice"] != "none":
        messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "Native web_search runs on the server. Its agent-tools/*.txt documents "
                    "are temporary search artifacts, accessible only through native Read. "
                    "For workspace files, patches, and terminal commands, use the callable "
                    "MCP tools supplied by the client. Native Read cannot access the client's "
                    "workspace, and client tools cannot access server search artifacts."
                ),
            },
        )
    if not messages:
        raise invalid("input", "input must contain a message or function output")
    if compact:
        tools, chat_tools, bindings = [], [], {}
        body["tools"], body["tool_choice"] = [], "none"
        messages.append({"role": "user", "content": COMPACTION_PROMPT})
        output_format = None
    elif output_format is not None:
        messages.insert(0, {"role": "system", "content": output_format.instruction})
    chat = {
        "messages": messages,
        "model": body.get("model"),
        "stream": body["stream"],
        "tools": chat_tools,
        "tool_choice": body["tool_choice"],
        "parallel_tool_calls": body["parallel_tool_calls"],
        "_cursor_web_search": hosted_search and not compact and body["tool_choice"] != "none",
    }
    validate_request(chat)
    return ResponsesRequest(
        body, chat, items, bindings, output_format, compact, compact_endpoint, codec
    )
