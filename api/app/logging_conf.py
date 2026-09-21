"""Structured logging.

JSON by default so logs are queryable wherever they end up, with a readable
console format available for local work.

§26 requires that logs carry no personal information and no secrets. The
filter below is the enforcement: it redacts anything that looks like a
credential in a query string, because provider URLs can carry API keys and a
URL is exactly the kind of thing that gets logged without thinking.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

# app_key=..., api_key=..., token=..., password=... in a URL or message.
_SECRET_IN_TEXT = re.compile(
    r"((?:app_key|app_id|api_key|apikey|token|access_token|password|secret|"
    r"authorization)=)([^&\s\"']+)",
    re.I,
)


def redact(text: str) -> str:
    return _SECRET_IN_TEXT.sub(r"\1[redacted]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(
                    redact(str(a)) if isinstance(a, str) else a for a in record.args
                )
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Anything passed via extra=, without clobbering the standard fields.
        for key, value in vars(record).items():
            if key not in self.RESERVED and key not in payload and not key.startswith("_"):
                try:
                    json.dumps(value)
                except (TypeError, ValueError):
                    value = str(value)
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        JsonFormatter() if settings.log_json
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())

    # These are chatty at INFO and say nothing the application does not.
    for noisy in ("httpx", "httpcore", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
