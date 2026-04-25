"""Source product — raw payload captured from a 1688/Taobao detail page.

Populated by the Chrome Extension via ``POST /detail-pages/ingest``.
The ``raw_payload`` JSONB blob preserves the entire scraped record
(title, price, specs, image URLs, options) so that downstream
processing (LLM copywriting, image rendering) can be re-run later
without re-scraping the original page.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .detail_page import DetailPage


class SourceProduct(Base, TimestampMixin):
    __tablename__ = "source_products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_url: Mapped[str] = mapped_column(
        String(2048), nullable=False, unique=True
    )
    source_platform: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="'1688' or 'taobao'"
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    detail_pages: Mapped[list["DetailPage"]] = relationship(
        "DetailPage",
        back_populates="source_product",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SourceProduct id={self.id} platform={self.source_platform!r} "
            f"url={self.source_url!r}>"
        )
