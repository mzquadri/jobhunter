"""Turning a completed scan into things worth telling the user.

Every signal is derived from rows that a scan actually wrote. Nothing here
invents activity to make the interface look busy: if a scan found nothing, the
feed says so, because a dashboard that manufactures events is worse than an
empty one -- it trains you to ignore it.

One store, two presentations. The overview reads the most recent entries as a
"Career Signals" feed; the bell reads the same rows with their unread state.
Two parallel systems would inevitably disagree.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    CompanyTier,
    Job,
    Notification,
    Run,
    utcnow,
)
from app.settings import Profile

log = logging.getLogger(__name__)

# Notification kinds, kept as constants so the UI and the generator agree.
HIGH_MATCH = "high_match"
DREAM_COMPANY = "dream_company"
RUN_FAILED = "run_failed"
JOB_CLOSED = "job_closed"
FOLLOW_UP_DUE = "follow_up_due"
SCAN_SUMMARY = "scan_summary"


def _exists(session: Session, dedupe_key: str) -> bool:
    return session.scalars(
        select(Notification.id).where(Notification.dedupe_key == dedupe_key).limit(1)
    ).first() is not None


def _add(
    session: Session,
    *,
    kind: str,
    title: str,
    body: str = "",
    href: str = "",
    severity: str = "info",
    dedupe_key: str,
    job_id: str | None = None,
    company_id: str | None = None,
) -> Notification | None:
    """Create a notification unless an identical one already exists.

    The dedupe key is what stops a standing condition -- a role that stays
    open, a source that stays broken -- from producing the same alert every
    hour until the feed is useless.
    """
    if _exists(session, dedupe_key):
        return None
    row = Notification(
        kind=kind, title=title, body=body, href=href, severity=severity,
        dedupe_key=dedupe_key, job_id=job_id, company_id=company_id,
    )
    session.add(row)
    return row


def generate_for_run(session: Session, run: Run, profile: Profile,
                     new_job_ids: set[str]) -> int:
    """Create notifications for what one scan changed. Returns how many."""
    prefs = (profile.raw.get("notifications") or {}) if hasattr(profile, "raw") else {}
    threshold = int(prefs.get("high_match_threshold", 80))
    created = 0

    # --- a scan that could not complete properly -------------------------
    if prefs.get("notify_run_failed", True) and run.errors_count:
        created += bool(_add(
            session,
            kind=RUN_FAILED,
            title=f"{run.errors_count} source{'s' if run.errors_count != 1 else ''} "
                  "did not answer",
            body=f"{run.providers_ok} of {run.providers_checked} sources responded. "
                 "Affected employers may have roles that were not seen.",
            href="/automation",
            severity="warning",
            dedupe_key=f"run:{run.id}:errors",
        ))

    if not new_job_ids:
        # A scan that found nothing new is worth recording once, so the feed
        # distinguishes "nothing was posted" from "nothing ran".
        if run.status in ("ok", "partial"):
            created += bool(_add(
                session,
                kind=SCAN_SUMMARY,
                title="No new roles this scan",
                body=f"{run.postings_seen:,} postings checked across "
                     f"{run.providers_ok} sources.",
                href="/jobs",
                severity="muted",
                dedupe_key=f"run:{run.id}:empty",
            ))
        session.commit()
        return created

    new_jobs = session.scalars(
        select(Job).where(Job.id.in_(new_job_ids)).order_by(Job.score.desc())
    ).all()

    # --- individually strong roles ---------------------------------------
    if prefs.get("notify_high_match", True):
        for job in (j for j in new_jobs if j.score >= threshold):
            created += bool(_add(
                session,
                kind=HIGH_MATCH,
                title=f"Strong match: {job.title}",
                body=f"{job.company_name} · {job.city or job.location_raw or 'location not stated'}"
                     f" · {job.score}% match",
                href=f"/jobs/{job.id}",
                severity="success",
                dedupe_key=f"high:{job.id}",
                job_id=job.id,
                company_id=job.company_id,
            ))

    # --- shortlisted employers hiring ------------------------------------
    if prefs.get("notify_dream_company", True):
        dream_ids = {
            c.id for c in session.scalars(
                select(Company).where(Company.tier.in_(
                    (CompanyTier.DREAM, CompanyTier.HIGH)
                ))
            ).all()
        }
        by_company: dict[str, list[Job]] = {}
        for job in new_jobs:
            if job.company_id in dream_ids:
                by_company.setdefault(job.company_id, []).append(job)

        for company_id, jobs in by_company.items():
            company = session.get(Company, company_id)
            if company is None:
                continue
            count = len(jobs)
            created += bool(_add(
                session,
                kind=DREAM_COMPANY,
                title=f"{company.name} posted {count} new role{'s' if count != 1 else ''}",
                body=", ".join(j.title for j in jobs[:3])
                     + (f" and {count - 3} more" if count > 3 else ""),
                href=f"/companies/{company.id}",
                severity="success",
                dedupe_key=f"dream:{run.id}:{company.id}",
                company_id=company.id,
            ))

    # --- a saved role that has gone --------------------------------------
    if prefs.get("notify_job_closed", True):
        closed = session.scalars(
            select(Job).where(
                Job.is_open.is_(False),
                Job.starred.is_(True),
                Job.removed_at.is_not(None),
                Job.removed_at >= utcnow() - timedelta(hours=2),
            )
        ).all()
        for job in closed:
            created += bool(_add(
                session,
                kind=JOB_CLOSED,
                title=f"A saved role closed: {job.title}",
                body=f"{job.company_name} is no longer advertising this position.",
                href=f"/jobs/{job.id}",
                severity="warning",
                dedupe_key=f"closed:{job.id}",
                job_id=job.id,
            ))

    session.commit()
    return created


def generate_follow_up_reminders(session: Session, profile: Profile) -> int:
    """Applications whose follow-up date has arrived.

    Separate from a scan: this is about the user's own pipeline, and should
    fire whether or not discovery ran.
    """
    prefs = (profile.raw.get("notifications") or {}) if hasattr(profile, "raw") else {}
    if not prefs.get("notify_follow_up_due", True):
        return 0

    due = session.scalars(
        select(Job).where(
            Job.follow_up_at.is_not(None),
            Job.follow_up_at <= date.today(),
        )
    ).all()

    created = 0
    for job in due:
        created += bool(_add(
            session,
            kind=FOLLOW_UP_DUE,
            title=f"Follow up on {job.company_name}",
            body=f"{job.title} · due {job.follow_up_at}",
            href=f"/jobs/{job.id}",
            severity="info",
            # Keyed by date, so it fires once per day rather than per scan.
            dedupe_key=f"followup:{job.id}:{job.follow_up_at}",
            job_id=job.id,
        ))
    session.commit()
    return created


def prune(session: Session, keep_days: int = 30) -> int:
    """Drop read notifications older than the window."""
    cutoff = utcnow() - timedelta(days=keep_days)
    stale = session.scalars(
        select(Notification).where(
            Notification.created_at < cutoff,
            Notification.read_at.is_not(None),
        )
    ).all()
    for row in stale:
        session.delete(row)
    session.commit()
    return len(stale)


def unread_count(session: Session) -> int:
    return session.scalar(
        select(func.count()).select_from(Notification).where(Notification.read_at.is_(None))
    ) or 0
