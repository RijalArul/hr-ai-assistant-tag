# Rencana Upgrade Fungsional HR Consultant untuk HR.ai

Dokumen ini merangkum arah improvement fungsional HR.ai dari chatbot HR berbasis Q&A menjadi sistem yang lebih mirip "HR consultant" digital untuk employee dan platform orkestrasi operasional untuk tim HR.

Dokumen ini adalah rencana perubahan produk dan arsitektur, bukan deskripsi fitur yang sudah aktif penuh di repository saat ini.

## Status Saat Ini

Saat ini HR.ai sudah punya fondasi yang cukup kuat untuk:
- auth dan trusted session context
- HR data retrieval berbasis employee scope
- company policy dan company structure retrieval
- guardrail dasar untuk jalur sensitif
- action engine untuk beberapa workflow
- conversations API dan OpenAI-compatible surface

Namun perilaku produk saat ini masih dominan sebagai:
- HR Q&A assistant
- structured data retriever
- basic workflow trigger

Artinya, HR.ai sudah bisa menjawab dan mengambil data, tetapi belum sepenuhnya bertindak sebagai:
- company navigator
- policy reasoner berbasis kasus
- employee guidance assistant
- HR workflow brain untuk follow-up operasional yang lebih kaya

## Arah Perubahan

Perubahan yang dituju adalah:

> HR.ai bergerak dari static HR Q&A assistant menjadi AI-powered employee support and HR operations platform.

Versi positioning singkat:

> HR.ai = Employee Assistant + Policy Reasoner + HR Workflow Orchestrator

Versi positioning yang lebih operasional:
- untuk employee, HR.ai menjadi pintu masuk tunggal untuk bertanya, memahami policy, cek data, minta bantuan, dan mendapat langkah berikutnya
- untuk tim HR, HR.ai menjadi mesin triage, task orchestration, dan operational visibility

## Masalah yang Ingin Diselesaikan

Problem utama yang ingin dipecahkan oleh perubahan ini:
- employee sering tahu pertanyaannya, tetapi tidak tahu harus mulai dari mana atau harus ke siapa
- policy perusahaan sering ada, tetapi sulit dipetakan ke kasus spesifik employee
- request operasional HR sering masuk dalam bentuk chat bebas yang tidak terstruktur
- topik sensitif butuh jalur aman dan tidak boleh diperlakukan seperti request operasional biasa
- tim HR sering harus membaca percakapan panjang sebelum bisa mengambil tindakan

## Target Functional Shift

Secara fungsional, HR.ai perlu naik kelas dari:
- menjawab pertanyaan

menjadi:
- memahami konteks employee
- memberi guidance yang bisa ditindaklanjuti
- melakukan reasoning atas policy dan eligibility
- mengarahkan employee ke PIC atau jalur yang tepat
- mengubah percakapan menjadi workflow yang terstruktur
- tetap aman untuk kasus sensitif dan keputusan high-impact

## Pilar Capability Target

### 1. Company Navigation Assistant

HR.ai membantu employee tahu harus tanya ke siapa berdasarkan konteks masalahnya, bukan hanya title formal.

Contoh target use case:
- "Kalau mau nanya payroll ke siapa?"
- "Kalau ada issue teknis internal, harus ke siapa dulu?"
- "Kalau mau referral hiring, siapa PIC yang tepat?"

Output ideal:
- PIC utama
- alternatif PIC
- channel yang disarankan
- data atau dokumen yang perlu disiapkan sebelum kontak

### 2. Employee Decision Support

HR.ai membantu employee saat menghadapi keputusan sensitif atau penting.

Contoh target use case:
- resign intention
- burnout atau kebingungan kerja
- konflik dengan atasan
- pertanyaan tentang mutasi atau internal move

Perilaku target:
- tidak auto-execute proses formal terlalu cepat
- validasi konteks secara netral
- sarankan langkah awal yang aman
- arahkan ke manusia yang tepat

### 3. Policy Reasoning Engine

HR.ai tidak hanya mencari policy, tetapi melakukan reasoning terhadap kasus spesifik employee.

Contoh target use case:
- reimbursement psikolog online
- reimbursement kacamata
- benefit interpretation
- leave eligibility
- allowance interpretation

Output ideal:
- relevant policy
- kemungkinan eligible / tidak / perlu verifikasi
- alasan reasoning
- limit, constraint, atau syarat
- dokumen yang perlu disiapkan
- next action

### 4. Employee Self-Service and Conversational Requests

HR.ai menjadi pintu masuk natural-language untuk:
- cek data personal
- request dokumen
- ajukan cuti
- ajukan reimbursement
- update data tertentu

Perilaku target:
- AI mengumpulkan informasi yang kurang
- memvalidasi data minimal
- membuat request formal di backend
- meneruskan ke workflow approval atau review

### 5. HR Workflow Orchestration

Percakapan yang perlu tindak lanjut harus diubah menjadi objek kerja yang terstruktur untuk tim HR.

Output target untuk HR:
- ringkasan kasus
- kategori
- urgency
- suggested PIC
- status
- rekomendasi tindakan

### 6. Safe and Controlled HR Operations

Semua automation tetap harus dijaga dengan guardrail.

Cakupan:
- sensitive case handling
- manual review untuk kasus tertentu
- audit trail
- SLA dan escalation
- configurable automation

## Response Mode yang Perlu Diperkenalkan

