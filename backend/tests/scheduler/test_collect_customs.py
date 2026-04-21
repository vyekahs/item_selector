"""Tests for :class:`CollectCustomsJob`."""
from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.contracts.dto import CustomsImportDTO, CustomsTrendDTO
from app.models import HsCode, ImportStat
from app.scheduler.jobs import CollectCustomsJob


class _CustomsStub:
    cache_ttl = 7 * 86_400

    def __init__(self, *, points_per_code: int = 3):
        self.calls: list[tuple[str, str, int]] = []
        self._points = points_per_code

    async def fetch(self, hs_code, country_code="CN", *, months=12):
        self.calls.append((hs_code, country_code, months))
        points = [
            CustomsImportDTO(
                hs_code=hs_code,
                year_month=f"2026-{m:02d}",
                country_code=country_code,
                import_quantity=Decimal("1000") + Decimal(m),
                import_value_usd=Decimal("50000") + Decimal(m * 100),
            )
            for m in range(1, self._points + 1)
        ]
        return CustomsTrendDTO(
            hs_code=hs_code,
            country_code=country_code,
            points=points,
            growth_rate_3m=5.0,
            growth_rate_12m=8.0,
        )


def _seed_hs(session, code: str, name: str = "test") -> HsCode:
    hs = HsCode(code=code, name_ko=name)
    session.add(hs)
    session.flush()
    return hs


def test_collect_customs_writes_import_stats(db_session):
    _seed_hs(db_session, "230910", "사료")
    _seed_hs(db_session, "850980", "가정용 전기기기")

    job = CollectCustomsJob(customs_client=_CustomsStub(points_per_code=2))
    metrics = asyncio.run(job.run(db_session))

    assert metrics["hs_codes_processed"] == 2
    assert metrics["records_written"] == 4  # 2 codes × 2 months

    rows = db_session.execute(select(ImportStat)).scalars().all()
    assert len(rows) == 4
    assert all(r.country_code == "CN" for r in rows)


def test_collect_customs_is_idempotent(db_session):
    _seed_hs(db_session, "230910")
    job = CollectCustomsJob(customs_client=_CustomsStub(points_per_code=3))

    asyncio.run(job.run(db_session))
    asyncio.run(job.run(db_session))

    rows = db_session.execute(select(ImportStat)).scalars().all()
    # Still 3 (unique on (hs_code, year_month, country_code)).
    assert len(rows) == 3


def test_collect_customs_no_codes_is_noop(db_session):
    client = _CustomsStub()
    job = CollectCustomsJob(customs_client=client)
    metrics = asyncio.run(job.run(db_session))

    assert metrics == {"hs_codes_processed": 0, "records_written": 0}
    assert client.calls == []


def test_collect_customs_isolates_failures(db_session):
    _seed_hs(db_session, "230910")
    _seed_hs(db_session, "850980")

    class _FlakyStub(_CustomsStub):
        async def fetch(self, hs_code, country_code="CN", *, months=12):
            if hs_code == "230910":
                raise RuntimeError("upstream flaky")
            return await super().fetch(hs_code, country_code, months=months)

    job = CollectCustomsJob(customs_client=_FlakyStub(points_per_code=2))
    metrics = asyncio.run(job.run(db_session))

    assert metrics["hs_codes_processed"] == 2
    assert metrics["records_written"] == 2  # only one code succeeded
    assert len(metrics["failures"]) == 1
    assert "230910" in metrics["failures"][0]
