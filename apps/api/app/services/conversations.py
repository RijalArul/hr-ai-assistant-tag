from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import orchestrate_message
from app.core.security import SessionContext
from app.guardrails.config_loader import load_config as load_guardrail_config
from app.guardrails.input_guard import check_input as guardrail_check_input
from app.guardrails.output_guard import validate_output as guardrail_validate_output
from app.models import (
    ActionExecutionRequest,
    ActionResponse,
    ActionListResponse,
    AgentRoute,
    AgentTraceStep,
    ConversationRequestCategory,
    ConversationCreateRequest,
    ConversationIntent,
    ConversationMessageCreateRequest,
    ConversationMessageExchangeResponse,
    ConversationMessageResponse,
    ConversationMessageRole,
    ConversationResponse,
    ConversationUpdateRequest,
    IntentAssessment,
    OrchestratorRequest,
    OrchestratorResponse,
    ResponseMode,
    SensitivityAssessment,
)
from app.services.action_engine import (
    create_actions_from_rule_trigger,
    execute_action,
    list_actions_for_conversation,
    should_auto_execute_action,
)
from app.services.execution_intent import assess_action_execution_intent
from shared import ConversationStatus, RuleTrigger, SensitivityLevel

# Intents that can trigger conversational intake actions (F.4).
_INTAKE_INTENTS: frozenset[str] = frozenset(
    [
        "payroll_document_request",
        "time_off_request_status",
        "company_policy",
        "personal_profile",
    ]
)

CONVERSATION_SELECT = """
SELECT
    c.id,
    c.company_id,
    c.employee_id,
    c.title,
    c.status::text AS status,
    c.metadata,
    c.last_message_at,
    c.created_at,
    c.updated_at
FROM conversations c
"""

CONVERSATION_MESSAGE_SELECT = """
SELECT
    m.id,
    m.conversation_id,
    m.role::text AS role,
    m.content,
    m.attachments,
    m.metadata,
    m.created_at
FROM conversation_messages m
"""


def _json_dumps(value: object) -> str:
    import json

    return json.dumps(value, default=str)


def _conversation_scope_clause(
    alias: str,
    session: SessionContext,
) -> tuple[str, dict[str, str]]:
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


def _conversation_from_row(
    row: dict,
    messages: list[ConversationMessageResponse] | None = None,
) -> ConversationResponse:
    data = dict(row)
    if messages is not None:
        data["messages"] = messages
    return ConversationResponse.model_validate(data)


def _conversation_message_from_row(row: dict) -> ConversationMessageResponse:
    return ConversationMessageResponse.model_validate(dict(row))


def _normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message.lower()).strip()


def _build_action_follow_up_note(triggered_actions: list[ActionResponse]) -> str | None:
    if not triggered_actions:
        return None

    generated_documents = [
        action
        for action in triggered_actions
        if action.execution_result is not None
        and isinstance(action.execution_result.get("document"), dict)
    ]
    if generated_documents:
        execution_result = generated_documents[0].execution_result
        if isinstance(execution_result, dict):
            document = execution_result.get("document")
            if isinstance(document, dict):
                period = document.get("period", {})
                period_label = period.get("label") if isinstance(period, dict) else None
                if period_label:
                    return (
                        f" Aku juga sudah menyiapkan PDF payslip untuk periode {period_label} "
                        "di action percakapan ini."
                    )
        return " Aku juga sudah menyiapkan PDF payslip di action percakapan ini."

    if len(triggered_actions) == 1:
        return f" Aku juga sudah membuat action tindak lanjut: {triggered_actions[0].title}."

    return (
        f" Aku juga sudah membuat {len(triggered_actions)} action tindak lanjut "
        "dari percakapan ini."
    )


def _assess_action_execution_intent(
    message: str,
    *,
    intent_key: str,
) -> dict[str, object]:
    return assess_action_execution_intent(message, intent_key=intent_key)


def _build_action_gate_note(action_gate: dict[str, object]) -> str | None:
    if action_gate.get("should_trigger"):
        return None
    if action_gate.get("mode") not in {"exploratory_request", "topic_only"}:
        return None

    return (
        " Kalau kamu memang ingin aku langsung membuat action atau generate dokumennya, "
        "minta secara eksplisit, misalnya: tolong generate PDF payslip saya untuk Maret 2026."
    )


