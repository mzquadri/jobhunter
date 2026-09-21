"""Salary extraction.

The governing rule is §13: never present a derived figure as something the
employer stated, and never invent one at all.

So this module only ever reports what a posting literally contains. It does
not estimate from market data, job title or company size -- there is no source
for that here, and a plausible-looking guess is worse than an empty field
because it looks like information.

Two figures are kept and they mean different things:

  * ``amount_min/max`` with ``currency`` and ``period`` -- exactly as printed
  * ``annual_eur_min/max`` -- annualised and converted, always derived

``basis`` describes the first: EXPLICIT when the posting stated numbers,
UNKNOWN when it did not. ESTIMATED is defined for a future market-data source
and is never produced by this code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.enrich.text import find_evidence
from app.models.base import SalaryBasis

# Static, approximate, and deliberately so: a live FX feed would add a network
# dependency and a failure mode to a number that is only ever indicative.
# Any figure converted with these is surfaced as "≈" in the interface.
FX_TO_EUR: dict[str, float] = {
    "EUR": 1.00, "CHF": 1.06, "GBP": 1.17, "USD": 0.92, "SEK": 0.087,
    "DKK": 0.134, "NOK": 0.086, "PLN": 0.23, "CZK": 0.040,
}

_CURRENCY_TOKENS = {
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "chf": "CHF", "sfr": "CHF", "fr.": "CHF",
    "£": "GBP", "gbp": "GBP",
    "$": "USD", "usd": "USD",
    "sek": "SEK", "dkk": "DKK", "nok": "NOK", "pln": "PLN", "czk": "CZK",
}

# Multipliers to an annual figure.
_PERIOD_FACTOR = {"year": 1.0, "month": 12.0, "week": 52.0, "day": 220.0, "hour": 1720.0}

_PERIOD_WORDS: list[tuple[str, re.Pattern[str]]] = [
    ("hour", re.compile(r"\b(?:per\s+hour|/\s*h\b|hourly|pro\s+stunde|/\s*hr\b|p\.?h\.?)\b", re.I)),
    ("day", re.compile(r"\b(?:per\s+day|daily|pro\s+tag|/\s*day|tagessatz)\b", re.I)),
    ("week", re.compile(r"\b(?:per\s+week|weekly|pro\s+woche)\b", re.I)),
    ("month", re.compile(r"\b(?:per\s+month|monthly|pro\s+monat|/\s*month|monatlich|"
                         r"brutto\s*/\s*monat)\b", re.I)),
    ("year", re.compile(r"\b(?:per\s+year|per\s+annum|annual(?:ly)?|p\.?a\.?|yearly|"
                        r"pro\s+jahr|j[äa]hrlich|/\s*year|brutto\s*/\s*jahr|"
                        r"jahresgehalt|annual\s+salary)\b", re.I)),
]

# A number that might be money: optional thousands separators, optional k.
_NUM = r"\d{1,3}(?:[.,  ' ]\d{3})*(?:[.,]\d{1,2})?\s*[kK]?|\d{4,7}(?:[.,]\d{1,2})?\s*[kK]?"

# A range, with the currency on either side.
_RANGE = re.compile(
    rf"(?P<cur1>€|£|\$|\b(?:EUR|CHF|GBP|USD|SEK|DKK|NOK|PLN|CZK)\b)?\s*"
    rf"(?P<lo>{_NUM})\s*(?:-|–|—|to|bis|until)\s*"
    rf"(?P<cur2>€|£|\$|\b(?:EUR|CHF|GBP|USD|SEK|DKK|NOK|PLN|CZK)\b)?\s*"
    rf"(?P<hi>{_NUM})\s*"
    rf"(?P<cur3>€|£|\$|\b(?:EUR|CHF|GBP|USD|SEK|DKK|NOK|PLN|CZK)\b)?",
    re.I,
)

_SINGLE = re.compile(
    rf"(?P<cur1>€|£|\$|\b(?:EUR|CHF|GBP|USD|SEK|DKK|NOK|PLN|CZK)\b)\s*(?P<val>{_NUM})"
    rf"|(?P<val2>{_NUM})\s*(?P<cur2>€|£|\$|\b(?:EUR|CHF|GBP|USD|SEK|DKK|NOK|PLN|CZK)\b)",
    re.I,
)

# Only look near language that actually announces pay. Without this anchor a
# posting mentioning "€2 billion revenue" or "founded in 1998" yields a salary.
_SALARY_CONTEXT = re.compile(
    r"(salary|salaries|compensation|remuneration|pay\s+range|package|gehalt|"
    r"verg[üu]tung|lohn|jahresgehalt|brutto|gross|annual\s+base|base\s+pay|"
    r"we\s+offer\s+(?:you\s+)?(?:a\s+)?(?:competitive\s+)?(?:salary|compensation))",
    re.I,
)

# Sanity bounds on an annualised figure, to reject years, headcounts and
# revenue figures that survive everything above.
_MIN_PLAUSIBLE_ANNUAL = 12_000
_MAX_PLAUSIBLE_ANNUAL = 500_000


@dataclass(frozen=True)
class SalaryVerdict:
    basis: str = SalaryBasis.UNKNOWN
    amount_min: float | None = None
    amount_max: float | None = None
    currency: str = ""
    period: str = ""
    annual_eur_min: float | None = None
    annual_eur_max: float | None = None
    evidence: str = ""

    @property
    def found(self) -> bool:
        return self.basis == SalaryBasis.EXPLICIT


def parse_amount(token: str) -> float | None:
    """Parse a money token written in any of the conventions employers use.

    '90k' -> 90000, '90.000' -> 90000 (German), '90,000' -> 90000 (English),
    '1.234,56' -> 1234.56, '1,234.56' -> 1234.56.
    """
    if not token:
        return None
    raw = token.strip()
    multiplier = 1000.0 if raw[-1] in "kK" else 1.0
    raw = raw.rstrip("kK").strip()
    raw = raw.replace(" ", "").replace(" ", "").replace("'", "").replace(" ", "")

    has_dot, has_comma = "." in raw, "," in raw
    if has_dot and has_comma:
        # Whichever separator comes last is the decimal point.
        raw = (raw.replace(".", "").replace(",", ".")
               if raw.rfind(",") > raw.rfind(".")
               else raw.replace(",", ""))
    elif has_comma:
        parts = raw.split(",")
        raw = raw.replace(",", "") if len(parts[-1]) == 3 else raw.replace(",", ".")
    elif has_dot:
        parts = raw.split(".")
        if len(parts[-1]) == 3:                      # 90.000 -> thousands
            raw = raw.replace(".", "")

    try:
        return float(raw) * multiplier
    except ValueError:
        return None


def _currency_from(*tokens: str | None) -> str:
    for token in tokens:
        if token:
            code = _CURRENCY_TOKENS.get(token.strip().lower())
            if code:
                return code
    return ""


def _detect_period(window: str) -> str:
    for name, pattern in _PERIOD_WORDS:
        if pattern.search(window):
            return name
    return ""


def _annualise(value: float | None, period: str, currency: str) -> float | None:
    if value is None:
        return None
    factor = _PERIOD_FACTOR.get(period or "year", 1.0)
    rate = FX_TO_EUR.get(currency or "EUR")
    if rate is None:
        return None
    return round(value * factor * rate, 2)


def _plausible(lo: float | None, hi: float | None) -> bool:
    values = [v for v in (lo, hi) if v is not None]
    if not values:
        return False
    if any(v < _MIN_PLAUSIBLE_ANNUAL or v > _MAX_PLAUSIBLE_ANNUAL for v in values):
        return False
    return not (lo is not None and hi is not None and hi < lo)


def extract_salary(title: str, description: str) -> SalaryVerdict:
    """Find a salary a posting actually printed, or report that there is none."""
    text = f"{title}\n{description}"
    if not text.strip():
        return SalaryVerdict()

    for context in _SALARY_CONTEXT.finditer(text):
        # Look only at the neighbourhood of the pay-related phrase.
        window = text[max(0, context.start() - 120): context.end() + 260]
        period = _detect_period(window) or _detect_period(text)

        if verdict := _try_range(window, period, text):
            return verdict
        if verdict := _try_single(window, period, text):
            return verdict

    return SalaryVerdict(evidence="No salary stated in the posting.")


def _try_range(window: str, period: str, full_text: str) -> SalaryVerdict | None:
    for match in _RANGE.finditer(window):
        currency = _currency_from(match.group("cur1"), match.group("cur2"), match.group("cur3"))
        if not currency:
            continue
        lo, hi = parse_amount(match.group("lo")), parse_amount(match.group("hi"))
        eur_lo = _annualise(lo, period, currency)
        eur_hi = _annualise(hi, period, currency)
        if not _plausible(eur_lo, eur_hi):
            continue
        return SalaryVerdict(
            basis=SalaryBasis.EXPLICIT,
            amount_min=lo, amount_max=hi,
            currency=currency, period=period or "year",
            annual_eur_min=eur_lo, annual_eur_max=eur_hi,
            evidence=find_evidence(full_text, match.group(0)) or match.group(0).strip(),
        )
    return None


def _try_single(window: str, period: str, full_text: str) -> SalaryVerdict | None:
    for match in _SINGLE.finditer(window):
        currency = _currency_from(match.group("cur1"), match.group("cur2"))
        value = parse_amount(match.group("val") or match.group("val2") or "")
        eur = _annualise(value, period, currency)
        if not currency or not _plausible(eur, eur):
            continue
        return SalaryVerdict(
            basis=SalaryBasis.EXPLICIT,
            amount_min=value, amount_max=value,
            currency=currency, period=period or "year",
            annual_eur_min=eur, annual_eur_max=eur,
            evidence=find_evidence(full_text, match.group(0)) or match.group(0).strip(),
        )
    return None


def format_salary(verdict: SalaryVerdict) -> str:
    """Short display string, or empty when nothing was stated.

    Marks a converted figure with '≈' so an annualised or FX-converted number
    is never mistaken for the employer's own wording.
    """
    if not verdict.found or verdict.annual_eur_min is None:
        return ""
    lo, hi = verdict.annual_eur_min, verdict.annual_eur_max or verdict.annual_eur_min
    derived = verdict.currency != "EUR" or verdict.period != "year"
    prefix = "≈ " if derived else ""
    if abs(hi - lo) < 1:
        return f"{prefix}€{lo:,.0f}"
    return f"{prefix}€{lo:,.0f}–{hi:,.0f}"
