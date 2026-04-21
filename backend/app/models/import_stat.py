"""Monthly import statistics by HS code (관세청 수출입실적)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .hs_code import HsCode


class ImportStat(Base, TimestampMixin):
    __tablename__ = "import_stats"
    __table_args__ = (
        UniqueConstraint(
            "hs_code",
            "year_month",
            "country_code",
            name="import_stat_unique_period",
        ),
        Index(
            "ix_import_stats_hs_code_year_month",
            "hs_code",
            "year_month",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hs_code: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("hs_codes.code", ondelete="CASCADE"),
        nullable=False,
    )
    # YYYY-MM (always 7 chars). Stored as string for portability with the
    # 관세청 API which returns 'YYYYMM'.
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="CN", server_default="CN"
    )
    import_quantity: Mapped[float | None] = mapped_column(Numeric(20, 3), nullable=True)
    import_value_usd: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)

    hs_code_ref: Mapped["HsCode"] = relationship(
        "HsCode", back_populates="import_stats"
    )
