"""Explicit approximate input usage for clients' context budgeting."""

from .protocol import json_bytes


def estimate_input_tokens(body: dict) -> int:
    images = 0

    def text_only(value):
        nonlocal images
        if isinstance(value, str) and value.startswith("data:image/"):
            images += 1
            return "[image]"
        if isinstance(value, dict):
            return {key: text_only(item) for key, item in value.items()}
        if isinstance(value, list):
            return [text_only(item) for item in value]
        return value

    count = (len(json_bytes(text_only(body))) + 2) // 3
    return count + images * 1536
