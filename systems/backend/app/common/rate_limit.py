"""Rate-limit policy contract shared by routers and infrastructure adapters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .exceptions import RateLimitExceeded


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int


LOGIN_RATE = RateLimitRule(limit=12, window_seconds=60)
SESSION_RATE = RateLimitRule(limit=20, window_seconds=60)
PLANNER_RATE = RateLimitRule(limit=30, window_seconds=60)
EXPORT_RATE = RateLimitRule(limit=20, window_seconds=60)


class RateLimiter:
    """Synchronous limiter port used by HTTP dependencies."""

    @staticmethod
    def anonymized_key(*parts: str) -> str:
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def check(self, *, bucket: str, subject: str, rule: RateLimitRule) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


__all__ = [
    "EXPORT_RATE",
    "LOGIN_RATE",
    "PLANNER_RATE",
    "RateLimitExceeded",
    "RateLimiter",
    "RateLimitRule",
    "SESSION_RATE",
]
