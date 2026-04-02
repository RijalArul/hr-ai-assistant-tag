from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.services.db import AsyncSessionLocal
from app.services.redis import get_redis

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "database": "ok",
                "redis": "ok",
            }
        }
    )

    status: Literal["ok", "degraded"]
    database: str
    redis: str


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health check",
    description=(
        "Checks API dependencies used in Phase 1. The endpoint always returns 200, "
        "then reports `status = degraded` when PostgreSQL or Redis cannot be reached."
    ),
)
async def health() -> HealthResponse:
    result = {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
    }

    # Check database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        result["database"] = f"error: {e}"
        result["status"] = "degraded"

    # Check Redis
    try:
        redis = get_redis()
        await redis.ping()
    except Exception as e:
        result["redis"] = f"error: {e}"
        result["status"] = "degraded"

    return HealthResponse(**result)
