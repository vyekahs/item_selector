"""Response schemas for ``GET /categories``."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CategoryNode(BaseModel):
    """Single node in the category tree."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    parent_id: int | None = None
    is_certification_required: bool = False
    children: list["CategoryNode"] = Field(default_factory=list)


CategoryNode.model_rebuild()


class CategoryResponse(BaseModel):
    """Top-level wrapper for the category tree."""

    model_config = ConfigDict(extra="forbid")

    roots: list[CategoryNode] = Field(default_factory=list)
