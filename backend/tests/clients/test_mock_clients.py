"""Mock client smoke tests.

Each Mock implementation must:

* Construct successfully without any external dependencies.
* Return a list/object that conforms to the contract DTO.
* Be selected by the ``get_*_client()`` factory when ``USE_MOCK_CLIENTS``
  is unset or truthy.
"""
from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.contracts.dto import (
    BlogCafeDTO,
    CoupangSearchDTO,
    CustomsTrendDTO,
    ExchangeRateDTO,
    GoogleTrendDTO,
    HsCodeDTO,
    KeywordVolumeDTO,
    NaverTrendDTO,
    ShoppingResultDTO,
    YouTubeSignalDTO,
)
# Mock classes live in their submodules; ``app.clients`` only re-exports
# the protocols + factories.
from app.clients.coupang_partners import MockCoupangPartnersClient, get_coupang_partners_client
from app.clients.customs import MockCustomsClient, get_customs_client
from app.clients.exchange_rate import MockExchangeRateClient, get_exchange_rate_client
from app.clients.google_trends import MockGoogleTrendsClient, get_google_trends_client
from app.clients.hs_code import MockHsCodeClient, get_hs_code_client
from app.clients.naver_blogcafe import MockNaverBlogCafeClient, get_naver_blogcafe_client
from app.clients.naver_datalab import MockNaverDataLabClient, get_naver_datalab_client
from app.clients.naver_searchad import MockNaverSearchAdClient, get_naver_searchad_client
from app.clients.naver_shopping import MockNaverShoppingClient, get_naver_shopping_client
from app.clients.youtube import MockYouTubeClient, get_youtube_client


def _run(coro):
    return asyncio.run(coro)


# ---- factory honours USE_MOCK_CLIENTS -------------------------------


@pytest.fixture(autouse=True)
def _force_mocks(monkeypatch):
    monkeypatch.setenv("USE_MOCK_CLIENTS", "true")


def test_factories_return_mock_instances():
    assert isinstance(get_naver_searchad_client(), MockNaverSearchAdClient)
    assert isinstance(get_naver_datalab_client(), MockNaverDataLabClient)
    assert isinstance(get_naver_shopping_client(), MockNaverShoppingClient)
    assert isinstance(get_naver_blogcafe_client(), MockNaverBlogCafeClient)
    assert isinstance(get_coupang_partners_client(), MockCoupangPartnersClient)
    assert isinstance(get_customs_client(), MockCustomsClient)
    assert isinstance(get_hs_code_client(), MockHsCodeClient)
    assert isinstance(get_exchange_rate_client(), MockExchangeRateClient)
    assert isinstance(get_youtube_client(), MockYouTubeClient)
    assert isinstance(get_google_trends_client(), MockGoogleTrendsClient)


# ---- per-client DTO conformance -------------------------------------


def test_naver_searchad_returns_keyword_volume_dtos():
    client = MockNaverSearchAdClient()
    rows = _run(client.fetch(["휴대용선풍기"]))
    assert rows
    assert all(isinstance(r, KeywordVolumeDTO) for r in rows)
    # total_monthly_volume must equal pc + mobile.
    for r in rows:
        assert r.total_monthly_volume == r.pc_monthly_volume + r.mobile_monthly_volume
        assert 0.0 <= r.competition_index <= 1.0


def test_naver_datalab_returns_trend_dto():
    client = MockNaverDataLabClient()
    out = _run(client.fetch([["휴대용선풍기"]]))
    assert out and isinstance(out[0], NaverTrendDTO)
    assert out[0].points
    assert isinstance(out[0].points[0].period, date)


def test_naver_shopping_aggregates_prices():
    client = MockNaverShoppingClient()
    dto = _run(client.fetch("휴대용선풍기"))
    assert isinstance(dto, ShoppingResultDTO)
    assert dto.query == "휴대용선풍기"
    assert dto.total_count > 0
    assert dto.avg_price > 0
    assert dto.median_price > 0
    assert dto.top10_avg_review_count >= 0


def test_naver_blogcafe_counts_recent_30d():
    client = MockNaverBlogCafeClient()
    dto = _run(client.fetch("휴대용선풍기"))
    assert isinstance(dto, BlogCafeDTO)
    assert dto.blog_post_count > 0
    assert dto.cafe_post_count > 0
    assert dto.recent_30d_blog_count >= 0


def test_coupang_partners_returns_search_dto():
    client = MockCoupangPartnersClient()
    dto = _run(client.fetch("휴대용선풍기"))
    assert isinstance(dto, CoupangSearchDTO)
    assert dto.query == "휴대용선풍기"
    assert dto.items
    assert dto.avg_price > 0
    assert 0.0 <= dto.rocket_ratio <= 1.0


def test_customs_returns_trend_with_records():
    client = MockCustomsClient()
    dto = _run(client.fetch("841451", "CN"))
    assert isinstance(dto, CustomsTrendDTO)
    assert dto.country_code == "CN"
    assert dto.points
    # Each record's hs_code is normalised to 6 digits.
    assert all(len(p.hs_code) == 6 for p in dto.points)


def test_hs_code_lookup_matches_korean_name():
    client = MockHsCodeClient()
    rows = _run(client.fetch("선풍기"))
    assert rows and all(isinstance(r, HsCodeDTO) for r in rows)
    assert any("선풍기" in r.name_ko for r in rows)


def test_exchange_rate_returns_decimal_rate():
    client = MockExchangeRateClient()
    dto = _run(client.fetch("CNY/KRW"))
    assert isinstance(dto, ExchangeRateDTO)
    assert dto.currency_pair == "CNY/KRW"
    # Sanity range — CNY/KRW lives around 180-200.
    assert 100 < float(dto.rate) < 300


def test_youtube_returns_signal_dto():
    client = MockYouTubeClient()
    dto = _run(client.fetch("휴대용선풍기"))
    assert isinstance(dto, YouTubeSignalDTO)
    assert dto.total_video_count > 0
    assert dto.avg_view_count > 0


def test_google_trends_returns_dto_with_rising():
    client = MockGoogleTrendsClient()
    dto = _run(client.fetch("휴대용선풍기", region="KR"))
    assert isinstance(dto, GoogleTrendDTO)
    assert dto.region == "KR"
    assert dto.points
    assert dto.related_rising
