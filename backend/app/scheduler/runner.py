"""Execute a :class:`ScheduledJob` with retries + structured logging.

The runner is intentionally decoupled from APScheduler so unit tests
can drive jobs directly without spinning the scheduler up.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal

from .base import JobResult, ScheduledJob, utcnow

__all__ = ["JobRunner"]


logger = logging.getLogger("app.scheduler")


class JobRunner:
    """Run a job with exponential-backoff retry + structured logs.

    Session lifecycle
    -----------------
    By default the runner creates a fresh :class:`Session` via
    :func:`SessionLocal` per attempt (so a retry always starts with a
    clean transaction). Tests can inject a callable via
    ``session_factory`` to reuse a SAVEPOINT-wrapped session.
    """

    def __init__(
        self,
        session_factory: Any = None,
        *,
        sleep: Any = asyncio.sleep,
    ):
        self._session_factory = session_factory or SessionLocal
        self._sleep = sleep

    async def execute(self, job: ScheduledJob) -> JobResult:
        """Run ``job`` end-to-end. Always returns a :class:`JobResult`.

        Never raises upward: the scheduler must keep running even if a
        job permanently fails.
        """
        started_at = utcnow()
        attempts = 0
        last_error: BaseException | None = None
        metrics: dict[str, Any] = {}

        while attempts < max(1, job.max_attempts):
            attempts += 1
            session = self._session_factory()
            try:
                metrics = await job.run(session)
                if metrics is None:  # be tolerant
                    metrics = {}
                finished_at = utcnow()
                result = JobResult(
                    job_name=job.name,
                    started_at=started_at,
                    finished_at=finished_at,
                    success=True,
                    attempts=attempts,
                    metrics=dict(metrics),
                )
                self._log(result, level=logging.INFO)
                return result
            except Exception as exc:  # noqa: BLE001 — runner swallows by design
                last_error = exc
                try:
                    session.rollback()
                except Exception:  # pragma: no cover — rollback on closed tx
                    pass
                # On the last attempt, do *not* sleep — we fall through.
                if attempts >= job.max_attempts:
                    break
                delay = min(
                    job.backoff_max,
                    job.backoff_base * (2 ** (attempts - 1)),
                )
                logger.warning(
                    "job=%s attempt=%d/%d failed: %s; retrying in %.1fs",
                    job.name,
                    attempts,
                    job.max_attempts,
                    exc,
                    delay,
                )
                await self._sleep(delay)
            finally:
                try:
                    session.close()
                except Exception:  # pragma: no cover
                    pass

        finished_at = utcnow()
        result = JobResult(
            job_name=job.name,
            started_at=started_at,
            finished_at=finished_at,
            success=False,
            attempts=attempts,
            error=f"{type(last_error).__name__}: {last_error}" if last_error else None,
            metrics=metrics,
        )
        self._log(result, level=logging.ERROR)
        return result

    # ---- logging ---------------------------------------------------------

    def _log(self, result: JobResult, *, level: int) -> None:
        try:
            payload = json.dumps(result.to_log_dict(), ensure_ascii=False)
        except (TypeError, ValueError):
            # Fall back to repr when metrics contain non-JSON-serializable values.
            payload = repr(result.to_log_dict())
        logger.log(level, "scheduler.job %s", payload)
