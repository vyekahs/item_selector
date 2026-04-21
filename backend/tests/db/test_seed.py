"""Seed script idempotency."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, CoupangFee, HsCode
from app.scripts.seed import (
    COUPANG_FEES,
    PET_HS_CODES,
    TOP_LEVEL_CATEGORIES,
    seed,
)


def _counts(session: Session) -> dict[str, int]:
    return {
        "categories": session.execute(
            select(Category).order_by(Category.id)
        ).scalars().all().__len__(),
        "hs_codes": session.execute(
            select(HsCode).order_by(HsCode.id)
        ).scalars().all().__len__(),
        "coupang_fees": session.execute(
            select(CoupangFee).order_by(CoupangFee.id)
        ).scalars().all().__len__(),
    }


def test_seed_creates_expected_rows(db_session: Session) -> None:
    summary_first = seed(db_session)
    db_session.flush()

    assert summary_first["categories"] >= len(TOP_LEVEL_CATEGORIES)
    assert summary_first["hs_codes"] >= len(PET_HS_CODES)
    assert summary_first["coupang_fees"] >= len(COUPANG_FEES)

    # Flat hierarchy — every top-level category has parent_id=NULL.
    for name, _cert in TOP_LEVEL_CATEGORIES:
        row = db_session.execute(
            select(Category).where(Category.name == name)
        ).scalar_one()
        assert row.parent_id is None


def test_seed_is_idempotent(db_session: Session) -> None:
    seed(db_session)
    db_session.flush()
    counts_after_first = _counts(db_session)

    seed(db_session)
    db_session.flush()
    counts_after_second = _counts(db_session)

    assert counts_after_first == counts_after_second, (
        f"second seed produced different row counts: "
        f"{counts_after_first} vs {counts_after_second}"
    )
