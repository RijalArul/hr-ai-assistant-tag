from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    SessionContext,
    get_current_session,
    require_session_roles,
)
from app.models import (
    ErrorResponse,
    WebhookCreateRequest,
    WebhookListResponse,
    WebhookResponse,
    WebhookUpdateRequest,
)
from app.services.action_engine import (
    create_webhook,
    delete_webhook,
    get_webhook,
    list_webhooks,
    update_webhook,
)
from app.services.db import get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

IT_ADMIN_ROLES = {"it_admin"}


@router.get(
    "",
    response_model=WebhookListResponse,
    status_code=status.HTTP_200_OK,
    summary="List webhooks",
    description=(
        "Lists webhook registrations for the current company. This is a "
        "technical integration surface limited to IT Admin."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read webhooks.",
        },
    },
)
async def list_webhooks_route(
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> WebhookListResponse:
    require_session_roles(session, IT_ADMIN_ROLES)
    return await list_webhooks(db, session.company_id)


@router.get(
    "/{webhook_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Get webhook details",
    description="Returns one webhook registration in the current company scope.",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read webhooks.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Webhook was not found in the current company scope.",
        },
    },
)
async def get_webhook_route(
    webhook_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    require_session_roles(session, IT_ADMIN_ROLES)
    return await get_webhook(db, webhook_id, session.company_id)


@router.post(
    "",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create webhook",
    description=(
        "Registers one outbound webhook endpoint and stores the signing secret "
        "used for HMAC-SHA256 delivery signatures."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to create webhooks.",
        },
    },
)
async def create_webhook_route(
    payload: WebhookCreateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    require_session_roles(session, IT_ADMIN_ROLES)
    return await create_webhook(db, session.company_id, payload)


@router.patch(
    "/{webhook_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Update webhook",
    description="Updates one webhook registration and optional secret rotation.",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to update webhooks.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Webhook was not found in the current company scope.",
        },
    },
)
async def update_webhook_route(
    webhook_id: UUID,
    payload: WebhookUpdateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    require_session_roles(session, IT_ADMIN_ROLES)
    return await update_webhook(db, webhook_id, session.company_id, payload)


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete webhook",
    description="Deletes one webhook registration from the current company scope.",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to delete webhooks.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Webhook was not found in the current company scope.",
        },
    },
)
async def delete_webhook_route(
    webhook_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_session_roles(session, IT_ADMIN_ROLES)
    await delete_webhook(db, webhook_id, session.company_id)
