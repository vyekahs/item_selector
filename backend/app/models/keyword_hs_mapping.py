"""Keyword ↔ HS code many-to-many mapping with confidence."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .hs_code import HsCode
    from .keyword import Keyword


class KeywordHsMapping(Base, TimestampMixin):
    __tablename__ = "keyword_hs_mappings"
    __table_args__ = (
        UniqueConstraint("keyword_id", "hs_code", name="keyword_hs_unique"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_between_0_and_1",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hs_code: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("hs_codes.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=0.0, server_default="0.0"
    )
    is_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="hs_mappings")
    hs_code_ref: Mapped["HsCode"] = relationship(
        "HsCode", back_populates="keyword_mappings"
    )
