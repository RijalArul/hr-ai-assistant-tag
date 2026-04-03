# Desain NVC Response Synthesis Phase 5 HR.ai

Dokumen ini menjelaskan desain dan rencana implementasi Non-Violent Communication (NVC) framework ke dalam response synthesis HR.ai.

Dokumen ini adalah rencana implementasi, bukan deskripsi fitur yang sudah aktif.

## Status Saat Ini

Supaya tidak rancu, ini kondisi repo saat ini terkait response generation:

Fungsi `_synthesize_answer()` di `app/agents/orchestrator.py` (baris 469-490) saat ini bekerja sebagai simple string concatenation:

```python
def _synthesize_answer(route, hr_summary, company_summary, file_summary):
    parts = []
    if route == AgentRoute.HR_DATA and hr_summary:
        parts.append(hr_summary)
    elif route == AgentRoute.COMPANY and company_summary:
        parts.append(company_summary)
    elif route == AgentRoute.MIXED:
        if hr_summary:
            parts.append(f"Data personal: {hr_summary}")
        if company_summary:
            parts.append(f"Referensi perusahaan: {company_summary}")
    if file_summary:
        parts.append(f"Lampiran: {file_summary}")
    return " ".join(part for part in parts if part).strip()
```

Artinya:
- tidak ada LLM yang terlibat dalam menyusun response final
- data dari agent langsung disambung dan dikembalikan ke user
- tidak ada tone instruction, tidak ada empati, tidak ada NVC

Response sensitive dan out-of-scope juga hardcoded tanpa NVC:

```python
def _build_sensitive_response(sensitivity):
    return (
        "Topik ini masuk jalur sensitif. Aku tidak akan menyimpulkan atau "
        "mengotomasi penanganannya. Mohon teruskan ke HR/Admin..."
    )
```

Artinya saat ini, response HR.ai terasa seperti output database, bukan percakapan yang manusiawi.

## Kenapa NVC Diperlukan

HR.ai bukan sekadar query engine. Positioning kita adalah AI yang membantu karyawan navigate HR dengan nyaman, terutama untuk topik yang sensitif secara emosional seperti:
- "Kenapa gaji bulan ini dipotong?"
- "Saya ngerasa dibully di kantor"
- "Saya bingung aturan cuti carry-over-nya"

Untuk konteks seperti ini, response yang hanya berisi data mentah seperti `"Saldo cuti: 8 dari 12 hari"` terasa dingin dan transaksional. Response yang baik seharusnya:
- mengakui konteks yang ditanyakan employee
- menyajikan fakta dengan jelas tanpa judgment
- memvalidasi situasi employee tanpa berpihak
- menawarkan langkah selanjutnya yang konkret

NVC (Non-Violent Communication) dikembangkan oleh Marshall Rosenberg sebagai framework komunikasi yang fokus pada empati, fakta, dan kebutuhan — cocok untuk konteks HR support.

## Prinsip NVC Dalam Konteks HR.ai

NVC asli punya empat komponen: Observation, Feeling, Need, Request. Dalam konteks HR AI, kita adaptasikan menjadi empat prinsip yang lebih operasional:

**1. Acknowledge (Pengakuan)**
Akui apa yang ditanyakan atau dialami employee tanpa menilai atau mengambil kesimpulan tentang situasinya.

Contoh buruk: `"Gaji kamu dipotong karena absen."`
Contoh NVC: `"Terlihat ada perbedaan di komponen gaji bulan ini yang mungkin membingungkan."`

**2. Inform (Informasi Faktual)**
Sajikan data dan fakta secara jelas, akurat, dan lengkap tanpa menambahkan interpretasi yang tidak diminta.

Contoh buruk: `"Saldo cuti: 8"`
Contoh NVC: `"Sampai hari ini, kamu masih punya 8 hari cuti tersisa dari total 12 hari yang diberikan tahun 2026."`

**3. Validate (Validasi Konteks)**
Validasi situasi employee jika relevan — bukan berpihak ke employee atau perusahaan, tapi mengakui bahwa situasinya memang perlu kejelasan.

Contoh NVC: `"Wajar kalau ini membingungkan karena aturan carry-over memang berbeda tiap perusahaan."`

