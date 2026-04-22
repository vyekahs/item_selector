"""Tests for :class:`CollectMetricsJob`.

The job is exercised with stub Naver clients so we can assert exactly
what lands in ``keyword_metrics`` and how the per-keyword status
transitions.
"""
from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import select

from app.contracts.dto import (
    BlogCafeDTO,
    NaverTrendDTO,
    ShoppingItem,
    ShoppingResultDTO,
    TrendPoint,
)
from app.models import Keyword, KeywordMetric, KeywordStatus
from app.scheduler.jobs import CollectMetricsJob


# ---- stubs ---------------------------------------------------------------


class _DataLabStub:
    cache_ttl = 86_400

    async def fetch(self, keyword_groups, *, start_date=None, end_date=None):
        results = []
        for grp in keyword_groups:
            term = grp[0] if grp else "unknown"
            results.append(
                NaverTrendDTO(
                    term=term,
                    points=[
                        TrendPoint(period=date(2026, 1, 1), ratio=50.0),
                        TrendPoint(period=date(2026, 2, 1), ratio=60.0),
                    ],
                    growth_rate_3m=12.5,
                    growth_rate_6m=20.0,
                    growth_rate_12m=30.0,
                )
            )
        return results


class _ShoppingStub:
    cache_ttl = 43_200

    async def fetch(self, query, *, display=10):
        return ShoppingResultDTO(
            query=query,
            total_count=4_321,
            items=[
                ShoppingItem(title="A", mall_name="mallA", price=10_000, review_count=100)
            ],
            avg_price=10_000,
            median_price=10_000,
            top10_avg_review_count=100.0,
        )


class _BlogCafeStub:
    cache_ttl = 86_400

    async def fetch(self, term):
        return BlogCafeDTO(
            term=term,
            blog_post_count=500,
            cafe_post_count=200,
            recent_30d_blog_count=80,
            recent_30d_growth_rate=10.0,
        )


class _ShoppingFailingStub:
    cache_ttl = 43_200

    async def fetch(self, query, *, display=10):
        raise RuntimeError("upstream down")


# ---- helpers -------------------------------------------------------------


def _seed_keyword(session, term: str, *, status=KeywordStatus.PENDING) -> Keyword:
    kw = Keyword(term=term, is_seed=False, status=status)
    session.add(kw)
    session.flush()
    return kw


def _make_job(**overrides):
    defaults = dict(
        datalab_client=_DataLabStub(),
        shopping_client=_ShoppingStub(),
        blogcafe_client=_BlogCafeStub(),
    )
    defaults.update(overrides)
    return CollectMetricsJob(**defaults)


# ---- tests ---------------------------------------------------------------


def test_collect_metrics_writes_one_row_per_keyword(db_session):
    _seed_keyword(db_session, "kw1")
    _seed_keyword(db_session, "kw2")

    job = _make_job()
    metrics = asyncio.run(job.run(db_session))

    assert metrics["keywords_processed"] == 2
    assert metrics["metrics_written"] == 2

    rows = db_session.execute(select(KeywordMetric)).scalars().all()
    assert len(rows) == 2
    assert all(r.snapshot_date == date.today() for r in rows)
    assert all(r.naver_shopping_count == 4_321 for r in rows)
    # blog + cafe summed
    assert all(r.blog_post_count == 700 for r in rows)


def test_collect_metrics_promotes_pending_to_active(db_session):
    kw = _seed_keyword(db_session, "kw1", status=KeywordStatus.PENDING)
    job = _make_job()

    asyncio.run(job.run(db_session))

    db_session.refresh(kw)
    assert kw.status == KeywordStatus.ACTIVE
    assert kw.last_collected_at is not None


def test_collect_metrics_isolates_per_keyword_failures(db_session):
    _seed_keyword(db_session, "kw1")
    _seed_keyword(db_session, "kw2")

    # Shopping always fails. Per-source isolation: trend/searchad/blog
    # still succeed so the row is written (with NULL shopping fields)
    # and the job records the shopping failure for observability.
    job = _make_job(shopping_client=_ShoppingFailingStub())
    metrics = asyncio.run(job.run(db_session))

    assert metrics["metrics_written"] == 2
    # One failure entry per keyword (shopping call), no datalab failures.
    assert any("shopping" in f for f in metrics["failures"])


def test_collect_metrics_skips_excluded_and_deprecated(db_session):
    _seed_keyword(db_session, "active1", status=KeywordStatus.ACTIVE)
    _seed_keyword(db_session, "excluded1", status=KeywordStatus.EXCLUDED)
    _seed_keyword(db_session, "deprecated1", status=KeywordStatus.DEPRECATED)

    job = _make_job()
    metrics = asyncio.run(job.run(db_session))

    assert metrics["keywords_processed"] == 1
    assert metrics["metrics_written"] == 1


def test_collect_metrics_is_idempotent_same_day(db_session):
    _seed_keyword(db_session, "kw1")
    job = _make_job()

    asyncio.run(job.run(db_session))
    asyncio.run(job.run(db_session))

    rows = db_session.execute(select(KeywordMetric)).scalars().all()
    # Unique constraint on (keyword_id, snapshot_date) → still one row.
    assert len(rows) == 1
