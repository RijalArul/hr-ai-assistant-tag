# Desain UI Layer Phase 5 HR.ai

Dokumen ini menjelaskan desain UI Layer untuk Phase 5 dalam Bahasa Indonesia.

HR.ai adalah AI service, bukan UI product. Karena itu, strategi UI dibagi menjadi tiga track yang berjalan paralel sesuai dengan siapa yang akan menggunakannya.

Dokumen ini adalah rencana implementasi phase berikutnya, bukan deskripsi fitur yang sudah aktif.

## Tujuan Phase 5 (UI)

Phase 5 UI menjawab satu pertanyaan utama:
"Bagaimana company customer bisa mulai menggunakan HR.ai tanpa harus membangun UI dari nol?"

Ada tiga jalur jawaban:

- **Track 1:** HR Admin butuh dashboard untuk manage actions, conversations, dan rules
- **Track 2:** Employee butuh chat interface yang siap pakai sebagai referensi atau white-label
- **Track 3:** IT Admin butuh tahu bagaimana menghubungkan HR.ai ke open source chat UI yang sudah ada

## Posisi Dalam Arsitektur

```text
Phase 1-4 -> backend AI service (sudah selesai)
Phase 5   -> UI layer di atas Phase 4 API
```

UI layer sepenuhnya berdiri di atas Phase 4 conversations API. Tidak ada business logic baru di UI.

```text
HR Admin   -> HR Dashboard (Next.js)
Employee   -> Sample Chat UI (Next.js)
IT Team    -> Open source LLM UI + OpenAI-compatible endpoint (Phase 6)
```

## Apps Web Yang Sudah Ada

Repository sudah punya scaffolding `apps/web/` dengan:
- Next.js 15.3.9 (App Router)
- React 19
- TypeScript 5
- Netlify deployment config

Yang belum ada:
- styling framework
- component library
- state management
- halaman apapun selain placeholder home

Phase 5 membangun di atas scaffolding yang sudah ada ini.

---

## Track 1: HR Admin Dashboard

### Tujuan

Dashboard untuk HR Admin mengelola action queue, mereview conversations, dan mengubah status rule. Ini adalah surface utama yang dibutuhkan company customer untuk merasakan value Phase 2 (action engine).

### Pages

**`/hr` — Dashboard Home**

Halaman overview yang menampilkan:
- card statistik: total actions pending, active conversations, escalated cases hari ini
- activity feed terbaru: 10 event terakhir lintas conversations dan actions
- quick links ke action queue dan conversations

**`/hr/actions` — Action Queue**

Tampilan tabel semua actions yang perlu di-review oleh HR Admin.

Fitur:
- filter berdasarkan: status, type, priority, sensitivity
- sort berdasarkan: created_at, priority
- inline status update tanpa pindah halaman
- detail drawer: klik action untuk lihat full context dan conversation history
- execute button untuk action yang sudah ready

API yang dipakai:
- `GET /api/v1/actions` untuk list
- `PATCH /api/v1/actions/{id}` untuk update status
- `POST /api/v1/actions/{id}/execute` untuk eksekusi

**`/hr/conversations` — Conversation Monitor**

Daftar semua conversations di company dengan status badges.

Fitur:
- filter berdasarkan: status (active, resolved, escalated, closed), sensitivity
- klik untuk lihat full message history
- tombol update status: escalate atau close
- badge visual untuk sensitivity level

API yang dipakai:
- `GET /api/v1/conversations` untuk list (Phase 4)
- `GET /api/v1/conversations/{id}` untuk detail
- `PATCH /api/v1/conversations/{id}` untuk update status

**`/hr/rules` — Rule Management**

Daftar semua rules yang aktif di company dengan toggle enabled/disabled.

Catatan:
- HR Admin hanya bisa toggle `is_enabled`
- create, delete, dan full edit hanya untuk IT Admin (bukan di dashboard ini)

API yang dipakai:
- `GET /api/v1/rules` untuk list
- `PATCH /api/v1/rules/{id}` untuk toggle

**`/hr/settings` — Settings**

Halaman minimal untuk pengaturan notifikasi dan preferensi tampilan.

### Tech Stack HR Dashboard

```text
framework    : Next.js 15 (App Router, sudah ada)
styling      : Tailwind CSS + shadcn/ui
state        : TanStack Query (React Query) untuk server state
auth         : JWT token di cookies httpOnly, route guard via middleware.ts
tables       : TanStack Table untuk action queue dan conversation list
charts       : Recharts untuk stats cards
real-time    : polling 30 detik (MVP), WebSocket (future)
```

