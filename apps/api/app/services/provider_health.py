from __future__ import annotations

from app.services.cache import get_cache

DEFAULT_PROVIDER_CIRCUIT_SECONDS = 45


def get_open_circuit_reason(provider_name: str) -> str | None:
    cache = get_cache("provider_health")
    payload = cache.get(f"circuit:{provider_name}")
    if isinstance(payload, dict):
        reason = payload.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return None


def open_provider_circuit(
    provider_name: str,
    reason: str,
    *,
    ttl_seconds: int = DEFAULT_PROVIDER_CIRCUIT_SECONDS,
) -> None:
    cache = get_cache("provider_health")
    cache.set(
        f"circuit:{provider_name}",
        {"reason": reason.strip()},
        ttl_seconds=ttl_seconds,
    )


def close_provider_circuit(provider_name: str) -> None:
    cache = get_cache("provider_health")
    cache.delete(f"circuit:{provider_name}")
