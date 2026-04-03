from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import orchestrate_message
from app.core.security import SessionContext
from app.models import (
    ActionExecutionRequest,
    ActionResponse,
    ActionListResponse,
    AgentRoute,
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
    ConversationMessageExchangeResponse,
    ConversationMessageResponse,
    ConversationMessageRole,
    ConversationResponse,
    ConversationUpdateRequest,
    OrchestratorRequest,
)
from app.services.action_engine import (
    create_actions_from_rule_trigger,
    execute_action,
    list_actions_for_conversation,
    should_auto_execute_action,
)
from shared import ConversationStatus
from shared import RuleTrigger

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
        document = generated_documents[0].execution_result["document"]
        period = document.get("period", {})
        period_label = period.get("label")
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

    user_attachments = [attachment.model_dump(mode="json") for attachment in payload.attachments]
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

    orchestration = await orchestrate_message(
        db,
        session,
        OrchestratorRequest(
            message=payload.message,
            attachments=payload.attachments,
        ),
    )

    triggered_actions: list[ActionResponse] = []
    if (
        orchestration.intent.primary_intent.value == "payroll_document_request"
        and orchestration.route != AgentRoute.SENSITIVE_REDIRECT
    ):
        triggered_actions = await create_actions_from_rule_trigger(
            db,
            session=session,
            conversation_id=conversation_id,
            trigger=RuleTrigger.CONVERSATION_RESOLVED,
            intent_key=orchestration.intent.primary_intent.value,
            sensitivity=orchestration.sensitivity.level,
            message=payload.message,
        )
        finalized_actions: list[ActionResponse] = []
        for action in triggered_actions:
            if should_auto_execute_action(action):
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
                finalized_actions.append(execution.action)
                continue
            finalized_actions.append(action)
        triggered_actions = finalized_actions

    action_note = _build_action_follow_up_note(triggered_actions)
    if action_note:
        orchestration = orchestration.model_copy(
            update={
                "answer": f"{orchestration.answer}{action_note}",
                "context": {
                    **orchestration.context,
                    "triggered_actions": [
                        {
                            "id": str(action.id),
                            "type": action.type.value,
                            "status": action.status.value,
                            "title": action.title,
                        }
                        for action in triggered_actions
                    ],
                },
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
