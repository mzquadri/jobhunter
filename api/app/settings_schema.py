"""Validation for the profile document.

The profile used to be a YAML file a human edited, where a typo produced a
confusing failure three layers down during a scan. Now that it can be written
from the UI it has to be validated at the boundary, so a malformed document
can never reach the database.

The schema is strict about *shape* and permissive about *content*. Sections
are typed and bounds are enforced, but unknown keys are preserved rather than
rejected: the document is also the seed format, and refusing a key someone
added by hand would turn a forward-compatible file into a brittle one.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Tier = Literal["dream", "high", "normal", "ignored"]


class Candidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    primary_city: str = "Munich"
    available_from: str = "immediately"
    education_level: Literal["bsc", "msc", "phd"] = "msc"
    german_level: Literal["none", "a1", "a2", "b1", "b2", "c1", "c2", "native"] = "a2"
    years_experience: Annotated[float, Field(ge=0, le=50)] = 1.5
    headline: str = ""


class SearchPrefs(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_age_days: Annotated[int, Field(ge=1, le=365)] = 14
    archive_after_days: Annotated[int, Field(ge=1, le=3650)] = 30
    #: What is stored. Low on purpose: every scan re-scores, so a posting
    #: below today's bar can rise once a skill or a location tier changes.
    min_score: Annotated[int, Field(ge=0, le=100)] = 25
    #: What is shown by default. The product's central number -- a role where
    #: roughly 60% of the description is met is worth applying to.
    recommend_min_score: Annotated[int, Field(ge=0, le=100)] = 60
    #: The "read this first" line.
    high_match_score: Annotated[int, Field(ge=0, le=100)] = 80
    draft_min_score: Annotated[int, Field(ge=0, le=100)] = 60
    keep_undated: bool = True
    target_salary_eur: Annotated[int, Field(ge=0, le=1_000_000)] = 70_000
    # A preference, never a filter: a posting that stated no salary is not
    # evidence of a low one, so it must still be shown.
    salary_is_hard_filter: bool = False

    # No cross-field rule between min_score and draft_min_score on purpose.
    # An earlier version rejected draft_min_score < min_score as inconsistent,
    # which made raising the visibility threshold fail validation -- a
    # perfectly reasonable action. The two cannot actually conflict: drafts
    # are only considered for postings that were persisted, and persistence
    # already requires min_score, so the effective threshold is simply the
    # higher of the two.

    @property
    def effective_draft_score(self) -> int:
        return max(self.min_score, self.draft_min_score)


class Locations(BaseModel):
    model_config = ConfigDict(extra="allow")

    tiers: dict[int, list[str]] = Field(default_factory=dict)
    exclude: list[str] = Field(default_factory=list)
    countries: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("tiers", mode="before")
    @classmethod
    def coerce_tier_keys(cls, value: Any) -> Any:
        # YAML gives integer keys; JSON round-trips them as strings.
        if isinstance(value, dict):
            return {int(k): v for k, v in value.items()}
        return value


class Roles(BaseModel):
    model_config = ConfigDict(extra="allow")

    include: list[str] = Field(default_factory=list)
    too_senior: list[str] = Field(default_factory=list)
    not_fulltime: list[str] = Field(default_factory=list)
    categories: dict[str, list[str]] = Field(default_factory=dict)


class ScoringWeights(BaseModel):
    model_config = ConfigDict(extra="allow")

    technical: float = 0.26
    location: float = 0.20
    freshness: float = 0.16
    experience: float = 0.15
    language: float = 0.13
    domain: float = 0.06
    education: float = 0.04

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> ScoringWeights:
        total = sum(self.model_dump().values())
        if not 0.98 <= total <= 1.02:
            raise ValueError(f"scoring weights must sum to 1.0, got {total:.3f}")
        return self


class Scoring(BaseModel):
    model_config = ConfigDict(extra="allow")

    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    tier_bonus: dict[str, int] = Field(default_factory=lambda: {"dream": 10, "high": 5})
    seniority_penalty: dict[str, int] = Field(
        default_factory=lambda: {"senior": 30, "lead": 45, "executive": 60}
    )
    #: A language requirement beyond your own is not a missing nice-to-have --
    #: it decides whether applying can succeed. The sub-score alone is too
    #: small a lever to say so, so these subtract from the total as well.
    language_penalty: dict[str, int] = Field(
        default_factory=lambda: {
            "german_b2": 8, "german_c1_plus": 22, "german_native": 30
        }
    )
    freshness_curve: list[list[int]] = Field(
        default_factory=lambda: [[1, 100], [3, 92], [7, 75], [14, 45], [30, 15]]
    )

    @field_validator("freshness_curve")
    @classmethod
    def curve_is_pairs_and_descending(cls, value: list[list[int]]) -> list[list[int]]:
        if not value:
            raise ValueError("freshness_curve cannot be empty")
        for point in value:
            if len(point) != 2:
                raise ValueError("each freshness_curve point must be [days, score]")
        ages = [p[0] for p in value]
        if ages != sorted(ages):
            raise ValueError("freshness_curve must be ordered by increasing age")
        return value


class FlagRule(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    penalty: Annotated[int, Field(ge=0, le=100)] = 0
    explain: str = ""
    phrases: list[str] = Field(default_factory=list)


class CompanyEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    tier: Tier = "normal"
    # Absent for watchlist-only employers, which have no readable endpoint.
    adapter: str | None = None
    arg: str | None = None
    careers_url: str = ""
    industry: str = ""
    enabled: bool = True

    @model_validator(mode="after")
    def adapter_needs_an_argument(self) -> CompanyEntry:
        if self.adapter and not self.arg:
            raise ValueError(f"{self.name}: an adapter also needs an 'arg'")
        return self


class Boards(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: list[str] = Field(default_factory=lambda: ["arbeitnow", "jobsch"])
    arbeitnow_pages: Annotated[int, Field(ge=1, le=20)] = 4
    queries: list[str] = Field(default_factory=list)
    adzuna_countries: list[str] = Field(default_factory=lambda: ["de"])


class Automation(BaseModel):
    model_config = ConfigDict(extra="allow")

    #: 0 disables the schedule; the user can still scan by hand.
    scan_interval_minutes: Annotated[int, Field(ge=0, le=1440)] = 60
    scan_on_startup: bool = True
    enabled: bool = True


class Notifications(BaseModel):
    model_config = ConfigDict(extra="allow")

    high_match_threshold: Annotated[int, Field(ge=0, le=100)] = 80
    #: Days after applying before a follow-up is due. 0 sets no date at all,
    #: which is also what happens if the candidate clears the field by hand.
    follow_up_after_days: Annotated[int, Field(ge=0, le=90)] = 7
    notify_high_match: bool = True
    notify_dream_company: bool = True
    notify_run_failed: bool = True
    notify_job_closed: bool = True
    notify_follow_up_due: bool = True


class Appearance(BaseModel):
    model_config = ConfigDict(extra="allow")

    theme: Literal["system", "light", "dark"] = "dark"
    density: Literal["comfortable", "compact"] = "comfortable"


class SavedSearchEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str = ""
    query: dict[str, Any] = Field(default_factory=dict)
    pinned: bool = False


class ProfileDocument(BaseModel):
    """The whole settings document, as stored and as seeded."""

    model_config = ConfigDict(extra="allow")

    candidate: Candidate = Field(default_factory=Candidate)
    search: SearchPrefs = Field(default_factory=SearchPrefs)
    locations: Locations = Field(default_factory=Locations)
    roles: Roles = Field(default_factory=Roles)
    skills: dict[str, list[str]] = Field(default_factory=dict)
    domains: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)
    scoring: Scoring = Field(default_factory=Scoring)
    flags: list[FlagRule] = Field(default_factory=list)
    companies: list[CompanyEntry] = Field(default_factory=list)
    company_queries: list[str] = Field(default_factory=lambda: ["machine learning"])
    boards: Boards = Field(default_factory=Boards)
    saved_searches: list[SavedSearchEntry] = Field(default_factory=list)
    automation: Automation = Field(default_factory=Automation)
    notifications: Notifications = Field(default_factory=Notifications)
    appearance: Appearance = Field(default_factory=Appearance)

    @field_validator("skills", mode="before")
    @classmethod
    def accept_a_flat_skill_list(cls, value: Any) -> Any:
        # Tolerated so a hand-written seed does not have to group its skills.
        if isinstance(value, list):
            return {"general": value}
        return value

    def to_storage(self) -> dict[str, Any]:
        """The form written to the database: plain JSON, no None holes."""
        return self.model_dump(mode="json", exclude_none=False)


def validate_profile(raw: dict[str, Any]) -> ProfileDocument:
    """Validate a document, raising ``ValidationError`` with a usable message."""
    return ProfileDocument.model_validate(raw or {})


def merge_patch(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge an update into the stored document.

    Nested dictionaries merge one level deep, so the settings UI can save a
    single section without having to send the whole document back. Lists are
    replaced wholesale, because a list is a complete statement of intent --
    removing a target role has to actually remove it.
    """
    merged = dict(current)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
