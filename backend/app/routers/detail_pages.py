"""``/detail-pages/*`` router — detail-page generator API.

Receives raw payloads from the Chrome Extension (or Frontend manual
form), persists ``SourceProduct`` + ``DetailPage(status='pending')``,
and schedules a background pipeline that downloads images, runs LLM
copywriting, and renders the final JPG.

Why ``asyncio.create_task`` (mirroring ``app.routers.admin``):
FastAPI ``BackgroundTasks`` were observed to silently no-op in this
deployment; scheduling on the running event loop sidesteps that and
also lets us hold a module-level handle if we later add status polling.

Module C (``app.services.detail_pages``) is not yet wired in. This file
deliberately uses a local ``_process_stub`` so the router can ship and
be tested in isolation; replacing the stub with the real pipeline call
is the only surface change needed once Module C lands.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, func, select

from app.deps import DbSession
from app.models import DetailPage, SourceProduct
from app.schemas.requests.detail_page import IngestRequest
from app.schemas.responses.detail_page import (
    DetailPageDetail,
    DetailPageSummary,
    IngestAcceptedResponse,
    PaginatedDetailPagesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/detail-pages", tags=["detail-pages"])


# ---------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------
from app.services.detail_pages.ingest import process_detail_page


def _schedule_processing(detail_page_id: int) -> None:
    """Detach the pipeline coroutine from the request lifecycle."""
    asyncio.create_task(process_detail_page(detail_page_id))


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------


@router.post(
    "/ingest",
    response_model=IngestAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a 1688/Taobao scrape and queue background generation",
)
async def ingest(payload: IngestRequest, db: DbSession) -> IngestAcceptedResponse:
    """Persist source payload + create a ``pending`` detail page.

    ``SourceProduct`` is upserted on ``source_url`` so re-ingesting the
    same product (e.g. user clicks the extension button twice) reuses
    the existing source row but always creates a fresh ``DetailPage``
    so each generation attempt is independently trackable.
    """
    source_url = str(payload.source_url)

    source = db.execute(
        select(SourceProduct).where(SourceProduct.source_url == source_url)
    ).scalar_one_or_none()

    raw_payload = payload.model_dump(mode="json")

    if source is None:
        source = SourceProduct(
            source_url=source_url,
            source_platform=payload.source_platform,
            raw_payload=raw_payload,
        )
        db.add(source)
        db.flush()  # populate source.id
    else:
        # Refresh raw payload so re-ingest captures any DOM changes,
        # but keep the original row id to preserve FK relationships.
        source.raw_payload = raw_payload
        source.source_platform = payload.source_platform

    detail_page = DetailPage(
        source_product_id=source.id,
        status="pending",
    )
    db.add(detail_page)
    db.commit()
    db.refresh(detail_page)

    _schedule_processing(detail_page.id)

    return IngestAcceptedResponse(
        id=detail_page.id,
        status="pending",
        message="상세페이지 생성이 시작되었습니다. 잠시 후 결과를 확인하세요.",
    )


@router.get(
    "",
    response_model=PaginatedDetailPagesResponse,
    summary="List detail pages (newest first), optional status filter",
)
def list_detail_pages(
    db: DbSession,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="pending | processing | done | failed.",
    ),
) -> PaginatedDetailPagesResponse:
    base_stmt = (
        select(DetailPage, SourceProduct)
        .join(SourceProduct, DetailPage.source_product_id == SourceProduct.id)
    )
    count_stmt = select(func.count()).select_from(DetailPage)

    if status_filter is not None:
        base_stmt = base_stmt.where(DetailPage.status == status_filter)
        count_stmt = count_stmt.where(DetailPage.status == status_filter)

    rows = db.execute(
        base_stmt.order_by(desc(DetailPage.created_at)).limit(limit).offset(offset)
    ).all()
    total = db.execute(count_stmt).scalar_one()

    items = [
        DetailPageSummary(
            id=dp.id,
            status=dp.status,
            title_ko=dp.title_ko,
            image_path=dp.image_path,
            source_url=sp.source_url,
            source_platform=sp.source_platform,
            created_at=dp.created_at,
        )
        for dp, sp in rows
    ]
    return PaginatedDetailPagesResponse(
        items=items, total=int(total), limit=limit, offset=offset
    )


@router.get(
    "/{detail_page_id}",
    response_model=DetailPageDetail,
    summary="Fetch a single detail page (full props + failure reason)",
)
def get_detail_page(detail_page_id: int, db: DbSession) -> DetailPageDetail:
    row = db.execute(
        select(DetailPage, SourceProduct)
        .join(SourceProduct, DetailPage.source_product_id == SourceProduct.id)
        .where(DetailPage.id == detail_page_id)
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"detail page {detail_page_id} not found",
        )
    dp, sp = row
    return DetailPageDetail(
        id=dp.id,
        status=dp.status,
        title_ko=dp.title_ko,
        image_path=dp.image_path,
        source_url=sp.source_url,
        source_platform=sp.source_platform,
        created_at=dp.created_at,
        props=dp.props,
        failure_reason=dp.failure_reason,
    )


@router.post(
    "/{detail_page_id}/regenerate",
    response_model=IngestAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reset a detail page to pending and re-run the pipeline",
)
async def regenerate(
    detail_page_id: int, db: DbSession
) -> IngestAcceptedResponse:
    detail_page = db.execute(
        select(DetailPage).where(DetailPage.id == detail_page_id)
    ).scalar_one_or_none()
    if detail_page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"detail page {detail_page_id} not found",
        )

    detail_page.status = "pending"
    detail_page.image_path = None
    detail_page.failure_reason = None
    detail_page.props = None
    db.commit()

    _schedule_processing(detail_page.id)

    return IngestAcceptedResponse(
        id=detail_page.id,
        status="pending",
        message="상세페이지 재생성이 시작되었습니다.",
    )
