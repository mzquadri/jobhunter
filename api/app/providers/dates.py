"""Date parsing shared by providers.

Every ATS invented its own format, and getting one wrong quietly fills the
dashboard with stale postings -- so each is handled explicitly and anything
unrecognised returns empty rather than a plausible guess.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def from_relative(text: str | None) -> str:
    """Workday says 'Posted 5 Days Ago' rather than giving a date.

    'Posted 30+ Days Ago' is its ceiling: everything older reports the same
    string, so 30 is a floor on the true age, never an exact figure.
    """
    if not text:
        return ""
    t = text.lower()
    today = datetime.now()
    if "today" in t or "just posted" in t:
        return _iso(today)
    if "yesterday" in t:
        return _iso(today - timedelta(days=1))
    if m := re.search(r"(\d+)\+?\s*day", t):
        return _iso(today - timedelta(days=int(m.group(1))))
    if m := re.search(r"(\d+)\+?\s*month", t):
        return _iso(today - timedelta(days=30 * int(m.group(1))))
    if m := re.search(r"(\d+)\+?\s*week", t):
        return _iso(today - timedelta(weeks=int(m.group(1))))
    return ""


def from_any(value: object) -> str:
    """ISO, RFC-822 or a unix epoch -- all become YYYY-MM-DD, or ''."""
    if value in (None, ""):
        return ""
    if isinstance(value, int | float) or (isinstance(value, str) and value.isdigit()):
        try:
            n = int(value)
            if n > 4_000_000_000:                  # milliseconds
                n //= 1000
            return _iso(datetime.fromtimestamp(n, tz=UTC))
        except (ValueError, OSError, OverflowError):
            return ""
    s = str(value).strip()
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", s):
        return m.group(0)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%d %b %Y", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return _iso(datetime.strptime(s[:31].strip(), fmt))
        except ValueError:
            continue
    return ""


def days_old(posted: str | None) -> int | None:
    """Age in days, or None when the source gave no date.

    Returning None rather than 0 matters: an undated posting must not be
    ranked as though it were published today.
    """
    if not posted:
        return None
    try:
        return (datetime.now() - datetime.strptime(posted, "%Y-%m-%d")).days
    except ValueError:
        return None
