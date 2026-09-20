"""Where the postings come from.

Large employers do not build their own career sites -- they rent one of about
five Applicant Tracking Systems, and every one of those exposes a public JSON
or RSS endpoint. So there is an adapter per ATS rather than a scraper per
company, and adding a company is one line of YAML.

Every adapter yields RawPosting objects with the same shape. `description` may
be empty here; the pipeline fills it in later, and only for the postings that
already look worth the extra request.

Verified working 20 Sep 2026: Workday, SmartRecruiters, SuccessFactors RSS,
Greenhouse, Lever, arbeitnow, jobs.ch.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

from app.settings import Profile, get_settings

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, application/rss+xml, text/xml, text/html;q=0.9, */*",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}


@dataclass
class RawPosting:
    company: str
    title: str
    url: str
    source: str
    location: str = ""
    posted: str = ""            # YYYY-MM-DD, or "" when the source is silent
    description: str = ""
    tier: str = "NORMAL"
    salary: str = ""
    tags: str = ""
    detail_url: str = ""        # where the full text lives, when it is elsewhere
    extras: dict = field(default_factory=dict)


class Collector:
    """Holds the HTTP client and records which sources misbehaved."""

    def __init__(self, profile: Profile, client: httpx.Client | None = None) -> None:
        self.profile = profile
        settings = get_settings()
        self.client = client or httpx.Client(
            headers=HEADERS,
            timeout=settings.http_timeout,
            follow_redirects=True,
        )
        self.problems: list[tuple[str, str]] = []

    def close(self) -> None:
        self.client.close()

    def problem(self, source: str, detail: object) -> None:
        text = str(detail)
        self.problems.append((source[:160], text[:400]))
        log.warning("source problem: %s -- %s", source, text[:200])

    # -- plumbing ---------------------------------------------------------
    def _get(self, url: str) -> httpx.Response:
        r = self.client.get(url)
        r.raise_for_status()
        return r

    def _post(self, url: str, payload: dict) -> httpx.Response:
        r = self.client.post(url, json=payload)
        r.raise_for_status()
        return r

    # -- company adapters -------------------------------------------------
    def fetch_company(self, name: str, adapter: str, arg: str, tier: str) -> list[RawPosting]:
        fn = getattr(self, f"_from_{adapter}", None)
        if fn is None:
            self.problem(name, f"unknown adapter '{adapter}'")
            return []
        try:
            postings = fn(name, arg)
        except Exception as exc:  # one broken source must not end the sweep
            self.problem(name, exc)
            return []
        for p in postings:
            p.tier = tier
        return postings

    # Workday's "Posting Date" facet uses a per-tenant GUID for each bucket, so
    # the ids cannot be hardcoded -- but the descriptors are stable.
    WD_RECENT = ("1 day", "today", "1 week", "last week", "2-4 weeks",
                 "2 - 4 weeks", "last 30 days", "30 days")

    def _workday_recent_facet(self, api: str, query: str) -> list[str]:
        """Read the posting-date facet so Workday returns recent roles.

        Without this Workday answers by relevance and happily hands back jobs
        posted three months ago, which is where stale listings come from.
        """
        try:
            data = self._post(api, {"appliedFacets": {}, "limit": 1,
                                    "offset": 0, "searchText": query}).json()
        except Exception:
            return []
        for facet in data.get("facets") or []:
            if facet.get("facetParameter") == "startDate":
                return [
                    v["id"] for v in facet.get("values") or []
                    if v.get("id")
                    and str(v.get("descriptor", "")).strip().lower() in self.WD_RECENT
                ]
        return []

    def _from_workday(self, company: str, arg: str) -> list[RawPosting]:
        """arg = 'tenant|wdN|CareerSiteName'.

        Two things make this work on employers the size of Airbus (1800 open
        roles): search for the field rather than listing everything, and apply
        Workday's own posting-date filter.
        """
        tenant, wd, site = arg.split("|")
        base = f"https://{tenant}.{wd}.myworkdayjobs.com"
        api = f"{base}/wday/cxs/{tenant}/{site}/jobs"

        recent = self._workday_recent_facet(api, self.profile.company_queries[0])
        facets = {"startDate": recent} if recent else {}
        if not recent:
            self.problem(company, "no posting-date facet; falling back to all dates")

        out: list[RawPosting] = []
        seen: set[str] = set()
        for query in self.profile.company_queries:
            for page in range(2):
                try:
                    data = self._post(api, {"appliedFacets": facets, "limit": 20,
                                            "offset": page * 20, "searchText": query}).json()
                except Exception as exc:
                    self.problem(f"{company} [{query}]", exc)
                    break
                posts = data.get("jobPostings") or []
                if not posts:
                    break
                for p in posts:
                    path = p.get("externalPath") or ""
                    if path in seen:
                        continue
                    seen.add(path)
                    out.append(RawPosting(
                        company=company,
                        title=p.get("title") or "",
                        url=f"{base}/en-US/{site}{path}",
                        location=p.get("locationsText") or "",
                        posted=date_from_relative(p.get("postedOn")),
                        source="workday",
                        detail_url=f"{base}/wday/cxs/{tenant}/{site}{path}",
                    ))
                if (page + 1) * 20 >= (data.get("total") or 0):
                    break
        return out

    def _from_smartrecruiters(self, company: str, slug: str) -> list[RawPosting]:
        """Bosch has 4800 postings, so search rather than list."""
        out: list[RawPosting] = []
        seen: set[str] = set()
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        for query in self.profile.company_queries:
            try:
                r = self.client.get(url, params={"limit": 100, "q": query})
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                self.problem(f"{company} [{query}]", exc)
                continue
            for p in data.get("content") or []:
                pid = p.get("id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                loc = p.get("location") or {}
                where = ", ".join(x for x in (loc.get("city"), loc.get("region"),
                                              loc.get("country")) if x)
                out.append(RawPosting(
                    company=company,
                    title=p.get("name") or "",
                    url=f"https://jobs.smartrecruiters.com/{slug}/{pid}",
                    location=where,
                    posted=date_from_any(p.get("releasedDate") or p.get("createdOn")),
                    source="smartrecruiters",
                    detail_url=f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{pid}",
                ))
        return out

    def _from_sf_rss(self, company: str, host: str) -> list[RawPosting]:
        """Every SuccessFactors career site answers the same RSS path.

        It returns only the ~20 newest postings, which for a monitor is exactly
        what is wanted.
        """
        xml = self._get(f"https://{host}/services/rss/job/?locale=en_US").text
        out: list[RawPosting] = []
        for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
            def tag(name: str, blk: str = block) -> str:
                m = re.search(rf"<{name}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", blk, re.S)
                return (m.group(1) or "").strip() if m else ""

            title, link = tag("title"), tag("link")
            if not (title and link):
                continue
            body = strip_html(tag("description"))
            out.append(RawPosting(
                company=company,
                title=html.unescape(title),
                url=link,
                location=tag("location") or self._guess_location(body),
                posted=date_from_any(tag("pubDate")),
                description=body,
                source="successfactors",
            ))
        return out

    def _from_greenhouse(self, company: str, slug: str) -> list[RawPosting]:
        # first_published is when the job went live. updated_at moves whenever
        # someone fixes a typo, which made month-old roles look brand new.
        data = self._get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").json()
        return [
            RawPosting(
                company=company,
                title=j.get("title") or "",
                url=j.get("absolute_url") or "",
                location=(j.get("location") or {}).get("name") or "",
                posted=date_from_any(j.get("first_published") or j.get("updated_at")),
                source="greenhouse",
                detail_url=f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{j.get('id')}",
            )
            for j in data.get("jobs") or []
        ]

    def _from_lever(self, company: str, slug: str) -> list[RawPosting]:
        data = self._get(f"https://api.lever.co/v0/postings/{slug}?mode=json").json()
        return [
            RawPosting(
                company=company,
                title=j.get("text") or "",
                url=j.get("hostedUrl") or "",
                location=(j.get("categories") or {}).get("location") or "",
                posted=date_from_any(j.get("createdAt")),
                description=j.get("descriptionPlain") or "",
                source="lever",
            )
            for j in data
        ]

    def _guess_location(self, text: str) -> str:
        """SuccessFactors RSS often hides the city in the body text."""
        if not text:
            return ""
        for cities in self.profile.location_tiers.values():
            for city in cities:
                if len(city) > 3 and re.search(rf"\b{re.escape(city)}\b", text, re.I):
                    return city.title()
        return ""

    # -- board adapters ---------------------------------------------------
    def fetch_board(self, name: str) -> list[RawPosting]:
        fn = getattr(self, f"_board_{name}", None)
        if fn is None:
            self.problem(name, "unknown board")
            return []
        try:
            return fn()
        except Exception as exc:
            self.problem(name, exc)
            return []

    def _board_arbeitnow(self) -> list[RawPosting]:
        """Free German job board API. 250 per page, newest first, full text included."""
        pages = int(self.profile.boards.get("arbeitnow_pages", 4))
        out: list[RawPosting] = []
        for page in range(1, pages + 1):
            url = "https://www.arbeitnow.com/api/job-board-api"
            if page > 1:
                url += f"?page={page}"
            rows = self._get(url).json().get("data") or []
            if not rows:
                break
            for j in rows:
                out.append(RawPosting(
                    company=j.get("company_name") or "?",
                    title=j.get("title") or "",
                    url=j.get("url") or "",
                    location=j.get("location") or "",
                    posted=date_from_any(j.get("created_at")),
                    description=strip_html(j.get("description")),
                    source="arbeitnow (DE)",
                    tags=" ".join(j.get("tags") or []) + " " + " ".join(j.get("job_types") or []),
                ))
        return out

    def _board_jobsch(self) -> list[RawPosting]:
        """jobs.ch public search -- the main Swiss board."""
        out: list[RawPosting] = []
        for query in self.profile.boards.get("queries", []):
            url = "https://www.jobs.ch/api/v1/public/search"
            try:
                data = self.client.get(url, params={"query": query, "rows": 40}).json()
            except Exception as exc:
                self.problem(f"jobs.ch [{query}]", exc)
                continue
            for j in data.get("documents") or []:
                links = j.get("_links") or {}
                href = ((links.get("detail") or {}).get("href")
                        or (links.get("self") or {}).get("href") or "")
                if href.startswith("/"):
                    href = "https://www.jobs.ch" + href
                regions = ", ".join(
                    r.get("name", "") for r in (j.get("regions") or []) if isinstance(r, dict)
                )
                out.append(RawPosting(
                    company=j.get("company_name") or "?",
                    title=j.get("title") or "",
                    url=href or f"https://www.jobs.ch/en/vacancies/detail/{j.get('job_id')}/",
                    location=regions or "Switzerland",
                    posted=date_from_any(j.get("publication_date")),
                    description=strip_html(j.get("preview")),
                    source="jobs.ch (CH)",
                ))
        return out

    def _board_adzuna(self) -> list[RawPosting]:
        """Optional. Needs a free key; adds salary data across DE/CH/AT/NL."""
        settings = get_settings()
        if not (settings.adzuna_app_id and settings.adzuna_app_key):
            self.problem("adzuna", "no API key configured -- skipped")
            return []
        out: list[RawPosting] = []
        countries = self.profile.boards.get("adzuna_countries", ["de"])
        for country in countries:
            for query in self.profile.boards.get("queries", [])[:3]:
                url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
                params = {
                    "app_id": settings.adzuna_app_id,
                    "app_key": settings.adzuna_app_key,
                    "results_per_page": 50,
                    "what": query,
                    "sort_by": "date",
                    "max_days_old": self.profile.max_age_days,
                }
                try:
                    data = self.client.get(url, params=params).json()
                except Exception as exc:
                    self.problem(f"adzuna {country}", exc)
                    continue
                for j in data.get("results") or []:
                    salary = ""
                    if j.get("salary_min"):
                        salary = f"{int(j['salary_min']):,}–{int(j.get('salary_max') or 0):,}"
                    out.append(RawPosting(
                        company=(j.get("company") or {}).get("display_name") or "?",
                        title=j.get("title") or "",
                        url=j.get("redirect_url") or "",
                        location=(j.get("location") or {}).get("display_name") or country.upper(),
                        posted=date_from_any(j.get("created")),
                        description=strip_html(j.get("description")),
                        source=f"adzuna ({country.upper()})",
                        salary=salary,
                    ))
        return out

    # -- enrichment -------------------------------------------------------
    def fetch_detail(self, posting: RawPosting) -> str:
        """Full posting text, so the warning rules have something to read."""
        try:
            if not posting.detail_url:
                if not posting.url:
                    return ""
                return strip_html(self._get(posting.url).text)[:20_000]

            if posting.source == "workday":
                info = self._get(posting.detail_url).json().get("jobPostingInfo") or {}
                return strip_html(info.get("jobDescription") or "")[:20_000]

            if posting.source == "smartrecruiters":
                ad = self._get(posting.detail_url).json().get("jobAd") or {}
                parts = [
                    strip_html(sec.get("text") or "")
                    for sec in (ad.get("sections") or {}).values()
                    if isinstance(sec, dict)
                ]
                return "\n\n".join(p for p in parts if p)[:20_000]

            if posting.source == "greenhouse":
                content = self._get(posting.detail_url).json().get("content") or ""
                return strip_html(content)[:20_000]

            return strip_html(self._get(posting.detail_url).text)[:20_000]
        except Exception as exc:
            self.problem(f"detail {posting.company}", exc)
            return ""


# --------------------------------------------------------------------------
# text and date helpers -- every ATS invented its own format
# --------------------------------------------------------------------------
def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def date_from_relative(text: str | None) -> str:
    """Workday says 'Posted 5 Days Ago' rather than giving a date."""
    if not text:
        return ""
    t = text.lower()
    today = datetime.now()
    if "today" in t or "just posted" in t:
        return _iso(today)
    if "yesterday" in t:
        return _iso(today - timedelta(days=1))
    if m := re.search(r"(\d+)\+?\s*day", t):
        return _iso(today - timedelta(days=int(m.group(1))))
    if m := re.search(r"(\d+)\+?\s*month", t):
        return _iso(today - timedelta(days=30 * int(m.group(1))))
    return ""


def date_from_any(value: object) -> str:
    """ISO string, RFC-822 string or unix epoch -- all become YYYY-MM-DD."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            n = int(value)
            if n > 4_000_000_000:          # milliseconds
                n //= 1000
            return _iso(datetime.fromtimestamp(n, tz=UTC))
        except (ValueError, OSError, OverflowError):
            return ""
    s = str(value).strip()
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", s):
        return m.group(0)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%d %b %Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return _iso(datetime.strptime(s[:31].strip(), fmt))
        except ValueError:
            continue
    return ""


def days_old(posted: str | None) -> int | None:
    if not posted:
        return None
    try:
        return (datetime.now() - datetime.strptime(posted, "%Y-%m-%d")).days
    except ValueError:
        return None
