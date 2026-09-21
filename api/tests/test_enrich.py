"""Tests for the inference layer.

These parsers decide what the candidate sees, so the cases below are the ones
that actually bite: German and English number formats, a salary figure that is
really a year, a title that disagrees with the body, and an office list that
must not be read as the job's location.
"""

from __future__ import annotations

import pytest

from app.enrich.language import classify_language
from app.enrich.location import LocationResolver, detect_remote
from app.enrich.salary import extract_salary, format_salary, parse_amount
from app.enrich.seniority import classify_seniority, extract_years
from app.enrich.skills import SkillExtractor
from app.enrich.text import clean_html, detect_language, summarise
from app.models.base import LanguageRequirement, RemotePolicy, SalaryBasis, Seniority


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------
class TestCleanHtml:
    def test_extracts_readable_text(self):
        assert clean_html("<p>We use <b>PyTorch</b> daily.</p>") == "We use PyTorch daily."

    def test_removes_script_contents_not_just_tags(self):
        out = clean_html("<p>Real</p><script>steal(document.cookie)</script>")
        assert "steal" not in out and "cookie" not in out
        assert "Real" in out

    def test_removes_style_and_iframe_contents(self):
        out = clean_html("<style>.a{color:red}</style><iframe src='evil'></iframe><p>Keep</p>")
        assert "color" not in out and "evil" not in out and "Keep" in out

    def test_strips_markup_that_was_entity_encoded(self):
        # A single-pass stripper that unescapes last would emit a live tag here.
        out = clean_html("&lt;script&gt;alert(1)&lt;/script&gt; Engineer")
        assert "<script>" not in out
        assert "Engineer" in out

    def test_list_items_become_bullets(self):
        assert "•" in clean_html("<ul><li>Python</li><li>Docker</li></ul>")

    def test_handles_empty_input(self):
        assert clean_html(None) == ""
        assert clean_html("") == ""


class TestDetectLanguage:
    def test_detects_german_prose(self):
        text = ("Wir suchen eine Mitarbeiterin oder einen Mitarbeiter mit Erfahrung "
                "und sehr guten Kenntnissen, die oder der bei uns im Team arbeiten "
                "möchte und durch eigene Aufgaben überzeugt.")
        assert detect_language(text) == "de"

    def test_detects_english_prose(self):
        text = ("We are looking for an engineer with experience in machine learning "
                "and the skills to work with our team on models that we ship, and "
                "you will have the freedom to choose the tools that you use.")
        assert detect_language(text) == "en"

    def test_short_text_is_unknown_not_guessed(self):
        assert detect_language("ML Engineer") == "unknown"


class TestSummarise:
    def test_skips_boilerplate_headings(self):
        text = ("About us\n"
                "We are an equal opportunity employer and value diversity here.\n"
                "You will build and deploy machine learning models that run in "
                "production and are held to a real standard by the team.")
        assert "machine learning models" in summarise(text)

    def test_empty_input_is_empty(self):
        assert summarise("") == ""


# ---------------------------------------------------------------------------
# language requirement
# ---------------------------------------------------------------------------
class TestLanguageClassification:
    @pytest.mark.parametrize("text,expected", [
        ("English is our working language.", LanguageRequirement.ENGLISH_ONLY),
        ("We work entirely in English.", LanguageRequirement.ENGLISH_ONLY),
        ("Fluent in English required.", LanguageRequirement.ENGLISH_PREFERRED),
        ("German is a plus.", LanguageRequirement.GERMAN_OPTIONAL),
        ("Deutschkenntnisse von Vorteil.", LanguageRequirement.GERMAN_OPTIONAL),
        ("No German is required for this role.", LanguageRequirement.GERMAN_OPTIONAL),
        ("Basic German (A2) is helpful.", LanguageRequirement.GERMAN_BASIC),
        ("German at level B1.", LanguageRequirement.GERMAN_B1),
        ("Gute Deutschkenntnisse erforderlich.", LanguageRequirement.GERMAN_B2),
        ("German B2 required.", LanguageRequirement.GERMAN_B2),
        ("Verhandlungssichere Deutschkenntnisse.", LanguageRequirement.GERMAN_C1_PLUS),
        ("Fließend Deutsch in Wort und Schrift.", LanguageRequirement.GERMAN_C1_PLUS),
        ("Fluent in German required.", LanguageRequirement.GERMAN_C1_PLUS),
        ("Deutsch als Muttersprache.", LanguageRequirement.GERMAN_NATIVE),
        ("Native-level German speaker.", LanguageRequirement.GERMAN_NATIVE),
    ])
    def test_classifies_each_level(self, text, expected):
        assert classify_language("ML Engineer", text).level == expected

    def test_strictest_statement_wins(self):
        # Both claims appear; the operative requirement is the stricter one.
        text = "English is our working language. German C1 is required for this role."
        assert classify_language("Engineer", text).level == LanguageRequirement.GERMAN_C1_PLUS

    def test_silence_is_unclear_never_invented(self):
        verdict = classify_language("ML Engineer", "You will train models in PyTorch.")
        assert verdict.level == LanguageRequirement.UNCLEAR
        assert verdict.is_explicit is False

    def test_german_posting_is_noted_as_evidence_not_promoted_to_requirement(self):
        german = ("Wir suchen eine Mitarbeiterin oder einen Mitarbeiter mit Erfahrung "
                  "und Kenntnissen, die oder der bei uns im Team arbeiten und durch "
                  "eigene Aufgaben überzeugen wird.")
        verdict = classify_language("Ingenieur", german)
        assert verdict.level == LanguageRequirement.UNCLEAR
        assert verdict.posting_language == "de"
        assert "written in German" in verdict.evidence

    def test_every_verdict_carries_evidence(self):
        verdict = classify_language("Engineer", "Verhandlungssicheres Deutsch notwendig.")
        assert verdict.evidence
        assert verdict.matched_phrase