Supaya perilaku sistem lebih productized, jawaban HR.ai tidak cukup dibedakan hanya dengan intent. Kita juga perlu response mode.

Mode yang disarankan:
- `informational`
  Untuk jawaban faktual atau retrieval biasa.
- `guidance`
  Untuk jawaban yang menuntun user ke PIC, jalur, atau langkah berikutnya.
- `policy_reasoning`
  Untuk jawaban berbasis kasus dan rule interpretation.
- `workflow_intake`
  Untuk request yang perlu diubah menjadi task atau request formal.
- `sensitive_guarded`
  Untuk topik sensitif yang harus dijawab secara hati-hati dan tidak langsung diautomasi.
- `hr_ops_summary`
  Untuk ringkasan yang ditujukan ke dashboard atau task queue internal HR.

## Workstream Upgrade

### Workstream A - Product and Capability Blueprint

Tujuan:
- menyelaraskan positioning, domain capability, dan batas modul

Area yang perlu di-update:
- `README.md`
- `docs/architecture/phase-7-product-capability-blueprint-id.md`
- `docs/architecture/phase-3-agent-architecture.md`
- `docs/architecture/phase-3-workflow-id.md`
- `docs/architecture/phase-3-semantic-routing-id.md`
- roadmap dan capability docs turunan bila perlu

Output:
- capability matrix
- functional glossary
- module boundaries
- response mode taxonomy

### Workstream B - Intent, Route, and Decision Taxonomy

Tujuan:
- memisahkan jenis kebutuhan employee dengan lebih jelas

Update yang dibutuhkan:
- intent taxonomy baru
- route selection yang tidak hanya keyword-based
- response mode resolution
- next best action selection

Kategori baru yang perlu lebih eksplisit:
- question
- guidance request
- policy reasoning request
- workflow request
- sensitive report
- decision support

Area yang kemungkinan kena update:
- orchestrator
- semantic routing examples
- agent capability definitions

### Workstream C - Company Navigation and Internal Routing

Tujuan:
- menjadikan HR.ai internal company navigator

Update yang dibutuhkan:
- functional owner mapping
- responsibility route mapping
- PIC utama dan alternatif
- channel recommendation
- required preparation checklist

Kemungkinan data model tambahan:
- `functional_owners`
- `department_contacts`
- `responsibility_routes`

Area yang kemungkinan kena update:
- `company-agent`
- seed data company structure
- semantic examples dan capability samples

### Workstream D - Policy Reasoning

Tujuan:
- naik dari policy retrieval menjadi case-based reasoning

Update yang dibutuhkan:
- ekstraksi variable kasus
- penandaan metadata policy yang lebih terstruktur
- eligibility reasoning
- limit and constraint reasoning
- document requirement reasoning

Area yang kemungkinan kena update:
- `company-agent`
- policy data model / policy metadata
- response synthesis format
- seed `company_rules`

### Workstream E - Sensitive Intent Handling

Tujuan:
- menangani topik high-impact dengan jalur yang lebih aman

Kategori target:
- resignation intention
- burnout / emotional distress
- manager conflict
- unsafe workplace
- harassment / discrimination

Update yang dibutuhkan:
- sensitivity taxonomy yang lebih granular
- guarded response templates
- escalation rules
- manual review policies

Area yang kemungkinan kena update:
- orchestrator
- guardrail config
- action rules
- dashboard triage logic

### Workstream F - Conversational Request Intake

Tujuan:
- mengubah chat menjadi pintu masuk universal untuk request HR

Contoh target:
- leave request
- reimbursement request
- document request
- profile update request

Update yang dibutuhkan:
- request schema
- missing-info collection
- minimum validation rules
- task / action creation path

Area yang kemungkinan kena update:
- orchestrator
- conversations service
- action engine
- actions API and docs

### Workstream G - HR Operations Layer

Tujuan:
- memperkuat sisi HR team, bukan hanya employee chat

Kemampuan target:
- structured task queue
- triage
- SLA
- escalation
- suggested PIC
- case summary
- progress tracking

Area yang kemungkinan kena update:
- dashboard requirements
- action engine models
- admin workflow docs
- future web implementation

### Workstream H - Audit, Analytics, and Governance

Tujuan:
- memastikan sistem enterprise-ready dan mudah dioperasikan

Kemampuan target:
- full audit trail
- reasoning trace
- SLA compliance insight
- request volume analytics
- sensitive case analytics
- operational bottleneck insight

Area yang kemungkinan kena update:
- guardrail logs
- action logs
- analytics event design
- dashboard metrics requirements

### Workstream I - AI Quality, Retrieval, and Runtime Reliability

Tujuan:
- meningkatkan kualitas jawaban AI secara teknis, bukan hanya secara fungsional

Kemampuan target:
- hybrid retrieval untuk semantic + lexical matching
- metadata-aware retrieval untuk policy dan routing
- context packing / evidence packing yang lebih rapi
- evaluation harness untuk routing, retrieval, dan reasoning quality
- caching, resilience, dan provider fallback yang lebih stabil
- workflow runtime yang lebih aman untuk request dan automation

Area yang kemungkinan kena update:
- `apps/api/app/services/semantic_router.py`
- `apps/api/app/services/embeddings.py`
- `apps/api/app/agents/orchestrator.py`
- `apps/api/app/agents/company_agent.py`
- `apps/api/app/services/conversations.py`
- `apps/api/app/services/action_engine.py`
- scripts sinkronisasi embedding dan rule chunks
- observability / trace / metrics docs

