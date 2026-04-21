"""Per-channel profit calculation (스마트스토어 / 쿠팡)."""
from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .product_score import ProductScore


class Channel(str, enum.Enum):
    SMARTSTORE = "SMARTSTORE"
    COUPANG = "COUPANG"


class ChannelProfit(Base, TimestampMixin):
    __tablename__ = "channel_profits"
    __table_args__ = (
        UniqueConstraint(
            "product_score_id",
            "channel",
            name="channel_profit_unique_per_score_channel",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_score_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product_scores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[Channel] = mapped_column(
        SAEnum(Channel, name="sales_channel"), nullable=False
    )

    unit_cost_krw: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    expected_price_krw: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    platform_fee_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    ad_cost_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    unit_profit_krw: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    margin_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    roi_pct: Mapped[float] = mapped_column(Numeric(7, 3), nullable=False)
    breakeven_units: Mapped[int] = mapped_column(Integer, nullable=False)

    product_score: Mapped["ProductScore"] = relationship(
        "ProductScore", back_populates="channel_profits"
    )
