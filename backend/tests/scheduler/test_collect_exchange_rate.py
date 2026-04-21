"""Tests for :class:`CollectExchangeRateJob`.

The hybrid client returns the existing DB row when it's < 1h old, so
the job must not cause a new row insert in that case. After a forced
stale state (no recent row) the upstream must be called and a new row
persisted.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.contracts.dto import ExchangeRateDTO
from app.models import ExchangeRate
from app.scheduler.jobs import CollectExchangeRateJob


class _StubUpstream:
    """Upstream exchange-rate client; counts how many times it was hit."""

    cache_ttl = 3600

    def __init__(self, rate_map: dict[str, Decimal]):
        self._rates = rate_map
        self.calls: list[str] = []

    async def fetch(self, *, currency_pair: str) -> ExchangeRateDTO:
        self.calls.append(currency_pair)
        return ExchangeRateDTO(
            currency_pair=currency_pair,
            rate=self._rates[currency_pair],
            fetched_at=datetime.now(tz=timezone.utc),
        )


def _count(session, pair: str) -> int:
    return len(session.execute(
        select(ExchangeRate).where(ExchangeRate.currency_pair == pair)
    ).all())


def test_collect_exchange_rate_writes_when_stale(db_session):
    upstream = _StubUpstream(
        {"CNY/KRW": Decimal("190.0"), "USD/KRW": Decimal("1300.0")}
    )
    job = CollectExchangeRateJob(upstream_client=upstream)

    before_cny = _count(db_session, "CNY/KRW")
    before_usd = _count(db_session, "USD/KRW")

    result = asyncio.run(job.run(db_session))

    assert result["inserts"] == 2
    assert _count(db_session, "CNY/KRW") == before_cny + 1
    assert _count(db_session, "USD/KRW") == before_usd + 1
    assert sorted(upstream.calls) == ["CNY/KRW", "USD/KRW"]


def test_collect_exchange_rate_reuses_recent_row(db_session):
    # Seed a fresh (< 1h old) row for CNY/KRW so the hybrid should
    # short-circuit and skip the upstream fetch entirely.
    fresh = ExchangeRate(
        currency_pair="CNY/KRW",
        rate=Decimal("188.5"),
        fetched_at=datetime.now(tz=timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(fresh)
    db_session.flush()

    upstream = _StubUpstream(
        {"CNY/KRW": Decimal("190.0"), "USD/KRW": Decimal("1300.0")}
    )
    job = CollectExchangeRateJob(upstream_client=upstream)

    before_cny = _count(db_session, "CNY/KRW")

    result = asyncio.run(job.run(db_session))

    # CNY/KRW was already fresh: no new row. USD/KRW was stale: 1 new row.
    assert _count(db_session, "CNY/KRW") == before_cny
    # Upstream should have been called only for USD/KRW.
    assert upstream.calls == ["USD/KRW"]
    assert result["inserts"] == 1
