"""네이버 블로그 + 카페 검색 API adapter.

Reference
---------
* https://developers.naver.com/docs/serviceapi/search/blog/blog.md
* https://developers.naver.com/docs/serviceapi/search/cafearticle/cafearticle.md

We collapse the two endpoints behind a single client because downstream
scoring just wants a "social buzz" signal — total counts plus a
30-day window for momentum.

Real client transport
---------------------
Two ``GET`` calls executed in parallel:
* ``/v1/search/blog.json`` for blog totals + postdates
* ``/v1/search/cafearticle.json`` for café totals
``display`` is capped at 100 by Naver. The blog endpoint returns
``postdate`` as ``"YYYYMMDD"``; the cafe endpoint does not surface
dates reliably so only its ``total`` is consumed.
"""
from __future__ import annotations

import asyncio
import copy
import os
from datetime import date, datetime, timedelta
from typing import Any, Protocol

import httpx

from app.contracts.dto import BlogCafeDTO

from .base import ApiError, AuthError, BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 86_400


# ---- helpers --------------------------------------------------------


def _parse_postdate(value: str) -> date | None:
    value = (value or "").strip()
    if len(value) == 8 and value.isdigit():
        try:
            return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _count_recent(items: list[dict[str, Any]], days: int, *, now: date | None = None) -> int:
    cutoff = (now or date.today()) - timedelta(days=days)
    n = 0
    for item in items:
        posted = _parse_postdate(str(item.get("postdate", "")))
        if posted and posted >= cutoff:
            n += 1
    return n


# ---- protocol ------------------------------------------------------


class NaverBlogCafeClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, term: str) -> BlogCafeDTO:
        ...


# ---- mock ----------------------------------------------------------


class MockNaverBlogCafeClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "naver_blogcafe_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, term: str) -> BlogCafeDTO:
        payload = copy.deepcopy(self._sample)
        items = payload.get("items", [])
        blog_total = int(payload.get("total", len(items)))
        # We don't have a separate cafe fixture; reuse a fraction so
        # downstream maths exercise both fields.
        cafe_total = int(blog_total * 0.42)

        # Pin "today" relative to the youngest post so growth stays > 0.
        post_dates = [_parse_postdate(str(it.get("postdate", ""))) for it in items]
        post_dates = [d for d in post_dates if d is not None]
        anchor = max(post_dates) + timedelta(days=1) if post_dates else date.today()

        recent_30d_blog = _count_recent(items, 30, now=anchor)
        # Synthesise growth: posts in last 30d vs. previous 30d.
        prev_window = []
        for it in items:
            d = _parse_postdate(str(it.get("postdate", "")))
            if d and (anchor - timedelta(days=60)) <= d < (anchor - timedelta(days=30)):
                prev_window.append(it)

        prev_count = max(1, len(prev_window))
        growth = ((recent_30d_blog - prev_count) / prev_count) * 100.0

        return BlogCafeDTO(
            term=term,
            blog_post_count=blog_total,
            cafe_post_count=cafe_total,
            recent_30d_blog_count=recent_30d_blog,
            recent_30d_growth_rate=growth,
        )


# ---- real stub -----------------------------------------------------


def _growth_from_windows(recent: int, previous: int) -> float:
    """Return percentage change ``(recent / previous - 1) * 100``.

    Uses the same +10000 ceiling as other clients when the previous
    window is zero but we still saw activity.
    """
    if previous == 0:
        if recent == 0:
            return 0.0
        return 10000.0
    return ((recent - previous) / previous) * 100.0


class RealNaverBlogCafeClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS
    _BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
    _CAFE_URL = "https://openapi.naver.com/v1/search/cafearticle.json"
    _TIMEOUT_SECONDS: float = 15.0

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

    async def _get(
        self, client: httpx.AsyncClient, url: str, term: str, label: str
    ) -> dict[str, Any]:
        resp = await client.get(
            url,
            params={"query": term, "display": 100, "start": 1, "sort": "date"},
            headers=self._headers(),
        )
        if resp.status_code in (401, 403):
            raise AuthError(
                f"naver {label} auth failed ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ApiError(
                f"naver {label} HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    async def fetch(self, term: str) -> BlogCafeDTO:
        if not (self.client_id and self.client_secret):
            raise AuthError(
                "NAVER_OPENAPI_{CLIENT_ID,CLIENT_SECRET} env vars are required"
            )

        async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
            blog_payload, cafe_payload = await asyncio.gather(
                self._get(client, self._BLOG_URL, term, "blog"),
                self._get(client, self._CAFE_URL, term, "cafearticle"),
            )

        blog_items = blog_payload.get("items") or []
        blog_total = int(blog_payload.get("total") or 0)
        cafe_total = int(cafe_payload.get("total") or 0)

        today = date.today()
        recent = _count_recent(blog_items, 30, now=today)
        previous = 0
        cutoff_prev_start = today - timedelta(days=60)
        cutoff_prev_end = today - timedelta(days=30)
        for it in blog_items:
            d = _parse_postdate(str(it.get("postdate", "")))
            if d and cutoff_prev_start <= d < cutoff_prev_end:
                previous += 1

        return BlogCafeDTO(
            term=term,
            blog_post_count=blog_total,
            cafe_post_count=cafe_total,
            recent_30d_blog_count=recent,
            recent_30d_growth_rate=_growth_from_windows(recent, previous),
        )


# ---- factory -------------------------------------------------------


def get_naver_blogcafe_client() -> NaverBlogCafeClientProtocol:
    if use_mock_clients():
        return MockNaverBlogCafeClient()
    return RealNaverBlogCafeClient()
