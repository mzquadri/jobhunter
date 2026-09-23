"""One discovery run, start to finish.

    1. every enabled source is asked for its postings, in parallel
    2. sightings of the same vacancy are merged, keeping all provenance
    3. anything not a full-time AI/ML role in reach is dropped on the title
       alone -- cheap, and it removes most of what arrives
    4. survivors have their full text fetched, so language, salary and
       seniority have something to read
    5. everything is scored, persisted and drafted

Two invariants hold throughout:

  * Columns a human owns -- status, notes, starred, hidden, applied_at -- are
    never written by a run. Re-running is always safe.
  * A source failing is recorded, not raised. One broken provider must not end
    the run.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import false, func, or_, select, update
from sqlalchemy.orm import Session

from app.dedup import JobGroup, Sighting, deduplicate
from app.enrich.text import summarise
from app.matching import MatchEngine, MatchResult
from app.models import (
    ApplicationStatus,
    Company,
    CompanyTier,
    Job,
    JobSource,
    ProviderState,
    Run,
    RunProvider,
    RunStatus,
    SourceStatus,
    slugify,
    utcnow,
)
from app.providers import (
    BOARD_PROVIDERS,
    REGISTRY,
    FetchContext,
    ProviderResult,
    run_provider,
)
from app.providers.dates import days_old
from app.security import RateLimit
from app.services import health, signals
from app.services.drafts import Drafter, DraftInput
from app.settings import Profile, Settings

log = logging.getLogger(__name__)


@dataclass
class Task:
    provider: str
    target: str
    company: str
    tier: str


def _as_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date() if text else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def run_discovery(
    session: Session, profile: Profile, settings: Settings, triggered_by: str = "scheduler"
) -> Run:
    started = time.monotonic()
    run = Run(started_at=utcnow(), status=RunStatus.RUNNING, triggered_by=triggered_by)
    session.add(run)
    session.commit()

    try:
        sync_companies(session, profile)
        tasks = _build_tasks(session, profile, settings, run)

        sightings, provider_rows = _collect(tasks, profile, settings)
        for row in provider_rows:
            row.run_id = run.id
            session.add(row)
        session.commit()
        apply_health(session, provider_rows, settings)

        groups = deduplicate(sightings)
        duplicates = sum(g.duplicate_count for g in groups)
        log.info("%d sightings collapsed to %d vacancies (%d duplicates merged)",
                 len(sightings), len(groups), duplicates)

        engine = MatchEngine(profile)
        shortlisted = _shortlist(groups, engine)
        log.info("%d vacancies pass the title filter", len(shortlisted))

        _enrich(shortlisted, profile, settings)
        scored = _score(shortlisted, engine, profile)
        log.info("%d vacancies worth keeping", len(scored))

        # Employers found through a board become real companies before the
        # jobs are written, so every posting can be linked to one.
        adopted = adopt_discovered_companies(session, [g for g, _ in scored])

        # Which sources this run actually asked. Anything else must not have
        # its vacancies closed just because they were not seen this time.
        asked_company_ids = {
            slugify(t.company)
            for t in tasks
            if t.company and t.provider not in BOARD_PROVIDERS
        }
        asked_boards = {t.provider for t in tasks if t.provider in BOARD_PROVIDERS}

        new_ids, updated, closed = _persist(
            session, scored, profile, asked_company_ids, asked_boards
        )
        drafts = _write_drafts(session, scored, new_ids, profile, settings)
        _refresh_company_counts(session)
        _archive(session, profile)

        run.providers_checked = len(provider_rows)
        run.providers_ok = sum(1 for r in provider_rows if r.state == ProviderState.HEALTHY)
        run.companies_checked = len({t.company for t in tasks if t.company})
        run.postings_seen = len(sightings)
        run.postings_relevant = len(scored)
        run.duplicates_merged = duplicates
        run.jobs_new = len(new_ids)
        run.jobs_updated = updated
        run.jobs_closed = closed
        run.drafts_written = drafts
        run.errors_count = sum(1 for r in provider_rows if r.error)
        if adopted:
            log.info("%d newly discovered employers now tracked", adopted)
        run.status = RunStatus.PARTIAL if run.errors_count else RunStatus.OK

        # Turn what changed into things worth telling the user. Derived
        # strictly from rows this run wrote.
        session.flush()
        signals.generate_for_run(session, run, profile, new_ids)
        signals.generate_follow_up_reminders(session, profile)
    except Exception as exc:
        log.exception("discovery run failed")
        run.status = RunStatus.FAILED
        run.error = str(exc)[:2000]
    finally:
        run.finished_at = utcnow()
        run.duration_ms = int((time.monotonic() - started) * 1000)
        session.commit()

    return run


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------
def sync_companies(session: Session, profile: Profile) -> None:
    """Reconcile the company table with the profile.

    Config is authoritative for what a company *is*; the database keeps what
    has been *observed* about it. Notes are left alone -- they belong to the
    candidate.
    """
    for entry in profile.companies:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        company_id = slugify(name)
        row = session.get(Company, company_id)
        if row is None:
            row = Company(id=company_id, name=name)
            session.add(row)
        row.name = name
        row.tier = str(entry.get("tier", "normal")).lower()
        row.adapter = entry.get("adapter")
        row.adapter_arg = str(entry["arg"]) if entry.get("arg") else None
        row.careers_url = str(entry.get("careers_url") or "")
        row.industry = str(entry.get("industry") or "")
        row.enabled = bool(entry.get("enabled", True))
        row.country = str(entry.get("country") or "")
        row.parent_id = slugify(str(entry["parent"])) if entry.get("parent") else None
        row.aliases = [str(a) for a in (entry.get("aliases") or [])]

        # Source status starts from what is configured and is corrected by what
        # actually happens: an employer with no adapter is manual and always
        # will be, and one with an adapter is only "live" once a run has
        # fetched from it. `apply_health` moves it on from there.
        #
        # The `or MANUAL` matters. On a row created a moment ago the column
        # default has not been applied yet -- SQLAlchemy fills it at flush --
        # so the attribute is still None, and comparing it against MANUAL
        # silently left every newly configured employer marked manual.
        if not row.adapter:
            row.source_status = SourceStatus.MANUAL
            row.verified_at = None
        elif (row.source_status or SourceStatus.MANUAL) == SourceStatus.MANUAL:
            # Configured, but nothing has been fetched yet. "Idle" is the one
            # honest starting point; "live" would be a claim we have not earned.
            row.source_status = SourceStatus.IDLE
    session.commit()


def adopt_discovered_companies(session: Session, groups: list[JobGroup]) -> int:
    """Create company rows for employers that arrived through a job board.

    Without this, a relevant ML role at a Munich company nobody had configured
    is stored with ``company_id = None``: it never appears under an employer,
    never gets a tier, and cannot be promoted to the shortlist. The registry is
    for *targeted* coverage; boards are for *discovery*, and discovery is
    worthless if what it finds cannot become a first-class employer.

    Matching is by name and by alias, so "BMW AG" from a board resolves to the
    configured "BMW Group" instead of creating a near-duplicate. Anything
    genuinely new is created as a normal-tier, manual-source employer with its
    provenance recorded -- never as automated, because no endpoint is known.
    """
    known: dict[str, str] = {}
    for company in session.scalars(select(Company)).all():
        known[_match_key(company.name)] = company.id
        for alias in company.aliases or []:
            known.setdefault(_match_key(alias), company.id)

    created = 0
    for group in groups:
        name = (group.primary.company or "").strip()
        if not name or _match_key(name) in known:
            continue
        company_id = slugify(name)
        if session.get(Company, company_id) is not None:
            known[_match_key(name)] = company_id
            continue

        session.add(Company(
            id=company_id,
            name=name[:200],
            tier=CompanyTier.NORMAL,
            adapter=None,
            source_status=SourceStatus.MANUAL,
            discovered_from=group.primary.provider[:40],
            careers_url="",
            enabled=True,
        ))
        known[_match_key(name)] = company_id
        created += 1

    if created:
        session.commit()
        log.info("%d employers discovered through boards and added", created)
    return created


def _match_key(name: str) -> str:
    """Normalise an employer name for comparison.

    Employers are inconsistent about legal suffixes across their own postings
    -- "Celonis SE", "Celonis", "Celonis GmbH" -- and treating those as three
    companies fragments the whole company view.
    """
    text = (name or "").lower().strip()
    for suffix in (" se", " ag", " gmbh", " ltd", " ltd.", " limited", " inc",
                   " inc.", " b.v.", " bv", " nv", " n.v.", " plc", " sa",
                   " s.a.", " srl", " s.r.l.", " oy", " ab", " as", " a/s",
                   " kg", " gmbh & co. kg", " group", " holding"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return "".join(ch for ch in text if ch.isalnum())


#: How often each tier's employers are worth asking, in minutes.
#:
#: 117 sources every hour is 2,800 requests a day to other people's servers to
#: re-read a market that moves in days, not minutes. The employers you actually
#: care about keep the hourly cadence; the rest are asked often enough that a
#: posting is still fresh when it arrives.
#:
#: 0 means every run. A company whose last check is unknown is always due, so a
#: newly added employer is read immediately rather than waiting out its tier.
CADENCE_MINUTES: dict[str, int] = {
    CompanyTier.DREAM: 0,        # every run
    CompanyTier.HIGH: 0,         # every run
    CompanyTier.NORMAL: 240,     # four hours
    CompanyTier.IGNORED: 1440,   # daily, in case the tier is changed back
}


def _is_due(company: Company, now: datetime) -> bool:
    """Whether this employer's cadence has elapsed since the last check."""
    interval = CADENCE_MINUTES.get(company.tier, 0)
    if interval <= 0 or company.last_checked_at is None:
        return True
    last = company.last_checked_at
    if last.tzinfo is None:                     # SQLite hands back naive values
        last = last.replace(tzinfo=UTC)
    return (now - last) >= timedelta(minutes=interval)


