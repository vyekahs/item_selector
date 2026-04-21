"""Opportunity score tests.

Strategy: start from the baseline fixture (which already lands in the
healthy-mid range), then perturb one input at a time and assert on the
specific subscore + total. Boundary tests cover the "0 / max" corners
of every axis.
"""
from __future__ import annotations

import pytest

from app.scoring.opportunity import (
    OpportunityInputs,
    calculate_opportunity_score,
)
from app.scoring.types import (
    KeywordVolumeDTO,
    NaverTrendDTO,
    ShoppingResultDTO,
)

from tests.scoring.conftest import (
    make_blog_cafe,
    make_customs,
    make_shopping,
    make_trend,
    make_volume,
    make_youtube,
)


# ---- happy path ------------------------------------------------------------


def test_baseline_scores_within_healthy_band(
    baseline_opportunity_inputs: OpportunityInputs,
):
    r = calculate_opportunity_score(baseline_opportunity_inputs)
    # Healthy mid-range fixture should score in the 50–95 range and not
    # be excluded; we keep a wide envelope so minor weight tweaks don't
    # flake the test, but lock the bounds.
    assert 50.0 <= r.total_score <= 95.0
    assert not r.is_excluded
    assert r.exclusion_reasons == []
    # Sanity: per-axis subscores honour their max.
    assert 0 <= r.demand_score <= 25
    assert 0 <= r.growth_score <= 20
    assert 0 <= r.competition_score <= 20
    assert 0 <= r.customs_score <= 20
    assert 0 <= r.trend_score <= 10
    assert 0 <= r.stability_score <= 5


# ---- demand axis -----------------------------------------------------------


def test_demand_zero_when_no_volume(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"volume": make_volume(pc=0, mobile=0)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.demand_score == 0.0


def test_demand_saturates_at_anchor(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"volume": make_volume(pc=50_000, mobile=50_000)}
    )
    r = calculate_opportunity_score(new_inputs)
    # 100K maps exactly to the saturation anchor → full 25 points.
    assert r.demand_score == pytest.approx(25.0, abs=0.05)


def test_demand_above_anchor_clamps(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"volume": make_volume(pc=500_000, mobile=500_000)}
    )
    r = calculate_opportunity_score(new_inputs)
    # Spec: clamp at full marks even when the wire reports way more.
    assert r.demand_score == 25.0


# ---- growth axis -----------------------------------------------------------


