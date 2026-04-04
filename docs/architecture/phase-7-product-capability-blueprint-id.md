# Blueprint Kapabilitas Produk HR.ai

Dokumen ini merangkum positioning, capability blueprint, glossary, response mode, dan module boundaries untuk handoff cepat lintas chat atau session.

Detail backlog dan delivery plan tetap ada di:
- `docs/architecture/phase-7-hr-consultant-functional-upgrade-id.md`

## Positioning Singkat

> HR.ai adalah AI-powered employee support and HR operations platform.

Ringkasnya:

> HR.ai = Employee Assistant + Policy Reasoner + HR Workflow Orchestrator

Repositori saat ini sudah menunjukkan fondasi untuk:
- employee-facing conversational entry
- safe personal HR data retrieval
- company navigation guidance untuk topik tertentu
- case-based policy reasoning awal
- rule-driven action creation dan delivery
- trust boundary, guardrail, dan audit-oriented controls

## Capability Matrix

| Pilar | Outcome utama | Bukti repo saat ini | Arah upgrade dekat |
| --- | --- | --- | --- |
| Employee support | Employee bisa bertanya, cek data, minta guidance, dan mulai request dari chat | `orchestrator`, `hr_data_agent`, `company_agent`, `file_agent`, conversations API | self-service lebih luas, missing-info collection, request intake yang lebih kaya |
| Policy reasoning | Policy dijelaskan dalam konteks kasus, bukan hanya dicari sebagai dokumen | `company_agent`, semantic routing, `response_mode=policy_reasoning`, reimbursement slice awal | metadata policy terstruktur, eligibility reasoning lebih deterministik |
| Workflow orchestration | Percakapan yang eligible berubah menjadi object kerja yang bisa dieksekusi atau ditinjau | `action_engine`, rules, actions API, webhooks, linked conversation actions | request formal lintas use case, queue, SLA, suggested PIC |
| Governance and trust | Sistem tetap aman, netral, dan bisa diaudit | auth/session boundary, guardrails, manual review default untuk kasus tertentu, traces | analytics, richer audit trail, governance surface untuk HR |

## Taxonomy Ringkas

### Request category yang sudah ada di contract orchestrator

| Category | Makna ringkas |
| --- | --- |
| `informational_question` | User hanya butuh jawaban faktual atau lookup biasa |
| `guidance_request` | User butuh diarahkan ke PIC, channel, atau langkah berikutnya |
| `policy_reasoning_request` | User butuh interpretasi policy berbasis kasus |
| `workflow_request` | User ingin memulai request atau tindak lanjut formal |
| `sensitive_report` | User melaporkan kasus sensitif yang perlu jalur aman |
| `decision_support` | User sedang menghadapi keputusan penting dan perlu arahan netral |

### Response mode yang sudah ada di contract orchestrator

| Mode | Bentuk jawaban yang diharapkan |
| --- | --- |
| `informational` | Jawaban faktual, retrieval, atau penjelasan ringkas |
| `guidance` | Jawaban yang memberi PIC, channel, checklist, dan next step |
| `policy_reasoning` | Jawaban policy dengan reasoning, eligibility state, constraint, dan next action |
| `workflow_intake` | Jawaban yang mengumpulkan atau memvalidasi data sebelum request formal dibuat |
| `sensitive_guarded` | Jawaban hati-hati untuk topik high-impact, mengutamakan safety dan human handoff |
| `hr_ops_summary` | Ringkasan internal untuk queue, triage, atau dashboard HR |

## Module Boundaries

### Alur besar

```text
Employee / UI / API
  -> Employee Support Layer
  -> Reasoning Layer
  -> HR Operations Layer
  -> Delivery / Review / External Integration
```

Layer trust, auth, dan guardrail melintang di semua tahap di atas.

### 1. Employee Support Layer

Tanggung jawab:
- menerima input employee dari chat, API, atau attachment
- menyusun jawaban yang employee-facing
- menampilkan self-service data, guidance, dan next step
- menjadi entrypoint conversational request

Scope repo saat ini:
- `apps/api/app/agents/orchestrator.py`
- `apps/api/app/agents/hr_data_agent.py`
- `apps/api/app/agents/company_agent.py`
- `apps/api/app/agents/file_agent.py`
- `apps/api/app/services/conversations.py`
- `apps/api/app/api/routes/conversations.py`

