"""The discovery worker.

Runs as its own container so a sweep cannot slow the API down, and so either
can be restarted without touching the other.

Two properties the spec asks for explicitly:

  * **Schedules survive restarts.** APScheduler persists its job table in the
    same PostgreSQL the application already uses, so a restart resumes the
    existing schedule rather than starting a fresh clock.

  * **Concurrent workers cannot double-ingest.** Every run first tries a
    PostgreSQL advisory lock. ``pg_try_advisory_lock`` returns immediately, so
    a second worker learns it lost and skips rather than queueing a duplicate
    sweep behind the first. The lock is released when the connection ends, so
    a killed worker cannot wedge the schedule.

Redis and a broker were considered and rejected: the database already
provides both durability and mutual exclusion, and §22 warns against
infrastructure that exists only for decoration.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from contextlib import suppress
from datetime import datetime

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import SessionLocal, advisory_lock, engine, wait_for_schema
from app.logging_conf import configure_logging
from app.services.discovery import run_discovery
from app.settings import get_profile, get_settings

log = logging.getLogger("jobhunter.worker")

JOB_ID = "discovery"
_shutdown = threading.Event()


def sweep(triggered_by: str = "scheduler") -> None:
    """One discovery run, guarded so only one worker performs it."""
    settings = get_settings()
    with SessionLocal() as session, advisory_lock(session) as acquired:
        if not acquired:
            log.info("another worker holds the discovery lock; skipping this tick")
            return
        try:
            run = run_discovery(session, get_profile(), settings, triggered_by)
        except Exception:
            log.exception("discovery raised")
            return

        log.info(
            "run %s %s in %.1fs: %d seen, %d relevant, %d new, %d updated, "
            "%d closed, %d duplicates merged, %d drafts, %d provider errors",
            run.id, run.status, run.duration_ms / 1000, run.postings_seen,
            run.postings_relevant, run.jobs_new, run.jobs_updated, run.jobs_closed,
            run.duplicates_merged, run.drafts_written, run.errors_count,
        )


def build_scheduler(settings) -> BlockingScheduler:
    scheduler = BlockingScheduler(
        timezone="UTC",
        jobstores={"default": SQLAlchemyJobStore(engine=engine,
                                                 tablename="scheduler_jobs")},
        job_defaults={
            # A slow sweep must never stack up behind itself.
            "max_instances": 1,
            "coalesce": True,
            # Tolerate the worker being down briefly without losing the tick.
            "misfire_grace_time": 600,
        },
    )
    scheduler.add_job(
        sweep,
        trigger=IntervalTrigger(minutes=settings.sweep_interval_minutes),
        id=JOB_ID,
        name="Discovery sweep",
        replace_existing=True,
    )
    return scheduler


def main() -> int:
    settings = get_settings()
    configure_logging(settings)

    if settings.sweep_interval_minutes <= 0:
        log.info("SWEEP_INTERVAL_MINUTES is 0; the worker will idle")

    log.info("worker %s starting", settings.worker_name)
    wait_for_schema()

    if settings.sweep_on_startup:
        # In a thread so a slow first sweep does not delay the scheduler
        # taking over its own clock.
        log.info("running a sweep on startup")
        threading.Thread(
            target=sweep, args=("startup",), name="startup-sweep", daemon=True
        ).start()

    if settings.sweep_interval_minutes <= 0:
        _shutdown.wait()
        return 0

    scheduler = build_scheduler(settings)

    def stop(signum, _frame):
        log.info("signal %s received; shutting down", signum)
        scheduler.shutdown(wait=False)
        _shutdown.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    log.info("sweeping every %d minutes; next run at %s",
             settings.sweep_interval_minutes,
             datetime.now().isoformat(timespec="seconds"))
    with suppress(KeyboardInterrupt, SystemExit):
        scheduler.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