def _build_orchestrator_history(
    messages: list[ConversationMessageResponse],
    *,
    max_items: int = 4,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages[-max_items:]:
        history.append(
            {
                "role": message.role.value,
                "content": message.content,
            }
        )
    return history


def _build_auto_execution_issue_note(
    action: ActionResponse,
    exc: Exception,
) -> str:
    if (
        isinstance(exc, HTTPException)
        and exc.status_code == status.HTTP_404_NOT_FOUND
        and action.type.value == "document_generation"
        and getattr(action.payload, "document_type", None) in {"salary_slip", "payslip"}
    ):
        return (
            " PDF payslip belum bisa digenerate otomatis karena payroll untuk periode "
            "yang diminta belum tersedia."
        )

    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "eksekusi otomatis gagal."
        return (
            " Action tindak lanjutnya sudah dibuat, tapi eksekusi otomatisnya belum "
            f"berhasil: {detail}"
        )

    return (
        " Action tindak lanjutnya sudah dibuat, tapi eksekusi otomatisnya belum "
        "berhasil dan masih bisa ditinjau manual."
    )


async def _list_conversation_messages(
    db: AsyncSession,
    conversation_id: UUID,
    company_id: str,
) -> list[ConversationMessageResponse]:
    result = await db.execute(
        text(
            f"""
            {CONVERSATION_MESSAGE_SELECT}
            WHERE m.conversation_id = :conversation_id
              AND m.company_id = :company_id
            ORDER BY m.created_at ASC
            """
        ),
        {
            "conversation_id": str(conversation_id),
            "company_id": company_id,
        },
    )
    rows = [dict(row) for row in result.mappings().all()]
    return [_conversation_message_from_row(row) for row in rows]


async def _get_conversation_or_404(
    db: AsyncSession,
    conversation_id: UUID,
    session: SessionContext,
) -> ConversationResponse:
    scope_clause, scope_params = _conversation_scope_clause("c", session)
    result = await db.execute(
        text(
            f"""
            {CONVERSATION_SELECT}
            WHERE c.id = :conversation_id
              AND c.company_id = :company_id
              {scope_clause}
            """
        ),
        {
            "conversation_id": str(conversation_id),
            "company_id": session.company_id,
            **scope_params,
        },
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    return _conversation_from_row(dict(row))


async def _insert_conversation_message(
    db: AsyncSession,
    *,
    conversation_id: str,
    company_id: str,
    employee_id: str,
    role: ConversationMessageRole,
    content: str,
    attachments: list[dict],
    metadata: dict,
) -> ConversationMessageResponse:
    result = await db.execute(
        text(
            """
            INSERT INTO conversation_messages (
                conversation_id,
                company_id,
                employee_id,
                role,
                content,
                attachments,
                metadata
            )
            VALUES (
                CAST(:conversation_id AS uuid),
                CAST(:company_id AS uuid),
                CAST(:employee_id AS uuid),
                CAST(:role AS conversation_message_role_enum),
                :content,
                CAST(:attachments AS jsonb),
                CAST(:metadata AS jsonb)
            )
            RETURNING
                id,
                conversation_id,
                role::text AS role,
                content,
                attachments,
                metadata,
                created_at
            """
        ),
        {
            "conversation_id": conversation_id,
            "company_id": company_id,
            "employee_id": employee_id,
            "role": role.value,
            "content": content,
            "attachments": _json_dumps(attachments),
            "metadata": _json_dumps(metadata),
        },
    )
    return _conversation_message_from_row(dict(result.mappings().one()))


async def create_conversation(
    db: AsyncSession,
    session: SessionContext,
    payload: ConversationCreateRequest,
) -> ConversationResponse:
    result = await db.execute(
        text(
            """
            INSERT INTO conversations (
                company_id,
                employee_id,
                title,
                status,
                metadata
            )
            VALUES (
                CAST(:company_id AS uuid),
                CAST(:employee_id AS uuid),
                :title,
                CAST(:status AS conversation_status_enum),
                CAST(:metadata AS jsonb)
            )
            RETURNING id
            """
        ),
        {
            "company_id": session.company_id,
            "employee_id": session.employee_id,
            "title": payload.title,
            "status": ConversationStatus.ACTIVE.value,
            "metadata": _json_dumps(payload.metadata),
        },
    )
    conversation_id = result.scalar_one()
    await db.commit()
    return await get_conversation(db, conversation_id, session)


async def get_conversation(
    db: AsyncSession,
    conversation_id: UUID,
    session: SessionContext,
) -> ConversationResponse:
    conversation = await _get_conversation_or_404(db, conversation_id, session)
    messages = await _list_conversation_messages(db, conversation_id, session.company_id)
    return conversation.model_copy(update={"messages": messages})


async def update_conversation(
    db: AsyncSession,
    conversation_id: UUID,
    payload: ConversationUpdateRequest,
    session: SessionContext,
) -> ConversationResponse:
    await _get_conversation_or_404(db, conversation_id, session)

    set_clauses: list[str] = []
    params: dict[str, object] = {
        "conversation_id": str(conversation_id),
        "company_id": session.company_id,
    }

    if payload.title is not None:
        set_clauses.append("title = :title")
        params["title"] = payload.title

    if payload.status is not None:
        set_clauses.append("status = CAST(:conversation_status AS conversation_status_enum)")
        params["conversation_status"] = payload.status.value

    if payload.metadata is not None:
        set_clauses.append("metadata = CAST(:metadata AS jsonb)")
        params["metadata"] = _json_dumps(payload.metadata)

    if not set_clauses:
        return await get_conversation(db, conversation_id, session)

    set_clauses.append("updated_at = now()")

    await db.execute(
        text(
            f"""
            UPDATE conversations
            SET {", ".join(set_clauses)}
            WHERE id = :conversation_id
              AND company_id = :company_id
            """
        ),
        params,
    )
    await db.commit()
    return await get_conversation(db, conversation_id, session)


async def create_conversation_message(
    db: AsyncSession,
    conversation_id: UUID,
    payload: ConversationMessageCreateRequest,
    session: SessionContext,
) -> ConversationMessageExchangeResponse:
    conversation = await _get_conversation_or_404(db, conversation_id, session)

    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed conversations cannot accept new messages.",
        )

    # ── Phase 5: Input Guard ──────────────────────────────────────────────────
    guardrail_config = await load_guardrail_config(db, session.company_id)
    input_result = await guardrail_check_input(
        db,
        message=payload.message,
        session=session,
        config=guardrail_config,
        conversation_id=str(conversation_id),
        action_type="messages",
    )

    user_attachments = [attachment.model_dump(mode="json") for attachment in payload.attachments]
    prior_messages = await _list_conversation_messages(
        db,
        conversation_id,
        session.company_id,
    )
    user_message = await _insert_conversation_message(
        db,
        conversation_id=str(conversation_id),
        company_id=session.company_id,
        employee_id=session.employee_id,
        role=ConversationMessageRole.USER,
        content=payload.message,
        attachments=user_attachments,
        metadata=payload.metadata,
    )

    if input_result.blocked:
        # Return safe guardrail response without invoking orchestrator
        safe_content = input_result.safe_response or "Permintaan tidak dapat diproses."
        assistant_message = await _insert_conversation_message(
            db,
            conversation_id=str(conversation_id),
            company_id=session.company_id,
            employee_id=session.employee_id,
            role=ConversationMessageRole.ASSISTANT,
            content=safe_content,
            attachments=[],
            metadata={"guardrail_triggered": True, "guardrail_event": input_result.event_type},
        )
        guardrail_orchestration = OrchestratorResponse(
            route=AgentRoute.OUT_OF_SCOPE,
            intent=IntentAssessment(
                primary_intent=ConversationIntent.OUT_OF_SCOPE,
                confidence=1.0,
            ),
            sensitivity=SensitivityAssessment(
                level=SensitivityLevel.LOW,
                rationale="Blocked by guardrail.",
            ),
            request_category=ConversationRequestCategory.INFORMATIONAL_QUESTION,
            response_mode=ResponseMode.INFORMATIONAL,
            answer=safe_content,
            recommended_next_steps=[],
            trace=[
                AgentTraceStep(
                    agent="input-guard",
                    status="used",
                    detail=f"Blocked: {input_result.event_type}",
                )
            ],
            context={
                "guardrail_triggered": True,
                "guardrail_event": input_result.event_type,
                "response_contract": {
                    "request_category": ConversationRequestCategory.INFORMATIONAL_QUESTION.value,
                    "response_mode": ResponseMode.INFORMATIONAL.value,
                    "recommended_next_steps": [],
                },
            },
        )
        refreshed = await _get_conversation_or_404(db, conversation_id, session)
        messages = await _list_conversation_messages(db, conversation_id, session.company_id)
        refreshed = refreshed.model_copy(update={"messages": messages})
        return ConversationMessageExchangeResponse(
            conversation=refreshed,
            user_message=user_message,
            assistant_message=assistant_message,
            orchestration=guardrail_orchestration,
            triggered_actions=[],
        )

    # Use sanitized message if available
    effective_message = input_result.sanitized_message or payload.message

    orchestration = await orchestrate_message(
        db,
        session,
        OrchestratorRequest(
            message=effective_message,
            attachments=payload.attachments,
            conversation_history=_build_orchestrator_history(prior_messages),
        ),
    )

    # ── Phase 5: Output Guard ─────────────────────────────────────────────────
    output_result = await guardrail_validate_output(
        db,
        response=orchestration.answer,
        session=session,
        config=guardrail_config,
        evidence=orchestration.evidence,
        route_confidence=orchestration.intent.confidence,
        conversation_id=str(conversation_id),
    )
    orchestration = orchestration.model_copy(update={"answer": output_result.response})

    triggered_actions: list[ActionResponse] = []
    auto_execution_issues: list[dict[str, object]] = []
    auto_execution_issue_notes: list[str] = []
    action_gate = _assess_action_execution_intent(
        payload.message,
        intent_key=orchestration.intent.primary_intent.value,
    )
    sensitive_handling = orchestration.context.get("sensitive_handling")
    sensitive_automation = (
        sensitive_handling.get("automation")
        if isinstance(sensitive_handling, dict)
        else None
    )
    sensitive_trigger = None
    sensitive_intent_key = None
    should_create_sensitive_action = False
    if isinstance(sensitive_automation, dict):
        raw_trigger = sensitive_automation.get("trigger")
        raw_intent_key = sensitive_automation.get("intent_key")
        should_create_sensitive_action = bool(
            sensitive_automation.get("should_create_action")
        )
        if isinstance(raw_trigger, str):
            sensitive_trigger = RuleTrigger(raw_trigger)
        if isinstance(raw_intent_key, str) and raw_intent_key.strip():
            sensitive_intent_key = raw_intent_key.strip()

    if (
        orchestration.route == AgentRoute.SENSITIVE_REDIRECT
        and should_create_sensitive_action
        and sensitive_trigger is not None
        and sensitive_intent_key is not None
    ):
        triggered_actions = await create_actions_from_rule_trigger(
            db,
            session=session,
            conversation_id=conversation_id,
            trigger=sensitive_trigger,
            intent_key=sensitive_intent_key,
            sensitivity=orchestration.sensitivity.level,
            message=payload.message,
        )
    elif (
        orchestration.intent.primary_intent.value in _INTAKE_INTENTS
        and orchestration.route != AgentRoute.SENSITIVE_REDIRECT
        and action_gate.get("mode") == "missing_info"
    ):
        # Gate detected the intent but required fields were not in the message.
        # Append the natural-language follow-up prompt so the user provides them.
        follow_up = action_gate.get("follow_up_prompt", "")
        if follow_up:
            orchestration = orchestration.model_copy(
                update={"answer": f"{orchestration.answer}\n\n{follow_up}"}
            )
    elif (
        orchestration.intent.primary_intent.value in _INTAKE_INTENTS
        and orchestration.route != AgentRoute.SENSITIVE_REDIRECT
        and bool(action_gate["should_trigger"])
    ):
        extracted_params = action_gate.get("extracted")
        triggered_actions = await create_actions_from_rule_trigger(
            db,
            session=session,
            conversation_id=conversation_id,
            trigger=RuleTrigger.CONVERSATION_RESOLVED,
            intent_key=orchestration.intent.primary_intent.value,
            sensitivity=orchestration.sensitivity.level,
            message=payload.message,
            extracted_params=extracted_params if isinstance(extracted_params, dict) else {},
        )
        finalized_actions: list[ActionResponse] = []
        for action in triggered_actions:
            if should_auto_execute_action(action):
                try:
                    execution = await execute_action(
                        db,
                        action.id,
                        ActionExecutionRequest(
                            trigger_delivery=False,
                            executor_note=(
                                "Auto-generated from employee self-service conversation."
                            ),
                        ),
                        session,
                    )
                except Exception as exc:
                    auto_execution_issues.append(
                        {
                            "action_id": str(action.id),
                            "action_type": action.type.value,
                            "status": action.status.value,
                            "detail": (
                                exc.detail
                                if isinstance(exc, HTTPException)
                                and isinstance(exc.detail, str)
                                else str(exc) or "Automatic execution failed."
                            ),
                        }
                    )
                    auto_execution_issue_notes.append(
                        _build_auto_execution_issue_note(action, exc)
                    )
                    finalized_actions.append(action)
                    continue
                finalized_actions.append(execution.action)
                continue
            finalized_actions.append(action)
        triggered_actions = finalized_actions

    action_note = _build_action_follow_up_note(triggered_actions)
    gate_note = _build_action_gate_note(action_gate)
    issue_note = "".join(auto_execution_issue_notes) if auto_execution_issue_notes else None
    combined_note = "".join(note for note in [action_note, gate_note, issue_note] if note)
    if combined_note:
        orchestration = orchestration.model_copy(
            update={
                "answer": f"{orchestration.answer}{combined_note}",
                "context": {
                    **orchestration.context,
                    "action_gate": action_gate,
                    "triggered_actions": [
                        {
                            "id": str(action.id),
                            "type": action.type.value,
                            "status": action.status.value,
                            "title": action.title,
                        }
                        for action in triggered_actions
                    ],
                    "auto_execution_issues": auto_execution_issues,
                },
            }
        )
    else:
        orchestration = orchestration.model_copy(
            update={
                "context": {
                    **orchestration.context,
                    "action_gate": action_gate,
                }
            }
        )

    assistant_message = await _insert_conversation_message(
        db,
        conversation_id=str(conversation_id),
        company_id=session.company_id,
        employee_id=session.employee_id,
        role=ConversationMessageRole.ASSISTANT,
        content=orchestration.answer,
        attachments=[],
        metadata={
            "orchestration": orchestration.model_dump(mode="json"),
        },
    )

    next_status = (
        ConversationStatus.ESCALATED
        if (
            conversation.status == ConversationStatus.ESCALATED
            or orchestration.route == AgentRoute.SENSITIVE_REDIRECT
        )
        else ConversationStatus.ACTIVE
    )
    await db.execute(
        text(
            """
            UPDATE conversations
            SET
                status = CAST(:conversation_status AS conversation_status_enum),
                last_message_at = :last_message_at,
                updated_at = now()
            WHERE id = :conversation_id
              AND company_id = :company_id
            """
        ),
        {
            "conversation_id": str(conversation_id),
            "company_id": session.company_id,
            "conversation_status": next_status.value,
            "last_message_at": datetime.now(UTC),
        },
    )
    await db.commit()

    refreshed = await get_conversation(db, conversation_id, session)
    return ConversationMessageExchangeResponse(
        conversation=refreshed,
        user_message=user_message,
        assistant_message=assistant_message,
        orchestration=orchestration,
        triggered_actions=triggered_actions,
    )


async def get_conversation_actions(
    db: AsyncSession,
    conversation_id: UUID,
    session: SessionContext,
) -> ActionListResponse:
    await _get_conversation_or_404(db, conversation_id, session)
    return await list_actions_for_conversation(db, conversation_id, session)
