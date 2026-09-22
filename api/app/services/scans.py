"""Starting a scan from the application, and reporting what it is doing.

The user should never need a terminal to refresh their jobs, so the UI needs
a way to ask for a scan and a way to watch one. Both live here.

Concurrency is handled by the same PostgreSQL advisory lock the scheduled
worker uses, so a button press and an hourly tick cannot both ingest the same
sweep. The API does not take the lock itself -- it starts a background task
that does, exactly as the worker would.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, advisory_lock
from app.models import Company, Run, RunStatus, utcnow
from app.services.discovery import run_discovery
from app.services.profile_service import load_document, load_profile
from app.settings import get_settings

log = logging.getLogger(__name__)

# A run that has been "running" for longer than this is assumed dead -- a
# worker killed mid-sweep leaves the row behind, and without this the UI would
# refuse to start another scan forever.
STALE_RUN_AFTER = timedelta(minutes=30)


@dataclass
class IndustryProgress:
    """How far one industry's employers have got, this run.

    Counted from run_providers rows the scan has already committed, so the
    numbers are completed work rather than an animated estimate. §67 asks for
    "Automotive 42 / 48", and 42 has to mean forty-two sources actually
    finished.
    """

    key: str
    label: str
    done: int
    total: int
    postings: int = 0


@dataclass
class ScanState:
    running: bool
    run_id: int | None = None
    started_at: datetime | None = None
    triggered_by: str = ""
    # Sources finished so far, from run_providers rows written as it goes.
    providers_done: int = 0
    providers_total: int = 0
    postings_seen: int = 0
    next_run_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_status: str = ""
    by_industry: list[IndustryProgress] = field(default_factory=list)


def current_run(session: Session) -> Run | None:
    """The scan in progress, if one genuinely is.

    A row stuck in `running` past the staleness window is treated as finished
    and marked failed, rather than blocking every future scan.
    """
    row = session.scalars(
        select(Run).where(Run.status == RunStatus.RUNNING)
        .order_by(Run.started_at.desc()).limit(1)
    ).first()
    if row is None:
        return None

    if row.started_at and utcnow() - row.started_at > STALE_RUN_AFTER:
        log.warning("run %s has been running for over %s; marking it failed",
                    row.id, STALE_RUN_AFTER)
        row.status = RunStatus.FAILED
        row.error = "The worker stopped before this run finished."
        row.finished_at = utcnow()
        session.commit()
        return None

    return row


def scan_state(session: Session) -> ScanState:
    """Everything the UI needs to show scan status, in one query set."""
    running = current_run(session)
    last = session.scalars(
        select(Run).where(Run.status != RunStatus.RUNNING)
        .order_by(Run.started_at.desc()).limit(1)
    ).first()

    # The cadence is a user setting, not this process's environment. The API
    # deliberately runs with scanning disabled, so reading its own interval
    # here would always report "no next scan" while the worker was happily
    # scanning every hour.
    automation = load_document(session).automation
    interval = automation.scan_interval_minutes if automation.enabled else 0
    next_at = None
    if last and last.started_at and interval > 0:
        next_at = last.started_at + timedelta(minutes=interval)

    if running is None:
        return ScanState(
            running=False,
            next_run_at=next_at,
            last_finished_at=last.finished_at if last else None,
            last_status=last.status if last else "",
        )

    # Progress comes from rows the run has already committed, so it is real
    # rather than an animated guess.
    done = len(running.providers or [])
    return ScanState(
        running=True,
        run_id=running.id,
        started_at=running.started_at,
        triggered_by=running.triggered_by,
        providers_done=done,
        providers_total=running.providers_checked or 0,
        postings_seen=running.postings_seen or 0,
        next_run_at=next_at,
        last_finished_at=last.finished_at if last else None,
        last_status=last.status if last else "",
        by_industry=_industry_progress(session, running),
    )


def _industry_progress(session: Session, run: Run) -> list[IndustryProgress]:
    """Per-industry completion for the run in progress.

    `total` is every employer whose source this run intends to ask, taken from
    the registry. `done` is how many of them have written a run_providers row.
    Boards are not employers and are grouped separately rather than being
    silently folded into whichever industry they happened to surface.
    """
    industries = dict(session.execute(
        select(Company.name, Company.industry)
        .where(Company.enabled.is_(True), Company.adapter.is_not(None))
    ).all())
    if not industries:
        return []

    totals: dict[str, int] = {}
    for industry in industries.values():
        key = industry or "other"
        totals[key] = totals.get(key, 0) + 1

    done: dict[str, int] = {}
    postings: dict[str, int] = {}
    for row in run.providers or []:
        # run_providers.target holds the employer name for company sources and
        # the provider's own name for boards.
        industry = industries.get(row.target)
        if industry is None:
            continue
        key = industry or "other"
        done[key] = done.get(key, 0) + 1
        postings[key] = postings.get(key, 0) + (row.postings or 0)

    return sorted(
        (
            IndustryProgress(
                key=key,
                label=key.replace("_", " ").title() if key != "other" else "Other",
                done=done.get(key, 0),
                total=total,
                postings=postings.get(key, 0),
            )
            for key, total in totals.items()
        ),
        key=lambda i: (-i.total, i.label),
    )


def _scan_worker(triggered_by: str) -> None:
    """Run one scan on a background thread, guarded by the advisory lock."""
    session = SessionLocal()
    try:
        with advisory_lock(session) as acquired:
            if not acquired:
                log.info("a scan is already running elsewhere; the request was ignored")
                return
            run_discovery(session, load_profile(session), get_settings(), triggered_by)
    except Exception:
        log.exception("a manually requested scan failed")
    finally:
        session.close()


def request_scan(session: Session, triggered_by: str = "manual") -> tuple[bool, ScanState]:
    """Ask for a scan.

    Returns ``(started, state)``. ``started`` is False when one is already in
    progress, which the API turns into a 409 so the interface can say so
    plainly rather than silently doing nothing.
    """
    state = scan_state(session)
    if state.running:
        return False, state

    threading.Thread(
        target=_scan_worker, args=(triggered_by,), name="manual-scan", daemon=True
    ).start()

    # The thread needs a moment to create its Run row; the UI polls for the
    # rest, so there is nothing to wait on here.
    return True, state
