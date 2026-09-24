<div align="center">

# ⚡ Cursor Gateway

**Подключите свой аккаунт Cursor к API, совместимому с OpenAI**

[English](../en/README.md) · **Русский** · [简体中文](../../README.md) · [Español](../es/README.md) · [Bahasa Indonesia](../id/README.md) · [Português (Brasil)](../pt-BR/README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md)

Используйте привычные клиенты с моделями, доступными вашему аккаунту Cursor. Поддерживаются Chat Completions, Responses API и Codex CLI.

[![CI](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](../../LICENSE)

[Возможности](#features) · [Быстрый старт](#quick-start) · [Аккаунты](#accounts) · [Docker](#docker) · [Настройка клиентов](#clients) · [Решение проблем](#faq) · [Спонсор](#sponsors)

</div>

---

<a id="sponsors"></a>

## ❤️ Спонсор

<table>
<tr>
<td width="180" align="center"><a href="https://ai18n.chat"><img src="../assets/sponsors/ai18n.png" alt="ai18n" width="150"></a></td>
<td>Благодарим <a href="https://ai18n.chat"><strong>ai18n</strong></a> за спонсорскую поддержку проекта! ai18n предоставляет услуги проксирования API ИИ для таких инструментов, как OpenClaw, Claude Code, Codex и Gemini.</td>
</tr>
</table>

---

Cursor Gateway — порт [cursor2api](https://github.com/AstroQore/cursor2api) на Python. Он обслуживает HTTP-запросы через FastAPI и напрямую подключается к серверной части Cursor Agent по HTTP/2 и protobuf. Для работы шлюза не нужны Node.js, Cursor CLI или автоматизация браузера.

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
> Это неофициальный клиент, не связанный с Anysphere и не одобренный этой компанией. Используйте собственный аккаунт Cursor. Доступность моделей и квоты зависят от вашего аккаунта и вышестоящего сервиса.

<a id="features"></a>

## ✨ Возможности

| Возможность | Описание |
| --- | --- |
| 🔌 **API, совместимые с OpenAI** | `/v1/models`, `/v1/chat/completions` и `/v1/responses` |
| 💻 **Интеграция с Codex CLI** | Включён скрипт запуска для работы с патчами файлов, терминалами / PTY, MCP, несколькими агентами, восстановлением сессий и проверкой кода |
| 📡 **Потоковая передача** | Ответы JSON и SSE, сводки рассуждений и события вызова инструментов |
| 🛠️ **Вызов инструментов** | Инструменты-функции и результаты инструментов в нескольких ходах; Responses также поддерживает пользовательские инструменты, пространства имён и обнаружение инструментов на стороне клиента |
| 🧠 **Продолжение задач** | Результаты инструментов в Responses позволяют продолжить тот же Cursor Run, в том числе при `store=false` |
| 👁️ **Ввод изображений** | Встроенные изображения PNG, JPEG, WebP и GIF в base64, если модель их поддерживает |
| 🔍 **Веб-поиск** | `web_search` / `web_search_preview` в Responses сопоставляются со встроенным поиском Cursor |
| 📐 **Структурированный вывод** | Responses поддерживает инструкции модели и проверку итогового вывода для `json_object` / `json_schema` |
| 💬 **История и сжатие контекста** | `previous_response_id`, получение / удаление ответов, постраничная выдача ввода и зашифрованные контрольные точки сжатия |
| 🔀 **Несколько аккаунтов** | Выбор по кругу, перечитывание файла без перезапуска, автоматическое обновление токенов и пауза после ошибок аутентификации или исчерпания квоты |
| 🤖 **Динамическое обнаружение моделей** | Списки и кеши моделей для каждого аккаунта; поддерживаются старые имена с префиксом `cursor-` |
| 🌐 **Прокси SOCKS5** | Проксируются опрос статуса входа, обнаружение моделей, генерация и обновление токенов; поддерживаются имя пользователя и пароль |
| 🐳 **Развёртывание и диагностика** | Docker Compose, пример systemd, интерактивная документация API и журналы с идентификаторами запросов |

Подробные ограничения описаны в разделе [Совместимость](#compatibility). Выполнением инструментов и разрешениями управляет вызывающий клиент.

<a id="models"></a>

## 🤖 Доступные модели

Шлюз получает каталог моделей аккаунта, выбранного для запроса. После входа и запуска сервиса:

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

Укажите один из полученных `data[].id` в настройке модели клиента. В примерах используется `auto`; если он недоступен вашему аккаунту, выберите доступную модель из списка.

- По умолчанию префикс `cursor-` вышестоящего сервиса убирается из имён. Например, `grok-4.6-medium` сопоставляется с фактическим идентификатором на сервере.
- Старые имена с `cursor-` по-прежнему работают. Задайте `CURSOR_DIRECT_MODEL_PREFIX`, чтобы изменить имена, предоставляемые клиентам.
- Каталоги моделей кешируются на 10 минут. При сбое обнаружения шлюз использует старый кеш или резервный каталог и повторяет попытку через 30 секунд.

> [!NOTE]
> Резервный каталог используется при сбое обнаружения и не гарантирует доступ ко всем перечисленным моделям. При нескольких аккаунтах каждый запрос возвращает каталог аккаунта, выбранного для этого запроса.

<a id="quick-start"></a>

## 🚀 Быстрый старт

Для разработки и отладки выберите **запуск через Python**, а для развёртывания в контейнере — **[Docker Compose](#docker)**.

### Требования

- **Python 3.14+**. Для разработки, тестирования и образа Docker используется Python 3.14.
- Аккаунт Cursor с возможностью входа и доступной квотой.
- Сетевой доступ к сервисам Cursor напрямую или через [прокси SOCKS5](#proxy).

### 1. Получите проект и установите его

Клонируйте репозиторий по URL на его странице или выберите **Code → Download ZIP** и распакуйте архив.

```bash
git clone https://github.com/hnewcity/cursor-gateway.git
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Если не указано иное, все последующие команды выполняйте из корня репозитория.

<details>
<summary>🪟 Установка в Windows PowerShell</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

В Windows заменяйте `.venv/bin/python` и `.venv/bin/cursor-gateway` в последующих примерах на `.venv\Scripts\python.exe` и `.venv\Scripts\cursor-gateway.exe`.

</details>

### 2. Войдите в Cursor

```bash
.venv/bin/cursor-gateway login
```

Откройте URL из терминала и подтвердите вход в браузере. Также можно [импортировать локальный вход](#accounts) или использовать существующий файл аккаунтов. По умолчанию учётные данные сохраняются в `accounts.json` в корне репозитория.

### 3. Запустите сервис

```bash
.venv/bin/cursor-gateway serve
```

Адрес по умолчанию — `http://127.0.0.1:8790`. Сервис читает `.env` из текущего каталога; уже заданные переменные окружения имеют приоритет.

```bash
# Set the listen address and port
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# Alternatively, start through the Python module
.venv/bin/python -m cursor_gateway serve
```

### 4. Отправьте первый запрос

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello! Please introduce yourself."}]}'
```

> [!TIP]
> Для защиты API шлюза задайте `CURSOR_DIRECT_API_KEY=sk-your-secret` в `.env` и настройте тот же ключ в клиентах. Этот ключ шлюза не является токеном аккаунта Cursor.
> Примеры запросов читают ключ из окружения терминала. Если он задан только в серверном `.env`, выполните `export CURSOR_DIRECT_API_KEY="sk-your-secret"` в терминале клиента.

<a id="accounts"></a>

## 🔐 Настройка аккаунтов

Выберите подходящий способ. Если файл аккаунтов уже есть, переходите к варианту 3.

### Вариант 1: Вход через браузер

Работает локально и на удалённом сервере. Сервер выводит URL, который можно открыть на своём компьютере.

```bash
.venv/bin/cursor-gateway login
```

Чтобы задать прокси для опроса статуса входа:

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### Вариант 2: Импорт локального входа

Если на том же компьютере выполнен вход в **настольное приложение Cursor**, импортируйте учётные данные из его базы SQLite:

```bash
.venv/bin/cursor-gateway import-local

# Use a custom data directory
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 Экспорт аккаунта Cursor CLI / настольного приложения для сервера</summary>

Отдельный [скрипт экспорта учётных данных](../../scripts/export_cursor_credentials.py) использует только стандартную библиотеку Python. Он не требует установки шлюза, не делает сетевых запросов и никуда автоматически не отправляет учётные данные.

```bash
# Run from the repository root to create a server-ready account file
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# Use only the Cursor CLI login
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

Также можно скопировать только скрипт на компьютер, где выполнен вход в Cursor:

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

По умолчанию скрипт создаёт `accounts.json` рядом с собой и отказывается перезаписывать существующий файл. Поддерживаются `--source cli` / `--source desktop`, `--out` и `--db` для базы настольного приложения. macOS может запросить доступ к Связке ключей.

Поместите экспортированный файл в `data/accounts.json` на сервере, чтобы использовать его с конфигурацией Docker Compose из репозитория.

</details>

### Вариант 3: Существующий файл аккаунтов

Шлюз принимает формат аккаунтов `cursor2api`. Задайте путь в `.env`:

```dotenv
CURSOR_DIRECT_AUTH_FILE=/absolute/path/to/accounts.json
```

<details>
<summary>📄 Формат accounts.json</summary>

```json
[
  {
    "label": "main",
    "accessToken": "your-access-token",
    "refreshToken": "your-refresh-token"
  }
]
```

Также принимается формат `{"accounts": [...]}`. Поле `refreshToken` необязательно, но требуется для автоматического обновления. Необязательные поля `expiresAt` и `disabledUntil` принимают временные метки ISO.

Вход, импорт и обновление используют атомарную запись с правами доступа `0600`. При использовании существующего файла автоматическое обновление записывает новые токены в тот же файл.

</details>

> [!IMPORTANT]
> `accounts.json` содержит учётные данные, предоставляющие доступ к аккаунту. Храните его в тайне. Файлы аккаунтов, `.env` и ключи сжатия контекста включены в `.gitignore`.

<a id="multi-account"></a>

## 🔀 Несколько аккаунтов

Добавляйте аккаунты с помощью `--merge`:

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| Поведение | Описание |
| --- | --- |
| Объединение | `--merge` заменяет аккаунт с той же меткой и сохраняет остальные. **Без этого параметра выходной файл заменяется целиком.** |
| Маршрутизация запросов | Новые запросы по очереди используют доступные аккаунты; возобновлённый нативный Run сохраняет исходный аккаунт |
| Перечитывание без перезапуска | Изменения файла аккаунтов применяются к следующим запросам без перезапуска |
| Обновление токенов | Попытка обновления выполняется в течение 30 минут до истечения срока; одновременные обновления объединяются в пределах процесса |
| Временная пауза | Исчерпание квоты, ошибки аутентификации или доступа вызывают паузу на 60 секунд; следующие запросы используют другие доступные аккаунты |

Ошибка вышестоящего сервиса возвращается текущему запросу без автоматического повтора уже начавшейся генерации. В каждый файл аккаунтов должен записывать только один процесс шлюза.

<a id="docker"></a>

## 🐳 Развёртывание в Docker

В репозитории есть `Dockerfile` и `docker-compose.yml`. Выполните из корня репозитория:

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

Контейнер слушает `0.0.0.0:8790`, а на хосте по умолчанию используется привязка к `127.0.0.1:8790`. Compose монтирует `./data` в `/data`. Аккаунты хранятся в `/data/accounts.json`, а ключ сжатия контекста по умолчанию — в том же каталоге.

<details>
<summary>🔧 Основные команды управления</summary>

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

`CURSOR_DIRECT_PORT` задаёт опубликованный порт хоста; порт контейнера остаётся `8790`. Compose фиксирует путь аккаунтов на `/data/accounts.json` и не использует `CURSOR_DIRECT_AUTH_FILE` из `.env`.

Внутри контейнера `127.0.0.1` означает сам контейнер. Для прокси на хосте укажите адрес, доступный из контейнера. В Docker Desktop можно использовать `host.docker.internal`, если это допускает настройка сети.

</details>

<details>
<summary>🐧 Развёртывание с systemd</summary>

Пример доступен в [deploy/cursor-gateway.service](../../deploy/cursor-gateway.service).

Установите проект и виртуальное окружение в `/opt/cursor-gateway`, создайте служебного пользователя `cursor-gateway` и разрешите ему читать проект и конфигурацию и записывать в `data`. После подготовки:

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

Пример использует `/opt/cursor-gateway/data/accounts.json` и читает `.env` из корня проекта.

</details>

<a id="clients"></a>

## 💡 Настройка клиентов

### Клиенты, совместимые с OpenAI

| Параметр | Значение |
| --- | --- |
| Базовый URL | `http://127.0.0.1:8790/v1` |
| Ключ API | Значение `CURSOR_DIRECT_API_KEY`; любая непустая строка, если ключ не задан |
| Модель | Модель из `/v1/models`, например `auto`, если она доступна аккаунту |
| Протокол API | Chat Completions или Responses в зависимости от клиента |

Для клиентов на другом компьютере замените `127.0.0.1` на доступный адрес шлюза и настройте адрес прослушивания или проброс портов.

### Codex CLI

Установите Codex CLI, запустите шлюз и воспользуйтесь включённым скриптом запуска:

```bash
# Interactive use
.venv/bin/python scripts/run_codex.py --model auto

# Run a coding task
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write 'Create hello.py, run it, and check the output'
```

Скрипт использует Responses через HTTP/SSE и временный каталог моделей. Обычная конфигурация сохраняется без изменения `~/.codex/config.toml`. Экспортируйте ключ шлюза в текущем терминале. Codex управляет выполнением инструментов, подтверждениями MCP и песочницей.

По умолчанию бюджет контекста клиента составляет 65 536 токенов; измените его через `--context-window`. Для моделей без поддержки изображений используйте `--text-only`, для другого адреса шлюза — `--url`.

Восстановление сессий, продолжение нативного Run и сжатие контекста описаны в [руководстве Codex CLI (на английском)](../en/codex-usage.md).

### Примеры запросов

<details>
<summary>📡 Потоковый Chat Completions</summary>

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

Фрагменты текста поступают в `choices[].delta.content`, фрагменты рассуждений — в `reasoning_content`. При `include_usage` перед завершающим `[DONE]` отправляется дополнительный блок статистики с `choices: []`.

</details>

<details>
<summary>💬 Запрос к Responses API</summary>

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

Видимый текст содержится в элементах `output_text` внутри `output[].content[]`. Задайте `stream: true` для типизированных SSE-событий `response.*` или `store: false`, чтобы не сохранять историю ответов.

</details>

<details>
<summary>🐍 OpenAI SDK для Python</summary>

Установите клиентскую зависимость:

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

Инструменты-функции, потоковая передача Responses, продолжение истории и подробности совместимости описаны в [справочнике API (на английском)](../en/api-reference.md).

</details>

<a id="api"></a>

## 📡 Эндпоинты API

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` / `HEAD` | `/`, `/health` | Проверка работы процесса и число доступных аккаунтов; аутентификация не требуется |
| `GET` / `HEAD` | `/v1/models` | Каталог моделей выбранного аккаунта |
| `POST` | `/v1/chat/completions` | Chat Completions, JSON / SSE |
| `POST` | `/v1/responses` | Responses, JSON / SSE |
| `POST` | `/v1/responses/compact` | Создание зашифрованной контрольной точки сжатия |
| `GET` | `/v1/responses/{response_id}` | Получение сохранённого ответа |
| `DELETE` | `/v1/responses/{response_id}` | Удаление ответа и снимка его входных данных |
| `GET` | `/v1/responses/{response_id}/input_items` | Получение истории ввода с пагинацией |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc и описание OpenAPI; аутентификация не требуется |

Если задан `CURSOR_DIRECT_API_KEY`, все эндпоинты `/v1/*` принимают аутентификацию через `Authorization: Bearer <key>` или `x-api-key`. В Swagger UI введите ключ через **Authorize**.

<a id="configuration"></a>

## ⚙️ Конфигурация

Скопируйте [.env.example](../../.env.example) в `.env` и отредактируйте. Основные параметры:

| Переменная окружения | По умолчанию | Описание |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | Адрес прослушивания |
| `CURSOR_DIRECT_PORT` | `8790` | Порт прослушивания |
| `CURSOR_DIRECT_API_KEY` | Пусто | Ключ, с которым клиенты обращаются к шлюзу |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | Путь к файлу аккаунтов |
| `CURSOR_DIRECT_PROXY_URL` | Пусто | URL прокси SOCKS5 |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | Тайм-аут связи с Agent на один ход, включая подключение и согласование соединения, в миллисекундах |
| `CURSOR_DIRECT_MODEL_PREFIX` | Пусто | Префикс имён моделей для клиентов; исходный префикс `cursor-` по умолчанию удаляется |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | Записывать сводки, идентификаторы и длительность запросов; ошибки записываются и при отключении |

<details>
<summary>🔧 Все расширенные настройки</summary>

| Переменная окружения | По умолчанию | Описание |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | HTTP(S)-адрес вышестоящего сервиса |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | Заголовок версии клиента для вышестоящего сервиса |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | Разрешённые нативные инструменты сервиса; `*` отключает передачу заголовка ограничения |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | Преобразовывать инструкции system / developer в исторические ходы конфигурации |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | Сохранять недавние сводки рассуждений при повторной передаче всей истории |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | Общий лимит символов повторно передаваемых сводок, с приоритетом новых записей |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | Число попыток исправления формата ввода инструмента в одном Run, от 0 до 3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | Продолжать ожидающий нативный Run с результатами инструментов |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | Максимальное ожидание результатов инструментов клиента в секундах |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | Максимальное число сохраняемых нативных Run |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | Инструкция продолжения при повторной передаче всей истории |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | Лимит размера запроса / ответа; потоки Responses также ограничивают накопленный вывод |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | Время хранения истории ответов в секундах |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | Максимальное число сохранённых ответов |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | Максимальный размер сериализованной истории ответов в байтах |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | `compaction.key` рядом с файлом аккаунтов | Ключ контрольных точек сжатия; обеспечьте постоянное хранение файла |

Обнаружение моделей и обновление токенов имеют отдельные сетевые тайм-ауты, поэтому первый запрос может занять больше времени.

Сгенерированные классы protobuf включены в проект. Для запуска шлюза не нужен `protoc`; переменная `CURSOR_DIRECT_PROTO_DIR` исходного Node-проекта не используется.

</details>

<a id="proxy"></a>

## 🌐 Поддержка прокси

Задайте прокси в `.env`:

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# For username / password authentication, use this format
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

И `socks5://`, и `socks5h://` разрешают имена конечных хостов через прокси. Специальные символы имени пользователя и пароля кодируйте для URL. Прокси охватывает обнаружение моделей, генерацию, обновление токенов и опрос статуса входа. URL HTTP-прокси пока не поддерживаются.

<a id="faq"></a>

## 🔧 Решение проблем

<details>
<summary>Проверка состояния проходит. Почему запросы возвращают 503?</summary>

`/health` проверяет, работает ли процесс. `{"ok": true, "accounts": 0, ...}` означает, что процесс запущен, но доступных аккаунтов нет. Возможно, вход ещё не выполнен или все аккаунты временно приостановлены.

Выполните `login` / `import-local` и проверьте путь аккаунтов, фактически используемый сервисом. Локальный путь по умолчанию — `./accounts.json`; Docker Compose использует `./data/accounts.json`. Если ошибка пришла от вышестоящего сервиса, изучите её детали для проверки доступности сервиса.

</details>

<details>
<summary>Почему возникает 400? Как отправлять изображения и инструменты?</summary>

Проверьте JSON `error` у клиента и журналы с тем же `X-Request-ID`. Типичные причины:

- `tool_choice="required"`, принудительный выбор инструмента или другие неподдерживаемые параметры.
- Удалённые URL изображений, идентификаторы файлов или аудиоввод. Изображения должны иметь поддерживаемый формат и передаваться в data URL с base64.
- Нереализованные серверные инструменты, например `file_search`, или неподдерживаемые поля `include`.
- Некорректный JSON, неверный формат ввода пользовательского инструмента или некорректная настройка JSON Schema.

Responses поддерживает изображения и проверку вывода по JSON Schema через `text.format`. Форматы описаны в [справочнике API (на английском)](../en/api-reference.md). Если в журнале указан `stage="upstream"`, изучите сообщение вышестоящего сервиса и выбранную модель.

</details>

<details>
<summary>Как исследовать конкретный неудачный запрос?</summary>

Диагностика запросов доступна при стандартном уровне журналирования `info`. Для Docker:

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# Replace the placeholder with the X-Request-ID response header value
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F 'REPLACE_WITH_REQUEST_ID'
```

Сообщения журнала — однострочный JSON. События одного запроса имеют одинаковый `request_id`:

| Событие | Что проверить |
| --- | --- |
| `request_started` / `request_parsed` | Путь, клиент и сводка параметров запроса |
| `generation_started` | Метка аккаунта, фактическая модель сервиса, число элементов истории и инструментов |
| `compatibility_notice` | Информация о сопоставлении совместимости; само событие не означает сбой |
| `request_error` | `stage`, `error_status`, `error_param`, `error_message` и `error_code` вышестоящего сервиса |
| `request_finished` | Статус HTTP, `outcome`, длительность и число байтов |

Ошибки после начала SSE могут сопровождаться статусом HTTP 200. Проверяйте также ошибки потока и `outcome` в журнале. Типичные соответствия ошибок вышестоящего сервиса:

| Ошибка сервиса | Статус HTTP |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| Прочие ошибки протокола или вышестоящего сервиса | `502` |

Сводки журналов не содержат промптов, тел сообщений, аргументов / результатов инструментов, значений метаданных, cookies и заголовков аутентификации. Известные учётные данные в тексте ошибок скрываются. Отключение `CURSOR_DIRECT_LOG_REQUESTS` выключает только обычные журналы запросов.

</details>

<details>
<summary>Почему previous_response_id перестаёт работать после перезапуска?</summary>

История ответов хранится в памяти процесса; стандартные ограничения — один час, 256 записей и 128 MiB. Перезапуск очищает её, а разные процессы и экземпляры не разделяют эту память. При отсутствии записи в кеше возвращается `404`.

Для управления историей на стороне клиента используйте `store=false` и передавайте полный ввод, предыдущий вывод и результаты инструментов. Контрольные точки сжатия зависят от `compaction.key`; сохранение того же ключа позволяет декодировать их после перезапуска. Контрольные точки и хранение ответов по ID — разные механизмы.

При использовании `previous_response_id` заново передавайте необходимые `instructions` и определения инструментов на каждом ходу.

</details>

<a id="compatibility"></a>

## 📋 Совместимость

| Возможность | Реализация и ограничения |
| --- | --- |
| Протоколы API | Chat Completions, Responses и Models; нет Anthropic `/v1/messages`, Embeddings и интерфейса управления |
| Изображения | Оба API генерации принимают встроенные PNG / JPEG / WebP / GIF: до 16 MiB на изображение и 32 изображений в запросе в пределах общего лимита тела; удалённые URL, идентификаторы файлов и аудио не поддерживаются |
| Инструменты | Клиенты выполняют инструменты-функции / пользовательские инструменты. `tool_choice` принимает `auto` / `none`. `parallel_tool_calls` собирает вызовы, поступившие одним пакетом; появление параллельных вызовов зависит от вышестоящей модели |
| Структурированный вывод | Responses инструктирует модель и проверяет итоговый ответ, без нативного декодирования с ограничениями. `response_format` в Chat Completions не влияет на результат |
| Управление семплированием и рассуждениями | Параметры вроде `temperature`, `top_p` и лимитов токенов не полностью соблюдаются вышестоящим сервисом. Chat Completions поддерживает только `n=1` |
| Состояние рассуждений | Доступны видимые сводки рассуждений; OpenAI `reasoning.encrypted_content` не создаётся и не расшифровывается |
| Учёт токенов | Chat Completions сообщает ноль токенов промпта. Входные токены Responses оцениваются и помечаются `estimated=true`. Счётчики сервиса сопоставляются с выходными токенами; отдельная детализация оплаты кеша / рассуждений недоступна |
| Веб-поиск | Responses использует встроенный поиск Cursor без параметров OpenAI для местоположения и фильтрации доменов |
| Транспорт и серверные функции | HTTP/SSE; нет Responses WebSocket, `background=true`, серверных `conversation` / `prompt` и других встроенных серверных инструментов. Отключение клиента отменяет запрос к вышестоящему сервису |

Инструкции system / developer по умолчанию передаются как сообщения истории с метками источника; их действие зависит от инструкций вышестоящего сервиса. Даже при `CURSOR_ALLOWED_NATIVE_TOOLS=*` шлюз не выполняет команды оболочки, файловые операции или патчи клиента на своём хосте.

Поведение параметров описано в [справочнике API (на английском)](../en/api-reference.md), настройка клиента — в [руководстве Codex CLI (на английском)](../en/codex-usage.md).

<a id="development"></a>

## 🧪 Разработка и проверка

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

Автоматические тесты используют вымышленные учётные данные и локальную имитацию вышестоящего сервиса. Они проверяют обновление аккаунтов, валидацию запросов, JSON / SSE, циклы инструментов, историю Responses, отмену и транспорт HTTP/2 / protobuf через локальные TCP-соединения. Реальные учётные данные, платная генерация и Codex CLI не нужны.

<details>
<summary>🛠️ Генерация кода протокола</summary>

После изменения определений протокола заново сгенерируйте классы Python с помощью `protoc 36.1`:

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 Структура проекта</summary>

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

## 🤝 Участие в разработке

Используйте Issues для воспроизводимых ошибок и обсуждения возможностей. Перед отправкой pull request прочтите [руководство для участников (на китайском / английском)](../../CONTRIBUTING.md).
При изменении поведения, настроек или примеров синхронизируйте README на восьми языках и руководства на китайском и английском; соблюдайте [кодекс поведения (на китайском / английском)](../../CODE_OF_CONDUCT.md).
Сообщайте об уязвимостях приватно согласно [политике безопасности (на китайском / английском)](../../SECURITY.md). Изменения версий перечислены в [журнале изменений (на английском)](../../CHANGELOG.md).

<a id="credits"></a>

## 🙏 Благодарности и лицензия

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api): исходная реализация, с которой портирован проект, включая сопоставления протокола, формат аккаунтов и резервный каталог моделей.
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi): источник провайдера Cursor / `agent.proto`, указанный в исходном проекте.
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway): образец оформления README и структуры документации.

Проект распространяется по лицензии **[AGPL-3.0-only](../../LICENSE)**. Полный список источников и авторства приведён в [NOTICE](../../NOTICE).

При распространении или эксплуатации изменённой версии для других пользователей соблюдайте требования AGPL о предоставлении соответствующего исходного кода. Предоставляйте полный код работающей версии через репозиторий или архив исходников и понятную точку доступа к нему для сетевых пользователей. При сборке контейнера публичный адрес исходников можно записать через `--build-arg SOURCE_URL=PUBLIC_SOURCE_URL`.
