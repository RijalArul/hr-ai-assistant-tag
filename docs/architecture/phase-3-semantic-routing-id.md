# Desain Semantic Routing Phase 3 HR.ai

Dokumen ini menjelaskan desain lanjutan untuk Phase 3 agar classifier tidak terlalu bergantung pada hardcoded keyword. Fokus utamanya adalah memindahkan logika routing dari pola `keyword -> classify -> route` menjadi `semantic retrieval -> LLM judge -> agent routing`.

Dokumen ini adalah proposal arsitektur berikutnya, bukan deskripsi penuh dari runtime yang sudah aktif saat ini.

## Status Saat Ini

Supaya tidak rancu, status repo saat ini dibagi menjadi dua tahap:

- **Stage 1 sudah aktif**:
  - `intent_examples` sudah ada sebagai fondasi semantic routing
  - orchestrator sudah mengambil kandidat intent secara semantic
  - kandidat semantic sudah diteruskan ke MiniMax sebagai judge
  - jika provider gagal, semantic routing bisa menjadi fallback sebelum pesan jatuh ke `out_of_scope`
- **Stage 2 MVP juga sudah aktif**:
  - `agent_capabilities` sudah ada sebagai knowledge base capability untuk agent yang sudah ada
  - orchestrator sudah mengambil kandidat agent secara semantic
  - kandidat capability sudah diteruskan ke MiniMax sebagai judge
  - capability routing bisa mempromosikan route saat classifier biasa masih gagal menangkap konteks
  - `planned_agents` sekarang sudah muncul sebagai bagian dari planning internal orchestrator
- **Stage 2 penuh belum selesai**:
  - provider belum menjadi satu-satunya source of truth untuk execution plan
  - sistem masih sengaja dibatasi pada `hr-data-agent`, `company-agent`, dan `file-agent`

Dengan kata lain, Stage 1 sekarang membuat sistem lebih baik memahami maksud user, sedangkan Stage 2 nanti membuat sistem lebih baik memilih agent yang harus dijalankan.

## Kenapa Desain Ini Diperlukan

Classifier hardcoded punya beberapa kelemahan:
- sensitif terhadap typo seperti `brdasrkan`
- sensitif terhadap phrasing alami user
- cepat membesar jika semua variasi kalimat harus ditambah manual
- terlalu cepat jatuh ke `out_of_scope` saat exact keyword tidak ketemu

Untuk domain HR support, user sering bertanya dengan bahasa yang:
- tidak formal
- campur Indonesia dan Inggris
- singkat dan ambigu
- mengandung intent yang implisit, bukan eksplisit

Karena itu, kita butuh lapisan semantic retrieval lebih dulu sebelum LLM classifier mengambil keputusan.

## Prinsip Utama

Arsitektur ini mengikuti prinsip:
- jangan langsung `out_of_scope` hanya karena exact keyword tidak cocok
- cari dulu kandidat intent dan kandidat agent secara semantic
- gunakan LLM sebagai judge di atas hasil retrieval, bukan classifier dari nol
- tetap pertahankan trust boundary dan session safety
- jalankan agent yang independen secara paralel

## Guardrail Runtime Yang Sudah Ditambahkan

Walaupun routing makin semantic, runtime sekarang tetap menambahkan dua guardrail penting:

### 1. Exact vs semantic precedence

Untuk query personal HR yang sifatnya exact:
- payroll
- attendance
- leave balance / leave request status
- personal profile

semantic routing **boleh membantu memahami intent**, tetapi tidak boleh mengambil alih sumber kebenaran. Query seperti ini tetap harus berakhir di jalur deterministic / structured lookup.

Karena itu orchestrator sekarang menyimpan `query_policy` internal yang membedakan:
- `factual_exact_lookup`
- `temporal_lookup`
- `comparison_lookup`
- `semantic_lookup`
- `ambiguous_lookup`

Dan juga `boundary_mode`, misalnya:
- `must_be_deterministic`
- `deterministic_preferred`
- `semantic_assisted`
- `needs_clarification_or_provider`

Tujuannya supaya semantic capability atau provider judge tidak bisa sembarangan melebarkan query deterministic menjadi route yang tidak perlu.

### 2. Explicit execution intent gate

Intent conversation dan execution intent tidak selalu sama.

Contoh:
- `payslip saya bulan ini bagaimana?` -> topiknya memang `payroll_document_request`
- tapi itu belum tentu berarti user benar-benar ingin sistem membuat action atau generate PDF

