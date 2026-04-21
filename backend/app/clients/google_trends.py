"""Google Trends adapter (pytrends library wrapper).

Reference
---------
* https://github.com/GeneralMills/pytrends

Google has no official API; ``pytrends`` scrapes the public endpoints.
We keep usage modest (24 h cache) and the real client raises a clear
``NotImplementedError`` until we wire pytrends in — the mock returns
deterministic data for development.
"""
from __future__ import annotations

import copy
from datetime import date
from typing import Any, Protocol

from app.contracts.dto import GoogleTrendDTO, TrendPoint

from .base import BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 86_400


# ---- helpers --------------------------------------------------------


def _parse_date(value: str) -> date:
    s = value.strip()
    if "-" in s:
        return date.fromisoformat(s)
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def _growth_rate(points: list[TrendPoint], window_months: int) -> float:
    if len(points) <= window_months:
        return 0.0
    latest = points[-1].ratio
    reference = points[-1 - window_months].ratio
    if reference == 0:
        return 0.0 if latest == 0 else 10000.0
    return ((latest - reference) / reference) * 100.0


def _build_dto(term: str, payload: dict[str, Any]) -> GoogleTrendDTO:
    raw_points = payload.get("interest_over_time", [])
    points = [
        TrendPoint(period=_parse_date(str(p["date"])), ratio=float(p["value"]))
        for p in raw_points
    ]
    rising = [
        str(r.get("query", "")).strip()
        for r in payload.get("related_queries_rising", [])
        if r.get("query")
    ]
    return GoogleTrendDTO(
        term=term,
        region=str(payload.get("geo", "KR")),
        points=points,
        related_rising=rising,
        growth_rate_3m=_growth_rate(points, 3),
    )


# ---- protocol ------------------------------------------------------


class GoogleTrendsClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, term: str, *, region: str = "KR") -> GoogleTrendDTO:
        ...


# ---- mock ----------------------------------------------------------


class MockGoogleTrendsClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "google_trends_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, term: str, *, region: str = "KR") -> GoogleTrendDTO:
        payload = copy.deepcopy(self._sample)
        payload["geo"] = region
        return _build_dto(term, payload)


# ---- real stub -----------------------------------------------------


class RealGoogleTrendsClient(BaseApiClient):
    """pytrends-based stub. Pytrends has no API key but is rate-limited
    by Google; we'll add throttling when we wire it for real."""

    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self) -> None:
        # Pytrends instance constructed lazily once we wire the real call.
        self._pytrends = None

    async def fetch(self, term: str, *, region: str = "KR") -> GoogleTrendDTO:
        raise NotImplementedError(
            "RealGoogleTrendsClient is a stub -- set USE_MOCK_CLIENTS=true."
        )


# ---- factory -------------------------------------------------------


def get_google_trends_client() -> GoogleTrendsClientProtocol:
    if use_mock_clients():
        return MockGoogleTrendsClient()
    return RealGoogleTrendsClient()
