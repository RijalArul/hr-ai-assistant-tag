from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext
from app.models import (
    ActionCreateRequest,
    ActionDeliveryResponse,
    ActionExecutionRequest,
    ActionExecutionResponse,
    ActionListResponse,
    ActionLogResponse,
    ActionResponse,
    ActionResultResponse,
    ActionUpdateRequest,
    RuleActionConfig,
    RuleCreateRequest,
    RuleListResponse,
    RuleResponse,
    RuleUpdateRequest,
    WebhookCreateRequest,
    WebhookListResponse,
    WebhookResponse,
    WebhookUpdateRequest,
)
from app.models.action_engine import ACTION_TYPE_TO_PAYLOAD_MODEL, DocumentGenerationPayload
from app.services.object_storage import upload_document_bytes
from shared import (
    ActionType,
    ActionStatus,
    DeliveryChannel,
    RuleTrigger,
    SensitivityLevel,
    WebhookEvent,
)

ACTION_SELECT = """
SELECT
    a.id,
    a.company_id,
    a.employee_id,
    a.conversation_id,
    a.rule_id,
    a.type::text AS type,
    a.title,
    a.summary,
    a.status::text AS status,
    a.priority::text AS priority,
    a.sensitivity::text AS sensitivity,
    a.delivery_channels::text[] AS delivery_channels,
    a.payload,
    a.execution_result,
    a.metadata,
    a.last_executed_at,
    a.created_at,
    a.updated_at
FROM actions a
"""

RULE_SELECT = """
SELECT
    r.id,
    r.company_id,
    r.name,
    r.description,
    r.trigger::text AS trigger,
    r.intent_key,
    r.sensitivity_threshold::text AS sensitivity_threshold,
    r.is_enabled,
    r.created_at,
    r.updated_at
FROM rules r
"""

RULE_ACTION_SELECT = """
SELECT
    ra.rule_id,
    ra.action_type::text AS action_type,
    ra.title_template,
    ra.summary_template,
    ra.priority::text AS priority,
    ra.delivery_channels::text[] AS delivery_channels,
    ra.payload_template
FROM rule_actions ra
"""

WEBHOOK_SELECT = """
SELECT
    w.id,
    w.company_id,
    w.name,
    w.target_url,
    w.subscribed_events::text[] AS subscribed_events,
    w.secret,
    w.is_active,
    w.created_at,
    w.updated_at
FROM webhooks w
"""

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

PAYSLIP_DOCUMENT_TYPES = {"salary_slip", "payslip"}
SENSITIVITY_RANK = {
    SensitivityLevel.LOW.value: 0,
    SensitivityLevel.MEDIUM.value: 1,
    SensitivityLevel.HIGH.value: 2,
}


class _SafeFormatDict(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


def _json_dumps(value: object) -> str:
    return json.dumps(value, default=str)


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

    if any(phrase in lowered for phrase in ["bulan lalu", "last month", "bulan kemarin"]):
        previous_month = now.replace(day=1) - timedelta(days=1)
        return previous_month.month, previous_month.year

    if any(phrase in lowered for phrase in ["tahun ini", "this year"]):
        return None, now.year

    if any(phrase in lowered for phrase in ["tahun lalu", "last year"]):
        return None, now.year - 1

    return None, None


def _format_rupiah(value: object) -> str:
    if value is None:
        return "-"
    amount = int(float(value))
    return f"Rp{amount:,}".replace(",", ".")


def _format_date(value: date | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return f"{value.day} {MONTH_NAMES_ID[value.month]} {value.year}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "document"


def _render_template_value(value: object, context: dict[str, object]) -> object:
    if isinstance(value, str):
        return value.format_map(_SafeFormatDict(context))
    if isinstance(value, list):
        return [_render_template_value(item, context) for item in value]
    if isinstance(value, dict):
        return {
            key: _render_template_value(item, context)
            for key, item in value.items()
        }
    return value


def _sensitivity_within_threshold(
    actual_sensitivity: str,
    threshold: str | None,
) -> bool:
    if threshold is None:
        return True
    return SENSITIVITY_RANK[actual_sensitivity] <= SENSITIVITY_RANK[threshold]


def _document_period_label(month: int | None, year: int | None) -> str | None:
    if month is not None and year is not None:
        return f"{MONTH_NAMES_ID[month]} {year}"
    if year is not None:
        return str(year)
    return None


def _build_simple_pdf(lines: list[str]) -> bytes:
    def escape_pdf_text(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )

    commands = [
        "BT",
        "/F1 12 Tf",
        "50 790 Td",
        "16 TL",
    ]
    for index, line in enumerate(lines):
        if index > 0:
            commands.append("T*")
        commands.append(f"({escape_pdf_text(line)}) Tj")
    commands.append("ET")

    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        ),
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        (
            f"5 0 obj << /Length {len(stream)} >> stream\n".encode("ascii")
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )
    return bytes(pdf)


def _sanitize_delivery_channels(
    sensitivity: str,
    delivery_channels: Sequence[str] | None,
) -> list[str]:
    if sensitivity != SensitivityLevel.LOW.value:
        return [DeliveryChannel.MANUAL_REVIEW.value]

    if not delivery_channels:
        return [DeliveryChannel.IN_APP.value]

    return _dedupe_preserve_order(list(delivery_channels))


def _action_scope_clause(alias: str, session: SessionContext) -> tuple[str, dict[str, str]]:
    if session.role == "employee":
        return f" AND {alias}.employee_id = :session_employee_id", {
            "session_employee_id": session.employee_id,
        }
    if session.role == "hr_admin":
        return "", {}
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to access this resource.",
    )


