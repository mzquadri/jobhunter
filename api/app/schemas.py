"""Response and request shapes. Pydantic keeps the API contract explicit."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Flag(BaseModel):
    code: str
    why: str = ""


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company: str
    title: str
    url: str
    location: str
    source: str
    tier: str
    salary: str
    posted_on: date | None
    score: int
    flags: list[Flag]
    skills: list[str]
    domains: list[str]
    first_seen: datetime
    last_seen: datetime
    is_new: bool
    is_open: bool
    starred: bool
    hidden: bool
    status: str
    notes: str
    applied_on: date | None
    draft_folder: str
    excerpt: str = ""
    age_days: int | None = None


class JobPage(BaseModel):
    items: list[JobOut]
    total: int
    limit: int
    offset: int


class JobPatch(BaseModel):
    """Only the fields a human owns. A sweep never writes these."""

    starred: bool | None = None
    hidden: bool | None = None
    status: str | None = Field(default=None, max_length=24)
    notes: str | None = None
    applied_on: date | None = None


class DayCount(BaseModel):
    day: date
    label: str
    age_days: int
    count: int


class SourceProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    detail: str


class SweepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int
    postings_fetched: int
    matched: int
    new_jobs: int
    closed_jobs: int
    drafts_written: int
    sources_ok: int
    sources_total: int
    status: str
    error: str
    problems: list[SourceProblemOut] = []


class WatchlistItem(BaseModel):
    name: str
    url: str


class Stats(BaseModel):
    total_open: int
    fresh_48h: int
    new_since_last_sweep: int
    dream: int
    no_warnings: int
    starred: int
    applied: int
    max_age_days: int
    headline: str
    histogram: list[DayCount]
    last_sweep: SweepOut | None
    next_sweep_at: datetime | None
    watchlist: list[WatchlistItem]