Karena itu runtime sekarang membedakan:
- `execution_request`
- `exploratory_request`
- `topic_only`

Action Phase 4 hanya otomatis dibuat untuk request yang benar-benar lolos gate eksekusi eksplisit.

### 3. Conversation grounding and freshness guardrails

Routing semantic sekarang juga diberi dua guardrail tambahan:

- follow-up yang pendek atau referensial seperti `yang tadi`, `itu`, atau `sebelumnya` bisa membawa potongan history percakapan terbaru agar maksud user tetap grounded
- untuk `company_rules`, ranking semantic/keyword sekarang tetap memperhatikan `effective_date`, sehingga versi policy yang lebih baru tidak mudah kalah oleh versi lama yang kebetulan lebih mirip secara lexical atau semantic

## Alur Target

Flow yang diusulkan:

```text
trusted session
  -> optional file-agent
  -> semantic retrieval untuk intent examples
  -> semantic retrieval untuk agent capabilities
  -> LLM judge / classifier
  -> route selection
  -> parallel agent execution
  -> final synthesis
```

Atau lebih detail:

```text
message user
  -> preprocess
  -> retrieve top-k intent examples
  -> retrieve top-k agent candidates
  -> judge dengan LLM
  -> putuskan:
       - primary_intent
       - secondary_intents
       - route
       - confidence
       - sensitivity
  -> jalankan hr-data-agent / company-agent / file-agent / custom agents
  -> gabungkan hasil akhir
```

## Perbedaan Dengan Flow Sekarang

Flow saat ini di repo lebih dekat ke:
- hardcoded heuristics lebih dulu
- provider classifier dipakai kalau local result ambigu
- route diputuskan dari intent enum

Flow usulan ini mengubah pusat gravitasi classifier:
- hardcoded rule tetap ada, tapi hanya sebagai guardrail tipis
- retrieval semantic menjadi pintu utama untuk memahami maksud user
- LLM menghakimi kandidat yang sudah dipersempit retrieval

Jadi ini bukan menghapus hardcode sepenuhnya, tetapi menurunkan perannya dari “mesin utama” menjadi “safety net”.

## Komponen Utama

### 1. Intent Examples

Kita butuh tabel contoh intent yang bisa dicari dengan semantic similarity.

Contoh data:
- `time_off_balance` -> "cuti saya sisa berapa"
- `attendance_review` -> "jam masuk saya rata-rata berapa"
- `payroll_document_request` -> "tolong kirim payslip bulan ini"
- `company_policy` -> "apa aturan carry over cuti"

Tujuan tabel ini:
- memberi contoh natural language untuk tiap intent
- menangkap phrasing yang tidak selalu berbentuk exact keyword
- menjadi knowledge base kecil untuk classifier

### 2. Agent Capabilities

Selain intent, kita juga bisa menyimpan deskripsi kemampuan agent.

Contoh:
- `hr-data-agent` -> payroll, attendance, time off, profile
- `company-agent` -> company rules, structure, policy lookup
- `file-agent` -> attachment extraction
- future custom agents -> attendance analytics, payroll insights, grievance triage

Tujuan tabel ini:
- membantu LLM memilih agent yang paling relevan
- membuat route tidak terlalu dikunci oleh hardcoded mapping saja

Yang penting dipahami: `agent_capabilities` **bukan sekadar daftar tabel database**.

Ia sebaiknya menjelaskan:
- scope bisnis agent
- source data atau tools yang dipakai
- jenis pertanyaan yang cocok
- batas aman kapan agent itu boleh dijalankan
- apakah agent aman dijalankan paralel dengan agent lain

### 3. Semantic Retrieval Layer

Sebelum classify, sistem melakukan retrieval ke:
- `intent_examples`
- `agent_capabilities`

Hasil retrieval:
- top-k intent candidates
- top-k agent candidates
- similarity score

Dengan begitu, pesan seperti:
- "Saya minta data jam masuk kantor saya, brdasrkan bulan kemarin"

tetap bisa dikaitkan ke:
- `attendance_review`
- `attendance analytics`

walaupun keyword exact tidak sempurna.

### 4. LLM Judge

LLM tidak lagi classify dari nol. LLM menerima:
- user message
- attachment context kalau ada
- top-k intent examples
- top-k agent candidates
- trusted session metadata yang aman dipakai

