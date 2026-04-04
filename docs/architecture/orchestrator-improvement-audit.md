# Orchestrator & Custom Agents — Improvement Audit

> **Generated**: 2026-04-04  
> **Scope**: `orchestrator.py`, `hr_data_agent.py`, `company_agent.py`, `file_agent.py`, guardrails, services  
> **Status**: Recommendation only — no code implementation

---

## Table of Contents

1. [Context & Topic Bleeding](#1-context--topic-bleeding)
2. [Hallucination Risks](#2-hallucination-risks)
3. [Hardcoded Values & Configurability](#3-hardcoded-values--configurability)
4. [Error Handling & Edge Cases](#4-error-handling--edge-cases)
5. [Sensitive Case Handling](#5-sensitive-case-handling)
6. [Caching & Data Freshness](#6-caching--data-freshness)
7. [Security Gaps](#7-security-gaps)
8. [Scalability](#8-scalability)
9. [Multi-Language Support](#9-multi-language-support)
10. [Logging & Observability](#10-logging--observability)
11. [Priority Matrix](#11-priority-matrix)

---

## 1. Context & Topic Bleeding

**Severity: HIGH** — Langsung berdampak ke akurasi jawaban.

### 1.1 Grounding Logic Terlalu Agresif

**File**: `orchestrator.py` → `_should_use_conversation_grounding()`

| Problem | Detail |
|---------|--------|
| Short follow-up threshold (≤6 token) terlalu broad | Pesan pendek tapi topik baru (misal "mau lapor pelecehan") tetap di-ground ke history sebelumnya |
| `standalone_signals` list incomplete | ~~Keyword sensitive/report/decision tidak ada~~ ✅ **Sudah di-fix** |
| Tidak ada topic-change detection | ~~Tidak membandingkan domain topik lama vs baru~~ ✅ **Sudah di-fix** (`_TOPIC_DOMAIN_MAP`) |

**Yang masih perlu di-improve**:

- **Explicit context reset detection**: User kadang bilang "pertanyaan baru ya", "ganti topik", "beda lagi" — ini belum ditangani sebagai topic boundary.
- **Time-based context decay**: History dari 3 hari lalu seharusnya tidak di-ground ke pesan hari ini. Tidak ada timestamp check di grounding logic.
- **Confidence-based history suppression**: Bahkan ketika intent confidence sudah tinggi (>0.9), history tetap di-prepend. Seharusnya high-confidence standalone message skip grounding.

### 1.2 HR Agent Period Inheritance Terlalu Agresif

**File**: `hr_data_agent.py` → `_build_contextual_message()`

| Problem | Detail |
|---------|--------|
| Inherits FULL previous user message | `f"{recent_user_message}\n{message}"` — semua parameter (bulan, tahun, nama) ikut terbawa |
| Month/year extractor parses inherited content | "Gaji Maret?" → "Rata-rata jam masuk?" → Attendance query di-filter Maret |
| ~~Domain signals list incomplete~~ | ✅ **Sudah di-fix** |

**Yang masih perlu di-improve**:

- **Selective parameter inheritance**: Hanya inherit parameter yang relevan ke intent baru. Contoh: bulan boleh inherit kalau topik masih payroll→payroll, tapi jangan inherit kalau payroll→attendance.
- **Inherit dengan confidence scoring**: Bukan binary inherit/skip, tapi scoring berapa "likely" parameter itu relevan ke pertanyaan baru.

### 1.3 Mixed Mode Agents Share Context

**File**: `orchestrator.py` → `_run_hr_data_agent_isolated()`, `_run_company_agent_isolated()`

- DB session sudah isolated ✅
- Tapi `conversation_history` dan `session` context masih shared
- Jika satu agent menilai context tertentu (misal PROBATION), agent lain bisa terpengaruh

**Recommendation**: Filter conversation history per agent — HR agent hanya terima history yang relevan ke data personal, company agent hanya terima history tentang policy.

---

## 2. Hallucination Risks

**Severity: HIGH** — Bisa memberikan informasi finansial yang salah.

### 2.1 Response Synthesis Tanpa Fact Verification

**File**: `orchestrator.py` → `_synthesize_answer()`

```
Input dari HR agent: "Gaji pokok Anda Rp 12 juta"
Input dari Company agent: "Sesuai policy, kompensasi level 5 adalah Rp 10-15 juta"
Output: "Data personal: Gaji pokok Anda Rp 12 juta. Referensi perusahaan: ..."
```

**Problem**: Tidak ada cross-verification bahwa "Rp 12 juta" benar-benar dari DB record. Kalau HR agent hallucinate angka, synthesizer langsung pakai.

**Recommendation**:
- Tambahin `source_evidence` field di setiap claim numerik
- Hallucination checker harus verify: angka di response == angka di evidence records
- Jika mismatch, flag response untuk review

### 2.2 Hallucination Checker Tolerance Terlalu Loose

**File**: `guardrails/hallucination_checker.py`

- Numeric tolerance 1% → Rp 100K bisa lolos di gaji Rp 10M
- Untuk konteks gaji karyawan, Rp 100K itu signifikan
- Harusnya tolerance absolute, bukan persentase: misal max Rp 0 deviation untuk salary figures

### 2.3 Agent Bisa Generate Angka yang Tidak Ada di DB

**File**: `hr_data_agent.py`

- Agent menerima payroll records → `[{"basic_salary": 10000000}]`
- Agent meng-construct summary text: "Gaji pokok Anda Rp 10.000.000"
- Tapi kalau ada rounding/formatting error, angka bisa berubah
- Tidak ada post-check bahwa angka di summary == angka di raw record

**Recommendation**: Implement **grounded response generation** — setiap angka di response WAJIB punya reference ke raw data record.

### 2.4 Company Rules Version Conflict

**File**: `company_agent.py` → `_rank_rules()`

- Rules di-rank berdasarkan keyword/semantic similarity
- Versi lama policy bisa rank lebih tinggi dari versi baru jika keyword match lebih baik
- Sudah ada preferensi ke `effective_date` DESC, tapi ranking bisa override-nya

**Recommendation**: Hard constraint — jika ada policy dengan judul sama, selalu gunakan versi terbaru. Baru fallback ke similarity ranking.

---

## 3. Hardcoded Values & Configurability

**Severity: MEDIUM** — Tidak critical sekarang, tapi akan blocking saat scale.

### 3.1 Classification Thresholds

| Constant | Value | File | Should Be |
|----------|-------|------|-----------|
| `LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD` | 0.78 | orchestrator.py | Per-company config |
| `SEMANTIC_PROVIDER_HINT_THRESHOLD` (vector) | 0.52 | orchestrator.py | Per-company config |
| `SEMANTIC_PROVIDER_HINT_THRESHOLD` (lexical) | 0.34 | orchestrator.py | Per-company config |
| `AGENT_CAPABILITY_ROUTE_THRESHOLD` (vector) | 0.58 | orchestrator.py | Per-company config |
| `SEMANTIC_DIRECT_FALLBACK_THRESHOLD` (vector) | 0.72 | orchestrator.py | Per-company config |
| Conversation history window | 4 items | orchestrator.py | Per-conversation config |
| Payroll record limit | 1 or 3 | hr_data_agent.py | User-adjustable |
| Policy similarity threshold | 0.55 / 0.72 / 0.78 | company_agent.py | Per-company config |
| Hallucination tolerance | 1% | hallucination_checker.py | Per-data-type config |

**Recommendation**: Buat `ClassifierConfig` model di DB, per company. Load via `_load_classifier_overrides()` yang sudah ada — extend saja confignya.

### 3.2 Intent Keywords Monolit

- Semua intent keywords hardcoded di Python source
- Untuk tambah intent baru atau update keyword → deploy ulang
- Seharusnya bisa manage dari DB / admin panel

---

## 4. Error Handling & Edge Cases

**Severity: MEDIUM**

### 4.1 Silent Failures yang Berbahaya

| Location | Problem | Impact |
|----------|---------|--------|
| `hr_data_agent._get_employee_profile()` | Return `None` tanpa error message | User dapat response kosong, bingung kenapa |
| `hr_data_agent._get_payroll_records()` | Return `[]` baik pas no data maupun DB error | "No payroll" vs "DB down" tidak bisa dibedakan |
| `company_agent._load_company_rules()` | Return `[]` on exception | User dikasih "Tidak ada policy" padahal sebenarnya DB timeout |
| `semantic_router.generate_embedding()` | Return `None` on failure | Downstream vector search pakai None → undefined behavior |

**Recommendation**: Setiap data retrieval function harus return `Result[T, ErrorReason]` pattern:
```python
@dataclass
class DataResult:
    data: Any
    status: Literal["ok", "not_found", "error"]
    error_reason: str | None = None
```

### 4.2 Conversation History Tanpa Validation

- History dari DB langsung dipakai tanpa schema validation
- Bisa ada malformed `role`, missing `content`, Unicode corruption
- Tidak ada max size check — 1000 messages bisa di-load sekaligus

### 4.3 Date Edge Cases

- Tidak handle midnight rollover (query jam 23:55 vs 00:05 beda bulan)
- Tidak handle timezone difference antara server dan user
- Relative date parsing ("minggu lalu", "bulan kemarin") tidak timezone-aware

---

## 5. Sensitive Case Handling

**Severity: HIGH** — Berkaitan dengan wellbeing dan legal compliance.

### 5.1 Sensitive Context Tidak Persist Across Messages

```
Msg 1: "Saya dibully di tim"    → SENSITIVE_REDIRECT → ✅ Handled
Msg 2: "Bagaimana kalau mereka tahu?"  → OUT_OF_SCOPE → ❌ Context lost
```

- Setelah di-mark SENSITIVE, pesan follow-up tanpa keyword sensitive bisa di-classify biasa
- Conversation sudah di-mark `escalated` di DB, tapi classifier per-message tidak cek status ini
- Follow-up ambigu bisa salah route

**Recommendation**: 
- Cek `conversation.status == escalated` sebelum classify
- Jika conversation sudah escalated, bias routing ke sensitive handler
- Tambah "escalated conversation follow-up" mode

### 5.2 Sensitive Report Tidak Punya Structured Intake

- User bilang "mau lapor pelecehan" → sistem respond dengan template empati
- Tapi tidak ada structured intake: siapa pelaku, kapan kejadian, dll
- Action dibuat tapi detail kosong

**Recommendation**: Implement guided intake flow untuk sensitive cases — step-by-step questions setelah initial detection.

### 5.3 Sensitive Policy Matrix Belum Complete

- `assess_sensitive_case()` mendeteksi kategori (harassment, discrimination, etc.)
- Tapi response template per-kategori masih generic
- Belum ada differentiation antara "lapor ke HR" vs "lapor ke ethics committee" vs "hubungi hotline"

---

## 6. Caching & Data Freshness

**Severity: MEDIUM**

### 6.1 Cache Staleness Risk

| Cache | TTL | Staleness Risk |
|-------|-----|----------------|
| Employee profile | 300s | Medium — user update profile, cache masih lama |
| Payroll records | 300s | Low — payroll jarang berubah |
| Company rules | 300s | Medium — rule update di-deploy, cache masih lama |
| Semantic embeddings | 120s | Low |
| Intent examples | 300s | High — admin tambah example, efek delayed |

### 6.2 Tidak Ada Cache Invalidation Manual

- Tidak ada endpoint `/admin/cache/invalidate`
- Kalau ada data corruption di cache, harus wait TTL expire
- Untuk emergency fix, tidak bisa force refresh

### 6.3 Cache Empty Results Pada Error

- DB timeout → cache menyimpan `[]` selama 60s
- User selama 60s itu dikasih "tidak ada data"
- Seharusnya: jangan cache error results, atau cache dengan TTL sangat pendek (5s)

### 6.4 Cache Key Collision Risk

- Key format: `f"{company_id}:{employee_id}:{month}:{year}"`
- Jika UUID format berubah atau ada special character, bisa collision
- Recommendation: Hash seluruh key params

---

## 7. Security Gaps

**Severity: MEDIUM-HIGH**

### 7.1 LIMIT Parameter String Interpolation

**File**: `hr_data_agent.py`

```python
result = await db.execute(
    text(f"""... LIMIT {resolved_limit} ...""")
)
```

- `resolved_limit` saat ini computed internally → aman
- Tapi kalau di-refactor dan jadi user-input → SQL injection vector
- **Recommendation**: Ganti ke parameterized: `LIMIT :record_limit`

### 7.2 Tidak Ada Rate Limit per Operation Type

- Rate limiter hanya track jumlah messages total
- "Generate 1000 payslips" = 1 message tapi sangat expensive
- Bisa di-abuse untuk resource exhaustion

**Recommendation**: Weight-based rate limiting — payslip generation = 10 credits, simple question = 1 credit.

### 7.3 Tidak Ada Audit Trail untuk Data Access

- Tidak ada log siapa access data siapa, kapan
- Untuk GDPR/compliance, ini wajib
- Terutama untuk payroll data (financial PII)

### 7.4 PII Leakage di Cross-Employee Scenario

- PII scanner mask email yang bukan milik current user
- Tapi tidak detect nama orang lain di response content
- Kalau agent hallucinate data karyawan lain, PII scanner bisa miss

### 7.5 Session Context Trust

- Orchestrator trust `session.company_id` tanpa re-verify
- Jika middleware compromised → bisa serve data company lain
- Recommendation: Final-mile verification di agent level

---

## 8. Scalability

**Severity: LOW-MEDIUM** — Belum masalah di volume saat ini, tapi akan jadi bottleneck.

### 8.1 Linear Rule Matching

- `company_agent._load_company_rules()` load SEMUA active rules lalu rank di memory
- 100+ policies = megabytes data di memory per request
- Recommendation: Vector search + LIMIT di DB level, bukan load-all-then-filter

### 8.2 Embedding Generation Tidak Rate-Limited

- Setiap unique message trigger embedding API call
- Tidak ada circuit breaker yang persist state
- High traffic bisa exceed provider rate limit

### 8.3 Grounding Message Size Explosion

- 4 history items × 400 chars = +1,600 chars added ke message
- Semantic router di-train dengan message pendek → accuracy drop untuk message panjang
- Recommendation: Summarize history instead of raw prepend

---

## 9. Multi-Language Support

**Severity: LOW** — Tergantung target market.

### 9.1 Current Language Coverage

| Component | Indonesian | English | Others |
|-----------|-----------|---------|--------|
| Month parsing | ✅ | ✅ Partial | ❌ |
| Intent keywords | ✅ | ❌ Partial | ❌ |
| Standalone signals | ✅ | ❌ Partial | ❌ |
| Referential markers | ✅ | ❌ | ❌ |
| Profanity detection | ✅ | ✅ Partial | ❌ |
| Response templates | ✅ | ❌ | ❌ |
| Date format parsing | ✅ "Januari" | ✅ "January" | ❌ |

### 9.2 Missing

- i18n framework untuk response templates
- Language detection per message
- Locale-aware date/currency formatting
- Multi-script keyword matching (CJK, Arabic, etc.)

---

## 10. Logging & Observability

**Severity: MEDIUM**

### 10.1 Missing Telemetry Points

| Decision Point | Logged? | Should Log |
|----------------|---------|------------|
| Grounding decision (used/skipped) | ✅ Trace | ✅ |
| Topic domain detection | ❌ | Which domain detected, confidence |
| Period inheritance | ❌ | What was inherited, from which message |
| Cache hit/miss | ❌ | Hit rate, TTL remaining |
| Embedding generation time | ❌ | Latency per call |
| Provider failure reason | ❌ Partial | Exact error type (timeout/rate-limit/parse) |
| Sensitive case detection | ❌ | Category, keywords matched, confidence |
| DB query latency | ❌ | Per-query timing |
| PII masking actions | ❌ | What was masked, why |

### 10.2 Tracing Tanpa Detail

- `AgentTraceStep` hanya capture `agent`, `status`, `detail` string
- Tidak structured — tidak bisa query "semua cases dimana grounding menyebabkan misclassification"
- Recommendation: Structured trace events dengan typed fields

---

## 11. Priority Matrix

| # | Improvement | Severity | Effort | Priority |
|---|------------|----------|--------|----------|
| 1 | ~~Standalone signals untuk sensitive/report~~ | ~~HIGH~~ | ~~LOW~~ | ✅ Done |
| 2 | ~~Topic-divergence detection~~ | ~~HIGH~~ | ~~LOW~~ | ✅ Done |
| 3 | ~~HR agent domain signals update~~ | ~~HIGH~~ | ~~LOW~~ | ✅ Done |
| 4 | Explicit context reset detection ("ganti topik") | HIGH | LOW | **P0** |
| 5 | Escalated conversation follow-up mode | HIGH | MEDIUM | **P0** |
| 6 | Grounded response generation (angka harus dari DB) | HIGH | MEDIUM | **P0** |
| 7 | Selective period inheritance (per-intent) | HIGH | MEDIUM | **P1** |
| 8 | Hallucination checker: absolute tolerance for salary | HIGH | LOW | **P1** |
| 9 | Silent failure → explicit error reason | MEDIUM | MEDIUM | **P1** |
| 10 | LIMIT parameter parameterization | MEDIUM | LOW | **P1** |
| 11 | Cache invalidation endpoint | MEDIUM | LOW | **P1** |
| 12 | Confidence-based history suppression | MEDIUM | LOW | **P2** |
| 13 | Time-based context decay | MEDIUM | LOW | **P2** |
| 14 | Structured trace events | MEDIUM | MEDIUM | **P2** |
| 15 | Per-operation rate limiting | MEDIUM | MEDIUM | **P2** |
| 16 | Data access audit trail | MEDIUM | MEDIUM | **P2** |
| 17 | Configurable thresholds (per-company) | MEDIUM | HIGH | **P3** |
| 18 | Multi-language support | LOW | HIGH | **P3** |
| 19 | Rule pagination / vector pre-filter | LOW | MEDIUM | **P3** |
| 20 | Embedding rate limiter + circuit breaker | LOW | MEDIUM | **P3** |