def _build_tasks(
    session: Session, profile: Profile, settings: Settings, run: Run
) -> list[Task]:
    """Every source to ask this run, minus the ones backed off or not yet due."""
    known = health.load_all(session)
    tasks: list[Task] = []

    now = utcnow()
    for company in session.scalars(
        select(Company).where(Company.enabled.is_(True), Company.adapter.is_not(None))
    ).all():
        if company.adapter not in REGISTRY:
            log.warning("company %s names unknown adapter %r", company.name, company.adapter)
            continue
        key = health.health_key(company.adapter, company.adapter_arg or "")
        if health.is_backed_off(known.get(key)):
            session.add(RunProvider(
                run_id=run.id, provider=company.adapter, target=company.name,
                state=ProviderState.SKIPPED, error="backed off after repeated failures",
            ))
            continue
        if not _is_due(company, now):
            session.add(RunProvider(
                run_id=run.id, provider=company.adapter, target=company.name,
                state=ProviderState.SKIPPED,
                error=f"not due yet ({CADENCE_MINUTES.get(company.tier, 0)}m cadence)",
            ))
            continue
        tasks.append(Task(company.adapter, company.adapter_arg or "",
                          company.name, company.tier))

    boards = profile.boards.get("enabled", [])
    for board in boards:
        if board not in REGISTRY or board not in BOARD_PROVIDERS:
            log.warning("unknown board %r", board)
            continue
        key = health.health_key(board, "")
        if health.is_backed_off(known.get(key)):
            continue
        target = str(profile.boards.get("arbeitnow_pages", 4)) if board == "arbeitnow" else ""
        if board == "adzuna":
            target = ",".join(profile.boards.get("adzuna_countries", ["de"]))
        tasks.append(Task(board, target, "", "normal"))

    session.commit()
    return tasks


