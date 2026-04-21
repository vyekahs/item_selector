"""Shared fixtures + factory helpers for scoring tests.

Every fixture builds a *baseline* DTO that already passes every
exclusion filter and lands in the middle of every scoring axis. Tests
then mutate one field at a time to probe a specific behaviour, which
keeps the assertions readable.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.scoring.opportunity import OpportunityInputs
from app.scoring.product import ProductScoreInputs
from app.scoring.revenue import (
    DEFAULT_COUPANG_AD_PCT,
    DEFAULT_SMARTSTORE_AD_PCT,
    RevenueInputs,
    calculate_coupang_revenue,
    calculate_smartstore_revenue,
)
from app.scoring.opportunity import calculate_opportunity_score
from app.scoring.types import (
    BlogCafeDTO,
    CustomsTrendDTO,
    CustomsTrendPoint,
    KeywordVolumeDTO,
    NaverTrendDTO,
    ShoppingItemDTO,
    ShoppingResultDTO,
    TrendPoint,
    YouTubeSignalDTO,
)


# ---- DTO factories ---------------------------------------------------------


def make_volume(
    term: str = "고양이 자동급수기",
    pc: int = 8_000,
    mobile: int = 20_000,
    competition: float = 0.5,
) -> KeywordVolumeDTO:
    return KeywordVolumeDTO(
        term=term,
        pc_monthly_volume=pc,
        mobile_monthly_volume=mobile,
        total_monthly_volume=pc + mobile,
        competition_index=competition,
        related_keywords=["자동급수기", "고양이 급수기"],
    )


def make_trend(growth_3m: float = 0.20) -> NaverTrendDTO:
    return NaverTrendDTO(
        term="고양이 자동급수기",
        points=[
            TrendPoint(period=date(2026, 1, 1), ratio=70.0),
            TrendPoint(period=date(2026, 2, 1), ratio=80.0),
            TrendPoint(period=date(2026, 3, 1), ratio=90.0),
        ],
        growth_rate_3m=growth_3m,
        growth_rate_6m=0.30,
        growth_rate_12m=0.45,
    )


def make_shopping(
    total: int = 2_000,
    top10_reviews: int = 200,
) -> ShoppingResultDTO:
    return ShoppingResultDTO(
        query="고양이 자동급수기",
        total_count=total,
        items=[
            ShoppingItemDTO(title="A", price=38_000, review_count=top10_reviews),
            ShoppingItemDTO(title="B", price=42_000, review_count=top10_reviews),
        ],
        avg_price=40_000,
        median_price=40_000,
        top10_avg_review_count=top10_reviews,
    )


def make_blog_cafe(growth: float = 0.25) -> BlogCafeDTO:
    return BlogCafeDTO(
        term="고양이 자동급수기",
        blog_post_count=5_000,
        cafe_post_count=1_200,
        recent_30d_blog_count=300,
        recent_30d_growth_rate=growth,
    )


def make_youtube(growth: float = 0.30) -> YouTubeSignalDTO:
    return YouTubeSignalDTO(
        term="고양이 자동급수기",
        total_video_count=400,
        recent_30d_video_count=80,
        avg_view_count=12_000.0,
        growth_rate_30d=growth,
    )


def make_customs(growth_3m: float = 0.34) -> CustomsTrendDTO:
    return CustomsTrendDTO(
        hs_code="8509.80",
        country_code="CN",
        points=[
            CustomsTrendPoint(
                year_month="2026-01", import_value_usd=120_000, import_quantity=1000
            ),
            CustomsTrendPoint(
                year_month="2026-02", import_value_usd=145_000, import_quantity=1200
            ),
            CustomsTrendPoint(
                year_month="2026-03", import_value_usd=160_000, import_quantity=1400
            ),
        ],
        growth_rate_3m=growth_3m,
        growth_rate_12m=0.50,
    )


# ---- composite fixtures ----------------------------------------------------


@pytest.fixture
def baseline_opportunity_inputs() -> OpportunityInputs:
    """Mid-range inputs designed to score around 60–80 / 100."""
    return OpportunityInputs(
        keyword="고양이 자동급수기",
        volume=make_volume(),
        trend=make_trend(),
        shopping=make_shopping(),
        blog_cafe=make_blog_cafe(),
        youtube=make_youtube(),
        google_trend=None,
        customs=make_customs(),
        category_name="반려동물용품",
        is_certification_required=False,
        seasonality_index=1.2,
    )


@pytest.fixture
def baseline_revenue_inputs() -> RevenueInputs:
    """Spec §6.2 sample numbers: ¥45 × MOQ 50 @ 195 KRW/CNY."""
    return RevenueInputs(
        cny_price=Decimal("45"),
        moq=50,
        expected_sell_price_krw=38_000,
        category_name="반려동물용품",
        exchange_rate=Decimal("195"),
        intl_shipping_krw=3_000,
        customs_duty_pct=Decimal("0.08"),
        ad_cost_pct=DEFAULT_SMARTSTORE_AD_PCT,
    )


@pytest.fixture
def baseline_product_inputs(
    baseline_opportunity_inputs: OpportunityInputs,
    baseline_revenue_inputs: RevenueInputs,
) -> ProductScoreInputs:
    opp = calculate_opportunity_score(baseline_opportunity_inputs)
    ss = calculate_smartstore_revenue(baseline_revenue_inputs)
    cp_inputs = baseline_revenue_inputs.model_copy(
        update={"ad_cost_pct": DEFAULT_COUPANG_AD_PCT}
    )
    cp = calculate_coupang_revenue(cp_inputs, Decimal("0.108"))

    moq = baseline_revenue_inputs.moq
    initial_cost = ss.unit_cost_krw * moq
    return ProductScoreInputs(
        opportunity=opp,
        smartstore=ss,
        coupang=cp,
        budget_krw=2_000_000,
        total_initial_cost_krw=initial_cost,
        expected_monthly_demand_units=50,
        user_stability_rating=7.0,
    )
