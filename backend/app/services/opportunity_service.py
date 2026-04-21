"""Read-side service for ``/opportunities``.

The actual *generation* of opportunity scores is owned by the Scoring
Engine + Scheduler agents (write path). This module only reads the
latest snapshot per keyword from ``opportunity_scores`` and turns it
into the frontend-facing schema.

A 1688 deep link is constructed from the keyword text. The URL format is
intentionally trivial -- 1688 accepts ``keywords=`` as a UTF-8 query
param and handles its own URL-encoding via the search page.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    Category,
    Keyword,
    KeywordMetric,
    OpportunityScore,
    Product,
)
from app.schemas.responses.opportunity import (
    CompetitionBreakdown,
    OpportunityMetricsSummary,
    OpportunityResponse,
)

_BASE_1688_SEARCH = "https://s.1688.com/selloffer/offer_search.htm?keywords="


def build_1688_search_url(term: str, chinese_term: str | None = None) -> str:
    """Build a 1688 deep link for the given term.

    1688's ``keywords=`` endpoint decodes the URL-decoded byte stream
    as **GBK**, not UTF-8. That means we must:

    1. Translate Korean → Simplified Chinese (``chinese_term``).
    2. Encode the Chinese string as **GBK bytes**, then URL-percent-encode
       those bytes. ``gb18030`` is used because it's a GBK superset and
       covers every CJK char Google Translate may emit.

    Falling back to the raw Korean ``term`` is still useful for debugging
    (link exists, just mojibakes) while the translate job catches up.
    """
    lookup = (chinese_term or "").strip() or term
    try:
        gbk_bytes = lookup.encode("gb18030")
    except UnicodeEncodeError:
        # Korean fallback won't round-trip through GBK; send as UTF-8.
        return _BASE_1688_SEARCH + quote(lookup, safe="")
    return _BASE_1688_SEARCH + quote(gbk_bytes, safe="")


def _competition_level_from_score(score: float | None) -> str | None:
    """Map a 0-20 competition_score back to 낮음 / 중간 / 높음.

    Higher score → emptier market (good for sourcing) → "낮음 경쟁".
    """
    if score is None:
        return None
    if score >= 14:
        return "낮음"
    if score >= 7:
        return "중간"
    return "높음"


def _to_response(
    rank: int,
    keyword: Keyword,
    score: OpportunityScore,
    metric: KeywordMetric | None,
    category_name: str | None,
    product_count: int = 0,
) -> OpportunityResponse:
    details = score.details or {}
    comp_detail = details.get("competition") if isinstance(details, dict) else None
    customs_detail = details.get("customs") if isinstance(details, dict) else None

    competition_breakdown: CompetitionBreakdown | None = None
    if isinstance(comp_detail, dict):
        ci = comp_detail.get("competition_index")
        # Scoring stores the raw vacancy multiplier after shopping
        # penalty; recover the penalty factor so the UI can show it.
        vacancy = comp_detail.get("vacancy")
        demand_factor = comp_detail.get("demand_factor")
        # penalty = vacancy_post / vacancy_pre where vacancy_pre = 1 - ci.
        penalty: float | None = None
        if ci is not None and vacancy is not None and (1.0 - float(ci)) > 0:
            penalty = round(float(vacancy) / (1.0 - float(ci)), 2)
        competition_breakdown = CompetitionBreakdown(
            competition_index=float(ci) if ci is not None else None,
            demand_factor=float(demand_factor) if demand_factor is not None else None,
            shopping_penalty=penalty,
        )

    customs_growth_pct: float | None = None
    if isinstance(customs_detail, dict):
        raw = customs_detail.get("growth_rate_3m_pct")
        if raw is not None:
            customs_growth_pct = float(raw)

    summary = OpportunityMetricsSummary(
        monthly_search_volume=metric.monthly_search_volume if metric else None,
        search_growth_3m=float(metric.growth_rate_3m) if metric and metric.growth_rate_3m is not None else None,
        customs_growth_3m_pct=customs_growth_pct,
        # kept for backward compat; frontend should migrate off.
        import_growth=float(score.customs_score) / 20.0 if score.customs_score is not None else None,
        competition_raw_score=(
            float(score.competition_score)
            if score.competition_score is not None
            else None
        ),
        competition_breakdown=competition_breakdown,
        competition_level=_competition_level_from_score(
            float(score.competition_score) if score.competition_score is not None else None
        ),
        naver_shopping_count=metric.naver_shopping_count if metric else None,
        smartstore_avg_price_krw=metric.shopping_avg_price_krw if metric else None,
        coupang_avg_price_krw=None,
    )
    return OpportunityResponse(
        rank=rank,
        keyword_id=keyword.id,
        term=keyword.term,
        category_id=keyword.category_id,
        category_name=category_name,
        score_details=details if isinstance(details, dict) and details else None,
        snapshot_date=score.snapshot_date,
        total_score=float(score.total_score),
        demand_score=float(score.demand_score),
        growth_score=float(score.growth_score),
        competition_score=float(score.competition_score),
        customs_score=float(score.customs_score),
        trend_score=float(score.trend_score),
        stability_score=float(score.stability_score),
        is_excluded=bool(score.is_excluded),
        exclusion_reasons=score.exclusion_reasons,
        metrics=summary,
        search_1688_url=build_1688_search_url(keyword.term, keyword.chinese_term),
        product_count=product_count,
    )


def get_top_opportunities(
    session: Session,
    *,
    category_id: int | None = None,
    limit: int = 20,
    min_score: float = 0,
    include_excluded: bool = False,
) -> list[OpportunityResponse]:
    """Return the latest snapshot per keyword, ranked by ``total_score`` desc.

    Implementation note: we use a correlated subquery to pick the
    "latest snapshot_date per keyword" and then join it back. This
    keeps the result set small even when the snapshot table is large
    (one row per keyword per day forever).
    """
    latest = (
        select(
            OpportunityScore.keyword_id.label("kid"),
            func.max(OpportunityScore.snapshot_date).label("max_date"),
        )
        .group_by(OpportunityScore.keyword_id)
        .subquery()
    )
    # Correlate the snapshot row with the (keyword_id, max_date) pair.
    score_alias = aliased(OpportunityScore)
    metric_alias = aliased(KeywordMetric)

    # Separately pick the latest metric per keyword -- the score job
    # and the metrics job don't always run on the same day (the score
    # can reuse yesterday's metrics through the scoring engine), so we
    # must NOT require ``metric.snapshot_date == score.snapshot_date``
    # or we'd drop valid recent metrics.
    latest_metric = (
        select(
            KeywordMetric.keyword_id.label("mkid"),
            func.max(KeywordMetric.snapshot_date).label("metric_date"),
        )
        .group_by(KeywordMetric.keyword_id)
        .subquery()
    )

    stmt = (
        select(Keyword, score_alias, metric_alias, Category)
        .join(latest, latest.c.kid == Keyword.id)
        .join(
            score_alias,
            and_(
                score_alias.keyword_id == latest.c.kid,
                score_alias.snapshot_date == latest.c.max_date,
            ),
        )
        .outerjoin(Category, Category.id == Keyword.category_id)
        .outerjoin(latest_metric, latest_metric.c.mkid == Keyword.id)
        .outerjoin(
            metric_alias,
            and_(
                metric_alias.keyword_id == Keyword.id,
                metric_alias.snapshot_date == latest_metric.c.metric_date,
            ),
        )
        .order_by(score_alias.total_score.desc(), Keyword.term.asc())
    )

    if category_id is not None:
        stmt = stmt.where(Keyword.category_id == category_id)
    if not include_excluded:
        stmt = stmt.where(score_alias.is_excluded.is_(False))
    if min_score > 0:
        stmt = stmt.where(score_alias.total_score >= min_score)
    stmt = stmt.limit(limit)

    rows: list[tuple[Keyword, OpportunityScore, KeywordMetric | None, Category | None]] = (
        session.execute(stmt).all()  # type: ignore[assignment]
    )

    # Count products per keyword in one query so the row build is O(1).
    keyword_ids = [k.id for k, *_ in rows]
    product_counts: dict[int, int] = {}
    if keyword_ids:
        count_rows = session.execute(
            select(Product.keyword_id, func.count(Product.id))
            .where(Product.keyword_id.in_(keyword_ids))
            .group_by(Product.keyword_id)
        ).all()
        product_counts = {kid: int(n) for kid, n in count_rows if kid is not None}

    out: list[OpportunityResponse] = []
    for rank, (keyword, score, metric, category) in enumerate(rows, start=1):
        out.append(
            _to_response(
                rank=rank,
                keyword=keyword,
                score=score,
                metric=metric,
                category_name=category.name if category else None,
                product_count=product_counts.get(keyword.id, 0),
            )
        )
    return out


# ---------------------------------------------------------------------
# Write-path stub: the actual collection + scoring pipeline lives in the
# Scheduler agent, but Backend may still want to trigger a refresh
# from an admin endpoint. We deliberately keep this as a "call out to
# whatever exists" stub so the route compiles even if Scoring/Data
# Collection are not yet wired together.
# ---------------------------------------------------------------------


def refresh_opportunities(  # pragma: no cover - thin orchestration stub
    session: Session,
    *,
    keyword_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Best-effort hand-off to the Scheduler / Scoring pipeline.

    The real implementation will:
      1. Resolve the keyword set (from ``keyword_ids`` or ``status==ACTIVE``).
      2. Fan out to ``app.clients.*`` for data collection.
      3. Call ``app.scoring.opportunity.calculate_opportunity_score``.
      4. Persist new ``opportunity_scores`` rows.

    Until both upstream agents land, this just reports what would run.
    """
    return {
        "status": "deferred",
        "reason": (
            "refresh pipeline owned by Scheduler agent + Scoring agent; "
            "not yet wired"
        ),
        "requested_keyword_ids": keyword_ids or [],
    }
