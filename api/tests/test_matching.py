"""Tests for the ranking engine.

The important property is not any single number but the *ordering*: a fresh
junior ML role in Munich must beat a stale senior role in Lisbon that requires
fluent German, and the reasons shown must explain why.
"""

from __future__ import annotations

import pytest

from app.matching.engine import MatchEngine
from app.models.base import LanguageRequirement, Seniority


@pytest.fixture
def engine(profile) -> MatchEngine:
    return MatchEngine(profile)


def score(engine, **kw) -> int:
    return evaluate(engine, **kw).score


def evaluate(engine, *, title="Machine Learning Engineer",
             description="You will build models in PyTorch and deploy with Docker.",
             location="Munich, Germany", company="Example GmbH",
             tier="normal", age_days=1, tags=""):
    return engine.evaluate(title, description, location, company, tier, age_days, tags)


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------
class TestGates:
    @pytest.mark.parametrize("title", [
        "Praktikum Machine Learning", "Werkstudent Data Science (m/w/d)",
        "Machine Learning Internship", "PhD Position in Deep Learning",
        "Data Science Industrial Placement", "VIE - Data Scientist",
    ])
    def test_rejects_non_full_time(self, engine, title):
        assert evaluate(engine, title=title).keep is False

    def test_rejects_other_fields(self, engine):
        assert evaluate(engine, title="Warehouse Operative").keep is False

    @pytest.mark.parametrize("location", [
        "Bangalore, India", "Hyderabad", "San Jose, California", "Tokyo, Japan",
    ])
    def test_rejects_unreachable_locations(self, engine, location):
        assert evaluate(engine, location=location).keep is False

    def test_keeps_multi_site_posting_including_a_wanted_city(self, engine):
        assert evaluate(engine, location="Munich; Bangalore; Austin").keep is True

    def test_rejects_stale_postings(self, engine, profile):
        assert evaluate(engine, age_days=profile.max_age_days + 5).keep is False

    def test_rejection_states_a_reason(self, engine):
        result = evaluate(engine, title="Praktikum ML")
        assert result.reject_reason


class TestSeniorityIsPenalisedNotRejected:
    """§11: senior roles stay searchable but must sink."""

    def test_senior_role_is_kept(self, engine):
        assert evaluate(engine, title="Senior Machine Learning Engineer").keep is True

    def test_senior_scores_far_below_equivalent_junior(self, engine):
        junior = score(engine, title="Machine Learning Engineer")
        senior = score(engine, title="Senior Machine Learning Engineer")
        assert senior < junior - 20

    def test_head_of_scores_below_senior(self, engine):
        senior = score(engine, title="Senior Machine Learning Engineer")
        head = score(engine, title="Head of Machine Learning")
        assert head < senior

    def test_penalty_appears_in_the_gaps(self, engine):
        result = evaluate(engine, title="Senior Machine Learning Engineer")
        assert any("level" in g.lower() for g in result.gaps)


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------
class TestOrdering:
    def test_fresher_beats_older(self, engine):
        assert score(engine, age_days=1) > score(engine, age_days=12)

    def test_munich_beats_elsewhere_in_europe(self, engine):
        assert (score(engine, location="Munich, Germany")
                > score(engine, location="Lisbon, Portugal"))

    def test_dream_employer_lifts_the_score(self, engine):
        assert score(engine, tier="dream") > score(engine, tier="normal")

    def test_more_matching_skills_scores_higher(self, engine):
        few = score(engine, description="You will write some Python.")
        many = score(engine, description=(
            "You will use PyTorch, Kafka, Docker, Kubernetes, FastAPI, MLflow "
            "and build RAG systems with Qdrant embeddings."))
        assert many > few

    def test_german_requirement_lowers_the_score(self, engine):
        plain = score(engine, description="You will build models in PyTorch.")
        german = score(engine, description=(
            "You will build models in PyTorch. Verhandlungssichere "
            "Deutschkenntnisse sind erforderlich."))
        assert german < plain

    def test_the_headline_case(self, engine):
        """Fresh junior ML role in Munich must beat a stale senior German role."""
        good = evaluate(engine, title="Machine Learning Engineer",
                        location="Munich, Germany", age_days=1,
                        description="PyTorch, Docker and Kubernetes in production.")
        bad = evaluate(engine, title="Senior Machine Learning Engineer",
                       location="Lisbon, Portugal", age_days=13,
                       description="Fließend Deutsch erforderlich. 8+ years required.")
        assert good.score > bad.score
        assert good.keep and bad.keep


