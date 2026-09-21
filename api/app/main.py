"""CareerOS API.

Serves the postings the worker discovers, and the fields the candidate owns.

Discovery does not run here. The worker container owns it, so restarting the
API never triggers an unscheduled crawl and a slow sweep can never make the
dashboard unresponsive.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import SessionLocal, wait_for_schema
from app.logging_conf import configure_logging
from app.routers import jobs, ops, product, stats
from app.services.discovery import sync_companies
from app.services.profile_service import load_profile, seed_if_missing
from app.services.seed import seed_saved_searches
from app.settings import get_settings

settings = get_settings()
configure_logging(settings)
log = logging.getLogger("jobhunter.api")

MUTATING = frozenset({"POST", "PATCH", "PUT", "DELETE"})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Migrations are applied by the `migrate` service, not here: two API
    # replicas starting together must not race into the same migration.
    wait_for_schema()
    with SessionLocal() as session:
        seed_if_missing(session)
        profile = load_profile(session)
        sync_companies(session, profile)
        seed_saved_searches(session, profile)
    log.info("api ready")
    yield


app = FastAPI(
    title="CareerOS API",
    version="2.0.0",
    summary=(
        "AI/ML job postings collected from company applicant-tracking systems "
        "and public job boards, scored against a candidate profile."
    ),
    description=(
        "Every score is derived and explainable: each posting carries its "
        "sub-scores, the reasons behind them and the gaps against the "
        "profile. Salary is only ever reported when the employer stated it."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Sliding-window rate limit on mutating endpoints. This is a single-user
# application on a private network, so the purpose is containment of a runaway
# client rather than defence against a determined attacker.
_hits: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.method not in MUTATING or settings.rate_limit_per_minute <= 0:
        return await call_next(request)

    client = request.client.host if request.client else "unknown"
    window = _hits[client]
    now = time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()

    if len(window) >= settings.rate_limit_per_minute:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many changes in a short period. Try again shortly."},
            headers={"Retry-After": "60"},
        )

    window.append(now)
    return await call_next(request)


app.include_router(jobs.router)
app.include_router(stats.router)
app.include_router(ops.companies)
app.include_router(ops.runs)
app.include_router(ops.searches)
app.include_router(ops.meta)
app.include_router(product.settings_router)
app.include_router(product.scans_router)
app.include_router(product.notifications_router)
app.include_router(product.analytics_router)
