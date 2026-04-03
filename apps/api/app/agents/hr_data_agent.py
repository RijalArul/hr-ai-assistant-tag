from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext
from app.models import ConversationIntent, EvidenceItem, HRDataAgentResult
from app.services.cache import get_cache

MONTH_ALIASES = {
    "jan": 1,
    "januari": 1,
    "january": 1,
    "feb": 2,
    "februari": 2,
    "february": 2,
    "mar": 3,
    "maret": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "mei": 5,
    "may": 5,
    "jun": 6,
    "juni": 6,
    "june": 6,
    "jul": 7,
    "juli": 7,
    "july": 7,
    "agu": 8,
    "agustus": 8,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "okt": 10,
    "oktober": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "des": 12,
    "desember": 12,
    "december": 12,
}

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

HR_INTENT_TO_TOPIC = {
    ConversationIntent.PAYROLL_INFO: ["payroll"],
    ConversationIntent.PAYROLL_DOCUMENT_REQUEST: ["payroll"],
    ConversationIntent.ATTENDANCE_REVIEW: ["attendance"],
    ConversationIntent.TIME_OFF_BALANCE: ["time_off"],
    ConversationIntent.TIME_OFF_REQUEST_STATUS: ["time_off"],
    ConversationIntent.PERSONAL_PROFILE: ["profile"],
}


def _format_rupiah(value: Decimal | int | float | None) -> str:
    if value is None:
        return "-"
    amount = int(value)
    return f"Rp{amount:,}".replace(",", ".")


def _format_date(value: date | None) -> str:
    if value is None:
        return "-"
    return f"{value.day} {MONTH_NAMES_ID[value.month]} {value.year}"


def _format_period_label(month: int | None, year: int | None) -> str | None:
    if month is not None and year is not None:
        return f"{MONTH_NAMES_ID[month]} {year}"
    if year is not None:
        return str(year)
    return None


def _extract_year(message: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", message)
    if match is None:
        return None
    return int(match.group(1))


def _extract_month(message: str) -> int | None:
    lowered = message.lower()
    for alias, month in MONTH_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return month
    return None


def _resolve_relative_period(
    message: str,
    *,
    now: datetime,
) -> tuple[int | None, int | None]:
    lowered = message.lower()

    if any(phrase in lowered for phrase in ["bulan ini", "this month", "month ini"]):
        return now.month, now.year

    if any(phrase in lowered for phrase in ["bulan lalu", "last month"]):
        previous_month = (now.replace(day=1) - timedelta(days=1))
        return previous_month.month, previous_month.year

    if "bulan kemarin" in lowered:
        previous_month = (now.replace(day=1) - timedelta(days=1))
        return previous_month.month, previous_month.year

    if any(phrase in lowered for phrase in ["tahun ini", "this year"]):
        return None, now.year

    if any(phrase in lowered for phrase in ["tahun lalu", "last year"]):
        return None, now.year - 1

    return None, None


def _normalize_context_message(message: str) -> str:
    return re.sub(r"\s+", " ", message.lower()).strip()


def _should_inherit_conversation_context(message: str) -> bool:
    lowered = _normalize_context_message(message)
    referential_markers = [
        "yang tadi",
        "tadi",
        "itu",
        "tersebut",
        "yang barusan",
        "barusan",
        "sebelumnya",
        "yang itu",
    ]
    if any(marker in lowered for marker in referential_markers):
        return True

    informative_tokens = re.findall(r"[a-zA-Z0-9_]{3,}", lowered)
    if len(informative_tokens) > 8:
        return False

    domain_signals = [
        "gaji",
        "salary",
        "payroll",
        "payslip",
        "slip gaji",
        "attendance",
        "kehadiran",
        "presensi",
        "jam masuk",
        "check in",
        "check-in",
        "cuti",
        "leave",
        "izin",
        "profil",
        "profile",
        "atasan",
        "manager",
    ]
    return not any(signal in lowered for signal in domain_signals)


def _get_recent_user_message(
    conversation_history: list[dict[str, str]] | None,
) -> str | None:
    if not conversation_history:
        return None

    for item in reversed(conversation_history):
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role == "user" and content:
            return content
    return None


def _build_contextual_message(
    message: str,
    conversation_history: list[dict[str, str]] | None,
) -> tuple[str, str | None]:
    if not _should_inherit_conversation_context(message):
        return message, None

    recent_user_message = _get_recent_user_message(conversation_history)
    if recent_user_message is None:
        return message, None

    return f"{recent_user_message}\n{message}", recent_user_message


def _wants_latest_relevant_period(message: str) -> bool:
    lowered = message.lower()
    return any(
        phrase in lowered
        for phrase in [
            "periode terkini",
            "period terbaru",
            "periode terbaru",
            "latest period",
            "latest payroll",
            "yang relevan terakhir",
            "yang terbaru",
        ]
    )


def _wants_rolling_30_day_window(message: str) -> bool:
    lowered = message.lower()
    return any(
        phrase in lowered
        for phrase in [
            "30 hari terakhir",
            "rolling 30 days",
            "rolling thirty days",
            "sebulan terakhir",
        ]
    )


def _previous_month_year(month: int, year: int) -> tuple[int, int]:
    if month == 1:
        return 12, year - 1
    return month - 1, year


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


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    return value


def _wants_average_check_in(message: str) -> bool:
    lowered = message.lower()
    mentions_check_in = any(
        token in lowered
        for token in [
            "jam masuk",
            "masuk kantor",
            "jam masuk kantor",
            "check in",
            "check-in",
            "jam datang",
        ]
    )
    mentions_average = any(
        token in lowered
        for token in [
            "rata",
            "rata-rata",
            "average",
            "avg",
            "rerata",
            "data",
            "jam berapa",
        ]
    )
    return mentions_check_in and mentions_average


def _wants_average_check_in_with_context(
    message: str,
    contextual_message: str,
    inherited_user_message: str | None,
) -> bool:
    if _wants_average_check_in(message):
        return True
    if inherited_user_message is None:
        return False

    lowered = message.lower()
    follow_up_markers = ["rata", "rata-rata", "average", "avg", "jam berapa"]
    return any(marker in lowered for marker in follow_up_markers) and _wants_average_check_in(
        contextual_message
    )


def _time_to_minutes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, time):
        return (value.hour * 60) + value.minute
    if isinstance(value, str):
        raw = value.strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(raw, fmt)
                return (parsed.hour * 60) + parsed.minute
            except ValueError:
                continue
    return None


