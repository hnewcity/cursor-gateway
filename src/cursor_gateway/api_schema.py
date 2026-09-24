"""OpenAPI documentation for the gateway's bounded, manually validated request body."""

from http import HTTPStatus

INLINE_IMAGE_PART = {
    "type": "object",
    "required": ["type", "image_url"],
    "properties": {
        "type": {"enum": ["input_image", "image_url"]},
        "image_url": {
            "oneOf": [
                {"type": "string", "description": "Inline base64 data:image/... URL."},
                {
                    "type": "object",
                    "required": ["url"],
                    "properties": {"url": {"type": "string"}, "detail": {"type": "string"}},
                },
            ]
        },
        "detail": {"enum": ["auto", "low", "high", "original"]},
    },
}

RESPONSES_CONTENT_PART = {
    "oneOf": [
        {
            "type": "object",
            "required": ["type", "text"],
            "properties": {
                "type": {"enum": ["input_text", "output_text"]},
                "text": {"type": "string"},
            },
        },
        {
            **INLINE_IMAGE_PART,
            "properties": {
                **INLINE_IMAGE_PART["properties"],
                "type": {"const": "input_image"},
            },
        },
    ],
}

RESPONSES_CALLABLE_TOOL = {
    "oneOf": [
        {
            "type": "object",
            "required": ["type", "name"],
            "properties": {
                "type": {"const": "function"},
                "name": {"type": "string"},
                "description": {"type": ["string", "null"]},
                "parameters": {"type": ["object", "null"]},
                "strict": {
                    "type": ["boolean", "null"],
                    "description": "Accepted; upstream strict validation is unavailable.",
                },
            },
        },
        {
            "type": "object",
            "required": ["type", "name"],
            "properties": {
                "type": {"const": "custom"},
                "name": {"type": "string"},
                "description": {"type": ["string", "null"]},
                "format": {
                    "type": ["object", "null"],
                    "description": "Text or lark/regex grammar guidance; grammar is not enforced.",
                    "properties": {
                        "type": {"enum": ["text", "grammar"]},
                        "syntax": {"enum": ["lark", "regex"]},
                        "definition": {"type": "string"},
                    },
                },
            },
        },
    ],
}

CHAT_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["messages"],
                "properties": {
                    "model": {
                        "type": ["string", "null"],
                        "description": (
                            "Model ID from /v1/models, without cursor- by default. "
                            "Defaults to auto (with the configured prefix, if any). "
                            "Legacy cursor- names are also accepted."
                        ),
                    },
                    "messages": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["role"],
                            "properties": {
                                "role": {
                                    "type": "string",
                                    "enum": ["system", "developer", "user", "assistant", "tool"],
                                },
                                "content": {
                                    "description": "Plain text, text/inline image parts, or null.",
                                    "type": ["string", "array", "null"],
                                    "items": {
                                        "oneOf": [
                                            {"type": "string"},
                                            INLINE_IMAGE_PART,
                                            {
                                                "type": "object",
                                                "required": ["type", "text"],
                                                "properties": {
                                                    "type": {"enum": ["text", "input_text"]},
                                                    "text": {"type": "string"},
                                                },
                                            },
                                        ],
                                    },
                                },
                                "tool_calls": {
                                    "type": "array",
                                    "items": {"type": "object"},
                                    "description": "Assistant function calls to replay in history.",
                                },
                                "tool_call_id": {"type": "string"},
                                "name": {"type": "string"},
                            },
                        },
                    },
                    "stream": {"type": "boolean", "default": False},
                    "stream_options": {
                        "type": ["object", "null"],
                        "properties": {"include_usage": {"type": "boolean", "default": False}},
                    },
                    "tools": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["function"],
                            "properties": {
                                "type": {"type": "string", "enum": ["function"]},
                                "function": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string", "minLength": 1},
                                        "description": {"type": "string"},
                                        "parameters": {"type": "object"},
                                    },
                                },
                            },
                        },
                    },
                    "tool_choice": {"enum": ["auto", "none", None], "default": "auto"},
                    "parallel_tool_calls": {"type": ["boolean", "null"], "default": False},
                    "n": {"type": "integer", "const": 1, "default": 1},
                },
            },
            "example": {
                "model": "auto",
                "messages": [{"role": "user", "content": "你好"}],
                "stream": False,
            },
        },
    },
}

