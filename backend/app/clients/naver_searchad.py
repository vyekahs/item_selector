"""네이버 검색광고 API ``keywordstool`` adapter.

Reference
---------
* https://naver.github.io/searchad-apidoc/#/guides/authorization
* https://naver.github.io/searchad-apidoc/#/tags/RelKwdStat

**Auth**: HMAC-SHA256 over ``timestamp.method.path`` using
``NAVER_SEARCHAD_SECRET_KEY``; additionally requires
``NAVER_SEARCHAD_API_KEY`` + ``NAVER_SEARCHAD_CUSTOMER_ID`` headers.
No listed rate-limit (spec §3.1). Response TTL: 24 h.

This adapter exposes :class:`KeywordVolumeDTO` from
:mod:`app.contracts.dto` — the upstream wire shape (Korean field names,
"낮음/중간/높음" competition strings, ``"< 10"`` low-volume markers, …)
is normalised inside the mock/real client so downstream consumers never
see Naver-specific quirks.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import os
import time
from typing import Any, Protocol

import httpx

from app.contracts.dto import KeywordVolumeDTO

from .base import ApiError, AuthError, BaseApiClient, load_sample_json, use_mock_clients

# 24 h cache TTL — public guidance plus our own cost ceiling.
CACHE_TTL_SECONDS: int = 86_400


# ---- helpers --------------------------------------------------------


_COMPETITION_TO_INDEX: dict[str, float] = {
    "낮음": 0.2,
    "중간": 0.5,
    "높음": 0.8,
}


def _to_int(val: Any) -> int:
    """Naver returns strings like ``"< 10"`` for very low volumes."""
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        stripped = val.strip().lstrip("<").strip()
        if not stripped or not stripped.isdigit():
            return 0
        return int(stripped)
    return 0


def _competition_to_index(raw: Any) -> float:
    """Map either the Korean label or a numeric value to ``[0, 1]``."""
    if isinstance(raw, (int, float)):
        if raw <= 1.0:
            return float(raw)
        # Naver sometimes returns 0–100; normalise.
        return max(0.0, min(1.0, float(raw) / 100.0))
    if isinstance(raw, str):
        return _COMPETITION_TO_INDEX.get(raw.strip(), 0.5)
    return 0.5


def _parse_keyword_row(raw: dict[str, Any]) -> KeywordVolumeDTO:
    pc = _to_int(raw.get("monthlyPcQcCnt", 0))
    mobile = _to_int(raw.get("monthlyMobileQcCnt", 0))
    return KeywordVolumeDTO(
        term=str(raw.get("relKeyword", "")),
        pc_monthly_volume=pc,
        mobile_monthly_volume=mobile,
        total_monthly_volume=pc + mobile,
        competition_index=_competition_to_index(raw.get("compIdx", "중간")),
        related_keywords=list(raw.get("relatedKeywords", []) or []),
    )


# ---- protocol ------------------------------------------------------


class NaverSearchAdClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, keywords: list[str]) -> list[KeywordVolumeDTO]:
        """Return keyword volume rows for ``keywords`` (≤5 per API call)."""
        ...


# ---- mock ----------------------------------------------------------


class MockNaverSearchAdClient(BaseApiClient):
    """Reads ``naver_searchad_sample_1.json`` and returns parsed DTOs."""

    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "naver_searchad_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, keywords: list[str]) -> list[KeywordVolumeDTO]:
        payload = copy.deepcopy(self._sample)
        rows = payload.get("keywordList", [])
        # If caller passed specific keywords, filter to those rows that
        # match them when possible — otherwise return the full sample so
        # tests have data to assert on.
        if keywords:
            wanted = {k.strip() for k in keywords}
            filtered = [r for r in rows if r.get("relKeyword") in wanted]
            if filtered:
                rows = filtered
        return [_parse_keyword_row(r) for r in rows]


# ---- real stub -----------------------------------------------------


class RealNaverSearchAdClient(BaseApiClient):
    """Live keywordstool caller.

    Auth per https://naver.github.io/searchad-apidoc/#/guides/authorization :

    * ``X-Timestamp``   = current Unix time in milliseconds
    * ``X-API-KEY``     = access license (NAVER_SEARCHAD_API_KEY)
    * ``X-Customer``    = customer id (NAVER_SEARCHAD_CUSTOMER_ID)
    * ``X-Signature``   = base64(HMAC-SHA256(secret, f"{ts}.{method}.{path}"))

    ``hintKeywords`` accepts up to 5 comma-separated terms per call.
    Response schema: ``{"keywordList": [{"relKeyword": ..., "monthlyPcQcCnt": ..., "compIdx": "낮음|중간|높음", ...}, ...]}``
    """

    cache_ttl: int = CACHE_TTL_SECONDS
    _BASE_URL = "https://api.searchad.naver.com"
    _PATH = "/keywordstool"
    _TIMEOUT_SECONDS: float = 15.0

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        customer_id: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("NAVER_SEARCHAD_API_KEY")
        self.secret_key = secret_key or os.environ.get("NAVER_SEARCHAD_SECRET_KEY")
        self.customer_id = customer_id or os.environ.get("NAVER_SEARCHAD_CUSTOMER_ID")

    def _signed_headers(self, method: str, path: str) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        message = f"{ts}.{method}.{path}"
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {
            "X-Timestamp": ts,
            "X-API-KEY": self.api_key,
            "X-Customer": str(self.customer_id),
            "X-Signature": signature,
        }

    async def fetch(self, keywords: list[str]) -> list[KeywordVolumeDTO]:
        if not all([self.api_key, self.secret_key, self.customer_id]):
            raise AuthError(
                "NAVER_SEARCHAD_{API_KEY,SECRET_KEY,CUSTOMER_ID} env vars are required"
            )
        if not keywords:
            return []
        # Naver caps hintKeywords at 5 per request. Additionally the
        # keywordstool endpoint **rejects keywords containing spaces**
        # (HTTP 400, code 11001 "hintKeywords 파라미터가 유효하지 않습니다")
        # -- so collapse whitespace before sending.
        batch = [
            "".join(k.split())
            for k in keywords[:5]
            if k and k.strip()
        ]
        batch = [k for k in batch if k]
        if not batch:
            return []

        params = {
            "hintKeywords": ",".join(batch),
            "showDetail": "1",
        }
        headers = self._signed_headers("GET", self._PATH)

        async with httpx.AsyncClient(
            base_url=self._BASE_URL, timeout=self._TIMEOUT_SECONDS
        ) as client:
            resp = await client.get(self._PATH, params=params, headers=headers)

        if resp.status_code == 401 or resp.status_code == 403:
            raise AuthError(
                f"naver searchad auth failed ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ApiError(
                f"naver searchad HTTP {resp.status_code}: {resp.text[:200]}"
            )

        payload = resp.json()
        rows = payload.get("keywordList") or []
        return [_parse_keyword_row(r) for r in rows]


# ---- factory -------------------------------------------------------


def get_naver_searchad_client() -> NaverSearchAdClientProtocol:
    if use_mock_clients():
        return MockNaverSearchAdClient()
    return RealNaverSearchAdClient()