Output yang diharapkan dari LLM:
- `primary_intent`
- `secondary_intents`
- `route`
- `confidence`
- `sensitivity`
- `chosen_agents`
- `reasoning_summary`

Dengan desain ini, LLM lebih mirip `decision judge` daripada `first-pass classifier`.

## Kenapa Ini Lebih Baik

Keuntungan desain ini:
- lebih tahan typo dan variasi phrasing
- tidak terlalu bergantung ke keyword literal
- lebih mudah diskalakan dengan contoh-contoh intent baru
- lebih aman dari false `out_of_scope`
- lebih cocok untuk custom agents yang bertambah seiring waktu

Dalam praktiknya, user HR support sangat sering bertanya dengan pola seperti:
- "tolong cek yang bulan lalu"
- "slip saya yang terbaru dong"
- "rata-rata saya masuk jam berapa"
- "cuti saya aman nggak kalau bulan depan"

Kalimat seperti ini sering punya maksud yang jelas untuk manusia, tapi sulit ditutup penuh hanya dengan hardcoded keyword.

## Peran Hardcode Setelah Refactor

Hardcode masih tetap dibutuhkan, tapi perannya berubah.

Yang tetap cocok di-hardcode:
- enum intent resmi
- enum route resmi
- sensitivity high-risk patterns
- trust boundary
- aturan akses data personal
- fallback safety behavior

Yang sebaiknya tidak lagi terlalu hardcoded:
- seluruh synonym intent
- variasi natural language
- kandidat agent
- contoh phrasing user

Jadi model targetnya:
- contract dan safety di code
- examples dan capability hints di DB/vector store

## Desain Data yang Disarankan

### Tabel `intent_examples`

Kolom yang disarankan:
- `id`
- `company_id` nullable
- `intent_key`
- `example_text`
- `language`
- `weight`
- `embedding`
- `is_active`
- `created_at`
- `updated_at`

Catatan:
- `company_id = null` berarti contoh global/default
- `company_id != null` berarti override atau contoh khusus tenant

### Tabel `agent_capabilities`

Kolom yang disarankan:
- `id`
- `company_id` nullable
- `agent_key`
- `title`
- `description`
- `supported_intents`
- `data_sources`
- `execution_mode`
- `requires_trusted_employee_context`
- `can_run_in_parallel`
- `sample_queries`
- `embedding`
- `is_active`
- `created_at`
- `updated_at`

Contoh bentuk capability yang sehat:

- `hr-data-agent`
  - menangani payroll, attendance, time off, dan profile
  - data source: `employees`, `personal_infos`, `payroll`, `attendance`, `time_offs`
  - execution mode: `structured_lookup`
  - butuh trusted employee context: `true`
- `company-agent`
  - menangani company policy dan company structure
  - data source: `company_rules`, `company_rule_chunks`, `departments`, `employees`
  - execution mode: `policy_lookup`
  - butuh trusted employee context: `false`
- `file-agent`
  - menangani ekstraksi attachment
  - data source: file input / attachment content
  - execution mode: `file_extraction`
  - butuh trusted employee context: `false`

Jadi metadata seperti “query tabel apa” memang masuk, tetapi tidak boleh menjadi satu-satunya isi capability record.

### Optional: `sensitivity_examples`

Kalau nanti sensitivity ingin diperkaya semantic retrieval juga, bisa dibuat tabel terpisah untuk contoh:
- harassment
- discrimination
- burnout
- wellbeing concern

Namun untuk tahap awal, sensitivity high-risk masih lebih aman dipertahankan dengan hardcoded rules + LLM verification.

## Decision Logic yang Disarankan

Contoh decision ladder:

1. kalau high-risk sensitivity cocok secara eksplisit:
   - langsung `sensitive_redirect`
   - tidak perlu menunggu semantic retrieval penuh

2. kalau semantic similarity tinggi:
   - gunakan top-k candidates sebagai dasar route
   - boleh skip LLM jika sangat yakin

3. kalau semantic similarity menengah:
   - kirim ke LLM judge
   - LLM memilih intent dan agent dari candidates

4. kalau semantic similarity rendah:
   - LLM boleh classify lebih bebas
   - jika tetap lemah, jawab clarify / `general_hr_support`

Jadi fallback idealnya:
- retrieval dulu
- baru LLM
- baru generic response

