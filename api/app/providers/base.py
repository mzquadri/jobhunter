"""Provider contract and the HTTP client every provider shares.

A provider knows one thing: how to turn a target -- a Workday tenant, a
Greenhouse slug, a board name -- into normalised ``Sighting`` objects. It does
not know about the database, scoring or deduplication, which is what makes
adding a source one file and one line of YAML.

Failure is expected and contained. A source that times out, rate-limits or
changes its response shape must not end the run, so every provider call is
wrapped and reported as a ``ProviderResult`` carrying its own error rather
than raising into the pipeline.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx

from app.dedup import Sighting
from app.security import RateLimit, UnsafeUrl, validate_url
from app.settings import Settings

log = logging.getLogger(__name__)


class RateLimited(Exception):
    """The remote end asked us to slow down."""


@dataclass
class FetchContext:
    """Everything a provider needs that is not its own target."""

    queries: list[str]
    max_age_days: int
    settings: Settings
    client: httpx.Client
    limiter: RateLimit


@dataclass
class ProviderResult:
    sightings: list[Sighting] = field(default_factory=list)
    requests_made: int = 0
    # What the source turned out to support. Workday's posting-date facet is
    # per-tenant configuration, so whether filtering happened server-side or
    # had to be done locally is a property of the run, not of the code.
    capabilities: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    rate_limited: bool = False

    @property
    def ok(self) -> bool:
        return not self.error


class Http:
    """Shared HTTP behaviour: validation, pacing, retries, backoff.

    Retries only on conditions that can plausibly succeed on a second attempt
    -- timeouts, connection errors, 5xx and 429. A 404 is an answer, not a
    failure to retry.
    """

    RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(self, ctx: FetchContext) -> None:
        self.ctx = ctx
        self.requests_made = 0

    def _host(self, url: str) -> str:
        return (urlparse(url).hostname or "").lower()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        validate_url(url)
        settings = self.ctx.settings
        last_error: Exception | None = None

        for attempt in range(1, settings.http_max_retries + 1):
            self.ctx.limiter.wait(self._host(url))
            self.requests_made += 1
            try:
                response = self.ctx.client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
            else:
                if response.status_code == 429:
                    if attempt == settings.http_max_retries:
                        raise RateLimited(f"{self._host(url)} returned 429")
                    self._sleep(attempt, response)
                    continue
                if response.status_code in self.RETRYABLE_STATUS:
                    last_error = httpx.HTTPStatusError(
                        f"{response.status_code} from {self._host(url)}",
                        request=response.request, response=response,
                    )
                elif response.is_error:
                    # Carry the server's own explanation. jobs.ch answers a
                    # too-large page size with "20 is the upper limit", and
                    # that sentence is the difference between a five-minute
                    # fix and an afternoon of guessing.
                    raise httpx.HTTPStatusError(
                        f"{response.status_code} from {self._host(url)}: "
                        f"{self._detail(response)}",
                        request=response.request, response=response,
                    )
                else:
                    return response

            if attempt < settings.http_max_retries:
                self._sleep(attempt)

        raise last_error or httpx.TransportError(f"{url} failed")

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        """A short, safe excerpt of an error body."""
        try:
            body = response.text
        except Exception:                          # pragma: no cover - defensive
            return ""
        return " ".join(body.split())[:200]

    def _sleep(self, attempt: int, response: httpx.Response | None = None) -> None:
        """Exponential backoff, honouring Retry-After when the server sends it.

        Jitter matters here: without it, a dozen provider threads that all hit
        a 503 would retry in lockstep and reproduce the burst that caused it.
        """
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(min(int(retry_after), 60))
                return
        base = self.ctx.settings.http_backoff_seconds
        time.sleep(min(base * (2 ** (attempt - 1)) + random.uniform(0, 0.4), 30))

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs).json()

    def post_json(self, url: str, payload: dict, **kwargs: Any) -> Any:
        return self.request("POST", url, json=payload, **kwargs).json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.request("GET", url, **kwargs).text


class Provider(ABC):
    """One way of reaching postings."""

    #: Stable identifier, used in the database and in provider health.
    name: str = ""
    #: True when the provider reaches one employer; False for open boards.
    employer_scoped: bool = True

    @abstractmethod
    def fetch(self, target: str, company: str, tier: str, ctx: FetchContext) -> ProviderResult:
        """Return every current posting for ``target``."""

    def fetch_detail(self, sighting: Sighting, ctx: FetchContext) -> str:
        """Full description for one posting.

        The default fetches nothing: several providers already return the
        whole description in their listing, and a provider that cannot do
        better should not pretend to.
        """
        return ""

    # -- helpers shared by implementations --------------------------------
    @staticmethod
    def safe(url: str) -> bool:
        try:
            validate_url(url, resolve=False)
        except UnsafeUrl:
            return False
        return True

    @staticmethod
    def within_age(posted: str, max_age_days: int, keep_undated: bool = True) -> bool:
        """Cheap client-side freshness filter.

        Used by providers that cannot filter server-side, so stale postings are
        dropped before the expense of fetching their full text.
        """
        if not posted:
            return keep_undated
        try:
            when = datetime.strptime(posted, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return keep_undated
        return when >= datetime.now(UTC) - timedelta(days=max_age_days)


def run_provider(
    provider: Provider, target: str, company: str, tier: str, ctx: FetchContext
) -> ProviderResult:
    """Call a provider and convert any failure into a reportable result.

    This is the isolation boundary the spec asks for: one broken source must
    not break the search.
    """
    started = time.monotonic()
    try:
        result = provider.fetch(target, company, tier, ctx)
    except RateLimited as exc:
        return ProviderResult(error=str(exc)[:400], rate_limited=True)
    except UnsafeUrl as exc:
        log.warning("%s: refused an unsafe URL: %s", provider.name, exc)
        return ProviderResult(error=f"unsafe URL refused: {exc}"[:400])
    except httpx.HTTPStatusError as exc:
        # str(exc) already carries the server's explanation, which is the part
        # worth keeping; the bare status code rarely is.
        return ProviderResult(error=str(exc)[:400])
    except Exception as exc:                       # noqa: BLE001 - isolation is the point
        log.warning("%s failed for %s", provider.name, target, exc_info=True)
        return ProviderResult(error=f"{type(exc).__name__}: {exc}"[:400])
    finally:
        elapsed = (time.monotonic() - started) * 1000
        log.debug("%s/%s took %.0fms", provider.name, target, elapsed)

    return result
