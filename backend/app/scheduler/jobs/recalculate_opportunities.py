"""Recompute ``opportunity_scores`` for every active keyword.

Wiring
------
Upstream clients return percentage-form growth rates (``5.0 = +5%``)
while :mod:`app.scoring` expects decimal form (``0.05 = +5%``) — see
``app/scoring/types.py``. This job performs the conversion inline
when composing :class:`~app.scoring.OpportunityInputs`.

Idempotency
-----------
Upserts on ``(keyword_id, snapshot_date)``. Re-running the same day
updates the existing row, so a failed metrics fetch followed by a
successful retry converges.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.clients import (
    CustomsClientProtocol,
    NaverBlogCafeClientProtocol,
    NaverDataLabClientProtocol,
    NaverSearchAdClientProtocol,
    NaverShoppingClientProtocol,
    YouTubeClientProtocol,
    get_customs_client,
    get_naver_blogcafe_client,
    get_naver_datalab_client,
    get_naver_searchad_client,
    get_naver_shopping_client,
    get_youtube_client,
)
from app.contracts.dto import (
    BlogCafeDTO,
    CustomsTrendDTO,
    KeywordVolumeDTO,
    NaverTrendDTO,
    ShoppingResultDTO,
    YouTubeSignalDTO,
)
from app.models import (
    Category,
    Keyword,
    KeywordHsMapping,
    KeywordStatus,
    OpportunityScore,
)
from app.scheduler.base import ScheduledJob, utcnow
from app.scoring import (
    OpportunityInputs,
    calculate_opportunity_score,
    suggest_hs_codes,
)

__all__ = ["RecalculateOpportunitiesJob"]


# Fallback category name used when a keyword has no ``category_id``.
_UNCATEGORIZED = "미분류"


def _pct_to_decimal(pct: float | None) -> float:
    """Convert a percent value (5.0 → +5%) to scoring's decimal form (0.05)."""
    if pct is None:
        return 0.0
    return float(pct) / 100.0


def _to_scoring_volume(dto: KeywordVolumeDTO) -> dict[str, Any]:
    return {
        "term": dto.term,
        "pc_monthly_volume": dto.pc_monthly_volume,
        "mobile_monthly_volume": dto.mobile_monthly_volume,
        "total_monthly_volume": dto.total_monthly_volume,
        "competition_index": dto.competition_index,
        "related_keywords": list(dto.related_keywords),
    }


def _to_scoring_trend(dto: NaverTrendDTO) -> dict[str, Any]:
    return {
        "term": dto.term,
        "points": [
            {"period": p.period, "ratio": p.ratio} for p in dto.points
        ],
        "growth_rate_3m": _pct_to_decimal(dto.growth_rate_3m),
        "growth_rate_6m": _pct_to_decimal(dto.growth_rate_6m),
        "growth_rate_12m": _pct_to_decimal(dto.growth_rate_12m),
    }


def _to_scoring_shopping(dto: ShoppingResultDTO) -> dict[str, Any]:
    return {
        "query": dto.query,
        "total_count": dto.total_count,
        "items": [
            {
                "title": it.title,
                "price": it.price,
                "review_count": it.review_count or 0,
            }
            for it in dto.items
        ],
        "avg_price": dto.avg_price,
        "median_price": dto.median_price,
        "top10_avg_review_count": int(round(dto.top10_avg_review_count)),
    }


def _to_scoring_blogcafe(dto: BlogCafeDTO) -> dict[str, Any]:
    return {
        "term": dto.term,
        "blog_post_count": dto.blog_post_count,
        "cafe_post_count": dto.cafe_post_count,
        "recent_30d_blog_count": dto.recent_30d_blog_count,
        "recent_30d_growth_rate": _pct_to_decimal(dto.recent_30d_growth_rate),
    }


def _to_scoring_youtube(dto: YouTubeSignalDTO) -> dict[str, Any]:
    return {
        "term": dto.term,
        "total_video_count": dto.total_video_count,
        "recent_30d_video_count": dto.recent_30d_video_count,
        "avg_view_count": float(dto.avg_view_count),
        "growth_rate_30d": _pct_to_decimal(dto.growth_rate_30d),
    }


