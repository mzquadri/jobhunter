"""Companies and the watchlist.

A company row exists for every employer worth checking directly, including the
ones with no machine-readable careers endpoint. Those carry `adapter = None`
and are surfaced in the dashboard as one-click links -- saying "this cannot be
automated" is more useful than silently omitting the employer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CompanyTier, utcnow


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
