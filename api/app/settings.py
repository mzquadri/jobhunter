"""Runtime settings and the candidate profile.

Two sources, deliberately separated:

  * ``Settings`` comes from the environment -- connection strings, intervals,
    optional API keys. Nothing here identifies a person.
  * ``Profile`` comes from a YAML file that is gitignored, with a committed
    example beside it. Name, contact details, skills and target employers live
    there.

That split is what makes the repository publishable while the deployment stays
personal. Anything that would identify the candidate belongs in the profile.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- database ----
    postgres_user: str = "jobhunter"
    postgres_password: str = "jobhunter"
    postgres_db: str = "jobhunter"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # ---- discovery ----
    # How often to scan, and whether to scan on startup, are application
    # settings rather than deployment settings: they live in the app_settings
    # row and are changed in the Automation screen, which takes effect without
    # a restart. Environment variables for them existed once and were ignored.
    #
    # Identifies the process in run records, so concurrent workers are
    # distinguishable in the run history.
    worker_name: str = "worker"

    # ---- http ----
    http_timeout: float = 30.0
    http_max_retries: int = 3
    http_backoff_seconds: float = 1.5
    max_workers: int = 8
    # Full-text fetches per run. Descriptions feed the language, salary and
    # seniority parsers, but each one is a request, so only the strongest
    # candidates are enriched.
    max_enrich: int = 120
    user_agent: str = (
        "CareerOS/1.0 (+https://github.com/mzquadri/jobhunter) "
        "personal job-search agent"
    )

    # ---- provider health ----
    # Consecutive failures before a source is backed off, and for how long.
    failures_before_backoff: int = 3
    backoff_minutes: int = 180

    # ---- paths ----
    # Seed only. Read once on first boot to create the settings row; after
    # that the database is authoritative and this file is never consulted.
    profile_path: Path = REPO_ROOT / "config" / "profile.yml"
    letter_path: Path = REPO_ROOT / "config" / "letter.md"
    drafts_dir: Path = REPO_ROOT / "data" / "drafts"

    # ---- optional integrations; all absent by default ----
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # ---- api ----
    log_level: str = "INFO"
    log_json: bool = True
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    # Requests per minute per client for mutating endpoints.
    rate_limit_per_minute: int = 120

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


class Profile:
    """The candidate profile, read from YAML.

    Thin accessors rather than a deep Pydantic model: the YAML is the source of
    truth and is meant to be edited by hand, so the code reads it rather than
    mirroring it in a schema that would have to be kept in step. Every accessor
    supplies a safe default, so a partially filled profile still runs.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw or {}

    def _section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name)
        return value if isinstance(value, dict) else {}

    def _list(self, section: str, key: str) -> list[str]:
        value = self._section(section).get(key) if section else self.raw.get(key)
        return [str(x).lower() for x in value] if isinstance(value, list) else []

    # ---- identity -------------------------------------------------------
    @property
    def candidate(self) -> dict[str, Any]:
        return self._section("candidate")

    @property
    def headline(self) -> str:
        c = self.candidate
        where = c.get("primary_city", "Europe")
        return f"Full-time AI/ML · {where} first · available {c.get('available_from', 'now')}"

    @property
    def education_level(self) -> str:
        return str(self.candidate.get("education_level", "msc")).lower()

    @property
    def german_level(self) -> str:
        return str(self.candidate.get("german_level", "a2")).lower()

    @property
    def years_experience(self) -> float:
        try:
            return float(self.candidate.get("years_experience", 1.5))
        except (TypeError, ValueError):
            return 1.5

    # ---- search ---------------------------------------------------------
    @property
    def search(self) -> dict[str, Any]:
        return self._section("search")

    @property
    def max_age_days(self) -> int:
        return int(self.search.get("max_age_days", 14))

    @property
    def archive_after_days(self) -> int:
        return int(self.search.get("archive_after_days", 30))

    @property
    def min_score(self) -> int:
        """What is persisted. Kept low so re-scoring can rescue a posting."""
        return int(self.search.get("min_score", 25))

    @property
    def recommend_min_score(self) -> int:
        """What is shown by default -- the "worth applying" line."""
        return int(self.search.get("recommend_min_score", 60))

    @property
    def high_match_score(self) -> int:
        return int(self.search.get("high_match_score", 80))

    @property
    def draft_min_score(self) -> int:
        return int(self.search.get("draft_min_score", 60))

    @property
    def keep_undated(self) -> bool:
        return bool(self.search.get("keep_undated", True))

    @property
    def target_salary_eur(self) -> int:
        return int(self.search.get("target_salary_eur", 70000))

    # ---- locations ------------------------------------------------------
    @property
    def location_tiers(self) -> dict[int, list[str]]:
        tiers = self._section("locations").get("tiers", {})
        if not isinstance(tiers, dict):
            return {}
        return {int(k): [str(x).lower() for x in v] for k, v in tiers.items()}

    @property
    def location_exclude(self) -> list[str]:
        return self._list("locations", "exclude")

    @property
    def country_map(self) -> dict[str, list[str]]:
        """country code -> city/region terms that imply it."""
        raw = self._section("locations").get("countries", {})
        if not isinstance(raw, dict):
            return {}
        return {str(k).lower(): [str(x).lower() for x in v] for k, v in raw.items()}

    # ---- roles ----------------------------------------------------------
    @property
    def role_words(self) -> list[str]:
        return self._list("roles", "include")

    @property
    def too_senior(self) -> list[str]:
        return self._list("roles", "too_senior")

    @property
    def not_fulltime(self) -> list[str]:
        return self._list("roles", "not_fulltime")

    @property
    def role_categories(self) -> dict[str, list[str]]:
        raw = self._section("roles").get("categories", {})
        if not isinstance(raw, dict):
            return {}
        return {str(k): [str(x).lower() for x in v] for k, v in raw.items()}

    # ---- profile content ------------------------------------------------
    @property
    def skills(self) -> dict[str, list[str]]:
        """Skill group -> terms. Groups let the matcher say *why* something
        matched ("strong PyTorch match") rather than counting keywords."""
        raw = self.raw.get("skills", {})
        if isinstance(raw, list):                       # tolerate a flat list
            return {"general": [str(x).lower() for x in raw]}
        if not isinstance(raw, dict):
            return {}
        return {str(k): [str(x).lower() for x in v] for k, v in raw.items()}

    @property
    def all_skills(self) -> list[str]:
        return sorted({s for group in self.skills.values() for s in group})

    @property
    def domains(self) -> list[str]:
        value = self.raw.get("domains")
        return [str(x).lower() for x in value] if isinstance(value, list) else []

    @property
    def preferred_industries(self) -> list[str]:
        value = self.raw.get("preferred_industries")
        return [str(x).lower() for x in value] if isinstance(value, list) else []

    # ---- scoring --------------------------------------------------------
    @property
    def weights(self) -> dict[str, Any]:
        return self._section("scoring")

    @property
    def flags(self) -> list[dict[str, Any]]:
        value = self.raw.get("flags")
        return value if isinstance(value, list) else []

    # ---- sources --------------------------------------------------------
    @property
    def companies(self) -> list[dict[str, Any]]:
        value = self.raw.get("companies")
        return value if isinstance(value, list) else []

    @property
    def company_queries(self) -> list[str]:
        value = self.raw.get("company_queries")
        return [str(x) for x in value] if isinstance(value, list) else ["machine learning"]

    @property
    def boards(self) -> dict[str, Any]:
        return self._section("boards")

    @property
    def saved_searches(self) -> list[dict[str, Any]]:
        value = self.raw.get("saved_searches")
        return value if isinstance(value, list) else []


def load_profile_from_seed() -> Profile:
    """Read the YAML seed directly.

    Only for tooling that has no database session -- tests, and the Alembic
    environment. Application code must go through
    ``app.services.profile_service``, because the database is authoritative
    once the settings row exists.
    """
    settings = get_settings()
    for path in (Path(settings.profile_path),
                 Path(settings.profile_path).with_name("profile.example.yml")):
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                return Profile(yaml.safe_load(fh) or {})
    return Profile({})
