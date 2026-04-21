"""Opportunity score (기획서 §4.2) — 100 points across six axes.

The function is **pure**: every external signal is supplied via
:class:`OpportunityInputs` so the caller (Backend / Scheduler agent)
owns the IO. No DB, no HTTP, no time.

Score breakdown
---------------
=========================  =====  ============================================
Axis                       Max    Source signal
=========================  =====  ============================================
Demand size                25     ``volume.total_monthly_volume`` (log-norm)
Demand growth              20     ``trend.growth_rate_3m``
Competition vacancy        20     ``volume / shopping.total_count`` blue-ocean
Customs reality            20     ``customs.growth_rate_3m`` (neutral if None)
Trend leading              10     youtube + blog/cafe 30d growth, averaged
Stability                  5      seasonality penalty
=========================  =====  ============================================

Exclusion filters (§4.3) live in :mod:`app.scoring.filters`. When any
filter trips we still report the per-axis subscores (so the UI can
explain *why* the keyword scored as it did) but flag ``is_excluded``.
"""
from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from .filters import apply_all_filters
from .types import (
    BlogCafeDTO,
    CustomsTrendDTO,
    GoogleTrendDTO,
    KeywordVolumeDTO,
    NaverTrendDTO,
    ShoppingResultDTO,
    YouTubeSignalDTO,
)

__all__ = [
    "OpportunityInputs",
    "OpportunityScoreResult",
    "calculate_opportunity_score",
]


# ---- inputs / outputs ------------------------------------------------------


class OpportunityInputs(BaseModel):
    """Bundle of *already collected* signals for one keyword."""

    model_config = ConfigDict(arbitrary_types_allowed=False)

    keyword: str
    volume: KeywordVolumeDTO
    trend: NaverTrendDTO
    shopping: ShoppingResultDTO
    blog_cafe: BlogCafeDTO | None = None
    youtube: YouTubeSignalDTO | None = None
    google_trend: GoogleTrendDTO | None = None
    customs: CustomsTrendDTO | None = None
    category_name: str
    is_certification_required: bool = False
    seasonality_index: float = Field(
        1.0,
        ge=0.0,
        description="1.0 = flat, 2.5+ = severe; >2.5 triggers exclusion",
    )


class OpportunityScoreResult(BaseModel):
    """Per-axis breakdown + total + exclusion verdict."""

    total_score: float = Field(..., ge=0.0, le=100.0)
    demand_score: float = Field(..., ge=0.0, le=25.0)
    growth_score: float = Field(..., ge=0.0, le=20.0)
    competition_score: float = Field(..., ge=0.0, le=20.0)
    customs_score: float = Field(..., ge=0.0, le=20.0)
    trend_score: float = Field(..., ge=0.0, le=10.0)
    stability_score: float = Field(..., ge=0.0, le=5.0)
    is_excluded: bool
    exclusion_reasons: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


# ---- normalization helpers -------------------------------------------------

# Anchor for the demand-size log normalization. 100K monthly searches
# saturates the demand axis to 25 points; everything above is clamped.
DEMAND_LOG_ANCHOR: int = 100_000

# Demand floor for the competition axis: volume below this gets no
# bonus from a "low competition" signal (a dead keyword isn't an
# opportunity just because nobody else is there).
COMPETITION_VOLUME_FLOOR: int = 1_000
COMPETITION_VOLUME_ANCHOR: int = 10_000  # full demand weight at ≥10K/mo

# Caps for 30-day leading growth (blog/cafe, YouTube). Values arrive
# here in *decimal* form (the scheduler's ``_pct_to_decimal`` already
# divided by 100). Real-world data shows runaway values when the prior
# window has few posts; +200% (decimal 2.0) is a sensible saturation
# point -- anything higher is noise or a one-off trend pop.
LEADING_GROWTH_CAP: float = 2.0   # = +200%
LEADING_GROWTH_FLOOR: float = -0.5  # = -50%


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _log_norm(value: float, anchor: float) -> float:
    """log10(value+1) / log10(anchor+1), clamped to [0, 1]."""
    if value <= 0:
        return 0.0
    if anchor <= 0:
        return 0.0
    numerator = math.log10(value + 1.0)
    denominator = math.log10(anchor + 1.0)
    if denominator <= 0:
        return 0.0
    return _clamp01(numerator / denominator)


