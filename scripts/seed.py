"""
Seed the database with realistic Indonesian HR demo data.

Usage:
    python scripts/seed.py              # seed all (skip if data exists)
    python scripts/seed.py --reset      # drop all data first, then seed

Requires:
    pip install psycopg2-binary python-dotenv
"""

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        print("[ERROR] .env file not found.")
        sys.exit(1)
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def normalize_database_url(database_url: str) -> str:
    # psycopg2 expects a standard PostgreSQL DSN, not SQLAlchemy async dialects.
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


SEED_SQL = """
-- ─── Company ──────────────────────────────────────────────────────────────────
INSERT INTO companies (id, name, industry) VALUES
    ('00000000-0000-0000-0000-000000000001', 'PT Maju Bersama Tbk', 'Technology')
ON CONFLICT (id) DO NOTHING;

-- ─── Departments ──────────────────────────────────────────────────────────────
INSERT INTO departments (id, company_id, parent_id, name) VALUES
    ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', NULL, 'IT'),
    ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', NULL, 'Human Resources')
ON CONFLICT (company_id, name) DO NOTHING;

-- ─── Employees ────────────────────────────────────────────────────────────────
-- 1. HR Admin
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000002', NULL,
        'Siti Rahayu', 'siti.rahayu@majubersama.id', 'HR Manager',
        'permanent', 'active', 'hr_admin', '2021-01-15')
ON CONFLICT (company_id, email) DO NOTHING;

-- 2. IT Admin
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000001', NULL,
        'Andi Wirawan', 'andi.wirawan@majubersama.id', 'IT Administrator',
        'permanent', 'active', 'it_admin', '2021-03-01')
ON CONFLICT (company_id, email) DO NOTHING;

-- 3. Tech Lead IT
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000001', NULL,
        'Budi Santoso', 'budi.santoso@majubersama.id', 'Tech Lead',
        'permanent', 'active', 'employee', '2022-01-10')
ON CONFLICT (company_id, email) DO NOTHING;

-- 4. Fakhrul Muhammad Rijal - Software Engineer
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, discord_user_id, join_date) VALUES
    ('20000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000003',
        'Fakhrul Muhammad Rijal', 'fakhrul.rijal@majubersama.id', 'Software Engineer',
        'permanent', 'active', 'employee', '851293259510710323', '2023-06-01')
ON CONFLICT (company_id, email) DO NOTHING;

-- 5. HR Operations Specialist
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001',
        'Dina Pratama', 'dina.pratama@majubersama.id', 'HR Operations Specialist',
        'permanent', 'active', 'employee', '2023-02-13')
ON CONFLICT (company_id, email) DO NOTHING;

-- 6. Payroll and Benefits Specialist
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000006', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001',
        'Rina Maheswari', 'rina.maheswari@majubersama.id', 'Payroll and Benefits Specialist',
        'permanent', 'active', 'employee', '2023-04-10')
ON CONFLICT (company_id, email) DO NOTHING;

-- 7. Talent Acquisition Specialist
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000007', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001',
        'Nadya Putri', 'nadya.putri@majubersama.id', 'Talent Acquisition Specialist',
        'permanent', 'active', 'employee', '2023-05-08')
ON CONFLICT (company_id, email) DO NOTHING;

-- 8. HR Business Partner
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000008', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001',
        'Arif Nugroho', 'arif.nugroho@majubersama.id', 'HR Business Partner',
        'permanent', 'active', 'employee', '2022-11-21')
ON CONFLICT (company_id, email) DO NOTHING;

-- 9. IT Support Specialist
INSERT INTO employees (id, company_id, department_id, manager_id, name, email, position, employment_type, employment_status, role, join_date) VALUES
    ('20000000-0000-0000-0000-000000000009', '00000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000002',
        'Kevin Saputra', 'kevin.saputra@majubersama.id', 'IT Support Specialist',
        'permanent', 'active', 'employee', '2023-07-03')
ON CONFLICT (company_id, email) DO NOTHING;

-- Set Tech Lead as head of IT department
UPDATE departments
SET head_employee_id = '20000000-0000-0000-0000-000000000003'
WHERE id = '10000000-0000-0000-0000-000000000001';

-- Set HR Manager as head of HR department
UPDATE departments
SET head_employee_id = '20000000-0000-0000-0000-000000000001'
WHERE id = '10000000-0000-0000-0000-000000000002';

-- ─── Personal Infos ───────────────────────────────────────────────────────────
INSERT INTO personal_infos (employee_id, phone, address, bank_account, emergency_contact, emergency_phone) VALUES
    ('20000000-0000-0000-0000-000000000001', '+62811111111', 'Jl. Sudirman No.1, Jakarta Selatan', '1234567890', 'Agus Rahayu (Suami)', '+62822222222'),
    ('20000000-0000-0000-0000-000000000002', '+62833333333', 'Jl. Gatot Subroto No.10, Jakarta Selatan', '2345678901', 'Nina Wirawan (Istri)', '+62844444444'),
    ('20000000-0000-0000-0000-000000000003', '+62855555555', 'Jl. Rasuna Said No.5, Jakarta Selatan', '3456789012', 'Rina Santoso (Istri)', '+62866666666'),
    ('20000000-0000-0000-0000-000000000004', '+62877777777', 'Jl. Kuningan No.15, Jakarta Selatan', '4567890123', 'Muhammad Rijal (Ayah)', '+62888888888')
ON CONFLICT (employee_id) DO NOTHING;

-- ─── Time Offs (balance 2026) ─────────────────────────────────────────────────
INSERT INTO time_offs (employee_id, leave_type, record_type, total_days, used_days, remaining_days, year) VALUES
    ('20000000-0000-0000-0000-000000000001', 'annual_leave', 'balance', 12, 2, 10, 2026),
    ('20000000-0000-0000-0000-000000000002', 'annual_leave', 'balance', 12, 0, 12, 2026),
    ('20000000-0000-0000-0000-000000000003', 'annual_leave', 'balance', 12, 3, 9,  2026),
    ('20000000-0000-0000-0000-000000000004', 'annual_leave', 'balance', 12, 1, 11, 2026)
ON CONFLICT DO NOTHING;

-- Leave request sample for Fakhrul
INSERT INTO time_offs (employee_id, leave_type, record_type, total_days, start_date, end_date, status, reason, year) VALUES
    ('20000000-0000-0000-0000-000000000004', 'annual_leave', 'request', 1, '2026-03-20', '2026-03-20', 'approved', 'Urusan keluarga', 2026)
ON CONFLICT DO NOTHING;

-- ─── Attendance (last 7 working days for Fakhrul) ────────────────────────────
INSERT INTO attendance (employee_id, attendance_date, check_in, check_out, status) VALUES
    ('20000000-0000-0000-0000-000000000004', '2026-03-25', '08:52', '17:05', 'present'),
    ('20000000-0000-0000-0000-000000000004', '2026-03-26', '09:01', '17:00', 'present'),
    ('20000000-0000-0000-0000-000000000004', '2026-03-27', '08:48', '17:10', 'present'),
    ('20000000-0000-0000-0000-000000000004', '2026-03-28', NULL,    NULL,    'wfh'),
    ('20000000-0000-0000-0000-000000000004', '2026-03-31', '09:15', '17:00', 'late'),
    ('20000000-0000-0000-0000-000000000004', '2026-04-01', '08:55', '17:05', 'present'),
    ('20000000-0000-0000-0000-000000000004', '2026-04-02', '08:50', '17:00', 'present')
ON CONFLICT (employee_id, attendance_date) DO NOTHING;

-- ─── Payroll (Jan–Mar 2026 for Fakhrul) ──────────────────────────────────────
INSERT INTO payroll (employee_id, month, year, basic_salary, allowances, gross_salary, deductions, bpjs_kesehatan, bpjs_ketenagakerjaan, pph21, net_pay, payment_status, payment_date) VALUES
    ('20000000-0000-0000-0000-000000000004', 1, 2026, 12000000, 1500000, 13500000, 400000, 144000, 240000, 700000, 12016000, 'paid', '2026-01-28'),
    ('20000000-0000-0000-0000-000000000004', 2, 2026, 12000000, 1500000, 13500000, 400000, 144000, 240000, 700000, 12016000, 'paid', '2026-02-25'),
    ('20000000-0000-0000-0000-000000000004', 3, 2026, 12000000, 1500000, 13500000, 400000, 144000, 240000, 700000, 12016000, 'paid', '2026-03-27')
ON CONFLICT (employee_id, year, month) DO NOTHING;

-- ─── Personal Info (Fakhrul) ──────────────────────────────────────────────────
INSERT INTO personal_infos (employee_id, phone, address, national_id, tax_id, bank_account, emergency_contact, emergency_phone) VALUES
    ('20000000-0000-0000-0000-000000000004', '081234567890', 'Jl. Kebon Jeruk No. 123, Jakarta Barat', '3171234567890001', '01.234.567.8-901.000', 'BCA - 1234567890', 'Siti Aminah', '081298765432')
ON CONFLICT (employee_id) DO NOTHING;

-- ─── Company Rules ────────────────────────────────────────────────────────────
INSERT INTO company_rules (id, company_id, title, category, content, metadata, effective_date, is_active) VALUES
    ('30000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Reimbursement Transportasi',
        'benefit',
        'Karyawan dapat mengajukan reimbursement untuk biaya transportasi operasional seperti taksi, ojek online, tol, dan parkir saat menjalankan tugas kantor. Batas maksimal reimbursement adalah Rp 1.000.000 per bulan. Klaim wajib dilampiri bukti pembayaran digital (e-receipt), karcis tol, atau struk parkir asli. Pengajuan dilakukan maksimal H+7 setelah tanggal pengeluaran.',
        '{"policy_key":"benefit.transportation_reimbursement","case_type":"transportation","coverage_type":"reimbursement","amount_limit":{"max_value":1000000,"unit":"idr","period":"month"},"frequency_limit":null,"eligible_levels":["permanent","contract"],"required_documents":["e-receipt","karcis tol","struk parkir"],"constraints":{"max_age_days":7},"simulation_mode":true,"affects_balance":false,"approval_chain":["atasan langsung"]}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Reimbursement Komunikasi',
        'benefit',
        'Karyawan berhak atas reimbursement biaya paket data internet atau pulsa telepon maksimal Rp 500.000 per bulan untuk mendukung kerja remote atau WFH. Klaim wajib melampirkan invoice tagihan bulanan atau bukti pembelian pulsa/paket data. Biaya pemasangan awal internet rumah tidak ditanggung.',
        '{"policy_key":"benefit.communication_reimbursement","case_type":"internet_allowance","coverage_type":"reimbursement","amount_limit":{"max_value":500000,"unit":"idr","period":"month"},"frequency_limit":null,"eligible_levels":["permanent","contract"],"required_documents":["invoice","bukti pembelian"],"constraints":{"excluded_keywords":["pemasangan awal"]},"simulation_mode":true,"affects_balance":false,"approval_chain":["atasan langsung"]}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Cuti Tahunan',
        'leave',
        'Karyawan tetap (permanent) berhak atas 12 hari cuti tahunan per tahun kalender. Cuti tahunan dapat diambil setelah karyawan melewati masa percobaan (probation period) selama 3 bulan. Pengajuan cuti harus dilakukan minimal 3 hari kerja sebelumnya melalui sistem HR, kecuali untuk keadaan darurat. Cuti yang tidak diambil dalam satu tahun kalender tidak dapat dibawa ke tahun berikutnya (tidak ada carry-over). Karyawan kontrak dan magang mendapat jatah cuti pro-rata sesuai durasi kontrak.',
        '{"policy_key":"leave.annual_leave","case_type":"annual_leave","coverage_type":"entitlement","amount_limit":{"max_value":12,"unit":"day","period":"year"},"frequency_limit":null,"eligible_levels":["permanent","contract","intern"],"required_documents":[],"constraints":{"min_tenure_months":3,"carry_over_allowed":false,"pro_rata_levels":["contract","intern"],"request_notice_days":3},"simulation_mode":true,"affects_balance":true,"balance_type":"annual_leave","approval_chain":["atasan langsung"]}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Cuti Sakit',
        'leave',
        'Karyawan berhak atas cuti sakit berbayar dengan syarat melampirkan surat keterangan dokter. Untuk ketidakhadiran 1-2 hari karena sakit, surat dokter dapat diserahkan maksimal H+2 setelah masuk kerja. Ketidakhadiran lebih dari 2 hari wajib disertai surat keterangan dokter yang diserahkan pada hari pertama sakit atau dikirimkan secara digital. Cuti sakit tidak mengurangi jatah cuti tahunan.',
        '{"policy_key":"leave.sick_leave","case_type":"sick_leave","coverage_type":"entitlement","amount_limit":null,"frequency_limit":null,"eligible_levels":["permanent","contract","intern"],"required_documents":["surat dokter"],"constraints":{"digital_submission_allowed":true,"doctor_note_required_for_extended_absence":true},"simulation_mode":true,"affects_balance":false,"approval_chain":["atasan langsung"]}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Work From Home (WFH)',
        'work_arrangement',
        'Karyawan diperbolehkan bekerja dari rumah (WFH) maksimal 2 hari per minggu, dengan persetujuan atasan langsung. Karyawan yang sedang dalam masa probation tidak diperkenankan WFH kecuali atas persetujuan khusus dari HR Manager. Pada hari WFH, karyawan wajib tetap dapat dihubungi dan hadir dalam meeting yang dijadwalkan. WFH tidak berlaku pada hari dengan kegiatan kantor wajib seperti all-hands meeting atau town hall.',
        '{"policy_key":"work_arrangement.wfh","case_type":"wfh","coverage_type":"arrangement","amount_limit":null,"frequency_limit":{"max_count":2,"unit":"day","period":"week"},"eligible_levels":["permanent","contract","intern"],"required_documents":[],"constraints":{"excluded_levels":["probation"],"manager_approval_required":true,"blocked_event_keywords":["all-hands","town hall"]}}'::jsonb,
        '2024-06-01', true),
    ('30000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Jam Kerja dan Keterlambatan',
        'attendance',
        'Jam kerja standar adalah 08:00 - 17:00 WIB, Senin sampai Jumat. Toleransi keterlambatan adalah 15 menit. Keterlambatan lebih dari 15 menit wajib dikompensasi dengan perpanjangan jam kerja di hari yang sama atau atas persetujuan atasan. Keterlambatan yang tidak dikomunikasikan lebih dari 3 kali dalam satu bulan akan menjadi catatan dalam evaluasi kinerja.',
        '{"policy_key":"attendance.working_hours","case_type":"attendance","coverage_type":"compliance","amount_limit":null,"frequency_limit":{"max_count":3,"unit":"late_case","period":"month"},"eligible_levels":["permanent","contract","intern"],"required_documents":[],"constraints":{"lateness_tolerance_minutes":15}}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Gaji dan Kompensasi',
        'payroll',
        'Gaji dibayarkan setiap akhir bulan, selambat-lambatnya tanggal 28 setiap bulan. Komponen gaji terdiri dari gaji pokok, tunjangan tetap (transport dan makan), dan tunjangan variabel (lembur jika ada). Potongan wajib meliputi iuran BPJS Kesehatan (1% dari gaji pokok), iuran BPJS Ketenagakerjaan (2% dari gaji pokok), dan PPh 21 sesuai peraturan perpajakan yang berlaku. Slip gaji dikirimkan melalui email setiap bulan pada tanggal pembayaran gaji.',
        '{"policy_key":"payroll.salary_compensation","case_type":"payroll","coverage_type":"schedule","amount_limit":null,"frequency_limit":{"max_count":1,"unit":"payment","period":"month"},"eligible_levels":["permanent","contract","intern"],"required_documents":[],"constraints":{"salary_payment_day_max":28,"payslip_delivery":"payment_day","fixed_allowances":["transport","makan"]}}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000007', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Reimbursement Mental Health',
        'benefit',
        'Perusahaan memberikan reimbursement konsultasi psikolog atau layanan mental health online maksimal Rp 300.000 per sesi dan maksimal 6 sesi per tahun kalender. Klaim wajib dilampiri invoice atau receipt serta bukti bayar yang jelas. Reimbursement tidak mencakup layanan yang tidak terkait konsultasi profesional seperti subscription konten wellness.',
        '{"policy_key":"benefit.mental_health_reimbursement","case_type":"mental_health","coverage_type":"reimbursement","amount_limit":{"max_value":300000,"unit":"idr","period":"session"},"frequency_limit":{"max_count":6,"unit":"session","period":"year"},"eligible_levels":["permanent","contract"],"required_documents":["invoice","receipt","bukti bayar"],"constraints":{"excluded_keywords":["subscription","wellness"],"requires_professional_service":true}}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000008', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Reimbursement Optical',
        'benefit',
        'Perusahaan memberikan reimbursement kacamata atau optical maksimal Rp 750.000 per tahun kalender. Klaim wajib dilampiri kuitansi atau invoice pembelian. Reimbursement optical hanya berlaku untuk lensa, frame, atau paket kacamata dan tidak mencakup aksesoris non-medis.',
        '{"policy_key":"benefit.optical_reimbursement","case_type":"optical","coverage_type":"reimbursement","amount_limit":{"max_value":750000,"unit":"idr","period":"year"},"frequency_limit":{"max_count":1,"unit":"claim","period":"year"},"eligible_levels":["permanent","contract"],"required_documents":["kuitansi","invoice"],"constraints":{"excluded_keywords":["aksesoris","non medis"]}}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000009', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Reimbursement Medical Outpatient',
        'benefit',
        'Perusahaan memberikan reimbursement rawat jalan atau medical outpatient maksimal Rp 500.000 per kunjungan dan maksimal 10 klaim per tahun kalender. Klaim wajib dilampiri invoice atau receipt, bukti bayar, serta surat dokter atau resep bila ada tindakan medis. Reimbursement tidak mencakup vitamin, suplemen, atau medical check-up executive yang tidak direkomendasikan dokter.',
        '{"policy_key":"benefit.medical_outpatient_reimbursement","case_type":"medical","coverage_type":"reimbursement","amount_limit":{"max_value":500000,"unit":"idr","period":"visit"},"frequency_limit":{"max_count":10,"unit":"claim","period":"year"},"eligible_levels":["permanent","contract"],"required_documents":["invoice","receipt","bukti bayar","surat dokter","resep"],"constraints":{"excluded_keywords":["vitamin","suplemen","medical check-up executive"]}}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Tunjangan Komunikasi dan Internet',
        'payroll',
        'Perusahaan memberikan tunjangan komunikasi dan internet sebesar Rp 250.000 per bulan untuk karyawan tetap dan karyawan kontrak aktif. Tunjangan ini tidak berlaku untuk karyawan magang atau karyawan yang masih dalam masa probation. Tunjangan dibayarkan bersama payroll bulanan dan tidak memerlukan klaim manual.',
        '{"policy_key":"payroll.communication_allowance","case_type":"allowance","coverage_type":"allowance","amount_limit":{"max_value":250000,"unit":"idr","period":"month"},"frequency_limit":{"max_count":1,"unit":"allowance","period":"month"},"eligible_levels":["permanent","contract"],"required_documents":[],"constraints":{"excluded_levels":["intern","probation"],"paid_with_payroll":true}}'::jsonb,
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000006', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Kode Etik dan Perilaku',
        'conduct',
        'Seluruh karyawan wajib menjaga integritas dan profesionalisme dalam bekerja. Dilarang melakukan tindakan diskriminasi, pelecehan, atau intimidasi dalam bentuk apapun di lingkungan kerja. Informasi rahasia perusahaan, termasuk data karyawan, data klien, dan strategi bisnis, wajib dijaga kerahasiaannya. Pelanggaran terhadap kode etik dapat berujung pada tindakan disipliner hingga pemutusan hubungan kerja.',
        '{"policy_key":"conduct.code_of_conduct","case_type":"conduct","coverage_type":"governance","amount_limit":null,"frequency_limit":null,"eligible_levels":["permanent","contract","intern"],"required_documents":[],"constraints":{}}'::jsonb,
        '2024-01-01', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO responsibility_routes (
    id,
    company_id,
    topic_key,
    department_id,
    primary_employee_id,
    alternate_employee_id,
    recommended_channel,
    preparation_checklist,
    metadata,
    is_active
) VALUES
    (
        '40000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'recruiting',
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000007',
        '20000000-0000-0000-0000-000000000001',
        'chat atau email internal recruiter / TA',
        '["Siapkan nama kandidat dan posisi yang ingin direferensikan.", "Kalau ada CV, LinkedIn, atau ringkasan profil kandidat, siapkan juga sebelum menghubungi tim terkait."]'::jsonb,
        '{"routing_type": "functional_owner"}'::jsonb,
        true
    ),
    (
        '40000000-0000-0000-0000-000000000002',
        '00000000-0000-0000-0000-000000000001',
        'payroll_benefits',
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000006',
        '20000000-0000-0000-0000-000000000005',
        'chat atau email internal payroll / benefits',
        '["Siapkan periode, nominal, atau jenis benefit yang ingin ditanyakan.", "Kalau ada bukti transaksi atau dokumen pendukung, siapkan juga sebelum menghubungi tim terkait."]'::jsonb,
        '{"routing_type": "functional_owner"}'::jsonb,
        true
    ),
    (
        '40000000-0000-0000-0000-000000000003',
        '00000000-0000-0000-0000-000000000001',
        'people_partner',
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000008',
        '20000000-0000-0000-0000-000000000001',
        'chat atau email internal HRBP / people partner',
        '["Siapkan konteks tim, concern utama, dan outcome yang ingin kamu diskusikan.", "Kalau menyangkut karier atau internal move, jelaskan role saat ini dan arah role yang kamu tuju."]'::jsonb,
        '{"routing_type": "functional_owner"}'::jsonb,
        true
    ),
    (
        '40000000-0000-0000-0000-000000000004',
        '00000000-0000-0000-0000-000000000001',
        'it_support',
        '10000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000009',
        '20000000-0000-0000-0000-000000000002',
        'chat atau tiket internal IT support',
        '["Siapkan nama sistem, perangkat, atau akun yang bermasalah.", "Kalau ada error message atau screenshot, siapkan juga untuk mempercepat triage."]'::jsonb,
        '{"routing_type": "functional_owner"}'::jsonb,
        true
    ),
    (
        '40000000-0000-0000-0000-000000000005',
        '00000000-0000-0000-0000-000000000001',
        'hr_operations',
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000005',
        '20000000-0000-0000-0000-000000000001',
        'chat atau email internal tim HR operations',
        '["Siapkan ringkasan topik atau issue yang ingin kamu bahas.", "Kalau menyangkut periode tertentu, sebutkan juga bulan atau tanggal yang relevan."]'::jsonb,
        '{"routing_type": "functional_owner"}'::jsonb,
        true
    ),
    (
        '40000000-0000-0000-0000-000000000006',
        '00000000-0000-0000-0000-000000000001',
        'leave_operations',
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000005',
        '20000000-0000-0000-0000-000000000001',
        'chat atasan langsung atau email internal HR operations',
        '["Siapkan jenis cuti, tanggal, dan konteks singkat kebutuhanmu.", "Kalau menyangkut izin sakit, siapkan juga dokumen pendukung seperti surat dokter bila sudah ada."]'::jsonb,
        '{"routing_type": "functional_owner"}'::jsonb,
        true
    ),
    (
        '40000000-0000-0000-0000-000000000007',
        '00000000-0000-0000-0000-000000000001',
        'attendance_correction',
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000005',
        '20000000-0000-0000-0000-000000000001',
        'chat atasan langsung atau portal internal HR',
        '["Siapkan tanggal absensi yang salah.", "Tentukan status yang benar (WFH/WFO/Sakit).", "Berikan alasan singkat koreksi (misal: lupa check-in)."]'::jsonb,
        '{"routing_type": "functional_owner"}'::jsonb,
        true
    )
ON CONFLICT (company_id, topic_key) DO UPDATE SET
    department_id = EXCLUDED.department_id,
    primary_employee_id = EXCLUDED.primary_employee_id,
    alternate_employee_id = EXCLUDED.alternate_employee_id,
    recommended_channel = EXCLUDED.recommended_channel,
    preparation_checklist = EXCLUDED.preparation_checklist,
    metadata = EXCLUDED.metadata,
    is_active = EXCLUDED.is_active;

INSERT INTO classifier_keyword_overrides (
    company_id,
    classifier_type,
    target_key,
    keyword,
    weight,
    is_active
) VALUES
    (
        '00000000-0000-0000-0000-000000000001',
        'intent',
        'time_off_balance',
        'cuti sisa',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'intent',
        'payroll_document_request',
        'slip bulan ini',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'sensitivity',
        'medium',
        'diintimidasi',
        2,
        true
    )
ON CONFLICT (company_id, classifier_type, target_key, keyword) DO NOTHING;

INSERT INTO intent_examples (
    company_id,
    intent_key,
    example_text,
    language,
    weight,
    is_active
) VALUES
    (
        '00000000-0000-0000-0000-000000000001',
        'time_off_balance',
        'cuti saya sisa berapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'time_off_balance',
        'jatah cuti saya tahun ini berapa',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'time_off_request_status',
        'status pengajuan cuti saya bagaimana',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'time_off_request_status',
        'saya mau izin sakit ke mana saya harus izin',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'time_off_request_status',
        'atasan yang approve cuti saya siapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'time_off_balance',
        'kapan saldo cuti saya nambah',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'time_off_simulation',
        'kalau saya cuti 3 hari sisa cuti saya berapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'payroll_document_request',
        'tolong kirim payslip bulan ini',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'payroll_document_request',
        'saya butuh slip gaji bulan lalu',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'payroll_info',
        'gaji saya bulan ini berapa',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'payroll_info',
        'potongan gaji saya apa saja bulan ini',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'payroll_info',
        'kapan gaji bulan ini cair',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'payroll_info',
        'slip saya belum keluar kenapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'attendance_review',
        'rata rata saya masuk jam berapa sebulan terakhir',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'attendance_review',
        'jam masuk kantor saya bulan kemarin',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'attendance_review',
        'tolong cek absensi saya bulan lalu',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'personal_profile',
        'siapa manager saya',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'personal_profile',
        'atasan aku siapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'personal_profile',
        'posisi saya apa di perusahaan ini',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'personal_profile',
        'saya karyawan baru harus dibimbing siapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'apa aturan carry over cuti',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'bagaimana kebijakan wfh di kantor',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'saya tadi ke psikolog online 150 ribu bisa reimburse nggak',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'kalau reimburse kacamata limit saya berapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'saya masih probation 2 bulan bisa ambil cuti tahunan nggak',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'kalau gaji dibayar tanggal 30 masih sesuai policy nggak',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'saya magang apakah dapat tunjangan internet 250 ribu per bulan',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_policy',
        'rawat jalan 400 ribu bisa claim nggak',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_structure',
        'siapa kepala departemen hr',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_structure',
        'kalau bingung administrasi atau hr harus tanya siapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_structure',
        'saya karyawan baru harus hubungi siapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_structure',
        'kalau mau refer temen harus ke siapa',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_structure',
        'kalau mau nanya payroll ke siapa ya',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company_structure',
        'kalau ada issue teknis internal harus ke siapa dulu',
        'id',
        2,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'employee_wellbeing_concern',
        'saya merasa dibully di kantor',
        'id',
        3,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'employee_wellbeing_concern',
        'saya mengalami pelecehan di tempat kerja',
        'id',
        3,
        true
    )
ON CONFLICT (company_id, intent_key, example_text) DO NOTHING;

INSERT INTO agent_capabilities (
    company_id,
    agent_key,
    title,
    description,
    supported_intents,
    data_sources,
    execution_mode,
    requires_trusted_employee_context,
    can_run_in_parallel,
    sample_queries,
    is_active
) VALUES
    (
        '00000000-0000-0000-0000-000000000001',
        'hr-data-agent',
        'Employee HR Data Agent',
        'Menangani payroll, attendance, time off, dan personal profile berdasarkan trusted employee session.',
        '["payroll_info", "payroll_document_request", "attendance_review", "time_off_balance", "time_off_request_status", "personal_profile"]'::jsonb,
        '["employees", "personal_infos", "payroll", "attendance", "time_offs"]'::jsonb,
        'structured_lookup',
        true,
        true,
        '["cuti saya sisa berapa", "payslip bulan ini", "rata rata saya masuk jam berapa"]'::jsonb,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'company-agent',
        'Company Policy and Structure Agent',
        'Menangani company policy, handbook, department structure, dan referensi company-level lainnya.',
        '["company_policy", "company_structure"]'::jsonb,
        '["company_rules", "company_rule_chunks", "departments", "employees"]'::jsonb,
        'policy_lookup',
        false,
        true,
        '["apa aturan carry over cuti", "siapa kepala departemen hr", "kalau bingung administrasi atau hr harus tanya siapa", "kalau mau refer temen harus ke siapa", "kalau ada issue teknis internal harus ke siapa dulu", "saya tadi ke psikolog online 150 ribu bisa reimburse nggak", "kalau reimburse kacamata limit saya berapa", "saya masih probation 2 bulan bisa ambil cuti tahunan nggak", "kalau gaji dibayar tanggal 30 masih sesuai policy nggak", "saya magang apakah dapat tunjangan internet 250 ribu per bulan", "rawat jalan 400 ribu bisa claim nggak"]'::jsonb,
        true
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        'file-agent',
        'Attachment Extraction Agent',
        'Menangani ekstraksi teks dan metadata dari attachment sebelum agent lain mengambil keputusan lanjutan.',
        '["general_hr_support"]'::jsonb,
        '["attachments"]'::jsonb,
        'file_extraction',
        false,
        false,
        '["tolong cek lampiran ini", "baca pdf ini", "cek dokumen yang saya unggah"]'::jsonb,
        true
    )
ON CONFLICT (company_id, agent_key) DO NOTHING;

-- Phase 2 demo rules
INSERT INTO rules (id, company_id, name, description, trigger, intent_key, sensitivity_threshold, is_enabled) VALUES
    (
        '60000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'Payroll document follow-up',
        'Generate and route payroll-related documents after a resolved conversation.',
        'conversation_resolved',
        'payroll_document_request',
        'medium',
        true
    ),
    (
        '60000000-0000-0000-0000-000000000002',
        '00000000-0000-0000-0000-000000000001',
        'Sensitive wellbeing escalation',
        'Create a manual review counseling task when sensitive wellbeing signals are detected.',
        'sensitivity_detected',
        'employee_wellbeing_concern',
        'high',
        true
    ),
    (
        '60000000-0000-0000-0000-000000000003',
        '00000000-0000-0000-0000-000000000001',
        'Unsafe workplace escalation',
        'Create a manual review escalation task when an unsafe workplace report is detected.',
        'sensitivity_detected',
        'sensitive_unsafe_workplace_case',
        'high',
        true
    ),
    (
        '60000000-0000-0000-0000-000000000004',
        '00000000-0000-0000-0000-000000000001',
        'Harassment escalation',
        'Create a manual review escalation task when harassment or discrimination is reported.',
        'sensitivity_detected',
        'sensitive_harassment_case',
        'high',
        true
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO rule_actions (
    id,
    rule_id,
    action_type,
    title_template,
    summary_template,
    priority,
    delivery_channels,
    payload_template
) VALUES
    (
        '61000000-0000-0000-0000-000000000001',
        '60000000-0000-0000-0000-000000000001',
        'document_generation',
        'Generate salary slip',
        'Prepare the requested salary slip and queue outbound delivery.',
        'medium',
        ARRAY['email', 'in_app', 'webhook']::delivery_channel_enum[],
        $${
            "document_type": "salary_slip",
            "template_key": "payroll_salary_slip_v1",
            "parameters": {
                "month": 3,
                "year": 2026
            },
            "delivery_note": "Send the generated slip to the employee after verification."
        }$$::jsonb
    ),
    (
        '61000000-0000-0000-0000-000000000002',
        '60000000-0000-0000-0000-000000000002',
        'counseling_task',
        'Open counseling review task',
        'Escalate a sensitive wellbeing case for manual HR handling.',
        'high',
        ARRAY['manual_review']::delivery_channel_enum[],
        $${
            "topic": "Wellbeing follow-up",
            "assigned_role": "hr_admin",
            "due_at": "2026-04-07T09:00:00Z",
            "note": "Review the conversation details before any external follow-up."
        }$$::jsonb
    ),
    (
        '61000000-0000-0000-0000-000000000003',
        '60000000-0000-0000-0000-000000000003',
        'escalation',
        'Open unsafe workplace review',
        'Sensitive workplace safety concern detected and queued for manual HR review.',
        'high',
        ARRAY['manual_review']::delivery_channel_enum[],
        $${
            "reason": "Unsafe workplace report requires manual review.",
            "target_role": "hr_admin",
            "escalation_level": 2,
            "note": "Review the report and triage the safest next step before any outbound follow-up."
        }$$::jsonb
    ),
    (
        '61000000-0000-0000-0000-000000000004',
        '60000000-0000-0000-0000-000000000004',
        'escalation',
        'Open harassment report review',
        'Sensitive harassment or discrimination report detected and queued for manual HR review.',
        'high',
        ARRAY['manual_review']::delivery_channel_enum[],
        $${
            "reason": "Harassment or discrimination report requires manual review.",
            "target_role": "hr_admin",
            "escalation_level": 3,
            "note": "Review the report, preserve confidentiality, and decide the formal handling path."
        }$$::jsonb
    )
ON CONFLICT (id) DO NOTHING;

-- Phase 2 demo webhooks
INSERT INTO webhooks (
    id,
    company_id,
    name,
    target_url,
    subscribed_events,
    secret,
    is_active
) VALUES
    (
        '70000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'Primary HRIS webhook',
        'https://example.com/webhooks/hr-ai',
        ARRAY['action.created', 'action.executed', 'action.delivery_requested']::webhook_event_enum[],
        'super-secret-signing-key-0001',
        true
    )
ON CONFLICT (id) DO NOTHING;

-- Phase 4 demo conversations
INSERT INTO conversations (
    id,
    company_id,
    employee_id,
    title,
    status,
    metadata,
    last_message_at,
    created_at,
    updated_at
) VALUES
    (
        '40000000-0000-0000-0000-000000000101',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        'Payroll self-service chat',
        'resolved',
        $${
            "source": "seed_demo",
            "entrypoint": "api"
        }$$::jsonb,
        '2026-04-03T08:15:00Z',
        '2026-04-03T08:10:00Z',
        '2026-04-03T08:15:00Z'
    ),
    (
        '40000000-0000-0000-0000-000000000102',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        'Sensitive wellbeing concern',
        'escalated',
        $${
            "source": "seed_demo",
            "entrypoint": "api"
        }$$::jsonb,
        '2026-04-03T09:00:00Z',
        '2026-04-03T09:00:00Z',
        '2026-04-03T09:00:00Z'
    ),
    (
        '40000000-0000-0000-0000-000000000103',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        'Attendance reminder follow-up',
        'active',
        $${
            "source": "seed_demo",
            "entrypoint": "api"
        }$$::jsonb,
        '2026-04-03T10:00:00Z',
        '2026-04-03T10:00:00Z',
        '2026-04-03T10:00:00Z'
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO conversation_messages (
    id,
    conversation_id,
    company_id,
    employee_id,
    role,
    content,
    attachments,
    metadata,
    created_at
) VALUES
    (
        '41000000-0000-0000-0000-000000000001',
        '40000000-0000-0000-0000-000000000101',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        'user',
        'Tolong bantu kirim slip gaji bulan Maret 2026.',
        '[]'::jsonb,
        $${
            "channel": "seed_demo"
        }$$::jsonb,
        '2026-04-03T08:10:00Z'
    ),
    (
        '41000000-0000-0000-0000-000000000002',
        '40000000-0000-0000-0000-000000000101',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        'assistant',
        'Permintaan slip gaji sudah diproses dan ditautkan ke action follow-up.',
        '[]'::jsonb,
        $${
            "channel": "seed_demo",
            "route": "hr_data"
        }$$::jsonb,
        '2026-04-03T08:15:00Z'
    ),
    (
        '41000000-0000-0000-0000-000000000003',
        '40000000-0000-0000-0000-000000000102',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        'user',
        'Saya merasa dibully dan butuh bantuan.',
        '[]'::jsonb,
        $${
            "channel": "seed_demo"
        }$$::jsonb,
        '2026-04-03T09:00:00Z'
    ),
    (
        '41000000-0000-0000-0000-000000000004',
        '40000000-0000-0000-0000-000000000102',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        'assistant',
        'Topik ini sensitif dan sudah diarahkan ke jalur penanganan HR yang lebih aman.',
        '[]'::jsonb,
        $${
            "channel": "seed_demo",
            "route": "sensitive_redirect"
        }$$::jsonb,
        '2026-04-03T09:00:30Z'
    )
ON CONFLICT (id) DO NOTHING;

-- Phase 2 demo actions
INSERT INTO actions (
    id,
    company_id,
    employee_id,
    conversation_id,
    rule_id,
    type,
    title,
    summary,
    status,
    priority,
    sensitivity,
    delivery_channels,
    payload,
    execution_result,
    metadata,
    last_executed_at
) VALUES
    (
        '50000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        '40000000-0000-0000-0000-000000000101',
        '60000000-0000-0000-0000-000000000001',
        'document_generation',
        'Generate salary slip for March 2026',
        'Prepare the payroll document and queue delivery for the employee.',
        'completed',
        'medium',
        'low',
        ARRAY['email', 'in_app', 'webhook']::delivery_channel_enum[],
        $${
            "type": "document_generation",
            "document_type": "salary_slip",
            "template_key": "payroll_salary_slip_v1",
            "parameters": {
                "month": 3,
                "year": 2026
            },
            "delivery_note": "Generated from payroll self-service request."
        }$$::jsonb,
        $${
            "executed_at": "2026-04-03T08:15:00Z",
            "delivery_channels": ["email", "in_app", "webhook"],
            "delivery_requested": true,
            "executor_note": "Seeded completed action for Phase 2 demo.",
            "delivery_mode": "direct_delivery"
        }$$::jsonb,
        $${
            "source": "seed_demo",
            "intent_key": "payroll_document_request"
        }$$::jsonb,
        '2026-04-03T08:15:00Z'
    ),
    (
        '50000000-0000-0000-0000-000000000002',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        '40000000-0000-0000-0000-000000000102',
        '60000000-0000-0000-0000-000000000002',
        'counseling_task',
        'Open wellbeing counseling review',
        'Sensitive concern detected and routed to manual HR review.',
        'pending',
        'high',
        'high',
        ARRAY['manual_review']::delivery_channel_enum[],
        $${
            "type": "counseling_task",
            "topic": "Wellbeing follow-up",
            "assigned_role": "hr_admin",
            "due_at": "2026-04-07T09:00:00Z",
            "note": "Check whether the employee needs formal counseling support."
        }$$::jsonb,
        NULL,
        $${
            "source": "seed_demo",
            "intent_key": "employee_wellbeing_concern"
        }$$::jsonb,
        NULL
    ),
    (
        '50000000-0000-0000-0000-000000000003',
        '00000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000004',
        '40000000-0000-0000-0000-000000000103',
        NULL,
        'followup_chat',
        'Send follow-up on attendance reminder',
        'Prepare an in-app follow-up message related to attendance punctuality.',
        'ready',
        'low',
        'low',
        ARRAY['in_app']::delivery_channel_enum[],
        $${
            "type": "followup_chat",
            "target_audience": "employee",
            "message_template": "Halo Fakhrul, jangan lupa check-in tepat waktu minggu ini ya.",
            "scheduled_at": "2026-04-04T01:00:00Z"
        }$$::jsonb,
        NULL,
        $${
            "source": "seed_demo",
            "intent_key": "attendance_followup"
        }$$::jsonb,
        NULL
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO action_logs (
    id,
    action_id,
    company_id,
    event_name,
    status,
    message,
    metadata,
    created_at
) VALUES
    (
        '51000000-0000-0000-0000-000000000001',
        '50000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'action.created',
        'pending',
        'Action created from payroll document rule.',
        $${
            "delivery_channels": ["email", "in_app", "webhook"]
        }$$::jsonb,
        '2026-04-03T08:10:00Z'
    ),
    (
        '51000000-0000-0000-0000-000000000002',
        '50000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'action.executed',
        'completed',
        'Action executed.',
        $${
            "delivery_requested": true,
            "delivery_mode": "direct_delivery"
        }$$::jsonb,
        '2026-04-03T08:15:00Z'
    ),
    (
        '51000000-0000-0000-0000-000000000003',
        '50000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'action.delivery_requested',
        'completed',
        'Action delivery queued.',
        $${
            "delivery_request_count": 3,
            "webhook_deliveries_queued": 1
        }$$::jsonb,
        '2026-04-03T08:16:00Z'
    ),
    (
        '51000000-0000-0000-0000-000000000004',
        '50000000-0000-0000-0000-000000000002',
        '00000000-0000-0000-0000-000000000001',
        'action.created',
        'pending',
        'Sensitive action created and held for manual review.',
        $${
            "delivery_channels": ["manual_review"]
        }$$::jsonb,
        '2026-04-03T09:00:00Z'
    ),
    (
        '51000000-0000-0000-0000-000000000005',
        '50000000-0000-0000-0000-000000000003',
        '00000000-0000-0000-0000-000000000001',
        'action.created',
        'ready',
        'Action prepared for follow-up delivery.',
        $${
            "delivery_channels": ["in_app"]
        }$$::jsonb,
        '2026-04-03T09:30:00Z'
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO action_deliveries (
    id,
    action_id,
    company_id,
    channel,
    delivery_status,
    target_reference,
    payload,
    created_at
) VALUES
    (
        '52000000-0000-0000-0000-000000000001',
        '50000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'email',
        'delivered',
        'employee:20000000-0000-0000-0000-000000000004',
        $${
            "action_id": "50000000-0000-0000-0000-000000000001",
            "action_type": "document_generation",
            "status": "completed",
            "title": "Generate salary slip for March 2026"
        }$$::jsonb,
        '2026-04-03T08:16:00Z'
    ),
    (
        '52000000-0000-0000-0000-000000000002',
        '50000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'in_app',
        'delivered',
        'employee:20000000-0000-0000-0000-000000000004',
        $${
            "action_id": "50000000-0000-0000-0000-000000000001",
            "action_type": "document_generation",
            "status": "completed",
            "title": "Generate salary slip for March 2026"
        }$$::jsonb,
        '2026-04-03T08:16:30Z'
    ),
    (
        '52000000-0000-0000-0000-000000000003',
        '50000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
        'webhook',
        'queued',
        'registered_company_webhooks',
        $${
            "action_id": "50000000-0000-0000-0000-000000000001",
            "action_type": "document_generation",
            "status": "completed",
            "title": "Generate salary slip for March 2026"
        }$$::jsonb,
        '2026-04-03T08:17:00Z'
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO webhook_deliveries (
    id,
    webhook_id,
    action_id,
    event_name,
    delivery_status,
    response_status,
    response_body,
    attempted_at
) VALUES
    (
        '53000000-0000-0000-0000-000000000001',
        '70000000-0000-0000-0000-000000000001',
        '50000000-0000-0000-0000-000000000001',
        'action.delivery_requested',
        'queued',
        202,
        '{"message":"queued for downstream HRIS processing"}',
        '2026-04-03T08:17:05Z'
    )
ON CONFLICT (id) DO NOTHING;
"""