## Area Repository yang Perlu Di-update

Supaya perubahannya tidak terlalu abstrak, berikut area repo yang kemungkinan besar terdampak:

### Docs and Positioning
- `README.md`
- `docs/architecture/phase-7-product-capability-blueprint-id.md`
- `docs/architecture/phase-3-agent-architecture.md`
- `docs/architecture/phase-3-workflow-id.md`
- `docs/architecture/phase-3-semantic-routing-id.md`
- docs blueprint tambahan jika dibutuhkan

### Backend Models and Routing
- `apps/api/app/models/agent_architecture.py`
- `apps/api/app/agents/orchestrator.py`
- semantic routing data dan capability examples

### Retrieval and Runtime Quality
- `apps/api/app/services/semantic_router.py`
- `apps/api/app/services/embeddings.py`
- `apps/api/app/services/provider_health.py`
- scripts sinkronisasi embeddings dan rule chunks
- context synthesis dan answer planning di orchestrator

### Company Navigation and Policy
- `apps/api/app/agents/company_agent.py`
- seed data untuk structure, rules, dan routing examples

### Employee Data and Request Intake
- `apps/api/app/agents/hr_data_agent.py`
- `apps/api/app/services/conversations.py`
- `apps/api/app/services/action_engine.py`

### Guardrails and Sensitive Handling
- `apps/api/app/guardrails/`
- routes dan docs untuk operational handling

### Dashboard and Ops Surface
- `apps/web/`
- dashboard / queue / analytics planning docs

### Testing
- `apps/api/tests/`
- skenario routing
- skenario policy reasoning
- skenario sensitive handling
- skenario workflow intake

## Fase Delivery yang Disarankan

### Phase 0 - Product Alignment

Tujuan:
- menyepakati capability map, terminology, dan module boundaries

Output:
- capability blueprint
- feature matrix
- intent / route / response mode taxonomy

### Phase 1 - Company Navigation Foundation

Tujuan:
- membangun company navigator dan actionable guidance dasar

Output:
- internal routing by function
- PIC suggestion
- channel recommendation
- preparation checklist

### Phase 2 - Policy Reasoning Foundation

Tujuan:
- membangun policy interpretation by case

Output:
- eligibility reasoning
- structured response untuk policy cases
- benefit and reimbursement reasoning awal

### Phase 3 - Sensitive Decision Support

Tujuan:
- membangun jalur aman untuk high-impact employee intent

Output:
- guarded response flow
- resignation / wellbeing / conflict handling
- review and escalation rules

### Phase 4 - Conversational Request Intake

Tujuan:
- menjadikan chat sebagai pintu masuk workflow formal

Output:
- conversational leave/reimbursement/document request
- missing-info collection
- task creation / request object creation

### Phase 5 - HR Operations Layer

Tujuan:
- memperkuat dashboard dan task handling untuk tim HR

Output:
- structured queue
- triage
- status management
- SLA and escalation

### Phase 6 - Governance and Analytics

Tujuan:
- melengkapi auditability dan operational insight

Output:
- audit completeness
- analytics surfaces
- insight and compliance readiness

## Progress Implementasi per Session

Catatan:
- checklist `[x]` di bagian ini berarti slice awalnya sudah ada di codebase
- beberapa item yang dicentang masih bisa diperdalam lagi pada session berikutnya
- backlog detail tetap memakai `TODO Master List` di bawah

### Session 2026-04-04

Yang sudah dikerjakan pada session ini:
- [x] Menambahkan `request_category` dan `response_mode` ke contract orchestrator
- [x] Menambahkan rule dasar `recommended_next_steps` per response mode
- [x] Memperluas guidance routing untuk topik HR, payroll/benefits, recruiter/TA, HRBP, dan IT support
- [x] Menambahkan data model `responsibility_routes` untuk functional owner routing awal
- [x] Menambahkan mapping PIC utama dan alternatif untuk recruiting, payroll/benefits, HRBP, HR operations, dan IT support
- [x] Menambahkan `recommended_channel` dan `preparation_checklist` pada company guidance output
- [x] Menambahkan seed demo owner fungsional untuk HR ops, payroll/benefits, recruiter/TA, HRBP, dan IT support
- [x] Menambahkan seed/examples untuk use case guidance routing dan reimbursement policy reasoning
- [x] Menambahkan policy reasoning dasar untuk reimbursement mental health dan optical
- [x] Menambahkan reasoning state `eligible`, `not_eligible`, dan `needs_review` untuk policy case dasar
- [x] Memisahkan `decision_support` dari `sensitive_report` pada taxonomy dasar
- [x] Menambahkan targeted tests untuk guidance routing, workflow intake, policy reasoning, dan sensitive decision support
- [x] Memperbaiki bug agar output `not_eligible` tidak lagi menyarankan ajukan klaim atau menampilkan estimasi reimbursement yang kontradiktif
- [x] Mempersempit false positive policy routing agar kalimat seperti update kondisi biasa tidak terlalu mudah jatuh ke `company_policy`
- [x] Menyelaraskan positioning README agar HR.ai konsisten diposisikan sebagai employee support dan HR operations platform
- [x] Menambahkan capability blueprint ringkas untuk capability matrix, glossary, response mode, dan module boundaries
- [x] Menyinkronkan docs Phase 3 agar selaras dengan `request_category`, `response_mode`, dan boundary layer terbaru
- [x] Menambahkan template guarded response yang berbeda untuk resign, burnout, manager conflict, unsafe workplace, dan harassment/discrimination
- [x] Menambahkan policy matrix sensitif untuk membedakan kasus yang hanya guidance vs yang membuat task formal
- [x] Menghubungkan unsafe workplace dan harassment/discrimination ke rule `sensitivity_detected` dengan delivery `manual_review`
- [x] Menambahkan metadata `sensitive_handling` dan targeted tests untuk policy/action sensitive per kategori

