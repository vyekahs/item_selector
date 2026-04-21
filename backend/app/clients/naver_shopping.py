"""네이버 쇼핑 검색 API adapter.

Reference
---------
* https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md

The upstream returns up to 100 items per page; we summarise into
:class:`ShoppingResultDTO` (avg / median price + top-10 average review
count). Review counts aren't part of the public API response so the
mock simulates them deterministically based on price tiers.

Real client transport
---------------------
``GET https://openapi.naver.com/v1/search/shop.json`` with headers
``X-Naver-Client-Id`` / ``X-Naver-Client-Secret``. Supports ``query``,
``display`` (1-100), ``start`` and ``sort`` query params. Review
counts aren't exposed by this endpoint — ``review_count`` stays
``None`` and ``top10_avg_review_count`` defaults to ``0.0``.
"""
from __future__ import annotations

import copy
import os
import statistics
from typing import Any, Protocol

import httpx

from app.contracts.dto import ShoppingItem, ShoppingResultDTO

from .base import ApiError, AuthError, BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 43_200  # 12 h


def _to_int_price(val: Any) -> int:
    if val in (None, "", "0"):
        return 0
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return 0


def _strip_html(text: str) -> str:
    """Naver search responses wrap matched terms in ``<b>...</b>`` tags."""
    return (
        text.replace("<b>", "")
        .replace("</b>", "")
        .replace("&amp;", "&")
        .strip()
    )


def _aggregate(query: str, total: int, raw_items: list[dict[str, Any]]) -> ShoppingResultDTO:
    items: list[ShoppingItem] = []
    for raw in raw_items:
        price = _to_int_price(raw.get("lprice") or raw.get("price"))
        items.append(
            ShoppingItem(
                title=_strip_html(str(raw.get("title", ""))),
                mall_name=str(raw.get("mallName", raw.get("mall_name", ""))),
                price=price,
                review_count=raw.get("reviewCount") or raw.get("review_count"),
                category1=(raw.get("category1") or None),
                category2=(raw.get("category2") or None),
            )
        )

    prices = [it.price for it in items if it.price > 0]
    avg_price = int(round(sum(prices) / len(prices))) if prices else 0
    median_price = int(round(statistics.median(prices))) if prices else 0

    review_counts = [it.review_count for it in items[:10] if it.review_count is not None]
    top10_avg = float(sum(review_counts) / len(review_counts)) if review_counts else 0.0

    return ShoppingResultDTO(
        query=query,
        total_count=total,
        items=items,
        avg_price=avg_price,
        median_price=median_price,
        top10_avg_review_count=top10_avg,
    )


# ---- protocol ------------------------------------------------------


class NaverShoppingClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, query: str, *, display: int = 10) -> ShoppingResultDTO:
        ...


# ---- mock ----------------------------------------------------------


class MockNaverShoppingClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "naver_shopping_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, query: str, *, display: int = 10) -> ShoppingResultDTO:
        payload = copy.deepcopy(self._sample)
        items = payload.get("items", [])[:display]
        # Inject deterministic review counts from price tier so the
        # aggregate makes sense without changing the canned wire fixture.
        for idx, it in enumerate(items):
            it.setdefault("reviewCount", 4500 - idx * 700)
        total = int(payload.get("total", len(items)))
        return _aggregate(query, total, items)


# ---- real stub -----------------------------------------------------


class RealNaverShoppingClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS
    _BASE_URL = "https://openapi.naver.com/v1/search/shop.json"
    _TIMEOUT_SECONDS: float = 15.0
    _MAX_DISPLAY = 100

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.client_id = client_id or os.environ.get("NAVER_OPENAPI_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("NAVER_OPENAPI_CLIENT_SECRET")

    def _headers(self) -> dict[str, str]:
        return {
            "X-Naver-Client-Id": str(self.client_id),
            "X-Naver-Client-Secret": str(self.client_secret),
        }

    async def fetch(self, query: str, *, display: int = 10) -> ShoppingResultDTO:
        if not (self.client_id and self.client_secret):
            raise AuthError(
                "NAVER_OPENAPI_{CLIENT_ID,CLIENT_SECRET} env vars are required"
            )

        params = {
            "query": query,
            "display": max(1, min(self._MAX_DISPLAY, int(display or 10))),
            "start": 1,
            "sort": "sim",
        }

        async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
            resp = await client.get(
                self._BASE_URL, params=params, headers=self._headers()
            )

        if resp.status_code in (401, 403):
            raise AuthError(
                f"naver shopping auth failed ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ApiError(
                f"naver shopping HTTP {resp.status_code}: {resp.text[:200]}"
            )

        payload = resp.json()
        items = payload.get("items") or []
        total = int(payload.get("total") or 0)
        return _aggregate(query, total, items)


# ---- factory -------------------------------------------------------


def get_naver_shopping_client() -> NaverShoppingClientProtocol:
    if use_mock_clients():
        return MockNaverShoppingClient()
    return RealNaverShoppingClient()