Bukan:
- keyword gagal
- langsung `out_of_scope`

## Rencana Stage 2

Bagian ini sekarang perlu dibaca sebagai:
- **Stage 2 MVP yang sudah aktif**
- ditambah arah penguatan berikutnya

Stage 2 adalah lanjutan natural setelah Stage 1.

Kalau Stage 1 fokus pada:
- semantic retrieval untuk memahami **intent**

Maka Stage 2 fokus pada:
- semantic retrieval untuk memahami **agent mana yang paling relevan**

Flow target Stage 2:

```text
message user
  -> semantic intent retrieval
  -> semantic agent capability retrieval
  -> LLM judge
  -> chosen_agents
  -> parallel execution where safe
  -> final synthesis
```

Output judge yang diharapkan pada Stage 2:
- `primary_intent`
- `secondary_intents`
- `confidence`
- `sensitivity`
- `chosen_agents`
- `execution_mode`
- `reasoning_summary`

## Scope MVP Stage 2

Agar tidak melebar terlalu cepat, MVP Stage 2 sebaiknya sengaja sempit:

- hanya untuk agent yang **sudah ada**
  - `hr-data-agent`
  - `company-agent`
  - `file-agent`
- belum menambah banyak custom agent baru
- belum menjadikan LLM sebagai pengambil keputusan akses data
- belum menghapus hardcoded trust boundary

Artinya Stage 2 MVP bukan “sistem agent kompleks”, tetapi:
- capability-aware routing
- chosen agent lebih fleksibel
- parallel execution lebih terarah

Status implementasi saat ini:
- tabel `agent_capabilities` sudah ada
- semantic retrieval untuk candidate agent sudah ada
- MiniMax sudah menerima candidate intent + candidate agent
- orchestrator sudah menyimpan `planned_agents` dan `planning_reason`
- capability routing sudah bisa mengangkat route dari `out_of_scope` ke `hr_data` atau `company` bila sinyal semantic cukup kuat

## Yang Tetap Di Code Pada Stage 2

Walaupun routing makin semantic, beberapa hal tetap harus keras di code:

- trust boundary `employee_id` dan `company_id`
- sensitivity high-risk override
- route `sensitive_redirect`
- aturan agent mana yang boleh menyentuh personal HR data
- aturan bahwa DB session paralel harus dipisah

Jadi Stage 2 menambah keluwesan routing, tetapi tidak mengendurkan safety layer.

## Contoh Keputusan Stage 2

Contoh 1:
- pesan: `Berapa sisa cuti saya dan apa aturan carry over?`
- intent candidates:
  - `time_off_balance`
  - `company_policy`
- chosen agents:
  - `hr-data-agent`
  - `company-agent`
- execution:
  - paralel

Contoh 2:
- pesan: `Tolong cek lampiran ini, ini slip gaji saya atau bukan?`
- chosen agents:
  - `file-agent`
  - `hr-data-agent`
- execution:
  - `file-agent` dulu untuk ekstraksi
  - lalu `hr-data-agent` kalau perlu verifikasi isi

Contoh 3:
- pesan: `Saya minta data jam masuk kantor saya berdasarkan bulan kemarin`
- intent candidates:
  - `attendance_review`
- chosen agents:
  - `hr-data-agent`
- execution:
  - tunggal, tidak perlu `company-agent`

## Non-Goal Stage 2

Supaya ekspektasinya sehat, ini yang **bukan** target Stage 2 MVP:

- membuat banyak custom agent baru sekaligus
- memindahkan seluruh business logic ke LLM
- mengganti SQL exact lookup dengan vector search
- menghapus local fallback
- menjadikan `agent_capabilities` sebagai pengganti auth/authorization

## Parallel Execution

Begitu route sudah dipilih, agent-agent yang independen sebaiknya jalan paralel.

Contoh:
- query butuh personal data + policy -> `hr-data-agent` + `company-agent`
- query butuh attachment context + structured lookup -> `file-agent` + `hr-data-agent`

Catatan implementasi penting:
- agent paralel yang pakai DB harus memakai session terpisah
- jangan share satu `AsyncSession` SQLAlchemy untuk concurrent query

Tujuan parallel execution:
- quality routing tetap tinggi
- latency total tidak meledak terlalu jauh

## Bagaimana LLM Harus Dipakai

LLM terbaik di desain ini bukan dipakai untuk:
- menebak semua dari nol
- menggantikan SQL/TAG
- menggantikan policy retrieval

