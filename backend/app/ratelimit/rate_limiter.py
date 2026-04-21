"""Token-bucket rate limiter with Redis + in-memory back ends.

Primary consumer: :class:`app.clients.coupang_partners.RealCoupangPartnersClient`
(Coupang Partners Search API allows **10 requests per hour**). The
bucket refills linearly at ``refill_per_hour / 3600`` tokens/second up
to ``capacity``.

Design decisions
----------------
* **Redis is authoritative** when ``REDIS_URL`` is reachable so
  multiple worker processes (Scheduler + API) share the same quota.
* If Redis is down, :func:`build_coupang_bucket` falls back to the
  in-memory implementation so a single-process dev run still works
  (with the caveat that quotas are not shared). A log line makes this
  visible.
* ``acquire(block=False)`` raises :class:`~app.clients.base.RateLimitError`
  immediately when empty; ``acquire(block=True)`` sleeps until a token
  is available.
* Time is read via :func:`time.time` / :func:`asyncio.sleep` so
  ``freezegun`` works for deterministic tests.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Protocol

try:  # pragma: no cover - optional dep guard
    import redis
    import redis.exceptions
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]

from app.clients.base import RateLimitError

logger = logging.getLogger(__name__)


class TokenBucket(Protocol):
    """Minimal token-bucket surface every back end implements."""

    capacity: int
    refill_per_hour: int

    async def acquire(self, block: bool = True, timeout: float | None = None) -> None:
        """Consume one token. Raise :class:`RateLimitError` when unavailable.

        * ``block=True``  (default): sleep until a token is ready, or up
          to ``timeout`` seconds. Raises ``RateLimitError`` on timeout.
        * ``block=False``: return immediately with success, or raise
          ``RateLimitError`` if the bucket is empty right now.
        """
        ...

    def peek_tokens(self) -> float:
        """Return the current token count (for tests / introspection)."""
        ...


# ---- in-memory back end --------------------------------------------


class InMemoryTokenBucket:
    """Single-process token bucket.

    Not safe across processes -- use :class:`RedisTokenBucket` in
    production. This class is used by tests and as the automatic
    fallback when Redis is unreachable.
    """

    def __init__(self, capacity: int, refill_per_hour: int):
        if capacity <= 0 or refill_per_hour <= 0:
            raise ValueError("capacity and refill_per_hour must be positive")
        self.capacity = capacity
        self.refill_per_hour = refill_per_hour
        self._tokens: float = float(capacity)
        self._last_refill: float = time.time()
        self._lock = asyncio.Lock()

    @property
    def _refill_rate_per_sec(self) -> float:
        return self.refill_per_hour / 3600.0

    def _refill(self) -> None:
        """Add tokens based on wall-clock elapsed time since last refill."""
        now = time.time()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed <= 0:
            return
        self._tokens = min(
            float(self.capacity),
            self._tokens + elapsed * self._refill_rate_per_sec,
        )
        self._last_refill = now

    def peek_tokens(self) -> float:
        self._refill()
        return self._tokens

    async def acquire(self, block: bool = True, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.time() + timeout
        # Polling interval kept small so tests (freezegun + tick) are
        # responsive. Real usage is rare so overhead is negligible.
        poll = 0.05

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                missing = 1.0 - self._tokens
                wait_for = missing / self._refill_rate_per_sec

            if not block:
                raise RateLimitError(
                    f"bucket empty (capacity={self.capacity}, "
                    f"refill_per_hour={self.refill_per_hour})"
                )
            if deadline is not None and time.time() >= deadline:
                raise RateLimitError(
                    f"timeout while waiting for token (waited {timeout}s)"
                )
            await asyncio.sleep(min(poll, wait_for))


# ---- Redis back end ------------------------------------------------


class RedisTokenBucket:
    """Redis-backed token bucket using two keys per bucket:

    * ``<prefix>:tokens``       current token count (float, atomic via Lua)
    * ``<prefix>:last_refill``  unix timestamp of last refill

    We keep the Lua script inline and tiny -- it refills based on
    elapsed time, then decrements if a token is available, returning
    the new count. Atomicity means multiple workers can safely race.
    """

    _LUA_ACQUIRE = """
    local tokens_key = KEYS[1]
    local ts_key = KEYS[2]
    local now = tonumber(ARGV[1])
    local capacity = tonumber(ARGV[2])
    local rate = tonumber(ARGV[3])  -- tokens per second

    local tokens = tonumber(redis.call('GET', tokens_key) or capacity)
    local last = tonumber(redis.call('GET', ts_key) or now)

    local elapsed = math.max(0, now - last)
    tokens = math.min(capacity, tokens + elapsed * rate)

    local allowed = 0
    if tokens >= 1 then
        tokens = tokens - 1
        allowed = 1
    end

    redis.call('SET', tokens_key, tokens)
    redis.call('SET', ts_key, now)
    return {allowed, tostring(tokens)}
    """

    def __init__(
        self,
        client: "redis.Redis",  # type: ignore[name-defined]
        key_prefix: str,
        capacity: int,
        refill_per_hour: int,
    ):
        if redis is None:  # pragma: no cover
            raise RuntimeError("redis-py is not installed")
        if capacity <= 0 or refill_per_hour <= 0:
            raise ValueError("capacity and refill_per_hour must be positive")
        self._redis = client
        self._prefix = key_prefix
        self.capacity = capacity
        self.refill_per_hour = refill_per_hour
        self._script = self._redis.register_script(self._LUA_ACQUIRE)

    @property
    def _refill_rate_per_sec(self) -> float:
        return self.refill_per_hour / 3600.0

    def _keys(self) -> tuple[str, str]:
        return f"{self._prefix}:tokens", f"{self._prefix}:last_refill"

    def _run_script(self) -> tuple[int, float]:
        now = time.time()
        k1, k2 = self._keys()
        allowed, tokens = self._script(
            keys=[k1, k2],
            args=[now, self.capacity, self._refill_rate_per_sec],
        )
        return int(allowed), float(tokens)

    def peek_tokens(self) -> float:
        """Non-consuming estimate. Triggers a refill but no decrement.

        We do this by calling the script once, then putting the token
        back. For diagnostics only; tests should use the in-memory
        bucket for exact accounting.
        """
        allowed, tokens = self._run_script()
        if allowed:
            # Put it back
            k1, _ = self._keys()
            self._redis.incrbyfloat(k1, 1.0)
            tokens += 1.0
        return tokens

    async def acquire(self, block: bool = True, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.time() + timeout
        poll = 0.5  # Redis round-trip is more expensive than in-memory

        while True:
            try:
                allowed, tokens = self._run_script()
            except (redis.exceptions.RedisError, OSError) as exc:  # type: ignore[union-attr]
                # On Redis unavailability we fail closed -- callers can
                # decide whether to retry. Better than silently letting
                # the quota blow through.
                raise RateLimitError(f"redis unavailable: {exc}") from exc

            if allowed:
                return

            if not block:
                raise RateLimitError(
                    f"bucket empty (capacity={self.capacity}, "
                    f"tokens={tokens:.3f})"
                )
            if deadline is not None and time.time() >= deadline:
                raise RateLimitError(
                    f"timeout while waiting for token (waited {timeout}s)"
                )
            # Sleep for *at most* the time to the next token, capped at poll.
            missing = 1.0 - tokens
            wait_for = max(0.01, missing / self._refill_rate_per_sec)
            await asyncio.sleep(min(poll, wait_for))


# ---- factory -------------------------------------------------------


def build_coupang_bucket(
    redis_url: str | None = None,
    *,
    prefer_memory: bool = False,
) -> TokenBucket:
    """Return a rate limiter sized for Coupang Partners Search API.

    Capacity 10, refill 10/hour (§3.4 of the spec).

    * Uses Redis at ``redis_url`` or ``REDIS_URL`` when available.
    * Falls back to in-memory if Redis is unreachable or the caller
      explicitly requests ``prefer_memory=True`` (useful for tests).
    """
    capacity = 10
    refill = 10
    key_prefix = "ratelimit:coupang_partners"

    if prefer_memory or redis is None:
        return InMemoryTokenBucket(capacity=capacity, refill_per_hour=refill)

    url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
    except Exception as exc:
        logger.warning("Redis unreachable (%s); falling back to in-memory bucket", exc)
        return InMemoryTokenBucket(capacity=capacity, refill_per_hour=refill)

    return RedisTokenBucket(
        client=client,
        key_prefix=key_prefix,
        capacity=capacity,
        refill_per_hour=refill,
    )
