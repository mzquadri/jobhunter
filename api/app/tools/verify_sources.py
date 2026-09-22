"""Probe candidate employer sources and report which ones actually work.

The temptation when expanding coverage is to guess: most companies on
Greenhouse use their own name as the board token, so writing three hundred
guesses into the config produces an impressive-looking employer list. Roughly
half of those guesses are wrong, and a wrong one is not neutral — it is an
employer the dashboard claims to monitor and never fetches a single job from.
"§34: do not label an employer 'monitored' if nothing actually retrieves its
jobs."

So candidates go through here first. Each one is fetched once, against the real
endpoint, and classified by what came back:

  ``live``         postings returned
  ``empty``        the board exists and answered, but has nothing open right now
  ``not-found``    no such tenant, board or account — the guess was wrong
  ``blocked``      the source refused us (403/429); not a wrong guess, but not
                   usable either
  ``error``        anything else, with the reason kept

Only ``live`` and ``empty`` may become automated entries in the registry:
``empty`` is a real board that happens to have nothing open today, which is a
completely normal state for a company with forty employees.

Usage::

    python -m app.tools.verify_sources candidates.json --out verified.json

It is a developer tool, run when the registry changes, not part of a scan.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from app.providers import REGISTRY, FetchContext, RateLimited
from app.providers.base import RateLimit
from app.settings import get_settings

#: Politeness. These are other people's servers and we are asking a favour.
CONCURRENCY = 6
TIMEOUT = 25.0


@dataclass
class Probe:
    name: str
    adapter: str
    arg: str
    status: str = "error"
    postings: int = 0
    detail: str = ""

    @property
    def usable(self) -> bool:
        """Whether this may be written into the registry as automated."""
        return self.status in ("live", "empty")


def _classify_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, RateLimited):
        return "blocked", "rate limited"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403, 429):
            return "blocked", f"HTTP {code}"
        if code in (404, 410):
            return "not-found", f"HTTP {code}"
        return "error", f"HTTP {code}"
    if isinstance(exc, httpx.TimeoutException):
        return "error", "timed out"
    text = str(exc)
    # Providers raise plain ValueErrors for a shape they cannot read; a board
    # that does not exist usually shows up as a 404 handled above, but some
    # return a 200 with an error document.
    if "not found" in text.lower() or "404" in text:
        return "not-found", text[:120]
    return "error", text[:120]


def probe(client: httpx.Client, name: str, adapter: str, arg: str) -> Probe:
    result = Probe(name=name, adapter=adapter, arg=arg)

    provider = REGISTRY.get(adapter)
    if provider is None:
        result.status = "error"
        result.detail = f"no adapter named {adapter!r}"
        return result

    # A wide window on purpose: this asks "does the source answer", not "is
    # anything fresh". A board with nothing posted this fortnight is still a
    # working board.
    ctx = FetchContext(
        queries=["machine learning"],
        max_age_days=365,
        settings=get_settings(),
        client=client,
        limiter=RateLimit(),
    )
    try:
        outcome = provider.fetch(arg, name, "normal", ctx)
    except Exception as exc:  # noqa: BLE001 — every failure mode is reported
        result.status, result.detail = _classify_error(exc)
        return result

    if outcome.error:
        result.status, result.detail = "error", outcome.error[:160]
        return result

    result.postings = len(outcome.sightings)
    dropped = int(outcome.capabilities.get("stale_dropped") or 0)
    if result.postings or dropped:
        result.status = "live"
    else:
        result.status = "empty"
        result.detail = "answered, nothing currently open"
    return result


def run(candidates: list[dict]) -> list[Probe]:
    results: list[Probe] = []
    with httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "CareerOS/1.0 (+https://github.com/mzquadri/jobhunter)"},
    ) as client, ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [
            pool.submit(probe, client, c["name"], c["adapter"], c["arg"])
            for c in candidates
        ]
        for future in futures:
            outcome = future.result()
            results.append(outcome)
            mark = "ok " if outcome.usable else "   "
            print(
                f"{mark} {outcome.status:10} {outcome.adapter:16} "
                f"{outcome.arg[:44]:46} {outcome.name}"
                + (f"  ({outcome.postings} postings)" if outcome.postings else "")
                + (f"  {outcome.detail}" if outcome.detail and not outcome.postings else ""),
                file=sys.stderr,
            )
    return results


def summarise(results: list[Probe]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        counts[item.status] = counts.get(item.status, 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path,
                        help="JSON list of {name, adapter, arg}")
    parser.add_argument("--out", type=Path, help="where to write the full results")
    args = parser.parse_args()

    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    results = run(candidates)

    counts = summarise(results)
    print("\n" + "  ".join(f"{k}={v}" for k, v in counts.items()), file=sys.stderr)
    usable = [r for r in results if r.usable]
    print(f"{len(usable)}/{len(results)} usable as automated sources", file=sys.stderr)

    payload = [asdict(r) for r in results]
    if args.out:
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        json.dump(payload, sys.stdout, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