def _format_minutes_as_time(value: int) -> str:
    hours = value // 60
    minutes = value % 60
    return f"{hours:02d}:{minutes:02d}"


def _wants_payroll_delta_explanation(message: str) -> bool:
    lowered = message.lower()
    mentions_payroll = any(
        token in lowered
        for token in [
            "gaji",
            "salary",
            "payroll",
            "net pay",
            "slip gaji",
            "payslip",
        ]
    )
    mentions_delta = any(
        token in lowered
        for token in [
            "lebih rendah",
            "lebih kecil",
            "lower",
            "decrease",
            "decreased",
            "drop",
            "turun",
            "why",
            "kenapa",
            "mengapa",
        ]
    )
    return mentions_payroll and mentions_delta


def _wants_payroll_delta_explanation_with_context(
    message: str,
    contextual_message: str,
    inherited_user_message: str | None,
) -> bool:
    if _wants_payroll_delta_explanation(message):
        return True
    if inherited_user_message is None:
        return False

    lowered = message.lower()
    follow_up_markers = [
        "kenapa",
        "mengapa",
        "why",
        "lebih rendah",
        "lebih kecil",
        "lower",
        "drop",
        "turun",
    ]
    return any(marker in lowered for marker in follow_up_markers) and (
        _wants_payroll_delta_explanation(contextual_message)
    )


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _serialize_value(value) for key, value in row.items()}


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    for record in records:
        fingerprint = tuple(sorted((key, str(value)) for key, value in record.items()))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(record)

    return deduped


def _resolve_topics(
    message: str,
    primary_intent: ConversationIntent,
    secondary_intents: list[ConversationIntent],
) -> list[str]:
    topics: list[str] = []

    for intent in [primary_intent, *secondary_intents]:
        for topic in HR_INTENT_TO_TOPIC.get(intent, []):
            if topic not in topics:
                topics.append(topic)

    lowered = message.lower()
    keyword_topics = {
        "payroll": ["gaji", "payroll", "bpjs", "pph21", "slip gaji", "salary"],
        "attendance": ["attendance", "kehadiran", "absen", "terlambat", "telat", "wfh"],
        "time_off": ["cuti", "leave", "izin"],
        "profile": ["profil", "data saya", "atasan saya", "manager saya", "join date"],
    }

    for topic, keywords in keyword_topics.items():
        if any(keyword in lowered for keyword in keywords) and topic not in topics:
            topics.append(topic)

    return topics


