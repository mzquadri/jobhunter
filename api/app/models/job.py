"""Jobs, their provenance, and the history of how the candidate engaged with them.

Three deliberate separations, because the spec is explicit that manufactured
data is worse than absent data:

  * what the employer said       -- posted_at, salary_* with basis=explicit
  * what we observed             -- first_seen_at, last_seen_at, removed_at
  * what we inferred             -- seniority, language_requirement, skills,
                                    salary with basis=estimated

Nothing in the first group is ever written by an inference step, and anything
in the third carries enough evidence to audit it.

A second separation matters just as much: sweep-owned columns versus
human-owned columns. A sweep refreshes the former on every run and must never
touch the latter, so re-running discovery can never destroy application state.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    ApplicationStatus,
    Base,
    EmploymentType,
    LanguageRequirement,
    RemotePolicy,
    SalaryBasis,
    Seniority,
    utcnow,
)


class Job(Base):
    """One real vacancy, however many sources reported it."""

    __tablename__ = "jobs"

    # Deterministic dedup key: company slug + normalised title + location key.
    # Not the URL -- most ATS platforms mint a fresh URL when a posting is
    # edited, which would make every typo fix look like a new job.
    id: Mapped[str] = mapped_column(String(120), primary_key=True)

    # ---- identity -------------------------------------------------------
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_name: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(400))
    title_normalized: Mapped[str] = mapped_column(String(400), index=True)
    url: Mapped[str] = mapped_column(Text)
    # The provider whose sighting won the merge. Denormalised from
    # job_sources so the listing can show and filter on it without a join.
    source: Mapped[str] = mapped_column(String(40), default="", index=True)

    # ---- as published ---------------------------------------------------
    location_raw: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(120), default="", index=True)
    country: Mapped[str] = mapped_column(String(80), default="", index=True)
    remote_policy: Mapped[str] = mapped_column(String(16), default=RemotePolicy.UNKNOWN, index=True)
    employment_type: Mapped[str] = mapped_column(
        String(24), default=EmploymentType.UNKNOWN, index=True
    )
    description: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # ---- as observed by this system -------------------------------------
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # True only until the run after the one that introduced it.
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)

    # ---- inferred -------------------------------------------------------
    seniority: Mapped[str] = mapped_column(String(16), default=Seniority.UNKNOWN, index=True)
    experience_min_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_max_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    language_requirement: Mapped[str] = mapped_column(
        String(24), default=LanguageRequirement.UNCLEAR, index=True
    )
    language_evidence: Mapped[str] = mapped_column(String(400), default="")

    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(8), default="")
    salary_period: Mapped[str] = mapped_column(String(16), default="")
    salary_annual_eur_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_annual_eur_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_basis: Mapped[str] = mapped_column(String(12), default=SalaryBasis.UNKNOWN, index=True)
    salary_evidence: Mapped[str] = mapped_column(String(400), default="")

    skills: Mapped[list] = mapped_column(JSON, default=list)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    role_category: Mapped[str] = mapped_column(String(48), default="", index=True)

    # ---- match, all explainable ----------------------------------------
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    field_relevance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_evidence: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    score_technical: Mapped[int] = mapped_column(Integer, default=0)
    score_experience: Mapped[int] = mapped_column(Integer, default=0)
    score_language: Mapped[int] = mapped_column(Integer, default=0)
    score_location: Mapped[int] = mapped_column(Integer, default=0)
    score_education: Mapped[int] = mapped_column(Integer, default=0)
    score_freshness: Mapped[int] = mapped_column(Integer, default=0)
    score_domain: Mapped[int] = mapped_column(Integer, default=0)
    match_reasons: Mapped[list] = mapped_column(JSON, default=list)
    match_gaps: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    has_flags: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Lowercased company, title, location, skills and domains, so free-text
    # search is one indexed LIKE rather than four casts across JSON columns.
    search_blob: Mapped[str] = mapped_column(Text, default="")

    # ---- owned by the candidate; a sweep must never write these ---------
    status: Mapped[str] = mapped_column(String(24), default=ApplicationStatus.NEW, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    contact_person: Mapped[str] = mapped_column(String(200), default="")
    salary_discussion: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    starred: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    draft_folder: Mapped[str] = mapped_column(String(300), default="")

    sources: Mapped[list[JobSource]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )
    history: Mapped[list[StatusEvent]] = relationship(
        back_populates="job", cascade="all, delete-orphan",
        order_by="StatusEvent.at.desc()",
    )

    __table_args__ = (
        # The dashboard's default query: open, not hidden, newest first.
        Index("ix_jobs_board", "is_open", "hidden", "posted_at", "score"),
        Index("ix_jobs_pipeline", "status", "follow_up_at"),
        Index("ix_jobs_company_title", "company_name", "title_normalized"),
    )


class JobSource(Base):
    """One provider's sighting of a job. Several rows per job is the point:
    when a vacancy appears on both Greenhouse and the company's own site, the
    dashboard shows it once and this table records both."""

    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )

    provider: Mapped[str] = mapped_column(String(40), index=True)
    # Whatever the provider calls this posting -- requisition id, slug, path.
    external_id: Mapped[str] = mapped_column(String(300), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The record that won when duplicates were merged.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    job: Mapped[Job] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint("job_id", "provider", "external_id", name="uq_job_source"),
    )


class StatusEvent(Base):
    """Application status transitions, so the pipeline has a history rather
    than only a current value."""

    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str] = mapped_column(String(24), default="")
    to_status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    job: Mapped[Job] = relationship(back_populates="history")