RESPONSES_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "anyOf": [
                    {"required": ["input"]},
                    {"required": ["instructions"]},
                    {"required": ["previous_response_id"]},
                ],
                "properties": {
                    "model": {
                        "type": ["string", "null"],
                        "description": (
                            "Model ID from /v1/models, without cursor- by default. "
                            "Defaults to auto (with the configured prefix, if any). "
                            "Legacy cursor- names are also accepted."
                        ),
                    },
                    "input": {
                        "description": "Text or ordered messages, function calls and tool outputs.",
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "enum": [
                                                "message",
                                                "function_call",
                                                "function_call_output",
                                                "custom_tool_call",
                                                "custom_tool_call_output",
                                                "reasoning",
                                                "tool_search_call",
                                                "tool_search_output",
                                                "web_search_call",
                                                "compaction",
                                                "compaction_trigger",
                                                "configuration_update",
                                            ],
                                            "default": "message",
                                        },
                                        "id": {"type": "string"},
                                        "role": {
                                            "enum": ["user", "assistant", "system", "developer"]
                                        },
                                        "content": {
                                            "oneOf": [
                                                {"type": "string"},
                                                {
                                                    "type": "array",
                                                    "items": RESPONSES_CONTENT_PART,
                                                },
                                            ],
                                        },
                                        "call_id": {"type": "string"},
                                        "name": {"type": "string"},
                                        "namespace": {"type": ["string", "null"]},
                                        "arguments": {"type": ["string", "object"]},
                                        "phase": {
                                            "enum": ["commentary", "final_answer"],
                                            "description": (
                                                "Preserved on assistant history. Output phase is "
                                                "finalized in response.output_item.done."
                                            ),
                                        },
                                        "encrypted_content": {"type": "string"},
                                        "execution": {"enum": ["client", "server"]},
                                        "tools": {"type": "array", "items": {"type": "object"}},
                                        "action": {"type": "object"},
                                        "reasoning": {"type": "object"},
                                        "input": {"type": "string"},
                                        "output": {
                                            "type": ["string", "array"],
                                            "items": {"type": "object"},
                                        },
                                        "summary": {"type": "array", "items": {"type": "object"}},
                                    },
                                },
                            },
                        ],
                    },
                    "instructions": {"type": ["string", "null"]},
                    "previous_response_id": {
                        "type": ["string", "null"],
                        "description": "ID of a completed response still in this process's cache.",
                    },
                    "stream": {"type": ["boolean", "null"], "default": False},
                    "store": {
                        "type": ["boolean", "null"],
                        "default": True,
                        "description": "Save history in a bounded memory cache; lost on restart.",
                    },
                    "tools": {
                        "type": ["array", "null"],
                        "items": {
                            "oneOf": [
                                *RESPONSES_CALLABLE_TOOL["oneOf"],
                                {
                                    "type": "object",
                                    "required": ["type"],
                                    "properties": {
                                        "type": {"const": "tool_search"},
                                        "execution": {"enum": ["client", "server"]},
                                        "description": {"type": "string"},
                                        "parameters": {"type": "object"},
                                    },
                                },
                                {
                                    "type": "object",
                                    "required": ["type", "name", "tools"],
                                    "properties": {
                                        "type": {"const": "namespace"},
                                        "name": {"type": "string"},
                                        "description": {"type": "string"},
                                        "tools": {
                                            "type": "array",
                                            "items": RESPONSES_CALLABLE_TOOL,
                                        },
                                    },
                                },
                                {
                                    "type": "object",
                                    "required": ["type"],
                                    "description": (
                                        "Executed by Cursor's native hosted web search. "
                                        "Geography and domain filters are not supported."
                                    ),
                                    "properties": {
                                        "type": {
                                            "enum": [
                                                "web_search",
                                                "web_search_2025_08_26",
                                                "web_search_preview",
                                                "web_search_preview_2025_03_11",
                                            ]
                                        },
                                    },
                                },
                            ],
                        },
                    },
                    "include": {
                        "type": ["array", "null"],
                        "items": {"const": "reasoning.encrypted_content"},
                        "description": (
                            "Accepted for client compatibility. Cursor has no OpenAI encrypted "
                            "reasoning state, so encrypted_content is not produced."
                        ),
                    },
                    "tool_choice": {"enum": ["auto", "none", None], "default": "auto"},
                    "parallel_tool_calls": {
                        "type": ["boolean", "null"],
                        "default": False,
                        "description": (
                            "Return MCP calls dispatched in the same upstream batch; "
                            "execution remains on the client."
                        ),
                    },
                    "metadata": {
                        "type": ["object", "null"],
                        "additionalProperties": {"type": "string"},
                        "maxProperties": 16,
                    },
                    "background": {"enum": [False, None], "default": False},
                    "text": {
                        "type": ["object", "null"],
                        "properties": {
                            "format": {
                                "type": "object",
                                "properties": {
                                    "type": {"enum": ["text", "json_object", "json_schema"]},
                                    "name": {"type": "string"},
                                    "schema": {"type": "object"},
                                    "strict": {"type": "boolean"},
                                },
                            },
                            "verbosity": {"enum": ["low", "medium", "high", None]},
                        },
                    },
                    "reasoning": {
                        "type": ["object", "null"],
                        "description": "Accepted as metadata; does not control upstream reasoning.",
                    },
                    "temperature": {"type": ["number", "null"], "minimum": 0, "maximum": 2},
                    "top_p": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                    "max_output_tokens": {"type": ["integer", "null"], "minimum": 1},
                    "max_tool_calls": {"type": ["integer", "null"], "minimum": 1},
                    "truncation": {"enum": ["disabled", None]},
                    "stream_options": {
                        "type": ["object", "null"],
                        "properties": {
                            "include_obfuscation": {"type": "boolean"},
                            "reasoning_summary_delivery": {"const": "sequential_cutoff"},
                        },
                    },
                },
            },
            "example": {"model": "auto", "input": "你好", "stream": False},
        },
    },
}

ERROR_RESPONSES = {
    status: {
        "description": HTTPStatus(status).phrase,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {
                            "type": "object",
                            "required": ["message", "type"],
                            "properties": {
                                "message": {"type": "string"},
                                "type": {"type": "string"},
                                "code": {"type": "string"},
                                "param": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }
    for status in (400, 401, 403, 404, 413, 415, 429, 501, 502, 503, 504)
}
