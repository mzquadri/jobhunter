"""Job listing, filtering and the fields a human owns."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Job
from app.schemas import JobOut, JobPage, JobPatch
from app.settings import Profile, get_profile

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

SortKey = Literal["newest", "score", "company"]


def _to_out(row: Job) -> JobOut:
    out = JobOut.model_validate(row)
    out.excerpt = (row.description or "")[:520]
    if row.posted_on:
        out.age_days = (date.today() - row.posted_on).days
    return out


@router.get("", response_model=JobPage)
def list_jobs(
    session: Session = Depends(get_session),
    profile: Profile = Depends(get_profile),
    q: str | None = Query(None, description="Free text over company, title, location, skills"),
    tier: str | None = Query(None, description="DREAM, PRIORITY or NORMAL"),
    country: Literal["de", "ch", "at", "eu"] | None = None,
    fresh_hours: int | None = Query(None, ge=1, le=720),
    only_new: bool = False,
    only_starred: bool = False,
    only_clean: bool = Query(False, description="Hide anything carrying a warning flag"),
    status: str | None = None,
    include_hidden: bool = False,
    include_closed: bool = False,
    min_score: int | None = None,
    sort: SortKey = "newest",
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> JobPage:
    stmt = select(Job)

    if not include_closed:
        stmt = stmt.where(Job.is_open.is_(True))
    if not include_hidden:
        stmt = stmt.where(Job.hidden.is_(False))
    if only_new:
        stmt = stmt.where(Job.is_new.is_(True))
    if only_starred:
        stmt = stmt.where(Job.starred.is_(True))
    if only_clean:
        stmt = stmt.where(Job.has_flags.is_(False))
    if tier:
        stmt = stmt.where(Job.tier == tier.upper())
    if status:
        stmt = stmt.where(Job.status == status)
    if min_score is not None:
        stmt = stmt.where(Job.score >= min_score)
    if fresh_hours:
        cutoff = date.today() - timedelta(days=max(1, fresh_hours // 24))
        stmt = stmt.where(Job.posted_on.is_not(None), Job.posted_on >= cutoff)
    if country:
        stmt = stmt.where(_country_clause(country, profile))
    if q:
        stmt = stmt.where(Job.search_blob.like(f"%{q.lower().strip()}%"))

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if sort == "score":
        stmt = stmt.order_by(Job.score.desc(), Job.posted_on.desc().nullslast())
    elif sort == "company":
        stmt = stmt.order_by(Job.company.asc(), Job.score.desc())
    else:
        stmt = stmt.order_by(Job.posted_on.desc().nullslast(), Job.score.desc())

    rows = session.scalars(stmt.limit(limit).offset(offset)).all()
    return JobPage(items=[_to_out(r) for r in rows], total=total, limit=limit, offset=offset)


def _country_clause(country: str, profile: Profile):
    """Match on the cities configured for that tier rather than a hardcoded list."""
    tiers = profile.location_tiers
    groups = {
        "de": [18, 22],
        "ch": [16],
        "at": [14],
        "eu": [11, 8],
    }
    cities: list[str] = []
    for tier in groups.get(country, []):
        cities += tiers.get(tier, [])
    if not cities:
        return Job.id.is_not(None)
    return or_(*[func.lower(Job.location).like(f"%{c}%") for c in cities])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobOut:
    row = session.get(Job, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No job with that id")
    out = _to_out(row)
    out.excerpt = row.description or ""
    return out


@router.patch("/{job_id}", response_model=JobOut)
def patch_job(
    job_id: str, patch: JobPatch, session: Session = Depends(get_session)
) -> JobOut:
    """Update the fields a human owns. Sweeps never overwrite these."""
    row = session.get(Job, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No job with that id")

    data = patch.model_dump(exclude_unset=True)
    if data.get("status") == "applied" and not row.applied_on and "applied_on" not in data:
        data["applied_on"] = datetime.now().date()
    for key, value in data.items():
        setattr(row, key, value)

    session.commit()
    session.refresh(row)
    return _to_out(row)
