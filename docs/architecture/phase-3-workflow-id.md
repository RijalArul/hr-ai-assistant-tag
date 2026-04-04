# Workflow Phase 3 HR.ai

Dokumen ini menjelaskan workflow Phase 3 dalam Bahasa Indonesia berdasarkan implementasi yang sudah ada di repository ini.

## Tujuan Phase 3

Phase 3 adalah lapisan orkestrasi AI yang berada di tengah:
- di atas fondasi keamanan dan session dari Phase 1
- di atas action engine dari Phase 2
- di bawah API percakapan publik yang nanti bisa ditambahkan di Phase 4

Artinya, Phase 3 bertugas memahami pesan user, menentukan jalur pemrosesan yang benar, lalu menyusun jawaban akhir dengan tetap menjaga trust boundary.

Dalam blueprint produk Phase 7, Phase 3 saat ini menjalankan dua lapisan sekaligus:
- employee support layer
- reasoning layer

Sedangkan HR operations layer tetap berada di action engine dan surface API action/rules/webhooks.

Referensi ringkas:
- `docs/architecture/phase-7-product-capability-blueprint-id.md`

## Posisi Dalam Arsitektur

Urutan besarnya seperti ini:

```text
Phase 1 -> Trust boundary dan session aman
Phase 2 -> Action engine dan follow-up terstruktur
Phase 3 -> Orchestrator AI, intent, sensitivity, routing
Phase 4 -> Conversations API / public endpoint
```

Jadi Phase 3 bukan endpoint chat publik. Phase 3 adalah "otak routing" internal yang nanti dipanggil oleh layer lain.

## Alur Utama Phase 3

Workflow ringkasnya:

```text
trusted session
  -> optional file-agent
  -> intent classification
  -> sensitivity assessment
  -> route selection
  -> hr-data-agent dan/atau company-agent
  -> request category + response mode resolution
  -> final synthesized answer
```

## Penjelasan Step-by-Step

### 1. Trusted session masuk lebih dulu

Sebelum model atau agent memproses apa pun, sistem sudah punya session context yang dipercaya, misalnya:
- `employee_id`
- `company_id`
- identitas user hasil autentikasi

Ini penting karena data personal tidak boleh diambil berdasarkan tebakan model atau isi prompt user.

Contoh prinsipnya:
- user boleh bertanya: "berapa sisa cuti saya?"
- tapi agent tetap mengambil data berdasarkan `employee_id` dari session
- agent tidak menerima `employee_id` dari hasil inferensi model

## 2. File-agent berjalan jika ada attachment

Kalau request membawa lampiran, Phase 3 akan mencoba memproses lampiran itu lebih dulu lewat `file-agent`.

Tujuannya:
- membaca teks dari file jika memungkinkan
- mengenali metadata file
- memberi konteks tambahan sebelum routing dilakukan

Perilaku saat ini:
- file teks bisa dibaca langsung
- PDF bisa diekstrak secara lokal
- gambar saat ini minimal menghasilkan metadata lokal
- jika provider diaktifkan, sistem bisa mencoba Gemini lebih dulu

## 3. Intent classification

Setelah itu orchestrator mencoba memahami maksud utama user.

Contoh intent yang saat ini didukung:
- `payroll_info`
- `payroll_document_request`
- `attendance_review`
- `time_off_balance`
- `time_off_request_status`
- `personal_profile`
- `company_policy`
- `company_structure`
- `employee_wellbeing_concern`
- `general_hr_support`
- `out_of_scope`

Tujuan langkah ini adalah menjawab pertanyaan:
- user sedang menanyakan data HR personal?
- user sedang menanyakan kebijakan perusahaan?
- user sedang menanyakan keduanya?
- atau pertanyaannya di luar domain HR.ai?

## 4. Sensitivity assessment

Setelah intent, sistem mengecek apakah pesan mengandung topik sensitif.

Contoh topik sensitif:
- pelecehan
- diskriminasi
- bullying
- burnout berat
- kekerasan
- self-harm atau bunuh diri

Hasil langkah ini menentukan apakah jalur otomatis masih aman dipakai atau harus diarahkan ke jalur yang lebih hati-hati.

## 5. Route selection

Berdasarkan intent dan sensitivity, orchestrator memilih route akhir.

Route yang ada sekarang:
- `hr_data`
- `company`
- `mixed`
- `sensitive_redirect`
- `out_of_scope`

Aturan sederhananya:
- kalau pertanyaan menyangkut data personal HR -> `hr_data`
- kalau pertanyaan menyangkut policy/struktur perusahaan -> `company`
- kalau dua-duanya dibutuhkan -> `mixed`
- kalau topiknya sensitif -> `sensitive_redirect`
- kalau di luar domain -> `out_of_scope`

## 6. Agent yang sesuai dijalankan

### Jalur `hr_data`

`hr-data-agent` dipakai untuk data yang sifatnya personal dan terstruktur, seperti:
- payroll
- attendance
- time off
- profile karyawan

Prinsip utamanya:
- query selalu terikat ke `session.employee_id`
- query juga tetap dibatasi oleh `session.company_id`

Ini membuat akses data tetap aman walaupun user bertanya dengan bahasa natural.

### Jalur `company`

`company-agent` dipakai untuk data perusahaan yang sifatnya bersama, seperti:
- company rules
- company structure

Saat ini agent ini bisa:
- mencari policy berdasarkan keyword/ranking
- memakai vector search ke `company_rule_chunks` jika embedding tersedia

### Jalur `mixed`

Kalau pertanyaan butuh dua sumber sekaligus, orchestrator menjalankan:
- `hr-data-agent`
- `company-agent`

Lalu hasil keduanya digabungkan menjadi satu jawaban.

