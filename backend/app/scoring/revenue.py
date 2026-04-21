"""Per-channel revenue / margin / ROI calculation (기획서 §5.2).

The math is the same for both channels; what differs is the platform
fee (스마트스토어 5.5% fixed vs 쿠팡 카테고리별) and the default ad-spend
ratio (10% vs 15%, spec §9). The caller (Backend / Scoring orchestrator)
is responsible for fetching the Coupang fee from ``coupang_fees`` and
passing it in -- this module deliberately avoids any DB access.

All money is held as :class:`~decimal.Decimal` to dodge the float rounding
errors that bite when KRW totals are rolled up across MOQ × unit. The
final result struct uses ``int`` for KRW (sub-won precision is not
meaningful) and ``float`` for percentages (display).
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from .types import Channel

__all__ = [
    "RevenueInputs",
    "ChannelRevenueResult",
    "CostBreakdown",
    "compute_cost_breakdown",
    "SMARTSTORE_FEE_PCT",
    "DEFAULT_SMARTSTORE_AD_PCT",
    "DEFAULT_COUPANG_AD_PCT",
    "DEFAULT_CUSTOMS_DUTY_PCT",
    "DEFAULT_VAT_PCT",
    "DEFAULT_INTL_SHIPPING_PER_UNIT_KRW",
    "DEFAULT_FILING_FEE_KRW",
    "MOKROK_THRESHOLD_USD",
    "calculate_smartstore_revenue",
    "calculate_coupang_revenue",
]

# ---- constants -------------------------------------------------------------

#: 스마트스토어 수수료 = 5.5% (결제 수수료 포함 단순화).
SMARTSTORE_FEE_PCT: Decimal = Decimal("0.055")

#: 광고비 기본값.
DEFAULT_SMARTSTORE_AD_PCT: Decimal = Decimal("0.10")
DEFAULT_COUPANG_AD_PCT: Decimal = Decimal("0.15")

#: 관세 기본값 — 반려동물 카테고리 대부분 8%. HS코드 기반 조회로 override.
DEFAULT_CUSTOMS_DUTY_PCT: Decimal = Decimal("0.08")

#: 부가세 고정 10%.
DEFAULT_VAT_PCT: Decimal = Decimal("0.10")

#: 국제배송 기본 가정 — 개당 4,000원 (평균 1kg 가정, kg당 ~4천원대).
DEFAULT_INTL_SHIPPING_PER_UNIT_KRW: int = 4_000

#: 수입신고 대행 수수료 (CIF > 목록통관 한도일 때만 부과).
DEFAULT_FILING_FEE_KRW: int = 30_000

#: 목록통관 자가사용 한도. 이 도구는 **판매 목적 소싱**을 전제로 해서
#: 자동 적용하지 않는다 (판매 목적 수입은 CIF 금액 무관하게 정식 수입
#: 통관 대상). 사용자 UI 설명용으로만 사용.
MOKROK_THRESHOLD_USD: Decimal = Decimal("150")

#: 1 CNY ≈ 몇 USD인지 rough-cut (실시간 환율 호출 안 하고 정적 변환만
#: 필요한 경우 사용). 정확한 환율은 caller가 ``exchange_rate``로 전달.
_CNY_TO_USD_APPROX: Decimal = Decimal("0.14")

#: Cap MOQ at this for breakeven_units sentinel when unit_profit ≤ 0.
BREAKEVEN_INFINITE_SENTINEL: int = 10**9


# ---- inputs / outputs ------------------------------------------------------


class RevenueInputs(BaseModel):
    """Everything needed to compute one channel's economics for one product."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cny_price: Decimal = Field(..., gt=Decimal(0), description="1688 단가 (CNY)")
    moq: int = Field(..., gt=0)
    expected_sell_price_krw: int = Field(..., gt=0)
    category_name: str
    exchange_rate: Decimal = Field(
        ..., gt=Decimal(0), description="CNY → KRW (e.g. 195)"
    )
    # ---- 수입 원가 구성 (모두 optional, 전체 MOQ 기준 총액) ----
    china_domestic_shipping_krw: int = Field(
        0, ge=0,
        description="중국 국내 배송비 (공장→배송대행지). 1688 상품에 보통 포함.",
    )
    intl_shipping_krw: int | None = Field(
        None, ge=0,
        description="국제 배송비 (중국→한국) 총액. None이면 "
                    "DEFAULT_INTL_SHIPPING_PER_UNIT_KRW × MOQ로 추정.",
    )
    customs_duty_pct: Decimal = Field(
        DEFAULT_CUSTOMS_DUTY_PCT,
        ge=Decimal(0),
        description="관세율 (CIF 대비). 기본 8% — HS코드별 override.",
    )
    vat_pct: Decimal = Field(
        DEFAULT_VAT_PCT,
        ge=Decimal(0),
        description="부가세율 (CIF+관세 대비). 고정 10%.",
    )
    filing_fee_krw: int | None = Field(
        None, ge=0,
        description="수입신고 대행 수수료. None이면 목록통관 한도 자동 판단.",
    )
    ad_cost_pct: Decimal = Field(
        ..., ge=Decimal(0), description="채널별 광고비 비율 (호출자 지정)"
    )


