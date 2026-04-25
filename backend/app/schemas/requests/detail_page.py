"""Request schemas for ``/detail-pages/*`` endpoints.

The Chrome Extension scrapes a 1688/Taobao detail page and POSTs the
raw payload here. ``IngestRequest`` is the contract enforced at that
boundary — every field downstream (``services/detail_pages``,
``templates/detail_page_v1.html``) consumes data shaped exactly by this
model so renaming a field here is a breaking change for both the
extension and the renderer.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class OptionImage(BaseModel):
    """One option/variant thumbnail (e.g. color/size swatch)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="옵션 이름 (예: 'Red', 'M').")
    url: str = Field(..., description="옵션 이미지 URL.")


class IngestRequest(BaseModel):
    """Raw scrape payload from the Chrome Extension.

    Stored verbatim in ``source_products.raw_payload`` so the pipeline
    can be re-run later without re-scraping the original page.
    """

    model_config = ConfigDict(extra="forbid")

    source_url: HttpUrl = Field(
        ...,
        max_length=2048,
        description="1688/타오바오 상품 상세 페이지 URL.",
    )
    source_platform: Literal["1688", "taobao"] = Field(
        ...,
        description="원본 플랫폼.",
    )
    title_zh: str = Field(..., description="중국어 원제목.")
    price_cny: float | None = Field(
        default=None,
        ge=0,
        description="단가 (CNY). 표기 없으면 None.",
    )
    category_path: list[str] = Field(
        default_factory=list,
        description="카테고리 breadcrumb (가장 상위 → 하위 순).",
    )
    specs: dict[str, str] = Field(
        default_factory=dict,
        description="스펙 표 (예: {'무게': '0.5kg', '사이즈': 'M/L'}).",
    )
    main_images: list[str] = Field(
        ...,
        description="메인 이미지 URL 리스트 (캐러셀).",
    )
    detail_images: list[str] = Field(
        default_factory=list,
        description="상세설명 이미지 URL 리스트 (중국어 포함 가능).",
    )
    option_images: list[OptionImage] = Field(
        default_factory=list,
        description="옵션/변형 썸네일 (색상, 사이즈 등).",
    )