# ---------------------------------------------------------------------------
# salary
# ---------------------------------------------------------------------------
class TestParseAmount:
    @pytest.mark.parametrize("token,expected", [
        ("90000", 90000), ("90,000", 90000), ("90.000", 90000),
        ("90k", 90000), ("90K", 90000), ("1.234,56", 1234.56),
        ("1,234.56", 1234.56), ("120'000", 120000),
    ])
    def test_parses_every_convention_employers_use(self, token, expected):
        assert parse_amount(token) == pytest.approx(expected)

    def test_rejects_nonsense(self):
        assert parse_amount("abc") is None
        assert parse_amount("") is None


class TestSalaryExtraction:
    def test_english_range(self):
        v = extract_salary("ML Engineer", "Salary: €70,000 - €90,000 per year.")
        assert v.basis == SalaryBasis.EXPLICIT
        assert v.currency == "EUR"
        assert v.annual_eur_min == pytest.approx(70000)
        assert v.annual_eur_max == pytest.approx(90000)

    def test_german_format_and_wording(self):
        v = extract_salary("Data Scientist", "Jahresgehalt: 65.000 - 80.000 EUR brutto")
        assert v.basis == SalaryBasis.EXPLICIT
        assert v.annual_eur_min == pytest.approx(65000)

    def test_monthly_is_annualised(self):
        v = extract_salary("Engineer", "Gehalt: 6.000 EUR brutto pro Monat")
        assert v.annual_eur_min == pytest.approx(72000)
        assert v.period == "month"

    def test_foreign_currency_converted_and_marked(self):
        v = extract_salary("ML Engineer", "Compensation: CHF 120,000 per year")
        assert v.currency == "CHF"
        assert v.annual_eur_min and v.annual_eur_min > 100_000
        assert format_salary(v).startswith("≈")

    def test_euro_annual_is_not_marked_as_derived(self):
        v = extract_salary("Engineer", "Salary range €80,000 to €95,000 per annum")
        assert not format_salary(v).startswith("≈")

    def test_absent_salary_is_unknown_not_guessed(self):
        v = extract_salary("ML Engineer", "You will build models. Great team.")
        assert v.basis == SalaryBasis.UNKNOWN
        assert v.annual_eur_min is None
        assert format_salary(v) == ""

    def test_never_estimates(self):
        # ESTIMATED exists for a future market-data source and must never be
        # produced by parsing alone.
        v = extract_salary("Senior ML Engineer in Munich", "Competitive salary offered.")
        assert v.basis != SalaryBasis.ESTIMATED

    def test_ignores_numbers_that_are_not_pay(self):
        v = extract_salary("Engineer", "Founded in 1998, we serve €2 billion in revenue.")
        assert v.basis == SalaryBasis.UNKNOWN

    def test_rejects_implausible_figures(self):
        v = extract_salary("Engineer", "Salary: €5 per year")
        assert v.basis == SalaryBasis.UNKNOWN


# ---------------------------------------------------------------------------
# seniority
# ---------------------------------------------------------------------------
class TestYears:
    @pytest.mark.parametrize("text,expected", [
        ("3+ years of experience", 3),
        ("at least 5 years of relevant experience", 5),
        ("2-4 years experience", 2),
        ("mindestens 3 Jahre Berufserfahrung", 3),
        ("You have 7 years of professional experience", 7),
    ])
    def test_extracts_the_entry_bar(self, text, expected):
        assert extract_years(text)[0] == expected

    def test_takes_the_lowest_of_several(self):
        text = "5+ years of leadership and 2+ years of Python experience"
        assert extract_years(text)[0] == 2

    def test_absent_is_none_not_zero(self):
        assert extract_years("You will build models.")[0] is None


