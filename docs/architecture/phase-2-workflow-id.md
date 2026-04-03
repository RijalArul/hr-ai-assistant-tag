# Workflow Phase 2 HR.ai

Dokumen ini menjelaskan workflow Phase 2 dalam Bahasa Indonesia berdasarkan implementasi yang sekarang ada di repository ini.

## Tujuan Phase 2

Phase 2 adalah action engine.

Fase ini bertugas mengubah hasil interaksi atau keputusan bisnis menjadi objek operasional yang terstruktur, bisa dilacak, dan punya jalur delivery yang jelas.

Dengan kata lain, Phase 2 menjawab pertanyaan:
"setelah sistem tahu ada follow-up yang perlu dilakukan, bagaimana follow-up itu disimpan, direview, dieksekusi, dan diantrikan ke channel delivery yang benar?"

## Posisi Dalam Arsitektur

Urutan fungsionalnya seperti ini:

```text
Phase 1 -> trusted session dan role boundary
Phase 2 -> action contracts, persistence, execution, delivery queue
Phase 3 -> AI orchestration yang nanti bisa memicu action flow
```

Saat ini Phase 2 sudah menyediakan surface publik untuk:
- review action
- update action
- execute action
- konfigurasi rules
- registrasi webhook

Catatan penting:
- pembuatan action sudah ada di service layer
- tetapi route publik yang tersedia sekarang lebih fokus ke review dan execution
- jadi action engine-nya sudah siap, walau automation penuh "conversation resolved -> create action" masih menjadi fondasi untuk fase berikutnya

## Alur Utama Phase 2

Workflow ringkasnya:

```text
trusted session
  -> role / scope validation
  -> baca atau kelola action / rule / webhook
  -> action execution
  -> delivery channel disanitasi
  -> action log ditulis
  -> delivery queue records dibuat
  -> webhook delivery queue records dibuat jika relevan
```

## Konsep Inti Phase 2

Ada tiga blok besar di Phase 2:

### 1. Actions

Action adalah follow-up yang konkret, misalnya:
- `document_generation`
- `counseling_task`
- `followup_chat`
- `escalation`
- `custom_webhook`

Setiap action punya:
- tipe
- title
- summary
- priority
- sensitivity
- delivery channels
- payload terstruktur
- status eksekusi

### 2. Rules

Rule adalah konfigurasi yang memetakan kondisi tertentu ke template action.

Secara konsep, rule dipakai untuk menjawab:
- intent atau trigger apa yang perlu ditindaklanjuti?
- kalau kondisi itu terjadi, action apa yang seharusnya dibuat?

### 3. Webhooks

Webhook adalah konfigurasi endpoint outbound milik company yang ingin menerima event tertentu dari HR.ai.

Webhook saat ini menyimpan:
- nama
- target URL
- event subscription
- secret signing
- status aktif/tidak aktif

## Penjelasan Step-by-Step

### 1. Semua flow Phase 2 dimulai dari trusted session

Phase 2 tidak berjalan sendiri. Semua endpoint publiknya berdiri di atas Phase 1.

Artinya:
- token bearer harus valid
- `company_id` diambil dari session
- `employee_id` diambil dari session
- role diambil dari session

Ini penting karena action, rule, dan webhook semuanya harus tetap scoped ke company yang benar.

## 2. Role dan scope diverifikasi lebih dulu

Sebelum action atau konfigurasi diakses, sistem memeriksa role.

Batasannya saat ini:
- `employee`
  Bisa melihat action miliknya sendiri.

- `hr_admin`
  Bisa melihat action dalam company, update action, execute action, membaca rules, dan toggle `is_enabled`.

- `it_admin`
  Bisa mengelola rule secara penuh dan mengelola webhook.

Selain role, action tertentu juga dibatasi oleh scope:
- employee hanya boleh melihat action dengan `employee_id` miliknya
- HR Admin bekerja di scope company yang sama

## 3. Action dibuat dan disimpan sebagai record terstruktur

Di service layer, action dibuat dengan kontrak yang tegas lewat model Pydantic.

Contoh tipe payload yang didukung:
- document generation
- counseling task
- follow-up chat
- escalation
- custom webhook

Saat action dibuat:
- action disimpan ke tabel `actions`
- status awal di-set ke `pending`
- delivery channels dibersihkan dan dinormalisasi
- log `action.created` ikut ditulis

Catatan penting:
- saat ini flow create action sudah ada di service layer
- surface publik yang tersedia lebih fokus ke review dan execution action yang sudah ada

## 4. Sensitive-case safeguard diterapkan

Ini guardrail utama Phase 2.

Kalau `sensitivity != low`, maka channel delivery akan dinormalisasi menjadi:

```text
manual_review
```

Artinya meskipun request awal menginginkan:
- email
- webhook
- in_app

sistem tetap memaksa jalur aman:
- `manual_review` saja

Tujuannya supaya kasus sensitif tidak langsung didorong ke delivery otomatis.

## 5. Action bisa direview dan diupdate

Setelah action ada, Phase 2 menyediakan surface untuk:
- list actions
- get action detail
- update action
- baca execution result

Update ini dipakai untuk mengubah hal-hal seperti:
- title
- summary
- priority
- status non-terminal
- sensitivity
- delivery channels
- metadata

Tetapi ada batasannya:
- action yang sudah terminal tidak bisa diubah manual sembarangan
- status seperti `completed` dan `failed` diarahkan ke flow execution, bukan patch biasa

## 6. Action dieksekusi oleh HR Admin

