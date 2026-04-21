"""관세청 품목별 국가별 수출입 실적 adapter (data.go.kr).

Reference
---------
* https://www.data.go.kr/data/15093796/openapi.do

Returns monthly customs records for a (HS code, country) pair, plus
3- and 12-month growth rates derived from the value time series.

Real client transport
---------------------
``GET https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList`` with
query params:

* ``serviceKey`` — decoded key from ``CUSTOMS_API_KEY``
* ``cntyCd`` — ISO country code (default ``CN``)
* ``hsSgn`` — 6-digit HS code (upstream silently accepts 10 too)
* ``strtYymm`` / ``endYymm`` — ``YYYYMM`` window
* ``type=json``

The response envelope is ``response.body.items.item`` where ``item``
can be either a single dict or a list. We always normalise to a list.
"""
from __future__ import annotations

import copy
import os
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import httpx

from app.contracts.dto import CustomsImportDTO, CustomsTrendDTO

from .base import ApiError, AuthError, BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 7 * 86_400  # 7 d (slow-moving monthly data)


# ---- helpers --------------------------------------------------------


def _to_decimal(val: Any) -> Decimal:
    if val in (None, ""):
        return Decimal(0)
    try:
        return Decimal(str(val).strip())
    except Exception:
        return Decimal(0)


def _to_year_month(raw: Any) -> str | None:
    """Accepts ``"202501"``, ``"2025.01"``, or ``"2025-01"``. Returns
    ``"YYYY-MM"`` or ``None`` when the value is a roll-up label (e.g.
    "총계") that should be skipped by the caller.
    """
    s = str(raw).strip()
    if len(s) == 6 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}"
    if len(s) == 7 and s[4] == "-" and s[:4].isdigit():
        return s
    if len(s) == 7 and s[4] == "." and s[:4].isdigit():
        return f"{s[0:4]}-{s[5:7]}"
    return None


def _parse_record(raw: dict[str, Any]) -> CustomsImportDTO | None:
    """Return the DTO, or ``None`` for summary/non-monthly rows."""
    raw_ym = (
        raw.get("statMonth")
        or raw.get("year")
        or raw.get("year_month", "")
    )
    ym = _to_year_month(raw_ym) if raw_ym else None
    if ym is None:
        return None  # e.g. year == "총계" roll-up row
    hs_raw = str(raw.get("hsCd") or raw.get("hsSgn") or "")
    if not hs_raw.isdigit():
        return None  # placeholder "-" rows
    return CustomsImportDTO(
        hs_code=hs_raw[:6],
        year_month=ym,
        country_code=str(raw.get("statCd", raw.get("country_code", ""))).upper(),
        import_quantity=_to_decimal(raw.get("impWgt", raw.get("import_quantity", 0))),
        import_value_usd=_to_decimal(raw.get("impDlr", raw.get("import_value_usd", 0))),
    )


def _xml_to_items(text: str) -> list[dict[str, Any]]:
    """Parse the public-data XML envelope into a list of item dicts.

    The endpoint ignores ``type=json`` and always returns XML. Structure:
    ``<response><body><items><item>...child elements...</item></items></body></response>``.
    """
    root = ET.fromstring(text)
    items: list[dict[str, Any]] = []
    for item_el in root.iter("item"):
        items.append({child.tag: (child.text or "") for child in item_el})
    return items


def _growth_rate(values: list[Decimal], window: int) -> float:
    """Latest point vs. point ``window`` ago, in percent."""
    if len(values) <= window:
        return 0.0
    latest = values[-1]
    reference = values[-1 - window]
    if reference == 0:
        return 0.0 if latest == 0 else 10000.0
    return float((latest - reference) / reference) * 100.0


def _window_avg_growth(values: list[Decimal], window: int) -> float:
    """Mean of last ``window`` vs. mean of the prior ``window``, in percent.

    Matches the "최근 vs 평균" semantic from the client spec — smoother
    than a single-point delta for noisy monthly customs series.
    """
    if len(values) < window * 2:
        return _growth_rate(values, window)
    recent = values[-window:]
    previous = values[-2 * window : -window]
    recent_avg = sum(recent) / Decimal(window)
    prev_avg = sum(previous) / Decimal(window)
    if prev_avg == 0:
        return 0.0 if recent_avg == 0 else 10000.0
    return float((recent_avg - prev_avg) / prev_avg) * 100.0


def _yyyymm_minus(end_yyyymm: str, months: int) -> str:
    """Return ``YYYYMM`` that is ``months`` calendar months before ``end_yyyymm``."""
    year = int(end_yyyymm[0:4])
    month = int(end_yyyymm[4:6]) - months + 1
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{year:04d}{month:02d}"


# ---- protocol ------------------------------------------------------


class CustomsClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(
        self,
        hs_code: str,
        country_code: str = "CN",
        *,
        months: int = 12,
    ) -> CustomsTrendDTO:
        ...


# ---- mock ----------------------------------------------------------


class MockCustomsClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "customs_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(
        self,
        hs_code: str,
        country_code: str = "CN",
        *,
        months: int = 12,
    ) -> CustomsTrendDTO:
        payload = copy.deepcopy(self._sample)
        items = (payload.get("body") or {}).get("items", [])
        # Keep records matching the (hs_code, country_code) when present;
        # otherwise return the canned series so tests have data.
        normalised = [_parse_record(it) for it in items]
        filtered = [
            r
            for r in normalised
            if r.hs_code.startswith(hs_code[:6]) and r.country_code == country_code.upper()
        ]
        records = (filtered or normalised)[-months:]
        values = [r.import_value_usd for r in records]
        return CustomsTrendDTO(
            hs_code=hs_code[:6],
            country_code=country_code.upper(),
            points=records,
            growth_rate_3m=_growth_rate(values, 3),
            growth_rate_12m=_growth_rate(values, 12),
        )


