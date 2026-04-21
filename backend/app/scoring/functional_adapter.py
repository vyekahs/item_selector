"""Adapter bridging the stateless scoring functions and the
``ProductScorer`` Protocol owned by the Backend API Agent.

The Backend service calls ``scorer.score(ScoringInput) -> ProductScoringResult``.
This module wraps the functional scoring primitives
(``calculate_smartstore_revenue`` / ``calculate_coupang_revenue`` /
``calculate_product_score``) into an instance that satisfies that
Protocol.

Phase 1 limitation
------------------
The upstream opportunity score (25/20/20/20/10/5 axes from the
keyword pipeline) lives in the ``opportunity_scores`` table and
depends on data the scheduler collects from Naver + 관세청 + YouTube.
The Backend's ``ScoringInput`` intentionally does *not* include that
context because Phase 1 is a cold-start: users can submit a 1688
product before the keyword pipeline has ever run against that term.

For now, when no opportunity data is available we fall back to a
**neutral** opportunity score (total=50/100). A Phase-2 refinement
is to pass a session-bound context provider into
``build_functional_scorer`` and look up the latest snapshot in
``opportunity_scores`` keyed by ``ScoringInput.keyword_id``.

Expected-sell-price heuristic
-----------------------------
Without Naver 쇼핑 검색 결과 in hand, we estimate the Korean retail
price as ``max(10_000 KRW, unit_cost × 3)``. This is the crude
Phase-1 placeholder; the scheduler-backed path will substitute the
``keyword_metrics.smartstore_avg_price_krw`` once that column is
populated.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.scoring.opportunity import OpportunityScoreResult
from app.scoring.product import (
    DEFAULT_STABILITY_RATING,
    ProductScoreInputs,
    calculate_product_score,
)
from app.scoring.revenue import (
    RevenueInputs,
    calculate_coupang_revenue,
    calculate_smartstore_revenue,
    compute_cost_breakdown,
)
from app.scoring.types import Channel

__all__ = ["build_functional_scorer", "FunctionalScorer"]


# Phase-1 fallbacks when upstream context is missing.
NEUTRAL_OPPORTUNITY_TOTAL: float = 50.0  # middle-of-the-road starting point
DEFAULT_BUDGET_KRW: int = 2_000_000      # spec §2 typical user budget (200만)
PRICE_MULTIPLIER_OVER_UNIT_COST: Decimal = Decimal("3.0")
PRICE_FLOOR_KRW: int = 10_000
DEFAULT_CATEGORY_NAME: str = "default"


def _neutral_opportunity() -> OpportunityScoreResult:
    """Phase-1 fallback when no ``opportunity_scores`` row exists."""
    return OpportunityScoreResult(
        total_score=NEUTRAL_OPPORTUNITY_TOTAL,
        demand_score=12.5,      # half of 25
        growth_score=10.0,      # half of 20
        competition_score=10.0, # half of 20
        customs_score=10.0,     # half of 20
        trend_score=5.0,        # half of 10
        stability_score=2.5,    # half of 5
        is_excluded=False,
        exclusion_reasons=[],
        details={"source": "neutral_fallback"},
    )


def _estimate_price_krw(unit_cost_krw: Decimal) -> int:
    """Placeholder expected sell price (Phase-1)."""
    raw = unit_cost_krw * PRICE_MULTIPLIER_OVER_UNIT_COST
    return max(PRICE_FLOOR_KRW, int(raw.to_integral_value()))


def _unit_cost_krw(
    cny_price: Decimal, cny_to_krw: Decimal, customs_duty_pct: Decimal
) -> Decimal:
    """Per-unit landed cost (excluding per-unit amortisation of fixed intl
    shipping — that lands inside the revenue calc).
    """
    gross = cny_price * cny_to_krw
    duty = gross * customs_duty_pct
    return gross + duty


@dataclass(frozen=True)
class FunctionalScorer:
    """Binds the stateless scoring functions to the service-layer
    ``ProductScorer`` Protocol.

    Attributes are all Phase-1 defaults; swap in constructor args to
    customize (e.g. per-user budget).
    """

    budget_krw: int = DEFAULT_BUDGET_KRW
    stability_rating: float = DEFAULT_STABILITY_RATING
    customs_duty_pct: Decimal = Decimal("0.08")
    intl_shipping_krw: int = 3_000

    def score(self, inputs):  # type: ignore[no-untyped-def]
        # Local import to avoid a circular dep (product_service imports
        # this module lazily via ``_load_scorer``).
        from app.services.product_service import (
            ChannelProfitDraft,
            CostBreakdownDraft,
            ProductScoringResult,
        )

        unit_cost_per_item = _unit_cost_krw(
            inputs.cny_price, inputs.cny_to_krw, self.customs_duty_pct
        )
        supplied = getattr(inputs, "expected_sell_price_krw", None)
        if supplied and supplied > 0:
            expected_price_krw = int(supplied)
        else:
            # Phase-1 fallback when no Naver 쇼핑 data is linked.
            expected_price_krw = _estimate_price_krw(unit_cost_per_item)

        # User-override shipping + duty from ScoringInput (None = defaults).
        china_shipping = getattr(inputs, "china_domestic_shipping_krw", None) or 0
        intl_shipping_override = getattr(inputs, "intl_shipping_krw", None)
        duty_pct_override = getattr(inputs, "customs_duty_pct", None)
        duty_pct = (
            duty_pct_override
            if duty_pct_override is not None
            else self.customs_duty_pct
        )

        ss_rev = calculate_smartstore_revenue(
            RevenueInputs(
                cny_price=inputs.cny_price,
                moq=inputs.moq,
                expected_sell_price_krw=expected_price_krw,
                category_name=DEFAULT_CATEGORY_NAME,
                exchange_rate=inputs.cny_to_krw,
                china_domestic_shipping_krw=china_shipping,
                intl_shipping_krw=intl_shipping_override,
                customs_duty_pct=duty_pct,
                ad_cost_pct=inputs.smartstore_ad_pct,
            )
        )
        cp_rev = calculate_coupang_revenue(
            RevenueInputs(
                cny_price=inputs.cny_price,
                moq=inputs.moq,
                expected_sell_price_krw=expected_price_krw,
                category_name=DEFAULT_CATEGORY_NAME,
                exchange_rate=inputs.cny_to_krw,
                china_domestic_shipping_krw=china_shipping,
                intl_shipping_krw=intl_shipping_override,
                customs_duty_pct=duty_pct,
                ad_cost_pct=inputs.coupang_ad_pct,
            ),
            coupang_fee_pct=inputs.coupang_fee_pct,
        )

        total_initial_cost = int(ss_rev.unit_cost_krw) * inputs.moq

        # Recompute the breakdown once so the UI has the full decomposition.
        breakdown = compute_cost_breakdown(
            RevenueInputs(
                cny_price=inputs.cny_price,
                moq=inputs.moq,
                expected_sell_price_krw=expected_price_krw,
                category_name=DEFAULT_CATEGORY_NAME,
                exchange_rate=inputs.cny_to_krw,
                china_domestic_shipping_krw=china_shipping,
                intl_shipping_krw=intl_shipping_override,
                customs_duty_pct=duty_pct,
                ad_cost_pct=inputs.smartstore_ad_pct,
            )
        )

        composite = calculate_product_score(
            ProductScoreInputs(
                opportunity=_neutral_opportunity(),
                smartstore=ss_rev,
                coupang=cp_rev,
                budget_krw=self.budget_krw,
                total_initial_cost_krw=max(1, total_initial_cost),
                user_stability_rating=self.stability_rating,
            )
        )

        def _draft(rev) -> ChannelProfitDraft:  # type: ignore[no-untyped-def]
            return ChannelProfitDraft(
                channel=Channel(rev.channel) if not isinstance(rev.channel, Channel) else rev.channel,
                unit_cost_krw=Decimal(rev.unit_cost_krw),
                expected_price_krw=Decimal(rev.expected_price_krw),
                platform_fee_pct=Decimal(str(rev.platform_fee_pct)),
                ad_cost_pct=Decimal(str(rev.ad_cost_pct)),
                unit_profit_krw=Decimal(rev.unit_profit_krw),
                margin_pct=Decimal(str(rev.margin_pct)),
                roi_pct=Decimal(str(rev.roi_pct)),
                breakeven_units=int(rev.breakeven_units),
            )

        return ProductScoringResult(
            total_score=composite.total_score,
            opportunity_score=composite.opportunity_score,
            profit_score=composite.profit_score,
            risk_score=composite.risk_score,
            stability_score=composite.stability_score,
            recommendation=composite.recommendation,
            channel_profits=[_draft(ss_rev), _draft(cp_rev)],
            cost_breakdown=CostBreakdownDraft(
                moq=breakdown.moq,
                goods_cost_krw=breakdown.goods_cost_krw,
                china_domestic_shipping_krw=breakdown.china_domestic_shipping_krw,
                intl_shipping_krw=breakdown.intl_shipping_krw,
                cif_krw=breakdown.cif_krw,
                cif_usd_approx=breakdown.cif_usd_approx,
                customs_duty_krw=breakdown.customs_duty_krw,
                vat_krw=breakdown.vat_krw,
                filing_fee_krw=breakdown.filing_fee_krw,
                mokrok_duty_free=breakdown.mokrok_duty_free,
                total_cost_krw=breakdown.total_cost_krw,
                unit_cost_krw=breakdown.unit_cost_krw,
                effective_duty_pct=breakdown.effective_duty_pct,
                effective_vat_pct=breakdown.effective_vat_pct,
            ),
        )


def build_functional_scorer() -> FunctionalScorer:
    """Factory expected by ``backend.app.services.product_service._load_scorer``."""
    return FunctionalScorer()
