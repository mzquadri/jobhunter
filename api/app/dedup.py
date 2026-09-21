"""Deduplication.

One vacancy often arrives several times in a single run: from the employer's
own ATS, from a national board that syndicates it, and sometimes twice from
the same provider under two requisition ids. The dashboard must show it once
while keeping every sighting, so the candidate can see where it came from and
a dead link from one source does not lose the job.

Three signals, cheapest first:

  1. employer requisition id -- when two postings carry the same one from the
     same employer they are the same vacancy, whatever the titles say
  2. canonical key -- normalised company, title and city
  3. fuzzy title match within an employer -- catches "ML Engineer" versus
     "Machine Learning Engineer (f/m/d)" when the key misses

Full description similarity is deliberately not used. It would cost an O(n²)
comparison over several thousand postings every hour to resolve a handful of
cases the first three signals already catch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.base import normalize_title, slugify

# Requisition ids as employers actually write them. Ordered most to least
# specific, because a bare long number is the weakest of these.
#
# The lookarounds are hand-rolled rather than \b: these ids are usually
# embedded in a URL slug as "…engineer_JR10389233-1", and an underscore is a
# word character, so \b never fires where it is needed most.
_REQ_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9])(JR[-_]?\d{5,})(?!\d)", re.I),    # Workday
    re.compile(r"(?<![A-Za-z0-9])(REQ[-_]?\d{4,})(?!\d)", re.I),   # SuccessFactors, Taleo
    re.compile(r"(?<![A-Za-z0-9])(\d{6}-\d{5,})(?!\d)"),           # Workday alternate
    re.compile(r"(?<![A-Za-z0-9])(R\d{6,})(?!\d)"),                # Greenhouse, Ashby
    re.compile(r"/(\d{7,})(?:[/?#]|$)"),                           # numeric id in a path
]

# Company suffixes that are noise for matching purposes.
_COMPANY_NOISE = re.compile(
    r"\b(gmbh|ag|se|kg|mbh|co|kgaa|plc|ltd|limited|inc|corp|corporation|"
    r"holding|holdings|group|gruppe|nv|bv|sa|sas|srl|spa|oy|ab|as|aps)\b\.?",
    re.I,
)

# Employer-direct sources are preferred over syndicated boards when choosing
# which sighting represents the vacancy.
_PROVIDER_RANK = {
    "workday": 0, "successfactors": 0, "smartrecruiters": 0, "greenhouse": 0,
    "lever": 0, "ashby": 0, "personio": 0, "workable": 0,
    "arbeitnow": 2, "jobsch": 2, "adzuna": 3,
}


def normalize_company(name: str) -> str:
    """Comparable form of an employer name.

    'BMW Group', 'BMW AG' and 'BMW' have to collapse, or the same vacancy is
    stored once per naming convention.
    """
    cleaned = _COMPANY_NOISE.sub(" ", (name or "").lower())
    return slugify(cleaned) or "unknown"


def normalize_city(location: str) -> str:
    """Coarse location key.

    Only the first component is used and country names are dropped: 'Munich',
    'Munich, Germany' and 'Munich, Bavaria, Germany' are one place.
    """
    first = re.split(r"[,;/|]", location or "")[0]
    first = re.sub(r"\(.*?\)", " ", first)
    return slugify(first)[:40]


def extract_requisition_id(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        for pattern in _REQ_PATTERNS:
            if match := pattern.search(text):
                return match.group(1).upper().replace("_", "-")
    return ""


def canonical_key(company: str, title: str, location: str) -> str:
    """Deterministic identity for a vacancy.

    Not the URL: most ATS platforms mint a fresh URL whenever a posting is
    edited, so keying on it announces the same job as new every time someone
    fixes a typo.
    """
    return f"{normalize_company(company)}|{normalize_title(title)}|{normalize_city(location)}"[:120]


def title_similarity(a: str, b: str) -> float:
    """Jaccard overlap of title tokens.

    Chosen over an edit-distance ratio because job titles differ by inserted
    words far more often than by typos: 'Machine Learning Engineer' versus
    'Machine Learning Engineer Perception' should read as close, and it does.
    """
    ta = set(normalize_title(a).split())
    tb = set(normalize_title(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


SIMILARITY_THRESHOLD = 0.72


@dataclass
class Sighting:
    """One provider's view of a posting, before merging."""

    provider: str
    company: str
    title: str
    url: str
    location: str = ""
    external_id: str = ""
    posted: str = ""
    description: str = ""
    tier: str = "normal"
    company_id: str | None = None
    tags: str = ""
    salary_hint: str = ""
    #: Facts a provider supplied as data rather than prose -- jobs.ch, for
    #: instance, publishes required languages as a structured field. Used only
    #: where the posting text itself is silent, and always attributed.
    structured: dict = field(default_factory=dict)

    @property
    def rank(self) -> int:
        return _PROVIDER_RANK.get(self.provider, 1)

    @property
    def requisition_id(self) -> str:
        return extract_requisition_id(self.external_id, self.url)