Yang masih terbuka besar untuk session berikutnya:
- [ ] Perluasan functional owner / responsibility routing ke cakupan yang lebih granular dan non-demo
- [ ] Structured policy metadata untuk employee level, frequency, dan constraint reasoning yang lebih deterministik
- [ ] Conversational request intake yang benar-benar membuat request formal lintas use case
- [x] Retrieval quality upgrade, evaluation harness, dan runtime hardening
- [ ] HR operations layer, analytics, dan governance surfaces

### Session F - AI Quality and Retrieval Reliability

Yang sudah dikerjakan pada session ini:
- [x] Mengubah retrieval intent dan capability dari fallback vector-or-lexical menjadi hybrid scoring (vector×0.70 + lexical×0.30) dengan per-signal discount
- [x] Menambahkan `context_hint` parameter ke `retrieve_intent_candidates()` untuk metadata-aware boosting pada policy_reasoning, guidance, dan hr_data
- [x] Memperbaiki `chunk_text()` agar berbasis section heading Markdown terlebih dahulu sebelum sliding window karakter
- [x] Reranking implicit melalui blended score di `_merge_hybrid_intent_candidates()` dan `_merge_hybrid_capability_candidates()`
- [x] Menambahkan tiga cache baru: `query_embeddings` (512 entries, 10 menit), `retrieval_results_intent` (256 entries, 2 menit), `retrieval_results_capability` (256 entries, 2 menit)
- [x] Menambahkan `ignore_provider_flag=True` ke `generate_embedding()` agar embedding retrieval tetap jalan saat provider classifier dimatikan
- [x] Menambahkan `_pack_agent_message()` di orchestrator dengan labeled sections [USER REQUEST], [CONVERSATION HISTORY], [ATTACHMENT CONTENT]
- [x] Membuat `scripts/eval_routing.py` dengan 50+ test case, per-intent F1, threshold sensitivity table, dan calibration recommendation
- [x] Action execution hardening: atomic IN_PROGRESS claim, FAILED status on error, idempotency guards untuk IN_PROGRESS dan FAILED
- [x] Update `FakeAsyncSession` di test suite untuk support `rowcount` dan status constraint pada atomic claim

Yang masih terbuka besar untuk session berikutnya:
- [ ] Perluasan functional owner / responsibility routing ke cakupan yang lebih granular dan non-demo
- [ ] Structured policy metadata untuk employee level, frequency, dan constraint reasoning yang lebih deterministik
- [ ] Conversational request intake yang benar-benar membuat request formal lintas use case
- [ ] HR operations layer, analytics, dan governance surfaces

## Pembagian Session yang Disarankan

Bagian ini dipakai untuk membagi backlog ke beberapa session kerja agar tidak saling tumpang tindih terlalu besar.

### Session A - Baseline Taxonomy and Guidance

Status:
- selesai pada session 2026-04-04

Objective:
- membangun fondasi taxonomy, response mode, guidance output, dan policy reasoning awal

In Scope:
- TODO B.1
- TODO B.2
- TODO B.3
- TODO B.4
- TODO C.3
- TODO C.4
- TODO D.3
- TODO D.5
- TODO E.1
- TODO J.1
- TODO J.2
- TODO J.3
- TODO J.4

Out of Scope:
- data model functional owner yang lebih granular
- policy metadata yang lebih terstruktur
- request intake lintas use case yang lengkap
- dashboard HR dan analytics

Files Likely Touched:
- `apps/api/app/agents/orchestrator.py`
- `apps/api/app/agents/company_agent.py`
- `apps/api/app/models/agent_architecture.py`
- `apps/api/app/services/conversations.py`
- `apps/api/tests/test_conversations_api.py`
- `scripts/seed.py`

Definition of Done:
- contract orchestrator punya `request_category` dan `response_mode`
- guidance route menghasilkan next steps yang lebih actionable
- policy reasoning dasar untuk reimbursement awal sudah tersedia
- ada targeted tests untuk guidance, workflow intake, policy reasoning, dan sensitive handling

Catatan:
- session ini menjadi fondasi untuk session-session berikutnya

### Session B - Company Navigation Data Model

Status:
- selesai pada session 2026-04-04

Objective:
- menjadikan company guidance tidak lagi bergantung hanya pada head department, tetapi pada owner fungsi yang lebih relevan

In Scope:
- TODO C.1
- TODO C.2
- TODO C.5

Out of Scope:
- policy reasoning yang lebih dalam
- perubahan besar ke action engine
- dashboard HR

Files Likely Touched:
- `apps/api/app/agents/company_agent.py`
- `scripts/seed.py`
- model data company structure / routing bila diperlukan
- `apps/api/tests/test_conversations_api.py`

Definition of Done:
- ada model routing owner fungsi yang bisa membedakan payroll, benefits, recruiter/TA, HRBP, dan IT support
- guidance output bisa memberi PIC utama dan alternatif bila tersedia
- seed demo punya data owner yang cukup untuk skenario guidance utama
- targeted tests membuktikan mapping guidance tidak lagi sekadar fallback ke head department

