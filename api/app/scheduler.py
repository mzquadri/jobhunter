"""The hourly sweep.

APScheduler lives inside the API process rather than in a separate worker.
For one user and a sweep that takes about twenty seconds that is the right
size of machinery; a queue and a broker would be more moving parts than the
job deserves.

`max_instances=1` and `coalesce=True` mean a slow sweep can never stack up
behind itself.
"""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.collector.pipeline import run_sweep
from app.db import SessionLocal
from app.settings import get_profile, get_settings

log = logging.getLogger(__name__)

JOB_ID = "sweep"
_scheduler: BackgroundScheduler | None = None


def sweep_job() -> None:
    session = SessionLocal()
    try:
        sweep = run_sweep(session, get_profile(), get_settings())
        log.info(
            "sweep %s finished in %dms: %d matched, %d new, %d closed",
            sweep.status, sweep.duration_ms, sweep.matched, sweep.new_jobs, sweep.closed_jobs,
        )
    except Exception:
        log.exception("scheduled sweep raised")
    finally:
        session.close()


def start() -> BackgroundScheduler | None:
    global _scheduler
    settings = get_settings()
    minutes = settings.sweep_interval_minutes
    if minutes <= 0:
        log.info("SWEEP_INTERVAL_MINUTES is 0; the scheduler stays off")
        return None

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        sweep_job,
        trigger=IntervalTrigger(minutes=minutes),
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    sched.start()
    _scheduler = sched
    log.info("scheduler started; sweeping every %d minutes", minutes)
    return sched


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_run_time() -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None
