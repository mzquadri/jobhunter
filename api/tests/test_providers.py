"""Provider parsing tests.

Every provider is exercised against a recorded response shape rather than a
live endpoint, so the suite is deterministic and runs offline in CI. The
fixtures are trimmed copies of what these APIs actually returned on
21 Sep 2026 -- they are test data, clearly marked as such, and never reach the
application.

The behaviours worth pinning down are the ones that broke in practice:
Workday's per-tenant posting-date facet, its missing location field, and
Greenhouse's two different date fields.
"""

from __future__ import annotations

import httpx
import pytest

from app.providers import REGISTRY, FetchContext, run_provider
from app.providers.base import Provider
from app.security import RateLimit
from app.settings import get_settings


def make_ctx(handler, queries=("machine learning",), max_age_days=14) -> FetchContext:
    """A FetchContext whose transport answers from ``handler`` rather than the
    network."""
    return FetchContext(
        queries=list(queries),
        max_age_days=max_age_days,
        settings=get_settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        limiter=RateLimit(per_minute=0),          # no pacing in tests
    )


def json_response(payload, status=200) -> httpx.Response:
    return httpx.Response(status, json=payload)


# ---------------------------------------------------------------------------
# Workday
# ---------------------------------------------------------------------------
WORKDAY_WITH_FACET = {
    "total": 2,
    "facets": [
        {
            "facetParameter": "startDate",
            "values": [
                {"id": "facet-1day", "descriptor": "1 Day", "count": 2},
                {"id": "facet-1week", "descriptor": "1 Week", "count": 9},
                {"id": "facet-old", "descriptor": "12+ Weeks", "count": 40},
            ],
        }
    ],
    "jobPostings": [
        {
            "title": "Machine Learning Engineer",
            "externalPath": "/job/Munich/Machine-Learning-Engineer_JR10389233",
            "postedOn": "Posted 2 Days Ago",
            "bulletFields": ["JR10389233", "Munich"],
        },
        {
            "title": "Data Scientist",
            "externalPath": "/job/Hamburg/Data-Scientist_JR10400000",
            "postedOn": "Posted 30+ Days Ago",
            "bulletFields": ["JR10400000", "Hamburg"],
        },
    ],
}

# Most tenants do not expose the posting-date facet at all. Verified against
# Roche, ABB, Thales, Novartis, Philips, Logitech and Accenture.
WORKDAY_NO_FACET = {
    "total": 2,
    "facets": [{"facetParameter": "jobFamilyGroup", "values": []}],
    "jobPostings": [
        {
            "title": "AI / ML Engineer",
            "externalPath": "/job/Bengaluru/AI---ML-Engineer_ATCI-5008345-S186611",
            "postedOn": "Posted 1 Day Ago",
            # No locationsText -- the location lives only in bulletFields.
            "bulletFields": ["ATCI-5008345-S186611", "Bengaluru, Bdc7C"],
        },
        {
            "title": "AI / ML Engineer",
            "externalPath": "/job/Bengaluru/AI---ML-Engineer_ATCI-5008361-S186610",
            "postedOn": "Posted 1 Day Ago",
            "bulletFields": ["ATCI-5008361-S186610", "Bengaluru, Bdc7C"],
        },
    ],
}


class TestWorkday:
    def test_uses_the_posting_date_facet_when_the_tenant_offers_one(self):
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json
            seen.append(json.loads(request.content))
            return json_response(WORKDAY_WITH_FACET)

        result = run_provider(
            REGISTRY["workday"], "ag|wd3|Airbus", "Airbus", "dream",
            make_ctx(handler),
        )
        assert result.capabilities["date_filter"] == "server"
        # The probe runs unfiltered; every later request carries the facet.
        applied = [r["appliedFacets"] for r in seen[1:]]
        assert applied and all("startDate" in a for a in applied)
        assert all("facet-old" not in a["startDate"] for a in applied)

    def test_falls_back_to_client_side_filtering_without_a_facet(self):
        result = run_provider(
            REGISTRY["workday"], "roche|wd3|roche-ext", "Roche", "high",
            make_ctx(lambda _r: json_response(WORKDAY_NO_FACET)),
        )
        # A missing facet is a tenant capability, not an error.
        assert result.ok
        assert result.capabilities["date_filter"] == "client"
        assert result.capabilities["pages_per_query"] > 2

    def test_reads_location_from_bullet_fields(self):
        result = run_provider(
            REGISTRY["workday"], "accenture|wd103|AccentureCareers", "Accenture", "normal",
            make_ctx(lambda _r: json_response(WORKDAY_NO_FACET)),
        )
        # Without this, Accenture postings arrive with no location and slip
        # straight past the geography gate.
        assert all(s.location for s in result.sightings)
        assert "Bengaluru" in result.sightings[0].location

    def test_uses_the_requisition_id_as_external_id(self):
        result = run_provider(
            REGISTRY["workday"], "accenture|wd103|AccentureCareers", "Accenture", "normal",
            make_ctx(lambda _r: json_response(WORKDAY_NO_FACET)),
        )
        ids = {s.external_id for s in result.sightings}
        # Twenty-one Accenture requisitions share the title "AI / ML Engineer".
        # Distinct ids are what stops them collapsing into one job.
        assert "ATCI-5008345-S186611" in ids
        assert len(ids) == len(result.sightings)

    def test_drops_stale_postings(self):
        result = run_provider(
            REGISTRY["workday"], "ag|wd3|Airbus", "Airbus", "dream",
            make_ctx(lambda _r: json_response(WORKDAY_WITH_FACET)),
        )
        assert result.capabilities["stale_dropped"] > 0
        assert all(s.title != "Data Scientist" for s in result.sightings)

    def test_malformed_target_is_reported_not_raised(self):
        result = run_provider(
            REGISTRY["workday"], "not-a-valid-target", "X", "normal",
            make_ctx(lambda _r: json_response({})),
        )
        assert not result.ok
        assert "malformed" in result.error


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------
class TestGreenhouse:
    def test_prefers_first_published_over_updated_at(self):
        from app.providers.dates import days_old

        payload = {"jobs": [{
            "id": 123,
            "title": "Machine Learning Engineer",
            "absolute_url": "https://boards.greenhouse.io/helsing/jobs/123",
            "location": {"name": "Munich"},
            "first_published": "2026-09-19T10:00:00Z",
            # An edit today must not make a month-old role look brand new.
            "updated_at": "2026-09-21T10:00:00Z",
        }]}
        result = run_provider(
            REGISTRY["greenhouse"], "helsing", "Helsing", "high",
            make_ctx(lambda _r: json_response(payload)),
        )
        assert result.sightings[0].posted == "2026-09-19"
        assert days_old(result.sightings[0].posted) is not None


