"""Transferable skills.

A posting that asks for TensorFlow is not closed to someone who has spent two
years in PyTorch, and a posting that asks for Pinecone is not closed to someone
who has run Qdrant in production. Literal string matching says otherwise, and
that single fact is what turns a realistic 74% opportunity into a 58% one that
never gets looked at.

So requirements are grouped into families. Holding any member of a family earns
partial credit towards the others, at a factor stated per family rather than
guessed per pair. The credit is never silent: every transfer produces a
sentence naming both skills, so the interface can say *why* a requirement was
treated as met rather than presenting a number that cannot be checked.

Two rules keep this honest:

  * Families contain genuinely adjacent technologies. Kafka and PostgreSQL are
    both infrastructure and are not in a family together.
  * Transfer is never 1.0. Knowing PyTorch is not knowing TensorFlow; it is
    knowing most of what makes TensorFlow learnable in a fortnight, which is
    what an employer is really asking about. A full-credit family would be a
    family whose members are the same thing under two names, and those are
    handled as aliases instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.enrich.terms import term_pattern


@dataclass(frozen=True)
class Family:
    """One group of adjacent technologies."""

    name: str
    members: tuple[str, ...]
    #: Credit, 0-1, for holding a different member of this family.
    transfer: float
    #: Completes the sentence "..., which transfers to X".
    why: str


# Ordered longest-name-first inside each family so "google cloud" is preferred
# over "gcp" when both would match; purely cosmetic, it only affects wording.
FAMILIES: tuple[Family, ...] = (
    Family(
        name="deep-learning frameworks",
        members=("pytorch", "tensorflow", "keras", "jax", "flax", "mxnet", "paddlepaddle"),
        transfer=0.75,
        why="the same training loops, autograd and tensor semantics",
    ),
    Family(
        name="classical ML libraries",
        members=("scikit-learn", "sklearn", "xgboost", "lightgbm", "catboost", "statsmodels"),
        transfer=0.8,
        why="a shared estimator API and the same modelling decisions",
    ),
    Family(
        name="vector databases",
        members=("qdrant", "pinecone", "weaviate", "milvus", "chroma", "faiss", "pgvector",
                 "opensearch", "elasticsearch"),
        transfer=0.75,
        why="the same indexing, filtering and recall trade-offs",
    ),
    Family(
        name="major clouds",
        members=("aws", "azure", "gcp", "google cloud", "amazon web services",
                 "microsoft azure"),
        transfer=0.55,
        why="the same managed primitives under different names",
    ),
    Family(
        name="container orchestration",
        members=("kubernetes", "k8s", "openshift", "nomad", "ecs", "docker swarm"),
        transfer=0.6,
        why="the same scheduling and service model",
    ),
    Family(
        name="containers",
        members=("docker", "podman", "containerd", "containerization", "containerisation"),
        transfer=0.9,
        why="the same images and runtime",
    ),
    Family(
        name="relational databases",
        members=("postgresql", "postgres", "mysql", "mariadb", "sql server", "oracle db",
                 "sqlite", "sql"),
        transfer=0.85,
        why="one query language and the same relational modelling",
    ),
    Family(
        name="event streaming",
        members=("kafka", "pulsar", "rabbitmq", "kinesis", "event streaming", "nats",
                 "event-driven"),
        transfer=0.75,
        why="the same producer/consumer and delivery guarantees",
    ),
    Family(
        name="Python web frameworks",
        members=("fastapi", "flask", "django", "starlette", "tornado", "rest api",
                 "restful api"),
        transfer=0.85,
        why="the same request handling, validation and deployment shape",
    ),
    Family(
        name="workflow orchestration",
        members=("airflow", "prefect", "dagster", "luigi", "kubeflow", "argo workflows",
                 "metaflow"),
        transfer=0.7,
        why="the same DAG scheduling and backfill concerns",
    ),
    Family(
        name="experiment tracking",
        members=("mlflow", "weights & biases", "wandb", "neptune.ai", "clearml",
                 "tensorboard", "sacred"),
        transfer=0.8,
        why="the same run, artefact and metric bookkeeping",
    ),
    Family(
        name="distributed data processing",
        members=("spark", "pyspark", "dask", "ray", "flink", "beam", "hadoop"),
        transfer=0.6,
        why="the same partitioning and shuffle model",
    ),
    Family(
        name="analytics warehouses",
        members=("snowflake", "bigquery", "redshift", "databricks", "clickhouse",
                 "duckdb", "synapse"),
        transfer=0.65,
        why="columnar SQL over the same analytical patterns",
    ),
    Family(
        name="infrastructure as code",
        members=("terraform", "pulumi", "cloudformation", "ansible", "helm", "cdk"),
        transfer=0.6,
        why="the same declarative provisioning model",
    ),
    Family(
        name="CI systems",
        members=("github actions", "gitlab ci", "jenkins", "circleci", "azure devops",
                 "teamcity", "ci/cd"),
        transfer=0.85,
        why="the same pipeline, caching and artefact concepts",
    ),
    Family(
        name="graph technologies",
        members=("neo4j", "knowledge graph", "knowledge graphs", "rdf", "sparql",
                 "cypher", "tigergraph", "arangodb", "graph database"),
        transfer=0.7,
        why="the same traversal and graph-modelling work",
    ),
    Family(
        name="geometric deep learning",
        members=("gnn", "graph neural network", "graph neural networks",
                 "geometric deep learning", "pytorch geometric", "dgl",
                 "message passing", "graph representation learning"),
        transfer=0.8,
        why="message passing over graph structure either way",
    ),
    Family(
        name="attention architectures",
        members=("transformer", "transformers", "attention", "self-attention",
                 "bert", "gpt", "vision transformer", "vit", "encoder-decoder"),
        transfer=0.85,
        why="one architecture family and the same training behaviour",
    ),
    Family(
        name="LLM application tooling",
        members=("langchain", "llamaindex", "haystack", "semantic kernel", "dspy",
                 "rag", "retrieval augmented generation", "retrieval-augmented generation"),
        transfer=0.75,
        why="the same retrieval, chunking and prompting pipeline",
    ),
    Family(
        name="LLM serving",
        members=("vllm", "tgi", "text generation inference", "ollama", "llama.cpp",
                 "triton inference server", "torchserve", "bentoml", "kserve"),
        transfer=0.7,
        why="the same batching, quantisation and throughput problems",
    ),
    Family(
        name="inference runtimes",
        members=("onnx", "onnxruntime", "tensorrt", "openvino", "coreml", "tflite",
                 "quantization", "quantisation"),
        transfer=0.65,
        why="the same graph export and optimisation steps",
    ),
    Family(
        name="classical computer vision",
        members=("opencv", "computer vision", "image processing", "scikit-image",
                 "pillow", "image segmentation", "object detection"),
        transfer=0.8,
        why="the same pixel-level operations and evaluation",
    ),
    Family(
        name="object-oriented systems languages",
        members=("c++", "rust", "java", "c#", "go", "golang", "scala"),
        transfer=0.4,
        why="transferable systems thinking, though the language itself differs",
    ),
    Family(
        name="scientific computing stacks",
        members=("numpy", "scipy", "matlab", "julia", "octave", "numerical methods",
                 "scientific computing", "fortran"),
        transfer=0.7,
        why="the same numerical methods under a different syntax",
    ),
    Family(
        name="simulation and digital twins",
        members=("simulation", "digital twin", "surrogate model", "surrogate models",
                 "finite element", "fem", "cfd", "physics-informed", "reduced order model"),
        transfer=0.7,
        why="the same surrogate-modelling and validation work",
    ),
    Family(
        name="robotics middleware",
        members=("ros", "ros2", "robot operating system", "mavlink", "px4", "autoware"),
        transfer=0.6,
        why="the same node, topic and message plumbing",
    ),
    Family(
        name="in-memory stores",
        members=("redis", "memcached", "valkey", "hazelcast"),
        transfer=0.85,
        why="the same caching and expiry model",
    ),
    Family(
        name="object storage",
        members=("minio", "s3", "blob storage", "gcs", "object storage"),
        transfer=0.85,
        why="the same bucket and object semantics",
    ),
    Family(
        name="dashboarding",
        members=("tableau", "power bi", "looker", "superset", "metabase", "grafana",
                 "qlik", "streamlit", "dash"),
        transfer=0.65,
        why="the same charting and data-model work",
    ),
    Family(
        name="frontend frameworks",
        members=("react", "next.js", "vue", "angular", "svelte", "typescript"),
        transfer=0.6,
        why="the same component model and build tooling",
    ),
    Family(
        name="uncertainty methods",
        members=("uncertainty quantification", "conformal prediction", "calibration",
                 "bayesian", "bayesian inference", "probabilistic modelling",
                 "monte carlo", "gaussian process"),
        transfer=0.75,
        why="the same probabilistic reasoning about model confidence",
    ),
    Family(
        name="time series and forecasting",
        members=("time series", "time-series", "forecasting", "demand forecasting",
                 "arima", "prophet", "anomaly detection", "predictive maintenance"),
        transfer=0.75,
        why="the same temporal modelling and backtesting",
    ),
    Family(
        name="optimisation",
        members=("optimization", "optimisation", "operations research", "linear programming",
                 "mixed integer", "gurobi", "cplex", "or-tools", "constraint programming",
                 "scheduling algorithms"),
        transfer=0.6,
        why="the same formulation and solver work",
    ),
)


_compile = term_pattern


# Compiled once at import; the tables above never change at runtime.
_MEMBER_PATTERNS: dict[str, re.Pattern[str]] = {
    member: _compile(member) for family in FAMILIES for member in family.members
}
_FAMILY_OF: dict[str, Family] = {
    member: family for family in FAMILIES for member in family.members
}


@dataclass
class Transfer:
    """One requirement met by an adjacent skill rather than the literal one."""

    requirement: str
    #: The skill on the profile that earned the credit.
    via: str
    credit: float
    family: str
    why: str

    def sentence(self) -> str:
        return (
            f"Asks for {self.requirement}; your {self.via} experience transfers "
            f"— {self.why}"
        )


@dataclass
class TransferVerdict:
    transfers: list[Transfer] = field(default_factory=list)
    #: Requirements with no literal match and no adjacent skill either.
    unmet: list[str] = field(default_factory=list)

    @property
    def credit(self) -> float:
        """Total partial credit, in units of 'requirements met'."""
        return sum(t.credit for t in self.transfers)


def _skills_present(skills: set[str], member: str) -> bool:
    """Whether the profile claims this family member.

    Compares against the profile's own skill list, normalised, rather than
    searching the posting: the question here is what *I* have, not what the
    employer wrote.
    """
    member_l = member.lower()
    if member_l in skills:
        return True
    # 'scikit-learn' on the profile should satisfy 'scikit learn' in a family.
    squashed = member_l.replace("-", "").replace(" ", "").replace("_", "")
    return any(s.replace("-", "").replace(" ", "").replace("_", "") == squashed
               for s in skills)


def find_transfers(requirements: list[str], profile_skills: list[str]) -> TransferVerdict:
    """Look for adjacent experience covering requirements I do not literally have.

    ``requirements`` are terms the posting actually contains and the profile
    does not claim — the output of ``SkillExtractor.missing_from``. Nothing is
    invented here: a requirement only appears because the employer wrote it.
    """
    mine = {s.lower() for s in profile_skills}
    verdict = TransferVerdict()

    for requirement in requirements:
        family = _FAMILY_OF.get(requirement.lower())
        if family is None:
            verdict.unmet.append(requirement)
            continue

        # The best member I actually hold. Sorted for a stable explanation
        # rather than whichever happened to be declared first.
        held = sorted(
            (m for m in family.members
             if m.lower() != requirement.lower() and _skills_present(mine, m)),
            key=lambda m: (-len(m), m),
        )
        if not held:
            verdict.unmet.append(requirement)
            continue

        verdict.transfers.append(Transfer(
            requirement=requirement,
            via=held[0],
            credit=family.transfer,
            family=family.name,
            why=family.why,
        ))

    return verdict


def family_members_in(text: str) -> set[str]:
    """Every family member named anywhere in a text.

    Used to widen the requirement watchlist beyond a hand-maintained constant:
    if a posting names a technology that sits in a family, it is a requirement
    worth reasoning about whether or not anyone thought to list it.
    """
    return {member for member, pattern in _MEMBER_PATTERNS.items() if pattern.search(text)}
