from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    SessionContext,
    get_current_session,
    require_session_roles,
)
from app.models import (
    ActionListResponse,
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
    ConversationMessageExchangeResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    ErrorResponse,
)
from app.services.conversations import (
    create_conversation,
    create_conversation_message,
    get_conversation,
    get_conversation_actions,
    update_conversation,
)
from app.services.db import get_db

router = APIRouter(prefix="/conversations", tags=["conversations"])

CONVERSATION_READ_ROLES = {"employee", "hr_admin"}
CONVERSATION_WRITE_ROLES = {"employee"}
CONVERSATION_PATCH_ROLES = {"employee", "hr_admin"}


def _validate_conversation_patch_permissions(
    session: SessionContext,
    payload: ConversationUpdateRequest,
) -> None:
    if session.role == "hr_admin":
        return

    require_session_roles(session, CONVERSATION_PATCH_ROLES)
    if payload.status is not None and payload.status.value == "escalated":
        raise PermissionError("Employees cannot escalate conversations manually.")


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create conversation",
    description=(
        "Creates one conversation in the current trusted employee/company scope. "
        "This endpoint is the public Phase 4 entrypoint that later message "
        "requests can use to invoke the Phase 3 orchestrator."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to create conversations.",
        },
    },
)
async def create_conversation_route(
    payload: ConversationCreateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    require_session_roles(session, CONVERSATION_WRITE_ROLES)
    return await create_conversation(db, session, payload)


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get conversation details",
    description=(
        "Returns one conversation and its stored message history in the current "
        "session scope."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read conversations.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Conversation was not found in the current session scope.",
        },
    },
)
async def get_conversation_route(
    conversation_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    require_session_roles(session, CONVERSATION_READ_ROLES)
    return await get_conversation(db, conversation_id, session)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Update conversation",
    description=(
        "Updates one conversation title, status, or metadata in the current "
        "session scope."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to update conversations.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Conversation was not found in the current session scope.",
        },
    },
)
async def update_conversation_route(
    conversation_id: UUID,
    payload: ConversationUpdateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    try:
        _validate_conversation_patch_permissions(session, payload)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return await update_conversation(db, conversation_id, payload, session)


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationMessageExchangeResponse,
    status_code=status.HTTP_200_OK,
    summary="Post one conversation message",
    description=(
        "Appends one user message, invokes the Phase 3 orchestrator, stores the "
        "assistant response, and returns the orchestration result."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to write conversations.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Conversation was not found in the current session scope.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Conversation can no longer accept new messages.",
        },
    },
)
async def create_conversation_message_route(
    conversation_id: UUID,
    payload: ConversationMessageCreateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationMessageExchangeResponse:
    require_session_roles(session, CONVERSATION_WRITE_ROLES)
    return await create_conversation_message(db, conversation_id, payload, session)


@router.get(
    "/{conversation_id}/actions",
    response_model=ActionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List actions linked to a conversation",
    description=(
        "Returns actions whose `conversation_id` matches the current "
        "conversation in the caller's allowed scope."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read conversations.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Conversation was not found in the current session scope.",
        },
    },
)
async def get_conversation_actions_route(
    conversation_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionListResponse:
    require_session_roles(session, CONVERSATION_READ_ROLES)
    return await get_conversation_actions(db, conversation_id, session)
