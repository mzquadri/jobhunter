"""Sweep history, and triggering one by hand."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.collector.pipeline import run_sweep
from app.db import SessionLocal, get_session
from app.models import Sweep
from app.schemas import SweepOut
from app.settings import get_profile, get_settings

router = APIRouter(prefix="/api/sweeps", tags=["sweeps"])


@router.get("", response_model=list[SweepOut])
def list_sweeps(limit: int = 20, session: Session = Depends(get_session)) -> list[SweepOut]:
    rows = session.scalars(
        select(Sweep)
        .options(selectinload(Sweep.problems))
        .order_by(Sweep.started_at.desc())
        .limit(min(limit, 100))
    ).all()
    return [SweepOut.model_validate(r) for r in rows]


def _sweep_now() -> None:
    """Runs on a background worker with its own session."""
    session = SessionLocal()
    try:
        run_sweep(session, get_profile(), get_settings())
    finally:
        session.close()


@router.post("", response_model=dict, status_code=202)
def trigger_sweep(
    background: BackgroundTasks, session: Session = Depends(get_session)
) -> dict:
    running = session.scalars(
        select(Sweep).where(Sweep.status == "running").limit(1)
    ).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A sweep started at {running.started_at.isoformat()} is still running",
        )
    background.add_task(_sweep_now)
    return {"status": "accepted", "detail": "Sweep started; poll /api/sweeps for the result"}