RESET_SQL = """
DELETE FROM webhook_deliveries
WHERE webhook_id IN (
    SELECT w.id
    FROM webhooks w
    INNER JOIN companies c ON c.id = w.company_id
    WHERE c.name = 'PT Maju Bersama Tbk'
)
   OR action_id IN (
    SELECT a.id
    FROM actions a
    INNER JOIN companies c ON c.id = a.company_id
    WHERE c.name = 'PT Maju Bersama Tbk'
);
DELETE FROM action_deliveries
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM action_logs
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM actions
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM conversation_messages
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM conversations
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM rule_actions WHERE rule_id IN (
    SELECT r.id
    FROM rules r
    INNER JOIN companies c ON c.id = r.company_id
    WHERE c.name = 'PT Maju Bersama Tbk'
);
DELETE FROM rules
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM webhooks
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM company_rule_chunks
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM intent_examples
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM agent_capabilities
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM classifier_keyword_overrides
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM company_rules
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM payroll WHERE employee_id IN (
    SELECT e.id
    FROM employees e
    INNER JOIN companies c ON c.id = e.company_id
    WHERE c.name = 'PT Maju Bersama Tbk'
);
DELETE FROM attendance WHERE employee_id IN (
    SELECT e.id
    FROM employees e
    INNER JOIN companies c ON c.id = e.company_id
    WHERE c.name = 'PT Maju Bersama Tbk'
);
DELETE FROM time_offs WHERE employee_id IN (
    SELECT e.id
    FROM employees e
    INNER JOIN companies c ON c.id = e.company_id
    WHERE c.name = 'PT Maju Bersama Tbk'
);
DELETE FROM personal_infos WHERE employee_id IN (
    SELECT e.id
    FROM employees e
    INNER JOIN companies c ON c.id = e.company_id
    WHERE c.name = 'PT Maju Bersama Tbk'
);
DELETE FROM responsibility_routes
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM employees
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM departments
WHERE company_id IN (
    SELECT id FROM companies WHERE name = 'PT Maju Bersama Tbk'
);
DELETE FROM companies WHERE name = 'PT Maju Bersama Tbk';
"""

