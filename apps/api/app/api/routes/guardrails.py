"""Phase 5 Guardrail API routes.

GET  /guardrails/audit-logs          — it_admin (full), hr_admin (summary)
GET  /guardrails/audit-logs/{id}     — it_admin only
GET  /guardrails/config              — it_admin only
PATCH /guardrails/config             — it_admin only
GET  /guardrails/rate-status         — it_admin, hr_admin
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext, get_current_session, require_session_roles
from app.guardrails.config_loader import load_config, save_config
from app.guardrails.models import (
    GuardrailAuditLogListResponse,
    GuardrailAuditLogResponse,
    GuardrailConfig,
    GuardrailConfigUpdateRequest,
    RateStatusResponse,
)
from app.guardrails.rate_limiter import get_rate_status
from app.services.db import get_db

router = APIRouter(prefix="/guardrails", tags=["guardrails"])

IT_ADMIN = {"it_admin"}
IT_HR_ADMIN = {"it_admin", "hr_admin"}


# ─── Audit Logs ────────────────────────────────────────────────────────────────

@router.get(
    "/audit-logs",
    response_model=GuardrailAuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="List guardrail audit events",
)
async def list_audit_logs(
    event_type: str | None = Query(None),
    employee_id: UUID | None = Query(None),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> GuardrailAuditLogListResponse:
    require_session_roles(session, IT_HR_ADMIN)

    is_it_admin = session.role == "it_admin"

    # Build query
    conditions = ["company_id = :company_id"]
    params: dict = {"company_id": session.company_id, "limit": limit, "offset": offset}

    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type

    if employee_id:
        conditions.append("employee_id = :employee_id")
        params["employee_id"] = str(employee_id)

    if from_dt:
        conditions.append("created_at >= :from_dt")
        params["from_dt"] = from_dt

    if to_dt:
        conditions.append("created_at <= :to_dt")
        params["to_dt"] = to_dt

    where = " AND ".join(conditions)

    if is_it_admin:
        select_cols = "id, company_id, employee_id, conversation_id, event_type, trigger, action_taken, metadata, created_at"
    else:
        # hr_admin gets summary view — no trigger detail
        select_cols = "id, company_id, employee_id, conversation_id, event_type, '' AS trigger, action_taken, '{}' AS metadata, created_at"

    rows = await db.execute(
        text(
            f"SELECT {select_cols} FROM guardrail_audit_logs "
            f"WHERE {where} ORDER BY created_at DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    count_row = await db.execute(
        text(f"SELECT COUNT(*) FROM guardrail_audit_logs WHERE {where}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )

    total = count_row.scalar() or 0
    items = []
    import json
    for row in rows.fetchall():
        meta = row[7]
        if isinstance(meta, str):
            meta = json.loads(meta)
        items.append(
            GuardrailAuditLogResponse(
                id=row[0],
                company_id=row[1],
                employee_id=row[2],
                conversation_id=row[3],
                event_type=row[4],
                trigger=row[5],
                action_taken=row[6],
                metadata=meta or {},
                created_at=row[8],
            )
        )

    return GuardrailAuditLogListResponse(items=items, total=int(total))


@router.get(
    "/audit-logs/{log_id}",
    response_model=GuardrailAuditLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Get one guardrail audit event detail",
)
async def get_audit_log(
    log_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> GuardrailAuditLogResponse:
    require_session_roles(session, IT_ADMIN)

    import json
    row = await db.execute(
        text(
            "SELECT id, company_id, employee_id, conversation_id, event_type, "
            "trigger, action_taken, metadata, created_at "
            "FROM guardrail_audit_logs "
            "WHERE id = :id AND company_id = :company_id LIMIT 1"
        ),
        {"id": str(log_id), "company_id": session.company_id},
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Audit log not found.")

    meta = r[7]
    if isinstance(meta, str):
        meta = json.loads(meta)

    return GuardrailAuditLogResponse(
        id=r[0],
        company_id=r[1],
        employee_id=r[2],
        conversation_id=r[3],
        event_type=r[4],
        trigger=r[5],
        action_taken=r[6],
        metadata=meta or {},
        created_at=r[8],
    )


# ─── Config ────────────────────────────────────────────────────────────────────

@router.get(
    "/config",
    response_model=GuardrailConfig,
    status_code=status.HTTP_200_OK,
    summary="Get guardrail config for this company",
)
async def get_guardrail_config(
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> GuardrailConfig:
    require_session_roles(session, IT_ADMIN)
    return await load_config(db, session.company_id)


@router.patch(
    "/config",
    response_model=GuardrailConfig,
    status_code=status.HTTP_200_OK,
    summary="Update guardrail config (partial update supported)",
)
async def update_guardrail_config(
    payload: GuardrailConfigUpdateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> GuardrailConfig:
    require_session_roles(session, IT_ADMIN)

    current = await load_config(db, session.company_id)

    if payload.rate_limits is not None:
        current.rate_limits = payload.rate_limits
    if payload.pii_patterns is not None:
        current.pii_patterns = payload.pii_patterns
    if payload.blocked_topics is not None:
        current.blocked_topics = payload.blocked_topics
    if payload.sensitivity_overrides is not None:
        current.sensitivity_overrides = payload.sensitivity_overrides
    if payload.hallucination_check is not None:
        current.hallucination_check = payload.hallucination_check
    if payload.tone_check is not None:
        current.tone_check = payload.tone_check
    if payload.audit_level is not None:
        current.audit_level = payload.audit_level

    # Validate custom regex patterns
    import re
    for pattern_str in current.pii_patterns.custom:
        try:
            re.compile(pattern_str)
        except re.error as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid regex pattern in pii_patterns.custom: {pattern_str!r} — {e}",
            )

    return await save_config(db, session.company_id, current)


# ─── Rate Status ──────────────────────────────────────────────────────────────

@router.get(
    "/rate-status",
    response_model=RateStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current rate limit status for one employee",
)
async def get_rate_status_endpoint(
    employee_id: UUID = Query(..., description="The employee to check"),
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> RateStatusResponse:
    require_session_roles(session, IT_HR_ADMIN)

    # Verify employee belongs to this company
    row = await db.execute(
        text(
            "SELECT id FROM employees WHERE id = :id AND company_id = :company_id LIMIT 1"
        ),
        {"id": str(employee_id), "company_id": session.company_id},
    )
    if not row.fetchone():
        raise HTTPException(status_code=404, detail="Employee not found in this company.")

    config = await load_config(db, session.company_id)
    limits = await get_rate_status(session.company_id, str(employee_id), config.rate_limits)

    return RateStatusResponse(
        employee_id=str(employee_id),
        company_id=session.company_id,
        limits=limits,
    )
