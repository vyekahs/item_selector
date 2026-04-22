"""Map a seed keyword to an internal Category via Naver shopping lookup.

Internal category names track the Coupang commission fee table
(``COUPANG_FEES`` in ``app/scripts/seed.py``) so profit scoring can look
up the fee by name directly — no bridge table.

Policy
------
1. Query Naver shopping for the seed term (fetch 40 items for a fuller
   sample — sort=sim puts sponsored/ads at the top which can skew
   category1 majority on small windows).
2. Filter items whose ``title`` contains every query token. This
   excludes off-topic sponsored results (e.g. "스마트 LED 텐트" for
   the query "고양이 텐트") that inflate an unrelated category1.
3. Tally the full category path (``c1 > c2``) across filtered items.
   When any path contains ``반려동물``, return ``반려동물`` — Coupang's
   pet fee (10.8%) diverges enough from the 생활용품 default (7.8%)
   that the override pays for itself in margin accuracy.
4. Else map the top ``category1`` via ``NAVER_TO_INTERNAL``.
5. Empty / exception → ``기타``.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from app.clients import get_naver_shopping_client

if TYPE_CHECKING:
    from app.contracts.dto import ShoppingItem, ShoppingResultDTO

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

_TOKEN_RE = re.compile(r"[가-힣a-zA-Z0-9]+")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t]


def _item_matches_query(item: "ShoppingItem", query_tokens: list[str]) -> bool:
    """True when ``item.title`` contains every query token (substring match).

    Substring (not full-word) so "고양이텐트" matches "캠핑용고양이텐트".
    """
    if not query_tokens:
        return True
    title = (item.title or "").lower()
    return all(tok in title for tok in query_tokens)


async def infer_category_name(term: str) -> str:
    """Return the best-guess internal category name for ``term``."""
    client = get_naver_shopping_client()
    try:
        result: "ShoppingResultDTO" = await client.fetch(term, display=40)
    except Exception:
        return DEFAULT_CATEGORY

    query_tokens = _tokens(term)
    filtered = [it for it in result.items if _item_matches_query(it, query_tokens)]
    # Fall back to the raw result set when the title filter is too strict
    # (e.g. mall-specific phrasing that drops every result).
    items = filtered or list(result.items)
    if not items:
        return DEFAULT_CATEGORY

    # Pet override: any filtered result with category2 == '반려동물' wins.
    if any((it.category2 or "") == PET_CATEGORY for it in items):
        return PET_CATEGORY

    tally: Counter[str] = Counter(
        it.category1 for it in items if it.category1
    )
    if not tally:
        return DEFAULT_CATEGORY
    top_naver_cat, _ = tally.most_common(1)[0]
    return NAVER_TO_INTERNAL.get(top_naver_cat, DEFAULT_CATEGORY)
