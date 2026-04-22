"""Stateless landed-cost + per-channel profit calculator.

No DB writes — callers pass all inputs and get the same breakdown shape
as ``/products/{id}`` without committing a product row. Used by the
`/calculator` page when evaluating candidates that aren't in the
recommendation list yet.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DbSession
from app.models import CoupangFee, ExchangeRate
from app.scoring import (
    RevenueInputs,
    calculate_coupang_revenue,
    calculate_smartstore_revenue,
    compute_cost_breakdown,
)
from app.schemas.responses.product import (
    ChannelProfitResponse,
    CostBreakdownResponse,
)
from app.services.product_service import _lookup_intl_shipping_krw

router = APIRouter(prefix="/calculator", tags=["calculator"])


class CalculatorRequest(BaseModel):
    cny_price: float = Field(..., gt=0, description="1688 단가 (CNY)")
    moq: int = Field(..., gt=0)
    expected_sell_price_krw: int = Field(..., gt=0, description="예상 판매가 (KRW)")
    category_name: str = Field(..., description="Coupang 수수료 조회용")
    china_domestic_shipping_krw: int = Field(
        0, ge=0, description="중국 국내 배송비 (KRW, 총액)"
    )
    # Either unit_weight_kg (자동 국제 배송 계산) or intl_shipping_krw (수동).
    unit_weight_kg: float | None = Field(None, gt=0, description="개당 무게 (kg)")
    shipping_method: str | None = Field(
        None, description="'lcl' / 'sea_self' / None(auto)"
    )
    intl_shipping_krw: int | None = Field(
        None, ge=0, description="국제 배송비 직접 입력 (무게 미입력 시 사용)"
    )
    customs_duty_pct: float = Field(
        0.08, ge=0, le=1, description="관세율 (decimal). 기본 8%"
    )
    ad_cost_pct: float = Field(
        0.10, ge=0, le=1, description="광고비 비율 (decimal)"
    )


class CalculatorResponse(BaseModel):
    cost_breakdown: CostBreakdownResponse
    channel_profits: list[ChannelProfitResponse]
    recommended_channel: str | None


def _latest_cny_krw(db) -> Decimal:
    rate = db.execute(
        select(ExchangeRate.rate)
        .where(ExchangeRate.pair == "CNY/KRW")
        .order_by(ExchangeRate.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return Decimal(str(rate)) if rate is not None else Decimal("195")


def _coupang_fee_pct(db, category_name: str) -> Decimal:
    fee = db.execute(
        select(CoupangFee.fee_pct)
        .where(CoupangFee.category_path == category_name)
        .order_by(CoupangFee.effective_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    return Decimal(str(fee)) / 100 if fee is not None else Decimal("0.108")


@router.post(
    "",
    response_model=CalculatorResponse,
    summary="Stateless cost + channel-profit estimate",
)
def estimate(request: CalculatorRequest, db: DbSession) -> CalculatorResponse:
    rate = _latest_cny_krw(db)

    # Resolve intl shipping: weight-based auto > manual override.
    intl_price: int | None = None
    applied_method: str | None = None
    total_weight_kg: float | None = None
    if request.unit_weight_kg and request.unit_weight_kg > 0:
        total_weight = Decimal(str(request.unit_weight_kg)) * Decimal(request.moq)
        total_weight_kg = float(total_weight)
        intl_price, applied_method = _lookup_intl_shipping_krw(
            db, request.shipping_method, total_weight
        )
    if intl_price is None and request.intl_shipping_krw is not None:
        intl_price = int(request.intl_shipping_krw)

    if intl_price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unit_weight_kg 또는 intl_shipping_krw 중 하나는 필요합니다.",
        )

    # Build RevenueInputs shared by both channel calculators.
    ad_decimal = Decimal(str(request.ad_cost_pct))
    base_inputs = RevenueInputs(
        cny_price=Decimal(str(request.cny_price)),
        moq=request.moq,
        expected_sell_price_krw=request.expected_sell_price_krw,
        category_name=request.category_name,
        exchange_rate=rate,
        china_domestic_shipping_krw=request.china_domestic_shipping_krw,
        intl_shipping_krw=intl_price,
        customs_duty_pct=Decimal(str(request.customs_duty_pct)),
        ad_cost_pct=ad_decimal,
    )

    bd = compute_cost_breakdown(base_inputs)
    smartstore = calculate_smartstore_revenue(base_inputs)
    coupang_fee = _coupang_fee_pct(db, request.category_name)
    coupang = calculate_coupang_revenue(base_inputs, coupang_fee)

    profits = [
        ChannelProfitResponse(
            channel=r.channel.value if hasattr(r.channel, "value") else str(r.channel),
            unit_cost_krw=float(r.unit_cost_krw),
            expected_price_krw=float(r.expected_price_krw),
            platform_fee_pct=float(r.platform_fee_pct),
            ad_cost_pct=float(r.ad_cost_pct),
            unit_profit_krw=float(r.unit_profit_krw),
            margin_pct=float(r.margin_pct),
            roi_pct=float(r.roi_pct),
            breakeven_units=int(r.breakeven_units),
        )
        for r in (smartstore, coupang)
    ]
    recommended = max(profits, key=lambda p: p.unit_profit_krw).channel if profits else None

    cost_breakdown = CostBreakdownResponse(
        moq=bd.moq,
        goods_cost_krw=bd.goods_cost_krw,
        china_domestic_shipping_krw=bd.china_domestic_shipping_krw,
        intl_shipping_krw=bd.intl_shipping_krw,
        cif_krw=bd.cif_krw,
        cif_usd_approx=bd.cif_usd_approx,
        customs_duty_krw=bd.customs_duty_krw,
        vat_krw=bd.vat_krw,
        filing_fee_krw=bd.filing_fee_krw,
        mokrok_duty_free=bd.mokrok_duty_free,
        total_cost_krw=bd.total_cost_krw,
        unit_cost_krw=bd.unit_cost_krw,
        effective_duty_pct=bd.effective_duty_pct,
        effective_vat_pct=bd.effective_vat_pct,
        suggested_base_duty_pct=None,
        suggested_kcfta_duty_pct=None,
        duty_source="user_override",
        exchange_rate_cny_krw=float(rate),
        expected_sell_price_krw=request.expected_sell_price_krw,
        naver_avg_price_krw=None,
        sell_price_source="user_override",
        shipping_method_applied=applied_method,
        total_weight_kg=total_weight_kg,
        intl_shipping_source="rate_table" if applied_method else "user_override",
    )
    return CalculatorResponse(
        cost_breakdown=cost_breakdown,
        channel_profits=profits,
        recommended_channel=recommended,
    )
