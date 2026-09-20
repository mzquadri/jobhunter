"""Decide whether a posting is worth the candidate's time, and how much.

Five gates and then a score:

  1  is it a real full-time job?      rejects Praktikum, Werkstudent, PhD
  2  is it a level they can apply to? rejects Senior, Lead, Head of
  3  is it their field at all?        needs an ML/AI/data word in the title
  4  can they actually take it?       rejects postings outside Europe
  5  is it still worth applying to?   rejects anything past max_age_days

Gate 4 exists because without it the scoring cheerfully ranked a role in
Bangalore above every job in Munich: the skills matched beautifully and nothing
told it the location made the job useless.

Flags never reject a posting -- keyword detection is imperfect -- but they
subtract points, so a role that probably needs EU citizenship does not outrank
one the candidate can actually take.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.collector.sources import RawPosting, days_old
from app.settings import Profile

ENTRY_WORDS = [
    "graduate", "entry level", "entry-level", "junior", "berufseinsteiger",
    "absolvent", "early career", "new grad", "trainee", "young professional",
    "einsteiger", "0-2 years", "1-2 years", "no experience required",
]


@dataclass
class Verdict:
    keep: bool
    reason: str = ""
    score: int = 0
    flags: list[dict] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    location_tier: int = 0
    location_label: str = ""
    age_days: int | None = None


def _find(words: list[str], haystack: str) -> list[str]:
    """Which of `words` occur in `haystack`, tolerating -, _ and / for spaces."""
    hits = []
    for w in words:
        pattern = re.escape(w).replace(r"\ ", r"[\s\-_/]+")
        if re.search(r"(?<![a-z0-9])" + pattern, haystack):
            hits.append(w)
    return hits


class Matcher:
    def __init__(self, profile: Profile) -> None:
        self.p = profile
        s = profile.scoring
        self.w_tier = {"DREAM": int(s.get("dream", 25)),
                       "PRIORITY": int(s.get("priority", 12)),
                       "NORMAL": 0}
        self.w_skill = int(s.get("skill_each", 5))
        self.cap_skill = int(s.get("skill_cap", 24))
        self.w_domain = int(s.get("domain_each", 4))
        self.cap_domain = int(s.get("domain_cap", 12))
        self.w_entry = int(s.get("entry_bonus", 8))
        self.freshness = [(int(a), int(b)) for a, b in s.get("freshness", [[2, 25], [14, 4]])]

    # ---- location -------------------------------------------------------
    def location_score(self, location: str, description: str = "") -> tuple[int, str]:
        """Highest matching tier wins."""
        text = f"{location} {description[:1500]}".lower()
        best, label = 0, ""
        for points, cities in self.p.location_tiers.items():
            for city in cities:
                if re.search(r"(?<![a-z])" + re.escape(city) + r"(?![a-z])", text):
                    if points > best:
                        best, label = points, city.title()
                    break
        return best, label

    def outside_europe(self, location: str) -> str:
        """Only the location field is read, never the description.

        A Munich posting often lists global offices in its boilerplate, and
        reading that as 'this job is in Texas' would throw away good jobs.
        """
        where = (location or "").lower()
        if not where.strip():
            return ""                      # unknown location is not a rejection
        for region in self.p.location_exclude:
            if re.search(r"(?<![a-z])" + re.escape(region.strip()) + r"(?![a-z])", where):
                # a multi-site posting that also lists somewhere wanted is fine
                if self.location_score(where)[0] > 0:
                    return ""
                return region.strip()
        return ""

    # ---- the verdict ----------------------------------------------------
    def evaluate(self, posting: RawPosting) -> Verdict:
        title = (posting.title or "").lower()
        desc = (posting.description or "").lower()
        tags = (posting.tags or "").lower()
        company = (posting.company or "").lower()

        if blocked := _find(self.p.not_fulltime, title):
            return Verdict(False, f"not full-time ({blocked[0]})")

        if senior := _find(self.p.too_senior, title):
            return Verdict(False, f"too senior ({senior[0].strip()})")

        roles = _find(self.p.role_words, f"{title} {tags}")
        if not roles:
            return Verdict(False, "not an ML/AI/data role")

        if elsewhere := self.outside_europe(posting.location):
            return Verdict(False, f"outside Europe ({elsewhere})")

        age = days_old(posting.posted)
        if age is None and not self.p.keep_undated:
            return Verdict(False, "no posting date")
        if age is not None and age > self.p.max_age_days:
            return Verdict(False, f"stale ({age} days old)")

        # ---- score ------------------------------------------------------
        body = f"{title}\n{tags}\n{desc}"
        skills = _find(self.p.skills, body)
        domains = _find(self.p.domains, f"{body}\n{company}")

        score = self.w_tier.get(posting.tier, 0)
        score += min(len(skills) * self.w_skill, self.cap_skill)
        score += min(len(domains) * self.w_domain, self.cap_domain)

        loc_points, loc_label = self.location_score(posting.location, desc)
        score += loc_points

        if age is not None:
            for max_age, points in self.freshness:
                if age <= max_age:
                    score += points
                    break

        if _find(ENTRY_WORDS, body):
            score += self.w_entry

        flags = []
        for rule in self.p.flags:
            phrases = [str(x).lower() for x in rule.get("phrases", [])]
            if _find(phrases, body):
                flags.append({"code": rule["code"], "why": rule.get("explain", "")})
                score -= int(rule.get("penalty", 0))

        return Verdict(
            keep=True,
            score=max(score, 0),
            flags=flags,
            skills=skills[:10],
            domains=domains[:6],
            roles=roles[:3],
            location_tier=loc_points,
            location_label=loc_label,
            age_days=age,
        )
