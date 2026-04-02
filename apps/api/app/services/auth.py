from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext


async def authenticate_employee_by_email(
    db: AsyncSession,
    email: str,
) -> SessionContext:
    result = await db.execute(
        text(
            """
            SELECT
                id::text AS employee_id,
                company_id::text AS company_id,
                lower(email) AS email,
                role
            FROM employees
            WHERE lower(email) = :email
            ORDER BY created_at ASC
            LIMIT 2
            """
        ),
        {"email": email},
    )
    rows = result.mappings().all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email.",
        )

    if len(rows) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Email matches multiple companies. Phase 1 login expects a "
                "globally unique company email."
            ),
        )

    return SessionContext.model_validate(rows[0])
