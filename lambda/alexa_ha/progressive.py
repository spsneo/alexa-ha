"""Alexa progressive responses: say "one moment" while Home Assistant thinks.

This does not extend Alexa's 8 second limit; it only avoids dead air.
https://developer.amazon.com/docs/alexa/custom-skills/send-the-user-a-progressive-response.html
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from typing import Optional

LOGGER = logging.getLogger(__name__)


def _send(api_endpoint: str, api_token: str, request_id: str, ssml: str) -> None:
    body = json.dumps(
        {
            "header": {"requestId": request_id},
            "directive": {"type": "VoicePlayer.Speak", "speech": ssml},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        api_endpoint.rstrip("/") + "/v1/directives",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + api_token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            resp.read()
    except Exception as err:  # never let this break the main answer
        LOGGER.info("Progressive response not sent: %s", type(err).__name__)


class ProgressiveResponse:
    """Starts a timer; if the answer is not ready in time, speaks ``ssml``."""

    def __init__(self, delay: float, api_endpoint: Optional[str], api_token: Optional[str], request_id: Optional[str], ssml: str):
        self._timer: Optional[threading.Timer] = None
        if delay > 0 and api_endpoint and api_token and request_id:
            self._timer = threading.Timer(delay, _send, args=(api_endpoint, api_token, request_id, ssml))
            self._timer.daemon = True

    def __enter__(self) -> "ProgressiveResponse":
        if self._timer:
            self._timer.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._timer:
            self._timer.cancel()
            # If it is mid-send, give it a moment so it is spoken before our answer.
            self._timer.join(timeout=0.5)