async def _get_employee_profile(
    db: AsyncSession,
    session: SessionContext,
) -> dict[str, Any] | None:
    cache = get_cache("employee_profile")
    cache_key = f"{session.company_id}:{session.employee_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    result = await db.execute(
        text(
            """
            SELECT
                e.id::text AS employee_id,
                e.name,
                lower(e.email) AS email,
                e.position,
                e.employment_type::text AS employment_type,
                e.employment_status::text AS employment_status,
                e.join_date,
                d.name AS department_name,
                m.name AS manager_name
            FROM employees e
            LEFT JOIN departments d
              ON d.id = e.department_id
            LEFT JOIN employees m
              ON m.id = e.manager_id
            WHERE e.id = CAST(:employee_id AS uuid)
              AND e.company_id = CAST(:company_id AS uuid)
            """
        ),
        {
            "employee_id": session.employee_id,
            "company_id": session.company_id,
        },
    )
    row = result.mappings().first()
    if row is None:
        return None

    profile = _serialize_row(dict(row))
    cache.set(cache_key, profile)
    return profile


async def _get_payroll_records(
    db: AsyncSession,
    session: SessionContext,
    month: int | None,
    year: int | None,
) -> list[dict[str, Any]]:
    cache = get_cache("payroll_records")
    cache_key = (
        f"{session.company_id}:{session.employee_id}:"
        f"{month or 'all'}:{year or 'all'}"
    )
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    filters = [
        "e.id = CAST(:employee_id AS uuid)",
        "e.company_id = CAST(:company_id AS uuid)",
    ]
    params: dict[str, Any] = {
        "employee_id": session.employee_id,
        "company_id": session.company_id,
    }

    if month is not None:
        filters.append("p.month = :month")
        params["month"] = month
    if year is not None:
        filters.append("p.year = :year")
        params["year"] = year

    limit = 1 if month is not None and year is not None else 3
    result = await db.execute(
        text(
            f"""
            SELECT
                p.month,
                p.year,
                p.basic_salary,
                p.allowances,
                p.gross_salary,
                p.deductions,
                p.bpjs_kesehatan,
                p.bpjs_ketenagakerjaan,
                p.pph21,
                p.net_pay,
                p.payment_status::text AS payment_status,
                p.payment_date
            FROM payroll p
            INNER JOIN employees e
              ON e.id = p.employee_id
            WHERE {" AND ".join(filters)}
            ORDER BY p.year DESC, p.month DESC
            LIMIT {limit}
            """
        ),
        params,
    )
    records = [_serialize_row(dict(row)) for row in result.mappings().all()]
    cache.set(cache_key, records)
    return records