SEED_ID_REPLACEMENTS = {
    "00000000-0000-0000-0000-000000000001": "c72f8b7a-5e4d-4c3b-9a81-1f2e3d4c5b6a",
    "10000000-0000-0000-0000-000000000001": "a1b2c3d4-e5f6-47a8-9b0c-1d2e3f4a5b61",
    "10000000-0000-0000-0000-000000000002": "b1c2d3e4-f5a6-48b9-8c1d-2e3f4a5b6c72",
    "20000000-0000-0000-0000-000000000001": "c1d2e3f4-a5b6-49ca-9d2e-3f4a5b6c7d81",
    "20000000-0000-0000-0000-000000000002": "d1e2f3a4-b5c6-4adb-8e3f-4a5b6c7d8e92",
    "20000000-0000-0000-0000-000000000003": "e1f2a3b4-c5d6-4bec-9f4a-5b6c7d8e9fa3",
    "20000000-0000-0000-0000-000000000004": "f1a2b3c4-d5e6-4cfd-8a5b-6c7d8e9fab14",
    "30000000-0000-0000-0000-000000000001": "0f3a1b2c-4d5e-46f7-8a9b-0c1d2e3f4101",
    "30000000-0000-0000-0000-000000000002": "1a4b2c3d-5e6f-47a8-9b0c-1d2e3f4a5202",
    "30000000-0000-0000-0000-000000000003": "2b5c3d4e-6f7a-48b9-8c1d-2e3f4a5b6303",
    "30000000-0000-0000-0000-000000000004": "3c6d4e5f-7a8b-49ca-9d2e-3f4a5b6c7404",
    "30000000-0000-0000-0000-000000000005": "4d7e5f6a-8b9c-4adb-8e3f-4a5b6c7d8505",
    "30000000-0000-0000-0000-000000000006": "5e8f6a7b-9cad-4bec-9f4a-5b6c7d8e9606",
    "40000000-0000-0000-0000-000000000101": "be45c0d1-f203-4142-9faa-bccddeef0b01",
    "40000000-0000-0000-0000-000000000102": "cf56d1e2-034a-4253-8abb-cddeef0a1c02",
    "40000000-0000-0000-0000-000000000103": "d067e2f3-145b-4364-9bcc-ddeef0a1b203",
    "41000000-0000-0000-0000-000000000001": "e178f304-256c-4475-8cdd-eef0a1b2c301",
    "41000000-0000-0000-0000-000000000002": "f2890415-367d-4586-9dee-f0a1b2c3d402",
    "41000000-0000-0000-0000-000000000003": "0a9a1526-478e-4697-8eff-a1b2c3d4e503",
    "41000000-0000-0000-0000-000000000004": "1bab2637-589f-47a8-9fa1-b2c3d4e5f604",
    "50000000-0000-0000-0000-000000000001": "2cbc3748-69a0-48b9-8ab2-c3d4e5f60701",
    "50000000-0000-0000-0000-000000000002": "3dcd4859-7ab1-49ca-9bc3-d4e5f6071802",
    "50000000-0000-0000-0000-000000000003": "4ede596a-8bc2-4adb-8cd4-e5f607182903",
    "51000000-0000-0000-0000-000000000001": "5fef6a7b-9cd3-4bec-9de5-f60718293a01",
    "51000000-0000-0000-0000-000000000002": "60707b8c-ade4-4cfd-8ef6-0718293a4b02",
    "51000000-0000-0000-0000-000000000003": "71818c9d-bef5-4d0e-9f07-18293a4b5c03",
    "51000000-0000-0000-0000-000000000004": "82929dae-cf06-4e1f-8a18-293a4b5c6d04",
    "51000000-0000-0000-0000-000000000005": "93a3aebf-d017-4f20-9b29-3a4b5c6d7e05",
    "52000000-0000-0000-0000-000000000001": "a4b4bfc0-e128-4031-8c3a-4b5c6d7e8f01",
    "52000000-0000-0000-0000-000000000002": "b5c5c0d1-f239-4142-9d4b-5c6d7e8f9002",
    "52000000-0000-0000-0000-000000000003": "c6d6d1e2-034a-4253-8e5c-6d7e8f901103",
    "53000000-0000-0000-0000-000000000001": "d7e7e2f3-145b-4364-9f6d-7e8f90112401",
    "60000000-0000-0000-0000-000000000001": "6f907b8c-adbe-4cfd-8a5b-6c7d8e9fa701",
    "60000000-0000-0000-0000-000000000002": "7a018c9d-becf-4d0e-9b6c-7d8e9fabb802",
    "61000000-0000-0000-0000-000000000001": "8b129dae-cfd0-4e1f-8c7d-8e9fabbcc901",
    "61000000-0000-0000-0000-000000000002": "9c23aebf-d0e1-4f20-9d8e-9fabbccdda02",
    "70000000-0000-0000-0000-000000000001": "ad34bfc0-e1f2-4031-8e9f-abbccddeea01",
}


