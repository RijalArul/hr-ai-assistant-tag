# Desain OpenAI-Compatible Endpoint Phase 6 HR.ai

Dokumen ini menjelaskan desain Phase 6 dalam Bahasa Indonesia: endpoint OpenAI-compatible yang memungkinkan open source chatbot UI untuk berkomunikasi langsung dengan HR.ai API.

Dokumen ini adalah rencana implementasi, bukan deskripsi fitur yang sudah aktif.

## Tujuan Phase 6

Phase 6 menjawab satu pertanyaan dari IT Admin di company customer:
"Apakah karyawan kami bisa menggunakan LibreChat atau chatbot UI favorit kami untuk terhubung ke HR.ai?"

Jawabannya: ya, dengan menambahkan satu endpoint OpenAI-compatible wrapper di atas HR.ai conversations API.

Hampir semua open source chatbot UI di 2025-2026 mendukung custom backend melalui format OpenAI API. Jadi jika HR.ai mengekspos endpoint yang mengikuti format itu, company customer bisa menghubungkan UI apapun tanpa modifikasi.

## Posisi Dalam Arsitektur

```text
Phase 1-4 -> core backend (auth, action engine, orchestration, conversations)
Phase 5   -> guardrail layer + UI layer (HR Dashboard + Sample Chat UI)
Phase 6   -> OpenAI-compatible wrapper untuk headless integration
```

Phase 6 tidak menambah business logic baru. Ia hanya menerjemahkan format request/response antara OpenAI API standard dan HR.ai conversations API.

## Kenapa Format OpenAI

Alasan memilih OpenAI API format sebagai standard:

- mayoritas open source chat UI (LibreChat, Open WebUI, AnythingLLM, LobeChat) menggunakan OpenAI format sebagai protokol default
- format ini sudah menjadi de-facto standard untuk LLM API communication
- tidak ada dependency ke OpenAI product — ini hanya soal request/response format
- sekali endpoint ini ada, HR.ai bisa dikonsumsi dari puluhan UI berbeda tanpa perubahan apapun

## Endpoint Baru

```text
POST /v1/chat/completions
```

Endpoint ini mengikuti spesifikasi OpenAI Chat Completions API secara formal, tetapi memproses request melalui HR.ai orchestration pipeline, bukan melalui OpenAI.

Base URL untuk endpoint ini:

```text
https://api.hr-ai.io/v1/chat/completions
```

Catatan: URL path `/v1/` sengaja berbeda dari API internal HR.ai yang menggunakan `/api/v1/`. Ini supaya konsumen open source UI bisa langsung menggunakan URL sebagai custom API base.

## Format Request

Format yang diterima mengikuti OpenAI Chat Completions:

```json
{
  "model": "hr-ai",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "Berapa sisa cuti saya?" },
    { "role": "assistant", "content": "..." },
    { "role": "user", "content": "Bagaimana aturan carry-over-nya?" }
  ],
  "stream": false
}
```

Field yang dipakai:

| Field | Behavior di HR.ai |
|---|---|
| `model` | Diabaikan. HR.ai selalu menggunakan orchestrator internal. |
| `messages` | Dipakai untuk menentukan message terbaru dan conversation context. |
| `messages[].role` | `user` dan `assistant` dipetakan ke HR.ai message roles. `system` diabaikan. |
| `messages[].content` | Pesan terakhir dengan `role: user` dikirim ke orchestrator. |
| `stream` | `false` untuk response biasa, `true` untuk SSE streaming (opsional). |

## Mapping Ke HR.ai Conversations API

Wrapper ini menerjemahkan request ke dalam flow conversations API:

```text
request masuk ke /v1/chat/completions
  -> baca Authorization header untuk JWT session
  -> cari conversation_id dari header X-HR-Conversation-Id (opsional)
  -> jika tidak ada conversation_id, buat conversation baru via POST /conversations
  -> kirim message terakhir dari messages[] via POST /conversations/{id}/messages
  -> terima response dari orchestrator
  -> format ulang ke OpenAI response format
  -> kembalikan ke UI
```

Agar conversation bisa dilanjutkan lintas request:
- response menyertakan header `X-HR-Conversation-Id`
- UI bisa menyimpan conversation_id ini dan mengirimkannya kembali di request berikutnya
- jika UI tidak mengirim header ini, setiap request akan membuat conversation baru

## Format Response

Response mengikuti format OpenAI Chat Completions:

```json
{
  "id": "chatcmpl-conv-40000000-0000-0000-0000-000000000001",
  "object": "chat.completion",
  "created": 1714723200,
  "model": "hr-ai",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Sisa cuti kamu saat ini adalah 8 hari dari total 12 hari untuk tahun 2026."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": null,
    "completion_tokens": null,
    "total_tokens": null
  }
}
```

