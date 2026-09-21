"""URL validation and request-rate limiting.

Providers hand back URLs that this system then fetches: a Workday response
names the endpoint for each posting's full text. Those URLs are third-party
input, so they are validated before any request is made.

The threat is server-side request forgery. A hostile or compromised source
could return ``http://169.254.169.254/latest/meta-data/`` and turn the
collector into a proxy for reading cloud instance metadata, or point at a
service that is only reachable from inside the container network.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from urllib.parse import urlparse

# Only ever HTTPS. Plain HTTP is refused rather than upgraded, because a
# provider returning http:// is a signal worth surfacing, not smoothing over.
ALLOWED_SCHEMES = frozenset({"https"})

# Link-local, loopback, private and reserved ranges. Resolved addresses are
# checked against these, not just the hostname, so a DNS record pointing at a
# private address is caught too.
_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "metadata.google.internal", "metadata", "instance-data",
})


class UnsafeUrl(ValueError):
    """Raised when a URL must not be fetched."""


def _is_blocked_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable is not by itself unsafe; the request will simply fail.
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return True
    return False


def validate_url(url: str, *, resolve: bool = True) -> str:
    """Return the URL if it is safe to fetch, otherwise raise ``UnsafeUrl``.

    ``resolve=False`` skips the DNS lookup, for callers that only need the
    cheap structural checks.
    """
    if not url or len(url) > 2048:
        raise UnsafeUrl("empty or excessively long URL")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrl(f"scheme {parsed.scheme!r} is not allowed")

    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeUrl("URL has no host")
    if host in _BLOCKED_HOSTNAMES:
        raise UnsafeUrl(f"host {host!r} is not allowed")

    # A literal IP in the URL is checked directly, without DNS.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            raise UnsafeUrl(f"address {host} is in a blocked range")
        return url

    if resolve and _is_blocked_address(host):
        raise UnsafeUrl(f"host {host!r} resolves to a blocked address")

    return url


def is_safe_url(url: str, *, resolve: bool = True) -> bool:
    try:
        validate_url(url, resolve=resolve)
    except UnsafeUrl:
        return False
    return True


# ---------------------------------------------------------------------------
# rate limiting
# ---------------------------------------------------------------------------
@dataclass
class RateLimit:
    """Per-host request pacing.

    Sources are someone else's infrastructure and this runs unattended every
    hour, so it paces itself rather than relying on the remote end to push
    back. A sliding window is used rather than a token bucket because the
    relevant promise is "no more than N requests to one host per minute",
    which a window states directly.
    """

    per_minute: int = 60
    _hits: dict[str, deque[float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._hits = defaultdict(deque)

    def wait(self, host: str) -> float:
        """Block until another request to ``host`` is allowed. Returns the
        time spent waiting, so callers can report it."""
        if self.per_minute <= 0:
            return 0.0
        window = self._hits[host]
        now = time.monotonic()
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) < self.per_minute:
            window.append(now)
            return 0.0
        sleep_for = 60 - (now - window[0]) + 0.01
        time.sleep(max(0.0, sleep_for))
        window.popleft()
        window.append(time.monotonic())
        return sleep_for
