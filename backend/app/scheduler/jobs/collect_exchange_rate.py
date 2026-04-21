"""Hourly exchange-rate refresh.

The :class:`HybridExchangeRateClient` already implements the
"return DB row if < 1h old, else fetch + insert" rule, so this job
simply pokes that client for each currency pair we care about. If a
pair was fetched < 1h ago no new row is written (the hybrid short-
circuits to the existing DB row).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import (
    ExchangeRateClientProtocol,
    HybridExchangeRateClient,
    get_exchange_rate_client,
)
from app.models import ExchangeRate
from app.scheduler.base import ScheduledJob

__all__ = ["CollectExchangeRateJob"]


DEFAULT_PAIRS: tuple[str, ...] = ("CNY/KRW", "USD/KRW")


class CollectExchangeRateJob(ScheduledJob):
    """Refresh the ``exchange_rates`` cache every hour."""

    name: str = "collect_exchange_rate"
    max_attempts: int = 3

    def __init__(
        self,
        *,
        upstream_client: ExchangeRateClientProtocol | None = None,
        pairs: tuple[str, ...] = DEFAULT_PAIRS,
    ):
        super().__init__()
        self._upstream = upstream_client
        self._pairs = tuple(pairs)

    def _client(self) -> ExchangeRateClientProtocol:
        return self._upstream or get_exchange_rate_client()

    async def run(self, session: Session) -> dict[str, Any]:
        upstream = self._client()
        hybrid = HybridExchangeRateClient(session, upstream=upstream)

        # Snapshot the row count per pair *before* we poke the hybrid
        # so we can report how many new rows were actually written.
        before_counts: dict[str, int] = {}
        for pair in self._pairs:
            n = session.execute(
                select(ExchangeRate).where(ExchangeRate.currency_pair == pair)
            ).all()
            before_counts[pair] = len(n)

        fetched: list[str] = []
        failures: list[str] = []
        for pair in self._pairs:
            try:
                await hybrid.fetch(currency_pair=pair)
                fetched.append(pair)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{pair}: {type(exc).__name__}")

        after_counts: dict[str, int] = {}
        inserts = 0
        for pair in self._pairs:
            n = session.execute(
                select(ExchangeRate).where(ExchangeRate.currency_pair == pair)
            ).all()
            after_counts[pair] = len(n)
            inserts += max(0, after_counts[pair] - before_counts[pair])

        return {
            "pairs_checked": list(self._pairs),
            "fetched": fetched,
            "inserts": inserts,
            "failures": failures,
        }
