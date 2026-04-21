"""Automatic exclusion filters (기획서 §4.3).

Each filter is a small pure function returning a *reason string* when
the input should be excluded, or ``None`` to pass. ``apply_all_filters``
runs every check and aggregates the reasons. Keeping them split makes
it trivial to unit-test edge cases and to compose new combinations
(e.g. some categories may waive the certification rule).

Reason strings are stable identifiers so they can be persisted to
``opportunity_scores.exclusion_reasons`` and translated/displayed in
the UI without parsing free-form text.
"""
from __future__ import annotations

from .types import CustomsTrendDTO, KeywordVolumeDTO, ShoppingResultDTO

# ---- thresholds ------------------------------------------------------------

#: Average review count of the top-10 shopping results above which the
#: market is considered red-ocean (기획서 §4.3).
REDOCEAN_REVIEW_THRESHOLD: int = 1000

#: Seasonality index above which the keyword is too peaky to source.
SEASONALITY_THRESHOLD: float = 2.5

#: Customs 3-month growth rate (decimal, -0.30 = -30%) below which the
#: category is treated as actively shrinking enough to auto-exclude.
#: The spec's "3개월 연속 감소" intent is stricter than "any negative";
#: small dips (−2%, −5%) are just "market cooling" noise and should
#: show up in the score penalty, not as a hard exclusion.
IMPORTS_DECLINING_THRESHOLD: float = -0.30

#: Minimum monthly search volume (PC + mobile) required to even consider
#: a keyword for recommendation. Below this the market is effectively
#: dead -- you'd need near-100% conversion just to break even on a MOQ,
#: and competitor/trend signals become pure noise. 500/mo ≈ 16/day,
#: which is the operator's "am I even going to move one unit a week?"
#: floor.
MIN_MONTHLY_SEARCH_VOLUME: int = 500


# ---- atomic filters --------------------------------------------------------


def filter_certification_required(is_certification_required: bool) -> str | None:
    """KC / 전안법 / 식약처 등 인증 필수 카테고리는 제외."""
    if is_certification_required:
        return "certification_required"
    return None


def filter_seasonality(seasonality_index: float) -> str | None:
    """계절성 지수가 ``SEASONALITY_THRESHOLD``를 초과하면 제외."""
    if seasonality_index > SEASONALITY_THRESHOLD:
        return "seasonality_too_high"
    return None


def filter_redocean_reviews(shopping: ShoppingResultDTO) -> str | None:
    """경쟁 상품 평균 리뷰가 ``REDOCEAN_REVIEW_THRESHOLD``를 초과하면 제외."""
    if shopping.top10_avg_review_count > REDOCEAN_REVIEW_THRESHOLD:
        return "redocean_reviews"
    return None


def filter_insufficient_demand(volume: KeywordVolumeDTO) -> str | None:
    """월 검색량 ``MIN_MONTHLY_SEARCH_VOLUME`` 미만은 제외.

    너무 적게 찾는 키워드는 경쟁공백·트렌드 지표가 다 노이즈가 되고,
    실제로 팔려도 월 한 자릿수라 재고 회전이 안 나옴.
    """
    if volume.total_monthly_volume < MIN_MONTHLY_SEARCH_VOLUME:
        return "insufficient_demand"
    return None


def filter_declining_imports(customs: CustomsTrendDTO | None) -> str | None:
    """관세청 3개월 수입량이 심각하게 감소 중이면 제외.

    Threshold is ``IMPORTS_DECLINING_THRESHOLD`` (default −30%). Mild
    contractions (−2%, −10%) just dock the customs subscore; they're
    not an exclusion because mature categories routinely fluctuate
    month-to-month. No customs evidence at all is *not* an exclusion.
    """
    if customs is None:
        return None
    if customs.growth_rate_3m <= IMPORTS_DECLINING_THRESHOLD:
        return "imports_declining"
    return None


# ---- aggregator ------------------------------------------------------------


def apply_all_filters(
    *,
    is_certification_required: bool,
    seasonality_index: float,
    shopping: ShoppingResultDTO,
    customs: CustomsTrendDTO | None,
    volume: KeywordVolumeDTO | None = None,
) -> list[str]:
    """Run every exclusion filter and return the list of triggered reasons.

    Returns an empty list when the keyword passes every filter. The
    caller decides what to do (today: set ``is_excluded=True`` and
    persist the reasons string).
    """
    checks = [
        filter_certification_required(is_certification_required),
        filter_seasonality(seasonality_index),
        filter_redocean_reviews(shopping),
        filter_declining_imports(customs),
    ]
    if volume is not None:
        checks.append(filter_insufficient_demand(volume))
    return [reason for reason in checks if reason is not None]
