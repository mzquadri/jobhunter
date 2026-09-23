"""Is this posting an AI/ML/data role at all?

The first version of this test was one line: does the title contain a phrase
from a list. It is the single most destructive rule in the system, because it
decides what is never seen again, and a title is the part of a posting an
employer is least consistent about. "Algorithm Developer", "Perception
Engineer", "Autonomy Engineer" and "Decision Scientist" are all roles this
profile should see, and none of them contains a machine-learning phrase.

So relevance is now evidence-based and graded:

  * **Certain** — the title names the field outright.
  * **Likely** — the title names an adjacent discipline *and* the body backs it
    up with real technical vocabulary.
  * **Possible** — the title is generic engineering, but the body is dense with
    the field's vocabulary. Kept, and the uncertainty is visible.
  * **No** — nothing in either the title or the body suggests the field.

Only the last is rejected. The rest carry a confidence the score can use, so an
uncertain role sinks rather than disappearing — the same treatment seniority
already gets, and for the same reason.

Deterministic on purpose. §38 allows an optional model for ambiguous cases but
forbids making one a required dependency, and a rule you can read is a rule you
can argue with when it gets something wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum

from app.enrich.terms import alternation


class Relevance(IntEnum):
    NO = 0
    POSSIBLE = 1
    LIKELY = 2
    CERTAIN = 3


@dataclass(frozen=True)
class RelevanceVerdict:
    level: Relevance
    #: 0-1, how much the rest of the score should trust this being in-field.
    confidence: float
    reason: str
    evidence: str = ""

    @property
    def keep(self) -> bool:
        return self.level > Relevance.NO


def _words(*terms: str) -> re.Pattern[str]:
    """One alternation over a vocabulary list. See :mod:`app.enrich.terms`."""
    return alternation(terms)


# The title says it outright. No further evidence needed.
CERTAIN_TITLE = _words(
    "machine learning", "ml engineer", "ml scientist", "ml researcher",
    "deep learning", "artificial intelligence", "ai engineer", "ai scientist",
    "ai researcher", "ai developer", "ai architect", "ai specialist",
    "ai platform", "ml platform", "mlops", "ml ops", "llm", "genai",
    "generative ai", "nlp", "natural language processing",
    "computer vision", "data scientist", "data science", "applied scientist",
    "research scientist", "research engineer", "data engineer",
    "analytics engineer", "machine intelligence", "neural",
    "ml infrastructure", "ai infrastructure", "foundation model",
    "ai/ml", "ml/ai", "ai & ml", "data & ai", "ai and data",
)

# The title names an adjacent discipline. Real, but it needs the body to agree,
# because "Algorithm Engineer" is also a job title in telecoms and in finance.
ADJACENT_TITLE = _words(
    "algorithm", "algorithms", "perception", "autonomy", "autonomous",
    "sensor fusion", "slam", "localization", "localisation", "mapping",
    "robotics", "robotic", "vision", "imaging", "signal processing",
    "simulation", "digital twin", "surrogate", "scientific computing",
    "numerical", "optimization", "optimisation", "operations research",
    "forecasting", "quantitative", "quant", "statistician", "statistics",
    "decision scientist", "decision science", "data analyst", "analytics",
    "data platform", "data infrastructure", "big data", "recommendation",
    "recommender", "search engineer", "ranking", "personalization",
    "personalisation", "intelligent systems", "cognitive", "speech",
    "bioinformatics", "computational", "modelling", "modeling",
    "predictive", "knowledge graph", "semantic",
)

# Generic engineering titles that can be in-field when the body says so.
GENERIC_TITLE = _words(
    "software engineer", "software developer", "backend engineer",
    "backend developer", "platform engineer", "research software engineer",
    "systems engineer", "solutions engineer", "solution engineer",
    "product engineer", "developer", "engineer", "scientist", "researcher",
    "architect", "consultant", "specialist", "analyst",
    "softwareentwickler", "entwickler", "ingenieur",
)

# Vocabulary that only appears in a posting that is really about this field.
# Weighted: a posting naming three of these is not accidentally about ML.
STRONG_BODY = _words(
    "machine learning", "deep learning", "neural network", "neural networks",
    "pytorch", "tensorflow", "scikit-learn", "sklearn", "keras", "jax",
    "transformer", "transformers", "llm", "large language model",
    "generative ai", "computer vision", "nlp", "reinforcement learning",
    "mlops", "model training", "model inference", "feature engineering",
    "hyperparameter", "embeddings", "convolutional", "diffusion model",
    "foundation model", "fine-tuning", "fine tuning", "rag",
    "retrieval augmented", "graph neural network", "xgboost", "lightgbm",
    "semantic segmentation", "object detection", "anomaly detection",
    "predictive model", "statistical model", "data pipeline",
    "artificial intelligence", "künstliche intelligenz", "maschinelles lernen",
)

# Supporting vocabulary. On its own it proves nothing -- every backend job
# mentions Python -- but alongside strong terms it confirms the reading.
SUPPORTING_BODY = _words(
    "python", "numpy", "pandas", "scipy", "sql", "spark", "airflow",
    "kubernetes", "docker", "data science", "algorithm", "algorithms",
    "statistics", "statistical", "optimization", "optimisation",
    "simulation", "modelling", "modeling", "analytics", "dataset",
    "datasets", "training data", "inference", "gpu", "cuda", "matlab",
)

# A title that is decisively some other profession. Checked before anything
# else, because "Sales Engineer" contains "Engineer" and a body full of
# buzzwords will not make it an ML role.
OUT_OF_FIELD_TITLE = _words(
    "data entry", "human resources", "hr manager", "marketing",
    "sales", "account executive", "account manager", "business development",
    "recruiter", "recruiting", "talent acquisition", "hr business partner",
    "human resources", "personalreferent", "marketing manager",
    "social media", "content writer", "copywriter", "graphic designer",
    "accountant", "accounting", "controller", "controlling", "auditor",
    "tax ", "legal counsel", "lawyer", "paralegal", "compliance officer",
    "customer success", "customer service", "customer support",
    "technical support", "help desk", "service desk", "field service",
    "receptionist", "office manager", "executive assistant", "facility",
    "procurement", "buyer", "logistics coordinator", "warehouse",
    "truck driver", "forklift", "mechanic", "electrician", "technician",
    "nurse", "physician", "pharmacist", "cabin crew", "flight attendant",
    "pilot", "ground staff", "security guard", "cleaner", "chef", "cook",
    "elektroniker", "mechatroniker", "schlosser", "monteur", "pflegefach",
    "vertrieb", "einkäufer", "buchhalter", "steuerfachangestellte",
)


def _count(pattern: re.Pattern[str], text: str, cap: int = 12) -> tuple[int, str]:
    """Distinct terms matched, plus the first one, capped to bound the work."""
    found: list[str] = []
    for match in pattern.finditer(text):
        term = match.group(0).lower()
        if term not in found:
            found.append(term)
        if len(found) >= cap:
            break
    return len(found), (found[0] if found else "")


def classify_relevance(
    title: str,
    description: str,
    tags: str = "",
    extra_certain: re.Pattern[str] | None = None,
) -> RelevanceVerdict:
    """Decide whether a posting belongs to this profile's field.

    ``extra_certain`` carries the target roles from settings, so a title the
    user has explicitly asked for counts as certain without anyone editing this
    module. It is checked alongside the built-in list rather than instead of
    it: the built-ins describe the field, the setting describes this person's
    slice of it.
    """
    title = title or ""
    body = f"{tags}\n{description}"

    if match := OUT_OF_FIELD_TITLE.search(title):
        return RelevanceVerdict(
            Relevance.NO, 0.0,
            "the title is for a different profession",
            evidence=match.group(0),
        )

    match = CERTAIN_TITLE.search(title)
    if match is None and extra_certain is not None:
        match = extra_certain.search(title)
    if match:
        return RelevanceVerdict(
            Relevance.CERTAIN, 1.0,
            "the title names the field directly",
            evidence=match.group(0),
        )

    strong, strong_first = _count(STRONG_BODY, body)
    supporting, _ = _count(SUPPORTING_BODY, body)

    if match := ADJACENT_TITLE.search(title):
        signal = match.group(0)
        if strong >= 1:
            return RelevanceVerdict(
                Relevance.LIKELY, 0.9,
                f"the title is an adjacent discipline and the posting names {strong_first}",
                evidence=f"{signal} · {strong_first}",
            )
        if supporting >= 3:
            return RelevanceVerdict(
                Relevance.POSSIBLE, 0.7,
                "the title is an adjacent discipline with supporting technical detail",
                evidence=signal,
            )
        # An adjacent title with a body that says nothing technical is usually a
        # different kind of engineering wearing a familiar word.
        return RelevanceVerdict(
            Relevance.NO, 0.0,
            f"the title mentions {signal} but nothing in the posting is about this field",
            evidence=signal,
        )

    if GENERIC_TITLE.search(title):
        if strong >= 3:
            return RelevanceVerdict(
                Relevance.LIKELY, 0.85,
                f"a generic title, but the posting is clearly about {strong_first}",
                evidence=strong_first,
            )
        if strong >= 2 and supporting >= 2:
            return RelevanceVerdict(
                Relevance.POSSIBLE, 0.65,
                f"a generic title with real technical content ({strong_first})",
                evidence=strong_first,
            )
        return RelevanceVerdict(
            Relevance.NO, 0.0,
            "a general engineering role with no AI, ML or data content",
        )

    # An unrecognised title. Only a body that is unmistakably about the field
    # rescues it, because this is where genuinely unrelated work arrives.
    if strong >= 4:
        return RelevanceVerdict(
            Relevance.POSSIBLE, 0.6,
            f"an unfamiliar title, but the posting is dense with {strong_first}",
            evidence=strong_first,
        )

    return RelevanceVerdict(
        Relevance.NO, 0.0, "not an AI, ML or data role",
    )


RELEVANCE_LABELS: dict[int, str] = {
    Relevance.CERTAIN: "Clearly in your field",
    Relevance.LIKELY: "Very likely in your field",
    Relevance.POSSIBLE: "Possibly in your field",
    Relevance.NO: "Not in your field",
}
