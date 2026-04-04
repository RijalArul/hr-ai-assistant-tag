from __future__ import annotations

import re
from typing import Any


def _normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message.lower()).strip()


# ---------------------------------------------------------------------------
# Date / number helpers
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}"     # YYYY-MM-DD or YYYY/M/D
    r"|\d{1,2}[-/]\d{1,2}[-/]\d{4}"        # DD-MM-YYYY or D/M/YYYY
    r"|\d{1,2}\s+"                          # "12 April 2026" / "5 april"
      r"(?:jan(?:uari)?|feb(?:ruari)?|mar(?:et)?|apr(?:il)?|mei|jun(?:i)?|"
      r"jul(?:i)?|agu(?:stus)?|sep(?:tember)?|okt(?:ober)?|nov(?:ember)?|"
      r"des(?:ember)?|january|february|march|april|may|june|july|august|"
      r"september|october|november|december)"
      r"(?:\s+\d{4})?)\b",
    re.IGNORECASE,
)

_AMOUNT_RE = re.compile(
    r"\b(\d[\d.,]*)\s*"
    r"(?:k|rb|ribu|rbu|jt|juta|m(?:illion)?|000)?\b",
    re.IGNORECASE,
)

# Pre-removal: strip year-like tokens (1900–2099) so they are never
# mistaken for monetary amounts.
_YEAR_TOKEN_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")


def _extract_first_date(text: str) -> str | None:
    """Return the first date-like string found in *text*, or None."""
    match = _DATE_RE.search(text)
    return match.group(0).strip() if match else None


def _extract_all_dates(text: str) -> list[str]:
    return [m.group(0).strip() for m in _DATE_RE.finditer(text)]


def _parse_numeric(raw_str: str, *, has_suffix: bool) -> float:
    """Parse a numeric string that may use '.' or ',' as thousands or decimal
    separators.

    Rules:
    * Single dot/comma with 1-2 trailing chars and a suffix     → decimal  ("1.5jt" → 1.5)
    * Single dot/comma with 1-2 trailing chars, no suffix       → decimal  ("1.5" → 1.5)
    * Single dot/comma with 3 trailing chars                    → thousands ("1.500" → 1500)
    * Multiple separators                                       → all stripped ("1.500.000" → 1500000)
    """
    dots = raw_str.count(".")
    commas = raw_str.count(",")
    total_seps = dots + commas

    if total_seps == 0:
        return float(raw_str)

    if total_seps == 1:
        sep = "." if dots else ","
        parts = raw_str.split(sep)
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Decimal notation: "1.5" or "1,5" or "1.50"
            return float(f"{parts[0]}.{parts[1]}")
        else:
            # Thousands notation: "1.500" or "1,500"
            return float(raw_str.replace(sep, ""))

    # Multiple separators — strip all
    return float(raw_str.replace(".", "").replace(",", ""))


def _extract_amount(text: str) -> float | None:
    """Return the first monetary amount found in *text*, or None.

    Handles ``500rb``, ``1.5jt``, ``1,5jt``, ``2.000.000``, ``150000``.

    Year-like tokens (1900-2099) are stripped before matching so they cannot
    be mistaken for bare amounts.  Bare integers without a currency suffix
    require a minimum of Rp 1,000 to filter out stray date components.
    """
    # Remove year-like tokens so "April 2026" doesn't yield amount=2026.
    clean = _YEAR_TOKEN_RE.sub("", text)
    match = _AMOUNT_RE.search(clean)
    if not match:
        return None
    raw_str = match.group(1)
    suffix = match.group(0)[len(raw_str):].strip().lower()
    try:
        value = _parse_numeric(raw_str, has_suffix=bool(suffix))
    except ValueError:
        return None
    if suffix in {"k", "rb", "ribu", "rbu"}:
        value *= 1_000
    elif suffix in {"jt", "juta"}:
        value *= 1_000_000
    elif suffix in {"m", "million"}:
        value *= 1_000_000
    else:
        # No currency suffix — require at least Rp 1,000 to filter out day/
        # month numbers (1-31) and any residual small integers.
        if value < 1_000:
            return None
    return value


# ---------------------------------------------------------------------------
# Leave type inference
# ---------------------------------------------------------------------------