# ---------------------------------------------------------------------------
# collection
# ---------------------------------------------------------------------------
def _client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "application/json, application/rss+xml, text/xml, text/html;q=0.9, */*",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        },
        timeout=settings.http_timeout,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=settings.max_workers * 2),
    )


def _collect(
    tasks: list[Task], profile: Profile, settings: Settings
) -> tuple[list[Sighting], list[RunProvider]]:
    board_queries = profile.boards.get("queries", []) or profile.company_queries
    limiter = RateLimit(per_minute=90)

    sightings: list[Sighting] = []
    rows: list[RunProvider] = []

    with _client(settings) as client:
        def work(task: Task) -> tuple[Task, ProviderResult, int]:
            queries = board_queries if task.provider in BOARD_PROVIDERS \
                else profile.company_queries
            ctx = FetchContext(
                queries=queries, max_age_days=profile.max_age_days,
                settings=settings, client=client, limiter=limiter,
            )
            began = time.monotonic()
            result = run_provider(
                REGISTRY[task.provider], task.target,
                task.company or task.provider, task.tier, ctx,
            )
            return task, result, int((time.monotonic() - began) * 1000)

        with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
            for task, result, elapsed in pool.map(work, tasks):
                sightings.extend(result.sightings)
                if result.rate_limited:
                    state = ProviderState.RATE_LIMITED
                elif result.error:
                    state = ProviderState.FAILED
                else:
                    state = ProviderState.HEALTHY
                rows.append(RunProvider(
                    provider=task.provider,
                    target=task.company or task.provider,
                    state=state,
                    postings=len(result.sightings),
                    requests_made=result.requests_made,
                    duration_ms=elapsed,
                    error=result.error,
                    capabilities=result.capabilities,
                ))

    return sightings, rows


