"""Seed candidate — auto-discovered keyword waiting for operator approval."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SeedCandidate(Base, TimestampMixin):
    __tablename__ = "seed_candidates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hs_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    import_value_krw_3m: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    import_growth_3m_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    avg_unit_price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_search_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    search_growth_3m_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    combined_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_refreshed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=dt.datetime.utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SeedCandidate id={self.id} term={self.term!r} score={self.combined_score}>"