def _apply_seed_id_replacements(sql: str) -> str:
    rendered = sql
    for source, target in SEED_ID_REPLACEMENTS.items():
        rendered = rendered.replace(source, target)
    return rendered


SEED_SQL = _apply_seed_id_replacements(SEED_SQL)


def main() -> None:
    try:
        import psycopg2
    except ImportError:
        print("[ERROR] psycopg2-binary is not installed.")
        print("        Run: pip install psycopg2-binary")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete existing seed data before re-seeding")
    args = parser.parse_args()

    env = load_env()
    database_url = env.get("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL not found in .env")
        sys.exit(1)

    database_url = normalize_database_url(database_url)

    print("[INFO]  Connecting to database...")
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
    except Exception as e:
        print(f"[ERROR] Could not connect: {e}")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            if args.reset:
                print("[INFO]  Resetting seed data...")
                cur.execute(RESET_SQL)
                print("[OK]    Existing seed data removed.")

            print("[INFO]  Seeding database...")
            cur.execute(SEED_SQL)
            print("[OK]    Seed completed successfully.")
            print()
            print("  Company : PT Maju Bersama Tbk")
            print("  Departments: IT, Human Resources")
            print("  Employees:")
            print("    - Siti Rahayu           (HR Manager         / hr_admin)")
            print("    - Andi Wirawan          (IT Administrator   / it_admin)")
            print("    - Budi Santoso          (Tech Lead          / employee)")
            print("    - Fakhrul Muhammad Rijal(Software Engineer  / employee | discord: 851293259510710323)")
            print("  Phase 2 demo:")
            print("    - Rules   : 2")
            print("    - Webhooks: 1")
            print("    - Actions : 3")
    except Exception as e:
        print(f"[ERROR] Seed failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
