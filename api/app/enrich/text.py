"""Text handling for ingested postings.

Everything here treats provider output as untrusted. Job descriptions are
third-party HTML that ends up rendered in a browser, so scripts, styles,
iframes and event handlers are removed at ingestion rather than relying on the
frontend to escape them later.
"""

from __future__ import annotations

import html
import re

# Elements whose *contents* must go, not just their tags.
_DANGEROUS_BLOCKS = re.compile(
    r"<(script|style|iframe|object|embed|noscript|template)\b[^>]*>.*?</\1\s*>",
    re.S | re.I,
)
_UNCLOSED_DANGEROUS = re.compile(r"<(script|style|iframe|object|embed)\b[^>]*>", re.I)
_BLOCK_BREAK = re.compile(r"</(p|div|li|tr|h[1-6]|section|article)\s*>|<br\s*/?>", re.I)
_LIST_ITEM = re.compile(r"<li\b[^>]*>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_WS_INLINE = re.compile(r"[ \t\xa0  ]+")
_WS_BLOCK = re.compile(r"\n\s*\n\s*\n+")


def clean_html(raw: str | None) -> str:
    """HTML to readable plain text, with anything executable discarded."""
    if not raw:
        return ""
    text = _DANGEROUS_BLOCKS.sub(" ", raw)
    text = _UNCLOSED_DANGEROUS.sub(" ", text)
    text = _LIST_ITEM.sub("\n• ", text)
    text = _BLOCK_BREAK.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    # Unescaping can reveal markup that was entity-encoded to smuggle it past
    # a single-pass stripper, so strip once more on the decoded text.
    text = _ANY_TAG.sub(" ", text)
    text = _WS_INLINE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _WS_BLOCK.sub("\n\n", text).strip()


# ---------------------------------------------------------------------------
# language of the posting itself
# ---------------------------------------------------------------------------
# Frequent short words are a more reliable signal than umlauts: plenty of
# English postings contain German place names, and plenty of German postings
# avoid umlauts entirely.
_GERMAN_MARKERS = (
    " und ", " oder ", " nicht ", " mit ", " für ", " fuer ", " eine ", " einen ",
    " werden ", " wir ", " sie ", " ihre ", " sind ", " haben ", " bei ", " dich ",
    " deine ", " unser ", " unsere ", " sowie ", " durch ", " aufgaben", " profil",
    " kenntnisse", " erfahrung", " mitarbeiter", " stelle",
)
_ENGLISH_MARKERS = (
    " and ", " or ", " not ", " with ", " for ", " the ", " you ", " your ",
    " we ", " our ", " are ", " have ", " will ", " this ", " that ", " from ",
    " experience", " skills", " role", " team",
)


def detect_language(text: str) -> str:
    """Return 'de', 'en' or 'unknown' for the posting body.

    Used as supporting evidence only. A posting written in German is a hint
    that German is expected, but it is never treated as an explicit
    requirement -- the classifier reports it as evidence and nothing more.
    """
    if not text or len(text) < 120:
        return "unknown"
    padded = f" {text.lower()} "
    de = sum(padded.count(m) for m in _GERMAN_MARKERS)
    en = sum(padded.count(m) for m in _ENGLISH_MARKERS)
    if de == en == 0:
        return "unknown"
    if de >= en * 1.5:
        return "de"
    if en >= de * 1.5:
        return "en"
    return "unknown"


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
_BOILERPLATE = re.compile(
    r"^\s*(?:•\s*)?(?:about (?:us|the company)|who we are|equal opportunit|"
    r"we are an equal|diversity|benefits|what we offer|unser angebot|"
    r"wir bieten|über uns|ueber uns)\b",
    re.I,
)


def summarise(text: str, max_chars: int = 600) -> str:
    """First substantive prose of a posting.

    Deliberately extractive. An abstractive summary would need an LLM, and
    §34 is explicit that AI should not be used where deterministic parsing
    does the job -- an employer's own opening paragraph describes the role
    better than a paraphrase of it, and cannot hallucinate.
    """
    if not text:
        return ""
    out: list[str] = []
    total = 0
    for block in (b.strip() for b in text.split("\n")):
        if len(block) < 40 or _BOILERPLATE.match(block):
            continue
        out.append(block)
        total += len(block)
        if total >= max_chars:
            break
    summary = " ".join(out) if out else text
    return summary[:max_chars].rstrip() + ("…" if len(summary) > max_chars else "")


def find_evidence(text: str, needle: str, window: int = 140) -> str:
    """The sentence fragment around a match, so a classification can be
    audited against the posting instead of taken on trust."""
    if not text or not needle:
        return ""
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - window // 2)
    end = min(len(text), idx + len(needle) + window // 2)
    fragment = " ".join(text[start:end].split())
    return ("…" if start > 0 else "") + fragment + ("…" if end < len(text) else "")