def apply_health(session: Session, rows: list[RunProvider], settings: Settings) -> None:
    """Fold this run's provider outcomes into the rolling health record."""
    for row in rows:
        if row.state == ProviderState.SKIPPED:
            continue
        if row.state == ProviderState.HEALTHY:
            health.record_success(session, row.provider, row.target, row.capabilities)
        else:
            health.record_failure(
                session, row.provider, row.target, row.error, settings,
                rate_limited=row.state == ProviderState.RATE_LIMITED,
            )
    session.commit()
    _apply_source_status(session, rows)


def _apply_source_status(session: Session, rows: list[RunProvider]) -> None:
    """Record, per employer, what actually happened to their source.

    Without this every configured employer sits at "idle" forever and the
    coverage panel reports 117 sources in an indeterminate state after a run
    that fetched from all of them. The point of the field is to distinguish
    "configured" from "working", which requires writing down which it was.

    Keyed on (adapter, target) because that is what a run records, and several
    employers can legitimately share neither — a target belongs to one employer.
    """
    outcomes = {(r.provider, r.target): r for r in rows}
    if not outcomes:
        return

    now = utcnow()
    changed = 0
    for company in session.scalars(
        select(Company).where(Company.adapter.is_not(None))
    ).all():
        row = outcomes.get((company.adapter, company.adapter_arg or "")) \
            or outcomes.get((company.adapter, company.name))
        if row is None:
            continue

        if row.state == ProviderState.HEALTHY:
            # Answered. "Live" only when it actually carried postings; a board
            # that replied with an empty list is working and simply has nothing
            # open, which is a different fact and worth keeping distinct.
            status = SourceStatus.LIVE if row.postings else SourceStatus.IDLE
            company.verified_at = now
            company.last_success_at = now
        elif row.state == ProviderState.RATE_LIMITED:
            status = SourceStatus.RATE_LIMITED
        elif row.state == ProviderState.SKIPPED:
            continue
        else:
            # It had a working endpoint and stopped answering; that is broken,
            # not manual. Manual means "there is nothing to read", which is a
            # permanent property of the employer rather than today's failure.
            status = SourceStatus.BROKEN

        if company.source_status != status:
            company.source_status = status
            changed += 1

    if changed:
        session.commit()
        log.info("%d employer source states changed", changed)


# ---------------------------------------------------------------------------
# filtering, enrichment, scoring
# ---------------------------------------------------------------------------
def _shortlist(groups: list[JobGroup], engine: MatchEngine) -> list[JobGroup]:
    """Title-only pass, before paying for any description."""
    kept = []
    for group in groups:
        primary = group.primary
        verdict = engine.evaluate(
            primary.title, group.best_description(), primary.location,
            primary.company, primary.tier,
            days_old(group.earliest_posted()), primary.tags, primary.structured,
        )
        if verdict.keep:
            kept.append(group)
    return kept


def _enrich(groups: list[JobGroup], profile: Profile, settings: Settings) -> None:
    """Fetch full text where it is missing, strongest candidates first."""
    needing = [g for g in groups if len(g.best_description()) < 400]
    needing.sort(key=lambda g: {"dream": 0, "high": 1}.get(g.primary.tier, 2))
    needing = needing[: settings.max_enrich]
    if not needing:
        return

    limiter = RateLimit(per_minute=90)
    with _client(settings) as client:
        ctx = FetchContext(
            queries=profile.company_queries, max_age_days=profile.max_age_days,
            settings=settings, client=client, limiter=limiter,
        )

        def fetch(group: JobGroup) -> tuple[JobGroup, str]:
            provider = REGISTRY.get(group.primary.provider)
            if provider is None:
                return group, ""
            try:
                return group, provider.fetch_detail(group.primary, ctx)
            except Exception:                      # noqa: BLE001 - one posting, not the run
                log.debug("detail fetch failed for %s", group.primary.url, exc_info=True)
                return group, ""

        with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
            for group, text in pool.map(fetch, needing):
                if text:
                    group.primary.description = text


