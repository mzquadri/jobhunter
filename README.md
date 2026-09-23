# CareerOS

Finds the AI/ML jobs worth applying to, explains why each one scored what it
did, tracks the ones you pursue, and drafts the cover letter â€” so the work left
is reading and deciding, not searching.

It checks official employer and ATS sources on an adaptive cadence, drops
clearly unavailable or unrelated roles, and shows what survives. Employers
without a safe structured source remain visible as a manual watchlist. It never
applies on your behalf.

```
~5,000 postings read  â†’  gates and scoring  â†’  ~65 worth applying to
```

**It is built around 60%, not 90%.** A recent graduate who meets roughly
60% of what a posting describes should be applying to it â€” a job advert is an
employer's wish list, not a minimum. So a missing Kubernetes, an ambitious
"3+ years" and a preferred language lower the score and are named on the job;
they do not delete it.

A complete application, not a set of endpoints: a setup wizard on first run, a
command centre, a job explorer, a drag-and-drop application pipeline, employer
management, automation controls, analytics and a settings screen. Nothing in
normal use asks you to open a terminal, Swagger or a database client.

<!-- Screenshots: docs/screenshots/{overview,jobs,pipeline,analytics}.png -->

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

Every automated employer in the shipped config was **probed against its real
endpoint before being written down**. Of 279 plausible-looking candidates, 102
did not exist â€” guessing produces a config where two rows in five claim to be
monitored and fetch nothing. `python -m app.tools.verify_sources` is the tool
that checked them, and it is in the repository so the next expansion can be
checked the same way.

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

**Rejects little, ranks hard.** Only four things are thrown away outright, and
each answers "this opportunity is unavailable or is not this profession",
never "this candidate is imperfect":

1. **Not full-time** â€” Praktikum, Werkstudent, placements, VIE and PhD
   positions. `graduate programme` and `trainee` are deliberately kept.
2. **Not this field** â€” judged from the title *and* the description, graded
   certain / likely / possible. "Perception Engineer" and "Decision Scientist"
   survive on description evidence and pay a few points for the uncertainty.
   A title-only rule discarded them every scan.
3. **Somewhere excluded** â€” a posting clearly outside Europe.
4. **Too old** â€” nothing beyond `max_age_days`.

Everything else is a penalty, because a penalty is visible and arguable while
a filter is silent. Seniority, a language you do not have, a location outside
your tiers, a missing tool: all sink a role rather than hiding it.

Two of those exist because a weighted average could not express them. A
mandatory C1-German role and a role in Vietnam both scored in the high
seventies on technical merit alone; language is 13% of the sum and location
20%, which is not enough to say "you cannot take this job". Both now take an
explicit penalty on top of their sub-score.

**Credits adjacent experience.** A TensorFlow posting is not closed to someone
with two years of PyTorch. Requirements are grouped into families with a stated
transfer factor, and every transfer is spelled out â€” *"asks for TensorFlow;
your PyTorch experience transfers"* â€” rather than moving a number invisibly.

**Explains every score.** Seven sub-scores, the reasons behind them, and the
gaps against your profile â€” all visible, none hidden behind a tooltip:

```
Overall 78          Technical 86   Location 91   Freshness 100
                    Experience 95  Language 95   Domain 63    Education 85

+ Matches your genai experience: llm, rag, retrieval-augmented
+ Spans 5 of your skill areas
+ Advertised at graduate or junior level
âˆ’ Asks for azure, which is not on your profile
```

**Classifies the language requirement** into nine levels, from *English only*
through *German C1+*, each with the sentence it was read from. A large share of
German postings are effectively closed to a non-fluent speaker, and knowing
which in two seconds rather than two hours is most of the value here.

**Never invents a salary.** A figure appears only when the employer printed
one. Anything annualised or converted is marked `â‰ˆ`, so a derived number is
never mistaken for the employer's own. There is no market-data estimator,
because there is no source for one â€” and a plausible guess is worse than an
empty field, since it looks like information.

**Tells you what broke.** A run that found nothing because six sources failed
looks identical to a run where nothing was posted, unless the difference is
recorded. Every source's outcome is stored per run and shown on the dashboard.

## v3 source and review rules

CareerOS prefers official employer and ATS sources over boards. The registry currently tracks 372 employers: 117 have verified automated sources and 255 remain explicit manual watchlist entries because no safe, repeatable structured endpoint has been verified. A manual employer is never counted as monitored automation.

