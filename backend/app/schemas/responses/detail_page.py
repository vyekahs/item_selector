"""Response schemas for ``/detail-pages/*`` endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DetailPageSummary(BaseModel):
    """List-row projection of a ``DetailPage``.

    Lightweight fields only — heavy ``props`` JSON is fetched per-detail
    via :class:`DetailPageDetail`.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    status: str = Field(..., description="pending | processing | done | failed.")
    title_ko: str | None = Field(
        default=None, description="LLM 생성 한국어 제목 (가공 완료 후 채워짐)."
    )
    image_path: str | None = Field(
        default=None,
        description="최종 JPG 상대경로 (예: '42/page.jpg'). 'done'일 때만 존재.",
    )
    source_url: str
    source_platform: str
    template_name: str = Field(
        ...,
        description="이 row가 사용한 Jinja2 템플릿 파일명.",
    )
    created_at: datetime


class DetailPageDetail(DetailPageSummary):
    """Single-row projection — adds renderer payload + failure reason."""

    props: dict[str, Any] | None = Field(
        default=None,
        description="템플릿 바인딩 dict (AIDA, spec_table, image paths 등).",
    )
    failure_reason: str | None = Field(
        default=None,
        description="status='failed'일 때 원인 메시지.",
    )


class PaginatedDetailPagesResponse(BaseModel):
    """Paginated list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[DetailPageSummary]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=200)
    offset: int = Field(..., ge=0)


class DetailPageTemplateOption(BaseModel):
    """One pickable template entry exposed via ``GET /detail-pages/templates``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="템플릿 파일명 (예: 'detail_page_v2_minimal.html').")
    label: str = Field(..., description="UI 표시용 짧은 한국어 라벨.")
    description: str = Field(..., description="UI 표시용 한 줄 설명.")


class IngestAcceptedResponse(BaseModel):
    """202 response for ingest + regenerate.

    The actual JPG is not ready yet — the client should poll
    ``GET /detail-pages/{id}`` until ``status`` is ``done`` or ``failed``.
    """

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., description="DetailPage row id.")
    status: str = Field(default="pending")
    message: str