def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def build_webhook_signature(secret: str, raw_body: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        raw_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _action_from_row(row: dict) -> ActionResponse:
    data = dict(row)
    data.pop("rule_id", None)
    return ActionResponse.model_validate(data)


def _action_log_from_row(row: dict) -> ActionLogResponse:
    return ActionLogResponse.model_validate(dict(row))


def _action_delivery_from_row(row: dict) -> ActionDeliveryResponse:
    return ActionDeliveryResponse.model_validate(dict(row))


def _rule_action_from_row(row: dict) -> RuleActionConfig:
    return RuleActionConfig.model_validate(dict(row))


def _rule_from_rows(rule_row: dict, action_rows: list[dict]) -> RuleResponse:
    data = dict(rule_row)
    data["actions"] = [_rule_action_from_row(row) for row in action_rows]
    return RuleResponse.model_validate(data)


def _webhook_from_row(row: dict) -> WebhookResponse:
    data = dict(row)
    secret = data.pop("secret")
    data["secret_preview"] = _mask_secret(secret)
    return WebhookResponse.model_validate(data)


async def _rollback_and_raise_conflict(
    db: AsyncSession,
    exc: IntegrityError,
    *,
    constraint_name: str,
    detail: str,
) -> None:
    await db.rollback()
    if constraint_name in str(exc.orig):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc
    raise exc


async def _get_action_or_404(
    db: AsyncSession,
    action_id: UUID,
    session: SessionContext,
) -> ActionResponse:
    scope_clause, scope_params = _action_scope_clause("a", session)
    result = await db.execute(
        text(
            f"""
            {ACTION_SELECT}
            WHERE a.id = :action_id
              AND a.company_id = :company_id
              {scope_clause}
            """
        ),
        {
            "action_id": str(action_id),
            "company_id": session.company_id,
            **scope_params,
        },
    )
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action not found.",
        )

    return _action_from_row(dict(row))


async def _get_rule_or_404(
    db: AsyncSession,
    rule_id: UUID,
    company_id: str,
) -> RuleResponse:
    rule_result = await db.execute(
        text(
            f"""
            {RULE_SELECT}
            WHERE r.id = :rule_id
              AND r.company_id = :company_id
            """
        ),
        {
            "rule_id": str(rule_id),
            "company_id": company_id,
        },
    )
    rule_row = rule_result.mappings().first()

    if rule_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found.",
        )

    action_result = await db.execute(
        text(
            f"""
            {RULE_ACTION_SELECT}
            WHERE ra.rule_id = :rule_id
            ORDER BY ra.created_at ASC
            """
        ),
        {"rule_id": str(rule_id)},
    )
    action_rows = [dict(row) for row in action_result.mappings().all()]
    return _rule_from_rows(dict(rule_row), action_rows)


async def _get_webhook_or_404(
    db: AsyncSession,
    webhook_id: UUID,
    company_id: str,
) -> WebhookResponse:
    result = await db.execute(
        text(
            f"""
            {WEBHOOK_SELECT}
            WHERE w.id = :webhook_id
              AND w.company_id = :company_id
            """
        ),
        {
            "webhook_id": str(webhook_id),
            "company_id": company_id,
        },
    )
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found.",
        )

    return _webhook_from_row(dict(row))


async def _insert_action_log(
    db: AsyncSession,
    *,
    action_id: str,
    company_id: str,
    event_name: str,
    action_status: str,
    message: str | None,
    metadata: dict | None = None,
) -> ActionLogResponse:
    result = await db.execute(
        text(
            """
            INSERT INTO action_logs (
                action_id,
                company_id,
                event_name,
                status,
                message,
                metadata
            )
            VALUES (
                CAST(:action_id AS uuid),
                CAST(:company_id AS uuid),
                :event_name,
                CAST(:action_status AS action_status_enum),
                :message,
                CAST(:metadata AS jsonb)
            )
            RETURNING
                id,
                action_id,
                event_name,
                status::text AS status,
                message,
                metadata,
                created_at
            """
        ),
        {
            "action_id": action_id,
            "company_id": company_id,
            "event_name": event_name,
            "action_status": action_status,
            "message": message,
            "metadata": _json_dumps(metadata or {}),
        },
    )
    row = result.mappings().one()
    return _action_log_from_row(dict(row))


async def _insert_action_delivery(
    db: AsyncSession,
    *,
    action_id: str,
    company_id: str,
    channel: str,
    target_reference: str | None,
    payload: dict | None = None,
) -> ActionDeliveryResponse:
    result = await db.execute(
        text(
            """
            INSERT INTO action_deliveries (
                action_id,
                company_id,
                channel,
                delivery_status,
                target_reference,
                payload
            )
            VALUES (
                CAST(:action_id AS uuid),
                CAST(:company_id AS uuid),
                CAST(:channel AS delivery_channel_enum),
                :delivery_status,
                :target_reference,
                CAST(:payload AS jsonb)
            )
            RETURNING
                id,
                action_id,
                channel::text AS channel,
                delivery_status,
                target_reference,
                payload,
                created_at
            """
        ),
        {
            "action_id": action_id,
            "company_id": company_id,
            "channel": channel,
            "delivery_status": "queued",
            "target_reference": target_reference,
            "payload": _json_dumps(payload or {}),
        },
    )
    row = result.mappings().one()
    return _action_delivery_from_row(dict(row))


async def _queue_webhook_deliveries(
    db: AsyncSession,
    *,
    action_id: str,
    company_id: str,
    payload: dict,
) -> int:
    subscribed_webhooks = await db.execute(
        text(
            """
            SELECT id
            FROM webhooks
            WHERE company_id = CAST(:company_id AS uuid)
              AND is_active = true
              AND CAST(:event_name AS webhook_event_enum) = ANY(subscribed_events)
            """
        ),
        {
            "company_id": company_id,
            "event_name": WebhookEvent.ACTION_DELIVERY_REQUESTED.value,
        },
    )
    webhook_ids = [str(row["id"]) for row in subscribed_webhooks.mappings().all()]

    for webhook_id in webhook_ids:
        await db.execute(
            text(
                """
                INSERT INTO webhook_deliveries (
                    webhook_id,
                    action_id,
                    event_name,
                    delivery_status,
                    response_body
                )
                VALUES (
                    CAST(:webhook_id AS uuid),
                    CAST(:action_id AS uuid),
                    CAST(:event_name AS webhook_event_enum),
                    :delivery_status,
                    :response_body
                )
                """
            ),
            {
                "webhook_id": webhook_id,
                "action_id": action_id,
                "event_name": WebhookEvent.ACTION_DELIVERY_REQUESTED.value,
                "delivery_status": "queued",
                "response_body": _json_dumps(payload),
            },
        )

    return len(webhook_ids)


