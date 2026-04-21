"""Idempotent seed data loader.

Run with::

    python -m app.scripts.seed

Loads:
    1. Pet category tree (반려동물용품 + 5 children)
    2. Coupang commission fee table (spec §9)
    3. Sample HS codes for pet-related items

Re-running is safe: each insert is guarded by a SELECT (so no UNIQUE
violations and no duplicate rows).
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Category, CoupangFee, HsCode

logger = logging.getLogger(__name__)


# ---- data definitions ------------------------------------------------------

# Top-level categories aligned with Naver shopping's ``category1`` and
# the Coupang fee schedule. Seed keywords are auto-classified into one
# of these by :mod:`app.services.categorize`.
TOP_LEVEL_CATEGORIES: list[tuple[str, bool]] = [
    # (name, is_certification_required)
    ("반려동물", False),
    ("생활용품", False),
    ("주방용품", False),
    ("가전 소형", False),
    ("디지털", False),
    ("패션잡화", False),
    ("스포츠", False),
    ("화장품/미용", True),   # 기능성 화장품은 식약처 신고
    ("식품", True),           # 식품위생법
    ("출산/육아", False),
    ("도서", False),
    ("기타", False),
]

# Coupang commission fees per category. Rates are approximate — refine
# per-deal with the actual Coupang seller dashboard.
COUPANG_FEES: list[tuple[str, float]] = [
    ("반려동물", 10.8),
    ("생활용품", 7.8),
    ("주방용품", 7.8),
    ("가전 소형", 5.8),
    ("디지털", 5.0),
    ("패션잡화", 10.5),
    ("스포츠", 10.5),
    ("화장품/미용", 9.6),
    ("식품", 10.6),
    ("출산/육아", 10.0),
    ("도서", 10.8),
    ("기타", 10.8),
]
COUPANG_FEE_EFFECTIVE_FROM = date(2026, 1, 1)

# HS code samples relevant to pet-supply sourcing.
# 6-digit codes per WCO HS 2022 nomenclature.
PET_HS_CODES: list[tuple[str, str, str | None]] = [
    # (code, name_ko, name_en)
    ("230910", "개·고양이용 사료 (소매용)", "Dog or cat food, retail"),
    ("420100", "동물용 마구·하니스류", "Saddlery and harness for animals"),
    ("392690", "기타 플라스틱 제품 (반려동물 용기 등)", "Other plastic articles"),
    ("630790", "기타 방직용 제품 (펫 매트 등)", "Other made up textile articles"),
    ("960390", "브러시류 (펫 그루밍용 포함)", "Brushes (incl. pet grooming)"),
    ("392310", "플라스틱 박스·케이스 (펫 케이지 부품)", "Plastic boxes/cases"),
    ("731815", "스테인리스 볼트·스크류 (조립식 케이지)", "Stainless screws/bolts"),
    ("482359", "기타 종이 식품용기 (배변패드 등)", "Other paper food containers"),
    ("847989", "기타 기계장치 (자동급수기 포함)", "Other machinery (incl. auto feeders)"),
    ("950300", "장난감 (반려동물 장난감 포함)", "Toys (incl. pet toys)"),
]


# ---- helpers ---------------------------------------------------------------


def _get_or_create_category(
    session: Session,
    *,
    name: str,
    parent_id: int | None = None,
    is_certification_required: bool = False,
) -> Category:
    """SELECT by (name, parent_id) then INSERT-if-missing."""
    stmt = select(Category).where(
        Category.name == name,
        Category.parent_id.is_(parent_id) if parent_id is None else Category.parent_id == parent_id,
    )
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        # Keep the certification flag in sync if the seed value changes.
        if existing.is_certification_required != is_certification_required:
            existing.is_certification_required = is_certification_required
        return existing

    category = Category(
        name=name,
        parent_id=parent_id,
        is_certification_required=is_certification_required,
    )
    session.add(category)
    session.flush()
    return category


def _upsert_hs_code(
    session: Session,
    *,
    code: str,
    name_ko: str,
    name_en: str | None,
    category_id: int | None,
) -> HsCode:
    existing = session.execute(
        select(HsCode).where(HsCode.code == code)
    ).scalar_one_or_none()
    if existing is not None:
        existing.name_ko = name_ko
        existing.name_en = name_en
        if existing.category_id is None and category_id is not None:
            existing.category_id = category_id
        return existing

    hs = HsCode(
        code=code,
        name_ko=name_ko,
        name_en=name_en,
        category_id=category_id,
    )
    session.add(hs)
    session.flush()
    return hs


def _upsert_coupang_fee(
    session: Session,
    *,
    category_path: str,
    fee_pct: float,
    effective_from: date,
) -> CoupangFee:
    existing = session.execute(
        select(CoupangFee).where(
            CoupangFee.category_path == category_path,
            CoupangFee.effective_from == effective_from,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.fee_pct = fee_pct
        return existing
    fee = CoupangFee(
        category_path=category_path,
        fee_pct=fee_pct,
        effective_from=effective_from,
    )
    session.add(fee)
    session.flush()
    return fee


# ---- entry point -----------------------------------------------------------


def seed(session: Session | None = None) -> dict[str, int]:
    """Run the seed in a single transaction. Returns a row-count summary."""
    own_session = session is None
    session = session or SessionLocal()
    try:
        # 1) top-level categories (flat, no hierarchy — parent_id stays NULL)
        pet_category: Category | None = None
        for name, cert_required in TOP_LEVEL_CATEGORIES:
            cat = _get_or_create_category(
                session,
                name=name,
                parent_id=None,
                is_certification_required=cert_required,
            )
            if name == "반려동물":
                pet_category = cat

        # 2) Pet HS codes (legacy — attach to 반려동물 if it exists)
        pet_cat_id = pet_category.id if pet_category is not None else None
        for code, name_ko, name_en in PET_HS_CODES:
            _upsert_hs_code(
                session,
                code=code,
                name_ko=name_ko,
                name_en=name_en,
                category_id=pet_cat_id,
            )

        # 3) Coupang fees
        for category_path, fee_pct in COUPANG_FEES:
            _upsert_coupang_fee(
                session,
                category_path=category_path,
                fee_pct=fee_pct,
                effective_from=COUPANG_FEE_EFFECTIVE_FROM,
            )

        if own_session:
            session.commit()

        summary = {
            "categories": session.query(Category).count(),
            "hs_codes": session.query(HsCode).count(),
            "coupang_fees": session.query(CoupangFee).count(),
        }
        return summary
    except Exception:
        if own_session:
            session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def main() -> None:  # pragma: no cover - thin CLI wrapper
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = seed()
    logger.info("seed complete: %s", summary)


if __name__ == "__main__":  # pragma: no cover
    main()