# ---------------------------------------------------------------------------
# SuccessFactors
# ---------------------------------------------------------------------------
SF_RSS = """<?xml version="1.0"?><rss><channel>
<item>
  <title><![CDATA[AI Engineer (m/w/d)]]></title>
  <link>https://jobs.bmwgroup.com/job/123</link>
  <pubDate>Sun, 21 Sep 2026 08:00:00 GMT</pubDate>
  <description><![CDATA[<p>You will build models in <b>PyTorch</b>.</p>]]></description>
</item>
<item>
  <title>Broken item with no link</title>
</item>
</channel></rss>"""


class TestSuccessFactors:
    def test_parses_the_feed_and_cleans_html(self):
        result = run_provider(
            REGISTRY["successfactors"], "jobs.bmwgroup.com", "BMW Group", "dream",
            make_ctx(lambda _r: httpx.Response(200, text=SF_RSS)),
        )
        assert len(result.sightings) == 1          # the malformed item is skipped
        sighting = result.sightings[0]
        assert sighting.title == "AI Engineer (m/w/d)"
        assert "PyTorch" in sighting.description
        assert "<b>" not in sighting.description


# ---------------------------------------------------------------------------
# boards
# ---------------------------------------------------------------------------
class TestJobsCh:
    def test_uses_structured_language_data_and_the_localised_link(self):
        payload = {
            "num_pages": 1,
            "documents": [{
                "job_id": "abc",
                "title": "Data Scientist",
                "company_name": "Example AG",
                "place": "Zurich",
                "regions": [{"name": None}],
                "publication_date": "2026-09-20T10:00:00+02:00",
                "preview": "Short preview only.",
                "language_skills": [{"language": "de", "level": 3}],
                "_links": {"detail_en": {"href": "https://www.jobs.ch/en/vacancies/detail/abc/"}},
            }],
        }
        result = run_provider(
            REGISTRY["jobsch"], "", "Board", "normal",
            make_ctx(lambda _r: json_response(payload)),
        )
        sighting = result.sightings[0]
        assert sighting.location.startswith("Zurich")     # `place`, not null regions
        assert sighting.url.endswith("/en/vacancies/detail/abc/")
        assert sighting.structured["language_skills"][0]["language"] == "de"

    def test_respects_the_documented_page_size(self):
        # The API answers 422 with "20 is the upper limit" for anything more.
        assert REGISTRY["jobsch"].PAGE_SIZE <= 20  # type: ignore[attr-defined]


class TestAdzuna:
    def test_absent_key_is_reported_as_unconfigured_not_failed(self):
        result = run_provider(
            REGISTRY["adzuna"], "de", "Board", "normal",
            make_ctx(lambda _r: json_response({})),
        )
        # An optional integration nobody configured is not an error.
        assert result.ok
        assert result.capabilities["configured"] is False
        assert result.sightings == []


# ---------------------------------------------------------------------------
# resilience
# ---------------------------------------------------------------------------
class TestFailureIsolation:
    def test_http_error_is_captured_with_the_servers_message(self):
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(
                422, json={"errors": [{"message": "20 is the upper limit"}]}
            )

        result = run_provider(
            REGISTRY["greenhouse"], "whoever", "Whoever", "normal", make_ctx(handler)
        )
        assert not result.ok
        # The server's own explanation is what makes a break diagnosable.
        assert "upper limit" in result.error

    def test_a_crash_inside_a_provider_does_not_escape(self):
        def handler(_r: httpx.Request) -> httpx.Response:
            raise RuntimeError("something unexpected")

        result = run_provider(
            REGISTRY["greenhouse"], "x", "X", "normal", make_ctx(handler)
        )
        assert not result.ok
        assert result.sightings == []

    def test_unsafe_urls_are_refused(self):
        payload = {"jobs": [{
            "id": 1, "title": "ML Engineer",
            # A provider returning an internal address must not turn the
            # collector into a proxy for it.
            "absolute_url": "http://169.254.169.254/latest/meta-data/",
            "location": {"name": "Munich"},
            "first_published": "2026-09-20T10:00:00Z",
        }]}
        result = run_provider(
            REGISTRY["greenhouse"], "x", "X", "normal",
            make_ctx(lambda _r: json_response(payload)),
        )
        assert result.sightings == []

    @pytest.mark.parametrize("provider_name", sorted(REGISTRY))
    def test_every_provider_declares_a_name(self, provider_name):
        provider = REGISTRY[provider_name]
        assert isinstance(provider, Provider)
        assert provider.name == provider_name