async def _queue_action_deliveries(
    db: AsyncSession,
    *,
    action: ActionResponse,
    executor_note: str | None,
) -> tuple[list[ActionDeliveryResponse], int]:
    delivery_requests: list[ActionDeliveryResponse] = []
    webhook_deliveries_queued = 0

    for channel in action.delivery_channels:
        delivery_payload = {
            "action_id": str(action.id),
            "action_type": action.type.value,
            "status": action.status.value,
            "title": action.title,
            "employee_id": str(action.employee_id),
            "executor_note": executor_note,
        }
        document = None
        if action.execution_result is not None:
            document = action.execution_result.get("document")
        if isinstance(document, dict):
            delivery_payload["document"] = {
                key: document.get(key)
                for key in [
                    "document_type",
                    "file_name",
                    "mime_type",
                    "period",
                    "byte_size",
                    "object_key",
                    "download_url",
                ]
                if document.get(key) is not None
            }
        target_reference = {
            DeliveryChannel.EMAIL: f"employee:{action.employee_id}",
            DeliveryChannel.IN_APP: f"employee:{action.employee_id}",
            DeliveryChannel.MANUAL_REVIEW: "hr_admin_review_queue",
            DeliveryChannel.WEBHOOK: "registered_company_webhooks",
        }[channel]

        delivery_request = await _insert_action_delivery(
            db,
            action_id=str(action.id),
            company_id=str(action.company_id),
            channel=channel.value,
            target_reference=target_reference,
            payload=delivery_payload,
        )
        delivery_requests.append(delivery_request)

        if channel == DeliveryChannel.WEBHOOK:
            webhook_deliveries_queued += await _queue_webhook_deliveries(
                db,
                action_id=str(action.id),
                company_id=str(action.company_id),
                payload=delivery_payload,
            )

    return delivery_requests, webhook_deliveries_queued


async def _get_latest_payroll_period(
    db: AsyncSession,
    session: SessionContext,
    *,
    year: int | None = None,
) -> tuple[int, int] | None:
    filters = [
        "p.employee_id = CAST(:employee_id AS uuid)",
        "e.company_id = CAST(:company_id AS uuid)",
    ]
    params: dict[str, object] = {
        "employee_id": session.employee_id,
        "company_id": session.company_id,
    }

    if year is not None:
        filters.append("p.year = :year")
        params["year"] = year

    result = await db.execute(
        text(
            f"""
            SELECT p.month, p.year
            FROM payroll p
            INNER JOIN employees e
              ON e.id = p.employee_id
            WHERE {" AND ".join(filters)}
            ORDER BY p.year DESC, p.month DESC
            LIMIT 1
            """
        ),
        params,
    )
    row = result.mappings().first()
    if row is None:
        return None
    return int(row["month"]), int(row["year"])


async def _resolve_document_parameters(
    db: AsyncSession,
    session: SessionContext,
    *,
    message: str,
    document_type: str | None,
) -> dict[str, int]:
    if document_type not in PAYSLIP_DOCUMENT_TYPES:
        return {}

    current_now = datetime.now(UTC)
    explicit_month = _extract_month(message)
    explicit_year = _extract_year(message)
    relative_month, relative_year = _resolve_relative_period(message, now=current_now)
    month = explicit_month or relative_month
    year = explicit_year or relative_year or (current_now.year if month is not None else None)

    if month is not None and year is not None:
        return {"month": month, "year": year}

    latest_period = await _get_latest_payroll_period(db, session, year=year)
    if latest_period is None:
        return {}

    resolved_month, resolved_year = latest_period
    return {"month": resolved_month, "year": resolved_year}


async def _load_matching_rules(
    db: AsyncSession,
    *,
    company_id: str,
    trigger: RuleTrigger,
    intent_key: str,
    actual_sensitivity: str,
) -> list[RuleResponse]:
    result = await db.execute(
        text(
            f"""
            {RULE_SELECT}
            WHERE r.company_id = :company_id
              AND r.is_enabled = true
              AND r.trigger = CAST(:trigger AS rule_trigger_enum)
              AND r.intent_key = :intent_key
            ORDER BY r.created_at ASC
            """
        ),
        {
            "company_id": company_id,
            "trigger": trigger.value,
            "intent_key": intent_key,
        },
    )
    rule_rows = [dict(row) for row in result.mappings().all()]
    matched_rules: list[RuleResponse] = []

    for row in rule_rows:
        if not _sensitivity_within_threshold(
            actual_sensitivity,
            row.get("sensitivity_threshold"),
        ):
            continue
        action_result = await db.execute(
            text(
                f"""
                {RULE_ACTION_SELECT}
                WHERE ra.rule_id = :rule_id
                ORDER BY ra.created_at ASC
                """
            ),
            {"rule_id": str(row["id"])},
        )
        action_rows = [dict(action_row) for action_row in action_result.mappings().all()]
        matched_rules.append(_rule_from_rows(row, action_rows))

    return matched_rules