Catatan dependency:
- session ini sekarang bisa dianggap closed untuk kebutuhan handoff lintas chat
- session berikutnya bisa lanjut ke Session C atau Session D tanpa perlu membuka scope Session B lagi, kecuali memang ingin refactor company navigation lebih jauh

### Session C - Policy Reasoning Deepening

Status:
- next recommended

Objective:
- memperdalam policy reasoning dari slice reimbursement awal menjadi reasoning yang lebih deterministik dan lebih mudah dikalibrasi

In Scope:
- TODO D.1
- TODO D.2
- TODO D.4

Out of Scope:
- request intake formal
- dashboard HR
- retrieval overhaul besar

Files Likely Touched:
- `apps/api/app/agents/company_agent.py`
- `scripts/seed.py`
- policy metadata / rule structure
- `apps/api/tests/test_conversations_api.py`

Definition of Done:
- policy metadata punya struktur yang lebih eksplisit untuk amount, frequency, level, dokumen, dan constraint
- reasoning bisa menangani lebih banyak skenario benefit/policy selain slice awal
- output reasoning tetap konsisten untuk `eligible`, `not_eligible`, dan `needs_review`
- targeted tests mencakup skenario policy tambahan yang relevan

Catatan dependency:
- sebaiknya tidak dikerjakan paralel dengan Session B karena write scope-nya banyak overlap

### Session D - Sensitive Intent Handling

Status:
- selesai pada session 2026-04-04

Objective:
- memperkaya guarded response untuk resign, burnout, conflict, unsafe workplace, dan harassment

In Scope:
- TODO E.2
- TODO E.3
- TODO E.4

Out of Scope:
- request queue/dashboard HR
- retrieval overhaul
- perubahan data model company navigation

Files Likely Touched:
- `apps/api/app/agents/orchestrator.py`
- `apps/api/app/guardrails/`
- `apps/api/tests/`

Definition of Done:
- ada template respons yang berbeda untuk resign, burnout, conflict, unsafe workplace, dan harassment
- rule mana yang hanya guidance, mana yang create task, dan mana yang wajib manual review terdokumentasi dan teruji
- guardrail sensitif tidak lagi terasa seperti satu jalur generic yang sama untuk semua kasus

Catatan dependency:
- bisa dikerjakan terpisah dari Session B dan Session C selama perubahan taxonomy inti tidak diubah lagi

### Session E - Conversational Request Intake

Status:
- baseline implemented
- perlu perluasan use case dan penyelarasan intent taxonomy agar tidak hanya bertumpu pada slice yang ada sekarang

Objective:
- membuat chat benar-benar bisa menghasilkan request formal lintas use case

In Scope:
- TODO F.1
- TODO F.2
- TODO F.3
- TODO F.4

Out of Scope:
- dashboard HR penuh
- analytics/governance
- policy metadata yang dalam

Files Likely Touched:
- `apps/api/app/services/conversations.py`
- `apps/api/app/services/action_engine.py`
- `apps/api/app/agents/orchestrator.py`
- model request / action
- `apps/api/tests/test_conversations_api.py`

Definition of Done:
- leave, reimbursement, document request, atau profile update punya schema request yang jelas
- chat flow bisa mengumpulkan informasi yang kurang sebelum membuat request
- ada minimum validation sebelum object request/action dibuat
- ada targeted tests untuk conversational request intake

Catatan status saat ini:
- document request baseline tetap berjalan lewat payload `document_generation` yang sudah dipakai flow payslip
- schema payload untuk `leave_request`, `reimbursement_request`, dan `profile_update_request` sudah ada di backend
- flow missing-info collection dan minimum validation dasar sudah berjalan untuk slice intent yang sekarang dipakai conversation flow
- linked action creation sudah terhubung ke action engine, tetapi coverage use case formalnya masih perlu diperluas dan dirapikan lagi

Catatan dependency:
- lebih aman dikerjakan setelah Session A selesai
- bisa jalan paralel dengan Session D jika ownership file dibatasi jelas

### Session F - AI Quality and Retrieval Reliability

Status:
- selesai

Objective:
- meningkatkan kualitas AI secara teknis dan menyiapkan fondasi evaluasi yang lebih terukur

In Scope:
- TODO I.1
- TODO I.2
- TODO I.3
- TODO I.4
- TODO I.5
- TODO I.6
- TODO I.7
- TODO I.8
- TODO I.9
- TODO I.10

Out of Scope:
- perubahan product copy/docs besar
- dashboard HR

Files Likely Touched:
- `apps/api/app/services/semantic_router.py`
- `apps/api/app/services/embeddings.py`
- `apps/api/app/agents/orchestrator.py`
- `apps/api/app/services/conversations.py`
- sync scripts / eval scripts

Definition of Done:
- retrieval intent/capability lebih stabil daripada pola fallback sekarang
- ada eval harness minimal untuk routing/retrieval/reasoning
- ada improvement konkret pada context packing atau caching/runtime safety
- perubahan quality bisa diukur lewat test/eval, bukan hanya observasi manual

Catatan dependency:
- bisa mulai setelah Session A
- kalau menyentuh orchestrator besar-besaran, koordinasikan dengan Session D dan Session E

### Session G - HR Operations Layer

