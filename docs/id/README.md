<div align="center">

# ⚡ Cursor Gateway

**Hubungkan akun Cursor Anda ke API yang kompatibel dengan OpenAI**

[English](../en/README.md) · [Русский](../ru/README.md) · [简体中文](../../README.md) · [Español](../es/README.md) · **Bahasa Indonesia** · [Português (Brasil)](../pt-BR/README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md)

Gunakan klien yang biasa Anda pakai dengan model yang tersedia di akun Cursor Anda. Mendukung Chat Completions, API Responses, dan Codex CLI.

[![CI](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/hnewcity/cursor-gateway/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-AGPL--3.0--only-blue)](../../LICENSE)

[Fitur](#features) · [Mulai cepat](#quick-start) · [Akun](#accounts) · [Docker](#docker) · [Konfigurasi klien](#clients) · [Pemecahan masalah](#faq) · [Sponsor](#sponsors)

</div>

---

<a id="sponsors"></a>

## ❤️ Sponsor

<table>
<tr>
<td width="180" align="center"><a href="https://ai18n.chat"><img src="../assets/sponsors/ai18n.png" alt="ai18n" width="150"></a></td>
<td>Terima kasih kepada <a href="https://ai18n.chat"><strong>ai18n</strong></a> yang telah mensponsori proyek ini! ai18n menyediakan layanan perantara API AI untuk alat seperti OpenClaw, Claude Code, Codex, dan Gemini.</td>
</tr>
</table>

---

Cursor Gateway adalah port Python dari [cursor2api](https://github.com/AstroQore/cursor2api). Proyek ini melayani permintaan HTTP menggunakan FastAPI dan terhubung langsung ke backend Agent Cursor melalui HTTP/2 dan protobuf. Gateway dapat dijalankan tanpa Node.js, Cursor CLI, atau otomatisasi browser.

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
> Ini adalah klien tidak resmi yang tidak berafiliasi dengan maupun didukung oleh Anysphere. Gunakan akun Cursor Anda sendiri. Ketersediaan model dan kuota bergantung pada akun Anda serta layanan upstream.

<a id="features"></a>

## ✨ Fitur

| Fitur | Deskripsi |
| --- | --- |
| 🔌 **API kompatibel dengan OpenAI** | `/v1/models`, `/v1/chat/completions`, dan `/v1/responses` |
| 💻 **Integrasi Codex CLI** | Menyertakan peluncur untuk alur kerja yang melibatkan patch berkas, terminal / PTY, MCP, banyak agen, pemulihan sesi, dan peninjauan kode |
| 📡 **Streaming** | Respons JSON dan SSE, ringkasan penalaran, serta peristiwa pemanggilan alat |
| 🛠️ **Pemanggilan alat** | Alat fungsi dan hasil alat lintas giliran; Responses juga mendukung alat kustom, namespace, dan penemuan alat di sisi klien |
| 🧠 **Kelanjutan tugas** | Hasil alat pada Responses dapat melanjutkan Cursor Run yang sama, termasuk dengan `store=false` |
| 👁️ **Masukan gambar** | Gambar PNG, JPEG, WebP, dan GIF yang disisipkan dalam base64, jika didukung model |
| 🔍 **Pencarian web** | Memetakan `web_search` / `web_search_preview` pada Responses ke pencarian bawaan Cursor |
| 📐 **Keluaran terstruktur** | Responses mendukung instruksi kepada model dan validasi keluaran akhir untuk `json_object` / `json_schema` |
| 💬 **Riwayat dan pemadatan** | `previous_response_id`, pengambilan / penghapusan respons, paginasi masukan, dan checkpoint pemadatan terenkripsi |
| 🔀 **Banyak akun** | Pemilihan bergiliran, pemuatan ulang berkas tanpa restart, pembaruan token otomatis, serta masa jeda setelah kegagalan autentikasi atau kuota |
| 🤖 **Penemuan model dinamis** | Daftar dan cache model per akun, dengan dukungan nama model lama berawalan `cursor-` |
| 🌐 **Proxy SOCKS5** | Mencakup polling login, penemuan model, generasi, dan pembaruan token; mendukung autentikasi nama pengguna / kata sandi |
| 🐳 **Deployment dan diagnostik** | Docker Compose, contoh systemd, dokumentasi API interaktif, dan log dengan ID permintaan |

Lihat batasan terperinci di [Kompatibilitas](#compatibility). Klien pemanggil menangani eksekusi alat dan perizinan.

<a id="models"></a>

## 🤖 Model yang tersedia

Gateway mengambil katalog model untuk akun yang dipilih bagi permintaan tersebut. Setelah login dan menjalankan layanan:

```bash
curl http://127.0.0.1:8790/v1/models \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}"
```

Gunakan salah satu nilai `data[].id` yang dikembalikan sebagai pengaturan model klien. Contoh dalam dokumen ini menggunakan `auto`; jika akun Anda tidak mendukungnya, pilih model yang tersedia dari daftar.

- Secara default, nama model tidak menyertakan awalan `cursor-` dari upstream. Misalnya, `grok-4.6-medium` dipetakan ke ID upstream yang sebenarnya.
- Nama lama dengan awalan `cursor-` tetap berfungsi. Atur `CURSOR_DIRECT_MODEL_PREFIX` untuk menyesuaikan nama yang ditampilkan kepada klien.
- Katalog model disimpan dalam cache selama 10 menit. Jika penemuan gagal, gateway menggunakan cache lama atau katalog cadangan dan mencoba lagi setelah 30 detik.

> [!NOTE]
> Katalog cadangan digunakan saat penemuan gagal; katalog ini tidak menjamin akses ke semua model yang tercantum. Dengan banyak akun, setiap kueri mengembalikan katalog akun yang dipilih untuk permintaan tersebut.

<a id="quick-start"></a>

## 🚀 Mulai cepat

Pilih **Python langsung** untuk pengembangan dan debugging, atau **[Docker Compose](#docker)** untuk deployment kontainer.

### Prasyarat

- **Python 3.14+**. Pengembangan, pengujian, dan image Docker menggunakan Python 3.14.
- Akun Cursor yang dapat login dan memiliki kuota pemakaian.
- Akses jaringan ke layanan Cursor, secara langsung atau melalui [proxy SOCKS5](#proxy).

### 1. Unduh proyek dan instal

Clone menggunakan URL pada halaman repositori ini, atau pilih **Code → Download ZIP** lalu ekstrak arsipnya.

```bash
git clone https://github.com/hnewcity/cursor-gateway.git
cd cursor-gateway

python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Jalankan semua perintah berikutnya dari direktori utama repositori kecuali dinyatakan lain.

<details>
<summary>🪟 Instalasi dengan Windows PowerShell</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
.venv\Scripts\cursor-gateway.exe login
.venv\Scripts\cursor-gateway.exe serve
```

Di Windows, ganti `.venv/bin/python` dan `.venv/bin/cursor-gateway` dalam contoh berikutnya dengan `.venv\Scripts\python.exe` dan `.venv\Scripts\cursor-gateway.exe`.

</details>

### 2. Login ke Cursor

```bash
.venv/bin/cursor-gateway login
```

Buka URL yang ditampilkan terminal dan setujui login di browser. Anda juga dapat [mengimpor login lokal](#accounts) atau menggunakan berkas akun yang sudah ada. Secara default, kredensial disimpan ke `accounts.json` di direktori utama repositori.

### 3. Jalankan layanan

```bash
.venv/bin/cursor-gateway serve
```

Alamat default adalah `http://127.0.0.1:8790`. Layanan membaca `.env` dari direktori saat ini; variabel lingkungan yang sudah ada lebih diprioritaskan.

```bash
# Set the listen address and port
.venv/bin/cursor-gateway serve --host 127.0.0.1 --port 8790

# Alternatively, start through the Python module
.venv/bin/python -m cursor_gateway serve
```

### 4. Kirim permintaan pertama

```bash
curl http://127.0.0.1:8790/health

curl http://127.0.0.1:8790/v1/chat/completions \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello! Please introduce yourself."}]}'
```

> [!TIP]
> Untuk melindungi API gateway, atur `CURSOR_DIRECT_API_KEY=sk-your-secret` di `.env` dan gunakan kunci yang sama pada klien. Kunci gateway ini terpisah dari token akun Cursor Anda.
> Contoh permintaan membaca kunci dari lingkungan terminal. Jika Anda hanya mengaturnya di `.env` server, jalankan `export CURSOR_DIRECT_API_KEY="sk-your-secret"` di terminal yang digunakan oleh klien.

<a id="accounts"></a>

## 🔐 Konfigurasi akun

Pilih metode yang sesuai dengan lingkungan Anda. Jika sudah memiliki berkas akun, langsung ke opsi 3.

### Opsi 1: Login melalui browser

Berfungsi secara lokal maupun di server jarak jauh. Server menampilkan URL yang dapat Anda buka di komputer sendiri.

```bash
.venv/bin/cursor-gateway login
```

Untuk menentukan proxy bagi polling login:

```bash
.venv/bin/cursor-gateway login --proxy socks5://127.0.0.1:1080
```

### Opsi 2: Impor login lokal

Jika Anda sudah login ke **aplikasi desktop Cursor** di komputer yang sama, impor kredensial dari database SQLite-nya:

```bash
.venv/bin/cursor-gateway import-local

# Use a custom data directory
.venv/bin/cursor-gateway import-local --db /path/to/state.vscdb
```

<details>
<summary>📦 Ekspor akun Cursor CLI / desktop untuk deployment server</summary>

[Skrip ekspor kredensial](../../scripts/export_cursor_credentials.py) mandiri hanya menggunakan pustaka standar Python. Skrip ini tidak memerlukan instalasi gateway, tidak membuat permintaan jaringan, dan tidak mengirim kredensial secara otomatis ke mana pun.

```bash
# Run from the repository root to create a server-ready account file
mkdir -p data
python3.14 scripts/export_cursor_credentials.py --out data/accounts.json

# Use only the Cursor CLI login
python3.14 scripts/export_cursor_credentials.py --source cli --out data/cli-accounts.json
```

Anda juga dapat menyalin skrip saja ke komputer yang sudah login ke Cursor:

```bash
# macOS / Linux
python3.14 export_cursor_credentials.py
```

```powershell
# Windows PowerShell
py -3.14 export_cursor_credentials.py
```

Secara default, skrip membuat `accounts.json` di direktori yang sama dengan skrip dan menolak menimpa berkas yang sudah ada. Skrip mendukung `--source cli` / `--source desktop`, `--out`, serta `--db` untuk database desktop. macOS mungkin meminta akses Keychain.

Tempatkan berkas hasil ekspor di `data/accounts.json` pada server untuk menggunakannya dengan konfigurasi Docker Compose repositori ini.

</details>

### Opsi 3: Gunakan berkas akun yang sudah ada

Gateway menerima format akun `cursor2api`. Atur jalurnya di `.env`:

```dotenv
CURSOR_DIRECT_AUTH_FILE=/absolute/path/to/accounts.json
```

<details>
<summary>📄 Format accounts.json</summary>

```json
[
  {
    "label": "main",
    "accessToken": "your-access-token",
    "refreshToken": "your-refresh-token"
  }
]
```

Format `{"accounts": [...]}` juga diterima. `refreshToken` bersifat opsional, tetapi diperlukan untuk pembaruan otomatis. Kolom opsional `expiresAt` dan `disabledUntil` menerima cap waktu ISO.

Login, impor, dan pembaruan menggunakan penulisan atomik dengan izin berkas `0600`. Saat menggunakan berkas yang sudah ada, pembaruan otomatis menulis kembali token yang diperbarui ke berkas tersebut.

</details>

> [!IMPORTANT]
> `accounts.json` berisi kredensial yang memberikan akses ke akun Anda. Jaga kerahasiaannya. Berkas akun, `.env`, dan kunci pemadatan sudah dicantumkan di `.gitignore`.

<a id="multi-account"></a>

## 🔀 Banyak akun

Tambahkan akun dengan `--merge`:

```bash
.venv/bin/cursor-gateway login --merge --label second
.venv/bin/cursor-gateway import-local --merge --label desktop
```

| Perilaku | Deskripsi |
| --- | --- |
| Penggabungan | `--merge` mengganti akun dengan label yang sama dan mempertahankan akun lainnya. **Tanpa opsi ini, seluruh berkas keluaran akan diganti.** |
| Perutean permintaan | Permintaan baru bergiliran menggunakan akun yang tersedia; Run native yang dilanjutkan tetap memakai akun asalnya |
| Muat ulang tanpa restart | Perubahan berkas akun berlaku pada permintaan berikutnya tanpa memulai ulang layanan |
| Pembaruan token | Mencoba memperbarui dalam 30 menit sebelum kedaluwarsa; pembaruan bersamaan digabungkan dalam satu proses |
| Masa jeda | Kuota habis, kegagalan autentikasi, atau kesalahan izin memicu jeda 60 detik; permintaan berikutnya memakai akun lain yang tersedia |

Kesalahan upstream dikembalikan ke permintaan saat ini tanpa otomatis mengulangi generasi yang sudah dimulai. Gunakan satu proses gateway untuk menulis ke setiap berkas akun.

<a id="docker"></a>

## 🐳 Deployment Docker

Repositori menyertakan `Dockerfile` dan `docker-compose.yml`. Jalankan dari direktori utama repositori:

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

Kontainer mendengarkan pada `0.0.0.0:8790`, sedangkan binding host secara default adalah `127.0.0.1:8790`. Compose memasang `./data` ke `/data`. Akun disimpan di `/data/accounts.json`, dan kunci pemadatan secara default berada di direktori yang sama.

<details>
<summary>🔧 Perintah pengelolaan umum</summary>

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

`CURSOR_DIRECT_PORT` mengatur port yang dipublikasikan pada host; port kontainer tetap `8790`. Compose menetapkan jalur akun ke `/data/accounts.json` dan tidak menggunakan `CURSOR_DIRECT_AUTH_FILE` dari `.env`.

Di dalam kontainer, `127.0.0.1` merujuk pada kontainer itu sendiri. Untuk memakai proxy pada host, tentukan alamat yang dapat dijangkau dari kontainer. Deployment Docker Desktop dapat memakai `host.docker.internal` jika sesuai dengan konfigurasi jaringan.

</details>

<details>
<summary>🐧 Deployment dengan systemd</summary>

Lihat contoh di [deploy/cursor-gateway.service](../../deploy/cursor-gateway.service).

Instal proyek beserta lingkungan virtualnya di `/opt/cursor-gateway`, buat pengguna layanan `cursor-gateway`, dan izinkan pengguna tersebut membaca proyek serta konfigurasi dan menulis ke `data`. Setelah siap:

```bash
sudo cp deploy/cursor-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cursor-gateway
sudo journalctl -u cursor-gateway -f
```

Contoh ini menggunakan `/opt/cursor-gateway/data/accounts.json` dan membaca `.env` dari direktori utama proyek.

</details>

<a id="clients"></a>

## 💡 Konfigurasi klien

### Klien yang kompatibel dengan OpenAI

| Pengaturan | Nilai |
| --- | --- |
| URL dasar | `http://127.0.0.1:8790/v1` |
| Kunci API | Nilai `CURSOR_DIRECT_API_KEY`; string tidak kosong apa pun jika kunci belum dikonfigurasi |
| Model | Model yang dikembalikan oleh `/v1/models`, misalnya `auto` jika tersedia untuk akun Anda |
| Protokol API | Chat Completions atau Responses, bergantung pada klien |

Untuk klien di komputer lain, ganti `127.0.0.1` dengan alamat gateway yang dapat dijangkau dan sesuaikan alamat dengar atau pemetaan port.

### Codex CLI

Instal Codex CLI, jalankan gateway, lalu gunakan peluncur yang disertakan:

```bash
# Interactive use
.venv/bin/python scripts/run_codex.py --model auto

# Run a coding task
.venv/bin/python scripts/run_codex.py --model auto -- \
  exec --sandbox workspace-write 'Create hello.py, run it, and check the output'
```

Peluncur menggunakan Responses melalui HTTP/SSE dan katalog model sementara. Konfigurasi rutin Anda dipertahankan tanpa mengedit `~/.codex/config.toml`. Ekspor kunci gateway di terminal saat ini. Codex mengontrol eksekusi alat, persetujuan MCP, dan sandbox.

Batas konteks klien secara default adalah 65.536 token; sesuaikan dengan `--context-window`. Gunakan `--text-only` untuk model tanpa dukungan gambar, atau `--url` untuk alamat gateway yang berbeda.

Lihat [panduan Codex CLI (bahasa Inggris)](../en/codex-usage.md) untuk pemulihan sesi, kelanjutan Run native, dan pemadatan.

### Contoh permintaan

<details>
<summary>📡 Chat Completions dengan streaming</summary>

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

Potongan teks muncul di `choices[].delta.content`; potongan penalaran menggunakan `reasoning_content`. Dengan `include_usage`, satu potongan tambahan berisi penggunaan dengan `choices: []` dikirim sebelum `[DONE]` terakhir.

</details>

<details>
<summary>💬 Permintaan API Responses</summary>

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

Teks yang terlihat muncul sebagai item `output_text` di dalam `output[].content[]`. Atur `stream: true` untuk menerima peristiwa SSE bertipe `response.*`, atau `store: false` untuk melewati penyimpanan riwayat respons.

</details>

<details>
<summary>🐍 SDK OpenAI untuk Python</summary>

Instal dependensi klien:

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

Lihat [referensi API (bahasa Inggris)](../en/api-reference.md) untuk alat fungsi, streaming Responses, kelanjutan riwayat, dan catatan kompatibilitas terperinci.

</details>

<a id="api"></a>

## 📡 Endpoint API

| Metode | Jalur | Kegunaan |
| --- | --- | --- |
| `GET` / `HEAD` | `/`, `/health` | Status keaktifan proses dan jumlah akun yang tersedia; tidak memerlukan autentikasi |
| `GET` / `HEAD` | `/v1/models` | Katalog model untuk akun yang dipilih |
| `POST` | `/v1/chat/completions` | Chat Completions, JSON / SSE |
| `POST` | `/v1/responses` | Responses, JSON / SSE |
| `POST` | `/v1/responses/compact` | Membuat checkpoint pemadatan terenkripsi |
| `GET` | `/v1/responses/{response_id}` | Mengambil respons yang tersimpan |
| `DELETE` | `/v1/responses/{response_id}` | Menghapus respons dan snapshot masukannya |
| `GET` | `/v1/responses/{response_id}/input_items` | Mengambil riwayat masukan dengan paginasi |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc, dan deskripsi OpenAPI; tidak memerlukan autentikasi |

Saat `CURSOR_DIRECT_API_KEY` diatur, semua endpoint `/v1/*` menerima autentikasi `Authorization: Bearer <key>` atau `x-api-key`. Gunakan **Authorize** di Swagger UI untuk memasukkan kunci.

<a id="configuration"></a>

## ⚙️ Konfigurasi

Salin [.env.example](../../.env.example) ke `.env` lalu edit. Pengaturan umum:

| Variabel lingkungan | Default | Deskripsi |
| --- | --- | --- |
| `CURSOR_DIRECT_HOST` | `127.0.0.1` | Alamat dengar |
| `CURSOR_DIRECT_PORT` | `8790` | Port dengar |
| `CURSOR_DIRECT_API_KEY` | Kosong | Kunci yang digunakan klien untuk memanggil gateway |
| `CURSOR_DIRECT_AUTH_FILE` | `./accounts.json` | Jalur berkas akun |
| `CURSOR_DIRECT_PROXY_URL` | Kosong | URL proxy SOCKS5 |
| `CURSOR_DIRECT_TIMEOUT_MS` | `300000` | Batas waktu komunikasi Agent per giliran, termasuk koneksi dan handshake, dalam milidetik |
| `CURSOR_DIRECT_MODEL_PREFIX` | Kosong | Awalan nama model yang ditampilkan; awalan upstream `cursor-` dihapus secara default |
| `CURSOR_DIRECT_LOG_REQUESTS` | `true` | Catat ringkasan, ID, dan durasi permintaan; kesalahan tetap dicatat jika dinonaktifkan |

<details>
<summary>🔧 Semua pengaturan lanjutan</summary>

| Variabel lingkungan | Default | Deskripsi |
| --- | --- | --- |
| `CURSOR_DIRECT_BASE_URL` | `https://api2.cursor.sh` | Origin HTTP(S) upstream |
| `CURSOR_DIRECT_CLIENT_VERSION` | `cli-2026.08.11-e8db854` | Header versi klien untuk upstream |
| `CURSOR_ALLOWED_NATIVE_TOOLS` | `mcp_tool_call` | Alat native upstream yang diizinkan; `*` menghilangkan header pembatasan |
| `CURSOR_DIRECT_SYSTEM_AS_HISTORY` | `true` | Ubah instruksi sistem / developer menjadi giliran konfigurasi dalam riwayat |
| `CURSOR_DIRECT_REPLAY_REASONING` | `true` | Pertahankan ringkasan penalaran terbaru saat mengirim ulang seluruh riwayat |
| `CURSOR_DIRECT_REASONING_REPLAY_MAX_CHARS` | `12000` | Batas total karakter ringkasan yang dikirim ulang, dengan prioritas pada entri terbaru |
| `CURSOR_DIRECT_TOOL_INPUT_RETRIES` | `1` | Jumlah percobaan perbaikan format masukan alat dalam satu Run, dari 0 sampai 3 |
| `CURSOR_DIRECT_REUSE_SESSIONS` | `true` | Lanjutkan Run native yang tertunda dengan hasil alat |
| `CURSOR_DIRECT_SESSION_KEEPALIVE_SECONDS` | `300` | Waktu tunggu maksimum untuk hasil alat klien, dalam detik |
| `CURSOR_DIRECT_SESSION_MAX_ENTRIES` | `8` | Jumlah maksimum Run native yang disimpan |
| `CURSOR_DIRECT_CONTINUATION_PROMPT` | `Continue, using the tool results above.` | Prompt kelanjutan yang digunakan saat mengirim ulang seluruh riwayat |
| `CURSOR_DIRECT_MAX_BODY_BYTES` | `67108864` | Batas ukuran permintaan / respons; stream Responses juga membatasi keluaran kumulatif |
| `CURSOR_DIRECT_RESPONSE_CACHE_TTL` | `3600` | Masa simpan riwayat respons, dalam detik |
| `CURSOR_DIRECT_RESPONSE_CACHE_ENTRIES` | `256` | Jumlah maksimum respons tersimpan |
| `CURSOR_DIRECT_RESPONSE_CACHE_BYTES` | `134217728` | Ukuran maksimum riwayat respons terserialisasi, dalam byte |
| `CURSOR_DIRECT_COMPACTION_KEY_FILE` | `compaction.key` di samping berkas akun | Kunci checkpoint pemadatan; simpan berkas ini secara persisten |

Penemuan model dan pembaruan token memiliki batas waktu jaringan terpisah, sehingga permintaan pertama mungkin memerlukan waktu tambahan.

Kelas protobuf yang sudah dihasilkan disertakan dalam proyek. Menjalankan gateway tidak memerlukan `protoc`, dan gateway tidak memakai `CURSOR_DIRECT_PROTO_DIR` dari proyek Node asli.

</details>

<a id="proxy"></a>

## 🌐 Dukungan proxy

Atur proxy di `.env`:

```dotenv
CURSOR_DIRECT_PROXY_URL=socks5://127.0.0.1:1080

# For username / password authentication, use this format
# CURSOR_DIRECT_PROXY_URL=socks5://user:password@127.0.0.1:1080
```

Baik `socks5://` maupun `socks5h://` menyelesaikan nama host tujuan melalui proxy. Gunakan pengodean URL untuk karakter khusus dalam nama pengguna dan kata sandi. Proxy mencakup penemuan model, generasi, pembaruan token, dan polling login. URL proxy HTTP saat ini belum didukung.

<a id="faq"></a>

## 🔧 Pemecahan masalah

<details>
<summary>Pemeriksaan kesehatan berhasil. Mengapa permintaan mengembalikan 503?</summary>

`/health` memeriksa apakah proses aktif. `{"ok": true, "accounts": 0, ...}` berarti proses berjalan tetapi tidak ada akun yang tersedia. Anda mungkin belum login, atau semua akun sedang dalam masa jeda.

Jalankan `login` / `import-local` dan periksa jalur akun yang benar-benar dipakai layanan. Default lokal adalah `./accounts.json`; Docker Compose memakai `./data/accounts.json`. Jika kesalahan berasal dari upstream, gunakan detail kesalahan yang dikembalikan untuk menyelidiki ketersediaan layanan.

</details>

<details>
<summary>Mengapa saya mendapat 400? Bagaimana cara mengirim gambar dan alat?</summary>

Periksa JSON `error` pada klien dan log dengan `X-Request-ID` yang sama. Penyebab umum meliputi:

- `tool_choice="required"`, pemilihan alat secara paksa, atau parameter lain yang tidak didukung.
- URL gambar jarak jauh, ID berkas, atau masukan audio. Gambar harus memakai format yang didukung dalam URL data base64.
- Alat yang dihosting dan belum diimplementasikan seperti `file_search`, atau kolom `include` yang tidak didukung.
- JSON tidak valid, masukan alat kustom dengan format salah, atau konfigurasi JSON Schema tidak valid.

Responses mendukung gambar dan validasi keluaran JSON Schema melalui `text.format`. Lihat formatnya di [referensi API (bahasa Inggris)](../en/api-reference.md). Jika log menunjukkan `stage="upstream"`, selidiki pesan kesalahan upstream dan model yang dipilih.

</details>

<details>
<summary>Bagaimana cara menyelidiki permintaan tertentu yang gagal?</summary>

Diagnostik permintaan tersedia pada level log default `info`. Untuk deployment Docker:

```bash
docker compose logs --since 10m --timestamps -f cursor-gateway

# Replace the placeholder with the X-Request-ID response header value
docker compose logs --since 30m cursor-gateway 2>&1 | grep -F 'REPLACE_WITH_REQUEST_ID'
```

Pesan log berupa JSON satu baris. Peristiwa dalam satu permintaan memiliki `request_id` yang sama:

| Peristiwa | Yang perlu diperiksa |
| --- | --- |
| `request_started` / `request_parsed` | Jalur, klien, dan ringkasan parameter permintaan |
| `generation_started` | Label akun, model upstream sebenarnya, jumlah item riwayat, dan jumlah alat |
| `compatibility_notice` | Informasi pemetaan kompatibilitas; peristiwa ini saja tidak menandakan kegagalan |
| `request_error` | `stage`, `error_status`, `error_param`, `error_message`, dan `error_code` upstream |
| `request_finished` | Status HTTP, `outcome`, durasi, dan jumlah byte |

Kesalahan setelah SSE dimulai tetap dapat memiliki status HTTP 200. Periksa juga kesalahan stream dan `outcome` dalam log. Pemetaan kesalahan upstream yang umum:

| Kesalahan upstream | Status HTTP |
| --- | --- |
| `resource_exhausted` | `429` |
| `unauthenticated` / `permission_denied` | `401` / `403` |
| `invalid_argument` / `not_found` | `400` / `404` |
| `unimplemented` / `unavailable` / `deadline_exceeded` | `501` / `503` / `504` |
| Kesalahan protokol atau upstream lainnya | `502` |

Ringkasan log tidak menyertakan prompt, isi pesan, argumen / keluaran alat, nilai metadata, cookie, maupun header autentikasi. Kredensial yang dikenal dalam teks kesalahan disamarkan. Menonaktifkan `CURSOR_DIRECT_LOG_REQUESTS` hanya menonaktifkan log permintaan rutin.

</details>

<details>
<summary>Mengapa previous_response_id berhenti berfungsi setelah restart?</summary>

Riwayat respons disimpan dalam memori proses, dengan default satu jam, 256 entri, dan 128 MiB. Restart menghapusnya, dan riwayat ini tidak dibagikan antarproses atau instance. Jika respons tidak ditemukan dalam cache, layanan mengembalikan `404`.

Untuk riwayat yang dikelola klien, gunakan `store=false` lalu kirim masukan lengkap, keluaran sebelumnya, dan hasil alat. Checkpoint pemadatan bergantung pada `compaction.key`; menyimpan kunci yang sama secara persisten memungkinkan dekode setelah restart. Checkpoint dan penyimpanan berdasarkan ID respons adalah mekanisme terpisah.

Saat memakai `previous_response_id`, sertakan kembali `instructions` yang diperlukan dan definisi alat pada setiap giliran.

</details>

<a id="compatibility"></a>

## 📋 Kompatibilitas

| Kemampuan | Implementasi dan batasan |
| --- | --- |
| Protokol API | Chat Completions, Responses, dan Models; tanpa Anthropic `/v1/messages`, Embeddings, atau antarmuka pengelolaan |
| Gambar | Kedua API generasi menerima gambar PNG / JPEG / WebP / GIF yang disisipkan, maksimal 16 MiB per gambar dan 32 gambar per permintaan, dengan tetap mengikuti batas ukuran body total; URL jarak jauh, ID berkas, dan audio tidak didukung |
| Alat | Klien menjalankan alat fungsi / kustom. `tool_choice` menerima `auto` / `none`. Mengaktifkan `parallel_tool_calls` mengumpulkan panggilan yang datang dalam batch yang sama; apakah panggilan paralel dihasilkan bergantung pada model upstream |
| Keluaran terstruktur | Responses memberi instruksi kepada model dan memvalidasi jawaban akhir, tanpa decoding terkendala secara native. `response_format` pada Chat Completions tidak berpengaruh |
| Kontrol sampling dan penalaran | Parameter seperti `temperature`, `top_p`, dan batas token tidak sepenuhnya ditegakkan oleh upstream. Chat Completions hanya mendukung `n=1` |
| Status penalaran | Menampilkan ringkasan penalaran yang terlihat; tidak menghasilkan atau mendekripsi `reasoning.encrypted_content` OpenAI |
| Perhitungan token | Chat Completions melaporkan nol token prompt. Token masukan Responses adalah perkiraan yang ditandai `estimated=true`. Hitungan upstream dipetakan ke token keluaran; rincian tagihan cache / penalaran terpisah tidak tersedia |
| Pencarian web | Responses menggunakan pencarian bawaan Cursor, tanpa opsi lokasi atau filter domain OpenAI |
| Transport dan fitur yang dihosting | HTTP/SSE; tanpa Responses WebSocket, `background=true`, `conversation` / `prompt` yang dihosting, atau alat bawaan lain yang dihosting. Putusnya koneksi klien membatalkan permintaan upstream |

Secara default, instruksi sistem / developer dikirim sebagai pesan riwayat dengan label sumber; pengaruhnya tetap bergantung pada prompt upstream. Bahkan dengan `CURSOR_ALLOWED_NATIVE_TOOLS=*`, gateway tidak menjalankan perintah shell, operasi berkas, atau patch milik klien di host-nya.

Lihat [referensi API (bahasa Inggris)](../en/api-reference.md) untuk perilaku parameter terperinci dan [panduan Codex CLI (bahasa Inggris)](../en/codex-usage.md) untuk konfigurasi klien.

<a id="development"></a>

## 🧪 Pengembangan dan verifikasi

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

Pengujian otomatis menggunakan kredensial fiktif dan upstream simulasi lokal. Cakupannya meliputi pembaruan akun, validasi permintaan, JSON / SSE, siklus alat, riwayat Responses, pembatalan, serta transport HTTP/2 / protobuf melalui koneksi TCP lokal. Tidak diperlukan kredensial nyata, inferensi berbayar, atau Codex CLI.

<details>
<summary>🛠️ Pembuatan kode protokol</summary>

Setelah mengubah definisi protokol, hasilkan ulang kelas Python dengan `protoc 36.1`:

```bash
.venv/bin/python scripts/generate_proto.py
```

</details>

<details>
<summary>📂 Struktur proyek</summary>

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

## 🤝 Berkontribusi

Gunakan Issues untuk bug yang dapat direproduksi dan diskusi fitur, serta baca [panduan kontribusi (bahasa Mandarin / Inggris)](../../CONTRIBUTING.md) sebelum mengirim pull request.
Jaga agar README dalam delapan bahasa dan panduan Mandarin serta Inggris tetap selaras saat mengubah perilaku, konfigurasi, atau contoh, dan patuhi [kode etik (bahasa Mandarin / Inggris)](../../CODE_OF_CONDUCT.md).
Laporkan kerentanan secara privat sesuai [kebijakan keamanan (bahasa Mandarin / Inggris)](../../SECURITY.md). Lihat perubahan versi di [catatan perubahan (bahasa Inggris)](../../CHANGELOG.md).

<a id="credits"></a>

## 🙏 Kredit dan lisensi

- [AstroQore/cursor2api](https://github.com/AstroQore/cursor2api): implementasi asli yang menjadi sumber port proyek ini, termasuk pemetaan protokol, format akun, dan katalog model cadangan.
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi): sumber provider Cursor / `agent.proto` yang disebut oleh proyek asli.
- [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway): referensi tata letak README dan struktur dokumentasi ini.

Proyek ini menggunakan lisensi **[AGPL-3.0-only](../../LICENSE)**. Lihat atribusi lengkap di [NOTICE](../../NOTICE).

Saat mendistribusikan atau mengoperasikan versi modifikasi untuk orang lain, patuhi persyaratan AGPL mengenai penyediaan kode sumber terkait. Sediakan seluruh kode sumber versi yang sedang dijalankan melalui repositori atau distribusi sumber, dan berikan akses yang jelas ke kode sumber bagi pengguna jaringan. Build kontainer dapat mencatat lokasi sumber publik dengan `--build-arg SOURCE_URL=PUBLIC_SOURCE_URL`.
