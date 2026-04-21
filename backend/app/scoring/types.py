"""Local DTO stubs for the scoring engine.

The shared contract module ``backend/app/contracts/dto.py`` is being
authored by the **Data Collection Agent** in parallel. Until it lands,
this module declares the *minimum subset of fields* that the scoring
functions consume, with the exact field names from the spec so the
later swap is a one-line import change.

Migration plan once ``contracts/dto.py`` exists:

* Replace each ``...DTO`` class definition below with:
  ``from app.contracts.dto import ...``
* Delete the local definitions.
* Re-run ``pytest tests/scoring`` -- if any field name drifts, this
  file is the single source of truth for the scoring side of the
  contract and a follow-up sync is required.

Channel / Recommendation enums are re-exported from the SQLAlchemy
models so the scoring layer and the persistence layer agree by
construction.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Re-export persistence-layer enums to avoid drift.
from app.models.channel_profit import Channel
from app.models.product_score import Recommendation

__all__ = [
    "Channel",
    "Recommendation",
    "TrendPoint",
    "KeywordVolumeDTO",
    "NaverTrendDTO",
    "ShoppingItemDTO",
    "ShoppingResultDTO",
    "BlogCafeDTO",
    "CoupangProductDTO",
    "CoupangSearchDTO",
    "CustomsTrendPoint",
    "CustomsTrendDTO",
    "ExchangeRateDTO",
    "YouTubeSignalDTO",
    "GoogleTrendDTO",
]


class _StubModel(BaseModel):
    """Permissive base for stubs.

    ``extra='ignore'`` so the eventual real DTOs (which may carry more
    fields) deserialize cleanly into these subsets during tests.
    """

    model_config = ConfigDict(extra="ignore")


# ----- Shared trend point ---------------------------------------------------


class TrendPoint(_StubModel):
    period: date
    ratio: float = Field(..., description="0~100 normalized index")


# ----- Naver Search Ad ------------------------------------------------------


class KeywordVolumeDTO(_StubModel):
    """Spec field set for scoring; superset of the wire DTO."""

    term: str
    pc_monthly_volume: int = Field(..., ge=0)
    mobile_monthly_volume: int = Field(..., ge=0)
    total_monthly_volume: int = Field(..., ge=0)
    competition_index: float = Field(
        ..., ge=0.0, le=1.0, description="0=낮음, 1=높음"
    )
    related_keywords: list[str] = Field(default_factory=list)


# ----- Naver DataLab --------------------------------------------------------


class NaverTrendDTO(_StubModel):
    term: str
    points: list[TrendPoint] = Field(default_factory=list)
    growth_rate_3m: float = Field(
        0.0, description="−0.1 = −10%, +0.5 = +50% (decimal, NOT pct)"
    )
    growth_rate_6m: float = 0.0
    growth_rate_12m: float = 0.0


# ----- Naver Shopping -------------------------------------------------------


class ShoppingItemDTO(_StubModel):
    title: str
    price: int = Field(..., ge=0)
    review_count: int = Field(0, ge=0)


class ShoppingResultDTO(_StubModel):
    query: str
    total_count: int = Field(..., ge=0)
    items: list[ShoppingItemDTO] = Field(default_factory=list)
    avg_price: int = Field(0, ge=0)
    median_price: int = Field(0, ge=0)
    top10_avg_review_count: int = Field(0, ge=0)


# ----- Naver Blog/Cafe ------------------------------------------------------


class BlogCafeDTO(_StubModel):
    term: str
    blog_post_count: int = Field(0, ge=0)
    cafe_post_count: int = Field(0, ge=0)
    recent_30d_blog_count: int = Field(0, ge=0)
    recent_30d_growth_rate: float = Field(
        0.0, description="0.5 = +50% vs prior 30d"
    )


# ----- Coupang Partners -----------------------------------------------------


class CoupangProductDTO(_StubModel):
    product_id: str
    name: str
    price: int = Field(..., ge=0)
    rating: float = Field(0.0, ge=0.0, le=5.0)
    review_count: int = Field(0, ge=0)
    is_rocket: bool = False


class CoupangSearchDTO(_StubModel):
    query: str
    items: list[CoupangProductDTO] = Field(default_factory=list)
    avg_price: int = Field(0, ge=0)
    rocket_ratio: float = Field(0.0, ge=0.0, le=1.0)


# ----- 관세청 Customs --------------------------------------------------------


class CustomsTrendPoint(_StubModel):
    year_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    import_value_usd: float = Field(..., ge=0.0)
    import_quantity: float = Field(0.0, ge=0.0)


class CustomsTrendDTO(_StubModel):
    hs_code: str
    country_code: str = "CN"
    points: list[CustomsTrendPoint] = Field(default_factory=list)
    growth_rate_3m: float = Field(
        0.0, description="decimal, e.g. 0.34 = +34%"
    )
    growth_rate_12m: float = 0.0


# ----- Exchange Rate --------------------------------------------------------


class ExchangeRateDTO(_StubModel):
    currency_pair: Literal["CNY/KRW", "USD/KRW", "JPY/KRW", "EUR/KRW"]
    rate: float = Field(..., gt=0.0)
    fetched_at: str  # ISO-8601 timestamp


# ----- YouTube --------------------------------------------------------------


class YouTubeSignalDTO(_StubModel):
    term: str
    total_video_count: int = Field(0, ge=0)
    recent_30d_video_count: int = Field(0, ge=0)
    avg_view_count: float = Field(0.0, ge=0.0)
    growth_rate_30d: float = Field(0.0, description="decimal")


# ----- Google Trends --------------------------------------------------------


class GoogleTrendDTO(_StubModel):
    term: str
    region: str = "KR"
    points: list[TrendPoint] = Field(default_factory=list)
    related_rising: list[str] = Field(default_factory=list)
    growth_rate_3m: float = 0.0
