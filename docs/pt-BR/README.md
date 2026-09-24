<div align="center">

# ⚡ Cursor Gateway

**Conecte sua conta do Cursor a uma API compatível com OpenAI**

[English](../en/README.md) · [Русский](../ru/README.md) · [简体中文](../../README.md) · [Español](../es/README.md) · [Bahasa Indonesia](../id/README.md) · **Português (Brasil)** · [日本語](../ja/README.md) · [한국어](../ko/README.md)

Use seus clientes habituais com os modelos disponíveis na sua conta do Cursor. Compatível com Chat Completions, a API Responses e Codex CLI.

[![CI](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](../../LICENSE)

[Recursos](#features) · [Início rápido](#quick-start) · [Contas](#accounts) · [Docker](#docker) · [Configuração de clientes](#clients) · [Solução de problemas](#faq) · [Patrocinador](#sponsors)

</div>

---

<a id="sponsors"></a>

## ❤️ Patrocinador

<table>
<tr>
<td width="180" align="center"><a href="https://ai18n.chat"><img src="../assets/sponsors/ai18n.png" alt="ai18n" width="150"></a></td>
<td>Agradecemos à <a href="https://ai18n.chat"><strong>ai18n</strong></a> pelo patrocínio deste projeto! A ai18n oferece serviços de intermediação de APIs de IA para ferramentas como OpenClaw, Claude Code, Codex e Gemini.</td>
</tr>
</table>

---

Cursor Gateway é uma versão em Python do [cursor2api](https://github.com/AstroQore/cursor2api). Atende requisições HTTP com FastAPI e se conecta diretamente ao backend Agent do Cursor via HTTP/2 e protobuf. A execução do gateway não exige Node.js, Cursor CLI nem automação de navegador.

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
> Este cliente não é oficial, não tem vínculo com a Anysphere nem é endossado por ela. Use sua própria conta do Cursor. A disponibilidade dos modelos e as cotas dependem da sua conta e do serviço de origem.

<a id="features"></a>

## ✨ Recursos

| Recurso | Descrição |
| --- | --- |
| 🔌 **APIs compatíveis com OpenAI** | `/v1/models`, `/v1/chat/completions` e `/v1/responses` |
| 💻 **Integração com Codex CLI** | Inclui um inicializador para fluxos com patches de arquivos, terminais / PTYs, MCP, múltiplos agentes, recuperação de sessões e revisão de código |
| 📡 **Streaming** | Respostas JSON e SSE, resumos de raciocínio e eventos de chamadas de ferramentas |
| 🛠️ **Chamadas de ferramentas** | Ferramentas de função e resultados em múltiplos turnos; Responses também aceita ferramentas personalizadas, namespaces e descoberta de ferramentas no cliente |
| 🧠 **Continuidade de tarefas** | Resultados de ferramentas em Responses podem retomar o mesmo Cursor Run, inclusive com `store=false` |
| 👁️ **Entrada de imagens** | Imagens PNG, JPEG, WebP e GIF embutidas em base64, quando o modelo oferece suporte |
| 🔍 **Busca na web** | Mapeia `web_search` / `web_search_preview` de Responses para a busca nativa do Cursor |
| 📐 **Saída estruturada** | Responses oferece instruções ao modelo e validação da saída final para `json_object` / `json_schema` |
| 💬 **Histórico e compactação** | `previous_response_id`, consulta / exclusão de respostas, paginação de entradas e checkpoints de compactação criptografados |
| 🔀 **Múltiplas contas** | Seleção em rodízio, recarga de arquivos sem reiniciar, renovação automática de tokens e pausas após falhas de autenticação ou de cota |
| 🤖 **Descoberta dinâmica de modelos** | Listas e caches por conta, com suporte aos nomes antigos com prefixo `cursor-` |
| 🌐 **Proxy SOCKS5** | Abrange consultas de status do login, descoberta de modelos, geração e renovação de tokens; aceita autenticação por usuário / senha |
| 🐳 **Implantação e diagnóstico** | Docker Compose, exemplo de systemd, documentação interativa da API e logs com IDs de requisição |

Veja os limites em [Compatibilidade](#compatibility). O cliente que faz a chamada gerencia a execução das ferramentas e as permissões.

<a id="models"></a>

## 🤖 Modelos disponíveis

O gateway busca o catálogo de modelos da conta selecionada para a requisição. Depois de fazer login e iniciar o serviço:

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

Use um dos valores `data[].id` retornados como modelo no cliente. Os exemplos deste documento usam `auto`; se sua conta não oferecer suporte a ele, escolha um modelo disponível na lista.

- Por padrão, os nomes omitem o prefixo `cursor-` do serviço de origem. Por exemplo, `grok-4.6-medium` é mapeado para o ID real na origem.
- Os nomes antigos com `cursor-` continuam funcionando. Defina `CURSOR_DIRECT_MODEL_PREFIX` para personalizar os nomes expostos aos clientes.
- Os catálogos ficam em cache por 10 minutos. Se a descoberta falhar, o gateway usa um cache anterior ou o catálogo de fallback e tenta novamente após 30 segundos.

> [!NOTE]
> O catálogo de fallback é usado quando a descoberta falha; ele não garante acesso a todos os modelos listados. Com múltiplas contas, cada consulta retorna o catálogo da conta selecionada para aquela requisição.

<a id="quick-start"></a>

## 🚀 Início rápido

Escolha **Python nativo** para desenvolvimento e depuração ou **[Docker Compose](#docker)** para implantação em contêineres.

### Pré-requisitos

- **Python 3.14+**. O desenvolvimento, os testes e a imagem Docker usam Python 3.14.
- Uma conta do Cursor que consiga fazer login e tenha cota de uso disponível.
- Acesso de rede aos serviços do Cursor, diretamente ou por um [proxy SOCKS5](#proxy).

### 1. Obter o projeto e instalar

Clone usando a URL desta página do repositório ou escolha **Code → Download ZIP** e extraia o arquivo.

```bash
git clone https://github.com/hnewcity/cursor-gateway.git
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Execute todos os comandos seguintes na raiz do repositório, salvo indicação em contrário.

<details>
<summary>🪟 Instalação com Windows PowerShell</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

No Windows, substitua `.venv/bin/python` e `.venv/bin/cursor-gateway` nos exemplos seguintes por `.venv\Scripts\python.exe` e `.venv\Scripts\cursor-gateway.exe`.

</details>

### 2. Fazer login no Cursor

```bash
.venv/bin/cursor-gateway login
```

Abra a URL exibida no terminal e autorize o login no navegador. Você também pode [importar um login local](#accounts) ou usar um arquivo de contas existente. Por padrão, as credenciais são salvas em `accounts.json`, na raiz do repositório.

### 3. Iniciar o serviço

```bash
.venv/bin/cursor-gateway serve
```

O endereço padrão é `http://127.0.0.1:8790`. O serviço lê `.env` do diretório atual; variáveis de ambiente já definidas têm prioridade.

```bash
# Set the listen address and port
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# Alternatively, start through the Python module
.venv/bin/python -m cursor_gateway serve
```

### 4. Enviar a primeira requisição

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello! Please introduce yourself."}]}'
```

> [!TIP]
> Para proteger a API do gateway, defina `CURSOR_DIRECT_API_KEY=sk-your-secret` em `.env` e configure os clientes com a mesma chave. Essa chave do gateway é independente do token da sua conta do Cursor.
> Os exemplos leem a chave do ambiente do terminal. Se você a definiu apenas no `.env` do servidor, execute `export CURSOR_DIRECT_API_KEY="sk-your-secret"` no terminal usado para o cliente.

<a id="accounts"></a>

## 🔐 Configuração de contas

Escolha o método adequado ao seu ambiente. Se já tiver um arquivo de contas, vá para a opção 3.

### Opção 1: Login pelo navegador

Funciona localmente ou em um servidor remoto. O servidor exibe uma URL que você pode abrir no seu computador.

```bash
.venv/bin/cursor-gateway login
```

Para especificar um proxy para as consultas de status do login:

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### Opção 2: Importar um login local

Se você estiver conectado ao **aplicativo de desktop do Cursor** na mesma máquina, importe as credenciais do banco de dados SQLite dele:

```bash
.venv/bin/cursor-gateway import-local

# Use a custom data directory
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 Exportar uma conta do Cursor CLI / desktop para implantação em servidor</summary>

O [script independente de exportação de credenciais](../../scripts/export_cursor_credentials.py) usa apenas a biblioteca padrão do Python. Não exige instalar o gateway, não faz requisições de rede nem envia credenciais automaticamente para qualquer destino.

```bash
# Run from the repository root to create a server-ready account file
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# Use only the Cursor CLI login
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

Você também pode copiar apenas o script para uma máquina com login ativo no Cursor:

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

Por padrão, o script cria `accounts.json` ao lado de si mesmo e recusa sobrescrever um arquivo existente. Aceita `--source cli` / `--source desktop`, `--out` e `--db` para um banco de dados do aplicativo de desktop. O macOS pode solicitar acesso às Chaves.

Coloque o arquivo exportado em `data/accounts.json` no servidor para usá-lo com a configuração do Docker Compose deste repositório.

</details>

### Opção 3: Usar um arquivo de contas existente

O gateway aceita o formato de contas do `cursor2api`. Defina o caminho em `.env`:

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

O formato `{"accounts": [...]}` também é aceito. `refreshToken` é opcional, mas necessário para a renovação automática. Os campos opcionais `expiresAt` e `disabledUntil` aceitam datas e horários no formato ISO.

Login, importação e renovação usam gravações atômicas com permissões de arquivo `0600`. Ao usar um arquivo existente, a renovação automática grava os tokens atualizados nesse mesmo arquivo.

</details>

> [!IMPORTANT]
> `accounts.json` contém credenciais que dão acesso à sua conta. Mantenha-o privado. Arquivos de contas, `.env` e chaves de compactação estão incluídos em `.gitignore`.

<a id="multi-account"></a>

## 🔀 Múltiplas contas

Adicione contas com `--merge`:

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| Comportamento | Descrição |
| --- | --- |
| Mesclagem | `--merge` substitui a conta com o mesmo rótulo e preserva as demais. **Sem essa opção, todo o arquivo de saída é substituído.** |
| Roteamento de requisições | Novas requisições alternam entre as contas disponíveis; um Run nativo retomado mantém sua conta original |
| Recarga sem reinício | Alterações no arquivo de contas valem para as requisições seguintes sem reiniciar |
| Renovação de tokens | Tenta renovar nos 30 minutos anteriores à expiração; renovações simultâneas são agrupadas dentro de um processo |
| Pausa temporária | Cota esgotada e erros de autenticação ou permissão causam uma pausa de 60 segundos; requisições posteriores usam outras contas disponíveis |

Erros do serviço de origem são devolvidos à requisição atual, sem repetir automaticamente uma geração que já começou. Use um único processo do gateway para gravar em cada arquivo de contas.

<a id="docker"></a>

## 🐳 Implantação com Docker

O repositório inclui um `Dockerfile` e `docker-compose.yml`. Execute na raiz do repositório:

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

O contêiner escuta em `0.0.0.0:8790`, enquanto a publicação no host usa `127.0.0.1:8790` por padrão. O Compose monta `./data` em `/data`. As contas ficam em `/data/accounts.json` e, por padrão, a chave de compactação fica no mesmo diretório.

<details>
<summary>🔧 Comandos comuns de gerenciamento</summary>

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

`CURSOR_DIRECT_PORT` controla a porta publicada no host; a porta do contêiner permanece `8790`. O Compose fixa o caminho das contas em `/data/accounts.json` e não usa `CURSOR_DIRECT_AUTH_FILE` de `.env`.

Dentro de um contêiner, `127.0.0.1` se refere ao próprio contêiner. Para usar um proxy do host, informe um endereço acessível pelo contêiner. No Docker Desktop, `host.docker.internal` pode ser usado quando a configuração de rede permitir.

</details>

<details>
<summary>🐧 Implantar com systemd</summary>

Veja o exemplo em [deploy/cursor-gateway.service](../../deploy/cursor-gateway.service).

Instale o projeto e seu ambiente virtual em `/opt/cursor-gateway`, crie um usuário de serviço `cursor-gateway` e permita que ele leia o projeto e a configuração e grave em `data`. Depois da preparação:

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

O exemplo usa `/opt/cursor-gateway/data/accounts.json` e lê `.env` da raiz do projeto.

</details>

<a id="clients"></a>

## 💡 Configuração de clientes

### Clientes compatíveis com OpenAI

| Configuração | Valor |
| --- | --- |
| URL base | `http://127.0.0.1:8790/v1` |
| Chave de API | O valor de `CURSOR_DIRECT_API_KEY`; qualquer texto não vazio se nenhuma chave estiver configurada |
| Modelo | Um modelo retornado por `/v1/models`, como `auto` quando disponível na sua conta |
| Protocolo da API | Chat Completions ou Responses, conforme o cliente |

Para clientes em outra máquina, substitua `127.0.0.1` por um endereço acessível do gateway e ajuste o endereço de escuta ou o mapeamento de portas.

### Codex CLI

Instale o Codex CLI, inicie o gateway e execute o inicializador incluído:

```bash
# Interactive use
.venv/bin/python scripts/run_codex.py --model auto

# Run a coding task
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write 'Create hello.py, run it, and check the output'
```

O inicializador usa Responses via HTTP/SSE e um catálogo temporário de modelos. Preserva sua configuração habitual sem editar `~/.codex/config.toml`. Exporte a chave do gateway no terminal atual. O Codex controla a execução de ferramentas, as aprovações de MCP e o sandbox.

O limite de contexto do cliente é de 65.536 tokens por padrão; ajuste-o com `--context-window`. Use `--text-only` para modelos sem suporte a imagens ou `--url` para outro endereço do gateway.

Consulte o [guia do Codex CLI (em inglês)](../en/codex-usage.md) para recuperação de sessões, continuação de Runs nativos e compactação.

### Exemplos de requisições

<details>
<summary>📡 Chat Completions em streaming</summary>

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

Os fragmentos de texto aparecem em `choices[].delta.content`; os de raciocínio usam `reasoning_content`. Com `include_usage`, um fragmento adicional de uso com `choices: []` é enviado antes do `[DONE]` final.

</details>

<details>
<summary>💬 Requisição à API Responses</summary>

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

O texto visível aparece em itens `output_text` dentro de `output[].content[]`. Defina `stream: true` para receber eventos SSE tipados `response.*` ou `store: false` para não armazenar o histórico de respostas.

</details>

<details>
<summary>🐍 SDK da OpenAI para Python</summary>

Instale a dependência do cliente:

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

Consulte a [referência da API (em inglês)](../en/api-reference.md) para ferramentas de função, streaming de Responses, continuação de histórico e detalhes de compatibilidade.

</details>

<a id="api"></a>

## 📡 Endpoints da API

| Método | Caminho | Finalidade |
| --- | --- | --- |
| `GET` / `HEAD` | `/`, `/health` | Verificação de atividade e quantidade de contas disponíveis; não exige autenticação |
| `GET` / `HEAD` | `/v1/models` | Catálogo de modelos da conta selecionada |
| `POST` | `/v1/chat/completions` | Chat Completions, JSON / SSE |
| `POST` | `/v1/responses` | Responses, JSON / SSE |
| `POST` | `/v1/responses/compact` | Gerar um checkpoint de compactação criptografado |
| `GET` | `/v1/responses/{response_id}` | Consultar uma resposta armazenada |
| `DELETE` | `/v1/responses/{response_id}` | Excluir uma resposta e o snapshot de sua entrada |
| `GET` | `/v1/responses/{response_id}/input_items` | Consultar o histórico de entrada com paginação |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc e descrição OpenAPI; não exige autenticação |

Quando `CURSOR_DIRECT_API_KEY` está definida, todos os endpoints `/v1/*` aceitam autenticação por `Authorization: Bearer <key>` ou `x-api-key`. Use **Authorize** no Swagger UI para informar a chave.

<a id="configuration"></a>

## ⚙️ Configuração

Copie [.env.example](../../.env.example) para `.env` e edite-o. Configurações comuns:

| Variável de ambiente | Padrão | Descrição |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | Endereço de escuta |
| `CURSOR_DIRECT_PORT` | `8790` | Porta de escuta |
| `CURSOR_DIRECT_API_KEY` | Vazio | Chave usada pelos clientes para chamar o gateway |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | Caminho do arquivo de contas |
| `CURSOR_DIRECT_PROXY_URL` | Vazio | URL do proxy SOCKS5 |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | Tempo limite de comunicação com Agent por turno, incluindo conexão e handshake, em milissegundos |
| `CURSOR_DIRECT_MODEL_PREFIX` | Vazio | Prefixo dos nomes de modelos expostos; o prefixo `cursor-` da origem é removido por padrão |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | Registrar resumos, IDs e duração de requisições; erros continuam sendo registrados quando desativado |

<details>
<summary>🔧 Todas as configurações avançadas</summary>

| Variável de ambiente | Padrão | Descrição |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | Origem HTTP(S) do serviço upstream |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | Cabeçalho de versão do cliente enviado à origem |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | Ferramentas nativas permitidas na origem; `*` omite o cabeçalho de restrição |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | Converter instruções de sistema / desenvolvedor em turnos históricos de configuração |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | Manter resumos recentes de raciocínio ao reenviar o histórico completo |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | Limite total de caracteres dos resumos reenviados, priorizando os mais recentes |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | Tentativas de corrigir o formato de entrada das ferramentas em um Run, de 0 a 3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | Retomar um Run nativo pendente com resultados de ferramentas |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | Espera máxima por resultados de ferramentas do cliente, em segundos |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | Quantidade máxima de Runs nativos mantidos |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | Prompt de continuação usado ao reenviar o histórico completo |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | Limite de tamanho de requisições / respostas; streams de Responses também limitam a saída acumulada |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | Tempo de vida do histórico de respostas, em segundos |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | Quantidade máxima de respostas armazenadas |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | Tamanho máximo do histórico de respostas serializado, em bytes |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | `compaction.key` ao lado do arquivo de contas | Chave dos checkpoints de compactação; mantenha esse arquivo persistente |

A descoberta de modelos e a renovação de tokens têm tempos limite de rede separados, então a primeira requisição pode demorar mais.

As classes protobuf geradas estão incluídas no projeto. Não é necessário `protoc` para iniciar o gateway, e ele não usa `CURSOR_DIRECT_PROTO_DIR` do projeto Node original.

</details>

<a id="proxy"></a>

## 🌐 Suporte a proxy

Configure o proxy em `.env`:

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# For username / password authentication, use this format
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

Tanto `socks5://` quanto `socks5h://` resolvem os nomes de host de destino pelo proxy. Aplique codificação de URL a caracteres especiais de usuário e senha. O proxy abrange descoberta de modelos, geração, renovação de tokens e consultas de status do login. URLs de proxy HTTP ainda não são suportadas.

<a id="faq"></a>

## 🔧 Solução de problemas

<details>
<summary>A verificação de saúde passa. Por que as requisições retornam 503?</summary>

`/health` verifica se o processo está ativo. `{"ok": true, "accounts": 0, ...}` significa que ele está em execução, mas não há contas disponíveis. Você pode não ter feito login, ou todas as contas podem estar em pausa temporária.

Execute `login` / `import-local` e confira o caminho de contas realmente usado pelo serviço. O padrão local é `./accounts.json`; o Docker Compose usa `./data/accounts.json`. Se o erro vier da origem, use os detalhes retornados para investigar a disponibilidade do serviço.

</details>

<details>
<summary>Por que recebo 400? Como envio imagens e ferramentas?</summary>

Verifique o JSON `error` do cliente e os logs com o mesmo `X-Request-ID`. Causas comuns incluem:

- `tool_choice="required"`, escolha forçada de ferramenta ou outros parâmetros não suportados.
- URLs de imagens remotas, IDs de arquivos ou entrada de áudio. As imagens devem usar um formato suportado em uma URL de dados base64.
- Ferramentas hospedadas não implementadas, como `file_search`, ou campos `include` não suportados.
- JSON inválido, entrada malformada de ferramentas personalizadas ou configuração inválida de JSON Schema.

Responses aceita imagens e validação de saída com JSON Schema por meio de `text.format`. Consulte os formatos na [referência da API (em inglês)](../en/api-reference.md). Se os logs mostrarem `stage="upstream"`, investigue a mensagem de erro da origem e o modelo selecionado.

</details>

<details>
<summary>Como investigo uma requisição específica que falhou?</summary>

Os diagnósticos de requisições estão disponíveis no nível padrão de log `info`. Para implantações Docker:

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# Replace the placeholder with the X-Request-ID response header value
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F 'REPLACE_WITH_REQUEST_ID'
```

As mensagens de log são JSON em uma única linha. Eventos de uma requisição compartilham o mesmo `request_id`:

| Evento | O que verificar |
| --- | --- |
| `request_started` / `request_parsed` | Caminho, cliente e resumo dos parâmetros |
| `generation_started` | Rótulo da conta, modelo real na origem, quantidade de itens de histórico e de ferramentas |
| `compatibility_notice` | Informações de mapeamento de compatibilidade; esse evento isolado não indica falha |
| `request_error` | `stage`, `error_status`, `error_param`, `error_message` e `error_code` da origem |
| `request_finished` | Status HTTP, `outcome`, duração e contagem de bytes |

Erros após o início do SSE ainda podem ter status HTTP 200. Verifique também os erros do stream e o `outcome` registrado. Mapeamentos comuns de erros da origem:

| Erro da origem | Status HTTP |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| Outros erros de protocolo ou da origem | `502` |

Os resumos de log excluem prompts, corpos de mensagens, argumentos / saídas de ferramentas, valores de metadados, cookies e cabeçalhos de autenticação. Credenciais conhecidas no texto dos erros são ocultadas. Desativar `CURSOR_DIRECT_LOG_REQUESTS` desliga apenas os logs rotineiros de requisições.

</details>

<details>
<summary>Por que previous_response_id deixa de funcionar após reiniciar?</summary>

O histórico de respostas fica na memória do processo, com limites padrão de uma hora, 256 entradas e 128 MiB. Reiniciar apaga esse histórico, que não é compartilhado entre processos ou instâncias. Uma resposta ausente no cache retorna `404`.

Para gerenciar o histórico no cliente, use `store=false` e envie a entrada completa, a saída anterior e os resultados de ferramentas. Checkpoints de compactação dependem de `compaction.key`; persistir a mesma chave permite decodificá-los após reiniciar. Checkpoints e armazenamento por ID de resposta são mecanismos separados.

Ao usar `previous_response_id`, forneça novamente as `instructions` necessárias e as definições de ferramentas em cada turno.

</details>

<a id="compatibility"></a>

## 📋 Compatibilidade

| Capacidade | Implementação e limites |
| --- | --- |
| Protocolos de API | Chat Completions, Responses e Models; sem `/v1/messages` da Anthropic, Embeddings ou interface de gerenciamento |
| Imagens | As duas APIs de geração aceitam imagens PNG / JPEG / WebP / GIF embutidas, de até 16 MiB cada e 32 imagens por requisição, respeitando o limite total do corpo; URLs remotas, IDs de arquivo e áudio não são suportados |
| Ferramentas | Os clientes executam ferramentas de função / personalizadas. `tool_choice` aceita `auto` / `none`. Ativar `parallel_tool_calls` reúne chamadas recebidas no mesmo lote; a produção de chamadas paralelas depende do modelo de origem |
| Saída estruturada | Responses instrui o modelo e valida a resposta final, sem decodificação restrita nativa. `response_format` de Chat Completions não tem efeito |
| Controles de amostragem e raciocínio | Parâmetros como `temperature`, `top_p` e limites de tokens não são integralmente aplicados na origem. Chat Completions aceita apenas `n=1` |
| Estado de raciocínio | Expõe resumos visíveis de raciocínio; não gera nem descriptografa `reasoning.encrypted_content` da OpenAI |
| Contagem de tokens | Chat Completions informa zero tokens de entrada. Os tokens de entrada de Responses são estimativas marcadas com `estimated=true`. As contagens da origem são mapeadas para tokens de saída; não há detalhes separados de cobrança de cache / raciocínio |
| Busca na web | Responses usa a busca nativa do Cursor, sem as opções de localização ou filtragem de domínios da OpenAI |
| Transporte e recursos hospedados | HTTP/SSE; sem WebSocket de Responses, `background=true`, `conversation` / `prompt` hospedados ou outras ferramentas integradas hospedadas. A desconexão do cliente cancela a requisição à origem |

Por padrão, instruções de sistema / desenvolvedor são transmitidas como mensagens históricas com rótulos de origem; seu efeito continua dependendo dos prompts do serviço de origem. Mesmo com `CURSOR_ALLOWED_NATIVE_TOOLS=*`, o gateway não executa comandos de shell, operações de arquivos ou patches do cliente em seu host.

Consulte a [referência da API (em inglês)](../en/api-reference.md) para o comportamento detalhado dos parâmetros e o [guia do Codex CLI (em inglês)](../en/codex-usage.md) para configurar o cliente.

<a id="development"></a>

## 🧪 Desenvolvimento e verificação

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

Os testes automatizados usam credenciais fictícias e um serviço de origem simulado local. Cobrem renovação de contas, validação de requisições, JSON / SSE, ciclos de ferramentas, histórico de Responses, cancelamento e transporte HTTP/2 / protobuf por conexões TCP locais. Não exigem credenciais reais, inferência paga nem Codex CLI.

<details>
<summary>🛠️ Geração de código do protocolo</summary>

Após alterar as definições do protocolo, gere novamente as classes Python com `protoc 36.1`:

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 Estrutura do projeto</summary>

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

## 🤝 Como contribuir

Use Issues para relatar bugs reproduzíveis e discutir recursos, e leia o [guia de contribuição (chinês / inglês)](../../CONTRIBUTING.md) antes de enviar um pull request.
Mantenha os README dos oito idiomas e os guias em chinês e inglês sincronizados ao alterar comportamentos, configurações ou exemplos, e siga o [código de conduta (chinês / inglês)](../../CODE_OF_CONDUCT.md).
Relate vulnerabilidades de forma privada conforme a [política de segurança (chinês / inglês)](../../SECURITY.md). Veja as alterações de versão no [histórico de mudanças (em inglês)](../../CHANGELOG.md).

<a id="credits"></a>

## 🙏 Créditos e licença

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api): implementação original da qual este projeto foi portado, incluindo mapeamentos de protocolo, formato de contas e catálogo de modelos de fallback.
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi): origem do provedor Cursor / `agent.proto` creditada pelo projeto original.
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway): referência para o layout deste README e a estrutura da documentação.

Este projeto está licenciado sob **[AGPL-3.0-only](../../LICENSE)**. Veja a atribuição completa em [NOTICE](../../NOTICE).

Ao distribuir ou operar uma versão modificada para outras pessoas, cumpra os requisitos da AGPL quanto ao fornecimento do código-fonte correspondente. Disponibilize o código-fonte completo da versão em execução pelo repositório ou por uma distribuição de fontes, com um acesso claro ao código para usuários da rede. Builds de contêineres podem registrar a localização pública do código com `--build-arg SOURCE_URL=PUBLIC_SOURCE_URL`.
