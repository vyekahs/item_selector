"""쿠팡 파트너스 search API adapter.

Reference
---------
* https://partners.coupang.com/#api

**Quota**: 10 requests / hour. Two protections combined:

* Postgres :class:`app.cache.ApiCacheStore` — durable 24h cache so a
  process restart never replays the same query.
* :func:`app.ratelimit.build_coupang_bucket` — Redis token bucket sized
  exactly to the published 10/h limit, shared across worker processes.
"""
from __future__ import annotations

import copy
import os
from typing import Any, Protocol

from app.contracts.dto import CoupangProductDTO, CoupangSearchDTO

from .base import AuthError, BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 86_400  # 24 h — REQUIRED per the quota analysis.


# ---- helpers --------------------------------------------------------


def _parse_product(raw: dict[str, Any]) -> CoupangProductDTO:
    return CoupangProductDTO(
        product_id=str(raw.get("productId", "")),
        name=str(raw.get("productName", "")),
        price=int(raw.get("productPrice", 0) or 0),
        rating=float(raw.get("rating", 0.0) or 0.0),
        review_count=int(raw.get("ratingCount", 0) or 0),
        is_rocket=bool(raw.get("isRocket", False)),
        category_path=str(raw.get("categoryName", "")),
    )


def _aggregate(query: str, raw_items: list[dict[str, Any]]) -> CoupangSearchDTO:
    items = [_parse_product(r) for r in raw_items]
    prices = [it.price for it in items if it.price > 0]
    avg_price = int(round(sum(prices) / len(prices))) if prices else 0
    rocket_ratio = (sum(1 for it in items if it.is_rocket) / len(items)) if items else 0.0
    return CoupangSearchDTO(
        query=query,
        items=items,
        avg_price=avg_price,
        rocket_ratio=rocket_ratio,
    )


# ---- protocol ------------------------------------------------------


class CoupangPartnersClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, query: str, *, limit: int = 20) -> CoupangSearchDTO:
        ...


# ---- mock ----------------------------------------------------------


class MockCoupangPartnersClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "coupang_partners_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, query: str, *, limit: int = 20) -> CoupangSearchDTO:
        payload = copy.deepcopy(self._sample)
        items = (payload.get("data") or {}).get("productData", [])[:limit]
        return _aggregate(query, items)


# ---- real stub -----------------------------------------------------


class RealCoupangPartnersClient(BaseApiClient):
    """Live client stub. The actual call must hold a token from
    :func:`app.ratelimit.build_coupang_bucket` before issuing the HTTP
    request.
    """

    cache_ttl: int = CACHE_TTL_SECONDS
    _BASE_URL = "https://api-gateway.coupang.com/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        self.access_key = access_key or os.environ.get("COUPANG_ACCESS_KEY")
        self.secret_key = secret_key or os.environ.get("COUPANG_SECRET_KEY")

    async def fetch(self, query: str, *, limit: int = 20) -> CoupangSearchDTO:
        if not (self.access_key and self.secret_key):
            raise AuthError(
                "COUPANG_{ACCESS_KEY,SECRET_KEY} env vars are required"
            )
        raise NotImplementedError(
            "RealCoupangPartnersClient is a stub -- set USE_MOCK_CLIENTS=true."
        )


# ---- factory -------------------------------------------------------


def get_coupang_partners_client() -> CoupangPartnersClientProtocol:
    if use_mock_clients():
        return MockCoupangPartnersClient()
    return RealCoupangPartnersClient()
