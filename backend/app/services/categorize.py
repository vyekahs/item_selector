"""Map a seed keyword to an internal Category via Naver shopping lookup.

Internal category names track the Coupang commission fee table
(``COUPANG_FEES`` in ``app/scripts/seed.py``) so profit scoring can look
up the fee by name directly — no bridge table.

Policy
------
1. Query Naver shopping for the seed term.
2. Tally category1 across the top-10 results. Pet products get a bump:
   if any item's category2 is ``반려동물``, return ``반려동물`` regardless
   of category1 — the Coupang pet fee (10.8%) is high enough that
   mis-classification would distort the margin materially.
3. Fall back to the most common category1, mapped through
   ``NAVER_TO_INTERNAL`` (absorbs Naver's category1 ↔ our Coupang-
   aligned names).
4. If shopping returns nothing, default to ``기타``.
"""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from app.clients import get_naver_shopping_client

if TYPE_CHECKING:
    from app.contracts.dto import ShoppingResultDTO

# Naver category1 → internal category name (matches CoupangFee rows).
NAVER_TO_INTERNAL: dict[str, str] = {
    "생활/건강": "생활용품",
    "디지털/가전": "디지털",
    "패션의류": "패션잡화",
    "패션잡화": "패션잡화",
    "화장품/미용": "화장품/미용",
    "가구/인테리어": "생활용품",
    "식품": "식품",
    "출산/육아": "출산/육아",
    "스포츠/레저": "스포츠",
    "도서": "도서",
}

DEFAULT_CATEGORY = "기타"
PET_CATEGORY = "반려동물"


async def infer_category_name(term: str) -> str:
    """Return the best-guess internal category name for ``term``."""
    client = get_naver_shopping_client()
    try:
        result: "ShoppingResultDTO" = await client.fetch(term, display=10)
    except Exception:
        return DEFAULT_CATEGORY

    items = result.items[:10]
    if not items:
        return DEFAULT_CATEGORY

    # Pet override: any result with category2 == '반려동물' wins.
    if any((it.category2 or "") == PET_CATEGORY for it in items):
        return PET_CATEGORY

    tally: Counter[str] = Counter(
        it.category1 for it in items if it.category1
    )
    if not tally:
        return DEFAULT_CATEGORY
    top_naver_cat, _ = tally.most_common(1)[0]
    return NAVER_TO_INTERNAL.get(top_naver_cat, DEFAULT_CATEGORY)
