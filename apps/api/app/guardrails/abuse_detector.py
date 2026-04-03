"""Content abuse detector.

Detects repetitive messages, gibberish (high entropy noise), and
escalates based on abuse count.
"""

from __future__ import annotations

import hashlib
import math
import time

from app.services.redis import get_redis

_REPEAT_WINDOW_SECONDS = 300   # 5 minutes
_REPEAT_THRESHOLD = 3
_COOLDOWN_SECONDS = 1800       # 30 minutes

_GIBBERISH_ENTROPY_THRESHOLD = 4.8  # bits per char; high = likely random


def _message_hash(message: str) -> str:
    """Stable hash of normalized message for deduplication."""
    normalized = " ".join(message.lower().strip().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _compute_entropy(text: str) -> float:
    """Shannon entropy in bits per character."""
    if not text:
        return 0.0
    freq: dict[str, int] = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    total = len(text)
    entropy = 0.0
    for count in freq.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def _is_gibberish(message: str) -> bool:
    """Simple entropy-based gibberish detection."""
    words = message.split()
    if len(words) < 3:
        return False
    # Only consider long messages for entropy check
    if len(message) < 20:
        return False
    entropy = _compute_entropy(message)
    return entropy > _GIBBERISH_ENTROPY_THRESHOLD


async def check_abuse(
    company_id: str,
    employee_id: str,
    message: str,
) -> tuple[bool, str | None, str]:
    """Check for abuse patterns.

    Returns (is_cooldown_active, event_type | None, action_taken).
    """
    redis = get_redis()
    now = time.time()

    # Check if in cooldown
    cooldown_key = f"abuse:cooldown:{company_id}:{employee_id}"
    in_cooldown = await redis.exists(cooldown_key)
    if in_cooldown:
        return True, "abuse_warned", "cooldown_applied"

    # Check gibberish
    if _is_gibberish(message):
        return False, "abuse_warned", "warned"

    # Check repetitive messages
    msg_hash = _message_hash(message)
    repeat_key = f"abuse:repeat:{company_id}:{employee_id}"
    window_start = now - _REPEAT_WINDOW_SECONDS

    pipe = redis.pipeline()
    pipe.zremrangebyscore(repeat_key, "-inf", window_start)
    pipe.zrangebyscore(repeat_key, window_start, "+inf")
    pipe.zadd(repeat_key, {f"{msg_hash}:{now}": now})
    pipe.expire(repeat_key, _REPEAT_WINDOW_SECONDS + 60)
    results = await pipe.execute()

    recent_hashes: list[str] = results[1]
    recent_msg_hashes = [h.split(":")[0] for h in recent_hashes]
    repeat_count = recent_msg_hashes.count(msg_hash)

    if repeat_count >= _REPEAT_THRESHOLD:
        # Apply cooldown
        await redis.setex(cooldown_key, _COOLDOWN_SECONDS, "1")
        return True, "abuse_warned", "cooldown_applied"

    return False, None, "allowed"
