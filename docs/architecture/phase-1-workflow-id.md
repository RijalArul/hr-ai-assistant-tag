# Workflow Phase 1 HR.ai

Dokumen ini menjelaskan workflow Phase 1 dalam Bahasa Indonesia berdasarkan implementasi yang sekarang ada di repository ini.

## Tujuan Phase 1

Phase 1 adalah fondasi kepercayaan sistem.

Fase ini memastikan:
- API bisa hidup dengan dependency dasar yang benar
- session user bisa dibuat dan divalidasi
- identitas karyawan dan company context berasal dari sumber yang dipercaya
- layer berikutnya tidak mengambil data HR personal dari prompt atau tebakan model

Kalau disederhanakan, Phase 1 menjawab pertanyaan:
"siapa user ini, berada di company mana, dan apakah konteks itu aman dipakai oleh sistem?"

## Posisi Dalam Arsitektur

Urutan perannya seperti ini:

```text
startup app
  -> inisialisasi cache dan redis
  -> health check untuk dependency dasar
  -> login user
  -> pembuatan JWT bearer token
  -> pembacaan trusted session di request berikutnya
  -> trust boundary siap dipakai fase lain
```

Phase 1 belum bicara soal AI routing atau action follow-up. Fokusnya adalah identitas, session, dan readiness sistem.

## Alur Utama Phase 1

Workflow ringkasnya:

```text
app start
  -> init LRU cache
  -> init Redis
  -> health endpoint mengecek dependency
  -> login by email
  -> lookup employee
  -> generate JWT berisi session context
  -> bearer token dipakai ke request berikutnya
  -> token di-decode menjadi trusted SessionContext
```

## Penjelasan Step-by-Step

### 1. Aplikasi start dan menyiapkan dependency dasar

Saat API hidup, aplikasi menjalankan lifecycle startup untuk menyiapkan komponen yang dibutuhkan sejak awal.

Yang diinisialisasi:
- LRU cache in-memory untuk data yang relatif statis
- Redis untuk kebutuhan data dinamis / TTL-oriented

Saat aplikasi shutdown:
- cache registry dibersihkan
- koneksi Redis ditutup

Ini membuat service punya fondasi operasional yang konsisten sebelum request bisnis masuk.

## 2. Health check memverifikasi readiness

Phase 1 menyediakan endpoint health untuk mengecek apakah dependency dasar bisa diakses.

Yang dicek:
- PostgreSQL
- Redis
- LRU cache registry

Perilaku pentingnya:
- endpoint tetap mengembalikan `200 OK`
- tetapi field `status` bisa bernilai `degraded`
- detail error dependency ditaruh di response body

Jadi endpoint ini dipakai untuk menjawab:
- apakah API hidup?
- apakah dependency pendukungnya siap?

## 3. User login menggunakan email

Flow login Phase 1 saat ini memang masih sederhana: user login dengan email.

Prosesnya:
- request masuk ke `POST /auth/login`
- email dinormalisasi
- service mencari employee berdasarkan email
- bila ketemu persis satu record, sistem membuat session context

Validasi penting:
- kalau email tidak ditemukan -> `401 Unauthorized`
- kalau satu email muncul di lebih dari satu company -> `409 Conflict`

Kenapa duplicate email ditolak?
Karena Phase 1 tidak mau membuat session yang ambigu. Sistem harus tahu company context secara pasti.

## 4. Session context dibentuk dari data yang trusted

Setelah employee ditemukan, sistem membentuk `SessionContext` yang saat ini memuat:
- `employee_id`
- `company_id`
- `email`
- `role`

Inilah trust boundary paling penting di repo ini:
- `employee_id` tidak datang dari prompt
- `company_id` tidak datang dari prompt
- keduanya datang dari hasil lookup backend yang trusted

Jadi setelah login, sistem tidak perlu menebak identitas user dari bahasa natural.

## 5. JWT bearer token dibuat

Setelah `SessionContext` siap, sistem membuat access token JWT.

Payload token memuat:
- `sub` sebagai `employee_id`
- `company_id`
- `email`
- `role`
- `iat`
- `exp`

