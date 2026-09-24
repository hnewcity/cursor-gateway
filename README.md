<div align="center">

# ⚡ Cursor Gateway

**将你的 Cursor 账号接入 OpenAI 兼容 API**

[English](docs/en/README.md) · [Русский](docs/ru/README.md) · **简体中文** · [Español](docs/es/README.md) · [Bahasa Indonesia](docs/id/README.md) · [Português (Brasil)](docs/pt-BR/README.md) · [日本語](docs/ja/README.md) · [한국어](docs/ko/README.md)

用熟悉的客户端，调用 Cursor 账号可用的模型。支持 Chat Completions、Responses API 与 Codex CLI。

[![CI](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](LICENSE)

[功能特性](#features) · [快速开始](#quick-start) · [账号配置](#accounts) · [Docker 部署](#docker) · [客户端接入](#clients) · [常见问题](#faq) · [赞助](#sponsors)

</div>

---

<a id="sponsors"></a>

## ❤️ 赞助

<table>
<tr>
<td width="180" align="center"><a href="https://ai18n.chat"><img src="docs/assets/sponsors/ai18n.png" alt="ai18n" width="150"></a></td>
<td>感谢 <a href="https://ai18n.chat"><strong>ai18n</strong></a> 对本项目的赞助！ai18n 提供 AI API 中转服务，支持 OpenClaw、Claude Code、Codex、Gemini 等工具。</td>
</tr>
</table>

---

Cursor Gateway 是 [cursor2api](https://github.com/AstroQore/cursor2api) 的 Python 移植版，使用 FastAPI 提供 HTTP 服务，通过 HTTP/2 与 protobuf 直接连接 Cursor 的 Agent 后端。网关运行时无需 Node.js、Cursor CLI 或浏览器自动化。

```text
OpenAI 兼容客户端 / OpenAI SDK / Codex CLI
                     │
       Chat Completions / Responses API
                     ▼
              Cursor Gateway
                     │
        Connect-RPC · HTTP/2 · protobuf
                     ▼
              Cursor Agent 后端
```

> [!NOTE]
> 本项目是非官方客户端，与 Anysphere 无隶属或背书关系。请使用自己的 Cursor 账号；模型可用性和额度以账号及上游服务为准。

<a id="features"></a>

## ✨ 功能特性

| 功能 | 说明 |
| --- | --- |
| 🔌 **OpenAI 兼容接口** | 提供 `/v1/models`、`/v1/chat/completions` 与 `/v1/responses` |
| 💻 **Codex CLI 接入** | 附带启动器，支持文件补丁、终端 / PTY、MCP、多 agent、会话恢复和代码审查工作流 |
| 📡 **流式输出** | 支持 JSON、SSE、推理摘要及工具调用增量 |
| 🛠️ **工具调用** | 函数工具、多轮结果回传；Responses 额外支持自定义工具、命名空间和客户端工具发现 |
| 🧠 **任务连续性** | Responses 工具结果可续接同一个 Cursor Run，支持 `store=false` |
| 👁️ **图片输入** | 支持内联 base64 图片，包括 PNG、JPEG、WebP 和 GIF；需模型支持视觉 |
| 🔍 **联网搜索** | Responses 的 `web_search` / `web_search_preview` 映射到 Cursor 原生搜索 |
| 📐 **结构化输出** | Responses 支持 `json_object` / `json_schema` 提示约束与最终结果校验 |
| 💬 **历史与压缩** | 支持 `previous_response_id`、响应查询 / 删除、输入分页和加密压缩检查点 |
| 🔀 **多账号管理** | 账号轮询、文件热加载、自动刷新，以及鉴权 / 配额失败后的账号冷却 |
| 🤖 **动态模型发现** | 按账号获取模型列表，独立缓存并兼容旧的 `cursor-` 模型名称 |
| 🌐 **SOCKS5 代理** | 登录轮询、模型查询、聊天和 token 刷新统一走代理，支持用户名密码 |
| 🐳 **部署与诊断** | Docker Compose、systemd 示例、交互式 API 文档和带请求 ID 的诊断日志 |

详细能力边界见 [兼容范围](#compatibility)，工具执行与权限由调用方客户端负责。

<a id="models"></a>

## 🤖 可用模型

网关根据当前选中账号动态获取模型目录。启动并登录后查询：

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

将返回的 `data[].id` 填入客户端的模型设置即可。本文示例使用 `auto`；如当前账号不支持，请替换为列表中的可用模型。

- 默认展示无 `cursor-` 前缀的名称，例如 `grok-4.6-medium`，网关会映射到实际上游 ID。
- 兼容旧的 `cursor-` 名称，也可通过 `CURSOR_DIRECT_MODEL_PREFIX` 自定义对外前缀。
- 模型目录缓存 10 分钟；获取失败时使用旧缓存或备用列表，并在 30 秒后重试。

> [!NOTE]
> 备用列表用于模型发现失败时的降级，不代表其中所有模型都能由当前账号调用。多账号轮询时，每次查询返回的是本次选中账号的目录。

<a id="quick-start"></a>

## 🚀 快速开始

选择部署方式：**本地 Python** 适合开发和调试；**[Docker Compose](#docker)** 适合容器部署。

### 环境要求

- **Python 3.14+**；项目开发、测试和 Docker 镜像统一使用 Python 3.14。
- 一个可以登录并具有可用额度的 Cursor 账号。
- 能够连接 Cursor 服务的网络，或可用的 [SOCKS5 代理](#proxy)。

### 1. 获取项目并安装

从当前仓库页面复制克隆地址，或选择 **Code → Download ZIP** 下载并解压。

```bash
git clone https://github.com/hnewcity/cursor-gateway.git
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

后续命令默认在仓库根目录执行。

<details>
<summary>🪟 Windows PowerShell 安装命令</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

后文的 `.venv/bin/python` 和 `.venv/bin/cursor-gateway` 在 Windows 下对应 `.venv\Scripts\python.exe` 和 `.venv\Scripts\cursor-gateway.exe`。

</details>

### 2. 登录 Cursor

```bash
.venv/bin/cursor-gateway login
```

终端会显示登录链接，在浏览器中打开并确认即可。也可以[导入本机登录](#accounts)或使用已有账号文件。默认凭据保存到仓库根目录的 `accounts.json`。

### 3. 启动服务

```bash
.venv/bin/cursor-gateway serve
```

默认地址：`http://127.0.0.1:8790`。服务自动读取当前目录的 `.env`，已有环境变量优先。

```bash
# 自定义监听地址和端口
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# 也可以通过 Python 模块启动
.venv/bin/python -m cursor_gateway serve
```

### 4. 发送第一个请求

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"你好，请介绍一下自己。"}]}'
```

> [!TIP]
> 如需保护网关接口，在 `.env` 中设置 `CURSOR_DIRECT_API_KEY=sk-your-secret`。客户端使用相同的 key，它与 Cursor 账号 token 是两种不同的凭据。
> 本文请求示例从终端环境读取 key；若仅在服务端 `.env` 中配置，请在运行客户端的终端执行 `export CURSOR_DIRECT_API_KEY="sk-your-secret"`。

<a id="accounts"></a>

## 🔐 账号配置

选择最适合你的一种方式。已有账号文件时，可直接跳到方式三。

### 方式一：浏览器登录

适合本地或远程服务器。服务器输出链接，你可以在自己的电脑上完成确认。

```bash
.venv/bin/cursor-gateway login
```

需要为登录轮询指定代理时：

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### 方式二：导入本机登录

本机 **Cursor 桌面版** 已登录时，可直接读取其 SQLite 数据库：

```bash
.venv/bin/cursor-gateway import-local

# 使用自定义数据目录
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 从 Cursor CLI / 桌面版导出账号，再部署到服务器</summary>

仓库提供独立的 [凭据导出脚本](scripts/export_cursor_credentials.py)。只依赖 Python 标准库，无需安装网关，不会联网或自动发送凭据。

```bash
# 在仓库根目录运行，生成服务器可用的账号文件
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# 仅使用 Cursor CLI 的登录
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

也可以单独复制脚本到已登录的电脑上运行：

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

默认在脚本旁生成 `accounts.json`，已有文件不会被覆盖。支持 `--source cli` / `--source desktop`、`--out` 和桌面版的 `--db` 参数。macOS 可能提示钥匙串授权。

将导出的文件放到服务器的 `data/accounts.json`，即可供本仓库的 Docker Compose 使用。

</details>

### 方式三：使用已有账号文件

兼容 `cursor2api` 的账号格式。在 `.env` 中设置路径：

```dotenv
CURSOR_DIRECT_AUTH_FILE=/absolute/path/to/accounts.json
```

<details>
<summary>📄 accounts.json 格式</summary>

```json
[
  {
    "label": "main",
    "accessToken": "your-access-token",
    "refreshToken": "your-refresh-token"
  }
]
```

也接受 `{"accounts": [...]}` 格式。`refreshToken` 可选；没有它时无法自动续期。支持 `expiresAt`、`disabledUntil` ISO 时间字段。

登录、导入和刷新使用原子写入，账号文件权限为 `0600`。使用已有文件时，自动刷新会将新的 token 写回同一文件。

</details>

> [!IMPORTANT]
> `accounts.json` 包含可以使用你账号的访问凭据，请妥善保管。账号文件、`.env` 和压缩密钥已列入 `.gitignore`。

<a id="multi-account"></a>

## 🔀 多账号管理

通过 `--merge` 添加账号：

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| 行为 | 说明 |
| --- | --- |
| 合并账号 | `--merge` 替换同名账号并保留其他账号；**省略时会替换整个输出文件** |
| 请求分配 | 新请求在可用账号之间轮询；复用原生 Run 时继续使用原账号 |
| 热加载 | 账号文件变更在后续请求时生效，无需重启 |
| 自动刷新 | 临近过期前 30 分钟尝试刷新；同一进程内合并并发刷新 |
| 失败冷却 | 配额耗尽、鉴权失败或权限不足后冷却 60 秒，后续请求使用其他可用账号 |

当前请求的上游错误会直接返回，不自动重放已经开始的推理请求。建议每个账号文件仅交给一个网关进程负责写入。

<a id="docker"></a>

## 🐳 Docker 部署

仓库自带 `Dockerfile` 和 `docker-compose.yml`。在仓库根目录执行：

```bash
# 首次配置；已有 .env 时直接编辑该文件
cp .env.example .env
mkdir -p data

# 从当前源码构建镜像
docker compose build

# 浏览器登录；已有 data/accounts.json 时可跳过
docker compose run --rm cursor-gateway login

# 启动并查看日志
docker compose up -d
docker compose logs -f cursor-gateway
```

容器内监听 `0.0.0.0:8790`，宿主机默认仅绑定 `127.0.0.1:8790`。Compose 将 `./data` 挂载到 `/data`，账号保存在 `/data/accounts.json`，压缩密钥也默认保存在该目录。

<details>
<summary>🔧 常用管理命令</summary>

```bash
# 查看状态
docker compose ps

# 最近 10 分钟的日志
docker compose logs --since 10m --timestamps cursor-gateway

# 更新源码或 .env 后，重建并应用配置
docker compose up -d --build

# 停止服务
docker compose down

# 为现有账号池追加登录
docker compose run --rm cursor-gateway login --merge --label second
```

`CURSOR_DIRECT_PORT` 控制宿主机映射端口；容器内端口固定为 `8790`。Compose 内账号路径固定为 `/data/accounts.json`，不使用 `.env` 中的 `CURSOR_DIRECT_AUTH_FILE`。

容器中的 `127.0.0.1` 指向容器自身。使用宿主机代理时，请填写容器可访问的地址；Docker Desktop 可按实际网络配置使用 `host.docker.internal`。

</details>

<details>
<summary>🐧 使用 systemd 部署</summary>

示例配置见 [deploy/cursor-gateway.service](deploy/cursor-gateway.service)。

将项目安装到 `/opt/cursor-gateway` 并创建虚拟环境，准备 `cursor-gateway` 服务用户，确保该用户可以读取项目与配置，并读写 `data` 目录。准备完成后：

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

示例将账号路径设置为 `/opt/cursor-gateway/data/accounts.json`，配置文件位于项目根目录的 `.env`。

</details>

<a id="clients"></a>

## 💡 客户端接入

### 通用 OpenAI 兼容客户端

| 设置项 | 填写内容 |
| --- | --- |
| Base URL | `http://127.0.0.1:8790/v1` |
| API Key | 与 `CURSOR_DIRECT_API_KEY` 一致；未配置时可填任意非空字符串 |
| Model | 从 `/v1/models` 获取，如账号可用的 `auto` |
| 接口协议 | Chat Completions 或 Responses，按客户端支持选择 |

客户端运行在其他机器时，将 `127.0.0.1` 替换为实际可访问的网关地址，并调整监听地址或端口映射。

### Codex CLI

先安装 Codex CLI 并启动网关，再运行仓库附带的启动器：

```bash
# 交互式使用
.venv/bin/python scripts/run_codex.py --model auto

# 执行一个编码任务
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write '创建 hello.py，运行并检查输出'
```

启动器使用 Responses HTTP/SSE，临时生成模型目录并保留日常配置，不修改 `~/.codex/config.toml`。网关 key 需要在当前终端导出；工具执行、MCP 审批和沙箱由 Codex 客户端控制。

默认客户端上下文预算为 65,536 tokens，可用 `--context-window` 调整；模型不支持视觉时使用 `--text-only`。指定其他网关可使用 `--url`。

会话恢复、原生 Run 续接与压缩说明见 [Codex CLI 接入指南](docs/codex-usage.md)。

### 请求示例

<details>
<summary>📡 Chat Completions 流式请求</summary>

```bash
curl -N http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "stream": true,
    "stream_options": {"include_usage": true},
    "messages": [{"role": "user", "content": "一句话解释 HTTP/2。"}]
  }'
```

文本增量位于 `choices[].delta.content`，推理增量位于 `reasoning_content`。设置 `include_usage` 后，结束前会追加 `choices: []` 的 usage 块，最后发送 `[DONE]`。

</details>

<details>
<summary>💬 Responses API 请求</summary>

```bash
curl http://127.0.0.1:8790/v1/responses \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "instructions": "请用中文简洁回答。",
    "input": "HTTP/2 有哪些特点？"
  }'
```

可见文本位于 `output[].content[]` 的 `output_text` 项。设置 `stream: true` 可接收带类型的 `response.*` SSE 事件；使用 `store: false` 可跳过响应历史存储。

</details>

<details>
<summary>🐍 Python OpenAI SDK</summary>

安装客户端依赖：

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
    messages=[{"role": "user", "content": "你好！"}],
)
print(completion.choices[0].message.content)

# Responses API
response = client.responses.create(
    model="auto",
    instructions="请用中文简洁回答。",
    input="解释一下 HTTP/2。",
)
print(response.output_text)
```

函数工具、Responses 流式输出、历史续接和完整兼容说明见 [API 参考](docs/api-reference.md)。

</details>

<a id="api"></a>

## 📡 API 端点

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` / `HEAD` | `/`、`/health` | 存活检查与可用账号数量，无需鉴权 |
| `GET` / `HEAD` | `/v1/models` | 当前选中账号的模型目录 |
| `POST` | `/v1/chat/completions` | Chat Completions，支持 JSON / SSE |
| `POST` | `/v1/responses` | Responses，支持 JSON / SSE |
| `POST` | `/v1/responses/compact` | 生成加密压缩检查点 |
| `GET` | `/v1/responses/{response_id}` | 查询已保存的响应 |
| `DELETE` | `/v1/responses/{response_id}` | 删除响应与输入快照 |
| `GET` | `/v1/responses/{response_id}/input_items` | 查询输入历史，支持分页 |
| `GET` | `/docs`、`/redoc`、`/openapi.json` | Swagger UI、ReDoc 与 OpenAPI 描述，无需鉴权 |

设置 `CURSOR_DIRECT_API_KEY` 后，所有 `/v1/*` 接口接受 `Authorization: Bearer <key>` 或 `x-api-key` 鉴权。Swagger UI 中可以通过 **Authorize** 填写密钥。

<a id="configuration"></a>

## ⚙️ 环境配置

复制 [.env.example](.env.example) 为 `.env` 后修改。常用配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | 监听地址 |
| `CURSOR_DIRECT_PORT` | `8790` | 监听端口 |
| `CURSOR_DIRECT_API_KEY` | 空 | 客户端调用网关的密钥 |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | 账号文件路径 |
| `CURSOR_DIRECT_PROXY_URL` | 空 | SOCKS5 代理地址 |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | 单轮 Agent 通信超时，含连接和握手，单位毫秒 |
| `CURSOR_DIRECT_MODEL_PREFIX` | 空 | 对外模型前缀，默认去掉上游的 `cursor-` |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | 记录请求摘要、ID 和耗时；关闭后仍记录错误 |

<details>
<summary>🔧 展开全部进阶配置</summary>

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | 上游 HTTP(S) origin |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | 上游客户端版本头 |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | 上游原生工具白名单；`*` 省略限制头 |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | 将 system / developer 指令转为历史配置回合 |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | 完整历史回放时保留近期推理摘要 |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | 回放摘要总字符预算，优先保留近期内容 |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | 同一 Run 内的工具输入格式修正次数，范围 0–3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | 将工具结果续接到等待中的原生 Run |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | 等待客户端工具结果的有效期，单位秒 |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | 原生 Run 最多保留数量 |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | 完整历史回放时使用的继续提示 |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | 请求体和响应大小限制；Responses 流也限制累计输出 |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | Responses 历史有效期，单位秒 |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | Responses 历史最大条数 |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | Responses 历史最大序列化字节数 |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | 账号目录下的 `compaction.key` | 压缩检查点密钥文件，需持久化 |

模型发现和 token 刷新有独立的网络超时，首次请求可能额外包含这部分耗时。

项目附带已生成的 protobuf 类，启动无需 `protoc`；不使用原 Node 项目的 `CURSOR_DIRECT_PROTO_DIR`。

</details>

<a id="proxy"></a>

## 🌐 代理支持

在 `.env` 中设置：

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# 如需用户名密码，使用以下形式
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

支持 `socks5://` 和 `socks5h://`，两者均在代理端解析目标域名；用户名密码中的特殊字符需要 URL 编码。代理覆盖模型查询、聊天、token 刷新和登录轮询。目前不支持 HTTP 代理地址。

<a id="faq"></a>

## 🔧 常见问题

<details>
<summary>健康检查正常，为什么请求返回 503？</summary>

`/health` 是存活检查。`{"ok": true, "accounts": 0, ...}` 表示进程正常，但没有可用账号，可能尚未登录或所有账号都在冷却中。

先运行 `login` / `import-local`，并检查实际使用的账号路径。本地默认是 `./accounts.json`；Docker Compose 使用 `./data/accounts.json`。若错误来自上游，则按响应错误信息排查服务可用性。

</details>

<details>
<summary>为什么返回 400？图片和工具该怎么传？</summary>

检查客户端收到的 `error` JSON，以及同一个 `X-Request-ID` 对应的日志。常见原因包括：

- `tool_choice="required"`、强制指定工具或其他未支持的参数。
- 远程图片 URL、文件 ID 或音频输入；图片需要使用支持格式的 base64 data URL。
- `file_search` 等未实现的托管工具，或不支持的 `include` 字段。
- 无效 JSON、自定义工具输入格式错误或不合法的 JSON Schema 配置。

Responses 支持图片和 `text.format` 的 JSON Schema 输出校验，完整格式见 [API 参考](docs/api-reference.md)。如果日志为 `stage="upstream"`，应结合上游错误消息和所选模型排查。

</details>

<details>
<summary>如何定位某一次失败请求？</summary>

默认 `info` 级别即可查看请求诊断。Docker 部署中运行：

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# 将占位内容替换为响应头中的 X-Request-ID
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F '替换为请求ID'
```

日志消息为单行 JSON，同一次请求共用 `request_id`：

| 事件 | 关注内容 |
| --- | --- |
| `request_started` / `request_parsed` | 路径、客户端与请求参数摘要 |
| `generation_started` | 账号标签、实际上游模型、历史和工具数量 |
| `compatibility_notice` | 兼容映射说明，本身不表示请求失败 |
| `request_error` | `stage`、`error_status`、`error_param`、`error_message`、上游 `error_code` |
| `request_finished` | HTTP 状态、`outcome`、耗时与收发字节数 |

SSE 开始后的失败可能仍显示 HTTP 200，应同时检查流内错误与日志的 `outcome`。常见上游错误映射：

| 上游错误 | HTTP 状态 |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| 其他协议或上游错误 | `502` |

日志摘要不包含提示词、消息正文、工具参数 / 输出、metadata 值、Cookie 或鉴权请求头；错误文本中的已知凭据会脱敏。关闭 `CURSOR_DIRECT_LOG_REQUESTS` 仅关闭常规请求日志。

</details>

<details>
<summary>为什么重启后 previous_response_id 无法继续？</summary>

Responses 历史保存在当前进程内存中，默认最多 1 小时、256 条、128 MiB。重启会清空，多进程或多实例也不共享缓存；未命中时返回 `404`。

需要客户端自行管理历史时，使用 `store=false` 并传入完整输入、先前输出和工具结果。压缩检查点依赖 `compaction.key`，持久化同一密钥后可跨重启解码；它与响应 ID 缓存是两套机制。

使用 `previous_response_id` 时，每轮仍需重新提供所需的 `instructions` 和工具定义。

</details>

<a id="compatibility"></a>

## 📋 兼容范围

| 能力 | 当前实现与边界 |
| --- | --- |
| API 协议 | Chat Completions、Responses 与 Models；未提供 Anthropic `/v1/messages`、Embeddings 或管理页面 |
| 图片 | 两种生成接口均支持内联 PNG / JPEG / WebP / GIF；单图最多 16 MiB、单请求最多 32 张，仍受请求体限制；不支持远程 URL、文件 ID 或音频 |
| 工具 | 客户端执行函数 / 自定义工具；`tool_choice` 支持 `auto` / `none`。启用 `parallel_tool_calls` 可收集同批调用，是否产生并行调用取决于上游模型 |
| 结构化输出 | Responses 使用提示约束并校验最终答案，不提供原生约束解码；Chat Completions 的 `response_format` 不生效 |
| 采样与推理参数 | `temperature`、`top_p`、token 上限等参数没有完整的上游硬控制映射；Chat Completions 仅支持 `n=1` |
| 推理状态 | 输出可见推理摘要；不生成或解密 OpenAI 的 `reasoning.encrypted_content` |
| Token 统计 | Chat Completions 的 prompt tokens 为 0；Responses 输入 token 为标注 `estimated=true` 的估算。上游计数映射为输出 token，不提供可靠的独立缓存 / 推理计费明细 |
| 联网搜索 | Responses 使用 Cursor 原生搜索，不支持 OpenAI 搜索的地理位置和域名过滤选项 |
| 传输与托管能力 | 使用 HTTP/SSE；不支持 Responses WebSocket、`background=true`、托管 `conversation` / `prompt` 或其他托管内置工具；客户端断连会取消上游请求 |

system / developer 指令默认通过带来源说明的历史消息传入，效果仍受上游提示词影响。即使配置 `CURSOR_ALLOWED_NATIVE_TOOLS=*`，网关也不会在主机上执行客户端的 shell、文件或补丁操作。

更细的参数行为见 [API 参考](docs/api-reference.md)，客户端配置见 [Codex CLI 接入指南](docs/codex-usage.md)。

<a id="development"></a>

## 🧪 开发与验证

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

自动化测试使用虚构凭据和本地模拟上游，覆盖账号刷新、请求校验、JSON / SSE、工具循环、Responses 历史、断连取消，以及本地 TCP 上的 HTTP/2 / protobuf 传输，无需真实账号、付费推理或 Codex CLI。

<details>
<summary>🛠️ 协议代码生成</summary>

修改协议定义后，用 `protoc 36.1` 重新生成 Python 类：

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 项目结构</summary>

```text
cursor-gateway/
├── src/cursor_gateway/       # 网关实现
│   ├── cli.py               # 服务启动、登录和本机导入
│   ├── config.py            # 环境配置
│   ├── auth.py              # 账号池、刷新和凭据存储
│   ├── models.py            # 模型发现与缓存
│   ├── transport.py         # HTTP/2、TLS 与 SOCKS5
│   ├── protocol.py          # Connect 封帧与 Value 解码
│   ├── session.py           # Cursor Run 状态机
│   ├── continuations.py     # 跨请求原生会话续接
│   ├── translate.py         # 历史消息与工具转换
│   ├── server.py            # 路由、鉴权与 Chat Completions
│   ├── responses.py         # Responses JSON 与 SSE
│   ├── response_store.py    # 有效期与容量受限的历史缓存
│   └── proto/               # 协议定义与生成代码
├── scripts/                 # Codex 启动器、凭据导出与协议生成
├── tests/                   # 单元与集成测试
├── docs/                    # API 与客户端接入文档
├── deploy/                  # systemd 示例
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

</details>

<a id="contributing"></a>

## 🤝 参与贡献

使用 Issues 反馈可复现的问题或讨论功能建议，提交 PR 前请阅读 [贡献指南](CONTRIBUTING.md)。
修改功能、配置或示例时请同步八种语言的 README 及中英文指南，并遵循 [行为准则](CODE_OF_CONDUCT.md)。
安全问题请按 [安全报告流程](SECURITY.md) 私密反馈。版本变化见 [CHANGELOG](CHANGELOG.md)。

<a id="credits"></a>

## 🙏 致谢与许可证

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api)：本项目的原始参考实现，提供协议映射、账号格式与备用模型目录。
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi)：原项目所注明的 Cursor provider / `agent.proto` 来源。
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway)：README 的布局与文档组织参考。

本项目采用 **[AGPL-3.0-only](LICENSE)** 许可证。完整来源说明见 [NOTICE](NOTICE)。

分发或对外运行修改版本时，请遵守 AGPL 的对应源码提供要求。使用仓库源码或源码发行包提供运行版本的完整源码；对外服务还应提供清晰的源码获取入口。构建容器时可通过 `--build-arg SOURCE_URL=公开源码地址` 设置镜像来源信息。
