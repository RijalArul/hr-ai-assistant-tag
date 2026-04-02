from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Generic, TypeVar

from app.core.config import get_settings

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class LRUCache(Generic[T]):
    def __init__(self, max_entries: int, ttl_seconds: int) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None

            if entry.expires_at < monotonic():
                self._entries.pop(key, None)
                return None

            self._entries.move_to_end(key)
            return entry.value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._entries[key] = CacheEntry(
                value=value,
                expires_at=monotonic() + self.ttl_seconds,
            )
            self._entries.move_to_end(key)
            self._evict_if_needed()

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._prune_expired()
            return {
                "size": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }

    def _evict_if_needed(self) -> None:
        self._prune_expired()
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def _prune_expired(self) -> None:
        now = monotonic()
        expired_keys = [
            key for key, entry in self._entries.items() if entry.expires_at < now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)


settings = get_settings()
_cache_registry: dict[str, LRUCache[object]] | None = None


def init_cache_registry() -> dict[str, LRUCache[object]]:
    global _cache_registry
    if _cache_registry is None:
        _cache_registry = {
            "employee_profile": LRUCache(
                max_entries=settings.lru_cache_max_entries,
                ttl_seconds=settings.lru_cache_ttl_seconds,
            ),
            "personal_info": LRUCache(
                max_entries=settings.lru_cache_max_entries,
                ttl_seconds=settings.lru_cache_ttl_seconds,
            ),
            "company_rules": LRUCache(
                max_entries=settings.lru_cache_max_entries,
                ttl_seconds=settings.lru_cache_ttl_seconds,
            ),
        }
    return _cache_registry


def get_cache(name: str) -> LRUCache[object]:
    registry = init_cache_registry()
    try:
        return registry[name]
    except KeyError as exc:
        raise KeyError(f"Unknown cache namespace: {name}") from exc


def get_cache_registry() -> dict[str, LRUCache[object]]:
    return init_cache_registry()


def close_cache_registry() -> None:
    global _cache_registry
    if _cache_registry is not None:
        for cache in _cache_registry.values():
            cache.clear()
        _cache_registry = None


def get_cache_health() -> dict[str, object]:
    registry = init_cache_registry()
    return {
        "status": "ok",
        "namespaces": sorted(registry.keys()),
        "stats": {name: cache.stats() for name, cache in registry.items()},
    }
