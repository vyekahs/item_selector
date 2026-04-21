"""Composite product score (spec §5.3) and GO/CONDITIONAL/PASS verdict."""
from __future__ import annotations

import enum
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .channel_profit import ChannelProfit
    from .product import Product


class Recommendation(str, enum.Enum):
    GO = "GO"
    CONDITIONAL = "CONDITIONAL"
    PASS = "PASS"


class ProductScore(Base, TimestampMixin):
    __tablename__ = "product_scores"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "snapshot_date",
            name="product_score_unique_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    opportunity_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    profit_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    risk_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    stability_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    recommendation: Mapped[Recommendation] = mapped_column(
        SAEnum(Recommendation, name="product_recommendation"),
        nullable=False,
    )

    product: Mapped["Product"] = relationship("Product", back_populates="scores")
    channel_profits: Mapped[list["ChannelProfit"]] = relationship(
        "ChannelProfit",
        back_populates="product_score",
        cascade="all, delete-orphan",
    )
