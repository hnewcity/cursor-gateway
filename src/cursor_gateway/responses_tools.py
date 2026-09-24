"""Adapt Responses function/custom namespaces to Cursor's flat MCP tool catalogue."""

import hashlib
import re
from dataclasses import dataclass

from .diagnostics import event
from .protocol import json_bytes
from .translate import RequestError

HOSTED_SEARCH_TYPES = (
    "web_search",
    "web_search_2025_08_26",
    "web_search_preview",
    "web_search_preview_2025_03_11",
)


def text(value, param: str, *, empty: bool = True) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise RequestError(
            "expected a string" if empty else "expected a non-empty string", param=param
        )
    return value


def tool_alias(name: str, namespace: str | None = None, kind: str = "function") -> str:
    # Stable across stateless history replay and changing catalogue order. Reserve our prefix
    # so a top-level function cannot collide with a generated namespace/custom alias.
    if (
        namespace is None
        and kind == "function"
        and not name.startswith("cgw_")
        and re.fullmatch(r"[A-Za-z0-9_-]{1,48}", name)
    ):
        return name
    # Keep common tools readable: a long random suffix is easy for the model to
    # mistype. The kind and namespace length make this encoding unambiguous even
    # for (namespace="a_b", name="c") versus (namespace="a", name="b_c").
    scope = namespace or ""
    marker = {"function": "f", "custom": "c", "tool_search": "s"}[kind]
    readable = f"cgw_{marker}{len(scope)}_{scope + '_' if scope else ''}{name}"
    if len(readable) <= 48 and re.fullmatch(r"[A-Za-z0-9_-]+", readable):
        return readable
    # Cursor prepends its provider identifier. Reserve space below the native
    # 64-character limit and retain the leaf tool name for long/Unicode scopes.
    identity = json_bytes([namespace, name, kind])
    digest = hashlib.sha256(identity).hexdigest()[:16]
    label = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:24]
    return f"cgw_h_{label}_{digest}"


@dataclass(frozen=True, slots=True)
class ToolBinding:
    name: str
    namespace: str | None = None
    kind: str = "function"
    input_format: dict | None = None


def merge_discovered_tools(declared, discovered: list[list[dict]]) -> list[dict]:
    """Replay discovered tools; newer/current definitions take precedence by identity."""
    if declared is None:
        declared = []
    if not isinstance(declared, list):
        raise RequestError("tools must be an array", param="tools")
    # Validate each catalogue independently before merging, so duplicate declarations in the
    # same request don't get silently accepted by the merge.
    normalize_tools(declared)
    if not discovered:
        return declared
    merged: dict[tuple, dict] = {}
    for catalogue in [*discovered, declared]:
        normalize_tools(catalogue)
        for tool in catalogue:
            key = (
                ("namespace", tool["name"])
                if tool["type"] == "namespace"
                else (
                    "callable" if tool["type"] in ("function", "custom") else tool["type"],
                    tool.get("name"),
                )
            )
            if tool["type"] == "namespace" and key in merged:
                children = {child["name"]: child for child in merged[key]["tools"]}
                children.update({child["name"]: child for child in tool["tools"]})
                merged[key] = {**tool, "tools": list(children.values())}
            else:
                merged[key] = tool
    return list(merged.values())


