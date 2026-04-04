from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext
from app.models import CompanyAgentResult, EvidenceItem
from app.services.embeddings import generate_embedding, to_pgvector_literal
from app.services.cache import get_cache

RULE_CATEGORY_KEYWORDS = {
    "leave": ["cuti", "leave", "izin", "carry over", "cuti sakit", "cuti tahunan"],
    "attendance": ["attendance", "kehadiran", "presensi", "telat", "terlambat", "jam kerja"],
    "work_arrangement": ["wfh", "work from home", "remote", "hybrid"],
    "payroll": ["gaji", "salary", "payroll", "kompensasi", "bpjs", "pph21", "slip gaji"],
    "benefit": [
        "benefit",
        "benefits",
        "reimburse",
        "reimbursement",
        "klaim",
        "claim",
        "medical",
        "optical",
        "kacamata",
        "psikolog",
        "dokter",
        "rawat jalan",
    ],
    "conduct": ["kode etik", "integritas", "diskriminasi", "pelecehan", "conduct"],
}

POLICY_EXPLICIT_KEYWORDS = [
    "aturan",
    "kebijakan",
    "policy",
    "peraturan",
    "ketentuan",
    "handbook",
]

CONTACT_GUIDANCE_KEYWORDS = [
    "tanya siapa",
    "hubungi siapa",
    "kontak siapa",
    "ke siapa",
    "harus ke siapa",
    "harus tanya ke siapa",
    "siapa yang bisa bantu",
    "siapa yang harus saya hubungi",
    "siapa pic",
    "pic siapa",
    "siapa recruiter",
    "siapa hrbp",
    "ke tim mana",
    "jalur mana",
    "karyawan baru",
    "pegawai baru",
    "onboarding",
]

DEPARTMENT_KEYWORDS = {
    "human resources": [
        "hr",
        "human resources",
        "personalia",
        "administrasi",
        "admin hr",
        "onboarding",
        "karyawan baru",
        "pegawai baru",
        "cuti",
        "leave",
        "payroll",
        "gaji",
        "slip gaji",
        "slip",
        "payslip",
        "bpjs",
        "pph21",
        "benefit",
        "benefits",
        "reimbursement",
        "reimburse",
        "klaim",
        "claim",
        "medical",
        "optical",
        "kacamata",
        "psikolog",
        "referral",
        "refer",
        "recruiter",
        "recruitment",
        "rekrutmen",
        "hiring",
        "talent acquisition",
        "ta",
        "candidate",
        "kandidat",
        "lowongan",
        "hrbp",
        "people partner",
        "people ops",
        "karier",
        "career",
        "internal move",
        "mutasi",
        "performance",
        "appraisal",
        "kontak hr",
        "tim hr",
        "pic hr",
    ],
    "it": [
        "it",
        "teknologi",
        "engineering",
        "developer",
        "akun",
        "password",
        "akses",
        "vpn",
        "email kantor",
        "laptop",
        "device",
        "komputer",
        "issue teknis",
        "teknis internal",
        "it support",
        "support internal",
    ],
}

CONTACT_GUIDANCE_TOPICS = [
    {
        "key": "recruiting",
        "department_name": "human resources",
        "keywords": [
            "referral",
            "refer",
            "recruiter",
            "recruitment",
            "rekrutmen",
            "hiring",
            "talent acquisition",
            "ta",
            "candidate",
            "kandidat",
            "lowongan",
            "hire",
        ],
        "recommended_channel": "chat atau email internal tim HR / recruiter / TA",
        "preparation_checklist": [
            "Siapkan nama kandidat dan posisi yang ingin direferensikan.",
            "Kalau ada CV, LinkedIn, atau ringkasan profil kandidat, siapkan juga sebelum menghubungi tim terkait.",
        ],
        "summary_template": (
            "Untuk urusan referral hiring, rekrutmen, recruiter, atau TA, kamu bisa "
            "mulai dari {contact_name} di departemen {department_name}. Kalau struktur "
            "recruiter belum dipisah, jalur awal paling aman tetap lewat tim HR."
        ),
    },
    {
        "key": "payroll_benefits",
        "department_name": "human resources",
        "keywords": [
            "payroll",
            "gaji",
            "salary",
            "slip gaji",
            "slip",
            "payslip",
            "bpjs",
            "pph21",
            "benefit",
            "benefits",
            "reimbursement",
            "reimburse",
            "klaim",
            "claim",
            "allowance",
            "medical",
            "optical",
            "kacamata",
            "psikolog",
        ],
        "recommended_channel": "chat atau email internal tim HR / payroll / benefits",
        "preparation_checklist": [
            "Siapkan periode, nominal, atau jenis benefit yang ingin ditanyakan.",
            "Kalau ada bukti transaksi atau dokumen pendukung, siapkan juga sebelum menghubungi tim terkait.",
        ],
        "summary_template": (
            "Untuk urusan payroll, reimbursement, benefit, atau administrasi kompensasi, "
            "kamu bisa mulai dari {contact_name} di departemen {department_name}."
        ),
    },
    {
        "key": "people_partner",
        "department_name": "human resources",
        "keywords": [
            "hrbp",
            "people partner",
            "people ops",
            "karier",
            "career",
            "internal move",
            "mutasi",
            "performance",
            "appraisal",
            "promosi",
            "pengembangan",
        ],
        "recommended_channel": "chat atau email internal HRBP / people partner",
        "preparation_checklist": [
            "Siapkan konteks tim, concern utama, dan outcome yang ingin kamu diskusikan.",
            "Kalau menyangkut karier atau internal move, jelaskan role saat ini dan arah role yang kamu tuju.",
        ],
        "summary_template": (
            "Untuk urusan HRBP, people matters, diskusi karier, atau internal move, kamu "
            "bisa mulai dari {contact_name} di departemen {department_name}."
        ),
    },
    {
        "key": "it_support",
        "department_name": "it",
        "keywords": [
            "akun",
            "password",
            "akses",
            "vpn",
            "email kantor",
            "laptop",
            "device",
            "komputer",
            "issue teknis",
            "teknis internal",
            "it support",
            "support internal",
        ],
        "recommended_channel": "chat atau tiket internal IT support",
        "preparation_checklist": [
            "Siapkan nama sistem, perangkat, atau akun yang bermasalah.",
            "Kalau ada error message atau screenshot, siapkan juga untuk mempercepat triage.",
        ],
        "summary_template": (
            "Untuk urusan akun kerja, akses sistem, perangkat, atau issue teknis internal, "
            "kamu bisa mulai dari {contact_name} di departemen {department_name}."
        ),
    },
    {
        "key": "leave_operations",
        "department_name": "human resources",
        "keywords": [
            "cuti",
            "leave",
            "izin sakit",
            "cuti sakit",
            "sick leave",
            "saldo cuti",
            "jatah cuti",
            "leave balance",
            "approve",
            "approval",
            "persetujuan",
        ],
        "recommended_channel": "chat atasan langsung atau email internal HR operations",
        "preparation_checklist": [
            "Siapkan jenis cuti, tanggal, dan konteks singkat kebutuhanmu.",
            "Kalau menyangkut izin sakit, siapkan juga dokumen pendukung seperti surat dokter bila sudah ada.",
        ],
        "summary_template": (
            "Untuk pengajuan cuti, izin sakit, approval cuti, atau pertanyaan saldo cuti, "
            "kamu bisa mulai dari {contact_name} di departemen {department_name}. Kalau "
            "ini menyangkut persetujuan personal, langkah awal paling aman tetap lewat "
            "atasan langsungmu."
        ),
    },
    {
        "key": "hr_operations",
        "department_name": "human resources",
        "keywords": [
            "hr",
            "human resources",
            "personalia",
            "administrasi",
            "admin hr",
            "onboarding",
            "karyawan baru",
            "pegawai baru",
            "cuti",
            "leave",
            "kontak hr",
            "tim hr",
            "pic hr",
        ],
        "recommended_channel": "chat atau email internal tim HR",
        "preparation_checklist": [
            "Siapkan ringkasan topik atau issue yang ingin kamu bahas.",
            "Kalau menyangkut periode tertentu, sebutkan juga bulan atau tanggal yang relevan.",
        ],
        "summary_template": (
            "Untuk urusan administrasi HR, onboarding, cuti, atau policy internal, kamu "
            "bisa mulai dari {contact_name} di departemen {department_name}."
        ),
    },
    {
        "key": "attendance_correction",
        "department_name": "human resources",
        "keywords": [
            "lupa absen",
            "lupa check-in",
            "lupa check in",
            "salah absen",
            "koreksi absen",
            "update absen",
            "lupa lapor",
            "salah status",
            "harusnya wfh",
            "harusnya wfo",
            "correction",
        ],
        "recommended_channel": "chat atasan langsung atau portal internal HR",
        "preparation_checklist": [
            "Siapkan tanggal absensi yang salah.",
            "Tentukan status yang benar (WFH/WFO/Sakit).",
            "Berikan alasan singkat koreksi (misal: lupa check-in).",
        ],
        "summary_template": (
            "Untuk urusan lupa absen, lupa check-in, salah absen, koreksi absen, update absen, lupa lapor, "
            "salah status, harusnya wfh, harusnya wfo, atau correction, jalur tercepat biasanya lewat {contact_name} "
            "di departemen {department_name} atau portal HR."
        ),
    },
]

MONTH_NAMES_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}

POLICY_REASONING_TRIGGER_KEYWORDS = [
    "reimburse",
    "reimbursement",
    "klaim",
    "claim",
    "benefit",
    "benefits",
    "eligible",
    "ditanggung",
    "cover",
    "covered",
    "limit",
    "maksimal",
    "syarat",
    "berhak",
    "jatah",
    "carry over",
    "probation",
    "sesuai policy",
    "tunjangan",
    "allowance",
]

