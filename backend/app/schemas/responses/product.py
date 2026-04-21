"""Response schemas for product endpoints (spec §6.2)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChannelLiteral = Literal["SMARTSTORE", "COUPANG"]
RecommendationLiteral = Literal["GO", "CONDITIONAL", "PASS"]


class ChannelProfitResponse(BaseModel):
    """Per-channel margin breakdown -- one row of the §6.2 comparison table."""

    model_config = ConfigDict(extra="forbid")

    channel: ChannelLiteral
    unit_cost_krw: float = Field(..., ge=0)
    expected_price_krw: float = Field(..., ge=0)
    platform_fee_pct: float = Field(..., ge=0)
    ad_cost_pct: float = Field(..., ge=0)
    unit_profit_krw: float
    margin_pct: float
    roi_pct: float
    breakeven_units: int = Field(..., ge=0)


class CostBreakdownResponse(BaseModel):
    """Landed-cost decomposition shown on product detail page."""

    model_config = ConfigDict(extra="forbid")

    moq: int
    goods_cost_krw: int = Field(..., description="상품 원가 (CNY×MOQ×환율).")
    china_domestic_shipping_krw: int = Field(..., description="중국 국내 배송비.")
    intl_shipping_krw: int = Field(..., description="국제 배송비 총액.")
    cif_krw: int = Field(..., description="CIF = 상품원가+중국국내+국제배송.")
    cif_usd_approx: float = Field(..., description="CIF USD 근사값.")
    customs_duty_krw: int = Field(..., description="관세.")
    vat_krw: int = Field(..., description="부가세.")
    filing_fee_krw: int = Field(..., description="수입신고 대행 수수료.")
    mokrok_duty_free: bool = Field(
        ..., description="목록통관 면세 적용 여부 (CIF ≤ USD 150)."
    )
    total_cost_krw: int = Field(..., description="총 수입 원가 (MOQ 기준).")
    unit_cost_krw: int = Field(..., description="개당 원가.")
    effective_duty_pct: float
    effective_vat_pct: float
    suggested_base_duty_pct: float | None = Field(
        default=None,
        description="HS 코드 자동 조회한 기본 관세율. 사용자 override 판단용.",
    )
    suggested_kcfta_duty_pct: float | None = Field(
        default=None,
        description="HS 코드 자동 조회한 한-중 FTA 관세율.",
    )
    duty_source: str | None = Field(
        default=None,
        description=(
            "적용된 관세율 출처: 'user_override' / 'hs_lookup' / 'default_8pct'."
        ),
    )
    exchange_rate_cny_krw: float = Field(
        ...,
        description="계산에 사용된 CNY→KRW 환율 (실시간 반영). "
                    "UI는 이 값으로 위안화 입력을 원화로 환산.",
    )
    expected_sell_price_krw: int | None = Field(
        default=None,
        description="현재 적용된 판매가 (사용자 override > Naver avg > 휴리스틱).",
    )
    naver_avg_price_krw: int | None = Field(
        default=None,
        description="참고용 Naver 쇼핑 실측 평균가 (편집 폼 힌트).",
    )
    sell_price_source: str | None = Field(
        default=None,
        description="판매가 출처: 'user_override' / 'naver_avg' / 'heuristic_3x'.",
    )
    shipping_method_applied: str | None = Field(
        default=None,
        description="적용된 국제 운송 방식: 'lcl' / 'sea_self' / None (수동 override).",
    )
    total_weight_kg: float | None = Field(
        default=None,
        description="MOQ × 개당 무게 (kg).",
    )
    intl_shipping_source: str | None = Field(
        default=None,
        description="국제배송비 출처: 'user_override' / 'auto_lookup' / 'default_per_unit'.",
    )


class ProductScoreResponse(BaseModel):
    """Composite product score (spec §5.3)."""

    model_config = ConfigDict(extra="forbid")

    product_id: int
    snapshot_date: date
    total_score: float = Field(..., ge=0, le=100)
    opportunity_score: float = Field(..., ge=0)
    profit_score: float = Field(..., ge=0)
    risk_score: float = Field(..., ge=0)
    stability_score: float = Field(..., ge=0)
    recommendation: RecommendationLiteral

    channel_profits: list[ChannelProfitResponse] = Field(default_factory=list)
    recommended_channel: ChannelLiteral | None = Field(
        default=None,
        description="Channel with the higher unit profit (None on tie / no data).",
    )
    cost_breakdown: CostBreakdownResponse | None = Field(
        default=None,
        description="원가 구성 내역 (CIF, 관세, 부가세, 수입신고).",
    )


class ProductResponse(BaseModel):
    """A user-input product without scoring detail (used in lists)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    keyword_id: int | None = None
    url: str
    name: str | None = None
    cny_price: float
    moq: int
    notes: str | None = None
    created_by_user: str | None = None
    created_at: datetime
    latest_score: ProductScoreResponse | None = Field(
        default=None,
        description="Most recent score snapshot, if any.",
    )


class ProductDetailResponse(ProductResponse):
    """Single-product detail -- adds full score history."""

    score_history: list[ProductScoreResponse] = Field(default_factory=list)


class PaginatedProductsResponse(BaseModel):
    """Paginated list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProductResponse]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=200)
    offset: int = Field(..., ge=0)
