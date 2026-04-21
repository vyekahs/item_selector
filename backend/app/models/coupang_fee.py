"""Coupang category-level commission fee table (spec §9)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CoupangFee(Base, TimestampMixin):
    __tablename__ = "coupang_fees"
    __table_args__ = (
        UniqueConstraint(
            "category_path",
            "effective_from",
            name="coupang_fee_unique_category_period",
        ),
        Index("ix_coupang_fees_effective_from", "effective_from"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_path: Mapped[str] = mapped_column(String(255), nullable=False)
    fee_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