_LEAVE_TYPE_MAP: list[tuple[list[str], str]] = [
    (["annual", "tahunan", "cuti tahunan"], "annual"),
    (["sakit", "sick", "medical"], "sick"),
    (["melahirkan", "maternity", "paternity", "hamil"], "maternity/paternity"),
    (["pernikahan", "married", "nikah", "kawin"], "marriage"),
    (["duka", "meninggal", "bereavement"], "bereavement"),
    (["khusus", "special", "penting"], "special"),
]


def _infer_leave_type(text: str) -> str:
    lowered = text.lower()
    for keywords, label in _LEAVE_TYPE_MAP:
        if any(kw in lowered for kw in keywords):
            return label
    return "annual"  # sensible default


# ---------------------------------------------------------------------------
# Reimbursement category inference
# ---------------------------------------------------------------------------

_REIMBURSE_CATEGORY_MAP: list[tuple[list[str], str]] = [
    (["kacamata", "optical", "lensa", "frame"], "optical"),
    (["psikolog", "psychologist", "mental health", "konseling", "counseling"], "mental_health"),
    (["dokter", "doctor", "rumah sakit", "hospital", "medical", "kesehatan", "klinik"], "medical"),
    (["internet", "wifi", "modem", "broadband"], "internet_allowance"),
    (["transport", "transportasi", "ojek", "grab", "gojek", "taxi", "bensin", "bbm"], "transportation"),
    (["makan", "meal", "lunch", "dinner", "food", "restoran"], "meal"),
    (["training", "pelatihan", "kursus", "course", "sertifikasi", "certification"], "training"),
]


def _infer_reimbursement_category(text: str) -> str:
    lowered = text.lower()
    for keywords, label in _REIMBURSE_CATEGORY_MAP:
        if any(kw in lowered for kw in keywords):
            return label
    return "general"


# ---------------------------------------------------------------------------
# Profile field inference
# ---------------------------------------------------------------------------

_PROFILE_FIELD_MAP: list[tuple[list[str], str]] = [
    (["nomor hp", "no hp", "phone", "telepon", "handphone", "nomer hp"], "phone_number"),
    (["email", "surel"], "email"),
    (["alamat", "address", "domisili"], "address"),
    (["rekening", "bank account", "account number", "no rek"], "bank_account"),
    (["npwp", "tax id", "pajak"], "npwp"),
    (["nama darurat", "emergency contact", "kontak darurat"], "emergency_contact"),
]


def _infer_profile_fields(text: str) -> dict[str, Any]:
    lowered = text.lower()
    fields: dict[str, Any] = {}
    for keywords, field_name in _PROFILE_FIELD_MAP:
        if any(kw in lowered for kw in keywords):
            fields[field_name] = None  # value to be collected
    return fields


# ---------------------------------------------------------------------------
# Execution gate for payroll document request (unchanged)
# ---------------------------------------------------------------------------

def _assess_payroll_document_request(lowered: str) -> dict[str, Any]:
    has_document_target = any(
        token in lowered
        for token in ["payslip", "salary slip", "pay slip", "slip gaji", "pdf"]
    )
    has_strong_execution_verb = any(
        token in lowered
        for token in [
            "generate", "buatkan", "buat", "kirimkan", "kirim", "send",
            "emailkan", "email", "downloadkan", "download", "siapkan",
            "prepare", "terbitkan",
        ]
    )
    addresses_assistant_directly = any(
        token in lowered
        for token in [
            "tolong", "please", "bantu", "bisakah kamu", "could you",
            "can you", "minta tolong",
        ]
    )
    exploratory_markers = any(
        token in lowered
        for token in [
            "bagaimana", "how", "cara", "apakah", "what",
            "bisa nggak", "bisa gak", "bisakah saya", "can i", "could i",
        ]
    )

    if (
        has_document_target
        and exploratory_markers
        and not (addresses_assistant_directly and has_strong_execution_verb)
    ):
        return {
            "mode": "exploratory_request",
            "should_trigger": False,
            "reason": "The user appears to be asking about document availability, not requesting execution yet.",
        }

    if has_document_target and (
        has_strong_execution_verb
        or (addresses_assistant_directly and not exploratory_markers)
    ):
        return {
            "mode": "execution_request",
            "should_trigger": True,
            "reason": "The user explicitly asked the assistant to generate or deliver the document.",
        }

    return {
        "mode": "topic_only",
        "should_trigger": False,
        "reason": "The message mentions a document topic but does not clearly request execution.",
    }


