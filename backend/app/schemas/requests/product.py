"""Request body for ``POST /products``."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProductCreateRequest(BaseModel):
    """User-supplied 1688 product details (spec §5.1).

    Three required fields (URL / CNY 단가 / MOQ) plus an optional
    ``keyword_id`` link back to the opportunity keyword that triggered
    the sourcing decision and an optional ``notes`` for free-form notes
    (e.g. supplier name, lead time).
    """

    model_config = ConfigDict(extra="forbid")

    keyword_id: int | None = Field(
        default=None,
        description="Linked keyword id (omit if sourcing without a keyword).",
        ge=1,
    )
    url: HttpUrl = Field(
        ...,
        description="1688 product URL.",
    )
    cny_price: float = Field(
        ...,
        gt=0,
        description="Unit price quoted in CNY.",
    )
    moq: int = Field(
        ...,
        ge=1,
        description="Minimum order quantity (units).",
    )
    china_domestic_shipping_krw: int | None = Field(
        default=None,
        ge=0,
        description="중국 국내 배송비 (공장→배송대행지) 총액. "
                    "None이면 0원으로 계산.",
    )
    intl_shipping_krw: int | None = Field(
        default=None,
        ge=0,
        description="국제 배송비 (중국→한국) 총액. "
                    "None이면 개당 4,000원 × MOQ로 추정.",
    )
    customs_duty_pct: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="관세율 (decimal). 0.08 = 8%. "
                    "한-중 FTA 대상 품목이면 0.0 ~ 0.05로 조정. None이면 8%.",
    )
    expected_sell_price_krw: int | None = Field(
        default=None,
        ge=0,
        description="판매가 수동 지정 (KRW). None이면 Naver 쇼핑 평균가 사용.",
    )
    ad_cost_pct: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="광고비 비율 (decimal). 0 = 유기적 판매. "
                    "None이면 채널별 기본(SS 10%, 쿠팡 15%).",
    )
    unit_weight_kg: float | None = Field(
        default=None,
        ge=0,
        description="개당 무게 (kg). 국제배송비 자동 조회용.",
    )
    shipping_method: str | None = Field(
        default=None,
        description="운송 방식: 'lcl' / 'sea_self'. None이면 무게로 자동 선택.",
    )
    name: str | None = Field(
        default=None,
        max_length=500,
        description="Optional human-readable product name.",
    )
    notes: str | None = Field(
        default=None,
        description="Free-form notes (supplier, lead time, etc.).",
    )
    created_by_user: str | None = Field(
        default=None,
        max_length=255,
        description="User identifier (single-user mode → typically null).",
    )


class ProductUpdateRequest(BaseModel):
    """Partial update for cost parameters that the user may adjust on the
    detail page. Any ``None`` field is left unchanged.

    When at least one field is supplied the server re-runs the scorer
    and persists a new ``product_scores`` snapshot for today.
    """

    model_config = ConfigDict(extra="forbid")

    moq: int | None = Field(default=None, ge=1)
    china_domestic_shipping_krw: int | None = Field(default=None, ge=0)
    intl_shipping_krw: int | None = Field(default=None, ge=0)
    customs_duty_pct: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="관세율 (decimal). 0.08=8% 기본, 한-중 FTA는 0.0~0.05.",
    )
    expected_sell_price_krw: int | None = Field(
        default=None,
        ge=0,
        description="판매가 수동 지정 (KRW). 변경 시 마진율 즉시 재계산.",
    )
    ad_cost_pct: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="광고비 비율 (decimal). 0 = 광고 미집행.",
    )
    unit_weight_kg: float | None = Field(
        default=None, ge=0, description="개당 무게 (kg)."
    )
    shipping_method: str | None = Field(
        default=None,
        description="운송 방식: 'lcl' / 'sea_self'. None이면 자동 선택.",
    )