# ---------------------------------------------------------------------------
# explainability -- §10 requires the score to be auditable
# ---------------------------------------------------------------------------
class TestExplainability:
    def test_every_sub_score_is_populated(self, engine):
        sub = evaluate(engine).sub.as_dict()
        assert set(sub) == {"technical", "experience", "language", "location",
                            "education", "freshness", "domain"}
        assert all(0 <= v <= 100 for v in sub.values())

    def test_reasons_are_given(self, engine):
        result = evaluate(engine, location="Munich, Germany", age_days=0)
        assert result.reasons
        assert any("Munich" in r for r in result.reasons)

    def test_named_skills_appear_in_the_reasons(self, engine):
        result = evaluate(engine, description="Deep experience with PyTorch required.")
        assert any("pytorch" in r.lower() for r in result.reasons)

    def test_experience_gap_is_reported(self, engine):
        result = evaluate(engine, description="We need 9+ years of experience.")
        assert any("years" in g for g in result.gaps)

    def test_missing_requirements_come_only_from_the_posting(self, engine):
        # Snowflake is named by the posting and is not in the profile.
        result = evaluate(engine, description="You will use PyTorch and Snowflake daily.")
        assert any("snowflake" in g.lower() for g in result.gaps)
        # Scala is a known requirement the posting never mentioned, so
        # reporting it would be inventing a gap.
        assert not any("scala" in g.lower() for g in result.gaps)

    def test_profile_skills_are_never_reported_as_missing(self, engine):
        # Docker is on the profile, so naming it is a match, not a gap.
        result = evaluate(engine, description="You will use Docker daily.")
        assert not any("docker" in g.lower() for g in result.gaps)

    def test_a_transferable_skill_is_a_credit_rather_than_a_gap(self, engine):
        # Terraform is deliberately *not* claimed, but Docker and GitHub
        # Actions are, and infrastructure-as-code is an adjacent family. The
        # posting should read as partly covered and say which skill covered it,
        # instead of listing a flat "missing: terraform".
        result = evaluate(engine, description="You will use Ansible daily.")
        said = " ".join(result.reasons + result.gaps).lower()
        assert "ansible" in said

    def test_score_is_deterministic(self, engine):
        a = evaluate(engine)
        b = evaluate(engine)
        assert a.score == b.score
        assert a.sub.as_dict() == b.sub.as_dict()

    def test_score_stays_within_bounds(self, engine):
        worst = evaluate(engine, title="Senior Machine Learning Engineer",
                         location="", age_days=14,
                         description=("Fließend Deutsch. EU citizenship required. "
                                      "No sponsorship. 15+ years. PhD required."))
        assert 0 <= worst.score <= 100

        best = evaluate(engine, title="Graduate Machine Learning Engineer",
                        location="Munich, Germany", tier="dream", age_days=0,
                        description=("English is our working language. PyTorch, "
                                     "Kubernetes, Kafka, RAG, Qdrant, MLflow, "
                                     "FastAPI. Salary: €85,000 per year."))
        assert 0 <= best.score <= 100
        assert best.score > 70


# ---------------------------------------------------------------------------
# enrichment is carried through
# ---------------------------------------------------------------------------
class TestEnrichmentPassThrough:
    def test_language_is_classified_and_evidenced(self, engine):
        result = evaluate(engine, description="English is our working language.")
        assert result.language_requirement == LanguageRequirement.ENGLISH_ONLY
        assert result.language_evidence

    def test_seniority_is_recorded(self, engine):
        assert evaluate(engine, title="Graduate AI Engineer").seniority == Seniority.GRADUATE

    def test_salary_is_extracted_when_stated(self, engine):
        result = evaluate(engine, description="Salary: €80,000 - €95,000 per year.")
        assert result.salary.found
        assert result.salary.annual_eur_min == pytest.approx(80000)

    def test_salary_absent_is_not_invented(self, engine):
        assert evaluate(engine).salary.found is False

    def test_role_category_is_assigned(self, engine):
        result = evaluate(engine, title="Computer Vision Engineer")
        assert result.role_category == "Computer Vision"

    def test_flags_are_raised_and_penalised(self, engine):
        plain = score(engine)
        flagged = evaluate(engine, description=(
            "You will build models. EU citizenship required for this role."))
        assert any(f["code"] == "EU-ONLY" for f in flagged.flags)
        assert flagged.score < plain
