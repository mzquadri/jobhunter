"""Runtime settings and the candidate profile.

Settings come from the environment; the profile comes from a YAML file that is
deliberately kept out of the repository. Splitting them this way means the code
is publishable and the personal data is not.
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

    postgres_user: str = "jobhunter"
    postgres_password: str = "jobhunter"
    postgres_db: str = "jobhunter"
    postgres_host: str = "db"
    postgres_port: int = 5432

    sweep_interval_minutes: int = 60
    sweep_on_startup: bool = True
    log_level: str = "INFO"

    profile_path: Path = REPO_ROOT / "config" / "profile.yml"
    letter_path: Path = REPO_ROOT / "config" / "letter.md"
    drafts_dir: Path = REPO_ROOT / "data" / "drafts"

    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    http_timeout: float = 30.0
    max_workers: int = 8
    # Full-text fetches per sweep. Descriptions are what the warning flags read,
    # but each one is a request, so only the best candidates are enriched.
    max_enrich: int = 80

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

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
    """The candidate profile, loaded from YAML.

    Thin wrappers rather than a deep model: the YAML is the source of truth and
    is meant to be edited by hand, so the code reads it rather than mirroring
    it in a schema that would have to be kept in step.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    # ---- candidate ------------------------------------------------------
    @property
    def candidate(self) -> dict[str, Any]:
        return self.raw.get("candidate", {})

    @property
    def headline(self) -> str:
        c = self.candidate
        return f"Full-time AI/ML · Germany, Switzerland, EU · from {c.get('available_from', 'now')}"

    # ---- search ---------------------------------------------------------
    @property
    def max_age_days(self) -> int:
        return int(self.raw.get("search", {}).get("max_age_days", 14))

    @property
    def min_score(self) -> int:
        return int(self.raw.get("search", {}).get("min_score", 20))

    @property
    def draft_min_score(self) -> int:
        return int(self.raw.get("search", {}).get("draft_min_score", 55))

    @property
    def keep_undated(self) -> bool:
        return bool(self.raw.get("search", {}).get("keep_undated", True))

    # ---- matching -------------------------------------------------------
    @property
    def location_tiers(self) -> dict[int, list[str]]:
        tiers = self.raw.get("locations", {}).get("tiers", {})
        return {int(k): [str(x).lower() for x in v] for k, v in tiers.items()}

    @property
    def location_exclude(self) -> list[str]:
        return [str(x).lower() for x in self.raw.get("locations", {}).get("exclude", [])]

    def _roles(self, key: str) -> list[str]:
        return [str(x).lower() for x in self.raw.get("roles", {}).get(key, [])]

    @property
    def role_words(self) -> list[str]:
        return self._roles("include")

    @property
    def too_senior(self) -> list[str]:
        return self._roles("too_senior")

    @property
    def not_fulltime(self) -> list[str]:
        return self._roles("not_fulltime")

    @property
    def skills(self) -> list[str]:
        return [str(x).lower() for x in self.raw.get("skills", [])]

    @property
    def domains(self) -> list[str]:
        return [str(x).lower() for x in self.raw.get("domains", [])]

    @property
    def scoring(self) -> dict[str, Any]:
        return self.raw.get("scoring", {})

    @property
    def flags(self) -> list[dict[str, Any]]:
        return self.raw.get("flags", [])

    # ---- sources --------------------------------------------------------
    @property
    def companies(self) -> list[dict[str, Any]]:
        return self.raw.get("companies", [])

    @property
    def company_queries(self) -> list[str]:
        return self.raw.get("company_queries", ["machine learning"])

    @property
    def boards(self) -> dict[str, Any]:
        return self.raw.get("boards", {})

    @property
    def watchlist(self) -> list[dict[str, str]]:
        return self.raw.get("watchlist", [])


@lru_cache
def get_profile() -> Profile:
    settings = get_settings()
    path = Path(settings.profile_path)
    if not path.exists():
        example = path.with_name("profile.example.yml")
        raise FileNotFoundError(
            f"No profile at {path}. Copy {example.name} to {path.name} and edit it."
        )
    with path.open(encoding="utf-8") as fh:
        return Profile(yaml.safe_load(fh) or {})
