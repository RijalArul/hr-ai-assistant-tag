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
) -> list[dict[str, Any]]:
    cache = get_cache("attendance_records")
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
        filters.append("EXTRACT(MONTH FROM a.attendance_date) = :month")
        params["month"] = month
    if year is not None:
        filters.append("EXTRACT(YEAR FROM a.attendance_date) = :year")
        params["year"] = year

    limit = 31 if month is not None and year is not None else 7
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
            LIMIT {limit}
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


def _summarize_payroll(records: list[dict[str, Any]]) -> str:
    if not records:
        return "Aku tidak menemukan data payroll yang sesuai di session karyawan ini."

    latest = records[0]
    period_label = f"{MONTH_NAMES_ID[latest['month']]} {latest['year']}"
    return (
        f"Payroll terbaru yang ditemukan adalah periode {period_label} dengan net pay "
        f"{_format_rupiah(latest['net_pay'])}, gross salary {_format_rupiah(latest['gross_salary'])}, "
        f"dan status pembayaran {latest['payment_status']}."
    )


def _summarize_attendance(
    records: list[dict[str, Any]],
    *,
    wants_average_check_in: bool = False,
) -> str:
    if not records:
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
            return (
                f"Berdasarkan {len(check_in_minutes)} catatan check-in{period_detail}, "
                f"rata-rata jam masuk kamu adalah {_format_minutes_as_time(average_minutes)} WIB."
            )

    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1

    latest = records[0]
    breakdown = ", ".join(
        f"{count} {status}" for status, count in sorted(status_counts.items())
    )
    return (
        f"Dari {len(records)} catatan kehadiran yang dicek, ringkasannya adalah {breakdown}. "
        f"Catatan terbaru bertanggal {_format_date(date.fromisoformat(latest['attendance_date']))} "
        f"dengan status {latest['status']}."
    )


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
) -> HRDataAgentResult:
    secondary_intents = secondary_intents or []
    current_now = datetime.now(UTC)
    explicit_month = _extract_month(message)
    explicit_year = _extract_year(message)
    relative_month, relative_year = _resolve_relative_period(message, now=current_now)
    wants_average_check_in = _wants_average_check_in(message)

    month = explicit_month or relative_month
    current_year = current_now.year
    year = explicit_year or relative_year or current_year
    payroll_year_filter = explicit_year or relative_year or (current_year if month is not None else None)
    attendance_year_filter = explicit_year or relative_year or (current_year if month is not None else None)
    topics = _resolve_topics(message, primary_intent, secondary_intents)

    summary_parts: list[str] = []
    evidence: list[EvidenceItem] = []
    records: dict[str, Any] = {}

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
        records["payroll"] = payroll_records
        summary_parts.append(_summarize_payroll(payroll_records))
        if payroll_records:
            latest = payroll_records[0]
            evidence.append(
                EvidenceItem(
                    source_type="hr_data",
                    title="Payroll record",
                    snippet=(
                        f"{MONTH_NAMES_ID[latest['month']]} {latest['year']} | "
                        f"net pay {_format_rupiah(latest['net_pay'])}"
                    ),
                    metadata={
                        "month": latest["month"],
                        "year": latest["year"],
                        "payment_status": latest["payment_status"],
                    },
                )
            )

    if "attendance" in topics:
        attendance_records = await _get_attendance_records(
            db,
            session,
            month,
            attendance_year_filter,
        )
        records["attendance"] = attendance_records
        summary_parts.append(
            _summarize_attendance(
                attendance_records,
                wants_average_check_in=wants_average_check_in,
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

    return HRDataAgentResult(
        topics=topics,
        summary=" ".join(summary_parts),
        records=records,
        evidence=evidence,
    )
