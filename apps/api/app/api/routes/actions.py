from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    SessionContext,
    get_current_session,
    require_session_roles,
)
from app.models import (
    ActionExecutionRequest,
    ActionExecutionResponse,
    ActionListResponse,
    ActionResponse,
    ActionResultResponse,
    ActionUpdateRequest,
    ErrorResponse,
)
from app.services.action_engine import (
    execute_action,
    get_action,
    get_action_result,
    list_actions,
    update_action,
)
from app.services.db import get_db

router = APIRouter(prefix="/actions", tags=["actions"])

ACTION_READ_ROLES = {"employee", "hr_admin"}
ACTION_MUTATION_ROLES = {"hr_admin"}


@router.get(
    "",
    response_model=ActionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List actions",
    description=(
        "Lists actions visible to the current session. Employees only see their "
        "own actions, while HR Admin can review actions across the same company."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read actions.",
        }
    },
)
async def list_actions_route(
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionListResponse:
    require_session_roles(session, ACTION_READ_ROLES)
    return await list_actions(db, session)


@router.get(
    "/{action_id}",
    response_model=ActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get action details",
    description="Returns one action if it belongs to the current company scope.",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read actions.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Action was not found in the current session scope.",
        },
    },
)
async def get_action_route(
    action_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    require_session_roles(session, ACTION_READ_ROLES)
    return await get_action(db, action_id, session)


@router.patch(
    "/{action_id}",
    response_model=ActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update action",
    description=(
        "Updates action metadata or status. This route is limited to HR Admin."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to update actions.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Action is already terminal and cannot be updated manually.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Action was not found in the current company scope.",
        },
    },
)
async def update_action_route(
    action_id: UUID,
    payload: ActionUpdateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    require_session_roles(session, ACTION_MUTATION_ROLES)
    return await update_action(db, action_id, payload, session)


@router.post(
    "/{action_id}/execute",
    response_model=ActionExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute action",
    description=(
        "Executes one action and stores execution metadata. Sensitive actions "
        "are normalized to `manual_review` delivery only. This route is limited "
        "to HR Admin."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to execute actions.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Action is already completed or cancelled.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Action was not found in the current company scope.",
        },
    },
)
async def execute_action_route(
    action_id: UUID,
    payload: ActionExecutionRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionExecutionResponse:
    require_session_roles(session, ACTION_MUTATION_ROLES)
    return await execute_action(db, action_id, payload, session)


@router.get(
    "/{action_id}/result",
    response_model=ActionResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Get action execution result",
    description="Returns the latest stored execution result for an action.",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read actions.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Action was not found in the current session scope.",
        },
    },
)
async def get_action_result_route(
    action_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionResultResponse:
    require_session_roles(session, ACTION_READ_ROLES)
    return await get_action_result(db, action_id, session)
