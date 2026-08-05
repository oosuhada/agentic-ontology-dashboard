"""Rate limiting primitives shared by the canonical application runtime."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int


class RateLimitExceeded(RuntimeError):
    def __init__(self, *, bucket: str, retry_after: int) -> None:
        super().__init__(f"rate limit exceeded for {bucket}")
        self.bucket = bucket
        self.retry_after = max(1, retry_after)


class RateLimiter:
    """Synchronous limiter contract used by FastAPI dependencies."""

    @staticmethod
    def anonymized_key(*parts: str) -> str:
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def check(self, *, bucket: str, subject: str, rule: RateLimitRule) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class InMemoryRateLimiter(RateLimiter):
    """Single-process fixed-window limiter for the MVP API surface.

    Production multi-instance deployments should replace this with a shared Redis-backed limiter.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, *, bucket: str, subject: str, rule: RateLimitRule) -> None:
        now = time.monotonic()
        key = f"{bucket}:{subject}"
        threshold = now - rule.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= rule.limit:
                retry_after = int(rule.window_seconds - (now - events[0])) + 1
                raise RateLimitExceeded(bucket=bucket, retry_after=retry_after)
            events.append(now)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class RedisRateLimiter(RateLimiter):
    """Redis-backed fixed-window limiter shared by all API instances."""

    _SCRIPT = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
      redis.call('PEXPIRE', KEYS[1], ARGV[1])
    end
    local ttl = redis.call('PTTL', KEYS[1])
    return {current, ttl}
    """

    def __init__(self, redis_url: str, *, prefix: str = "ontology-dashboard:rate") -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "Redis rate limiting requires the api[production] optional dependency"
            ) from exc
        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )
        self.prefix = prefix.rstrip(":")
        self._script = self.client.register_script(self._SCRIPT)

    def check(self, *, bucket: str, subject: str, rule: RateLimitRule) -> None:
        key = f"{self.prefix}:{bucket}:{subject}"
        current, ttl_ms = self._script(
            keys=[key],
            args=[rule.window_seconds * 1000],
        )
        if int(current) > rule.limit:
            retry_after = max(1, (max(0, int(ttl_ms)) + 999) // 1000)
            raise RateLimitExceeded(bucket=bucket, retry_after=retry_after)

    def clear(self) -> None:
        cursor = 0
        pattern = f"{self.prefix}:*"
        while True:
            cursor, keys = self.client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                self.client.delete(*keys)
            if cursor == 0:
                break


LOGIN_RATE = RateLimitRule(limit=12, window_seconds=60)
PLANNER_RATE = RateLimitRule(limit=30, window_seconds=60)
EXPORT_RATE = RateLimitRule(limit=20, window_seconds=60)
SESSION_RATE = RateLimitRule(limit=20, window_seconds=60)
