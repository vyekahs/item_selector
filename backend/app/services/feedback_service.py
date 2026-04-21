"""Feedback service (60-day actual sales report)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Feedback, Product
from app.schemas.requests.feedback import FeedbackCreateRequest
from app.schemas.responses.feedback import FeedbackResponse


class FeedbackServiceError(RuntimeError):
    """Base for feedback-service errors."""


class FeedbackProductNotFoundError(FeedbackServiceError):
    pass


def create_feedback(
    session: Session, request: FeedbackCreateRequest
) -> FeedbackResponse:
    """Persist a feedback entry, validating the product exists."""
    exists = session.execute(
        select(Product.id).where(Product.id == request.product_id).limit(1)
    ).scalar_one_or_none()
    if exists is None:
        raise FeedbackProductNotFoundError(
            f"product id={request.product_id} not found"
        )

    row = Feedback(
        product_id=request.product_id,
        purchased=request.purchased,
        monthly_sales=request.monthly_sales,
        actual_revenue=request.actual_revenue,
        notes=request.notes,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    return FeedbackResponse(
        id=row.id,
        product_id=row.product_id,
        purchased=bool(row.purchased),
        monthly_sales=row.monthly_sales,
        actual_revenue=float(row.actual_revenue) if row.actual_revenue is not None else None,
        notes=row.notes,
        recorded_at=row.recorded_at,
    )
