"""Rate-limiter package.

Currently exposes a Redis-backed (or in-memory) token-bucket suitable
for the Coupang Partners "10 requests per hour" window. Other clients
that have daily quotas use the simpler DB cache to amortise calls and
typically don't need a hot-path rate limiter.
"""
from __future__ import annotations

from .rate_limiter import (
    InMemoryTokenBucket,
    RedisTokenBucket,
    TokenBucket,
    build_coupang_bucket,
)

__all__ = [
    "InMemoryTokenBucket",
    "RedisTokenBucket",
    "TokenBucket",
    "build_coupang_bucket",
]
