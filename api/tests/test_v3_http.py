"""Conditional requests preserve listings and never prove vacancy closure."""
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx

from app.providers import run_provider
from app.providers.ats import GreenhouseProvider
from app.providers.base import retry_after_seconds
from tests.test_providers import make_ctx


def test_conditional_listing_replays_on_304():
    provider = GreenhouseProvider()
    first = make_ctx(lambda _: httpx.Response(200, headers={"ETag": '"v1"'}, json={
        "jobs": [{"id": 1, "title": "ML Engineer", "absolute_url":
                  "https://boards.greenhouse.io/test/jobs/1", "location": {"name": "Munich"}}],
    }))
    result = run_provider(provider, "test", "Test", "normal", first)
    assert result.ok
    assert result.fetch_state["etag"] == '"v1"'
    assert result.capabilities["complete_snapshot"]

    def unchanged(request):
        assert request.headers["If-None-Match"] == '"v1"'
        return httpx.Response(304)

    second = make_ctx(unchanged)
    second.cache = result.fetch_state
    replay = run_provider(provider, "test", "Test", "normal", second)
    assert replay.ok and len(replay.sightings) == 1
    assert replay.capabilities["not_modified"]
    assert not replay.capabilities["complete_snapshot"]
    assert replay.requests_made == 1


def test_304_without_cached_payload_fails_safely():
    result = run_provider(GreenhouseProvider(), "test", "Test", "normal",
                          make_ctx(lambda _: httpx.Response(304)))
    assert not result.ok


def test_changed_empty_snapshot_can_confirm_absence():
    result = run_provider(GreenhouseProvider(), "test", "Test", "normal",
                          make_ctx(lambda _: httpx.Response(200, json={"jobs": []})))
    assert result.ok and result.capabilities["complete_snapshot"]


def test_malformed_listing_is_not_an_empty_snapshot():
    result = run_provider(GreenhouseProvider(), "test", "Test", "normal",
                          make_ctx(lambda _: httpx.Response(200, json={"message": "error"})))
    assert not result.ok


def test_retry_after_date_and_long_delay_are_respected():
    future = datetime.now(UTC) + timedelta(hours=2)
    response = httpx.Response(429, headers={"Retry-After": format_datetime(future)})
    delay = retry_after_seconds(response)
    assert 7190 < delay <= 7200
    ctx = make_ctx(lambda _: httpx.Response(429, headers={"Retry-After": "7200"}))
    result = run_provider(GreenhouseProvider(), "test", "Test", "normal", ctx)
    assert result.rate_limited
    assert result.capabilities["retry_after_seconds"] == 7200
    assert result.requests_made == 1
