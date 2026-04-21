"""``/feedback`` router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.deps import DbSession
from app.schemas.requests.feedback import FeedbackCreateRequest
from app.schemas.responses.feedback import FeedbackResponse
from app.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit 60-day actual sales feedback",
)
def submit_feedback(
    request: FeedbackCreateRequest, db: DbSession
) -> FeedbackResponse:
    try:
        return feedback_service.create_feedback(db, request)
    except feedback_service.FeedbackProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
