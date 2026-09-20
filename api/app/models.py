"""Database tables.

A posting is identified by a fingerprint of company plus normalised title,
not by its URL. Most ATS platforms mint a fresh URL when a posting is edited,
and without a stable key the same job is announced as new every time someone
fixes a typo in it.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def fingerprint(company: str, title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", f"{company}|{title}".lower())[:90]


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(90), primary_key=True)

    company: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(400))
    url: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(60), index=True)
    tier: Mapped[str] = mapped_column(String(16), default="NORMAL", index=True)
    salary: Mapped[str] = mapped_column(String(80), default="")

    posted_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    # Derived from flags. A plain indexed boolean beats querying inside JSON
    # for the one question the dashboard actually asks of it.
    has_flags: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Lowercased company, title, location and skills, so free-text search is a
    # single LIKE against one indexed column instead of four casts.
    search_blob: Mapped[str] = mapped_column(Text, default="")

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # True until the sweep that follows the one that introduced it.
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # False once a sweep no longer finds it -- the posting closed.
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # ---- yours to set, never touched by a sweep ----
    starred: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="new", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    applied_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    draft_folder: Mapped[str] = mapped_column(String(300), default="")

    __table_args__ = (
        Index("ix_jobs_board", "is_open", "hidden", "score"),
        Index("ix_jobs_recent", "is_open", "posted_on"),
    )


class Sweep(Base):
    """One run of the collector. Gives the dashboard a real history."""

    __tablename__ = "sweeps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    postings_fetched: Mapped[int] = mapped_column(Integer, default=0)
    matched: Mapped[int] = mapped_column(Integer, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, default=0)
    closed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    drafts_written: Mapped[int] = mapped_column(Integer, default=0)

    sources_ok: Mapped[int] = mapped_column(Integer, default=0)
    sources_total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    error: Mapped[str] = mapped_column(Text, default="")

    problems: Mapped[list[SourceProblem]] = relationship(
        back_populates="sweep", cascade="all, delete-orphan"
    )


class SourceProblem(Base):
    """A source that failed during a sweep. Shown rather than swallowed."""

    __tablename__ = "source_problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sweep_id: Mapped[int] = mapped_column(ForeignKey("sweeps.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str] = mapped_column(String(400))

    sweep: Mapped[Sweep] = relationship(back_populates="problems")
