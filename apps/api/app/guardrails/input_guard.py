"""Input Guard — entry point for all pre-orchestrator checks.

Pipeline:
  1. Rate limit check
  2. Cooldown / abuse check
  3. Prompt injection detection + sanitization
  4. Blocked topics check
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext
from app.guardrails.abuse_detector import check_abuse
from app.guardrails.audit import write_audit_log
from app.guardrails.injection_detector import check_and_sanitize
from app.guardrails.models import GuardrailConfig, InputGuardResult
from app.guardrails.rate_limiter import check_rate_limit

_BLOCKED_RESPONSE = (
    "Maaf, saya hanya bisa membantu pertanyaan terkait HR. Silakan coba kembali."
)
_RATE_LIMIT_RESPONSE = (
    "Terlalu banyak permintaan. Silakan coba lagi dalam beberapa menit."
)
_COOLDOWN_RESPONSE = (
    "Akun Anda sementara dibatasi karena pola penggunaan yang tidak biasa. "
    "Silakan coba lagi nanti."
)


async def check_input(
    db: AsyncSession,
    message: str,
    session: SessionContext,
    config: GuardrailConfig,
    conversation_id: str | None = None,
    action_type: str = "messages",
) -> InputGuardResult:
    """Run all input guard checks.

    Returns InputGuardResult. If blocked=True, use safe_response directly.
    """
    # ── 1. Rate limit ────────────────────────────────────────────────────────
    allowed, current, limit = await check_rate_limit(
        session.company_id,
        session.employee_id,
        action_type,
        config.rate_limits,
    )
    if not allowed:
        await write_audit_log(
            db,
            company_id=session.company_id,
            employee_id=session.employee_id,
            conversation_id=conversation_id,
            event_type="rate_limited",
            trigger=f"{action_type} limit exceeded: {current}/{limit}",
            action_taken="blocked",
            metadata={
                "limit_type": action_type,
                "current_count": current,
                "limit": limit,
                "window_seconds": 3600,
            },
        )
        return InputGuardResult(
            blocked=True,
            event_type="rate_limited",
            safe_response=_RATE_LIMIT_RESPONSE,
            audit_metadata={"limit_type": action_type, "current": current, "limit": limit},
        )

    # ── 2. Abuse / cooldown check ─────────────────────────────────────────────
    in_cooldown, abuse_event, abuse_action = await check_abuse(
        session.company_id,
        session.employee_id,
        message,
    )
    if in_cooldown:
        await write_audit_log(
            db,
            company_id=session.company_id,
            employee_id=session.employee_id,
            conversation_id=conversation_id,
            event_type="abuse_warned",
            trigger="Cooldown active or repetitive message detected",
            action_taken=abuse_action,
        )
        return InputGuardResult(
            blocked=True,
            event_type="abuse_warned",
            safe_response=_COOLDOWN_RESPONSE,
            audit_metadata={"abuse_action": abuse_action},
        )

    # ── 3. Injection detection + sanitization ──────────────────────────────────
    is_blocked, sanitized_message, block_reason = check_and_sanitize(message)
    if is_blocked:
        await write_audit_log(
            db,
            company_id=session.company_id,
            employee_id=session.employee_id,
            conversation_id=conversation_id,
            event_type="input_blocked",
            trigger=block_reason or "Prompt injection detected",
            action_taken="blocked",
        )
        return InputGuardResult(
            blocked=True,
            event_type="input_blocked",
            safe_response=_BLOCKED_RESPONSE,
            audit_metadata={"block_reason": block_reason},
        )

    # ── 4. Blocked topics check ────────────────────────────────────────────────
    lowered = sanitized_message.lower()
    for topic in config.blocked_topics:
        if topic.lower() in lowered:
            await write_audit_log(
                db,
                company_id=session.company_id,
                employee_id=session.employee_id,
                conversation_id=conversation_id,
                event_type="input_blocked",
                trigger=f"Blocked topic matched: {topic}",
                action_taken="blocked",
            )
            return InputGuardResult(
                blocked=True,
                event_type="input_blocked",
                safe_response=_BLOCKED_RESPONSE,
                audit_metadata={"blocked_topic": topic},
            )

    return InputGuardResult(
        blocked=False,
        sanitized_message=sanitized_message,
    )
