"""Coupang Partners rate-limiter + cache integration.

Verifies three guarantees that span the Data-Collection ↔ Scheduler
agents (spec §3.4 — 쿠팡 파트너스 10 req/hour):

1. With more keywords than the token bucket has capacity, the job
   stops after exhausting the bucket and reports the overflow under
   ``skipped_rate_limit``.
2. Every fetched response is persisted to ``api_cache`` with the
   ``coupang:search:<term>`` key.
3. On a second run of the same job (same day), cached keywords
   short-circuit — the upstream client is **not** called for those
   terms, saving the remaining quota.
"""
from __future__ import annotations

import asyncio

from app.cache.api_cache import ApiCacheStore
from app.contracts.dto import CoupangProductDTO, CoupangSearchDTO
from app.models import Keyword, KeywordStatus
from app.ratelimit.rate_limiter import InMemoryTokenBucket
from app.scheduler.jobs import CollectCoupangJob


class _CountingCoupangClient:
    """Records every upstream call so we can assert short-circuiting."""

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
        session.add(
            Keyword(term=t, is_seed=True, status=KeywordStatus.ACTIVE)
        )
    session.flush()
    session.commit()


def test_rate_limit_and_cache_short_circuit_second_run(db_session) -> None:
    # 12 keywords but a capacity-10 bucket → first run can only fetch 10.
    terms = [f"int-rate-{i:02d}" for i in range(12)]
    _seed_keywords(db_session, terms)

    client = _CountingCoupangClient()
    bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
    job = CollectCoupangJob(coupang_client=client, bucket=bucket, top_n=100)

    first = asyncio.run(job.run(db_session))

    # Bucket hit empty exactly once; 10 API calls made.
    assert first["api_calls"] == 10
    assert first["skipped_rate_limit"] == 1
    assert len(client.calls) == 10
    # The 10 fetched entries made it into api_cache.
    cache = ApiCacheStore(db_session)
    hits = [cache.get(f"coupang:search:{term}") for term in terms]
    assert sum(1 for h in hits if h is not None) == 10

    # Second run with a **fresh** bucket (still 10 tokens): the 10 terms
    # already cached must short-circuit and the remaining 2 must fill
    # in. Total upstream calls must not exceed the original + 2.
    previous_call_count = len(client.calls)
    fresh_bucket = InMemoryTokenBucket(capacity=10, refill_per_hour=10)
    job2 = CollectCoupangJob(
        coupang_client=client, bucket=fresh_bucket, top_n=100
    )
    second = asyncio.run(job2.run(db_session))

    # Only the 2 originally-skipped terms need a real fetch.
    new_calls = len(client.calls) - previous_call_count
    assert new_calls == 2
    assert second["cache_hits"] == 10
    assert second["api_calls"] == 2
    assert second["skipped_rate_limit"] == 0

    # Every keyword now has a cache entry.
    hits_after = [cache.get(f"coupang:search:{term}") for term in terms]
    assert all(h is not None for h in hits_after)