def normalize_tools(raw) -> tuple[list[dict], list[dict], dict[str, ToolBinding], bool]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise RequestError("tools must be an array", param="tools")
    tools, chat_tools, bindings = [], [], {}
    namespaces, identities = set(), set()
    hosted_search = False

    def callable_tool(tool, param: str, namespace=None, namespace_description="") -> dict:
        if not isinstance(tool, dict) or tool.get("type") not in ("function", "custom"):
            raise RequestError("only function and custom tools are supported here", param=param)
        kind = tool["type"]
        name = text(tool.get("name"), f"{param}.name", empty=False)
        description = tool.get("description")
        description = "" if description is None else text(description, f"{param}.description")
        alias = tool_alias(name, namespace, kind)
        identity = (namespace, name)
        if identity in identities:
            raise RequestError("tool names must be unique within their namespace", param=param)
        if alias in bindings:
            raise RequestError("tool aliases collide", param=param)
        normalized = {"type": kind, "name": name, "description": description}
        upstream_description = description
        if namespace is not None or alias != name:
            upstream_description = (
                f"Tool {namespace + '.' if namespace else ''}{name}.\n"
                f"{namespace_description}\n{description}"
            )
        if kind == "function":
            parameters = tool.get("parameters")
            if parameters is None:
                parameters = {"type": "object", "properties": {}}
            if not isinstance(parameters, dict):
                raise RequestError("function parameters must be a JSON schema object", param=param)
            strict = tool.get("strict")
            if strict is not None and not isinstance(strict, bool):
                raise RequestError("function strict must be a boolean", param=f"{param}.strict")
            normalized.update(parameters=parameters, strict=strict or False)
        else:
            format_ = tool.get("format")
            if format_ is None:
                format_ = {"type": "text"}
            if not isinstance(format_, dict) or format_.get("type") not in ("text", "grammar"):
                raise RequestError(
                    "custom tool format must be text or grammar", param=f"{param}.format"
                )
            if format_["type"] == "grammar":
                if format_.get("syntax") not in ("lark", "regex"):
                    raise RequestError(
                        "grammar syntax must be lark or regex", param=f"{param}.format"
                    )
                definition = text(
                    format_.get("definition"), f"{param}.format.definition", empty=False
                )
                # Cursor can receive the grammar as guidance, but cannot enforce constrained
                # decoding; the client still validates/executes the actual tool input.
                upstream_description += (
                    f"\nWrite input matching this {format_['syntax']} grammar:\n{definition}"
                )
                format_ = {"type": "grammar", "syntax": format_["syntax"], "definition": definition}
            else:
                format_ = {"type": "text"}
            normalized["format"] = format_
            upstream_description += (
                "\nPass the complete, unmodified tool input in the input string."
            )
            parameters = {
                "type": "object",
                "properties": {"input": {"type": "string"}},
                "required": ["input"],
                "additionalProperties": False,
            }
        # Deferred tool definitions are loaded eagerly. No hosted tool-search executor is needed.
        identities.add(identity)
        bindings[alias] = ToolBinding(name, namespace, kind, format_ if kind == "custom" else None)
        chat_tools.append(
            {
                "type": "function",
                "function": {
                    "name": alias,
                    "description": upstream_description,
                    "parameters": parameters,
                },
            }
        )
        return normalized

    for index, tool in enumerate(raw):
        param = f"tools[{index}]"
        if not isinstance(tool, dict):
            raise RequestError("each tool must be an object", param=param)
        kind = tool.get("type")
        if kind in HOSTED_SEARCH_TYPES:
            if hosted_search:
                raise RequestError("only one web_search tool may be declared", param=param)
            # Cursor runs the search on its servers. Its protocol does not expose
            # OpenAI's geography/domain controls; reject those instead of ignoring them.
            if tool.get("filters") or tool.get("user_location"):
                raise RequestError(
                    "Cursor web search does not support filters or user_location", param=param
                )
            hosted_search = True
            tools.append(dict(tool))
            event(
                "compatibility_notice",
                feature=kind,
                action="cursor_native",
                reason="web search is executed by Cursor",
                param=param,
            )
        elif kind == "tool_search":
            execution = tool.get("execution", "server")
            if execution not in ("server", "client"):
                raise RequestError("tool_search execution must be client or server", param=param)
            if execution == "server":
                event(
                    "compatibility_notice",
                    feature="tool_search",
                    action="eagerly_loaded",
                    reason="declared deferred tools are already loaded",
                )
                continue
            if any(binding.kind == "tool_search" for binding in bindings.values()):
                raise RequestError("only one client tool_search may be declared", param=param)
            description = text(
                tool.get("description", "Discover tools available on the client."),
                f"{param}.description",
            )
            parameters = tool.get("parameters") or {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }
            if not isinstance(parameters, dict):
                raise RequestError("tool_search parameters must be an object", param=param)
            alias = tool_alias("tool_search", kind="tool_search")
            bindings[alias] = ToolBinding("tool_search", kind="tool_search")
            tools.append(
                {
                    "type": kind,
                    "execution": "client",
                    "description": description,
                    "parameters": parameters,
                }
            )
            chat_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": alias,
                        "description": description,
                        "parameters": parameters,
                    },
                }
            )
        elif kind == "namespace":
            name = text(tool.get("name"), f"{param}.name", empty=False)
            if name in namespaces:
                raise RequestError("namespace names must be unique", param=f"{param}.name")
            namespaces.add(name)
            description = text(tool.get("description", ""), f"{param}.description")
            children = tool.get("tools")
            if not isinstance(children, list):
                raise RequestError("namespace tools must be an array", param=f"{param}.tools")
            tools.append(
                {
                    "type": "namespace",
                    "name": name,
                    "description": description,
                    "tools": [
                        callable_tool(child, f"{param}.tools[{i}]", name, description)
                        for i, child in enumerate(children)
                    ],
                }
            )
        else:
            tools.append(callable_tool(tool, param))
    return tools, chat_tools, bindings, hosted_search
