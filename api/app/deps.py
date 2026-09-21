"""Shared FastAPI dependencies.

Kept apart from ``app.settings`` so that the settings module stays free of
database imports, and apart from the routers so they do not each reimplement
how a profile is obtained.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.profile_service import load_profile
from app.settings import Profile


def profile_dep(session: Session = Depends(get_session)) -> Profile:
    """The current settings, read from the database on every request.

    Not cached. Settings are edited from the UI, and a cached profile is
    exactly how a saved preference silently fails to take effect. This is one
    primary-key read of a single JSON row.
    """
    return load_profile(session)
