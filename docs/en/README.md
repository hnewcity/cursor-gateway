<div align="center">

# ⚡ Cursor Gateway

**Connect your Cursor account to an OpenAI-compatible API**

[简体中文](../../README.md) · **English**

Use familiar clients with the models available to your Cursor account. Supports Chat Completions, the Responses API, and Codex CLI.

![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](../../LICENSE)

[Features](#features) · [Quick Start](#quick-start) · [Accounts](#accounts) · [Docker](#docker) · [Client Setup](#clients) · [Troubleshooting](#faq)

</div>

---

Cursor Gateway is a Python port of [cursor2api](https://github.com/AstroQore/cursor2api). It serves HTTP requests with FastAPI and connects directly to Cursor's Agent backend over HTTP/2 and protobuf. The gateway runtime does not require Node.js, Cursor CLI, or browser automation.

```text
OpenAI-compatible clients / OpenAI SDK / Codex CLI
                         │
           Chat Completions / Responses API
                         ▼
                  Cursor Gateway
                         │
            Connect-RPC · HTTP/2 · protobuf
                         ▼
               Cursor Agent backend
```

> [!NOTE]
> This is an unofficial client, unaffiliated with and not endorsed by Anysphere. Use your own Cursor account. Model availability and quotas depend on your account and the upstream service.

<a id="features"></a>

## ✨ Features

| Feature | Description |
| --- | --- |
| 🔌 **OpenAI-compatible APIs** | `/v1/models`, `/v1/chat/completions`, and `/v1/responses` |
| 💻 **Codex CLI integration** | Includes a launcher for workflows involving file patches, terminals / PTYs, MCP, multiple agents, session recovery, and code review |
| 📡 **Streaming** | JSON and SSE responses, reasoning summaries, and tool call events |
| 🛠️ **Tool calling** | Function tools and multi-turn tool results; Responses also supports custom tools, namespaces, and client-side tool discovery |
| 🧠 **Task continuity** | Responses tool results can resume the same Cursor Run, including with `store=false` |
| 👁️ **Image input** | Inline base64 PNG, JPEG, WebP, and GIF images, when supported by the model |
| 🔍 **Web search** | Maps Responses `web_search` / `web_search_preview` to Cursor's native search |
| 📐 **Structured output** | Responses supports prompting and final-output validation for `json_object` / `json_schema` |
| 💬 **History and compaction** | `previous_response_id`, response retrieval / deletion, input pagination, and encrypted compaction checkpoints |
| 🔀 **Multiple accounts** | Round-robin selection, file hot reload, automatic token refresh, and cooldowns after authentication or quota failures |
| 🤖 **Dynamic model discovery** | Per-account model lists and caches, with support for legacy `cursor-` model names |
| 🌐 **SOCKS5 proxy** | Proxies login polling, model discovery, generation, and token refresh; supports username / password authentication |
| 🐳 **Deployment and diagnostics** | Docker Compose, a systemd example, interactive API documentation, and logs with request IDs |

See [Compatibility](#compatibility) for detailed limits. The calling client handles tool execution and permissions.

<a id="models"></a>

## 🤖 Available Models

The gateway fetches the model catalog for the account selected for the request. After signing in and starting the service:

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

Use a returned `data[].id` as your client's model setting. Examples in this document use `auto`; if your account does not support it, choose an available model from the list.

- Model names omit the upstream `cursor-` prefix by default. For example, `grok-4.6-medium` maps to the actual upstream ID.
- Legacy `cursor-` names still work. Set `CURSOR_DIRECT_MODEL_PREFIX` to customize the names exposed to clients.
- Model catalogs are cached for 10 minutes. If discovery fails, the gateway uses an older cache or the fallback catalog and retries after 30 seconds.

> [!NOTE]
> The fallback catalog is used when discovery fails; it does not guarantee access to every listed model. With multiple accounts, each query returns the catalog for the account selected for that request.

<a id="quick-start"></a>

## 🚀 Quick Start

Choose **native Python** for development and debugging, or **[Docker Compose](#docker)** for container deployment.

### Prerequisites

- **Python 3.14+**. Development, testing, and the Docker image use Python 3.14.
- A Cursor account that can sign in and has available usage quota.
- Network access to Cursor services, directly or through a [SOCKS5 proxy](#proxy).

### 1. Get the project and install

Clone using the URL on this repository page, or choose **Code → Download ZIP** and extract the archive.

```bash
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Run all subsequent commands from the repository root unless stated otherwise.

<details>
<summary>🪟 Windows PowerShell installation</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

On Windows, replace `.venv/bin/python` and `.venv/bin/cursor-gateway` in subsequent examples with `.venv\Scripts\python.exe` and `.venv\Scripts\cursor-gateway.exe`.

</details>

### 2. Sign in to Cursor

```bash
.venv/bin/cursor-gateway login
```

Open the URL printed in your terminal and approve the login in a browser. You can also [import a local login](#accounts) or use an existing account file. Credentials are saved to `accounts.json` in the repository root by default.

### 3. Start the service

```bash
.venv/bin/cursor-gateway serve
```

The default address is `http://127.0.0.1:8790`. The service reads `.env` from the current directory; existing environment variables take precedence.

```bash
# Set the listen address and port
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# Alternatively, start through the Python module
.venv/bin/python -m cursor_gateway serve
```

### 4. Send your first request

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello! Please introduce yourself."}]}'
```

> [!TIP]
> To protect the gateway API, set `CURSOR_DIRECT_API_KEY=sk-your-secret` in `.env` and configure clients with the same key. This gateway key is separate from your Cursor account token.
> Request examples read the key from the terminal environment. If you only set it in the server's `.env`, run `export CURSOR_DIRECT_API_KEY="sk-your-secret"` in the terminal used for the client.

<a id="accounts"></a>

## 🔐 Account Configuration

Choose the method that fits your setup. If you already have an account file, skip to option 3.

### Option 1: Browser login

Works locally or on a remote server. The server prints a URL that you can open on your own computer.

```bash
.venv/bin/cursor-gateway login
```

To specify a proxy for login polling:

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### Option 2: Import a local login

If you are signed in to the **Cursor desktop app** on the same machine, import credentials from its SQLite database:

```bash
.venv/bin/cursor-gateway import-local

# Use a custom data directory
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 Export a Cursor CLI / desktop account for server deployment</summary>

The standalone [credential export script](../../scripts/export_cursor_credentials.py) only uses the Python standard library. It does not require installing the gateway, make network requests, or automatically send credentials anywhere.

```bash
# Run from the repository root to create a server-ready account file
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# Use only the Cursor CLI login
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

You can also copy just the script to a machine where Cursor is signed in:

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

By default, the script creates `accounts.json` next to itself and refuses to overwrite an existing file. It supports `--source cli` / `--source desktop`, `--out`, and `--db` for a desktop database. macOS may ask for Keychain access.

Place the exported file at `data/accounts.json` on the server to use it with this repository's Docker Compose configuration.

</details>

### Option 3: Use an existing account file

The gateway accepts the `cursor2api` account format. Set the path in `.env`:

```dotenv
CURSOR_DIRECT_AUTH_FILE=/absolute/path/to/accounts.json
```

<details>
<summary>📄 accounts.json format</summary>

```json
[
  {
    "label": "main",
    "accessToken": "your-access-token",
    "refreshToken": "your-refresh-token"
  }
]
```

The `{"accounts": [...]}` format is also accepted. `refreshToken` is optional, but automatic renewal requires it. Optional `expiresAt` and `disabledUntil` fields accept ISO timestamps.

Login, import, and refresh use atomic writes with file permissions set to `0600`. When using an existing file, automatic refresh writes updated tokens back to the same file.

</details>

> [!IMPORTANT]
> `accounts.json` contains credentials that grant access to your account. Keep it private. Account files, `.env`, and compaction keys are included in `.gitignore`.

<a id="multi-account"></a>

## 🔀 Multiple Accounts

Add accounts with `--merge`:

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| Behavior | Description |
| --- | --- |
| Merging | `--merge` replaces an account with the same label and keeps others. **Omitting it replaces the entire output file.** |
| Request routing | New requests rotate through available accounts; a resumed native Run keeps its original account |
| Hot reload | Account file changes apply to subsequent requests without a restart |
| Token refresh | Attempts renewal within 30 minutes of expiry; concurrent refreshes are coalesced within a process |
| Cooldown | Quota exhaustion, authentication failures, or permission errors trigger a 60-second cooldown; later requests use other available accounts |

An upstream error is returned to the current request without automatically replaying generation that has already started. Use a single gateway process to write to each account file.

<a id="docker"></a>

## 🐳 Docker Deployment

The repository includes a `Dockerfile` and `docker-compose.yml`. Run from the repository root:

```bash
# First-time setup; edit the existing .env if you already have one
cp .env.example .env
mkdir -p data

# Build from the current source
docker compose build

# Browser login; skip if data/accounts.json already exists
docker compose run --rm cursor-gateway login

# Start and follow logs
docker compose up -d
docker compose logs -f cursor-gateway
```

The container listens on `0.0.0.0:8790`, while the host binding defaults to `127.0.0.1:8790`. Compose mounts `./data` at `/data`. Accounts are stored in `/data/accounts.json`, and the compaction key is stored in the same directory by default.

<details>
<summary>🔧 Common management commands</summary>

```bash
# Show service status
docker compose ps

# Logs from the last 10 minutes
docker compose logs --since 10m --timestamps cursor-gateway

# Rebuild and apply source or .env changes
docker compose up -d --build

# Stop the service
docker compose down

# Add a login to the existing account pool
docker compose run --rm cursor-gateway login --merge --label second
```

`CURSOR_DIRECT_PORT` controls the published host port; the container port stays at `8790`. Compose fixes the account path at `/data/accounts.json` and does not use `CURSOR_DIRECT_AUTH_FILE` from `.env`.

Inside a container, `127.0.0.1` refers to that container. To use a host proxy, specify an address reachable from the container. Docker Desktop deployments can use `host.docker.internal` when appropriate for the network configuration.

</details>

<details>
<summary>🐧 Deploy with systemd</summary>

See [deploy/cursor-gateway.service](../../deploy/cursor-gateway.service) for an example.

Install the project and its virtual environment at `/opt/cursor-gateway`, create a `cursor-gateway` service user, and allow that user to read the project and configuration and write to `data`. Once prepared:

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

The example uses `/opt/cursor-gateway/data/accounts.json` and reads `.env` from the project root.

</details>

<a id="clients"></a>

## 💡 Client Setup

### OpenAI-compatible clients

| Setting | Value |
| --- | --- |
| Base URL | `http://127.0.0.1:8790/v1` |
| API Key | The value of `CURSOR_DIRECT_API_KEY`; any nonempty string if no key is configured |
| Model | A model returned by `/v1/models`, such as `auto` when available to your account |
| API protocol | Chat Completions or Responses, depending on the client |

For clients on another machine, replace `127.0.0.1` with a reachable gateway address and adjust the listen address or port mapping.

### Codex CLI

Install Codex CLI, start the gateway, and run the included launcher:

```bash
# Interactive use
.venv/bin/python scripts/run_codex.py --model auto

# Run a coding task
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write 'Create hello.py, run it, and check the output'
```

The launcher uses Responses over HTTP/SSE and a temporary model catalog. It preserves your regular configuration without editing `~/.codex/config.toml`. Export the gateway key in the current terminal. Codex controls tool execution, MCP approvals, and the sandbox.

The default client context budget is 65,536 tokens; adjust it with `--context-window`. Use `--text-only` for models without vision support, or `--url` for a different gateway address.

See the [Codex CLI guide](codex-usage.md) for session recovery, native Run continuation, and compaction.

### Request examples

<details>
<summary>📡 Streaming Chat Completions</summary>

```bash
curl -N http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "stream": true,
    "stream_options": {"include_usage": true},
    "messages": [{"role": "user", "content": "Explain HTTP/2 in one sentence."}]
  }'
```

Text deltas appear in `choices[].delta.content`; reasoning deltas use `reasoning_content`. With `include_usage`, an additional usage chunk with `choices: []` is sent before the final `[DONE]`.

</details>

<details>
<summary>💬 Responses API request</summary>

```bash
curl http://127.0.0.1:8790/v1/responses \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "instructions": "Answer briefly in English.",
    "input": "What are the main features of HTTP/2?"
  }'
```

Visible text appears in `output_text` items within `output[].content[]`. Set `stream: true` for typed `response.*` SSE events, or `store: false` to skip response history storage.

</details>

<details>
<summary>🐍 Python OpenAI SDK</summary>

Install the client dependency:

```bash
.venv/bin/python -m pip install openai
```

```python
import os

from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8790/v1",
    api_key=os.getenv("CURSOR_DIRECT_API_KEY") or "unused",
)

# Chat Completions
completion = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(completion.choices[0].message.content)

# Responses API
response = client.responses.create(
    model="auto",
    instructions="Answer briefly in English.",
    input="Explain HTTP/2.",
)
print(response.output_text)
```

See the [API reference](api-reference.md) for function tools, Responses streaming, history continuation, and detailed compatibility notes.

</details>

<a id="api"></a>

## 📡 API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `HEAD` | `/`, `/health` | Liveness and available-account count; no authentication required |
| `GET` / `HEAD` | `/v1/models` | Model catalog for the selected account |
| `POST` | `/v1/chat/completions` | Chat Completions, JSON / SSE |
| `POST` | `/v1/responses` | Responses, JSON / SSE |
| `POST` | `/v1/responses/compact` | Generate an encrypted compaction checkpoint |
| `GET` | `/v1/responses/{response_id}` | Retrieve a stored response |
| `DELETE` | `/v1/responses/{response_id}` | Delete a response and its input snapshot |
| `GET` | `/v1/responses/{response_id}/input_items` | Retrieve input history with pagination |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc, and the OpenAPI description; no authentication required |

When `CURSOR_DIRECT_API_KEY` is set, all `/v1/*` endpoints accept `Authorization: Bearer <key>` or `x-api-key` authentication. Use **Authorize** in Swagger UI to enter the key.

<a id="configuration"></a>

## ⚙️ Configuration

Copy [.env.example](../../.env.example) to `.env` and edit it. Common settings:

| Environment variable | Default | Description |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | Listen address |
| `CURSOR_DIRECT_PORT` | `8790` | Listen port |
| `CURSOR_DIRECT_API_KEY` | Empty | Key used by clients to call the gateway |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | Account file path |
| `CURSOR_DIRECT_PROXY_URL` | Empty | SOCKS5 proxy URL |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | Agent communication timeout per turn, including connection and handshake, in milliseconds |
| `CURSOR_DIRECT_MODEL_PREFIX` | Empty | Prefix for exposed model names; the upstream `cursor-` prefix is removed by default |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | Log request summaries, IDs, and duration; errors are still logged when disabled |

<details>
<summary>🔧 All advanced settings</summary>

| Environment variable | Default | Description |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | Upstream HTTP(S) origin |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | Upstream client version header |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | Allowed upstream native tools; `*` omits the restriction header |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | Convert system / developer instructions into historical configuration turns |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | Retain recent reasoning summaries when replaying full history |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | Total character budget for replayed summaries, keeping newer entries first |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | Tool input format correction attempts within one Run, from 0 to 3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | Resume a pending native Run with tool results |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | Maximum wait for client tool results, in seconds |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | Maximum retained native Runs |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | Continuation prompt used during full-history replay |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | Request / response size limit; Responses streams also limit accumulated output |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | Response history lifetime, in seconds |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | Maximum stored responses |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | Maximum serialized response history size in bytes |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | `compaction.key` beside the account file | Compaction checkpoint key; persist this file |

Model discovery and token refresh have separate network timeouts, so the first request may take additional time.

Generated protobuf classes are bundled with the project. Starting the gateway does not require `protoc`, and it does not use the original Node project's `CURSOR_DIRECT_PROTO_DIR`.

</details>

<a id="proxy"></a>

## 🌐 Proxy Support

Set the proxy in `.env`:

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# For username / password authentication, use this format
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

Both `socks5://` and `socks5h://` resolve destination hostnames through the proxy. URL-encode special characters in usernames and passwords. The proxy covers model discovery, generation, token refresh, and login polling. HTTP proxy URLs are not currently supported.

<a id="faq"></a>

## 🔧 Troubleshooting

<details>
<summary>The health check passes. Why do requests return 503?</summary>

`/health` is a liveness check. `{"ok": true, "accounts": 0, ...}` means the process is running but no account is available. You may not have signed in, or all accounts may be cooling down.

Run `login` / `import-local` and check the account path actually used by the service. The local default is `./accounts.json`; Docker Compose uses `./data/accounts.json`. If the error originates upstream, use the returned error details to investigate service availability.

</details>

<details>
<summary>Why am I getting 400? How should I send images and tools?</summary>

Check the client's `error` JSON and the logs for the same `X-Request-ID`. Common causes include:

- `tool_choice="required"`, a forced tool choice, or other unsupported parameters.
- Remote image URLs, file IDs, or audio input. Images must use a supported format in a base64 data URL.
- Unimplemented hosted tools such as `file_search`, or unsupported `include` fields.
- Invalid JSON, malformed custom tool input, or an invalid JSON Schema configuration.

Responses supports images and JSON Schema output validation through `text.format`. See the [API reference](api-reference.md) for formats. If logs show `stage="upstream"`, investigate the upstream error message and selected model.

</details>

<details>
<summary>How do I investigate a specific failed request?</summary>

Request diagnostics are available at the default `info` log level. For Docker deployments:

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# Replace the placeholder with the X-Request-ID response header value
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F 'REPLACE_WITH_REQUEST_ID'
```

Log messages are single-line JSON. Events for a request share the same `request_id`:

| Event | What to check |
| --- | --- |
| `request_started` / `request_parsed` | Path, client, and request parameter summary |
| `generation_started` | Account label, actual upstream model, history count, and tool count |
| `compatibility_notice` | Compatibility mapping information; this event alone does not indicate failure |
| `request_error` | `stage`, `error_status`, `error_param`, `error_message`, and upstream `error_code` |
| `request_finished` | HTTP status, `outcome`, duration, and byte counts |

Errors after SSE begins may still have HTTP status 200. Check stream errors and the logged `outcome` as well. Common upstream error mappings:

| Upstream error | HTTP status |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| Other protocol or upstream errors | `502` |

Log summaries exclude prompts, message bodies, tool arguments / output, metadata values, cookies, and authentication headers. Known credentials in error text are redacted. Disabling `CURSOR_DIRECT_LOG_REQUESTS` only turns off routine request logs.

</details>

<details>
<summary>Why does previous_response_id stop working after a restart?</summary>

Response history is stored in process memory, with defaults of one hour, 256 entries, and 128 MiB. A restart clears it, and multiple processes or instances do not share it. A cache miss returns `404`.

For client-managed history, use `store=false` and send the complete input, previous output, and tool results. Compaction checkpoints depend on `compaction.key`; persisting the same key allows decoding after a restart. Checkpoints and response ID storage are separate mechanisms.

When using `previous_response_id`, provide the required `instructions` and tool definitions again on every turn.

</details>

<a id="compatibility"></a>

## 📋 Compatibility

| Capability | Implementation and limits |
| --- | --- |
| API protocols | Chat Completions, Responses, and Models; no Anthropic `/v1/messages`, Embeddings, or management UI |
| Images | Both generation APIs accept inline PNG / JPEG / WebP / GIF images, up to 16 MiB each and 32 images per request, subject to the overall body limit; remote URLs, file IDs, and audio are unsupported |
| Tools | Clients execute function / custom tools. `tool_choice` accepts `auto` / `none`. Enabling `parallel_tool_calls` collects calls arriving in the same batch; whether parallel calls are produced depends on the upstream model |
| Structured output | Responses prompts the model and validates the final answer, without native constrained decoding. Chat Completions `response_format` has no effect |
| Sampling and reasoning controls | Parameters such as `temperature`, `top_p`, and token limits do not have complete upstream enforcement. Chat Completions only supports `n=1` |
| Reasoning state | Exposes visible reasoning summaries; does not generate or decrypt OpenAI `reasoning.encrypted_content` |
| Token accounting | Chat Completions reports zero prompt tokens. Responses input tokens are estimates marked `estimated=true`. Upstream counts map to output tokens; separate cache / reasoning billing details are unavailable |
| Web search | Responses uses Cursor's native search, without OpenAI location or domain-filter options |
| Transport and hosted features | HTTP/SSE; no Responses WebSocket, `background=true`, hosted `conversation` / `prompt`, or other hosted built-in tools. Client disconnection cancels the upstream request |

System / developer instructions are passed as historical messages with source labels by default; their effect remains subject to upstream prompting. Even with `CURSOR_ALLOWED_NATIVE_TOOLS=*`, the gateway does not execute client shell commands, file operations, or patches on its host.

See the [API reference](api-reference.md) for detailed parameter behavior and the [Codex CLI guide](codex-usage.md) for client configuration.

<a id="development"></a>

## 🧪 Development and Verification

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

Automated tests use synthetic credentials and a local mock upstream. They cover account refresh, request validation, JSON / SSE, tool loops, Responses history, cancellation, and HTTP/2 / protobuf transport over local TCP connections. Real credentials, paid inference, and Codex CLI are not required.

<details>
<summary>🛠️ Protocol code generation</summary>

After changing protocol definitions, regenerate Python classes using `protoc 36.1`:

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 Project structure</summary>

```text
cursor-gateway/
├── src/cursor_gateway/       # Gateway implementation
│   ├── cli.py               # Server, login, and local import
│   ├── config.py            # Environment configuration
│   ├── auth.py              # Account pool, refresh, and credential storage
│   ├── models.py            # Model discovery and caching
│   ├── transport.py         # HTTP/2, TLS, and SOCKS5
│   ├── protocol.py          # Connect framing and Value decoding
│   ├── session.py           # Cursor Run state machine
│   ├── continuations.py     # Native session continuation across requests
│   ├── translate.py         # History and tool translation
│   ├── server.py            # Routes, authentication, and Chat Completions
│   ├── responses.py         # Responses JSON and SSE
│   ├── response_store.py    # History cache with expiry and capacity limits
│   └── proto/               # Protocol definitions and generated code
├── scripts/                 # Codex launcher, credential export, and protocol generation
├── tests/                   # Unit and integration tests
├── docs/                    # API and client setup documentation
├── deploy/                  # systemd example
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

</details>

<a id="contributing"></a>

## 🤝 Contributing

Use Issues for reproducible bugs and feature discussions, and read the [contributing guide](../../CONTRIBUTING.md) before submitting a pull request.
Keep Chinese and English documentation in sync when changing behavior, configuration, or examples, and follow the [code of conduct](../../CODE_OF_CONDUCT.md).
Report vulnerabilities privately using the [security policy](../../SECURITY.md). See the [changelog](../../CHANGELOG.md) for version changes.

<a id="credits"></a>

## 🙏 Credits and License

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api): the original implementation this project was ported from, including protocol mappings, account format, and fallback model catalog.
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi): the Cursor provider / `agent.proto` source credited by the original project.
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway): the reference for this README's layout and documentation structure.

This project is licensed under **[AGPL-3.0-only](../../LICENSE)**. See [NOTICE](../../NOTICE) for full attribution.

When distributing or operating a modified version for others, comply with the AGPL requirements for providing corresponding source. Supply the complete source for the running version through the repository or a source distribution, and provide a clear source-access entry point for network users. Container builds can record the public source location with `--build-arg SOURCE_URL=PUBLIC_SOURCE_URL`.
