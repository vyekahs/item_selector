"""Unit tests for :class:`InMemoryTokenBucket`.

Coupang Partners preset (capacity=10, refill=10/hour). We test:

1. Ten ``acquire(block=False)`` calls succeed.
2. The eleventh raises :class:`RateLimitError` immediately.
3. Advancing wall-clock by 6 minutes refills a single token, letting the
   next ``acquire`` succeed.

All async work happens inside a single ``asyncio.run`` per test so the
``asyncio.Lock`` binds to exactly one event loop.
"""
from __future__ import annotations

import asyncio

import pytest
from freezegun import freeze_time

from app.clients.base import RateLimitError
from app.ratelimit.rate_limiter import (
    InMemoryTokenBucket,
    build_coupang_bucket,
)


def test_ten_acquires_succeed_then_eleventh_fails():
    """Coupang Partners quota: 10 req/h."""

    async def scenario() -> None:
        with freeze_time("2026-04-18 10:00:00"):
            bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
            for _ in range(10):
                await bucket.acquire(block=False)
            with pytest.raises(RateLimitError):
                await bucket.acquire(block=False)

    asyncio.run(scenario())


def test_bucket_refills_after_time_passes():

    async def scenario() -> None:
        with freeze_time("2026-04-18 10:00:00") as frozen:
            bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
            for _ in range(10):
                await bucket.acquire(block=False)
            with pytest.raises(RateLimitError):
                await bucket.acquire(block=False)

            # 6 minutes of wall-clock → exactly 1 token at 10/h.
            frozen.tick(delta=6 * 60)
            await bucket.acquire(block=False)

            # The single refilled token is now consumed — empty again.
            with pytest.raises(RateLimitError):
                await bucket.acquire(block=False)

    asyncio.run(scenario())


def test_bucket_rejects_invalid_config():
    with pytest.raises(ValueError):
        InMemoryTokenBucket(capacity=0, refill_per_hour=10)
    with pytest.raises(ValueError):
        InMemoryTokenBucket(capacity=10, refill_per_hour=0)


def test_peek_tokens_does_not_consume():

    async def scenario() -> None:
        with freeze_time("2026-04-18 10:00:00"):
            bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
            assert bucket.peek_tokens() == pytest.approx(10.0)
            # Still able to drain all 10 afterwards.
            for _ in range(10):
                await bucket.acquire(block=False)

    asyncio.run(scenario())


def test_block_false_raises_immediately_when_empty():

    async def scenario() -> None:
        with freeze_time("2026-04-18 10:00:00"):
            bucket = InMemoryTokenBucket(capacity=1, refill_per_hour=1)
            await bucket.acquire(block=False)
            with pytest.raises(RateLimitError):
                await bucket.acquire(block=False)

    asyncio.run(scenario())


# ---- factory --------------------------------------------------------


def test_build_coupang_bucket_returns_preset_capacity():
    """Spec §3.4: Coupang Partners = 10 requests per hour."""
    bucket = build_coupang_bucket(prefer_memory=True)
    assert isinstance(bucket, InMemoryTokenBucket)
    assert bucket.capacity == 10
    assert bucket.refill_per_hour == 10