Status:
- baseline backend implemented
- UI triage/dashboard masih partial dan perlu penyelarasan lebih lanjut agar sepenuhnya sesuai requirement dashboard

Objective:
- membangun sisi HR team, task queue, triage, dan SLA handling

In Scope:
- TODO G.1
- TODO G.2
- TODO G.3
- TODO G.4
- TODO G.5

Out of Scope:
- retrieval/policy reasoning core
- docs alignment umum

Files Likely Touched:
- `apps/web/`
- `apps/api/app/services/action_engine.py`
- docs admin workflow

Definition of Done:
- ada definisi task queue dan summary task yang usable untuk tim HR
- urgency, suggested PIC, suggested next action, SLA, dan escalation punya model yang konsisten
- kebutuhan dashboard HR terdokumentasi cukup jelas untuk implementasi lanjut

Catatan status saat ini:
- model action dan migration backend sudah punya `priority`, `suggested_pic`, `suggested_next_action`, `sla_hours`, dan `escalation_rule`
- halaman dashboard HR dasar dan action detail sudah ada di `apps/web`, tetapi surface triage yang kaya masih belum lengkap
- penyelarasan UI dengan kontrak action execution masih perlu dijaga supaya tidak drift dari API

Catatan dependency:
- paling ideal setelah Session E mulai membentuk request/task object yang stabil

### Session H - Audit, Analytics, and Governance

Status:
- later phase

Objective:
- melengkapi observability, audit trail, dan governance layer

In Scope:
- TODO H.1
- TODO H.2
- TODO H.3
- TODO H.4
- TODO J.5

Out of Scope:
- implementasi dashboard employee-facing
- redesign besar orchestrator taxonomy

Files Likely Touched:
- `apps/api/app/guardrails/`
- action logs / trace models
- analytics docs / metrics design

Definition of Done:
- routing, reasoning, recommendation, approval, dan escalation punya jejak audit yang cukup
- analytics operasional utama sudah didefinisikan
- boundary logging untuk sensitive case lebih aman
- ada skenario end-to-end minimal dari chat sampai task/audit trail

Catatan dependency:
- paling ideal setelah Session D, Session E, dan Session G mulai stabil

### Session I - Product and Docs Alignment

Status:
- selesai pada session 2026-04-04

Objective:
- merapikan positioning, capability blueprint, glossary, dan module boundaries

In Scope:
- TODO A.1
- TODO A.2
- TODO A.3
- TODO A.4

Out of Scope:
- perubahan runtime/backend logic
- refactor orchestrator atau agent implementation

Files Likely Touched:
- `README.md`
- `docs/architecture/phase-7-product-capability-blueprint-id.md`
- `docs/architecture/phase-3-agent-architecture.md`
- `docs/architecture/phase-3-workflow-id.md`
- `docs/architecture/phase-3-semantic-routing-id.md`
- `docs/architecture/phase-7-hr-consultant-functional-upgrade-id.md`

Definition of Done:
- positioning produk konsisten di README dan docs
- capability blueprint, glossary, dan module boundaries terdokumentasi jelas
- dokumen cukup ringkas dan bisa dipakai sebagai handoff ke chat/session lain

Catatan dependency:
- closed untuk baseline docs alignment
- update docs berikutnya bisa menumpang pada blueprint ini tanpa perlu mendesain ulang istilah dasar

## Rekomendasi Kombinasi Session

Kalau ingin membagi kerja ke beberapa session tanpa konflik besar, kombinasi yang paling aman adalah:

- Session C lalu Session D
- Session D dan Session E bisa lanjut di atas baseline docs Session I yang sudah closed
- Session F jalan sendiri atau setelah Session D dan Session E mulai stabil
- Session G dan Session H dikerjakan belakangan setelah request/task model lebih matang

## TODO Master List

Checklist di bawah ini adalah backlog kerja yang bisa dijalankan bertahap.

Catatan sinkronisasi status:
- checklist `[x]` pada bagian F dan G berarti baseline slice atau fondasi utamanya sudah ada di codebase
- status `baseline implemented` atau `partial` pada Session E dan Session G tetap menjadi sumber kebenaran untuk breadth lanjutan, UX, dan hardening yang belum final

### A. Product and Docs
- [x] Perbarui positioning HR.ai di `README.md` agar tidak lagi hanya terdengar seperti HR Q&A platform
- [x] Tambahkan capability blueprint formal untuk employee support, policy reasoning, workflow orchestration, dan governance
- [x] Definisikan module boundaries antara employee support layer, reasoning layer, dan HR operations layer
- [x] Tambahkan glossary untuk istilah seperti guidance, policy reasoning, workflow intake, dan sensitive guarded response

### B. Intent and Response Taxonomy
- [x] Refactor intent taxonomy agar membedakan informational question, guidance request, policy reasoning request, workflow request, dan sensitive report
- [x] Tambahkan response mode taxonomy ke orchestrator contract
- [x] Definisikan rule penentuan next best action per response mode
- [x] Perluas semantic routing examples agar mewakili use case guidance, policy reasoning, dan conversational request

### C. Company Navigation Assistant
- [x] Tambahkan data model untuk functional owner / responsibility routing
- [x] Tambahkan mapping PIC utama dan alternatif per topik
- [x] Tambahkan rekomendasi channel komunikasi per route
- [x] Tambahkan daftar informasi yang harus disiapkan employee sebelum menghubungi PIC
- [x] Lengkapi seed data untuk HR, payroll, benefits, TA/recruiter, HRBP, dan IT support owner

