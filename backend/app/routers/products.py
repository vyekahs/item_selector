"""``/products`` router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import DbSession
from app.schemas.requests.product import ProductCreateRequest, ProductUpdateRequest
from app.schemas.responses.product import (
    PaginatedProductsResponse,
    ProductDetailResponse,
    ProductScoreResponse,
)
from app.services import product_service

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "",
    response_model=ProductScoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a 1688 product for scoring",
)
def create_product(request: ProductCreateRequest, db: DbSession) -> ProductScoreResponse:
    try:
        return product_service.create_product_and_score(db, request)
    except product_service.DuplicateProductError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except product_service.ScoringUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Product detail with score history",
)
def get_product(product_id: int, db: DbSession) -> ProductDetailResponse:
    try:
        return product_service.get_product_detail(db, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch(
    "/{product_id}",
    response_model=ProductScoreResponse,
    summary="Adjust cost parameters and rescore",
)
def update_product_costs(
    product_id: int,
    request: ProductUpdateRequest,
    db: DbSession,
) -> ProductScoreResponse:
    """MOQ / 중국 국내 배송비 / 국제 배송비를 수정하면 즉시 재스코어링."""
    try:
        return product_service.update_product_costs(db, product_id, request)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except product_service.ScoringUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )


@router.get(
    "",
    response_model=PaginatedProductsResponse,
    summary="List user-submitted products (paginated)",
)
def list_products(
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    keyword_id: int | None = Query(default=None, ge=1),
) -> PaginatedProductsResponse:
    return product_service.list_products(
        db, limit=limit, offset=offset, keyword_id=keyword_id
    )
