"""Companies and the watchlist.

A company row exists for every employer worth checking directly, including the
ones with no machine-readable careers endpoint. Those carry `adapter = None`
and are surfaced in the dashboard as one-click links -- saying "this cannot be
automated" is more useful than silently omitting the employer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CompanyTier, utcnow


class SourceStatus:
    """What is actually known about reaching this employer's jobs.

    The distinction that matters is between "we have not managed to read this"
    and "this cannot be read". Both are honest; neither is "monitored".
    """

    #: A verified endpoint that returned postings.
    LIVE = "live"
    #: A verified endpoint that answered with nothing open. Normal for a
    #: forty-person company, and not a fault.
    IDLE = "idle"
    #: Answering, but failing often enough that results are incomplete.
    DEGRADED = "degraded"
    #: Refusing us for now. Backed off rather than retried harder.
    RATE_LIMITED = "rate_limited"
    #: No machine-readable source exists. Listed for one-click checking.
    MANUAL = "manual"
    #: Had a working source; it stopped answering.
    BROKEN = "broken"

    AUTOMATED = frozenset({LIVE, IDLE, DEGRADED, RATE_LIMITED, BROKEN})


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)     # slug
    name: Mapped[str] = mapped_column(String(200), index=True)
    tier: Mapped[str] = mapped_column(String(12), default=CompanyTier.NORMAL, index=True)

    # None for watchlist-only employers.
    adapter: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    adapter_arg: Mapped[str | None] = mapped_column(String(200), nullable=True)
    careers_url: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str] = mapped_column(String(80), default="", index=True)

    # ---- group structure -------------------------------------------------
    # Volkswagen Group -> Audi, Porsche, MAN, Scania; Lufthansa Group -> SWISS,
    # Austrian, Eurowings. The vacancy keeps the legal employer that posted it;
    # this only records who owns whom, so the interface can group them.
    parent_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    #: Other names the same employer posts under, for matching a board result
    #: back to a known company: "BMW AG", "BMW Group", "Bayerische Motoren Werke".
    aliases: Mapped[list] = mapped_column(JSON, default=list)

    country: Mapped[str] = mapped_column(String(8), default="", index=True)

    # ---- source honesty --------------------------------------------------
    #: See :class:`SourceStatus`. Never "monitored" unless something fetches.
    source_status: Mapped[str] = mapped_column(
        String(16), default=SourceStatus.MANUAL, index=True
    )
    #: When this source was last proven to work, by a scan or by the verifier.
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Empty for configured employers; the provider name for one that arrived
    #: through a job board and was created automatically.
    discovered_from: Mapped[str] = mapped_column(String(40), default="")

    # Set to false for an employer that should be skipped without deleting the
    # configuration that describes how to reach it.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    open_roles: Mapped[int] = mapped_column(Integer, default=0)
    new_roles_7d: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def is_automated(self) -> bool:
        return bool(self.adapter)