# ---------------------------------------------------------------------------
# Execution gate for leave request (F.2 + F.3)
# ---------------------------------------------------------------------------

_LEAVE_TRIGGER_VERBS = [
    "ajukan", "ajukan cuti", "minta cuti", "request cuti", "request leave",
    "apply cuti", "apply leave", "ambil cuti", "book cuti", "book leave",
    "izin", "cuti", "leave",
]
_LEAVE_EXPLORATORY = [
    # "bisa" and "boleh" intentionally excluded: they appear in legitimate
    # submission phrases like "cuti, bisa mulai 10 April?" and cause false
    # negatives when included.
    "apakah", "how", "bagaimana", "cara", "gimana",
    "kalau", "syarat", "ketentuan", "aturan",
]


def _assess_leave_request(message: str, lowered: str) -> dict[str, Any]:
    has_trigger_verb = any(v in lowered for v in _LEAVE_TRIGGER_VERBS)
    is_exploratory = any(m in lowered for m in _LEAVE_EXPLORATORY)

    if not has_trigger_verb or is_exploratory:
        return {
            "mode": "not_applicable",
            "should_trigger": False,
            "reason": "Message does not contain a clear leave submission request.",
        }

    dates = _extract_all_dates(message)
    start_date: str | None = dates[0] if len(dates) >= 1 else None
    end_date: str | None = dates[1] if len(dates) >= 2 else None
    leave_type = _infer_leave_type(message)

    missing_fields: list[str] = []
    if start_date is None:
        missing_fields.append("start_date")
    if end_date is None:
        missing_fields.append("end_date")

    if missing_fields:
        return {
            "mode": "missing_info",
            "should_trigger": False,
            "reason": "Leave request detected but required fields are missing.",
            "missing_fields": missing_fields,
            "extracted": {
                "leave_type": leave_type,
                "start_date": start_date,
                "end_date": end_date,
            },
            "follow_up_prompt": _build_leave_follow_up_prompt(missing_fields),
        }

    return {
        "mode": "execution_request",
        "should_trigger": True,
        "reason": "Leave request detected with sufficient information to create a formal request.",
        "extracted": {
            "leave_type": leave_type,
            "start_date": start_date,
            "end_date": end_date,
        },
    }


def _build_leave_follow_up_prompt(missing_fields: list[str]) -> str:
    if "start_date" in missing_fields and "end_date" in missing_fields:
        return (
            "Untuk mengajukan cuti, aku butuh tanggal mulai dan tanggal selesai cuti kamu. "
            "Misalnya: cuti dari 10 April sampai 14 April 2026."
        )
    if "start_date" in missing_fields:
        return "Mulai tanggal berapa cutinya?"
    if "end_date" in missing_fields:
        return "Sampai tanggal berapa cutinya?"
    return "Tolong lengkapi detail cuti kamu."


# ---------------------------------------------------------------------------
# Execution gate for reimbursement request (F.2 + F.3)
# ---------------------------------------------------------------------------

_REIMBURSE_TRIGGER_VERBS = [
    "klaim", "claim", "reimburse", "reimbursement", "ajukan klaim",
    "minta reimburse", "ajukan reimburse", "minta klaim", "submit klaim",
    "submit claim", "tagih",
]
_REIMBURSE_EXPLORATORY = [
    # "bisa" and "boleh" excluded — too ambiguous (see _LEAVE_EXPLORATORY note).
    "apakah", "how", "bagaimana", "cara", "gimana",
    "kalau", "syarat", "ketentuan", "aturan", "limit", "berapa",
]


def _assess_reimbursement_request(message: str, lowered: str) -> dict[str, Any]:
    has_trigger_verb = any(v in lowered for v in _REIMBURSE_TRIGGER_VERBS)
    is_exploratory = any(m in lowered for m in _REIMBURSE_EXPLORATORY)

    if not has_trigger_verb or is_exploratory:
        return {
            "mode": "not_applicable",
            "should_trigger": False,
            "reason": "Message does not contain a clear reimbursement submission request.",
        }

    category = _infer_reimbursement_category(message)
    amount = _extract_amount(message)
    expense_date = _extract_first_date(message)

    missing_fields: list[str] = []
    if amount is None:
        missing_fields.append("amount")
    if expense_date is None:
        missing_fields.append("expense_date")

    if missing_fields:
        return {
            "mode": "missing_info",
            "should_trigger": False,
            "reason": "Reimbursement request detected but required fields are missing.",
            "missing_fields": missing_fields,
            "extracted": {
                "category": category,
                "amount": amount,
                "expense_date": expense_date,
            },
            "follow_up_prompt": _build_reimburse_follow_up_prompt(missing_fields, category),
        }

    return {
        "mode": "execution_request",
        "should_trigger": True,
        "reason": "Reimbursement request detected with sufficient information to create a formal request.",
        "extracted": {
            "category": category,
            "amount": amount,
            "expense_date": expense_date,
        },
    }


