"""HS code (관세청 HS부호) model.

``code`` holds the 6 or 10 digit HS code as a string (leading zeroes
must be preserved).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .category import Category
    from .import_stat import ImportStat
    from .keyword_hs_mapping import KeywordHsMapping


class HsCode(Base, TimestampMixin):
    __tablename__ = "hs_codes"
    __table_args__ = (
        CheckConstraint(
            "length(code) IN (6, 10)",
            name="code_length_6_or_10",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    name_ko: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    category: Mapped["Category | None"] = relationship(
        "Category", back_populates="hs_codes"
    )
    import_stats: Mapped[list["ImportStat"]] = relationship(
        "ImportStat", back_populates="hs_code_ref"
    )
    keyword_mappings: Mapped[list["KeywordHsMapping"]] = relationship(
        "KeywordHsMapping", back_populates="hs_code_ref"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HsCode code={self.code} name_ko={self.name_ko!r}>"
