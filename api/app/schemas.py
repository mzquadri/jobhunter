"""Request and response shapes.

Pydantic keeps the API contract explicit, and the dashboard's TypeScript types
are generated from the OpenAPI document these produce -- so the contract has
one definition and the two sides cannot drift apart.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enrich.language import LANGUAGE_LABELS
from app.enrich.location import REMOTE_LABELS
from app.enrich.seniority import SENIORITY_LABELS
from app.models.base import ApplicationStatus, SalaryBasis

SortKey = Literal["newest", "score", "company", "discovered", "salary"]
CountryCode = Literal["de", "ch", "at", "nl", "eu"]


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------
class Flag(BaseModel):
    code: str
    why: str = ""
    evidence: str = ""


class SubScores(BaseModel):
    technical: int
    experience: int
    language: int
    location: int
    education: int
    freshness: int
    domain: int


class Salary(BaseModel):
    """Two figures with different meanings, kept apart on purpose.

    ``amount_*`` is exactly what the posting printed. ``annual_eur_*`` is
    annualised and converted, so it is always derived -- ``is_derived`` says
    when, and the interface marks those with a "≈".
    """

    basis: SalaryBasis
    amount_min: float | None = None
    amount_max: float | None = None
    currency: str = ""
    period: str = ""
    annual_eur_min: float | None = None
    annual_eur_max: float | None = None
    evidence: str = ""
    display: str = ""
    is_derived: bool = False


class JobSummary(BaseModel):
    """The listing row. Deliberately lighter than the detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    company_id: str | None = None
    title: str
    url: str
    location_raw: str
    city: str
    country: str
    remote_policy: str
    source: str
    tier: str = "normal"

    posted_at: date | None
    first_seen_at: datetime
    age_days: int | None = None
    is_new: bool
    is_open: bool

    score: int
    sub_scores: SubScores
    match_reasons: list[str] = []
    match_gaps: list[str] = []
    flags: list[Flag] = []

    seniority: str
    seniority_label: str = ""
    experience_min_years: int | None = None
    language_requirement: str
    language_label: str = ""
    remote_label: str = ""
    salary: Salary
    skills: list[str] = []
    domains: list[str] = []
    role_category: str = ""

    status: ApplicationStatus
    starred: bool
    hidden: bool
    applied_at: date | None = None
    follow_up_at: date | None = None
    draft_folder: str = ""


class JobSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    external_id: str
    url: str
    posted_at: date | None
    first_seen_at: datetime
    last_seen_at: datetime
    is_primary: bool


class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str
    to_status: str
    note: str
    at: datetime


class JobDetail(JobSummary):
    """Everything about one posting, including its provenance and history."""

    description: str = ""
    summary: str = ""
    language_evidence: str = ""
    employment_type: str
    last_seen_at: datetime
    removed_at: datetime | None = None
    times_seen: int = 1
    notes: str = ""
    contact_person: str = ""
    salary_discussion: str = ""
    sources: list[JobSourceOut] = []
    history: list[StatusEventOut] = []


class JobPage(BaseModel):
    items: list[JobSummary]
    total: int
    limit: int
    offset: int


class JobPatch(BaseModel):
    """Only the fields a human owns. A discovery run never writes these."""

    model_config = ConfigDict(extra="forbid")

    starred: bool | None = None
    hidden: bool | None = None
    status: ApplicationStatus | None = None
    notes: Annotated[str, Field(max_length=20_000)] | None = None
    contact_person: Annotated[str, Field(max_length=200)] | None = None
    salary_discussion: Annotated[str, Field(max_length=5_000)] | None = None
    applied_at: date | None = None
    follow_up_at: date | None = None
    status_note: Annotated[str, Field(max_length=2_000)] | None = None


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------
class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tier: str
    industry: str
    adapter: str | None
    careers_url: str
    enabled: bool
    open_roles: int
    new_roles_7d: int
    last_checked_at: datetime | None
    notes: str = ""
    is_automated: bool = False


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------
class RunProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    target: str
    state: str
    postings: int
    requests_made: int
    duration_ms: int
    error: str
    capabilities: dict = {}


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int
    status: str
    triggered_by: str
    error: str

    providers_checked: int
    providers_ok: int
    companies_checked: int
    postings_seen: int
    postings_relevant: int
    duplicates_merged: int
    jobs_new: int
    jobs_updated: int
    jobs_closed: int
    drafts_written: int
    errors_count: int


class RunDetail(RunOut):
    providers: list[RunProviderOut] = []


class ProviderHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    provider: str
    target: str
    state: str
    consecutive_failures: int
    total_runs: int
    total_failures: int
    last_ok_at: datetime | None
    last_error_at: datetime | None
    last_error: str
    backoff_until: datetime | None
    capabilities: dict = {}
    success_rate: float = 0.0


# ---------------------------------------------------------------------------
# saved searches
# ---------------------------------------------------------------------------
class SavedSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    query: dict
    pinned: bool
    is_builtin: bool
    created_at: datetime


class SavedSearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=300)] = ""
    query: dict = {}
    pinned: bool = False

    @field_validator("query")
    @classmethod
    def query_must_be_usable(cls, value: dict) -> dict:
        """Reject a search that could never be executed.

        Validating on write means a saved search cannot fail later with a
        confusing error from deep inside the query builder.
        """
        allowed = {
            "q", "tier", "country", "city", "company", "category", "language",
            "source", "status", "domain", "remote", "seniority",
            "min_score", "max_age_days", "salary_min", "only_new",
            "only_starred", "only_clean", "sort",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown filter(s): {', '.join(sorted(unknown))}")
        return value


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------
class DayCount(BaseModel):
    day: date
    label: str
    age_days: int
    count: int


class NamedCount(BaseModel):
    key: str
    label: str
    count: int


class Charts(BaseModel):
    by_day: list[DayCount]
    by_country: list[NamedCount]
    by_category: list[NamedCount]
    by_company: list[NamedCount]
    by_language: list[NamedCount]
    by_score_band: list[NamedCount]


class Stats(BaseModel):
    found_today: int
    new_since_last_run: int
    high_match: int
    total_open: int
    applications_pending: int
    applications_submitted: int
    companies_with_roles: int
    average_match_score: float
    max_age_days: int
    headline: str

    charts: Charts
    last_run: RunOut | None
    next_run_at: datetime | None
    watchlist: list[CompanyOut] = []


# ---------------------------------------------------------------------------
# helpers shared by routers
# ---------------------------------------------------------------------------
def label_job(job: JobSummary) -> JobSummary:
    """Fill the display labels, so the API and dashboard cannot disagree."""
    job.language_label = LANGUAGE_LABELS.get(job.language_requirement, "Not stated")
    job.seniority_label = SENIORITY_LABELS.get(job.seniority, "Not stated")
    job.remote_label = REMOTE_LABELS.get(job.remote_policy, "Not stated")
    return job
