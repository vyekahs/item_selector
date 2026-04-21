"""Per-channel revenue regression tests.

The first cluster pins down the spec example from §6.2 so any future
math change has to consciously update the expected numbers. The
remaining tests cover boundaries (MOQ=1, loss-making, zero ad spend)
and the cross-channel difference (smartstore should out-earn coupang
when fees + ad spend are higher).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.scoring.revenue import (
    BREAKEVEN_INFINITE_SENTINEL,
    DEFAULT_COUPANG_AD_PCT,
    DEFAULT_SMARTSTORE_AD_PCT,
    SMARTSTORE_FEE_PCT,
    RevenueInputs,
    calculate_coupang_revenue,
    calculate_smartstore_revenue,
)
from app.scoring.types import Channel


# ---- spec § 6.2 sample numbers (after CIF→관세→부가세→수입신고 split) ------
#
# Inputs: ¥45 × 50 × 195 → goods 438,750 / intl 3,000 / china 0
#   CIF            = 441,750 (goods + china + intl)
#   CIF USD approx = 45×50×0.14 + 3000/195×0.14 ≈ 317.15 > 150 → duty/VAT 적용
#   관세 (CIF×8%)  = 35,340
#   부가세         = (CIF + 관세)×10% = 47,709
#   수입신고 수수료 = 30,000
#   total          = 441,750 + 35,340 + 47,709 + 30,000 = 554,799
#   unit cost      = 554,799 / 50 = 11,096


@pytest.fixture
def spec_inputs() -> RevenueInputs:
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


def test_smartstore_spec_regression(spec_inputs: RevenueInputs):
    r = calculate_smartstore_revenue(spec_inputs)
    assert r.channel == Channel.SMARTSTORE
    assert r.unit_cost_krw == 11_096
    assert r.expected_price_krw == 38_000
    assert r.platform_fee_pct == pytest.approx(0.055)
    assert r.ad_cost_pct == pytest.approx(0.10)
    # profit = 38,000 − 11,096 − 2,090 − 3,800 = 21,014
    assert r.unit_profit_krw == 21_014
    assert r.margin_pct == pytest.approx(21_014 / 38_000, abs=0.0005)
    # roi = 21,014×50 / 554,799 ≈ 1.894
    assert r.roi_pct == pytest.approx(1.894, abs=0.005)
    # breakeven = ceil(554,799 / 21,014) = 27
    assert r.breakeven_units == 27


def test_coupang_spec_regression(spec_inputs: RevenueInputs):
    coupang_inputs = spec_inputs.model_copy(
        update={
            "expected_sell_price_krw": 42_000,
            "ad_cost_pct": DEFAULT_COUPANG_AD_PCT,
        }
    )
    r = calculate_coupang_revenue(coupang_inputs, Decimal("0.108"))
    # fee = 42,000×0.108 = 4,536 / ad = 42,000×0.15 = 6,300
    # profit = 42,000 − 11,096 − 4,536 − 6,300 = 20,068
    assert r.channel == Channel.COUPANG
    assert r.unit_cost_krw == 11_096
    assert r.expected_price_krw == 42_000
    assert r.platform_fee_pct == pytest.approx(0.108)
    assert r.ad_cost_pct == pytest.approx(0.15)
    assert r.unit_profit_krw == 20_068
    assert r.margin_pct == pytest.approx(20_068 / 42_000, abs=0.0005)
    # breakeven = ceil(554,799 / 20,068) = 28
    assert r.breakeven_units == 28


# ---- boundary cases --------------------------------------------------------


def test_moq_one_commercial_import(spec_inputs: RevenueInputs):
    """Single-unit purchase: 판매 목적이라 CIF가 작아도 정식 수입 통관 적용.

    goods 8,775 + intl 3,000 = CIF 11,775
    관세 8% → 942, 부가세 10% → 1,272, 수입신고 30,000
    total = 11,775 + 942 + 1,272 + 30,000 = 43,989
    """
    one = spec_inputs.model_copy(update={"moq": 1})
    r = calculate_smartstore_revenue(one)
    assert r.unit_cost_krw == 43_989
    # SS profit = 38,000 − 43,989 − 2,090 − 3,800 < 0 (loss)
    assert r.unit_profit_krw < 0


def test_loss_making_breakeven_sentinel(spec_inputs: RevenueInputs):
    """Negative unit profit → breakeven sentinel and negative ROI."""
    bad = spec_inputs.model_copy(update={"expected_sell_price_krw": 5_000})
    r = calculate_smartstore_revenue(bad)
    assert r.unit_profit_krw < 0
    assert r.breakeven_units == BREAKEVEN_INFINITE_SENTINEL
    assert r.roi_pct < 0
    assert r.margin_pct < 0


def test_zero_ad_cost(spec_inputs: RevenueInputs):
    """ad_cost_pct=0 should be allowed (some sellers run organic-only)."""
    organic = spec_inputs.model_copy(update={"ad_cost_pct": Decimal(0)})
    r = calculate_smartstore_revenue(organic)
    assert r.ad_cost_pct == pytest.approx(0.0)
    # New regression profit 21,014 + ad spend saved 3,800 = 24,814.
    assert r.unit_profit_krw == 21_014 + 3_800


def test_smartstore_fee_constant_is_55_pct():
    assert SMARTSTORE_FEE_PCT == Decimal("0.055")


def test_coupang_fee_negative_rejected(spec_inputs: RevenueInputs):
    with pytest.raises(ValueError):
        calculate_coupang_revenue(spec_inputs, Decimal("-0.01"))


# ---- cross-channel sanity --------------------------------------------------


def test_smartstore_outperforms_coupang_when_fees_higher(
    spec_inputs: RevenueInputs,
):
    """At equal sell price, smartstore (5.5% / 10% ad) beats coupang (10.8% / 15% ad)."""
    coupang_inputs = spec_inputs.model_copy(
        update={"ad_cost_pct": DEFAULT_COUPANG_AD_PCT}
    )
    ss = calculate_smartstore_revenue(spec_inputs)
    cp = calculate_coupang_revenue(coupang_inputs, Decimal("0.108"))
    assert ss.unit_profit_krw > cp.unit_profit_krw
    assert ss.margin_pct > cp.margin_pct
    assert ss.roi_pct > cp.roi_pct


def test_higher_moq_lowers_unit_cost(spec_inputs: RevenueInputs):
    """판매 목적은 항상 정식 수입이므로 어떤 MOQ에서도 fixed filing fee(30K)
    + 관세 + 부가세가 부과된다. MOQ가 커질수록 filing fee 30,000원이
    분산돼 개당 원가가 내려간다.
    """
    small = calculate_smartstore_revenue(spec_inputs.model_copy(update={"moq": 10}))
    large = calculate_smartstore_revenue(spec_inputs.model_copy(update={"moq": 500}))
    assert large.unit_cost_krw < small.unit_cost_krw