### D. Policy Reasoning Engine
- [ ] Definisikan struktur metadata policy agar lebih mudah dipakai reasoning
- [ ] Tambahkan ekstraksi variable kasus seperti category, amount, employee level, document requirement, frequency, dan limit
- [x] Definisikan format output policy reasoning yang konsisten
- [ ] Tambahkan skenario reasoning untuk reimbursement, medical claim, optical claim, leave, payroll, dan allowance
- [x] Definisikan kapan output harus `eligible`, `not_eligible`, atau `needs_review`

### E. Sensitive Intent Handling
- [x] Pisahkan resignation intention dari sensitive case reporting biasa
- [x] Tambahkan response template untuk resignation, burnout, conflict, unsafe workplace, dan harassment
- [x] Definisikan kasus mana yang hanya boleh guidance, mana yang bisa create task, dan mana yang wajib manual review
- [x] Review ulang guardrail dan escalation policy untuk jalur sensitif

### F. Conversational Request Intake
- [x] Definisikan schema request untuk leave, reimbursement, document request, dan profile update
- [x] Definisikan missing-info collection flow untuk request berbasis chat
- [x] Tambahkan validation rules minimum sebelum request formal dibuat
- [x] Integrasikan request intake dengan action engine atau request queue yang terstruktur

### G. HR Operations Layer
- [x] Definisikan bentuk structured task queue untuk tim HR
- [x] Tambahkan suggested PIC dan suggested next action pada task summary
- [x] Tambahkan urgency / priority model yang konsisten
- [x] Tambahkan SLA target dan escalation rule per category
- [x] Definisikan kebutuhan dashboard HR untuk triage, review, dan follow-up

### H. Audit, Analytics, and Governance
- [ ] Lengkapi audit trail untuk routing, reasoning, recommendation, approval, dan escalation
- [ ] Definisikan analytics operasional seperti top category, SLA compliance, recurring issue, dan bottleneck
- [ ] Definisikan confidence / trace model yang cukup untuk observability tetapi tidak membebani UX
- [ ] Pastikan semua sensitive case punya boundary logging yang aman

### I. AI Quality and Technical Reliability
- [x] Ubah retrieval intent dan capability dari fallback vector-or-lexical menjadi hybrid retrieval yang lebih stabil
- [x] Tambahkan metadata-aware retrieval untuk policy reasoning dan internal routing
- [x] Perbaiki chunking policy agar berbasis section / heading, bukan hanya potongan karakter mentah
- [x] Tambahkan reranking layer setelah retrieval top-k untuk memilih evidence terbaik
- [x] Tambahkan query embedding cache dan retrieval result cache untuk query yang sering berulang
- [x] Decouple semantic retrieval dari dependency penuh pada provider flag agar kualitas semantic tidak turun terlalu jauh saat provider classifier dimatikan
- [x] Perbaiki context packing agar attachment, history, dan evidence tidak hanya di-concat mentah ke prompt
- [x] Tambahkan evaluation harness untuk routing, retrieval, policy match, false positive, ambiguity, dan answer quality
- [x] Review dan kalibrasi threshold similarity / confidence berdasarkan dataset evaluasi, bukan hanya tuning manual
- [x] Hardening workflow runtime dengan idempotency, retry policy, dan status transition yang lebih ketat untuk auto-generated request atau action

### J. Testing and Validation
- [x] Tambahkan test untuk guidance routing by function
- [x] Tambahkan test untuk policy reasoning by case
- [x] Tambahkan test untuk sensitive decision support flow
- [x] Tambahkan test untuk conversational request intake
- [ ] Tambahkan skenario end-to-end dari employee chat sampai HR task queue

## Prioritas Eksekusi yang Disarankan

Kalau ingin hasil cepat tanpa scope meledak, prioritas yang paling bernilai adalah:

1. Product alignment dan taxonomy
2. AI quality foundation: retrieval, context packing, observability, dan evaluation harness
3. Company Navigation Assistant
4. Actionable guidance output
5. Policy Reasoning Engine
6. Sensitive Intent Handling
7. Conversational Request Intake
8. HR Operations Layer
9. Analytics and governance hardening

### Prioritas Coverage Harian Untuk Employee Support

Bagian ini sengaja lebih sempit dari roadmap besar di atas.
Fokusnya adalah:
- topik yang paling sering muncul dalam operasional kantor sehari-hari
- topik yang paling cepat terasa manfaatnya bagi employee
- topik yang fondasi backend-nya sudah cukup ada sehingga realistis untuk diperdalam lebih dulu

Definisi bucket:
- `Highest`
  Harus diprioritaskan lebih dulu karena frekuensi hariannya tinggi, dampaknya langsung terasa, dan gap saat ini masih cukup jelas di UX atau reasoning.
- `High`
  Penting dan sering dipakai, tetapi urgensinya sedikit di bawah bucket `Highest` atau breadth use case-nya sedikit lebih sempit.
- `Needed`
  Tetap layak di-cover karena membantu employee support platform terasa lengkap, tetapi bukan use case paling harian untuk mayoritas employee.

Definisi status implementasi aktual:
- `Mostly covered`
  Use case utamanya sudah cukup usable di chat, regression test utamanya sudah ada, tetapi coverage belum bisa disebut complete.
- `Partial`
  Fondasi utamanya sudah ada dan beberapa prompt sudah jalan, tetapi behavior belum konsisten atau breadth use case masih sempit.
