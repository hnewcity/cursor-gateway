# API Reference

[简体中文](../api-reference.md) · **English**

[← Back to README](README.md) · [Codex CLI guide](codex-usage.md)

The service listens on `http://127.0.0.1:8790` by default. Use `http://127.0.0.1:8790/v1` as the client Base URL.
When a gateway key is configured, all `/v1/*` endpoints require `Authorization: Bearer <key>` or `x-api-key`.
Examples read `CURSOR_DIRECT_API_KEY` from the terminal environment. If the key is only set in the server's `.env`,
export the same value in the terminal where you run the examples. If no gateway key is configured, `unused` works.

Interactive API documentation is available at `/docs`, ReDoc at `/redoc`, and the OpenAPI description at `/openapi.json`.

## Responses API

`POST /v1/responses` accepts Responses `input` and flat function tool definitions.
The existing `/v1/chat/completions` endpoint remains available.

```bash
curl http://127.0.0.1:8790/v1/responses \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","instructions":"Answer briefly in English.","input":"Explain HTTP/2."}'

curl -N http://127.0.0.1:8790/v1/responses \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","input":"Hello!","stream":true,"store":false}'
```

The returned object's `object` field is `response`. Visible text appears in `output_text` entries within
`output[].content[]`. Upstream thinking deltas map to `summary_text` in `reasoning` output items,
separate from the visible answer.

You can use the official Python SDK directly. These examples use Python 3.14; the SDK is included in the project's development dependencies.

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8790/v1",
    api_key=os.getenv("CURSOR_DIRECT_API_KEY") or "unused",
)
# Choose a model returned by /v1/models.
model = "auto"
response = client.responses.create(
    model=model,
    instructions="Answer briefly in English.",
    input="What are the main features of HTTP/2?",
)
print(response.output_text)

# Continue by ID; provide required instructions again on each turn.
followup = client.responses.create(
    model=model,
    previous_response_id=response.id,
    instructions="Answer briefly in English.",
    input="Give another example.",
)
print(followup.output_text)

# stream=True returns typed Responses events.
stream = client.responses.create(model=model, input="Hello!", stream=True)
for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
    elif event.type == "response.failed":
        raise RuntimeError(event.response.error.message)
```

The SDK's `client.responses.stream(...)` context manager and `get_final_response()` are also supported.
SSE events include increasing `sequence_number` values and matching `event:` names:

- `response.created`, `response.in_progress`
- `response.output_item.added` / `.done`
- `response.content_part.added` / `.done`, `response.output_text.delta` / `.done`
- `response.reasoning_summary_part.added` / `.done`, `response.reasoning_summary_text.delta` / `.done`
- `response.function_call_arguments.delta` / `.done`
- `response.completed` or `response.failed`

The terminal event includes the full response and usage. Responses streams do not send the Chat Completions `[DONE]` marker.
Upstream errors before the first output retain their HTTP status; errors after streaming output begins use `response.failed`.
Tool calls are returned to the caller as a completed response, with status `completed`.

Responses tool calling example, using the same `client` and `model`:

```python
import json

tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "Look up the weather for a city",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}]
response = client.responses.create(
    model=model, input="What is the weather in Beijing?", tools=tools,
)
tool_outputs = []
for item in response.output:
    if item.type == "function_call":
        args = json.loads(item.arguments)
        # Execute the real tool in the caller; this is demonstration data.
        result = {"city": args["city"], "temperature": 25, "condition": "sunny"}
        tool_outputs.append({
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": json.dumps(result, ensure_ascii=False),
        })
if tool_outputs:
    response = client.responses.create(
        model=model, previous_response_id=response.id, tools=tools, input=tool_outputs,
    )
print(response.output_text)
```

Return tool results using `call_id`, not the output item's `id`. To continue without a response ID,
set `store=false` and include the previous input, `response.output`, and `function_call_output` items
in that order in the next request's `input`. Convert SDK objects to dictionaries with
`item.model_dump(exclude_none=True)` when needed. Reasoning summaries can be passed back unchanged;
the gateway does not treat them as visible answer text.

History management endpoints use gateway authentication:

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/responses/{response_id}` | Retrieve the full stored JSON response |
| `DELETE /v1/responses/{response_id}` | Delete the response and its input snapshot |
| `GET /v1/responses/{response_id}/input_items` | Inspect input history used for continuation; supports `after`, `limit`, and `order` |

`store` defaults to `true`. History is stored only in the current process's memory. Defaults are one hour,
256 responses, and 128 MiB of serialized data. When capacity is exhausted, the least recently accessed
responses are evicted. Expiry is measured from the time of storage; reads do not extend it.
Expired entries are cleaned up on the next cache access.

A restart clears the cache, and multiple processes or instances do not share history. Use `store=false`
and carry the full history in such deployments. Cache misses return `404`; the gateway does not silently
discard history and continue generating. Deleting a parent response does not remove history copies stored
in child responses. Cache access is gateway-wide and follows the same gateway API key permissions.

`previous_response_id` restores earlier input and output but does not inherit top-level `instructions` or tool definitions.
If `model` is omitted, the previous response's model is used. Merged history and the final response are each
subject to `CURSOR_DIRECT_MAX_BODY_BYTES`; Responses streams also limit accumulated output.

