"""One sweep, start to finish.

    1. every source is asked for its postings, in parallel
    2. anything that is not a full-time ML/AI job in reach is dropped on the
       title alone -- cheap, and it removes about 95% of what arrives
    3. survivors have their full description fetched, so the German /
       citizenship / sponsorship warnings have something to read
    4. everything is scored, deduplicated and written to the database
    5. strong new matches get an application folder with a draft cover letter

Fields a human owns -- starred, hidden, status, notes, applied_on -- are never
touched by a sweep. Re-running is always safe.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.collector.drafter import Drafter
from app.collector.matcher import Matcher, Verdict
from app.collector.sources import Collector, RawPosting
from app.models import Job, SourceProblem, Sweep, fingerprint, utcnow
from app.settings import Profile, Settings

log = logging.getLogger(__name__)


def _as_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date() if text else None
    except ValueError:
        return None


def run_sweep(session: Session, profile: Profile, settings: Settings) -> Sweep:
    """Collect, score and persist. Returns the finished Sweep row."""
    started = time.monotonic()
    sweep = Sweep(started_at=utcnow(), status="running")
    session.add(sweep)
    session.commit()

    collector = Collector(profile)
    matcher = Matcher(profile)
    try:
        raw, sources_ok, sources_total = _collect(collector, profile, settings)
        log.info("fetched %d postings from %d/%d sources", len(raw), sources_ok, sources_total)

        shortlist = _shortlist(raw, matcher)
        log.info("%d postings pass the title filter", len(shortlist))

        _enrich(collector, shortlist, settings)

        scored = _score(shortlist, matcher, profile)
        log.info("%d postings worth keeping", len(scored))

        new_ids, closed = _persist(session, scored)
        drafts = _write_drafts(session, profile, settings, scored, new_ids)

        sweep.postings_fetched = len(raw)
        sweep.matched = len(scored)
        sweep.new_jobs = len(new_ids)
        sweep.closed_jobs = closed
        sweep.drafts_written = drafts
        sweep.sources_ok = sources_ok
        sweep.sources_total = sources_total
        sweep.status = "ok"
    except Exception as exc:
        log.exception("sweep failed")
        sweep.status = "failed"
        sweep.error = str(exc)[:1000]
    finally:
        for source, detail in collector.problems[:60]:
            session.add(SourceProblem(sweep_id=sweep.id, source=source, detail=detail))
        collector.close()
        sweep.finished_at = utcnow()
        sweep.duration_ms = int((time.monotonic() - started) * 1000)
        session.commit()

    return sweep


# --------------------------------------------------------------------------
def _collect(collector: Collector, profile: Profile,
             settings: Settings) -> tuple[list[RawPosting], int, int]:
    jobs = [
        (c["name"], lambda c=c: collector.fetch_company(
            c["name"], c["adapter"], str(c["arg"]), c.get("tier", "NORMAL")))
        for c in profile.companies
    ]
    jobs += [
        (b, lambda b=b: collector.fetch_board(b))
        for b in profile.boards.get("enabled", [])
    ]

    postings: list[RawPosting] = []
    ok = 0
    with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
        for found in pool.map(lambda pair: pair[1](), jobs):
            if found:
                ok += 1
            postings.extend(found)
    return postings, ok, len(jobs)


def _shortlist(raw: list[RawPosting], matcher: Matcher) -> list[RawPosting]:
    """Title-only pass, plus deduplication across sources."""
    kept: list[RawPosting] = []
    seen: set[str] = set()
    for posting in raw:
        if not (posting.title and posting.url):
            continue
        if not matcher.evaluate(posting).keep:
            continue
        fp = fingerprint(posting.company, posting.title)
        if fp in seen:
            continue
        seen.add(fp)
        posting.extras["fingerprint"] = fp
        kept.append(posting)
    return kept


def _enrich(collector: Collector, postings: list[RawPosting], settings: Settings) -> None:
    """Fetch full text where it is missing, best candidates first."""
    need = [p for p in postings if len(p.description or "") < 250]
    need.sort(key=lambda p: {"DREAM": 0, "PRIORITY": 1}.get(p.tier, 2))
    need = need[: settings.max_enrich]
    if not need:
        return
    with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
        for posting, text in zip(need, pool.map(collector.fetch_detail, need), strict=False):
            if text:
                posting.description = text


def _score(postings: list[RawPosting], matcher: Matcher,
           profile: Profile) -> list[tuple[RawPosting, Verdict]]:
    scored = []
    for posting in postings:
        verdict = matcher.evaluate(posting)
        if verdict.keep and verdict.score >= profile.min_score:
            scored.append((posting, verdict))
    scored.sort(key=lambda pair: -pair[1].score)
    return scored


def _persist(session: Session, scored: list[tuple[RawPosting, Verdict]]) -> tuple[set[str], int]:
    """Upsert this sweep's findings. Returns (ids that are new, count closed)."""
    now = utcnow()
    found_ids = {p.extras["fingerprint"] for p, _ in scored}

    existing = {
        row.id: row
        for row in session.scalars(select(Job).where(Job.id.in_(found_ids or {""}))).all()
    }

    new_ids: set[str] = set()
    for posting, verdict in scored:
        jid = posting.extras["fingerprint"]
        row = existing.get(jid)
        if row is None:
            row = Job(id=jid, first_seen=now, is_new=True)
            session.add(row)
            new_ids.add(jid)

        # sweep-owned fields
        row.company = posting.company[:160]
        row.title = posting.title[:400]
        row.url = posting.url
        row.location = (posting.location or "")[:300]
        row.description = posting.description or ""
        row.source = posting.source[:60]
        row.tier = posting.tier
        row.salary = (posting.salary or "")[:80]
        row.posted_on = _as_date(posting.posted)
        row.score = verdict.score
        row.flags = verdict.flags
        row.skills = verdict.skills
        row.domains = verdict.domains
        row.has_flags = bool(verdict.flags)
        row.search_blob = " ".join([
            posting.company, posting.title, posting.location or "",
            *verdict.skills, *verdict.domains, posting.source,
        ]).lower()[:2000]
        row.last_seen = now
        row.is_open = True
        # human-owned fields (starred, hidden, status, notes, applied_on,
        # draft_folder) are deliberately not written here.

    # anything not seen this sweep has closed
    closed = session.execute(
        update(Job)
        .where(Job.is_open.is_(True), Job.id.notin_(found_ids or {""}))
        .values(is_open=False)
    ).rowcount or 0

    # postings introduced by an earlier sweep stop being "new"
    session.execute(
        update(Job)
        .where(Job.is_new.is_(True), Job.id.notin_(new_ids or {""}))
        .values(is_new=False)
    )

    session.commit()
    return new_ids, closed


def _write_drafts(session: Session, profile: Profile, settings: Settings,
                  scored: list[tuple[RawPosting, Verdict]], new_ids: set[str]) -> int:
    letter = Path(settings.letter_path)
    if not letter.exists():
        log.warning("no letter template at %s; skipping drafts", letter)
        return 0

    drafter = Drafter(profile, letter, Path(settings.drafts_dir))
    written = 0
    for posting, verdict in scored:
        jid = posting.extras["fingerprint"]
        if jid not in new_ids or verdict.score < profile.draft_min_score:
            continue
        try:
            folder = drafter.build(posting, verdict)
        except Exception:
            log.exception("could not write a draft for %s", posting.company)
            continue
        if folder:
            session.execute(update(Job).where(Job.id == jid).values(draft_folder=folder))
            written += 1
    session.commit()
    return written


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
