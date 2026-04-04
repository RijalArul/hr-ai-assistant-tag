# Custom Agents, Conversations, Action Engine & Semantic Routing — Improvement Audit

> **Generated**: 2026-04-04  
> **Scope**: `hr_data_agent.py`, `company_agent.py`, `file_agent.py`, `conversations.py`, `action_engine.py`, `execution_intent.py`, `semantic_router.py`, guardrails, models  
> **Status**: Recommendation only — no code implementation

---

## Table of Contents

1. [Custom Agents (HR Data, Company, File)](#1-custom-agents)
2. [Conversation Service](#2-conversation-service)
3. [Action Engine & Execution Intent](#3-action-engine--execution-intent)
4. [Semantic Routing](#4-semantic-routing)
5. [Guardrails (Input/Output/PII/Hallucination)](#5-guardrails)
6. [Cross-Cutting Concerns](#6-cross-cutting-concerns)
7. [Priority Matrix](#7-priority-matrix)

---

## 1. Custom Agents

### 1.1 HR Data Agent (`hr_data_agent.py`)

#### A. Sequential DB Queries — Slow Latency

```
profile    = await _get_employee_profile(db, session)          # ~100ms
payroll    = await _get_payroll_records(db, session, month, year) # ~100ms
attendance = await _get_attendance_records(db, session, ...)     # ~100ms
time_off   = await _get_time_off_snapshot(db, session, year)    # ~100ms
                                                        TOTAL:   ~400ms
```

Semua query **sequential**, padahal tidak saling depend. Bisa pakai `asyncio.gather()` untuk parallel → ~100ms total.

**Recommendation**: Parallel fetch pakai `asyncio.gather()` untuk queries yang independent. Conditional fetch berdasarkan intent (tidak perlu fetch attendance kalau intent = PAYROLL_INFO).

#### B. Silent Failure pada Data Retrieval

| Function | Saat Error | Behavior | Problem |
|----------|-----------|----------|---------|
| `_get_employee_profile()` | Employee not found | Return `None` | Agent lanjut dengan None, response kosong/aneh |
| `_get_payroll_records()` | DB timeout | Return `[]` | Tidak bisa dibedakan dari "belum ada payroll" |
| `_get_attendance_records()` | Query error | Return `[]` | User dikasih "tidak ada data kehadiran" |
| `_get_time_off_snapshot()` | DB error | Return `{}` | User dikasih "saldo cuti tidak tersedia" |

**Recommendation**: Return structured result (`DataResult` dengan status: `ok | not_found | error`) supaya downstream bisa kasih pesan yang tepat ke user.

#### C. Period Inheritance Terlalu Agresif (Partial Fix)

**Sudah di-fix**:
- ✅ `_should_inherit_conversation_context()` sudah ditambah keyword sensitive/report/decision

**Masih bermasalah**:
- Inherit seluruh user message sebelumnya (`f"{recent_user_message}\n{message}"`) → semua parameter terbawa
- Month extractor parse dari inherited content tanpa tahu konteksnya

**Contoh masalah yang tersisa**:
```
Turn 1: "Gaji Maret untuk karyawan departemen finance"
Turn 2: "Berapa rata-ratanya?"  (short → inherit)
Jadi:   "Gaji Maret untuk karyawan departemen finance\nBerapa rata-ratanya?"
```
Month "Maret" + context "departemen finance" ikut terbawa, padahal user mungkin tanya "rata-rata" secara general.

**Recommendation**: Selective inheritance — hanya inherit parameter yang **relevan ke intent saat ini**. Misal intent=PAYROLL → boleh inherit month/year. Intent=ATTENDANCE → jangan inherit payroll context.

#### D. Decimal Precision Lost di Serialization

```python
def _serialize_value(value):
    if isinstance(value, Decimal):
        return int(value)  # Decimal 99999.99 → int 99999
```

Untuk data payroll yang punya desimal (THR prorata, potongan PPh21 per-hari, dll), precision hilang.

**Recommendation**: Ganti `int(value)` ke `float(value)` atau `str(value)` untuk preserve precision di evidence.

#### E. Payroll Delta / Comparison Belum Implemented

- User tanya "kenapa gaji bulan ini turun?"
- Intent detected: `PAYROLL_INFO` 
- Tapi agent hanya fetch 1 period → tidak ada comparison logic
- Tidak ada breakdown per-komponen (BPJS naik? PPh21 berubah? Tunjangan hilang?)

**Recommendation**: Implement `_compare_payroll_periods()` yang auto-fetch N dan N-1, lalu diff setiap komponen.

#### F. Time-Off Simulation Tidak Complete

- Intent `TIME_OFF_SIMULATION` cuma return snapshot saldo
- Tidak calculate: "kalau ambil 5 hari, sisa jadi berapa?"
- Tidak cek: carry-over rules, probation restriction, pending requests yang belum approved

**Recommendation**: Implement simulation engine yang project saldo ke depan berdasarkan input hari + policy constraints.

---

### 1.2 Company Agent (`company_agent.py`)

#### A. Company Structure Lookup Belum Ada

- Intent `COMPANY_STRUCTURE` exists di model
- Tapi agent hanya handle **policy + guidance lookup**
- "Siapa PIC HR?" → tidak ada query ke `responsibility_routes` table
- "Struktur departemen engineering?" → tidak ada hierarchy retrieval

**Recommendation**: Implement structure retrieval dari `responsibility_routes` + department hierarchy tables.

#### B. Policy Version Conflict

```
Rules di database:
  - "Annual Leave Policy v3.2" (2023, outdated)
  - "Cuti Tahunan 2024 v4.0" (current)

Semantic matcher rank v3.2 lebih tinggi (keyword match lebih baik)
Agent cite: "Carry over tidak diizinkan (v3.2)"
Padahal v4.0: "Carry over 5 hari per tahun"
```

Sudah ada preferensi `effective_date DESC`, tapi semantic similarity bisa override.

**Recommendation**: Hard constraint — jika ada policy dengan subjek sama, WAJIB gunakan yang `effective_date` paling baru. Versi lama hanya boleh dipakai kalau user explicitly minta ("policy tahun lalu").

#### C. Full-Table Load untuk Rules

- `_load_company_rules()` load SEMUA active rules ke memory
- Lalu rank/filter di Python
- Untuk company dengan 100+ policies → megabytes data per request

**Recommendation**: Pre-filter di DB level berdasarkan `category` atau `intent_key` sebelum load ke memory. Atau gunakan vector search di DB (pgvector).

#### D. Policy Reasoning Incomplete

Extracts:
- ✅ Amount, documents, frequency
- ✅ Employee level (probation, etc.)

Missing:
- ❌ Eligibility criterion evaluation ("Apakah saya eligible?")
- ❌ Coverage determination
- ❌ Exclusion rules application
- ❌ Multi-condition evaluation ("Level 3 AND masa kerja > 2 tahun")

**Recommendation**: Implement rule-based eligibility engine yang evaluate conditions against employee profile.

---

### 1.3 File Agent (`file_agent.py`)

#### A. Path Traversal Not Validated

```python
path = Path(attachment.file_path).expanduser().resolve()
if not path.exists():
    ...  # Only checks existence, not location
```

Tidak ada check apakah resolved path masih dalam allowed upload directory.

**Recommendation**: Validate `path.is_relative_to(UPLOAD_DIR)` setelah resolve.

#### B. Large File Not Handled

- `.txt`, `.md`, `.json` di-read langsung dengan `read_text()`
- File 10MB+ bisa cause OOM
- Tidak ada size limit check sebelum read

**Recommendation**: Check file size sebelum read. Untuk file besar, stream/chunk atau reject dengan pesan error.

#### C. Gemini Fallback Chain Incomplete

```
Gemini → PDF extractor → image metadata only
```

- Kalau Gemini gagal untuk `.png`/`.jpg`, fallback hanya return dimensi gambar
- Tidak ada OCR fallback (Tesseract, etc.)
- User upload foto struk reimburse → hanya dapat "Image 1024x768" tanpa content

**Recommendation**: Add OCR fallback untuk image files ketika Gemini unavailable.

---

## 2. Conversation Service

### 2.1 History Truncation — Context Window Terlalu Kecil

```
DB: conversation_messages (semua history, bisa 50+ messages)
  ↓
Truncate ke max_history_items = 4
  ↓
Agents hanya lihat 4 message terakhir
```

**Problem**: Conversation turn 10 tentang "gaji Maret", tapi context "Maret" established di turn 2 → agents tidak bisa lihat.

**Recommendation**: 
- Increase window secara conditional (simple chat = 4, intake workflow = 8)
- Atau: summarize older messages instead of truncating

### 2.2 Conversation Status Kurang Granular

Current states:
- `ACTIVE` — default
- `ESCALATED` — sensitive case
- `CLOSED` — manual only

Missing states:

| Missing State | Use Case |
|---------------|----------|
| `WAITING_FOR_INPUT` | Intake flow sedang collect data (start_date, end_date) |
| `ACTION_PENDING` | Menunggu HR execute action |
| `RESOLVED` | Conversation selesai, semua action sudah complete |
| `STALE` | Conversation idle > 24 jam |

**Recommendation**: Tambah states untuk granularity. Ini penting agar UI bisa show progress yang benar.

### 2.3 Orchestration Context Tidak Fully Persisted

```
OrchestratorResponse:
  - route, intent, sensitivity, trace steps
  
Stored di: conversation_messages.metadata["orchestration"]
  ↓
Tapi: rule yang matched, action intent_key → TIDAK di-join saat retrieve
```

**Problem**: Saat debug issue, tidak bisa lihat "message ini trigger rule apa?" tanpa manual join.

**Recommendation**: Denormalize rule_id dan action_id ke message metadata, atau buat relasi explicit.

### 2.4 Concurrent Status Update Race Condition

```
T1 (User message endpoint):  UPDATE conversations SET status='ESCALATED'
T2 (Rules endpoint, parallel): UPDATE conversations SET status='ACTIVE'
```

Tidak ada optimistic concurrency control. Kalau 2 update concurrent, yang terakhir menang tanpa check.

**Recommendation**: Tambah `AND updated_at = :expected_updated_at` di WHERE clause, atau row-level lock.

### 2.5 Tidak Ada Multi-Turn Intake State Tracking

```
Turn 1: "Mau ajukan cuti dari 10 April" → Missing end_date → System: "Sampai tanggal berapa?"
Turn 2: "Sampai 14 April"
```

**Problem**: Turn 2 TIDAK punya memory bahwa Turn 1 sudah extract `start_date=10 April`. Harus re-extract dari history grounding yang bisa miss.

**Recommendation**: Implement `intake_state` field di conversation yang track partial data:
```json
{
  "workflow": "leave_request",
  "collected": {"start_date": "2026-04-10"},
  "missing": ["end_date"],
  "step": 2
}
```

---

## 3. Action Engine & Execution Intent

### 3.1 Tidak Ada Request Deduplication

User kirim "cuti dari 10 April sampai 14 April" dua kali:
1. Pertama → create `LeaveRequestPayload` action ✅
2. Kedua → create **duplicate** action ✅ (harusnya ❌)

HR lihat 2 leave request yang sama → bingung approve yang mana.

**Recommendation**: Idempotency check sebelum `create_actions_from_rule_trigger`:
```python
existing = await _find_action(db, conversation_id, intent_key, payload_hash)
if existing:
    return existing  # Return existing instead of creating duplicate
```

### 3.2 Action Status Transition Tidak Validated

Valid transitions seharusnya:
```
PENDING → READY → IN_PROGRESS → COMPLETED
PENDING → READY → IN_PROGRESS → FAILED
ANY → CANCELLED
```

**Problem**: Tidak ada state machine definition. Logic tersebar di conditional SQL WHERE clauses. Edge case:
- `IN_PROGRESS → READY` (rollback) — harusnya illegal, tapi tidak di-block
- `COMPLETED → IN_PROGRESS` (re-open) — harusnya illegal

**Recommendation**: Define explicit `ALLOWED_TRANSITIONS` dict dan validate sebelum update:
```python
ALLOWED_TRANSITIONS = {
    "PENDING": ["READY", "CANCELLED"],
    "READY": ["IN_PROGRESS", "CANCELLED"],
    "IN_PROGRESS": ["COMPLETED", "FAILED", "CANCELLED"],
}
```

### 3.3 Action Claim Race Condition

```
HR Admin A: PATCH /actions/{id} status=IN_PROGRESS  → OK ✅
HR Admin B: PATCH /actions/{id} status=IN_PROGRESS  → 409 Conflict ✅

Employee:   GET /actions/{id}
  → Action sudah di-claim HR Admin A
  → Employee dapat 403 Forbidden (bukan 404)
  → User bingung: dihapus atau diklaim?
```

**Recommendation**: Tambah `claimed_by` field. Employee tetap bisa lihat action tapi dengan status "sedang diproses oleh HR".

### 3.4 Template Materialization Silently Ignores Missing Vars

```python
class _SafeFormatDict(dict):
    def __missing__(self, key):
        return f"{{{key}}}"  # Return literal {key} if not found
```

**Problem**: Payload template `{"month": "{month}", "year": "{year}"}` — kalau `year` tidak ter-extract, payload jadi:
```json
{"month": "3", "year": "{year}"}  // Literal string, bukan error
```

Action di-create dengan data incomplete, tapi tidak ada warning.

**Recommendation**: 
- Log warning ketika template var tidak ter-resolve
- Atau: reject action creation kalau ada unresolved required vars

### 3.5 Delivery Channel Sanitization Setelah Creation

```python
# Sensitive action → force MANUAL_REVIEW regardless of requested channels
if sensitivity != SensitivityLevel.LOW.value:
    return [DeliveryChannel.MANUAL_REVIEW.value]
```

User request `delivery_channels=[WEBHOOK, EMAIL]` tapi sensitivity=HIGH → silently changed ke `MANUAL_REVIEW`. Response 200 OK tanpa warning.

**Recommendation**: Validate SEBELUM creation. Return 400 dengan pesan "Sensitive actions hanya bisa via manual review" supaya user tahu.

### 3.6 Date Extraction Brittle

`_extract_all_dates()` di `execution_intent.py`:
- "cuti dari 10 April sampai 14 April" ✅ ter-extract
- "cuti mulai 10 April, selesai 14 April" ❌ mungkin miss (synonym verb)
- "cuti 10 ke 14 April 2025" — bisa extract 4 date-like tokens → salah assign start/end

**Recommendation**: 
- Test lebih banyak date format variations
- Gunakan NLP date parser (dateutil, etc.) instead of pure regex
- Validate: start_date < end_date

### 3.7 Rule Action Config Validation Terlalu Lenient

```json
{
  "type": "document_generation",
  "parameters": {
    "month": "{{month}}",
    "year": "this_year"  // Typo, harusnya {{year}}
  }
}
```

Validation pass karena ada `{{month}}` token. Tapi `this_year` literal bukan template var → dokumen generated dengan input salah.

**Recommendation**: Strict validation — SEMUA parameter values harus either template var `{{...}}` atau constant dari allowed list.

---

## 4. Semantic Routing

### 4.1 Embedding Failure → Lexical-Only dengan Discount Berat

```python
# Ketika embedding API down:
lexical_only_score = raw_score * 0.60  # 40% discount
```

**Problem**: Message ambigu yang butuh semantic understanding jatuh ke lexical matching dengan confidence rendah → route ke `OUT_OF_SCOPE` padahal seharusnya bisa di-route benar.

**Recommendation**: 
- Increase lexical weight ketika vector unavailable (misal 0.80x bukan 0.60x)
- Atau: queue message untuk retry ketika embedding pulih

### 4.2 Cache Key Include context_hint — Double Cache Load

```python
cache_key = f"{company_id}:{context_hint or ''}:{_message_hash(normalized_message)}"
```

Same message "cuti" dengan hint "policy_reasoning" vs "guidance" → 2 separate cache entries. Untuk multi-intent messages, cache load berlipat.

**Recommendation**: Split jadi 2 cache layers:
1. **Retrieval cache** (context-independent): `{company_id}:{message_hash}` → raw candidates
2. **Ranking cache** (context-dependent): apply hint re-ranking on top of cached candidates

### 4.3 Tidak Ada Negative Example Support

Semantic router hanya punya **positive examples** per intent. Tidak ada "message ini BUKAN intent X".

**Problem**:
```
"Saya bayar tagihan BPJS" → matched ke PAYROLL_INFO (karena "bayar" + "BPJS")
Padahal ini bukan payroll question — ini general statement
```

**Recommendation**: Support negative examples di `intent_examples` table agar routing bisa learn boundaries.

### 4.4 Semantic Router Tidak Handle Multi-Intent

```
"Berapa gaji saya bulan ini, dan sisa cuti saya?"
```

Router hanya return **1 primary intent** + secondary intents sebagai metadata. Orchestrator harus handle split, tapi:
- Hanya 1 agent execution path (HR_DATA or COMPANY or MIXED)
- Kalau primary=PAYROLL_INFO → time off data tidak di-fetch

**Recommendation**: 
- Detect multi-intent messages explicitly
- Split ke parallel agent executions
- Atau: MIXED route harus cover intra-HR-agent multi-intent, bukan cuma cross-agent

### 4.5 Intent Example Staleness

```python
cache_key = f"intent_examples:{company_id}"  # TTL 300s
```

Admin tambah intent example baru → user harus tunggu 5 menit sebelum efek terlihat. Tidak ada manual invalidation.

**Recommendation**: Add cache invalidation endpoint / event-driven invalidation saat intent example di-update.

---

## 5. Guardrails

### 5.1 PII Scanner — Salary Amount Tidak Di-mask

```python
if pii_type == "salary_amount":
    continue  # Skip masking for MVP
```

Response "Gaji kamu Rp 15.000.000" → salary exposed. Comment bilang "check at agent level" tapi tidak ada check di agent code.

**Recommendation**: Implement context-aware masking:
- Mask salary kalau response mention orang lain
- Don't mask kalau user tanya gaji sendiri
- Add ownership check, bukan skip entirely

### 5.2 Hallucination Checker — Evidence Source Tidak Di-tag

```python
evidence_numbers = [12, 2, 5]  # From different sources
response: "Saldo cuti kamu 12 hari"

# Checker: "12 is in evidence_numbers? Yes → PASS"
# But 12 came from pending_request, not balance!
```

**Recommendation**: Tag evidence: `{value: 12, source: "leave_balance"}` vs `{value: 2, source: "pending_days"}`. Check bahwa number dalam response cocok dengan source yang semantically benar.

### 5.3 Hallucination Tolerance Perlu Per-Data-Type

| Data Type | Current Tolerance | Should Be |
|-----------|------------------|-----------|
| Salary (Rp) | 1% (~Rp 100K) | 0% (exact match) |
| Attendance hours | 1% | 5% (acceptable rounding) |
| Leave days | 1% | 0% (exact match) |
| Reimbursement amount | 1% | 0% (exact match) |

**Recommendation**: Per-data-type tolerance config, bukan global 1%.

### 5.4 Injection Detector — Indonesian Variants Missing

Detected:
- ✅ "ignore all previous instructions"
- ✅ "system prompt"

Not detected:
- ❌ "abaikan semua instruksi di atas"
- ❌ "lupakan perintah sebelumnya"
- ❌ "mode developer"
- ❌ "kamu sekarang jadi..."

**Recommendation**: Tambah pattern Indonesian injection variants.

### 5.5 Rate Limiter — Redis Down = Allow All

```python
except RuntimeError:
    return True, 0, limit  # Allow all if Redis fails
```

Redis down → semua request diizinkan tanpa limit.

**Recommendation**: In-memory fallback rate limiter (sliding window) ketika Redis unavailable. Conservative limit (misal 50% of normal).

### 5.6 Rate Limiter — No Company-Level Aggregate

- Per-employee limiting ada ✅
- Per-company limiting tidak ada ❌
- 100 compromised employee tokens dari 1 company bisa flood API

**Recommendation**: Tambah company-level rate limit (misal 1000 req/min total per company).

### 5.7 Custom PII Pattern — ReDoS Risk

```python
for custom_pattern_str in (pii_config_custom or []):
    custom_pattern = re.compile(custom_pattern_str)  # No complexity check
```

Malicious admin bisa set pattern `(a+)+b` → regex catastrophic backtracking → CPU hang.

**Recommendation**: Validate regex complexity sebelum compile. Atau: timeout pada regex execution.

---

## 6. Cross-Cutting Concerns

### 6.1 Tidak Ada Distributed Transaction Coordination

Orchestration pipeline:
```
1. Input guardrail  ✅
2. Agent execution   ✅
3. Output guardrail  ✅
4. Action creation   ❌ (bisa fail)
5. Auto-execution    ❌ (bisa fail)
```

Kalau step 4 gagal setelah step 3 sukses → user sudah dapat response tapi action tidak ter-create. Inconsistent state.

**Recommendation**: Wrapping step 3-5 dalam single transaction, atau compensating action (log error, retry queue).

### 6.2 Tidak Ada Conversation Versioning

- Messages immutable ✅
- Tapi orchestration result reflect **current** rule set
- Kalau rule berubah di masa depan, tidak bisa replay keputusan lama

**Recommendation**: Snapshot rule version di message metadata saat creation.

### 6.3 Tidak Ada Audit Trail untuk Data Access

| Access | Logged? |
|--------|---------|
| Employee lihat gaji sendiri | ❌ |
| Employee lihat profil sendiri | ❌ |
| HR admin claim action | ❌ Partial (status change only) |
| Failed data access attempt | ❌ |
| Sensitive case detection | ❌ |

Untuk GDPR/compliance, semua data access harus di-audit.

**Recommendation**: Implement audit log table dengan fields: who, what, when, result, ip_address.

### 6.4 No Health Check for External Dependencies

- Minimax API → circuit breaker tapi no health probe
- Embedding API → silent failure
- Redis → allow-all fallback
- Gemini → no health check

**Recommendation**: Background health check loop yang periodically probe external dependencies. Expose status di `/health` endpoint.

---

## 7. Priority Matrix

### Legend
- **P0**: Bisa cause incorrect data / security issue — fix ASAP
- **P1**: Bisa cause bad UX / confusion — fix soon  
- **P2**: Nice to have, improves quality — plan later
- **P3**: Low impact, future improvement

### Custom Agents

| # | Issue | Severity | Effort | Priority |
|---|-------|----------|--------|----------|
| 1 | HR agent sequential DB queries → parallel | MEDIUM | LOW | **P1** |
| 2 | Silent failure → structured error result | MEDIUM | MEDIUM | **P1** |
| 3 | Selective period inheritance (per-intent) | HIGH | MEDIUM | **P1** |
| 4 | Decimal precision loss di serialization | MEDIUM | LOW | **P1** |
| 5 | Payroll delta / comparison engine | MEDIUM | HIGH | **P2** |
| 6 | Time-off simulation engine | MEDIUM | HIGH | **P2** |
| 7 | Company structure lookup implementation | MEDIUM | MEDIUM | **P2** |
| 8 | Policy version hard constraint | HIGH | LOW | **P1** |
| 9 | Company rules pre-filter di DB | LOW | MEDIUM | **P3** |
| 10 | File agent path traversal validation | HIGH | LOW | **P0** |
| 11 | File agent large file handling | MEDIUM | LOW | **P1** |
| 12 | File agent OCR fallback | LOW | HIGH | **P3** |

### Conversation Service

| # | Issue | Severity | Effort | Priority |
|---|-------|----------|--------|----------|
| 13 | Multi-turn intake state tracking | HIGH | MEDIUM | **P0** |
| 14 | Conversation status granularity | MEDIUM | MEDIUM | **P1** |
| 15 | Conversation concurrent update race condition | MEDIUM | LOW | **P1** |
| 16 | History truncation too aggressive | MEDIUM | LOW | **P2** |
| 17 | Orchestration context fully persisted | LOW | LOW | **P2** |

### Action Engine

| # | Issue | Severity | Effort | Priority |
|---|-------|----------|--------|----------|
| 18 | Action deduplication (idempotency key) | HIGH | LOW | **P0** |
| 19 | Action status transition state machine | HIGH | LOW | **P0** |
| 20 | Template missing vars → warning/reject | MEDIUM | LOW | **P1** |
| 21 | Delivery channel validate before creation | MEDIUM | LOW | **P1** |
| 22 | Date extraction robustness | MEDIUM | MEDIUM | **P1** |
| 23 | Action claim `claimed_by` field | LOW | LOW | **P2** |
| 24 | Rule action config strict validation | MEDIUM | LOW | **P2** |

### Semantic Routing

| # | Issue | Severity | Effort | Priority |
|---|-------|----------|--------|----------|
| 25 | Embedding failure → better lexical fallback | MEDIUM | LOW | **P1** |
| 26 | Cache layer split (retrieval vs ranking) | LOW | MEDIUM | **P2** |
| 27 | Multi-intent message handling | MEDIUM | HIGH | **P2** |
| 28 | Negative example support | LOW | MEDIUM | **P3** |
| 29 | Intent example cache invalidation | LOW | LOW | **P2** |

### Guardrails

| # | Issue | Severity | Effort | Priority |
|---|-------|----------|--------|----------|
| 30 | PII salary masking (context-aware) | HIGH | MEDIUM | **P0** |
| 31 | Hallucination evidence source tagging | HIGH | MEDIUM | **P1** |
| 32 | Hallucination tolerance per-data-type | MEDIUM | LOW | **P1** |
| 33 | Indonesian injection patterns | HIGH | LOW | **P0** |
| 34 | Rate limiter Redis fallback | MEDIUM | LOW | **P1** |
| 35 | Rate limiter company-level | MEDIUM | MEDIUM | **P1** |
| 36 | PII custom pattern ReDoS guard | MEDIUM | LOW | **P1** |

### Cross-Cutting

| # | Issue | Severity | Effort | Priority |
|---|-------|----------|--------|----------|
| 37 | Data access audit trail | HIGH | MEDIUM | **P1** |
| 38 | Transaction coordination | MEDIUM | HIGH | **P2** |
| 39 | Conversation versioning | LOW | MEDIUM | **P3** |
| 40 | External dependency health checks | MEDIUM | MEDIUM | **P2** |

---

## Summary: Top 10 Paling Urgent

| Rank | Issue | Why Urgent |
|------|-------|------------|
| 1 | **Action deduplication** (#18) | Duplicate leave/reimburse requests bingungkan HR |
| 2 | **Action state machine** (#19) | Illegal state transitions bisa corrupt workflow |
| 3 | **Multi-turn intake tracking** (#13) | Intake flow gagal collect data → incomplete actions |
| 4 | **File agent path traversal** (#10) | Security vulnerability |
| 5 | **PII salary masking** (#30) | Data exposure risk |
| 6 | **Indonesian injection patterns** (#33) | Security vulnerability |
| 7 | **Policy version hard constraint** (#8) | Bisa cite outdated policy → wrong advice |
| 8 | **HR agent parallel queries** (#1) | Quick win, ~300ms latency reduction |
| 9 | **Hallucination evidence tagging** (#31) | Angka bisa lolos checker padahal dari source salah |
| 10 | **Selective period inheritance** (#3) | Masih bisa terjadi topic bleeding di edge cases |
