"""Integration test: Mock clients plus the Postgres response cache.

This test emulates the consumer pattern the Scoring/Scheduler agents
will use — ``get_or_fetch(cache_key, client.fetch(...))``. It verifies
that the *first* call hits the client, the *second* call uses the
cached JSON, and that expiry causes another client hit.
"""
from __future__ import annotations

import asyncio

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.cache import ApiCacheStore
from app.clients.naver_searchad import MockNaverSearchAdClient


class _CountingClient:
    """Wraps a mock and records how many times ``fetch`` was invoked."""

    def __init__(self, inner: MockNaverSearchAdClient) -> None:
        self._inner = inner
        self.calls = 0
        self.cache_ttl = inner.cache_ttl

    async def fetch(self, keywords: list[str]):
        self.calls += 1
        return await self._inner.fetch(keywords)


async def _get_or_fetch(store: ApiCacheStore, client: _CountingClient, cache_key: str):
    cached = store.get(cache_key)
    if cached is not None:
        # Reconstruct DTOs from the cached JSON using the same parsing
        # path the mock uses. For this test we only need the raw dict.
        return cached
    dtos = await client.fetch(["x"])
    payload = {"items": [d.model_dump(mode="json") for d in dtos]}
    store.set(cache_key, payload, ttl_seconds=client.cache_ttl)
    return payload


def _run(coro):
    return asyncio.run(coro)


def test_cache_miss_calls_client_then_hit_avoids_call(db_session: Session) -> None:
    store = ApiCacheStore(db_session)
    client = _CountingClient(MockNaverSearchAdClient())

    with freeze_time("2026-04-18 10:00:00"):
        # Miss → client called once.
        _run(_get_or_fetch(store, client, "searchad:휴대용선풍기"))
        assert client.calls == 1

        # Hit → client NOT called again.
        _run(_get_or_fetch(store, client, "searchad:휴대용선풍기"))
        assert client.calls == 1


def test_cache_expiry_causes_refetch(db_session: Session) -> None:
    store = ApiCacheStore(db_session)
    # Force a tiny TTL so we don't need to advance 24h in the test.
    client = _CountingClient(MockNaverSearchAdClient())
    client.cache_ttl = 30

    with freeze_time("2026-04-18 10:00:00") as frozen:
        _run(_get_or_fetch(store, client, "k"))
        assert client.calls == 1

        # Still fresh.
        _run(_get_or_fetch(store, client, "k"))
        assert client.calls == 1

        # Expire the entry.
        frozen.tick(delta=45)
        _run(_get_or_fetch(store, client, "k"))
        assert client.calls == 2


def test_distinct_keys_are_cached_independently(db_session: Session) -> None:
    store = ApiCacheStore(db_session)
    client = _CountingClient(MockNaverSearchAdClient())

    with freeze_time("2026-04-18 10:00:00"):
        _run(_get_or_fetch(store, client, "k:a"))
        _run(_get_or_fetch(store, client, "k:b"))
        assert client.calls == 2

        _run(_get_or_fetch(store, client, "k:a"))
        _run(_get_or_fetch(store, client, "k:b"))
        assert client.calls == 2  # both cached
