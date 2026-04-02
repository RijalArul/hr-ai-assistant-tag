from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    SessionContext,
    create_access_token,
    get_current_session,
)
from app.services.auth import authenticate_employee_by_email
from app.services.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Could not validate credentials.",
            }
        }
    )

    detail: str


class ValidationErrorItem(BaseModel):
    type: str
    loc: list[str | int]
    msg: str
    input: object | None = None


class ValidationErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["body", "email"],
                        "msg": "Value error, email must be a valid email address",
                        "input": "not-an-email",
                    }
                ]
            }
        }
    )

    detail: list[ValidationErrorItem]


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "fakhrul.rijal@majubersama.id",
            }
        }
    )

    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("email must be a valid email address")
        return normalized


class LoginResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "<jwt-access-token>",
                "token_type": "bearer",
                "session": {
                    "employee_id": "20000000-0000-0000-0000-000000000004",
                    "company_id": "00000000-0000-0000-0000-000000000001",
                    "email": "fakhrul.rijal@majubersama.id",
                    "role": "employee",
                },
            }
        }
    )

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    session: SessionContext


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Login with employee email",
    description=(
        "Simple Phase 1 login endpoint. The API looks up an employee by email, "
        "then returns a JWT bearer token containing trusted session context. "
        "The returned `employee_id` and `company_id` should be treated as the "
        "only trusted identity source for downstream HR data access."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Email was not found in the employee table.",
        },
        409: {
            "model": ErrorResponse,
            "description": (
                "The same email exists in multiple companies, so the API refuses "
                "to create an ambiguous session."
            ),
        },
        422: {
            "model": ValidationErrorResponse,
            "description": "Request body validation failed.",
        },
    },
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    session = await authenticate_employee_by_email(db, payload.email)
    access_token = create_access_token(session)
    return LoginResponse(access_token=access_token, session=session)


@router.get(
    "/me",
    response_model=SessionContext,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated session",
    description=(
        "Returns the trusted session context extracted from the bearer token. "
        "Use this endpoint to validate that the token is still valid and to "
        "confirm which `employee_id` and `company_id` are active in the current session."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing, malformed, expired, or invalid bearer token.",
        }
    },
)
async def me(
    session: SessionContext = Depends(get_current_session),
) -> SessionContext:
    return session
