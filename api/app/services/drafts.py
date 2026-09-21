"""Application folders for postings worth applying to.

The interesting part is paragraph selection. ``config/letter.md`` holds every
paragraph the candidate might use, each tagged. For a given posting each
paragraph is scored by how many of its tags the job actually asked for and the
best three are kept, so an aerospace role and a pharma imaging role receive
genuinely different letters rather than the same letter with the company name
swapped.

Nothing here is sent anywhere. It writes files a human reads, edits and
submits. §19 is explicit that no external application may be submitted without
confirmation, and this module is the boundary: it prepares, it never sends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.matching import MatchResult
from app.settings import Profile

BULLET_RE = re.compile(
    r"<!--\s*BULLET:\s*([A-Z0-9\-]+)\s*\|\s*tags:\s*([^>]*?)-->\s*(.*?)(?=\n<!--|\Z)",
    re.S,
)

# Tool names a cover letter must not get wrong -- "Fastapi" or "Pytorch" reads
# as carelessness to exactly the people who would notice.
SPELLING = {
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "scikit-learn": "scikit-learn",
    "xgboost": "XGBoost", "hugging face": "Hugging Face", "fastapi": "FastAPI",
    "postgresql": "PostgreSQL", "mongodb": "MongoDB", "mlflow": "MLflow",
    "neo4j": "Neo4j", "qdrant": "Qdrant", "ollama": "Ollama", "numpy": "NumPy",
    "ci/cd": "CI/CD", "llm": "LLMs", "rag": "RAG", "gnn": "GNNs", "ocr": "OCR",
    "lora": "LoRA", "sql": "SQL", "matlab": "MATLAB", "grad-cam": "Grad-CAM",
    "jax": "JAX", "opencv": "OpenCV", "ros": "ROS", "aws": "AWS",
    "weights & biases": "Weights & Biases", "graph neural": "graph neural networks",
    "vector database": "vector databases", "knowledge graph": "knowledge graphs",
    "retrieval-augmented": "retrieval-augmented generation",
    "physics-informed": "physics-informed models",
}

AEROSPACE = {"aerospace", "aviation", "aircraft", "airline", "space", "satellite",
             "rocket", "propulsion", "turbine", "defence", "defense"}
AUTOMOTIVE = {"automotive", "vehicle", "car", "mobility", "autonomous", "adas"}
MEDICAL = {"medical", "healthcare", "imaging", "radiology", "pharma", "clinical"}


@dataclass(frozen=True)
class DraftInput:
    """Just enough of a posting to write about it."""

    company: str
    title: str
    url: str
    location: str = ""
    posted_at: date | None = None
    description: str = ""
    source: str = ""


@dataclass
class Paragraph:
    id: str
    tags: list[str]
    text: str


class Drafter:
    def __init__(self, profile: Profile, letter_path: Path, output_dir: Path) -> None:
        self.p = profile
        self.letter_path = Path(letter_path)
        self.output_dir = Path(output_dir)

    @property
    def available(self) -> bool:
        return self.letter_path.exists()

    def load(self) -> tuple[list[Paragraph], str]:
        raw = self.letter_path.read_text(encoding="utf-8")
        paragraphs = [
            Paragraph(
                id=pid.strip(),
                tags=[t.strip().lower() for t in tags.split(",") if t.strip()],
                text=text.strip(),
            )
            for pid, tags, text in BULLET_RE.findall(raw)
        ]
        match = re.search(r"<!--\s*LETTER\s*-->\s*(.*)", raw, re.S)
        return paragraphs, (match.group(1).strip() if match else "")

    @staticmethod
    def pick(paragraphs: list[Paragraph], wanted: list[str], how_many: int = 3) -> list[Paragraph]:
        """Rank paragraphs by tag overlap with what the posting asked for."""
        want = {w.lower() for w in wanted}
        scored: list[tuple[float, Paragraph]] = []
        for para in paragraphs:
            overlap = float(sum(1 for t in para.tags if t in want))
            if not overlap:
                # Partial credit, so "computer vision" in the posting still
                # reaches a paragraph tagged merely "vision".
                overlap = sum(0.5 for t in para.tags for w in want if t in w or w in t)
            scored.append((overlap, para))
        scored.sort(key=lambda x: -x[0])

        chosen = [p for s, p in scored if s > 0][:how_many]
        if len(chosen) < how_many:                 # always send a complete letter
            for para in (p for _, p in scored):
                if len(chosen) >= how_many:
                    break
                if para not in chosen:
                    chosen.append(para)
        return chosen

    def skills_line(self, result: MatchResult) -> str:
        skills = result.skills
        if not skills:
            return ("My day-to-day stack is Python, PyTorch, FastAPI, Docker and SQL, "
                    "with Kafka and CI/CD around the services I ship.")
        pretty: list[str] = []
        for s in skills[:7]:
            pretty.append(SPELLING[s] if s in SPELLING
                          else (s if s[:1].isupper() else s.capitalize()))
        if len(pretty) > 1:
            listed = ", ".join(pretty[:-1]) + " and " + pretty[-1]
            tail = ("These are tools I use in production rather than ones I have only "
                    "read about.")
        else:
            listed = pretty[0]
            tail = "That is a tool I use in production rather than one I have only read about."
        return f"The posting asks for {listed}. {tail}"

    def why_company(self, posting: DraftInput, result: MatchResult) -> str:
        domains = set(result.domains)
        company = posting.company
        if domains & AEROSPACE:
            hook = (f"{company} works on systems where a wrong prediction is not a rounding "
                    "error, which is exactly why I spent my thesis on quantifying when a "
                    "model should not be trusted.")
        elif domains & AUTOMOTIVE:
            hook = (f"My internship in automotive engineering showed me how such an "
                    f"organisation actually runs, and my thesis applied uncertainty "
                    f"quantification to traffic and mobility models — both of which point "
                    f"straight at the work {company} is doing.")
        elif domains & MEDICAL:
            hook = (f"I have trained and deployed a chest X-ray classifier with Grad-CAM "
                    f"explanations, so I understand why {company} needs models clinicians "
                    f"can interrogate rather than simply trust.")
        else:
            hook = (f"What draws me to {company} is the chance to work on models that run in "
                    "production and are held to a real standard, which is the kind of work I "
                    "have been doing.")
        return (
            hook + "\n\n"
            "> **Replace this paragraph before sending.** Spend ten minutes on the company: "
            "name the specific team, product or recent announcement you care about. This is "
            "the paragraph a recruiter reads to decide whether you actually want *this* job. "
            "A generic version here undoes everything above it."
        )

    @staticmethod
    def safe_name(text: str, limit: int = 48) -> str:
        text = re.sub(r"[^\w\s\-]", "", text).strip()
        text = re.sub(r"[\s_]+", "-", text)
        return text[:limit].strip("-") or "job"

    def build(self, posting: DraftInput, result: MatchResult) -> str:
        """Create the application folder. Returns its name, or '' if it existed."""
        paragraphs, frame = self.load()
        wanted = result.skills + result.domains + ([result.role_category.lower()]
                                                   if result.role_category else [])
        chosen = self.pick(paragraphs, wanted)

        folder_name = "{}__{}__{}".format(
            datetime.now().strftime("%Y-%m-%d"),
            self.safe_name(posting.company, 24),
            self.safe_name(posting.title, 44),
        )
        folder = self.output_dir / folder_name
        if folder.exists():
            return folder_name
        folder.mkdir(parents=True, exist_ok=True)

        c = self.p.candidate
        location = posting.location or ""
        letter = (
            frame
            .replace("{{DATE}}", datetime.now().strftime("%d %B %Y"))
            .replace("{{ROLE}}", posting.title)
            .replace("{{COMPANY}}", posting.company)
            .replace("{{LOCATION_LINE}}", f" — {location}" if location else "")
            .replace("{{GRADUATION}}", str(c.get("available_from", "")))
            .replace("{{NAME}}", str(c.get("name", "")))
            .replace("{{EMAIL}}", str(c.get("email", "")))
            .replace("{{PHONE}}", str(c.get("phone", "")))
            .replace("{{CITY}}", str(c.get("city", "")))
            .replace("{{BULLETS}}", "\n\n".join(p.text for p in chosen))
            .replace("{{SKILLS_LINE}}", self.skills_line(result))
            .replace("{{WHY_COMPANY}}", self.why_company(posting, result))
        )

        (folder / "cover_letter_DRAFT.md").write_text(letter, encoding="utf-8")
        (folder / "job_description.txt").write_text(
            f"{posting.title}\n{posting.company}\n{location}\n"
            f"Posted: {posting.posted_at or 'unknown'}\nSource: {posting.source}\n\n"
            f"{posting.url}\n\n{posting.description or '(not captured)'}\n",
            encoding="utf-8",
        )
        (folder / "00_SUMMARY.md").write_text(
            self._summary(posting, result, chosen), encoding="utf-8"
        )
        (folder / "checklist.md").write_text(self._checklist(posting), encoding="utf-8")
        return folder_name

    def _summary(self, posting: DraftInput, result: MatchResult,
                 chosen: list[Paragraph]) -> str:
        age = "" if result.age_days is None else f"  ({result.age_days} days ago)"
        sub = result.sub.as_dict()
        lines = [
            f"# {posting.title}",
            "",
            f"**{posting.company}** · {posting.location or 'location not stated'}",
            "",
            "| | |",
            "|---|---|",
            f"| Overall match | **{result.score}** |",
            *(f"| {name.title()} | {value} |" for name, value in sub.items()),
            f"| Posted | {posting.posted_at or 'unknown'}{age} |",
            f"| Source | {posting.source} |",
            f"| Link | {posting.url} |",
            "",
        ]
        if result.reasons:
            lines += ["## Why this matches", ""]
            lines += [f"- {r}" for r in result.reasons]
            lines += [""]
        if result.gaps:
            lines += ["## Gaps and things to check", ""]
            lines += [f"- {g}" for g in result.gaps]
            lines += [""]
        lines += [
            f"Paragraphs chosen for the draft: {', '.join(p.id for p in chosen)}",
            "",
            "## Next",
            "",
            "1. Open `cover_letter_DRAFT.md` and rewrite the **Why this company** paragraph.",
            "2. Skim `job_description.txt` for anything the draft should answer.",
            "3. Apply at the link above, then set the status in the dashboard.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _checklist(posting: DraftInput) -> str:
        return "\n".join([
            f"# Application checklist — {posting.company}, {posting.title}",
            "",
            "- [ ] Read the full job description",
            "- [ ] Rewrote the 'Why this company' paragraph (do not send it generic)",
            "- [ ] Cover letter exported to PDF",
            "- [ ] CV attached",
            "- [ ] Transcripts attached (if asked)",
            "- [ ] Checked whether the German level is a problem",
            "- [ ] Checked whether they sponsor a visa or need EU citizenship",
            f"- [ ] **Submitted** at {posting.url}",
            "- [ ] Status set to 'applied' in the dashboard",
            "- [ ] Follow-up date set for two weeks from submission",
        ])