**4. Guide (Panduan Selanjutnya)**
Tawarkan langkah berikutnya yang jelas dan bisa langsung dilakukan.

Contoh NVC: `"Kalau mau konfirmasi lebih lanjut, tim HR bisa dihubungi langsung untuk penjelasan detail."`

## Arsitektur Synthesis Yang Diusulkan

### Komponen Baru: Response Synthesizer

File baru yang diusulkan: `app/services/response_synthesizer.py`

Ini adalah service yang dipanggil orchestrator sebagai pengganti `_synthesize_answer()` saat ini.

Flow yang diusulkan:

```text
agents selesai dijalankan (hr_result, company_result, file_summary)
  -> response_synthesizer.synthesize(
       user_message=...,
       intent=...,
       sensitivity=...,
       hr_data=hr_result.summary,
       company_data=company_result.summary,
       file_data=file_summary,
       conversation_history=...,
       provider_available=...
     )
  -> LLM dipanggil dengan NVC system prompt
  -> response divalidasi (panjang, kelengkapan)
  -> jika LLM gagal, fallback ke template-based synthesis
  -> return final_response
```

### System Prompt NVC

Inti dari implementasi ini adalah system prompt yang diberikan ke LLM saat synthesis.

Prompt dirancang dalam tiga lapisan:

**Lapisan 1 — Identitas dan Batasan:**
```
Kamu adalah HR AI assistant yang bekerja untuk {company_name}.
Tugasmu adalah menyampaikan informasi HR kepada karyawan dengan cara yang jelas, empatik, dan profesional.

Kamu TIDAK boleh:
- Memberikan opini tentang apakah keputusan perusahaan benar atau salah
- Berpihak kepada karyawan atau kepada perusahaan
- Memberikan nasihat hukum, keuangan, atau medis
- Menyimpulkan sesuatu yang tidak ada di data yang diberikan
- Menambahkan data yang tidak ada di context di bawah ini
```

**Lapisan 2 — Prinsip NVC:**
```
Gunakan prinsip komunikasi berikut:
1. Acknowledge: Akui apa yang ditanyakan dengan hangat, tanpa menilai.
2. Inform: Sampaikan fakta dari data yang tersedia secara jelas dan lengkap.
3. Validate: Validasi bahwa pertanyaan atau situasinya wajar untuk dikonfirmasi.
4. Guide: Tawarkan langkah selanjutnya yang konkret jika relevan.

Gaya bahasa:
- Gunakan bahasa Indonesia yang natural dan tidak kaku
- Sapa karyawan dengan "kamu" (bukan "Anda" yang terlalu formal, bukan "lo" yang terlalu casual)
- Hindari jargon HR yang terlalu teknis kecuali memang diperlukan
- Jawaban harus ringkas tapi lengkap — tidak bertele-tele, tidak terpotong
```

**Lapisan 3 — Context Data:**
```
Berikut data yang tersedia untuk menjawab pertanyaan ini.
Gunakan HANYA data di bawah ini. Jangan tambahkan informasi lain.

[DATA PERSONAL KARYAWAN]
{hr_data}

[KEBIJAKAN PERUSAHAAN]
{company_data}

[KONTEN LAMPIRAN]
{file_data}

Pertanyaan karyawan: {user_message}
```

### Handling Per Route

Response synthesizer menyesuaikan context yang dikirim ke LLM berdasarkan route:

| Route | Data yang disertakan | Tone hint tambahan |
|---|---|---|
| `HR_DATA` | hr_data saja | Fokus pada data personal, validasi jika ada perbedaan dengan ekspektasi |
| `COMPANY` | company_data saja | Jelaskan kebijakan dengan bahasa yang mudah dimengerti |
| `MIXED` | hr_data + company_data | Hubungkan data personal dengan kebijakan yang relevan |
| `SENSITIVE_REDIRECT` | Tidak ada data | Empati penuh, redirect ke HR, tidak expose detail sensitif |
| `OUT_OF_SCOPE` | Tidak ada data | Friendly, arahkan ke topik yang bisa dibantu |

### NVC Untuk Sensitive Response

