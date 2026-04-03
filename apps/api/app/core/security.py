from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


class SessionContext(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "employee_id": "20000000-0000-0000-0000-000000000004",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "email": "fakhrul.rijal@majubersama.id",
                "role": "employee",
            }
        }
    )

    employee_id: str
    company_id: str
    email: str
    role: str


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(session: SessionContext) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": session.employee_id,
        "company_id": session.company_id,
        "email": session.email,
        "role": session.role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> SessionContext:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise _credentials_exception() from exc

    employee_id = payload.get("sub")
    company_id = payload.get("company_id")
    email = payload.get("email")
    role = payload.get("role")

    if not all([employee_id, company_id, email, role]):
        raise _credentials_exception()

    return SessionContext(
        employee_id=employee_id,
        company_id=company_id,
        email=email,
        role=role,
    )


async def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> SessionContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _credentials_exception()

    return decode_access_token(credentials.credentials)


def require_session_roles(
    session: SessionContext,
    allowed_roles: set[str],
) -> SessionContext:
    if session.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource.",
        )
    return session
