# Desain Guardrail Agent Phase 5 HR.ai

Dokumen ini menjelaskan desain Guardrail Agent untuk Phase 5 dalam Bahasa Indonesia.

Guardrail Agent adalah safety layer baru yang berjalan sebagai interceptor di orchestration pipeline, di dua titik: sebelum message masuk ke orchestrator (Input Guard) dan setelah response dibentuk oleh agents (Output Guard).

Dokumen ini adalah rencana implementasi phase berikutnya, bukan deskripsi fitur yang sudah aktif sekarang.

## Tujuan Phase 5

Phase 5 adalah safety dan abuse prevention layer.

Fase ini menjawab dua pertanyaan sekaligus:
- "apakah input dari user aman untuk diproses?"
- "apakah output dari AI aman untuk dikirim ke user?"

Dengan kata lain, Phase 5 memastikan:
- prompt injection tidak bisa memanipulasi behavior AI
- rate limit mencegah penyalahgunaan resource
- PII tidak bocor dari output AI ke user yang salah
- angka dan klaim yang dihasilkan AI memiliki dasar evidence yang bisa diverifikasi
- tone response tetap profesional dan netral

## Posisi Dalam Arsitektur

Guardrail Agent bukan agent yang berdiri sendiri. Ia berjalan sebagai middleware layer di dalam orchestration pipeline:

```text
Phase 1 -> trusted session dan role boundary
Phase 2 -> action contracts dan delivery
Phase 3 -> agent orchestration (HR Data, Company, File)
Phase 4 -> conversations API
Phase 5 -> guardrail layer (Input Guard + Output Guard)
```

Posisi Guardrail dalam satu request:

```text
user message
  -> [INPUT GUARD]
      -> rate limit check
      -> injection detection
      -> input sanitization
      -> content abuse detection
  -> orchestrator (Phase 3 + 4)
      -> agents (hr-data, company, file)
  -> [OUTPUT GUARD]
      -> PII scan
      -> hallucination check
      -> tone validation
  -> response ke user
```

## Kenapa Ini Diperlukan

Kondisi saat ini di repo punya beberapa gap keamanan yang harus ditutup sebelum production:

**Gap di sisi input:**
- tidak ada rate limit per user atau per company
- tidak ada deteksi prompt injection
- input sanitization terbatas pada panjang karakter saja

**Gap di sisi output:**
- tidak ada scanning PII di response AI
- tidak ada validasi bahwa angka yang dikutip AI memang berasal dari data yang di-query
- tidak ada enforcement tone NVC pada output

**Kenapa ini penting untuk B2B:**
- company customer punya kewajiban GDPR/PDPA untuk melindungi data karyawan
- satu kebocoran PII bisa merusak reputasi dan memicu audit
- halusinasi angka gaji atau sisa cuti bisa menimbulkan konflik antara karyawan dan HR

## Prinsip Utama

Guardrail Agent dirancang dengan prinsip berikut:

- jangan expose alasan penolakan ke user (hindari membantu attacker iterate)
- jangan block semua pesan dengan heuristic yang terlalu agresif
- selalu ada fallback response yang aman, bukan HTTP error mentah
- rate limit berbasis Redis yang sudah ada di stack
- evidence-based validation untuk angka, bukan validasi LLM ulang
- konfigurasi per company untuk override threshold

## Komponen Utama

Ada dua komponen besar di Phase 5: Input Guard dan Output Guard.

---

## Input Guard

Input Guard berjalan sebelum pesan masuk ke orchestrator. Fungsinya memfilter dan memvalidasi semua input dari user.

### 1. Rate Limiter

Rate limit diimplementasikan sebagai Redis sliding window counter.

Key pattern yang dipakai:

```text
rate:{company_id}:{employee_id}:{action_type}
```

Tabel limit default:

| Action Type | Limit | Window | Response jika melebihi |
|---|---|---|---|
| messages | 30 | per jam | 429 + cooldown notice |
| conversations_new | 10 | per hari | 429 + cooldown notice |
| file_uploads | 5 | per jam | 429 + file limit notice |
| auth_failed | 5 | per 15 menit | temporary lockout |

