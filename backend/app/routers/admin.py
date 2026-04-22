"""``/admin`` router — manual job triggers.

Guarded by the external Caddy basic-auth layer. Kicks off the full
``collect_keywords → collect_metrics → recalculate_opportunities``
pipeline on a detached asyncio task so the caller gets a 202 back in
milliseconds while the 3–5 min pipeline runs in the event loop.

Why ``asyncio.create_task`` instead of FastAPI ``BackgroundTasks``:
BackgroundTasks were producing no observable effect in this setup —
the 202 landed, the DB never changed, and no logs appeared. Scheduling
the task directly on the running event loop sidesteps that and also
lets us keep a module-level handle to the in-flight task (for status
polling later).
"""
from __future__ import annotations

import asyncio
import logging
import sys

from fastapi import APIRouter, HTTPException, status

from app.db.session import SessionLocal
from app.scheduler.jobs.collect_keywords import CollectKeywordsJob
from app.scheduler.jobs.collect_metrics import CollectMetricsJob
from app.scheduler.jobs.recalculate_opportunities import RecalculateOpportunitiesJob
from app.scheduler.jobs.translate_keywords import TranslateKeywordsJob

# Ensure ``logger.info`` reaches docker logs even if uvicorn didn't
# configure the ``app.*`` logger tree. Idempotent: repeat calls only
# attach a handler when the root logger has none.
logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=False)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/admin", tags=["admin"])

# At most one pipeline in flight. Prevents overlapping runs if the user
# hammers the button or the UI retries.
_running_task: asyncio.Task | None = None


async def _run_pipeline() -> None:
    """Run the four jobs sequentially, each with its own DB session."""
    steps = [
        ("collect_keywords", CollectKeywordsJob()),
        ("translate_keywords", TranslateKeywordsJob()),
        ("collect_metrics", CollectMetricsJob()),
        ("recalculate_opportunities", RecalculateOpportunitiesJob()),
    ]
    logger.info("admin pipeline: starting")
    for name, job in steps:
        try:
            with SessionLocal() as session:
                result = await job.run(session)
            logger.info("admin pipeline: %s → %s", name, result)
        except Exception:
            logger.exception("admin pipeline: %s failed", name)
            return
    logger.info("admin pipeline: done")


@router.post(
    "/expand",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run collect_keywords → metrics → opportunities in the background",
)
async def expand_and_recalculate() -> dict[str, str]:
    global _running_task
    if _running_task is not None and not _running_task.done():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 실행 중입니다. 2~3분 후 다시 시도하세요.",
        )
    _running_task = asyncio.create_task(_run_pipeline())
    return {
        "status": "accepted",
        "message": "키워드 확장 + 메트릭 수집 + 기회 점수 재계산이 시작되었습니다. 2~3분 후 새로고침하세요.",
    }