Current Responses compatibility:

- Supports `function` / `custom` tools inside `type="namespace"`. Different namespaces may contain tools with the same name.
  Returned calls preserve the original `name` and `namespace`. Function arguments and custom text inputs are returned through
  JSON / SSE and continued with `function_call_output` / `custom_tool_call_output`.
  Clients execute tools; the gateway does not run client shell commands, patches, or file operations.
- Accepts Codex's `include=["reasoning.encrypted_content"]`. Cursor has no OpenAI encrypted reasoning state,
  so the gateway does not produce `encrypted_content`. Reasoning summaries are retained in Responses history.
  By default, `CURSOR_DIRECT_REPLAY_REASONING=true` passes recent summaries to Cursor as historical assistant work notes
  when a native Run cannot be reused. The total budget is 12,000 characters; newer entries are retained and truncation is marked.
  Existing encrypted reasoning from other services cannot be decrypted and returns `400`.
- Completed assistant messages are marked `phase="commentary"` or `phase="final_answer"`.
  Streaming clients receive the final phase in `response.output_item.done`; creation events do not guess it.
  Replay preserves the original phase and adds a phase description to Cursor's assistant history text.
- `web_search` / `web_search_preview` use Cursor's native search and emit `web_search_call`, sources, and corresponding SSE events.
  Temporary search documents stay in the native Run's memory; they do not read or write the gateway host's or client's workspace.
  OpenAI location and domain-filter options are not supported.
- Custom tools support plain text and lark/regex grammars supplied as model prompts, without guaranteed grammar-constrained decoding.
  The gateway validates the custom tool's `input` string and checks boundary formatting for Codex patch grammars.
  Before the first external tool call is emitted, malformed input is sent back to the same Cursor Run for correction,
  with one attempt by default. If it remains invalid, an explicit tool input error is returned.
  Parallel batches with some calls already emitted remain subject to client validation so that results from the same batch are not lost.
  The gateway does not rewrite patches or execute file operations. The client remains responsible for full syntax and execution validation.
  `defer_loading` tools are treated as already loaded.
- Images can be included in user input or tool results using base64 data URLs. PNG, JPEG, WebP, and GIF are supported.
  Remote image URLs, file IDs, audio, other hosted built-in tools, and `item_reference` return `400`.
- `tool_search` supports client-side discovery and result continuation. Server-declared deferred tools are treated as loaded.
- `text.format` supports `json_object` / `json_schema` through model prompting and final-answer validation.
  The upstream does not provide native constrained decoding; invalid output returns an error.
- `/v1/responses/compact` and in-stream `compaction_trigger` generate gateway-encrypted summary checkpoints,
  preserving pending tool calls and discovered tools. `compaction.key` defaults to the account file's directory
  and should be persisted with it. The same key can decode checkpoints after a service restart.
  This mechanism is separate from OpenAI encrypted reasoning.
- `background=true`, `conversation`, hosted `prompt`, automatic truncation, other `include` fields, and forced tool selection return `400`.
  Codex's client-side compaction, tool execution, and session recovery do not require those features.
- `temperature`, `top_p`, `max_output_tokens`, `max_tool_calls`, `reasoning`, `text.verbosity`, and tool `strict`
  may be supplied, but the upstream has no implemented controls or strict validation guarantees for them.
  With `parallel_tool_calls=true`, multiple MCP calls arriving in the same batch are collected for client execution.
  Whether parallel calls are produced depends on the model. Integer arguments are recursively restored as JSON integers;
  fractional numbers, strings, and booleans retain their types.
- Responses input tokens are estimates marked `estimated=true`, used for client compaction budgets.
  Upstream token counts map to `output_tokens`; reliable separate cache / reasoning counts are unavailable.
- Transport uses HTTP/SSE, without WebSocket or background response management endpoints. Client disconnection cancels the upstream request.
  This provides Codex compatibility without implementing every OpenAI hosted API or native model capability.

Protocol references:
[Create a response](https://developers.openai.com/api/reference/resources/responses/methods/create),
[streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events),
and [function tools](https://developers.openai.com/api/docs/guides/function-calling).

## Chat Completions Tool Calling

Declare tools using standard function definitions:

```json
{
  "model": "auto",
  "messages": [{"role": "user", "content": "What is the weather in Beijing?"}],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Look up the weather for a city",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
      }
    }
  }]
}
```

After receiving `finish_reason: "tool_calls"`, execute the tools in the caller.
Append the complete assistant message and tool results to `messages` in the next request:

```json
{
  "role": "tool",
  "tool_call_id": "REPLACE_WITH_RETURNED_CALL_ID",
  "content": "{\"temperature\":25,\"condition\":\"sunny\"}"
}
```

Chat Completions uses full-history replay: the gateway replays earlier tool calls and results to Cursor
and sends a user turn asking it to continue. With `parallel_tool_calls=true`, multiple calls arriving
in the same upstream batch can be collected; the caller executes them.
Tool arguments are decoded through `google.protobuf.Value`, supporting objects, arrays, booleans, numbers, and null.
Characters such as newlines in upstream call IDs are converted to underscores to avoid downstream client rejection.
