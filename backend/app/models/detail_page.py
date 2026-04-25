"""Detail page — Korean-localized e-commerce detail page generated from a SourceProduct.

The pipeline is asynchronous: an ingest call inserts a row with
``status='pending'``; a background task transitions it through
``processing`` to either ``done`` (with ``image_path`` populated) or
``failed`` (with ``failure_reason`` populated).

Allowed values for ``status``:
    - ``pending``    — row created, awaiting background pickup
    - ``processing`` — pipeline running (LLM, image download, render)
    - ``done``       — JPG written to ``/app/generated/{id}/page.jpg``
    - ``failed``     — pipeline raised; see ``failure_reason``
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .source_product import SourceProduct


class DetailPage(Base, TimestampMixin):
    __tablename__ = "detail_pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("source_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending | processing | done | failed",
    )
    title_ko: Mapped[str | None] = mapped_column(String(200), nullable=True)
    props: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_product: Mapped["SourceProduct"] = relationship(
        "SourceProduct", back_populates="detail_pages"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DetailPage id={self.id} status={self.status!r} "
            f"source_product_id={self.source_product_id}>"
        )