class CostBreakdown(BaseModel):
    """Full landed-cost decomposition for one product (all in KRW, MOQ total).

    Shown on the product detail page so the operator can see *why* the
    unit cost is what it is.
    """

    moq: int
    goods_cost_krw: int = Field(..., description="상품 원가 (CNY×MOQ×환율).")
    china_domestic_shipping_krw: int
    intl_shipping_krw: int
    cif_krw: int = Field(
        ..., description="CIF = 상품원가 + 중국국내배송 + 국제배송 (관세 과표)."
    )
    cif_usd_approx: float = Field(
        ..., description="CIF를 USD로 환산한 근사값 (목록통관 판단용)."
    )
    customs_duty_krw: int
    vat_krw: int
    filing_fee_krw: int
    mokrok_duty_free: bool = Field(
        ...,
        description=(
            "판매 목적 수입은 목록통관 면세 대상이 아니므로 항상 False. "
            "UI는 이 값을 참고해 면세 여부를 표시."
        ),
    )
    total_cost_krw: int
    unit_cost_krw: int
    effective_duty_pct: float = Field(
        ..., description="적용된 관세율 (면세면 0)."
    )
    effective_vat_pct: float = Field(
        ..., description="적용된 부가세율 (면세면 0)."
    )


class ChannelRevenueResult(BaseModel):
    """Per-channel computed economics. Persisted to ``channel_profits``."""

    channel: Channel
    unit_cost_krw: int
    expected_price_krw: int
    platform_fee_pct: float
    ad_cost_pct: float
    unit_profit_krw: int
    margin_pct: float
    roi_pct: float
    breakeven_units: int


# ---- helpers ---------------------------------------------------------------


