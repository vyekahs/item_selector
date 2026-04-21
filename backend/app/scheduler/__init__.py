"""APScheduler-based batch pipeline for itemSelector.

Runs in a dedicated container (see ``docker-compose.yml`` service
``scheduler``). Entry point: ``python -m app.scheduler.main``.

Public surface
--------------
* :class:`~app.scheduler.base.ScheduledJob` — abstract job contract.
* :class:`~app.scheduler.runner.JobRunner` — executes a job with
  structured logging + retry/backoff (see :mod:`tenacity`).
* :func:`~app.scheduler.registry.build_scheduler` — returns a configured
  :class:`apscheduler.schedulers.asyncio.AsyncIOScheduler` with every
  pipeline job registered on its real schedule.

Test-friendliness
-----------------
All jobs accept an optional ``clients`` dict so tests can inject mocks
without touching environment variables. The default (``clients=None``)
falls back to the factory-produced clients, which honour
``USE_MOCK_CLIENTS``.
"""
from __future__ import annotations

from .base import JobResult, ScheduledJob
from .runner import JobRunner

__all__ = [
    "JobResult",
    "JobRunner",
    "ScheduledJob",
]