Providers use latest-first requests and posting-date cutoffs where supported. ETags, Last-Modified, and 304 responses are recorded as successful unchanged checks; a 304 is not a complete snapshot and cannot close jobs. Official provenance wins deduplication while board provenance is retained.

Field relevance is stored separately from candidate match, with evidence and a requirement matrix for matched, transferable, partial, missing, and blocking requirements. Saved searches and review mode support a focused pass through new roles with J/K navigation, save, ignore, prepare, and official-posting actions.
## Quick start

Requires Docker.

```bash
git clone https://github.com/mzquadri/jobhunter
cd jobhunter

cp .env.example .env
cp config/profile.example.yml config/profile.yml
cp config/letter.example.md   config/letter.md

docker compose up -d --build
```

Then open <http://localhost:3000>. The setup wizard runs on first visit and
fills everything in from the defaults, so you can press Next through it and
change your mind later in Settings. The copied config files are the seed for
that first boot â€” they are yours, and both are gitignored.

The worker scans on startup and then hourly, so the first roles appear within
about a minute.

| | |
| --- | --- |
| The application | <http://localhost:3000> |
| API | <http://localhost:8000> |
| API reference | <http://localhost:8000/docs> â€” for extending it, not for using it |

## The application

| Screen | For |
| --- | --- |
| **Overview** | What changed since you last looked: high-priority roles, the larger "worth applying" list, career signals, shortlist radar, where the market is active, and coverage |
| **Jobs** | The explorer. Opens on *Recommended* â€” match, plus nudges for freshness, employer priority and a language you have. Grouped one-click views, and a detail panel you can walk with `j`/`k` without losing your place |
| **Applications** | A pipeline board. Drag a role between stages, or move it from the menu on the card |
| **Companies** | Who is watched, what state each source is actually in, and who publishes no feed at all |
| **Automation** | What the scanner is doing and what it did â€” schedule, run history, per-source health |
| **Analytics** | What the market looks like for your profile, including how much of it stated a salary |
| **Settings** | Everything the scanner uses, in seven sections, each saving on its own |
| **Set up** | A six-step wizard on first run. Everything is pre-filled; you can press Next through it |

`âŒ˜K` / `Ctrl+K` opens a command palette that searches jobs against the API,
jumps to any screen, starts a scan, or switches the theme. `/` focuses search.

Keyboard, light and dark, empty states that say what to do next, and error
states that say what went wrong â€” not a spinner that never resolves.

## Application tracking

Thirteen statuses from *New* to *Offer*, with a recorded history of every
transition, plus notes, contact person, follow-up date and salary discussion.
Eight of those statuses are the columns of the pipeline board.

Moving a role to *Applied* fills in the date you applied and schedules a
follow-up, so the reminder is real rather than something you have to remember
to set. Both are yours to change, and the delay is a setting.

These fields are yours. **A discovery run never writes them**, so re-running is
always safe â€” a sweep can refresh a score while your notes stay untouched. That
invariant is asserted directly in the test suite.

## Configuration

**Settings live in the database and are edited in the Settings screen.** They
take effect on the next scan â€” there is no file to edit and no restart.

The employer registry ships with **321 employers**: 117 with a verified feed
that is read automatically, and the rest listed with a link because they
publish nothing readable. Those are two different numbers and the interface
prints them as two different numbers â€” an employer nothing fetches from is not
"monitored". Job boards add to this on their own: a relevant role from a
company nobody configured creates that company, so targeted coverage and open
discovery work together.

`config/profile.yml` is the *seed*: it is read once, on the first boot of an
empty database, to populate those settings. Editing it afterwards changes
nothing, because the database is the source of truth from that point on.
*Restore defaults* in Settings re-reads it.

The employer list is the one part still expressed there, because adding an
employer is a line of YAML rather than a form:

```yaml
companies:
  - { name: Siemens Energy, adapter: workday, arg: "tenant|wd3|SiteName", tier: high }
```

Each setting, under its name in the Settings screen:

| Setting | Does |
| --- | --- |
| `search.max_age_days` | Hides anything older. Default 14 |
| `search.min_score` | Below this a posting is noise |
| `search.draft_min_score` | Only stronger matches get a cover-letter draft |
| `locations.tiers` | Points per city â€” Munich 24, Germany 20, Switzerland 17 |
| `locations.exclude` | Hard reject |
| `scoring.weights` | How much each sub-score contributes |
| `scoring.freshness_curve` | `[[days, score], â€¦]`. Steep by design |
| `flags` | Warning rules and what each costs |
| `saved_searches` | Seeded on first boot; yours are never overwritten |

