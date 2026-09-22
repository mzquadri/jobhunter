"""Skill, domain and role-category extraction.

Skills are grouped in the profile rather than listed flat, so the matcher can
say "strong PyTorch and deep-learning match" instead of "11 keywords hit".
Groups are what make the explanation readable.

Matching is deliberately literal. An embedding model would catch paraphrases,
but §10 requires the score to be explainable and §34 says not to reach for AI
where deterministic parsing suffices -- and "the posting contains the word
PyTorch" is a reason a human can check in one second.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.enrich.terms import term_pattern


@dataclass
class SkillVerdict:
    matched: list[str] = field(default_factory=list)
    by_group: dict[str, list[str]] = field(default_factory=dict)
    domains: list[str] = field(default_factory=list)
    role_category: str = ""

    @property
    def strongest_group(self) -> str:
        if not self.by_group:
            return ""
        return max(self.by_group.items(), key=lambda kv: len(kv[1]))[0]


#: Compiling a term now lives in one place. See :mod:`app.enrich.terms` for
#: why: the substitution is easy to rewrite as a chained ``.replace``, which
#: corrupts every multi-word term without raising anything.
_compile = term_pattern


class SkillExtractor:
    """Compiles the profile's vocabulary once and reuses it for every posting."""

    def __init__(
        self,
        skill_groups: dict[str, list[str]],
        domains: list[str],
        role_categories: dict[str, list[str]],
    ) -> None:
        self._groups = {
            group: [(term, _compile(term)) for term in terms]
            for group, terms in skill_groups.items()
        }
        self._domains = [(term, _compile(term)) for term in domains]
        # Longest category term lists first so a specific category wins over a
        # generic one when a title matches both.
        self._categories = sorted(
            ((name, [(t, _compile(t)) for t in terms]) for name, terms in role_categories.items()),
            key=lambda kv: -max((len(t) for t, _ in kv[1]), default=0),
        )

    def extract(self, title: str, description: str, tags: str = "") -> SkillVerdict:
        haystack = f"{title}\n{tags}\n{description}"

        by_group: dict[str, list[str]] = {}
        matched: list[str] = []
        for group, terms in self._groups.items():
            hits = [term for term, pattern in terms if pattern.search(haystack)]
            if hits:
                by_group[group] = hits
                matched.extend(hits)

        domains = [term for term, pattern in self._domains if pattern.search(haystack)]

        role_category = ""
        for name, terms in self._categories:
            if any(pattern.search(title or "") for _, pattern in terms):
                role_category = name
                break
        if not role_category:
            for name, terms in self._categories:
                if any(pattern.search(haystack) for _, pattern in terms):
                    role_category = name
                    break

        # Deduplicate while preserving the order groups were declared in.
        seen: set[str] = set()
        ordered = [s for s in matched if not (s in seen or seen.add(s))]

        return SkillVerdict(
            matched=ordered,
            by_group=by_group,
            domains=domains,
            role_category=role_category,
        )

    def missing_from(self, verdict: SkillVerdict, posting_text: str,
                     watch_terms: list[str]) -> list[str]:
        """Requirements the posting names that the profile does not claim.

        This is what fills "missing skills" in the interface. It only ever
        reports terms the posting actually contains -- never a guess about what
        an employer might want.
        """
        have = {s.lower() for s in verdict.matched}
        missing = []
        for term in watch_terms:
            if term.lower() in have:
                continue
            if _compile(term).search(posting_text):
                missing.append(term)
        return missing
