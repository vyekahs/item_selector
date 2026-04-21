"""Common error envelope used by exception handlers."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str = Field(..., description="Human-readable error message.")
    code: str | None = Field(
        default=None,
        description="Machine-readable error code (e.g. 'rate_limited', 'not_found').",
    )
