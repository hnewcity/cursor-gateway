<div align="center">

# ⚡ Cursor Gateway

**Cursor アカウントを OpenAI 互換 API に接続**

[English](../en/README.md) · [Русский](../ru/README.md) · [简体中文](../../README.md) · [Español](../es/README.md) · [Bahasa Indonesia](../id/README.md) · [Português (Brasil)](../pt-BR/README.md) · **日本語** · [한국어](../ko/README.md)

使い慣れたクライアントから、Cursor アカウントで利用可能なモデルを呼び出せます。Chat Completions、Responses API、Codex CLI に対応しています。

[![CI](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](../../LICENSE)

[機能](#features) · [クイックスタート](#quick-start) · [アカウント](#accounts) · [Docker](#docker) · [クライアント設定](#clients) · [トラブルシューティング](#faq) · [スポンサー](#sponsors)

</div>

---

<a id="sponsors"></a>

## ❤️ スポンサー

<table>
<tr>
<td width="180" align="center"><a href="https://ai18n.chat"><img src="../assets/sponsors/ai18n.png" alt="ai18n" width="150"></a></td>
<td>本プロジェクトをご支援いただいている <a href="https://ai18n.chat"><strong>ai18n</strong></a> に感謝します！ai18n は、OpenClaw、Claude Code、Codex、Gemini などのツール向けに AI API の中継サービスを提供しています。</td>
</tr>
</table>

---

Cursor Gateway は [cursor2api](https://github.com/AstroQore/cursor2api) の Python 移植版です。FastAPI で HTTP リクエストを処理し、HTTP/2 と protobuf を使って Cursor の Agent バックエンドに直接接続します。ゲートウェイの実行に Node.js、Cursor CLI、ブラウザーの自動操作は必要ありません。

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
> 本プロジェクトは非公式のクライアントであり、Anysphere との提携関係や同社による承認はありません。ご自身の Cursor アカウントを使用してください。利用可能なモデルと使用枠は、アカウントと上流サービスに依存します。

<a id="features"></a>

## ✨ 機能

| 機能 | 説明 |
| --- | --- |
| 🔌 **OpenAI 互換 API** | `/v1/models`、`/v1/chat/completions`、`/v1/responses` |
| 💻 **Codex CLI 連携** | ファイルへのパッチ適用、ターミナル / PTY、MCP、複数エージェント、セッション復元、コードレビューに対応する起動スクリプトを同梱 |
| 📡 **ストリーミング** | JSON / SSE レスポンス、推論の要約、ツール呼び出しイベント |
| 🛠️ **ツール呼び出し** | 関数ツールと複数ターンにわたるツール結果に対応。Responses ではカスタムツール、名前空間、クライアント側でのツール検出も利用可能 |
| 🧠 **タスクの継続** | Responses のツール結果で同じ Cursor Run を再開可能。`store=false` にも対応 |
| 👁️ **画像入力** | モデルが対応している場合、base64 で埋め込んだ PNG、JPEG、WebP、GIF 画像を入力可能 |
| 🔍 **ウェブ検索** | Responses の `web_search` / `web_search_preview` を Cursor のネイティブ検索に変換 |
| 📐 **構造化出力** | Responses で `json_object` / `json_schema` 用のモデルへの指示と最終出力の検証をサポート |
| 💬 **履歴と圧縮** | `previous_response_id`、レスポンスの取得 / 削除、入力のページ分割、暗号化された圧縮チェックポイント |
| 🔀 **複数アカウント** | ラウンドロビン選択、ファイルのホットリロード、トークンの自動更新、認証エラーや使用枠不足後のクールダウン |
| 🤖 **動的なモデル検出** | アカウントごとのモデル一覧とキャッシュ。従来の `cursor-` 付きモデル名にも対応 |
| 🌐 **SOCKS5 プロキシ** | ログイン状況のポーリング、モデル検出、生成、トークン更新を中継。ユーザー名 / パスワード認証に対応 |
| 🐳 **デプロイと診断** | Docker Compose、systemd の設定例、対話型 API ドキュメント、リクエスト ID 付きログ |

制限の詳細は[互換性](#compatibility)を参照してください。ツールの実行と権限管理は、呼び出し元のクライアントが担当します。

<a id="models"></a>

## 🤖 利用可能なモデル

ゲートウェイは、そのリクエストに選ばれたアカウントのモデル一覧を取得します。ログインしてサービスを起動した後、次を実行します。

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

返された `data[].id` のいずれかをクライアントのモデル設定に指定します。このドキュメントの例では `auto` を使用します。アカウントで利用できない場合は、一覧から利用可能なモデルを選んでください。

- デフォルトでは、上流の `cursor-` プレフィックスをモデル名から除去します。たとえば `grok-4.6-medium` は実際の上流 ID に対応付けられます。
- 従来の `cursor-` 付きの名前も使用できます。クライアントに公開する名前を変更するには、`CURSOR_DIRECT_MODEL_PREFIX` を設定します。
- モデル一覧は 10 分間キャッシュされます。検出に失敗した場合は、古いキャッシュまたはフォールバック一覧を使用し、30 秒後に再試行します。

> [!NOTE]
> フォールバック一覧は検出に失敗した場合に使用されるもので、記載されたすべてのモデルへのアクセスを保証するものではありません。複数アカウントがある場合、各リクエストで選択されたアカウントの一覧が返されます。

<a id="quick-start"></a>

## 🚀 クイックスタート

開発やデバッグには **Python で直接実行する方法**、コンテナでのデプロイには **[Docker Compose](#docker)** を選んでください。

### 前提条件

- **Python 3.14+**。開発、テスト、Docker イメージでは Python 3.14 を使用しています。
- ログイン可能で、利用枠の残っている Cursor アカウント。
- Cursor のサービスへのネットワーク接続。直接接続または [SOCKS5 プロキシ](#proxy)を使用できます。

### 1. プロジェクトの取得とインストール

このリポジトリのページにある URL でクローンするか、**Code → Download ZIP** を選んでアーカイブを展開します。

```bash
git clone https://github.com/hnewcity/cursor-gateway.git
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

特に指定がない限り、以降のコマンドはリポジトリのルートで実行してください。

<details>
<summary>🪟 Windows PowerShell でのインストール</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

Windows では、以降の例にある `.venv/bin/python` と `.venv/bin/cursor-gateway` を、それぞれ `.venv\Scripts\python.exe` と `.venv\Scripts\cursor-gateway.exe` に置き換えてください。

</details>

### 2. Cursor にログイン

```bash
.venv/bin/cursor-gateway login
```

ターミナルに表示された URL をブラウザーで開き、ログインを承認します。[ローカルのログイン情報をインポート](#accounts)するか、既存のアカウントファイルを使用することもできます。認証情報は、デフォルトではリポジトリのルートにある `accounts.json` に保存されます。

### 3. サービスの起動

```bash
.venv/bin/cursor-gateway serve
```

デフォルトのアドレスは `http://127.0.0.1:8790` です。サービスは現在のディレクトリの `.env` を読み込みます。既存の環境変数が優先されます。

```bash
# Set the listen address and port
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# Alternatively, start through the Python module
.venv/bin/python -m cursor_gateway serve
```

### 4. 最初のリクエストを送信

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello! Please introduce yourself."}]}'
```

> [!TIP]
> ゲートウェイ API を保護するには、`.env` に `CURSOR_DIRECT_API_KEY=sk-your-secret` を設定し、クライアントにも同じキーを指定します。このゲートウェイ用キーは Cursor アカウントのトークンとは別のものです。
> リクエスト例はターミナルの環境変数からキーを読み取ります。サーバーの `.env` だけに設定した場合は、クライアントを使うターミナルで `export CURSOR_DIRECT_API_KEY="sk-your-secret"` を実行してください。

<a id="accounts"></a>

## 🔐 アカウント設定

環境に合う方法を選んでください。すでにアカウントファイルがある場合は、方法 3 に進めます。

### 方法 1: ブラウザーでログイン

ローカルでもリモートサーバーでも利用できます。サーバーが表示する URL を、ご自身のコンピューターで開いてください。

```bash
.venv/bin/cursor-gateway login
```

ログイン状況のポーリングにプロキシを指定する場合:

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### 方法 2: ローカルのログイン情報をインポート

同じコンピューターの **Cursor デスクトップアプリ**にログイン済みの場合、SQLite データベースから認証情報をインポートできます。

```bash
.venv/bin/cursor-gateway import-local

# Use a custom data directory
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 サーバーへのデプロイ用に Cursor CLI / デスクトップのアカウントをエクスポート</summary>

単独で使える[認証情報エクスポートスクリプト](../../scripts/export_cursor_credentials.py)は、Python 標準ライブラリのみを使用します。ゲートウェイのインストールは不要で、ネットワークリクエストや認証情報の自動送信も行いません。

```bash
# Run from the repository root to create a server-ready account file
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# Use only the Cursor CLI login
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

Cursor にログイン済みのコンピューターに、スクリプトだけをコピーして使用することもできます。

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

デフォルトでは、スクリプトと同じディレクトリに `accounts.json` を作成し、既存ファイルの上書きは拒否します。`--source cli` / `--source desktop`、`--out`、デスクトップのデータベースを指定する `--db` に対応しています。macOS ではキーチェーンへのアクセスを求められる場合があります。

エクスポートしたファイルをサーバーの `data/accounts.json` に配置すると、このリポジトリの Docker Compose 設定で使用できます。

</details>

### 方法 3: 既存のアカウントファイルを使用

ゲートウェイは `cursor2api` のアカウント形式に対応しています。`.env` にパスを設定します。

```dotenv
CURSOR_DIRECT_AUTH_FILE=/absolute/path/to/accounts.json
```

<details>
<summary>📄 accounts.json の形式</summary>

```json
[
  {
    "label": "main",
    "accessToken": "your-access-token",
    "refreshToken": "your-refresh-token"
  }
]
```

`{"accounts": [...]}` 形式にも対応しています。`refreshToken` は任意ですが、自動更新には必要です。任意の `expiresAt` と `disabledUntil` には ISO 形式のタイムスタンプを指定できます。

ログイン、インポート、更新では、ファイル権限を `0600` に設定してアトミックに書き込みます。既存ファイルを使用する場合、自動更新したトークンは同じファイルに書き戻されます。

</details>

> [!IMPORTANT]
> `accounts.json` には、アカウントへのアクセスを許可する認証情報が含まれています。公開しないでください。アカウントファイル、`.env`、圧縮用キーは `.gitignore` に含まれています。

<a id="multi-account"></a>

## 🔀 複数アカウント

`--merge` でアカウントを追加します。

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| 動作 | 説明 |
| --- | --- |
| マージ | `--merge` は同じラベルのアカウントを置き換え、それ以外を保持します。**省略すると出力ファイル全体が置き換えられます。** |
| リクエストの振り分け | 新しいリクエストは利用可能なアカウントを順番に使用。再開したネイティブ Run は元のアカウントを維持 |
| ホットリロード | アカウントファイルの変更は、再起動せずに後続のリクエストへ反映 |
| トークン更新 | 有効期限まで 30 分以内になると更新を試行。同一プロセス内の同時更新はまとめて処理 |
| クールダウン | 利用枠の枯渇、認証失敗、権限エラーで 60 秒間のクールダウン。後続リクエストは他の利用可能なアカウントを使用 |

上流エラーは現在のリクエストに返され、開始済みの生成が自動で再実行されることはありません。各アカウントファイルへの書き込みは、単一のゲートウェイプロセスで行ってください。

<a id="docker"></a>

## 🐳 Docker でのデプロイ

リポジトリには `Dockerfile` と `docker-compose.yml` が含まれています。リポジトリのルートで実行します。

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

コンテナは `0.0.0.0:8790` で待ち受け、ホスト側の公開先はデフォルトで `127.0.0.1:8790` です。Compose は `./data` を `/data` にマウントします。アカウントは `/data/accounts.json` に保存され、圧縮用キーもデフォルトでは同じディレクトリに保存されます。

<details>
<summary>🔧 よく使う管理コマンド</summary>

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

`CURSOR_DIRECT_PORT` はホストに公開するポートを指定します。コンテナのポートは `8790` のままです。Compose のアカウントパスは `/data/accounts.json` に固定され、`.env` の `CURSOR_DIRECT_AUTH_FILE` は使用しません。

コンテナ内の `127.0.0.1` は、そのコンテナ自身を指します。ホストのプロキシを利用するには、コンテナから到達できるアドレスを指定してください。Docker Desktop では、ネットワーク構成が対応していれば `host.docker.internal` を使用できます。

</details>

<details>
<summary>🐧 systemd でデプロイ</summary>

設定例は [deploy/cursor-gateway.service](../../deploy/cursor-gateway.service) を参照してください。

プロジェクトと仮想環境を `/opt/cursor-gateway` にインストールし、サービス用ユーザー `cursor-gateway` を作成します。そのユーザーにプロジェクトと設定の読み取り、および `data` への書き込みを許可します。準備後に実行します。

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

この例では `/opt/cursor-gateway/data/accounts.json` を使用し、プロジェクトのルートから `.env` を読み込みます。

</details>

<a id="clients"></a>

## 💡 クライアント設定

### OpenAI 互換クライアント

| 設定 | 値 |
| --- | --- |
| ベース URL | `http://127.0.0.1:8790/v1` |
| API キー | `CURSOR_DIRECT_API_KEY` の値。キー未設定の場合は、空でない任意の文字列 |
| モデル | `/v1/models` が返すモデル。アカウントで利用可能なら `auto` など |
| API プロトコル | クライアントに応じて Chat Completions または Responses |

別のコンピューターから接続する場合は、`127.0.0.1` を到達可能なゲートウェイのアドレスに置き換え、待ち受けアドレスやポートマッピングを調整してください。

### Codex CLI

Codex CLI をインストールし、ゲートウェイを起動してから、同梱の起動スクリプトを実行します。

```bash
# Interactive use
.venv/bin/python scripts/run_codex.py --model auto

# Run a coding task
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write 'Create hello.py, run it, and check the output'
```

起動スクリプトは HTTP/SSE 経由の Responses と一時的なモデル一覧を使用します。`~/.codex/config.toml` は編集せず、通常の設定を保持します。現在のターミナルでゲートウェイのキーをエクスポートしてください。ツールの実行、MCP の承認、サンドボックスは Codex が管理します。

クライアントのデフォルトのコンテキスト予算は 65,536 トークンです。`--context-window` で変更できます。画像非対応モデルには `--text-only`、別のゲートウェイアドレスには `--url` を指定します。

セッションの復元、ネイティブ Run の継続、圧縮については [Codex CLI ガイド（英語）](../en/codex-usage.md)を参照してください。

### リクエスト例

<details>
<summary>📡 Chat Completions のストリーミング</summary>

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

テキスト差分は `choices[].delta.content`、推論の差分は `reasoning_content` に格納されます。`include_usage` を指定すると、最後の `[DONE]` の前に `choices: []` を持つ使用量チャンクが追加で送信されます。

</details>

<details>
<summary>💬 Responses API のリクエスト</summary>

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

表示用テキストは `output[].content[]` 内の `output_text` 項目に格納されます。型付きの `response.*` SSE イベントを受け取るには `stream: true`、レスポンス履歴を保存しない場合は `store: false` を指定します。

</details>

<details>
<summary>🐍 Python 用 OpenAI SDK</summary>

クライアントの依存パッケージをインストールします。

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

関数ツール、Responses のストリーミング、履歴の継続、互換性の詳細は [API リファレンス（英語）](../en/api-reference.md)を参照してください。

</details>

<a id="api"></a>

## 📡 API エンドポイント

| メソッド | パス | 用途 |
| --- | --- | --- |
| `GET` / `HEAD` | `/`, `/health` | プロセスの稼働状態と利用可能なアカウント数。認証不要 |
| `GET` / `HEAD` | `/v1/models` | 選択されたアカウントのモデル一覧 |
| `POST` | `/v1/chat/completions` | Chat Completions、JSON / SSE |
| `POST` | `/v1/responses` | Responses、JSON / SSE |
| `POST` | `/v1/responses/compact` | 暗号化された圧縮チェックポイントを生成 |
| `GET` | `/v1/responses/{response_id}` | 保存済みレスポンスを取得 |
| `DELETE` | `/v1/responses/{response_id}` | レスポンスとその入力スナップショットを削除 |
| `GET` | `/v1/responses/{response_id}/input_items` | 入力履歴をページ分割して取得 |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI、ReDoc、OpenAPI 定義。認証不要 |

`CURSOR_DIRECT_API_KEY` が設定されている場合、すべての `/v1/*` エンドポイントは `Authorization: Bearer <key>` または `x-api-key` による認証を受け付けます。Swagger UI では **Authorize** からキーを入力します。

<a id="configuration"></a>

## ⚙️ 設定

[.env.example](../../.env.example) を `.env` にコピーして編集します。よく使う設定:

| 環境変数 | デフォルト | 説明 |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | 待ち受けアドレス |
| `CURSOR_DIRECT_PORT` | `8790` | 待ち受けポート |
| `CURSOR_DIRECT_API_KEY` | 空 | クライアントがゲートウェイを呼び出すためのキー |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | アカウントファイルのパス |
| `CURSOR_DIRECT_PROXY_URL` | 空 | SOCKS5 プロキシの URL |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | 接続とハンドシェイクを含む、ターンごとの Agent 通信タイムアウト（ミリ秒） |
| `CURSOR_DIRECT_MODEL_PREFIX` | 空 | 公開するモデル名のプレフィックス。デフォルトでは上流の `cursor-` を除去 |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | リクエストの要約、ID、所要時間を記録。無効でもエラーは記録 |

<details>
<summary>🔧 すべての詳細設定</summary>

| 環境変数 | デフォルト | 説明 |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | 上流の HTTP(S) オリジン |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | 上流に送るクライアントバージョンヘッダー |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | 許可する上流のネイティブツール。`*` で制限ヘッダーを省略 |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | system / developer 指示を過去の設定ターンに変換 |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | 全履歴を再送するときに最近の推論要約を保持 |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | 再送する要約の合計文字数上限。新しい項目を優先 |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | 1 つの Run 内でツール入力の形式修正を試行する回数。0〜3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | ツール結果で待機中のネイティブ Run を再開 |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | クライアントのツール結果を待つ最大時間（秒） |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | 保持するネイティブ Run の最大数 |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | 全履歴の再送時に使う継続プロンプト |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | リクエスト / レスポンスのサイズ上限。Responses のストリームでは累積出力も制限 |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | レスポンス履歴の保持時間（秒） |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | 保存するレスポンスの最大数 |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | シリアル化したレスポンス履歴の最大サイズ（バイト） |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | アカウントファイルと同じディレクトリの `compaction.key` | 圧縮チェックポイント用のキー。このファイルを永続化すること |

モデル検出とトークン更新には別々のネットワークタイムアウトがあるため、最初のリクエストには追加の時間がかかる場合があります。

生成済みの protobuf クラスはプロジェクトに同梱されています。ゲートウェイの起動に `protoc` は不要で、元の Node プロジェクトの `CURSOR_DIRECT_PROTO_DIR` も使用しません。

</details>

<a id="proxy"></a>

## 🌐 プロキシ対応

`.env` にプロキシを設定します。

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# For username / password authentication, use this format
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

`socks5://` と `socks5h://` はどちらも、接続先ホスト名をプロキシ経由で解決します。ユーザー名とパスワードの特殊文字は URL エンコードしてください。プロキシはモデル検出、生成、トークン更新、ログイン状況のポーリングに適用されます。HTTP プロキシの URL には現在対応していません。

<a id="faq"></a>

## 🔧 トラブルシューティング

<details>
<summary>ヘルスチェックは成功するのに、リクエストが 503 になるのはなぜですか？</summary>

`/health` はプロセスの稼働を確認します。`{"ok": true, "accounts": 0, ...}` は、プロセスは動作しているものの利用可能なアカウントがないことを示します。未ログイン、または全アカウントがクールダウン中の可能性があります。

`login` / `import-local` を実行し、サービスが実際に使用しているアカウントパスを確認してください。ローカルのデフォルトは `./accounts.json`、Docker Compose では `./data/accounts.json` です。上流由来のエラーなら、返されたエラー詳細からサービスの稼働状況を調べてください。

</details>

<details>
<summary>400 が返るのはなぜですか？画像やツールはどう送りますか？</summary>

クライアントの `error` JSON と、同じ `X-Request-ID` のログを確認してください。よくある原因:

- `tool_choice="required"`、ツールの強制選択、その他の非対応パラメーター。
- リモート画像 URL、ファイル ID、音声入力。画像は対応形式を base64 の data URL で送る必要があります。
- `file_search` などの未実装のホスト型ツール、または非対応の `include` フィールド。
- 不正な JSON、カスタムツール入力の形式不備、無効な JSON Schema 設定。

Responses は画像に対応し、`text.format` による JSON Schema 出力検証もサポートします。形式は [API リファレンス（英語）](../en/api-reference.md)を参照してください。ログに `stage="upstream"` があれば、上流のエラーメッセージと選択されたモデルを調べてください。

</details>

<details>
<summary>特定のリクエストの失敗を調べるには？</summary>

デフォルトのログレベル `info` でリクエストの診断情報を確認できます。Docker の場合:

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# Replace the placeholder with the X-Request-ID response header value
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F 'REPLACE_WITH_REQUEST_ID'
```

ログメッセージは 1 行の JSON です。同じリクエストのイベントは共通の `request_id` を持ちます。

| イベント | 確認項目 |
| --- | --- |
| `request_started` / `request_parsed` | パス、クライアント、リクエストパラメーターの要約 |
| `generation_started` | アカウントのラベル、実際の上流モデル、履歴数、ツール数 |
| `compatibility_notice` | 互換性変換の情報。このイベントだけでは失敗を意味しない |
| `request_error` | `stage`、`error_status`、`error_param`、`error_message`、上流の `error_code` |
| `request_finished` | HTTP ステータス、`outcome`、所要時間、バイト数 |

SSE 開始後のエラーでは HTTP ステータスが 200 のままの場合があります。ストリーム内のエラーとログの `outcome` も確認してください。主な上流エラーの対応:

| 上流エラー | HTTP ステータス |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| その他のプロトコルエラーまたは上流エラー | `502` |

ログの要約には、プロンプト、メッセージ本文、ツールの引数 / 出力、メタデータの値、Cookie、認証ヘッダーは含まれません。エラー文に含まれる既知の認証情報はマスクされます。`CURSOR_DIRECT_LOG_REQUESTS` の無効化で停止するのは通常のリクエストログのみです。

</details>

<details>
<summary>再起動すると previous_response_id が使えなくなるのはなぜですか？</summary>

レスポンス履歴はプロセスのメモリに保存され、デフォルトの上限は 1 時間、256 件、128 MiB です。再起動すると消去され、複数のプロセスやインスタンス間では共有されません。キャッシュに見つからない場合は `404` が返ります。

クライアント側で履歴を管理する場合は、`store=false` を使い、完全な入力、前回の出力、ツール結果を送信します。圧縮チェックポイントは `compaction.key` に依存し、同じキーを永続化すれば再起動後も復号できます。チェックポイントとレスポンス ID による保存は別の仕組みです。

`previous_response_id` を使用する場合は、必要な `instructions` とツール定義を毎ターン指定し直してください。

</details>

<a id="compatibility"></a>

## 📋 互換性

| 項目 | 実装と制限 |
| --- | --- |
| API プロトコル | Chat Completions、Responses、Models に対応。Anthropic の `/v1/messages`、Embeddings、管理 UI は非対応 |
| 画像 | 両方の生成 API が埋め込み PNG / JPEG / WebP / GIF に対応。1 枚 16 MiB、1 リクエスト 32 枚までで、リクエスト全体のサイズ上限も適用。リモート URL、ファイル ID、音声は非対応 |
| ツール | 関数 / カスタムツールはクライアントが実行。`tool_choice` は `auto` / `none` に対応。`parallel_tool_calls` を有効にすると同一バッチ内の呼び出しをまとめるが、並列呼び出しの生成は上流モデルに依存 |
| 構造化出力 | Responses はモデルへの指示と最終回答の検証を行う。ネイティブな制約付きデコードは行わない。Chat Completions の `response_format` は効果なし |
| サンプリングと推論の制御 | `temperature`、`top_p`、トークン上限などは上流で完全には適用されない。Chat Completions は `n=1` のみ対応 |
| 推論状態 | 表示可能な推論要約を公開。OpenAI の `reasoning.encrypted_content` の生成や復号は行わない |
| トークン数の集計 | Chat Completions の入力トークン数はゼロ。Responses の入力トークン数は `estimated=true` 付きの推定値。上流のカウントは出力トークン数に対応し、キャッシュ / 推論の個別課金内訳は取得不可 |
| ウェブ検索 | Responses は Cursor のネイティブ検索を使用。OpenAI の位置情報指定やドメインフィルターには非対応 |
| 通信とホスト型機能 | HTTP/SSE を使用。Responses WebSocket、`background=true`、ホスト型の `conversation` / `prompt`、その他のホスト型組み込みツールは非対応。クライアント切断時は上流リクエストをキャンセル |

system / developer 指示は、デフォルトでは出所ラベルを付けた履歴メッセージとして渡されます。その効果は上流のプロンプト処理に依存します。`CURSOR_ALLOWED_NATIVE_TOOLS=*` でも、ゲートウェイがクライアントのシェルコマンド、ファイル操作、パッチをホスト上で実行することはありません。

パラメーターの詳しい動作は [API リファレンス（英語）](../en/api-reference.md)、クライアント設定は [Codex CLI ガイド（英語）](../en/codex-usage.md)を参照してください。

<a id="development"></a>

## 🧪 開発と検証

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

自動テストでは架空の認証情報とローカルの模擬上流サービスを使用します。アカウント更新、リクエスト検証、JSON / SSE、ツールループ、Responses の履歴、キャンセル、ローカル TCP 接続による HTTP/2 / protobuf 通信を検証します。実際の認証情報、有料の推論、Codex CLI は不要です。

<details>
<summary>🛠️ プロトコルコードの生成</summary>

プロトコル定義を変更した後は、`protoc 36.1` を使用して Python クラスを再生成します。

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 プロジェクト構成</summary>

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

## 🤝 コントリビューション

再現可能な不具合や機能の相談には Issues を利用し、プルリクエストの前に[貢献ガイド（中国語 / 英語）](../../CONTRIBUTING.md)をお読みください。
動作、設定、例を変更した場合は、8 言語の README と中英のガイドを同期し、[行動規範（中国語 / 英語）](../../CODE_OF_CONDUCT.md)に従ってください。
脆弱性は[セキュリティポリシー（中国語 / 英語）](../../SECURITY.md)に従い、非公開で報告してください。バージョンごとの変更は[変更履歴（英語）](../../CHANGELOG.md)を参照してください。

<a id="credits"></a>

## 🙏 謝辞とライセンス

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api): 本プロジェクトの移植元。プロトコルの対応付け、アカウント形式、フォールバックのモデル一覧を含みます。
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi): 元プロジェクトが出典として挙げる Cursor プロバイダー / `agent.proto` の提供元。
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway): この README のレイアウトとドキュメント構成の参考元。

本プロジェクトは **[AGPL-3.0-only](../../LICENSE)** で提供されています。帰属表示の全体は [NOTICE](../../NOTICE) を参照してください。

改変版を他者に配布または提供する場合は、対応するソースコードの提供に関する AGPL の要件に従ってください。稼働中のバージョンの完全なソースをリポジトリまたはソース配布物で提供し、ネットワーク利用者がソースにアクセスできる明確な入口を用意してください。コンテナのビルド時には `--build-arg SOURCE_URL=PUBLIC_SOURCE_URL` で公開ソースの場所を記録できます。
