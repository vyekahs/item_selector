"""Google Cloud Translation v2 adapter (Korean → Simplified Chinese).

Used to build 1688 deep links: 1688's search endpoint decodes the
``keywords=`` query param as GBK, so Korean UTF-8 bytes show up as
mojibake (臧曥晞歆…). Translating the keyword to zh-CN first makes
the link click through to actual Chinese search results.

Auth reuses the same API key we issued for YouTube Data API v3
(``YOUTUBE_API_KEY`` env var, shared Google Cloud project). Cloud
Translation API must be *enabled* on that project -- the first call
after enabling returns 403 until a few seconds after propagation.

Free tier: 500,000 characters / month. We track usage in Redis
(``gt:chars:YYYY-MM``) and refuse new calls once we pass
``MONTHLY_CHAR_BUDGET``. Callers must handle :class:`QuotaExceededError`
by skipping the translation — it will be retried on the next scheduler
run (or next month, when the budget resets).
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Protocol

import httpx

from .base import ApiError, AuthError, BaseApiClient, use_mock_clients

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS: int = 30 * 86_400  # translations are effectively static

# Monthly safety cap: free tier is 500K. We stop at 450K so a burst of
# traffic near month-end can't slip into paid territory.
MONTHLY_CHAR_BUDGET: int = 450_000


class QuotaExceededError(ApiError):
    """Raised when monthly char budget is reached — skip translation."""


def _redis_client():  # noqa: ANN202 — lazy import, optional dep
    try:
        import redis
    except ImportError:
        return None
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:  # noqa: BLE001
        return None


def _budget_key() -> str:
    return f"gt:chars:{dt.date.today():%Y-%m}"


def _check_and_reserve_budget(chars: int) -> None:
    """Raise :class:`QuotaExceededError` if ``chars`` would exceed the cap.

    Atomically increments the month-scoped counter in Redis. When Redis
    is unreachable, err on the side of letting the call through (log a
    warning) — the alternative is blocking all translation on a cache
    outage.
    """
    if chars <= 0:
        return
    client = _redis_client()
    if client is None:
        logger.warning("google translate budget: redis unavailable, skipping guard")
        return
    key = _budget_key()
    try:
        used = int(client.get(key) or 0)
    except Exception:  # noqa: BLE001
        logger.warning("google translate budget: redis read failed", exc_info=True)
        return
    if used + chars > MONTHLY_CHAR_BUDGET:
        raise QuotaExceededError(
            f"google translate monthly budget reached: "
            f"used={used}, would add={chars}, cap={MONTHLY_CHAR_BUDGET}"
        )
    try:
        new_total = client.incrby(key, chars)
        # 40d TTL: survives the month-end roll-over and then auto-cleans.
        client.expire(key, 40 * 86_400)
        logger.debug("google translate budget: %s chars used (this month)", new_total)
    except Exception:  # noqa: BLE001
        logger.warning("google translate budget: redis incr failed", exc_info=True)


class GoogleTranslateClientProtocol(Protocol):
    cache_ttl: int

    async def translate(self, text: str, *, source: str = "ko", target: str = "zh-CN") -> str:
        ...


class MockGoogleTranslateClient(BaseApiClient):
    """Deterministic stand-in for tests. Returns ``"[zh] <text>"``."""

    cache_ttl: int = CACHE_TTL_SECONDS

    async def translate(self, text: str, *, source: str = "ko", target: str = "zh-CN") -> str:
        return f"[{target}] {text}"


class RealGoogleTranslateClient(BaseApiClient):
    """Calls the v2 REST endpoint (``translate.googleapis.com``)."""

    cache_ttl: int = CACHE_TTL_SECONDS
    _BASE_URL = "https://translation.googleapis.com/language/translate/v2"
    _TIMEOUT_SECONDS: float = 10.0

    def __init__(self, api_key: str | None = None):
        # Reuses the YouTube key (same Google Cloud project).
        self.api_key = (
            api_key
            or os.environ.get("GOOGLE_TRANSLATE_API_KEY")
            or os.environ.get("YOUTUBE_API_KEY")
        )

    async def translate(
        self, text: str, *, source: str = "ko", target: str = "zh-CN"
    ) -> str:
        if not self.api_key:
            raise AuthError(
                "GOOGLE_TRANSLATE_API_KEY (or YOUTUBE_API_KEY fallback) env var required"
            )
        stripped = text.strip()
        if not stripped:
            return ""
        # Reserve budget before hitting the wire. Raises QuotaExceededError
        # when we'd exceed MONTHLY_CHAR_BUDGET for the current month.
        _check_and_reserve_budget(len(stripped))
        payload = {"q": text, "source": source, "target": target, "format": "text"}
        async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
            resp = await client.post(
                self._BASE_URL,
                params={"key": self.api_key},
                json=payload,
            )
        # Google also returns 403 with ``rateLimitExceeded`` / ``quotaExceeded``
        # when a project-level quota cap is set in the Cloud Console. Map
        # those to QuotaExceededError so callers can back off the same way.
        if resp.status_code == 403 and (
            "quota" in resp.text.lower() or "rateLimit" in resp.text
        ):
            raise QuotaExceededError(
                f"google translate quota hit at upstream: {resp.text[:200]}"
            )
        if resp.status_code in (401, 403):
            raise AuthError(
                f"google translate auth/enable failed ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code == 429:
            raise QuotaExceededError(
                f"google translate 429 rate limit: {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ApiError(
                f"google translate HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        translations = (data.get("data") or {}).get("translations") or []
        if not translations:
            raise ApiError(f"google translate empty response: {resp.text[:200]}")
        return str(translations[0].get("translatedText") or "")


def get_google_translate_client() -> GoogleTranslateClientProtocol:
    if use_mock_clients():
        return MockGoogleTranslateClient()
    return RealGoogleTranslateClient()