Catatan:
- limit default bisa di-override per company via `guardrail_config`
- company enterprise bisa punya batas lebih tinggi sesuai tier

### 2. Prompt Injection Detector

Deteksi prompt injection berjalan dalam empat layer yang berurutan.

**Layer 1 — Pattern Matching:**

Regex-based detection untuk pola injeksi yang umum:

```text
ignore previous instructions
forget what i said
you are now
pretend to be
act as if you have no restrictions
system prompt:
<system>
[INST]
base64 encoded instructions
encoded in hex
```

Pola ini di-check tanpa case sensitivity dan termasuk variasi dengan spasi, tanda baca, dan karakter unicode.

**Layer 2 — Input Sanitization:**

Pembersihan karakter berbahaya sebelum message diproses:
- strip control characters (0x00-0x1F kecuali newline dan tab)
- normalize unicode ke NFC form
- detect zero-width characters yang sering dipakai sebagai steganography
- detect homoglyph substitution (huruf yang mirip tapi beda unicode)

**Layer 3 — Context Boundary Enforcement:**

System prompt di-hardcode dan di-wrap dengan delimiter yang jelas. User message di-wrap dalam block terpisah sehingga model bisa distinguish keduanya:

```text
[SYSTEM_CONTEXT]
Kamu adalah HR AI assistant yang bekerja untuk {company_name}...
[END_SYSTEM_CONTEXT]

[USER_MESSAGE]
{user_message}
[END_USER_MESSAGE]
```

Delimiter ini tidak diekspos ke user dan bisa dikustomisasi per deployment.

**Layer 4 — Semantic Injection Classifier (opsional, P2):**

Lightweight binary classifier yang score apakah input adalah legitimate HR question atau manipulation attempt. Menggunakan embedding similarity ke contoh-contoh injeksi yang diketahui.

Kalau score melebihi threshold, message diblok dengan respons:

```text
Maaf, saya hanya bisa membantu pertanyaan terkait HR. Silakan coba kembali.
```

### 3. Content Abuse Detector

Abuse detection berbasis pola penggunaan, bukan konten.

Yang dideteksi:
- repetitive messages: pesan yang sama atau sangat mirip dikirim lebih dari 3 kali dalam 5 menit
- gibberish: string dengan entropy yang tidak wajar (spam karakter random)
- topic drift yang tiba-tiba: conversation yang mendadak shift dari HR ke topik yang sama sekali tidak relevan

Eskalasi jika terdeteksi:
- peringatan pertama: response informatif tanpa penalti
- peringatan ketiga: temporary cooldown 30 menit
- cooldown ketiga dalam 24 jam: notifikasi ke HR Admin

---

## Output Guard

Output Guard berjalan setelah response dibentuk oleh agents, sebelum response dikirim ke user.

### 1. PII Scanner

PII Scanner men-scan setiap response untuk mendeteksi dan mask data sensitif yang seharusnya tidak terekspos.

Pola PII yang di-scan:

```text
NIK: 16 digit berurutan
NPWP: format XX.XXX.XXX.X-XXX.XXX
BPJS: format yang diketahui
Nomor rekening bank: 10-16 digit
Nomor telepon: +62 atau 08xx
Email: format valid tapi bukan milik session user sendiri
Gaji orang lain: salary amount dengan nama orang yang berbeda dari session
```

Context-aware masking:

- kalau employee tanya gaji dirinya sendiri → tampilkan
- kalau response accidentally mention gaji orang lain → MASK
- kalau response mention NIK orang lain → MASK

Format masking:

```text
"Rp 15.000.000" → "Rp **.****.***"
"0812-XXXX-1234" → "****-****-1234"
"32XXXXXXXXXXXXXX" → "32****..."
```

Aturan utama: employee hanya boleh melihat data dirinya sendiri. Cross-employee data di-mask bahkan jika AI menghasilkannya secara tidak sengaja.

### 2. Hallucination Checker

Pendekatan: evidence-based validation, bukan LLM re-check.

Setiap angka dan klaim dalam response harus traceable ke evidence yang dikembalikan oleh agents.