POLICY_REASONING_CASE_TYPES = [
    {
        "key": "mental_health",
        "label": "konsultasi psikolog / mental health",
        "category": "benefit",
        "keywords": [
            "psikolog",
            "psychologist",
            "mental health",
            "konseling",
            "counseling",
            "kesehatan mental",
        ],
    },
    {
        "key": "optical",
        "label": "kacamata / optical",
        "category": "benefit",
        "keywords": [
            "kacamata",
            "optical",
            "lensa",
            "frame",
            "mata",
        ],
    },
    {
        "key": "medical",
        "label": "medical / rawat jalan",
        "category": "benefit",
        "keywords": [
            "dokter",
            "medical",
            "klinik",
            "rawat jalan",
            "obat",
            "hospital",
            "rumah sakit",
        ],
    },
    {
        "key": "annual_leave",
        "label": "cuti tahunan",
        "category": "leave",
        "keywords": [
            "cuti tahunan",
            "annual leave",
            "jatah cuti",
            "carry over",
            "masa probation",
            "masa percobaan",
        ],
    },
    {
        "key": "sick_leave",
        "label": "cuti sakit / izin sakit",
        "category": "leave",
        "keywords": [
            "izin sakit",
            "cuti sakit",
            "sick leave",
            "surat dokter",
        ],
    },
    {
        "key": "allowance",
        "label": "tunjangan / allowance",
        "category": "payroll",
        "keywords": [
            "tunjangan",
            "allowance",
            "internet",
            "komunikasi",
            "transport",
            "meal allowance",
        ],
    },
    {
        "key": "payroll",
        "label": "payroll / slip gaji",
        "category": "payroll",
        "keywords": [
            "slip gaji",
            "payslip",
            "pay slip",
            "gaji",
            "salary",
            "gajian",
            "tanggal pembayaran",
            "tanggal gajian",
        ],
    },
]

POLICY_REASONING_QUESTION_HINTS = [
    "bisa",
    "boleh",
    "apakah bisa",
    "apakah dapat",
    "eligible",
    "berhak",
    "syarat",
    "sesuai",
    "maksimal",
    "limit",
]

POLICY_REQUIRED_DOCUMENT_HINTS = [
    ("kwitansi", "kwitansi"),
    ("kuitansi", "kuitansi"),
    ("receipt", "receipt"),
    ("e-receipt", "e-receipt"),
    ("invoice", "invoice"),
    ("bukti bayar", "bukti bayar"),
    ("bukti pembayaran", "bukti pembayaran"),
    ("surat dokter", "surat dokter"),
    ("resep", "resep"),
    ("karcis tol", "karcis tol"),
    ("struk parkir", "struk parkir"),
    ("bill", "bill"),
    ("tagihan", "tagihan"),
]

POLICY_EXCLUSION_HINTS = [
    "tidak dapat direimburse",
    "tidak bisa direimburse",
    "tidak ditanggung",
    "tidak termasuk",
    "tidak mencakup",
    "dikecualikan",
]

POLICY_EXCLUSION_TAIL_STOPWORDS = {
    "dan",
    "atau",
    "yang",
    "untuk",
    "dengan",
    "tidak",
    "bisa",
    "dapat",
    "reimburse",
    "reimbursement",
    "klaim",
    "claim",
    "ditanggung",
    "termasuk",
    "mencakup",
    "layanan",
    "produk",
    "item",
    "terkait",
    "konsultasi",
    "consultation",
    "profesional",
    "professional",
    "seperti",
    "hanya",
    "berlaku",
    "non",
    "medis",
}

EMPLOYEE_LEVEL_KEYWORDS = {
    "probation": [
        "probation",
        "masa probation",
        "masa percobaan",
    ],
    "intern": [
        "magang",
        "intern",
        "internship",
    ],
    "contract": [
        "kontrak",
        "contract",
        "karyawan kontrak",
        "pegawai kontrak",
    ],
    "permanent": [
        "permanent",
        "tetap",
        "karyawan tetap",
        "pegawai tetap",
        "full time",
    ],
}

EMPLOYEE_LEVEL_LABELS = {
    "probation": "karyawan probation",
    "intern": "karyawan magang",
    "contract": "karyawan kontrak",
    "permanent": "karyawan tetap",
}


def _format_date(value: date | None) -> str:
    if value is None:
        return "-"
    return f"{value.day} {MONTH_NAMES_ID[value.month]} {value.year}"


def _format_rupiah(value: int | None) -> str:
    if value is None:
        return "-"
    return f"Rp{value:,.0f}".replace(",", ".")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _normalize_rule_version_key(rule: dict[str, Any]) -> str:
    title = _normalize_text(str(rule.get("title") or ""))
    category = _normalize_text(str(rule.get("category") or ""))
    return f"{category}::{title}"


def _parse_effective_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _contains_term(text: str, term: str) -> bool:
    pattern = rf"(?<!\w){re.escape(term.lower())}(?!\w)"
    return re.search(pattern, text) is not None


def _parse_amount_value(raw_number: str, suffix: str | None = None) -> int | None:
    cleaned = raw_number.strip().lower()
    if not cleaned:
        return None

    multiplier = 1
    normalized_suffix = (suffix or "").strip().lower()
    if normalized_suffix in {"k", "rb", "ribu"}:
        multiplier = 1_000
    elif normalized_suffix in {"jt", "juta"}:
        multiplier = 1_000_000
    elif normalized_suffix in {"m", "million"}:
        multiplier = 1_000_000_000

    if normalized_suffix:
        decimal_candidate = cleaned.replace(",", ".")
        if (
            (decimal_candidate.count(".") == 1 and len(decimal_candidate.split(".")[1]) <= 2)
            or decimal_candidate.replace(".", "", 1).isdigit()
        ):
            try:
                return int(float(decimal_candidate) * multiplier)
            except ValueError:
                pass

    digits_only = re.sub(r"[^\d]", "", cleaned)
    if not digits_only:
        return None
    return int(digits_only) * multiplier


def _extract_currency_amount(text: str) -> tuple[int | None, str | None]:
    lowered = _normalize_text(text)

    compact_match = re.search(
        r"\b(?:rp\.?\s*)?(\d+(?:[.,]\d+)?)\s*(k|rb|ribu|jt|juta|m|million)\b",
        lowered,
    )
    if compact_match:
        amount = _parse_amount_value(compact_match.group(1), compact_match.group(2))
        return amount, compact_match.group(0)

    rupiah_match = re.search(
        r"\brp\.?\s*([\d][\d\.,]*)\b",
        lowered,
    )
    if rupiah_match:
        amount = _parse_amount_value(rupiah_match.group(1))
        return amount, rupiah_match.group(0)

    plain_rupiah_word_match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*(ribu|rb|juta|jt|million|m)\b",
        lowered,
    )
    if plain_rupiah_word_match:
        amount = _parse_amount_value(
            plain_rupiah_word_match.group(1),
            plain_rupiah_word_match.group(2),
        )
        return amount, plain_rupiah_word_match.group(0)

    return None, None


def _detect_policy_case_type(lowered_message: str) -> dict[str, Any] | None:
    for candidate in POLICY_REASONING_CASE_TYPES:
        if any(_contains_term(lowered_message, keyword) for keyword in candidate["keywords"]):
            return candidate
    return None


def _extract_employee_level(lowered_message: str) -> str | None:
    for level, keywords in EMPLOYEE_LEVEL_KEYWORDS.items():
        if any(_contains_term(lowered_message, keyword) for keyword in keywords):
            return level
    return None


def _extract_documents_from_message(lowered_message: str) -> list[str]:
    documents: list[str] = []
    for keyword, label in POLICY_REQUIRED_DOCUMENT_HINTS:
        if _contains_term(lowered_message, keyword) and label not in documents:
            documents.append(label)
    return documents


def _extract_missing_documents_from_message(lowered_message: str) -> list[str]:
    missing_documents: list[str] = []
    missing_markers = [
        "tanpa",
        "tidak ada",
        "ga ada",
        "gak ada",
        "nggak ada",
        "belum ada",
        "ga punya",
        "gak punya",
        "nggak punya",
        "tidak punya",
    ]
    for marker in missing_markers:
        clause_matches = re.findall(
            rf"{re.escape(marker)}\s+([^.,;!?]+)",
            lowered_message,
        )
        for clause in clause_matches:
            for keyword, label in POLICY_REQUIRED_DOCUMENT_HINTS:
                if _contains_term(clause, keyword) and label not in missing_documents:
                    missing_documents.append(label)

    for keyword, label in POLICY_REQUIRED_DOCUMENT_HINTS:
        if any(f"{marker} {keyword}" in lowered_message for marker in missing_markers):
            if label not in missing_documents:
                missing_documents.append(label)
    return missing_documents


def _extract_frequency_request(lowered_message: str) -> dict[str, Any] | None:
    unit_aliases = {
        "sesi": "session",
        "session": "session",
        "kali": "claim",
        "klaim": "claim",
        "claim": "claim",
        "kunjungan": "visit",
        "visit": "visit",
        "hari": "day",
        "day": "day",
    }
    period = None
    if any(
        phrase in lowered_message
        for phrase in [
            "tahun kalender",
            "tahun ini",
            "per tahun",
            "setahun",
            "dalam setahun",
        ]
    ):
        period = "year"
    elif any(
        phrase in lowered_message
        for phrase in [
            "bulan ini",
            "per bulan",
            "sebulan",
        ]
    ):
        period = "month"
    elif any(
        phrase in lowered_message
        for phrase in [
            "minggu ini",
            "per minggu",
        ]
    ):
        period = "week"

    ordinal_match = re.search(
        r"(?:ke-|ke )(\d+)\s*(sesi|session|kali|klaim|claim|kunjungan|visit|hari|day)\b",
        lowered_message,
    )
    if ordinal_match:
        return {
            "count": int(ordinal_match.group(1)),
            "unit": unit_aliases[ordinal_match.group(2)],
            "period": period,
        }

    reverse_ordinal_match = re.search(
        r"\b(sesi|session|kali|klaim|claim|kunjungan|visit|hari|day)\s*(?:ke-|ke )(\d+)\b",
        lowered_message,
    )
    if reverse_ordinal_match:
        return {
            "count": int(reverse_ordinal_match.group(2)),
            "unit": unit_aliases[reverse_ordinal_match.group(1)],
            "period": period,
        }

    count_match = re.search(
        r"\b(\d+)\s*(sesi|session|kali|klaim|claim|kunjungan|visit|hari|day)\b",
        lowered_message,
    )
    if count_match:
        return {
            "count": int(count_match.group(1)),
            "unit": unit_aliases[count_match.group(2)],
            "period": period,
        }

    return None


def _extract_tenure_months(lowered_message: str) -> int | None:
    match = re.search(r"\b(?:baru|masih|sudah)?\s*(\d+)\s*bulan\b", lowered_message)
    if not match:
        return None
    return int(match.group(1))


def _extract_day_of_month(lowered_message: str) -> int | None:
    match = re.search(r"\btanggal\s+(\d{1,2})\b", lowered_message)
    if not match:
        return None
    day = int(match.group(1))
    if 1 <= day <= 31:
        return day
    return None