def test_growth_floor_at_minus_10pct(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"trend": make_trend(growth_3m=-0.10)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.growth_score == pytest.approx(0.0, abs=0.01)


def test_growth_full_at_plus_50pct(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"trend": make_trend(growth_3m=0.50)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.growth_score == pytest.approx(20.0, abs=0.01)


def test_growth_clamps_above_plus_50pct(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"trend": make_trend(growth_3m=2.0)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.growth_score == 20.0


def test_growth_below_floor_clamps_to_zero(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # Triggers the customs-decline filter via shared logic; here we
    # only care about the growth subscore lower clamp.
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"trend": make_trend(growth_3m=-0.50)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.growth_score == 0.0


# ---- competition axis ------------------------------------------------------


def test_competition_zero_when_market_saturated(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # High 검색광고 competition index (0.8 = 높음) + flooded shelf (>500K
    # listings) should drop the axis below 5pt regardless of demand.
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={
            "volume": make_volume(pc=10_000, mobile=18_000, competition=0.8),
            "shopping": make_shopping(total=1_000_000, top10_reviews=100),
        }
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.competition_score < 5.0


def test_competition_high_when_blue_ocean(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # Low 검색광고 competition (0.1 = 낮음) + good demand (≥10K/mo) +
    # sparse shelf → near full 20pt.
    inputs = baseline_opportunity_inputs.model_copy(
        update={
            "volume": make_volume(pc=10_000, mobile=10_000, competition=0.1),
            "shopping": make_shopping(total=100, top10_reviews=50),
        }
    )
    r = calculate_opportunity_score(inputs)
    assert r.competition_score >= 15.0


# ---- customs axis ----------------------------------------------------------


def test_customs_neutral_when_missing(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(update={"customs": None})
    r = calculate_opportunity_score(new_inputs)
    # Spec: missing data → neutral midpoint = 10/20.
    assert r.customs_score == pytest.approx(10.0, abs=0.01)
    # Missing data should NOT add an exclusion.
    assert "imports_declining" not in r.exclusion_reasons


def test_customs_full_at_plus_30pct(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"customs": make_customs(growth_3m=0.30)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.customs_score == pytest.approx(20.0, abs=0.01)


def test_customs_zero_at_minus_30pct(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # New scale (symmetric around 0%): -30% → 0, 0% → 10, +30% → 20.
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"customs": make_customs(growth_3m=-0.30)}
    )
    r = calculate_opportunity_score(new_inputs)
    # Subscore floors at 0 even though the exclusion fires too.
    assert r.customs_score == pytest.approx(0.0, abs=0.01)


def test_customs_neutral_at_flat_zero(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # 0% import growth = stable established category → 10 pt (neutral).
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"customs": make_customs(growth_3m=0.0)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.customs_score == pytest.approx(10.0, abs=0.01)


# ---- trend axis ------------------------------------------------------------


def test_trend_neutral_when_no_leading_signals(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"youtube": None, "blog_cafe": None}
    )
    r = calculate_opportunity_score(new_inputs)
    # Half marks when we have nothing to measure.
    assert r.trend_score == pytest.approx(5.0, abs=0.01)


def test_trend_full_at_plus_200pct_average(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # New cap: +200% saturates. Values above are clamped to the cap so
    # runaway 10000%+ signals can't single-handedly pin the axis.
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={
            "youtube": make_youtube(growth=2.5),       # clamped to 2.0
            "blog_cafe": make_blog_cafe(growth=2.0),   # already at cap
        }
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.trend_score == pytest.approx(10.0, abs=0.01)


def test_trend_runaway_value_is_clamped(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # Real-world 10000% blog growth should not exceed the cap.
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={
            "youtube": make_youtube(growth=0.0),        # 0% (neutral)
            "blog_cafe": make_blog_cafe(growth=100.0),  # +10000% → clamped to 200%
        }
    )
    r = calculate_opportunity_score(new_inputs)
    # Avg of 0% and 200% = 100%. Norm = (1.0 - (-0.5)) / 2.5 = 0.6 → 6pt.
    assert r.trend_score == pytest.approx(6.0, abs=0.5)


# ---- stability axis --------------------------------------------------------


def test_stability_full_when_flat(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"seasonality_index": 1.0}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.stability_score == pytest.approx(5.0, abs=0.01)


def test_stability_zero_at_3_5(
    baseline_opportunity_inputs: OpportunityInputs,
):
    # Note: 3.5 > 2.5 also trips the seasonality filter; we still
    # expect the subscore math to drop to 0 cleanly.
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"seasonality_index": 3.5}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.stability_score == 0.0
    assert r.is_excluded


# ---- exclusion behaviour ---------------------------------------------------


def test_certification_excludes(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"is_certification_required": True}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.is_excluded
    assert "certification_required" in r.exclusion_reasons
    # Subscore math still runs so the UI can explain the verdict.
    assert r.total_score > 0


def test_redocean_excludes(
    baseline_opportunity_inputs: OpportunityInputs,
):
    new_inputs = baseline_opportunity_inputs.model_copy(
        update={"shopping": make_shopping(total=2_000, top10_reviews=2_500)}
    )
    r = calculate_opportunity_score(new_inputs)
    assert r.is_excluded
    assert "redocean_reviews" in r.exclusion_reasons


def test_total_bounded_in_zero_to_hundred(
    baseline_opportunity_inputs: OpportunityInputs,
):
    """Worst-case + best-case inputs both stay within [0, 100]."""
    worst = baseline_opportunity_inputs.model_copy(
        update={
            "volume": make_volume(pc=0, mobile=0),
            "trend": make_trend(growth_3m=-0.50),
            "shopping": make_shopping(total=10**7, top10_reviews=5_000),
            "customs": make_customs(growth_3m=-0.50),
            "youtube": make_youtube(growth=-1.0),
            "blog_cafe": make_blog_cafe(growth=-1.0),
            "seasonality_index": 5.0,
        }
    )
    best = baseline_opportunity_inputs.model_copy(
        update={
            "volume": make_volume(pc=10_000_000, mobile=10_000_000),
            "trend": make_trend(growth_3m=5.0),
            "shopping": make_shopping(total=1, top10_reviews=0),
            "customs": make_customs(growth_3m=5.0),
            "youtube": make_youtube(growth=5.0),
            "blog_cafe": make_blog_cafe(growth=5.0),
            "seasonality_index": 1.0,
        }
    )
    rw = calculate_opportunity_score(worst)
    rb = calculate_opportunity_score(best)
    assert 0.0 <= rw.total_score <= 100.0
    assert 0.0 <= rb.total_score <= 100.0
    assert rb.total_score > rw.total_score