def _to_scoring_customs(dto: CustomsTrendDTO) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    for pt in dto.points:
        points.append(
            {
                "year_month": pt.year_month,
                "import_value_usd": float(pt.import_value_usd),
                "import_quantity": float(pt.import_quantity),
            }
        )
    return {
        "hs_code": dto.hs_code,
        "country_code": dto.country_code,
        "points": points,
        "growth_rate_3m": _pct_to_decimal(dto.growth_rate_3m),
        "growth_rate_12m": _pct_to_decimal(dto.growth_rate_12m),
    }


class RecalculateOpportunitiesJob(ScheduledJob):
    """Run :func:`calculate_opportunity_score` for every ACTIVE keyword."""

    name: str = "recalculate_opportunities"
    max_attempts: int = 3

    def __init__(
        self,
        *,
        searchad_client: NaverSearchAdClientProtocol | None = None,
        datalab_client: NaverDataLabClientProtocol | None = None,
        shopping_client: NaverShoppingClientProtocol | None = None,
        blogcafe_client: NaverBlogCafeClientProtocol | None = None,
        youtube_client: YouTubeClientProtocol | None = None,
        customs_client: CustomsClientProtocol | None = None,
        max_keywords: int = 500,
        keyword_ids: list[int] | None = None,
    ):
        super().__init__()
        self._searchad = searchad_client
        self._datalab = datalab_client
        self._shopping = shopping_client
        self._blogcafe = blogcafe_client
        self._youtube = youtube_client
        self._customs = customs_client
        self._max_keywords = max_keywords
        # Optional narrow-retry mode: when set, only these keyword IDs
        # are reprocessed (used by :class:`FillMissingSignalsJob`).
        self._keyword_ids = keyword_ids

    # --- client resolvers (explicit so tests can override one at a time) ---

    def _searchad_client(self) -> NaverSearchAdClientProtocol:
        return self._searchad or get_naver_searchad_client()

    def _datalab_client(self) -> NaverDataLabClientProtocol:
        return self._datalab or get_naver_datalab_client()

    def _shopping_client(self) -> NaverShoppingClientProtocol:
        return self._shopping or get_naver_shopping_client()

    def _blogcafe_client(self) -> NaverBlogCafeClientProtocol:
        return self._blogcafe or get_naver_blogcafe_client()

    def _youtube_client(self) -> YouTubeClientProtocol:
        return self._youtube or get_youtube_client()

    def _customs_client(self) -> CustomsClientProtocol:
        return self._customs or get_customs_client()

    # --- implementation ---------------------------------------------------

    async def _customs_for(
        self,
        session: Session,
        kw: Keyword,
        category_name: str,
        customs_client: CustomsClientProtocol,
    ) -> CustomsTrendDTO | None:
        """Pick a plausible HS code and fetch its customs trend, if any."""
        # Prefer an explicit DB mapping (highest confidence first).
        mapping = session.execute(
            select(KeywordHsMapping)
            .where(KeywordHsMapping.keyword_id == kw.id)
            .order_by(KeywordHsMapping.confidence.desc())
            .limit(1)
        ).scalar_one_or_none()

        hs_code: str | None = mapping.hs_code if mapping else None
        if hs_code is None:
            suggestions = suggest_hs_codes(category_name, kw.term)
            hs_code = suggestions[0] if suggestions else None
        if hs_code is None:
            return None

        try:
            return await customs_client.fetch(hs_code)
        except Exception:  # noqa: BLE001 — treat as "no customs data".
            return None

    async def run(self, session: Session) -> dict[str, Any]:
        searchad = self._searchad_client()
        datalab = self._datalab_client()
        shopping = self._shopping_client()
        blogcafe = self._blogcafe_client()
        youtube = self._youtube_client()
        customs = self._customs_client()

        # Score any ACTIVE keyword — PENDING keywords have no metrics yet.
        stmt = (
            select(Keyword)
            .where(Keyword.status == KeywordStatus.ACTIVE)
            .order_by(Keyword.is_seed.desc(), Keyword.id.asc())
            .limit(self._max_keywords)
        )
        if self._keyword_ids:
            # Narrow-retry mode: only process these IDs.
            stmt = (
                select(Keyword)
                .where(Keyword.id.in_(self._keyword_ids))
                .limit(self._max_keywords)
            )
        keywords: list[Keyword] = list(session.execute(stmt).scalars())
        if not keywords:
            return {"keywords_processed": 0, "scores_written": 0}

        today = date.today()
        scores_written = 0
        excluded_count = 0
        failures: list[str] = []

        # Resolve category names in one query.
        cat_ids = {k.category_id for k in keywords if k.category_id is not None}
        cat_lookup: dict[int, tuple[str, bool]] = {}
        if cat_ids:
            for cat in session.execute(
                select(Category).where(Category.id.in_(cat_ids))
            ).scalars():
                cat_lookup[cat.id] = (cat.name, bool(cat.is_certification_required))

        for kw in keywords:
            category_name, cert_required = (
                cat_lookup.get(kw.category_id, (_UNCATEGORIZED, False))
                if kw.category_id is not None
                else (_UNCATEGORIZED, False)
            )
            try:
                volume_rows = await searchad.fetch([kw.term])
                if not volume_rows:
                    failures.append(f"{kw.term}: no_volume")
                    continue
                volume = volume_rows[0]

                trend_rows = await datalab.fetch([[kw.term]])
                if not trend_rows:
                    failures.append(f"{kw.term}: no_trend")
                    continue
                trend = trend_rows[0]

                shopping_dto = await shopping.fetch(kw.term)

                # Soft-fail the optional leading signals.
                blogcafe_dto: BlogCafeDTO | None
                youtube_dto: YouTubeSignalDTO | None
                try:
                    blogcafe_dto = await blogcafe.fetch(kw.term)
                except Exception:  # noqa: BLE001
                    blogcafe_dto = None
                try:
                    youtube_dto = await youtube.fetch(kw.term)
                except Exception:  # noqa: BLE001
                    youtube_dto = None

                customs_dto = await self._customs_for(
                    session, kw, category_name, customs
                )

            except Exception as exc:  # noqa: BLE001 — per-keyword isolation
                failures.append(f"{kw.term}: {type(exc).__name__}")
                continue

            inputs = OpportunityInputs.model_validate(
                {
                    "keyword": kw.term,
                    "volume": _to_scoring_volume(volume),
                    "trend": _to_scoring_trend(trend),
                    "shopping": _to_scoring_shopping(shopping_dto),
                    "blog_cafe": _to_scoring_blogcafe(blogcafe_dto)
                    if blogcafe_dto
                    else None,
                    "youtube": _to_scoring_youtube(youtube_dto)
                    if youtube_dto
                    else None,
                    "customs": _to_scoring_customs(customs_dto)
                    if customs_dto
                    else None,
                    "category_name": category_name,
                    "is_certification_required": cert_required,
                    "seasonality_index": 1.0,
                }
            )
            result = calculate_opportunity_score(inputs)

            reasons_str = ",".join(result.exclusion_reasons) or None
            # Make details JSONB-safe: Decimals and non-JSON scalars can
            # leak in from upstream DTOs. json round-trip normalises.
            import json as _json

            safe_details = _json.loads(_json.dumps(result.details, default=str))
            ins = pg_insert(OpportunityScore).values(
                keyword_id=kw.id,
                snapshot_date=today,
                total_score=Decimal(str(result.total_score)),
                demand_score=Decimal(str(result.demand_score)),
                growth_score=Decimal(str(result.growth_score)),
                competition_score=Decimal(str(result.competition_score)),
                customs_score=Decimal(str(result.customs_score)),
                trend_score=Decimal(str(result.trend_score)),
                stability_score=Decimal(str(result.stability_score)),
                is_excluded=result.is_excluded,
                exclusion_reasons=reasons_str,
                details=safe_details,
            )
            ins = ins.on_conflict_do_update(
                constraint="opportunity_score_unique_snapshot",
                set_={
                    "total_score": ins.excluded.total_score,
                    "demand_score": ins.excluded.demand_score,
                    "growth_score": ins.excluded.growth_score,
                    "competition_score": ins.excluded.competition_score,
                    "customs_score": ins.excluded.customs_score,
                    "trend_score": ins.excluded.trend_score,
                    "stability_score": ins.excluded.stability_score,
                    "is_excluded": ins.excluded.is_excluded,
                    "exclusion_reasons": ins.excluded.exclusion_reasons,
                    "details": ins.excluded.details,
                    "updated_at": utcnow(),
                },
            )
            session.execute(ins)
            scores_written += 1
            if result.is_excluded:
                excluded_count += 1

        session.commit()

        return {
            "keywords_processed": len(keywords),
            "scores_written": scores_written,
            "excluded_count": excluded_count,
            "failures": failures,
        }
