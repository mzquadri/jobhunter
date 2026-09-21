"""Reading and writing the settings document.

One place owns this. Before, every component that wanted a preference read the
YAML itself; now they all come through here, so there is exactly one answer to
"where do settings live" and one place to change it.

The lifecycle:

  * **Before first boot** ``config/profile.yml`` is only a seed -- shipped
    defaults and an example.
  * **On first boot** if no row exists, the YAML is read, validated and
    written once.
  * **After that** the database is authoritative and the YAML is never read
    again. A preference changed in the UI takes effect on the next scan with
    no restart, rebuild or remount.

Deliberately uncached. The previous implementation wrapped profile loading in
``lru_cache``, which is precisely what would make a saved preference fail to
reach the next scan. This is one indexed primary-key read of a single JSON
row, against a scan that makes thousands of HTTP requests -- caching it would
trade correctness for nothing measurable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SETTINGS_ID, AppSettings
from app.settings import Profile, get_settings
from app.settings_schema import ProfileDocument, merge_patch, validate_profile

log = logging.getLogger(__name__)


class SettingsNotInitialised(RuntimeError):
    """No settings row, and no seed available to create one from."""


def _seed_candidates() -> list[Path]:
    """Where to look for seed defaults, best first.

    The user's own profile.yml wins when present, so an existing installation
    keeps its configuration on upgrade. The committed example is the fallback,
    which is what a fresh clone gets.
    """
    settings = get_settings()
    configured = Path(settings.profile_path)
    return [configured, configured.with_name("profile.example.yml")]


def read_seed() -> dict[str, Any] | None:
    for path in _seed_candidates():
        if path.exists():
            try:
                with path.open(encoding="utf-8") as fh:
                    loaded = yaml.safe_load(fh) or {}
                log.info("read settings seed from %s", path.name)
                return loaded
            except (OSError, yaml.YAMLError):
                log.warning("could not read seed at %s", path, exc_info=True)
    return None


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
def get_row(session: Session) -> AppSettings | None:
    return session.scalars(
        select(AppSettings).where(AppSettings.id == SETTINGS_ID)
    ).first()


def load_document(session: Session) -> ProfileDocument:
    """The validated settings document, seeding it if this is the first boot."""
    row = get_row(session) or seed_if_missing(session)
    return validate_profile(row.profile)


def load_profile(session: Session) -> Profile:
    """The accessor wrapper the collector and matcher already expect.

    Returning the existing ``Profile`` type means moving the storage from a
    file to a table changed no calling code beyond how it is obtained.
    """
    row = get_row(session) or seed_if_missing(session)
    return Profile(row.profile)


def is_onboarded(session: Session) -> bool:
    row = get_row(session)
    return bool(row and row.onboarded)


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------
def seed_if_missing(session: Session) -> AppSettings:
    """Create the settings row from the YAML seed, once.

    Safe to call on every boot: if the row exists it is returned untouched, so
    a restart can never overwrite settings the user has since changed.
    """
    existing = get_row(session)
    if existing is not None:
        return existing

    raw = read_seed()
    if raw is None:
        # An empty but valid document, so a fresh install without any config
        # still starts and can be completed through onboarding.
        log.warning("no settings seed found; starting from built-in defaults")
        document = ProfileDocument()
        source = "built-in defaults"
    else:
        try:
            document = validate_profile(raw)
            source = "config/profile.yml"
        except ValidationError as exc:
            log.error("the settings seed is invalid, falling back to defaults:\n%s", exc)
            document = ProfileDocument()
            source = "built-in defaults (seed was invalid)"

    row = AppSettings(
        id=SETTINGS_ID,
        profile=document.to_storage(),
        # A seeded install is not a configured one: onboarding decides that.
        onboarded=False,
        seeded_from=source,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    log.info("settings initialised from %s", source)
    return row


def update_document(session: Session, patch: dict[str, Any]) -> AppSettings:
    """Merge a partial update into the stored document.

    Validated before it is written, so a malformed section is rejected with a
    usable message instead of breaking the next scan.
    """
    row = get_row(session) or seed_if_missing(session)
    merged = merge_patch(row.profile or {}, patch)
    document = validate_profile(merged)            # raises ValidationError

    row.profile = document.to_storage()
    session.commit()
    session.refresh(row)
    return row


def replace_document(session: Session, document: dict[str, Any]) -> AppSettings:
    """Overwrite the whole document. Used by onboarding, which composes it."""
    row = get_row(session) or seed_if_missing(session)
    validated = validate_profile(document)
    row.profile = validated.to_storage()
    session.commit()
    session.refresh(row)
    return row


def mark_onboarded(session: Session, value: bool = True) -> AppSettings:
    row = get_row(session) or seed_if_missing(session)
    row.onboarded = value
    session.commit()
    session.refresh(row)
    return row


def reset_to_seed(session: Session) -> AppSettings:
    """Discard stored settings and re-read the shipped defaults."""
    row = get_row(session)
    if row is not None:
        session.delete(row)
        session.commit()
    return seed_if_missing(session)
