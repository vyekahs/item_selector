"""``/keywords`` router.

Currently exposes a single ``POST /keywords/seed`` endpoint for adding
a new seed keyword. The term is auto-classified into an internal
category by looking up Naver shopping results.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DbSession
from app.models import Category, Keyword, KeywordStatus
from app.services.categorize import DEFAULT_CATEGORY, infer_category_name

router = APIRouter(prefix="/keywords", tags=["keywords"])


class SeedCreateRequest(BaseModel):
    term: str = Field(..., min_length=1, max_length=255)


class SeedResponse(BaseModel):
    id: int
    term: str
    category_id: int | None
    category_name: str | None
    status: str
    is_seed: bool


@router.post(
    "/seed",
    response_model=SeedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a seed keyword with auto-detected category",
)
async def create_seed(request: SeedCreateRequest, db: DbSession) -> SeedResponse:
    term = request.term.strip()
    if not term:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="term empty"
        )

    # Auto-classify via Naver shopping top-10 category tally.
    category_name = await infer_category_name(term)

    # Resolve Category row (upsert — default category should exist from seed.py).
    category = db.execute(
        select(Category).where(Category.name == category_name)
    ).scalar_one_or_none()
    if category is None:
        # Seed.py normally pre-creates all names; if somehow missing, create on the fly.
        category = Category(name=category_name, parent_id=None)
        db.add(category)
        db.flush()

    # Upsert keyword — promote existing row to seed if present.
    keyword = db.execute(
        select(Keyword).where(Keyword.term == term)
    ).scalar_one_or_none()
    if keyword is None:
        keyword = Keyword(
            term=term,
            is_seed=True,
            status=KeywordStatus.ACTIVE,
            category_id=category.id,
        )
        db.add(keyword)
    else:
        keyword.is_seed = True
        keyword.status = KeywordStatus.ACTIVE
        keyword.category_id = category.id
    db.commit()
    db.refresh(keyword)

    return SeedResponse(
        id=keyword.id,
        term=keyword.term,
        category_id=keyword.category_id,
        category_name=category.name,
        status=keyword.status.value,
        is_seed=keyword.is_seed,
    )
