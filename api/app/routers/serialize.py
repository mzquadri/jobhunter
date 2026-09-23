"""Turning ORM rows into response models.

Kept in one place so the listing and the detail view can never disagree about
what a field means -- particularly the salary, where the difference between
"what the employer printed" and "what we derived" has to survive all the way
to the screen.
"""

from __future__ import annotations

from datetime import date

from app.enrich.salary import SalaryVerdict, format_salary
from app.models import Job
from app.models.base import SalaryBasis
from app.schemas import (
    Flag,
    JobDetail,
    JobSourceOut,
    JobSummary,
    Salary,
    StatusEventOut,
    SubScores,
    label_job,
)


def _salary(job: Job) -> Salary:
    verdict = SalaryVerdict(
        basis=job.salary_basis or SalaryBasis.UNKNOWN,
        amount_min=job.salary_min,
        amount_max=job.salary_max,
        currency=job.salary_currency or "",
        period=job.salary_period or "",
        annual_eur_min=job.salary_annual_eur_min,
        annual_eur_max=job.salary_annual_eur_max,
        evidence=job.salary_evidence or "",
    )
    # A figure is derived whenever it had to be annualised or converted.
    derived = bool(verdict.found) and (
        (verdict.currency or "EUR") != "EUR" or (verdict.period or "year") != "year"
    )
    return Salary(
        basis=verdict.basis,
        amount_min=verdict.amount_min,
        amount_max=verdict.amount_max,
        currency=verdict.currency,
        period=verdict.period,
        annual_eur_min=verdict.annual_eur_min,
        annual_eur_max=verdict.annual_eur_max,
        evidence=verdict.evidence,
        display=format_salary(verdict),
        is_derived=derived,
    )


def _age(job: Job) -> int | None:
    """Days since the employer published it, or None when no date was given.

    None rather than 0: an undated posting must never be ranked or displayed
    as though it appeared today.
    """
    return (date.today() - job.posted_at).days if job.posted_at else None


def _base_fields(job: Job, tier: str) -> dict:
    return {
        "id": job.id,
        "company_name": job.company_name,
        "company_id": job.company_id,
        "title": job.title,
        "url": job.url,
        "location_raw": job.location_raw,
        "city": job.city,
        "country": job.country,
        "remote_policy": job.remote_policy,
        "source": job.source,
        "tier": tier,
        "posted_at": job.posted_at,
        "first_seen_at": job.first_seen_at,
        "age_days": _age(job),
        "is_new": job.is_new,
        "is_open": job.is_open,
        "score": job.score,
        "field_relevance": job.field_relevance,
        "field_evidence": job.field_evidence or "",
        "reviewed_at": job.reviewed_at,
        "sub_scores": SubScores(
            technical=job.score_technical,
            experience=job.score_experience,
            language=job.score_language,
            location=job.score_location,
            education=job.score_education,
            freshness=job.score_freshness,
            domain=job.score_domain,
        ),
        "match_reasons": job.match_reasons or [],
        "match_gaps": job.match_gaps or [],
        "flags": [Flag(**f) for f in (job.flags or [])],
        "seniority": job.seniority,
        "experience_min_years": job.experience_min_years,
        "language_requirement": job.language_requirement,
        "salary": _salary(job),
        "skills": job.skills or [],
        "domains": job.domains or [],
        "role_category": job.role_category,
        "status": job.status,
        "starred": job.starred,
        "hidden": job.hidden,
        "applied_at": job.applied_at,
        "follow_up_at": job.follow_up_at,
        "draft_folder": job.draft_folder,
    }


def to_summary(job: Job, tier: str = "normal") -> JobSummary:
    return label_job(JobSummary(**_base_fields(job, tier)))


def to_detail(job: Job, tier: str = "normal") -> JobDetail:
    detail = JobDetail(
        **_base_fields(job, tier),
        description=job.description or "",
        requirements=job.requirements or [],
        summary=job.summary or "",
        language_evidence=job.language_evidence or "",
        employment_type=job.employment_type,
        last_seen_at=job.last_seen_at,
        removed_at=job.removed_at,
        times_seen=job.times_seen or 1,
        notes=job.notes or "",
        contact_person=job.contact_person or "",
        salary_discussion=job.salary_discussion or "",
        sources=[JobSourceOut.model_validate(s) for s in job.sources],
        history=[StatusEventOut.model_validate(h) for h in job.history],
    )
    label_job(detail)
    return detail
