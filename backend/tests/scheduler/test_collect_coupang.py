"""Tests for :class:`CollectCoupangJob`.

Key behavioural guarantees verified here:

* Respects the 10-req/hour token bucket — stops early once the bucket
  is empty, without sleeping.
* Caches the raw Coupang response under ``coupang:search:<term>``
  with a 24h TTL (spec §3.4).
* On cache hit for a term, does not call the upstream API.
"""
from __future__ import annotations

import asyncio

from app.cache.api_cache import ApiCacheStore
from app.contracts.dto import CoupangProductDTO, CoupangSearchDTO
from app.models import Keyword, KeywordStatus
from app.ratelimit.rate_limiter import InMemoryTokenBucket
from app.scheduler.jobs import CollectCoupangJob


class _StubCoupangClient:
    """Deterministic Coupang Partners stand-in."""

    cache_ttl = 86_400

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, query: str) -> CoupangSearchDTO:
        self.calls.append(query)
        return CoupangSearchDTO(
            query=query,
            items=[
                CoupangProductDTO(
                    product_id=f"p-{query}-1",
                    name=f"{query} A",
                    price=19_900,
                    rating=4.5,
                    review_count=123,
                    is_rocket=True,
                    category_path="반려동물>고양이",
                )
            ],
            avg_price=19_900,
            rocket_ratio=1.0,
        )


def _seed_keywords(session, terms: list[str]) -> None:
    for t in terms:
        session.add(Keyword(term=t, is_seed=True, status=KeywordStatus.ACTIVE))
    session.flush()


def test_collect_coupang_stops_when_bucket_empty(db_session):
    # 12 keywords, bucket holds only 10 tokens → 10 API calls max.
    terms = [f"kw-{i:02d}" for i in range(12)]
    _seed_keywords(db_session, terms)

    client = _StubCoupangClient()
    bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
    job = CollectCoupangJob(coupang_client=client, bucket=bucket, top_n=100)

    result = asyncio.run(job.run(db_session))

    assert result["api_calls"] == 10
    assert result["skipped_rate_limit"] == 1
    assert len(client.calls) == 10


def test_collect_coupang_skips_cached_terms(db_session):
    terms = ["cached-term", "fresh-term"]
    _seed_keywords(db_session, terms)

    cache = ApiCacheStore(db_session)
    cache.set(
        "coupang:search:cached-term",
        {"query": "cached-term", "avg_price": 0, "rocket_ratio": 0.0, "items": []},
        ttl_seconds=3600,
    )

    client = _StubCoupangClient()
    bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
    job = CollectCoupangJob(coupang_client=client, bucket=bucket, top_n=50)

    result = asyncio.run(job.run(db_session))

    assert result["cache_hits"] == 1
    assert result["api_calls"] == 1
    assert client.calls == ["fresh-term"]


def test_collect_coupang_persists_cache_entry(db_session):
    _seed_keywords(db_session, ["미니 가습기"])
    client = _StubCoupangClient()
    bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
    job = CollectCoupangJob(coupang_client=client, bucket=bucket, top_n=10)

    asyncio.run(job.run(db_session))

    cached = ApiCacheStore(db_session).get("coupang:search:미니 가습기")
    assert cached is not None
    assert cached["query"] == "미니 가습기"
    assert cached["items"][0]["product_id"] == "p-미니 가습기-1"
