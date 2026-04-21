"""Exchange rate cache (한국수출입은행 API)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ExchangeRate(Base, TimestampMixin):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        Index(
            "ix_exchange_rates_pair_fetched_at",
            "currency_pair",
            "fetched_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # E.g. 'CNY/KRW'
    currency_pair: Mapped[str] = mapped_column(String(10), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(14, 6), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
