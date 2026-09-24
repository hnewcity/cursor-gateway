<div align="center">

# ⚡ Cursor Gateway

**Cursor 계정을 OpenAI 호환 API에 연결하세요**

[English](../en/README.md) · [Русский](../ru/README.md) · [简体中文](../../README.md) · [Español](../es/README.md) · [Bahasa Indonesia](../id/README.md) · [Português (Brasil)](../pt-BR/README.md) · [日本語](../ja/README.md) · **한국어**

익숙한 클라이언트에서 Cursor 계정으로 이용 가능한 모델을 호출할 수 있습니다. Chat Completions, Responses API, Codex CLI를 지원합니다.

[![CI](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](../../LICENSE)

[기능](#features) · [빠른 시작](#quick-start) · [계정](#accounts) · [Docker](#docker) · [클라이언트 설정](#clients) · [문제 해결](#faq) · [후원](#sponsors)

</div>

---

<a id="sponsors"></a>

## ❤️ 후원

<table>
<tr>
<td width="180" align="center"><a href="https://ai18n.chat"><img src="../assets/sponsors/ai18n.png" alt="ai18n" width="150"></a></td>
<td>이 프로젝트를 후원해 주시는 <a href="https://ai18n.chat"><strong>ai18n</strong></a>에 감사드립니다! ai18n은 OpenClaw, Claude Code, Codex, Gemini 등의 도구를 위한 AI API 중계 서비스를 제공합니다.</td>
</tr>
</table>

---

Cursor Gateway는 [cursor2api](https://github.com/AstroQore/cursor2api)를 Python으로 이식한 프로젝트입니다. FastAPI로 HTTP 요청을 처리하고 HTTP/2와 protobuf를 통해 Cursor의 Agent 백엔드에 직접 연결합니다. 게이트웨이 실행에는 Node.js, Cursor CLI, 브라우저 자동화가 필요하지 않습니다.

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
> 이 프로젝트는 비공식 클라이언트이며 Anysphere와 제휴 관계가 없고 해당 회사의 승인을 받지 않았습니다. 본인의 Cursor 계정을 사용하세요. 모델 이용 가능 여부와 사용 한도는 계정 및 업스트림 서비스에 따라 달라집니다.

<a id="features"></a>

## ✨ 기능

| 기능 | 설명 |
| --- | --- |
| 🔌 **OpenAI 호환 API** | `/v1/models`, `/v1/chat/completions`, `/v1/responses` |
| 💻 **Codex CLI 연동** | 파일 패치, 터미널 / PTY, MCP, 여러 에이전트, 세션 복구, 코드 검토를 포함한 작업 흐름용 실행 스크립트 제공 |
| 📡 **스트리밍** | JSON 및 SSE 응답, 추론 요약, 도구 호출 이벤트 |
| 🛠️ **도구 호출** | 함수 도구와 여러 턴에 걸친 도구 결과 지원. Responses는 사용자 정의 도구, 네임스페이스, 클라이언트 측 도구 탐색도 지원 |
| 🧠 **작업 이어가기** | Responses의 도구 결과로 동일한 Cursor Run을 재개할 수 있으며 `store=false`에서도 지원 |
| 👁️ **이미지 입력** | 모델이 지원하는 경우 base64로 인라인 삽입한 PNG, JPEG, WebP, GIF 이미지 사용 가능 |
| 🔍 **웹 검색** | Responses의 `web_search` / `web_search_preview`를 Cursor의 네이티브 검색에 매핑 |
| 📐 **구조화된 출력** | Responses에서 `json_object` / `json_schema`에 대한 모델 지시와 최종 출력 검증 지원 |
| 💬 **기록 및 압축** | `previous_response_id`, 응답 조회 / 삭제, 입력 페이지 분할, 암호화된 압축 체크포인트 |
| 🔀 **여러 계정** | 라운드 로빈 선택, 파일 핫 리로드, 자동 토큰 갱신, 인증 또는 사용 한도 오류 이후 일시 대기 |
| 🤖 **동적 모델 탐색** | 계정별 모델 목록과 캐시. 기존 `cursor-` 접두사가 붙은 모델 이름도 지원 |
| 🌐 **SOCKS5 프록시** | 로그인 상태 폴링, 모델 탐색, 생성, 토큰 갱신에 적용. 사용자 이름 / 비밀번호 인증 지원 |
| 🐳 **배포 및 진단** | Docker Compose, systemd 예제, 대화형 API 문서, 요청 ID가 포함된 로그 |

자세한 제한은 [호환성](#compatibility)을 참고하세요. 도구 실행과 권한 관리는 호출하는 클라이언트가 담당합니다.

<a id="models"></a>

## 🤖 사용 가능한 모델

게이트웨이는 해당 요청에 선택된 계정의 모델 목록을 가져옵니다. 로그인하고 서비스를 시작한 뒤 실행하세요.

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

반환된 `data[].id` 중 하나를 클라이언트의 모델 설정에 사용하세요. 이 문서의 예제는 `auto`를 사용합니다. 계정에서 지원하지 않는다면 목록에서 사용 가능한 모델을 선택하세요.

- 기본적으로 모델 이름에서 업스트림의 `cursor-` 접두사를 제거합니다. 예를 들어 `grok-4.6-medium`은 실제 업스트림 ID에 매핑됩니다.
- 기존 `cursor-` 접두사 이름도 계속 사용할 수 있습니다. 클라이언트에 노출할 이름을 바꾸려면 `CURSOR_DIRECT_MODEL_PREFIX`를 설정하세요.
- 모델 목록은 10분간 캐시됩니다. 탐색에 실패하면 이전 캐시 또는 대체 목록을 사용하고 30초 후 다시 시도합니다.

> [!NOTE]
> 대체 목록은 탐색 실패 시 사용되며, 나열된 모든 모델에 대한 접근을 보장하지 않습니다. 여러 계정을 사용하는 경우 각 요청에 선택된 계정의 목록이 반환됩니다.

<a id="quick-start"></a>

## 🚀 빠른 시작

개발과 디버깅에는 **Python 직접 실행**을, 컨테이너 배포에는 **[Docker Compose](#docker)** 를 선택하세요.

### 사전 요구 사항

- **Python 3.14+**. 개발, 테스트, Docker 이미지에는 Python 3.14를 사용합니다.
- 로그인할 수 있고 사용 한도가 남아 있는 Cursor 계정.
- Cursor 서비스에 직접 또는 [SOCKS5 프록시](#proxy)를 통해 연결할 수 있는 네트워크 환경.

### 1. 프로젝트 다운로드 및 설치

이 저장소 페이지의 URL로 복제하거나 **Code → Download ZIP**을 선택하여 압축을 푸세요.

```bash
git clone https://github.com/hnewcity/cursor-gateway.git
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

별도 안내가 없으면 이후의 모든 명령은 저장소 루트에서 실행하세요.

<details>
<summary>🪟 Windows PowerShell 설치</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

Windows에서는 이후 예제의 `.venv/bin/python`과 `.venv/bin/cursor-gateway`를 각각 `.venv\Scripts\python.exe`와 `.venv\Scripts\cursor-gateway.exe`로 바꾸세요.

</details>

### 2. Cursor에 로그인

```bash
.venv/bin/cursor-gateway login
```

터미널에 표시된 URL을 브라우저에서 열고 로그인을 승인하세요. [로컬 로그인 정보를 가져오거나](#accounts) 기존 계정 파일을 사용할 수도 있습니다. 인증 정보는 기본적으로 저장소 루트의 `accounts.json`에 저장됩니다.

### 3. 서비스 시작

```bash
.venv/bin/cursor-gateway serve
```

기본 주소는 `http://127.0.0.1:8790`입니다. 서비스는 현재 디렉터리의 `.env`를 읽으며, 이미 설정된 환경 변수가 우선합니다.

```bash
# Set the listen address and port
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# Alternatively, start through the Python module
.venv/bin/python -m cursor_gateway serve
```

### 4. 첫 요청 보내기

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello! Please introduce yourself."}]}'
```

> [!TIP]
> 게이트웨이 API를 보호하려면 `.env`에 `CURSOR_DIRECT_API_KEY=sk-your-secret`를 설정하고 클라이언트에도 동일한 키를 지정하세요. 이 게이트웨이 키는 Cursor 계정 토큰과 별개입니다.
> 요청 예제는 터미널 환경에서 키를 읽습니다. 서버의 `.env`에만 설정했다면 클라이언트에 사용하는 터미널에서 `export CURSOR_DIRECT_API_KEY="sk-your-secret"`를 실행하세요.

<a id="accounts"></a>

## 🔐 계정 설정

환경에 맞는 방법을 선택하세요. 계정 파일이 이미 있다면 방법 3으로 이동할 수 있습니다.

### 방법 1: 브라우저 로그인

로컬과 원격 서버 모두에서 사용할 수 있습니다. 서버가 출력한 URL을 본인의 컴퓨터에서 열면 됩니다.

```bash
.venv/bin/cursor-gateway login
```

로그인 상태 폴링에 사용할 프록시를 지정하려면:

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### 방법 2: 로컬 로그인 정보 가져오기

같은 컴퓨터의 **Cursor 데스크톱 앱**에 로그인되어 있다면 SQLite 데이터베이스에서 인증 정보를 가져올 수 있습니다.

```bash
.venv/bin/cursor-gateway import-local

# Use a custom data directory
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 서버 배포용 Cursor CLI / 데스크톱 계정 내보내기</summary>

독립 실행형 [인증 정보 내보내기 스크립트](../../scripts/export_cursor_credentials.py)는 Python 표준 라이브러리만 사용합니다. 게이트웨이를 설치할 필요가 없으며, 네트워크 요청을 하거나 인증 정보를 자동 전송하지 않습니다.

```bash
# Run from the repository root to create a server-ready account file
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# Use only the Cursor CLI login
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

Cursor에 로그인된 컴퓨터에 스크립트만 복사해서 사용할 수도 있습니다.

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

기본적으로 스크립트와 같은 디렉터리에 `accounts.json`을 만들며 기존 파일 덮어쓰기는 거부합니다. `--source cli` / `--source desktop`, `--out`, 데스크톱 데이터베이스 지정용 `--db`를 지원합니다. macOS에서는 키체인 접근 권한을 요청할 수 있습니다.

내보낸 파일을 서버의 `data/accounts.json`에 두면 이 저장소의 Docker Compose 설정으로 사용할 수 있습니다.

</details>

### 방법 3: 기존 계정 파일 사용

게이트웨이는 `cursor2api` 계정 형식을 지원합니다. `.env`에 경로를 설정하세요.

```dotenv
CURSOR_DIRECT_AUTH_FILE=/absolute/path/to/accounts.json
```

<details>
<summary>📄 accounts.json 형식</summary>

```json
[
  {
    "label": "main",
    "accessToken": "your-access-token",
    "refreshToken": "your-refresh-token"
  }
]
```

`{"accounts": [...]}` 형식도 지원합니다. `refreshToken`은 선택 사항이지만 자동 갱신에는 필요합니다. 선택 필드인 `expiresAt`과 `disabledUntil`은 ISO 타임스탬프를 받습니다.

로그인, 가져오기, 갱신은 파일 권한을 `0600`으로 설정하여 원자적으로 기록합니다. 기존 파일을 사용하면 자동 갱신된 토큰은 같은 파일에 다시 저장됩니다.

</details>

> [!IMPORTANT]
> `accounts.json`에는 계정에 접근할 수 있는 인증 정보가 들어 있습니다. 비공개로 보관하세요. 계정 파일, `.env`, 압축 키는 `.gitignore`에 포함되어 있습니다.

<a id="multi-account"></a>

## 🔀 여러 계정

`--merge`로 계정을 추가하세요.

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| 동작 | 설명 |
| --- | --- |
| 병합 | `--merge`는 같은 레이블의 계정을 교체하고 나머지는 유지합니다. **생략하면 출력 파일 전체를 교체합니다.** |
| 요청 라우팅 | 새 요청은 사용 가능한 계정을 순환하며 선택. 재개한 네이티브 Run은 원래 계정을 유지 |
| 핫 리로드 | 계정 파일 변경 사항은 재시작 없이 이후 요청에 적용 |
| 토큰 갱신 | 만료까지 30분 이내일 때 갱신 시도. 같은 프로세스의 동시 갱신은 하나로 합쳐 처리 |
| 일시 대기 | 사용 한도 소진, 인증 실패, 권한 오류가 발생하면 60초간 대기. 이후 요청은 다른 사용 가능한 계정을 사용 |

업스트림 오류는 현재 요청에 반환되며, 이미 시작된 생성을 자동으로 재실행하지 않습니다. 각 계정 파일에는 하나의 게이트웨이 프로세스만 쓰도록 구성하세요.

<a id="docker"></a>

## 🐳 Docker 배포

저장소에 `Dockerfile`과 `docker-compose.yml`이 포함되어 있습니다. 저장소 루트에서 실행하세요.

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

컨테이너는 `0.0.0.0:8790`에서 수신하고 호스트 바인딩은 기본적으로 `127.0.0.1:8790`입니다. Compose는 `./data`를 `/data`에 마운트합니다. 계정은 `/data/accounts.json`에 저장되며 압축 키도 기본적으로 같은 디렉터리에 저장됩니다.

<details>
<summary>🔧 자주 사용하는 관리 명령</summary>

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

`CURSOR_DIRECT_PORT`는 호스트에 공개하는 포트를 제어하며 컨테이너 포트는 `8790`으로 유지됩니다. Compose의 계정 경로는 `/data/accounts.json`으로 고정되며 `.env`의 `CURSOR_DIRECT_AUTH_FILE`은 사용하지 않습니다.

컨테이너 안에서 `127.0.0.1`은 그 컨테이너 자신을 가리킵니다. 호스트의 프록시를 사용하려면 컨테이너에서 접근 가능한 주소를 지정하세요. Docker Desktop에서는 네트워크 구성이 허용하는 경우 `host.docker.internal`을 사용할 수 있습니다.

</details>

<details>
<summary>🐧 systemd로 배포</summary>

[deploy/cursor-gateway.service](../../deploy/cursor-gateway.service)에서 예제를 확인하세요.

프로젝트와 가상 환경을 `/opt/cursor-gateway`에 설치하고 `cursor-gateway` 서비스 사용자를 만드세요. 해당 사용자가 프로젝트와 설정을 읽고 `data`에 쓸 수 있도록 권한을 부여하세요. 준비가 끝나면:

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

이 예제는 `/opt/cursor-gateway/data/accounts.json`을 사용하고 프로젝트 루트에서 `.env`를 읽습니다.

</details>

<a id="clients"></a>

## 💡 클라이언트 설정

### OpenAI 호환 클라이언트

| 설정 | 값 |
| --- | --- |
| 기본 URL | `http://127.0.0.1:8790/v1` |
| API 키 | `CURSOR_DIRECT_API_KEY`의 값. 키를 설정하지 않았다면 비어 있지 않은 임의의 문자열 |
| 모델 | `/v1/models`에서 반환하는 모델. 계정에서 이용 가능하다면 `auto` 등 |
| API 프로토콜 | 클라이언트에 따라 Chat Completions 또는 Responses |

다른 컴퓨터의 클라이언트에서는 `127.0.0.1`을 접근 가능한 게이트웨이 주소로 바꾸고 수신 주소나 포트 매핑을 조정하세요.

### Codex CLI

Codex CLI를 설치하고 게이트웨이를 시작한 뒤 포함된 실행 스크립트를 사용하세요.

```bash
# Interactive use
.venv/bin/python scripts/run_codex.py --model auto

# Run a coding task
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write 'Create hello.py, run it, and check the output'
```

실행 스크립트는 HTTP/SSE 기반 Responses와 임시 모델 목록을 사용합니다. `~/.codex/config.toml`을 수정하지 않고 기존 설정을 유지합니다. 현재 터미널에서 게이트웨이 키를 환경 변수로 내보내세요. 도구 실행, MCP 승인, 샌드박스는 Codex가 제어합니다.

클라이언트의 기본 컨텍스트 예산은 65,536토큰이며 `--context-window`로 조정할 수 있습니다. 이미지 미지원 모델에는 `--text-only`를, 다른 게이트웨이 주소에는 `--url`을 사용하세요.

세션 복구, 네이티브 Run 이어가기, 압축에 대해서는 [Codex CLI 가이드(영어)](../en/codex-usage.md)를 참고하세요.

### 요청 예제

<details>
<summary>📡 Chat Completions 스트리밍</summary>

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

텍스트 델타는 `choices[].delta.content`에, 추론 델타는 `reasoning_content`에 나타납니다. `include_usage`를 사용하면 마지막 `[DONE]` 앞에 `choices: []`가 포함된 사용량 청크가 추가로 전송됩니다.

</details>

<details>
<summary>💬 Responses API 요청</summary>

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

표시할 텍스트는 `output[].content[]` 안의 `output_text` 항목에 포함됩니다. 타입이 지정된 `response.*` SSE 이벤트를 받으려면 `stream: true`를, 응답 기록을 저장하지 않으려면 `store: false`를 설정하세요.

</details>

<details>
<summary>🐍 Python용 OpenAI SDK</summary>

클라이언트 의존성을 설치하세요.

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

함수 도구, Responses 스트리밍, 기록 이어가기, 자세한 호환성 정보는 [API 레퍼런스(영어)](../en/api-reference.md)를 참고하세요.

</details>

<a id="api"></a>

## 📡 API 엔드포인트

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| `GET` / `HEAD` | `/`, `/health` | 프로세스 실행 상태와 사용 가능한 계정 수. 인증 불필요 |
| `GET` / `HEAD` | `/v1/models` | 선택된 계정의 모델 목록 |
| `POST` | `/v1/chat/completions` | Chat Completions, JSON / SSE |
| `POST` | `/v1/responses` | Responses, JSON / SSE |
| `POST` | `/v1/responses/compact` | 암호화된 압축 체크포인트 생성 |
| `GET` | `/v1/responses/{response_id}` | 저장된 응답 조회 |
| `DELETE` | `/v1/responses/{response_id}` | 응답과 입력 스냅샷 삭제 |
| `GET` | `/v1/responses/{response_id}/input_items` | 입력 기록을 페이지 단위로 조회 |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc, OpenAPI 명세. 인증 불필요 |

`CURSOR_DIRECT_API_KEY`가 설정되면 모든 `/v1/*` 엔드포인트가 `Authorization: Bearer <key>` 또는 `x-api-key` 인증을 받습니다. Swagger UI에서는 **Authorize**를 눌러 키를 입력하세요.

<a id="configuration"></a>

## ⚙️ 설정

[.env.example](../../.env.example)을 `.env`로 복사하고 편집하세요. 주요 설정:

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | 수신 주소 |
| `CURSOR_DIRECT_PORT` | `8790` | 수신 포트 |
| `CURSOR_DIRECT_API_KEY` | 비어 있음 | 클라이언트가 게이트웨이를 호출할 때 사용하는 키 |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | 계정 파일 경로 |
| `CURSOR_DIRECT_PROXY_URL` | 비어 있음 | SOCKS5 프록시 URL |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | 연결과 핸드셰이크를 포함한 턴당 Agent 통신 제한 시간(밀리초) |
| `CURSOR_DIRECT_MODEL_PREFIX` | 비어 있음 | 공개 모델 이름의 접두사. 기본적으로 업스트림의 `cursor-` 접두사를 제거 |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | 요청 요약, ID, 소요 시간 기록. 비활성화해도 오류는 기록 |

<details>
<summary>🔧 전체 고급 설정</summary>

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | 업스트림 HTTP(S) 오리진 |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | 업스트림으로 보내는 클라이언트 버전 헤더 |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | 허용할 업스트림 네이티브 도구. `*`이면 제한 헤더 생략 |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | system / developer 지시를 과거 설정 턴으로 변환 |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | 전체 기록 재전송 시 최근 추론 요약 유지 |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | 재전송할 요약의 총 문자 수 제한. 최신 항목 우선 |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | 한 Run 안에서 도구 입력 형식 수정 시도 횟수. 0~3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | 도구 결과로 대기 중인 네이티브 Run 재개 |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | 클라이언트 도구 결과를 기다리는 최대 시간(초) |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | 유지할 네이티브 Run의 최대 수 |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | 전체 기록 재전송 시 사용할 이어가기 프롬프트 |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | 요청 / 응답 크기 제한. Responses 스트림의 누적 출력도 제한 |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | 응답 기록 보관 시간(초) |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | 저장할 응답의 최대 수 |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | 직렬화된 응답 기록의 최대 크기(바이트) |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | 계정 파일과 같은 디렉터리의 `compaction.key` | 압축 체크포인트 키. 이 파일은 영구 보관 필요 |

모델 탐색과 토큰 갱신에는 별도의 네트워크 제한 시간이 있으므로 첫 요청에 시간이 더 걸릴 수 있습니다.

생성된 protobuf 클래스는 프로젝트에 포함되어 있습니다. 게이트웨이를 시작할 때 `protoc`이 필요하지 않으며 원래 Node 프로젝트의 `CURSOR_DIRECT_PROTO_DIR`도 사용하지 않습니다.

</details>

<a id="proxy"></a>

## 🌐 프록시 지원

`.env`에 프록시를 설정하세요.

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# For username / password authentication, use this format
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

`socks5://`와 `socks5h://` 모두 프록시를 통해 대상 호스트 이름을 확인합니다. 사용자 이름과 비밀번호의 특수 문자는 URL 인코딩하세요. 프록시는 모델 탐색, 생성, 토큰 갱신, 로그인 상태 폴링에 적용됩니다. HTTP 프록시 URL은 현재 지원하지 않습니다.

<a id="faq"></a>

## 🔧 문제 해결

<details>
<summary>상태 확인은 성공하는데 요청이 503을 반환하는 이유는 무엇인가요?</summary>

`/health`는 프로세스가 실행 중인지 확인합니다. `{"ok": true, "accounts": 0, ...}`은 프로세스는 실행 중이지만 사용 가능한 계정이 없다는 뜻입니다. 로그인하지 않았거나 모든 계정이 일시 대기 중일 수 있습니다.

`login` / `import-local`을 실행하고 서비스가 실제로 사용하는 계정 경로를 확인하세요. 로컬 기본값은 `./accounts.json`이며 Docker Compose는 `./data/accounts.json`을 사용합니다. 업스트림에서 발생한 오류라면 반환된 오류 세부 정보로 서비스 가용성을 확인하세요.

</details>

<details>
<summary>왜 400 오류가 발생하나요? 이미지와 도구는 어떻게 보내나요?</summary>

클라이언트의 `error` JSON과 같은 `X-Request-ID`를 가진 로그를 확인하세요. 일반적인 원인:

- `tool_choice="required"`, 강제 도구 선택 또는 기타 지원하지 않는 매개변수.
- 원격 이미지 URL, 파일 ID 또는 오디오 입력. 이미지는 지원 형식의 base64 데이터 URL로 보내야 합니다.
- `file_search`처럼 구현되지 않은 호스팅 도구 또는 지원하지 않는 `include` 필드.
- 잘못된 JSON, 형식이 잘못된 사용자 정의 도구 입력 또는 유효하지 않은 JSON Schema 설정.

Responses는 이미지와 `text.format`을 통한 JSON Schema 출력 검증을 지원합니다. 형식은 [API 레퍼런스(영어)](../en/api-reference.md)를 참고하세요. 로그에 `stage="upstream"`이 표시되면 업스트림 오류 메시지와 선택한 모델을 확인하세요.

</details>

<details>
<summary>특정 요청의 실패 원인은 어떻게 조사하나요?</summary>

기본 로그 수준인 `info`에서 요청 진단 정보를 확인할 수 있습니다. Docker 배포에서는:

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# Replace the placeholder with the X-Request-ID response header value
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F 'REPLACE_WITH_REQUEST_ID'
```

로그 메시지는 한 줄짜리 JSON입니다. 같은 요청의 이벤트는 동일한 `request_id`를 공유합니다.

| 이벤트 | 확인할 내용 |
| --- | --- |
| `request_started` / `request_parsed` | 경로, 클라이언트, 요청 매개변수 요약 |
| `generation_started` | 계정 레이블, 실제 업스트림 모델, 기록 수, 도구 수 |
| `compatibility_notice` | 호환성 매핑 정보. 이 이벤트만으로는 실패를 의미하지 않음 |
| `request_error` | `stage`, `error_status`, `error_param`, `error_message`, 업스트림의 `error_code` |
| `request_finished` | HTTP 상태, `outcome`, 소요 시간, 바이트 수 |

SSE가 시작된 뒤 오류가 발생하면 HTTP 상태가 200으로 남을 수 있습니다. 스트림 오류와 로그의 `outcome`도 확인하세요. 주요 업스트림 오류 매핑:

| 업스트림 오류 | HTTP 상태 |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| 기타 프로토콜 또는 업스트림 오류 | `502` |

로그 요약에는 프롬프트, 메시지 본문, 도구 인수 / 출력, 메타데이터 값, 쿠키, 인증 헤더가 포함되지 않습니다. 오류 텍스트에 있는 알려진 인증 정보는 마스킹됩니다. `CURSOR_DIRECT_LOG_REQUESTS`를 비활성화하면 일반 요청 로그만 꺼집니다.

</details>

<details>
<summary>재시작하면 previous_response_id가 동작하지 않는 이유는 무엇인가요?</summary>

응답 기록은 프로세스 메모리에 저장되며 기본 제한은 1시간, 256개 항목, 128 MiB입니다. 재시작하면 삭제되고 여러 프로세스나 인스턴스 간에 공유되지 않습니다. 캐시에서 찾지 못하면 `404`가 반환됩니다.

클라이언트에서 기록을 관리하려면 `store=false`를 사용하고 전체 입력, 이전 출력, 도구 결과를 보내세요. 압축 체크포인트는 `compaction.key`에 의존하며 같은 키를 영구 보관하면 재시작 후에도 디코딩할 수 있습니다. 체크포인트와 응답 ID 저장은 별개의 방식입니다.

`previous_response_id`를 사용할 때는 매 턴 필요한 `instructions`와 도구 정의를 다시 제공하세요.

</details>

<a id="compatibility"></a>

## 📋 호환성

| 항목 | 구현 및 제한 |
| --- | --- |
| API 프로토콜 | Chat Completions, Responses, Models 지원. Anthropic `/v1/messages`, Embeddings, 관리 UI는 미지원 |
| 이미지 | 두 생성 API 모두 인라인 PNG / JPEG / WebP / GIF 지원. 이미지당 최대 16 MiB, 요청당 32개이며 전체 본문 크기 제한도 적용. 원격 URL, 파일 ID, 오디오는 미지원 |
| 도구 | 함수 / 사용자 정의 도구는 클라이언트가 실행. `tool_choice`는 `auto` / `none` 지원. `parallel_tool_calls`를 활성화하면 같은 배치로 들어온 호출을 모으며, 병렬 호출 생성 여부는 업스트림 모델에 따라 달라짐 |
| 구조화된 출력 | Responses는 모델에 지시하고 최종 답변을 검증하며 네이티브 제약 디코딩은 수행하지 않음. Chat Completions의 `response_format`은 효과 없음 |
| 샘플링 및 추론 제어 | `temperature`, `top_p`, 토큰 제한 등의 매개변수는 업스트림에서 완전히 적용되지 않음. Chat Completions는 `n=1`만 지원 |
| 추론 상태 | 표시 가능한 추론 요약을 제공. OpenAI의 `reasoning.encrypted_content`를 생성하거나 복호화하지 않음 |
| 토큰 집계 | Chat Completions는 프롬프트 토큰 수를 0으로 보고. Responses 입력 토큰은 `estimated=true`로 표시한 추정값. 업스트림 집계는 출력 토큰에 매핑되며 별도의 캐시 / 추론 과금 내역은 제공되지 않음 |
| 웹 검색 | Responses는 Cursor의 네이티브 검색을 사용하며 OpenAI의 위치 또는 도메인 필터 옵션은 미지원 |
| 전송 및 호스팅 기능 | HTTP/SSE 사용. Responses WebSocket, `background=true`, 호스팅된 `conversation` / `prompt`, 기타 호스팅 내장 도구는 미지원. 클라이언트 연결 해제 시 업스트림 요청 취소 |

system / developer 지시는 기본적으로 출처 레이블을 붙인 과거 메시지로 전달되며 효과는 업스트림의 프롬프트 처리에 따라 달라집니다. `CURSOR_ALLOWED_NATIVE_TOOLS=*`를 사용해도 게이트웨이가 클라이언트의 셸 명령, 파일 작업, 패치를 호스트에서 실행하지는 않습니다.

매개변수의 자세한 동작은 [API 레퍼런스(영어)](../en/api-reference.md)를, 클라이언트 설정은 [Codex CLI 가이드(영어)](../en/codex-usage.md)를 참고하세요.

<a id="development"></a>

## 🧪 개발 및 검증

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

자동 테스트는 가상 인증 정보와 로컬 모의 업스트림을 사용합니다. 계정 갱신, 요청 검증, JSON / SSE, 도구 루프, Responses 기록, 취소, 로컬 TCP 연결을 통한 HTTP/2 / protobuf 전송을 검증합니다. 실제 인증 정보, 유료 추론, Codex CLI는 필요하지 않습니다.

<details>
<summary>🛠️ 프로토콜 코드 생성</summary>

프로토콜 정의를 변경한 뒤에는 `protoc 36.1`로 Python 클래스를 다시 생성하세요.

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 프로젝트 구조</summary>

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

## 🤝 기여하기

재현 가능한 버그나 기능 논의에는 Issues를 사용하고, 풀 리퀘스트를 보내기 전에 [기여 가이드(중국어 / 영어)](../../CONTRIBUTING.md)를 읽어 주세요.
동작, 설정, 예제를 변경하면 8개 언어의 README와 중국어 및 영어 가이드를 함께 갱신하고 [행동 강령(중국어 / 영어)](../../CODE_OF_CONDUCT.md)을 따라 주세요.
취약점은 [보안 정책(중국어 / 영어)](../../SECURITY.md)에 따라 비공개로 보고하세요. 버전별 변경 사항은 [변경 기록(영어)](../../CHANGELOG.md)을 참고하세요.

<a id="credits"></a>

## 🙏 감사 및 라이선스

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api): 이 프로젝트의 이식 원본. 프로토콜 매핑, 계정 형식, 대체 모델 목록을 포함합니다.
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi): 원본 프로젝트에서 출처로 명시한 Cursor 공급자 / `agent.proto`의 원본입니다.
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway): 이 README의 레이아웃과 문서 구조를 참고한 프로젝트입니다.

이 프로젝트는 **[AGPL-3.0-only](../../LICENSE)** 라이선스로 제공됩니다. 전체 출처 표시는 [NOTICE](../../NOTICE)를 참고하세요.

수정한 버전을 다른 사람에게 배포하거나 제공할 때는 해당 소스 코드 제공에 관한 AGPL 요구 사항을 준수하세요. 실행 중인 버전의 전체 소스를 저장소 또는 소스 배포본으로 제공하고, 네트워크 사용자가 소스에 접근할 수 있는 명확한 경로를 마련하세요. 컨테이너 빌드에서는 `--build-arg SOURCE_URL=PUBLIC_SOURCE_URL`로 공개 소스 위치를 기록할 수 있습니다.
