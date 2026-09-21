"""Declarative base, shared column helpers and the enums the schema uses.

Enums are stored as short strings rather than native PostgreSQL enum types.
Adding a value to a native enum needs a migration and a table rewrite; these
change as the parsers improve, so strings with an application-level enum are
the right trade here.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# enums
# ---------------------------------------------------------------------------
class CompanyTier(StrEnum):
    DREAM = "dream"
    HIGH = "high"
    NORMAL = "normal"
    IGNORED = "ignored"


class RemotePolicy(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    WORKING_STUDENT = "working_student"
    THESIS = "thesis"
    PHD = "phd"
    APPRENTICESHIP = "apprenticeship"
    UNKNOWN = "unknown"


class Seniority(StrEnum):
    GRADUATE = "graduate"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class LanguageRequirement(StrEnum):
    """Nine levels, as specified. Ordered from most to least accessible for a
    candidate whose German is elementary."""

    ENGLISH_ONLY = "english_only"
    ENGLISH_PREFERRED = "english_preferred"
    GERMAN_OPTIONAL = "german_optional"
    GERMAN_BASIC = "german_a1_a2"
    GERMAN_B1 = "german_b1"
    GERMAN_B2 = "german_b2"
    GERMAN_C1_PLUS = "german_c1_plus"
    GERMAN_NATIVE = "german_native"
    UNCLEAR = "unclear"


# How friendly each level is to an A2 speaker, 0-100. Used by the matcher and
# shown in the dashboard, so the two can never disagree.
LANGUAGE_ACCESSIBILITY: dict[str, int] = {
    LanguageRequirement.ENGLISH_ONLY: 100,
    LanguageRequirement.ENGLISH_PREFERRED: 95,
    LanguageRequirement.GERMAN_OPTIONAL: 88,
    LanguageRequirement.GERMAN_BASIC: 80,
    LanguageRequirement.UNCLEAR: 60,
    LanguageRequirement.GERMAN_B1: 45,
    LanguageRequirement.GERMAN_B2: 22,
    LanguageRequirement.GERMAN_C1_PLUS: 8,
    LanguageRequirement.GERMAN_NATIVE: 0,
}


class SalaryBasis(StrEnum):
    """Where a salary figure came from. Never let an estimate be displayed as
    if the employer stated it."""

    EXPLICIT = "explicit"      # the posting states it
    ESTIMATED = "estimated"    # derived, and must be labelled as such
    UNKNOWN = "unknown"        # no figure available; show nothing


class ApplicationStatus(StrEnum):
    NEW = "new"
    REVIEWING = "reviewing"
    INTERESTED = "interested"
    TO_APPLY = "to_apply"
    APPLIED = "applied"
    INTERVIEW = "interview"
    TECHNICAL_INTERVIEW = "technical_interview"
    HR_INTERVIEW = "hr_interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    IGNORED = "ignored"


# Statuses that mean the application is live and awaiting something.
PENDING_STATUSES = frozenset({
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.TECHNICAL_INTERVIEW,
    ApplicationStatus.HR_INTERVIEW,
    ApplicationStatus.OFFER,
})


class ProviderState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    SKIPPED = "skipped"


class RunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# normalisation helpers, shared by dedup and search
# ---------------------------------------------------------------------------
_PUNCT = re.compile(r"[^a-z0-9]+")

# Noise that employers append to titles and that must not defeat
# deduplication. Listed as separate alternatives rather than one clever
# pattern so each can be read and corrected on its own.
_TITLE_NOISE = re.compile(
    # Gender markers in every ordering employers use: (m/w/d), (f/m/d),
    # (d/f/m), (m/f/x), (w/m/gn) and so on. Enumerating orderings by hand
    # missed (f/m/d) in production, so this matches any combination.
    r"\(?\s*\b[mwfdxg]n?(?:\s*[/|·]\s*[mwfdxg]n?){1,3}\b\s*\)?"
    r"|\ball\s+genders?\b|\bdiv(?:ers[e]?)?\.?\b|\bgn\b"
    # Workload ranges and single percentages: "80-100%", "100 %", "(60%)".
    r"|\d{1,3}\s*[-–—]\s*\d{1,3}\s*%|\d{1,3}\s*%"
    # Reference numbers.
    r"|\bref\.?\s*\w*\d+\w*\b|\bjob\s*(?:id|nr\.?|no\.?)\s*[:#]?\s*\w*\d+\b"
    # Brackets left empty once their contents were removed.
    r"|\(\s*\)|\[\s*\]",
    re.I,
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_title(title: str) -> str:
    """Comparable form of a job title.

    'Senior ML Engineer (m/w/d) 80-100%' and 'Senior ML Engineer (all genders)'
    have to collapse to the same string or the same vacancy is stored twice.
    """
    t = strip_accents((title or "").lower())
    t = _TITLE_NOISE.sub(" ", t)
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def slugify(text: str, limit: int = 80) -> str:
    s = _PUNCT.sub("-", strip_accents((text or "").lower())).strip("-")
    return s[:limit] or "unknown"
