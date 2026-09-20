"""The gates are the part worth testing: each one exists because something
real slipped through before it was added."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.collector.matcher import Matcher
from app.collector.sources import RawPosting


def days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def posting(**kw) -> RawPosting:
    base = dict(
        company="Example GmbH",
        title="Machine Learning Engineer",
        url="https://example.com/job/1",
        source="test",
        location="Munich, Germany",
        posted=days_ago(1),
        description="We use PyTorch and Docker.",
    )
    base.update(kw)
    return RawPosting(**base)


@pytest.fixture
def matcher(profile) -> Matcher:
    return Matcher(profile)


class TestGates:
    @pytest.mark.parametrize("title", [
        "Praktikum Machine Learning",
        "Werkstudent Data Science (m/w/d)",
        "Machine Learning Internship",
        "PhD position in Deep Learning",
        "Data Science Industrial Placement",
        "VIE - Data Scientist",
    ])
    def test_rejects_anything_that_is_not_full_time(self, matcher, title):
        assert matcher.evaluate(posting(title=title)).keep is False

    @pytest.mark.parametrize("title", [
        "Senior Machine Learning Engineer",
        "Lead Data Scientist",
        "Head of AI",
        "Principal Research Scientist",
    ])
    def test_rejects_levels_a_graduate_cannot_apply_to(self, matcher, title):
        assert matcher.evaluate(posting(title=title)).keep is False

    def test_keeps_graduate_programmes(self, matcher):
        # "graduate" and "trainee" must never be treated as not-full-time
        assert matcher.evaluate(posting(title="Graduate AI Engineer")).keep is True
        assert matcher.evaluate(posting(title="Trainee Data Scientist")).keep is True

    def test_rejects_roles_outside_the_field(self, matcher):
        assert matcher.evaluate(posting(title="Warehouse Operative")).keep is False

    @pytest.mark.parametrize("location", [
        "Bangalore, India", "Hyderabad", "San Jose, California", "Tokyo, Japan",
    ])
    def test_rejects_jobs_outside_europe(self, matcher, location):
        # Without this gate a perfectly matched role in Bangalore outranked
        # every job in Munich.
        assert matcher.evaluate(posting(location=location)).keep is False

    def test_keeps_multi_site_postings_that_include_a_wanted_city(self, matcher):
        v = matcher.evaluate(posting(location="Munich; Bangalore; Austin"))
        assert v.keep is True

    def test_keeps_postings_with_no_location(self, matcher):
        assert matcher.evaluate(posting(location="")).keep is True

    def test_rejects_stale_postings(self, matcher, profile):
        old = posting(posted=days_ago(profile.max_age_days + 5))
        assert matcher.evaluate(old).keep is False

    def test_keeps_postings_right_at_the_age_limit(self, matcher, profile):
        edge = posting(posted=days_ago(profile.max_age_days))
        assert matcher.evaluate(edge).keep is True


class TestScoring:
    def test_fresher_postings_score_higher(self, matcher):
        new = matcher.evaluate(posting(posted=days_ago(1)))
        old = matcher.evaluate(posting(posted=days_ago(12)))
        assert new.score > old.score

    def test_dream_companies_score_higher(self, matcher):
        dream = posting()
        dream.tier = "DREAM"
        normal = posting()
        assert matcher.evaluate(dream).score > matcher.evaluate(normal).score

    def test_munich_outranks_the_rest_of_europe(self, matcher):
        munich = matcher.evaluate(posting(location="Munich, Germany"))
        lisbon = matcher.evaluate(posting(location="Lisbon, Portugal"))
        assert munich.score > lisbon.score

    def test_named_skills_are_reported(self, matcher):
        v = matcher.evaluate(posting(description="You will use PyTorch, Kafka and FastAPI."))
        assert {"pytorch", "kafka", "fastapi"} <= set(v.skills)


class TestFlags:
    def test_flags_german_requirement_and_costs_points(self, matcher):
        plain = matcher.evaluate(posting())
        german = matcher.evaluate(posting(description="Fließend Deutsch is required."))
        assert [f["code"] for f in german.flags] == ["DEUTSCH"]
        assert german.score < plain.score

    def test_flags_eu_citizenship(self, matcher):
        v = matcher.evaluate(posting(description="EU citizenship required for this role."))
        assert "EU-ONLY" in [f["code"] for f in v.flags]

    def test_flags_never_reject(self, matcher):
        v = matcher.evaluate(posting(description="No sponsorship available."))
        assert v.keep is True
        assert v.flags

    def test_score_never_goes_negative(self, matcher):
        v = matcher.evaluate(posting(
            description="EU citizenship required. No sponsorship. Fließend Deutsch.",
            location="",
        ))
        assert v.score >= 0
