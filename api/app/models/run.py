"""Discovery runs and provider health.

A run that returned nothing because six sources quietly broke looks identical
to a run where nothing was posted -- unless the difference is recorded. These
tables exist so the dashboard can always answer "did it actually work?".
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ProviderState, RunStatus, utcnow


class Run(Base):
    """One pass over every enabled source."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default=RunStatus.RUNNING, index=True)
    # Which process ran it, so concurrent workers can be told apart in the log.
    triggered_by: Mapped[str] = mapped_column(String(40), default="scheduler")
    error: Mapped[str] = mapped_column(Text, default="")

    providers_checked: Mapped[int] = mapped_column(Integer, default=0)
    providers_ok: Mapped[int] = mapped_column(Integer, default=0)
    companies_checked: Mapped[int] = mapped_column(Integer, default=0)
    postings_seen: Mapped[int] = mapped_column(Integer, default=0)
    postings_relevant: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_merged: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_closed: Mapped[int] = mapped_column(Integer, default=0)
    drafts_written: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)

    providers: Mapped[list[RunProvider]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class RunProvider(Base):
    """What one source did during one run."""

    __tablename__ = "run_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)

    provider: Mapped[str] = mapped_column(String(40), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")   # company or board name
    state: Mapped[str] = mapped_column(String(16), default=ProviderState.HEALTHY, index=True)
    postings: Mapped[int] = mapped_column(Integer, default=0)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")

    # What this source can and cannot do, discovered at runtime. Workday's
    # posting-date facet is per-tenant configuration: Airbus exposes it, Roche
    # does not. Recording that as a capability stops a permanent difference in
    # configuration being logged forever as an hourly failure.
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[Run] = relationship(back_populates="providers")

    __table_args__ = (Index("ix_run_providers_lookup", "run_id", "state"),)


class ProviderHealth(Base):
    """Rolling health per source, carried across runs so a failing provider can
    be backed off instead of hammered every hour."""

    __tablename__ = "provider_health"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)  # "provider:target"
    provider: Mapped[str] = mapped_column(String(40), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")

    state: Mapped[str] = mapped_column(String(16), default=ProviderState.HEALTHY, index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    # While set in the future, the source is skipped.
    backoff_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    # Internal conditional-fetch state. Not exposed by the health API.
    fetch_state: Mapped[dict] = mapped_column(JSON, default=dict)

    @property
    def success_rate(self) -> float:
        return 0.0 if not self.total_runs else 1 - (self.total_failures / self.total_runs)
