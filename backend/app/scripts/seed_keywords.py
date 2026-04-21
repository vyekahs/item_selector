"""Idempotent seed keyword loader.

Ensures the initial seed keywords exist in the ``keywords`` table on
fresh deployments. Each seed is pinned to the ``반려동물`` category so
marker-based expansion stays in-domain for the pet-only bootstrap set.
Users add seeds for other categories via ``POST /keywords/seed`` (auto-
classified via Naver shopping).

Safe to re-run: rows are upserted by ``term``.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Category, Keyword, KeywordStatus

logger = logging.getLogger(__name__)

# Bootstrap seeds — all under the 반려동물 category.
SEED_TERMS: list[str] = [
    "스마트펫볼",
    "펫소프트바디",
    "캣타워",
    "고양이자동급수기",
    "고양이정수기",
    "강아지사료",
    "고양이사료",
    "강아지간식",
    "고양이간식",
    "강아지장난감",
    "고양이장난감",
    "강아지하네스",
    "강아지목줄",
    "고양이화장실",
    "강아지쿨매트",
    "펫드라이룸",
    "반려동물카메라",
    "자동급식기",
    "강아지유모차",
    "고양이캣휠",
]
BOOTSTRAP_CATEGORY = "반려동물"


def seed_keywords(session: Session | None = None) -> dict[str, int]:
    own = session is None
    s = session or SessionLocal()
    try:
        # Resolve bootstrap category (created by seed.py — must exist).
        cat_id = s.execute(
            select(Category.id).where(Category.name == BOOTSTRAP_CATEGORY)
        ).scalar_one_or_none()
        existing = {
            t: kid
            for t, kid in s.execute(
                select(Keyword.term, Keyword.id).where(Keyword.term.in_(SEED_TERMS))
            ).all()
        }
        inserted = promoted = 0
        for term in SEED_TERMS:
            if term in existing:
                kw = s.get(Keyword, existing[term])
                if not kw.is_seed:
                    kw.is_seed = True
                    kw.status = KeywordStatus.ACTIVE
                    promoted += 1
                if kw.category_id is None and cat_id is not None:
                    kw.category_id = cat_id
            else:
                s.add(
                    Keyword(
                        term=term,
                        is_seed=True,
                        status=KeywordStatus.ACTIVE,
                        category_id=cat_id,
                    )
                )
                inserted += 1
        s.commit()
        return {"inserted": inserted, "promoted": promoted, "total_seeds": len(SEED_TERMS)}
    except Exception:
        if own:
            s.rollback()
        raise
    finally:
        if own:
            s.close()


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = seed_keywords()
    logger.info("seed_keywords complete: %s", summary)


if __name__ == "__main__":  # pragma: no cover
    main()
