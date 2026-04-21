"""Smoke test for real API clients against live upstream services.

Invoke against the production APIs to confirm credentials + transport
layer work end-to-end. Intended for **manual** use only — we never run
this in CI because it spends real quota.

Usage
-----
::

    set -a && source /Users/arang/projects/itemSelector/.env && set +a
    cd backend
    .venv/bin/python -m scripts.smoke_real_api

Each client runs independently; a failure in one does not stop the
others. Results are printed one-per-line with the client name, latency
and a small sample of the returned DTO.
"""
from __future__ import annotations

import asyncio
import time
import traceback
from typing import Any, Awaitable, Callable

from app.clients.customs import RealCustomsClient
from app.clients.exchange_rate import RealExchangeRateClient
from app.clients.naver_blogcafe import RealNaverBlogCafeClient
from app.clients.naver_datalab import RealNaverDataLabClient
from app.clients.naver_searchad import RealNaverSearchAdClient
from app.clients.naver_shopping import RealNaverShoppingClient
from app.clients.youtube import RealYouTubeClient


async def _timed(name: str, coro_factory: Callable[[], Awaitable[Any]]) -> None:
    start = time.perf_counter()
    try:
        result = await coro_factory()
    except Exception as exc:  # noqa: BLE001 — we want every failure surfaced
        elapsed = (time.perf_counter() - start) * 1000
        print(f"[FAIL] {name:<24s} {elapsed:7.0f} ms  {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return
    elapsed = (time.perf_counter() - start) * 1000
    summary = _summarise(result)
    print(f"[ OK ] {name:<24s} {elapsed:7.0f} ms  {summary}")


def _summarise(obj: Any) -> str:
    """Produce a single-line digest of the DTO shape."""
    if isinstance(obj, list):
        return f"list len={len(obj)}; first={_summarise(obj[0]) if obj else '—'}"
    # pydantic models have ``model_dump``.
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump()
        # trim long lists for readability
        for key, value in list(dumped.items()):
            if isinstance(value, list) and len(value) > 3:
                dumped[key] = f"[{len(value)} items]"
        return str(dumped)[:200]
    return str(obj)[:200]


async def main() -> None:
    await _timed(
        "naver_searchad",
        lambda: RealNaverSearchAdClient().fetch(["휴대용선풍기"]),
    )
    await _timed(
        "naver_datalab",
        lambda: RealNaverDataLabClient().fetch([["휴대용선풍기"]]),
    )
    await _timed(
        "naver_shopping",
        lambda: RealNaverShoppingClient().fetch("휴대용선풍기", display=10),
    )
    await _timed(
        "naver_blogcafe",
        lambda: RealNaverBlogCafeClient().fetch("휴대용선풍기"),
    )
    await _timed(
        "customs (HS 841451)",
        lambda: RealCustomsClient().fetch("841451", country_code="CN", months=12),
    )
    await _timed(
        "exchange_rate CNY/KRW",
        lambda: RealExchangeRateClient().fetch("CNY/KRW"),
    )
    await _timed(
        "youtube",
        lambda: RealYouTubeClient().fetch("휴대용선풍기"),
    )


if __name__ == "__main__":
    asyncio.run(main())
