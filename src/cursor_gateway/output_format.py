"""Prompt and validate structured output without claiming native constrained decoding."""

import json
from dataclasses import dataclass
from typing import Any

from jsonschema import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable

from .protocol import json_bytes
from .translate import RequestError


def no_remote_schema(uri: str):
    raise NoSuchResource(ref=uri)


@dataclass
class OutputFormat:
    schema: dict
    validator: Any

    @property
    def instruction(self) -> str:
        return (
            "The final answer must be valid JSON matching the following JSON Schema. "
            "Return only that JSON, without Markdown fences or additional commentary. "
            "You may call the supplied tools before producing the final JSON answer.\n"
            + json_bytes(self.schema).decode()
        )

    def validate(self, response: dict) -> None:
        if any(
            item["type"] in ("function_call", "custom_tool_call", "tool_search_call")
            for item in response["output"]
        ):
            return
        text = "".join(
            part["text"]
            for item in response["output"]
            if item["type"] == "message"
            for part in item["content"]
            if part["type"] == "output_text"
        )
        try:

            def reject_constant(value):
                raise ValueError("invalid number")

            value = json.loads(text, parse_constant=reject_constant)
            error = next(self.validator.iter_errors(value), None)
            if error is not None:
                raise ValueError("schema mismatch")
        except ValueError, Unresolvable, RecursionError:
            raise RequestError(
                "model output did not match the requested JSON format",
                status=502,
                param="output",
                code="invalid_structured_output",
            ) from None


def prepare_output_format(text) -> OutputFormat | None:
    if not isinstance(text, dict):
        return None
    spec = text.get("format")
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise RequestError("text.format must be an object", param="text.format")
    kind = spec.get("type")
    if kind == "text":
        return None
    if kind not in ("json_object", "json_schema"):
        raise RequestError("format must be text, json_object or json_schema", param="text.format")
    schema = {"type": "object"} if kind == "json_object" else spec.get("schema")
    if not isinstance(schema, dict):
        raise RequestError("JSON Schema must be an object", param="text.format.schema")
    if spec.get("strict") is not None and not isinstance(spec["strict"], bool):
        raise RequestError("format strict must be boolean", param="text.format.strict")
    try:
        cls = validator_for(schema)
        cls.check_schema(schema)
    except SchemaError, RecursionError:
        raise RequestError("invalid JSON Schema", param="text.format.schema") from None
    # Never let a caller-controlled $ref cause an outbound fetch from the gateway.
    return OutputFormat(schema, cls(schema, registry=Registry(retrieve=no_remote_schema)))