Saat `execute action` dipanggil:
- sistem mengambil action yang masih valid
- memastikan action belum `completed` atau `cancelled`
- menghitung ulang delivery channels yang aman
- membuat `execution_result`
- mengubah status action menjadi `completed`
- menulis log `action.executed`

Hasil execution biasanya memuat:
- waktu eksekusi
- delivery channels final
- apakah delivery dipicu
- catatan executor
- delivery mode

Kalau action sensitif, `delivery_mode` akan menunjukkan jalur `manual_review_only`.

## 7. Delivery queue record dibuat

Kalau execution meminta `trigger_delivery = true`, sistem membuat queue record per channel delivery.

Channel yang didukung:
- `email`
- `webhook`
- `in_app`
- `manual_review`

Untuk setiap channel, sistem membuat `action_deliveries` record dengan:
- action id
- channel
- target reference
- payload delivery
- status queued

Contoh target reference:
- email -> employee tertentu
- in-app -> employee tertentu
- manual review -> `hr_admin_review_queue`
- webhook -> kumpulan webhook company yang aktif

## 8. Webhook delivery queue juga bisa dibuat

Kalau salah satu channel adalah `webhook`, sistem tidak langsung menembak HTTP request di tempat.

Yang dilakukan saat ini:
- mencari webhook company yang aktif
- memfilter webhook yang subscribe ke event `action.delivery_requested`
- membuat record di `webhook_deliveries`

Jadi Phase 2 saat ini sudah menyiapkan:
- kontrak delivery
- queue records
- tracking dasar

tetapi belum menjadi worker pengirim HTTP outbound penuh.

## 9. Rules dan webhook adalah surface konfigurasi

Selain action execution, Phase 2 juga menyediakan dua permukaan konfigurasi penting.

### Rules

Rules dipakai untuk menyimpan mapping trigger -> action template.

Yang bisa dilakukan:
- list rule
- lihat detail rule
- create rule
- update rule
- delete rule

Batas role-nya:
- HR Admin boleh membaca rule
- HR Admin hanya boleh toggle `is_enabled`
- perubahan template rule penuh hanya boleh oleh IT Admin

### Webhooks

Webhooks dipakai untuk registrasi endpoint outbound milik company.

Yang bisa dilakukan:
- list webhook
- lihat detail webhook
- create webhook
- update webhook
- delete webhook

Batas role-nya:
- seluruh operasi webhook dibatasi ke IT Admin

## Output Penting Dari Phase 2

Output utama Phase 2 saat ini berupa:
- `ActionResponse`
- `ActionExecutionResponse`
- `ActionResultResponse`
- `RuleResponse`
- `WebhookResponse`

Dengan kontrak ini, fase berikutnya bisa:
- membuat action secara konsisten
- membaca hasil execution
- menghubungkan event ke workflow delivery

## Guardrail Yang Dipakai

Guardrail penting di Phase 2:
- scoping action ke company dan employee yang benar
- role check per route
- status terminal tidak bisa dieksekusi dua kali
- status terminal tidak boleh diubah sembarangan lewat patch biasa
- delivery channel sensitif dipaksa ke `manual_review`
- webhook access dibatasi ke IT Admin
- secret webhook dimask di response

## Endpoint Yang Termasuk Phase 2

Surface publik Phase 2 saat ini:

### Actions
- `GET /api/v1/actions`
- `GET /api/v1/actions/{id}`
- `PATCH /api/v1/actions/{id}`
- `POST /api/v1/actions/{id}/execute`
- `GET /api/v1/actions/{id}/result`

### Rules
- `GET /api/v1/rules`
- `GET /api/v1/rules/{id}`
- `POST /api/v1/rules`
- `PATCH /api/v1/rules/{id}`
- `DELETE /api/v1/rules/{id}`

### Webhooks
- `GET /api/v1/webhooks`
- `GET /api/v1/webhooks/{id}`
- `POST /api/v1/webhooks`
- `PATCH /api/v1/webhooks/{id}`
- `DELETE /api/v1/webhooks/{id}`

## Pemetaan Ke File Implementasi

Supaya lebih mudah belajar dari codebase, ini file utamanya:

- `apps/api/app/models/action_engine.py`
  Kontrak action, rule, webhook, request, response, dan validator payload.

- `apps/api/app/services/action_engine.py`
  Inti Phase 2: create/list/update/execute action, queue delivery, rules, dan webhook management.

- `apps/api/app/api/routes/actions.py`
  Surface HTTP untuk review, update, execute, dan melihat result action.

- `apps/api/app/api/routes/rules.py`
  Surface HTTP untuk konfigurasi rule dan pembatasan role HR Admin vs IT Admin.

- `apps/api/app/api/routes/webhooks.py`
  Surface HTTP untuk registrasi dan maintenance webhook.

- `apps/api/app/core/security.py`
  Pembacaan session trusted dan role guard yang dipakai di seluruh route Phase 2.

## Cara Memahami Phase 2 Secara Sederhana

Kalau disederhanakan, Phase 2 bekerja seperti ini:

1. sistem menerima request dengan session yang sudah trusted
2. sistem memastikan role dan scope-nya benar
3. action, rule, atau webhook dibaca atau dikelola sesuai kebutuhan
4. saat action dieksekusi, sistem menulis hasil eksekusi
5. sistem menyiapkan queue delivery yang relevan
6. kasus sensitif selalu diarahkan ke `manual_review`

Inti Phase 2 adalah:
- follow-up punya bentuk yang terstruktur
- semua perubahan bisa dilacak
- jalur delivery jelas
- kasus sensitif tidak lolos ke automasi biasa
