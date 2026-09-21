"""Deduplication tests.

The scenario that matters is the one the spec names: the same vacancy arriving
from the employer's ATS and from a board, under slightly different names, and
appearing once with both sources retained.
"""

from __future__ import annotations

from app.dedup import (
    Sighting,
    canonical_key,
    deduplicate,
    extract_requisition_id,
    normalize_city,
    normalize_company,
    title_similarity,
)


def sighting(**kw) -> Sighting:
    base = dict(
        provider="greenhouse", company="Helsing", title="Machine Learning Engineer",
        url="https://boards.greenhouse.io/helsing/jobs/123",
        location="Munich, Germany", external_id="123", posted="2026-09-20",
        description="Build models.",
    )
    base.update(kw)
    return Sighting(**base)


class TestNormalisation:
    def test_company_suffixes_collapse(self):
        assert normalize_company("BMW Group") == normalize_company("BMW AG")
        assert normalize_company("Helsing GmbH") == normalize_company("Helsing")

    def test_city_drops_country_and_region(self):
        assert normalize_city("Munich, Germany") == normalize_city("Munich")
        assert normalize_city("Munich, Bavaria, Germany") == normalize_city("Munich")

    def test_gender_and_percentage_noise_does_not_break_the_key(self):
        a = canonical_key("ABB", "ML Engineer (m/w/d) 80-100%", "Zurich")
        b = canonical_key("ABB", "ML Engineer (all genders)", "Zurich")
        assert a == b

    def test_different_roles_keep_different_keys(self):
        assert (canonical_key("BMW", "ML Engineer", "Munich")
                != canonical_key("BMW", "Data Engineer", "Munich"))

    def test_same_role_different_city_is_not_merged(self):
        assert (canonical_key("BMW", "ML Engineer", "Munich")
                != canonical_key("BMW", "ML Engineer", "Berlin"))


class TestRequisitionIds:
    def test_extracts_workday_id(self):
        url = "https://ag.wd3.myworkdayjobs.com/en-US/Airbus/job/Munich/x_JR10389233-1"
        assert extract_requisition_id("", url) == "JR10389233"

    def test_extracts_successfactors_id(self):
        assert extract_requisition_id("REQ-123456", "") == "REQ-123456"

    def test_absent_id_is_empty(self):
        assert extract_requisition_id("", "https://example.com/careers/ml-engineer") == ""


class TestTitleSimilarity:
    def test_inserted_words_stay_close(self):
        assert title_similarity(
            "Machine Learning Engineer", "Machine Learning Engineer (f/m/d)") > 0.9

    def test_unrelated_titles_are_far(self):
        assert title_similarity("Machine Learning Engineer", "Warehouse Operative") < 0.2


class TestDeduplicate:
    def test_single_posting_yields_one_group(self):
        groups = deduplicate([sighting()])
        assert len(groups) == 1
        assert groups[0].duplicate_count == 0

    def test_same_vacancy_from_two_providers_merges(self):
        groups = deduplicate([
            sighting(provider="greenhouse", company="Helsing"),
            sighting(provider="arbeitnow", company="Helsing GmbH",
                     external_id="xyz", url="https://arbeitnow.com/jobs/xyz"),
        ])
        assert len(groups) == 1
        assert groups[0].duplicate_count == 1
        assert set(groups[0].providers) == {"greenhouse", "arbeitnow"}

    def test_employer_direct_source_wins_as_primary(self):
        groups = deduplicate([
            sighting(provider="arbeitnow", external_id="board-1",
                     url="https://arbeitnow.com/jobs/board-1"),
            sighting(provider="greenhouse", external_id="gh-1"),
        ])
        assert groups[0].primary.provider == "greenhouse"

    def test_requisition_id_merges_despite_different_titles(self):
        url = "https://ag.wd3.myworkdayjobs.com/en-US/Airbus/job/Munich/a_JR10389233"
        groups = deduplicate([
            sighting(provider="workday", company="Airbus",
                     title="Data Scientist - Artificial Intelligence", url=url,
                     external_id="JR10389233"),
            sighting(provider="workday", company="Airbus",
                     title="Machine Learning Engineer (MLOps)",
                     url=url + "-1", external_id="JR10389233"),
        ])
        # Airbus renames postings without changing the requisition id; the
        # stale URL slug is what exposed this in production.
        assert len(groups) == 1

    def test_fuzzy_title_merges_within_an_employer(self):
        groups = deduplicate([
            sighting(title="Machine Learning Engineer", external_id="a"),
            sighting(title="Machine Learning Engineer (f/m/d)", external_id="b",
                     url="https://example.com/b"),
        ])
        assert len(groups) == 1

    def test_different_employers_never_merge(self):
        groups = deduplicate([
            sighting(company="Helsing"),
            sighting(company="Wayve", url="https://example.com/wayve"),
        ])
        assert len(groups) == 2

    def test_same_provider_and_id_twice_is_not_double_counted(self):
        groups = deduplicate([sighting(), sighting()])
        assert len(groups) == 1
        assert len(groups[0].sightings) == 1

    def test_earliest_posting_date_wins(self):
        groups = deduplicate([
            sighting(provider="greenhouse", posted="2026-09-20"),
            sighting(provider="arbeitnow", posted="2026-09-14", external_id="b",
                     url="https://arbeitnow.com/b"),
        ])
        # A board that syndicated the job later must not make it look newer,
        # and an earlier sighting must not be discarded.
        assert groups[0].earliest_posted() == "2026-09-14"

    def test_fullest_description_is_kept_even_if_another_source_won(self):
        groups = deduplicate([
            sighting(provider="greenhouse", description="Short."),
            sighting(provider="arbeitnow", description="A much longer description " * 12,
                     external_id="b", url="https://arbeitnow.com/b"),
        ])
        assert groups[0].primary.provider == "greenhouse"
        assert len(groups[0].best_description()) > 100

    def test_postings_without_a_url_are_dropped(self):
        assert deduplicate([sighting(url="")]) == []
