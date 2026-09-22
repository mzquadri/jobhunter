"""The endpoints the application itself needs.

Everything here exists so the user never has to open a terminal, Swagger or a
SQL client: starting a scan, reading settings, changing them, seeing what
happened and what it means.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import profile_dep
from app.enrich.language import LANGUAGE_LABELS
from app.enrich.seniority import SENIORITY_LABELS
from app.models import (
    PENDING_STATUSES,
    ApplicationStatus,
    Job,
    Notification,
    Run,
    SalaryBasis,
    utcnow,
)
from app.schemas import (
    Analytics,
    DayCount,
    FunnelStage,
    NamedCount,
    NotificationOut,
    NotificationPage,
    OnboardingState,
    SalaryBand,
    ScanStateOut,
    SettingsOut,
)
from app.services import profile_service, scans, signals
from app.settings import Profile

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])
scans_router = APIRouter(prefix="/api/scans", tags=["scans"])
notifications_router = APIRouter(prefix="/api/notifications", tags=["notifications"])
analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
@settings_router.get("", response_model=SettingsOut, summary="Current settings")
def read_settings(session: Session = Depends(get_session)) -> SettingsOut:
    row = profile_service.seed_if_missing(session)
    return SettingsOut(
        profile=row.profile,
        onboarded=row.onboarded,
        seeded_from=row.seeded_from,
        updated_at=row.updated_at,
    )


@settings_router.patch("", response_model=SettingsOut, summary="Update some settings")
def patch_settings(
    patch: dict = Body(..., description="Partial document; sections merge, lists replace"),
    session: Session = Depends(get_session),
) -> SettingsOut:
    """Merge an update into the stored settings.

    Validated before it is written, so a malformed section is refused with a
    readable message rather than breaking the next scan.
    """
    try:
        row = profile_service.update_document(session, patch)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_readable(exc)) from exc
    return SettingsOut(
        profile=row.profile, onboarded=row.onboarded,
        seeded_from=row.seeded_from, updated_at=row.updated_at,
    )


@settings_router.put("", response_model=SettingsOut, summary="Replace all settings")
def replace_settings(
    document: dict = Body(...), session: Session = Depends(get_session)
) -> SettingsOut:
    try:
        row = profile_service.replace_document(session, document)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_readable(exc)) from exc
    return SettingsOut(
        profile=row.profile, onboarded=row.onboarded,
        seeded_from=row.seeded_from, updated_at=row.updated_at,
    )


@settings_router.post("/reset", response_model=SettingsOut, summary="Restore defaults")
def reset_settings(session: Session = Depends(get_session)) -> SettingsOut:
    row = profile_service.reset_to_seed(session)
    return SettingsOut(
        profile=row.profile, onboarded=row.onboarded,
        seeded_from=row.seeded_from, updated_at=row.updated_at,
    )


@settings_router.get("/onboarding", response_model=OnboardingState)
def onboarding_state(session: Session = Depends(get_session)) -> OnboardingState:
    """Whether to show the wizard or the dashboard."""
    row = profile_service.seed_if_missing(session)
    has_jobs = session.scalar(select(func.count()).select_from(Job)) or 0
    has_run = session.scalar(select(func.count()).select_from(Run)) or 0
    return OnboardingState(
        onboarded=row.onboarded, has_jobs=has_jobs > 0, has_run=has_run > 0
    )


@settings_router.post("/onboarding/complete", response_model=SettingsOut)
def complete_onboarding(
    document: dict | None = Body(default=None),
    session: Session = Depends(get_session),
) -> SettingsOut:
    """Save what the wizard collected and mark setup finished."""
    if document:
        try:
            profile_service.update_document(session, document)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_readable(exc)) from exc
    row = profile_service.mark_onboarded(session)
    return SettingsOut(
        profile=row.profile, onboarded=row.onboarded,
        seeded_from=row.seeded_from, updated_at=row.updated_at,
    )


def _readable(exc: ValidationError) -> str:
    """Turn a Pydantic error into one sentence a person can act on."""
    parts = []
    for error in exc.errors()[:4]:
        where = ".".join(str(p) for p in error["loc"]) or "document"
        parts.append(f"{where}: {error['msg']}")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# scans
# ---------------------------------------------------------------------------
@scans_router.get("", response_model=ScanStateOut, summary="What the scanner is doing")
def scan_status(session: Session = Depends(get_session)) -> ScanStateOut:
    return ScanStateOut(**vars(scans.scan_state(session)))


@scans_router.post("", response_model=ScanStateOut, status_code=202,
                   summary="Start a scan now")
def start_scan(session: Session = Depends(get_session)) -> ScanStateOut:
    """Request a scan.

    Answers 409 when one is already in progress, so the interface can say so
    rather than appearing to do nothing.
    """
    started, state = scans.request_scan(session, triggered_by="manual")
    if not started:
        raise HTTPException(
            status_code=409,
            detail=f"A scan started {state.started_at:%H:%M} is still running.",
        )
    return ScanStateOut(**vars(scans.scan_state(session)))


# ---------------------------------------------------------------------------
# notifications and signals
# ---------------------------------------------------------------------------
@notifications_router.get("", response_model=NotificationPage)
def list_notifications(
    session: Session = Depends(get_session),
    limit: int = Query(30, ge=1, le=200),
    unread_only: bool = False,
) -> NotificationPage:
    stmt = select(Notification).order_by(Notification.created_at.desc())
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = session.scalars(stmt.limit(limit)).all()
    return NotificationPage(
        items=[NotificationOut.model_validate(r) for r in rows],
        unread=signals.unread_count(session),
    )


@notifications_router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, session: Session = Depends(get_session)) -> NotificationOut:
    row = session.get(Notification, notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No notification with that id")
    row.read_at = row.read_at or utcnow()
    session.commit()
    session.refresh(row)
    return NotificationOut.model_validate(row)


@notifications_router.post("/read-all", response_model=NotificationPage)
def mark_all_read(session: Session = Depends(get_session)) -> NotificationPage:
    now = utcnow()
    for row in session.scalars(
        select(Notification).where(Notification.read_at.is_(None))
    ).all():
        row.read_at = now
    session.commit()
    return list_notifications(session=session)


@notifications_router.get("/signals", response_model=list[NotificationOut],
                          summary="Recent activity, for the overview feed")
def career_signals(
    session: Session = Depends(get_session), limit: int = Query(8, ge=1, le=40)
) -> list[NotificationOut]:
    """The same store the bell reads, presented as a feed.

    Two separate systems would eventually disagree about what happened.
    """
    rows = session.scalars(
        select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    ).all()
    return [NotificationOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------
@analytics_router.get("", response_model=Analytics, summary="Aggregates for the charts")
def analytics(
    session: Session = Depends(get_session),
    profile: Profile = Depends(profile_dep),
    days: int = Query(30, ge=7, le=365),
) -> Analytics:
    today = date.today()

    def grouped(column, limit: int = 12, labeller=None) -> list[NamedCount]:
        rows = session.execute(
            select(column, func.count())
            .where(Job.is_open.is_(True), Job.hidden.is_(False),
                   column.is_not(None), column != "")
            .group_by(column).order_by(func.count().desc()).limit(limit)
        ).all()
        return [
            NamedCount(key=str(k), label=labeller(k) if labeller else str(k), count=c)
            for k, c in rows
        ]

    # Discovery over time uses first_seen_at: this chart is about what the
    # scanner found, not when employers published.
    since = utcnow() - timedelta(days=days)
    per_day = dict(
        session.execute(
            select(func.date(Job.first_seen_at), func.count())
            .where(Job.first_seen_at >= since)
            .group_by(func.date(Job.first_seen_at))
        ).all()
    )
    discovered = []
    for age in range(days, -1, -1):
        day = today - timedelta(days=age)
        count = per_day.get(day) or per_day.get(day.isoformat()) or 0
        discovered.append(
            DayCount(day=day, label=day.strftime("%d %b"), age_days=age, count=int(count))
        )

    score_band = case(
        (Job.score >= 80, "80-100"), (Job.score >= 60, "60-79"),
        (Job.score >= 40, "40-59"), else_="under 40",
    )
    fresh_band = case(
        (Job.posted_at >= today - timedelta(days=1), "today"),
        (Job.posted_at >= today - timedelta(days=3), "1-3 days"),
        (Job.posted_at >= today - timedelta(days=7), "4-7 days"),
        else_="over a week",
    )

    def banded(expr, order: list[str]) -> list[NamedCount]:
        rows = session.execute(
            select(expr, func.count())
            .where(Job.is_open.is_(True), Job.hidden.is_(False))
            .group_by(expr)
        ).all()
        found = {str(k): c for k, c in rows}
        return [NamedCount(key=k, label=k, count=found.get(k, 0)) for k in order]

    # Salary is only charted from figures an employer actually printed.
    # Coverage is reported alongside, so a band built on four postings is not
    # mistaken for a market rate.
    salaried = session.scalars(
        select(Job.salary_annual_eur_min).where(
            Job.is_open.is_(True), Job.hidden.is_(False),
            Job.salary_basis == SalaryBasis.EXPLICIT,
            Job.salary_annual_eur_min.is_not(None),
        )
    ).all()
    total_open = session.scalar(
        select(func.count()).select_from(Job)
        .where(Job.is_open.is_(True), Job.hidden.is_(False))
    ) or 0

    bands = [(0, "under 50k"), (50_000, "50–65k"), (65_000, "65–80k"),
             (80_000, "80–100k"), (100_000, "over 100k")]
    salary_bands = []
    for index, (floor, label) in enumerate(bands):
        ceiling = bands[index + 1][0] if index + 1 < len(bands) else float("inf")
        count = sum(1 for value in salaried if floor <= value < ceiling)
        salary_bands.append(SalaryBand(label=label, count=count, floor=floor))

    funnel_order: list[tuple[str, str]] = [
        ("interested", "Interested"), ("to_apply", "To apply"),
        ("applied", "Applied"), ("interview", "Interview"),
        ("technical_interview", "Technical"), ("offer", "Offer"),
    ]
    status_counts = dict(
        session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    funnel = [
        FunnelStage(key=key, label=label, count=int(status_counts.get(key, 0)))
        for key, label in funnel_order
    ]

    return Analytics(
        discovered_by_day=discovered,
        by_country=grouped(Job.country),
        by_category=grouped(Job.role_category),
        by_company=grouped(Job.company_name, limit=10),
        by_language=grouped(
            Job.language_requirement,
            labeller=lambda k: LANGUAGE_LABELS.get(str(k), str(k)),
        ),
        by_seniority=grouped(
            Job.seniority, labeller=lambda k: SENIORITY_LABELS.get(str(k), str(k))
        ),
        by_source=grouped(Job.source),
        score_distribution=banded(score_band, ["80-100", "60-79", "40-59", "under 40"]),
        freshness_distribution=banded(
            fresh_band, ["today", "1-3 days", "4-7 days", "over a week"]
        ),
        salary_bands=salary_bands,
        salary_coverage=round(len(salaried) / total_open, 3) if total_open else 0.0,
        funnel=funnel,
        totals={
            "open": total_open,
            "with_salary": len(salaried),
            "applications": int(
                session.scalar(
                    select(func.count()).select_from(Job)
                    .where(Job.status != ApplicationStatus.NEW)
                ) or 0
            ),
            "pending": int(
                session.scalar(
                    select(func.count()).select_from(Job)
                    .where(Job.status.in_(tuple(PENDING_STATUSES)))
                ) or 0
            ),
            "window_days": profile.max_age_days,
        },
    )
