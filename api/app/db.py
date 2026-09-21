"""Engine, session factory, and the lock that keeps concurrent workers honest.

Schema changes go through Alembic, never ``create_all``. The API waits for
migrations rather than applying them, so two API replicas starting together
cannot race each other into a half-migrated database.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.settings import get_settings

log = logging.getLogger(__name__)

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,      # survives Postgres restarting under us
    pool_size=5,
    max_overflow=10,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def wait_for_db(attempts: int = 60, delay: float = 1.0) -> None:
    """Compose starts dependents as soon as the port answers, which is earlier
    than Postgres is ready to serve. Retry rather than crash-loop."""
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            if attempt == attempts:
                raise
            if attempt % 5 == 0:
                log.info("waiting for database (%d/%d)", attempt, attempts)
            time.sleep(delay)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session]:
    """Transactional scope for background work, which has no request to hang
    a dependency off."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# single-flight
# ---------------------------------------------------------------------------
# Arbitrary but fixed: the advisory-lock namespace for discovery runs.
DISCOVERY_LOCK_ID = 0x4A48_0001


@contextmanager
def advisory_lock(session: Session, lock_id: int = DISCOVERY_LOCK_ID) -> Generator[bool]:
    """Try to take a Postgres session-level advisory lock.

    This is how two workers are stopped from ingesting the same run without
    adding Redis or a broker. ``pg_try_advisory_lock`` returns immediately:
    the second worker learns it lost and skips rather than queueing up a
    duplicate sweep behind the first.

    The lock is released explicitly and is also dropped automatically if the
    connection dies, so a killed worker cannot wedge the schedule.
    """
    acquired = bool(session.execute(
        text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id}
    ).scalar())
    try:
        yield acquired
    finally:
        if acquired:
            try:
                session.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
                session.commit()
            except Exception:                       # pragma: no cover - cleanup path
                log.warning("could not release advisory lock %s", lock_id, exc_info=True)


def schema_is_ready() -> bool:
    """True once Alembic has created the core tables."""
    try:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT to_regclass('public.jobs')")).scalar())
    except OperationalError:
        return False


def wait_for_schema(attempts: int = 60, delay: float = 1.0) -> None:
    wait_for_db()
    for attempt in range(1, attempts + 1):
        if schema_is_ready():
            return
        if attempt % 5 == 0:
            log.info("waiting for migrations (%d/%d)", attempt, attempts)
        time.sleep(delay)
    raise RuntimeError(
        "Migrations have not run. The 'migrate' service applies them; "
        "check its logs with: docker compose logs migrate"
    )
