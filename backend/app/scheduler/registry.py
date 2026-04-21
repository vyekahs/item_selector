"""Map :class:`ScheduledJob` instances to APScheduler triggers.

Single source of truth for the production schedule. Tests can call
:func:`build_scheduler` and then introspect ``scheduler.get_jobs()``
to confirm registration without actually starting it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .base import ScheduledJob
from .jobs import (
    CollectCoupangJob,
    CollectCustomsJob,
    CollectExchangeRateJob,
    CollectKeywordsJob,
    CollectMetricsJob,
    FillMissingSignalsJob,
    RecalculateOpportunitiesJob,
    TranslateKeywordsJob,
)
from .runner import JobRunner

__all__ = ["JobSchedule", "build_scheduler", "default_schedule"]


@dataclass(frozen=True)
class JobSchedule:
    """A job + the trigger that fires it.

    Kept as a plain dataclass rather than apscheduler's internal
    ``Job`` type so this layer stays library-agnostic for tests.
    """

    job: ScheduledJob
    trigger: BaseTrigger

    @property
    def id(self) -> str:
        return self.job.name


def default_schedule() -> list[JobSchedule]:
    """Return the production cron table.

    All times are UTC. Pipeline ordering (per spec §4.1):

    * 02:00 — collect_keywords        (seed expansion)
    * 03:00 — collect_metrics         (DataLab + Shopping + Blog/Cafe)
    * 04:00 Mon — collect_customs     (weekly, low-frequency upstream)
    * 05:00 — recalculate_opportunities (after metrics settle)
    * every 1h   — collect_exchange_rate

    Coupang Partners collection is disabled by default: the operator
    opted for the 네이버-only pipeline (spec Option A, 2026-04-20).
    Set ``ENABLE_COUPANG_COLLECTOR=true`` to re-enable once Partners
    API access is obtained.
    """
    specs: list[JobSchedule] = [
        JobSchedule(
            job=CollectKeywordsJob(),
            trigger=CronTrigger(hour=2, minute=0),
        ),
        JobSchedule(
            job=CollectMetricsJob(),
            trigger=CronTrigger(hour=3, minute=0),
        ),
        JobSchedule(
            job=CollectCustomsJob(),
            trigger=CronTrigger(day_of_week="mon", hour=4, minute=0),
        ),
        JobSchedule(
            job=RecalculateOpportunitiesJob(),
            trigger=CronTrigger(hour=5, minute=0),
        ),
        JobSchedule(
            job=CollectExchangeRateJob(),
            trigger=IntervalTrigger(hours=1),
        ),
        # Every 30 min: retry any keyword whose today-snapshot is still
        # missing YouTube / 관세청 data (e.g. after a YouTube quota hit).
        JobSchedule(
            job=FillMissingSignalsJob(),
            trigger=IntervalTrigger(minutes=30),
        ),
        # Hourly: translate newly-added Korean keywords to Simplified
        # Chinese so the 1688 deep link doesn't mojibake.
        JobSchedule(
            job=TranslateKeywordsJob(),
            trigger=IntervalTrigger(hours=1),
        ),
    ]
    import os

    if os.environ.get("ENABLE_COUPANG_COLLECTOR", "false").lower() == "true":
        specs.append(
            JobSchedule(
                job=CollectCoupangJob(),
                trigger=IntervalTrigger(minutes=10),
            )
        )
    return specs


def _make_runnable(runner: JobRunner, job: ScheduledJob):
    """Bind a :class:`JobRunner` to a job for APScheduler's add_job."""

    async def _run() -> None:
        await runner.execute(job)

    # APScheduler logs identify functions by ``__name__``; give it
    # something useful per job.
    _run.__name__ = f"run_{job.name}"
    return _run


def build_scheduler(
    schedule: list[JobSchedule] | None = None,
    *,
    runner: JobRunner | None = None,
    timezone: str = "UTC",
    **scheduler_kwargs: Any,
) -> AsyncIOScheduler:
    """Wire jobs + runner into an :class:`AsyncIOScheduler`.

    The scheduler is **not** started here — the caller (production:
    :mod:`app.scheduler.main`; tests: assertions over ``get_jobs``)
    decides when ``start()`` is appropriate.
    """
    schedule = schedule or default_schedule()
    runner = runner or JobRunner()
    scheduler = AsyncIOScheduler(timezone=timezone, **scheduler_kwargs)
    for spec in schedule:
        scheduler.add_job(
            _make_runnable(runner, spec.job),
            trigger=spec.trigger,
            id=spec.id,
            name=spec.id,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
            replace_existing=True,
        )
    return scheduler
