"""Job listing, detail, and the fields a human owns."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.deps import profile_dep
from app.models import ApplicationStatus, Company, CompanyTier, Job, StatusEvent, utcnow
from app.models.base import LanguageRequirement
from app.providers import BOARD_PROVIDERS, REGISTRY
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
    only_unseen: bool = False,
    official_only: bool = False,
    english_compatible: bool = False,
    min_relevance: int | None = None,
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
    if only_unseen:
        stmt = stmt.where(Job.reviewed_at.is_(None))
    if official_only:
        stmt = stmt.where(Job.source.in_(set(REGISTRY) - set(BOARD_PROVIDERS)))
    if min_relevance is not None:
        stmt = stmt.where(Job.field_relevance >= min_relevance)
    if english_compatible:
        stmt = stmt.where(Job.language_requirement.in_((
            LanguageRequirement.ENGLISH_ONLY, LanguageRequirement.ENGLISH_PREFERRED,
            LanguageRequirement.GERMAN_OPTIONAL, LanguageRequirement.GERMAN_BASIC,
            LanguageRequirement.UNCLEAR,
        )))
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


#: How much each ingredient moves the recommended ordering, in score-points.
#:
#: Deliberately small next to the match score, which is already a weighted
#: judgement of fit. These answer the question the score cannot: of two roles
#: that fit equally well, which should be read first? A fortnight-old 80 and a
#: three-hour-old 80 are not equally urgent, and the older one is often already
#: on a shortlist by the time it is opened.
RECOMMEND_WEIGHTS = {
    "posted_today": 10,
    "posted_3_days": 6,
    "posted_week": 2,
    "tier_dream": 12,
    "tier_high": 5,
    "language_easy": 6,      # English-only, English-preferred, German optional
    "language_hard": -10,    # B2 and above, on top of the score's own penalty
}


def _recommend_rank():
    """Ordering for the default view: what to read first this morning.

    Sorting by score alone buries a role posted three hours ago behind one
    that has been open a fortnight, and sorting by date alone puts a 34 above
    an 88. Neither is what a person scanning their morning list wants.

    This is a SQL expression rather than a stored column on purpose: freshness
    changes every hour without anything being rewritten, and the tier can be
    changed from the Companies screen and must take effect on the next page
    load rather than the next scan.
    """
    today = date.today()

    freshness = case(
        (Job.posted_at >= today - timedelta(days=1), RECOMMEND_WEIGHTS["posted_today"]),
        (Job.posted_at >= today - timedelta(days=3), RECOMMEND_WEIGHTS["posted_3_days"]),
        (Job.posted_at >= today - timedelta(days=7), RECOMMEND_WEIGHTS["posted_week"]),
        else_=0,
    )
    # Company.tier rather than Job.tier: the job's copy is written by the scan
    # that found it, so promoting an employer in the UI would not show up here
    # until the next run.
    priority = case(
        (Company.tier == CompanyTier.DREAM, RECOMMEND_WEIGHTS["tier_dream"]),
        (Company.tier == CompanyTier.HIGH, RECOMMEND_WEIGHTS["tier_high"]),
        else_=0,
    )
    language = case(
        (
            Job.language_requirement.in_((
                LanguageRequirement.ENGLISH_ONLY,
                LanguageRequirement.ENGLISH_PREFERRED,
                LanguageRequirement.GERMAN_OPTIONAL,
                LanguageRequirement.GERMAN_BASIC,
            )),
            RECOMMEND_WEIGHTS["language_easy"],
        ),
        (
            Job.language_requirement.in_((
                LanguageRequirement.GERMAN_B2,
                LanguageRequirement.GERMAN_C1_PLUS,
                LanguageRequirement.GERMAN_NATIVE,
            )),
            RECOMMEND_WEIGHTS["language_hard"],
        ),
        else_=0,
    )
    # Location is already 20% of the match score and carries its own penalty
    # for somewhere unreachable, so it is not added a third time here.
    return Job.score + freshness + priority + language


def apply_sort(stmt: Select, sort: SortKey) -> Select:
    columns = {"field_relevance": Job.field_relevance, "experience": Job.score_experience,
               "language": Job.score_language, "location": Job.score_location}
    if sort in columns:
        return stmt.order_by(columns[sort].desc().nullslast(), Job.score.desc(), Job.id.asc())
    if sort == "company_priority":
        return stmt.outerjoin(Company, Job.company_id == Company.id).order_by(
            case((Company.tier == "dream", 3), (Company.tier == "high", 2), else_=1).desc(),
            Job.score.desc(), Job.id.asc(),
        )
    if sort == "recommended":
        # Outer, not inner: a role from an employer the registry has not caught
        # up with yet must still be rankable, just without a tier bonus.
        return stmt.outerjoin(Company, Job.company_id == Company.id).order_by(
            _recommend_rank().desc(),
            Job.posted_at.desc().nullslast(),
            Job.id.asc(),          # stable, so paging cannot repeat a row
        )
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
    max_age_days: int | None = Query(None, ge=0, le=365),
    salary_min: int | None = Query(None, ge=0),
    only_new: bool = False,
    only_unseen: bool = False,
    official_only: bool = False,
    english_compatible: bool = False,
    min_relevance: int | None = Query(None, ge=0, le=100),
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
        only_unseen=only_unseen, official_only=official_only,
        english_compatible=english_compatible, min_relevance=min_relevance,
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