def _score(
    groups: list[JobGroup], engine: MatchEngine, profile: Profile
) -> list[tuple[JobGroup, MatchResult]]:
    scored = []
    for group in groups:
        primary = group.primary
        result = engine.evaluate(
            primary.title, group.best_description(), primary.location,
            primary.company, primary.tier,
            days_old(group.earliest_posted()), primary.tags, primary.structured,
        )
        if result.keep and result.score >= profile.min_score:
            scored.append((group, result))
    scored.sort(key=lambda pair: -pair[1].score)
    return scored


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------
def _persist(
    session: Session,
    scored: list[tuple[JobGroup, MatchResult]],
    profile: Profile,
    asked_company_ids: set[str],
    asked_boards: set[str],
) -> tuple[set[str], int, int]:
    now = utcnow()
    seen_ids = {group.key for group, _ in scored}
    existing = {
        row.id: row
        for row in session.scalars(select(Job).where(Job.id.in_(seen_ids or {""}))).all()
    }
    # Keyed on the normalised name and every alias, so "BMW AG" from a board
    # resolves to the configured "BMW Group" rather than going unlinked.
    companies: dict[str, str] = {}
    for company in session.scalars(select(Company)).all():
        companies[_match_key(company.name)] = company.id
        for alias in company.aliases or []:
            companies.setdefault(_match_key(alias), company.id)

    new_ids: set[str] = set()
    updated = 0

    for group, result in scored:
        primary = group.primary
        row = existing.get(group.key)
        if row is None:
            row = Job(id=group.key, first_seen_at=now, is_new=True, times_seen=0)
            session.add(row)
            new_ids.add(group.key)
        else:
            updated += 1

        # ---- run-owned columns -----------------------------------------
        row.company_name = primary.company[:200]
        row.company_id = companies.get(_match_key(primary.company))
        row.title = primary.title[:400]
        row.title_normalized = group.key.split("|")[1][:400]
        row.url = primary.url
        row.location_raw = (primary.location or "")[:300]
        row.city = result.city[:120]
        row.country = result.country[:80]
        row.remote_policy = result.remote_policy
        row.employment_type = result.employment_type
        row.description = group.best_description()[:60_000]
        row.summary = _summary(group.best_description())
        row.posted_at = _as_date(group.earliest_posted())
        row.source = primary.provider

        row.seniority = result.seniority
        row.experience_min_years = result.experience_min_years
        row.experience_max_years = result.experience_max_years
        row.language_requirement = result.language_requirement
        row.language_evidence = result.language_evidence[:400]

        salary = result.salary
        row.salary_min = salary.amount_min
        row.salary_max = salary.amount_max
        row.salary_currency = salary.currency
        row.salary_period = salary.period
        row.salary_annual_eur_min = salary.annual_eur_min
        row.salary_annual_eur_max = salary.annual_eur_max
        row.salary_basis = salary.basis
        row.salary_evidence = salary.evidence[:400]

        row.skills = result.skills
        row.domains = result.domains
        row.role_category = result.role_category[:48]
        row.score = result.score
        sub = result.sub
        row.score_technical = sub.technical
        row.score_experience = sub.experience
        row.score_language = sub.language
        row.score_location = sub.location
        row.score_education = sub.education
        row.score_freshness = sub.freshness
        row.score_domain = sub.domain
        row.match_reasons = result.reasons
        row.match_gaps = result.gaps
        row.flags = result.flags
        row.has_flags = bool(result.flags)
        row.search_blob = " ".join([
            primary.company, primary.title, primary.location or "",
            result.city, result.country, result.role_category,
            *result.skills, *result.domains,
        ]).lower()[:2000]

        row.last_seen_at = now
        row.is_open = True
        row.removed_at = None
        row.times_seen = (row.times_seen or 0) + 1
        # status, notes, starred, hidden, applied_at, follow_up_at,
        # contact_person and salary_discussion are the candidate's. Never
        # written here.

        _sync_sources(session, row, group, now)

    session.flush()

    # A run may only close what it actually looked at.
    #
    # This used to close every open job not seen this run, which was correct
    # while every source was asked every time. Tiered cadence broke that
    # assumption hard: a normal-tier employer is asked every four hours, so on
    # the five runs in between, all of their still-open vacancies were marked
    # closed and then reopened -- jobs vanishing from the dashboard for hours,
    # "job closed" signals firing constantly, and the closed count meaningless.
    #
    # Coverage is per source, not per run: an employer's jobs are closable only
    # when that employer was asked, and a board's jobs only when that board ran.
    covered = or_(
        Job.company_id.in_(asked_company_ids) if asked_company_ids else false(),
        Job.source.in_(asked_boards) if asked_boards else false(),
    )
    closed = session.execute(
        update(Job)
        .where(Job.is_open.is_(True), Job.id.notin_(seen_ids or {""}), covered)
        .values(is_open=False, removed_at=now)
    ).rowcount or 0

    session.execute(
        update(Job)
        .where(Job.is_new.is_(True), Job.id.notin_(new_ids or {""}))
        .values(is_new=False)
    )
    session.commit()
    return new_ids, updated, closed


