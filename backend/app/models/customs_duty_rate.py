"""관세청 품목번호별 관세율 (기본 + 한-중 FTA)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CustomsDutyRate(Base, TimestampMixin):
    __tablename__ = "customs_duty_rates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hs_code: Mapped[str] = mapped_column(
        String(10), nullable=False, unique=True, index=True
    )
    base_duty_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    kcfta_duty_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    effective_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CustomsDutyRate hs={self.hs_code} "
            f"base={self.base_duty_pct} fta={self.kcfta_duty_pct}>"
        )
