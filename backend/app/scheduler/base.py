"""Scheduler primitives — job contract + standard result type.

The scheduler deliberately avoids persisting run metadata in the DB:
the DB schema is owned by the Database Agent and introducing a
``job_runs`` table is out-of-scope for this agent. Instead, every
:class:`JobRunner` emits structured JSON log lines that an external
aggregator (loki / CloudWatch / …) can ingest.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

__all__ = ["JobResult", "ScheduledJob"]


@dataclass(slots=True)
class JobResult:
    """Result of a single :class:`ScheduledJob` execution.

    The fields here are the minimum every caller expects; individual
    jobs can pack additional metrics into :attr:`metrics`.
    """

    job_name: str
    started_at: datetime
    finished_at: datetime
    success: bool
    error: str | None = None
    attempts: int = 1
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at).total_seconds() * 1000.0

    def to_log_dict(self) -> dict[str, Any]:
        """Serializable payload suitable for ``json.dumps``."""
        return {
            "job": self.job_name,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "attempts": self.attempts,
            "error": self.error,
            "metrics": self.metrics,
        }


class ScheduledJob(ABC):
    """Abstract base for every pipeline job.

    Subclasses implement :meth:`run` as an async coroutine receiving a
    live SQLAlchemy :class:`Session`. Any exception escaping ``run`` is
    caught + retried by :class:`~app.scheduler.runner.JobRunner`; after
    the final attempt it is logged with ``success=False`` and the
    scheduler *continues* (crash-free).

    Subclasses MUST set :attr:`name` (stable identifier used in logs +
    registry dedup). They MAY override :attr:`max_attempts` for jobs
    that shouldn't be retried (e.g. idempotence isn't guaranteed).
    """

    #: Stable identifier (snake_case).
    name: str = ""

    #: Maximum attempts including the first. ``1`` disables retry.
    max_attempts: int = 3

    #: Base back-off (seconds) for exponential backoff. Effective wait
    #: on attempt ``n`` is ``backoff_base * 2 ** (n - 1)``, capped at
    #: :attr:`backoff_max`.
    backoff_base: float = 1.0
    backoff_max: float = 30.0

    def __init__(self) -> None:
        if not self.name:
            raise ValueError(
                f"{type(self).__name__} must set a non-empty `name` attribute"
            )

    @abstractmethod
    async def run(self, session: Session) -> dict[str, Any]:
        """Execute one pass of the job.

        Return a metrics dict (can be empty). Exceptions propagate; the
        :class:`JobRunner` converts them into retryable/terminal logs.
        """
        raise NotImplementedError


def utcnow() -> datetime:
    """tz-aware UTC ``datetime.now`` — factored out for freezegun."""
    return datetime.now(tz=timezone.utc)
