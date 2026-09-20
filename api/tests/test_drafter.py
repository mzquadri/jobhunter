"""Paragraph selection is the part that makes a draft worth opening: an
aerospace role and an imaging role must not receive the same letter."""

from __future__ import annotations

import pytest

from app.collector.drafter import Drafter, Paragraph
from app.collector.matcher import Verdict
from app.collector.sources import RawPosting

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
EXAMPLE_LETTER = REPO_ROOT / "config" / "letter.example.md"


@pytest.fixture
def drafter(profile, tmp_path) -> Drafter:
    return Drafter(profile, EXAMPLE_LETTER, tmp_path)


def verdict(**kw) -> Verdict:
    base = dict(keep=True, score=70, skills=["pytorch"], domains=["aerospace"],
                roles=["machine learning"], age_days=1)
    base.update(kw)
    return Verdict(**base)


def posting(**kw) -> RawPosting:
    base = dict(company="Airbus", title="Machine Learning Engineer",
                url="https://example.com/1", source="workday",
                location="Munich", posted="2026-09-19", description="PyTorch.")
    base.update(kw)
    return RawPosting(**base)


class TestTemplate:
    def test_example_letter_parses(self, drafter):
        paragraphs, frame = drafter.load()
        assert paragraphs, "the published example must contain paragraphs"
        assert "{{BULLETS}}" in frame

    def test_every_paragraph_has_tags(self, drafter):
        paragraphs, _ = drafter.load()
        assert all(p.tags for p in paragraphs)


class TestSelection:
    PARAS = [
        Paragraph("AERO", ["aerospace", "simulation"], "aero text"),
        Paragraph("MED", ["imaging", "clinical"], "medical text"),
        Paragraph("OPS", ["docker", "mlops"], "ops text"),
        Paragraph("MATH", ["mathematics"], "maths text"),
    ]

    def test_picks_paragraphs_matching_the_posting(self):
        chosen = Drafter.pick(self.PARAS, ["aerospace", "simulation"], how_many=1)
        assert chosen[0].id == "AERO"

    def test_different_jobs_get_different_paragraphs(self):
        aero = Drafter.pick(self.PARAS, ["aerospace"], how_many=1)[0].id
        med = Drafter.pick(self.PARAS, ["imaging"], how_many=1)[0].id
        assert aero != med

    def test_always_returns_a_complete_letter(self):
        # No tag matches at all must still produce three paragraphs, not one.
        chosen = Drafter.pick(self.PARAS, ["nothing-matches-this"], how_many=3)
        assert len(chosen) == 3

    def test_never_repeats_a_paragraph(self):
        chosen = Drafter.pick(self.PARAS, ["aerospace"], how_many=3)
        assert len({p.id for p in chosen}) == len(chosen)


class TestOutput:
    def test_writes_the_four_files(self, drafter, tmp_path):
        name = drafter.build(posting(), verdict())
        folder = tmp_path / name
        assert {p.name for p in folder.iterdir()} == {
            "00_SUMMARY.md", "checklist.md", "cover_letter_DRAFT.md", "job_description.txt",
        }

    def test_leaves_an_existing_folder_alone(self, drafter, tmp_path):
        name = drafter.build(posting(), verdict())
        letter = tmp_path / name / "cover_letter_DRAFT.md"
        letter.write_text("edited by hand", encoding="utf-8")
        drafter.build(posting(), verdict())
        assert letter.read_text(encoding="utf-8") == "edited by hand"

    def test_no_placeholders_survive(self, drafter, tmp_path):
        name = drafter.build(posting(), verdict())
        text = (tmp_path / name / "cover_letter_DRAFT.md").read_text(encoding="utf-8")
        assert "{{" not in text

    def test_summary_lists_the_warnings(self, drafter, tmp_path):
        v = verdict(flags=[{"code": "EU-ONLY", "why": "May require EU citizenship"}])
        name = drafter.build(posting(), v)
        assert "EU-ONLY" in (tmp_path / name / "00_SUMMARY.md").read_text(encoding="utf-8")


class TestSkillsLine:
    def test_spells_tool_names_correctly(self, drafter):
        line = drafter.skills_line(verdict(skills=["fastapi", "pytorch", "postgresql"]))
        assert "FastAPI" in line and "PyTorch" in line and "PostgreSQL" in line
        assert "Fastapi" not in line

    def test_single_skill_reads_as_singular(self, drafter):
        assert "That is a tool" in drafter.skills_line(verdict(skills=["pytorch"]))

    def test_falls_back_when_nothing_matched(self, drafter):
        assert drafter.skills_line(verdict(skills=[])).startswith("My day-to-day stack")
