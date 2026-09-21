"""Company-independent job boards.

These are how employers outside the configured watchlist get discovered at all
— §4 asks for relevant companies to be found automatically, not only searched
for by name.

LinkedIn and Indeed are deliberately absent. Both block automated access, and
LinkedIn automation risks a permanent account ban. §8 asks for sources to be
used "where legally and technically appropriate"; these two are neither.
"""

from __future__ import annotations

from app.dedup import Sighting
from app.enrich.text import clean_html
from app.providers.base import FetchContext, Http, Provider, ProviderResult
from app.providers.dates import from_any


class ArbeitnowProvider(Provider):
    """A free, public German job-board API. Newest first, full text included."""

    name = "arbeitnow"
    employer_scoped = False
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self, target, company, tier, ctx: FetchContext) -> ProviderResult:
        http = Http(ctx)
        pages = int(target) if str(target).isdigit() else 4

        sightings, stale = [], 0
        for page in range(1, pages + 1):
            params = {"page": page} if page > 1 else None
            data = http.get_json(self.URL, params=params)
            rows = data.get("data") or []
            if not rows:
                break

            for job in rows:
                posted = from_any(job.get("created_at"))
                if not self.within_age(posted, ctx.max_age_days):
                    stale += 1
                    continue
                url = job.get("url") or ""
                if not self.safe(url):
                    continue
                sightings.append(Sighting(
                    provider=self.name,
                    company=job.get("company_name") or "Unknown",
                    title=job.get("title") or "",
                    url=url,
                    location=job.get("location") or "",
                    external_id=job.get("slug") or "",
                    posted=posted,
                    description=clean_html(job.get("description")),
                    tags=" ".join(job.get("tags") or [])
                         + " " + " ".join(job.get("job_types") or []),
                    tier="normal",
                ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"date_filter": "client", "stale_dropped": stale,
                                            "pages": pages})


class JobsChProvider(Provider):
    """jobs.ch public search — the main Swiss board.

    ``rows`` is capped at 20 by the API, which answers 422 with an explicit
    "20 is the upper limit" when asked for more. Volume therefore comes from
    paging, not from a larger page.
    """

    name = "jobsch"
    employer_scoped = False
    URL = "https://www.jobs.ch/api/v1/public/search"
    PAGE_SIZE = 20          # the documented maximum
    MAX_PAGES = 3

    def fetch(self, target, company, tier, ctx: FetchContext) -> ProviderResult:
        http = Http(ctx)
        sightings: list[Sighting] = []
        seen: set[str] = set()
        stale = 0

        for query in ctx.queries:
            for page in range(1, self.MAX_PAGES + 1):
                data = http.get_json(
                    self.URL,
                    params={"query": query, "rows": self.PAGE_SIZE, "page": page},
                )
                documents = data.get("documents") or []
                if not documents:
                    break
                stale += self._collect(documents, sightings, seen, ctx)
                if page >= int(data.get("num_pages") or 1):
                    break

        return ProviderResult(
            sightings=sightings, requests_made=http.requests_made,
            capabilities={"date_filter": "client", "page_size": self.PAGE_SIZE,
                          "stale_dropped": stale},
        )

    def _collect(self, documents: list, sightings: list[Sighting], seen: set[str],
                 ctx: FetchContext) -> int:
        """Append the usable postings from one page. Returns how many were stale."""
        stale = 0
        for job in documents:
            job_id = str(job.get("job_id") or "")
            if job_id and job_id in seen:
                continue
            seen.add(job_id)

            posted = from_any(job.get("publication_date"))
            if not self.within_age(posted, ctx.max_age_days):
                stale += 1
                continue

            # The feed exposes detail_en / detail_de / detail_fr, not "detail".
            links = job.get("_links") or {}
            href = ""
            for key in ("detail_en", "detail_de", "detail_fr"):
                candidate = (links.get(key) or {}).get("href")
                if candidate:
                    href = str(candidate)
                    break
            if href.startswith("/"):
                href = "https://www.jobs.ch" + href
            url = href or f"https://www.jobs.ch/en/vacancies/detail/{job_id}/"
            if not self.safe(url):
                continue

            # `regions` is frequently a list of nulls; `place` carries the town.
            regions = ", ".join(
                r.get("name", "") for r in (job.get("regions") or [])
                if isinstance(r, dict) and r.get("name")
            )
            place = str(job.get("place") or "").strip()
            location = ", ".join(filter(None, (place, regions))) or "Switzerland"

            sightings.append(Sighting(
                provider=self.name,
                company=job.get("company_name") or "Unknown",
                title=job.get("title") or "",
                url=url,
                location=location,
                external_id=job_id,
                posted=posted,
                # Only a short preview is published; the full advertisement
                # lives on the employer's own page, which is not fetched here.
                description=clean_html(job.get("preview")),
                tier="normal",
                structured={"language_skills": job.get("language_skills") or []},
            ))
        return stale


class AdzunaProvider(Provider):
    """Optional. Adds salary data across DE, CH, AT and NL.

    Needs a free key. Absent one, the provider reports itself as skipped
    rather than failing -- an unconfigured optional integration is not an
    error, and §27/§35 both ask for integrations to stay optional.
    """

    name = "adzuna"
    employer_scoped = False

    def fetch(self, target, company, tier, ctx: FetchContext) -> ProviderResult:
        settings = ctx.settings
        if not (settings.adzuna_app_id and settings.adzuna_app_key):
            return ProviderResult(capabilities={"configured": False})

        http = Http(ctx)
        countries = [c.strip() for c in str(target).split(",") if c.strip()] or ["de"]
        sightings = []

        for country in countries:
            for query in ctx.queries[:3]:
                data = http.get_json(
                    f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                    params={
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_app_key,
                        "results_per_page": 50,
                        "what": query,
                        "sort_by": "date",
                        "max_days_old": ctx.max_age_days,
                    },
                )
                for job in data.get("results") or []:
                    url = job.get("redirect_url") or ""
                    if not self.safe(url):
                        continue
                    # Adzuna's own salary figures are frequently its estimate
                    # rather than the employer's. They are passed as a hint for
                    # the parser to confirm against the description, never
                    # promoted straight to an explicit salary.
                    hint = ""
                    if job.get("salary_min") and job.get("salary_is_predicted") != "1":
                        low = job["salary_min"]
                        high = job.get("salary_max") or low
                        hint = f"{low:.0f}-{high:.0f} EUR per year"
                    sightings.append(Sighting(
                        provider=self.name,
                        company=(job.get("company") or {}).get("display_name") or "Unknown",
                        title=job.get("title") or "",
                        url=url,
                        location=(job.get("location") or {}).get("display_name") or country.upper(),
                        external_id=str(job.get("id") or ""),
                        posted=from_any(job.get("created")),
                        description=clean_html(job.get("description")),
                        tier="normal",
                        salary_hint=hint,
                    ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"configured": True, "date_filter": "server"})
