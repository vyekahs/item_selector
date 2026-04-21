"""Time-series snapshot of per-keyword metrics."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .keyword import Keyword


class KeywordMetric(Base, TimestampMixin):
    __tablename__ = "keyword_metrics"
    __table_args__ = (
        UniqueConstraint(
            "keyword_id", "snapshot_date", name="keyword_metric_unique_snapshot"
        ),
        Index(
            "ix_keyword_metrics_keyword_id_snapshot_date",
            "keyword_id",
            "snapshot_date",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    monthly_search_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    competition_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    naver_shopping_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shopping_avg_price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blog_post_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    youtube_video_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    growth_rate_3m: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    growth_rate_6m: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="metrics")
