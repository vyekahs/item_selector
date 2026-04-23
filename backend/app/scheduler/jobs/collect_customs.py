"""Weekly customs-import refresh (관세청 수출입실적).

Iterates every ``hs_codes`` row and stores the monthly points returned
by the 관세청 API into ``import_stats``. Idempotent via the
``(hs_code, year_month, country_code)`` unique constraint.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.clients import CustomsClientProtocol, get_customs_client
from app.models import HsCode, ImportStat
from app.scheduler.base import ScheduledJob

__all__ = ["CollectCustomsJob"]


# Default to CN since §1 of the spec is all about sourcing from 1688.
DEFAULT_COUNTRY: str = "CN"


class CollectCustomsJob(ScheduledJob):
    """Weekly refresh of customs import statistics (per HS code)."""

    name: str = "collect_customs"
    max_attempts: int = 3

    def __init__(
        self,
        *,
        customs_client: CustomsClientProtocol | None = None,
        country_code: str = DEFAULT_COUNTRY,
        months: int = 12,
        max_codes: int = 3000,
    ):
        super().__init__()
        self._customs = customs_client
        self._country = country_code.upper()
        self._months = months
        self._max_codes = max_codes

    def _client(self) -> CustomsClientProtocol:
        return self._customs or get_customs_client()

    async def run(self, session: Session) -> dict[str, Any]:
        client = self._client()

        # Random order so repeated runs cover different HS prefixes
        # rather than repeatedly hitting the first 200 alphabetically
        # (which are all in 01-24 = 동물/식품 and excluded from seed
        # discovery anyway).
        from sqlalchemy import func as _func

        codes: list[str] = list(
            session.execute(
                select(HsCode.code)
                .order_by(_func.random())
                .limit(self._max_codes)
            ).scalars()
        )
        if not codes:
            return {"hs_codes_processed": 0, "records_written": 0}

        written = 0
        failures: list[str] = []

        for code in codes:
            try:
                trend = await client.fetch(
                    code, self._country, months=self._months
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{code}: {type(exc).__name__}")
                continue

            for point in trend.points:
                # The real customs API sometimes ships 10-digit codes
                # while ``hs_codes`` may only carry the 6-digit parent
                # — normalise to what the FK expects.
                target_code = code
                values = {
                    "hs_code": target_code,
                    "year_month": point.year_month,
                    "country_code": (point.country_code or self._country).upper()[:3],
                    "import_quantity": Decimal(point.import_quantity),
                    "import_value_usd": Decimal(point.import_value_usd),
                }
                ins = pg_insert(ImportStat).values(**values)
                ins = ins.on_conflict_do_update(
                    constraint="import_stat_unique_period",
                    set_={
                        "import_quantity": ins.excluded.import_quantity,
                        "import_value_usd": ins.excluded.import_value_usd,
                    },
                )
                session.execute(ins)
                written += 1

        session.commit()

        return {
            "hs_codes_processed": len(codes),
            "records_written": written,
            "failures": failures,
        }