def _sync_sources(session: Session, row: Job, group: JobGroup, now) -> None:
    """Record every provider that reported this vacancy."""
    existing = {(s.provider, s.external_id): s for s in row.sources}
    for sighting in group.sightings:
        key = (sighting.provider, sighting.external_id)
        source = existing.get(key)
        if source is None:
            source = JobSource(
                job_id=row.id, provider=sighting.provider,
                external_id=sighting.external_id[:300],
                first_seen_at=now,
            )
            session.add(source)
        source.url = sighting.url
        source.posted_at = _as_date(sighting.posted)
        source.last_seen_at = now
        source.is_primary = sighting is group.primary


def _summary(text: str) -> str:
    return summarise(text)[:1200]


def _refresh_company_counts(session: Session) -> None:
    """Denormalised counts for the company view."""
    week_ago = utcnow() - timedelta(days=7)
    open_counts = dict(session.execute(
        select(Job.company_id, func.count())
        .where(Job.is_open.is_(True), Job.company_id.is_not(None))
        .group_by(Job.company_id)
    ).all())
    new_counts = dict(session.execute(
        select(Job.company_id, func.count())
        .where(Job.is_open.is_(True), Job.company_id.is_not(None),
               Job.first_seen_at >= week_ago)
        .group_by(Job.company_id)
    ).all())

    for company in session.scalars(select(Company)).all():
        company.open_roles = open_counts.get(company.id, 0)
        company.new_roles_7d = new_counts.get(company.id, 0)
        if company.adapter:
            company.last_checked_at = utcnow()
    session.commit()


def _archive(session: Session, profile: Profile) -> None:
    """Drop long-closed postings the candidate never engaged with.

    §30 asks for history without keeping full copies forever. A closed job
    that was never starred, never noted and never moved out of 'new' carries
    no information worth the row; anything touched is kept.
    """
    cutoff = utcnow() - timedelta(days=profile.archive_after_days)
    stale = session.scalars(
        select(Job).where(
            Job.is_open.is_(False),
            Job.removed_at.is_not(None),
            Job.removed_at < cutoff,
            Job.status == ApplicationStatus.NEW,
            Job.starred.is_(False),
            Job.notes == "",
        )
    ).all()
    for job in stale:
        session.delete(job)
    if stale:
        log.info("archived %d closed postings that were never engaged with", len(stale))
    session.commit()


def _write_drafts(
    session: Session,
    scored: list[tuple[JobGroup, MatchResult]],
    new_ids: set[str],
    profile: Profile,
    settings: Settings,
) -> int:
    drafter = Drafter(profile, Path(settings.letter_path), Path(settings.drafts_dir))
    if not drafter.available:
        log.info("no letter template at %s; skipping drafts", settings.letter_path)
        return 0

    written = 0
    for group, result in scored:
        if group.key not in new_ids or result.score < profile.draft_min_score:
            continue
        primary = group.primary
        try:
            folder = drafter.build(
                DraftInput(
                    company=primary.company, title=primary.title, url=primary.url,
                    location=primary.location,
                    posted_at=_as_date(group.earliest_posted()),
                    description=group.best_description(), source=primary.provider,
                ),
                result,
            )
        except Exception:                          # noqa: BLE001 - one draft, not the run
            log.exception("could not write a draft for %s", primary.company)
            continue
        if folder:
            session.execute(
                update(Job).where(Job.id == group.key).values(draft_folder=folder)
            )
            written += 1
    session.commit()
    return written