# ---- per-axis scoring ------------------------------------------------------


def _score_demand(volume: KeywordVolumeDTO) -> tuple[float, dict]:
    norm = _log_norm(volume.total_monthly_volume, DEMAND_LOG_ANCHOR)
    return norm * 25.0, {
        "total_monthly_volume": volume.total_monthly_volume,
        "norm": norm,
    }


def _score_growth(trend: NaverTrendDTO) -> tuple[float, dict]:
    # Spec: −10% → 0 pt, +50% → 20 pt. growth_rate_3m is decimal.
    g_pct = trend.growth_rate_3m * 100.0
    norm = _clamp01((g_pct + 10.0) / 60.0)
    return norm * 20.0, {"growth_rate_3m_pct": g_pct, "norm": norm}


def _score_competition(
    volume: KeywordVolumeDTO, shopping: ShoppingResultDTO
) -> tuple[float, dict]:
    """Reward uncrowded demand, penalise both extremes.

    Uses the 검색광고 ``competition_index`` (0=낮음, 0.5=중간, 0.8=높음) as the
    primary signal — it's far more reliable than ``shopping.total_count``
    (Naver 쇼핑 returns ≥100K listings for most terms because it matches
    loose keywords). ``total_count`` is kept as a tiebreaker.

    A low-volume keyword (<1K searches/mo) is not an opportunity
    regardless of how uncrowded it looks, so we gate the score by a
    demand factor that ramps from 0 at 1K searches to 1 at 10K+.
    """
    if volume.total_monthly_volume < COMPETITION_VOLUME_FLOOR:
        demand_factor = 0.0
    elif volume.total_monthly_volume >= COMPETITION_VOLUME_ANCHOR:
        demand_factor = 1.0
    else:
        span = COMPETITION_VOLUME_ANCHOR - COMPETITION_VOLUME_FLOOR
        demand_factor = (
            volume.total_monthly_volume - COMPETITION_VOLUME_FLOOR
        ) / span

    vacancy = _clamp01(1.0 - volume.competition_index)
    # Secondary modifier: if total_count is astronomically high
    # (> 500K listings) trim vacancy slightly. This catches cases where
    # 검색광고 says 낮음 but the Naver shopping shelf is actually flooded.
    if shopping.total_count > 500_000:
        vacancy *= 0.7
    elif shopping.total_count > 200_000:
        vacancy *= 0.85

    score = vacancy * demand_factor * 20.0
    return score, {
        "competition_index": volume.competition_index,
        "vacancy": vacancy,
        "demand_factor": demand_factor,
        "shopping_total_count": shopping.total_count,
    }


def _score_customs(customs: CustomsTrendDTO | None) -> tuple[float, dict]:
    """Import-trend scoring.

    Scale: -30% → 0 pt, 0% (flat) → 10 pt, +30% → 20 pt. The mid-point
    anchor means a mature, stable import category is not punished —
    only an actively-shrinking one is. Matches the spec intent of
    treating customs as a *corroborating* signal, not a pass/fail.
    """
    if customs is None:
        return 10.0, {"reason": "no_customs_data", "norm": 0.5}
    g_pct = customs.growth_rate_3m * 100.0
    # Symmetric ramp around 0%: -30% = 0, 0% = 10, +30% = 20.
    norm = _clamp01((g_pct + 30.0) / 60.0)
    return norm * 20.0, {"growth_rate_3m_pct": g_pct, "norm": norm}


