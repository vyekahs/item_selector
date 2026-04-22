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

import datetime as dt

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.deps import DbSession
from app.db.session import SessionLocal
from app.models import Keyword, KeywordStatus, SeedCandidate
from app.scheduler.jobs.collect_keywords import CollectKeywordsJob
from app.scheduler.jobs.collect_metrics import CollectMetricsJob
from app.scheduler.jobs.recalculate_opportunities import RecalculateOpportunitiesJob
from app.scheduler.jobs.translate_keywords import TranslateKeywordsJob
from app.services import discover_seeds
from app.services.categorize import infer_category_name
from app.models import Category

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


# ---------------------------------------------------------------------
# Seed discovery + approval
# ---------------------------------------------------------------------


_discover_task: asyncio.Task | None = None


class SeedCandidateOut(BaseModel):
    id: int
    term: str
    hs_code: str | None
    import_value_krw_3m: int | None
    import_growth_3m_pct: float | None
    avg_unit_price_krw: int | None
    monthly_search_volume: int | None
    combined_score: float
    is_approved: bool


class ApproveRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=200)


async def _run_discover() -> None:
    logger.info("discover_seeds: starting")
    try:
        with SessionLocal() as session:
            result = await discover_seeds.run(session)
        logger.info("discover_seeds: done → %s", result)
    except Exception:
        logger.exception("discover_seeds: failed")


@router.post(
    "/discover-seeds",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Mine 관세청 imports + Naver signals → populate seed_candidates",
)
async def discover_seeds_endpoint() -> dict[str, str]:
    global _discover_task
    if _discover_task is not None and not _discover_task.done():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 실행 중입니다. 5~30분 후 다시 시도하세요.",
        )
    _discover_task = asyncio.create_task(_run_discover())
    return {
        "status": "accepted",
        "message": "시드 후보 발굴이 시작되었습니다. 5~30분 후 추천 목록을 확인하세요.",
    }


@router.get(
    "/seed-candidates",
    response_model=list[SeedCandidateOut],
    summary="List pending seed candidates, highest combined_score first",
)
def list_candidates(
    db: DbSession, limit: int = 50, include_approved: bool = False
) -> list[SeedCandidateOut]:
    stmt = select(SeedCandidate).order_by(desc(SeedCandidate.combined_score))
    if not include_approved:
        stmt = stmt.where(SeedCandidate.is_approved.is_(False))
    stmt = stmt.limit(max(1, min(limit, 200)))
    rows = db.execute(stmt).scalars().all()
    return [
        SeedCandidateOut(
            id=r.id,
            term=r.term,
            hs_code=r.hs_code,
            import_value_krw_3m=r.import_value_krw_3m,
            import_growth_3m_pct=(
                float(r.import_growth_3m_pct)
                if r.import_growth_3m_pct is not None
                else None
            ),
            avg_unit_price_krw=r.avg_unit_price_krw,
            monthly_search_volume=r.monthly_search_volume,
            combined_score=float(r.combined_score),
            is_approved=r.is_approved,
        )
        for r in rows
    ]


@router.post(
    "/seed-candidates/approve",
    summary="Promote selected candidates to keywords(is_seed=True)",
)
async def approve_candidates(
    request: ApproveRequest, db: DbSession
) -> dict[str, int]:
    candidates = db.execute(
        select(SeedCandidate).where(SeedCandidate.id.in_(request.ids))
    ).scalars().all()
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no matching candidates"
        )

    promoted = 0
    for cand in candidates:
        if cand.is_approved:
            continue
        # Auto-categorize via Naver shopping lookup.
        category_name = await infer_category_name(cand.term)
        category = db.execute(
            select(Category).where(Category.name == category_name)
        ).scalar_one_or_none()
        if category is None:
            category = Category(name=category_name, parent_id=None)
            db.add(category)
            db.flush()

        # Upsert keyword.
        kw = db.execute(
            select(Keyword).where(Keyword.term == cand.term)
        ).scalar_one_or_none()
        if kw is None:
            kw = Keyword(
                term=cand.term,
                is_seed=True,
                status=KeywordStatus.ACTIVE,
                category_id=category.id,
            )
            db.add(kw)
        else:
            kw.is_seed = True
            kw.status = KeywordStatus.ACTIVE
            kw.category_id = category.id

        cand.is_approved = True
        cand.approved_at = dt.datetime.utcnow()
        promoted += 1

    db.commit()
    return {"promoted": promoted, "requested": len(request.ids)}