def _q_money(value: Decimal) -> int:
    """Round a Decimal KRW amount to the nearest integer won."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _q_pct(value: Decimal) -> float:
    """Quantize a percentage to 4-decimal precision and return float."""
    return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def compute_cost_breakdown(inputs: RevenueInputs) -> CostBreakdown:
    """Break the landed cost into its legally-meaningful pieces.

    Pipeline
    --------
    goods = cny × MOQ × 환율
    CIF   = goods + 중국국내배송 + 국제배송
    관세  = CIF × duty_pct     (목록통관 면세 시 0)
    부가세 = (CIF + 관세) × vat  (면세 시 0)
    수입신고 = 30,000원 고정    (면세 시 0)
    total = CIF + 관세 + 부가세 + 수입신고
    """
    moq = Decimal(inputs.moq)
    goods = inputs.cny_price * moq * inputs.exchange_rate
    china_domestic = Decimal(inputs.china_domestic_shipping_krw)
    intl = Decimal(
        inputs.intl_shipping_krw
        if inputs.intl_shipping_krw is not None
        else DEFAULT_INTL_SHIPPING_PER_UNIT_KRW * inputs.moq
    )
    cif = goods + china_domestic + intl

    # CIF USD approx purely for UI context (show "CIF ≈ $xxx" next to
    # the line). The mokrok 자가사용 면세는 "판매 목적"에는 적용되지 않으므로
    # 무조건 관세 + 부가세 + 수입신고 계산.
    cif_usd = (inputs.cny_price * moq + (china_domestic + intl) / inputs.exchange_rate) * _CNY_TO_USD_APPROX
    mokrok = False  # always treat as commercial import (판매 목적 전제)

    duty = cif * inputs.customs_duty_pct
    vat = (cif + duty) * inputs.vat_pct
    filing = Decimal(
        inputs.filing_fee_krw
        if inputs.filing_fee_krw is not None
        else DEFAULT_FILING_FEE_KRW
    )
    duty_pct_applied = inputs.customs_duty_pct
    vat_pct_applied = inputs.vat_pct

    total = cif + duty + vat + filing
    unit_cost = total / moq

    return CostBreakdown(
        moq=inputs.moq,
        goods_cost_krw=_q_money(goods),
        china_domestic_shipping_krw=int(china_domestic),
        intl_shipping_krw=int(intl),
        cif_krw=_q_money(cif),
        cif_usd_approx=float(cif_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        customs_duty_krw=_q_money(duty),
        vat_krw=_q_money(vat),
        filing_fee_krw=int(filing),
        mokrok_duty_free=mokrok,
        total_cost_krw=_q_money(total),
        unit_cost_krw=_q_money(unit_cost),
        effective_duty_pct=_q_pct(duty_pct_applied),
        effective_vat_pct=_q_pct(vat_pct_applied),
    )


def _calculate(
    inputs: RevenueInputs,
    *,
    channel: Channel,
    platform_fee_pct: Decimal,
) -> ChannelRevenueResult:
    """Shared math kernel for both channels."""
    breakdown = compute_cost_breakdown(inputs)
    moq = Decimal(inputs.moq)
    total_cost = Decimal(breakdown.total_cost_krw)
    unit_cost = Decimal(breakdown.unit_cost_krw)

    expected_price = Decimal(inputs.expected_sell_price_krw)
    platform_fee = expected_price * platform_fee_pct
    ad_cost = expected_price * inputs.ad_cost_pct

    unit_profit = expected_price - unit_cost - platform_fee - ad_cost

    if unit_profit > 0:
        margin = unit_profit / expected_price
        # ROI per spec § 5.2 = (unit_profit × MOQ) / total_cost. We use
        # the *cost basis*, not the revenue basis, so the metric stays
        # comparable across MOQ tiers.
        roi = (unit_profit * moq) / total_cost
        breakeven = math.ceil(float(total_cost / unit_profit))
    else:
        # Loss-making: surface negative numbers so downstream filters /
        # PASS verdicts have something to bite on, but cap breakeven.
        if expected_price > 0:
            margin = unit_profit / expected_price
        else:
            margin = Decimal(0)
        roi = (unit_profit * moq) / total_cost if total_cost > 0 else Decimal(0)
        breakeven = BREAKEVEN_INFINITE_SENTINEL

    return ChannelRevenueResult(
        channel=channel,
        unit_cost_krw=_q_money(unit_cost),
        expected_price_krw=int(expected_price),
        platform_fee_pct=_q_pct(platform_fee_pct),
        ad_cost_pct=_q_pct(inputs.ad_cost_pct),
        unit_profit_krw=_q_money(unit_profit),
        margin_pct=_q_pct(margin),
        roi_pct=_q_pct(roi),
        breakeven_units=int(breakeven),
    )


# ---- entry points ----------------------------------------------------------


def calculate_smartstore_revenue(inputs: RevenueInputs) -> ChannelRevenueResult:
    """Compute economics for the 스마트스토어 channel.

    Platform fee is fixed at :data:`SMARTSTORE_FEE_PCT`; ``inputs.ad_cost_pct``
    is supplied by the caller (spec default: ``DEFAULT_SMARTSTORE_AD_PCT``).
    """
    return _calculate(
        inputs,
        channel=Channel.SMARTSTORE,
        platform_fee_pct=SMARTSTORE_FEE_PCT,
    )


def calculate_coupang_revenue(
    inputs: RevenueInputs, coupang_fee_pct: Decimal
) -> ChannelRevenueResult:
    """Compute economics for the 쿠팡 channel.

    The fee rate is per-category (see ``coupang_fees`` table; spec §9
    defaults range 4~10.8%). The caller is responsible for the lookup.
    """
    if coupang_fee_pct < Decimal(0):
        raise ValueError("coupang_fee_pct must be non-negative")
    return _calculate(
        inputs,
        channel=Channel.COUPANG,
        platform_fee_pct=coupang_fee_pct,
    )
