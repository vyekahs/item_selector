"""``/admin`` router — manual job triggers.

Guarded by the external Caddy basic-auth layer. Kicks off the full
``collect_keywords → collect_metrics → recalculate_opportunities``
pipeline in the background so the caller doesn't wait 2–3 min on a
single request.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, status

from app.db.session import SessionLocal
from app.scheduler.jobs.collect_keywords import CollectKeywordsJob
from app.scheduler.jobs.collect_metrics import CollectMetricsJob
from app.scheduler.jobs.recalculate_opportunities import RecalculateOpportunitiesJob
from app.scheduler.jobs.translate_keywords import TranslateKeywordsJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


async def _run_pipeline() -> None:
    """Run the four jobs sequentially in one session per job."""
    steps = [
        ("collect_keywords", CollectKeywordsJob()),
        ("translate_keywords", TranslateKeywordsJob()),
        ("collect_metrics", CollectMetricsJob()),
        ("recalculate_opportunities", RecalculateOpportunitiesJob()),
    ]
    for name, job in steps:
        try:
            with SessionLocal() as session:
                result = await job.run(session)
            logger.info("admin pipeline: %s → %s", name, result)
        except Exception:
            logger.exception("admin pipeline: %s failed", name)
            return  # stop the chain; later steps need earlier ones


@router.post(
    "/expand",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run collect_keywords → metrics → opportunities in the background",
)
async def expand_and_recalculate(background: BackgroundTasks) -> dict[str, str]:
    background.add_task(_run_pipeline)
    return {
        "status": "accepted",
        "message": "키워드 확장 + 메트릭 수집 + 기회 점수 재계산이 시작되었습니다. 2~3분 후 새로고침하세요.",
    }
