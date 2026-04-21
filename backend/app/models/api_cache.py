"""External API response cache (e.g. 24h Coupang Partners cache).

Used by Data Collection Agent to satisfy the 1-hour rate limits
described in spec §3.4.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ApiCache(Base, TimestampMixin):
    __tablename__ = "api_cache"
    __table_args__ = (
        # Unique cache key index is implicit via `unique=True`, but
        # naming it explicitly so the expiry-sweep job can also use it.
        Index("ix_api_cache_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