Response sensitif saat ini hardcoded dan terasa mechanical. Dengan NVC, response menjadi lebih manusiawi sambil tetap aman:

**Saat ini:**
```
"Topik ini masuk jalur sensitif. Aku tidak akan menyimpulkan atau
mengotomasi penanganannya. Mohon teruskan ke HR/Admin yang berwenang
untuk review manual. Indikator yang terdeteksi: pelecehan, diskriminasi."
```

**Target dengan NVC:**
```
"Terima kasih sudah mempercayai aku dengan hal ini. Topik yang kamu
sampaikan adalah sesuatu yang perlu ditangani dengan penuh perhatian
oleh tim yang tepat — bukan melalui AI.

Tim HR siap mendengarkan dan membantu. Kamu bisa menghubungi mereka
langsung, dan semua yang kamu sampaikan akan diperlakukan secara
rahasia sesuai prosedur perusahaan."
```

Template NVC untuk sensitive response tetap pre-written (tidak di-generate LLM) karena:
- predictability lebih penting dari nuance di kasus high-risk
- tidak ada data yang perlu di-synthesize
- LLM call tambahan meningkatkan latency di moment yang justru membutuhkan respon cepat

Tapi template-nya di-upgrade dengan NVC principles, bukan hardcoded seperti sekarang.

### NVC Untuk Out-of-Scope Response

**Saat ini:**
```
"Pesan ini belum cukup jelas atau belum masuk domain HR.ai."
```

**Target dengan NVC:**
```
"Sepertinya pertanyaan ini sedikit di luar area yang bisa aku bantu
saat ini. Aku bisa membantu dengan hal-hal seperti informasi gaji,
sisa cuti, kehadiran, kebijakan perusahaan, atau struktur organisasi.

Ada yang ingin kamu tanyakan terkait salah satu topik itu?"
```

---

## Provider Strategy Untuk Synthesis

LLM synthesis membutuhkan model yang baik dalam bahasa natural Indonesia. Dua opsi:

**Opsi 1 — MiniMax (sudah ada di stack, preferred):**
- Sudah terbukti handle Bahasa Indonesia dengan baik di classification
- API sudah terkonfigurasi
- Sama dengan yang dipakai untuk classification, tinggal tambah synthesis role

**Opsi 2 — Gemini 2.5 Flash (sudah ada di stack):**
- Sudah dipakai untuk file extraction
- Kualitas Bahasa Indonesia sangat baik
- Lebih powerful dari MiniMax untuk nuanced response, tapi lebih mahal per call

**Rekomendasi:** Gunakan MiniMax untuk synthesis karena sudah ada dan latency-nya lebih rendah. Gemini jadi fallback jika MiniMax unavailable.

## Fallback Strategy

Synthesis dengan LLM bisa gagal (provider down, timeout, response tidak valid). Fallback harus ada:

```text
LLM synthesis dipanggil (MiniMax)
  -> berhasil: return NVC response
  -> gagal / timeout: coba Gemini
      -> berhasil: return NVC response
      -> gagal: jalankan template-based synthesis (versi yang lebih baik dari _synthesize_answer() sekarang)
```

Template-based fallback tidak menggunakan LLM tapi menggunakan template yang sudah di-upgrade dengan bahasa yang lebih natural dari yang sekarang.

Contoh template fallback untuk `HR_DATA`:
```
"Berikut informasi yang berhasil aku temukan untuk kamu:

{hr_data}

Kalau ada yang ingin dikonfirmasi lebih lanjut, tim HR siap membantu."
```

---

## Conversation History Awareness

Synthesis yang baik harus mempertimbangkan riwayat conversation, bukan hanya message terakhir. Ini penting untuk:
- menghindari pengulangan informasi yang sudah disampaikan sebelumnya
- menjaga konsistensi tone sepanjang conversation
- memahami konteks yang sudah dibangun di turn sebelumnya

Conversation history dikirim ke LLM dalam format:
```
[RIWAYAT PERCAKAPAN SEBELUMNYA]
Karyawan: ...
Asisten: ...
Karyawan: ...
Asisten: ...

[PERTANYAAN TERBARU]
Karyawan: {user_message}
```

