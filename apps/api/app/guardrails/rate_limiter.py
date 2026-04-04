"""Redis sliding window rate limiter.

Key pattern: rate:{company_id}:{employee_id}:{action_type}
Window entries are stored as sorted set with timestamp as score.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from app.services.redis import get_redis
from app.guardrails.models import RateLimitConfig, RateLimitEntry


_WINDOWS: dict[str, int] = {
    "messages": 3600,          # 1 hour
    "conversations_new": 86400,  # 1 day
    "file_uploads": 3600,       # 1 hour
    "auth_failed": 900,         # 15 minutes
}


def _key(company_id: str, employee_id: str, action_type: str) -> str:
    return f"rate:{company_id}:{employee_id}:{action_type}"


async def check_rate_limit(
    company_id: str,
    employee_id: str,
    action_type: str,
    config: RateLimitConfig,
) -> tuple[bool, int, int]:
    """Check and increment the sliding window counter.

    Returns (is_allowed, current_count, limit).
    Increments the counter if allowed.
    """
    limit = _get_limit(action_type, config)
    window_seconds = _WINDOWS.get(action_type, 3600)
    try:
        redis = get_redis()
    except RuntimeError:
        return True, 0, limit
    key = _key(company_id, employee_id, action_type)
    now = time.time()
    window_start = now - window_seconds

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", window_start)
    pipe.zcard(key)
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, window_seconds + 60)
    results = await pipe.execute()

    current_count = int(results[1])
    if current_count >= limit:
        # Remove the zadd we just did since we're blocking
        await redis.zremrangebyscore(key, now, now)
        return False, current_count, limit

    return True, current_count + 1, limit


async def get_rate_status(
    company_id: str,
    employee_id: str,
    config: RateLimitConfig,
) -> dict[str, RateLimitEntry]:
    """Return current rate status for all action types for one employee."""
    try:
        redis = get_redis()
    except RuntimeError:
        now = datetime.now(UTC)
        return {
            "messages_per_hour": RateLimitEntry(
                limit=config.messages_per_hour,
                current=0,
                remaining=config.messages_per_hour,
                resets_at=now + timedelta(seconds=3600),
            ),
            "conversations_per_day": RateLimitEntry(
                limit=config.conversations_per_day,
                current=0,
                remaining=config.conversations_per_day,
                resets_at=now + timedelta(seconds=86400),
            ),
            "file_uploads_per_hour": RateLimitEntry(
                limit=config.file_uploads_per_hour,
                current=0,
                remaining=config.file_uploads_per_hour,
                resets_at=now + timedelta(seconds=3600),
            ),
        }
    now = time.time()
    result: dict[str, RateLimitEntry] = {}

    action_map = {
        "messages": ("messages_per_hour", config.messages_per_hour, 3600),
        "conversations_new": ("conversations_per_day", config.conversations_per_day, 86400),
        "file_uploads": ("file_uploads_per_hour", config.file_uploads_per_hour, 3600),
    }

    for action_type, (label, limit, window_seconds) in action_map.items():
        key = _key(company_id, employee_id, action_type)
        window_start = now - window_seconds
        await redis.zremrangebyscore(key, "-inf", window_start)
        current = await redis.zcard(key)
        resets_at = datetime.now(UTC) + timedelta(seconds=window_seconds)
        result[label] = RateLimitEntry(
            limit=limit,
            current=int(current),
            remaining=max(0, limit - int(current)),
            resets_at=resets_at,
        )

    return result


def _get_limit(action_type: str, config: RateLimitConfig) -> int:
    if action_type == "messages":
        return config.messages_per_hour
    if action_type == "conversations_new":
        return config.conversations_per_day
    if action_type == "file_uploads":
        return config.file_uploads_per_hour
    if action_type == "auth_failed":
        return 5
    return 30
