"""Response schemas for ``GET /opportunities``.

Mirrors the wireframe in spec §6.1:

    1위 ⭐ 87점  고양이 자동급수기
       월 검색 28K ↑19% │ 수입량 ↑34% │ 경쟁 낮음
       스마트스토어 평균가 38K / 쿠팡 42K
       [1688에서 찾기 →] [상품 입력]
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CompetitionBreakdown(BaseModel):
    """Inputs that produced the competition subscore, for UI tooltip."""

    model_config = ConfigDict(extra="forbid")

    competition_index: float | None = Field(
        default=None,
        description="네이버 검색광고 competition_index (0=낮음, 0.8=높음)",
    )
    demand_factor: float | None = Field(
        default=None,
        description="검색량 기반 demand gate (1K미만=0, 10K+=1.0 선형)",
    )
    shopping_penalty: float | None = Field(
        default=None,
        description="쇼핑 상품수 과포화 감점 (500K+ → 0.7, 200K+ → 0.85, else 1.0)",
    )


class OpportunityMetricsSummary(BaseModel):
    """Compact metric bundle for the keyword card."""

    model_config = ConfigDict(extra="forbid")

    monthly_search_volume: int | None = Field(
        default=None, description="Latest monthly search volume (PC + mobile)."
    )
    search_growth_3m: float | None = Field(
        default=None, description="3-month search-volume growth rate (-1.0 ~ +N)."
    )
    # --- 수입성장: actual percent from customs (was 0-1 proxy before) ---
    customs_growth_3m_pct: float | None = Field(
        default=None,
        description="관세청 수입량 최근 3개월 vs 직전 3개월 성장률 (percent).",
    )
    import_growth: float | None = Field(
        default=None,
        description="DEPRECATED: customs_score/20 0-1 proxy. Use customs_growth_3m_pct.",
    )
    # --- 경쟁도: actual 0-20 score + formula inputs (replaces 낮음/중간/높음) ---
    competition_raw_score: float | None = Field(
        default=None, description="경쟁 공백 subscore 0~20 (높을수록 블루오션)."
    )
    competition_breakdown: CompetitionBreakdown | None = Field(
        default=None, description="경쟁 subscore 입력값 (계산식 툴팁용)."
    )
    competition_level: str | None = Field(
        default=None,
        description="DEPRECATED: 낮음/중간/높음 label. Use competition_raw_score.",
    )
    naver_shopping_count: int | None = Field(
        default=None,
        description="네이버 쇼핑 검색 결과 상품 수 (경쟁 강도 간접 지표).",
    )
    smartstore_avg_price_krw: int | None = Field(
        default=None,
        description="네이버 쇼핑(스마트스토어) 평균가.",
    )
    coupang_avg_price_krw: int | None = Field(
        default=None,
        description="쿠팡 평균가 (Option A: 미수집).",
    )


class OpportunityResponse(BaseModel):
    """One row of the TOP 20 opportunity list."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(..., ge=1, description="1-based rank within the list.")
    keyword_id: int = Field(..., description="DB id of the keyword.")
    term: str = Field(..., description="Keyword text.")
    category_id: int | None = Field(default=None, description="Linked category id.")
    category_name: str | None = Field(default=None)

    score_details: dict | None = Field(
        default=None,
        description=(
            "Raw per-axis breakdown from the scorer (demand, growth, "
            "competition, customs, trend, stability). Used by the UI to "
            "render formula tooltips."
        ),
    )

    snapshot_date: date = Field(..., description="When the score was computed.")
    total_score: float = Field(..., ge=0, le=100)
    demand_score: float = Field(..., ge=0)
    growth_score: float = Field(..., ge=0)
    competition_score: float = Field(..., ge=0)
    customs_score: float = Field(..., ge=0)
    trend_score: float = Field(..., ge=0)
    stability_score: float = Field(..., ge=0)

    is_excluded: bool = Field(default=False)
    exclusion_reasons: str | None = None

    metrics: OpportunityMetricsSummary = Field(
        default_factory=OpportunityMetricsSummary,
        description="Latest snapshot of underlying KPIs.",
    )

    search_1688_url: str = Field(
        ...,
        description="Deep link to 1688 search for this term.",
    )

    product_count: int = Field(
        default=0,
        ge=0,
        description="Number of products already registered for this keyword.",
    )
