"""Workday.

Target format: ``tenant|wdN|CareerSiteName``, for example ``ag|wd3|Airbus``.

Two things make this work on employers the size of Airbus, which has around
1,800 open roles at any time:

  * search for the candidate's field rather than listing everything, or the
    first page is maintenance planners and accountants;
  * filter by posting date, so relevance ranking does not bury fresh roles.

The second is where this gets interesting. Workday exposes a ``startDate``
facet whose values are per-tenant GUIDs, and **whether the facet exists at all
is per-tenant configuration**. Airbus offers it; Roche, ABB, Thales, Novartis,
Philips, Logitech and Accenture do not, and no request variation makes it
appear -- that was verified directly against all eight tenants.

So the provider adapts: it uses the facet where offered, and where it is not,
it pages deeper and filters on the ``postedOn`` string that every posting
carries anyway. Which path was taken is reported as a capability, because a
permanent difference in a tenant's configuration is not an error to log every
hour.
"""

from __future__ import annotations

from app.dedup import Sighting
from app.enrich.text import clean_html
from app.providers.base import FetchContext, Http, Provider, ProviderResult
from app.providers.dates import from_relative

# Facet buckets worth asking for. Descriptors are stable across tenants even
# though the ids behind them are not.
RECENT_BUCKETS = frozenset({
    "1 day", "today", "1 week", "last week", "2-4 weeks", "2 - 4 weeks",
    "last 30 days", "30 days",
})

PAGE_SIZE = 20
PAGES_WITH_FACET = 2        # the facet already narrows the result
PAGES_WITHOUT_FACET = 5     # dig deeper when filtering has to happen locally


class WorkdayProvider(Provider):
    name = "workday"

    def fetch(self, target: str, company: str, tier: str,
              ctx: FetchContext) -> ProviderResult:
        try:
            tenant, wd, site = target.split("|")
        except ValueError:
            return ProviderResult(error=f"malformed Workday target {target!r}; "
                                        "expected 'tenant|wdN|SiteName'")

        http = Http(ctx)
        base = f"https://{tenant}.{wd}.myworkdayjobs.com"
        api = f"{base}/wday/cxs/{tenant}/{site}/jobs"

        facet_ids = self._posting_date_facet(http, api, ctx)
        applied = {"startDate": facet_ids} if facet_ids else {}
        pages = PAGES_WITH_FACET if facet_ids else PAGES_WITHOUT_FACET

        sightings: list[Sighting] = []
        seen: set[str] = set()
        dropped_stale = 0

        for query in ctx.queries:
            for page in range(pages):
                data = http.post_json(api, {
                    "appliedFacets": applied,
                    "limit": PAGE_SIZE,
                    "offset": page * PAGE_SIZE,
                    "searchText": query,
                })
                postings = data.get("jobPostings") or []
                if not postings:
                    break

                for posting in postings:
                    path = posting.get("externalPath") or ""
                    if not path or path in seen:
                        continue
                    seen.add(path)

                    posted = from_relative(posting.get("postedOn"))
                    if not self.within_age(posted, ctx.max_age_days):
                        dropped_stale += 1
                        continue

                    url = f"{base}/en-US/{site}{path}"
                    if not self.safe(url):
                        continue

                    requisition, location = self._bullets(posting, path)
                    sightings.append(Sighting(
                        provider=self.name,
                        company=company,
                        title=posting.get("title") or "",
                        url=url,
                        location=location,
                        # The requisition id, not the path. Two things depend
                        # on this: Airbus renames postings without changing
                        # the id (so the path alone would look like a new
                        # job), and Accenture omits locationsText entirely
                        # (so without a distinct id, twenty separate
                        # requisitions for the same title collapse into one).
                        external_id=requisition or path,
                        posted=posted,
                        tier=tier,
                    ))

                if (page + 1) * PAGE_SIZE >= (data.get("total") or 0):
                    break

        return ProviderResult(
            sightings=sightings,
            requests_made=http.requests_made,
            capabilities={
                "date_filter": "server" if facet_ids else "client",
                "pages_per_query": pages,
                "stale_dropped": dropped_stale,
            },
        )

    @staticmethod
    def _bullets(posting: dict, path: str) -> tuple[str, str]:
        """Requisition id and location from ``bulletFields``.

        Workday's list response carries ``bulletFields`` as
        ``[requisition_id, location]``. Several tenants -- Accenture among
        them -- omit ``locationsText`` entirely but still populate this, so it
        is the more reliable source for both. The URL path is the last resort
        for location, since it encodes the city as a slug.
        """
        bullets = [str(b).strip() for b in (posting.get("bulletFields") or []) if b]
        requisition = bullets[0] if bullets else ""
        location = bullets[1] if len(bullets) > 1 else ""

        if not location:
            location = posting.get("locationsText") or ""
        if not location and path.startswith("/job/"):
            # "/job/Bengaluru-BDC7C/Some-Title_REQ123" -> "Bengaluru BDC7C"
            parts = path.split("/")
            if len(parts) > 2:
                location = parts[2].replace("-", " ").strip()

        # "Location Negotiable" and similar are not places; treating them as
        # one would defeat the geography gate rather than inform it.
        if location.lower() in {"location negotiable", "multiple locations", "various"}:
            location = ""
        return requisition, location

    def _posting_date_facet(self, http: Http, api: str, ctx: FetchContext) -> list[str]:
        """Facet value ids for recent postings, or [] when the tenant has none."""
        try:
            data = http.post_json(api, {
                "appliedFacets": {}, "limit": 1, "offset": 0,
                "searchText": ctx.queries[0] if ctx.queries else "",
            })
        except Exception:
            # Not fatal: the caller falls back to client-side filtering.
            return []

        for facet in data.get("facets") or []:
            if facet.get("facetParameter") != "startDate":
                continue
            return [
                value["id"] for value in facet.get("values") or []
                if value.get("id")
                and str(value.get("descriptor", "")).strip().lower() in RECENT_BUCKETS
            ]
        return []

    def fetch_detail(self, sighting: Sighting, ctx: FetchContext) -> str:
        """Full text lives behind the CXS path mirroring the public URL.

        The path is recovered from the URL rather than from ``external_id``,
        which now holds the requisition id.
        """
        host, marker, rest = sighting.url.partition("/en-US/")
        if not marker or "/" not in rest:
            return ""
        site, _, path = rest.partition("/")
        tenant = host.split("//")[-1].split(".")[0]
        if not (site and tenant and path):
            return ""

        api = f"{host}/wday/cxs/{tenant}/{site}/{path}"
        if not self.safe(api):
            return ""
        info = Http(ctx).get_json(api).get("jobPostingInfo") or {}
        return clean_html(info.get("jobDescription") or "")[:40_000]