def _extract_policy_case(message: str) -> dict[str, Any] | None:
    lowered = _normalize_text(message)
    has_trigger = any(
        _contains_term(lowered, keyword) for keyword in POLICY_REASONING_TRIGGER_KEYWORDS
    )
    has_question_signal = any(
        _contains_term(lowered, keyword) for keyword in POLICY_REASONING_QUESTION_HINTS
    )
    amount, raw_amount = _extract_currency_amount(lowered)
    case_type = _detect_policy_case_type(lowered)

    # Keep policy reasoning explicit enough to avoid treating plain life updates
    # like "kacamata saya pecah" as company policy requests.
    if case_type is None and not has_trigger:
        return None
    if case_type is not None and not (has_trigger or has_question_signal):
        return None

    provided_documents = _extract_documents_from_message(lowered)
    missing_documents = _extract_missing_documents_from_message(lowered)
    frequency_requested = _extract_frequency_request(lowered)
    return {
        "case_type": case_type["key"] if case_type else "general_benefit",
        "case_label": case_type["label"] if case_type else "benefit / reimbursement umum",
        "policy_category": case_type["category"] if case_type else "benefit",
        "amount_requested": amount,
        "amount_text": raw_amount,
        "document_mentioned": bool(provided_documents),
        "provided_documents": provided_documents,
        "missing_documents": missing_documents,
        "employee_level": _extract_employee_level(lowered),
        "frequency_requested": frequency_requested,
        "tenure_months": _extract_tenure_months(lowered),
        "requested_day_of_month": _extract_day_of_month(lowered),
        "carry_over_requested": any(
            phrase in lowered
            for phrase in [
                "carry over",
                "dibawa ke tahun depan",
                "bawa ke tahun depan",
                "ke tahun berikutnya",
            ]
        ),
    }


def _detect_leave_operational_policy_focus(message: str) -> str | None:
    lowered = _normalize_text(message)
    mentions_balance = any(
        _contains_term(lowered, keyword)
        for keyword in ["saldo cuti", "jatah cuti", "leave balance", "sisa cuti"]
    )
    asks_balance_refresh = any(_contains_term(lowered, keyword) for keyword in ["kapan", "when"]) and any(
        _contains_term(lowered, keyword)
        for keyword in ["nambah", "bertambah", "increase", "refresh", "reset"]
    )
    mentions_sick_leave = any(
        _contains_term(lowered, keyword)
        for keyword in ["izin sakit", "cuti sakit", "sick leave"]
    ) or ("sakit" in lowered and "izin" in lowered)
    asks_approval = any(
        _contains_term(lowered, keyword)
        for keyword in ["approve", "approval", "persetujuan"]
    ) and any(_contains_term(lowered, keyword) for keyword in ["siapa", "jalur", "harus"])
    mentions_leave = any(_contains_term(lowered, keyword) for keyword in ["cuti", "leave", "izin"])

    if mentions_balance and asks_balance_refresh:
        return "balance_refresh"
    if mentions_sick_leave and any(
        _contains_term(lowered, keyword)
        for keyword in ["ke siapa", "ke mana", "lapor", "ajukan", "izin"]
    ):
        return "sick_leave_guidance"
    if mentions_leave and asks_approval:
        return "approval_chain"
    return None


def _detect_contact_guidance_topic(message: str) -> dict[str, Any] | None:
    lowered = _normalize_text(message)
    if "sakit" in lowered and any(
        _contains_term(lowered, keyword) for keyword in ["izin", "lapor"]
    ):
        for topic in CONTACT_GUIDANCE_TOPICS:
            if topic["key"] == "leave_operations":
                return topic

    for topic in CONTACT_GUIDANCE_TOPICS:
        if any(_contains_term(lowered, keyword) for keyword in topic["keywords"]):
            return topic
    return None


