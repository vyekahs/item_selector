"""YouTube Data API v3 (search.list / videos.list) adapter.

Reference
---------
* https://developers.google.com/youtube/v3/docs/search/list
* https://developers.google.com/youtube/v3/docs/videos/list

Returns a single :class:`YouTubeSignalDTO` summarising video count +
average view count + 30-day momentum for a search term.

Real client transport
---------------------
1. ``search.list`` (``part=snippet``, ``type=video``, ``maxResults=50``)
   — returns video ids + ``publishedAt``. ``pageInfo.totalResults`` is
   used for the total count even though YouTube rounds it for high
   cardinality terms.
2. ``videos.list`` (``part=statistics``, up to 50 ids) — needed for
   ``viewCount``; ``search.list`` does **not** populate ``statistics``.

Quota: ``search.list`` costs 100 units, ``videos.list`` costs 1 —
keep callers aware when bulk-running against the 10K daily limit.
"""
from __future__ import annotations

import copy
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import httpx

from app.contracts.dto import YouTubeSignalDTO

from .base import ApiError, AuthError, BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 86_400


# ---- helpers --------------------------------------------------------


def _parse_iso(value: str) -> datetime | None:
    try:
        # ``2026-03-22T08:12:00Z`` → tz-aware datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _aggregate(term: str, payload: dict[str, Any]) -> YouTubeSignalDTO:
    items = payload.get("items", [])
    page_info = payload.get("pageInfo", {})
    total = _to_int(page_info.get("totalResults", len(items)))

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=30)
    prev_cutoff = now - timedelta(days=60)

    recent_30d = 0
    prev_30d = 0
    view_counts: list[int] = []

    for item in items:
        published = _parse_iso(str(item.get("snippet", {}).get("publishedAt", "")))
        if published:
            if published >= cutoff:
                recent_30d += 1
            elif prev_cutoff <= published < cutoff:
                prev_30d += 1
        view_counts.append(_to_int(item.get("statistics", {}).get("viewCount", 0)))

    avg_views = int(round(sum(view_counts) / len(view_counts))) if view_counts else 0

    # Scale recent count to total when the items array is just a sample.
    if items:
        scale = total / len(items)
        recent_30d_scaled = int(round(recent_30d * scale))
        prev_30d_scaled = int(round(prev_30d * scale))
    else:
        recent_30d_scaled = recent_30d
        prev_30d_scaled = prev_30d

    if prev_30d_scaled == 0:
        growth = 0.0 if recent_30d_scaled == 0 else 100.0
    else:
        growth = ((recent_30d_scaled - prev_30d_scaled) / prev_30d_scaled) * 100.0

    return YouTubeSignalDTO(
        term=term,
        total_video_count=total,
        recent_30d_video_count=recent_30d_scaled,
        avg_view_count=avg_views,
        growth_rate_30d=growth,
    )


# ---- protocol ------------------------------------------------------


class YouTubeClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, term: str) -> YouTubeSignalDTO:
        ...


# ---- mock ----------------------------------------------------------


class MockYouTubeClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "youtube_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, term: str) -> YouTubeSignalDTO:
        payload = copy.deepcopy(self._sample)
        return _aggregate(term, payload)


# ---- real stub -----------------------------------------------------


class RealYouTubeClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS
    _BASE_URL = "https://www.googleapis.com/youtube/v3"
    _SEARCH_PATH = "/search"
    _VIDEOS_PATH = "/videos"
    _TIMEOUT_SECONDS: float = 15.0
    _MAX_RESULTS = 50

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")

    def _raise_for_status(self, resp: httpx.Response, label: str) -> None:
        if resp.status_code in (401, 403):
            raise AuthError(
                f"youtube {label} auth failed ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ApiError(
                f"youtube {label} HTTP {resp.status_code}: {resp.text[:200]}"
            )

    async def fetch(self, term: str) -> YouTubeSignalDTO:
        if not self.api_key:
            raise AuthError("YOUTUBE_API_KEY env var is required")

        search_params = {
            "part": "snippet",
            "type": "video",
            "q": term,
            "maxResults": self._MAX_RESULTS,
            "key": self.api_key,
        }

        async with httpx.AsyncClient(
            base_url=self._BASE_URL, timeout=self._TIMEOUT_SECONDS
        ) as client:
            search_resp = await client.get(self._SEARCH_PATH, params=search_params)
            self._raise_for_status(search_resp, "search")
            search_payload = search_resp.json()

            items = search_payload.get("items") or []
            video_ids = [
                (it.get("id") or {}).get("videoId")
                for it in items
                if isinstance(it.get("id"), dict)
            ]
            video_ids = [vid for vid in video_ids if vid]

            # Enrich items with statistics.viewCount via videos.list.
            stats_by_id: dict[str, dict[str, Any]] = {}
            if video_ids:
                videos_params = {
                    "part": "statistics",
                    "id": ",".join(video_ids[: self._MAX_RESULTS]),
                    "key": self.api_key,
                }
                videos_resp = await client.get(
                    self._VIDEOS_PATH, params=videos_params
                )
                self._raise_for_status(videos_resp, "videos")
                videos_payload = videos_resp.json()
                for raw in videos_payload.get("items") or []:
                    vid = raw.get("id")
                    if vid:
                        stats_by_id[vid] = raw.get("statistics") or {}

        enriched_items: list[dict[str, Any]] = []
        for it in items:
            vid = (it.get("id") or {}).get("videoId") if isinstance(it.get("id"), dict) else None
            enriched = dict(it)
            if vid and vid in stats_by_id:
                enriched["statistics"] = stats_by_id[vid]
            enriched_items.append(enriched)

        aggregate_payload = {
            "items": enriched_items,
            "pageInfo": search_payload.get("pageInfo", {}),
        }
        return _aggregate(term, aggregate_payload)


# ---- factory -------------------------------------------------------


def get_youtube_client() -> YouTubeClientProtocol:
    if use_mock_clients():
        return MockYouTubeClient()
    return RealYouTubeClient()
