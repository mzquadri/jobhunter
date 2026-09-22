"""The employer registry, and what it is allowed to claim.

Two things are being protected here.

The first is honesty about coverage. It is easy to write three hundred
employers into the config and report "300 companies monitored"; roughly half of
any guessed set does not exist, and the dashboard then claims to watch
employers it never fetches from. So the registry distinguishes an employer with
a verified feed from one that can only be checked by hand, and these tests
assert the shipped file keeps that distinction straight.

The second is that discovery and the registry complement each other. The
registry gives targeted coverage of employers worth watching; job boards find
the Munich startup nobody had heard of. A vacancy from an unconfigured employer
has to become a first-class company, or discovery is decoration.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.dedup import JobGroup, Sighting
from app.models import Base, Company, CompanyTier, SourceStatus
from app.services.discovery import (
    _match_key,
    adopt_discovered_companies,
    sync_companies,
)
from app.settings import Profile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "config" / "profile.example.yml"


@pytest.fixture(scope="module")
def registry() -> list[dict]:
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))["companies"]


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'registry.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def sighting(company: str, provider: str = "arbeitnow") -> Sighting:
    return Sighting(
        provider=provider, company=company, title="Machine Learning Engineer",
        url="https://example.com/job/1", location="Munich, Germany",
        external_id="1", description="PyTorch and deep learning.", tier="normal",
    )


def group(company: str, provider: str = "arbeitnow") -> JobGroup:
    one = sighting(company, provider)
    return JobGroup(key=f"{company}|machine learning engineer|munich",
                    primary=one, sightings=[one])


# ---------------------------------------------------------------------------
# what the shipped registry may claim
# ---------------------------------------------------------------------------
class TestShippedRegistry:
    def test_every_automated_entry_names_a_real_adapter(self, registry):
        from app.providers import REGISTRY as PROVIDERS

        for entry in registry:
            if entry.get("adapter"):
                assert entry["adapter"] in PROVIDERS, (
                    f"{entry['name']} names adapter {entry['adapter']!r}, "
                    f"which no provider implements"
                )

    def test_every_automated_entry_has_an_argument(self, registry):
        for entry in registry:
            if entry.get("adapter"):
                assert entry.get("arg"), f"{entry['name']} has an adapter but no arg"

    def test_every_manual_entry_has_somewhere_to_click(self, registry):
        # A watchlist row's entire value is the link. Without one it is an
        # employer we neither scan nor help the user reach.
        for entry in registry:
            if not entry.get("adapter"):
                assert entry.get("careers_url", "").startswith("https://"), (
                    f"{entry['name']} is manual but has no careers URL"
                )

    def test_no_employer_is_listed_twice(self, registry):
        keys = [_match_key(e["name"]) for e in registry]
        duplicates = {k for k in keys if keys.count(k) > 1}
        assert not duplicates, f"duplicate employers: {duplicates}"

    def test_no_two_entries_scan_the_same_source(self, registry):
        sources = [
            (e["adapter"], e["arg"]) for e in registry if e.get("adapter")
        ]
        duplicates = {s for s in sources if sources.count(s) > 1}
        assert not duplicates, f"the same source would be fetched twice: {duplicates}"

    def test_every_parent_refers_to_an_employer_that_exists(self, registry):
        from app.models import slugify

        ids = {slugify(e["name"]) for e in registry}
        for entry in registry:
            if parent := entry.get("parent"):
                assert parent in ids, (
                    f"{entry['name']} names parent {parent!r}, which is not in the registry"
                )

    def test_coverage_is_substantial_and_mostly_automated_is_not_claimed(self, registry):
        automated = [e for e in registry if e.get("adapter")]
        manual = [e for e in registry if not e.get("adapter")]
        # Not an arbitrary bar: this is the point of the expansion, and a
        # regression that silently halves coverage should fail loudly.
        assert len(automated) >= 100, f"only {len(automated)} automated sources"
        assert manual, "a registry with no manual entries is hiding something"


# ---------------------------------------------------------------------------
# the registry reaching the database
# ---------------------------------------------------------------------------
class TestSync:
    def test_an_employer_without_an_adapter_is_marked_manual(self, db):
        profile = Profile({"companies": [
            {"name": "Ferrari", "tier": "dream",
             "careers_url": "https://example.com/careers"},
        ]})
        with db() as session:
            sync_companies(session, profile)
            row = session.get(Company, "ferrari")
            assert row.source_status == SourceStatus.MANUAL
            assert row.verified_at is None
            assert not row.is_automated

    def test_a_configured_adapter_starts_unproven_rather_than_live(self, db):
        # "Configured" is not "working". Claiming live before anything has been
        # fetched is exactly the overstatement this field exists to prevent.
        profile = Profile({"companies": [
            {"name": "Helsing", "adapter": "greenhouse", "arg": "helsing"},
        ]})
        with db() as session:
            sync_companies(session, profile)
            assert session.get(Company, "helsing").source_status == SourceStatus.IDLE

    def test_group_structure_and_aliases_are_stored(self, db):
        profile = Profile({"companies": [
            {"name": "Volkswagen Group", "industry": "automotive"},
            {"name": "Audi", "parent": "volkswagen-group", "country": "de",
             "aliases": ["Audi AG", "AUDI"]},
        ]})
        with db() as session:
            sync_companies(session, profile)
            audi = session.get(Company, "audi")
            assert audi.parent_id == "volkswagen-group"
            assert audi.country == "de"
            assert "Audi AG" in audi.aliases


# ---------------------------------------------------------------------------
# §62 — an employer nobody configured
# ---------------------------------------------------------------------------
class TestBoardDiscovery:
    def test_an_unknown_employer_becomes_a_company(self, db):
        with db() as session:
            created = adopt_discovered_companies(session, [group("Unheard-Of Robotics")])
            assert created == 1
            row = session.get(Company, "unheard-of-robotics")
            assert row is not None
            assert row.tier == CompanyTier.NORMAL
            assert row.discovered_from == "arbeitnow"
            assert row.source_status == SourceStatus.MANUAL, (
                "a discovered employer has no known endpoint, so it is not automated"
            )

    def test_a_discovered_employer_is_not_claimed_as_monitored(self, db):
        with db() as session:
            adopt_discovered_companies(session, [group("Unheard-Of Robotics")])
            assert session.get(Company, "unheard-of-robotics").adapter is None

    def test_a_configured_employer_is_not_duplicated(self, db):
        profile = Profile({"companies": [
            {"name": "Helsing", "adapter": "greenhouse", "arg": "helsing"},
        ]})
        with db() as session:
            sync_companies(session, profile)
            assert adopt_discovered_companies(session, [group("Helsing")]) == 0
            assert len(session.scalars(select(Company)).all()) == 1

    def test_a_legal_suffix_does_not_create_a_second_company(self, db):
        profile = Profile({"companies": [{"name": "Celonis", "industry": "technology"}]})
        with db() as session:
            sync_companies(session, profile)
            created = adopt_discovered_companies(
                session, [group("Celonis SE"), group("Celonis GmbH")]
            )
            assert created == 0, "Celonis, Celonis SE and Celonis GmbH are one employer"

    def test_an_alias_resolves_to_the_configured_employer(self, db):
        profile = Profile({"companies": [
            {"name": "BMW Group", "adapter": "successfactors", "arg": "jobs.bmwgroup.com",
             "aliases": ["BMW", "BMW AG", "Bayerische Motoren Werke"]},
        ]})
        with db() as session:
            sync_companies(session, profile)
            assert adopt_discovered_companies(session, [group("BMW AG")]) == 0

    def test_several_new_employers_in_one_run(self, db):
        with db() as session:
            created = adopt_discovered_companies(
                session, [group("Alpha Labs"), group("Beta Systems"), group("Alpha Labs")]
            )
            assert created == 2


class TestSourceStatusReflectsReality:
    """§34 — an employer is never labelled working on the strength of config."""

    def _run_rows(self, state, postings=3, name="Helsing"):
        from app.models import RunProvider

        return [RunProvider(run_id=1, provider="greenhouse", target=name,
                            state=state, postings=postings)]

    def _configured(self, session, name="Helsing"):
        sync_companies(session, Profile({"companies": [
            {"name": name, "adapter": "greenhouse", "arg": name.lower()},
        ]}))

    def test_a_successful_fetch_marks_the_source_live(self, db):
        from app.models.base import ProviderState
        from app.services.discovery import _apply_source_status

        with db() as session:
            self._configured(session)
            _apply_source_status(session, self._run_rows(ProviderState.HEALTHY))
            row = session.get(Company, "helsing")
            assert row.source_status == SourceStatus.LIVE
            assert row.verified_at is not None

    def test_a_source_that_answered_with_nothing_is_idle_not_broken(self, db):
        from app.models.base import ProviderState
        from app.services.discovery import _apply_source_status

        with db() as session:
            self._configured(session)
            _apply_source_status(
                session, self._run_rows(ProviderState.HEALTHY, postings=0)
            )
            row = session.get(Company, "helsing")
            assert row.source_status == SourceStatus.IDLE
            assert row.verified_at is not None, "it answered; that is worth recording"

    def test_a_failure_marks_the_source_broken(self, db):
        from app.models.base import ProviderState
        from app.services.discovery import _apply_source_status

        with db() as session:
            self._configured(session)
            _apply_source_status(session, self._run_rows(ProviderState.FAILED))
            assert session.get(Company, "helsing").source_status == SourceStatus.BROKEN

    def test_being_refused_is_not_the_same_as_being_broken(self, db):
        from app.models.base import ProviderState
        from app.services.discovery import _apply_source_status

        with db() as session:
            self._configured(session)
            _apply_source_status(session, self._run_rows(ProviderState.RATE_LIMITED))
            assert (session.get(Company, "helsing").source_status
                    == SourceStatus.RATE_LIMITED)

    def test_a_manual_employer_is_untouched_by_a_run(self, db):
        from app.models.base import ProviderState
        from app.services.discovery import _apply_source_status

        with db() as session:
            sync_companies(session, Profile({"companies": [
                {"name": "Ferrari", "careers_url": "https://example.com/careers"},
            ]}))
            _apply_source_status(
                session, self._run_rows(ProviderState.HEALTHY, name="Ferrari")
            )
            assert session.get(Company, "ferrari").source_status == SourceStatus.MANUAL


class TestScanCadence:
    """§65/§66 — ask often enough to be useful, not often enough to be rude.

    117 sources every hour is ~2,800 requests a day to other people's servers
    to re-read a market that moves in days. The employers that matter keep the
    hourly cadence; the rest are spaced out.
    """

    def _company(self, tier, last_checked):
        from app.models import Company

        return Company(
            id="x", name="X", tier=tier, adapter="greenhouse", adapter_arg="x",
            last_checked_at=last_checked,
        )

    def test_a_shortlisted_employer_is_always_due(self):
        from datetime import timedelta

        from app.models import CompanyTier, utcnow
        from app.services.discovery import _is_due

        now = utcnow()
        company = self._company(CompanyTier.DREAM, now - timedelta(minutes=1))
        assert _is_due(company, now), "a dream employer is checked every run"

    def test_a_normal_employer_waits_for_its_cadence(self):
        from datetime import timedelta

        from app.models import CompanyTier, utcnow
        from app.services.discovery import CADENCE_MINUTES, _is_due

        now = utcnow()
        wait = CADENCE_MINUTES[CompanyTier.NORMAL]
        assert not _is_due(self._company(CompanyTier.NORMAL, now - timedelta(minutes=5)), now)
        assert _is_due(
            self._company(CompanyTier.NORMAL, now - timedelta(minutes=wait + 1)), now
        )

    def test_an_employer_never_checked_is_due_immediately(self):
        from app.models import CompanyTier, utcnow
        from app.services.discovery import _is_due

        # Otherwise adding an employer means waiting out their tier before
        # seeing a single job from them.
        assert _is_due(self._company(CompanyTier.NORMAL, None), utcnow())

    def test_a_naive_timestamp_does_not_crash(self):
        # SQLite hands back naive datetimes; Postgres does not. Comparing the
        # two raises, and it would raise inside the scan rather than in a test.
        from datetime import datetime, timedelta

        from app.models import CompanyTier, utcnow
        from app.services.discovery import _is_due

        now = utcnow()
        naive = datetime.now().replace(tzinfo=None) - timedelta(hours=9)
        assert _is_due(self._company(CompanyTier.NORMAL, naive), now)


class TestARunOnlyClosesWhatItLookedAt:
    """The bug tiered cadence introduced, and must never reintroduce.

    Closing every open job not seen this run was correct while every source was
    asked every time. With a cadence it is catastrophic: a normal-tier employer
    is asked every four hours, so on the runs in between all of their still-open
    vacancies were marked closed and then reopened. Jobs vanished from the
    dashboard for hours and the closed count became meaningless.
    """

    def _open_job(self, session, job_id, company_id, source):
        from datetime import UTC, datetime

        from app.models import Job

        session.add(Job(
            id=job_id, company_name=company_id, company_id=company_id,
            title="Machine Learning Engineer", title_normalized="ml engineer",
            url=f"https://example.com/{job_id}", source=source,
            location_raw="Munich", city="Munich", country="DE",
            remote_policy="onsite", employment_type="full_time",
            description="PyTorch.", summary="PyTorch.",
            first_seen_at=datetime.now(UTC), last_seen_at=datetime.now(UTC),
            is_open=True, is_new=False, seniority="junior",
            language_requirement="english_only", salary_basis="unknown",
            score=70, score_technical=70, score_experience=70, score_language=70,
            score_location=70, score_education=70, score_freshness=70,
            score_domain=70, search_blob=job_id, status="new",
        ))
        session.commit()

    def test_an_employer_that_was_not_asked_keeps_its_jobs(self, db):
        from app.models import Job
        from app.services.discovery import _persist

        with db() as session:
            self._open_job(session, "asked|ml|munich", "asked-co", "greenhouse")
            self._open_job(session, "skipped|ml|munich", "skipped-co", "greenhouse")

            # A run that asked only one of the two employers, and saw nothing.
            _persist(session, [], Profile({}), {"asked-co"}, set())

            assert session.get(Job, "skipped|ml|munich").is_open is True, (
                "an employer this run never asked must not have its jobs closed"
            )
            assert session.get(Job, "asked|ml|munich").is_open is False, (
                "an employer that was asked and returned nothing has genuinely closed"
            )

    def test_a_board_that_did_not_run_keeps_its_jobs(self, db):
        from app.models import Job
        from app.services.discovery import _persist

        with db() as session:
            self._open_job(session, "board|ml|munich", "startup-co", "arbeitnow")
            _persist(session, [], Profile({}), set(), {"jobsch"})
            assert session.get(Job, "board|ml|munich").is_open is True

    def test_a_board_that_did_run_closes_what_it_no_longer_lists(self, db):
        from app.models import Job
        from app.services.discovery import _persist

        with db() as session:
            self._open_job(session, "board|ml|munich", "startup-co", "arbeitnow")
            _persist(session, [], Profile({}), set(), {"arbeitnow"})
            assert session.get(Job, "board|ml|munich").is_open is False

    def test_a_run_that_asked_nothing_closes_nothing(self, db):
        from app.models import Job
        from app.services.discovery import _persist

        with db() as session:
            self._open_job(session, "any|ml|munich", "any-co", "greenhouse")
            _persist(session, [], Profile({}), set(), set())
            assert session.get(Job, "any|ml|munich").is_open is True


class TestMatchKey:
    @pytest.mark.parametrize("a,b", [
        ("Celonis SE", "Celonis"),
        ("Helsing GmbH", "Helsing"),
        ("Booking.com B.V.", "Booking.com"),
        ("TRATON Group", "TRATON"),
        ("N26 AG", "N26"),
    ])
    def test_treats_legal_variants_as_one_employer(self, a, b):
        assert _match_key(a) == _match_key(b)

    @pytest.mark.parametrize("a,b", [
        ("Siemens", "Siemens Energy"),
        ("Airbus", "Airbus Helicopters"),
        ("Bosch", "Bosch Rexroth"),
    ])
    def test_does_not_collapse_genuinely_different_employers(self, a, b):
        assert _match_key(a) != _match_key(b)
