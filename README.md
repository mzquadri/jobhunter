# JobHunter

Finds AI/ML jobs worth applying to, scores them against your CV, and drafts the
cover letter — so the work left is reading and deciding, not searching.

It sweeps 27 company career systems and two job boards every hour, drops
anything you could not take, and shows what survives on a dashboard. It never
applies on your behalf.

```
┌──────────┐   ┌───────────────────────────────┐   ┌──────────┐   ┌───────────┐
│ 27 ATS   │──▶│ gates → score → warnings      │──▶│ Postgres │◀──│ dashboard │
│ 2 boards │   │ (full-time? level? reachable? │   └──────────┘   └───────────┘
└──────────┘   │  in field? still fresh?)      │          ▲
  ~3,600       └───────────────────────────────┘          │
  postings              ~40 worth reading         hourly sweep (APScheduler)
```

## Why it exists

Job boards optimise for volume. A search for "machine learning engineer" in
Germany returns thousands of results, most of which are senior roles, working
student positions, postings from three months ago, or jobs in a country you
cannot move to. Reading them is the actual work, and it is the part that stops
people applying.

This does the reading. What reaches the dashboard is full-time, at a level you
can apply to, in a place you can work, in your field, and posted recently
enough that applying is still worth the evening.

## What it does

**Reads career systems directly.** Large employers do not build their own
career sites; they rent one of about five Applicant Tracking Systems, each with
a public JSON or RSS endpoint. So there is one adapter per ATS rather than one
scraper per company, and adding a company is a single line of YAML.

| Adapter | Reaches | Notes |
| --- | --- | --- |
| `workday` | Airbus, ABB, Roche, Novartis, Thales, Philips, Logitech | Uses Workday's own posting-date facet so only recent roles come back |
| `smartrecruiters` | Bosch, Continental, Etihad | Searches rather than lists — Bosch alone has 4,800 open roles |
| `sf_rss` | BMW, MTU Aero, DLR, SAP, Swiss Re, Schaeffler, Novo Nordisk | Every SuccessFactors site answers the same RSS path |
| `greenhouse` | Helsing, Isar Aerospace, Wayve, Celonis, Parloa, KONUX, Nuro | |
| `lever` | any Lever board | |
| `arbeitnow` | Germany-wide board | 1,000 newest postings, full text included |
| `jobsch` | Switzerland | |
| `adzuna` | DE, CH, AT, NL | Optional; adds salary data. Needs a free key |

LinkedIn and Indeed are deliberately absent: both block automated access, and
LinkedIn automation risks a permanent account ban.

**Filters before it scores.** Five gates, each added because something real got
through without it:

1. **Full-time only** — drops Praktikum, Werkstudent, placements, VIE, PhD
   positions. `graduate programme` and `trainee` are deliberately kept.
2. **A level you can apply to** — drops Senior, Lead, Principal, Head of.
3. **Your field** — an ML/AI/data term has to be in the title.
4. **Somewhere you can work** — drops postings outside Europe. Without this
   gate, a perfectly matched role in Bangalore outranked every job in Munich:
   the skills matched beautifully and nothing told the scorer that the location
   made the job useless.
5. **Still fresh** — nothing older than `max_age_days` (14 by default).

**Scores what is left,** weighting freshness steeply (a posting under 48 hours
old is worth more than any other single factor), then location, then the skills
and domains the posting actually names.

**Warns instead of guessing.** Three flags never reject a posting but do cost
it points:

- `DEUTSCH` — asks for fluent German
- `EU-ONLY` — asks for EU citizenship or security clearance
- `NO-VISA` — states that sponsorship is not available

A large share of aerospace and defence postings carry `EU-ONLY`. Knowing that
in two seconds rather than two hours is most of the value here.

**Drafts the letter.** `config/letter.md` holds every paragraph you might use,
each tagged. For a given posting the tags are scored against what the job asked
for and the best three are kept, so an aerospace role and a pharma imaging role
get genuinely different letters rather than the same letter with the company
name swapped. Each strong match gets a folder with the draft, the saved job
description, a summary and a checklist.

**Tells you what broke.** A sweep that found nothing because a source stopped
answering looks exactly like a sweep where nothing was posted. Failed sources
are recorded per sweep and shown on the dashboard.

## Quick start

Requires Docker.

