"""Category (카테고리) model.

Self-referential hierarchy. ``is_certification_required`` feeds the
자동 제외 필터 (spec §4.3).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .hs_code import HsCode
    from .keyword import Keyword


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_certification_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ---- relationships ----
    parent: Mapped["Category | None"] = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
    )
    children: Mapped[list["Category"]] = relationship(
        "Category",
        back_populates="parent",
        cascade="all",
    )
    hs_codes: Mapped[list["HsCode"]] = relationship(
        "HsCode", back_populates="category"
    )
    keywords: Mapped[list["Keyword"]] = relationship(
        "Keyword", back_populates="category"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category id={self.id} name={self.name!r}>"