async def _get_existing_rule_action(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    company_id: str,
    employee_id: str,
    rule_id: UUID,
    action_type: ActionType,
    session: SessionContext,
) -> ActionResponse | None:
    result = await db.execute(
        text(
            """
            SELECT id
            FROM actions
            WHERE company_id = CAST(:company_id AS uuid)
              AND employee_id = CAST(:employee_id AS uuid)
              AND conversation_id = CAST(:conversation_id AS uuid)
              AND rule_id = CAST(:rule_id AS uuid)
              AND type = CAST(:action_type AS action_type_enum)
              AND status != CAST(:cancelled_status AS action_status_enum)
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "conversation_id": str(conversation_id),
            "rule_id": str(rule_id),
            "action_type": action_type.value,
            "cancelled_status": ActionStatus.CANCELLED.value,
        },
    )
    row = result.mappings().first()
    if row is None:
        return None
    return await _get_action_or_404(db, row["id"], session)


def _materialize_payload_template(
    action_config: RuleActionConfig,
    context: dict[str, object],
) -> dict[str, object]:
    payload_data = copy.deepcopy(action_config.payload_template)
    payload_data = _render_template_value(payload_data, context)
    if not isinstance(payload_data, dict):
        payload_data = {}

    if action_config.action_type == ActionType.DOCUMENT_GENERATION:
        parameters = payload_data.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        document_parameters = context.get("document_parameters")
        if isinstance(document_parameters, dict):
            parameters = {
                **parameters,
                **document_parameters,
            }
        payload_data["parameters"] = parameters

    return payload_data


def _materialize_action_title(
    title_template: str,
    *,
    action_type: ActionType,
    context: dict[str, object],
    payload_data: dict[str, object],
) -> str:
    title = str(_render_template_value(title_template, context))
    if (
        action_type == ActionType.DOCUMENT_GENERATION
        and payload_data.get("document_type") in PAYSLIP_DOCUMENT_TYPES
        and "{period_label}" not in title_template
    ):
        period_label = context.get("period_label")
        if isinstance(period_label, str) and period_label and period_label not in title:
            return f"{title} for {period_label}"
    return title


def _build_document_generation_result_from_row(
    row: dict[str, object],
    payload: DocumentGenerationPayload,
) -> dict[str, object]:
    month = int(row["month"])
    year = int(row["year"])
    period_label = _document_period_label(month, year) or f"{month}/{year}"
    employee_name = str(row["employee_name"])
    file_name = f"payslip-{year:04d}-{month:02d}-{_slugify(employee_name)}.pdf"
    preview_lines = [
        "HR.ai Payslip",
        f"Company: {row['company_name']}",
        f"Employee: {employee_name}",
        f"Position: {row['position']}",
        f"Department: {row.get('department_name') or '-'}",
        f"Period: {period_label}",
        f"Payment status: {row['payment_status']}",
        f"Payment date: {_format_date(row.get('payment_date'))}",
        f"Basic salary: {_format_rupiah(row.get('basic_salary'))}",
        f"Allowances: {_format_rupiah(row.get('allowances'))}",
        f"Gross salary: {_format_rupiah(row.get('gross_salary'))}",
        f"Deductions: {_format_rupiah(row.get('deductions'))}",
        f"BPJS Kesehatan: {_format_rupiah(row.get('bpjs_kesehatan'))}",
        f"BPJS Ketenagakerjaan: {_format_rupiah(row.get('bpjs_ketenagakerjaan'))}",
        f"PPH21: {_format_rupiah(row.get('pph21'))}",
        f"Net pay: {_format_rupiah(row.get('net_pay'))}",
    ]
    pdf_bytes = _build_simple_pdf(preview_lines)

    return {
        "file_name": file_name,
        "pdf_bytes": pdf_bytes,
        "document": {
            "document_type": payload.document_type,
            "template_key": payload.template_key,
            "file_name": file_name,
            "mime_type": "application/pdf",
            "byte_size": len(pdf_bytes),
            "period": {
                "month": month,
                "year": year,
                "label": period_label,
            },
            "preview_lines": preview_lines,
        },
        "document_data": {
            "company_name": row["company_name"],
            "employee_name": employee_name,
            "employee_email": row["employee_email"],
            "position": row["position"],
            "department_name": row.get("department_name"),
            "month": month,
            "year": year,
            "payment_status": row["payment_status"],
            "payment_date": str(row["payment_date"]) if row.get("payment_date") else None,
            "basic_salary": int(float(row["basic_salary"])),
            "allowances": int(float(row["allowances"])),
            "gross_salary": int(float(row["gross_salary"])),
            "deductions": int(float(row["deductions"])),
            "bpjs_kesehatan": int(float(row["bpjs_kesehatan"])),
            "bpjs_ketenagakerjaan": int(float(row["bpjs_ketenagakerjaan"])),
            "pph21": int(float(row["pph21"])),
            "net_pay": int(float(row["net_pay"])),
        },
    }


async def _build_document_generation_result(
    db: AsyncSession,
    *,
    action: ActionResponse,
    session: SessionContext,
) -> dict[str, object]:
    if not isinstance(action.payload, DocumentGenerationPayload):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action payload is not a document generation payload.",
        )

    payload = action.payload
    parameters = payload.parameters if isinstance(payload.parameters, dict) else {}
    month = parameters.get("month")
    year = parameters.get("year")

    filters = [
        "e.id = CAST(:employee_id AS uuid)",
        "e.company_id = CAST(:company_id AS uuid)",
    ]
    params: dict[str, object] = {
        "employee_id": session.employee_id,
        "company_id": session.company_id,
    }
    if month is not None:
        filters.append("p.month = :month")
        params["month"] = int(month)
    if year is not None:
        filters.append("p.year = :year")
        params["year"] = int(year)

    result = await db.execute(
        text(
            f"""
            SELECT
                c.name AS company_name,
                e.name AS employee_name,
                lower(e.email) AS employee_email,
                e.position,
                d.name AS department_name,
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
            INNER JOIN companies c
              ON c.id = e.company_id
            LEFT JOIN departments d
              ON d.id = e.department_id
            WHERE {" AND ".join(filters)}
            ORDER BY p.year DESC, p.month DESC
            LIMIT 1
            """
        ),
        params,
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll record not found for the requested document period.",
        )

    if payload.document_type in PAYSLIP_DOCUMENT_TYPES:
        rendered = _build_document_generation_result_from_row(dict(row), payload)
        pdf_bytes = rendered.pop("pdf_bytes")
        file_name = str(rendered.pop("file_name"))
        document = rendered["document"]
        period = document["period"]
        object_key = (
            f"companies/{session.company_id}/employees/{session.employee_id}/"
            f"documents/payslips/{period['year']}/{int(period['month']):02d}/{file_name}"
        )
        storage_result = await upload_document_bytes(
            object_key=object_key,
            content=pdf_bytes,
            content_type="application/pdf",
            metadata={
                "conversation_id": str(action.conversation_id),
                "employee_id": session.employee_id,
                "document_type": payload.document_type,
                "period_month": str(period["month"]),
                "period_year": str(period["year"]),
            },
        )
        if storage_result.object_key and storage_result.bucket:
            document.update(
                {
                    "storage_provider": "s3_compatible",
                    "bucket": storage_result.bucket,
                    "object_key": storage_result.object_key,
                    "download_url": storage_result.url,
                    "download_url_expires_at": storage_result.expires_at,
                    "etag": storage_result.etag,
                }
            )
        else:
            document.update(
                {
                    "storage_provider": "inline_fallback",
                    "storage_error": storage_result.fallback_reason,
                    "encoding": "base64",
                    "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                }
            )
        return rendered

    return {
        "document": {
            "document_type": payload.document_type,
            "template_key": payload.template_key,
            "parameters": parameters,
        }
    }


def should_auto_execute_action(action: ActionResponse) -> bool:
    if action.type != ActionType.DOCUMENT_GENERATION:
        return False
    if action.status not in {ActionStatus.PENDING, ActionStatus.READY}:
        return False
    if action.sensitivity != SensitivityLevel.LOW:
        return False
    if not isinstance(action.payload, DocumentGenerationPayload):
        return False
    return action.payload.document_type in PAYSLIP_DOCUMENT_TYPES


async def create_actions_from_rule_trigger(
    db: AsyncSession,
    *,
    session: SessionContext,
    conversation_id: UUID,
    trigger: RuleTrigger,
    intent_key: str,
    sensitivity: SensitivityLevel,
    message: str,
) -> list[ActionResponse]:
    matched_rules = await _load_matching_rules(
        db,
        company_id=session.company_id,
        trigger=trigger,
        intent_key=intent_key,
        actual_sensitivity=sensitivity.value,
    )
    created_actions: list[ActionResponse] = []

    for rule in matched_rules:
        for action_config in rule.actions:
            existing_action = await _get_existing_rule_action(
                db,
                conversation_id=conversation_id,
                company_id=session.company_id,
                employee_id=session.employee_id,
                rule_id=rule.id,
                action_type=action_config.action_type,
                session=session,
            )
            if existing_action is not None:
                created_actions.append(existing_action)
                continue

            payload_template = copy.deepcopy(action_config.payload_template)
            document_type = None
            if isinstance(payload_template, dict):
                raw_document_type = payload_template.get("document_type")
                if isinstance(raw_document_type, str):
                    document_type = raw_document_type

            document_parameters = await _resolve_document_parameters(
                db,
                session,
                message=message,
                document_type=document_type,
            )
            period_label = _document_period_label(
                document_parameters.get("month"),
                document_parameters.get("year"),
            )
            context = {
                "conversation_id": str(conversation_id),
                "intent_key": intent_key,
                "message": message,
                "document_parameters": document_parameters,
                "month": document_parameters.get("month"),
                "year": document_parameters.get("year"),
                "period_label": period_label,
            }
            payload_data = _materialize_payload_template(action_config, context)
            payload_model = ACTION_TYPE_TO_PAYLOAD_MODEL[action_config.action_type].model_validate(
                {
                    "type": action_config.action_type.value,
                    **payload_data,
                }
            )
            title = _materialize_action_title(
                action_config.title_template,
                action_type=action_config.action_type,
                context=context,
                payload_data=payload_data,
            )
            summary = action_config.summary_template
            if summary is not None:
                summary = str(_render_template_value(summary, context))
                if (
                    action_config.action_type == ActionType.DOCUMENT_GENERATION
                    and payload_data.get("document_type") in PAYSLIP_DOCUMENT_TYPES
                    and period_label
                    and "{period_label}" not in action_config.summary_template
                    and period_label not in summary
                ):
                    summary = f"{summary} Requested period: {period_label}."

            action = await create_action(
                db,
                session,
                ActionCreateRequest(
                    conversation_id=conversation_id,
                    title=title,
                    summary=summary,
                    priority=action_config.priority,
                    sensitivity=sensitivity,
                    delivery_channels=action_config.delivery_channels,
                    payload=payload_model,
                    metadata={
                        "automation": {
                            "trigger": trigger.value,
                            "intent_key": intent_key,
                        },
                        "source_message": message,
                        "document_parameters": document_parameters,
                    },
                ),
                rule_id=rule.id,
            )
            created_actions.append(action)

    return created_actions


async def create_action(
    db: AsyncSession,
    session: SessionContext,
    payload: ActionCreateRequest,
    *,
    rule_id: UUID | None = None,
) -> ActionResponse:
    delivery_channels = _sanitize_delivery_channels(
        payload.sensitivity.value,
        [channel.value for channel in payload.delivery_channels],
    )

    result = await db.execute(
        text(
            """
            INSERT INTO actions (
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
                metadata
            )
            VALUES (
                CAST(:company_id AS uuid),
                CAST(:employee_id AS uuid),
                CAST(:conversation_id AS uuid),
                CAST(:rule_id AS uuid),
                CAST(:action_type AS action_type_enum),
                :title,
                :summary,
                CAST(:action_status AS action_status_enum),
                CAST(:priority AS action_priority_enum),
                CAST(:sensitivity AS sensitivity_level_enum),
                CAST(:delivery_channels AS delivery_channel_enum[]),
                CAST(:payload AS jsonb),
                CAST(:metadata AS jsonb)
            )
            RETURNING id
            """
        ),
        {
            "company_id": session.company_id,
            "employee_id": session.employee_id,
            "conversation_id": str(payload.conversation_id),
            "rule_id": str(rule_id) if rule_id else None,
            "action_type": payload.payload.type,
            "title": payload.title,
            "summary": payload.summary,
            "action_status": ActionStatus.PENDING.value,
            "priority": payload.priority.value,
            "sensitivity": payload.sensitivity.value,
            "delivery_channels": delivery_channels,
            "payload": _json_dumps(payload.payload.model_dump(mode="json")),
            "metadata": _json_dumps(payload.metadata),
        },
    )
    action_id = result.scalar_one()

    await _insert_action_log(
        db,
        action_id=str(action_id),
        company_id=session.company_id,
        event_name="action.created",
        action_status=ActionStatus.PENDING.value,
        message="Action created.",
        metadata={"delivery_channels": delivery_channels},
    )
    await db.commit()

    return await _get_action_or_404(db, action_id, session)


async def list_actions(
    db: AsyncSession,
    session: SessionContext,
) -> ActionListResponse:
    scope_clause, scope_params = _action_scope_clause("a", session)
    result = await db.execute(
        text(
            f"""
            {ACTION_SELECT}
            WHERE a.company_id = :company_id
              {scope_clause}
            ORDER BY a.created_at DESC
            """
        ),
        {
            "company_id": session.company_id,
            **scope_params,
        },
    )
    rows = [dict(row) for row in result.mappings().all()]
    items = [_action_from_row(row) for row in rows]
    return ActionListResponse(items=items, total=len(items))


async def list_actions_for_conversation(
    db: AsyncSession,
    conversation_id: UUID,
    session: SessionContext,
) -> ActionListResponse:
    scope_clause, scope_params = _action_scope_clause("a", session)
    result = await db.execute(
        text(
            f"""
            {ACTION_SELECT}
            WHERE a.company_id = :company_id
              AND a.conversation_id = :conversation_id
              {scope_clause}
            ORDER BY a.created_at DESC
            """
        ),
        {
            "company_id": session.company_id,
            "conversation_id": str(conversation_id),
            **scope_params,
        },
    )
    rows = [dict(row) for row in result.mappings().all()]
    items = [_action_from_row(row) for row in rows]
    return ActionListResponse(items=items, total=len(items))


async def get_action(
    db: AsyncSession,
    action_id: UUID,
    session: SessionContext,
) -> ActionResponse:
    return await _get_action_or_404(db, action_id, session)


async def update_action(
    db: AsyncSession,
    action_id: UUID,
    payload: ActionUpdateRequest,
    session: SessionContext,
) -> ActionResponse:
    existing = await _get_action_or_404(db, action_id, session)

    if existing.status in {ActionStatus.COMPLETED, ActionStatus.FAILED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Terminal actions cannot be modified manually.",
        )

    values: dict[str, object] = {}
    set_clauses: list[str] = []

    if payload.title is not None:
        set_clauses.append("title = :title")
        values["title"] = payload.title

    if payload.summary is not None:
        set_clauses.append("summary = :summary")
        values["summary"] = payload.summary

    if payload.priority is not None:
        set_clauses.append("priority = CAST(:priority AS action_priority_enum)")
        values["priority"] = payload.priority.value

    if payload.status is not None:
        set_clauses.append("status = CAST(:action_status AS action_status_enum)")
        values["action_status"] = payload.status.value

    if payload.metadata is not None:
        set_clauses.append("metadata = CAST(:metadata AS jsonb)")
        values["metadata"] = _json_dumps(payload.metadata)

    if payload.sensitivity is not None or payload.delivery_channels is not None:
        sensitivity = (
            payload.sensitivity.value
            if payload.sensitivity is not None
            else existing.sensitivity.value
        )
        channels = (
            [channel.value for channel in payload.delivery_channels]
            if payload.delivery_channels is not None
            else [channel.value for channel in existing.delivery_channels]
        )
        sanitized_channels = _sanitize_delivery_channels(sensitivity, channels)
        set_clauses.append("sensitivity = CAST(:sensitivity AS sensitivity_level_enum)")
        set_clauses.append("delivery_channels = CAST(:delivery_channels AS delivery_channel_enum[])")
        values["sensitivity"] = sensitivity
        values["delivery_channels"] = sanitized_channels

    if not set_clauses:
        return existing

    await db.execute(
        text(
            f"""
            UPDATE actions
            SET {", ".join(set_clauses)}
            WHERE id = :action_id
              AND company_id = :company_id
            """
        ),
        {
            "action_id": str(action_id),
            "company_id": session.company_id,
            **values,
        },
    )
    refreshed = await _get_action_or_404(db, action_id, session)
    await _insert_action_log(
        db,
        action_id=str(action_id),
        company_id=session.company_id,
        event_name="action.updated",
        action_status=refreshed.status.value,
        message="Action updated.",
    )
    await db.commit()
    return refreshed


async def execute_action(
    db: AsyncSession,
    action_id: UUID,
    payload: ActionExecutionRequest,
    session: SessionContext,
) -> ActionExecutionResponse:
    existing = await _get_action_or_404(db, action_id, session)

    if existing.status == ActionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed actions cannot be executed twice.",
        )

    if existing.status == ActionStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancelled actions cannot be executed.",
        )

    requested_channels = (
        [channel.value for channel in payload.delivery_channels]
        if payload.delivery_channels is not None
        else [channel.value for channel in existing.delivery_channels]
    )
    sanitized_channels = _sanitize_delivery_channels(
        existing.sensitivity.value,
        requested_channels,
    )
    executed_at = datetime.now(UTC)
    execution_result: dict[str, object] = {
        "executed_at": executed_at.isoformat(),
        "delivery_channels": sanitized_channels,
        "delivery_requested": payload.trigger_delivery,
        "executor_note": payload.executor_note,
        "delivery_mode": (
            "manual_review_only"
            if existing.sensitivity != SensitivityLevel.LOW
            else "direct_delivery"
        ),
    }
    if existing.type == ActionType.DOCUMENT_GENERATION:
        execution_result.update(
            await _build_document_generation_result(
                db,
                action=existing,
                session=session,
            )
        )

    await db.execute(
        text(
            """
            UPDATE actions
            SET
                status = CAST(:action_status AS action_status_enum),
                delivery_channels = CAST(:delivery_channels AS delivery_channel_enum[]),
                execution_result = CAST(:execution_result AS jsonb),
                last_executed_at = :last_executed_at
            WHERE id = :action_id
              AND company_id = :company_id
            """
        ),
        {
            "action_id": str(action_id),
            "company_id": session.company_id,
            "action_status": ActionStatus.COMPLETED.value,
            "delivery_channels": sanitized_channels,
            "execution_result": _json_dumps(execution_result),
            "last_executed_at": executed_at,
        },
    )
    refreshed = await _get_action_or_404(db, action_id, session)
    execution_log = await _insert_action_log(
        db,
        action_id=str(action_id),
        company_id=session.company_id,
        event_name="action.executed",
        action_status=ActionStatus.COMPLETED.value,
        message="Action executed.",
        metadata=execution_result,
    )
    delivery_requests: list[ActionDeliveryResponse] = []
    webhook_deliveries_queued = 0

    if payload.trigger_delivery:
        delivery_requests, webhook_deliveries_queued = await _queue_action_deliveries(
            db,
            action=refreshed,
            executor_note=payload.executor_note,
        )
        await _insert_action_log(
            db,
            action_id=str(action_id),
            company_id=session.company_id,
            event_name=WebhookEvent.ACTION_DELIVERY_REQUESTED.value,
            action_status=ActionStatus.COMPLETED.value,
            message="Action delivery queued.",
            metadata={
                "delivery_channels": [channel.value for channel in refreshed.delivery_channels],
                "delivery_request_count": len(delivery_requests),
                "webhook_deliveries_queued": webhook_deliveries_queued,
            },
        )
    await db.commit()
    return ActionExecutionResponse(
        action=refreshed,
        delivery_channels=refreshed.delivery_channels,
        delivery_requested=payload.trigger_delivery,
        execution_log=execution_log,
        delivery_requests=delivery_requests,
        webhook_deliveries_queued=webhook_deliveries_queued,
    )


async def get_action_result(
    db: AsyncSession,
    action_id: UUID,
    session: SessionContext,
) -> ActionResultResponse:
    action = await _get_action_or_404(db, action_id, session)
    return ActionResultResponse(
        action_id=action.id,
        status=action.status,
        execution_result=action.execution_result,
        last_executed_at=action.last_executed_at,
    )


async def list_rules(
    db: AsyncSession,
    company_id: str,
) -> RuleListResponse:
    result = await db.execute(
        text(
            f"""
            {RULE_SELECT}
            WHERE r.company_id = :company_id
            ORDER BY r.created_at DESC
            """
        ),
        {"company_id": company_id},
    )
    rule_rows = [dict(row) for row in result.mappings().all()]
    items: list[RuleResponse] = []

    for row in rule_rows:
        items.append(await _get_rule_or_404(db, row["id"], company_id))

    return RuleListResponse(items=items, total=len(items))


async def get_rule(
    db: AsyncSession,
    rule_id: UUID,
    company_id: str,
) -> RuleResponse:
    return await _get_rule_or_404(db, rule_id, company_id)


async def create_rule(
    db: AsyncSession,
    company_id: str,
    payload: RuleCreateRequest,
) -> RuleResponse:
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO rules (
                    company_id,
                    name,
                    description,
                    trigger,
                    intent_key,
                    sensitivity_threshold,
                    is_enabled
                )
                VALUES (
                    CAST(:company_id AS uuid),
                    :name,
                    :description,
                    CAST(:trigger AS rule_trigger_enum),
                    :intent_key,
                    CAST(:sensitivity_threshold AS sensitivity_level_enum),
                    :is_enabled
                )
                RETURNING id
                """
            ),
            {
                "company_id": company_id,
                "name": payload.name,
                "description": payload.description,
                "trigger": payload.trigger.value,
                "intent_key": payload.intent_key,
                "sensitivity_threshold": (
                    payload.sensitivity_threshold.value
                    if payload.sensitivity_threshold is not None
                    else None
                ),
                "is_enabled": payload.is_enabled,
            },
        )
        rule_id = result.scalar_one()

        for action_config in payload.actions:
            await db.execute(
                text(
                    """
                    INSERT INTO rule_actions (
                        rule_id,
                        action_type,
                        title_template,
                        summary_template,
                        priority,
                        delivery_channels,
                        payload_template
                    )
                    VALUES (
                        CAST(:rule_id AS uuid),
                        CAST(:action_type AS action_type_enum),
                        :title_template,
                        :summary_template,
                        CAST(:priority AS action_priority_enum),
                        CAST(:delivery_channels AS delivery_channel_enum[]),
                        CAST(:payload_template AS jsonb)
                    )
                    """
                ),
                {
                    "rule_id": str(rule_id),
                    "action_type": action_config.action_type.value,
                    "title_template": action_config.title_template,
                    "summary_template": action_config.summary_template,
                    "priority": action_config.priority.value,
                    "delivery_channels": [channel.value for channel in action_config.delivery_channels],
                    "payload_template": _json_dumps(action_config.payload_template),
                },
            )

        await db.commit()
    except IntegrityError as exc:
        await _rollback_and_raise_conflict(
            db,
            exc,
            constraint_name="uq_rules_company_name",
            detail="A rule with the same name already exists in this company.",
        )
    return await _get_rule_or_404(db, rule_id, company_id)


