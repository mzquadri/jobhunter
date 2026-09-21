"""Companies, runs, provider health, saved searches and liveness.

Grouped into one module because each is a handful of read endpoints over a
single table; splitting them would be five files of boilerplate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import engine, get_session
from app.deps import profile_dep
from app.models import Company, Job, ProviderHealth, Run, SavedSearch
from app.models.base import slugify
from app.routers.jobs import apply_filters, apply_sort
from app.routers.serialize import to_summary
from app.schemas import (
    CompanyOut,
    CompanyPatch,
    JobPage,
    ProviderHealthOut,
    RunDetail,
    RunOut,
    SavedSearchIn,
    SavedSearchOut,
)
from app.services import profile_service
from app.settings import Profile

companies = APIRouter(prefix="/api/companies", tags=["companies"])
runs = APIRouter(prefix="/api/runs", tags=["runs"])
searches = APIRouter(prefix="/api/searches", tags=["searches"])
meta = APIRouter(prefix="/api", tags=["meta"])


def _out(row: Company) -> CompanyOut:
    out = CompanyOut.model_validate(row)
    out.is_automated = bool(row.adapter)
    return out


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------
@companies.get("", response_model=list[CompanyOut], summary="The company watchlist")
def list_companies(
    session: Session = Depends(get_session),
    tier: str | None = None,
    automated: bool | None = Query(
        None, description="true for employers with a readable endpoint, "
                          "false for the manual watchlist",
    ),
) -> list[CompanyOut]:
    stmt = select(Company).where(Company.enabled.is_(True))
    if tier:
        stmt = stmt.where(Company.tier == tier.lower())
    if automated is True:
        stmt = stmt.where(Company.adapter.is_not(None))
    elif automated is False:
        stmt = stmt.where(Company.adapter.is_(None))
    rows = session.scalars(
        stmt.order_by(Company.open_roles.desc(), Company.name.asc())
    ).all()
    return [_out(c) for c in rows]


@companies.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: str, session: Session = Depends(get_session)) -> CompanyOut:
    row = session.get(Company, company_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No company with that id")
    return _out(row)


@companies.patch("/{company_id}", response_model=CompanyOut,
                 summary="Change a company's priority")
def patch_company(
    company_id: str,
    payload: CompanyPatch,
    session: Session = Depends(get_session),
) -> CompanyOut:
    """Promote or demote an employer from the interface.

    Written to two places on purpose. The row is what every read and the next
    score use; the settings document is what ``sync_companies`` reconciles the
    row against at the start of each scan. Writing only the row looked correct
    for an hour and was then silently reverted by the next scan.

    Notes stay on the row alone: they are the candidate's, and the seed
    document has no business holding them.
    """
    row = session.get(Company, company_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No company with that id")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    session.commit()
    session.refresh(row)

    reconciled = {k: v for k, v in data.items() if k in ("tier", "enabled")}
    if reconciled:
        _persist_company_config(session, company_id, reconciled)

    return _out(row)


def _persist_company_config(session: Session, company_id: str, changes: dict) -> None:
    """Mirror a company change into the stored settings document.

    Silent when the employer is not in the document: an employer discovered
    from a board has no config entry, and inventing one would add a source the
    candidate never asked to watch.
    """
    # The stored JSON rather than the validated model: this rewrites one entry
    # in a list and hands it straight back, and round-tripping through the
    # model would drop nothing but buy nothing either.
    row = profile_service.seed_if_missing(session)
    entries = [dict(e) for e in (row.profile.get("companies") or [])]
    for entry in entries:
        if slugify(str(entry.get("name") or "")) == company_id:
            entry.update(changes)
            profile_service.update_document(session, {"companies": entries})
            return


@companies.get("/{company_id}/jobs", response_model=JobPage,
               summary="Roles at one company")
def company_jobs(
    company_id: str,
    session: Session = Depends(get_session),
    include_closed: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> JobPage:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="No company with that id")

    stmt = select(Job).where(Job.company_id == company_id)
    if not include_closed:
        stmt = stmt.where(Job.is_open.is_(True))
    rows = session.scalars(
        stmt.order_by(Job.score.desc(), Job.posted_at.desc().nullslast()).limit(limit)
    ).all()
    return JobPage(
        items=[to_summary(j, company.tier) for j in rows],
        total=len(rows), limit=limit, offset=0,
    )


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------
@runs.get("", response_model=list[RunOut], summary="Discovery run history")
def list_runs(
    session: Session = Depends(get_session), limit: int = Query(30, ge=1, le=200)
) -> list[RunOut]:
    rows = session.scalars(
        select(Run).order_by(Run.started_at.desc()).limit(limit)
    ).all()
    return [RunOut.model_validate(r) for r in rows]


@runs.get("/{run_id}", response_model=RunDetail, summary="One run, provider by provider")
def get_run(run_id: int, session: Session = Depends(get_session)) -> RunDetail:
    row = session.scalars(
        select(Run).options(selectinload(Run.providers)).where(Run.id == run_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No run with that id")
    return RunDetail.model_validate(row)


@meta.get("/providers", response_model=list[ProviderHealthOut],
          summary="Rolling health of every source")
def provider_health(session: Session = Depends(get_session)) -> list[ProviderHealthOut]:
    rows = session.scalars(
        select(ProviderHealth).order_by(
            ProviderHealth.state.asc(), ProviderHealth.provider.asc()
        )
    ).all()
    out = []
    for row in rows:
        item = ProviderHealthOut.model_validate(row)
        item.success_rate = round(row.success_rate, 3)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# saved searches
# ---------------------------------------------------------------------------
@searches.get("", response_model=list[SavedSearchOut])
def list_searches(session: Session = Depends(get_session)) -> list[SavedSearchOut]:
    rows = session.scalars(
        select(SavedSearch).order_by(
            SavedSearch.pinned.desc(), SavedSearch.sort_order.asc(), SavedSearch.name.asc()
        )
    ).all()
    return [SavedSearchOut.model_validate(r) for r in rows]


@searches.post("", response_model=SavedSearchOut, status_code=201)
def create_search(
    payload: SavedSearchIn, session: Session = Depends(get_session)
) -> SavedSearchOut:
    if session.scalars(select(SavedSearch).where(SavedSearch.name == payload.name)).first():
        raise HTTPException(status_code=409, detail="A search with that name already exists")
    row = SavedSearch(**payload.model_dump(), is_builtin=False)
    session.add(row)
    session.commit()
    session.refresh(row)
    return SavedSearchOut.model_validate(row)


@searches.delete("/{search_id}", status_code=204)
def delete_search(search_id: int, session: Session = Depends(get_session)) -> None:
    row = session.get(SavedSearch, search_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No search with that id")
    if row.is_builtin:
        raise HTTPException(
            status_code=409,
            detail="Built-in searches come from your profile; edit config/profile.yml instead",
        )
    session.delete(row)
    session.commit()


@searches.get("/{search_id}/results", response_model=JobPage,
              summary="Run a saved search")
def run_search(
    search_id: int,
    session: Session = Depends(get_session),
    profile: Profile = Depends(profile_dep),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JobPage:
    """Execute a saved search through exactly the same filter code as the
    listing endpoint, so a saved query can never behave differently from the
    query that created it."""
    row = session.get(SavedSearch, search_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No search with that id")

    query = dict(row.query or {})
    sort = query.pop("sort", "newest")
    stmt = apply_filters(select(Job), profile, **query)
    total = len(session.scalars(stmt.with_only_columns(Job.id)).all())
    rows = session.scalars(apply_sort(stmt, sort).limit(limit).offset(offset)).all()

    tiers = {c.id: c.tier for c in session.scalars(select(Company)).all()}
    return JobPage(
        items=[to_summary(j, tiers.get(j.company_id or "", "normal")) for j in rows],
        total=total, limit=limit, offset=offset,
    )


# ---------------------------------------------------------------------------
# liveness
# ---------------------------------------------------------------------------
@meta.get("/health", summary="Liveness and database reachability")
def health(session: Session = Depends(get_session)) -> dict:
    from sqlalchemy import text
    database = "ok"
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        database = "unreachable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "pool": {
            "size": engine.pool.size(),
            "checked_out": engine.pool.checkedout(),
        },
    }
