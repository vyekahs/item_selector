"""네이버 DataLab Search Trend adapter.

Reference
---------
* https://developers.naver.com/docs/serviceapi/datalab/search/search.md

The DataLab API returns a normalised 0–100 ratio over a time window. We
compute month-over-month growth rates (3 / 6 / 12 month) so downstream
scoring code only sees ready-to-use percentages, never raw curves.

Real client transport
---------------------
``POST https://openapi.naver.com/v1/datalab/search`` with headers
``X-Naver-Client-Id`` / ``X-Naver-Client-Secret`` and a JSON body
containing ``startDate`` / ``endDate`` / ``timeUnit`` / ``keywordGroups``.
Default window = last 12 months (``timeUnit=month``).
"""
from __future__ import annotations

import copy
import json
import os
from datetime import date
from typing import Any, Protocol

import httpx

from app.contracts.dto import NaverTrendDTO, TrendPoint

from .base import ApiError, AuthError, BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 86_400


# ---- helpers --------------------------------------------------------


def _parse_period(value: str) -> date:
    """Accept both ``YYYY-MM-DD`` and ``YYYYMMDD``."""
    value = value.strip()
    if "-" in value:
        return date.fromisoformat(value)
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def _growth_rate(points: list[TrendPoint], window_months: int) -> float:
    """Percentage change between the last point and the point ``window`` ago.

    Returns 0.0 when there's not enough history. Uses linear deltas; if
    the historical reference is 0 we cap the returned percentage at
    ``+10000`` to avoid Inf in downstream maths.
    """
    if len(points) <= window_months:
        return 0.0
    latest = points[-1].ratio
    reference = points[-1 - window_months].ratio
    if reference == 0:
        if latest == 0:
            return 0.0
        return 10000.0
    return ((latest - reference) / reference) * 100.0


def _build_dto(term: str, raw_points: list[dict[str, Any]]) -> NaverTrendDTO:
    points = [
        TrendPoint(period=_parse_period(p["period"]), ratio=float(p["ratio"]))
        for p in raw_points
    ]
    return NaverTrendDTO(
        term=term,
        points=points,
        growth_rate_3m=_growth_rate(points, 3),
        growth_rate_6m=_growth_rate(points, 6),
        growth_rate_12m=_growth_rate(points, 12),
    )


# ---- protocol ------------------------------------------------------


class NaverDataLabClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(
        self,
        keyword_groups: list[list[str]],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[NaverTrendDTO]:
        """Return one :class:`NaverTrendDTO` per keyword group."""
        ...


# ---- mock ----------------------------------------------------------


class MockNaverDataLabClient(BaseApiClient):
    """Loads ``naver_datalab_sample_1.json`` and projects to DTOs."""

    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "naver_datalab_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(
        self,
        keyword_groups: list[list[str]],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[NaverTrendDTO]:
        payload = copy.deepcopy(self._sample)
        results = payload.get("results", [])
        out: list[NaverTrendDTO] = []
        for grp in keyword_groups or [[]]:
            # Find a matching series by title; fall back to the first one
            # so single-shot calls always have data.
            wanted = grp[0] if grp else None
            series = next(
                (s for s in results if wanted is None or s.get("title") == wanted),
                results[0] if results else None,
            )
            if series is None:
                continue
            out.append(_build_dto(series.get("title", wanted or ""), series.get("data", [])))
        return out


# ---- real stub -----------------------------------------------------


def _default_date_window(months: int = 12) -> tuple[date, date]:
    """Return ``(start, end)`` covering the last ``months`` months including today.

    Naver DataLab's ``month`` bucket accepts day-precision endpoints and
    aligns to month starts internally, so using today is safe.
    """
    today = date.today()
    start_year = today.year
    start_month = today.month - months + 1
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    return date(start_year, start_month, 1), today


class RealNaverDataLabClient(BaseApiClient):
    """Live DataLab caller.

    Transport: ``POST /v1/datalab/search`` with ``Content-Type:
    application/json``, ``X-Naver-Client-Id`` and ``X-Naver-Client-Secret``
    headers. Request body keys: ``startDate``, ``endDate``, ``timeUnit``
    (``"month"``) and ``keywordGroups`` (each an object with
    ``groupName`` + up to five ``keywords``).
    """

    cache_ttl: int = CACHE_TTL_SECONDS
    _BASE_URL = "https://openapi.naver.com/v1/datalab/search"
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
            "Content-Type": "application/json",
        }

    async def fetch(
        self,
        keyword_groups: list[list[str]],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[NaverTrendDTO]:
        if not (self.client_id and self.client_secret):
            raise AuthError(
                "NAVER_OPENAPI_{CLIENT_ID,CLIENT_SECRET} env vars are required"
            )
        if not keyword_groups:
            return []

        if start_date is None or end_date is None:
            s, e = _default_date_window(12)
            start_date = start_date or s
            end_date = end_date or e

        # DataLab caps at 5 groups per call and each group at 5 keywords.
        groups_payload: list[dict[str, Any]] = []
        labels: list[str] = []
        for grp in keyword_groups[:5]:
            clean = [k for k in (grp or []) if k and k.strip()][:5]
            if not clean:
                continue
            label = clean[0]
            labels.append(label)
            groups_payload.append({"groupName": label, "keywords": clean})

        if not groups_payload:
            return []

        body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "timeUnit": "month",
            "keywordGroups": groups_payload,
        }

        async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
            resp = await client.post(
                self._BASE_URL,
                headers=self._headers(),
                content=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            )

        if resp.status_code in (401, 403):
            raise AuthError(
                f"naver datalab auth failed ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ApiError(
                f"naver datalab HTTP {resp.status_code}: {resp.text[:200]}"
            )

        payload = resp.json()
        results = payload.get("results") or []
        out: list[NaverTrendDTO] = []
        for idx, series in enumerate(results):
            title = series.get("title") or (labels[idx] if idx < len(labels) else "")
            out.append(_build_dto(title, series.get("data") or []))
        return out


# ---- factory -------------------------------------------------------


def get_naver_datalab_client() -> NaverDataLabClientProtocol:
    if use_mock_clients():
        return MockNaverDataLabClient()
    return RealNaverDataLabClient()
