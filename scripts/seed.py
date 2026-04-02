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
        '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000002',
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

-- Set Tech Lead as head of IT department
UPDATE departments
SET head_employee_id = '20000000-0000-0000-0000-000000000003'
WHERE id = '10000000-0000-0000-0000-000000000001';

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

-- ─── Company Rules ────────────────────────────────────────────────────────────
INSERT INTO company_rules (id, company_id, title, category, content, effective_date, is_active) VALUES
    ('30000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Cuti Tahunan',
        'leave',
        'Karyawan tetap (permanent) berhak atas 12 hari cuti tahunan per tahun kalender. Cuti tahunan dapat diambil setelah karyawan melewati masa percobaan (probation period) selama 3 bulan. Pengajuan cuti harus dilakukan minimal 3 hari kerja sebelumnya melalui sistem HR, kecuali untuk keadaan darurat. Cuti yang tidak diambil dalam satu tahun kalender tidak dapat dibawa ke tahun berikutnya (tidak ada carry-over). Karyawan kontrak dan magang mendapat jatah cuti pro-rata sesuai durasi kontrak.',
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Cuti Sakit',
        'leave',
        'Karyawan berhak atas cuti sakit berbayar dengan syarat melampirkan surat keterangan dokter. Untuk ketidakhadiran 1-2 hari karena sakit, surat dokter dapat diserahkan maksimal H+2 setelah masuk kerja. Ketidakhadiran lebih dari 2 hari wajib disertai surat keterangan dokter yang diserahkan pada hari pertama sakit atau dikirimkan secara digital. Cuti sakit tidak mengurangi jatah cuti tahunan.',
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Work From Home (WFH)',
        'work_arrangement',
        'Karyawan diperbolehkan bekerja dari rumah (WFH) maksimal 2 hari per minggu, dengan persetujuan atasan langsung. Karyawan yang sedang dalam masa probation tidak diperkenankan WFH kecuali atas persetujuan khusus dari HR Manager. Pada hari WFH, karyawan wajib tetap dapat dihubungi dan hadir dalam meeting yang dijadwalkan. WFH tidak berlaku pada hari dengan kegiatan kantor wajib seperti all-hands meeting atau town hall.',
        '2024-06-01', true),
    ('30000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Jam Kerja dan Keterlambatan',
        'attendance',
        'Jam kerja standar adalah 08:00 - 17:00 WIB, Senin sampai Jumat. Toleransi keterlambatan adalah 15 menit. Keterlambatan lebih dari 15 menit wajib dikompensasi dengan perpanjangan jam kerja di hari yang sama atau atas persetujuan atasan. Keterlambatan yang tidak dikomunikasikan lebih dari 3 kali dalam satu bulan akan menjadi catatan dalam evaluasi kinerja.',
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Gaji dan Kompensasi',
        'payroll',
        'Gaji dibayarkan setiap akhir bulan, selambat-lambatnya tanggal 28 setiap bulan. Komponen gaji terdiri dari gaji pokok, tunjangan tetap (transport dan makan), dan tunjangan variabel (lembur jika ada). Potongan wajib meliputi iuran BPJS Kesehatan (1% dari gaji pokok), iuran BPJS Ketenagakerjaan (2% dari gaji pokok), dan PPh 21 sesuai peraturan perpajakan yang berlaku. Slip gaji dikirimkan melalui email setiap bulan pada tanggal pembayaran gaji.',
        '2024-01-01', true),
    ('30000000-0000-0000-0000-000000000006', '00000000-0000-0000-0000-000000000001',
        'Kebijakan Kode Etik dan Perilaku',
        'conduct',
        'Seluruh karyawan wajib menjaga integritas dan profesionalisme dalam bekerja. Dilarang melakukan tindakan diskriminasi, pelecehan, atau intimidasi dalam bentuk apapun di lingkungan kerja. Informasi rahasia perusahaan, termasuk data karyawan, data klien, dan strategi bisnis, wajib dijaga kerahasiaannya. Pelanggaran terhadap kode etik dapat berujung pada tindakan disipliner hingga pemutusan hubungan kerja.',
        '2024-01-01', true)
ON CONFLICT (id) DO NOTHING;
"""

RESET_SQL = """
DELETE FROM company_rule_chunks WHERE company_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM company_rules WHERE company_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM payroll WHERE employee_id IN (
    SELECT id FROM employees WHERE company_id = '00000000-0000-0000-0000-000000000001'
);
DELETE FROM attendance WHERE employee_id IN (
    SELECT id FROM employees WHERE company_id = '00000000-0000-0000-0000-000000000001'
);
DELETE FROM time_offs WHERE employee_id IN (
    SELECT id FROM employees WHERE company_id = '00000000-0000-0000-0000-000000000001'
);
DELETE FROM personal_infos WHERE employee_id IN (
    SELECT id FROM employees WHERE company_id = '00000000-0000-0000-0000-000000000001'
);
DELETE FROM employees WHERE company_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM departments WHERE company_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM companies WHERE id = '00000000-0000-0000-0000-000000000001';
"""


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
            print("  Employees:")
            print("    - Siti Rahayu     (HR Manager / hr_admin)")
            print("    - Budi Santoso    (Backend Engineer / employee)")
            print("    - Dewi Kurniawati (Frontend Engineer / employee)")
            print("    - Ahmad Fauzi     (Finance Staff / employee)")
            print("    - Rizky Pratama   (Backend Engineer / contract / probation)")
    except Exception as e:
        print(f"[ERROR] Seed failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
