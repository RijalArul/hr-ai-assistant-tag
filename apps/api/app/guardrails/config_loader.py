"""Per-company guardrail config loader.

Reads config from Redis cache (fast path) or PostgreSQL (fallback).
Falls back to safe defaults if no company config exists.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.guardrails.models import (
    GuardrailConfig,
    HallucinationCheckConfig,
    PiiPatternConfig,
    RateLimitConfig,
    SensitivityOverrideConfig,
    ToneCheckConfig,
)
from app.services.redis import get_redis

_CACHE_TTL = 300  # 5 minutes


def _cache_key(company_id: str) -> str:
    return f"guardrail:config:{company_id}"


def _default_config(company_id: str) -> GuardrailConfig:
    return GuardrailConfig(company_id=company_id)


async def load_config(
    db: AsyncSession,
    company_id: str,
) -> GuardrailConfig:
    """Load guardrail config for a company.

    Redis cache → DB → defaults.
    """
    redis = get_redis()
    cache_key = _cache_key(company_id)

    cached = await redis.get(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            return GuardrailConfig.model_validate(data)
        except Exception:
            pass

    # Try DB
    try:
        result = await db.execute(
            text(
                "SELECT config_json, updated_at FROM guardrail_configs "
                "WHERE company_id = :company_id LIMIT 1"
            ),
            {"company_id": company_id},
        )
        row = result.fetchone()
        if row:
            config_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            config_data["company_id"] = company_id
            config_data["updated_at"] = row[1].isoformat() if row[1] else None
            config = GuardrailConfig.model_validate(config_data)
            await redis.setex(cache_key, _CACHE_TTL, config.model_dump_json())
            return config
    except Exception:
        pass

    return _default_config(company_id)


async def save_config(
    db: AsyncSession,
    company_id: str,
    config: GuardrailConfig,
) -> GuardrailConfig:
    """Upsert guardrail config and invalidate Redis cache."""
    config_dict = config.model_dump(exclude={"company_id", "updated_at"})
    config_json = json.dumps(config_dict)
    now = datetime.now(UTC)

    await db.execute(
        text(
            "INSERT INTO guardrail_configs (company_id, config_json, updated_at) "
            "VALUES (:company_id, :config_json, :now) "
            "ON CONFLICT (company_id) DO UPDATE SET "
            "config_json = EXCLUDED.config_json, updated_at = EXCLUDED.updated_at"
        ),
        {"company_id": company_id, "config_json": config_json, "now": now},
    )
    await db.commit()

    redis = get_redis()
    await redis.delete(_cache_key(company_id))

    config.updated_at = now
    return config
