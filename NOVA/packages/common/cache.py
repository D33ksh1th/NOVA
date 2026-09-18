"""
Optional Redis-backed JSON cache with graceful fallback.
"""

from __future__ import annotations

import json
from fnmatch import fnmatch
from threading import Lock
from typing import Any, Optional

from packages.common.logger import logger
from packages.config import settings

try:
    import redis
except Exception:  # pragma: no cover
    redis = None  # type: ignore


class CacheClient:
    def __init__(self) -> None:
        self._lock = Lock()
        self._redis: Optional[Any] = None
        self._warned_unavailable = False

    @property
    def enabled(self) -> bool:
        return bool(settings.REDIS_ENABLED)

    def _key(self, key: str) -> str:
        prefix = (settings.REDIS_KEY_PREFIX or "nova").strip() or "nova"
        return f"{prefix}:{key}"

    def _connect(self) -> Optional[Any]:
        if not self.enabled:
            return None
        if redis is None:
            if not self._warned_unavailable:
                logger.warning("Cache disabled: redis package not installed")
                self._warned_unavailable = True
            return None

        if self._redis is not None:
            return self._redis

        with self._lock:
            if self._redis is not None:
                return self._redis
            try:
                client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
                client.ping()
                self._redis = client
                logger.info("Redis cache connected", url=settings.REDIS_URL)
            except Exception as exc:
                if not self._warned_unavailable:
                    logger.warning("Redis unavailable; using direct mode", error=str(exc))
                    self._warned_unavailable = True
                self._redis = None
        return self._redis

    def get_json(self, key: str) -> Optional[Any]:
        client = self._connect()
        if client is None:
            return None
        try:
            raw = client.get(self._key(key))
            if not raw:
                return None
            return json.loads(raw)
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        client = self._connect()
        if client is None:
            return
        try:
            client.setex(self._key(key), max(1, int(ttl_seconds)), json.dumps(value))
        except Exception:
            return

    def delete(self, key: str) -> None:
        client = self._connect()
        if client is None:
            return
        try:
            client.delete(self._key(key))
        except Exception:
            return

    def delete_pattern(self, pattern: str) -> None:
        client = self._connect()
        if client is None:
            return
        full_pattern = self._key(pattern)
        try:
            if hasattr(client, "scan_iter"):
                keys = list(client.scan_iter(match=full_pattern, count=200))
            else:
                keys = [k for k in (client.keys() or []) if fnmatch(str(k), full_pattern)]
            if keys:
                client.delete(*keys)
        except Exception:
            return


cache = CacheClient()
