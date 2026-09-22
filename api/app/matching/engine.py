"""The matching engine.

Every score here is derived and auditable. Nothing is random, nothing is a
magic constant buried in code -- the weights live in the profile, each
sub-score is computed from a stated rule, and the reasons shown in the
interface are generated from the same calculation that produced the number.
If the dashboard says "Strong PyTorch match", the technical sub-score rose
because the word PyTorch is in the posting.

Gates are deliberately few. Seniority is not one of them -- an excessive level
is a heavy penalty so the role sinks rather than disappearing -- and neither is
a missing requirement. The product answers "is applying worth my time?", not
"am I already the perfect candidate?", and a graduate who meets roughly 60% of
what a posting describes should see it. Recruiters describe an ideal candidate;
treating that description as a checklist deletes most of the real market.

Two things follow, and they are the reason this module is not just a weighted
sum of keyword hits:

  * A requirement the profile does not literally hold can still be partly met
    by an adjacent one (:mod:`app.enrich.equivalence`), and the transfer is
    always explained in words.
  * Being in-field is graded rather than binary (:mod:`app.enrich.relevance`),
    so an unusual title with a convincing description survives at a discount
    instead of being rejected on a phrase list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.enrich.equivalence import TransferVerdict, family_members_in, find_transfers
from app.enrich.language import (
    LANGUAGE_LABELS,
    classify_from_structured,
    classify_language,
)
from app.enrich.location import LocationResolver
from app.enrich.relevance import Relevance, RelevanceVerdict, classify_relevance
from app.enrich.salary import SalaryVerdict, extract_salary
from app.enrich.seniority import classify_seniority
from app.enrich.skills import SkillExtractor
from app.enrich.terms import alternation
from app.models.base import (
    LANGUAGE_ACCESSIBILITY,
    EmploymentType,
    LanguageRequirement,
    RemotePolicy,
    Seniority,
)
from app.settings import Profile

# Requirements a posting may name that the profile does not claim. Used only
# to populate "missing requirements" -- a term is reported solely when the
# posting actually contains it, never as a guess about what an employer wants.
COMMON_REQUIREMENTS = [
    "kubernetes", "terraform", "aws", "azure", "gcp", "google cloud", "spark",
    "hadoop", "snowflake", "databricks", "airflow", "dbt", "kafka", "flink",
    "c++", "rust", "go", "scala", "java", "matlab", "julia", "r",
    "ros", "ros2", "cuda", "tensorrt", "onnx", "triton", "openvino",
    "react", "typescript", "graphql", "grpc", "microservices",
    "tableau", "power bi", "looker", "sap", "salesforce",
    "phd", "doctorate", "publications", "patents",
]

_DEGREE_PATTERNS = {
    "phd": re.compile(r"\b(ph\.?d|doctorate|doctoral degree|promotion erforderlich)\b", re.I),
    "msc": re.compile(r"\b(master'?s?(?:\s+degree)?|m\.?sc|diplom|magister)\b", re.I),
    "bsc": re.compile(r"\b(bachelor'?s?(?:\s+degree)?|b\.?sc)\b", re.I),
}
_DEGREE_RANK = {"bsc": 1, "msc": 2, "phd": 3}

_FULLTIME_HINT = re.compile(
    r"\b(full[\s-]?time|vollzeit|permanent|unbefristet|festanstellung)\b", re.I
)


@dataclass
class SubScores:
    technical: int = 0
    experience: int = 0
    language: int = 0
    location: int = 0
    education: int = 0
    freshness: int = 0
    domain: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "technical": self.technical,
            "experience": self.experience,
            "language": self.language,
            "location": self.location,
            "education": self.education,
            "freshness": self.freshness,
            "domain": self.domain,
        }


@dataclass
class MatchResult:
    keep: bool
    reject_reason: str = ""

    score: int = 0
    sub: SubScores = field(default_factory=SubScores)
    reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)

    # Everything the pipeline persists alongside the score.
    skills: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    role_category: str = ""
    seniority: str = Seniority.UNKNOWN
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    language_requirement: str = LanguageRequirement.UNCLEAR
    language_evidence: str = ""
    employment_type: str = EmploymentType.UNKNOWN
    remote_policy: str = RemotePolicy.UNKNOWN
    city: str = ""
    country: str = ""
    salary: SalaryVerdict = field(default_factory=SalaryVerdict)
    age_days: int | None = None


class MatchEngine:
    """Built once per run; holds the compiled vocabulary from the profile."""

    def __init__(self, profile: Profile) -> None:
        self.p = profile
        self.locations = LocationResolver(profile.location_tiers, profile.country_map)
        self.skills = SkillExtractor(
            profile.skills, profile.domains, profile.role_categories
        )

        weights = profile.weights or {}
        self.w: dict[str, float] = weights.get("weights") or {
            "technical": 0.26, "location": 0.20, "freshness": 0.16,
            "experience": 0.15, "language": 0.13, "domain": 0.06, "education": 0.04,
        }
        self.tier_bonus: dict[str, int] = weights.get("tier_bonus") or {}
        self.seniority_penalty: dict[str, int] = weights.get("seniority_penalty") or {}
        self.language_penalty: dict[str, int] = weights.get("language_penalty") or {
            LanguageRequirement.GERMAN_B2: 8,
            LanguageRequirement.GERMAN_C1_PLUS: 22,
            LanguageRequirement.GERMAN_NATIVE: 30,
        }
        self.freshness_curve: list[tuple[int, int]] = [
            (int(d), int(s)) for d, s in (weights.get("freshness_curve") or [[14, 50]])
        ]
        self.max_tier_points = max(profile.location_tiers or {0: []}, default=1) or 1
        # Flattened once: the equivalence layer asks what the profile holds,
        # not which group it was filed under.
        self._profile_skills = [
            term for terms in (profile.skills or {}).values() for term in terms
        ]

        self._not_fulltime = [re.compile(rf"(?<![a-z]){re.escape(t)}", re.I)
                              for t in profile.not_fulltime]
        # `roles.include` used to be a hard title gate -- the rule that
        # rejected "Perception Engineer" outright. It now widens the relevance
        # classifier instead, so the setting still decides what counts as this
        # person's field without being able to delete the rest of the market.
        self._target_titles = alternation(profile.role_words)

    # -- gates ------------------------------------------------------------
    def _gate(
        self, title: str, location: str, age_days: int | None, relevance: RelevanceVerdict
    ) -> str:
        """The few rejections that are safe to make.

        Each one answers "this opportunity is genuinely unavailable or is not
        this profession", never "this candidate is imperfect". A missing tool,
        an ambitious number of years and a preferred language are all handled by
        the score, where they are visible and arguable.
        """
        if any(p.search(title) for p in self._not_fulltime):
            return "not a full-time position"
        if not relevance.keep:
            return relevance.reason
        if region := self.locations.is_excluded(location, self.p.location_exclude):
            return f"outside the target region ({region})"
        if age_days is None and not self.p.keep_undated:
            return "no posting date"
        if age_days is not None and age_days > self.p.max_age_days:
            return f"older than {self.p.max_age_days} days"
        return ""

    # -- sub-scores -------------------------------------------------------
    def _technical(self, skills, transfers: TransferVerdict, reasons: list[str]) -> int:
        """How well the posting's technology matches the profile.

        Depth carries most of the weight and breadth is a bonus on top. The
        earlier version split the two evenly, which quietly punished the best
        possible outcome: a focused "Machine Learning Engineer — Python,
        PyTorch, MLOps" posting hit two of seven profile groups and scored in
        the twenties, while a scattergun posting listing one term from every
        group scored well. Employers hire for depth.

        Transferred credit counts here too, at its family's factor, because a
        requirement met by an adjacent skill is partly met.
        """
        literal = len(skills.matched)
        effective = literal + transfers.credit
        depth = min(effective, 7) / 7                       # saturates at seven
        breadth = min(len(skills.by_group), 4) / 4          # saturates at four
        score = round(depth * 72 + breadth * 28)

        if skills.by_group:
            strongest = skills.strongest_group
            hits = skills.by_group[strongest]
            pretty = ", ".join(hits[:3])
            reasons.append(f"Matches your {strongest.replace('_', ' ')} experience: {pretty}")
        if len(skills.by_group) >= 3:
            reasons.append(f"Spans {len(skills.by_group)} of your skill areas")
        for transfer in transfers.transfers[:3]:
            reasons.append(transfer.sentence())
        return min(score, 100)

    def _experience(self, min_years, seniority, reasons, gaps) -> int:
        """Years asked for, read as an aspiration rather than a gate.

        The ladder is deliberately gentle up to about four years. "3+ years" on
        a graduate-suitable posting is the single most common line in this
        market and is routinely written by teams who will happily interview
        someone with one year and the right background. Past five it steepens,
        because by then the posting is describing a different job.
        """
        mine = self.p.years_experience
        if min_years is None:
            if seniority in (Seniority.GRADUATE, Seniority.JUNIOR):
                reasons.append("Advertised at graduate or junior level")
                return 95
            return 75                                   # nothing stated
        if min_years <= mine + 1:
            reasons.append(f"Asks for {min_years}+ years, which you meet")
            return 100

        gap = min_years - mine
        if gap <= 1.5:                                  # ~3 years for this profile
            score = 82
            reasons.append(f"Asks for {min_years}+ years — a realistic stretch")
        elif gap <= 2.5:                                # ~4 years
            score = 68
            gaps.append(f"Asks for {min_years}+ years of experience — a stretch")
        elif gap <= 4:                                  # ~5 years
            score = 48
            gaps.append(f"Asks for {min_years}+ years of experience")
        else:
            score = max(0, round(52 - (gap - 4) * 13))
            gaps.append(f"Asks for {min_years}+ years of experience")
        return score

    def _language(self, verdict, reasons, gaps) -> int:
        score = LANGUAGE_ACCESSIBILITY.get(verdict.level, 60)
        # A posting written in German with no stated requirement is weaker
        # evidence than a stated requirement, but it is still evidence.
        if verdict.level == LanguageRequirement.UNCLEAR and verdict.posting_language == "de":
            score = max(0, score - 15)
            gaps.append("Advertised in German; language requirement not stated")
        label = LANGUAGE_LABELS.get(verdict.level, "Not stated")
        if score >= 88:
            reasons.append(f"Language requirement: {label}")
        elif score <= 45:
            gaps.append(f"Language requirement: {label}")
        return score

    def _location(self, loc, reasons, gaps) -> int:
        score = round(loc.tier_points / self.max_tier_points * 100) if loc.tier_points else 0
        if loc.tier_points:
            reasons.append(f"Location: {loc.tier_label}")
        elif loc.remote_policy == RemotePolicy.REMOTE:
            score = 60
            reasons.append("Remote role, so location is less binding")
        else:
            gaps.append("Location is outside your stated preferences or not stated")
        if loc.remote_policy in (RemotePolicy.REMOTE, RemotePolicy.HYBRID) and score < 100:
            score = min(100, score + 8)
        return score

    def _education(self, text, reasons, gaps) -> int:
        mine = _DEGREE_RANK.get(self.p.education_level, 2)
        asked = [name for name, pattern in _DEGREE_PATTERNS.items() if pattern.search(text)]
        if not asked:
            return 85                                   # nothing stated
        highest = max(_DEGREE_RANK[a] for a in asked)
        if highest <= mine:
            reasons.append("Your degree meets the stated requirement")
            return 100
        gaps.append("Asks for a doctorate")
        return 40

    def _freshness(self, age_days, reasons) -> int:
        if age_days is None:
            return 50
        for max_age, points in self.freshness_curve:
            if age_days <= max_age:
                if points >= 90:
                    reasons.append(
                        "Posted today" if age_days <= 1 else f"Posted {age_days} days ago"
                    )
                return points
        return 5

    def _domain(self, domains, reasons) -> int:
        if not domains:
            return 50                                   # neutral, not negative
        preferred = set(self.p.preferred_industries)
        overlap = [d for d in domains if d in preferred or any(d in p for p in preferred)]
        score = min(100, 45 + 18 * len(domains) + 10 * len(overlap))
        reasons.append(f"Industry fit: {', '.join(domains[:3])}")
        return score

    # -- entry point ------------------------------------------------------
    def evaluate(
        self,
        title: str,
        description: str,
        location: str,
        company_name: str,
        company_tier: str,
        age_days: int | None,
        tags: str = "",
        structured: dict | None = None,
    ) -> MatchResult:
        title = title or ""
        description = description or ""
        text = f"{title}\n{description}"

        relevance = classify_relevance(title, description, tags, self._target_titles)
        if reason := self._gate(title, location, age_days, relevance):
            return MatchResult(keep=False, reject_reason=reason, age_days=age_days)

        reasons: list[str] = []
        gaps: list[str] = []

        skills = self.skills.extract(title, description, tags)
        seniority = classify_seniority(title, description)

        # Requirements the posting names and the profile does not claim. The
        # watchlist is the hand-kept list plus every technology that belongs to
        # an equivalence family, so a transferable skill is considered even when
        # nobody remembered to add it to a constant.
        watch = sorted(set(COMMON_REQUIREMENTS) | family_members_in(text))
        missing = self.skills.missing_from(skills, text, watch)
        transfers = find_transfers(missing, self._profile_skills)

        language = classify_language(title, description)
        if not language.is_explicit and structured:
            # The posting text said nothing. A provider's structured field is
            # weaker evidence than the employer's own words, so it is only
            # consulted here, never allowed to override an explicit statement.
            from_data = classify_from_structured(structured.get("language_skills") or [])
            if from_data is not None:
                language = from_data
        loc = self.locations.resolve(location, title, description)
        salary = extract_salary(title, description)

        sub = SubScores(
            technical=self._technical(skills, transfers, reasons),
            experience=self._experience(seniority.min_years, seniority.level, reasons, gaps),
            language=self._language(language, reasons, gaps),
            location=self._location(loc, reasons, gaps),
            education=self._education(text, reasons, gaps),
            freshness=self._freshness(age_days, reasons),
            domain=self._domain(skills.domains, reasons),
        )

        base = sum(getattr(sub, key) * weight for key, weight in self.w.items())
        score = base + self.tier_bonus.get(company_tier, 0)

        if company_tier == "dream":
            reasons.append(f"{company_name} is on your shortlist")

        # Seniority is a penalty, not a gate: the role stays searchable.
        penalty = self.seniority_penalty.get(seniority.level, 0)
        if penalty:
            score -= penalty
            label = seniority.title_signal or seniority.level
            gaps.append(f"Advertised at {label} level")

        # A mandatory language you do not have is different in kind from a
        # missing tool: it decides whether an application can succeed at all.
        # The language sub-score alone cannot express that -- at 13% of the
        # weighting, dropping it from 60 to 8 moved a total by seven points and
        # left a role requiring negotiation-level German sitting in "Good
        # Match". So the hard levels also take an explicit penalty, the same
        # shape as seniority, configurable and visible in the profile.
        language_penalty = self.language_penalty.get(language.level, 0)
        if language_penalty:
            score -= language_penalty
            gaps.append(
                f"Requires {LANGUAGE_LABELS.get(language.level, language.level)} — "
                f"beyond your stated German"
            )

        flags = []
        for rule in self.p.flags:
            phrases = [str(x).lower() for x in rule.get("phrases", [])]
            hit = next((p for p in phrases if p in text.lower()), None)
            if hit:
                flags.append({"code": rule["code"], "why": rule.get("explain", ""),
                              "evidence": hit})
                score -= int(rule.get("penalty", 0))
                gaps.append(rule.get("explain", rule["code"]))

        if salary.found and salary.annual_eur_min:
            if salary.annual_eur_min >= self.p.target_salary_eur:
                reasons.append("Stated salary meets your target")
            score += 3

        # Only what nothing on the profile covers, literally or by transfer.
        gaps.extend(
            f"Asks for {m}, which is not on your profile" for m in transfers.unmet[:4]
        )

        # An uncertain reading of the field is a small discount, not a
        # rejection. A few points, not a multiplier: scaling by confidence
        # would drop a genuine 78 to a 47 and bury exactly the unusually-titled
        # roles this classifier exists to rescue.
        if relevance.level is Relevance.POSSIBLE:
            score -= 8
            gaps.append(
                f"Read as in-field from the description rather than the title "
                f"({relevance.reason})"
            )
        elif relevance.level is Relevance.LIKELY:
            score -= 3
            reasons.append(f"In your field: {relevance.reason}")

        employment = EmploymentType.FULL_TIME if _FULLTIME_HINT.search(text) \
            else EmploymentType.UNKNOWN

        return MatchResult(
            keep=True,
            score=max(0, min(100, round(score))),
            sub=sub,
            reasons=reasons[:8],
            gaps=gaps[:8],
            flags=flags,
            skills=skills.matched[:20],
            domains=skills.domains[:8],
            role_category=skills.role_category,
            seniority=seniority.level,
            experience_min_years=seniority.min_years,
            experience_max_years=seniority.max_years,
            language_requirement=language.level,
            language_evidence=language.evidence[:400],
            employment_type=employment,
            remote_policy=loc.remote_policy,
            city=loc.city,
            country=loc.country,
            salary=salary,
            age_days=age_days,
        )
