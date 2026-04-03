"""Output Guard — entry point for all post-agent response checks.

Pipeline:
  1. PII scan + masking
  2. Hallucination check (evidence-based)
  3. Tone validation
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext
from app.guardrails.audit import write_audit_log
from app.guardrails.hallucination_checker import check_hallucination
from app.guardrails.models import GuardrailConfig, OutputGuardResult
from app.guardrails.pii_scanner import scan_and_mask
from app.guardrails.tone_validator import validate_tone


async def validate_output(
    db: AsyncSession,
    response: str,
    session: SessionContext,
    config: GuardrailConfig,
    evidence: list[Any] | None = None,
    route_confidence: float = 1.0,
    conversation_id: str | None = None,
) -> OutputGuardResult:
    """Run all output guard checks.

    Modifies response in-place with masking and disclaimers.
    Never blocks the response — only modifies or adds context.
    """
    result_response = response
    pii_events = []
    hallucination_flags = []
    disclaimer_added = False
    tone_warning = False

    # ── 1. PII scan ───────────────────────────────────────────────────────────
    masked_response, pii_events = scan_and_mask(
        result_response,
        session_email=session.email,
        session_employee_id=session.employee_id,
        pii_config_custom=config.pii_patterns.custom,
    )
    result_response = masked_response

    if pii_events:
        for evt in pii_events:
            await write_audit_log(
                db,
                company_id=session.company_id,
                employee_id=session.employee_id,
                conversation_id=conversation_id,
                event_type="pii_masked",
                trigger=f"{evt.pii_type} pattern detected in output",
                action_taken="masked",
                metadata={"pii_type": evt.pii_type, "mask_count": evt.mask_count},
            )

    # ── 2. Hallucination check ────────────────────────────────────────────────
    if config.hallucination_check.enabled:
        checked_response, hallucination_flags, disclaimer_added = check_hallucination(
            result_response,
            evidence=evidence or [],
            route_confidence=route_confidence,
            tolerance_pct=config.hallucination_check.numeric_tolerance_pct,
        )
        result_response = checked_response

        if hallucination_flags:
            await write_audit_log(
                db,
                company_id=session.company_id,
                employee_id=session.employee_id,
                conversation_id=conversation_id,
                event_type="hallucination_flagged",
                trigger="Numeric mismatch detected between response and evidence",
                action_taken="disclaimer_added",
                metadata={
                    "flag_count": len(hallucination_flags),
                    "flags": [f.model_dump() for f in hallucination_flags],
                },
            )

    # ── 3. Tone validation ────────────────────────────────────────────────────
    if config.tone_check.enabled:
        tone_response, tone_warning = validate_tone(
            result_response,
            nvc_strict=config.tone_check.nvc_strict,
        )
        result_response = tone_response

    return OutputGuardResult(
        response=result_response,
        pii_masked=bool(pii_events),
        pii_events=pii_events,
        hallucination_flagged=bool(hallucination_flags),
        hallucination_flags=hallucination_flags,
        disclaimer_added=disclaimer_added,
        tone_warning=tone_warning,
        audit_metadata={
            "pii_event_count": len(pii_events),
            "hallucination_flag_count": len(hallucination_flags),
            "disclaimer_added": disclaimer_added,
            "tone_warning": tone_warning,
        },
    )