def _serialize_rule(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    effective_date = data.get("effective_date")
    if isinstance(effective_date, date):
        data["effective_date"] = effective_date.isoformat()
    if not isinstance(data.get("metadata"), dict):
        data["metadata"] = {}
    return data


def _snippet(text: str, *, max_length: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


async def _load_company_rules(
    db: AsyncSession,
    company_id: str,
) -> list[dict[str, Any]]:
    cache = get_cache("company_rules")
    cache_key = f"rules:{company_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    result = await db.execute(
        text(
            """
            SELECT
                id::text AS id,
                title,
                category,
                content,
                metadata,
                effective_date,
                is_active
            FROM company_rules
            WHERE company_id = CAST(:company_id AS uuid)
              AND is_active = true
            ORDER BY effective_date DESC NULLS LAST, created_at DESC
            """
        ),
        {"company_id": company_id},
    )
    rules = [_serialize_rule(dict(row)) for row in result.mappings().all()]
    cache.set(cache_key, rules)
    return rules


async def _load_company_structure(
    db: AsyncSession,
    company_id: str,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT
                d.id::text AS department_id,
                d.name AS department_name,
                parent.name AS parent_department_name,
                head.name AS head_employee_name
            FROM departments d
            LEFT JOIN departments parent
              ON parent.id = d.parent_id
            LEFT JOIN employees head
              ON head.id = d.head_employee_id
            WHERE d.company_id = CAST(:company_id AS uuid)
            ORDER BY d.name ASC
            """
        ),
        {"company_id": company_id},
    )
    return [dict(row) for row in result.mappings().all()]


def _coerce_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


async def _load_responsibility_routes(
    db: AsyncSession,
    company_id: str,
) -> list[dict[str, Any]]:
    cache = get_cache("responsibility_routes")
    cache_key = f"routes:{company_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    try:
        result = await db.execute(
            text(
                """
                SELECT
                    rr.id::text AS route_id,
                    rr.topic_key,
                    rr.department_id::text AS department_id,
                    d.name AS department_name,
                    primary_emp.id::text AS primary_employee_id,
                    primary_emp.name AS primary_contact_name,
                    primary_emp.position AS primary_contact_role,
                    alternate_emp.id::text AS alternate_employee_id,
                    alternate_emp.name AS alternate_contact_name,
                    alternate_emp.position AS alternate_contact_role,
                    rr.recommended_channel,
                    rr.preparation_checklist,
                    rr.metadata
                FROM responsibility_routes rr
                LEFT JOIN departments d
                  ON d.id = rr.department_id
                LEFT JOIN employees primary_emp
                  ON primary_emp.id = rr.primary_employee_id
                LEFT JOIN employees alternate_emp
                  ON alternate_emp.id = rr.alternate_employee_id
                WHERE rr.company_id = CAST(:company_id AS uuid)
                  AND rr.is_active = true
                ORDER BY rr.topic_key ASC
                """
            ),
            {"company_id": company_id},
        )
    except Exception:
        # Existing environments may not have the migration yet, so keep
        # company guidance on the current department-head fallback path.
        return []

    routes: list[dict[str, Any]] = []
    for row in result.mappings().all():
        route = dict(row)
        route["preparation_checklist"] = _coerce_text_list(
            route.get("preparation_checklist")
        )
        routes.append(route)

    cache.set(cache_key, routes)
    return routes


async def _search_rule_chunks_by_vector(
    db: AsyncSession,
    company_id: str,
    message: str,
) -> list[dict[str, Any]]:
    query_embedding = generate_embedding(message)
    if query_embedding is None:
        return []

    try:
        result = await db.execute(
            text(
                """
                SELECT
                    r.id::text AS id,
                    r.title,
                    r.category,
                    r.content,
                    r.metadata,
                    r.effective_date,
                    r.is_active,
                    c.content_chunk,
                    1 - (c.embedding <=> CAST(:query_embedding AS vector)) AS similarity
                FROM company_rule_chunks c
                INNER JOIN company_rules r
                  ON r.id = c.company_rule_id
                WHERE c.company_id = CAST(:company_id AS uuid)
                  AND r.is_active = true
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                LIMIT 5
                """
            ),
            {
                "company_id": company_id,
                "query_embedding": to_pgvector_literal(query_embedding),
            },
        )
    except Exception:
        return []
    rows = result.mappings().all()
    if not rows:
        return []

    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = _serialize_rule(dict(row))
        rule_id = data["id"]
        similarity = float(data["similarity"])
        if similarity < 0.55:
            continue

        existing = merged.get(rule_id)
        if existing is None or similarity > existing["similarity"]:
            merged[rule_id] = {
                "id": data["id"],
                "title": data["title"],
                "category": data["category"],
                "content": data["content"],
                "metadata": data.get("metadata", {}),
                "effective_date": data["effective_date"],
                "is_active": data["is_active"],
                "matched_terms": ["vector_search"],
                "matched_chunk": data["content_chunk"],
                "similarity": similarity,
                "ranking_score": similarity,
            }

    ranked = sorted(
        merged.values(),
        key=lambda item: item["similarity"],
        reverse=True,
    )
    return ranked[:3]


def _score_rule(message: str, rule: dict[str, Any]) -> tuple[int, list[str]]:
    lowered = _normalize_text(message)
    matched_terms: list[str] = []
    score = 0

    category = rule["category"]
    for keyword in RULE_CATEGORY_KEYWORDS.get(category, []):
        if _contains_term(lowered, keyword):
            score += 3
            matched_terms.append(keyword)

    searchable_fields = f"{rule['title']} {rule['content']}".lower()
    tokens = [
        token
        for token in re.findall(r"[a-zA-Z0-9_]{3,}", lowered)
        if token not in {
            "dan",
            "yang",
            "untuk",
            "saya",
            "apa",
            "bagaimana",
            "aturan",
            "tahun",
            "berapa",
            "this",
        }
    ]
    for token in tokens[:8]:
        if _contains_term(searchable_fields, token):
            score += 1
            matched_terms.append(token)

    if _contains_term(lowered, rule["title"]):
        score += 4
        matched_terms.append(rule["title"])

    return score, matched_terms


def _rank_rules(message: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for rule in rules:
        score, matched_terms = _score_rule(message, rule)
        if score > 0:
            enriched_rule = dict(rule)
            enriched_rule["matched_terms"] = sorted(set(matched_terms))
            enriched_rule["ranking_score"] = score
            ranked.append((score, enriched_rule))

    ranked.sort(
        key=lambda item: (
            item[0],
            item[1]["effective_date"] or "",
        ),
        reverse=True,
    )
    return [item[1] for item in ranked[:3]]


def _apply_policy_freshness(
    matched_rules: list[dict[str, Any]],
    all_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_by_key: dict[str, dict[str, Any]] = {}
    for rule in all_rules:
        key = _normalize_rule_version_key(rule)
        effective_date = _parse_effective_date(rule.get("effective_date"))
        existing = latest_by_key.get(key)
        if effective_date is None:
            continue
        existing_effective_date = (
            _parse_effective_date(existing.get("effective_date")) if existing else None
        )
        if existing is None or (
            existing_effective_date is not None and effective_date > existing_effective_date
        ):
            latest_by_key[key] = dict(rule)

    adjusted_by_key: dict[str, dict[str, Any]] = {}
    for rule in matched_rules:
        key = _normalize_rule_version_key(rule)
        effective_date = _parse_effective_date(rule.get("effective_date"))
        latest_rule = latest_by_key.get(key)
        latest_effective_date = (
            _parse_effective_date(latest_rule.get("effective_date"))
            if latest_rule is not None
            else None
        )
        enriched = dict(rule)
        if (
            latest_rule is not None
            and latest_rule.get("id") != rule.get("id")
            and latest_effective_date is not None
            and (effective_date is None or latest_effective_date > effective_date)
        ):
            enriched = {
                **dict(latest_rule),
                "matched_terms": list(rule.get("matched_terms", [])),
                "matched_chunk": rule.get("matched_chunk"),
                "similarity": rule.get("similarity"),
                "ranking_score": rule.get("ranking_score", 0.0),
                "promoted_from_rule_id": rule.get("id"),
                "version_source": "latest_active_version",
            }
            effective_date = latest_effective_date
        else:
            enriched["version_source"] = "matched_version"

        freshness_status = "unknown"
        if effective_date is not None and latest_effective_date is not None:
            freshness_status = (
                "current" if effective_date >= latest_effective_date else "outdated"
            )
        freshness_boost = 0.0
        if freshness_status == "current":
            freshness_boost = 0.04
        elif freshness_status == "outdated":
            freshness_boost = -0.04

        ranking_score = float(rule.get("ranking_score", 0.0) or 0.0) + freshness_boost
        enriched["freshness_status"] = freshness_status
        enriched["latest_effective_date"] = (
            latest_effective_date.isoformat() if latest_effective_date else None
        )
        enriched["ranking_score"] = round(ranking_score, 4)
        existing = adjusted_by_key.get(key)
        if existing is None:
            adjusted_by_key[key] = enriched
            continue

        existing_score = float(existing.get("ranking_score", 0.0) or 0.0)
        if ranking_score > existing_score:
            adjusted_by_key[key] = enriched
            continue

        if ranking_score == existing_score and (
            (enriched.get("effective_date") or "") > (existing.get("effective_date") or "")
        ):
            adjusted_by_key[key] = enriched

    adjusted_rules = list(adjusted_by_key.values())
    adjusted_rules.sort(
        key=lambda item: (
            float(item.get("ranking_score", 0.0) or 0.0),
            item.get("effective_date") or "",
        ),
        reverse=True,
    )
    return adjusted_rules[:3]


def _build_retrieval_assessment(
    status: str,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        **extra,
    }


def _assess_policy_retrieval(
    matched_rules: list[dict[str, Any]],
    *,
    retrieval_strategy: str,
) -> dict[str, Any]:
    if not matched_rules:
        return _build_retrieval_assessment(
            "weak",
            "Referensi policy yang ditemukan belum cukup kuat untuk dijadikan jawaban utama.",
            retrieval_strategy=retrieval_strategy,
            match_count=0,
        )

    version_promotion_used = any(
        rule.get("version_source") == "latest_active_version" for rule in matched_rules
    )
    if version_promotion_used:
        return _build_retrieval_assessment(
            "partial",
            "Semantic match sempat mengarah ke versi policy yang lebih lama, jadi sistem mempromosikan versi aktif terbaru dengan policy key yang sama sebagai referensi utama.",
            retrieval_strategy=retrieval_strategy,
            match_count=len(matched_rules),
            version_promotion_used=True,
        )

    if retrieval_strategy == "vector":
        best_similarity = max(float(rule.get("similarity", 0.0) or 0.0) for rule in matched_rules)
        top_rule = matched_rules[0]
        if top_rule.get("freshness_status") == "outdated":
            return _build_retrieval_assessment(
                "partial",
                "Rule yang paling mirip masih versi lama, jadi jawaban ini perlu dibaca dengan hati-hati sambil mengutamakan versi terbaru yang berlaku.",
                retrieval_strategy=retrieval_strategy,
                best_similarity=round(best_similarity, 4),
                match_count=len(matched_rules),
                freshness_status="outdated",
            )
        if best_similarity >= 0.78:
            return _build_retrieval_assessment(
                "enough",
                "Kecocokan semantic policy cukup kuat untuk dipakai sebagai referensi utama.",
                retrieval_strategy=retrieval_strategy,
                best_similarity=round(best_similarity, 4),
                match_count=len(matched_rules),
            )
        return _build_retrieval_assessment(
            "partial",
            "Kecocokan semantic policy masih menengah, jadi jawaban ini sebaiknya dianggap referensi awal.",
            retrieval_strategy=retrieval_strategy,
            best_similarity=round(best_similarity, 4),
            match_count=len(matched_rules),
        )

    strongest_keyword_count = max(len(rule.get("matched_terms", [])) for rule in matched_rules)
    if matched_rules[0].get("freshness_status") == "outdated":
        return _build_retrieval_assessment(
            "partial",
            "Policy yang paling cocok masih versi lama, jadi jawaban ini harus dibaca sebagai referensi awal sambil mengutamakan policy terbaru yang berlaku.",
            retrieval_strategy=retrieval_strategy,
            strongest_keyword_count=strongest_keyword_count,
            match_count=len(matched_rules),
            freshness_status="outdated",
        )
    if len(matched_rules) >= 2 or strongest_keyword_count >= 3:
        return _build_retrieval_assessment(
            "enough",
            "Keyword dan konteks policy yang ditemukan cukup kuat untuk dipakai sebagai referensi utama.",
            retrieval_strategy=retrieval_strategy,
            strongest_keyword_count=strongest_keyword_count,
            match_count=len(matched_rules),
        )

    return _build_retrieval_assessment(
        "partial",
        "Policy yang ditemukan masih berdasarkan kecocokan keyword yang terbatas, jadi jawabannya masih bersifat awal.",
        retrieval_strategy=retrieval_strategy,
        strongest_keyword_count=strongest_keyword_count,
        match_count=len(matched_rules),
    )


def _coerce_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return int(stripped)
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _normalize_limit_unit(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    aliases = {
        "rp": "idr",
        "rupiah": "idr",
        "idr": "idr",
        "hari": "day",
        "day": "day",
        "sesi": "session",
        "session": "session",
        "claim": "claim",
        "klaim": "claim",
        "visit": "visit",
        "kunjungan": "visit",
        "payment": "payment",
        "allowance": "allowance",
    }
    return aliases.get(normalized, normalized)


def _normalize_limit_period(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    aliases = {
        "session": "session",
        "sesi": "session",
        "visit": "visit",
        "kunjungan": "visit",
        "day": "day",
        "hari": "day",
        "month": "month",
        "bulan": "month",
        "week": "week",
        "minggu": "week",
        "year": "year",
        "tahun": "year",
        "payment_day": "payment_day",
    }
    return aliases.get(normalized, normalized)


def _normalize_policy_amount_limit(value: Any) -> dict[str, Any] | None:
    data = _coerce_json_object(value)
    if not data:
        return None
    max_value = _coerce_int(data.get("max_value"))
    if max_value is None:
        max_value = _coerce_int(data.get("max_amount"))
    if max_value is None:
        return None
    return {
        "max_value": max_value,
        "unit": _normalize_limit_unit(data.get("unit")) or "idr",
        "period": _normalize_limit_period(data.get("period")),
    }


def _normalize_policy_frequency_limit(value: Any) -> dict[str, Any] | None:
    data = _coerce_json_object(value)
    if not data:
        return None
    max_count = _coerce_int(data.get("max_count"))
    if max_count is None:
        return None
    return {
        "max_count": max_count,
        "unit": _normalize_limit_unit(data.get("unit")) or "claim",
        "period": _normalize_limit_period(data.get("period")),
    }


def _derive_amount_limit_period_from_text(text: str) -> str | None:
    lowered = _normalize_text(text)
    if any(phrase in lowered for phrase in ["per sesi", "tiap sesi"]):
        return "session"
    if any(phrase in lowered for phrase in ["per kunjungan", "tiap kunjungan"]):
        return "visit"
    if any(phrase in lowered for phrase in ["per bulan", "setiap bulan"]):
        return "month"
    if any(phrase in lowered for phrase in ["per minggu", "setiap minggu"]):
        return "week"
    if any(phrase in lowered for phrase in ["per tahun", "tahun kalender", "setiap tahun"]):
        return "year"
    return None


def _derive_frequency_limit_from_text(text: str) -> dict[str, Any] | None:
    lowered = _normalize_text(text)
    match = re.search(
        r"maks(?:imal)?\s+(\d+)\s*(sesi|session|klaim|claim|kunjungan|visit|hari|day)",
        lowered,
    )
    if not match:
        return None
    return {
        "max_count": int(match.group(1)),
        "unit": _normalize_limit_unit(match.group(2)),
        "period": _derive_amount_limit_period_from_text(text),
    }


def _derive_policy_constraints_from_text(text: str) -> dict[str, Any]:
    lowered = _normalize_text(text)
    constraints: dict[str, Any] = {}
    excluded_keywords = _extract_policy_exclusion_terms(text)
    if excluded_keywords:
        constraints["excluded_keywords"] = excluded_keywords

    if (
        "tidak dapat dibawa ke tahun berikutnya" in lowered
        or "tidak ada carry-over" in lowered
        or "tidak ada carry over" in lowered
    ):
        constraints["carry_over_allowed"] = False

    probation_match = re.search(
        r"(?:probation(?: period)?|masa percobaan).{0,30}?(\d+)\s*bulan",
        lowered,
    )
    if probation_match:
        constraints["min_tenure_months"] = int(probation_match.group(1))

    salary_day_match = re.search(r"tanggal\s+(\d{1,2})\s+setiap bulan", lowered)
    if salary_day_match and "gaji" in lowered:
        constraints["salary_payment_day_max"] = int(salary_day_match.group(1))

    if "slip gaji dikirim" in lowered and "tanggal pembayaran" in lowered:
        constraints["payslip_delivery"] = "payment_day"

    return constraints


def _infer_policy_case_type_from_rule(rule: dict[str, Any]) -> str:
    searchable = _normalize_text(f"{rule.get('title') or ''} {rule.get('content') or ''}")
    case_type = _detect_policy_case_type(searchable)
    if case_type is not None:
        return str(case_type["key"])
    category = str(rule.get("category") or "").strip().lower()
    if category == "leave":
        return "annual_leave"
    if category == "payroll":
        if any(_contains_term(searchable, keyword) for keyword in ["tunjangan", "allowance"]):
            return "allowance"
        return "payroll"
    if category == "benefit":
        return "general_benefit"
    return category or "general_policy"


def _infer_policy_coverage_type(rule: dict[str, Any], case_type: str) -> str:
    if case_type in {"mental_health", "optical", "medical", "general_benefit"}:
        return "reimbursement"
    if case_type in {"annual_leave", "sick_leave"}:
        return "entitlement"
    if case_type == "allowance":
        return "allowance"
    if case_type == "payroll":
        return "schedule"
    return str(rule.get("category") or "policy").strip().lower() or "policy"


def _build_policy_metadata(rule: dict[str, Any]) -> dict[str, Any]:
    explicit_metadata = _coerce_json_object(rule.get("metadata"))
    content = str(rule.get("content") or "")
    case_type = (
        str(explicit_metadata.get("case_type") or "").strip().lower()
        or _infer_policy_case_type_from_rule(rule)
    )
    amount_limit = _normalize_policy_amount_limit(explicit_metadata.get("amount_limit"))
    if amount_limit is None:
        derived_limit_amount = _extract_limit_amount_from_policy(content)
        if derived_limit_amount is not None:
            amount_limit = {
                "max_value": derived_limit_amount,
                "unit": "idr",
                "period": _derive_amount_limit_period_from_text(content),
            }

    frequency_limit = _normalize_policy_frequency_limit(
        explicit_metadata.get("frequency_limit")
    )
    if frequency_limit is None:
        frequency_limit = _derive_frequency_limit_from_text(content)

    derived_constraints = _derive_policy_constraints_from_text(content)
    constraints = {
        **derived_constraints,
        **_coerce_json_object(explicit_metadata.get("constraints")),
    }

    required_documents = _coerce_text_list(explicit_metadata.get("required_documents"))
    if not required_documents:
        required_documents = _extract_required_documents(content)

    eligible_levels = _coerce_text_list(explicit_metadata.get("eligible_levels"))
    coverage_type = (
        str(explicit_metadata.get("coverage_type") or "").strip().lower()
        or _infer_policy_coverage_type(rule, case_type)
    )

    return {
        "policy_key": str(explicit_metadata.get("policy_key") or "").strip() or None,
        "case_type": case_type,
        "coverage_type": coverage_type,
        "amount_limit": amount_limit,
        "frequency_limit": frequency_limit,
        "eligible_levels": eligible_levels,
        "required_documents": required_documents,
        "constraints": constraints,
        "approval_chain": _coerce_text_list(explicit_metadata.get("approval_chain")),
        "simulation_mode": bool(explicit_metadata.get("simulation_mode")),
        "affects_balance": bool(explicit_metadata.get("affects_balance")),
        "balance_type": str(explicit_metadata.get("balance_type") or "").strip() or None,
    }


def _format_policy_limit(limit: dict[str, Any] | None) -> str | None:
    if not isinstance(limit, dict):
        return None
    max_value = _coerce_int(limit.get("max_value"))
    if max_value is None:
        return None
    unit = str(limit.get("unit") or "").strip().lower()
    period = str(limit.get("period") or "").strip().lower()
    if unit == "idr":
        formatted = _format_rupiah(max_value)
    else:
        unit_labels = {
            "day": "hari",
            "session": "sesi",
            "claim": "klaim",
            "visit": "kunjungan",
            "allowance": "tunjangan",
        }
        formatted = f"{max_value} {unit_labels.get(unit, unit)}".strip()
    period_labels = {
        "session": "sesi",
        "visit": "kunjungan",
        "month": "bulan",
        "week": "minggu",
        "year": "tahun",
        "day": "hari",
        "payment_day": "hari pembayaran",
    }
    if period:
        return f"{formatted} per {period_labels.get(period, period)}"
    return formatted


def _format_frequency_limit(limit: dict[str, Any] | None) -> str | None:
    if not isinstance(limit, dict):
        return None
    max_count = _coerce_int(limit.get("max_count"))
    if max_count is None:
        return None
    unit_labels = {
        "session": "sesi",
        "claim": "klaim",
        "visit": "kunjungan",
        "day": "hari",
        "payment": "pembayaran",
        "allowance": "tunjangan",
    }
    period_labels = {
        "month": "bulan",
        "week": "minggu",
        "year": "tahun",
        "payment_day": "hari pembayaran",
    }
    unit_text = unit_labels.get(str(limit.get("unit") or "").strip().lower(), "kali")
    period = str(limit.get("period") or "").strip().lower()
    if period:
        return f"{max_count} {unit_text} per {period_labels.get(period, period)}"
    return f"{max_count} {unit_text}"


def _format_employee_levels(levels: list[str]) -> str:
    labels = [EMPLOYEE_LEVEL_LABELS.get(level, level) for level in levels]
    return ", ".join(labels)


def _matches_excluded_policy_keyword(
    message: str,
    constraints: dict[str, Any],
    policy_text: str,
) -> bool:
    lowered_message = _normalize_text(message)
    explicit_keywords = _coerce_text_list(constraints.get("excluded_keywords"))
    if explicit_keywords:
        return any(_contains_term(lowered_message, keyword) for keyword in explicit_keywords)
    return _message_matches_policy_exclusion(message, policy_text)


def _is_employee_level_allowed(
    employee_level: str | None,
    eligible_levels: list[str],
    constraints: dict[str, Any],
) -> bool | None:
    if employee_level is None:
        return None
    excluded_levels = _coerce_text_list(constraints.get("excluded_levels"))
    if employee_level in excluded_levels:
        return False
    if eligible_levels and employee_level not in eligible_levels:
        return False
    return True


def _policy_followup_target(policy_case: dict[str, Any]) -> str:
    category = str(policy_case.get("policy_category") or "").strip().lower()
    if category == "leave":
        return "HR"
    if category == "payroll":
        return "HR / payroll"
    return "HR / benefits"


def _extract_limit_amount_from_policy(text: str) -> int | None:
    lowered = _normalize_text(text)
    patterns = [
        r"(?:maks(?:imal)?|hingga|sampai|limit)\s+rp\.?\s*([\d][\d\.,]*)",
        r"(?:maks(?:imal)?|hingga|sampai|limit)\s+(\d+(?:[.,]\d+)?)\s*(k|rb|ribu|jt|juta|m|million)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        if len(match.groups()) == 1:
            amount = _parse_amount_value(match.group(1))
        else:
            amount = _parse_amount_value(match.group(1), match.group(2))
        if amount is not None:
            return amount
    return None


def _extract_required_documents(text: str) -> list[str]:
    lowered = _normalize_text(text)
    documents: list[str] = []
    for keyword, label in POLICY_REQUIRED_DOCUMENT_HINTS:
        if _contains_term(lowered, keyword) and label not in documents:
            documents.append(label)
    return documents


def _extract_policy_exclusion_terms(text: str) -> list[str]:
    lowered = _normalize_text(text)
    terms: list[str] = []
    clauses = re.split(r"[.!?;]+", lowered)
    for clause in clauses:
        normalized_clause = clause.strip()
        if not normalized_clause:
            continue

        for phrase in POLICY_EXCLUSION_HINTS:
            if phrase not in normalized_clause:
                continue

            tail = normalized_clause.split(phrase, 1)[1]
            for token in re.findall(r"[a-zA-Z]{3,}", tail):
                if token in POLICY_EXCLUSION_TAIL_STOPWORDS:
                    continue
                if token not in terms:
                    terms.append(token)

    return terms


def _message_matches_policy_exclusion(message: str, policy_text: str) -> bool:
    lowered_message = _normalize_text(message)
    exclusion_terms = _extract_policy_exclusion_terms(policy_text)
    if not exclusion_terms:
        return False

    return any(_contains_term(lowered_message, token) for token in exclusion_terms)


def _score_rule_for_policy_case(
    rule: dict[str, Any],
    policy_case: dict[str, Any],
) -> int:
    searchable = _normalize_text(
        f"{rule.get('title') or ''} {rule.get('content') or ''}"
    )
    policy_metadata = _build_policy_metadata(rule)
    score = 0
    if rule.get("category") == policy_case.get("policy_category"):
        score += 3

    if policy_metadata.get("case_type") == policy_case.get("case_type"):
        score += 6

    case_type = str(policy_case.get("case_type") or "")
    case_keywords = {
        "mental_health": ["psikolog", "psychologist", "mental health", "konseling"],
        "optical": ["kacamata", "optical", "lensa", "frame", "mata"],
        "medical": ["dokter", "medical", "klinik", "rawat jalan", "obat"],
        "annual_leave": ["cuti tahunan", "annual leave", "carry over", "probation"],
        "allowance": ["tunjangan", "allowance", "internet", "komunikasi"],
        "payroll": ["slip gaji", "payslip", "gaji", "salary", "tanggal 28"],
    }
    for keyword in case_keywords.get(case_type, []):
        if _contains_term(searchable, keyword):
            score += 2

    for keyword in ["reimburse", "reimbursement", "klaim", "claim", "ditanggung", "benefit"]:
        if keyword in searchable:
            score += 1

    if policy_metadata.get("amount_limit") is not None:
        score += 1
    if policy_metadata.get("frequency_limit") is not None:
        score += 1
    if policy_metadata.get("required_documents"):
        score += 1

    return score


def _pick_best_rule_for_policy_case(
    matched_rules: list[dict[str, Any]],
    policy_case: dict[str, Any],
) -> dict[str, Any] | None:
    if not matched_rules:
        return None

    best_rule: dict[str, Any] | None = None
    best_score = -1
    for rule in matched_rules:
        score = _score_rule_for_policy_case(rule, policy_case)
        if score > best_score:
            best_rule = rule
            best_score = score

    if best_score <= 0:
        return matched_rules[0]
    return best_rule


def _evaluate_policy_reasoning(
    message: str,
    matched_rules: list[dict[str, Any]],
    *,
    policy_assessment: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    policy_case = _extract_policy_case(message)
    if policy_case is None:
        return None

    followup_target = _policy_followup_target(policy_case)
    best_rule = _pick_best_rule_for_policy_case(matched_rules, policy_case)
    if best_rule is None:
        return {
            "case_type": policy_case["case_type"],
            "case_label": policy_case["case_label"],
            "policy_category": policy_case["policy_category"],
            "amount_requested": policy_case["amount_requested"],
            "eligibility": "needs_review",
            "reason": "Aku belum menemukan policy yang cukup spesifik untuk kasus ini.",
            "estimated_maximum_reimbursement": None,
            "required_documents": [],
            "matched_rule_title": None,
            "matched_rule_id": None,
            "policy_key": None,
            "coverage_type": None,
            "policy_limit": None,
            "policy_frequency_limit": None,
            "eligible_levels": [],
            "detected_employee_level": policy_case.get("employee_level"),
            "provided_documents": policy_case.get("provided_documents", []),
            "missing_required_documents": policy_case.get("missing_documents", []),
            "frequency_requested": policy_case.get("frequency_requested"),
            "requested_day_of_month": policy_case.get("requested_day_of_month"),
            "constraints_triggered": [],
            "next_action": (
                f"Coba verifikasi dulu ke {followup_target} sambil menyiapkan detail "
                "pengeluaran, periode, dan dokumen pendukung yang relevan."
            ),
        }

    rule_content = str(best_rule.get("content") or "")
    policy_metadata = _build_policy_metadata(best_rule)
    policy_limit = policy_metadata.get("amount_limit")
    frequency_limit = policy_metadata.get("frequency_limit")
    constraints = _coerce_json_object(policy_metadata.get("constraints"))
    eligible_levels = _coerce_text_list(policy_metadata.get("eligible_levels"))
    required_documents = _coerce_text_list(policy_metadata.get("required_documents"))
    amount_requested = policy_case["amount_requested"]
    employee_level = str(policy_case.get("employee_level") or "").strip().lower() or None
    frequency_requested = policy_case.get("frequency_requested")
    missing_documents = [
        document
        for document in _coerce_text_list(policy_case.get("missing_documents"))
        if not required_documents or document in required_documents
    ]
    case_match_score = _score_rule_for_policy_case(best_rule, policy_case)
    has_specific_case_match = (
        policy_case["case_type"] == policy_metadata.get("case_type")
        or (
            policy_case["case_type"] != "general_benefit"
            and case_match_score >= 6
        )
    )
    has_structured_policy_guidance = any(
        [
            policy_limit is not None,
            frequency_limit is not None,
            bool(required_documents),
            bool(eligible_levels),
            bool(constraints),
        ]
    )
    estimated_maximum = None
    if isinstance(policy_limit, dict) and policy_limit.get("unit") == "idr":
        estimated_maximum = _coerce_int(policy_limit.get("max_value"))

    eligibility = "eligible"
    reason = (
        f"Policy yang paling relevan adalah {best_rule.get('title') or 'policy terkait'} "
        f"dan struktur metadata-nya cukup dekat dengan kasus {policy_case['case_label']}."
    )
    next_action = (
        f"Siapkan detail nominal, periode, atau konteks kasusnya lalu verifikasi ke {followup_target}."
    )
    if required_documents:
        next_action = (
            "Siapkan dokumen pendukung yang diminta policy, lalu verifikasi atau lanjutkan "
            f"ke {followup_target}."
        )

    triggered_constraints: list[str] = []
    has_exclusion = _matches_excluded_policy_keyword(message, constraints, rule_content)
    employee_level_allowed = _is_employee_level_allowed(
        employee_level,
        eligible_levels,
        constraints,
    )
    min_tenure_months = _coerce_int(constraints.get("min_tenure_months"))
    salary_payment_day_max = _coerce_int(constraints.get("salary_payment_day_max"))
    carry_over_allowed = _coerce_bool(constraints.get("carry_over_allowed"))
    tenure_months = _coerce_int(policy_case.get("tenure_months"))
    requested_day = _coerce_int(policy_case.get("requested_day_of_month"))
    frequency_requested_count = (
        _coerce_int(frequency_requested.get("count"))
        if isinstance(frequency_requested, dict)
        else None
    )
    frequency_limit_max_count = (
        _coerce_int(frequency_limit.get("max_count"))
        if isinstance(frequency_limit, dict)
        else None
    )
    policy_limit_max_value = (
        _coerce_int(policy_limit.get("max_value"))
        if isinstance(policy_limit, dict)
        else None
    )

    if has_exclusion:
        eligibility = "not_eligible"
        triggered_constraints.append("excluded_keywords")
        reason = (
            f"Policy {best_rule.get('title') or 'yang ditemukan'} mengandung pengecualian "
            "yang membuat kasus ini kemungkinan tidak ditanggung."
        )
    elif (
        min_tenure_months is not None
        and (
            employee_level == "probation"
            or (tenure_months is not None and tenure_months < min_tenure_months)
        )
    ):
        eligibility = "not_eligible"
        triggered_constraints.append("minimum_tenure")
        reason = (
            f"Policy ini baru berlaku setelah minimal {min_tenure_months} bulan masa kerja, "
            "jadi kasus yang masih probation kemungkinan belum eligible."
        )
    elif employee_level_allowed is False:
        eligibility = "not_eligible"
        triggered_constraints.append("employee_level")
        allowed_levels_text = _format_employee_levels(eligible_levels)
        detected_level_text = EMPLOYEE_LEVEL_LABELS.get(employee_level or "", employee_level or "level ini")
        reason = (
            f"Policy ini berlaku untuk {allowed_levels_text}, sedangkan dari pertanyaanmu "
            f"kondisinya terdengar seperti {detected_level_text}."
        )
    elif policy_case.get("carry_over_requested") and carry_over_allowed is False:
        eligibility = "not_eligible"
        triggered_constraints.append("carry_over_not_allowed")
        reason = (
            "Policy ini menyebut cuti atau benefit terkait tidak bisa di-carry over ke "
            "tahun berikutnya."
        )
    elif (
        salary_payment_day_max is not None
        and requested_day is not None
        and requested_day > salary_payment_day_max
    ):
        eligibility = "not_eligible"
        triggered_constraints.append("salary_payment_day_max")
        reason = (
            f"Policy payroll menetapkan pembayaran paling lambat tanggal {salary_payment_day_max}, "
            f"jadi tanggal {requested_day} terlihat di luar batas policy."
        )
    elif (
        isinstance(frequency_limit, dict)
        and isinstance(frequency_requested, dict)
        and str(frequency_limit.get("unit") or "") == str(frequency_requested.get("unit") or "")
        and frequency_requested_count is not None
        and frequency_limit_max_count is not None
        and frequency_requested_count > frequency_limit_max_count
    ):
        eligibility = "not_eligible"
        triggered_constraints.append("frequency_limit")
        reason = (
            f"Policy ini membatasi sampai {_format_frequency_limit(frequency_limit)}, jadi "
            f"{frequency_requested.get('count')} {frequency_requested.get('unit')} terlihat "
            "melewati batas tersebut."
        )
    elif (
        isinstance(policy_limit, dict)
        and policy_limit.get("unit") == "day"
        and isinstance(frequency_requested, dict)
        and str(frequency_requested.get("unit") or "") == "day"
        and frequency_requested_count is not None
        and policy_limit_max_value is not None
        and frequency_requested_count > policy_limit_max_value
    ):
        eligibility = "not_eligible"
        triggered_constraints.append("day_limit")
        reason = (
            f"Policy ini memberi batas {_format_policy_limit(policy_limit)}, jadi jumlah hari "
            "yang disebutkan terlihat melebihi batas policy."
        )
    elif missing_documents:
        eligibility = "needs_review"
        triggered_constraints.append("missing_documents")
        reason = (
            "Policy ini mensyaratkan dokumen tertentu, tetapi dari pertanyaanmu dokumen "
            f"berikut belum ada: {', '.join(missing_documents)}."
        )
        next_action = (
            "Lengkapi dokumen yang diwajibkan policy dulu, lalu verifikasi kembali "
            f"ke {followup_target}."
        )
    elif policy_assessment and policy_assessment.get("status") == "weak":
        eligibility = "needs_review"
        reason = (
            "Policy yang ditemukan masih sangat lemah, jadi kasus ini lebih aman dianggap "
            "perlu verifikasi manual."
        )
    elif (
        policy_assessment
        and policy_assessment.get("status") == "partial"
        and not (has_specific_case_match and has_structured_policy_guidance)
    ):
        eligibility = "needs_review"
        reason = (
            "Policy yang ditemukan masih bersifat awal atau parsial, jadi kasus ini lebih "
            "aman dianggap perlu verifikasi manual."
        )

    if (
        eligibility == "eligible"
        and isinstance(policy_limit, dict)
        and policy_limit.get("unit") == "idr"
        and amount_requested is not None
    ):
        max_value = _coerce_int(policy_limit.get("max_value"))
        if max_value is not None:
            estimated_maximum = min(amount_requested, max_value)
            if amount_requested > max_value:
                reason = (
                    f"Kasus ini kemungkinan eligible, tetapi nominalnya terlihat melebihi limit "
                    f"policy sehingga acuan awalnya dibatasi sampai {_format_rupiah(max_value)}."
                )
    elif eligibility == "not_eligible":
        estimated_maximum = None
        required_documents = []
        if policy_case["policy_category"] == "benefit":
            next_action = (
                "Jangan ajukan klaim dulu. Kalau kamu merasa kasusmu berbeda dari pengecualian "
                f"policy ini, verifikasi manual dulu ke {followup_target}."
            )
        elif policy_case["policy_category"] == "payroll":
            next_action = (
                f"Jangan anggap ini otomatis sesuai policy dulu. Verifikasi manual ke {followup_target} "
                "kalau ada konteks tambahan yang belum disebut."
            )
        else:
            next_action = (
                f"Jangan anggap ini otomatis diperbolehkan dulu. Verifikasi manual ke {followup_target} "
                "kalau ada konteks tambahan."
            )

    return {
        "case_type": policy_case["case_type"],
        "case_label": policy_case["case_label"],
        "policy_category": policy_case["policy_category"],
        "amount_requested": amount_requested,
        "eligibility": eligibility,
        "reason": reason,
        "estimated_maximum_reimbursement": estimated_maximum,
        "required_documents": required_documents,
        "matched_rule_title": best_rule.get("title"),
        "matched_rule_id": best_rule.get("id"),
        "policy_key": policy_metadata.get("policy_key"),
        "coverage_type": policy_metadata.get("coverage_type"),
        "policy_limit": policy_limit,
        "policy_frequency_limit": frequency_limit,
        "eligible_levels": eligible_levels,
        "detected_employee_level": employee_level,
        "provided_documents": policy_case.get("provided_documents", []),
        "missing_required_documents": missing_documents,
        "frequency_requested": frequency_requested,
        "requested_day_of_month": policy_case.get("requested_day_of_month"),
        "case_match_score": case_match_score,
        "constraints_triggered": triggered_constraints,
        "next_action": next_action,
        "approval_chain": policy_metadata.get("approval_chain"),
        "simulation_mode": policy_metadata.get("simulation_mode"),
        "affects_balance": policy_metadata.get("affects_balance"),
        "balance_type": policy_metadata.get("balance_type"),
    }


def _summarize_policy_reasoning(reasoning: dict[str, Any]) -> str:
    eligibility = str(reasoning.get("eligibility") or "needs_review")
    case_label = str(reasoning.get("case_label") or "kasus policy ini")
    rule_title = str(reasoning.get("matched_rule_title") or "policy terkait")
    reason = str(reasoning.get("reason") or "Perlu verifikasi policy lebih lanjut.")
    amount_requested = reasoning.get("amount_requested")
    estimated_maximum = reasoning.get("estimated_maximum_reimbursement")
    required_documents = reasoning.get("required_documents") or []
    policy_limit_text = _format_policy_limit(reasoning.get("policy_limit"))
    frequency_limit_text = _format_frequency_limit(reasoning.get("policy_frequency_limit"))
    detected_employee_level = str(reasoning.get("detected_employee_level") or "").strip()
    eligible_levels = _coerce_text_list(reasoning.get("eligible_levels"))

    approval_chain = _coerce_text_list(reasoning.get("approval_chain"))
    simulation_mode = bool(reasoning.get("simulation_mode"))

    if eligibility == "eligible":
        lead = f"Kasus {case_label} ini kemungkinan eligible."
    elif eligibility == "not_eligible":
        lead = f"Kasus {case_label} ini kemungkinan tidak eligible."
    else:
        lead = f"Kasus {case_label} ini sebaiknya dianggap needs review dulu."

    parts = [lead, f"Policy yang paling relevan: {rule_title}.", reason]
    if amount_requested is not None:
        parts.append(f"Nominal yang terbaca dari pertanyaanmu: {_format_rupiah(amount_requested)}.")
    if policy_limit_text:
        parts.append(f"Batas policy yang relevan: {policy_limit_text}.")
    if frequency_limit_text:
        parts.append(f"Limit frekuensi policy: {frequency_limit_text}.")
    if eligible_levels:
        parts.append(
            "Level yang dicakup policy ini: "
            + _format_employee_levels(eligible_levels)
            + "."
        )
    if detected_employee_level:
        parts.append(
            "Level yang terbaca dari pertanyaanmu: "
            + EMPLOYEE_LEVEL_LABELS.get(detected_employee_level, detected_employee_level)
            + "."
        )
    if estimated_maximum is not None:
        parts.append(
            "Estimasi batas nominal yang bisa dijadikan acuan awal: "
            + _format_rupiah(estimated_maximum)
            + "."
        )
    if required_documents:
        parts.append(
            "Dokumen yang sebaiknya disiapkan: " + ", ".join(required_documents) + "."
        )
    if approval_chain:
        parts.append(
            "Jalur persetujuan yang diperlukan: " + " -> ".join(approval_chain) + "."
        )
    if simulation_mode:
        parts.append(
            "Aku bisa membantumu mensimulasikan pengajuan ini jika kamu memberikan detail tanggal atau nominal yang lebih spesifik."
        )
    if reasoning.get("next_action"):
        parts.append(str(reasoning["next_action"]))
    return " ".join(parts)


def _select_leave_rule(
    matched_rules: list[dict[str, Any]],
    *,
    preferred_case_types: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    leave_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for rule in matched_rules:
        if str(rule.get("category") or "").strip().lower() != "leave":
            continue
        leave_candidates.append((rule, _build_policy_metadata(rule)))

    if not leave_candidates:
        return None, None

    for case_type in preferred_case_types:
        for rule, metadata in leave_candidates:
            if metadata.get("case_type") == case_type:
                return rule, metadata

    return leave_candidates[0]


def _summarize_leave_operational_policy(
    message: str,
    matched_rules: list[dict[str, Any]],
) -> str | None:
    focus = _detect_leave_operational_policy_focus(message)
    if focus is None:
        return None

    preferred_case_types = (
        ["annual_leave"]
        if focus in {"balance_refresh", "approval_chain"}
        else ["sick_leave", "annual_leave"]
    )
    rule, metadata = _select_leave_rule(
        matched_rules,
        preferred_case_types=preferred_case_types,
    )
    if rule is None or metadata is None:
        return None

    rule_title = str(rule.get("title") or "policy cuti")
    approval_chain = _coerce_text_list(metadata.get("approval_chain")) or ["atasan langsung"]
    constraints = _coerce_json_object(metadata.get("constraints"))
    required_documents = _coerce_text_list(metadata.get("required_documents"))

    if focus == "balance_refresh":
        parts = [
            f"Untuk pertanyaan saldo cuti, policy yang paling relevan adalah {rule_title}.",
            "Di policy ini, jatah cuti tahunan dibaca per tahun kalender, jadi bukan model yang bertambah sedikit demi sedikit setiap bulan.",
        ]
        policy_limit_text = _format_policy_limit(metadata.get("amount_limit"))
        if policy_limit_text:
            parts.append(f"Jatah dasarnya {policy_limit_text}.")
        min_tenure_months = _coerce_int(constraints.get("min_tenure_months"))
        if min_tenure_months is not None:
            parts.append(
                f"Cuti tahunan baru bisa dipakai setelah melewati {min_tenure_months} bulan masa probation."
            )
        if constraints.get("carry_over_allowed") is False:
            parts.append("Sisa cuti tidak dibawa ke tahun berikutnya.")
        return " ".join(parts)

    if focus == "approval_chain":
        parts = [
            f"Untuk cuti, jalur persetujuan yang tercatat di {rule_title} adalah {' -> '.join(approval_chain)}."
        ]
        request_notice_days = _coerce_int(constraints.get("request_notice_days"))
        if request_notice_days is not None:
            parts.append(
                f"Pengajuan sebaiknya diajukan minimal {request_notice_days} hari kerja sebelumnya lewat sistem HR."
            )
        return " ".join(parts)

    parts = [
        f"Untuk izin sakit, policy yang paling relevan adalah {rule_title}.",
        "Langkah awal paling aman tetap kabari atasan langsungmu terlebih dulu.",
    ]
    if required_documents:
        parts.append(
            "Dokumen yang biasanya diminta: " + ", ".join(required_documents) + "."
        )
    if bool(constraints.get("digital_submission_allowed")):
        parts.append("Dokumen pendukung bisa dikirim secara digital kalau dibutuhkan.")
    if metadata.get("affects_balance") is False:
        parts.append("Cuti sakit ini tidak mengurangi jatah cuti tahunan.")
    return " ".join(parts)


def _select_departments(
    message: str,
    departments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lowered = _normalize_text(message)
    topic = _detect_contact_guidance_topic(message)
    selected: list[dict[str, Any]] = []

    for department in departments:
        department_name = department["department_name"].lower()
        if department_name in lowered and department not in selected:
            selected.append(department)

    if topic is not None:
        target_department_name = topic["department_name"]
        for department in departments:
            if department["department_name"].lower() == target_department_name:
                if department not in selected:
                    selected.append(department)

    for department_name, keywords in DEPARTMENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            for department in departments:
                if department["department_name"].lower() == department_name:
                    if department not in selected:
                        selected.append(department)

    if selected:
        return selected
    if _wants_contact_guidance(message):
        for department in departments:
            if department["department_name"].lower() == "human resources":
                return [department]
    return departments[:3]


def _select_responsibility_route(
    message: str,
    responsibility_routes: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    topic = _detect_contact_guidance_topic(message)
    if topic is None:
        return None, None

    for route in responsibility_routes:
        if str(route.get("topic_key") or "").strip().lower() == topic["key"]:
            return topic, route

    return topic, None


def _ensure_route_department_selected(
    selected_departments: list[dict[str, Any]],
    all_departments: list[dict[str, Any]],
    responsibility_route: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if responsibility_route is None:
        return selected_departments

    department_id = str(responsibility_route.get("department_id") or "").strip()
    department_name = str(responsibility_route.get("department_name") or "").strip()
    if not department_id and not department_name:
        return selected_departments

    for department in selected_departments:
        if department_id and department.get("department_id") == department_id:
            return selected_departments
        if department_name and department.get("department_name") == department_name:
            return selected_departments

    for department in all_departments:
        if department_id and department.get("department_id") == department_id:
            return [*selected_departments, department]
        if department_name and department.get("department_name") == department_name:
            return [*selected_departments, department]

    synthesized_department = {
        "department_id": department_id or None,
        "department_name": department_name,
        "parent_department_name": None,
        "head_employee_name": None,
    }
    return [*selected_departments, synthesized_department]


def _summarize_rules(rules: list[dict[str, Any]]) -> str:
    if not rules:
        return (
            "Aku tidak menemukan kebijakan perusahaan yang cukup relevan dari "
            "kata kunci yang diberikan."
        )

    parts = []
    for rule in rules:
        effective_date = (
            _format_date(date.fromisoformat(rule["effective_date"]))
            if rule.get("effective_date")
            else "-"
        )
        parts.append(
            f"{rule['title']} ({rule['category']}, efektif {effective_date}): "
            f"{re.sub(r'\s+', ' ', rule['content']).strip()}"
        )
    return " ".join(parts)


def _summarize_structure(departments: list[dict[str, Any]]) -> str:
    if not departments:
        return "Aku tidak menemukan struktur departemen perusahaan untuk company ini."

    parts = []
    for department in departments:
        parts.append(
            f"Departemen {department['department_name']} dipimpin oleh "
            f"{department['head_employee_name'] or 'belum ditetapkan'}."
        )
    return " ".join(parts)


def _summarize_contact_guidance(
    message: str,
    departments: list[dict[str, Any]],
    responsibility_routes: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    if not departments:
        return (
            "Aku belum menemukan PIC struktur perusahaan yang cukup jelas untuk "
            "menentukan kontak yang paling tepat.",
            {},
        )

    topic, responsibility_route = _select_responsibility_route(
        message,
        responsibility_routes or [],
    )
    metadata: dict[str, Any] = {}
    if topic is not None:
        route_channel = (
            str(responsibility_route.get("recommended_channel") or "").strip()
            if responsibility_route is not None
            else ""
        )
        metadata = {
            "contact_guidance_topic": topic["key"],
            "recommended_channel": route_channel or topic["recommended_channel"],
            "preparation_checklist": (
                _coerce_text_list(
                    responsibility_route.get("preparation_checklist")
                    if responsibility_route is not None
                    else topic["preparation_checklist"]
                )
                or list(topic["preparation_checklist"])
            ),
        }

    if responsibility_route is not None and topic is not None:
        department_name = (
            str(responsibility_route.get("department_name") or "").strip()
            or departments[0]["department_name"]
        )
        primary_contact_name = (
            str(responsibility_route.get("primary_contact_name") or "").strip()
            or f"tim {department_name}"
        )
        primary_contact_role = str(
            responsibility_route.get("primary_contact_role") or ""
        ).strip()
        alternate_contact_name = str(
            responsibility_route.get("alternate_contact_name") or ""
        ).strip()
        alternate_contact_role = str(
            responsibility_route.get("alternate_contact_role") or ""
        ).strip()

        primary_label = primary_contact_name
        if primary_contact_role:
            primary_label = f"{primary_contact_name} ({primary_contact_role})"

        metadata.update(
            {
                "contact_guidance_route_source": "responsibility_route",
                "primary_contact_name": primary_contact_name,
                "primary_contact_role": primary_contact_role,
            }
        )
        if alternate_contact_name:
            metadata["alternate_contact_name"] = alternate_contact_name
        if alternate_contact_role:
            metadata["alternate_contact_role"] = alternate_contact_role

        summary = topic["summary_template"].format(
            contact_name=primary_label,
            department_name=department_name,
        )
        if alternate_contact_name:
            alternate_label = alternate_contact_name
            if alternate_contact_role:
                alternate_label = f"{alternate_contact_name} ({alternate_contact_role})"
            summary += f" Kalau PIC utama tidak tersedia, alternatif awalnya {alternate_label}."

        return summary, metadata

    parts = []
    for department in departments:
        department_name = department["department_name"]
        contact_name = department["head_employee_name"] or f"tim {department_name}"
        lowered_name = department_name.lower()

        if topic is not None and lowered_name == topic["department_name"]:
            parts.append(
                topic["summary_template"].format(
                    contact_name=contact_name,
                    department_name=department_name,
                )
            )
            continue

        if lowered_name == "human resources":
            parts.append(
                "Untuk urusan administrasi HR, onboarding, cuti, payroll, atau "
                f"policy internal, kamu bisa mulai dari {contact_name} di departemen "
                f"{department_name}."
            )
            continue

        if lowered_name == "it":
            parts.append(
                "Untuk urusan akun kerja, akses sistem, atau perangkat, kamu bisa "
                f"hubungi {contact_name} di departemen {department_name}."
            )
            continue

        parts.append(
            f"Untuk urusan yang terkait dengan {department_name}, kontak yang tercatat "
            f"adalah {contact_name}."
        )

    if metadata:
        metadata.setdefault("contact_guidance_route_source", "department_head_fallback")
    return " ".join(parts), metadata


def _wants_contact_guidance(message: str) -> bool:
    lowered = _normalize_text(message)
    if any(keyword in lowered for keyword in CONTACT_GUIDANCE_KEYWORDS):
        return True

    topic = _detect_contact_guidance_topic(message)
    if topic is None:
        return False

    return any(
        marker in lowered
        for marker in [
            "siapa",
            "hubungi",
            "kontak",
            "tanya",
            "pic",
            "jalur",
            "ke mana",
        ]
    )


def _wants_policy(message: str) -> bool:
    lowered = _normalize_text(message)
    if any(keyword in lowered for keyword in POLICY_EXPLICIT_KEYWORDS):
        return True
    if _detect_leave_operational_policy_focus(message) is not None:
        return True
    if _wants_contact_guidance(message):
        return False
    if _extract_policy_case(message) is not None:
        return True
    return any(
        _contains_term(lowered, keyword)
        for keywords in RULE_CATEGORY_KEYWORDS.values()
        for keyword in keywords
    )


def _wants_structure(message: str) -> bool:
    lowered = _normalize_text(message)
    if _wants_contact_guidance(message):
        return True
    return any(
        keyword in lowered
        for keyword in [
            "struktur",
            "organisasi",
            "departemen",
            "department",
            "tim hr",
            "kepala departemen",
            "head of",
            "human resources",
            "personalia",
            "kontak hr",
            "pic hr",
        ]
    )


async def run_company_agent(
    db: AsyncSession,
    session: SessionContext,
    message: str,
) -> CompanyAgentResult:
    wants_contact_guidance = _wants_contact_guidance(message)
    wants_structure = _wants_structure(message)
    wants_policy = _wants_policy(message)
    rules: list[dict[str, Any]] = []
    vector_matches: list[dict[str, Any]] = []
    matched_rules: list[dict[str, Any]] = []
    if wants_policy:
        rules = await _load_company_rules(db, session.company_id)
        vector_matches = await _search_rule_chunks_by_vector(db, session.company_id, message)
        if vector_matches:
            matched_rules = _apply_policy_freshness(vector_matches, rules)
        else:
            matched_rules = _apply_policy_freshness(_rank_rules(message, rules), rules)

    records: dict[str, Any] = {}
    evidence: list[EvidenceItem] = []
    summary_parts: list[str] = []
    retrieval_assessment: dict[str, Any] = {}

    retrieval_mode = "mixed_lookup" if wants_policy and wants_structure else (
        "structure_lookup" if wants_structure else "policy_lookup"
    )

    if matched_rules:
        records["matched_rules"] = matched_rules
        records["retrieval_strategy"] = "vector" if vector_matches else "keyword"
        policy_assessment = _assess_policy_retrieval(
            matched_rules,
            retrieval_strategy=records["retrieval_strategy"],
        )
        retrieval_assessment["policy"] = policy_assessment
        policy_reasoning = _evaluate_policy_reasoning(
            message,
            matched_rules,
            policy_assessment=policy_assessment,
        )
        if policy_reasoning is not None:
            records["policy_reasoning"] = policy_reasoning
            policy_summary = _summarize_policy_reasoning(policy_reasoning)
        else:
            leave_operational_summary = _summarize_leave_operational_policy(
                message,
                matched_rules,
            )
            policy_summary = leave_operational_summary or _summarize_rules(matched_rules)
            if policy_assessment["status"] == "partial":
                policy_summary = f"{policy_assessment['reason']} {policy_summary}"
        summary_parts.append(policy_summary)
        for rule in matched_rules:
            policy_metadata = _build_policy_metadata(rule)
            evidence.append(
                EvidenceItem(
                    source_type="company_rule",
                    title=rule["title"],
                    snippet=_snippet(rule.get("matched_chunk") or rule["content"]),
                    metadata={
                        "rule_id": rule["id"],
                        "category": rule["category"],
                        "matched_terms": rule.get("matched_terms", []),
                        "similarity": rule.get("similarity"),
                        "retrieval_status": policy_assessment["status"],
                        "freshness_status": rule.get("freshness_status"),
                        "latest_effective_date": rule.get("latest_effective_date"),
                        "version_source": rule.get("version_source"),
                        "promoted_from_rule_id": rule.get("promoted_from_rule_id"),
                        "policy_key": policy_metadata.get("policy_key"),
                        "case_type": policy_metadata.get("case_type"),
                    },
                )
            )
    elif wants_policy:
        retrieval_assessment["policy"] = _assess_policy_retrieval(
            matched_rules,
            retrieval_strategy="vector" if vector_matches else "keyword",
        )
        policy_reasoning = _evaluate_policy_reasoning(
            message,
            matched_rules,
            policy_assessment=retrieval_assessment["policy"],
        )
        if policy_reasoning is not None:
            records["policy_reasoning"] = policy_reasoning
            summary_parts.append(_summarize_policy_reasoning(policy_reasoning))

    if wants_structure:
        departments = await _load_company_structure(db, session.company_id)
        responsibility_routes = (
            await _load_responsibility_routes(db, session.company_id)
            if wants_contact_guidance
            else []
        )
        _topic, selected_route = _select_responsibility_route(
            message,
            responsibility_routes,
        )
        selected_departments = _select_departments(message, departments)
        selected_departments = _ensure_route_department_selected(
            selected_departments,
            departments,
            selected_route,
        )
        records["departments"] = selected_departments
        if wants_contact_guidance:
            records["contact_guidance_requested"] = True
            contact_summary, contact_metadata = _summarize_contact_guidance(
                message,
                selected_departments,
                responsibility_routes=responsibility_routes,
            )
            summary_parts.append(contact_summary)
            records.update(contact_metadata)
        else:
            summary_parts.append(_summarize_structure(selected_departments))
        retrieval_assessment["structure"] = _build_retrieval_assessment(
            "enough" if selected_departments else "weak",
            (
                "Struktur organisasi yang relevan berhasil ditemukan."
                if selected_departments
                else "Struktur organisasi yang relevan belum ditemukan."
            ),
            department_count=len(selected_departments),
        )

        for department in selected_departments:
            evidence.append(
                EvidenceItem(
                    source_type="company_structure",
                    title=department["department_name"],
                    snippet=(
                        f"Head: {department['head_employee_name'] or 'belum ditetapkan'}"
                    ),
                    metadata={
                        "department_id": department["department_id"],
                        "parent_department_name": department["parent_department_name"],
                        "retrieval_status": retrieval_assessment["structure"]["status"],
                        "contact_guidance": wants_contact_guidance,
                        "contact_guidance_topic": records.get("contact_guidance_topic"),
                        "contact_guidance_route_source": records.get(
                            "contact_guidance_route_source"
                        ),
                        "primary_contact_name": records.get("primary_contact_name"),
                        "alternate_contact_name": records.get("alternate_contact_name"),
                    },
                )
            )

    if not summary_parts:
        summary_parts.append(
            "Aku belum menemukan referensi policy atau struktur perusahaan yang cukup kuat."
        )
    if retrieval_assessment:
        records["retrieval_assessment"] = retrieval_assessment

    return CompanyAgentResult(
        retrieval_mode=retrieval_mode,
        summary=" ".join(summary_parts),
        records=records,
        evidence=evidence,
    )