Catatan:
- `id` menggunakan prefix `chatcmpl-conv-` diikuti conversation_id dari HR.ai
- `model` selalu dikembalikan sebagai `hr-ai`
- `usage` dikembalikan sebagai null karena HR.ai tidak menghitung token di layer ini
- header response menyertakan `X-HR-Conversation-Id` untuk session continuity

## Streaming Support

Jika request menyertakan `"stream": true`, response dikirim sebagai Server-Sent Events (SSE) mengikuti format OpenAI streaming:

```text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":"Sisa"},"index":0}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":" cuti"},"index":0}]}

data: [DONE]
```

Streaming membutuhkan orchestrator mengirimkan token secara incremental. Ini tergantung apakah MiniMax dan Gemini mendukung streaming response. Jika belum, streaming bisa di-fake dengan buffer dan flush setelah response selesai.

## Authentication

Endpoint ini menggunakan mekanisme auth yang sama dengan HR.ai API lainnya: JWT bearer token.

```text
Authorization: Bearer <hr-ai-jwt-token>
```

Cara mendapatkan token: employee login via `POST /api/v1/auth/login` seperti biasa.

Cara konfigurasi di open source UI: masukkan token ke field "API Key" di settings UI. Token ini akan dikirimkan sebagai `Authorization: Bearer` header di setiap request.

Tidak ada perubahan pada JWT format atau session scoping yang sudah ada.

## Batasan Yang Disengaja

Beberapa hal yang sengaja tidak didukung di endpoint ini:

- `function_calling` / `tools`: tidak didukung karena HR.ai menggunakan agent routing internal
- `logprobs`: tidak tersedia
- `temperature`, `top_p`, `max_tokens`: diabaikan, HR.ai menggunakan parameter internal
- multi-modal via base64 di `content`: file attachment tetap harus menggunakan flow attachment Phase 4

Batasan ini harus didokumentasikan di integration guide supaya company customer tahu apa yang bisa dan tidak bisa digunakan dari UI mereka.

## File Baru Yang Diperlukan

```text
apps/api/app/api/routes/openai_compat.py   # endpoint /v1/chat/completions
apps/api/app/services/openai_compat.py     # mapping logic antara format
apps/api/app/models/openai_compat.py       # Pydantic models untuk request/response OpenAI format
```

Endpoint ini didaftarkan di router utama dengan prefix berbeda dari API internal:

```python
# main.py
app.include_router(openai_compat_router, prefix="/v1")
app.include_router(api_router, prefix="/api/v1")
```

## Contoh Konfigurasi Per Open Source UI

### LibreChat

Di `librechat.yaml`:

```yaml
endpoints:
  custom:
    - name: "HR.ai"
      apiKey: "${HR_AI_JWT_TOKEN}"
      baseURL: "https://api.hr-ai.io/v1"
      models:
        default: ["hr-ai"]
        fetch: false
      titleConvo: true
      titleModel: "hr-ai"
```

### Open WebUI

Di environment variables:

```bash
OPENAI_API_BASE_URL=https://api.hr-ai.io/v1
OPENAI_API_KEY=<hr-ai-jwt-token>
```

### AnythingLLM

Di LLM Provider settings:
- Provider: Generic OpenAI
- Base URL: `https://api.hr-ai.io/v1`
- API Key: JWT token dari HR.ai login

---

## Guardrail Di Endpoint Ini

Endpoint OpenAI-compat tetap berjalan di atas semua guardrail Phase 5:

- rate limit: berlaku, berbagi counter dengan flow conversations biasa
- injection detection: berlaku, message diekstrak dari `messages[]` sebelum diproses
- PII scan: berlaku, response di-scan sebelum di-format ke OpenAI format
- hallucination check: berlaku, sama dengan flow normal

Artinya tidak ada perbedaan keamanan antara menggunakan UI bawaan HR.ai atau open source UI melalui endpoint ini.

---

## Cara Memahami Phase 6 Secara Sederhana

Kalau disederhanakan, Phase 6 bekerja seperti ini:

1. company customer install LibreChat atau Open WebUI di server mereka
2. mereka arahkan URL dan API key ke HR.ai endpoint
3. karyawan buka chat UI yang familiar
4. di balik layar, setiap pesan berjalan melalui orchestrator HR.ai, agents, guardrail
5. response kembali dalam format yang UI tersebut harapkan
6. company customer tidak perlu membangun UI apapun

Inti Phase 6 adalah:
- HR.ai tidak harus menjadi satu-satunya UI provider
- company customer bisa membawa UI favorit mereka
- intelligence dan safety tetap berjalan di HR.ai layer
- integrasi cukup dengan dua konfigurasi di sisi UI