Bukan tanggung jawab layer ini:
- lifecycle eksekusi action
- delivery queue dan webhook delivery
- admin queue management

### 2. Reasoning Layer

Tanggung jawab:
- intent detection
- sensitivity assessment
- `request_category` dan `response_mode` resolution
- semantic retrieval dan evidence selection
- policy reasoning dan next-best-action hints

Scope repo saat ini:
- `apps/api/app/models/agent_architecture.py`
- `apps/api/app/agents/orchestrator.py`
- `apps/api/app/agents/company_agent.py`
- `apps/api/app/services/semantic_router.py`
- `apps/api/app/services/embeddings.py`

Batas aman:
- tidak boleh menjadi source of truth untuk identity atau employee scope
- tidak boleh menggantikan structured lookup untuk data HR personal
- tidak boleh men-trigger action formal tanpa boundary dari layer operasi

### 3. HR Operations Layer

Tanggung jawab:
- mengubah hasil percakapan menjadi object kerja terstruktur
- mengeksekusi action yang aman
- mengatur delivery channel, manual review, dan status lifecycle
- menyiapkan permukaan untuk queue, triage, dan follow-up HR

Scope repo saat ini:
- `apps/api/app/services/action_engine.py`
- `apps/api/app/models/action_engine.py`
- `apps/api/app/api/routes/actions.py`
- `apps/api/app/api/routes/rules.py`
- `apps/api/app/api/routes/webhooks.py`

Bukan tanggung jawab layer ini:
- mengklasifikasikan intent percakapan dari nol
- memilih `employee_id` atau `company_id`
- menafsirkan policy tanpa evidence dari upstream layer

### 4. Cross-Cutting Trust and Integration Layer

Tanggung jawab:
- auth, session, dan trusted identity injection
- guardrails, audit, dan sensitive handling boundary
- API key, webhook, cache, storage, dan connector boundary

Scope repo saat ini:
- `apps/api/app/core/`
- `apps/api/app/guardrails/`
- `apps/api/app/services/cache.py`
- `apps/api/app/services/object_storage.py`
- `apps/api/app/services/auth.py`

Aturan utama:
- `employee_id` dan `company_id` selalu datang dari trusted session context, bukan dari LLM

## Glossary

### Guidance

Jawaban yang tidak berhenti di fakta. Output ini mengarahkan employee ke PIC, channel, dokumen yang perlu disiapkan, atau langkah lanjutan yang aman.

### Policy reasoning

Jawaban berbasis policy yang mencoba menilai kasus konkret employee dengan evidence, constraint, dan status seperti `eligible`, `not_eligible`, atau `needs_review`. Ini bukan keputusan final HR yang sepenuhnya otonom.

### Workflow intake

Mode interaksi saat sistem mulai mengumpulkan informasi minimum agar chat bisa berubah menjadi request formal, action, atau task terstruktur.

### Sensitive guarded response

Pola jawaban untuk topik high-impact seperti resign intention, konflik, distress, harassment, atau unsafe workplace. Prioritasnya adalah safety, netralitas, dan human handoff, bukan automation cepat.

### Employee support layer

Lapisan yang langsung berhadapan dengan employee dan menentukan pengalaman percakapan, lookup, guidance, dan next step.

### Reasoning layer

Lapisan yang menentukan bagaimana pesan dipahami: intent, evidence, policy reasoning, sensitivity, dan response shape.

### HR operations layer

Lapisan yang mengubah hasil percakapan menjadi object operasional yang bisa ditinjau, dieksekusi, atau dikirim ke sistem lain.

### Governance and trust

Serangkaian boundary yang menjaga agar sistem tetap aman, bisa diaudit, dan tidak memberikan otomatisasi berlebihan pada kasus berisiko tinggi.

## Handoff Ringkas

Kalau perlu cepat memahami arah repo, baca dalam urutan ini:
- `README.md`
- `docs/architecture/phase-7-product-capability-blueprint-id.md`
- `docs/architecture/phase-3-agent-architecture.md`
- `docs/architecture/phase-3-workflow-id.md`
- `docs/architecture/phase-7-hr-consultant-functional-upgrade-id.md`
