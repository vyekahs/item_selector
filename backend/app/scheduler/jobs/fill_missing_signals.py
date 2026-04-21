"""Targeted retry for keywords with incomplete opportunity-score signals.

Upstream APIs flake (YouTube Data API quota, DataLab timeouts, 관세청
transients). The main :class:`RecalculateOpportunitiesJob` runs once
a day; when it failed to collect a signal, the keyword has a gap
until tomorrow's run.

This job runs every 30 minutes and ONLY re-processes keywords whose
today's :class:`~app.models.opportunity_score.OpportunityScore.details`
are missing a retryable signal (YouTube / blog / customs / trend).
Complete rows are skipped, so it's cheap in the happy case.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Keyword, KeywordStatus, OpportunityScore
from app.scheduler.base import ScheduledJob
from app.scheduler.jobs.recalculate_opportunities import RecalculateOpportunitiesJob

__all__ = ["FillMissingSignalsJob"]


def _is_incomplete(details: dict | None) -> bool:
    """True when the per-axis details are missing a signal we can retry."""
    if not isinstance(details, dict):
        return True

    trend = details.get("trend") or {}
    if isinstance(trend, dict):
        if trend.get("reason") == "no_leading_signals":
            return True
        if "youtube_growth_30d_raw" not in trend:
            return True
        if "blog_growth_30d_raw" not in trend:
            return True

    customs = details.get("customs") or {}
    if isinstance(customs, dict) and customs.get("reason") == "no_customs_data":
        return True

    return False


class FillMissingSignalsJob(ScheduledJob):
    """Retry upstream fetches for today's keywords with partial scores."""

    name: str = "fill_missing_signals"
    max_attempts: int = 1  # we run every 30 min so a single pass is fine

    def __init__(self, *, batch_limit: int = 100):
        super().__init__()
        self._batch_limit = batch_limit

    async def run(self, session: Session) -> dict[str, Any]:
        today = date.today()

        stmt = (
            select(Keyword.id, OpportunityScore.details)
            .join(
                OpportunityScore,
                (OpportunityScore.keyword_id == Keyword.id)
                & (OpportunityScore.snapshot_date == today),
            )
            .where(Keyword.status == KeywordStatus.ACTIVE)
            .order_by(Keyword.id.asc())
            .limit(self._batch_limit)
        )

        checked = 0
        incomplete_ids: list[int] = []
        for kw_id, details in session.execute(stmt).all():
            checked += 1
            if _is_incomplete(details):
                incomplete_ids.append(kw_id)

        if not incomplete_ids:
            return {"checked": checked, "incomplete": 0, "refreshed": 0}

        inner_result = await RecalculateOpportunitiesJob(
            keyword_ids=incomplete_ids,
            max_keywords=len(incomplete_ids),
        ).run(session)

        return {
            "checked": checked,
            "incomplete": len(incomplete_ids),
            "refreshed": inner_result.get("scores_written", 0),
            "failures": inner_result.get("failures", []),
        }
