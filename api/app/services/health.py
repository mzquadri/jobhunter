"""Provider health, carried across runs.

A source that has failed three hours running is probably not going to answer
on the fourth, and hammering it every hour is neither useful nor polite. This
records the outcome of each attempt, escalates state, and backs a source off
for a while once it is clearly down.

Backoff is deliberately not permanent: sites recover, and a source that is
never retried is a source that is silently lost.
"""

from __future__ import annotations

from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProviderHealth, ProviderState, utcnow
from app.settings import Settings


def health_key(provider: str, target: str) -> str:
    return f"{provider}:{target}"[:120]


def load_all(session: Session) -> dict[str, ProviderHealth]:
    return {row.key: row for row in session.scalars(select(ProviderHealth)).all()}


def is_backed_off(record: ProviderHealth | None) -> bool:
    if not record or not record.backoff_until:
        return False
    until = record.backoff_until
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return until > utcnow()


def record_success(
    session: Session, provider: str, target: str, capabilities: dict | None = None
) -> ProviderHealth:
    record = _get_or_create(session, provider, target)
    record.state = ProviderState.HEALTHY
    record.consecutive_failures = 0
    record.total_runs += 1
    record.last_ok_at = utcnow()
    record.backoff_until = None
    record.last_error = ""
    if capabilities:
        record.capabilities = capabilities
    return record


def record_failure(
    session: Session,
    provider: str,
    target: str,
    error: str,
    settings: Settings,
    *,
    rate_limited: bool = False,
) -> ProviderHealth:
    record = _get_or_create(session, provider, target)
    record.consecutive_failures += 1
    record.total_runs += 1
    record.total_failures += 1
    record.last_error_at = utcnow()
    record.last_error = (error or "")[:2000]

    if rate_limited:
        # Asked to slow down, not broken: a short, certain pause.
        record.state = ProviderState.RATE_LIMITED
        record.backoff_until = utcnow() + timedelta(minutes=30)
    elif record.consecutive_failures >= settings.failures_before_backoff:
        record.state = ProviderState.FAILED
        record.backoff_until = utcnow() + timedelta(minutes=settings.backoff_minutes)
    else:
        # One or two failures is noise -- a timeout, a deploy, a blip. Flag it
        # without standing the source down.
        record.state = ProviderState.DEGRADED
    return record


def record_skipped(session: Session, provider: str, target: str) -> ProviderHealth:
    record = _get_or_create(session, provider, target)
    record.state = ProviderState.SKIPPED
    return record


def _get_or_create(session: Session, provider: str, target: str) -> ProviderHealth:
    key = health_key(provider, target)
    record = session.get(ProviderHealth, key)
    if record is None:
        # Counters are initialised explicitly rather than relying on the
        # column defaults: those are applied by SQLAlchemy at INSERT, so a
        # freshly constructed row still holds None and `+= 1` raises.
        record = ProviderHealth(
            key=key, provider=provider, target=target,
            state=ProviderState.HEALTHY,
            consecutive_failures=0, total_runs=0, total_failures=0,
            capabilities={},
        )
        session.add(record)
    return record
