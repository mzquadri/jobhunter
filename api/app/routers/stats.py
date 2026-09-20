"""Everything the dashboard header needs, in one request."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Job, Sweep
from app.schemas import DayCount, Stats, SweepOut, WatchlistItem
from app.settings import Profile, get_profile

router = APIRouter(prefix="/api", tags=["stats"])


def _count(session: Session, *conditions) -> int:
    stmt = select(func.count()).select_from(Job).where(
        Job.is_open.is_(True), Job.hidden.is_(False), *conditions
    )
    return session.scalar(stmt) or 0


@router.get("/stats", response_model=Stats)
def stats(
    session: Session = Depends(get_session),
    profile: Profile = Depends(get_profile),
) -> Stats:
    today = date.today()
    window = profile.max_age_days

    rows = session.execute(
        select(Job.posted_on, func.count())
        .where(
            Job.is_open.is_(True),
            Job.hidden.is_(False),
            Job.posted_on.is_not(None),
            Job.posted_on >= today - timedelta(days=window),
        )
        .group_by(Job.posted_on)
    ).all()
    per_day = {posted: n for posted, n in rows}

    histogram = [
        DayCount(
            day=today - timedelta(days=age),
            label=(today - timedelta(days=age)).strftime("%a %d %b"),
            age_days=age,
            count=per_day.get(today - timedelta(days=age), 0),
        )
        for age in range(window, -1, -1)
    ]

    last = session.scalars(
        select(Sweep)
        .options(selectinload(Sweep.problems))
        .where(Sweep.status != "running")
        .order_by(Sweep.started_at.desc())
        .limit(1)
    ).first()

    next_at = None
    if last and last.finished_at:
        from app.scheduler import next_run_time

        next_at = next_run_time()

    return Stats(
        total_open=_count(session),
        fresh_48h=_count(
            session, Job.posted_on.is_not(None), Job.posted_on >= today - timedelta(days=2)
        ),
        new_since_last_sweep=_count(session, Job.is_new.is_(True)),
        dream=_count(session, Job.tier == "DREAM"),
        no_warnings=_count(session, Job.has_flags.is_(False)),
        starred=_count(session, Job.starred.is_(True)),
        applied=session.scalar(
            select(func.count()).select_from(Job).where(Job.status == "applied")
        ) or 0,
        max_age_days=window,
        headline=profile.headline,
        histogram=histogram,
        last_sweep=SweepOut.model_validate(last) if last else None,
        next_sweep_at=next_at,
        watchlist=[WatchlistItem(**w) for w in profile.watchlist],
    )
