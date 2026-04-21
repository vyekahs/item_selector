"""``/opportunities`` router -- daily TOP-N keyword list."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import DbSession
from app.schemas.responses.opportunity import OpportunityResponse
from app.services import opportunity_service

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get(
    "",
    response_model=list[OpportunityResponse],
    summary="Top opportunity keywords",
    description=(
        "Returns the latest snapshot per keyword, sorted by total_score desc. "
        "Excluded keywords are hidden by default; pass ``include_excluded=true`` "
        "to inspect them."
    ),
)
def list_opportunities(
    db: DbSession,
    category_id: int | None = Query(
        default=None, ge=1, description="Filter by category id."
    ),
    limit: int = Query(default=20, ge=1, le=100),
    min_score: float = Query(
        default=0.0, ge=0, le=100, description="Inclusive lower bound on total_score."
    ),
    include_excluded: bool = Query(
        default=False,
        description="Include keywords flagged by the auto-exclusion filter.",
    ),
) -> list[OpportunityResponse]:
    return opportunity_service.get_top_opportunities(
        db,
        category_id=category_id,
        limit=limit,
        min_score=min_score,
        include_excluded=include_excluded,
    )