`config/profile.yml` and `config/letter.md` are gitignored, and so is the
database volume. The committed `*.example.*` files carry placeholders only â€”
your name, contact details, notes and application history never reach the
repository.

## How matching works

Each sub-score is 0â€“100, combined by the weights in your profile, then adjusted:

```
score = Î£(sub_score Ã— weight)
      + tier_bonus         (a shortlisted employer lifts a good match)
      âˆ’ seniority_penalty  (senior 30, lead 45, executive 60)
      âˆ’ language_penalty   (German B2 8, C1+ 22, native 30)
      âˆ’ location_penalty   (outside your tiers 26, or 10 if remote)
      âˆ’ relevance_discount (8 when the field was read from the description)
      âˆ’ flag_penalties     (EU-only 20, no-sponsorship 20, German 10)
```

The four penalties are not decoration. Language is 13% of the weighted sum and
location 20%, and neither share is enough to express *you cannot take this
job* â€” a role demanding negotiation-level German and a role in Vietnam both
reached the high seventies on technical merit alone before these existed.

The bands the interface uses:

| Score | | |
| --- | --- | --- |
| 90â€“100 | Exceptional match | |
| 80â€“89 | Strong match | own list at the top of the dashboard |
| 70â€“79 | Good match | |
| **60â€“69** | **Worth applying** | **the band the product is built around** |
| 50â€“59 | Stretch | visible, not recommended |
| under 50 | Low relevance | stored, not shown by default |

Three thresholds, deliberately different numbers. `min_score` (25) decides what
is **stored** â€” every scan re-scores, so a 43 today can be a 67 once you add a
skill, and discarding it would need the whole market re-fetched to get it back.
`recommend_min_score` (60) decides what is **shown**. `high_match_score` (80)
decides what is shouted about.

Nothing is random and nothing is a constant buried in code. The reasons shown
in the interface are generated by the same calculation that produced the
number â€” if it says "Strong PyTorch match", the technical sub-score rose
because the word PyTorch is in the posting.

See [docs/architecture.md](docs/architecture.md) for the full pipeline,
deduplication strategy and the invariants the design protects.

## Scan cadence

Shortlisted and priority employers are asked every run. Everything else is
asked every four hours, and a broken source is backed off.

Not a micro-optimisation: 117 sources every hour is about 2,800 requests a day
to other people's servers to re-read a market that moves in days. An employer
that has never been checked is always due, so adding one shows results on the
next run rather than after its tier elapses.

One consequence is worth stating because getting it wrong is silent. A run may
only close vacancies belonging to sources it actually asked â€” otherwise every
employer skipped by the cadence has all of their still-open roles marked closed
and reopened four hours later.

## Scheduler

APScheduler inside a dedicated worker container, with its schedule persisted in
PostgreSQL so it survives restarts. Every run first takes a Postgres advisory
lock, so scaling to several workers cannot double-ingest â€” the loser skips its
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
- **Ingested HTML is sanitised** at the boundary, twice â€” once on the raw
  markup and again after entity decoding, so encoded markup cannot survive a
  single pass.
- **Logs redact** anything resembling a credential.
- **Non-root containers** with real healthchecks.
- **Respectful collection.** Per-host rate limiting, retries with jittered
  backoff, `Retry-After` honoured. No CAPTCHA circumvention, no authentication
  bypass, no scraping of sites that forbid it.

## Development

```bash
# API â€” 328 tests
cd api && pip install -e ".[dev]"
ruff check . && pytest -q

# dashboard
cd web && npm install
npm run typecheck && npm run lint && npm run build

# regenerate the TypeScript client from the live OpenAPI schema
# (the stack has to be running â€” it reads http://localhost:8000/openapi.json)
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
| "CareerOS cannot reach its backend" | `docker compose ps` â€” is `api` healthy? |
| `migrate` exited with an error | `docker compose logs migrate`. `api` and `worker` wait for it deliberately |
| No roles after the first boot | The first scan takes about a minute. **Automation** shows it running; `docker compose logs worker` has the detail |
| A source shows as failed | Expected occasionally. It is backed off and retried later; see **Automation â†’ Sources** |
| A setting did not seem to apply | Settings apply from the *next* scan. **Automation â†’ Scan now** makes that immediate |
| Everything is `Not stated` for language | That source publishes only a short preview. The job panel links to the original |
| The setup wizard keeps appearing | Setup is only marked complete when you finish it. Press **Open CareerOS** on the last step |

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

