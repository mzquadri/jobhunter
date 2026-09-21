"""First-boot seeding.

Copies the saved searches declared in the profile into the database, once.
Searches the candidate created themselves are never touched, and a built-in
whose definition changed in the profile is refreshed rather than duplicated.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SavedSearch
from app.settings import Profile

log = logging.getLogger(__name__)


def seed_saved_searches(session: Session, profile: Profile) -> int:
    declared = profile.saved_searches
    if not declared:
        return 0

    existing = {
        row.name: row
        for row in session.scalars(select(SavedSearch)).all()
    }

    added = 0
    for order, entry in enumerate(declared):
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        row = existing.get(name)
        if row is None:
            session.add(SavedSearch(
                name=name,
                description=str(entry.get("description") or ""),
                query=entry.get("query") or {},
                pinned=bool(entry.get("pinned", False)),
                sort_order=order,
                is_builtin=True,
            ))
            added += 1
        elif row.is_builtin:
            # Refresh the shipped definition; a search the candidate made
            # themselves keeps whatever they set.
            row.description = str(entry.get("description") or "")
            row.query = entry.get("query") or {}
            row.pinned = bool(entry.get("pinned", False))
            row.sort_order = order

    session.commit()
    if added:
        log.info("seeded %d saved searches from the profile", added)
    return added