### Struktur File HR Dashboard

```text
apps/web/src/
  app/
    hr/
      layout.tsx             # HR Dashboard layout dengan sidebar
      page.tsx               # /hr — overview
      actions/
        page.tsx             # /hr/actions — action queue
        [id]/
          page.tsx           # /hr/actions/{id} — detail drawer (atau route terpisah)
      conversations/
        page.tsx             # /hr/conversations — list
        [id]/
          page.tsx           # /hr/conversations/{id} — message history
      rules/
        page.tsx             # /hr/rules — toggle list
      settings/
        page.tsx             # /hr/settings
  components/
    hr/
      ActionTable.tsx        # tabel actions dengan filter + sort
      ActionDetailDrawer.tsx # drawer detail action + conversation context
      ConversationList.tsx   # list conversations dengan status badges
      RuleToggleList.tsx     # list rules dengan toggle
      StatsCard.tsx          # stat overview card
      ActivityFeed.tsx       # recent activity
      SensitivityBadge.tsx   # badge visual untuk sensitivity level
      StatusBadge.tsx        # badge untuk status actions/conversations
  lib/
    api.ts                   # fetch wrapper dengan auth header injection
    hooks/
      useActions.ts          # TanStack Query hooks untuk actions API
      useConversations.ts    # TanStack Query hooks untuk conversations API
      useRules.ts            # TanStack Query hooks untuk rules API
    auth.ts                  # token read/write dari cookies
  middleware.ts              # Next.js route guard untuk /hr
```

---

## Track 2: Sample Employee Chat UI

### Tujuan

Reference implementation chat interface yang bisa langsung dipakai untuk demo atau di-white-label oleh company customer. Ini bukan produk utama HR.ai, tetapi diperlukan untuk menunjukkan end-to-end flow ke juri hackathon atau investor.

### Fitur Core

```text
- conversation list sidebar (riwayat chat sebelumnya)
- chat window dengan message history
- input field + send button
- file attachment upload (PDF, gambar)
- notification inline saat action dibuat otomatis
- visual indicator saat conversation di-escalate
- bahasa UI bisa di-toggle antara ID dan EN
```

### Pages

**`/chat` — Main Chat Interface**

Layout dua kolom:
- sidebar kiri: daftar conversations, tombol new conversation
- area utama: message history, input field, status bar

**`/chat/login` — Employee Login**

Login sederhana dengan email. JWT token disimpan di cookie httpOnly setelah berhasil login.

### Tech Stack Sample Chat UI

```text
framework    : Next.js 15 (App Router, share dengan HR Dashboard)
styling      : Tailwind CSS + shadcn/ui (share)
state        : TanStack Query
auth         : JWT cookie, shared middleware
streaming    : SSE (Server-Sent Events) jika backend support, fallback ke polling
file upload  : native file input dengan progress indicator
```

### Struktur File Sample Chat UI

```text
apps/web/src/
  app/
    chat/
      layout.tsx              # layout chat dengan sidebar
      page.tsx                # redirect ke conversation terbaru atau new
      [id]/
        page.tsx              # /chat/{conversation_id}
      login/
        page.tsx              # employee login form
  components/
    chat/
      ConversationSidebar.tsx # list conversations + new button
      MessageList.tsx         # scroll area dengan message bubbles
      MessageBubble.tsx       # bubble user/assistant
      MessageInput.tsx        # input field + send + attach
      AttachmentPreview.tsx   # preview file sebelum dikirim
      ActionNotification.tsx  # inline notif "Action created: ..."
      TypingIndicator.tsx     # loading state saat AI sedang generate
  lib/
    hooks/
      useChat.ts              # hook untuk send message + stream response
```

---

## Track 3: Open Source LLM UI Integration

### Tujuan

Menunjukkan bahwa HR.ai API bisa dikonsumsi dari open source chatbot UI yang sudah ada, tanpa perlu membangun UI baru dari nol. Ini adalah positioning HR.ai sebagai pure AI service.

Strategi ini relevan untuk IT team di company customer yang sudah punya atau ingin menggunakan open source chat platform di dalam infrastruktur mereka.

Detail implementasi OpenAI-compatible endpoint ada di dokumen terpisah:
- `docs/architecture/phase-6-openai-compat-id.md`

### Open Source UI yang Direkomendasikan

Tiga opsi yang disarankan untuk testing dan referensi:

**LibreChat (35k+ stars, MIT)**

Cocok untuk: enterprise, multi-user dengan OAuth2, fitur lengkap.