async def update_rule(
    db: AsyncSession,
    rule_id: UUID,
    company_id: str,
    payload: RuleUpdateRequest,
) -> RuleResponse:
    await _get_rule_or_404(db, rule_id, company_id)

    set_clauses: list[str] = []
    params: dict[str, object] = {
        "rule_id": str(rule_id),
        "company_id": company_id,
    }

    if payload.name is not None:
        set_clauses.append("name = :name")
        params["name"] = payload.name

    if payload.description is not None:
        set_clauses.append("description = :description")
        params["description"] = payload.description

    if payload.trigger is not None:
        set_clauses.append("trigger = CAST(:trigger AS rule_trigger_enum)")
        params["trigger"] = payload.trigger.value

    if payload.intent_key is not None:
        set_clauses.append("intent_key = :intent_key")
        params["intent_key"] = payload.intent_key

    if payload.sensitivity_threshold is not None:
        set_clauses.append("sensitivity_threshold = CAST(:sensitivity_threshold AS sensitivity_level_enum)")
        params["sensitivity_threshold"] = payload.sensitivity_threshold.value

    if payload.is_enabled is not None:
        set_clauses.append("is_enabled = :is_enabled")
        params["is_enabled"] = payload.is_enabled

    try:
        if set_clauses:
            await db.execute(
                text(
                    """
                    UPDATE rules
                    SET {set_clauses}
                    WHERE id = :rule_id
                      AND company_id = :company_id
                    )
                    """.replace("{set_clauses}", ", ".join(set_clauses))
                ),
                params,
            )

        if payload.actions is not None:
            await db.execute(
                text(
                    """
                    DELETE FROM rule_actions
                    WHERE rule_id = :rule_id
                    """
                ),
                {"rule_id": str(rule_id)},
            )

            for action_config in payload.actions:
                await db.execute(
                    text(
                        """
                        INSERT INTO rule_actions (
                            rule_id,
                            action_type,
                            title_template,
                            summary_template,
                            priority,
                            delivery_channels,
                            payload_template
                        )
                        VALUES (
                            CAST(:rule_id AS uuid),
                            CAST(:action_type AS action_type_enum),
                            :title_template,
                            :summary_template,
                            CAST(:priority AS action_priority_enum),
                            CAST(:delivery_channels AS delivery_channel_enum[]),
                            CAST(:payload_template AS jsonb)
                        )
                        """
                    ),
                    {
                        "rule_id": str(rule_id),
                        "action_type": action_config.action_type.value,
                        "title_template": action_config.title_template,
                        "summary_template": action_config.summary_template,
                        "priority": action_config.priority.value,
                        "delivery_channels": [channel.value for channel in action_config.delivery_channels],
                        "payload_template": _json_dumps(action_config.payload_template),
                    },
                )

        await db.commit()
    except IntegrityError as exc:
        await _rollback_and_raise_conflict(
            db,
            exc,
            constraint_name="uq_rules_company_name",
            detail="A rule with the same name already exists in this company.",
        )
    return await _get_rule_or_404(db, rule_id, company_id)