Batasan: maksimal 10 turn terakhir dikirim ke LLM untuk menghindari context window yang terlalu besar.

---

## Perubahan di Orchestrator

Perubahan minimal yang diperlukan di `app/agents/orchestrator.py`:

**1. Ganti panggilan `_synthesize_answer()` di baris 1399:**

```python
# SEBELUM
answer = _synthesize_answer(
    route,
    hr_result.summary if hr_result else None,
    company_result.summary if company_result else None,
    file_summary,
)

# SESUDAH
answer = await synthesize_response(
    user_message=request.message,
    intent=intent,
    sensitivity=sensitivity,
    route=route,
    hr_data=hr_result.summary if hr_result else None,
    company_data=company_result.summary if company_result else None,
    file_data=file_summary,
    conversation_history=request.history,
)
```

**2. Upgrade `_build_sensitive_response()` menjadi NVC template:**

```python
# Tidak lagi satu fungsi hardcoded, tapi diambil dari template registry
# berdasarkan sensitivity level dan matched keywords
answer = get_sensitive_template(
    sensitivity_level=sensitivity.level,
    matched_keywords=sensitivity.matched_keywords,
)
```

**3. Upgrade `_build_out_of_scope_response()` menjadi NVC template:**

```python
answer = get_out_of_scope_template(
    primary_intent=intent.primary_intent,
)
```

---

## File Baru Yang Diperlukan

```text
app/services/response_synthesizer.py
  - synthesize_response()          # entry point, dipanggil dari orchestrator
  - _call_minimax_synthesis()      # synthesis via MiniMax
  - _call_gemini_synthesis()       # synthesis via Gemini (fallback)
  - _build_nvc_system_prompt()     # build NVC system prompt dari context
  - _build_nvc_user_prompt()       # build user prompt berisi data + pertanyaan
  - _validate_synthesis_result()   # pastikan response tidak kosong, tidak terlalu pendek
  - _fallback_synthesis()          # template-based synthesis jika semua LLM gagal

app/services/response_templates.py
  - get_sensitive_template()       # NVC-upgraded sensitive response templates
  - get_out_of_scope_template()    # NVC-upgraded out-of-scope templates
  - SENSITIVE_TEMPLATES            # dict berisi variasi template per sensitivity level
  - OUT_OF_SCOPE_TEMPLATES         # dict berisi variasi template per intent
```

---

## Priority dan Estimasi

| Priority | Komponen | Estimasi |
|---|---|---|
| P0 | NVC system prompt dan synthesis logic (`response_synthesizer.py`) | 6 jam |
| P0 | NVC template upgrade untuk sensitive dan out-of-scope | 2 jam |
| P0 | Integrasi ke orchestrator (ganti panggilan `_synthesize_answer`) | 2 jam |
| P1 | Conversation history awareness di synthesis prompt | 3 jam |
| P1 | Fallback strategy (MiniMax → Gemini → template) | 3 jam |
| P2 | Tone validator di Output Guard (lihat phase-5-guardrail-agent-id.md) | 6 jam |

Total: ~22 jam

Catatan: P0 bisa dikerjakan dalam satu sprint pendek karena tidak memerlukan perubahan schema DB atau perubahan API surface.

---

## Risiko dan Tradeoff

**Latency:**
Menambahkan LLM call untuk synthesis menambah waktu response sekitar 1-3 detik tergantung provider. Ini adalah tradeoff yang disengaja: response yang lebih baik vs latency yang sedikit lebih tinggi. Mitigasi: jalankan synthesis dan agent execution secara paralel jika memungkinkan, dan simpan hasil synthesis di conversation record.

**Konsistensi:**
LLM bisa menghasilkan response yang sedikit berbeda untuk input yang sama. Ini diterima — variasi alami dalam bahasa adalah fitur, bukan bug, selama data yang disampaikan akurat. Akurasi data tetap dijaga oleh Output Guard (hallucination checker di `phase-5-guardrail-agent-id.md`).

**Cost:**
Satu LLM call tambahan per message. Untuk MVP masih masuk akal. Untuk scale, pertimbangkan caching synthesis result untuk pertanyaan yang sangat umum dan berulang.

