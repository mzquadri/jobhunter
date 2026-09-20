"""Date handling, because every ATS invented its own format and getting one
wrong silently fills the dashboard with stale postings."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.collector.sources import date_from_any, date_from_relative, days_old, strip_html


def iso(days: int = 0) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


class TestWorkdayRelativeDates:
    @pytest.mark.parametrize("text,expected_days", [
        ("Posted Today", 0),
        ("Posted Yesterday", 1),
        ("Posted 5 Days Ago", 5),
        ("Posted 30+ Days Ago", 30),
        ("Just Posted", 0),
    ])
    def test_parses_workday_phrasing(self, text, expected_days):
        assert date_from_relative(text) == iso(expected_days)

    def test_unknown_phrasing_yields_no_date(self):
        assert date_from_relative("Posted a while back") == ""
        assert date_from_relative(None) == ""


class TestGenericDates:
    def test_iso_timestamps(self):
        assert date_from_any("2026-09-15T10:02:49+02:00") == "2026-09-15"

    def test_rfc822(self):
        assert date_from_any("Mon, 15 Sep 2026 10:02:49 +0000") == "2026-09-15"

    def test_unix_seconds_and_milliseconds_agree(self):
        seconds = 1789926916
        assert date_from_any(seconds) == date_from_any(seconds * 1000)

    def test_junk_yields_no_date(self):
        assert date_from_any("") == ""
        assert date_from_any(None) == ""
        assert date_from_any("not a date") == ""


class TestAge:
    def test_counts_days(self):
        assert days_old(iso(7)) == 7

    def test_missing_date_is_unknown_not_zero(self):
        # Returning 0 here would make undated postings look brand new.
        assert days_old("") is None
        assert days_old(None) is None


class TestStripHtml:
    def test_removes_tags_and_decodes_entities(self):
        assert strip_html("<p>PyTorch &amp; Docker</p>") == "PyTorch & Docker"

    def test_drops_script_and_style_content(self):
        out = strip_html("<style>.x{color:red}</style><p>Keep</p><script>bad()</script>")
        assert "color" not in out and "bad()" not in out
        assert "Keep" in out

    def test_block_tags_become_line_breaks(self):
        assert "\n" in strip_html("<li>One</li><li>Two</li>")

    def test_handles_empty_input(self):
        assert strip_html(None) == ""
        assert strip_html("") == ""