- `Foundation only`
  Baru ada routing atau guidance dasar; pengalaman end-to-end belum terasa matang.

| Priority | Coverage area | Status implementasi aktual | Contoh pertanyaan harian | Kondisi repo saat ini | Gap utama yang masih tersisa |
| --- | --- | --- | --- | --- | --- |
| `Highest` | Leave dan izin operasional | `Partial` | "izin sakit ke mana", "kalau saya cuti 3 hari sisa saya berapa", "kapan saldo cuti saya nambah", "cuti saya harus di-approve siapa" | saldo dan request snapshot sudah ada, schema `leave_request` sudah ada, simulasi cuti dasar sudah ada, metadata approval chain policy sudah ada | mekanisme izin sakit dan approval guidance belum kaya, pertanyaan accrual masih belum kuat, phrasing operasional harian belum ter-cover merata |
| `Highest` | Attendance correction dan exception handling | `Partial` | "saya lupa check-in", "absensi saya salah", "telat hari ini harus lapor siapa", "WFH hari ini perlu update ke mana" | intent attendance correction, execution gate, dan contact guidance dasar sudah ada | correction flow belum terasa end-to-end, exception handling harian belum kaya, dan follow-up guidance masih tipis |
| `Highest` | Payroll issue explanation sehari-hari | `Mostly covered` | "potongan saya kenapa", "BPJS saya berubah kenapa", "gaji bulan ini kapan cair", "slip saya belum keluar" | explanation per komponen payroll, payment timing, payslip issue, dan mixed guidance ke PIC payroll sudah ada | reasoning historis masih bisa diperdalam, status file payslip masih inferred dari payroll data, dan beberapa skenario payroll issue lanjutan belum kaya |
| `High` | Reimbursement operasional | `Partial` | "cara klaim", "dokumen apa saja", "status klaim saya", "kalau nominal segini eligible nggak" | reasoning reimbursement awal, policy reasoning, dan schema `reimbursement_request` sudah ada | intake end-to-end, status claim, dan guidance dokumen per kasus masih perlu diperdalam |
| `High` | Profile dan employment self-service | `Partial` | "atasan saya siapa", "posisi saya apa", "join date saya kapan", "saya mau update rekening" | pertanyaan profil personal sudah jauh membaik, schema `profile_update_request` dan gate dasar update sudah ada | breadth field update masih sempit, UX self-service update belum matang, dan coverage employment admin belum penuh |
| `High` | Internal routing dan approval guidance | `Partial` | "HR atau atasan dulu", "kalau manager tidak ada saya lapor siapa", "untuk administrasi ini ke mana" | company navigation, responsibility routes, dan alternate PIC dasar sudah ada | belum semua phrasing natural dan skenario backup approver / backup PIC ter-cover |
| `Needed` | Onboarding harian | `Foundation only` | "hari pertama saya harus mulai dari mana", "akses apa yang harus saya punya", "siapa yang guide saya" | guidance dasar dan profile routing untuk guide onboarding sebagian sudah ada | checklist onboarding, role-based next step, dan integrasi lintas fungsi belum matang |
| `Needed` | IT support operasional | `Foundation only` | "reset password", "VPN saya tidak bisa", "akses tool belum aktif" | routing awal ke IT support sudah ada | intake issue teknis, triage detail, dan status follow-up belum dalam |
| `Needed` | Recruiting, referral, HRBP, dan internal move guidance | `Partial` | "mau refer teman ke siapa", "diskusi karier ke siapa", "kalau mau internal move mulai dari mana" | routing dasar, contact guidance, dan responsibility route untuk beberapa topik sudah ada | masih lebih kuat sebagai guidance awal daripada workflow atau case handling yang benar-benar kaya |

Ringkasan praktis:
- Kalau target terdekat adalah "employee assistant yang kepakai tiap hari", bucket `Highest` harus didahulukan.
- Kalau target berikutnya adalah "self-service yang mulai terasa lengkap", bucket `High` menjadi prioritas setelah bucket `Highest` stabil.
- Bucket `Needed` tetap penting untuk melengkapi positioning HR.ai sebagai pintu masuk tunggal employee support, tetapi tidak perlu didahulukan sebelum use case harian paling padat terasa solid.
- Secara status aktual hari ini, area yang paling dekat ke usable harian adalah `Payroll issue explanation`; area lain masih dominan `Partial` atau `Foundation only`.

## Exit Criteria Jangka Menengah

Rencana ini dianggap berhasil mulai bergerak ke arah yang benar jika:
- employee bisa bertanya "harus ke siapa" dan mendapat jawaban yang actionable
- policy answer tidak lagi hanya retrieval, tetapi sudah punya reasoning dasar
- jalur sensitif tidak lagi terasa seperti soft reject generik
- request HR lewat chat bisa diubah menjadi object kerja yang rapi
- tim HR bisa menerima kasus dalam bentuk task summary, bukan hanya transcript

## Ringkasan Penutup

Perubahan ini pada dasarnya menggeser HR.ai dari:
- static HR Q&A

menjadi:
- contextual guidance
- policy reasoning
- secure sensitive handling
- workflow orchestration
- HR operational support

Kalimat singkat yang bisa dipakai untuk menjaga arah produk:

> HR.ai dirancang untuk mengubah HR support dari static Q&A menjadi contextual guidance, secure case handling, dan operational workflow execution.
