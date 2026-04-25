"""itemSelector FastAPI application.

Wires routers, exception handlers and CORS so other agents (Frontend,
Scheduler) can talk to the API. Per spec §8, this service runs in
docker-compose alongside ``web``, ``collector``, ``scheduler``,
``postgres``, ``redis`` and ``nginx``.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.routers import (
    admin,
    calculator,
    categories,
    detail_pages,
    feedback,
    keywords,
    opportunities,
    products,
)
from app.schemas.responses.error import ErrorResponse
from app.services.feedback_service import FeedbackProductNotFoundError
from app.services.product_service import (
    DuplicateProductError,
    ProductNotFoundError,
    ScoringUnavailableError,
)


tags_metadata = [
    {"name": "health", "description": "Liveness/readiness probes."},
    {
        "name": "opportunities",
        "description": "Daily opportunity-keyword discovery (spec §6.1).",
    },
    {
        "name": "products",
        "description": "User-submitted 1688 products + 2-channel scoring (spec §6.2).",
    },
    {
        "name": "feedback",
        "description": "60-day actual sales feedback (spec §6.3).",
    },
    {"name": "categories", "description": "Category tree for filters."},
]


app = FastAPI(
    title="itemSelector API",
    version="0.1.0",
    description=(
        "Backend API for the China-sourcing opportunity discovery tool "
        "(see 기획서.md §6 for the user-facing flows)."
    ),
    openapi_tags=tags_metadata,
)


# CORS -- permissive in dev, tightened in nginx for prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------


@app.exception_handler(ProductNotFoundError)
async def _product_not_found_handler(_: Request, exc: ProductNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(detail=str(exc), code="not_found").model_dump(),
    )


@app.exception_handler(FeedbackProductNotFoundError)
async def _feedback_not_found_handler(
    _: Request, exc: FeedbackProductNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(detail=str(exc), code="not_found").model_dump(),
    )


@app.exception_handler(DuplicateProductError)
async def _duplicate_product_handler(_: Request, exc: DuplicateProductError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(detail=str(exc), code="duplicate").model_dump(),
    )


@app.exception_handler(ScoringUnavailableError)
async def _scoring_unavailable_handler(
    _: Request, exc: ScoringUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(detail=str(exc), code="scoring_unavailable").model_dump(),
    )


# ---------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------


app.include_router(opportunities.router)
app.include_router(products.router)
app.include_router(feedback.router)
app.include_router(categories.router)
app.include_router(keywords.router)
app.include_router(admin.router)
app.include_router(calculator.router)
app.include_router(detail_pages.router)


# ---------------------------------------------------------------------
# Static files — generated detail-page JPGs
# ---------------------------------------------------------------------
# Mount AFTER routers so explicit API paths win over the static handler.
# Module C writes to ``/app/generated/{detail_page_id}/page.jpg`` (CWD
# in the container is ``/app``); we resolve relative to CWD and create
# the dir on import so StaticFiles doesn't error on a fresh deploy.
_generated_dir = Path("generated")
_generated_dir.mkdir(exist_ok=True)
app.mount(
    "/generated",
    StaticFiles(directory=str(_generated_dir)),
    name="generated",
)


# ---------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness / readiness probe for compose + nginx."""
    return {"status": "ok"}
