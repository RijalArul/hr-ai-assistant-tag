# HR Operations Dashboard Requirements

Dokumen ini mendefinisikan bentuk, alur, dan kebutuhan data untuk Dashboard HR (HR Operations Layer) pada platform HR.ai. Layer ini dirancang untuk tim HR agar dapat melakukan triage, review, dan follow-up atas berbagai request maupun case sensitif yang masuk dari employee.

## Status Implementasi Saat Ini

Saat ini repositori sudah punya fondasi backend dan UI dasar untuk HR Operations Layer, tetapi belum semua requirement dashboard di bawah ini sudah surfaced penuh di web app.

Yang sudah terlihat ada di codebase:
- model `Action` sudah membawa `priority`, `sensitivity`, `suggested_pic`, `suggested_next_action`, `sla_hours`, dan `escalation_rule`
- API actions sudah mendukung list, detail, update non-terminal, dan execute
- dashboard HR dasar dan halaman detail case sudah tersedia di `apps/web`

Yang masih parsial:
- surface triage untuk payload terstruktur, missing information, dan relevant policy belum lengkap
- assignment/ownership UI masih belum matang
- analytics dan SLA insight masih lebih dekat ke requirement daripada implementasi final

## 1. Konsep Utama: Structured Task Queue

Setiap percakapan atau request dari employee yang memerlukan tindak lanjut akan diubah menjadi `Action` (Task). Task queue ini menggantikan kebiasaan membaca transkrip chat yang panjang menjadi sebuah tabel atau kanban board yang lebih actionable.

### Elemen Data pada Task Queue
- **Task ID & Title:** Judul singkat dari request (contoh: "Leave Request: Sick Leave - Budi").
- **Task Summary:** Ringkasan dari hasil chat, termasuk intent, konteks, dan sentimen (jika relevan).
- **Urgency / Priority:** Konsisten dengan `ActionPriority` (LOW, MEDIUM, HIGH, URGENT).
- **Sensitivity:** Konsisten dengan `SensitivityLevel` (LOW, MEDIUM, HIGH).
- **Status:** Konsisten dengan `ActionStatus` (PENDING, READY, IN_PROGRESS, COMPLETED, FAILED, CANCELLED).
- **Suggested PIC:** Rekomendasi individu atau grup HR yang paling relevan untuk menangani task ini.
- **Suggested Next Action:** Rekomendasi langkah selanjutnya (contoh: "Review medical certificate and approve in HRIS").
- **SLA Target:** Batas waktu penyelesaian yang diharapkan (misal: 24 jam, 48 jam).
- **Escalation Rule:** Aturan jika SLA terlampaui (misal: "Escalate to HR Manager").

## 2. Fitur Triage dan Review

Saat agent HR membuka sebuah task, mereka harus bisa melihat informasi yang dikurasi oleh AI tanpa harus membaca seluruh percakapan (kecuali dibutuhkan).

### Kebutuhan Informasi Triage
1. **Case Summary:** Ringkasan eksekutif buatan AI.
2. **Missing Information (Jika ada):** Apa saja yang masih kurang dari request employee?
3. **Structured Payload:** Data spesifik seperti `amount`, `expense_date`, `start_date`, `end_date` (tergantung ActionType).
4. **Relevant Policy/Rule:** Cuplikan peraturan perusahaan yang mendasari kenapa AI memberi rekomendasi tertentu.

## 3. SLA dan Escalation Management

Sistem membutuhkan konsistensi target penyelesaian task:
- **Urgent / High Sensitivity Tasks:** (Misal: Harassment report) SLA: 4 jam. Escalation: Head of HR & Legal.
- **High Priority Tasks:** (Misal: Payroll issue) SLA: 24 jam. Escalation: Payroll Manager.
- **Medium Priority Tasks:** (Misal: Leave approval) SLA: 48 jam. Escalation: Line Manager / HRBP.
- **Low Priority Tasks:** (Misal: General inquiry update) SLA: 72 jam. Escalation: N/A.

Setiap kategori harus dikonfigurasikan di sistem agar otomatis meng-assign SLA pada saat pembuatan Action.

## 4. Admin Workflow & Follow-up

Target jangka menengah untuk tim HR tetap mencakup lifecycle `PENDING` -> `IN_PROGRESS` -> `COMPLETED` atau `FAILED`, tetapi implementasi current state masih sedikit lebih ketat:
- update manual dipakai untuk perubahan non-terminal seperti `IN_PROGRESS` atau `CANCELLED`
- `COMPLETED` saat ini mengikuti jalur `POST /actions/{id}/execute`
- `FAILED` saat ini terutama dipakai oleh runtime ketika execution gagal, bukan tombol patch status biasa

- **In-Progress Claim:** Mekanisme claim atomik agar tidak ada 2 agen HR yang mengerjakan task yang sama.
- **Follow-up Chat:** Agen HR dapat mengetik respons atau resolusi, yang kemudian diteruskan kembali ke chat employee melalui webhook atau API delivery channel.
- **Audit Logging:** Setiap perubahan status, perubahan SLA, dan penugasan harus dicatat dalam `ActionLogResponse` yang immutable.
