"""The JSON and RSS applicant-tracking systems.

Seven providers in one module because they are each a dozen lines of mapping
against a documented endpoint. Splitting them into seven files would add
imports without adding clarity; Workday earns its own file because its
per-tenant behaviour genuinely is complicated.

Every endpoint below was verified against a live company on 21 Sep 2026.
"""

from __future__ import annotations

import re

from app.dedup import Sighting
from app.enrich.text import clean_html
from app.providers.base import Http, Provider, ProviderResult
from app.providers.dates import from_any


class SmartRecruitersProvider(Provider):
    """Target: the company slug, e.g. ``BoschGroup``.

    Bosch alone posts around 4,800 roles, so this searches rather than lists.
    """

    name = "smartrecruiters"
    BASE = "https://api.smartrecruiters.com/v1/companies"

    def fetch(self, target, company, tier, ctx) -> ProviderResult:
        http = Http(ctx)
        sightings: list[Sighting] = []
        seen: set[str] = set()
        stale = 0

        for query in ctx.queries:
            data = http.get_json(f"{self.BASE}/{target}/postings",
                                 params={"limit": 100, "q": query})
            for posting in data.get("content") or []:
                pid = posting.get("id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)

                posted = from_any(posting.get("releasedDate") or posting.get("createdOn"))
                if not self.within_age(posted, ctx.max_age_days):
                    stale += 1
                    continue

                location = posting.get("location") or {}
                where = ", ".join(filter(None, (
                    location.get("city"), location.get("region"), location.get("country")
                )))
                url = f"https://jobs.smartrecruiters.com/{target}/{pid}"
                if not self.safe(url):
                    continue

                sightings.append(Sighting(
                    provider=self.name, company=company, title=posting.get("name") or "",
                    url=url, location=where, external_id=str(pid), posted=posted, tier=tier,
                ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"date_filter": "client", "stale_dropped": stale})

    def fetch_detail(self, sighting, ctx) -> str:
        # The posting id is enough to rebuild the detail endpoint, and the
        # company slug is the path segment before it in the public URL.
        match = re.search(r"jobs\.smartrecruiters\.com/([^/]+)/", sighting.url)
        if not (match and sighting.external_id):
            return ""
        url = f"{self.BASE}/{match.group(1)}/postings/{sighting.external_id}"
        if not self.safe(url):
            return ""
        ad = Http(ctx).get_json(url).get("jobAd") or {}
        parts = [
            clean_html(section.get("text") or "")
            for section in (ad.get("sections") or {}).values()
            if isinstance(section, dict)
        ]
        return "\n\n".join(p for p in parts if p)[:40_000]


class SuccessFactorsProvider(Provider):
    """Target: the career-site hostname, e.g. ``jobs.bmwgroup.com``.

    Every SAP SuccessFactors career site answers the same RSS path, and it
    returns only the newest postings -- which for a freshness-driven monitor is
    exactly right, so there is nothing to filter server-side.
    """

    name = "successfactors"
    PATH = "/services/rss/job/?locale=en_US"

    def fetch(self, target, company, tier, ctx) -> ProviderResult:
        http = Http(ctx)
        xml = http.get_text(f"https://{target}{self.PATH}")

        sightings: list[Sighting] = []
        stale = 0
        for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
            def tag(name: str, blk: str = block) -> str:
                m = re.search(rf"<{name}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", blk, re.S)
                return (m.group(1) or "").strip() if m else ""

            title, link = tag("title"), tag("link")
            if not (title and link) or not self.safe(link):
                continue

            posted = from_any(tag("pubDate"))
            if not self.within_age(posted, ctx.max_age_days):
                stale += 1
                continue

            sightings.append(Sighting(
                provider=self.name, company=company, title=clean_html(title),
                url=link, location=tag("location"), external_id=link.rsplit("/", 1)[-1],
                posted=posted, description=clean_html(tag("description")), tier=tier,
            ))

        return ProviderResult(
            sightings=sightings, requests_made=http.requests_made,
            capabilities={"date_filter": "feed-is-newest-first", "stale_dropped": stale},
        )


class GreenhouseProvider(Provider):
    """Target: the board slug, e.g. ``helsing``."""

    name = "greenhouse"
    BASE = "https://boards-api.greenhouse.io/v1/boards"

    def fetch(self, target, company, tier, ctx) -> ProviderResult:
        http = Http(ctx)
        data = http.get_json(f"{self.BASE}/{target}/jobs")

        sightings, stale = [], 0
        for job in data.get("jobs") or []:
            # first_published is when the role went live. updated_at moves on
            # every edit, which made month-old roles look brand new.
            posted = from_any(job.get("first_published") or job.get("updated_at"))
            if not self.within_age(posted, ctx.max_age_days):
                stale += 1
                continue
            url = job.get("absolute_url") or ""
            if not self.safe(url):
                continue
            sightings.append(Sighting(
                provider=self.name, company=company, title=job.get("title") or "",
                url=url, location=(job.get("location") or {}).get("name") or "",
                external_id=str(job.get("id") or ""), posted=posted, tier=tier,
            ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"date_filter": "client", "stale_dropped": stale})

    def fetch_detail(self, sighting, ctx) -> str:
        match = re.search(r"greenhouse\.io/([^/]+)/jobs/", sighting.url)
        slug = match.group(1) if match else ""
        if not (slug and sighting.external_id):
            return ""
        url = f"{self.BASE}/{slug}/jobs/{sighting.external_id}"
        if not self.safe(url):
            return ""
        return clean_html(Http(ctx).get_json(url).get("content") or "")[:40_000]


class LeverProvider(Provider):
    """Target: the company slug. Lever returns full text in the listing."""

    name = "lever"

    def fetch(self, target, company, tier, ctx) -> ProviderResult:
        http = Http(ctx)
        data = http.get_json(f"https://api.lever.co/v0/postings/{target}",
                             params={"mode": "json"})

        sightings, stale = [], 0
        for job in data if isinstance(data, list) else []:
            posted = from_any(job.get("createdAt"))
            if not self.within_age(posted, ctx.max_age_days):
                stale += 1
                continue
            url = job.get("hostedUrl") or ""
            if not self.safe(url):
                continue
            sightings.append(Sighting(
                provider=self.name, company=company, title=job.get("text") or "",
                url=url, location=(job.get("categories") or {}).get("location") or "",
                external_id=str(job.get("id") or ""), posted=posted,
                description=job.get("descriptionPlain") or "", tier=tier,
            ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"date_filter": "client", "stale_dropped": stale})


class AshbyProvider(Provider):
    """Target: the job-board slug, e.g. ``deepl``."""

    name = "ashby"
    BASE = "https://api.ashbyhq.com/posting-api/job-board"

    def fetch(self, target, company, tier, ctx) -> ProviderResult:
        http = Http(ctx)
        data = http.get_json(f"{self.BASE}/{target}", params={"includeCompensation": "true"})

        sightings, stale = [], 0
        for job in data.get("jobs") or []:
            posted = from_any(job.get("publishedAt") or job.get("updatedAt"))
            if not self.within_age(posted, ctx.max_age_days):
                stale += 1
                continue
            url = job.get("jobUrl") or job.get("applyUrl") or ""
            if not self.safe(url):
                continue
            remote = " remote" if job.get("isRemote") else ""
            sightings.append(Sighting(
                provider=self.name, company=company, title=job.get("title") or "",
                url=url, location=(job.get("location") or "") + remote,
                external_id=str(job.get("id") or ""), posted=posted,
                description=clean_html(job.get("descriptionHtml")
                                       or job.get("descriptionPlain") or ""),
                tier=tier,
                salary_hint=str(job.get("compensation") or "")[:200],
            ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"date_filter": "client", "stale_dropped": stale})


class PersonioProvider(Provider):
    """Target: the subdomain, e.g. ``proglove``. Personio publishes XML."""

    name = "personio"

    def fetch(self, target, company, tier, ctx) -> ProviderResult:
        http = Http(ctx)
        xml = http.get_text(f"https://{target}.jobs.personio.de/xml")

        sightings = []
        for block in re.findall(r"<position>(.*?)</position>", xml, re.S):
            def tag(name: str, blk: str = block) -> str:
                m = re.search(rf"<{name}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", blk, re.S)
                return (m.group(1) or "").strip() if m else ""

            job_id, title = tag("id"), tag("name")
            if not (job_id and title):
                continue
            url = f"https://{target}.jobs.personio.de/job/{job_id}"
            if not self.safe(url):
                continue

            description = " ".join(clean_html(v) for v in
                                   re.findall(r"<value>(.*?)</value>", block, re.S))
            sightings.append(Sighting(
                provider=self.name, company=company, title=clean_html(title), url=url,
                location=tag("office"), external_id=job_id,
                # Personio's feed carries no publication date at all, so none
                # is claimed. The pipeline treats it as undated rather than new.
                posted="", description=description[:40_000], tier=tier,
            ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"date_filter": "none", "provides_dates": False})


class WorkableProvider(Provider):
    """Target: the account slug, e.g. ``agile-robots``."""

    name = "workable"
    BASE = "https://apply.workable.com/api/v1/widget/accounts"

    def fetch(self, target, company, tier, ctx) -> ProviderResult:
        http = Http(ctx)
        data = http.get_json(f"{self.BASE}/{target}", params={"details": "true"})

        sightings, stale = [], 0
        for job in data.get("jobs") or []:
            posted = from_any(job.get("published_on") or job.get("created_at"))
            if not self.within_age(posted, ctx.max_age_days):
                stale += 1
                continue
            url = job.get("url") or job.get("application_url") or ""
            if not self.safe(url):
                continue
            location = ", ".join(filter(None, (job.get("city"), job.get("country"))))
            sightings.append(Sighting(
                provider=self.name, company=company, title=job.get("title") or "",
                url=url, location=location, external_id=str(job.get("shortcode") or ""),
                posted=posted, description=clean_html(job.get("description") or ""),
                tier=tier,
            ))

        return ProviderResult(sightings=sightings, requests_made=http.requests_made,
                              capabilities={"date_filter": "client", "stale_dropped": stale})
