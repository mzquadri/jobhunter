"""Database models.

Importing every model here means Alembic's autogenerate and
``Base.metadata`` both see the full schema from a single import.
"""

from app.models.base import (
    LANGUAGE_ACCESSIBILITY,
    PENDING_STATUSES,
    ApplicationStatus,
    Base,
    CompanyTier,
    EmploymentType,
    LanguageRequirement,
    ProviderState,
    RemotePolicy,
    RunStatus,
    SalaryBasis,
    Seniority,
    normalize_title,
    slugify,
    strip_accents,
    utcnow,
)
from app.models.company import Company, SourceStatus
from app.models.job import Job, JobSource, StatusEvent
from app.models.run import ProviderHealth, Run, RunProvider
from app.models.search import SavedSearch
from app.models.settings import SETTINGS_ID, AppSettings, Notification

__all__ = [
    "LANGUAGE_ACCESSIBILITY",
    "PENDING_STATUSES",
    "SETTINGS_ID",
    "AppSettings",
    "ApplicationStatus",
    "Base",
    "Company",
    "CompanyTier",
    "SourceStatus",
    "EmploymentType",
    "Job",
    "JobSource",
    "LanguageRequirement",
    "Notification",
    "ProviderHealth",
    "ProviderState",
    "RemotePolicy",
    "Run",
    "RunProvider",
    "RunStatus",
    "SalaryBasis",
    "SavedSearch",
    "Seniority",
    "StatusEvent",
    "normalize_title",
    "slugify",
    "strip_accents",
    "utcnow",
]
