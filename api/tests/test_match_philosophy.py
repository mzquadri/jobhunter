"""The 60% rule.

CareerOS answers "which current openings are realistic enough that applying is
worth my time?", not "which am I already perfect for". These tests pin that
down with the scenarios that decide it, written against the shipped example
profile so they also catch a configuration change that quietly breaks the
philosophy.

Assertions are on bands and directions rather than exact numbers. A test that
demands 74 turns every future weight change into a failing test to be silenced,
which is how scoring gets tuned until the tests pass instead of until the
results are right.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from app.enrich.relevance import Relevance, classify_relevance
from app.matching import MatchEngine
from app.settings import Profile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "config" / "profile.example.yml"

#: The threshold the whole product is built around.
WORTH_APPLYING = 60


@pytest.fixture(scope="module")
def engine() -> MatchEngine:
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    return MatchEngine(Profile(raw))


def evaluate(engine: MatchEngine, title: str, body: str, *, location="Munich, Germany",
             company="Example GmbH", tier="normal", age_days=2):
    return engine.evaluate(title, body, location, company, tier, age_days)


# ---------------------------------------------------------------------------
# §70.1 — strong fit, missing infrastructure, three years asked for
# ---------------------------------------------------------------------------
STRONG_WITH_GAPS = """
We are looking for a Machine Learning Engineer to join our perception team in
Munich. You will train and deploy deep learning models in Python and PyTorch,
build FastAPI services around them, and ship them with Docker.

