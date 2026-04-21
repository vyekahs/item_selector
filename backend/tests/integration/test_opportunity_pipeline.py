"""End-to-end opportunity pipeline integration test.

This test drives the **scheduler → DB → HTTP API** path that powers the
"이번주 중국 소싱 기회 TOP N" landing page (spec §6.1):

1. Seed a category + seed keyword in the DB.
2. Run :class:`CollectKeywordsJob` to harvest 연관 키워드
   (Naver Searchad mock → new ``keywords`` rows with ``PENDING`` status).
3. Run :class:`CollectMetricsJob` which moves ``PENDING → ACTIVE`` and
   writes ``keyword_metrics`` rows.
4. Run :class:`RecalculateOpportunitiesJob` which UPSERTs
   ``opportunity_scores`` rows.
5. Hit ``GET /opportunities`` via the FastAPI test client and assert
   the scheduler's writes are visible, ranked by ``total_score`` desc,
   and include a 1688 deep link per row.

The mocked clients are the minimum-viable stubs required for
:class:`RecalculateOpportunitiesJob` — they deliberately do **not**
reuse the sample JSON fixtures so the test stays deterministic.
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
from app.scheduler.jobs import (
    CollectKeywordsJob,
    CollectMetricsJob,
    RecalculateOpportunitiesJob,
)


# --- stub clients (shared across steps 2+3+4) --------------------------------


class _SearchAd:
    """Expands ``고양이 자동급수기`` → two related terms."""

    cache_ttl = 86_400

    def __init__(self) -> None:
        self.fetch_calls: list[list[str]] = []

    async def fetch(self, keywords: list[str]) -> list[KeywordVolumeDTO]:
        self.fetch_calls.append(list(keywords))
        out: list[KeywordVolumeDTO] = []
        related_map = {
            "고양이 자동급수기": ["고양이 분수기", "자동 급수기"],
        }
        for kw in keywords:
            out.append(
                KeywordVolumeDTO(
                    term=kw,
                    pc_monthly_volume=5_000,
                    mobile_monthly_volume=15_000,
                    total_monthly_volume=20_000,
                    competition_index=0.35,
                    related_keywords=related_map.get(kw, []),
                )
            )
        return out


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
                growth_rate_3m=18.0,
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
                ShoppingItem(
                    title=f"{query} A",
                    mall_name="m",
                    price=19_900,
                    review_count=40,
                )
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


# --- helpers ----------------------------------------------------------------


def _seed_category_and_seed_keyword(session) -> tuple[Category, Keyword]:
    cat = Category(name="반려동물용품", is_certification_required=False)
    session.add(cat)
    session.flush()
    kw = Keyword(
        term="고양이 자동급수기",
        is_seed=True,
        status=KeywordStatus.ACTIVE,
        category_id=cat.id,
    )
    session.add(kw)
    session.flush()
    # Integration tests run inside a SAVEPOINT; commit promotes our writes
    # to the outer transaction so nested scheduler commits can see them.
    session.commit()
    return cat, kw


# --- tests ------------------------------------------------------------------


def test_opportunity_pipeline_end_to_end(client, db_session) -> None:
    """End-to-end: seed → collect_keywords → collect_metrics → recalc → GET /opportunities."""
    cat, seed_kw = _seed_category_and_seed_keyword(db_session)

    searchad = _SearchAd()
    datalab = _DataLab()
    shopping = _Shopping()
    blogcafe = _BlogCafe()
    youtube = _YouTube()
    customs = _Customs()

    # Step 1: keyword expansion
    collect_keywords = CollectKeywordsJob(searchad_client=searchad)
    kw_metrics = asyncio.run(collect_keywords.run(db_session))
    assert kw_metrics["seed_count"] == 1
    # Two related terms harvested.
    assert kw_metrics["new_keywords"] == 2

    # The new keywords are PENDING; give them the same category so the
    # categorised filter on GET /opportunities works.
    new_rows = db_session.execute(
        select(Keyword).where(Keyword.is_seed.is_(False))
    ).scalars().all()
    assert len(new_rows) == 2
    for k in new_rows:
        k.category_id = cat.id
    db_session.commit()

    # Step 2: collect metrics (PENDING → ACTIVE, writes keyword_metrics)
    collect_metrics = CollectMetricsJob(
        datalab_client=datalab,
        shopping_client=shopping,
        blogcafe_client=blogcafe,
    )
    metrics_result = asyncio.run(collect_metrics.run(db_session))
    # 3 keywords = 1 seed + 2 newly-harvested.
    assert metrics_result["keywords_processed"] == 3
    assert metrics_result["metrics_written"] == 3

    activated = db_session.execute(
        select(Keyword).where(Keyword.status == KeywordStatus.ACTIVE)
    ).scalars().all()
    assert len(activated) == 3

    # Step 3: recalc opportunity scores for all ACTIVE keywords
    recalc = RecalculateOpportunitiesJob(
        searchad_client=searchad,
        datalab_client=datalab,
        shopping_client=shopping,
        blogcafe_client=blogcafe,
        youtube_client=youtube,
        customs_client=customs,
    )
    recalc_result = asyncio.run(recalc.run(db_session))
    assert recalc_result["keywords_processed"] == 3
    assert recalc_result["scores_written"] == 3

    # Sanity: opportunity_scores rows exist and today's snapshot is present.
    scores = db_session.execute(select(OpportunityScore)).scalars().all()
    assert len(scores) == 3
    assert all(s.snapshot_date == date.today() for s in scores)
    assert all(0 <= float(s.total_score) <= 100 for s in scores)

    # Step 4: HTTP API read
    response = client.get("/opportunities", params={"limit": 20})
    assert response.status_code == 200
    body = response.json()
    # All three keywords are non-excluded in this fixture and should surface.
    assert len(body) == 3

    # Ranked by total_score desc, continuous 1-based ranks.
    ranks = [row["rank"] for row in body]
    assert ranks == [1, 2, 3]
    total_scores = [row["total_score"] for row in body]
    assert total_scores == sorted(total_scores, reverse=True)

    # Each row has a 1688 deep link + populated term/category.
    for row in body:
        assert row["search_1688_url"].startswith("https://s.1688.com/")
        assert row["term"]  # non-empty
        assert row["category_id"] == cat.id
        assert row["category_name"] == "반려동물용품"


def test_opportunity_pipeline_category_filter(client, db_session) -> None:
    """``?category_id=`` filters down the list to matching keywords."""
    pet_cat = Category(name="반려동물용품")
    home_cat = Category(name="생활용품")
    db_session.add_all([pet_cat, home_cat])
    db_session.flush()

    # Seed one ACTIVE keyword per category so we can verify the filter.
    kw_pet = Keyword(
        term="고양이 자동급수기",
        is_seed=True,
        status=KeywordStatus.ACTIVE,
        category_id=pet_cat.id,
    )
    kw_home = Keyword(
        term="휴대용 선풍기",
        is_seed=True,
        status=KeywordStatus.ACTIVE,
        category_id=home_cat.id,
    )
    db_session.add_all([kw_pet, kw_home])
    db_session.flush()
    db_session.commit()

    recalc = RecalculateOpportunitiesJob(
        searchad_client=_SearchAd(),
        datalab_client=_DataLab(),
        shopping_client=_Shopping(),
        blogcafe_client=_BlogCafe(),
        youtube_client=_YouTube(),
        customs_client=_Customs(),
    )
    asyncio.run(recalc.run(db_session))

    # Unfiltered → 2 rows.
    all_resp = client.get("/opportunities", params={"limit": 20}).json()
    assert {row["term"] for row in all_resp} == {
        "고양이 자동급수기",
        "휴대용 선풍기",
    }

    # Filtered → only the pet keyword.
    pet_resp = client.get(
        "/opportunities", params={"category_id": pet_cat.id, "limit": 20}
    ).json()
    assert [row["term"] for row in pet_resp] == ["고양이 자동급수기"]
