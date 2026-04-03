from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    SessionContext,
    get_current_session,
    require_session_roles,
)
from app.models import (
    ErrorResponse,
    RuleCreateRequest,
    RuleListResponse,
    RuleResponse,
    RuleUpdateRequest,
)
from app.services.action_engine import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    update_rule,
)
from app.services.db import get_db

router = APIRouter(prefix="/rules", tags=["rules"])

RULE_READ_ROLES = {"hr_admin", "it_admin"}
IT_ADMIN_ROLES = {"it_admin"}


def _validate_rule_patch_permissions(
    session: SessionContext,
    payload: RuleUpdateRequest,
) -> None:
    if session.role == "it_admin":
        return

    require_session_roles(session, RULE_READ_ROLES)
    provided_fields = set(payload.model_dump(exclude_none=True).keys())
    allowed_fields = {"is_enabled"}

    if provided_fields and not provided_fields.issubset(allowed_fields):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "HR Admin can only toggle `is_enabled`. Rule template changes "
                "must be performed by IT Admin."
            ),
        )


@router.get(
    "",
    response_model=RuleListResponse,
    status_code=status.HTTP_200_OK,
    summary="List rules",
    description=(
        "Lists action-generation rules for the current company. Access is "
        "limited to HR Admin and IT Admin roles."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read rules.",
        },
    },
)
async def list_rules_route(
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> RuleListResponse:
    require_session_roles(session, RULE_READ_ROLES)
    return await list_rules(db, session.company_id)


@router.get(
    "/{rule_id}",
    response_model=RuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Get rule details",
    description="Returns one rule definition and its mapped action templates.",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to read rules.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Rule was not found in the current company scope.",
        },
    },
)
async def get_rule_route(
    rule_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    require_session_roles(session, RULE_READ_ROLES)
    return await get_rule(db, rule_id, session.company_id)


@router.post(
    "",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create rule",
    description=(
        "Creates one rule and its mapped action templates. This route is "
        "restricted to IT Admin because it defines technical action behavior."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to create rules.",
        },
    },
)
async def create_rule_route(
    payload: RuleCreateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    require_session_roles(session, IT_ADMIN_ROLES)
    return await create_rule(db, session.company_id, payload)


@router.patch(
    "/{rule_id}",
    response_model=RuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Update rule",
    description=(
        "Updates one rule. HR Admin can toggle `is_enabled`, while IT Admin can "
        "change the full rule configuration."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to update this rule.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Rule was not found in the current company scope.",
        },
    },
)
async def update_rule_route(
    rule_id: UUID,
    payload: RuleUpdateRequest,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    _validate_rule_patch_permissions(session, payload)
    return await update_rule(db, rule_id, session.company_id, payload)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete rule",
    description="Deletes one rule and its mapped action templates.",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "Current role is not allowed to delete rules.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Rule was not found in the current company scope.",
        },
    },
)
async def delete_rule_route(
    rule_id: UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_session_roles(session, IT_ADMIN_ROLES)
    await delete_rule(db, rule_id, session.company_id)
