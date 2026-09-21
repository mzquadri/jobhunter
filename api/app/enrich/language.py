"""Language-requirement classification.

Nine levels, as specified. The rules are ordered from most specific to least
and the first match wins, because a posting saying "English is our working
language, German C1 required for this role" means C1 -- the stricter statement
is the operative one, so strict patterns are checked first.

Every classification carries the fragment of the posting it came from. A
requirement the candidate cannot verify is a requirement they cannot trust.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.enrich.text import detect_language, find_evidence
from app.models.base import LanguageRequirement


@dataclass(frozen=True)
class LanguageVerdict:
    level: str
    evidence: str
    posting_language: str            # 'de' | 'en' | 'unknown'
    matched_phrase: str = ""

    @property
    def is_explicit(self) -> bool:
        return self.level != LanguageRequirement.UNCLEAR


# (level, [patterns]) in strictness order. Patterns are regex, matched
# case-insensitively against the full posting text.
_RULES: list[tuple[str, list[str]]] = [
    (LanguageRequirement.GERMAN_NATIVE, [
        r"deutsch\s+als\s+muttersprache",
        r"muttersprach\w*\s+deutsch",
        r"german\s+(?:on\s+)?a?\s*native[\s-]*(?:level|speaker)?",
        r"native[\s-]*(?:level\s+)?german",
        r"native\s+speaker\s+of\s+german",
    ]),
    (LanguageRequirement.GERMAN_C1_PLUS, [
        r"deutsch\w*\s*(?:auf\s*)?(?:niveau\s*)?c[12]\b",
        r"german\s*(?:at\s*)?(?:level\s*)?c[12]\b",
        r"verhandlungssicher\w*\s+deutsch",
        r"deutsch\w*\s+verhandlungssicher",
        r"flie(?:ß|ss)end\w*\s+deutsch",
        r"deutsch\w*\s+flie(?:ß|ss)end",
        r"fluent\s+(?:in\s+)?german",
        r"german\s+fluen\w+",
        r"sehr\s+gute\s+deutschkenntnisse",
        r"excellent\s+german",
        r"business\s*[- ]?fluent\s+german",
    ]),
    (LanguageRequirement.GERMAN_B2, [
        r"deutsch\w*\s*(?:auf\s*)?(?:niveau\s*)?b2\b",
        r"german\s*(?:at\s*)?(?:level\s*)?b2\b",
        r"gute\s+deutschkenntnisse",
        r"good\s+(?:command\s+of\s+)?german",
        r"solide\s+deutschkenntnisse",
    ]),
    (LanguageRequirement.GERMAN_B1, [
        r"deutsch\w*\s*(?:auf\s*)?(?:niveau\s*)?b1\b",
        r"german\s*(?:at\s*)?(?:level\s*)?b1\b",
        r"intermediate\s+german",
        r"konversationssicher\w*\s+deutsch",
    ]),
    (LanguageRequirement.GERMAN_BASIC, [
        r"deutsch\w*\s*(?:auf\s*)?(?:niveau\s*)?a[12]\b",
        r"german\s*(?:at\s*)?(?:level\s*)?a[12]\b",
        r"basic\s+german",
        r"grundkenntnisse\s+(?:in\s+)?deutsch",
        r"deutsch\w*\s+grundkenntnisse",
        r"elementary\s+german",
    ]),
    (LanguageRequirement.GERMAN_OPTIONAL, [
        r"german\s+(?:is\s+)?(?:a\s+)?(?:plus|bonus|advantage|nice[\s-]to[\s-]have|"
        r"desirable|beneficial|welcome|appreciated)",
        r"deutsch\w*\s+(?:sind\s+)?(?:von\s+vorteil|wünschenswert|wuenschenswert|"
        r"ein\s+plus|willkommen)",
        r"german\s+(?:skills\s+)?(?:are\s+)?optional",
        r"no\s+german\s+(?:is\s+)?(?:required|needed|necessary)",
        r"german\s+(?:is\s+)?not\s+(?:required|mandatory|necessary)",
        r"keine\s+deutschkenntnisse\s+(?:erforderlich|notwendig)",
        r"willing(?:ness)?\s+to\s+learn\s+german",
    ]),
    (LanguageRequirement.ENGLISH_ONLY, [
        r"english\s+is\s+(?:our|the)\s+(?:only\s+)?(?:official\s+|company\s+|primary\s+)?"
        r"(?:working|business|corporate)\s+language",
        r"(?:we|our\s+team)\s+(?:work|operate|communicate)s?\s+(?:entirely\s+|only\s+)?in\s+english",
        r"english[\s-]only\s+(?:environment|workplace|team)",
        r"all\s+communication\s+(?:is\s+)?in\s+english",
        r"unternehmenssprache\s+(?:ist\s+)?englisch",
    ]),
    (LanguageRequirement.ENGLISH_PREFERRED, [
        r"flue\w*\s+(?:in\s+)?english",
        r"english\s+flue\w+",
        r"excellent\s+(?:written\s+and\s+spoken\s+)?english",
        r"(?:very\s+)?good\s+(?:command\s+of\s+)?english",
        r"proficien\w+\s+(?:in\s+)?english",
        r"english\s*(?:at\s*)?(?:level\s*)?c[12]\b",
        r"gute\s+englischkenntnisse",
        r"sehr\s+gute\s+englischkenntnisse",
    ]),
]

_COMPILED: list[tuple[str, list[re.Pattern[str]]]] = [
    (level, [re.compile(p, re.I) for p in patterns]) for level, patterns in _RULES
]


def classify_language(title: str, description: str) -> LanguageVerdict:
    """Determine what language ability a posting actually asks for."""
    text = f"{title}\n{description}"
    posting_language = detect_language(description)

    for level, patterns in _COMPILED:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                phrase = match.group(0)
                return LanguageVerdict(
                    level=level,
                    evidence=find_evidence(text, phrase) or phrase,
                    posting_language=posting_language,
                    matched_phrase=phrase,
                )

    # Nothing stated. The language the advertisement is written in is a hint,
    # but it is reported as evidence rather than promoted to a requirement --
    # inventing a requirement the employer never wrote would be exactly the
    # kind of manufactured data the spec forbids.
    if posting_language == "de":
        note = "No explicit language requirement found; the posting is written in German."
    elif posting_language == "en":
        note = "No explicit language requirement found; the posting is written in English."
    else:
        note = "No explicit language requirement found."

    return LanguageVerdict(
        level=LanguageRequirement.UNCLEAR,
        evidence=note,
        posting_language=posting_language,
    )


def classify_from_structured(language_skills: list) -> LanguageVerdict | None:
    """Classify from a provider's structured language field.

    jobs.ch publishes required languages as data -- ``[{"language": "de",
    "level": 3}]`` -- rather than leaving them in prose. That is better
    evidence than parsing a 150-character preview, but it is the board's
    summary of the employer's advertisement, not the advertisement itself, so
    the mapping is deliberately conservative: a high level is read as B2
    rather than C1, and the evidence string names where it came from.

    Returns None when there is nothing usable, so the caller can fall back.
    """
    if not language_skills:
        return None

    levels: dict[str, int] = {}
    for entry in language_skills:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("language") or "").lower()[:2]
        try:
            level = int(entry.get("level") or 0)
        except (TypeError, ValueError):
            level = 0
        if code:
            levels[code] = max(levels.get(code, 0), level)

    if not levels:
        return None

    described = ", ".join(f"{code.upper()} (level {lvl})" for code, lvl in sorted(levels.items()))
    evidence = f"Board lists required languages: {described}"

    german = levels.get("de")
    if german is not None:
        if german >= 3:
            level = LanguageRequirement.GERMAN_B2
        elif german == 2:
            level = LanguageRequirement.GERMAN_B1
        else:
            level = LanguageRequirement.GERMAN_BASIC
        return LanguageVerdict(level=level, evidence=evidence,
                               posting_language="de", matched_phrase=described)

    if "en" in levels:
        return LanguageVerdict(level=LanguageRequirement.ENGLISH_PREFERRED,
                               evidence=evidence, posting_language="en",
                               matched_phrase=described)
    return None


# Human-readable labels, so the API and the dashboard cannot drift apart.
LANGUAGE_LABELS: dict[str, str] = {
    LanguageRequirement.ENGLISH_ONLY: "English only",
    LanguageRequirement.ENGLISH_PREFERRED: "English preferred",
    LanguageRequirement.GERMAN_OPTIONAL: "German optional",
    LanguageRequirement.GERMAN_BASIC: "German A1/A2",
    LanguageRequirement.GERMAN_B1: "German B1",
    LanguageRequirement.GERMAN_B2: "German B2",
    LanguageRequirement.GERMAN_C1_PLUS: "German C1+",
    LanguageRequirement.GERMAN_NATIVE: "German native",
    LanguageRequirement.UNCLEAR: "Not stated",
}
