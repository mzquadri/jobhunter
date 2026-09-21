# JobHunter

Finds the AI/ML jobs worth applying to, explains why each one scored what it
did, and drafts the cover letter — so the work left is reading and deciding,
not searching.

It sweeps 45 sources every hour, drops everything you could not take, and
shows what survives. It never applies on your behalf.

```
~2,400 postings read  →  gates and scoring  →  ~90 worth your evening
```

<!-- Screenshots: docs/screenshots/{overview,jobs,detail}.png -->

## Why it exists

A search for "machine learning engineer" in Germany returns thousands of
results. Most are senior roles, working-student positions, postings from three
months ago, or jobs in countries you cannot move to. Reading them is the actual
work, and it is the part that stops people applying.

This does the reading. What reaches the dashboard is full-time, at a level a
recent graduate can apply to, somewhere you can legally work, in your field,
and recent enough that applying is still worth the evening.

## What it does

**Reads employer systems directly.** Large companies do not build their own
career sites; they rent one of a handful of applicant-tracking systems, each
with a public JSON or RSS endpoint. So there is one adapter per ATS rather than
one scraper per company, and adding an employer is a line of YAML.

| Adapter | Reaches |
| --- | --- |
| `workday` | Airbus, ABB, Roche, Novartis, Thales, Philips, Accenture, Logitech |
| `smartrecruiters` | Bosch, Continental, Etihad |
| `successfactors` | BMW, ZF, MAN, TRATON, Scania, MTU Aero, DLR, SAP, Swiss Re, Schaeffler |
| `greenhouse` | Helsing, Isar Aerospace, Wayve, Celonis, Anthropic, Databricks, N26 |
| `ashby` | DeepL, Cohere, Parloa, Synthesia |
| `lever`, `personio`, `workable` | ProGlove, Wandelbots, Agile Robots and any board on these |
| `arbeitnow`, `jobsch` | Germany-wide and Switzerland-wide boards |
| `adzuna` | Optional; adds salary data across DE/CH/AT/NL |

**Filters before it scores.** Four gates, each added because something real got
through without it:

1. **Full-time only** — drops Praktikum, Werkstudent, placements, VIE and PhD
   positions. `graduate programme` and `trainee` are deliberately kept.
2. **Your field** — an ML/AI/data term must be in the title.
3. **Somewhere you can work** — drops postings outside Europe. Without this, a
   perfectly matched role in Bangalore outranked every job in Munich: the
   skills matched and nothing said the location made it useless.
4. **Still fresh** — nothing older than `max_age_days`.

Seniority is *not* a gate. A senior role stays searchable and takes a heavy
penalty, so it sinks rather than disappearing.

**Explains every score.** Seven sub-scores, the reasons behind them, and the
gaps against your profile — all visible, none hidden behind a tooltip:

```
Overall 78          Technical 86   Location 91   Freshness 100
                    Experience 95  Language 95   Domain 63    Education 85

+ Matches your genai experience: llm, rag, retrieval-augmented
+ Spans 5 of your skill areas
+ Advertised at graduate or junior level
− Asks for azure, which is not on your profile
```

**Classifies the language requirement** into nine levels, from *English only*
through *German C1+*, each with the sentence it was read from. A large share of
German postings are effectively closed to a non-fluent speaker, and knowing
which in two seconds rather than two hours is most of the value here.

**Never invents a salary.** A figure appears only when the employer printed
one. Anything annualised or converted is marked `≈`, so a derived number is
never mistaken for the employer's own. There is no market-data estimator,
because there is no source for one — and a plausible guess is worse than an
empty field, since it looks like information.

**Tells you what broke.** A run that found nothing because six sources failed
looks identical to a run where nothing was posted, unless the difference is
recorded. Every source's outcome is stored per run and shown on the dashboard.

## Quick start

Requires Docker.

```bash
git clone https://github.com/mzquadri/jobhunter
cd jobhunter

cp .env.example .env
cp config/profile.example.yml config/profile.yml
cp config/letter.example.md   config/letter.md
# edit both config files — they are yours, and gitignored

docker compose up -d --build
```

| | |
| --- | --- |
| Dashboard | <http://localhost:3000> |
| API | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |

The worker sweeps on startup and then hourly, so the dashboard fills itself in
within about a minute of the first boot.

## The dashboard

- **Overview** — what arrived today, what is new since the last run, postings
  per day, and breakdowns by country, language, category and match.
- **Jobs** — a filterable table: country, employer tier, language requirement,
  work arrangement, status, minimum match, posting age. Saved searches run the
  same query code, so a saved filter behaves exactly like the one that made it.
- **Job detail** — the full match analysis, every source that reported the
  vacancy, the posting itself, and your own tracking panel.
- **Companies** — who is checked hourly and who has to be checked by hand.
- **Discovery** — run history, per-source health, what each run did.

## Application tracking

