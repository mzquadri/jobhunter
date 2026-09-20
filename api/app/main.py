"""JobHunter API.

Collects AI/ML job postings from company ATS platforms and job boards, scores
them against a candidate profile, and serves them to the dashboard.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import scheduler
from app.db import init_db
from app.routers import jobs, stats, sweeps
from app.settings import get_settings

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("jobhunter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    if settings.sweep_on_startup:
        # In a thread so the API answers immediately; a first sweep takes about
        # twenty seconds and an empty dashboard on first boot is a poor welcome.
        log.info("running a sweep on startup")
        threading.Thread(target=scheduler.sweep_job, name="startup-sweep", daemon=True).start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="JobHunter API",
    version="1.0.0",
    summary="Job postings collected from company ATS platforms, scored against a profile.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(stats.router)
app.include_router(sweeps.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
