"""Per-keyword signal collection (DataLab + 쇼핑 + 블로그/카페).

Populates one row per ``(keyword_id, snapshot_date=today)`` in
``keyword_metrics``. Safe to re-run the same day: the UPSERT targets
the ``(keyword_id, snapshot_date)`` unique constraint.

Scope
-----
This job intentionally does *not* touch ``opportunity_scores`` —
score recalculation is :class:`RecalculateOpportunitiesJob`'s
responsibility so that a failing metrics fetch doesn't wipe a
perfectly valid score from the previous day.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.clients import (
    NaverBlogCafeClientProtocol,
    NaverDataLabClientProtocol,
    NaverSearchAdClientProtocol,
    NaverShoppingClientProtocol,
    get_naver_blogcafe_client,
    get_naver_datalab_client,
    get_naver_searchad_client,
    get_naver_shopping_client,
)
from app.models import Keyword, KeywordMetric, KeywordStatus
from app.scheduler.base import ScheduledJob, utcnow

__all__ = ["CollectMetricsJob"]


class CollectMetricsJob(ScheduledJob):
    """Collect per-keyword signals into ``keyword_metrics``."""

    name: str = "collect_metrics"
    max_attempts: int = 3

    def __init__(
        self,
        *,
        datalab_client: NaverDataLabClientProtocol | None = None,
        shopping_client: NaverShoppingClientProtocol | None = None,
        blogcafe_client: NaverBlogCafeClientProtocol | None = None,
        searchad_client: NaverSearchAdClientProtocol | None = None,
        max_keywords: int = 500,
    ):
        super().__init__()
        self._datalab = datalab_client
        self._shopping = shopping_client
        self._blogcafe = blogcafe_client
        self._searchad = searchad_client
        # Soft cap so a single run doesn't balloon past the daily free tier.
        self._max_keywords = max_keywords

    def _datalab_client(self) -> NaverDataLabClientProtocol:
        return self._datalab or get_naver_datalab_client()

    def _shopping_client(self) -> NaverShoppingClientProtocol:
        return self._shopping or get_naver_shopping_client()

    def _blogcafe_client(self) -> NaverBlogCafeClientProtocol:
        return self._blogcafe or get_naver_blogcafe_client()

    def _searchad_client(self) -> NaverSearchAdClientProtocol:
        return self._searchad or get_naver_searchad_client()

    async def run(self, session: Session) -> dict[str, Any]:
        datalab = self._datalab_client()
        shopping = self._shopping_client()
        blogcafe = self._blogcafe_client()
        searchad = self._searchad_client()

        # Collect for PENDING + ACTIVE keywords. EXCLUDED / DEPRECATED
        # are intentionally skipped to save API calls.
        wanted_statuses = (KeywordStatus.PENDING, KeywordStatus.ACTIVE)
        stmt = (
            select(Keyword)
            .where(Keyword.status.in_(wanted_statuses))
            .order_by(Keyword.is_seed.desc(), Keyword.id.asc())
            .limit(self._max_keywords)
        )
        keywords: list[Keyword] = list(session.execute(stmt).scalars())
        if not keywords:
            return {"keywords_processed": 0, "metrics_written": 0}

        today = date.today()
        written = 0
        api_calls = 0
        failures: list[str] = []

        # --- DataLab: batch up to 5 keyword-groups per request ----------
        # Each keyword becomes its own single-term group so the returned
        # trend lines up 1:1 with the keyword list.
        DATALAB_BATCH = 5
        trend_by_term: dict[str, Any] = {}
        for i in range(0, len(keywords), DATALAB_BATCH):
            batch = keywords[i : i + DATALAB_BATCH]
            try:
                rows = await datalab.fetch([[k.term] for k in batch])
                api_calls += 1
                for dto in rows:
                    trend_by_term[dto.term] = dto
            except Exception as exc:  # noqa: BLE001
                terms = ",".join(k.term for k in batch)
                failures.append(f"datalab_batch[{terms}]: {type(exc).__name__}")
            # DataLab rate-limit buffer — 1s between batches stays safely
            # under the documented per-minute quota.
            await asyncio.sleep(1.0)

        async def _safe(fn, *args, label: str = "", **kwargs):
            """Call an async API client, swallow errors, return (result, ok)."""
            try:
                return (await fn(*args, **kwargs), True)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{label}: {type(exc).__name__}")
                return (None, False)

        for kw in keywords:
            trend = trend_by_term.get(kw.term)
            ok_trend = trend is not None
            shopping_dto, ok_shop = await _safe(
                shopping.fetch, kw.term, label=f"{kw.term}[shopping]"
            )
            api_calls += 1 if ok_shop else 0
            blogcafe_dto, ok_blog = await _safe(
                blogcafe.fetch, kw.term, label=f"{kw.term}[blogcafe]"
            )
            api_calls += 1 if ok_blog else 0
            volume_rows, ok_vol = await _safe(
                searchad.fetch, [kw.term], label=f"{kw.term}[searchad]"
            )
            api_calls += 1 if ok_vol else 0

            # If *every* source failed we have nothing worth persisting.
            if not any([ok_trend, ok_shop, ok_blog, ok_vol]):
                continue

            volume_rows = volume_rows or []

            stripped = "".join(kw.term.split()).lower()
            volume_row = next(
                (
                    v
                    for v in volume_rows
                    if "".join(v.term.split()).lower() == stripped
                ),
                volume_rows[0] if volume_rows else None,
            )

            values: dict[str, Any] = {
                "keyword_id": kw.id,
                "snapshot_date": today,
                "monthly_search_volume": (
                    volume_row.total_monthly_volume if volume_row else None
                ),
                "competition_score": (
                    float(volume_row.competition_index)
                    if volume_row is not None
                    else None
                ),
                "naver_shopping_count": (
                    shopping_dto.total_count if shopping_dto else None
                ),
                "shopping_avg_price_krw": (
                    (shopping_dto.avg_price or None) if shopping_dto else None
                ),
                "blog_post_count": (
                    blogcafe_dto.blog_post_count + blogcafe_dto.cafe_post_count
                    if blogcafe_dto
                    else None
                ),
                "youtube_video_count": None,
                # DataLab growth rates are percentages (e.g. 5.0 = +5%).
                # The DB column is Numeric(7,4) — decimal form works too
                # but we keep the wire percent to match what the existing
                # Naver client produces.
                "growth_rate_3m": float(trend.growth_rate_3m) if trend else None,
                "growth_rate_6m": float(trend.growth_rate_6m) if trend else None,
            }
            ins = pg_insert(KeywordMetric).values(**values)
            ins = ins.on_conflict_do_update(
                constraint="keyword_metric_unique_snapshot",
                set_={
                    "monthly_search_volume": ins.excluded.monthly_search_volume,
                    "competition_score": ins.excluded.competition_score,
                    "naver_shopping_count": ins.excluded.naver_shopping_count,
                    "shopping_avg_price_krw": ins.excluded.shopping_avg_price_krw,
                    "blog_post_count": ins.excluded.blog_post_count,
                    "growth_rate_3m": ins.excluded.growth_rate_3m,
                    "growth_rate_6m": ins.excluded.growth_rate_6m,
                    "updated_at": utcnow(),
                },
            )
            session.execute(ins)
            written += 1

            kw.last_collected_at = utcnow()
            if kw.status == KeywordStatus.PENDING:
                kw.status = KeywordStatus.ACTIVE

        session.commit()

        return {
            "keywords_processed": len(keywords),
            "metrics_written": written,
            "api_calls": api_calls,
            "failures": failures,
        }
