"""Shared DTO contracts for the three agents.

IMPORTANT
---------
This file is the **interface contract** between Data Collection, Scoring
and Backend API agents. Changing a field name or its declared type here
is a cross-agent breaking change — the other two agents import from this
module directly. If you need to evolve the shape, add an *optional* field
with a default and socialise the change first.

Conventions
-----------
* Prices are integer KRW.
* ``ratio`` / ``growth_rate_*`` are percentages unless the field comment
  says otherwise.
* ``competition_index`` is a normalized float in ``[0.0, 1.0]``.
* ``country_code`` / ``region`` follow ISO-3166 alpha-2 (e.g. "CN", "KR").
* ``year_month`` is ``"YYYY-MM"``.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


# ---- shared enums --------------------------------------------------


class Channel(str, Enum):
    """Sales channel used by both product records and channel_profit rows."""

    SMARTSTORE = "smartstore"
    COUPANG = "coupang"


class Recommendation(str, Enum):
    """Final go/no-go verdict produced by the Scoring Engine."""

    GO = "GO"
    CONDITIONAL = "CONDITIONAL"
    PASS = "PASS"


# ---- 네이버 검색광고 keywordstool -------------------------------------


class KeywordVolumeDTO(BaseModel):
    """Monthly search volume + competition for a single keyword.

    Source: 네이버 검색광고 API ``/keywordstool``.
    """

    term: str
    pc_monthly_volume: int
    mobile_monthly_volume: int
    total_monthly_volume: int
    competition_index: float = Field(..., ge=0.0, le=1.0)
    related_keywords: list[str] = Field(default_factory=list)


# ---- 네이버 DataLab -------------------------------------------------


class TrendPoint(BaseModel):
    """One point on a DataLab / Google-Trends style time series.

    ``ratio`` is the native 0–100 normalised value both Naver and Google
    expose; callers treat it as an interest index, not a raw volume.
    """

    period: date
    ratio: float = Field(..., ge=0.0, le=100.0)


class NaverTrendDTO(BaseModel):
    """Trend curve for a term plus 3/6/12-month growth rates (percent)."""

    term: str
    points: list[TrendPoint]
    growth_rate_3m: float
    growth_rate_6m: float
    growth_rate_12m: float


# ---- 네이버 쇼핑 -----------------------------------------------------


class ShoppingItem(BaseModel):
    """A single item from 네이버 쇼핑 search results."""

    title: str
    mall_name: str
    price: int
    review_count: int | None = None
    category1: str | None = None
    category2: str | None = None


class ShoppingResultDTO(BaseModel):
    """Aggregated 네이버 쇼핑 search result.

    ``total_count`` is the upstream-reported total number of matches
    (not ``len(items)``). ``top10_avg_review_count`` is a float because
    it's a mean over at most 10 items.
    """

    query: str
    total_count: int
    items: list[ShoppingItem]
    avg_price: int
    median_price: int
    top10_avg_review_count: float


# ---- 네이버 블로그 / 카페 --------------------------------------------


class BlogCafeDTO(BaseModel):
    """Blog + café post counts used as a social-buzz signal."""

    term: str
    blog_post_count: int
    cafe_post_count: int
    recent_30d_blog_count: int
    recent_30d_growth_rate: float


# ---- 쿠팡 파트너스 ---------------------------------------------------


class CoupangProductDTO(BaseModel):
    """One product in a Coupang Partners search result."""

    product_id: str
    name: str
    price: int
    rating: float = Field(..., ge=0.0, le=5.0)
    review_count: int
    is_rocket: bool
    category_path: str


class CoupangSearchDTO(BaseModel):
    """Aggregated Coupang Partners search (quota: 10 req/h — cache 24h)."""

    query: str
    items: list[CoupangProductDTO]
    avg_price: int
    rocket_ratio: float = Field(..., ge=0.0, le=1.0)


# ---- 관세청 품목별 국가별 수출입 실적 --------------------------------


class CustomsImportDTO(BaseModel):
    """Monthly customs import record for ``(hs_code, country, year_month)``."""

    hs_code: str  # 6 digits is the contract default; 10 allowed upstream.
    year_month: str  # "YYYY-MM"
    country_code: str
    import_quantity: Decimal
    import_value_usd: Decimal


class CustomsTrendDTO(BaseModel):
    """Import trend for one HS code + country pair."""

    hs_code: str
    country_code: str
    points: list[CustomsImportDTO]
    growth_rate_3m: float
    growth_rate_12m: float


# ---- HS 부호 --------------------------------------------------------


class HsCodeDTO(BaseModel):
    """HS code lookup row."""

    code: str
    name_ko: str
    name_en: str | None = None


# ---- 환율 -----------------------------------------------------------


class ExchangeRateDTO(BaseModel):
    """Single exchange-rate snapshot.

    ``currency_pair`` uses slash notation, e.g. ``"CNY/KRW"``. ``rate`` is
    a ``Decimal`` so round-tripping through JSON / Postgres doesn't lose
    precision.
    """

    currency_pair: str
    rate: Decimal
    fetched_at: datetime


# ---- YouTube --------------------------------------------------------


class YouTubeSignalDTO(BaseModel):
    """Aggregated YouTube signal for a search term."""

    term: str
    total_video_count: int
    recent_30d_video_count: int
    avg_view_count: int
    growth_rate_30d: float


# ---- Google Trends --------------------------------------------------


class GoogleTrendDTO(BaseModel):
    """Google Trends interest curve plus rising related queries."""

    term: str
    region: str
    points: list[TrendPoint]
    related_rising: list[str] = Field(default_factory=list)
    growth_rate_3m: float