Cara konek ke HR.ai:
- set custom endpoint di `librechat.yaml`
- arahkan ke `https://api.hr-ai.io/v1/chat/completions`
- set Authorization header dengan HR.ai JWT token

**Open WebUI (AGPL-3.0)**

Cocok untuk: company yang butuh offline / on-premise.

Cara konek ke HR.ai:
- set OPENAI_API_BASE_URL ke HR.ai API endpoint
- set OPENAI_API_KEY ke HR.ai JWT token
- fully offline, zero telemetry

**AnythingLLM (54k+ stars, MIT)**

Cocok untuk: company yang butuh document ingestion + chat dalam satu platform.

Cara konek ke HR.ai:
- add custom LLM provider via AnythingLLM settings
- arahkan base URL ke HR.ai API

### Docker Compose Template

Untuk mempermudah company customer mencoba integrasi, kita sediakan template Docker Compose siap pakai.

Lokasi di repo: `infra/examples/librechat-compose/docker-compose.yml`

Template ini menjalankan:
- HR.ai FastAPI backend
- LibreChat sebagai chat frontend
- PostgreSQL
- Redis

Company customer tinggal mengisi environment variables dan jalankan `docker compose up`.

### Integration Guide

Untuk setiap open source UI, kita sediakan quick-start guide di:

```text
docs/integration/
  librechat.md       # setup LibreChat + HR.ai
  open-webui.md      # setup Open WebUI + HR.ai
  anything-llm.md    # setup AnythingLLM + HR.ai
```

---

## API Integration Map Lengkap

Tabel mapping antara UI page dan API endpoint yang dipanggil:

| Page / Komponen | Method | Endpoint | Role |
|---|---|---|---|
| HR Dashboard Home | GET | /api/v1/actions | hr_admin |
| HR Dashboard Home | GET | /api/v1/conversations | hr_admin |
| Action Queue | GET | /api/v1/actions | hr_admin |
| Action Queue | PATCH | /api/v1/actions/{id} | hr_admin |
| Action Detail | POST | /api/v1/actions/{id}/execute | hr_admin |
| Conversation List | GET | /api/v1/conversations | hr_admin |
| Conversation Detail | GET | /api/v1/conversations/{id} | hr_admin |
| Conversation Detail | PATCH | /api/v1/conversations/{id} | hr_admin |
| Rule List | GET | /api/v1/rules | hr_admin |
| Rule Toggle | PATCH | /api/v1/rules/{id} | hr_admin |
| Chat: new conversation | POST | /api/v1/conversations | employee |
| Chat: send message | POST | /api/v1/conversations/{id}/messages | employee |
| Chat: load history | GET | /api/v1/conversations/{id} | employee |
| Chat: file upload | POST | /api/v1/conversations/{id}/messages | employee |
| Login | POST | /api/v1/auth/login | — |

---

## Dependencies Baru Yang Perlu Di-install

Di `apps/web/`:

```bash
npm install tailwindcss @tailwindcss/typography postcss autoprefixer
npm install @shadcn/ui
npm install @tanstack/react-query @tanstack/react-table
npm install recharts
npm install lucide-react
npm install js-cookie
npm install @types/js-cookie -D
```

---

## Shared Conventions

Aturan yang berlaku untuk semua komponen UI:

**Auth:**
- JWT token disimpan di cookie httpOnly dengan flag Secure dan SameSite=Strict
- tidak ada token di localStorage atau sessionStorage
- middleware Next.js redirect ke login jika token tidak valid atau expired

**Error Handling:**
- 401 redirect ke halaman login
- 403 tampilkan pesan "Akses tidak diizinkan"
- 404 tampilkan empty state yang informatif
- 5xx tampilkan error toast + retry button

**Loading States:**
- skeleton loader untuk list dan tabel
- spinner untuk action yang sedang diproses
- optimistic update untuk toggle status

**Environment Variables:**

```text
NEXT_PUBLIC_API_URL=https://api.hr-ai.io
```

---

## Cara Memahami Track Ini Secara Sederhana

Kalau disederhanakan, tiga track ini melayani tiga tipe pengguna berbeda:

1. HR Admin butuh antarmuka untuk manage pekerjaan timnya → Track 1
2. Employee butuh antarmuka chat yang simple → Track 2
3. IT team butuh tahu cara koneksi ke chat platform yang sudah ada → Track 3

Karena HR.ai adalah AI service, Track 3 adalah yang paling strategis:
- company customer tidak harus pakai UI buatan HR.ai
- mereka bisa pakai tool favorit mereka
- HR.ai tetap menjadi intelligence layer di belakangnya
