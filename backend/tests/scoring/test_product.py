"""Composite product score + GO/CONDITIONAL/PASS verdict tests.

We synthesize :class:`OpportunityScoreResult` and
:class:`ChannelRevenueResult` directly here -- the upstream scorers
have their own dedicated tests, and synthesizing lets us pin the
composite math precisely on each verdict boundary.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.scoring.opportunity import OpportunityScoreResult
from app.scoring.product import (
    CONDITIONAL_THRESHOLD,
    GO_THRESHOLD,
    ProductScoreInputs,
    calculate_product_score,
)
from app.scoring.revenue import (
    DEFAULT_COUPANG_AD_PCT,
    DEFAULT_SMARTSTORE_AD_PCT,
    ChannelRevenueResult,
    RevenueInputs,
    calculate_coupang_revenue,
    calculate_smartstore_revenue,
)
from app.scoring.types import Channel, Recommendation


# ---- helpers ---------------------------------------------------------------


def _make_opp(total: float) -> OpportunityScoreResult:
    """Build a synthetic opportunity result with a given total."""
    return OpportunityScoreResult(
        total_score=total,
        demand_score=min(25.0, total * 0.25),
        growth_score=min(20.0, total * 0.20),
        competition_score=min(20.0, total * 0.20),
        customs_score=min(20.0, total * 0.20),
        trend_score=min(10.0, total * 0.10),
        stability_score=min(5.0, total * 0.05),
        is_excluded=False,
        exclusion_reasons=[],
        details={},
    )


def _make_channel(
    channel: Channel,
    *,
    unit_profit: int,
    margin: float,
    roi: float,
    breakeven: int,
    expected_price: int = 38_000,
) -> ChannelRevenueResult:
    return ChannelRevenueResult(
        channel=channel,
        unit_cost_krw=expected_price - unit_profit - 5_000,
        expected_price_krw=expected_price,
        platform_fee_pct=0.055 if channel == Channel.SMARTSTORE else 0.108,
        ad_cost_pct=0.10 if channel == Channel.SMARTSTORE else 0.15,
        unit_profit_krw=unit_profit,
        margin_pct=margin,
        roi_pct=roi,
        breakeven_units=breakeven,
    )


# ---- baseline integration --------------------------------------------------


def test_baseline_uses_real_inputs(
    baseline_product_inputs: ProductScoreInputs,
):
    r = calculate_product_score(baseline_product_inputs)
    assert 0.0 <= r.total_score <= 100.0
    assert r.recommendation in {
        Recommendation.GO,
        Recommendation.CONDITIONAL,
        Recommendation.PASS,
    }


# ---- verdict thresholds ----------------------------------------------------


def _go_inputs(opp_total: float) -> ProductScoreInputs:
    """Build inputs that score profit/risk/stability near max so the
    verdict is dominated by the opportunity total."""
    ss = _make_channel(
        Channel.SMARTSTORE,
        unit_profit=24_000,
        margin=0.60,
        roi=1.50,
        breakeven=20,
    )
    cp = _make_channel(
        Channel.COUPANG,
        unit_profit=20_000,
        margin=0.50,
        roi=1.20,
        breakeven=25,
        expected_price=42_000,
    )
    return ProductScoreInputs(
        opportunity=_make_opp(opp_total),
        smartstore=ss,
        coupang=cp,
        budget_krw=10_000_000,
        total_initial_cost_krw=500_000,  # 5% of budget
        expected_monthly_demand_units=100,
        user_stability_rating=10.0,
    )


def test_verdict_go_above_threshold():
    r = calculate_product_score(_go_inputs(opp_total=95.0))
    assert r.total_score >= GO_THRESHOLD
    assert r.recommendation == Recommendation.GO


def test_verdict_conditional_in_band():
    """Tune opportunity so total lands in [60, 80)."""
    r = calculate_product_score(_go_inputs(opp_total=40.0))
    assert CONDITIONAL_THRESHOLD <= r.total_score < GO_THRESHOLD
    assert r.recommendation == Recommendation.CONDITIONAL


def test_verdict_pass_below_60():
    """Tank every axis to land below 60."""
    ss = _make_channel(
        Channel.SMARTSTORE,
        unit_profit=-1_000,
        margin=-0.05,
        roi=-0.10,
        breakeven=10**9,
    )
    cp = _make_channel(
        Channel.COUPANG,
        unit_profit=-2_000,
        margin=-0.10,
        roi=-0.20,
        breakeven=10**9,
        expected_price=42_000,
    )
    inp = ProductScoreInputs(
        opportunity=_make_opp(10.0),
        smartstore=ss,
        coupang=cp,
        budget_krw=1_000_000,
        total_initial_cost_krw=2_000_000,  # 200% of budget
        expected_monthly_demand_units=10,
        user_stability_rating=2.0,
    )
    r = calculate_product_score(inp)
    assert r.total_score < CONDITIONAL_THRESHOLD
    assert r.recommendation == Recommendation.PASS


# ---- profit subscore -------------------------------------------------------


def test_profit_axis_caps_at_35():
    """Both channels at >100% ROI and >50% margin should saturate the axis."""
    ss = _make_channel(
        Channel.SMARTSTORE,
        unit_profit=30_000,
        margin=0.80,
        roi=2.50,
        breakeven=10,
    )
    cp = _make_channel(
        Channel.COUPANG,
        unit_profit=28_000,
        margin=0.70,
        roi=2.00,
        breakeven=12,
        expected_price=42_000,
    )
    inp = ProductScoreInputs(
        opportunity=_make_opp(50.0),
        smartstore=ss,
        coupang=cp,
        budget_krw=10_000_000,
        total_initial_cost_krw=500_000,
        expected_monthly_demand_units=100,
        user_stability_rating=8.0,
    )
    r = calculate_product_score(inp)
    assert r.profit_score == pytest.approx(35.0, abs=0.01)


def test_profit_axis_zero_when_loss():
    ss = _make_channel(
        Channel.SMARTSTORE,
        unit_profit=-5_000,
        margin=-0.10,
        roi=-0.30,
        breakeven=10**9,
    )
    cp = _make_channel(
        Channel.COUPANG,
        unit_profit=-3_000,
        margin=-0.05,
        roi=-0.15,
        breakeven=10**9,
        expected_price=42_000,
    )
    inp = ProductScoreInputs(
        opportunity=_make_opp(50.0),
        smartstore=ss,
        coupang=cp,
        budget_krw=10_000_000,
        total_initial_cost_krw=500_000,
        expected_monthly_demand_units=100,
        user_stability_rating=8.0,
    )
    r = calculate_product_score(inp)
    assert r.profit_score == pytest.approx(0.0, abs=0.01)


# ---- risk subscore ---------------------------------------------------------


def test_risk_full_when_cheap_and_quick_breakeven():
    ss = _make_channel(
        Channel.SMARTSTORE,
        unit_profit=20_000,
        margin=0.50,
        roi=1.20,
        breakeven=10,
    )
    cp = _make_channel(
        Channel.COUPANG,
        unit_profit=15_000,
        margin=0.40,
        roi=1.00,
        breakeven=15,
        expected_price=42_000,
    )
    inp = ProductScoreInputs(
        opportunity=_make_opp(50.0),
        smartstore=ss,
        coupang=cp,
        budget_krw=10_000_000,
        total_initial_cost_krw=500_000,  # 5% of budget
        expected_monthly_demand_units=100,  # 15 / 100 = 0.15 (≤0.5)
        user_stability_rating=8.0,
    )
    r = calculate_product_score(inp)
    assert r.risk_score == pytest.approx(15.0, abs=0.01)


def test_risk_zero_when_overbudget_and_slow_breakeven():
    ss = _make_channel(
        Channel.SMARTSTORE,
        unit_profit=20_000,
        margin=0.50,
        roi=1.20,
        breakeven=500,
    )
    cp = _make_channel(
        Channel.COUPANG,
        unit_profit=15_000,
        margin=0.40,
        roi=1.00,
        breakeven=600,
        expected_price=42_000,
    )
    inp = ProductScoreInputs(
        opportunity=_make_opp(50.0),
        smartstore=ss,
        coupang=cp,
        budget_krw=1_000_000,
        total_initial_cost_krw=2_000_000,  # 200% of budget
        expected_monthly_demand_units=100,  # 600 / 100 = 6.0 (≥2.0)
        user_stability_rating=8.0,
    )
    r = calculate_product_score(inp)
    assert r.risk_score == pytest.approx(0.0, abs=0.01)


# ---- stability subscore ----------------------------------------------------


@pytest.mark.parametrize(
    "rating,expected",
    [(0.0, 0.0), (5.0, 5.0), (10.0, 10.0)],
)
def test_stability_linear(rating: float, expected: float):
    ss = _make_channel(
        Channel.SMARTSTORE, unit_profit=20_000, margin=0.5, roi=1.2, breakeven=20
    )
    cp = _make_channel(
        Channel.COUPANG,
        unit_profit=15_000,
        margin=0.4,
        roi=1.0,
        breakeven=25,
        expected_price=42_000,
    )
    inp = ProductScoreInputs(
        opportunity=_make_opp(50.0),
        smartstore=ss,
        coupang=cp,
        budget_krw=10_000_000,
        total_initial_cost_krw=500_000,
        expected_monthly_demand_units=100,
        user_stability_rating=rating,
    )
    r = calculate_product_score(inp)
    assert r.stability_score == pytest.approx(expected, abs=0.01)


# ---- end-to-end with real revenue calc ------------------------------------


def test_end_to_end_pipeline_matches_spec_example(
    baseline_revenue_inputs: RevenueInputs,
):
    """Smartstore + Coupang calculated from spec inputs flow into the
    product scorer cleanly. Lock the verdict so future weight tuning
    surfaces here."""
    ss = calculate_smartstore_revenue(baseline_revenue_inputs)
    cp_inputs = baseline_revenue_inputs.model_copy(
        update={
            "expected_sell_price_krw": 42_000,
            "ad_cost_pct": DEFAULT_COUPANG_AD_PCT,
        }
    )
    cp = calculate_coupang_revenue(cp_inputs, Decimal("0.108"))
    opp = _make_opp(80.0)  # strong opportunity
    inp = ProductScoreInputs(
        opportunity=opp,
        smartstore=ss,
        coupang=cp,
        budget_krw=2_000_000,
        total_initial_cost_krw=ss.unit_cost_krw * baseline_revenue_inputs.moq,
        expected_monthly_demand_units=50,
        user_stability_rating=8.0,
    )
    r = calculate_product_score(inp)
    # Budget pressure: 476,850 / 2,000,000 ≈ 0.24 → near-full risk budget.
    # Strong opportunity (80) + high profit on SS → expect GO.
    assert r.recommendation == Recommendation.GO
    assert r.total_score >= GO_THRESHOLD
