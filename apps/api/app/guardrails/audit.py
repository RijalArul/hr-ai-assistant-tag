"""Guardrail audit log writer.

Writes events to the guardrail_audit_logs table.
Events are written fire-and-forget (best-effort); failures are logged
but do not interrupt the main request flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def write_audit_log(
    db: AsyncSession,
    *,
    company_id: str,
    employee_id: str,
    conversation_id: str | None,
    event_type: str,
    trigger: str,
    action_taken: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write one guardrail audit event. Best-effort — never raises."""
    try:
        await db.execute(
            text(
                "INSERT INTO guardrail_audit_logs "
                "(id, company_id, employee_id, conversation_id, "
                " event_type, trigger, action_taken, metadata, created_at) "
                "VALUES (:id, :company_id, :employee_id, :conversation_id, "
                "        :event_type, :trigger, :action_taken, :metadata, NOW())"
            ),
            {
                "id": str(uuid4()),
                "company_id": company_id,
                "employee_id": employee_id,
                "conversation_id": conversation_id,
                "event_type": event_type,
                "trigger": trigger,
                "action_taken": action_taken,
                "metadata": json.dumps(metadata or {}),
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to write guardrail audit log: %s", exc)
