"""Database engine, session factory and the FastAPI dependency."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.settings import get_settings

log = logging.getLogger(__name__)

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def wait_for_db(attempts: int = 30, delay: float = 1.0) -> None:
    """Compose starts the API as soon as the port is open, which is earlier than
    Postgres is ready to answer. Retry rather than crash-loop."""
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            if attempt == attempts:
                raise
            log.info("database not ready (attempt %d/%d)", attempt, attempts)
            time.sleep(delay)


def init_db() -> None:
    wait_for_db()
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
