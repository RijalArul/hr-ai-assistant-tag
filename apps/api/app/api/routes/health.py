from typing import Literal
from inspect import isawaitable

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.services.cache import get_cache_health
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
                "lru_cache": "ok",
            }
        }
    )

    status: Literal["ok", "degraded"]
    database: str
    redis: str
    lru_cache: str


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health check",
    description=(
        "Checks API dependencies used in Phase 1. The endpoint always returns 200, "
        "then reports `status = degraded` when PostgreSQL, Redis, or the in-memory "
        "LRU cache layer cannot be reached."
    ),
)
async def health() -> HealthResponse:
    overall_status: Literal["ok", "degraded"] = "ok"
    database_status = "ok"
    redis_status = "ok"
    lru_cache_status = "ok"

    # Check database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        database_status = f"error: {e}"
        overall_status = "degraded"

    # Check Redis
    try:
        redis = get_redis()
        ping_result = redis.ping()
        if isawaitable(ping_result):
            await ping_result
    except Exception as e:
        redis_status = f"error: {e}"
        overall_status = "degraded"

    # Check LRU cache registry
    try:
        cache_health = get_cache_health()
        cache_status = cache_health.get("status")
        if not isinstance(cache_status, str):
            raise RuntimeError("Cache health status is unavailable.")
        lru_cache_status = cache_status
    except Exception as e:
        lru_cache_status = f"error: {e}"
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        database=database_status,
        redis=redis_status,
        lru_cache=lru_cache_status,
    )