LLM dipakai untuk:
- memilih intent dari kandidat retrieval
- memilih agent dari kandidat capability
- memutuskan apakah route tunggal atau mixed
- memutuskan apakah perlu klarifikasi

Jadi perannya adalah:
- judge
- planner ringan
- router

Bukan:
- source of truth untuk data

## Hubungan Dengan SQL dan pgvector

Arsitektur ini tetap hybrid:
- SQL/TAG untuk data personal yang exact
- pgvector untuk semantic retrieval intent dan doc capabilities
- pgvector juga tetap cocok untuk policy retrieval
- LLM judge di atas hasil retrieval

Artinya:
- `payroll`, `attendance`, `time_off`, `profile` tetap pakai SQL
- `company_rules` tetap boleh pakai vector retrieval
- `intent_examples` dan `agent_capabilities` juga pakai vector retrieval

Jadi pgvector di sini tidak dipakai untuk menghitung fakta personal, tetapi untuk:
- menemukan kandidat intent
- menemukan kandidat agent
- menemukan dokumen policy yang paling relevan

## Fallback Strategy Yang Disarankan

Fallback baru yang lebih sehat:

```text
exact / obvious pattern
  -> direct route

semantic retrieval kuat
  -> direct route atau light judge

semantic retrieval menengah
  -> LLM judge

semantic retrieval lemah
  -> clarify / general support

provider gagal
  -> local heuristic safety net
```

Ini membuat sistem:
- tidak terlalu bergantung ke keyword
- tidak terlalu mahal karena tidak semua request harus ke LLM
- tidak terlalu rapuh saat provider gagal

## Observability yang Perlu Dicatat

Karena flow jadi lebih canggih, observability juga harus naik.

Minimal simpan:
- top-k intent retrieval result
- top-k agent retrieval result
- similarity score
- apakah route dipilih dari retrieval langsung atau lewat LLM
- fallback reason
- latency per langkah

Tanpa ini, debugging akan sulit saat user bertanya “kenapa request ini masuk agent A, bukan agent B”.

## Risiko dan Tradeoff

Keuntungan:
- lebih pintar untuk bahasa natural
- lebih cocok untuk custom agent ecosystem
- tidak fragile terhadap phrasing user

Tradeoff:
- implementasi lebih kompleks
- butuh data examples yang bagus
- butuh tuning threshold similarity
- butuh monitoring yang lebih serius

Jadi ini bukan desain paling sederhana, tapi kualitas routing-nya berpotensi jauh lebih baik.

## Rekomendasi Tahapan Implementasi

Supaya tidak rewrite besar sekaligus, implementasi sebaiknya bertahap:

### Tahap 1
- buat tabel `intent_examples`
- seed contoh global untuk semua intent utama
- retrieval semantic untuk intent saja

### Tahap 2
- tambahkan `agent_capabilities`
- retrieval semantic untuk kandidat agent

### Tahap 3
- ubah LLM classifier menjadi `judge over retrieved candidates`
- bukan classifier dari nol

### Tahap 4
- aktifkan route mixed dan parallel execution berdasarkan hasil judge

### Tahap 5
- tambah custom agents seperti:
  - attendance analytics
  - payroll insights
  - leave advisory
  - grievance triage

## Posisi Dokumen Ini Dalam Repo

Dokumen ini menjelaskan arah refactor Phase 3 berikutnya:
- dari local heuristic-heavy routing
- menuju semantic retrieval + LLM judge + parallel agent execution

Dokumen ini sebaiknya dibaca bersama:
- `docs/architecture/phase-3-agent-architecture.md`
- `docs/architecture/phase-3-workflow-id.md`

## Ringkasan Singkat

Kalau disederhanakan, ide utamanya adalah:

1. jangan langsung `out_of_scope` saat keyword tidak cocok
2. cari dulu kemiripan semantic ke intent dan agent examples
3. beri kandidat itu ke LLM
4. biarkan LLM memilih route yang paling tepat
5. jalankan agent yang relevan secara paralel
6. gunakan hardcode hanya untuk guardrail dan safety

Ini membuat sistem lebih dekat ke cara manusia memahami pertanyaan:
- tidak kaku
- tidak terlalu literal
- lebih toleran terhadap typo dan phrasing alami
- tetap aman untuk data personal karena trust boundary tidak berubah
