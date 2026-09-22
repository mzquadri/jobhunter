"""Job listing, detail, and the fields a human owns."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.deps import profile_dep
from app.models import ApplicationStatus, Company, Job, StatusEvent, utcnow
from app.routers.serialize import to_detail, to_summary
from app.schemas import CountryCode, JobDetail, JobPage, JobPatch, SortKey
from app.settings import Profile

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _tier_map(session: Session) -> dict[str, str]:
    return {c.id: c.tier for c in session.scalars(select(Company)).all()}


def apply_filters(
    stmt: Select,
    profile: Profile,
    *,
    q: str | None = None,
    tier: str | None = None,
    country: CountryCode | None = None,
    city: str | None = None,
    company: str | None = None,
    category: str | None = None,
    language: str | None = None,
    source: str | None = None,
    status: ApplicationStatus | None = None,
    domain: str | None = None,
    remote: str | None = None,
    seniority: str | None = None,
    min_score: int | None = None,
    max_age_days: int | None = None,
    salary_min: int | None = None,
    only_new: bool = False,
    only_starred: bool = False,
    only_clean: bool = False,
    include_hidden: bool = False,
    include_closed: bool = False,
) -> Select:
    """One filter implementation, shared by the listing and by saved searches.

    Keeping it in a single function is what lets a saved search be executed by
    exactly the same code path as the query that created it.
    """
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
        stmt = stmt.where(Job.company_id.in_(
            select(Company.id).where(Company.tier == tier.lower())
        ))
    if status:
        stmt = stmt.where(Job.status == status)
    if language:
        stmt = stmt.where(Job.language_requirement == language)
    if source:
        stmt = stmt.where(Job.source == source)
    if seniority:
        stmt = stmt.where(Job.seniority == seniority)
    if remote:
        stmt = stmt.where(Job.remote_policy == remote)
    if category:
        stmt = stmt.where(Job.role_category == category)
    if company:
        stmt = stmt.where(Job.company_name.ilike(f"%{company}%"))
    if city:
        stmt = stmt.where(or_(Job.city.ilike(f"%{city}%"),
                              Job.location_raw.ilike(f"%{city}%")))
    if domain:
        stmt = stmt.where(Job.search_blob.like(f"%{domain.lower()}%"))
    if min_score is not None:
        stmt = stmt.where(Job.score >= min_score)
    if salary_min is not None:
        # Only postings that actually stated a figure can be compared; one
        # that stated nothing is not evidence of a low salary.
        stmt = stmt.where(Job.salary_annual_eur_min.is_not(None),
                          Job.salary_annual_eur_min >= salary_min)
    if max_age_days is not None:
        stmt = stmt.where(Job.posted_at.is_not(None),
                          Job.posted_at >= date.today() - timedelta(days=max_age_days))
    if country:
        terms = profile.country_map.get(country, [])
        if terms:
            stmt = stmt.where(or_(
                Job.country == country.upper(),
                *[Job.search_blob.like(f"%{t}%") for t in terms],
            ))
    if q:
        needle = f"%{q.lower().strip()}%"
        stmt = stmt.where(Job.search_blob.like(needle))
    return stmt


def apply_sort(stmt: Select, sort: SortKey) -> Select:
    if sort == "score":
        return stmt.order_by(Job.score.desc(), Job.posted_at.desc().nullslast())
    if sort == "company":
        return stmt.order_by(Job.company_name.asc(), Job.score.desc())
    if sort == "discovered":
        return stmt.order_by(Job.first_seen_at.desc(), Job.score.desc())
    if sort == "salary":
        return stmt.order_by(Job.salary_annual_eur_min.desc().nullslast(), Job.score.desc())
    return stmt.order_by(Job.posted_at.desc().nullslast(), Job.score.desc())


@router.get("", response_model=JobPage, summary="List and filter job postings")
def list_jobs(
    response: Response,
    session: Session = Depends(get_session),
    profile: Profile = Depends(profile_dep),
    q: str | None = Query(None, description="Free text over company, title, city and skills"),
    tier: str | None = Query(None, description="dream, high or normal"),
    country: CountryCode | None = None,
    city: str | None = None,
    company: str | None = None,
    category: str | None = Query(None, description="Role category, e.g. 'Computer Vision'"),
    language: str | None = Query(None, description="Language requirement level"),
    source: str | None = None,
    status: ApplicationStatus | None = None,
    domain: str | None = None,
    remote: str | None = Query(None, description="remote, hybrid, onsite or unknown"),
    seniority: str | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    max_age_days: int | None = Query(None, ge=1, le=365),
    salary_min: int | None = Query(None, ge=0),
    only_new: bool = False,
    only_starred: bool = False,
    only_clean: bool = Query(False, description="Hide anything carrying a warning flag"),
    include_hidden: bool = False,
    include_closed: bool = False,
    sort: SortKey = "newest",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JobPage:
    stmt = apply_filters(
        select(Job), profile,
        q=q, tier=tier, country=country, city=city, company=company, category=category,
        language=language, source=source, status=status, domain=domain, remote=remote,
        seniority=seniority, min_score=min_score, max_age_days=max_age_days,
        salary_min=salary_min, only_new=only_new, only_starred=only_starred,
        only_clean=only_clean, include_hidden=include_hidden, include_closed=include_closed,
    )
    # Count in the database rather than materialising every matching row.
    total = session.scalar(
        select(func.count()).select_from(stmt.with_only_columns(Job.id).subquery())
    ) or 0

    rows = session.scalars(
        apply_sort(stmt, sort).limit(limit).offset(offset)
    ).all()

    tiers = _tier_map(session)
    items = [to_summary(job, tiers.get(job.company_id or "", "normal")) for job in rows]

    response.headers["X-Total-Count"] = str(total)
    return JobPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobDetail, summary="One posting in full")
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobDetail:
    job = session.scalars(
        select(Job)
        .options(selectinload(Job.sources), selectinload(Job.history))
        .where(Job.id == job_id)
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="No job with that id")
    tiers = _tier_map(session)
    return to_detail(job, tiers.get(job.company_id or "", "normal"))


@router.patch("/{job_id}", response_model=JobDetail, summary="Update your own fields")
def patch_job(
    job_id: str,
    patch: JobPatch,
    session: Session = Depends(get_session),
    profile: Profile = Depends(profile_dep),
) -> JobDetail:
    """Update the fields a human owns.

    A discovery run never writes these, so nothing here can be lost to a
    sweep. A status change is recorded in the history rather than only
    overwriting the current value.
    """
    job = session.scalars(
        select(Job)
        .options(selectinload(Job.sources), selectinload(Job.history))
        .where(Job.id == job_id)
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="No job with that id")

    data = patch.model_dump(exclude_unset=True)
    note = data.pop("status_note", "") or ""

    new_status = data.get("status")
    if new_status and new_status != job.status:
        session.add(StatusEvent(
            job_id=job.id, from_status=job.status, to_status=new_status, note=note,
        ))
        job.status_changed_at = utcnow()
        # Applying is the one transition with an obvious date; fill it in
        # rather than making the candidate type today's date.
        if new_status == ApplicationStatus.APPLIED and not job.applied_at \
                and "applied_at" not in data:
            data["applied_at"] = date.today()
            # And a follow-up date, so the reminder this product promises can
            # actually fire. The delay is a setting, never a guess: at 0 no
            # date is set, and a date the candidate typed is left alone.
            after = int((profile.raw.get("notifications") or {}).get("follow_up_after_days", 7))
            if after > 0 and not job.follow_up_at and "follow_up_at" not in data:
                data["follow_up_at"] = date.today() + timedelta(days=after)

    for key, value in data.items():
        setattr(job, key, value)

    session.commit()
    session.refresh(job)
    tiers = _tier_map(session)
    return to_detail(job, tiers.get(job.company_id or "", "normal"))
