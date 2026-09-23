"""Recognise supported ATS URLs already supplied by a source; never guess tenants."""
import re
from urllib.parse import urlparse

from app.security import is_safe_url


def identify_official_source(url: str) -> tuple[str, str] | None:
    if not is_safe_url(url, resolve=False):
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    providers = {
        "boards.greenhouse.io": "greenhouse", "job-boards.greenhouse.io": "greenhouse",
        "jobs.lever.co": "lever", "jobs.ashbyhq.com": "ashby",
        "jobs.smartrecruiters.com": "smartrecruiters", "apply.workable.com": "workable",
    }
    if host in providers and re.fullmatch(r"[A-Za-z0-9_-]+", parts[0]):
        return providers[host], parts[0]
    if match := re.fullmatch(r"([a-z0-9-]+)\.jobs\.personio\.de", host):
        return "personio", match[1]
    if match := re.fullmatch(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com", host):
        localized = re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]) and len(parts) > 1
        site = parts[1] if localized else parts[0]
        if re.fullmatch(r"[A-Za-z0-9_-]+", site):
            return "workday", f"{match[1]}|{match[2]}|{site}"
    return None