Contoh:
- "Berapa sisa cuti saya dan apa aturan carry over?"

Pertanyaan seperti ini butuh:
- data personal cuti milik user
- aturan perusahaan tentang carry over

## 7. Final synthesis

Setelah agent selesai, orchestrator menyusun jawaban akhir yang lebih rapi untuk user.

Biasanya jawaban akhir memuat:
- ringkasan jawaban utama
- fakta yang relevan dari data atau policy
- mode jawaban yang tepat untuk konteks user
- evidence yang mendasari jawaban
- trace agent yang dipakai

Jadi orchestrator bukan hanya merutekan, tapi juga menjadi lapisan penyatu hasil.

## 7.1 Request category dan response mode

Sebelum jawaban akhir dikembalikan, orchestrator juga menyimpulkan jenis kebutuhan user dan bentuk jawaban yang paling tepat.

Contoh `request_category` saat ini:
- `informational_question`
- `guidance_request`
- `policy_reasoning_request`
- `workflow_request`
- `sensitive_report`
- `decision_support`

Contoh `response_mode` saat ini:
- `informational`
- `guidance`
- `policy_reasoning`
- `workflow_intake`
- `sensitive_guarded`
- `hr_ops_summary`

Dengan pemisahan ini, Phase 3 tidak hanya menjawab "intent-nya apa", tetapi juga "jawabannya harus berbentuk seperti apa".

## 8. Output yang dikembalikan

Output akhir dari orchestrator saat ini berisi:
- `route`
- `intent`
- `sensitivity`
- `request_category`
- `response_mode`
- `answer`
- `recommended_next_steps`
- `used_agents`
- `evidence`
- `trace`
- `extracted_attachment_text`
- `context`

Dengan bentuk ini, Phase 4 nanti bisa memakai output yang sama untuk conversation API tanpa menulis ulang logic routing.

## Guardrail dan Trust Boundary

Bagian paling penting dari Phase 3 adalah menjaga batas aman antara model dan data.

Guardrail yang dipakai:
- model tidak memilih `employee_id`
- model tidak memilih `company_id`
- data personal selalu diambil dari session yang trusted
- topik sensitif tidak dipaksakan lewat jalur otomatis biasa
- provider remote bersifat opt-in di local development

Ini yang membedakan Phase 3 dari chatbot biasa. Model membantu routing dan sintesis, tapi akses data tetap dikontrol oleh sistem.

## Fallback Strategy Saat Ini

Agar Phase 3 tetap bisa jalan walaupun provider AI eksternal belum aktif, repo ini memakai fallback lokal yang deterministik.

Fallback yang tersedia:
- intent classification berbasis keyword heuristics
- sensitivity detection berbasis keyword heuristics
- ekstraksi PDF lokal
- fallback metadata untuk image
- lookup policy berbasis keyword/ranking

Kalau environment mendukung, sistem bisa mencoba jalur provider-ready:
- MiniMax untuk classification
- Gemini untuk file extraction
- embedding/vector retrieval untuk `company_rule_chunks`

Tetapi default local development saat ini tetap aman karena provider remote tidak dipanggil otomatis.

## Cara Menjalankan Preview Lokal

Untuk mencoba workflow internal Phase 3 tanpa membuat endpoint publik, gunakan:

```bash
python scripts/phase3_preview.py \
  --email fakhrul.rijal@majubersama.id \
  --message "Berapa sisa cuti saya dan apa aturan carry over?"
```

Kalau mau mencoba dengan attachment:

```bash
python scripts/phase3_preview.py \
  --email fakhrul.rijal@majubersama.id \
  --message "Tolong cek lampiran ini" \
  --attachment C:/path/to/document.pdf
```

Kalau mau menyiapkan vector chunk dari `company_rules`, jalankan:

```bash
python scripts/sync_company_rule_chunks.py
```

## Pemetaan Ke File Implementasi

Supaya lebih mudah belajar dari codebase, ini peta file utamanya:

- `apps/api/app/models/agent_architecture.py`
  Kontrak data Phase 3: intent, route, request, response, evidence, trace.

- `apps/api/app/agents/orchestrator.py`
  Pusat workflow. Menjalankan klasifikasi, sensitivity, routing, pemanggilan agent, dan sintesis akhir.

- `apps/api/app/agents/hr_data_agent.py`
  Mengambil data personal karyawan dari sumber data terstruktur.

- `apps/api/app/agents/company_agent.py`
  Mengambil policy dan struktur perusahaan.

- `apps/api/app/agents/file_agent.py`
  Memproses attachment sebelum routing utama.

- `apps/api/app/services/minimax.py`
  Adapter provider untuk intent classification.

- `apps/api/app/services/gemini.py`
  Adapter provider untuk ekstraksi file.

- `apps/api/app/services/embeddings.py`
  Helper embedding dan chunking untuk policy retrieval.

- `scripts/phase3_preview.py`
  Harness lokal untuk mencoba workflow end-to-end di level service.

- `scripts/sync_company_rule_chunks.py`
  Script sinkronisasi chunk policy untuk vector retrieval.

## Ringkasan Sederhana

Kalau disederhanakan, Phase 3 bekerja seperti ini:

1. sistem menerima pesan user plus session yang sudah trusted
2. kalau ada lampiran, lampiran diproses dulu
3. orchestrator menebak intent dan level sensitivitas
4. orchestrator memilih agent yang tepat
5. agent mengambil data yang relevan
6. orchestrator menyusun jawaban akhir yang aman dan terarah

Inti Phase 3 adalah:
- memahami pertanyaan
- memilih jalur yang benar
- mengambil data dari sumber yang benar
- tetap menjaga batas akses data yang aman