---

## Contoh Response Sebelum dan Sesudah

### Kasus: Sisa Cuti

**Pertanyaan:** "Sisa cuti saya berapa?"

**Sebelum (saat ini):**
```
Saldo cuti kamu: 8 dari 12 hari (2026). Request status: none pending.
```

**Sesudah (dengan NVC synthesis):**
```
Untuk tahun 2026, kamu masih punya 8 hari cuti tersisa dari total
12 hari yang diberikan perusahaan. Saat ini tidak ada pengajuan cuti
yang sedang pending.

Kalau mau mengajukan cuti, kamu bisa lanjutkan langsung melalui
sistem HRIS atau hubungi HR untuk panduan prosedurnya.
```

---

### Kasus: Potongan Gaji

**Pertanyaan:** "Kenapa gaji bulan ini ada potongan yang nggak biasa?"

**Sebelum (saat ini):**
```
Data personal: Gaji April 2026: Rp 8.500.000. Potongan: BPJS Kesehatan
Rp 180.000, BPJS Ketenagakerjaan Rp 210.000, PPh21 Rp 320.000,
Adjustment Rp 500.000.
```

**Sesudah (dengan NVC synthesis):**
```
Wajar kalau ini perlu dikonfirmasi — perubahan komponen gaji memang
kadang tidak langsung jelas alasannya.

Untuk April 2026, total gaji yang diterima adalah Rp 8.500.000,
dengan rincian potongan:
- BPJS Kesehatan: Rp 180.000
- BPJS Ketenagakerjaan: Rp 210.000
- PPh21: Rp 320.000
- Adjustment: Rp 500.000

Untuk komponen "Adjustment" sebesar Rp 500.000, penjelasan detailnya
biasanya ada di slip gaji resmi atau bisa dikonfirmasi langsung ke tim
HR atau Payroll.
```

---

### Kasus: Sensitive Topic

**Pertanyaan:** "Saya merasa dibully sama atasan saya"

**Sebelum (saat ini):**
```
Topik ini masuk jalur sensitif. Aku tidak akan menyimpulkan atau
mengotomasi penanganannya. Mohon teruskan ke HR/Admin yang berwenang
untuk review manual. Indikator yang terdeteksi: dibully.
```

**Sesudah (dengan NVC template):**
```
Terima kasih sudah mau menyampaikan ini. Apa yang kamu rasakan penting
dan layak untuk ditangani dengan serius.

Situasi seperti ini perlu disampaikan langsung ke tim HR agar bisa
ditangani dengan tepat dan rahasia. Mereka punya prosedur khusus untuk
membantu kamu melalui proses ini dengan aman.

Kamu tidak harus menghadapi ini sendiri.
```

---

## Posisi Dokumen Ini Dalam Repo

Dokumen ini sebaiknya dibaca bersama:
- `docs/architecture/phase-5-guardrail-agent-id.md` — Output Guard termasuk tone validator yang berjalan setelah synthesis
- `docs/architecture/phase-3-agent-architecture.md` — arsitektur agent yang menghasilkan data yang di-synthesize
- `docs/architecture/phase-3-semantic-routing-id.md` — routing logic yang menentukan agent mana yang dijalankan

## Cara Memahami Ini Secara Sederhana

Kalau disederhanakan, implementasi NVC di sini bekerja seperti ini:

1. agent (HR Data, Company, File) tetap bekerja seperti biasa dan mengembalikan data mentah
2. data mentah itu tidak lagi langsung dikembalikan ke user
3. data mentah dikirim ke LLM bersama pesan user dan NVC system prompt
4. LLM menyusun ulang data itu menjadi response yang manusiawi
5. jika LLM gagal, template yang sudah di-upgrade dengan NVC language digunakan sebagai fallback
6. Output Guard kemudian memvalidasi response sebelum dikirim ke user

Inti perubahan ini adalah:
- agent tetap bertanggung jawab atas **akurasi data**
- response synthesizer bertanggung jawab atas **kualitas komunikasi**
- keduanya punya tanggung jawab yang jelas dan tidak tumpang tindih
