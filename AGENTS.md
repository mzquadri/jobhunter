# CareerOS engineering rules

- Runtime and verification are Docker-first. Host Python is optional tooling.
- Preserve the discovery invariant: a skipped or incomplete source cannot close
  jobs; closure requires a successful, complete snapshot from the owning source.
- Prefer official employer or ATS sources over boards. Never claim automation
  without a repeatable public endpoint that has been tested against live data.
- Keep source states honest: manual, live, idle, degraded, rate-limited, and
  broken describe observed source behavior, not coverage goals.
- Keep field relevance separate from candidate match and preserve explainable
  score evidence. A plausible 60% opportunity remains visible.
- Do not add credentials, personal profile files, application notes, cookies,
  databases, or private screenshots to the repository.
- Run API tests, Ruff, frontend typecheck/lint/build, OpenAPI checks, privacy
  audit, and Docker health checks before release work.
- Work on feature branches. Never push directly to `main`, merge pull requests,
  or submit applications automatically.
