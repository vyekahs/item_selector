"""Registry wiring tests for the scheduler.

Guards against the very easy mistake of forgetting to register a new
job in ``default_schedule``. Asserting on job names keeps the assertion
stable as triggers evolve.
"""
from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler.registry import build_scheduler, default_schedule


# Option A (2026-04-20): Coupang Partners collection disabled by
# default. Toggle via ``ENABLE_COUPANG_COLLECTOR=true``.
DEFAULT_JOB_NAMES = {
    "collect_keywords",
    "collect_metrics",
    "collect_customs",
    "recalculate_opportunities",
    "collect_exchange_rate",
    "fill_missing_signals",
    "translate_keywords",
}


def test_default_schedule_registers_every_job():
    specs = default_schedule()
    got = {spec.id for spec in specs}
    assert got == DEFAULT_JOB_NAMES


def test_build_scheduler_adds_all_jobs():
    # build_scheduler() does not start the scheduler — so no shutdown
    # call is needed. Any exception from a started scheduler would mean
    # the registry violated its contract.
    scheduler = build_scheduler()
    ids = {job.id for job in scheduler.get_jobs()}
    assert ids == DEFAULT_JOB_NAMES
    assert all(job.max_instances == 1 for job in scheduler.get_jobs())


def test_coupang_enabled_by_env_flag(monkeypatch):
    monkeypatch.setenv("ENABLE_COUPANG_COLLECTOR", "true")
    spec = next(s for s in default_schedule() if s.id == "collect_coupang")
    assert isinstance(spec.trigger, IntervalTrigger)
    # 10-minute interval → 600s.
    assert spec.trigger.interval.total_seconds() == 600


def test_exchange_rate_uses_hourly_interval():
    spec = next(s for s in default_schedule() if s.id == "collect_exchange_rate")
    assert isinstance(spec.trigger, IntervalTrigger)
    assert spec.trigger.interval.total_seconds() == 3600


def test_weekly_customs_runs_on_monday():
    spec = next(s for s in default_schedule() if s.id == "collect_customs")
    assert isinstance(spec.trigger, CronTrigger)
    # Day-of-week field is the fifth in APScheduler's CronTrigger.
    dow_field = next(f for f in spec.trigger.fields if f.name == "day_of_week")
    assert str(dow_field) == "mon"
