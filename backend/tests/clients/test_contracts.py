"""Regression tests pinning the shared DTO contract.

These tests fail loudly if a field is renamed, retyped or removed from
:mod:`app.contracts.dto`. They are the *cross-agent* contract — Scoring
Engine and Backend API rely on these shapes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.contracts.dto import (
    BlogCafeDTO,
    Channel,
    CoupangProductDTO,
    CoupangSearchDTO,
    CustomsImportDTO,
    CustomsTrendDTO,
    ExchangeRateDTO,
    GoogleTrendDTO,
    HsCodeDTO,
    KeywordVolumeDTO,
    NaverTrendDTO,
    Recommendation,
    ShoppingItem,
    ShoppingResultDTO,
    TrendPoint,
    YouTubeSignalDTO,
)


def _field_set(model_cls) -> set[str]:
    return set(model_cls.model_fields.keys())


# ---- enums -----------------------------------------------------------


def test_channel_values():
    assert Channel.SMARTSTORE.value == "smartstore"
    assert Channel.COUPANG.value == "coupang"


def test_recommendation_values():
    assert Recommendation.GO.value == "GO"
    assert Recommendation.CONDITIONAL.value == "CONDITIONAL"
    assert Recommendation.PASS.value == "PASS"


# ---- 네이버 검색광고 -------------------------------------------------


def test_keyword_volume_dto_fields():
    assert _field_set(KeywordVolumeDTO) == {
        "term",
        "pc_monthly_volume",
        "mobile_monthly_volume",
        "total_monthly_volume",
        "competition_index",
        "related_keywords",
    }


def test_keyword_volume_dto_construction():
    dto = KeywordVolumeDTO(
        term="휴대용선풍기",
        pc_monthly_volume=8900,
        mobile_monthly_volume=95300,
        total_monthly_volume=104200,
        competition_index=0.8,
        related_keywords=["미니선풍기"],
    )
    assert dto.term == "휴대용선풍기"
    assert dto.competition_index == 0.8
    assert dto.related_keywords == ["미니선풍기"]


def test_keyword_volume_dto_competition_bounds():
    # competition_index must be clamped to [0, 1]
    with pytest.raises(Exception):
        KeywordVolumeDTO(
            term="x",
            pc_monthly_volume=0,
            mobile_monthly_volume=0,
            total_monthly_volume=0,
            competition_index=1.5,
        )


# ---- 네이버 DataLab -------------------------------------------------


def test_trend_point_fields():
    assert _field_set(TrendPoint) == {"period", "ratio"}
    p = TrendPoint(period=date(2025, 1, 1), ratio=12.4)
    assert p.ratio == 12.4


def test_naver_trend_dto_fields():
    assert _field_set(NaverTrendDTO) == {
        "term",
        "points",
        "growth_rate_3m",
        "growth_rate_6m",
        "growth_rate_12m",
    }


# ---- 네이버 쇼핑 ----------------------------------------------------


def test_shopping_item_fields():
    assert _field_set(ShoppingItem) == {
        "title",
        "mall_name",
        "price",
        "review_count",
        "category1",
        "category2",
    }


def test_shopping_result_dto_fields():
    assert _field_set(ShoppingResultDTO) == {
        "query",
        "total_count",
        "items",
        "avg_price",
        "median_price",
        "top10_avg_review_count",
    }


# ---- 네이버 블로그/카페 ---------------------------------------------


def test_blogcafe_dto_fields():
    assert _field_set(BlogCafeDTO) == {
        "term",
        "blog_post_count",
        "cafe_post_count",
        "recent_30d_blog_count",
        "recent_30d_growth_rate",
    }


# ---- 쿠팡 파트너스 --------------------------------------------------


def test_coupang_product_dto_fields():
    assert _field_set(CoupangProductDTO) == {
        "product_id",
        "name",
        "price",
        "rating",
        "review_count",
        "is_rocket",
        "category_path",
    }


def test_coupang_product_rating_bounds():
    with pytest.raises(Exception):
        CoupangProductDTO(
            product_id="1",
            name="x",
            price=1,
            rating=6.0,
            review_count=0,
            is_rocket=False,
            category_path="a",
        )


def test_coupang_search_dto_fields():
    assert _field_set(CoupangSearchDTO) == {
        "query",
        "items",
        "avg_price",
        "rocket_ratio",
    }


# ---- 관세청 -----------------------------------------------------


def test_customs_import_dto_fields():
    assert _field_set(CustomsImportDTO) == {
        "hs_code",
        "year_month",
        "country_code",
        "import_quantity",
        "import_value_usd",
    }


def test_customs_import_dto_uses_decimal():
    dto = CustomsImportDTO(
        hs_code="841451",
        year_month="2025-01",
        country_code="CN",
        import_quantity="421350",
        import_value_usd="3812400",
    )
    assert isinstance(dto.import_quantity, Decimal)
    assert isinstance(dto.import_value_usd, Decimal)


def test_customs_trend_dto_fields():
    assert _field_set(CustomsTrendDTO) == {
        "hs_code",
        "country_code",
        "points",
        "growth_rate_3m",
        "growth_rate_12m",
    }


# ---- HS 부호 / 환율 -------------------------------------------------


def test_hs_code_dto_fields():
    assert _field_set(HsCodeDTO) == {"code", "name_ko", "name_en"}
    dto = HsCodeDTO(code="841451", name_ko="선풍기")
    assert dto.name_en is None  # optional default


def test_exchange_rate_dto_fields():
    assert _field_set(ExchangeRateDTO) == {"currency_pair", "rate", "fetched_at"}
    dto = ExchangeRateDTO(
        currency_pair="CNY/KRW",
        rate=Decimal("191.33"),
        fetched_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    assert isinstance(dto.rate, Decimal)


# ---- YouTube / Google Trends ----------------------------------------


def test_youtube_signal_dto_fields():
    assert _field_set(YouTubeSignalDTO) == {
        "term",
        "total_video_count",
        "recent_30d_video_count",
        "avg_view_count",
        "growth_rate_30d",
    }


def test_google_trend_dto_fields():
    assert _field_set(GoogleTrendDTO) == {
        "term",
        "region",
        "points",
        "related_rising",
        "growth_rate_3m",
    }
    dto = GoogleTrendDTO(term="x", region="KR", points=[], growth_rate_3m=0.0)
    assert dto.related_rising == []  # optional default