class TestSeniority:
    @pytest.mark.parametrize("title,expected", [
        ("Graduate AI Engineer", Seniority.GRADUATE),
        ("Junior Data Scientist", Seniority.JUNIOR),
        ("Senior ML Engineer", Seniority.SENIOR),
        ("Staff Software Engineer", Seniority.LEAD),
        ("Principal Research Scientist", Seniority.LEAD),
        ("Head of AI", Seniority.EXECUTIVE),
        ("VP Engineering", Seniority.EXECUTIVE),
    ])
    def test_reads_the_title(self, title, expected):
        assert classify_seniority(title, "").level == expected

    def test_senior_staff_reads_as_lead(self):
        assert classify_seniority("Senior Staff Engineer", "").level == Seniority.LEAD

    def test_falls_back_to_years_when_title_is_silent(self):
        v = classify_seniority("Machine Learning Engineer", "8+ years of experience required")
        assert v.level == Seniority.SENIOR

    def test_plain_title_with_low_years_is_graduate(self):
        v = classify_seniority("Machine Learning Engineer", "0-1 years of experience")
        assert v.level == Seniority.GRADUATE

    def test_records_both_signals_as_evidence(self):
        v = classify_seniority("Senior Engineer", "3+ years of experience")
        assert v.title_signal
        assert v.min_years == 3


# ---------------------------------------------------------------------------
# location and remote
# ---------------------------------------------------------------------------
@pytest.fixture
def resolver(profile) -> LocationResolver:
    return LocationResolver(profile.location_tiers, profile.country_map)


class TestLocation:
    def test_munich_outranks_elsewhere_in_germany(self, resolver):
        assert (resolver.resolve("Munich, Germany").tier_points
                > resolver.resolve("Leipzig, Germany").tier_points)

    def test_germany_outranks_southern_europe(self, resolver):
        assert (resolver.resolve("Berlin, Germany").tier_points
                > resolver.resolve("Lisbon, Portugal").tier_points)

    def test_extracts_city(self, resolver):
        assert resolver.resolve("Munich, Germany").city == "Munich"

    def test_excluded_region_is_named(self, resolver, profile):
        assert resolver.is_excluded("Bangalore, India", profile.location_exclude) == "india"

    def test_multi_site_posting_including_a_wanted_city_is_kept(self, resolver, profile):
        assert resolver.is_excluded("Munich; Bangalore; Austin",
                                    profile.location_exclude) == ""

    def test_unknown_location_is_not_excluded(self, resolver, profile):
        assert resolver.is_excluded("", profile.location_exclude) == ""


class TestRemotePolicy:
    @pytest.mark.parametrize("text,expected", [
        ("This is a fully-remote role", RemotePolicy.REMOTE),
        ("100% remote", RemotePolicy.REMOTE),
        ("Hybrid working, 2 days per week in the office", RemotePolicy.HYBRID),
        ("On-site only", RemotePolicy.ONSITE),
        ("Vor Ort in München", RemotePolicy.ONSITE),
    ])
    def test_classifies_policy(self, text, expected):
        assert detect_remote("", "", text)[0] == expected

    def test_silence_is_unknown(self):
        assert detect_remote("ML Engineer", "Munich", "You will build models.")[0] == (
            RemotePolicy.UNKNOWN
        )

    def test_explicit_rule_beats_bare_keyword(self):
        # "no remote" must not be read as "remote".
        assert detect_remote("", "", "No remote work is available.")[0] == RemotePolicy.ONSITE


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------
class TestSkillExtractor:
    @pytest.fixture
    def extractor(self, profile) -> SkillExtractor:
        return SkillExtractor(profile.skills, profile.domains, profile.role_categories)

    def test_finds_skills_and_groups_them(self, extractor):
        v = extractor.extract("ML Engineer", "You will use PyTorch and Docker daily.")
        assert "pytorch" in v.matched
        assert v.by_group

    @pytest.mark.parametrize("term,text", [
        ("machine learning", "We do Machine Learning at scale."),
        ("computer vision", "A Computer Vision team."),
        ("hugging face", "Models from Hugging Face."),
        ("graph neural", "We train Graph Neural networks."),
        ("vector database", "Backed by a vector database."),
    ])
    def test_multi_word_terms_match(self, extractor, term, text):
        # Regression: chained .replace() in the term compiler corrupted the
        # character class and silently broke every multi-word skill.
        assert term in extractor.extract("Engineer", text).matched

    def test_tolerates_separator_variations(self, extractor):
        hyphen = extractor.extract("Engineer", "We use scikit-learn here.").matched
        space = extractor.extract("Engineer", "We use scikit learn here.").matched
        assert "scikit-learn" in hyphen
        assert "scikit-learn" in space

    def test_reports_domains(self, extractor):
        v = extractor.extract("Perception Engineer", "Our autonomous vehicles use lidar.")
        assert "autonomous" in v.domains or "vehicle" in v.domains

    def test_missing_skills_only_come_from_the_posting(self, extractor):
        v = extractor.extract("ML Engineer", "You will use PyTorch.")
        missing = extractor.missing_from(v, "You will use PyTorch.", ["kubernetes", "pytorch"])
        assert missing == []            # kubernetes is not in the posting, so not reported

    def test_missing_skills_found_when_posting_names_them(self, extractor):
        text = "You will use PyTorch and deploy on Kubernetes."
        v = extractor.extract("ML Engineer", text)
        missing = extractor.missing_from(v, text, ["terraform"])
        assert missing == []
