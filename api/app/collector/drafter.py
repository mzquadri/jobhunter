"""Build an application folder for a posting worth applying to.

The interesting part is paragraph selection. config/letter.md holds every
paragraph the candidate might use, each tagged. For a given posting each
paragraph is scored by how many of its tags the job actually asked for, and
the best three are kept. An aerospace simulation role and a pharma imaging
role therefore get genuinely different letters, not the same letter with the
company name swapped.

Nothing here is sent anywhere. It writes files a human reads, edits and
submits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.collector.matcher import Verdict
from app.collector.sources import RawPosting
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
    "weights & biases": "Weights & Biases", "graph neural": "graph neural networks",
    "vector database": "vector databases", "knowledge graph": "knowledge graphs",
    "retrieval-augmented": "retrieval-augmented generation",
    "physics-informed": "physics-informed models",
}

AEROSPACE = {"aerospace", "aviation", "aircraft", "airline", "space", "satellite",
             "rocket", "propulsion", "turbine", "defence", "defense"}
AUTOMOTIVE = {"automotive", "vehicle", "car", "mobility", "autonomous", "adas"}
MEDICAL = {"medical", "healthcare", "imaging", "radiology", "pharma", "clinical"}


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

    # ---- template -------------------------------------------------------
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
        m = re.search(r"<!--\s*LETTER\s*-->\s*(.*)", raw, re.S)
        return paragraphs, (m.group(1).strip() if m else "")

    @staticmethod
    def pick(paragraphs: list[Paragraph], wanted: list[str], how_many: int = 3) -> list[Paragraph]:
        """Rank paragraphs by tag overlap with what the posting asked for."""
        want = {w.lower() for w in wanted}
        scored: list[tuple[float, Paragraph]] = []
        for para in paragraphs:
            overlap = float(sum(1 for t in para.tags if t in want))
            if not overlap:
                # partial credit: "computer vision" wanted should match tag "vision"
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

    # ---- pieces ---------------------------------------------------------
    def skills_line(self, verdict: Verdict) -> str:
        skills = verdict.skills
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

    def why_company(self, posting: RawPosting, verdict: Verdict) -> str:
        domains = set(verdict.domains)
        company = posting.company
        if domains & AEROSPACE:
            hook = (f"{company} works on systems where a wrong prediction is not a rounding "
                    "error, which is exactly why I spent my thesis on quantifying when a "
                    "model should not be trusted.")
        elif domains & AUTOMOTIVE:
            hook = (f"My internship at AUDI AG showed me how an automotive engineering "
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

    # ---- output ---------------------------------------------------------
    @staticmethod
    def safe_name(text: str, limit: int = 48) -> str:
        text = re.sub(r"[^\w\s\-]", "", text).strip()
        text = re.sub(r"[\s_]+", "-", text)
        return text[:limit].strip("-") or "job"

    def build(self, posting: RawPosting, verdict: Verdict) -> str:
        """Create the application folder. Returns its name, or '' if it existed."""
        paragraphs, frame = self.load()
        wanted = verdict.skills + verdict.domains + verdict.roles
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
            .replace("{{SKILLS_LINE}}", self.skills_line(verdict))
            .replace("{{WHY_COMPANY}}", self.why_company(posting, verdict))
        )

        (folder / "cover_letter_DRAFT.md").write_text(letter, encoding="utf-8")
        (folder / "job_description.txt").write_text(
            f"{posting.title}\n{posting.company}\n{location}\n"
            f"Posted: {posting.posted or 'unknown'}\n\n{posting.url}\n\n"
            f"{posting.description or '(not captured)'}\n",
            encoding="utf-8",
        )
        (folder / "00_SUMMARY.md").write_text(
            self._summary(posting, verdict, chosen), encoding="utf-8"
        )
        (folder / "checklist.md").write_text(self._checklist(posting), encoding="utf-8")
        return folder_name

    def _summary(self, posting: RawPosting, verdict: Verdict, chosen: list[Paragraph]) -> str:
        age = "" if verdict.age_days is None else f"  ({verdict.age_days} days ago)"
        lines = [
            f"# {posting.title}",
            "",
            f"**{posting.company}** · {posting.location or 'location not stated'}",
            "",
            "| | |",
            "|---|---|",
            f"| Match score | **{verdict.score}** |",
            f"| Posted | {posting.posted or 'unknown'}{age} |",
            f"| Source | {posting.source} |",
            f"| Link | {posting.url} |",
            "",
        ]
        if verdict.flags:
            lines += ["## Check these before you spend time", ""]
            lines += [f"- **{f['code']}** — {f['why']}" for f in verdict.flags]
            lines += [""]
        lines += [
            "## Why you match",
            "",
            f"Skills the posting names that you have: {', '.join(verdict.skills) or '—'}",
            "",
            f"Domain overlap: {', '.join(verdict.domains) or '—'}",
            "",
            f"Paragraphs chosen for the draft: {', '.join(p.id for p in chosen)}",
            "",
            "## Next",
            "",
            "1. Open `cover_letter_DRAFT.md` and rewrite the **Why this company** paragraph.",
            "2. Skim `job_description.txt` for anything the draft should answer.",
            "3. Apply at the link above, then tick `checklist.md`.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _checklist(posting: RawPosting) -> str:
        return "\n".join([
            f"# Application checklist — {posting.company}, {posting.title}",
            "",
            "- [ ] Read the full job description",
            "- [ ] Rewrote the 'Why this company' paragraph (do not send it generic)",
            "- [ ] Cover letter exported to PDF",
            "- [ ] CV attached",
            "- [ ] Master transcript attached (if asked)",
            "- [ ] Bachelor degree and transcript attached (if asked)",
            "- [ ] Checked whether the German level is a problem",
            "- [ ] Checked whether they sponsor a visa or need EU citizenship",
            f"- [ ] **Submitted** at {posting.url}",
            "- [ ] Marked as applied in the dashboard",
            "- [ ] Follow-up reminder set for two weeks from submission",
        ])
