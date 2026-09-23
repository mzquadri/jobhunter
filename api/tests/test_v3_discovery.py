"""Discovery must distinguish absence, filtering, failure and skipped work."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.dedup import JobGroup, Sighting
from app.matching import MatchEngine
from app.models import Base, Company, Job, ProviderState, RunProvider
from app.providers.base import Provider
from app.providers.boards import ArbeitnowProvider
from app.services.discovery import (
    _apply_source_status,
    _persist,
    _refresh_company_counts,
    _shortlist,
)
from app.settings import Profile
from tests.test_providers import make_ctx


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_skipped_count_refresh_does_not_reset_cadence(session):
    checked = datetime.now(UTC) - timedelta(hours=5)
    company = Company(id="test", name="Test", adapter="greenhouse", last_checked_at=checked)
    session.add(company)
    session.commit()
    _refresh_company_counts(session)
    assert company.last_checked_at.replace(tzinfo=UTC) == checked


def test_success_timestamp_updates_even_if_state_unchanged(session):
    company = Company(id="test", name="Test", adapter="greenhouse", source_status="live")
    session.add(company)
    session.commit()
    _apply_source_status(session, [RunProvider(
        provider="greenhouse", target="Test", state=ProviderState.HEALTHY, postings=1,
    )])
    session.expire_all()
    assert company.last_checked_at is not None
    assert company.last_success_at is not None


def test_observed_but_filtered_job_is_not_closed(session):
    job = Job(id="test|ml|munich", title="ML Engineer", title_normalized="ml engineer",
              company_name="Test", company_id="test", url="https://example.com/job",
              source="greenhouse", is_open=True)
    session.add(job)
    session.commit()
    _persist(session, [], Profile({}), {"test"}, set(), observed_ids={job.id})
    assert job.is_open
    _persist(session, [], Profile({}), {"test"}, set(), observed_ids=set())
    assert not job.is_open


@pytest.mark.parametrize("title,kept", [
    ("Software Engineer — Intelligent Systems", True),
    ("HR Manager", False), ("Marketing Manager", False),
    ("Warehouse Specialist", False), ("Data Entry Specialist", False),
    ("Software Engineer Intern", False),
])
def test_listing_pass_keeps_ambiguous_engineering_for_details(profile, title, kept):
    sighting = Sighting("workday", "Test", title, "https://example.com/job", "Munich")
    group = JobGroup("test|job|munich", sighting, [sighting])
    assert bool(_shortlist([group], MatchEngine(profile))) is kept


def test_newest_first_retains_recent_and_stops_after_old_page():
    today = datetime.now(UTC).date()
    calls = []

    def handler(request):
        page = int(request.url.params.get("page", 1))
        calls.append(page)
        ages = [0, 3, 10, 20] if page == 1 else [21, 22]
        return httpx.Response(200, json={"data": [
            {"title": "ML Engineer", "slug": f"{page}-{age}", "company_name": "Test",
             "url": f"https://example.com/{page}/{age}",
             "created_at": str(today - timedelta(days=age))}
            for age in ages
        ]})

    result = ArbeitnowProvider().fetch("8", "", "normal", make_ctx(handler))
    assert len(result.sightings) == 3
    assert calls == [1, 2]


def test_unordered_and_undated_pages_never_stop_early():
    old = str(datetime.now(UTC).date() - timedelta(days=20))
    assert not Provider.page_is_stale([old], 14, newest_first=False)
    assert not Provider.page_is_stale([old, ""], 14, newest_first=True)


def test_exact_fourteen_day_boundary_is_included():
    posted = str(datetime.now(UTC).date() - timedelta(days=14))
    assert Provider.within_age(posted, 14)


@pytest.mark.parametrize("state,complete,stays_open", [
    ("failed", True, True), ("rate_limited", True, True),
    ("healthy", False, True), ("healthy", True, False),
])
def test_only_successful_complete_fetch_can_close(
    session, monkeypatch, state, complete, stays_open,
):
    from app.services import discovery
    from app.settings import get_settings

    session.add(Company(id="test", name="Test", adapter="greenhouse", adapter_arg="test"))
    job = Job(id="test|ml|munich", title="ML Engineer", title_normalized="ml engineer",
              company_name="Test", company_id="test", url="https://example.com/job",
              source="greenhouse", is_open=True)
    session.add(job)
    session.commit()

    def collect(tasks, profile, settings, on_result):
        row = RunProvider(provider="greenhouse", target="Test", state=state, postings=0,
                          error="unavailable" if state != "healthy" else "",
                          capabilities={"complete_snapshot": complete})
        on_result(row)
        return [], [row]

    monkeypatch.setattr(discovery, "_collect", collect)
    monkeypatch.setattr(discovery, "_write_drafts", lambda *args: 0)
    result = discovery.run_discovery(session, Profile({}), get_settings(), "test")
    assert result.status != "failed", result.error
    assert job.is_open is stays_open
