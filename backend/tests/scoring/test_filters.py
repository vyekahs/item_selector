"""Exclusion-filter unit tests.

Each filter is exercised independently and through the
:func:`apply_all_filters` aggregator so we know:

1. Each rule trips on the correct boundary.
2. Reasons are stable identifiers (UI / persistence depend on this).
3. The aggregator is order-independent and additive.
"""
from __future__ import annotations

from app.scoring.filters import (
    REDOCEAN_REVIEW_THRESHOLD,
    SEASONALITY_THRESHOLD,
    apply_all_filters,
    filter_certification_required,
    filter_declining_imports,
    filter_redocean_reviews,
    filter_seasonality,
)

from tests.scoring.conftest import make_customs, make_shopping


# ---- atomic filters --------------------------------------------------------


class TestCertificationFilter:
    def test_blocks_when_required(self):
        assert filter_certification_required(True) == "certification_required"

    def test_passes_when_not_required(self):
        assert filter_certification_required(False) is None


class TestSeasonalityFilter:
    def test_blocks_above_threshold(self):
        assert (
            filter_seasonality(SEASONALITY_THRESHOLD + 0.01)
            == "seasonality_too_high"
        )

    def test_at_threshold_passes(self):
        # ">" semantics, not ">=".
        assert filter_seasonality(SEASONALITY_THRESHOLD) is None

    def test_flat_passes(self):
        assert filter_seasonality(1.0) is None


class TestRedoceanFilter:
    def test_blocks_above_threshold(self):
        s = make_shopping(top10_reviews=REDOCEAN_REVIEW_THRESHOLD + 1)
        assert filter_redocean_reviews(s) == "redocean_reviews"

    def test_at_threshold_passes(self):
        s = make_shopping(top10_reviews=REDOCEAN_REVIEW_THRESHOLD)
        assert filter_redocean_reviews(s) is None

    def test_low_competition_passes(self):
        s = make_shopping(top10_reviews=42)
        assert filter_redocean_reviews(s) is None


class TestDecliningImportsFilter:
    def test_blocks_severe_decline(self):
        # Threshold is -30%. Only a persistent/severe decline excludes.
        c = make_customs(growth_3m=-0.35)
        assert filter_declining_imports(c) == "imports_declining"

    def test_mild_decline_passes(self):
        # Mild contraction is only a score penalty, not an exclusion.
        c = make_customs(growth_3m=-0.10)
        assert filter_declining_imports(c) is None

    def test_zero_growth_passes(self):
        c = make_customs(growth_3m=0.0)
        assert filter_declining_imports(c) is None

    def test_positive_growth_passes(self):
        c = make_customs(growth_3m=0.20)
        assert filter_declining_imports(c) is None

    def test_no_customs_data_passes(self):
        # Missing data is neutral, NOT exclusion.
        assert filter_declining_imports(None) is None


# ---- aggregator ------------------------------------------------------------


class TestApplyAllFilters:
    def test_clean_inputs_return_empty(self):
        reasons = apply_all_filters(
            is_certification_required=False,
            seasonality_index=1.0,
            shopping=make_shopping(top10_reviews=100),
            customs=make_customs(growth_3m=0.20),
        )
        assert reasons == []

    def test_aggregates_multiple_reasons(self):
        reasons = apply_all_filters(
            is_certification_required=True,
            seasonality_index=3.0,
            shopping=make_shopping(top10_reviews=2_000),
            customs=make_customs(growth_3m=-0.40),
        )
        assert set(reasons) == {
            "certification_required",
            "seasonality_too_high",
            "redocean_reviews",
            "imports_declining",
        }

    def test_missing_customs_does_not_trip(self):
        reasons = apply_all_filters(
            is_certification_required=False,
            seasonality_index=1.0,
            shopping=make_shopping(top10_reviews=100),
            customs=None,
        )
        assert reasons == []
