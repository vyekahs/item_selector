"""Composite product score (기획서 §5.3) and GO / CONDITIONAL / PASS verdict.

The composite is intentionally small: it consumes the *outputs* of
the upstream scoring functions rather than recomputing anything. That
keeps the layering clean -- each scorer is independently testable, and
this module just weights and combines.

Score weights
-------------
=========================  =====  ============================================
Axis                       Max    Source
=========================  =====  ============================================
Opportunity                40     ``OpportunityScoreResult.total_score × 0.4``
Profit                     35     양 채널 평균 ROI / margin
Risk                       15     MOQ vs budget + breakeven vs expected demand
Stability (manual)         10     사용자 입력 (1~10), 기본 7
=========================  =====  ============================================

Verdict thresholds (§5.3): ≥80 GO, 60–79 CONDITIONAL, <60 PASS.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .opportunity import OpportunityScoreResult
from .revenue import ChannelRevenueResult
from .types import Recommendation

__all__ = [
    "ProductScoreInputs",
    "ProductScoreResult",
    "calculate_product_score",
    "GO_THRESHOLD",
    "CONDITIONAL_THRESHOLD",
]

# ---- thresholds ------------------------------------------------------------

GO_THRESHOLD: float = 80.0
CONDITIONAL_THRESHOLD: float = 60.0

# ROI saturation: 100% ROI (= doubled cost recovery) maps to full marks.
ROI_SATURATION: float = 1.0

# Margin saturation: 50% margin maps to full marks (typical sourcing target).
MARGIN_SATURATION: float = 0.5

# Default user-supplied stability rating when not provided.
DEFAULT_STABILITY_RATING: float = 7.0  # out of 10

# Default expected monthly demand used to evaluate breakeven feasibility
# when the caller doesn't have a better forecast. 50 units/month is the
# loose Phase-3 default the spec assumes (see screen mock §6.2).
DEFAULT_EXPECTED_MONTHLY_DEMAND: int = 50


# ---- inputs / outputs ------------------------------------------------------


class ProductScoreInputs(BaseModel):
    """Bundle for one product across both channels."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    opportunity: OpportunityScoreResult
    smartstore: ChannelRevenueResult
    coupang: ChannelRevenueResult

    # Risk axis context
    budget_krw: int = Field(
        ..., gt=0, description="사용자 사입 예산 (총원가 비교용)"
    )
    total_initial_cost_krw: int = Field(
        ..., gt=0, description="MOQ × unit_cost (양 채널 동일)"
    )
    expected_monthly_demand_units: int = Field(
        DEFAULT_EXPECTED_MONTHLY_DEMAND, gt=0
    )

    # Stability axis (user-supplied 1~10).
    user_stability_rating: float = Field(
        DEFAULT_STABILITY_RATING, ge=0.0, le=10.0
    )


class ProductScoreResult(BaseModel):
    total_score: float = Field(..., ge=0.0, le=100.0)
    opportunity_score: float = Field(..., ge=0.0, le=40.0)
    profit_score: float = Field(..., ge=0.0, le=35.0)
    risk_score: float = Field(..., ge=0.0, le=15.0)
    stability_score: float = Field(..., ge=0.0, le=10.0)
    recommendation: Recommendation
    details: dict = Field(default_factory=dict)


# ---- helpers ---------------------------------------------------------------


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _verdict(total: float) -> Recommendation:
    if total >= GO_THRESHOLD:
        return Recommendation.GO
    if total >= CONDITIONAL_THRESHOLD:
        return Recommendation.CONDITIONAL
    return Recommendation.PASS