async def _get_attendance_records(
    db: AsyncSession,
    session: SessionContext,
    month: int | None,
    year: int | None,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cache = get_cache("attendance_records")
    cache_key = (
        f"{session.company_id}:{session.employee_id}:"
        f"{month or 'all'}:{year or 'all'}:"
        f"{date_from.isoformat() if date_from else 'open'}:"
        f"{date_to.isoformat() if date_to else 'open'}:"
        f"{limit or 'default'}"
    )
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    filters = [
        "e.id = CAST(:employee_id AS uuid)",
        "e.company_id = CAST(:company_id AS uuid)",
    ]
    params: dict[str, Any] = {
        "employee_id": session.employee_id,
        "company_id": session.company_id,
    }

    if month is not None:
        filters.append("EXTRACT(MONTH FROM a.attendance_date) = :month")
        params["month"] = month
    if year is not None:
        filters.append("EXTRACT(YEAR FROM a.attendance_date) = :year")
        params["year"] = year
    if date_from is not None:
        filters.append("a.attendance_date >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        filters.append("a.attendance_date <= :date_to")
        params["date_to"] = date_to

    resolved_limit = limit or (31 if month is not None and year is not None else 7)
    result = await db.execute(
        text(
            f"""
            SELECT
                a.attendance_date,
                a.check_in,
                a.check_out,
                a.status::text AS status
            FROM attendance a
            INNER JOIN employees e
              ON e.id = a.employee_id
            WHERE {" AND ".join(filters)}
            ORDER BY a.attendance_date DESC
            LIMIT {resolved_limit}
            """
        ),
        params,
    )
    records = [_serialize_row(dict(row)) for row in result.mappings().all()]
    cache.set(cache_key, records)
    return records


async def _get_time_off_snapshot(
    db: AsyncSession,
    session: SessionContext,
    year: int,
) -> dict[str, Any]:
    cache = get_cache("time_off_snapshot")
    cache_key = f"{session.company_id}:{session.employee_id}:{year}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    balance_result = await db.execute(
        text(
            """
            SELECT
                leave_type,
                total_days,
                used_days,
                remaining_days,
                year
            FROM time_offs t
            INNER JOIN employees e
              ON e.id = t.employee_id
            WHERE e.id = CAST(:employee_id AS uuid)
              AND e.company_id = CAST(:company_id AS uuid)
              AND t.record_type = 'balance'
              AND t.year = :year
            ORDER BY leave_type ASC
            """
        ),
        {
            "employee_id": session.employee_id,
            "company_id": session.company_id,
            "year": year,
        },
    )
    balances = _dedupe_records(
        [_serialize_row(dict(row)) for row in balance_result.mappings().all()]
    )

    request_result = await db.execute(
        text(
            """
            SELECT
                leave_type,
                total_days,
                start_date,
                end_date,
                status::text AS status,
                reason,
                year
            FROM time_offs t
            INNER JOIN employees e
              ON e.id = t.employee_id
            WHERE e.id = CAST(:employee_id AS uuid)
              AND e.company_id = CAST(:company_id AS uuid)
              AND t.record_type = 'request'
              AND t.year = :year
            ORDER BY t.start_date DESC NULLS LAST
            LIMIT 3
            """
        ),
        {
            "employee_id": session.employee_id,
            "company_id": session.company_id,
            "year": year,
        },
    )
    requests = _dedupe_records(
        [_serialize_row(dict(row)) for row in request_result.mappings().all()]
    )
    snapshot = {
        "year": year,
        "balances": balances,
        "requests": requests,
    }
    cache.set(cache_key, snapshot)
    return snapshot


def _summarize_profile(profile: dict[str, Any]) -> str:
    return (
        f"Profil karyawan: {profile['name']} saat ini berposisi sebagai "
        f"{profile['position']} di departemen {profile['department_name'] or '-'}, "
        f"status {profile['employment_status']}, dengan atasan {profile['manager_name'] or '-'}."
    )


def _find_previous_payroll_record(
    reference_records: list[dict[str, Any]],
    target_record: dict[str, Any],
) -> dict[str, Any] | None:
    for index, record in enumerate(reference_records):
        if (
            record.get("month") == target_record.get("month")
            and record.get("year") == target_record.get("year")
        ):
            if index + 1 < len(reference_records):
                return reference_records[index + 1]
            return None
    if len(reference_records) >= 2:
        return reference_records[1]
    return None


def _summarize_payroll_difference(
    current_record: dict[str, Any],
    previous_record: dict[str, Any] | None,
) -> str | None:
    if previous_record is None:
        return None

    current_net = int(current_record["net_pay"])
    previous_net = int(previous_record["net_pay"])
    delta = current_net - previous_net
    previous_period = _format_period_label(
        previous_record.get("month"),
        previous_record.get("year"),
    ) or "periode sebelumnya"

    if delta == 0:
        return (
            f"Dibanding periode {previous_period}, net pay tidak lebih rendah; "
            f"nilainya tetap {_format_rupiah(current_net)}."
        )

    current_deductions = int(current_record.get("deductions", 0))
    previous_deductions = int(previous_record.get("deductions", 0))
    current_allowances = int(current_record.get("allowances", 0))
    previous_allowances = int(previous_record.get("allowances", 0))
    current_pph21 = int(current_record.get("pph21", 0))
    previous_pph21 = int(previous_record.get("pph21", 0))
    current_bpjs = int(current_record.get("bpjs_kesehatan", 0)) + int(
        current_record.get("bpjs_ketenagakerjaan", 0)
    )
    previous_bpjs = int(previous_record.get("bpjs_kesehatan", 0)) + int(
        previous_record.get("bpjs_ketenagakerjaan", 0)
    )

    factors: list[str] = []
    if current_deductions > previous_deductions:
        factors.append(
            f"potongan naik {_format_rupiah(current_deductions - previous_deductions)}"
        )
    if current_pph21 > previous_pph21:
        factors.append(
            f"PPH21 naik {_format_rupiah(current_pph21 - previous_pph21)}"
        )
    if current_bpjs > previous_bpjs:
        factors.append(
            f"total BPJS naik {_format_rupiah(current_bpjs - previous_bpjs)}"
        )
    if current_allowances < previous_allowances:
        factors.append(
            f"allowances turun {_format_rupiah(previous_allowances - current_allowances)}"
        )

    if delta < 0:
        summary = (
            f"Dibanding periode {previous_period}, net pay turun "
            f"{_format_rupiah(abs(delta))}."
        )
        if factors:
            summary += f" Perubahan yang paling terlihat: {', '.join(factors)}."
        return summary

    summary = (
        f"Dibanding periode {previous_period}, net pay justru naik "
        f"{_format_rupiah(delta)}."
    )
    if factors:
        summary += f" Walau begitu, ada perubahan komponen seperti {', '.join(factors)}."
    return summary


def _summarize_payroll(
    records: list[dict[str, Any]],
    *,
    requested_month: int | None = None,
    requested_year: int | None = None,
    latest_reference_records: list[dict[str, Any]] | None = None,
    wants_delta_explanation: bool = False,
    retrieval_assessment: dict[str, Any] | None = None,
) -> str:
    reference_records = latest_reference_records or records

    if not records:
        requested_period = _format_period_label(requested_month, requested_year)
        if requested_period and reference_records:
            latest = reference_records[0]
            latest_period = _format_period_label(
                latest.get("month"),
                latest.get("year"),
            ) or "periode terbaru"
            prefix = ""
            if retrieval_assessment and retrieval_assessment.get("status") == "partial":
                prefix = f"{retrieval_assessment['reason']} "
            summary = (
                prefix
                + (
                f"Aku belum menemukan payroll untuk periode {requested_period}, "
                f"jadi aku belum bisa memastikan kondisi gaji pada periode itu. "
                f"Payroll terbaru yang tersedia adalah periode {latest_period} dengan "
                f"net pay {_format_rupiah(latest['net_pay'])}, gross salary "
                f"{_format_rupiah(latest['gross_salary'])}, dan status pembayaran "
                f"{latest['payment_status']}."
                )
            )
            if wants_delta_explanation:
                difference_summary = _summarize_payroll_difference(
                    latest,
                    _find_previous_payroll_record(reference_records, latest),
                )
                if difference_summary:
                    summary += f" {difference_summary}"
            return summary
        return "Aku tidak menemukan data payroll yang sesuai di session karyawan ini."

    latest = records[0]
    period_label = f"{MONTH_NAMES_ID[latest['month']]} {latest['year']}"
    summary = (
        f"Payroll terbaru yang ditemukan adalah periode {period_label} dengan net pay "
        f"{_format_rupiah(latest['net_pay'])}, gross salary {_format_rupiah(latest['gross_salary'])}, "
        f"dan status pembayaran {latest['payment_status']}."
    )
    if wants_delta_explanation:
        difference_summary = _summarize_payroll_difference(
            latest,
            _find_previous_payroll_record(reference_records, latest),
        )
        if difference_summary:
            summary += f" {difference_summary}"
    return summary


def _summarize_attendance(
    records: list[dict[str, Any]],
    *,
    wants_average_check_in: bool = False,
    retrieval_assessment: dict[str, Any] | None = None,
) -> str:
    if not records:
        if retrieval_assessment:
            return (
                f"{retrieval_assessment['reason']} "
                "Aku tidak menemukan catatan kehadiran yang relevan untuk karyawan ini."
            )
        return "Aku tidak menemukan catatan kehadiran yang relevan untuk karyawan ini."

    if wants_average_check_in:
        check_in_minutes = [
            minutes
            for minutes in (_time_to_minutes(record.get("check_in")) for record in records)
            if minutes is not None
        ]
        if check_in_minutes:
            average_minutes = round(sum(check_in_minutes) / len(check_in_minutes))
            attendance_dates = sorted(
                record["attendance_date"]
                for record in records
                if isinstance(record.get("attendance_date"), str)
            )
            period_detail = ""
            if attendance_dates:
                period_detail = (
                    f" pada periode {attendance_dates[0]} sampai {attendance_dates[-1]}"
                )
            summary = (
                f"Berdasarkan {len(check_in_minutes)} catatan check-in{period_detail}, "
                f"rata-rata jam masuk kamu adalah {_format_minutes_as_time(average_minutes)} WIB."
            )
            if retrieval_assessment and retrieval_assessment.get("status") == "partial":
                return f"{retrieval_assessment['reason']} {summary}"
            return summary

    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1

    latest = records[0]
    breakdown = ", ".join(
        f"{count} {status}" for status, count in sorted(status_counts.items())
    )
    summary = (
        f"Dari {len(records)} catatan kehadiran yang dicek, ringkasannya adalah {breakdown}. "
        f"Catatan terbaru bertanggal {_format_date(date.fromisoformat(latest['attendance_date']))} "
        f"dengan status {latest['status']}."
    )
    if retrieval_assessment and retrieval_assessment.get("status") == "partial":
        return f"{retrieval_assessment['reason']} {summary}"
    return summary


def _summarize_time_off(snapshot: dict[str, Any]) -> str:
    balances = snapshot["balances"]
    requests = snapshot["requests"]
    if not balances and not requests:
        return "Aku tidak menemukan saldo atau riwayat pengajuan cuti untuk tahun yang diminta."

    parts: list[str] = []
    if balances:
        first_balance = balances[0]
        parts.append(
            f"Saldo cuti {snapshot['year']} untuk {first_balance['leave_type']} tersisa "
            f"{first_balance['remaining_days']} hari dari total {first_balance['total_days']} hari."
        )
    if requests:
        latest_request = requests[0]
        parts.append(
            f"Pengajuan cuti terbaru berstatus {latest_request['status']} untuk periode "
            f"{_format_date(date.fromisoformat(latest_request['start_date']))}."
        )
    return " ".join(parts)


async def run_hr_data_agent(
    db: AsyncSession,
    session: SessionContext,
    message: str,
    primary_intent: ConversationIntent,
    secondary_intents: list[ConversationIntent] | None = None,
    *,
    conversation_history: list[dict[str, str]] | None = None,
) -> HRDataAgentResult:
    secondary_intents = secondary_intents or []
    current_now = datetime.now(UTC)
    contextual_message, inherited_user_message = _build_contextual_message(
        message,
        conversation_history,
    )
    explicit_month = _extract_month(message)
    explicit_year = _extract_year(message)
    relative_month, relative_year = _resolve_relative_period(message, now=current_now)
    inherited_month = (
        _extract_month(inherited_user_message) if inherited_user_message else None
    )
    inherited_year = (
        _extract_year(inherited_user_message) if inherited_user_message else None
    )
    inherited_relative_month, inherited_relative_year = (
        _resolve_relative_period(inherited_user_message, now=current_now)
        if inherited_user_message
        else (None, None)
    )
    wants_average_check_in = _wants_average_check_in_with_context(
        message,
        contextual_message,
        inherited_user_message,
    )
    wants_payroll_delta_explanation = _wants_payroll_delta_explanation_with_context(
        message,
        contextual_message,
        inherited_user_message,
    )
    wants_latest_relevant_period = _wants_latest_relevant_period(message)
    rolling_window_days = 30 if _wants_rolling_30_day_window(message) else None

    month = explicit_month or relative_month or inherited_month or inherited_relative_month
    current_year = current_now.year
    year = (
        explicit_year
        or relative_year
        or inherited_year
        or inherited_relative_year
        or current_year
    )
    payroll_year_filter = (
        explicit_year
        or relative_year
        or inherited_year
        or inherited_relative_year
        or (current_year if month is not None else None)
    )
    attendance_year_filter = (
        explicit_year
        or relative_year
        or inherited_year
        or inherited_relative_year
        or (current_year if month is not None else None)
    )
    topics = _resolve_topics(contextual_message, primary_intent, secondary_intents)

    summary_parts: list[str] = []
    evidence: list[EvidenceItem] = []
    records: dict[str, Any] = {}
    retrieval_assessment: dict[str, Any] = {}

    if "profile" in topics:
        profile = await _get_employee_profile(db, session)
        if profile is not None:
            records["profile"] = profile
            summary_parts.append(_summarize_profile(profile))
            evidence.append(
                EvidenceItem(
                    source_type="hr_data",
                    title="Employee profile",
                    snippet=(
                        f"{profile['name']} | {profile['position']} | "
                        f"{profile['department_name'] or '-'}"
                    ),
                    metadata={
                        "employee_id": profile["employee_id"],
                        "employment_status": profile["employment_status"],
                    },
                )
            )

    if "payroll" in topics:
        payroll_records = await _get_payroll_records(
            db,
            session,
            month,
            payroll_year_filter,
        )
        payroll_reference_records: list[dict[str, Any]] = payroll_records
        if wants_payroll_delta_explanation or (
            not payroll_records and month is not None and payroll_year_filter is not None
        ):
            payroll_reference_records = await _get_payroll_records(
                db,
                session,
                None,
                None,
            )
        records["payroll"] = payroll_records
        if payroll_reference_records and payroll_reference_records is not payroll_records:
            records["payroll_reference"] = payroll_reference_records
        requested_current_period = (
            month == current_now.month and payroll_year_filter == current_now.year
        )
        if payroll_records:
            payroll_assessment = _build_retrieval_assessment(
                "enough",
                "Data payroll yang dibutuhkan tersedia dengan cukup jelas.",
                requested_period_found=True,
                requested_month=month,
                requested_year=payroll_year_filter,
            )
        elif payroll_reference_records:
            if requested_current_period and current_now.day <= 5:
                payroll_assessment = _build_retrieval_assessment(
                    "partial",
                    "Periode bulan ini masih sangat awal, jadi payroll lengkap biasanya belum tersedia. Aku memakai payroll lengkap terakhir sebagai konteks aman.",
                    requested_period_found=False,
                    fallback_mode="last_complete_period",
                    fallback_period_label=_format_period_label(
                        payroll_reference_records[0].get("month"),
                        payroll_reference_records[0].get("year"),
                    ),
                    requested_month=month,
                    requested_year=payroll_year_filter,
                )
            else:
                payroll_assessment = _build_retrieval_assessment(
                    "partial",
                    "Payroll untuk periode yang diminta belum tersedia, jadi jawaban ini memakai payroll terbaru yang tersedia sebagai konteks.",
                    requested_period_found=False,
                    fallback_mode="latest_available",
                    fallback_period_label=_format_period_label(
                        payroll_reference_records[0].get("month"),
                        payroll_reference_records[0].get("year"),
                    ),
                    requested_month=month,
                    requested_year=payroll_year_filter,
                )
        else:
            payroll_assessment = _build_retrieval_assessment(
                "weak",
                "Data payroll yang tersedia belum cukup untuk menjawab permintaan ini dengan aman.",
                requested_period_found=False,
                requested_month=month,
                requested_year=payroll_year_filter,
                asked_latest_relevant=wants_latest_relevant_period,
            )
        retrieval_assessment["payroll"] = payroll_assessment
        summary_parts.append(
            _summarize_payroll(
                payroll_records,
                requested_month=month,
                requested_year=payroll_year_filter,
                latest_reference_records=payroll_reference_records,
                wants_delta_explanation=wants_payroll_delta_explanation,
                retrieval_assessment=payroll_assessment,
            )
        )
        payroll_evidence_source = payroll_records or payroll_reference_records
        if payroll_evidence_source:
            latest = payroll_evidence_source[0]
            title = "Payroll record" if payroll_records else "Latest available payroll"
            evidence.append(
                EvidenceItem(
                    source_type="hr_data",
                    title=title,
                    snippet=(
                        f"{MONTH_NAMES_ID[latest['month']]} {latest['year']} | "
                        f"net pay {_format_rupiah(latest['net_pay'])}"
                    ),
                    metadata={
                        "month": latest["month"],
                        "year": latest["year"],
                        "payment_status": latest["payment_status"],
                        "requested_month": month,
                        "requested_year": payroll_year_filter,
                        "requested_period_found": bool(payroll_records),
                        "retrieval_status": payroll_assessment["status"],
                    },
                )
            )

    if "attendance" in topics:
        attendance_date_from = None
        attendance_date_to = None
        if rolling_window_days is not None:
            attendance_date_to = current_now.date()
            attendance_date_from = attendance_date_to - timedelta(days=rolling_window_days - 1)
        attendance_records = await _get_attendance_records(
            db,
            session,
            None if rolling_window_days is not None else month,
            None if rolling_window_days is not None else attendance_year_filter,
            date_from=attendance_date_from,
            date_to=attendance_date_to,
            limit=rolling_window_days or None,
        )
        attendance_assessment: dict[str, Any]
        if not attendance_records:
            attendance_assessment = _build_retrieval_assessment(
                "weak",
                "Catatan kehadiran untuk periode yang diminta belum cukup tersedia.",
                requested_month=month,
                requested_year=attendance_year_filter,
                rolling_window_days=rolling_window_days,
            )
        elif rolling_window_days is not None:
            if len(attendance_records) >= 10:
                attendance_assessment = _build_retrieval_assessment(
                    "enough",
                    "Catatan rolling period yang tersedia cukup untuk dijadikan ringkasan awal.",
                    rolling_window_days=rolling_window_days,
                    record_count=len(attendance_records),
                )
            else:
                attendance_assessment = _build_retrieval_assessment(
                    "partial",
                    "Catatan untuk rolling period ini masih terbatas, jadi ringkasannya masih bersifat awal.",
                    rolling_window_days=rolling_window_days,
                    record_count=len(attendance_records),
                )
        elif (
            wants_average_check_in
            and month == current_now.month
            and attendance_year_filter == current_now.year
            and current_now.day <= 5
            and len(attendance_records) < 3
        ):
            current_period_records = list(attendance_records)
            fallback_month, fallback_year = _previous_month_year(
                current_now.month,
                current_now.year,
            )
            fallback_records = await _get_attendance_records(
                db,
                session,
                fallback_month,
                fallback_year,
            )
            if fallback_records:
                records["attendance_requested_period"] = current_period_records
                records["attendance_fallback"] = fallback_records
                attendance_records = fallback_records
                attendance_assessment = _build_retrieval_assessment(
                    "partial",
                    (
                        "Periode bulan ini masih sangat awal dan catatan check-in belum cukup stabil. "
                        f"Aku memakai periode lengkap terakhir {_format_period_label(fallback_month, fallback_year)} sebagai konteks utama."
                    ),
                    requested_month=month,
                    requested_year=attendance_year_filter,
                    fallback_mode="last_complete_period",
                    fallback_period_label=_format_period_label(fallback_month, fallback_year),
                    original_record_count=len(current_period_records),
                    record_count=len(attendance_records),
                )
            else:
                attendance_assessment = _build_retrieval_assessment(
                    "partial",
                    "Periode bulan ini masih sangat awal dan catatan check-in yang tersedia belum cukup stabil.",
                    requested_month=month,
                    requested_year=attendance_year_filter,
                    record_count=len(attendance_records),
                )
        elif wants_average_check_in and len(attendance_records) < 3:
            attendance_assessment = _build_retrieval_assessment(
                "partial",
                "Jumlah catatan check-in yang tersedia masih terbatas untuk menghitung rata-rata yang stabil.",
                requested_month=month,
                requested_year=attendance_year_filter,
                record_count=len(attendance_records),
            )
        else:
            attendance_assessment = _build_retrieval_assessment(
                "enough",
                "Catatan kehadiran yang tersedia cukup untuk menjawab pertanyaan ini.",
                requested_month=month,
                requested_year=attendance_year_filter,
                rolling_window_days=rolling_window_days,
                record_count=len(attendance_records),
            )
        records["attendance"] = attendance_records
        retrieval_assessment["attendance"] = attendance_assessment
        summary_parts.append(
            _summarize_attendance(
                attendance_records,
                wants_average_check_in=wants_average_check_in,
                retrieval_assessment=attendance_assessment,
            )
        )
        if attendance_records:
            latest = attendance_records[0]
            evidence.append(
                EvidenceItem(
                    source_type="hr_data",
                    title="Attendance snapshot",
                    snippet=(
                        f"{latest['attendance_date']} | {latest['status']} | "
                        f"check-in {latest['check_in'] or '-'}"
                    ),
                    metadata={
                        "record_count": len(attendance_records),
                        "latest_status": latest["status"],
                        "retrieval_status": attendance_assessment["status"],
                    },
                )
            )

    if "time_off" in topics:
        time_off_snapshot = await _get_time_off_snapshot(db, session, year)
        records["time_off"] = time_off_snapshot
        summary_parts.append(_summarize_time_off(time_off_snapshot))
        if time_off_snapshot["balances"]:
            balance = time_off_snapshot["balances"][0]
            evidence.append(
                EvidenceItem(
                    source_type="hr_data",
                    title="Time-off balance",
                    snippet=(
                        f"{balance['leave_type']} {balance['year']} | "
                        f"sisa {balance['remaining_days']} hari"
                    ),
                    metadata={
                        "leave_type": balance["leave_type"],
                        "remaining_days": balance["remaining_days"],
                    },
                )
            )

    if not summary_parts:
        summary_parts.append(
            "Aku belum menemukan kebutuhan data personal yang cukup jelas dari pesan ini."
        )

    if retrieval_assessment:
        records["retrieval_assessment"] = retrieval_assessment

    return HRDataAgentResult(
        topics=topics,
        summary=" ".join(summary_parts),
        records=records,
        evidence=evidence,
    )
