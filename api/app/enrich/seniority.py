"""Seniority and required experience.

Two independent signals, because they disagree often enough to matter: a title
can say "Engineer" while the body asks for eight years, and a title can say
"Senior" where the body asks for three. The matcher sees both and penalises on
the worse of the two rather than trusting the title alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.enrich.text import find_evidence
from app.models.base import Seniority


@dataclass(frozen=True)
class SeniorityVerdict:
    level: str = Seniority.UNKNOWN
    min_years: int | None = None
    max_years: int | None = None
    evidence: str = ""
    title_signal: str = ""


# Checked in order; the first hit wins, so "Senior Staff" reads as lead-level.
_TITLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (Seniority.EXECUTIVE, re.compile(
        r"\b(chief|cto\b|cio\b|vp\b|vice[\s-]president|head\s+of|director|"
        r"abteilungsleiter|bereichsleiter|geschäftsführ\w+)", re.I)),
    (Seniority.LEAD, re.compile(
        # "Staff Software Engineer" and "Staff Research Scientist" put words
        # between the level and the discipline, so allow a couple.
        r"\b(lead\b|leader\b|principal\b|"
        r"staff\s+(?:\w+\s+){0,2}(?:engineer|scientist|researcher|developer)\b|"
        r"tech\s*lead|team\s*lead|teamlead|gruppenleiter|architect\b|"
        r"distinguished\b|fellow\b)", re.I)),
    (Seniority.SENIOR, re.compile(
        r"\b(senior|sr\.?\s|expert\b|experienced\b|erfahrene?r?\b)", re.I)),
    (Seniority.GRADUATE, re.compile(
        r"\b(graduate|absolvent\w*|new\s*grad|berufseinsteiger\w*|"
        r"trainee|traineeship|einsteiger\w*|entry[\s-]level)\b", re.I)),
    (Seniority.JUNIOR, re.compile(
        r"\b(junior|jr\.?\s|associate\b|nachwuchs\w*)\b", re.I)),
]

# "3+ years", "2-4 years", "at least 5 years", "mindestens 3 Jahre"
_YEARS_RANGE = re.compile(
    r"(\d{1,2})\s*(?:-|–|—|to|bis)\s*(\d{1,2})\s*\+?\s*"
    r"(?:years?|yrs?|jahre?n?)\b(?:[^.]{0,40}?(?:experience|erfahrung|berufserfahrung))?",
    re.I,
)
_YEARS_MIN = re.compile(
    r"(?:(?:at\s+least|minimum(?:\s+of)?|min\.?|mindestens|über|ueber|more\s+than|"
    r"upwards\s+of)\s*)?(\d{1,2})\s*\+\s*(?:years?|yrs?|jahre?n?)\b"
    r"|(?:at\s+least|minimum(?:\s+of)?|min\.?|mindestens)\s*(\d{1,2})\s*"
    r"(?:years?|yrs?|jahre?n?)\b",
    re.I,
)
_YEARS_PLAIN = re.compile(
    r"(\d{1,2})\s*(?:years?|yrs?|jahre?n?)\s*(?:of\s+)?"
    r"(?:relevant\s+|professional\s+|industry\s+|hands[\s-]on\s+)?"
    r"(?:experience|erfahrung|berufserfahrung)",
    re.I,
)

# Seniority implied by a stated number of years, used only when the title is
# silent.
def _level_from_years(min_years: int | None) -> str:
    if min_years is None:
        return Seniority.UNKNOWN
    if min_years <= 1:
        return Seniority.GRADUATE
    if min_years <= 3:
        return Seniority.JUNIOR
    if min_years <= 6:
        return Seniority.MID
    return Seniority.SENIOR


def extract_years(text: str) -> tuple[int | None, int | None, str]:
    """Smallest credible experience requirement stated anywhere in the text.

    Postings often list several ("3+ years Python, 5+ years leadership"); the
    lowest is the entry bar, which is the number that decides whether applying
    is realistic.
    """
    best_min: int | None = None
    best_max: int | None = None
    evidence = ""

    for match in _YEARS_RANGE.finditer(text):
        lo, hi = int(match.group(1)), int(match.group(2))
        if lo > hi or hi > 40:
            continue
        if best_min is None or lo < best_min:
            best_min, best_max, evidence = lo, hi, match.group(0)

    for pattern in (_YEARS_MIN, _YEARS_PLAIN):
        for match in pattern.finditer(text):
            value = next((int(g) for g in match.groups() if g), None)
            if value is None or value > 40:
                continue
            if best_min is None or value < best_min:
                best_min, evidence = value, match.group(0)
                best_max = best_max if best_max and best_max >= value else None

    return best_min, best_max, evidence.strip()


def classify_seniority(title: str, description: str) -> SeniorityVerdict:
    title_level = ""
    for level, pattern in _TITLE_RULES:
        if match := pattern.search(title or ""):
            title_level = level
            title_signal = match.group(0).strip()
            break
    else:
        title_signal = ""

    min_years, max_years, years_evidence = extract_years(description or "")

    # The title is authoritative when it makes a claim, because it is what the
    # employer chose to advertise. Years fill the gap when it does not.
    level = title_level or _level_from_years(min_years)

    evidence_parts = []
    if title_signal:
        evidence_parts.append(f"title says “{title_signal}”")
    if years_evidence:
        evidence_parts.append(f"posting asks for “{years_evidence}”")
    evidence = "; ".join(evidence_parts)
    if not evidence:
        evidence = "No seniority or experience requirement stated."
    elif years_evidence:
        evidence = find_evidence(description, years_evidence) or evidence

    return SeniorityVerdict(
        level=level or Seniority.UNKNOWN,
        min_years=min_years,
        max_years=max_years,
        evidence=evidence,
        title_signal=title_signal,
    )


SENIORITY_LABELS: dict[str, str] = {
    Seniority.GRADUATE: "Graduate",
    Seniority.JUNIOR: "Junior",
    Seniority.MID: "Mid-level",
    Seniority.SENIOR: "Senior",
    Seniority.LEAD: "Lead / Principal",
    Seniority.EXECUTIVE: "Executive",
    Seniority.UNKNOWN: "Not stated",
}
