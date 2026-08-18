from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

import redis

from .config import Settings


T = TypeVar("T")


class ResponseCache:
    """Small JSON cache backed by the platform-specific Redis instance.

    A process-local TTL cache keeps read APIs available if Redis is restarting;
    Redis failures never make the monitoring platform unavailable.
    """

    def __init__(self, settings: Settings):
        self.ttl = max(1, settings.cache_ttl_seconds)
        self.client = redis.Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1) if settings.redis_url else None
        self.local: dict[str, tuple[float, Any]] = {}
        self.lock = threading.Lock()

    def get_or_set(self, key: str, factory: Callable[[], T], ttl: int | None = None) -> T:
        lifetime = ttl or self.ttl
        if self.client:
            try:
                cached = self.client.get(key)
                if cached is not None:
                    return json.loads(cached)
            except redis.RedisError:
                pass
        now = time.monotonic()
        with self.lock:
            local = self.local.get(key)
            if local and local[0] > now:
                return local[1]
        value = factory()
        with self.lock:
            self.local[key] = (now + lifetime, value)
        if self.client:
            try:
                self.client.setex(key, lifetime, json.dumps(value, ensure_ascii=False, default=str))
            except redis.RedisError:
                pass
        return value

    def invalidate(self, prefix: str = "") -> None:
        with self.lock:
            self.local = {key: value for key, value in self.local.items() if not key.startswith(prefix)}
        if self.client and prefix:
            try:
                for key in self.client.scan_iter(match=f"{prefix}*"):
                    self.client.delete(key)
            except redis.RedisError:
                pass

    def close(self) -> None:
        if self.client:
            self.client.close()