Artinya token ini bukan sekadar bukti login, tapi juga carrier untuk context trusted yang dibutuhkan route lain.

## 6. Request berikutnya membaca session dari token

Saat user memanggil endpoint yang butuh autentikasi:
- bearer token diambil dari header
- token didecode
- payload divalidasi
- sistem membentuk kembali `SessionContext`

Kalau token:
- hilang
- salah format
- invalid
- expired

maka request ditolak dengan `401 Unauthorized`.

## 7. Role check dilakukan di route yang butuh proteksi

Setelah `SessionContext` berhasil dibaca, route bisa menambahkan pembatasan role.

Contohnya:
- route tertentu cukup butuh token valid
- route lain membatasi role tertentu saja

Phase 1 sendiri terutama menyediakan mekanisme session dan helper role check yang nanti dipakai oleh phase-phase berikutnya.

## Trust Boundary Inti

Kalau ada satu hal yang harus diingat dari Phase 1, ini dia:

```text
employee_id dan company_id hanya boleh berasal dari authenticated session context
```

Bukan dari:
- prompt user
- hasil inferensi model
- parameter liar dari frontend

Dengan aturan ini, semua fase setelahnya bisa membaca data HR dengan dasar identitas yang aman.

## Cache dan Runtime Foundation

Phase 1 juga menyiapkan fondasi runtime yang dipakai lintas fase.

Saat ini ada dua jenis cache:
- LRU cache in-memory
  Cocok untuk namespace yang lebih statis seperti `employee_profile`, `personal_info`, dan `company_rules`.

- Redis
  Cocok untuk data dinamis dan kebutuhan TTL-oriented.

Jadi Phase 1 bukan hanya auth, tapi juga readiness layer untuk service lain.

## Endpoint Yang Termasuk Phase 1

Surface publik Phase 1 saat ini:
- `GET /api/v1/health`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

Arti masing-masing:
- `health`: mengecek readiness dependency
- `login`: membuat session trusted dan access token
- `auth/me`: membaca kembali session trusted dari token

## Output Penting Dari Phase 1

Output paling penting dari Phase 1 adalah `SessionContext`.

Inilah kontrak yang dipakai fase berikutnya untuk:
- scoping employee
- scoping company
- role authorization
- menjaga agar data personal tidak diakses lewat jalur yang tidak trusted

## Guardrail Yang Dipakai

Guardrail Phase 1 saat ini:
- email invalid ditolak
- email ambigu lintas company ditolak
- token invalid ditolak
- route terproteksi membaca session hanya dari bearer token
- role check dilakukan server-side
- identity context tidak diambil dari model atau prompt

## Pemetaan Ke File Implementasi

Supaya lebih mudah belajar dari codebase, ini file utamanya:

- `apps/api/app/main.py`
  Menyiapkan lifecycle app, inisialisasi cache registry, dan inisialisasi Redis.

- `apps/api/app/api/routes/health.py`
  Endpoint health untuk memeriksa PostgreSQL, Redis, dan LRU cache.

- `apps/api/app/api/routes/auth.py`
  Endpoint login dan endpoint pembacaan session saat ini.

- `apps/api/app/services/auth.py`
  Lookup employee by email dan pembentukan session dari hasil query yang trusted.

- `apps/api/app/core/security.py`
  Pembuatan JWT, decoding token, pembentukan `SessionContext`, dan role guard helper.

- `apps/api/app/services/cache.py`
  Registry LRU cache in-memory beserta namespace statisnya.

- `apps/api/app/services/redis.py`
  Inisialisasi dan penutupan Redis client.

## Cara Memahami Phase 1 Secara Sederhana

Kalau disederhanakan, Phase 1 bekerja seperti ini:

1. API dinyalakan dan dependency dasar disiapkan
2. sistem mengecek apakah database, Redis, dan cache siap
3. user login dengan email
4. backend mencari employee yang valid
5. backend membuat JWT dengan session context yang trusted
6. request berikutnya membaca token itu untuk menentukan siapa user dan company-nya

Inti Phase 1 adalah:
- memastikan sistem siap
- memastikan identitas user jelas
- memastikan company context jelas
- memastikan fase lain selalu bekerja di atas session yang trusted