Requirements:
- 3+ years of professional experience in machine learning
- Strong Python, PyTorch, scikit-learn
- Experience with Docker and PostgreSQL
- Kubernetes and AWS experience is a plus
- Fluent English; German is not required
"""


class TestStrongFitWithOrdinaryGaps:
    def test_is_worth_applying(self, engine):
        result = evaluate(engine, "Machine Learning Engineer", STRONG_WITH_GAPS)
        assert result.keep
        assert result.score >= WORTH_APPLYING, (
            f"scored {result.score}: a strong ML role in Munich missing only "
            f"Kubernetes and AWS must remain an application opportunity"
        )

    def test_the_gaps_are_named_rather_than_hidden(self, engine):
        result = evaluate(engine, "Machine Learning Engineer", STRONG_WITH_GAPS)
        gaps = " ".join(result.gaps).lower()
        assert "kubernetes" in gaps
        assert "aws" in gaps

    def test_the_experience_ask_is_stated_somewhere_visible(self, engine):
        # In the reasons rather than the gaps, because at this profile's level
        # "3+ years" is a realistic stretch and the product should say so.
        result = evaluate(engine, "Machine Learning Engineer", STRONG_WITH_GAPS)
        shown = " ".join(result.reasons + result.gaps).lower()
        assert "3+ years" in shown

    def test_the_reasons_name_what_actually_matched(self, engine):
        result = evaluate(engine, "Machine Learning Engineer", STRONG_WITH_GAPS)
        reasons = " ".join(result.reasons).lower()
        assert "pytorch" in reasons or "core ml" in reasons


# ---------------------------------------------------------------------------
# §70.2 — perfect technology, mandatory C1 German
# ---------------------------------------------------------------------------
class TestMandatoryGermanIsHeavilyPenalised:
    COMMON = (
        "Machine Learning Engineer. Python, PyTorch, deep learning, MLOps, "
        "Docker, Kubernetes. "
    )
    GERMAN = "Verhandlungssichere Deutschkenntnisse auf C1-Niveau sind zwingend erforderlich."
    ENGLISH = "All work is in English."
    BODY = COMMON + GERMAN

    def test_scores_far_below_the_same_role_in_english(self, engine):
        german = evaluate(engine, "Machine Learning Engineer", self.BODY)
        english = evaluate(engine, "Machine Learning Engineer", self.COMMON + self.ENGLISH)
        assert german.sub.language < 30, german.sub.language
        assert english.score - german.score >= 8, (
            f"English {english.score} vs mandatory C1 German {german.score}: "
            f"the penalty must be visible in the total, not just the sub-score"
        )

    def test_the_requirement_is_reported(self, engine):
        result = evaluate(engine, "Machine Learning Engineer", self.BODY)
        assert "german" in " ".join(result.gaps).lower()


# ---------------------------------------------------------------------------
# §70.3 — TensorFlow asked for, PyTorch on the profile
# ---------------------------------------------------------------------------
class TestTransferableSkills:
    BODY = """
    AI Engineer. You will build and train deep learning models with TensorFlow
    and Keras, serve them behind REST APIs, and work with SQL databases.
    Fluent English. 2 years of experience.
    """

    def test_pytorch_earns_credit_for_a_tensorflow_role(self, engine):
        result = evaluate(engine, "AI Engineer", self.BODY)
        assert result.keep
        reasons = " ".join(result.reasons).lower()
        assert "tensorflow" in reasons and "pytorch" in reasons, (
            "the transfer must be stated in words, not folded silently into a number"
        )

    def test_the_credit_shows_up_in_the_technical_score(self, engine):
        with_transfer = evaluate(engine, "AI Engineer", self.BODY)
        # The same posting naming a technology in no family earns nothing.
        without = evaluate(
            engine, "AI Engineer",
            self.BODY.replace("TensorFlow\n    and Keras", "COBOL and RPG"),
        )
        assert with_transfer.sub.technical >= without.sub.technical

    def test_an_unrelated_requirement_is_not_pretended_to_transfer(self, engine):
        result = evaluate(
            engine, "Machine Learning Engineer",
            "Machine learning role requiring Python, PyTorch and extensive "
            "SAP ABAP customisation experience.",
        )
        reasons = " ".join(result.reasons).lower()
        assert "abap" not in reasons and "sap" not in reasons


# ---------------------------------------------------------------------------
# §70.4 — four years asked for, otherwise strong
# ---------------------------------------------------------------------------
class TestFourYearsIsAStretchNotARejection:
    BODY = """
    Machine Learning Engineer, Munich. Python, PyTorch, deep learning, Docker,
    FastAPI, PostgreSQL, MLOps. We ask for 4+ years of experience.
    English-speaking team.
    """

    def test_survives_and_stays_visible(self, engine):
        result = evaluate(engine, "Machine Learning Engineer", self.BODY)
        assert result.keep
        assert result.score >= 50, f"scored {result.score}"

    def test_scores_below_the_same_role_asking_for_two(self, engine):
        four = evaluate(engine, "Machine Learning Engineer", self.BODY)
        two = evaluate(engine, "Machine Learning Engineer",
                       self.BODY.replace("4+ years", "2+ years"))
        assert two.score > four.score

    def test_the_ladder_is_monotonic(self, engine):
        scores = [
            evaluate(engine, "Machine Learning Engineer",
                     self.BODY.replace("4+ years", f"{n}+ years")).sub.experience
            for n in (2, 3, 4, 5, 7, 10)
        ]
        assert scores == sorted(scores, reverse=True), scores
        assert scores[0] > scores[-1] + 40, scores


# ---------------------------------------------------------------------------
# §70.5 — senior staff role wanting ten years
# ---------------------------------------------------------------------------
class TestSeniorStaffRoleScoresLow:
    def test_a_ten_year_staff_role_is_low_relevance(self, engine):
        result = evaluate(
            engine, "Senior Staff Machine Learning Engineer",
            "Staff-level role. Python, PyTorch, deep learning at scale. "
            "10+ years of industry experience required. You will set technical "
            "direction across several teams.",
        )
        assert result.score < WORTH_APPLYING, f"scored {result.score}"

    def test_it_is_still_searchable_rather_than_deleted(self, engine):
        result = evaluate(
            engine, "Senior Staff Machine Learning Engineer",
            "Staff-level role. Python, PyTorch. 10+ years required.",
        )
        assert result.keep, "seniority is a penalty, never a gate"


# ---------------------------------------------------------------------------
# §37/§38 — titles that do not contain a machine-learning phrase
# ---------------------------------------------------------------------------
class TestTitlesThatDoNotSayMachineLearning:
    REAL_BODY = (
        "You will develop perception algorithms using deep learning and "
        "computer vision. Python, PyTorch, object detection, sensor data. "
        "Docker, ROS. English-speaking team in Munich."
    )

    @pytest.mark.parametrize("title", [
        "Algorithm Developer",
        "Perception Engineer",
        "Autonomy Engineer",
        "Vision Engineer",
        "Intelligent Systems Engineer",
        "Research Software Engineer",
        "Decision Scientist",
        "Optimization Engineer",
        "Digital Twin Engineer",
        "Simulation & AI Engineer",
    ])
    def test_are_kept_when_the_description_backs_them_up(self, engine, title):
        result = evaluate(engine, title, self.REAL_BODY)
        assert result.keep, f"{title!r} was rejected: {result.reject_reason}"

    @pytest.mark.parametrize("title,body", [
        ("Sales Engineer", REAL_BODY),
        ("Recruiter", "We are hiring a recruiter for our AI team. Python is a plus."),
        ("Elektroniker", "Wartung von Anlagen."),
    ])
    def test_other_professions_are_still_rejected(self, engine, title, body):
        assert not evaluate(engine, title, body).keep

    def test_a_generic_title_with_no_technical_content_is_rejected(self, engine):
        result = evaluate(
            engine, "Software Engineer",
            "You will maintain our internal CRM integrations and write "
            "documentation for the sales team.",
        )
        assert not result.keep

    def test_an_uncertain_reading_costs_points_but_not_the_listing(self, engine):
        # "Platform Engineer" is not a targeted title and does not name the
        # field; it survives on description evidence alone and pays for that.
        certain = evaluate(engine, "Machine Learning Engineer", self.REAL_BODY)
        inferred = evaluate(engine, "Platform Engineer", self.REAL_BODY)
        assert inferred.keep
        assert inferred.score < certain.score, (
            f"inferred {inferred.score} vs stated {certain.score}"
        )

    def test_a_targeted_title_is_certain_even_if_generic_sounding(self, engine):
        # roles.include is the user's own statement of what counts as their
        # field, so a title they listed is never treated as a guess.
        result = evaluate(engine, "Simulation Engineer", self.REAL_BODY)
        assert result.keep
        assert not any("description rather than the title" in g for g in result.gaps)


class TestRelevanceClassifier:
    def test_grades_rather_than_decides(self):
        assert classify_relevance("Machine Learning Engineer", "").level is Relevance.CERTAIN
        assert classify_relevance(
            "Perception Engineer", "deep learning and PyTorch"
        ).level is Relevance.LIKELY
        assert classify_relevance("Sales Manager", "machine learning").level is Relevance.NO

    def test_a_bare_adjacent_title_is_not_enough(self):
        # "Algorithm Engineer" exists in telecoms and in finance too.
        verdict = classify_relevance(
            "Algorithm Engineer",
            "You will work on radio resource allocation for our 5G base stations.",
        )
        assert verdict.level is Relevance.NO


# ---------------------------------------------------------------------------
# The direction of the whole change
# ---------------------------------------------------------------------------
class TestFocusedRolesAreNotPunishedForBeingFocused:
    def test_a_deep_narrow_match_beats_a_shallow_broad_one(self, engine):
        deep = evaluate(
            engine, "Machine Learning Engineer",
            "Python, PyTorch, deep learning, neural networks, transformers, "
            "scikit-learn and model training. English. Munich.",
        )
        # One term from several groups, none of them deeply.
        shallow = evaluate(
            engine, "Machine Learning Engineer",
            "Some machine learning exposure, a little SQL, some Docker, "
            "occasional reporting. English. Munich.",
        )
        assert deep.sub.technical > shallow.sub.technical, (
            f"deep {deep.sub.technical} vs shallow {shallow.sub.technical}: "
            f"employers hire for depth"
        )