@dataclass
class JobGroup:
    """One real vacancy and every sighting of it."""

    key: str
    primary: Sighting
    sightings: list[Sighting] = field(default_factory=list)

    @property
    def providers(self) -> list[str]:
        return sorted({s.provider for s in self.sightings})

    @property
    def duplicate_count(self) -> int:
        return max(0, len(self.sightings) - 1)

    def best_description(self) -> str:
        """The fullest text any source supplied.

        Boards often carry a richer description than the ATS list endpoint,
        so the winner of the merge is not necessarily the best text.
        """
        return max((s.description or "" for s in self.sightings), key=len, default="")

    def earliest_posted(self) -> str:
        """The earliest date any source reported.

        A board that syndicated a vacancy a week after the employer published
        it must not make the job look newer than it is.
        """
        dates = sorted(s.posted for s in self.sightings if s.posted)
        return dates[0] if dates else ""


def _may_merge(group: JobGroup, candidate: Sighting) -> bool:
    """Whether weak evidence is allowed to merge ``candidate`` into ``group``.

    A provider's own identifiers are authoritative *within* that provider: if
    it reports two postings under different ids, they are two postings, and no
    amount of title similarity should overrule that.

    This matters in practice. Accenture advertises twenty-one separate
    Bengaluru requisitions all titled "AI / ML Engineer", and returns no
    location for any of them -- so the canonical key was identical and they
    collapsed into a single job. Their requisition ids differ, and that is the
    fact worth trusting.

    Matching requisition ids are checked before this and still merge, which is
    what lets a renamed posting stay a single job.
    """
    for existing in group.sightings:
        if existing.provider != candidate.provider:
            continue
        if (existing.external_id and candidate.external_id
                and existing.external_id != candidate.external_id):
            return False
    return True


def _better_primary(candidate: Sighting, current: Sighting) -> bool:
    """Prefer an employer-direct source, then the fuller description."""
    if candidate.rank != current.rank:
        return candidate.rank < current.rank
    return len(candidate.description or "") > len(current.description or "")


def deduplicate(sightings: list[Sighting]) -> list[JobGroup]:
    """Collapse sightings into one group per real vacancy."""
    groups: dict[str, JobGroup] = {}
    # (company, requisition id) -> group key, for cross-provider matching.
    by_requisition: dict[tuple[str, str], str] = {}
    # company -> its group keys, to bound the fuzzy comparison.
    by_company: dict[str, list[str]] = {}

    for sighting in sightings:
        if not (sighting.title and sighting.url):
            continue

        company = normalize_company(sighting.company)
        key = canonical_key(sighting.company, sighting.title, sighting.location)

        # 1. same employer requisition id is decisive
        target: str | None = None
        req = sighting.requisition_id
        if req and (existing := by_requisition.get((company, req))):
            target = existing

        # 2. exact canonical key
        if target is None and key in groups and _may_merge(groups[key], sighting):
            target = key

        # 3. fuzzy title within the same employer
        if target is None:
            for other_key in by_company.get(company, []):
                other = groups[other_key]
                if normalize_city(other.primary.location) != normalize_city(sighting.location):
                    continue
                if not _may_merge(other, sighting):
                    continue
                if title_similarity(other.primary.title, sighting.title) >= SIMILARITY_THRESHOLD:
                    target = other_key
                    break

        if target is None:
            groups[key] = JobGroup(key=key, primary=sighting, sightings=[sighting])
            by_company.setdefault(company, []).append(key)
            if req:
                by_requisition[(company, req)] = key
            continue

        group = groups[target]
        # The same provider reporting the same posting twice is not a merge
        # worth recording, and would otherwise violate the uniqueness
        # constraint on job_sources.
        if any(s.provider == sighting.provider
               and s.external_id == sighting.external_id for s in group.sightings):
            continue
        group.sightings.append(sighting)
        if req:
            by_requisition.setdefault((company, req), target)
        if _better_primary(sighting, group.primary):
            group.primary = sighting

    return list(groups.values())