**Numeric Validation:**

Angka salary, sisa cuti, dan attendance count di-cross-check dengan data yang dikembalikan HR Data Agent.

Logika:

```text
extracted_numbers = parse_numbers(response)
evidence_numbers  = flatten(agent_results.hr_data)

for num in extracted_numbers:
    if not approximately_matches(num, evidence_numbers):
        flag_for_disclaimer()
```

Jika ada ketidakcocokan yang signifikan, response tidak diblok tapi diberi disclaimer:

```text
Catatan: Silakan konfirmasi detail angka ini langsung ke tim HR untuk memastikan keakuratannya.
```

**Policy Claim Verification:**

Jika response mengklaim "kebijakan perusahaan menyatakan X", sistem memverifikasi bahwa klaim tersebut memiliki backing di `company_rule_chunks` yang di-retrieve.

Jika tidak ada evidence, disclaimer ditambahkan:

```text
Catatan: Informasi ini berdasarkan dokumen kebijakan yang tersedia. Silakan verifikasi dengan HR untuk aturan terbaru.
```

**Confidence Threshold:**

Jika `orchestrator.route_confidence < 0.6`, response diberi disclaimer otomatis:

```text
Informasi ini mungkin tidak lengkap. Silakan konfirmasi dengan tim HR.
```

### 3. Tone Validator

Validator ini memastikan response memenuhi standar komunikasi profesional.

Yang di-check:
- NVC compliance: response harus empathetic, factual, dan non-judgmental
- prohibited content: tidak ada legal advice, financial advice, atau medical diagnosis
- neutrality: AI tidak boleh berpihak ke employee atau ke company
- language register: tidak ada slang, profanity, atau bahasa yang terlalu informal

Implementasi tone check menggunakan MiniMax yang sudah ada di stack sebagai judge ringan.

Jika response gagal tone check, ada dua opsi:
- rewrite oleh orchestrator dengan instruksi tambahan (P1)
- fallback ke template response netral (P0, lebih aman)

---

## Konfigurasi Per Company

Setiap company bisa menyesuaikan guardrail behavior via tabel `guardrail_config`.

Konfigurasi yang bisa di-override:

```text
rate_limits:
  messages_per_hour: int
  conversations_per_day: int
  file_uploads_per_hour: int

pii_patterns:
  custom: list[regex_string]   # tambah pola PII internal company

blocked_topics:
  list[string]                 # topik yang sepenuhnya di-block

sensitivity_overrides:
  custom_high: list[string]
  custom_medium: list[string]

hallucination_check:
  enabled: bool
  numeric_tolerance_pct: float  # seberapa toleran terhadap selisih angka

tone_check:
  enabled: bool
  nvc_strict: bool

audit_level:
  minimal | standard | verbose
```

Catatan: konfigurasi guardrail dikelola oleh IT Admin, bukan HR Admin.

---

## Audit Logging

Phase 5 memperkenalkan audit log yang lebih lengkap dari trace yang sudah ada.

Setiap event guardrail ditulis ke tabel `guardrail_audit_logs`:

```text
id
company_id
employee_id
conversation_id  (nullable)
event_type       (input_blocked, pii_masked, hallucination_flagged, rate_limited, abuse_warned)
trigger          (detail kenapa event ini terjadi)
action_taken     (blocked, masked, disclaimer_added, cooldown_applied)
metadata         (tambahan context tanpa PII)
created_at
```

Log ini tidak diekspos ke employee. HR Admin bisa membaca ringkasannya. IT Admin bisa mengakses log lengkap.

---

## Priority Implementasi

| Priority | Fitur | Estimasi | Dependency |
|---|---|---|---|
| P0 | Rate limiter (Redis sliding window) | 4 jam | Redis (sudah ada) |
| P0 | Injection detector (layer 1 + 2) | 6 jam | Tidak ada |
| P0 | PII output scanner | 4 jam | Regex patterns |
| P1 | Hallucination checker (evidence-based) | 8 jam | Agent evidence trace |
| P1 | Content abuse detector | 4 jam | Redis (sudah ada) |
| P2 | Tone validator (MiniMax judge) | 6 jam | MiniMax (sudah ada) |
| P2 | Semantic injection classifier | 6 jam | Training data |
| P3 | Per-company guardrail config | 8 jam | Config schema baru |
| P3 | Audit logging table + endpoints | 6 jam | DB migration |

