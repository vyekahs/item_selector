"""Snapshot of the opportunity score for a keyword (spec §4.2)."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .keyword import Keyword


class OpportunityScore(Base, TimestampMixin):
    __tablename__ = "opportunity_scores"
    __table_args__ = (
        UniqueConstraint(
            "keyword_id",
            "snapshot_date",
            name="opportunity_score_unique_snapshot",
        ),
        # Critical for "TOP N for date" queries.
        Index(
            "ix_opportunity_scores_snapshot_date_total_score",
            "snapshot_date",
            "total_score",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    demand_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    growth_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    competition_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    customs_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    trend_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    stability_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    is_excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    exclusion_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-axis scorer breakdown (raw inputs + norms), surfaced to the UI
    # so users can see *why* each sub-score came out as it did.
    details: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    keyword: Mapped["Keyword"] = relationship(
        "Keyword", back_populates="opportunity_scores"
    )
