"""Keyword (검색 키워드) model."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .category import Category
    from .keyword_hs_mapping import KeywordHsMapping
    from .keyword_metric import KeywordMetric
    from .opportunity_score import OpportunityScore
    from .product import Product


class KeywordStatus(str, enum.Enum):
    """Lifecycle state of a keyword in the discovery pipeline."""

    PENDING = "pending"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    EXCLUDED = "excluded"


class Keyword(Base, TimestampMixin):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Simplified-Chinese translation used to build 1688 search URLs
    # (1688 decodes ``keywords=`` as GBK, so Korean UTF-8 bytes get
    # mojibaked).
    chinese_term: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_seed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[KeywordStatus] = mapped_column(
        SAEnum(KeywordStatus, name="keyword_status"),
        nullable=False,
        default=KeywordStatus.PENDING,
        server_default=KeywordStatus.PENDING.value,
    )
    last_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    category: Mapped["Category | None"] = relationship(
        "Category", back_populates="keywords"
    )
    metrics: Mapped[list["KeywordMetric"]] = relationship(
        "KeywordMetric",
        back_populates="keyword",
        cascade="all, delete-orphan",
    )
    opportunity_scores: Mapped[list["OpportunityScore"]] = relationship(
        "OpportunityScore",
        back_populates="keyword",
        cascade="all, delete-orphan",
    )
    hs_mappings: Mapped[list["KeywordHsMapping"]] = relationship(
        "KeywordHsMapping",
        back_populates="keyword",
        cascade="all, delete-orphan",
    )
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="keyword"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Keyword id={self.id} term={self.term!r}>"
