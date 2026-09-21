"""Saved searches.

A saved search is a named filter over jobs already in the database, not a
separate crawl. Discovery is profile-driven and runs once for everything; these
are lenses onto the result, which keeps one hourly sweep serving every view.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")

    # A JobQuery, stored as given. Validated against the Pydantic query model
    # on write, so an unusable search can never be saved.
    query: Mapped[dict] = mapped_column(JSON, default=dict)

    pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Seeded on first boot; distinguishes shipped defaults from the
    # candidate's own, so defaults can be refreshed without destroying theirs.
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
