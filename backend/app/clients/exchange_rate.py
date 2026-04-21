"""Exchange-rate adapter (한국수출입은행 OpenAPI).

Reference
---------
* https://www.koreaexim.go.kr/site/program/financial/exchangeJSON

The API only updates once per business day so we cache aggressively.
The mock fixture is good enough for development. The
:class:`HybridExchangeRateClient` adds a thin DB layer on top that
returns the most recent ``exchange_rates`` row when it's < 1 hour old
before falling back to the underlying client (and persisting the new
value).

Real client transport
---------------------
``GET https://www.koreaexim.go.kr/site/program/financial/exchangeJSON``
with ``authkey``, ``searchdate=YYYYMMDD`` and ``data=AP01``. Weekends
and public holidays yield an empty list — we walk up to seven calendar
days backwards until we see a populated response.

We keep reading ``EXIM_BANK_API_KEY`` first (matches ``.env``) and fall
back to the legacy ``EXIM_API_KEY`` variable for backward compatibility
with existing tests and deployments.
"""
from __future__ import annotations

import copy
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.dto import ExchangeRateDTO
from app.models import ExchangeRate

from .base import ApiError, AuthError, BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 3_600  # 1 h

# Maps the EXIM ``cur_unit`` to a canonical ISO pair label.
_CURRENCY_PAIR_MAP: dict[str, str] = {
    "CNH": "CNY/KRW",
    "CNY": "CNY/KRW",
    "USD": "USD/KRW",
    "JPY(100)": "JPY/KRW",
    "EUR": "EUR/KRW",
}


# ---- helpers --------------------------------------------------------


def _to_decimal(val: Any) -> Decimal:
    if val in (None, ""):
        return Decimal(0)
    cleaned = str(val).replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except Exception:
        return Decimal(0)


def _row_to_dto(raw: dict[str, Any], *, fetched_at: datetime) -> ExchangeRateDTO | None:
    pair = _CURRENCY_PAIR_MAP.get(str(raw.get("cur_unit", "")).strip())
    if not pair:
        return None
    rate = _to_decimal(raw.get("deal_bas_r"))
    if rate == 0:
        return None
    return ExchangeRateDTO(currency_pair=pair, rate=rate, fetched_at=fetched_at)


# ---- protocol ------------------------------------------------------


class ExchangeRateClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, currency_pair: str = "CNY/KRW") -> ExchangeRateDTO:
        ...


# ---- mock ----------------------------------------------------------


class MockExchangeRateClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "exchange_rate_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, currency_pair: str = "CNY/KRW") -> ExchangeRateDTO:
        payload = copy.deepcopy(self._sample)
        now = datetime.now(tz=timezone.utc)
        for raw in payload:
            dto = _row_to_dto(raw, fetched_at=now)
            if dto and dto.currency_pair == currency_pair:
                return dto
        raise ValueError(f"currency_pair {currency_pair!r} not present in sample")


# ---- real stub -----------------------------------------------------


# Reverse map: our canonical pair label -> the ``cur_unit`` strings we
# accept from the API (first match wins).
_PAIR_TO_CUR_UNITS: dict[str, tuple[str, ...]] = {
    "CNY/KRW": ("CNH", "CNY"),
    "USD/KRW": ("USD",),
    "JPY/KRW": ("JPY(100)",),
    "EUR/KRW": ("EUR",),
}


class RealExchangeRateClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS
    _BASE_URL = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
    _TIMEOUT_SECONDS: float = 15.0
    _MAX_DAY_LOOKBACK = 7  # walk back up to a week to skip weekends/holidays

    def __init__(self, auth_key: str | None = None):
        self.auth_key = (
            auth_key
            or os.environ.get("EXIM_BANK_API_KEY")
            or os.environ.get("EXIM_API_KEY")
        )

    async def fetch(self, currency_pair: str = "CNY/KRW") -> ExchangeRateDTO:
        if not self.auth_key:
            raise AuthError(
                "EXIM_BANK_API_KEY (or EXIM_API_KEY) env var is required"
            )

        accepted_units = _PAIR_TO_CUR_UNITS.get(currency_pair)
        if not accepted_units:
            raise ValueError(f"unsupported currency_pair: {currency_pair!r}")

        now = datetime.now(tz=timezone.utc)
        today = date.today()

        async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
            for offset in range(self._MAX_DAY_LOOKBACK):
                query_day = today - timedelta(days=offset)
                params = {
                    "authkey": self.auth_key,
                    "searchdate": query_day.strftime("%Y%m%d"),
                    "data": "AP01",
                }
                resp = await client.get(self._BASE_URL, params=params)

                if resp.status_code in (401, 403):
                    raise AuthError(
                        f"exim auth failed ({resp.status_code}): {resp.text[:200]}"
                    )
                if resp.status_code >= 400:
                    raise ApiError(
                        f"exim HTTP {resp.status_code}: {resp.text[:200]}"
                    )

                try:
                    payload = resp.json()
                except ValueError as exc:
                    raise ApiError(f"exim invalid JSON: {resp.text[:200]}") from exc

                if not isinstance(payload, list) or not payload:
                    # Weekend / holiday / not-yet-published day.
                    continue

                # The API sometimes signals a bad key via a single
                # object with ``result`` != 1 and no rates — treat that
                # as an auth error.
                if (
                    len(payload) == 1
                    and isinstance(payload[0], dict)
                    and payload[0].get("result") not in (1, None)
                    and not payload[0].get("cur_unit")
                ):
                    raise AuthError(
                        f"exim rejected request (result={payload[0].get('result')})"
                    )

                for raw in payload:
                    if not isinstance(raw, dict):
                        continue
                    if str(raw.get("cur_unit", "")).strip() in accepted_units:
                        dto = _row_to_dto(raw, fetched_at=now)
                        if dto is not None:
                            return dto

        raise ApiError(
            f"exim returned no data for {currency_pair!r} within "
            f"{self._MAX_DAY_LOOKBACK} days"
        )


# ---- DB-backed wrapper ---------------------------------------------


class HybridExchangeRateClient:
    """Read-through wrapper that prefers a fresh DB row to an upstream call.

    This isn't strictly required by the protocol but it implements the
    "≤ 1h reuse otherwise insert" rule called out in the task spec.
    """

    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(
        self,
        session: Session,
        upstream: ExchangeRateClientProtocol | None = None,
        *,
        freshness: timedelta = timedelta(hours=1),
    ):
        self._session = session
        self._upstream = upstream or get_exchange_rate_client()
        self._freshness = freshness

    async def fetch(self, currency_pair: str = "CNY/KRW") -> ExchangeRateDTO:
        cutoff = datetime.now(tz=timezone.utc) - self._freshness
        stmt = (
            select(ExchangeRate)
            .where(
                ExchangeRate.currency_pair == currency_pair,
                ExchangeRate.fetched_at >= cutoff,
            )
            .order_by(ExchangeRate.fetched_at.desc())
            .limit(1)
        )
        row = self._session.execute(stmt).scalar_one_or_none()
        if row is not None:
            return ExchangeRateDTO(
                currency_pair=row.currency_pair,
                rate=Decimal(row.rate),
                fetched_at=row.fetched_at,
            )

        dto = await self._upstream.fetch(currency_pair=currency_pair)
        self._session.add(
            ExchangeRate(
                currency_pair=dto.currency_pair,
                rate=dto.rate,
                fetched_at=dto.fetched_at,
            )
        )
        self._session.commit()
        return dto


# ---- factory -------------------------------------------------------


def get_exchange_rate_client() -> ExchangeRateClientProtocol:
    if use_mock_clients():
        return MockExchangeRateClient()
    return RealExchangeRateClient()
