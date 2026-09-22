r"""Compiling vocabulary into patterns.

One module owns this because getting it wrong is silent. Three separate places
needed "match this term the way employers actually write it", and the second
and third each rewrote the substitution as a chain::

    re.escape(term).replace(r"\ ", r"[\s\-/]+").replace(r"\-", r"[\s\-/]+")

which looks equivalent and is not. The first replacement inserts a ``-`` into
the character class it just wrote; the second then rewrites that ``-``,
producing ``[\s[\s\-/]+/]+`` — a class that matches almost nothing. Every
multi-word term in the list stops working, no exception is raised, and the only
symptom is that good jobs quietly disappear.

So the substitution happens once, in one function, here.

Boundaries are hand-rolled rather than ``\b`` because ``+`` and ``/`` are not
word characters, so ``\b`` does the wrong thing at both ends of ``c++`` and
``ci/cd``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: An escaped space or hyphen, as produced by ``re.escape``. Matched in a
#: single pass so the replacement text is never itself rewritten.
_ESCAPED_SEPARATOR = re.compile(r"\\[ \-]")

#: What a separator in a term is allowed to be in a posting: 'scikit-learn'
#: must match 'scikit learn', and 'ci/cd' must match 'CI-CD'.
_SEPARATOR_CLASS = r"[\s\-_/]+"


def term_body(term: str) -> str:
    """The pattern for one term, without boundaries. Use for alternations."""
    return _ESCAPED_SEPARATOR.sub(lambda _: _SEPARATOR_CLASS, re.escape(term))


def term_pattern(term: str) -> re.Pattern[str]:
    """A compiled, boundary-guarded matcher for a single term."""
    return re.compile(rf"(?<![a-z0-9]){term_body(term)}(?![a-z0-9])", re.I)


def alternation(terms: Iterable[str]) -> re.Pattern[str]:
    """One boundary-guarded pattern matching any of ``terms``.

    Longest first, so 'machine learning engineer' wins over 'machine learning'
    when both would match and the caller reports what it found.
    """
    ordered = sorted({t for t in terms if t}, key=len, reverse=True)
    if not ordered:
        # A pattern that can never match, rather than an empty alternation —
        # `(?:)` matches the empty string everywhere.
        return re.compile(r"(?!)")
    body = "|".join(term_body(t) for t in ordered)
    return re.compile(rf"(?<![a-z0-9])(?:{body})(?![a-z0-9])", re.I)
