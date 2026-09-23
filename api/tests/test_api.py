"""API integration tests.

These run against a real schema on SQLite, so the whole request path is
exercised -- routing, filters, serialisation and the write path -- without
needing PostgreSQL in CI.

The one behaviour worth guarding above all others is that a discovery run
cannot destroy what the candidate typed. That is asserted directly in
``TestRunsNeverOverwriteHumanFields``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_session
from app.models import ApplicationStatus, Base, Company, Job, SavedSearch


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'test.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(session_factory, monkeypatch):
    """A TestClient wired to a throwaway SQLite schema.

    The startup sequence is stubbed out: it waits for PostgreSQL migrations
    and seeds the profile's companies and searches, none of which belongs in a
    test that asserts on exact counts.
    """
    from app import main as main_module

    monkeypatch.setattr(main_module, "wait_for_schema", lambda: None)
    monkeypatch.setattr(main_module, "SessionLocal", session_factory)
    monkeypatch.setattr(main_module, "sync_companies", lambda *a, **k: None)
    monkeypatch.setattr(main_module, "seed_saved_searches", lambda *a, **k: 0)
    app = main_module.app

    def override():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3000", "http://127.0.0.1:3000"],
)
def test_loopback_origins_are_allowed(client, origin):
    response = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_untrusted_origin_is_not_allowed(client):
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def make_job(session, **kw) -> Job:
    today = date.today()
    defaults = dict(
        id=kw.pop("id", "acme|machine learning engineer|munich"),
        company_name="Acme GmbH",
        title="Machine Learning Engineer",
        title_normalized="machine learning engineer",
        url="https://example.com/job/1",
        source="greenhouse",
        location_raw="Munich, Germany",
        city="Munich",
        country="DE",
        remote_policy="onsite",
        employment_type="full_time",
        description="You will build models in PyTorch.",
        summary="Build models.",
        posted_at=today - timedelta(days=2),
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        is_open=True,
        is_new=True,
        seniority="junior",
        language_requirement="english_only",
        salary_basis="unknown",
        skills=["pytorch"],
        domains=["automotive"],
        role_category="Machine Learning",
        score=75,
        score_technical=70, score_experience=80, score_language=100,
        score_location=95, score_education=85, score_freshness=92, score_domain=60,
        match_reasons=["Matches your core ml experience: pytorch"],
        match_gaps=[],
        flags=[],
        has_flags=False,
        search_blob="acme gmbh machine learning engineer munich de pytorch automotive",
        status=ApplicationStatus.NEW,
    )
    defaults.update(kw)
    job = Job(**defaults)
    session.add(job)
    session.commit()
    return job


@pytest.fixture
def seeded(session_factory):
    with session_factory() as session:
        session.add(Company(id="acme", name="Acme GmbH", tier="dream",
                            adapter="greenhouse", adapter_arg="acme"))
        session.add(Company(id="ferrari", name="Ferrari", tier="dream",
                            adapter=None, careers_url="https://example.com/careers"))
        session.commit()

        make_job(session, company_id="acme")
        make_job(
            session,
            id="other|senior data scientist|zurich",
            company_name="Other AG", title="Senior Data Scientist",
            title_normalized="senior data scientist",
            url="https://example.com/job/2",
            city="Zurich", country="CH", location_raw="Zurich, Switzerland",
            seniority="senior", language_requirement="german_c1_plus",
            role_category="Data Science",
            score=32, has_flags=True,
            flags=[{"code": "EU-ONLY", "why": "May require EU citizenship", "evidence": ""}],
            search_blob="other ag senior data scientist zurich ch",
            posted_at=date.today() - timedelta(days=9),
            is_new=False,
        )
        session.add(SavedSearch(name="Germany", description="German roles",
                                query={"country": "de"}, is_builtin=True))
        session.commit()
    return session_factory


# ---------------------------------------------------------------------------
class TestHealth:
    def test_reports_ok(self, client, seeded):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"


class TestListing:
    def test_primary_feed_excludes_legacy_non_full_time_titles(
        self, client, seeded, session_factory
    ):
        with session_factory() as session:
            make_job(session, id="legacy|postdoc|delft", title="Postdoc in Computer Vision")
            session.commit()
        response = client.get("/api/jobs")
        assert response.status_code == 200
        assert all("postdoc" not in item["title"].lower() for item in response.json()["items"])

    def test_returns_open_jobs(self, client, seeded):
        body = client.get("/api/jobs").json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_total_count_header(self, client, seeded):
        response = client.get("/api/jobs")
        assert response.headers["X-Total-Count"] == "2"

    @pytest.mark.parametrize("query,expected", [
        ("country=de", 1),
        ("country=ch", 1),
        ("min_score=70", 1),
        ("only_new=true", 1),
        ("only_clean=true", 1),
        ("language=english_only", 1),
        ("seniority=senior", 1),
        ("category=Machine%20Learning", 1),
        ("q=pytorch", 1),
        ("q=nothing-matches-this", 0),
        ("max_age_days=3", 1),
    ])
    def test_filters(self, client, seeded, query, expected):
        assert client.get(f"/api/jobs?{query}").json()["total"] == expected

    def test_tier_filter_uses_the_company_table(self, client, seeded):
        assert client.get("/api/jobs?tier=dream").json()["total"] == 1

    @pytest.mark.parametrize("sort,first", [
        ("score", "Machine Learning Engineer"),
        ("newest", "Machine Learning Engineer"),
        ("company", "Machine Learning Engineer"),
    ])
    def test_sorting(self, client, seeded, sort, first):
        items = client.get(f"/api/jobs?sort={sort}").json()["items"]
        assert items[0]["title"] == first

    def test_pagination(self, client, seeded):
        body = client.get("/api/jobs?limit=1&offset=0").json()
        assert len(body["items"]) == 1
        assert body["total"] == 2

    def test_hidden_jobs_are_excluded_by_default(self, client, seeded, session_factory):
        with session_factory() as session:
            job = session.get(Job, "acme|machine learning engineer|munich")
            job.hidden = True
            session.commit()
        assert client.get("/api/jobs").json()["total"] == 1
        assert client.get("/api/jobs?include_hidden=true").json()["total"] == 2

    def test_labels_are_filled_in(self, client, seeded):
        job = client.get("/api/jobs?sort=score").json()["items"][0]
        assert job["language_label"] == "English only"
        assert job["seniority_label"] == "Junior"
        assert job["remote_label"]


class TestDetail:
    def test_returns_the_full_record(self, client, seeded):
        body = client.get("/api/jobs/acme%7Cmachine%20learning%20engineer%7Cmunich").json()
        assert body["title"] == "Machine Learning Engineer"
        assert body["description"]
        assert "sub_scores" in body
        assert set(body["sub_scores"]) == {
            "technical", "experience", "language", "location",
            "education", "freshness", "domain",
        }

    def test_unknown_id_is_404(self, client, seeded):
        assert client.get("/api/jobs/does-not-exist").status_code == 404


class TestSalaryIsNeverInvented:
    def test_absent_salary_renders_as_nothing(self, client, seeded):
        job = client.get("/api/jobs?sort=score").json()["items"][0]
        assert job["salary"]["basis"] == "unknown"
        assert job["salary"]["display"] == ""
        assert job["salary"]["annual_eur_min"] is None

    def test_converted_salary_is_marked_derived(self, client, seeded, session_factory):
        with session_factory() as session:
            job = session.get(Job, "acme|machine learning engineer|munich")
            job.salary_basis = "explicit"
            job.salary_min = 120000
            job.salary_currency = "CHF"
            job.salary_period = "year"
            job.salary_annual_eur_min = 127200
            job.salary_annual_eur_max = 127200
            session.commit()
        job = client.get("/api/jobs/acme%7Cmachine%20learning%20engineer%7Cmunich").json()
        assert job["salary"]["is_derived"] is True
        assert job["salary"]["display"].startswith("≈")


class TestWritePath:
    JOB = "/api/jobs/acme%7Cmachine%20learning%20engineer%7Cmunich"

    def test_star_and_hide(self, client, seeded):
        body = client.patch(self.JOB, json={"starred": True}).json()
        assert body["starred"] is True

    def test_status_change_is_recorded_in_history(self, client, seeded):
        client.patch(self.JOB, json={"status": "interested", "status_note": "worth a look"})
        body = client.patch(self.JOB, json={"status": "applied"}).json()
        assert body["status"] == "applied"
        assert len(body["history"]) == 2
        assert body["history"][0]["to_status"] == "applied"

    def test_applying_fills_in_the_date(self, client, seeded):
        body = client.patch(self.JOB, json={"status": "applied"}).json()
        assert body["applied_at"] == date.today().isoformat()

    def test_applying_schedules_the_follow_up(self, client, seeded):
        """Without this the follow-up reminder could never fire."""
        after = client.get("/api/settings").json()["profile"]["notifications"][
            "follow_up_after_days"
        ]
        body = client.patch(self.JOB, json={"status": "applied"}).json()
        expected = date.today() + timedelta(days=after)
        assert body["follow_up_at"] == expected.isoformat()

    def test_a_follow_up_date_you_chose_is_left_alone(self, client, seeded):
        chosen = (date.today() + timedelta(days=21)).isoformat()
        client.patch(self.JOB, json={"follow_up_at": chosen})
        body = client.patch(self.JOB, json={"status": "applied"}).json()
        assert body["follow_up_at"] == chosen

    def test_zero_days_means_no_follow_up_date(self, client, seeded):
        client.patch("/api/settings", json={"notifications": {"follow_up_after_days": 0}})
        body = client.patch(self.JOB, json={"status": "applied"}).json()
        assert body["applied_at"] == date.today().isoformat()
        assert body["follow_up_at"] is None

    def test_notes_and_contact_round_trip(self, client, seeded):
        body = client.patch(
            self.JOB,
            json={"notes": "Referred by a colleague", "contact_person": "A. Recruiter"},
        ).json()
        assert body["notes"] == "Referred by a colleague"
        assert body["contact_person"] == "A. Recruiter"

    def test_unknown_field_is_rejected(self, client, seeded):
        # extra="forbid" keeps the write surface exactly as declared.
        assert client.patch(self.JOB, json={"score": 100}).status_code == 422

    def test_patching_an_unknown_job_is_404(self, client, seeded):
        assert client.patch("/api/jobs/nope", json={"starred": True}).status_code == 404


class TestRunsNeverOverwriteHumanFields:
    """The invariant the whole design rests on."""

    def test_a_sweep_refreshes_scoring_but_not_the_candidates_columns(
        self, client, seeded, session_factory
    ):
        job_id = "acme|machine learning engineer|munich"
        client.patch(
            f"/api/jobs/{job_id.replace('|', '%7C').replace(' ', '%20')}",
            json={"status": "applied", "notes": "Spoke to the hiring manager",
                  "starred": True},
        )

        # Simulate what a discovery run writes: only run-owned columns.
        with session_factory() as session:
            job = session.get(Job, job_id)
            job.score = 88
            job.description = "Refreshed by a later sweep."
            job.last_seen_at = datetime.now(UTC)
            job.times_seen = (job.times_seen or 1) + 1
            session.commit()

        body = client.get(
            f"/api/jobs/{job_id.replace('|', '%7C').replace(' ', '%20')}"
        ).json()
        assert body["score"] == 88                     # refreshed
        assert body["status"] == "applied"             # preserved
        assert body["notes"] == "Spoke to the hiring manager"
        assert body["starred"] is True


class TestRecommendedOrdering:
    """§52 — the ordering the morning view actually uses.

    Score alone buries a role posted three hours ago behind a fortnight-old
    one; date alone puts a 34 above an 88. These assert the compromise rather
    than any particular arithmetic, so re-weighting stays possible.
    """

    def test_it_is_offered(self, client, seeded):
        assert client.get("/api/jobs?sort=recommended").status_code == 200

    def test_freshness_breaks_a_tie_on_score(self, client, session_factory):
        with session_factory() as session:
            make_job(session, id="old|ml|munich", score=80,
                     posted_at=date.today() - timedelta(days=12))
            make_job(session, id="new|ml|munich", score=80,
                     posted_at=date.today())
        order = [j["id"] for j in
                 client.get("/api/jobs?sort=recommended").json()["items"]]
        assert order.index("new|ml|munich") < order.index("old|ml|munich")

    def test_a_much_better_match_still_wins_over_freshness(self, client, session_factory):
        # The nudges are small next to the score on purpose: recency should
        # break ties, not overturn a real difference in fit.
        with session_factory() as session:
            make_job(session, id="fresh-weak|ml|munich", score=40,
                     posted_at=date.today())
            make_job(session, id="old-strong|ml|munich", score=88,
                     posted_at=date.today() - timedelta(days=12))
        order = [j["id"] for j in
                 client.get("/api/jobs?sort=recommended").json()["items"]]
        assert order.index("old-strong|ml|munich") < order.index("fresh-weak|ml|munich")

    def test_a_shortlisted_employer_is_lifted(self, client, session_factory):
        with session_factory() as session:
            session.add(Company(id="dreamco", name="Dream Co", tier="dream"))
            session.add(Company(id="plainco", name="Plain Co", tier="normal"))
            session.commit()
            make_job(session, id="dreamco|ml|munich", company_id="dreamco",
                     company_name="Dream Co", score=70, posted_at=date.today())
            make_job(session, id="plainco|ml|munich", company_id="plainco",
                     company_name="Plain Co", score=70, posted_at=date.today())
        order = [j["id"] for j in
                 client.get("/api/jobs?sort=recommended").json()["items"]]
        assert order.index("dreamco|ml|munich") < order.index("plainco|ml|munich")

    def test_a_role_needing_fluent_german_sinks(self, client, session_factory):
        with session_factory() as session:
            make_job(session, id="english|ml|munich", score=70,
                     language_requirement="english_only", posted_at=date.today())
            make_job(session, id="germanc1|ml|munich", score=70,
                     language_requirement="german_c1_plus", posted_at=date.today())
        order = [j["id"] for j in
                 client.get("/api/jobs?sort=recommended").json()["items"]]
        assert order.index("english|ml|munich") < order.index("germanc1|ml|munich")

    def test_a_role_from_an_unknown_employer_is_still_ranked(self, client, session_factory):
        # Outer join: a board-discovered role whose company row does not exist
        # yet must not vanish from the default view.
        with session_factory() as session:
            make_job(session, id="nobody|ml|munich", company_id=None,
                     company_name="Nobody Ltd", score=75, posted_at=date.today())
        ids = [j["id"] for j in
               client.get("/api/jobs?sort=recommended").json()["items"]]
        assert "nobody|ml|munich" in ids


class TestStats:
    def test_reports_counts_and_charts(self, client, seeded):
        body = client.get("/api/stats").json()
        assert body["total_open"] == 2
        assert set(body["charts"]) == {
            "by_day", "by_country", "by_category",
            "by_company", "by_language", "by_score_band",
        }
        assert body["charts"]["by_day"]

    def test_the_thresholds_the_interface_must_agree_with_are_sent(self, client, seeded):
        # The frontend renders "Worth applying" and "High priority" from these
        # rather than from constants of its own, so changing the setting moves
        # every screen together.
        body = client.get("/api/stats").json()
        assert body["recommend_min_score"] == 60
        assert body["high_match_score"] == 80

    def test_counts_use_the_configured_thresholds_not_magic_numbers(self, client, seeded):
        body = client.get("/api/stats").json()
        recommend, high = body["recommend_min_score"], body["high_match_score"]

        listed = client.get(f"/api/jobs?min_score={recommend}&limit=200").json()
        assert body["worth_applying"] == listed["total"], (
            "the dashboard's headline count and the list it links to must agree"
        )
        assert body["high_match"] == client.get(
            f"/api/jobs?min_score={high}&limit=200"
        ).json()["total"]

    def test_raising_the_threshold_moves_the_counts(self, client, seeded):
        before = client.get("/api/stats").json()["worth_applying"]
        client.patch("/api/settings", json={"search": {"recommend_min_score": 99}})
        after = client.get("/api/stats").json()
        assert after["recommend_min_score"] == 99
        assert after["worth_applying"] <= before

    def test_watchlist_only_contains_unautomatable_employers(self, client, seeded):
        body = client.get("/api/stats").json()
        names = {c["name"] for c in body["watchlist"]}
        assert names == {"Ferrari"}

    def test_pending_and_submitted_track_status(self, client, seeded):
        client.patch(
            "/api/jobs/acme%7Cmachine%20learning%20engineer%7Cmunich",
            json={"status": "applied"},
        )
        body = client.get("/api/stats").json()
        assert body["applications_pending"] == 1
        assert body["applications_submitted"] == 1


class TestCompanies:
    def test_lists_all(self, client, seeded):
        assert len(client.get("/api/companies").json()) == 2

    def test_separates_automated_from_manual(self, client, seeded):
        automated = client.get("/api/companies?automated=true").json()
        manual = client.get("/api/companies?automated=false").json()
        assert [c["name"] for c in automated] == ["Acme GmbH"]
        assert [c["name"] for c in manual] == ["Ferrari"]
        assert manual[0]["is_automated"] is False


class TestSavedSearches:
    def test_lists_seeded_searches(self, client, seeded):
        assert [s["name"] for s in client.get("/api/searches").json()] == ["Germany"]

    def test_runs_a_saved_search_through_the_same_filters(self, client, seeded):
        search_id = client.get("/api/searches").json()[0]["id"]
        results = client.get(f"/api/searches/{search_id}/results").json()
        direct = client.get("/api/jobs?country=de").json()
        assert results["total"] == direct["total"] == 1

    def test_rejects_an_unusable_query_on_write(self, client, seeded):
        response = client.post(
            "/api/searches",
            json={"name": "Bad", "query": {"not_a_filter": "x"}},
        )
        assert response.status_code == 422

    def test_accepts_a_valid_query(self, client, seeded):
        response = client.post(
            "/api/searches",
            json={"name": "Swiss", "query": {"country": "ch", "sort": "score"}},
        )
        assert response.status_code == 201

    def test_duplicate_name_is_rejected(self, client, seeded):
        assert client.post(
            "/api/searches", json={"name": "Germany", "query": {}}
        ).status_code == 409

    def test_builtin_searches_cannot_be_deleted(self, client, seeded):
        search_id = client.get("/api/searches").json()[0]["id"]
        assert client.delete(f"/api/searches/{search_id}").status_code == 409
