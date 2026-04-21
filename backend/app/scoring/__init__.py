"""Scoring engine — pure functions over upstream DTOs.

Public surface (consumed by the Backend API + Scheduler agents):

* :func:`calculate_opportunity_score` — keyword-level 100-pt opportunity score.
* :func:`calculate_smartstore_revenue` / :func:`calculate_coupang_revenue` —
  per-channel economics.
* :func:`calculate_product_score` — composite product verdict + GO/CONDITIONAL/PASS.
* :func:`apply_all_filters` — automatic exclusion checks.
* :func:`suggest_hs_codes` — Phase-1 static HS-code suggestions.

The DTO classes in :mod:`app.scoring.types` are temporary local stubs
that mirror the shared ``app.contracts.dto`` contract being authored
in parallel by the Data Collection Agent. Once that lands, swap the
imports inside ``types.py`` and delete the local definitions; nothing
else in this package needs to change.
"""
from __future__ import annotations

from .filters import apply_all_filters
from .hs_mapping import suggest_hs_codes
from .opportunity import (
    OpportunityInputs,
    OpportunityScoreResult,
    calculate_opportunity_score,
)
from .product import (
    CONDITIONAL_THRESHOLD,
    GO_THRESHOLD,
    ProductScoreInputs,
    ProductScoreResult,
    calculate_product_score,
)
from .revenue import (
    DEFAULT_COUPANG_AD_PCT,
    DEFAULT_SMARTSTORE_AD_PCT,
    SMARTSTORE_FEE_PCT,
    ChannelRevenueResult,
    CostBreakdown,
    RevenueInputs,
    calculate_coupang_revenue,
    calculate_smartstore_revenue,
    compute_cost_breakdown,
)
from .types import Channel, Recommendation

__all__ = [
    # opportunity
    "OpportunityInputs",
    "OpportunityScoreResult",
    "calculate_opportunity_score",
    # revenue
    "RevenueInputs",
    "ChannelRevenueResult",
    "SMARTSTORE_FEE_PCT",
    "DEFAULT_SMARTSTORE_AD_PCT",
    "DEFAULT_COUPANG_AD_PCT",
    "CostBreakdown",
    "compute_cost_breakdown",
    "calculate_smartstore_revenue",
    "calculate_coupang_revenue",
    # product
    "ProductScoreInputs",
    "ProductScoreResult",
    "calculate_product_score",
    "GO_THRESHOLD",
    "CONDITIONAL_THRESHOLD",
    # filters / mapping
    "apply_all_filters",
    "suggest_hs_codes",
    # enums
    "Channel",
    "Recommendation",
]
