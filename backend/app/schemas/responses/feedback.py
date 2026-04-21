"""Response schema for ``POST /feedback``."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    product_id: int
    purchased: bool
    monthly_sales: int | None = None
    actual_revenue: float | None = None
    notes: str | None = None
    recorded_at: datetime
