"""Turning a raw posting into structured, auditable facts.

Each module here answers one question about a posting and returns its evidence
along with its answer, so every inference the dashboard shows can be traced
back to the words that produced it.
"""

from app.enrich.language import LANGUAGE_LABELS, LanguageVerdict, classify_language
from app.enrich.location import (
    REMOTE_LABELS,
    LocationResolver,
    LocationVerdict,
    detect_remote,
)
from app.enrich.salary import SalaryVerdict, extract_salary, format_salary
from app.enrich.seniority import SENIORITY_LABELS, SeniorityVerdict, classify_seniority
from app.enrich.skills import SkillExtractor, SkillVerdict
from app.enrich.text import clean_html, detect_language, find_evidence, summarise

__all__ = [
    "LANGUAGE_LABELS",
    "REMOTE_LABELS",
    "SENIORITY_LABELS",
    "LanguageVerdict",
    "LocationResolver",
    "LocationVerdict",
    "SalaryVerdict",
    "SeniorityVerdict",
    "SkillExtractor",
    "SkillVerdict",
    "classify_language",
    "classify_seniority",
    "clean_html",
    "detect_language",
    "detect_remote",
    "extract_salary",
    "find_evidence",
    "format_salary",
    "summarise",
]
