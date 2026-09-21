"""Settings storage and validation.

The behaviour that matters is the one that used to be impossible: a
preference changed through the application takes effect on the next scan,
without a file edit, a rebuild or a restart. That is asserted directly.
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import SETTINGS_ID, AppSettings, Base
from app.services import profile_service
from app.settings_schema import merge_patch, validate_profile

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "config" / "profile.example.yml"


@pytest.fixture
def db(tmp_path):
    """A throwaway schema, re-created per test."""
    engine = create_engine(f"sqlite:///{tmp_path/'settings.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def seed(monkeypatch):
    """Point the seed loader at the committed example."""
    monkeypatch.setattr(profile_service, "_seed_candidates", lambda: [EXAMPLE])


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
class TestValidation:
    def test_the_shipped_example_is_valid(self):
        raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
        document = validate_profile(raw)
        assert document.companies
        assert document.skills
        assert document.candidate.german_level == "a2"

    def test_an_empty_document_is_valid(self):
        # A fresh install with no config must still start.
        assert validate_profile({}).search.max_age_days == 14

    def test_scoring_weights_must_sum_to_one(self):
        with pytest.raises(ValidationError, match="sum to 1.0"):
            validate_profile({"scoring": {"weights": {
                "technical": 0.9, "location": 0.9, "freshness": 0.1,
                "experience": 0.1, "language": 0.1, "domain": 0.1, "education": 0.1,
            }}})

    def test_raising_the_visibility_threshold_is_allowed(self):
        # The two thresholds cannot conflict: drafts are only considered for
        # postings that were persisted, which already requires min_score.
        document = validate_profile({"search": {"min_score": 77, "draft_min_score": 60}})
        assert document.search.min_score == 77
        assert document.search.effective_draft_score == 77

    def test_out_of_range_values_are_rejected(self):
        with pytest.raises(ValidationError):
            validate_profile({"search": {"max_age_days": 0}})
        with pytest.raises(ValidationError):
            validate_profile({"search": {"min_score": 500}})

    def test_a_company_with_an_adapter_needs_an_argument(self):
        with pytest.raises(ValidationError, match="also needs an 'arg'"):
            validate_profile({"companies": [{"name": "X", "adapter": "greenhouse"}]})

    def test_a_watchlist_company_needs_no_adapter(self):
        document = validate_profile({"companies": [
            {"name": "Ferrari", "tier": "dream", "careers_url": "https://example.com"}
        ]})
        assert document.companies[0].adapter is None

    def test_freshness_curve_must_be_ordered(self):
        with pytest.raises(ValidationError, match="increasing age"):
            validate_profile({"scoring": {"freshness_curve": [[14, 40], [3, 90]]}})

    def test_a_flat_skill_list_is_accepted(self):
        # Tolerated so a hand-written seed need not group its skills.
        document = validate_profile({"skills": ["pytorch", "docker"]})
        assert document.skills == {"general": ["pytorch", "docker"]}

    def test_unknown_keys_are_preserved_not_rejected(self):
        document = validate_profile({"experimental_setting": 42})
        assert document.to_storage()["experimental_setting"] == 42


class TestMergePatch:
    def test_nested_sections_merge_rather_than_replace(self):
        merged = merge_patch(
            {"search": {"max_age_days": 14, "min_score": 25}},
            {"search": {"min_score": 40}},
        )
        assert merged["search"] == {"max_age_days": 14, "min_score": 40}

    def test_lists_are_replaced_wholesale(self):
        # A list is a complete statement of intent: removing a target role has
        # to actually remove it.
        merged = merge_patch({"domains": ["a", "b", "c"]}, {"domains": ["a"]})
        assert merged["domains"] == ["a"]


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------
class TestFirstBoot:
    def test_seeds_from_the_yaml_when_no_row_exists(self, db, seed):
        with db() as session:
            assert profile_service.get_row(session) is None
            row = profile_service.seed_if_missing(session)
            assert row.id == SETTINGS_ID
            assert row.profile["companies"]
            assert "profile" in row.seeded_from or "config" in row.seeded_from

    def test_a_seeded_install_is_not_yet_onboarded(self, db, seed):
        with db() as session:
            row = profile_service.seed_if_missing(session)
            assert row.onboarded is False
            assert profile_service.is_onboarded(session) is False

    def test_seeding_twice_does_not_overwrite(self, db, seed):
        with db() as session:
            profile_service.seed_if_missing(session)
            profile_service.update_document(session, {"search": {"min_score": 99}})
            # A restart calls this again; it must not undo the change.
            profile_service.seed_if_missing(session)
            assert profile_service.load_document(session).search.min_score == 99

    def test_starts_from_defaults_when_no_seed_is_available(self, db, monkeypatch):
        monkeypatch.setattr(profile_service, "_seed_candidates", lambda: [])
        with db() as session:
            row = profile_service.seed_if_missing(session)
            assert row.profile["search"]["max_age_days"] == 14
            assert "built-in" in row.seeded_from

    def test_an_invalid_seed_falls_back_rather_than_crashing(self, db, monkeypatch, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text("search:\n  max_age_days: 0\n", encoding="utf-8")
        monkeypatch.setattr(profile_service, "_seed_candidates", lambda: [bad])
        with db() as session:
            row = profile_service.seed_if_missing(session)
            assert "invalid" in row.seeded_from
            assert row.profile["search"]["max_age_days"] == 14


class TestUpdates:
    def test_a_partial_update_leaves_other_sections_alone(self, db, seed):
        with db() as session:
            profile_service.seed_if_missing(session)
            before = profile_service.load_document(session)
            profile_service.update_document(session, {"search": {"min_score": 55}})
            after = profile_service.load_document(session)
            assert after.search.min_score == 55
            assert after.search.max_age_days == before.search.max_age_days
            assert len(after.companies) == len(before.companies)

    def test_an_invalid_update_is_rejected_and_nothing_is_written(self, db, seed):
        with db() as session:
            profile_service.seed_if_missing(session)
            with pytest.raises(ValidationError):
                profile_service.update_document(session, {"search": {"max_age_days": -5}})
            assert profile_service.load_document(session).search.max_age_days == 14

    def test_onboarding_can_be_marked_complete(self, db, seed):
        with db() as session:
            profile_service.seed_if_missing(session)
            profile_service.mark_onboarded(session)
            assert profile_service.is_onboarded(session) is True

    def test_reset_restores_the_shipped_defaults(self, db, seed):
        with db() as session:
            profile_service.seed_if_missing(session)
            profile_service.update_document(session, {"search": {"min_score": 91}})
            profile_service.reset_to_seed(session)
            assert profile_service.load_document(session).search.min_score == 25


class TestPersistence:
    def test_settings_survive_a_restart(self, db, seed):
        """A new session is what a container restart looks like from here."""
        with db() as session:
            profile_service.seed_if_missing(session)
            profile_service.update_document(
                session, {"search": {"min_score": 66, "max_age_days": 21}}
            )

        with db() as fresh_session:                # simulates the restart
            document = profile_service.load_document(fresh_session)
            assert document.search.min_score == 66
            assert document.search.max_age_days == 21

    def test_no_yaml_is_read_once_the_row_exists(self, db, seed, monkeypatch):
        with db() as session:
            profile_service.seed_if_missing(session)

        # Make any further seed read explode. Nothing should touch it.
        def explode():
            raise AssertionError("the YAML seed was read after initialisation")

        monkeypatch.setattr(profile_service, "read_seed", explode)
        with db() as session:
            assert profile_service.load_document(session).search.max_age_days == 14


class TestScanUsesCurrentSettings:
    """The point of the whole change."""

    def test_a_changed_preference_reaches_the_matcher(self, db, seed):
        from app.matching import MatchEngine

        with db() as session:
            profile_service.seed_if_missing(session)

            engine_before = MatchEngine(profile_service.load_profile(session))
            assert engine_before.p.max_age_days == 14

            # The user narrows freshness in the UI.
            profile_service.update_document(session, {"search": {"max_age_days": 3}})

        # The next scan builds its engine from the database, as the worker does.
        with db() as session:
            engine_after = MatchEngine(profile_service.load_profile(session))
            assert engine_after.p.max_age_days == 3

            verdict = engine_after.evaluate(
                "Machine Learning Engineer", "PyTorch work.", "Munich, Germany",
                "Example", "normal", age_days=7,
            )
            # Seven days now exceeds the new window, so it is rejected.
            assert verdict.keep is False
            assert "3 days" in verdict.reject_reason

    def test_shortlisting_an_employer_survives_the_next_scan(self, db, seed):
        """A scan reconciles companies against the settings document.

        Writing the row alone looked right until the next scan overwrote it
        from the seed, so shortlisting an employer silently undid itself an
        hour later. The write has to reach the document too.
        """
        from app.models import Company
        from app.routers.ops import _persist_company_config
        from app.services.discovery import sync_companies

        with db() as session:
            profile_service.seed_if_missing(session)
            profile = profile_service.load_profile(session)
            sync_companies(session, profile)

            # Any configured employer that is not already shortlisted.
            row = next(
                c for c in session.scalars(select(Company)).all() if c.tier != "dream"
            )
            company_id, name = row.id, row.name

            row.tier = "dream"
            session.commit()
            _persist_company_config(session, company_id, {"tier": "dream"})

        # The next scan starts by reconciling the table with the document.
        with db() as session:
            sync_companies(session, profile_service.load_profile(session))
            assert session.get(Company, company_id).tier == "dream", (
                f"{name} lost its shortlist tier to the next scan"
            )

    def test_profile_loading_is_not_cached_between_calls(self, db, seed):
        with db() as session:
            profile_service.seed_if_missing(session)
            first = profile_service.load_profile(session)
            profile_service.update_document(session, {"search": {"min_score": 77}})
            second = profile_service.load_profile(session)
            assert first.min_score == 25
            assert second.min_score == 77


class TestStorageShape:
    def test_stored_document_is_plain_json(self, db, seed):
        import json

        with db() as session:
            row = profile_service.seed_if_missing(session)
            json.dumps(row.profile)            # must not raise

    def test_integer_tier_keys_survive_a_json_round_trip(self, db, seed):
        with db() as session:
            profile_service.seed_if_missing(session)
            profile = profile_service.load_profile(session)
            # JSON turns integer keys into strings; the accessor must coerce
            # them back or every location scores zero.
            assert all(isinstance(k, int) for k in profile.location_tiers)
            assert max(profile.location_tiers) >= 20


def test_app_settings_row_is_a_singleton(db, seed):
    with db() as session:
        profile_service.seed_if_missing(session)
        profile_service.seed_if_missing(session)
        assert session.query(AppSettings).count() == 1
