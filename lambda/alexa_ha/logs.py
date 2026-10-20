"""Logging that never prints secrets."""

from __future__ import annotations

import logging
import re
from typing import Iterable

_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I),
    re.compile(r"(\"?(?:access_token|apiAccessToken|ha_token|token)\"?\s*[:=]\s*\"?)[^\"\s,}]+", re.I),
    # JWTs, which is what Home Assistant long-lived tokens and Alexa API tokens look like.
    re.compile(r"()eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
]


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str] = ()):
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 8]

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "[redacted]")
        for pattern in _PATTERNS:
            text = pattern.sub(lambda m: m.group(1) + "[redacted]", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


_FILTER = RedactingFilter()


def setup(level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    root = logging.getLogger()
    if not root.handlers:  # running outside Lambda
        logging.basicConfig()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    _FILTER.secrets = [s for s in secrets if s and len(s) >= 8]
    for handler in root.handlers:
        if _FILTER not in handler.filters:
            handler.addFilter(_FILTER)
    # websocket-client can trace raw frames (which include the auth message). Keep it quiet.
    logging.getLogger("websocket").setLevel(logging.WARNING)
