# Codex CLI Guide

[简体中文](../codex-usage.md) · **English**

[← Back to README](README.md) · [API reference](api-reference.md)

Run these commands from the repository root after starting the gateway as described in the README.
Replace the example model with one available to your account in `/v1/models`.

After installing `codex` locally, connect through the launcher:

```bash
# Interactive use; preserves regular Codex configuration and client permissions.
.venv/bin/python scripts/run_codex.py --model grok-4.6-medium

# Isolated test configuration.
.venv/bin/python scripts/run_codex.py --model grok-4.6-medium -- \
  exec --ignore-user-config --sandbox workspace-write \
  'Create hello.py, run it, and check the output'

# Resume a specific Codex session; use a SESSION_ID from Codex.
.venv/bin/python scripts/run_codex.py --model grok-4.6-medium -- \
  exec resume --ignore-user-config SESSION_ID 'Continue the previous task'
```

Use `--url` for another gateway address. If the gateway has an API key, export `CURSOR_DIRECT_API_KEY`
in the current terminal first. The launcher generates a temporary model catalog, uses Responses over HTTP/SSE,
enables Cursor's native search, and places configuration overrides correctly for `exec` / `resume` / `review`.
It does not edit `~/.codex/config.toml`. Startup messages go to stderr, leaving `exec --json` stdout as JSONL.

The default client context budget is 65,536 tokens, adjustable through `--context-window`.
This is a client budget, not a guarantee of every Cursor model's native context window.
Use `--text-only` when the model does not support vision. When supplying an image through `--image`,
separate the prompt with `--` so that the CLI does not interpret it as an image path.

The Codex client executes tools and controls approval rules, including MCP approvals and the sandbox.
By default, the gateway retains a Cursor Run while it waits for client tool results.
When a subsequent Responses request matches the history, instructions, tool definitions, and complete batch
of tool results, those results are returned to the same upstream stream, preserving native reasoning and work progress.
This also works with Codex's common `store=false` usage and does not depend on `previous_response_id`.

By default, tool results may be pending for up to 300 seconds, with at most eight Runs retained.
Completion, cancellation, expiry, or service shutdown releases their connections.
Changes to instructions or tools, branching, compaction, restarts, or cache eviction fall back to full-history replay
with recent reasoning summaries. A custom provider's automatic compaction can use Codex's local summarization flow;
the gateway also implements `/v1/responses/compact` and in-stream `compaction_trigger`.

See the [API reference](api-reference.md) for endpoint behavior and limits, and the [contributing guide](../../CONTRIBUTING.md) for development and automated verification.
