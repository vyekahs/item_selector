"""Top-keyword Coupang Partners refresh.

The Coupang Partners Search API is quota-constrained to **10 requests
per hour** (§3.4 of the spec). This job therefore:

1. Picks the current TOP-N keywords by latest ``opportunity_scores``.
2. Acquires a token from :func:`build_coupang_bucket` before every
   request, using ``block=False`` — if the bucket is empty we *skip*
   the keyword rather than sleep inside a scheduled job.
3. Caches the raw response via :class:`ApiCacheStore` (24h TTL) so
   subsequent runs within the day short-circuit entirely.

The fetched price/rocket ratio is *not* persisted to dedicated columns
(the schema for that lives in Channel Profit / Product layers). We
only wire it into the cache + emit metrics, so scoring can read it
later without re-hitting the API.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.cache.api_cache import ApiCacheStore
from app.clients import (
    CoupangPartnersClientProtocol,
    RateLimitError,
    get_coupang_partners_client,
)
from app.clients.coupang_partners import CACHE_TTL_SECONDS as COUPANG_CACHE_TTL
from app.models import Keyword, OpportunityScore
from app.ratelimit.rate_limiter import TokenBucket, build_coupang_bucket
from app.scheduler.base import ScheduledJob

__all__ = ["CollectCoupangJob"]


DEFAULT_TOP_N: int = 100


class CollectCoupangJob(ScheduledJob):
    """Refresh Coupang Partners snapshots for the current TOP-N keywords."""

    name: str = "collect_coupang"
    # Rate-limited jobs must not retry blindly — a retry would just
    # bounce off the token bucket again. Single-shot.
    max_attempts: int = 1

    def __init__(
        self,
        *,
        coupang_client: CoupangPartnersClientProtocol | None = None,
        bucket: TokenBucket | None = None,
        top_n: int = DEFAULT_TOP_N,
    ):
        super().__init__()
        self._coupang = coupang_client
        self._bucket = bucket
        self._top_n = top_n

    def _client(self) -> CoupangPartnersClientProtocol:
        return self._coupang or get_coupang_partners_client()

    def _get_bucket(self) -> TokenBucket:
        return self._bucket or build_coupang_bucket()

    async def run(self, session: Session) -> dict[str, Any]:
        client = self._client()
        bucket = self._get_bucket()
        cache = ApiCacheStore(session)

        # Pull the latest opportunity_score row per keyword (by snapshot_date)
        # and order by total_score desc. Falls back to the most recently
        # created keywords when no scores exist yet.
        latest_date = (
            select(
                OpportunityScore.keyword_id.label("kid"),
                func.max(OpportunityScore.snapshot_date).label("max_date"),
            )
            .group_by(OpportunityScore.keyword_id)
            .subquery()
        )
        score_stmt = (
            select(Keyword.term, OpportunityScore.total_score)
            .join(latest_date, latest_date.c.kid == Keyword.id)
            .join(
                OpportunityScore,
                (OpportunityScore.keyword_id == latest_date.c.kid)
                & (OpportunityScore.snapshot_date == latest_date.c.max_date),
            )
            .order_by(desc(OpportunityScore.total_score))
            .limit(self._top_n)
        )
        top_terms: list[str] = [row[0] for row in session.execute(score_stmt).all()]

        if not top_terms:
            fallback_stmt = (
                select(Keyword.term)
                .order_by(Keyword.is_seed.desc(), Keyword.id.asc())
                .limit(self._top_n)
            )
            top_terms = list(session.execute(fallback_stmt).scalars())

        api_calls = 0
        cache_hits = 0
        skipped_rate_limit = 0
        skipped_errors: list[str] = []

        for term in top_terms:
            cache_key = f"coupang:search:{term}"
            if cache.get(cache_key) is not None:
                cache_hits += 1
                continue
            try:
                await bucket.acquire(block=False)
            except RateLimitError:
                skipped_rate_limit += 1
                # No point pushing against the quota further this hour.
                break

            try:
                dto = await client.fetch(term)
            except Exception as exc:  # noqa: BLE001
                skipped_errors.append(f"{term}: {type(exc).__name__}")
                continue

            # JSONB-safe payload. Avoid persisting the full DTO via
            # pydantic.model_dump — we keep only what downstream needs.
            payload = {
                "query": dto.query,
                "avg_price": dto.avg_price,
                "rocket_ratio": dto.rocket_ratio,
                "items": [
                    {
                        "product_id": it.product_id,
                        "name": it.name,
                        "price": it.price,
                        "rating": it.rating,
                        "review_count": it.review_count,
                        "is_rocket": it.is_rocket,
                    }
                    for it in dto.items
                ],
            }
            # JSON round-trip protects against any stray non-primitive
            # that sneaks in from subclasses.
            cache.set(cache_key, json.loads(json.dumps(payload)), ttl_seconds=COUPANG_CACHE_TTL)
            api_calls += 1

        return {
            "keywords_considered": len(top_terms),
            "api_calls": api_calls,
            "cache_hits": cache_hits,
            "skipped_rate_limit": skipped_rate_limit,
            "errors": skipped_errors,
        }
