"""Location parsing and remote policy.

Only the posting's own location field is used to decide *where* a job is.
Descriptions routinely list every office a company owns, and reading that as
"this role is in Texas" throws away good jobs in Munich -- a mistake that cost
real results before the rule was tightened.

The description is used for one thing only: whether the work is remote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.base import RemotePolicy, strip_accents


@dataclass(frozen=True)
class LocationVerdict:
    city: str = ""
    country: str = ""
    tier_points: int = 0
    tier_label: str = ""
    remote_policy: str = RemotePolicy.UNKNOWN
    remote_evidence: str = ""


_REMOTE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (RemotePolicy.REMOTE, re.compile(
        r"\b(100\s*%\s*remote|fully[\s-]remote|remote[\s-]first|work\s+from\s+anywhere|"
        r"vollst[äa]ndig\s+remote|komplett\s+remote|remote\s*\(.*\)|"
        r"this\s+is\s+a\s+remote\s+(?:role|position))\b", re.I)),
    (RemotePolicy.HYBRID, re.compile(
        r"\b(hybrid|hybrid[\s-]working|\d\s*days?\s+(?:per|a)\s+week\s+(?:in\s+)?"
        r"(?:the\s+)?office|mobiles\s+arbeiten|teilweise\s+remote|"
        r"flexible\s+(?:work|working)\s+model)\b", re.I)),
    (RemotePolicy.ONSITE, re.compile(
        r"\b(on[\s-]site\s+(?:only|role|position)|vor\s+ort|pr[äa]senz|"
        r"no\s+remote|not\s+a\s+remote|office[\s-]based|100\s*%\s*(?:on[\s-]site|vor\s+ort))\b",
        re.I)),
    # Bare "remote" is weakest and checked last: it appears in sentences like
    # "remote work is not available" and must not outrank an explicit rule.
    (RemotePolicy.REMOTE, re.compile(r"\bremote\b", re.I)),
]


def detect_remote(title: str, location: str, description: str) -> tuple[str, str]:
    """Remote policy plus the phrase that decided it."""
    for field in (title or "", location or ""):
        for policy, pattern in _REMOTE_RULES:
            if match := pattern.search(field):
                return policy, match.group(0).strip()

    body = description or ""
    for policy, pattern in _REMOTE_RULES:
        if match := pattern.search(body):
            return policy, match.group(0).strip()

    return RemotePolicy.UNKNOWN, ""


def _match_terms(haystack: str, terms: list[str]) -> str:
    for term in terms:
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", haystack):
            return term
    return ""


class LocationResolver:
    """Resolves a raw location string against the profile's own geography.

    Built once per run rather than per posting: a sweep resolves thousands of
    locations and rebuilding the term lists each time is wasted work.
    """

    def __init__(self, tiers: dict[int, list[str]], countries: dict[str, list[str]]) -> None:
        # Highest-scoring tier first, so the best match wins on the first hit.
        self.tiers = sorted(tiers.items(), key=lambda kv: -kv[0])
        self.countries = countries

    def resolve(self, location_raw: str, title: str = "", description: str = "") -> LocationVerdict:
        haystack = strip_accents((location_raw or "").lower())

        points, label = 0, ""
        for tier_points, terms in self.tiers:
            if term := _match_terms(haystack, [strip_accents(t) for t in terms]):
                points, label = tier_points, term.title()
                break

        country = ""
        for code, terms in self.countries.items():
            if _match_terms(haystack, [strip_accents(t) for t in terms]):
                country = code.upper()
                break

        # The first comma-separated component is the city far more often than
        # not; when it is a country name instead, it is dropped below.
        city = (location_raw or "").split(",")[0].split(";")[0].strip()
        if city.lower() in {c.lower() for c in self.countries} or len(city) > 60:
            city = ""

        policy, evidence = detect_remote(title, location_raw, description)

        return LocationVerdict(
            city=city[:120],
            country=country,
            tier_points=points,
            tier_label=label,
            remote_policy=policy,
            remote_evidence=evidence,
        )

    def is_excluded(self, location_raw: str, exclude: list[str]) -> str:
        """Name the excluded region a posting sits in, or '' if it does not.

        A posting listing several sites, one of which is wanted, is kept: a
        role advertised for "Munich; Bangalore" is still a Munich role.
        """
        haystack = strip_accents((location_raw or "").lower())
        if not haystack.strip():
            return ""                       # unknown location is not a rejection
        hit = _match_terms(haystack, [strip_accents(t) for t in exclude])
        if not hit:
            return ""
        for _, terms in self.tiers:
            if _match_terms(haystack, [strip_accents(t) for t in terms]):
                return ""
        return hit


REMOTE_LABELS: dict[str, str] = {
    RemotePolicy.REMOTE: "Remote",
    RemotePolicy.HYBRID: "Hybrid",
    RemotePolicy.ONSITE: "On-site",
    RemotePolicy.UNKNOWN: "Not stated",
}