Total estimasi: ~52 jam kerja

---

## Struktur File yang Diusulkan

```text
apps/api/app/guardrails/
  __init__.py
  input_guard.py          # orchestrator input guard, entry point
  output_guard.py         # orchestrator output guard, entry point
  rate_limiter.py         # Redis sliding window implementation
  injection_detector.py   # multi-layer prompt injection defense
  pii_scanner.py          # regex PII detection + context-aware masking
  hallucination_checker.py # evidence-based numeric + claim validation
  tone_validator.py       # NVC compliance + prohibited content check
  abuse_detector.py       # repetitive message + gibberish detection
  config_loader.py        # per-company guardrail config reader
  models.py               # Pydantic models untuk guardrail result + config
  audit.py                # audit log writer
```

---

## Integration Point di Orchestrator

Perubahan minimal di `orchestrator.py` untuk mengaktifkan guardrail:

```python
async def process_message(self, message, attachments, session):

    # --- INPUT GUARD ---
    input_result = await input_guard.check(
        message=message,
        session=session,
        company_config=await config_loader.load(session.company_id)
    )
    if input_result.blocked:
        return input_result.safe_response

    # ... orchestration flow yang sudah ada ...
    agent_response = await self._execute_agents(route, session, context)

    # --- OUTPUT GUARD ---
    validated = await output_guard.validate(
        response=agent_response.answer,
        evidence=context.collected_evidence,
        session=session
    )

    return validated.response
```

Tidak ada perubahan pada trust boundary atau agent execution flow yang sudah ada.

---

## Guardrail Yang Tidak Berubah

Beberapa guardrail dari phase sebelumnya tetap berjalan dan tidak digantikan:

- trust boundary `employee_id` dan `company_id` dari JWT (Phase 1)
- `sensitivity != low` memaksa `manual_review` channel (Phase 2)
- `sensitive_redirect` route untuk topik sensitif high-risk (Phase 3)
- Pydantic field validation dengan `max_length` constraints (Phase 4)

Phase 5 menambah layer baru di atas semua guardrail yang sudah ada.

---

## Pemetaan Ke File Implementasi (Setelah Selesai)

Setelah Phase 5 selesai, file-file berikut akan menjadi entry point:

- `apps/api/app/guardrails/input_guard.py`
  Entry point untuk semua check sebelum orchestrator.

- `apps/api/app/guardrails/output_guard.py`
  Entry point untuk semua check setelah agent execution.

- `apps/api/app/guardrails/config_loader.py`
  Membaca konfigurasi guardrail per company dari Redis cache atau DB.

- `apps/api/app/services/orchestrator.py`
  Titik integrasi: dua hook ditambahkan di awal dan akhir `process_message`.

- `apps/api/app/api/routes/guardrails.py` (baru)
  Endpoint publik untuk IT Admin membaca audit log dan mengupdate guardrail config.

---

## Cara Memahami Phase 5 Secara Sederhana

Kalau disederhanakan, Phase 5 bekerja seperti ini:

1. setiap message masuk dicek rate limit-nya dulu
2. message di-scan untuk prompt injection dan dibersihkan dari karakter berbahaya
3. message yang lolos masuk ke orchestrator seperti biasa
4. setelah AI menjawab, response di-scan untuk PII
5. angka dalam response diverifikasi terhadap data yang benar-benar di-query dari DB
6. kalau ada masalah, response diberi disclaimer atau di-mask — bukan diblok mentah-mentah
7. semua event dicatat di audit log

Inti Phase 5 adalah:
- pengguna yang coba menyalahgunakan API tidak akan berhasil memanipulasi AI
- data pribadi karyawan lain tidak akan bocor ke session yang salah
- angka yang dikutip AI selalu bisa ditelusuri ke sumber data aslinya
- audit trail tersedia untuk compliance review