```bash
cp .env.example .env
cp config/profile.example.yml config/profile.yml
cp config/letter.example.md config/letter.md
# edit both config files — they are yours and are gitignored

docker compose up --build
```

- Dashboard — <http://localhost:3000>
- API docs — <http://localhost:8000/docs>

The API sweeps on startup and then hourly, so the dashboard fills itself in
within about half a minute of the first boot.

## The dashboard

Postings are strips, not cards — dense and scannable, the way air traffic
control tracks flights, because forty of them have to be readable at a glance.
Colour carries status and nothing else, using cockpit convention: green is go,
amber is caution, red is warning, matching the flags exactly. Priority is shown
with weight instead — a dream employer gets a heavy left rule, everything else
a lighter one — so hue is never spent on decoration.

The header is a live readout: counts, a fourteen-day posting histogram, and how
long ago the last sweep ran.

Keyboard: `/` search · `j` `k` move · `Enter` expand · `o` open the posting ·
`s` star · `x` hide.

Starred, hidden and application status live in the database, so a sweep never
overwrites them.

## Configuration

Everything lives in `config/profile.yml`. There is no code to change.

Adding a company is one line:

```yaml
companies:
  - { name: Siemens Energy, adapter: workday, arg: "tenant|wd3|SiteName", tier: PRIORITY }
```

Which adapter a company uses is visible in its careers URL:

| URL contains | adapter | `arg` |
| --- | --- | --- |
| `*.myworkdayjobs.com` | `workday` | `tenant\|wdN\|CareerSiteName` |
| `*.smartrecruiters.com` | `smartrecruiters` | company slug |
| `jobs.<company>.com` | `sf_rss` | that hostname |
| `boards.greenhouse.io/<slug>` | `greenhouse` | the slug |
| `jobs.lever.co/<slug>` | `lever` | the slug |

Worth knowing:

| Setting | Does |
| --- | --- |
| `search.max_age_days` | Hides anything older. Default 14 |
| `search.min_score` | Below this a posting is noise. Default 20 |
| `search.draft_min_score` | Only stronger matches get a cover-letter draft |
| `locations.tiers` | Points per city. Munich 22, Germany 18, Switzerland 16 |
| `locations.exclude` | Hard reject. India, US, China and so on |
| `scoring.freshness` | `[[days, points], …]`. Steep by design |
| `flags` | Warning rules and what each costs |

Some career sites — Ferrari, Lamborghini, Audi, Porsche, Volkswagen,
Mercedes-Benz, Emirates, Siemens, ZEISS — render their listings with
JavaScript and publish no open endpoint. Nothing can read them automatically,
so they sit in a `watchlist` the dashboard renders as one-click links rather
than pretending otherwise.

## Architecture

```
api/                     FastAPI + SQLAlchemy 2.0 + APScheduler
  app/collector/         the part that talks to the outside world
    sources.py           one adapter per ATS
    matcher.py           gates, scoring, warning flags
    drafter.py           tag-matched cover letters
    pipeline.py          one sweep, start to finish
  app/routers/           /api/jobs, /api/stats, /api/sweeps
  app/models.py          jobs, sweeps, source problems
  tests/                 57 tests over the gates, dates and drafting
web/                     Next.js 15 + React 19 + Tailwind 4, TypeScript
config/                  your profile and letter (gitignored)
data/drafts/             generated application folders (gitignored)
```

A posting is keyed by a fingerprint of company plus normalised title, not by
its URL — most ATS platforms mint a fresh URL whenever a posting is edited, and
without a stable key the same job is announced as new every time someone fixes
a typo in it.

The scheduler runs inside the API process. For one user and a sweep that takes
about twenty seconds, a queue and a broker would be more moving parts than the
job deserves.

## Development

```bash
# API
cd api && pip install -e ".[dev]"
ruff check . && pytest -q

# dashboard
cd web && npm install
npm run typecheck && npm run lint && npm run build
```

CI runs all of the above plus both Docker builds on every push.

## What it will not do

It does not submit applications. The target employers use portals with
per-job questionnaires and CAPTCHAs; LinkedIn automation risks a permanent
account ban; and these roles are read by humans, so an auto-generated
application earns an auto-generated rejection. The value here is knowing
within the hour and having the letter 90% written — not pressing submit.

## Licence

MIT. See [LICENSE](LICENSE).