def _score_trend(
    youtube: YouTubeSignalDTO | None, blog_cafe: BlogCafeDTO | None
) -> tuple[float, dict]:
    """Average of YouTube + blog 30-day growth, clamped against runaway
    values.

    Upstream APIs return percent form already (e.g. 200.0 = +200%).
    When the prior 30-day window is ~0 the ratio explodes (we've seen
    10000% in the wild); :data:`LEADING_GROWTH_CAP_PCT` caps each input
    before averaging so one noisy signal can't pin the axis to full
    marks. Scale: -50% → 0 pt, +100% → 10 pt (linear).
    """
    samples: list[float] = []
    detail: dict = {}
    if youtube is not None:
        raw = max(
            LEADING_GROWTH_FLOOR, min(LEADING_GROWTH_CAP, youtube.growth_rate_30d)
        )
        samples.append(raw)
        detail["youtube_growth_30d_raw"] = youtube.growth_rate_30d
        detail["youtube_growth_30d_clamped"] = raw
    if blog_cafe is not None:
        raw = max(
            LEADING_GROWTH_FLOOR,
            min(LEADING_GROWTH_CAP, blog_cafe.recent_30d_growth_rate),
        )
        samples.append(raw)
        detail["blog_growth_30d_raw"] = blog_cafe.recent_30d_growth_rate
        detail["blog_growth_30d_clamped"] = raw
    if not samples:
        detail["reason"] = "no_leading_signals"
        return 5.0, detail
    avg_decimal = sum(samples) / len(samples)
    # Linear ramp over the cap span: floor → 0, cap → 1.
    span = LEADING_GROWTH_CAP - LEADING_GROWTH_FLOOR  # 2.5
    norm = _clamp01((avg_decimal - LEADING_GROWTH_FLOOR) / span)
    detail["avg_growth_decimal"] = avg_decimal
    detail["norm"] = norm
    return norm * 10.0, detail


def _score_stability(seasonality_index: float) -> tuple[float, dict]:
    # 1.0 → 5pt (perfectly stable), 3.5 → 0pt, clamp non-negative.
    raw = 5.0 - min(5.0, max(0.0, seasonality_index - 1.0) * 2.0)
    return max(0.0, raw), {"seasonality_index": seasonality_index}


# ---- entry point -----------------------------------------------------------


def calculate_opportunity_score(
    inputs: OpportunityInputs,
) -> OpportunityScoreResult:
    """Compute the 100-point opportunity score for one keyword.

    Always returns a result even when exclusion filters trip; the
    caller checks ``is_excluded`` before promoting the keyword to the
    user-facing TOP-N feed.
    """
    demand, d_detail = _score_demand(inputs.volume)
    growth, g_detail = _score_growth(inputs.trend)
    competition, c_detail = _score_competition(inputs.volume, inputs.shopping)
    customs, cu_detail = _score_customs(inputs.customs)
    trend, t_detail = _score_trend(inputs.youtube, inputs.blog_cafe)
    stability, s_detail = _score_stability(inputs.seasonality_index)

    total = demand + growth + competition + customs + trend + stability
    # Defensive clamp: subscore bounds + float math should already
    # guarantee 0..100 but we want a hard contract.
    total = max(0.0, min(100.0, total))

    reasons = apply_all_filters(
        is_certification_required=inputs.is_certification_required,
        seasonality_index=inputs.seasonality_index,
        shopping=inputs.shopping,
        customs=inputs.customs,
        volume=inputs.volume,
    )

    return OpportunityScoreResult(
        total_score=round(total, 2),
        demand_score=round(demand, 2),
        growth_score=round(growth, 2),
        competition_score=round(competition, 2),
        customs_score=round(customs, 2),
        trend_score=round(trend, 2),
        stability_score=round(stability, 2),
        is_excluded=bool(reasons),
        exclusion_reasons=reasons,
        details={
            "demand": d_detail,
            "growth": g_detail,
            "competition": c_detail,
            "customs": cu_detail,
            "trend": t_detail,
            "stability": s_detail,
        },
    )
