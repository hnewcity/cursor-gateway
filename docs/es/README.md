<div align="center">

# ⚡ Cursor Gateway

**Conecta tu cuenta de Cursor a una API compatible con OpenAI**

[English](../en/README.md) · [Русский](../ru/README.md) · [简体中文](../../README.md) · **Español** · [Bahasa Indonesia](../id/README.md) · [Português (Brasil)](../pt-BR/README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md)

Usa tus clientes habituales con los modelos disponibles en tu cuenta de Cursor. Compatible con Chat Completions, la API Responses y Codex CLI.

[![CI](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](../../LICENSE)

[Funciones](#features) · [Inicio rápido](#quick-start) · [Cuentas](#accounts) · [Docker](#docker) · [Configuración de clientes](#clients) · [Solución de problemas](#faq) · [Patrocinador](#sponsors)

</div>

---

<a id="sponsors"></a>

## ❤️ Patrocinador

<table>
<tr>
<td width="180" align="center"><a href="https://ai18n.chat"><img src="../assets/sponsors/ai18n.png" alt="ai18n" width="150"></a></td>
<td>¡Gracias a <a href="https://ai18n.chat"><strong>ai18n</strong></a> por patrocinar este proyecto! ai18n ofrece servicios de intermediación de API de IA para herramientas como OpenClaw, Claude Code, Codex y Gemini.</td>
</tr>
</table>

---

Cursor Gateway es una adaptación a Python de [cursor2api](https://github.com/AstroQore/cursor2api). Atiende solicitudes HTTP con FastAPI y se conecta directamente al backend Agent de Cursor mediante HTTP/2 y protobuf. Para ejecutar la pasarela no se necesita Node.js, Cursor CLI ni automatización del navegador.

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
> Este cliente no es oficial, no está afiliado a Anysphere ni cuenta con su respaldo. Usa tu propia cuenta de Cursor. La disponibilidad de modelos y las cuotas dependen de tu cuenta y del servicio de origen.

<a id="features"></a>

## ✨ Funciones

| Función | Descripción |
| --- | --- |
| 🔌 **API compatibles con OpenAI** | `/v1/models`, `/v1/chat/completions` y `/v1/responses` |
| 💻 **Integración con Codex CLI** | Incluye un lanzador para flujos con parches de archivos, terminales / PTY, MCP, varios agentes, recuperación de sesiones y revisión de código |
| 📡 **Transmisión en tiempo real** | Respuestas JSON y SSE, resúmenes de razonamiento y eventos de llamadas a herramientas |
| 🛠️ **Llamadas a herramientas** | Herramientas de función y resultados en varios turnos; Responses también admite herramientas personalizadas, espacios de nombres y descubrimiento de herramientas del lado del cliente |
| 🧠 **Continuidad de tareas** | Los resultados de herramientas de Responses pueden reanudar el mismo Cursor Run, incluso con `store=false` |
| 👁️ **Entrada de imágenes** | Imágenes PNG, JPEG, WebP y GIF incrustadas en base64, si el modelo las admite |
| 🔍 **Búsqueda web** | Traduce `web_search` / `web_search_preview` de Responses a la búsqueda nativa de Cursor |
| 📐 **Salida estructurada** | Responses admite instrucciones al modelo y validación de la salida final para `json_object` / `json_schema` |
| 💬 **Historial y compactación** | `previous_response_id`, recuperación / eliminación de respuestas, paginación de entradas y puntos de control de compactación cifrados |
| 🔀 **Varias cuentas** | Selección por turnos, recarga de archivos sin reiniciar, renovación automática de tokens y pausas tras errores de autenticación o de cuota |
| 🤖 **Descubrimiento dinámico de modelos** | Listas y cachés por cuenta, con compatibilidad con los nombres antiguos que empiezan por `cursor-` |
| 🌐 **Proxy SOCKS5** | Cubre el sondeo de inicio de sesión, el descubrimiento de modelos, la generación y la renovación de tokens; admite autenticación con usuario / contraseña |
| 🐳 **Despliegue y diagnóstico** | Docker Compose, un ejemplo de systemd, documentación interactiva de la API y registros con identificadores de solicitud |

Consulta los límites en [Compatibilidad](#compatibility). El cliente que realiza la llamada gestiona la ejecución de herramientas y los permisos.

<a id="models"></a>

## 🤖 Modelos disponibles

La pasarela obtiene el catálogo de modelos de la cuenta seleccionada para la solicitud. Después de iniciar sesión y arrancar el servicio:

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

Usa uno de los valores `data[].id` devueltos como modelo en tu cliente. Los ejemplos de este documento usan `auto`; si tu cuenta no lo admite, elige un modelo disponible de la lista.

- Por defecto, los nombres omiten el prefijo `cursor-` del servicio de origen. Por ejemplo, `grok-4.6-medium` se asigna al identificador real de origen.
- Los nombres antiguos con `cursor-` siguen funcionando. Define `CURSOR_DIRECT_MODEL_PREFIX` para personalizar los nombres que ven los clientes.
- Los catálogos se almacenan en caché durante 10 minutos. Si falla el descubrimiento, la pasarela usa una caché anterior o el catálogo de respaldo y vuelve a intentarlo tras 30 segundos.

> [!NOTE]
> El catálogo de respaldo se usa cuando falla el descubrimiento; no garantiza acceso a todos los modelos incluidos. Con varias cuentas, cada consulta devuelve el catálogo de la cuenta seleccionada para esa solicitud.

<a id="quick-start"></a>

## 🚀 Inicio rápido

Elige **Python nativo** para desarrollo y depuración, o **[Docker Compose](#docker)** para desplegar en contenedores.

### Requisitos previos

- **Python 3.14+**. El desarrollo, las pruebas y la imagen Docker usan Python 3.14.
- Una cuenta de Cursor que pueda iniciar sesión y tenga cuota disponible.
- Acceso de red a los servicios de Cursor, directamente o mediante un [proxy SOCKS5](#proxy).

### 1. Obtener el proyecto e instalarlo

Clona el repositorio con la URL de esta página, o elige **Code → Download ZIP** y extrae el archivo.

```bash
git clone https://github.com/hnewcity/cursor-gateway.git
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Salvo que se indique lo contrario, ejecuta todos los comandos siguientes desde la raíz del repositorio.

<details>
<summary>🪟 Instalación con Windows PowerShell</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

En Windows, sustituye `.venv/bin/python` y `.venv/bin/cursor-gateway` en los ejemplos siguientes por `.venv\Scripts\python.exe` y `.venv\Scripts\cursor-gateway.exe`.

</details>

### 2. Iniciar sesión en Cursor

```bash
.venv/bin/cursor-gateway login
```

Abre la URL que aparece en el terminal y autoriza el inicio de sesión en el navegador. También puedes [importar una sesión local](#accounts) o usar un archivo de cuentas existente. Por defecto, las credenciales se guardan en `accounts.json`, en la raíz del repositorio.

### 3. Iniciar el servicio

```bash
.venv/bin/cursor-gateway serve
```

La dirección predeterminada es `http://127.0.0.1:8790`. El servicio lee `.env` del directorio actual; las variables de entorno existentes tienen prioridad.

```bash
# Set the listen address and port
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# Alternatively, start through the Python module
.venv/bin/python -m cursor_gateway serve
```

### 4. Enviar la primera solicitud

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello! Please introduce yourself."}]}'
```

> [!TIP]
> Para proteger la API de la pasarela, define `CURSOR_DIRECT_API_KEY=sk-your-secret` en `.env` y configura los clientes con la misma clave. Esta clave de la pasarela es independiente del token de tu cuenta de Cursor.
> Los ejemplos leen la clave del entorno del terminal. Si solo la has definido en el `.env` del servidor, ejecuta `export CURSOR_DIRECT_API_KEY="sk-your-secret"` en el terminal que uses para el cliente.

<a id="accounts"></a>

## 🔐 Configuración de cuentas

Elige el método que se ajuste a tu entorno. Si ya tienes un archivo de cuentas, pasa a la opción 3.

### Opción 1: Iniciar sesión en el navegador

Funciona tanto en local como en un servidor remoto. El servidor muestra una URL que puedes abrir en tu propio equipo.

```bash
.venv/bin/cursor-gateway login
```

Para especificar un proxy para el sondeo de inicio de sesión:

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### Opción 2: Importar una sesión local

Si has iniciado sesión en la **aplicación de escritorio de Cursor** en el mismo equipo, importa las credenciales desde su base de datos SQLite:

```bash
.venv/bin/cursor-gateway import-local

# Use a custom data directory
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 Exportar una cuenta de Cursor CLI / escritorio para desplegar en un servidor</summary>

El [script de exportación de credenciales](../../scripts/export_cursor_credentials.py) independiente solo utiliza la biblioteca estándar de Python. No requiere instalar la pasarela, no hace solicitudes de red ni envía credenciales automáticamente a ningún destino.

```bash
# Run from the repository root to create a server-ready account file
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# Use only the Cursor CLI login
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

También puedes copiar únicamente el script a un equipo donde hayas iniciado sesión en Cursor:

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

Por defecto, el script crea `accounts.json` junto a sí mismo y se niega a sobrescribir un archivo existente. Admite `--source cli` / `--source desktop`, `--out` y `--db` para una base de datos de escritorio. macOS puede solicitar acceso al Llavero.

Coloca el archivo exportado en `data/accounts.json` del servidor para usarlo con la configuración de Docker Compose de este repositorio.

</details>

### Opción 3: Usar un archivo de cuentas existente

La pasarela acepta el formato de cuentas de `cursor2api`. Define la ruta en `.env`:

```dotenv
CURSOR_DIRECT_AUTH_FILE=/absolute/path/to/accounts.json
```

<details>
<summary>📄 Formato de accounts.json</summary>

```json
[
  {
    "label": "main",
    "accessToken": "your-access-token",
    "refreshToken": "your-refresh-token"
  }
]
```

También se acepta el formato `{"accounts": [...]}`. `refreshToken` es opcional, pero necesario para la renovación automática. Los campos opcionales `expiresAt` y `disabledUntil` admiten marcas de tiempo ISO.

El inicio de sesión, la importación y la renovación realizan escrituras atómicas con permisos de archivo `0600`. Al usar un archivo existente, la renovación automática escribe los tokens actualizados en ese mismo archivo.

</details>

> [!IMPORTANT]
> `accounts.json` contiene credenciales que dan acceso a tu cuenta. Mantenlo privado. Los archivos de cuentas, `.env` y las claves de compactación están incluidos en `.gitignore`.

<a id="multi-account"></a>

## 🔀 Varias cuentas

Añade cuentas con `--merge`:

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| Comportamiento | Descripción |
| --- | --- |
| Combinación | `--merge` sustituye la cuenta con la misma etiqueta y conserva las demás. **Si se omite, se reemplaza todo el archivo de salida.** |
| Enrutamiento de solicitudes | Las solicitudes nuevas alternan entre las cuentas disponibles; un Run nativo reanudado conserva su cuenta original |
| Recarga sin reinicio | Los cambios del archivo de cuentas se aplican a las solicitudes posteriores sin reiniciar |
| Renovación de tokens | Intenta renovar en los 30 minutos anteriores a la caducidad; las renovaciones simultáneas se agrupan dentro de un proceso |
| Pausa temporal | La cuota agotada y los errores de autenticación o permisos provocan una pausa de 60 segundos; las solicitudes posteriores usan otras cuentas disponibles |

Los errores del servicio de origen se devuelven a la solicitud actual, sin repetir automáticamente una generación que ya haya comenzado. Usa un único proceso de la pasarela para escribir en cada archivo de cuentas.

<a id="docker"></a>

## 🐳 Despliegue con Docker

El repositorio incluye un `Dockerfile` y `docker-compose.yml`. Ejecuta desde la raíz del repositorio:

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

El contenedor escucha en `0.0.0.0:8790`, mientras que en el host se publica por defecto en `127.0.0.1:8790`. Compose monta `./data` en `/data`. Las cuentas se guardan en `/data/accounts.json` y, por defecto, la clave de compactación se guarda en ese mismo directorio.

<details>
<summary>🔧 Comandos habituales de administración</summary>

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

`CURSOR_DIRECT_PORT` controla el puerto publicado en el host; el del contenedor sigue siendo `8790`. Compose fija la ruta de cuentas en `/data/accounts.json` y no utiliza `CURSOR_DIRECT_AUTH_FILE` de `.env`.

Dentro de un contenedor, `127.0.0.1` se refiere a ese contenedor. Para usar un proxy del host, especifica una dirección accesible desde el contenedor. Con Docker Desktop puedes usar `host.docker.internal` si la configuración de red lo permite.

</details>

<details>
<summary>🐧 Despliegue con systemd</summary>

Consulta el ejemplo en [deploy/cursor-gateway.service](../../deploy/cursor-gateway.service).

Instala el proyecto y su entorno virtual en `/opt/cursor-gateway`, crea un usuario de servicio `cursor-gateway` y permite que lea el proyecto y la configuración y escriba en `data`. Una vez preparado:

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

El ejemplo usa `/opt/cursor-gateway/data/accounts.json` y lee `.env` de la raíz del proyecto.

</details>

<a id="clients"></a>

## 💡 Configuración de clientes

### Clientes compatibles con OpenAI

| Ajuste | Valor |
| --- | --- |
| URL base | `http://127.0.0.1:8790/v1` |
| Clave de API | El valor de `CURSOR_DIRECT_API_KEY`; cualquier cadena no vacía si no se ha configurado una clave |
| Modelo | Un modelo devuelto por `/v1/models`, como `auto` si está disponible para tu cuenta |
| Protocolo de API | Chat Completions o Responses, según el cliente |

Para clientes en otro equipo, sustituye `127.0.0.1` por una dirección accesible de la pasarela y ajusta la dirección de escucha o el mapeo de puertos.

### Codex CLI

Instala Codex CLI, inicia la pasarela y ejecuta el lanzador incluido:

```bash
# Interactive use
.venv/bin/python scripts/run_codex.py --model auto

# Run a coding task
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write 'Create hello.py, run it, and check the output'
```

El lanzador usa Responses mediante HTTP/SSE y un catálogo de modelos temporal. Conserva tu configuración habitual sin editar `~/.codex/config.toml`. Exporta la clave de la pasarela en el terminal actual. Codex controla la ejecución de herramientas, las aprobaciones de MCP y el entorno aislado.

El presupuesto de contexto del cliente es de 65.536 tokens por defecto; ajústalo con `--context-window`. Usa `--text-only` para modelos sin visión o `--url` para otra dirección de la pasarela.

Consulta la [guía de Codex CLI (en inglés)](../en/codex-usage.md) para recuperar sesiones, continuar Runs nativos y compactar el contexto.

### Ejemplos de solicitudes

<details>
<summary>📡 Chat Completions en streaming</summary>

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

Los fragmentos de texto aparecen en `choices[].delta.content`; los de razonamiento usan `reasoning_content`. Con `include_usage`, se envía un fragmento adicional de uso con `choices: []` antes del `[DONE]` final.

</details>

<details>
<summary>💬 Solicitud a la API Responses</summary>

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

El texto visible aparece en elementos `output_text` dentro de `output[].content[]`. Define `stream: true` para recibir eventos SSE tipados `response.*`, o `store: false` para omitir el almacenamiento del historial de respuestas.

</details>

<details>
<summary>🐍 SDK de OpenAI para Python</summary>

Instala la dependencia del cliente:

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

Consulta la [referencia de la API (en inglés)](../en/api-reference.md) para herramientas de función, streaming de Responses, continuación del historial y notas detalladas de compatibilidad.

</details>

<a id="api"></a>

## 📡 Endpoints de la API

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` / `HEAD` | `/`, `/health` | Estado del proceso y número de cuentas disponibles; no requiere autenticación |
| `GET` / `HEAD` | `/v1/models` | Catálogo de modelos de la cuenta seleccionada |
| `POST` | `/v1/chat/completions` | Chat Completions, JSON / SSE |
| `POST` | `/v1/responses` | Responses, JSON / SSE |
| `POST` | `/v1/responses/compact` | Generar un punto de control de compactación cifrado |
| `GET` | `/v1/responses/{response_id}` | Recuperar una respuesta guardada |
| `DELETE` | `/v1/responses/{response_id}` | Eliminar una respuesta y la instantánea de su entrada |
| `GET` | `/v1/responses/{response_id}/input_items` | Recuperar el historial de entrada con paginación |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc y la descripción OpenAPI; no requiere autenticación |

Si se define `CURSOR_DIRECT_API_KEY`, todos los endpoints `/v1/*` aceptan autenticación con `Authorization: Bearer <key>` o `x-api-key`. Usa **Authorize** en Swagger UI para introducir la clave.

<a id="configuration"></a>

## ⚙️ Configuración

Copia [.env.example](../../.env.example) a `.env` y edítalo. Ajustes habituales:

| Variable de entorno | Valor predeterminado | Descripción |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | Dirección de escucha |
| `CURSOR_DIRECT_PORT` | `8790` | Puerto de escucha |
| `CURSOR_DIRECT_API_KEY` | Vacío | Clave que usan los clientes para llamar a la pasarela |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | Ruta del archivo de cuentas |
| `CURSOR_DIRECT_PROXY_URL` | Vacío | URL del proxy SOCKS5 |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | Tiempo límite de comunicación con Agent por turno, incluida la conexión y la negociación, en milisegundos |
| `CURSOR_DIRECT_MODEL_PREFIX` | Vacío | Prefijo de los nombres de modelos expuestos; por defecto se elimina el prefijo `cursor-` de origen |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | Registrar resúmenes, identificadores y duración de solicitudes; los errores se siguen registrando aunque se desactive |

<details>
<summary>🔧 Todos los ajustes avanzados</summary>

| Variable de entorno | Valor predeterminado | Descripción |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | Origen HTTP(S) del servicio de Cursor |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | Cabecera de versión del cliente enviada al servicio de origen |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | Herramientas nativas de origen permitidas; `*` omite la cabecera de restricción |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | Convertir instrucciones de sistema / desarrollador en turnos históricos de configuración |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | Conservar resúmenes de razonamiento recientes al reenviar el historial completo |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | Límite total de caracteres para los resúmenes reenviados, priorizando los más recientes |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | Intentos de corregir el formato de entrada de herramientas dentro de un Run, entre 0 y 3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | Reanudar un Run nativo pendiente con resultados de herramientas |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | Espera máxima de resultados de herramientas del cliente, en segundos |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | Número máximo de Runs nativos conservados |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | Instrucción de continuación usada al reenviar el historial completo |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | Límite de tamaño de solicitudes / respuestas; los streams de Responses también limitan la salida acumulada |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | Duración del historial de respuestas, en segundos |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | Número máximo de respuestas guardadas |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | Tamaño máximo del historial de respuestas serializado, en bytes |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | `compaction.key` junto al archivo de cuentas | Clave de los puntos de control de compactación; conserva este archivo de forma persistente |

El descubrimiento de modelos y la renovación de tokens tienen tiempos límite de red independientes, por lo que la primera solicitud puede tardar más.

Las clases protobuf generadas vienen incluidas en el proyecto. No hace falta `protoc` para iniciar la pasarela, y no se utiliza `CURSOR_DIRECT_PROTO_DIR` del proyecto Node original.

</details>

<a id="proxy"></a>

## 🌐 Compatibilidad con proxies

Configura el proxy en `.env`:

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# For username / password authentication, use this format
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

Tanto `socks5://` como `socks5h://` resuelven los nombres de host de destino a través del proxy. Codifica para URL los caracteres especiales de usuario y contraseña. El proxy cubre el descubrimiento de modelos, la generación, la renovación de tokens y el sondeo de inicio de sesión. Actualmente no se admiten URL de proxy HTTP.

<a id="faq"></a>

## 🔧 Solución de problemas

<details>
<summary>La comprobación de salud funciona. ¿Por qué las solicitudes devuelven 503?</summary>

`/health` comprueba que el proceso está activo. `{"ok": true, "accounts": 0, ...}` significa que está en ejecución, pero no hay ninguna cuenta disponible. Puede que no hayas iniciado sesión o que todas las cuentas estén en pausa temporal.

Ejecuta `login` / `import-local` y comprueba la ruta de cuentas que utiliza realmente el servicio. En local, el valor predeterminado es `./accounts.json`; Docker Compose usa `./data/accounts.json`. Si el error procede del servicio de origen, utiliza sus detalles para investigar su disponibilidad.

</details>

<details>
<summary>¿Por qué recibo 400? ¿Cómo envío imágenes y herramientas?</summary>

Revisa el JSON `error` del cliente y los registros con el mismo `X-Request-ID`. Las causas habituales son:

- `tool_choice="required"`, una herramienta forzada u otros parámetros no compatibles.
- URL de imágenes remotas, identificadores de archivo o entrada de audio. Las imágenes deben usar un formato compatible en una URL de datos base64.
- Herramientas alojadas no implementadas, como `file_search`, o campos `include` no compatibles.
- JSON no válido, entrada mal formada de herramientas personalizadas o una configuración de JSON Schema no válida.

Responses admite imágenes y validación de salida con JSON Schema mediante `text.format`. Consulta los formatos en la [referencia de la API (en inglés)](../en/api-reference.md). Si los registros muestran `stage="upstream"`, investiga el mensaje de error del servicio de origen y el modelo seleccionado.

</details>

<details>
<summary>¿Cómo investigo una solicitud fallida concreta?</summary>

Los diagnósticos de solicitudes están disponibles con el nivel de registro predeterminado `info`. Para despliegues Docker:

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# Replace the placeholder with the X-Request-ID response header value
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F 'REPLACE_WITH_REQUEST_ID'
```

Los mensajes de registro son JSON de una sola línea. Los eventos de una solicitud comparten el mismo `request_id`:

| Evento | Qué revisar |
| --- | --- |
| `request_started` / `request_parsed` | Ruta, cliente y resumen de parámetros |
| `generation_started` | Etiqueta de cuenta, modelo real de origen, número de elementos del historial y de herramientas |
| `compatibility_notice` | Información sobre las correspondencias de compatibilidad; este evento por sí solo no indica un fallo |
| `request_error` | `stage`, `error_status`, `error_param`, `error_message` y `error_code` del servicio de origen |
| `request_finished` | Estado HTTP, `outcome`, duración y número de bytes |

Los errores posteriores al inicio de SSE pueden seguir teniendo estado HTTP 200. Revisa también los errores del stream y el `outcome` registrado. Correspondencias habituales de errores de origen:

| Error de origen | Estado HTTP |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| Otros errores de protocolo o del servicio de origen | `502` |

Los resúmenes de registro excluyen prompts, cuerpos de mensajes, argumentos / resultados de herramientas, valores de metadatos, cookies y cabeceras de autenticación. Las credenciales conocidas se ocultan en el texto de los errores. Desactivar `CURSOR_DIRECT_LOG_REQUESTS` solo desactiva los registros rutinarios de solicitudes.

</details>

<details>
<summary>¿Por qué previous_response_id deja de funcionar después de reiniciar?</summary>

El historial de respuestas se almacena en la memoria del proceso, con límites predeterminados de una hora, 256 entradas y 128 MiB. Un reinicio lo borra y no se comparte entre procesos o instancias. Si no se encuentra en caché, se devuelve `404`.

Para gestionar el historial desde el cliente, usa `store=false` y envía la entrada completa, la salida anterior y los resultados de herramientas. Los puntos de control de compactación dependen de `compaction.key`; conservar la misma clave permite decodificarlos tras un reinicio. Los puntos de control y el almacenamiento por identificador de respuesta son mecanismos independientes.

Al usar `previous_response_id`, vuelve a proporcionar las `instructions` necesarias y las definiciones de herramientas en cada turno.

</details>

<a id="compatibility"></a>

## 📋 Compatibilidad

| Capacidad | Implementación y límites |
| --- | --- |
| Protocolos de API | Chat Completions, Responses y Models; sin `/v1/messages` de Anthropic, Embeddings ni interfaz de administración |
| Imágenes | Ambas API de generación aceptan imágenes PNG / JPEG / WebP / GIF incrustadas, de hasta 16 MiB cada una y 32 imágenes por solicitud, dentro del límite total del cuerpo; no se admiten URL remotas, identificadores de archivo ni audio |
| Herramientas | El cliente ejecuta las herramientas de función / personalizadas. `tool_choice` acepta `auto` / `none`. Activar `parallel_tool_calls` agrupa las llamadas que llegan en el mismo lote; que se generen llamadas paralelas depende del modelo de origen |
| Salida estructurada | Responses da instrucciones al modelo y valida la respuesta final, sin decodificación restringida nativa. `response_format` de Chat Completions no tiene efecto |
| Controles de muestreo y razonamiento | Parámetros como `temperature`, `top_p` y los límites de tokens no se aplican de forma completa en el servicio de origen. Chat Completions solo admite `n=1` |
| Estado de razonamiento | Expone resúmenes de razonamiento visibles; no genera ni descifra `reasoning.encrypted_content` de OpenAI |
| Contabilización de tokens | Chat Completions informa de cero tokens de entrada. Los tokens de entrada de Responses son estimaciones marcadas con `estimated=true`. Los recuentos de origen se asignan a tokens de salida; no hay detalles separados de facturación de caché / razonamiento |
| Búsqueda web | Responses utiliza la búsqueda nativa de Cursor, sin las opciones de ubicación o filtrado de dominios de OpenAI |
| Transporte y funciones alojadas | HTTP/SSE; sin WebSocket de Responses, `background=true`, `conversation` / `prompt` alojados ni otras herramientas integradas alojadas. La desconexión del cliente cancela la solicitud al servicio de origen |

Por defecto, las instrucciones de sistema / desarrollador se envían como mensajes históricos con etiquetas de origen; su efecto sigue dependiendo de las instrucciones del servicio de origen. Incluso con `CURSOR_ALLOWED_NATIVE_TOOLS=*`, la pasarela no ejecuta comandos de shell, operaciones de archivos ni parches del cliente en su host.

Consulta la [referencia de la API (en inglés)](../en/api-reference.md) para el comportamiento detallado de los parámetros y la [guía de Codex CLI (en inglés)](../en/codex-usage.md) para configurar el cliente.

<a id="development"></a>

## 🧪 Desarrollo y verificación

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

Las pruebas automatizadas utilizan credenciales ficticias y un servicio de origen simulado local. Cubren la renovación de cuentas, la validación de solicitudes, JSON / SSE, ciclos de herramientas, historial de Responses, cancelación y transporte HTTP/2 / protobuf mediante conexiones TCP locales. No requieren credenciales reales, inferencia de pago ni Codex CLI.

<details>
<summary>🛠️ Generación de código del protocolo</summary>

Después de cambiar las definiciones del protocolo, regenera las clases Python con `protoc 36.1`:

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 Estructura del proyecto</summary>

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

## 🤝 Contribuir

Usa Issues para informar de errores reproducibles y debatir funciones, y lee la [guía de contribución (chino / inglés)](../../CONTRIBUTING.md) antes de enviar un pull request.
Mantén sincronizados los README de los ocho idiomas y las guías en chino e inglés al cambiar el comportamiento, la configuración o los ejemplos, y sigue el [código de conducta (chino / inglés)](../../CODE_OF_CONDUCT.md).
Informa de vulnerabilidades de forma privada según la [política de seguridad (chino / inglés)](../../SECURITY.md). Consulta los cambios de versión en el [registro de cambios (en inglés)](../../CHANGELOG.md).

<a id="credits"></a>

## 🙏 Créditos y licencia

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api): implementación original de la que se adaptó este proyecto, incluidas las correspondencias del protocolo, el formato de cuentas y el catálogo de modelos de respaldo.
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi): origen del proveedor de Cursor / `agent.proto` reconocido por el proyecto original.
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway): referencia para el diseño de este README y la estructura de la documentación.

Este proyecto se distribuye bajo la licencia **[AGPL-3.0-only](../../LICENSE)**. Consulta la atribución completa en [NOTICE](../../NOTICE).

Al distribuir o ejecutar una versión modificada para otras personas, cumple los requisitos de AGPL relativos a la entrega del código fuente correspondiente. Ofrece el código fuente completo de la versión en ejecución a través del repositorio o de una distribución de fuentes, y proporciona a los usuarios de red un acceso claro al código. Las compilaciones de contenedores pueden registrar la ubicación pública del código con `--build-arg SOURCE_URL=PUBLIC_SOURCE_URL`.