def _profit_subscore(
    smartstore: ChannelRevenueResult, coupang: ChannelRevenueResult
) -> tuple[float, dict]:
    """35-point profit axis: 70% weight on ROI, 30% on margin.

    ROI is the dominant signal because the spec frames the tool as a
    capital-efficiency optimizer (limited 50–500만원 budget per cycle).
    Margin still matters as a tiebreaker between two ROI-equal items.
    """
    rois = [smartstore.roi_pct, coupang.roi_pct]
    margins = [smartstore.margin_pct, coupang.margin_pct]

    avg_roi = sum(rois) / len(rois)
    avg_margin = sum(margins) / len(margins)

    roi_norm = _clamp01(avg_roi / ROI_SATURATION)
    margin_norm = _clamp01(avg_margin / MARGIN_SATURATION)

    score = (roi_norm * 0.7 + margin_norm * 0.3) * 35.0
    return max(0.0, score), {
        "avg_roi": avg_roi,
        "avg_margin": avg_margin,
        "roi_norm": roi_norm,
        "margin_norm": margin_norm,
    }


def _risk_subscore(
    inputs: ProductScoreInputs,
) -> tuple[float, dict]:
    """15-point risk axis (lower risk → higher score).

    Two factors, equally weighted:

    * **MOQ-vs-budget** (7.5pt): how much of the user's discretionary
      budget the initial order eats. <30% → full marks, >100% → 0.
    * **Breakeven feasibility** (7.5pt): worst (max) breakeven units
      across both channels relative to expected monthly demand.
      ≤50% of demand → full marks, ≥200% → 0.
    """
    # Budget pressure
    budget_ratio = inputs.total_initial_cost_krw / inputs.budget_krw
    if budget_ratio <= 0.3:
        budget_norm = 1.0
    elif budget_ratio >= 1.0:
        budget_norm = 0.0
    else:
        budget_norm = 1.0 - (budget_ratio - 0.3) / 0.7
    budget_pts = budget_norm * 7.5

    # Breakeven feasibility (use the worse channel as the binding risk).
    worst_breakeven = max(
        inputs.smartstore.breakeven_units, inputs.coupang.breakeven_units
    )
    demand = inputs.expected_monthly_demand_units
    breakeven_ratio = worst_breakeven / demand
    if breakeven_ratio <= 0.5:
        breakeven_norm = 1.0
    elif breakeven_ratio >= 2.0:
        breakeven_norm = 0.0
    else:
        breakeven_norm = 1.0 - (breakeven_ratio - 0.5) / 1.5
    breakeven_pts = breakeven_norm * 7.5

    return budget_pts + breakeven_pts, {
        "budget_ratio": budget_ratio,
        "budget_norm": budget_norm,
        "worst_breakeven_units": worst_breakeven,
        "breakeven_ratio": breakeven_ratio,
        "breakeven_norm": breakeven_norm,
    }


def _stability_subscore(rating: float) -> tuple[float, dict]:
    """User-supplied 1–10 rating, scaled linearly to 0–10 score points."""
    norm = _clamp01(rating / 10.0)
    return norm * 10.0, {"user_rating": rating, "norm": norm}


# ---- entry point -----------------------------------------------------------


def calculate_product_score(inputs: ProductScoreInputs) -> ProductScoreResult:
    """Combine opportunity + per-channel revenue into the 100-pt verdict."""
    opp_score = inputs.opportunity.total_score * 0.4
    profit_score, profit_detail = _profit_subscore(
        inputs.smartstore, inputs.coupang
    )
    risk_score, risk_detail = _risk_subscore(inputs)
    stability_score, stability_detail = _stability_subscore(
        inputs.user_stability_rating
    )

    total = opp_score + profit_score + risk_score + stability_score
    total = max(0.0, min(100.0, total))
    verdict = _verdict(total)

    return ProductScoreResult(
        total_score=round(total, 2),
        opportunity_score=round(opp_score, 2),
        profit_score=round(profit_score, 2),
        risk_score=round(risk_score, 2),
        stability_score=round(stability_score, 2),
        recommendation=verdict,
        details={
            "opportunity": {
                "source_total": inputs.opportunity.total_score,
                "weight": 0.4,
            },
            "profit": profit_detail,
            "risk": risk_detail,
            "stability": stability_detail,
        },
    )
