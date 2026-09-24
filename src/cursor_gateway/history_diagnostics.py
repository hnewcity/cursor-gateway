"""Signals for repeated tool work, computed only from the current request's history."""

import hashlib
import json
import re
from collections import Counter


def _fingerprint(value) -> bytes:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).digest()


def _result(value):
    # Codex terminal results contain a new chunk ID and timing on every read.
    # Compare stdout with its exit status, retaining error/success distinctions.
    if isinstance(value, str) and value.startswith("Chunk ID: "):
        before, separator, output = value.partition("\nOutput:\n")
        code = re.search(r"^Process exited with code (-?\d+)$", before, flags=re.MULTILINE)
        if separator and code:
            return {"exit_code": int(code[1]), "output": output}
    return value


def repeated_tool_result(items: list[dict]) -> dict | None:
    """Report a repeated latest result; never stop work or log its contents."""
    calls, pairs = {}, []
    for item in items[-256:]:
        kind = item["type"]
        if kind in ("function_call", "custom_tool_call"):
            args = item.get("arguments", item.get("input", ""))
            if kind == "function_call":
                try:
                    args = json.loads(args)
                except ValueError:
                    pass
            calls[item["call_id"]] = _fingerprint([kind, item.get("namespace"), item["name"], args])
        elif kind in ("function_call_output", "custom_tool_call_output"):
            call = calls.get(item["call_id"])
            if call is not None:
                pairs.append((call, _fingerprint(_result(item["output"]))))
    if not pairs:
        return None
    counts = Counter(pairs)
    repeats = counts[pairs[-1]]
    if repeats < 3:
        return None
    return {"same_call_and_result_count": repeats, "observed_tool_results": len(pairs)}
