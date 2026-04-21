"""Container entry point: ``python -m app.scheduler.main``.

Boots an :class:`AsyncIOScheduler` with every pipeline job from
:mod:`app.scheduler.registry`, and blocks on a long-lived event loop.
SIGINT / SIGTERM trigger a graceful shutdown.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from .registry import build_scheduler


def _configure_logging() -> None:
    level_name = os.environ.get("SCHEDULER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


async def _run_forever() -> None:
    log = logging.getLogger("app.scheduler")
    scheduler = build_scheduler()
    scheduler.start()
    log.info(
        "scheduler started; jobs=%s",
        [job.id for job in scheduler.get_jobs()],
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        log.info("shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:  # pragma: no cover — Windows fallback
            signal.signal(sig, lambda *_: _request_shutdown())

    try:
        await stop_event.wait()
    finally:
        log.info("scheduler shutting down …")
        scheduler.shutdown(wait=True)
        log.info("scheduler stopped cleanly")


def main() -> None:
    _configure_logging()
    asyncio.run(_run_forever())


if __name__ == "__main__":  # pragma: no cover — exercised via container
    main()