def _build_reimburse_follow_up_prompt(missing_fields: list[str], category: str) -> str:
    parts: list[str] = []
    if "amount" in missing_fields:
        parts.append("nominal yang ingin diklaim")
    if "expense_date" in missing_fields:
        parts.append("tanggal pengeluaran")
    joined = " dan ".join(parts)
    return (
        f"Untuk mengajukan klaim {category}, aku butuh {joined}. "
        "Misalnya: klaim kacamata sebesar 500 ribu pada 3 April 2026."
    )


# ---------------------------------------------------------------------------
# Execution gate for profile update request (F.2 + F.3)
# ---------------------------------------------------------------------------

_PROFILE_TRIGGER_VERBS = [
    "update", "ubah", "ganti", "perbarui", "edit", "change",
    "revisi", "koreksi", "correct", "perbaiki",
]
_PROFILE_TARGET_WORDS = [
    "profil", "profile", "data", "nomor hp", "no hp", "telepon",
    "email", "alamat", "address", "rekening", "npwp", "kontak darurat",
]


def _assess_profile_update_request(message: str, lowered: str) -> dict[str, Any]:
    has_trigger_verb = any(v in lowered for v in _PROFILE_TRIGGER_VERBS)
    has_profile_target = any(t in lowered for t in _PROFILE_TARGET_WORDS)

    if not has_trigger_verb or not has_profile_target:
        return {
            "mode": "not_applicable",
            "should_trigger": False,
            "reason": "Message does not contain a clear profile update request.",
        }

    fields_to_update = _infer_profile_fields(message)

    if not fields_to_update:
        return {
            "mode": "missing_info",
            "should_trigger": False,
            "reason": "Profile update requested but no specific fields could be identified.",
            "missing_fields": ["fields_to_update"],
            "extracted": {"fields_to_update": {}},
            "follow_up_prompt": (
                "Data apa yang ingin kamu perbarui? "
                "Misalnya: nomor HP, alamat, rekening bank, atau NPWP."
            ),
        }

    return {
        "mode": "execution_request",
        "should_trigger": True,
        "reason": "Profile update request detected with identifiable fields.",
        "extracted": {"fields_to_update": fields_to_update},
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assess_action_execution_intent(
    message: str,
    *,
    intent_key: str,
) -> dict[str, Any]:
    """Assess whether *message* contains an actionable execution request.

    Returns a gate dict with at minimum:
    - ``mode``: "execution_request" | "missing_info" | "exploratory_request" |
                "topic_only" | "not_applicable"
    - ``should_trigger``: bool
    - ``reason``: str

    When ``mode == "missing_info"``:
    - ``missing_fields``: list[str] – fields that must be collected before triggering
    - ``extracted``: dict – fields that were successfully parsed from the message
    - ``follow_up_prompt``: str – a natural-language prompt to ask the user for missing info

    When ``mode == "execution_request"`` and the intent has extractable params:
    - ``extracted``: dict – parsed parameters to pass into the action payload
    """
    lowered = _normalize_message(message)

    if intent_key == "payroll_document_request":
        return _assess_payroll_document_request(lowered)

    if intent_key == "time_off_request_status":
        return _assess_leave_request(message, lowered)

    if intent_key == "company_policy" and any(
        v in lowered for v in _REIMBURSE_TRIGGER_VERBS
    ):
        return _assess_reimbursement_request(message, lowered)

    if intent_key == "personal_profile" and any(
        v in lowered for v in _PROFILE_TRIGGER_VERBS
    ):
        return _assess_profile_update_request(message, lowered)

    return {
        "mode": "not_applicable",
        "should_trigger": False,
        "reason": "No executable action gate was needed for this intent.",
    }