Thirteen statuses from *New* to *Offer*, with a recorded history of every
transition, plus notes, contact person, follow-up date and salary discussion.

These fields are yours. **A discovery run never writes them**, so re-running is
always safe — a sweep can refresh a score while your notes stay untouched. That
invariant is asserted directly in the test suite.

## Configuration

Everything lives in `config/profile.yml`. There is no code to change.

```yaml
companies:
  - { name: Siemens Energy, adapter: workday, arg: "tenant|wd3|SiteName", tier: high }
```

Worth knowing:

| Setting | Does |
| --- | --- |
| `search.max_age_days` | Hides anything older. Default 14 |
| `search.min_score` | Below this a posting is noise |
| `search.draft_min_score` | Only stronger matches get a cover-letter draft |
| `locations.tiers` | Points per city — Munich 24, Germany 20, Switzerland 17 |
| `locations.exclude` | Hard reject |
| `scoring.weights` | How much each sub-score contributes |
| `scoring.freshness_curve` | `[[days, score], …]`. Steep by design |
| `flags` | Warning rules and what each costs |
| `saved_searches` | Seeded on first boot; yours are never overwritten |

`config/profile.yml` and `config/letter.md` are gitignored. The committed
`*.example.*` files carry placeholders only.

## How matching works

Each sub-score is 0–100, combined by the weights in your profile, then adjusted:

```
score = Σ(sub_score × weight)
      + tier_bonus        (a shortlisted employer lifts a good match)
      − seniority_penalty (senior 30, lead 45, executive 60)
      − flag_penalties    (EU-only 20, no-sponsorship 20, German 10)
```

Nothing is random and nothing is a constant buried in code. The reasons shown
in the interface are generated by the same calculation that produced the
number — if it says "Strong PyTorch match", the technical sub-score rose
because the word PyTorch is in the posting.

See [docs/architecture.md](docs/architecture.md) for the full pipeline,
deduplication strategy and the invariants the design protects.

## Scheduler

APScheduler inside a dedicated worker container, with its schedule persisted in
PostgreSQL so it survives restarts. Every run first takes a Postgres advisory
lock, so scaling to several workers cannot double-ingest — the loser skips its
tick rather than queueing a duplicate sweep.

No Redis, no broker. The database already provides durability and mutual
exclusion; adding a broker would be a service to run in exchange for nothing
this workload needs.

## Security and privacy

- **No secrets in the repository.** `.env` and `config/profile.yml` are
  gitignored; every push is preceded by a secret scan (`scripts/audit.sh`).
- **SSRF protection.** Provider responses supply URLs that this system then
  fetches. Every one is validated: HTTPS only, DNS resolved, private and
  link-local ranges refused.
- **Ingested HTML is sanitised** at the boundary, twice — once on the raw
  markup and again after entity decoding, so encoded markup cannot survive a
  single pass.
- **Logs redact** anything resembling a credential.
- **Non-root containers** with real healthchecks.
- **Respectful collection.** Per-host rate limiting, retries with jittered
  backoff, `Retry-After` honoured. No CAPTCHA circumvention, no authentication
  bypass, no scraping of sites that forbid it.

## Development

```bash
# API — 215 tests
cd api && pip install -e ".[dev]"
ruff check . && pytest -q

# dashboard
cd web && npm install
npm run typecheck && npm run lint && npm run build

# regenerate the TypeScript client from the live OpenAPI schema
npm run generate:types

# migrations
cd api && alembic revision --autogenerate -m "what changed" && alembic upgrade head
```

Tests cover the gates, date parsing across every ATS format, salary extraction
in German and English conventions, deduplication (including the same vacancy
from several sources), provider parsing against recorded fixtures, and the full
API surface.

CI runs all of it plus both Docker builds on every push.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Dashboard says it cannot reach the API | `docker compose ps` — is `api` healthy? |
| `migrate` exited with an error | `docker compose logs migrate`. `api` and `worker` wait for it deliberately |
| No jobs after the first boot | The first sweep takes about a minute. `docker compose logs worker` |
| A source shows as failed | Expected occasionally. It is backed off and retried later; see **Discovery** |
| Everything is `Not stated` for language | That source publishes only a short preview. The detail page links to the original |

## What it will not do

It does not submit applications. The target employers use portals with per-job
questionnaires and CAPTCHAs; LinkedIn automation risks a permanent account ban;
and these roles are read by humans, so an auto-generated application earns an
auto-generated rejection.

It will not accept legal declarations, salary agreements, relocation or visa
commitments, or background-check consent on your behalf. It prepares. You
decide.

## Roadmap

- Embedding-based skill matching, kept alongside the literal match rather than
  replacing it, so explanations survive
- Optional notifications (email, Telegram) on high-match discoveries
- Browser-assisted form pre-fill, with a human pressing submit
- More provider adapters as employers expose endpoints

## Licence

MIT. See [LICENSE](LICENSE).
