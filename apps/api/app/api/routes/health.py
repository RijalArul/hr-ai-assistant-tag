from fastapi import APIRouter
from sqlalchemy import text

from app.services.db import AsyncSessionLocal
from app.services.redis import get_redis

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict:
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

    return result
