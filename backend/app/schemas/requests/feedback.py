"""Request body for ``POST /feedback``."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreateRequest(BaseModel):
    """60-day sales feedback (spec §6.3).

    All numeric fields are optional because the user might leave a
    "did not purchase" note without sales numbers.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(..., ge=1, description="Target product id.")
    purchased: bool = Field(
        default=False,
        description="Did the user actually source the product?",
    )
    monthly_sales: int | None = Field(
        default=None,
        ge=0,
        description="Units sold per month after launch.",
    )
    actual_revenue: float | None = Field(
        default=None,
        ge=0,
        description="Realised KRW revenue (sum across channels).",
    )
    notes: str | None = Field(
        default=None,
        description="Free-form notes about the outcome.",
    )