async def delete_rule(
    db: AsyncSession,
    rule_id: UUID,
    company_id: str,
) -> None:
    await _get_rule_or_404(db, rule_id, company_id)
    await db.execute(
        text(
            """
            DELETE FROM rules
            WHERE id = :rule_id
              AND company_id = :company_id
            """
        ),
        {
            "rule_id": str(rule_id),
            "company_id": company_id,
        },
    )
    await db.commit()


async def list_webhooks(
    db: AsyncSession,
    company_id: str,
) -> WebhookListResponse:
    result = await db.execute(
        text(
            f"""
            {WEBHOOK_SELECT}
            WHERE w.company_id = :company_id
            ORDER BY w.created_at DESC
            """
        ),
        {"company_id": company_id},
    )
    rows = [dict(row) for row in result.mappings().all()]
    items = [_webhook_from_row(row) for row in rows]
    return WebhookListResponse(items=items, total=len(items))


async def get_webhook(
    db: AsyncSession,
    webhook_id: UUID,
    company_id: str,
) -> WebhookResponse:
    return await _get_webhook_or_404(db, webhook_id, company_id)


async def create_webhook(
    db: AsyncSession,
    company_id: str,
    payload: WebhookCreateRequest,
) -> WebhookResponse:
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO webhooks (
                    company_id,
                    name,
                    target_url,
                    subscribed_events,
                    secret,
                    is_active
                )
                VALUES (
                    CAST(:company_id AS uuid),
                    :name,
                    :target_url,
                    CAST(:subscribed_events AS webhook_event_enum[]),
                    :secret,
                    :is_active
                )
                RETURNING id
                """
            ),
            {
                "company_id": company_id,
                "name": payload.name,
                "target_url": str(payload.target_url),
                "subscribed_events": [event.value for event in payload.subscribed_events],
                "secret": payload.secret,
                "is_active": payload.is_active,
            },
        )
        webhook_id = result.scalar_one()
        await db.commit()
    except IntegrityError as exc:
        await _rollback_and_raise_conflict(
            db,
            exc,
            constraint_name="uq_webhooks_company_name",
            detail="A webhook with the same name already exists in this company.",
        )
    return await _get_webhook_or_404(db, webhook_id, company_id)


async def update_webhook(
    db: AsyncSession,
    webhook_id: UUID,
    company_id: str,
    payload: WebhookUpdateRequest,
) -> WebhookResponse:
    await _get_webhook_or_404(db, webhook_id, company_id)

    set_clauses: list[str] = []
    params: dict[str, object] = {
        "webhook_id": str(webhook_id),
        "company_id": company_id,
    }

    if payload.name is not None:
        set_clauses.append("name = :name")
        params["name"] = payload.name

    if payload.target_url is not None:
        set_clauses.append("target_url = :target_url")
        params["target_url"] = str(payload.target_url)

    if payload.subscribed_events is not None:
        set_clauses.append("subscribed_events = CAST(:subscribed_events AS webhook_event_enum[])")
        params["subscribed_events"] = [event.value for event in payload.subscribed_events]

    if payload.secret is not None:
        set_clauses.append("secret = :secret")
        params["secret"] = payload.secret

    if payload.is_active is not None:
        set_clauses.append("is_active = :is_active")
        params["is_active"] = payload.is_active

    if set_clauses:
        try:
            await db.execute(
                text(
                    f"""
                    UPDATE webhooks
                    SET {", ".join(set_clauses)}
                    WHERE id = :webhook_id
                      AND company_id = :company_id
                    """
                ),
                params,
            )
            await db.commit()
        except IntegrityError as exc:
            await _rollback_and_raise_conflict(
                db,
                exc,
                constraint_name="uq_webhooks_company_name",
                detail="A webhook with the same name already exists in this company.",
            )

    return await _get_webhook_or_404(db, webhook_id, company_id)


async def delete_webhook(
    db: AsyncSession,
    webhook_id: UUID,
    company_id: str,
) -> None:
    await _get_webhook_or_404(db, webhook_id, company_id)
    await db.execute(
        text(
            """
            DELETE FROM webhooks
            WHERE id = :webhook_id
              AND company_id = :company_id
            """
        ),
        {
            "webhook_id": str(webhook_id),
            "company_id": company_id,
        },
    )
    await db.commit()
