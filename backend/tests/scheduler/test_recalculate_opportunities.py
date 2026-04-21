"""Tests for :class:`RecalculateOpportunitiesJob`.

The job pulls a handful of upstream DTOs per keyword, feeds them to
:func:`calculate_opportunity_score`, and upserts the result into the
``opportunity_scores`` table.

Assertions here intentionally stay structural (row exists, score is
within range, upsert idempotent) rather than pinning exact numeric
outputs — the scoring formula belongs to ``tests/scoring``.
"""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.contracts.dto import (
    BlogCafeDTO,
    CustomsImportDTO,
    CustomsTrendDTO,
    KeywordVolumeDTO,
    NaverTrendDTO,
    ShoppingItem,
    ShoppingResultDTO,
    TrendPoint,
    YouTubeSignalDTO,
)
from app.models import Category, Keyword, KeywordStatus, OpportunityScore
from app.scheduler.jobs import RecalculateOpportunitiesJob


# -------- stub clients -----------------------------------------------------


class _SearchAd:
    cache_ttl = 86_400

    async def fetch(self, keywords: list[str]) -> list[KeywordVolumeDTO]:
        return [
            KeywordVolumeDTO(
                term=k,
                pc_monthly_volume=5_000,
                mobile_monthly_volume=15_000,
                total_monthly_volume=20_000,
                competition_index=0.35,
                related_keywords=[],
            )
            for k in keywords
        ]


class _DataLab:
    cache_ttl = 86_400

    async def fetch(self, groups: list[list[str]]) -> list[NaverTrendDTO]:
        return [
            NaverTrendDTO(
                term=g[0],
                points=[
                    TrendPoint(period=date(2026, 1, 1), ratio=40.0),
                    TrendPoint(period=date(2026, 4, 1), ratio=60.0),
                ],
                growth_rate_3m=18.0,  # percent form, job converts to decimal
                growth_rate_6m=22.0,
                growth_rate_12m=35.0,
            )
            for g in groups
        ]


class _Shopping:
    cache_ttl = 43_200

    async def fetch(self, query: str) -> ShoppingResultDTO:
        return ShoppingResultDTO(
            query=query,
            total_count=420,
            items=[
                ShoppingItem(title="A", mall_name="m", price=19_900, review_count=40)
            ],
            avg_price=22_000,
            median_price=21_000,
            top10_avg_review_count=75.0,
        )


class _BlogCafe:
    cache_ttl = 86_400

    async def fetch(self, query: str) -> BlogCafeDTO:
        return BlogCafeDTO(
            term=query,
            blog_post_count=1_200,
            cafe_post_count=320,
            recent_30d_blog_count=180,
            recent_30d_growth_rate=25.0,
        )


class _YouTube:
    cache_ttl = 86_400

    async def fetch(self, query: str) -> YouTubeSignalDTO:
        return YouTubeSignalDTO(
            term=query,
            total_video_count=520,
            recent_30d_video_count=38,
            avg_view_count=12_000,
            growth_rate_30d=14.0,
        )


class _Customs:
    cache_ttl = 604_800

    async def fetch(self, hs_code: str) -> CustomsTrendDTO:
        return CustomsTrendDTO(
            hs_code=hs_code,
            country_code="CN",
            points=[
                CustomsImportDTO(
                    hs_code=hs_code,
                    year_month="2026-03",
                    country_code="CN",
                    import_quantity=Decimal("1000"),
                    import_value_usd=Decimal("25000"),
                )
            ],
            growth_rate_3m=22.0,
            growth_rate_12m=34.0,
        )


# -------- helpers -----------------------------------------------------------


def _seed_category(session, *, is_cert_required: bool = False) -> Category:
    cat = Category(
        name="반려동물용품",
        is_certification_required=is_cert_required,
    )
    session.add(cat)
    session.flush()
    return cat


def _seed_active_keyword(session, *, category_id: int, term: str) -> Keyword:
    kw = Keyword(
        term=term,
        is_seed=True,
        status=KeywordStatus.ACTIVE,
        category_id=category_id,
    )
    session.add(kw)
    session.flush()
    return kw


def _build_job() -> RecalculateOpportunitiesJob:
    return RecalculateOpportunitiesJob(
        searchad_client=_SearchAd(),
        datalab_client=_DataLab(),
        shopping_client=_Shopping(),
        blogcafe_client=_BlogCafe(),
        youtube_client=_YouTube(),
        customs_client=_Customs(),
    )


# -------- tests -------------------------------------------------------------


def test_recalculate_writes_opportunity_score_for_active_keyword(db_session):
    cat = _seed_category(db_session)
    kw = _seed_active_keyword(db_session, category_id=cat.id, term="고양이 자동급수기")

    result = asyncio.run(_build_job().run(db_session))

    assert result["keywords_processed"] == 1
    assert result["scores_written"] == 1

    row = db_session.execute(
        select(OpportunityScore).where(OpportunityScore.keyword_id == kw.id)
    ).scalar_one()
    assert row.snapshot_date == date.today()
    assert 0 <= float(row.total_score) <= 100


def test_recalculate_skips_non_active_keywords(db_session):
    cat = _seed_category(db_session)
    active_kw = _seed_active_keyword(db_session, category_id=cat.id, term="active-term")
    inactive_kw = Keyword(
        term="pending-term",
        is_seed=False,
        status=KeywordStatus.PENDING,
        category_id=cat.id,
    )
    db_session.add(inactive_kw)
    db_session.flush()

    asyncio.run(_build_job().run(db_session))

    rows = db_session.execute(select(OpportunityScore)).scalars().all()
    assert len(rows) == 1
    assert rows[0].keyword_id == active_kw.id


def test_recalculate_is_idempotent_same_day(db_session):
    cat = _seed_category(db_session)
    _seed_active_keyword(db_session, category_id=cat.id, term="kw")

    job = _build_job()
    asyncio.run(job.run(db_session))
    asyncio.run(job.run(db_session))

    rows = db_session.execute(select(OpportunityScore)).scalars().all()
    # Upsert on (keyword_id, snapshot_date) — should still be exactly 1 row.
    assert len(rows) == 1


def test_recalculate_marks_excluded_for_certification_category(db_session):
    cat = _seed_category(db_session, is_cert_required=True)
    _seed_active_keyword(db_session, category_id=cat.id, term="kw-certified")

    asyncio.run(_build_job().run(db_session))

    row = db_session.execute(select(OpportunityScore)).scalar_one()
    assert row.is_excluded is True
    assert row.exclusion_reasons is not None
    assert "certification" in row.exclusion_reasons.lower()
