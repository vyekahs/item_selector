"""Tests for :class:`app.scheduler.runner.JobRunner`.

Covers the success, retry-then-success, and final-failure paths plus
the no-raise contract (a permanently failing job must never crash the
caller).

Async paths are driven via ``asyncio.run`` to match the pattern used
by ``tests/clients/test_rate_limiter.py`` (no pytest-asyncio marker
machinery required).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.scheduler.base import ScheduledJob
from app.scheduler.runner import JobRunner


class _CountingJob(ScheduledJob):
    """Records how often :meth:`run` was called and what to do each time."""

    name = "counting"

    def __init__(self, behaviors: list[str], *, max_attempts: int = 3):
        super().__init__()
        self.max_attempts = max_attempts
        # Make retries effectively instantaneous.
        self.backoff_base = 0.0
        self.backoff_max = 0.0
        self._behaviors = behaviors
        self.calls = 0

    async def run(self, session) -> dict:  # type: ignore[override]
        self.calls += 1
        idx = min(self.calls - 1, len(self._behaviors) - 1)
        behavior = self._behaviors[idx]
        if behavior == "ok":
            return {"call": self.calls}
        if behavior == "raise":
            raise RuntimeError(f"boom-{self.calls}")
        raise AssertionError(f"unknown behavior: {behavior}")


class _FakeSession:
    """Minimal stand-in honouring the methods the runner pokes."""

    def __init__(self) -> None:
        self.rolled_back = 0
        self.closed = 0

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed += 1


def _runner(*, sleep_calls: list[float] | None = None) -> tuple[JobRunner, list[_FakeSession]]:
    """Build a runner whose ``sleep`` is captured but does no real waiting."""
    sessions: list[_FakeSession] = []

    def _factory() -> _FakeSession:
        s = _FakeSession()
        sessions.append(s)
        return s

    async def _sleep(seconds: float) -> None:
        if sleep_calls is not None:
            sleep_calls.append(seconds)

    return JobRunner(session_factory=_factory, sleep=_sleep), sessions


def test_runner_success_first_attempt():
    runner, sessions = _runner()
    job = _CountingJob(["ok"], max_attempts=3)

    result = asyncio.run(runner.execute(job))

    assert result.success is True
    assert result.attempts == 1
    assert result.metrics == {"call": 1}
    assert result.error is None
    assert job.calls == 1
    # One session opened + closed for the single attempt.
    assert len(sessions) == 1
    assert sessions[0].closed == 1


def test_runner_retries_then_succeeds():
    sleep_calls: list[float] = []
    runner, sessions = _runner(sleep_calls=sleep_calls)
    job = _CountingJob(["raise", "raise", "ok"], max_attempts=3)

    result = asyncio.run(runner.execute(job))

    assert result.success is True
    assert result.attempts == 3
    assert result.metrics == {"call": 3}
    assert job.calls == 3
    # Three attempts → three sessions; two sleeps between them.
    assert len(sessions) == 3
    assert len(sleep_calls) == 2


def test_runner_final_failure_does_not_raise():
    runner, sessions = _runner()
    job = _CountingJob(["raise"], max_attempts=3)

    result = asyncio.run(runner.execute(job))

    assert result.success is False
    assert result.attempts == 3
    assert result.error is not None
    assert "boom" in result.error
    assert job.calls == 3
    # Each failed attempt rolls back exactly once.
    assert all(s.rolled_back == 1 for s in sessions)


def test_runner_respects_max_attempts_one():
    runner, sessions = _runner()
    job = _CountingJob(["raise"], max_attempts=1)

    result = asyncio.run(runner.execute(job))

    assert result.success is False
    assert result.attempts == 1
    assert job.calls == 1
    assert len(sessions) == 1


def test_runner_log_payload_serialisable():
    runner, _ = _runner()
    job = _CountingJob(["ok"], max_attempts=1)

    result = asyncio.run(runner.execute(job))
    payload = result.to_log_dict()

    encoded = json.dumps(payload)
    assert "counting" in encoded
    assert payload["success"] is True
    assert payload["attempts"] == 1
    assert payload["error"] is None
    assert "duration_ms" in payload


def test_runner_backoff_grows_exponentially():
    sleep_calls: list[float] = []
    runner, _ = _runner(sleep_calls=sleep_calls)
    # max_attempts=4 → 3 sleeps in between.
    job = _CountingJob(["raise"] * 4, max_attempts=4)
    job.backoff_base = 1.0
    job.backoff_max = 30.0

    result = asyncio.run(runner.execute(job))

    assert result.success is False
    assert sleep_calls == [1.0, 2.0, 4.0]


def test_runner_backoff_caps_at_max():
    sleep_calls: list[float] = []
    runner, _ = _runner(sleep_calls=sleep_calls)
    job = _CountingJob(["raise"] * 5, max_attempts=5)
    job.backoff_base = 10.0
    job.backoff_max = 15.0

    asyncio.run(runner.execute(job))

    # 10, 20→capped to 15, 40→15, 80→15
    assert sleep_calls == [10.0, 15.0, 15.0, 15.0]


def test_scheduled_job_requires_name():
    class _Bad(ScheduledJob):
        name = ""

        async def run(self, session) -> dict[str, Any]:  # type: ignore[override]
            return {}

    with pytest.raises(ValueError):
        _Bad()
