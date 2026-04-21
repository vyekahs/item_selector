"""``/categories`` router."""
from __future__ import annotations

from fastapi import APIRouter

from app.deps import DbSession
from app.schemas.responses.category import CategoryResponse
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(
    "",
    response_model=CategoryResponse,
    summary="Category tree",
)
def get_categories(db: DbSession) -> CategoryResponse:
    return category_service.get_category_tree(db)