# ---- real stub -----------------------------------------------------


class RealCustomsClient(BaseApiClient):
    cache_ttl: int = CACHE_TTL_SECONDS
    # 15100475: 관세청_품목별 국가별 수출입실적(GW)
    # NOT /Itemtrade/getItemtradeList -- that's the nation-agnostic 15101609
    # dataset which our API key is not authorised for.
    _BASE_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
    _TIMEOUT_SECONDS: float = 15.0
    # The endpoint restricts each call to a **12-month** window
    # (resultCode=99 "시작과 종료의 조회기간은 1년이내 기간만 가능합니다").
    # We pull two successive years (up to 24 months) via two calls so
    # the 12-month avg-vs-avg growth metric has enough history.
    _MAX_WINDOW_MONTHS = 12

    def __init__(self, service_key: str | None = None):
        self.service_key = service_key or os.environ.get("CUSTOMS_API_KEY")

    async def fetch(
        self,
        hs_code: str,
        country_code: str = "CN",
        *,
        months: int = 12,
    ) -> CustomsTrendDTO:
        if not self.service_key:
            raise AuthError("CUSTOMS_API_KEY env var is required")

        # Input normalisation: upstream wants a 6-digit numeric HS
        # code. Callers pass various formats -- "4201.00", "420100",
        # "4201-00", even 10-digit codes -- so strip non-digits and
        # truncate to 6 before sending.
        hs_code = "".join(c for c in str(hs_code) if c.isdigit())[:6]
        if len(hs_code) != 6:
            raise ApiError(
                f"customs requires a 6-digit HS code after normalisation (got {hs_code!r})"
            )

        # 2-call strategy: pull the most-recent 12 months plus the
        # prior 12 months so 12-month avg-vs-avg growth has enough data.
        today = date.today()
        end_yyyymm = f"{today.year:04d}{today.month:02d}"
        mid_yyyymm = _yyyymm_minus(end_yyyymm, self._MAX_WINDOW_MONTHS - 1)
        prior_end = _yyyymm_minus(mid_yyyymm, 1)
        prior_start = _yyyymm_minus(prior_end, self._MAX_WINDOW_MONTHS - 1)

        windows = [
            (mid_yyyymm, end_yyyymm),   # last 12 months
            (prior_start, prior_end),   # preceding 12 months
        ]
        raw_items: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
            for start_ym, end_ym in windows:
                params = {
                    "serviceKey": self.service_key,
                    "cntyCd": country_code.upper(),
                    "hsSgn": hs_code[:6],
                    "strtYymm": start_ym,
                    "endYymm": end_ym,
                    "type": "json",
                }
                resp = await client.get(self._BASE_URL, params=params)

                if resp.status_code in (401, 403):
                    raise AuthError(
                        f"customs auth failed ({resp.status_code}): {resp.text[:200]}"
                    )
                if resp.status_code >= 400:
                    raise ApiError(
                        f"customs HTTP {resp.status_code}: {resp.text[:200]}"
                    )

                # Endpoint ignores ``type=json`` and returns XML.
                content_type = (resp.headers.get("content-type") or "").lower()
                try:
                    if "json" in content_type:
                        payload = resp.json()
                        body = (payload.get("response") or {}).get("body") or {}
                        items_wrapper = body.get("items") or {}
                        raw_item = (
                            items_wrapper.get("item")
                            if isinstance(items_wrapper, dict)
                            else items_wrapper
                        )
                        if raw_item is None:
                            chunk: list[dict[str, Any]] = []
                        elif isinstance(raw_item, dict):
                            chunk = [raw_item]
                        elif isinstance(raw_item, list):
                            chunk = raw_item
                        else:
                            chunk = []
                    else:
                        chunk = _xml_to_items(resp.text)
                except (ValueError, ET.ParseError) as exc:
                    raise ApiError(
                        f"customs malformed response: {resp.text[:200]}"
                    ) from exc

                raw_items.extend(chunk)

        # Multiple 10-digit sub-codes may roll up under a single 6-digit
        # HS for the same month → aggregate by (year_month, country, HS6).
        from collections import defaultdict

        bucketed: dict[tuple[str, str], tuple[Decimal, Decimal]] = defaultdict(
            lambda: (Decimal(0), Decimal(0))
        )
        for raw in raw_items:
            rec = _parse_record(raw)
            if rec is None:
                continue
            if rec.country_code != country_code.upper():
                continue
            if not rec.hs_code.startswith(hs_code[:6]):
                continue
            key = (rec.year_month, rec.country_code)
            qty, val = bucketed[key]
            bucketed[key] = (qty + rec.import_quantity, val + rec.import_value_usd)

        parsed = [
            CustomsImportDTO(
                hs_code=hs_code[:6],
                year_month=ym,
                country_code=cc,
                import_quantity=qty,
                import_value_usd=val,
            )
            for (ym, cc), (qty, val) in bucketed.items()
        ]
        parsed.sort(key=lambda r: r.year_month)

        all_values = [r.import_value_usd for r in parsed]
        points = parsed[-months:]
        return CustomsTrendDTO(
            hs_code=hs_code[:6],
            country_code=country_code.upper(),
            points=points,
            growth_rate_3m=_window_avg_growth(all_values, 3),
            growth_rate_12m=_window_avg_growth(all_values, 12),
        )


# ---- factory -------------------------------------------------------


def get_customs_client() -> CustomsClientProtocol:
    if use_mock_clients():
        return MockCustomsClient()
    return RealCustomsClient()
