"""Everything the dashboard overview needs, in one request."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import profile_dep
from app.enrich.language import LANGUAGE_LABELS
from app.models import PENDING_STATUSES, ApplicationStatus, Company, Job, Run
from app.models.base import RunStatus
from app.schemas import Charts, CompanyOut, DayCount, NamedCount, RunOut, Stats
from app.services import scans
from app.settings import Profile

router = APIRouter(prefix="/api", tags=["stats"])

HIGH_MATCH = 70


def _open(*conditions):
    return select(func.count()).select_from(Job).where(
        Job.is_open.is_(True), Job.hidden.is_(False), *conditions
    )


@router.get("/stats", response_model=Stats, summary="Dashboard overview and charts")
def stats(
    session: Session = Depends(get_session),
    profile: Profile = Depends(profile_dep),
) -> Stats:
    today = date.today()
    window = profile.max_age_days

    total_open = session.scalar(_open()) or 0
    found_today = session.scalar(
        _open(func.date(Job.first_seen_at) == today)
    ) or 0
    new_since = session.scalar(_open(Job.is_new.is_(True))) or 0
    high_match = session.scalar(_open(Job.score >= HIGH_MATCH)) or 0
    average = session.scalar(
        select(func.avg(Job.score)).where(Job.is_open.is_(True), Job.hidden.is_(False))
    )

    pending = session.scalar(
        select(func.count()).select_from(Job)
        .where(Job.status.in_(tuple(PENDING_STATUSES)))
    ) or 0
    submitted = session.scalar(
        select(func.count()).select_from(Job).where(Job.status != ApplicationStatus.NEW,
                                                    Job.applied_at.is_not(None))
    ) or 0
    companies_with_roles = session.scalar(
        select(func.count(func.distinct(Job.company_name)))
        .where(Job.is_open.is_(True), Job.hidden.is_(False))
    ) or 0

    last_run = session.scalars(
        select(Run).where(Run.status != RunStatus.RUNNING)
        .order_by(Run.started_at.desc()).limit(1)
    ).first()

    # Deliberately the same answer /api/scans gives. This used to read the API
    # process's own SWEEP_INTERVAL_MINUTES, which is 0 so that the API never
    # scans -- so the overview's "next scan" line was permanently blank while
    # the worker was scanning happily every hour.
    next_run_at = scans.scan_state(session).next_run_at

    watchlist = session.scalars(
        select(Company).where(Company.adapter.is_(None), Company.enabled.is_(True))
        .order_by(Company.tier.asc(), Company.name.asc())
    ).all()

    return Stats(
        found_today=found_today,
        new_since_last_run=new_since,
        high_match=high_match,
        total_open=total_open,
        applications_pending=pending,
        applications_submitted=submitted,
        companies_with_roles=companies_with_roles,
        average_match_score=round(float(average or 0), 1),
        max_age_days=window,
        headline=profile.headline,
        charts=_charts(session, window),
        last_run=RunOut.model_validate(last_run) if last_run else None,
        next_run_at=next_run_at,
        watchlist=[_company(c) for c in watchlist],
    )


def _company(row: Company) -> CompanyOut:
    out = CompanyOut.model_validate(row)
    out.is_automated = bool(row.adapter)
    return out


def _charts(session: Session, window: int) -> Charts:
    today = date.today()

    per_day = dict(session.execute(
        select(Job.posted_at, func.count())
        .where(Job.is_open.is_(True), Job.hidden.is_(False), Job.posted_at.is_not(None),
               Job.posted_at >= today - timedelta(days=window))
        .group_by(Job.posted_at)
    ).all())
    by_day = [
        DayCount(
            day=today - timedelta(days=age),
            label=(today - timedelta(days=age)).strftime("%a %d %b"),
            age_days=age,
            count=per_day.get(today - timedelta(days=age), 0),
        )
        for age in range(window, -1, -1)
    ]

    def grouped(column, limit: int = 12, labeller=None) -> list[NamedCount]:
        rows = session.execute(
            select(column, func.count())
            .where(Job.is_open.is_(True), Job.hidden.is_(False), column.is_not(None),
                   column != "")
            .group_by(column).order_by(func.count().desc()).limit(limit)
        ).all()
        return [
            NamedCount(key=str(key), label=(labeller(key) if labeller else str(key)),
                       count=count)
            for key, count in rows
        ]

    # Score bands, computed in SQL so the chart matches the listing exactly.
    band = case(
        (Job.score >= 80, "80-100"),
        (Job.score >= 60, "60-79"),
        (Job.score >= 40, "40-59"),
        else_="under 40",
    )
    band_rows = session.execute(
        select(band, func.count())
        .where(Job.is_open.is_(True), Job.hidden.is_(False))
        .group_by(band)
    ).all()
    order = {"80-100": 0, "60-79": 1, "40-59": 2, "under 40": 3}
    by_score = sorted(
        (NamedCount(key=str(k), label=str(k), count=c) for k, c in band_rows),
        key=lambda n: order.get(n.key, 9),
    )

    return Charts(
        by_day=by_day,
        by_country=grouped(Job.country),
        by_category=grouped(Job.role_category),
        by_company=grouped(Job.company_name),
        by_language=grouped(
            Job.language_requirement,
            labeller=lambda k: LANGUAGE_LABELS.get(str(k), str(k)),
        ),
        by_score_band=by_score,
    )
