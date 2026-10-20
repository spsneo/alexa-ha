"""Talk to Home Assistant over its WebSocket API.

In "pipeline" mode we run your Assist pipeline from the intent stage to the
intent stage (text in, text out), exactly like a Voice PE does after it has
turned your voice into text. That keeps pipeline settings such as
"Prefer handling commands locally" working. In "agent" mode we call one
conversation agent directly.

Every network step has a deadline so the whole call fits inside Alexa's
8 second limit.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import websocket  # websocket-client

from .config import Config

LOGGER = logging.getLogger(__name__)

# Pipeline name -> id, cached while the Lambda container stays warm.
_PIPELINE_CACHE: Dict[Tuple[str, str], Tuple[str, float]] = {}
_PIPELINE_CACHE_SECONDS = 600
_PIPELINE_CACHE_LOCK = threading.Lock()


class HAError(Exception):
    """Something went wrong talking to Home Assistant.

    ``kind`` is one of: auth, unreachable, timeout, pipeline_not_found,
    agent_failed, bad_response.
    """

    def __init__(self, kind: str, detail: str = ""):
        super().__init__("%s: %s" % (kind, detail) if detail else kind)
        self.kind = kind
        self.detail = detail


@dataclass
class HAReply:
    speech: str
    conversation_id: Optional[str]
    continue_conversation: bool
    response_type: str
    processed_locally: Optional[bool] = None


class _Deadline:
    def __init__(self, seconds: float):
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        left = self.end - time.monotonic()
        if left <= 0:
            raise HAError("timeout", "deadline reached")
        return left


class _Connection:
    def __init__(self, cfg: Config, deadline: _Deadline):
        self.cfg = cfg
        self.deadline = deadline
        self.ws: Optional[websocket.WebSocket] = None
        self._next_id = 1

    def __enter__(self) -> "_Connection":
        try:
            self.ws = websocket.create_connection(
                self.cfg.websocket_url,
                timeout=min(self.cfg.connect_timeout_seconds, self.deadline.remaining()),
                enable_multithread=False,
                skip_utf8_validation=True,
            )
        except websocket.WebSocketBadStatusException as err:
            status = getattr(err, "status_code", None)
            if status in (401, 403):
                raise HAError("auth", "HTTP %s on websocket upgrade" % status)
            raise HAError("unreachable", "HTTP %s on websocket upgrade" % status)
        except (websocket.WebSocketTimeoutException, socket.timeout):
            raise HAError("timeout", "connecting")
        except ssl.SSLError as err:
            raise HAError("unreachable", "TLS error: %s" % type(err).__name__)
        except (OSError, websocket.WebSocketException) as err:
            raise HAError("unreachable", type(err).__name__)
        try:
            self._authenticate()
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.ws is not None:
            try:
                self.ws.close(timeout=0.2)
            except Exception:  # closing is best effort
                pass

    def send(self, message: Dict[str, Any]) -> int:
        if "type" in message and message["type"] != "auth":
            message = dict(message, id=self._next_id)
            self._next_id += 1
        assert self.ws is not None
        try:
            self.ws.settimeout(self.deadline.remaining())
            self.ws.send(json.dumps(message))
        except (websocket.WebSocketTimeoutException, socket.timeout):
            raise HAError("timeout", "sending")
        except (OSError, websocket.WebSocketException) as err:
            raise HAError("unreachable", "send failed: %s" % type(err).__name__)
        return message.get("id", 0)

    def recv(self) -> Dict[str, Any]:
        assert self.ws is not None
        try:
            self.ws.settimeout(self.deadline.remaining())
            raw = self.ws.recv()
        except (websocket.WebSocketTimeoutException, socket.timeout):
            raise HAError("timeout", "waiting for Home Assistant")
        except websocket.WebSocketConnectionClosedException:
            raise HAError("unreachable", "connection closed")
        except (OSError, websocket.WebSocketException) as err:
            raise HAError("unreachable", "receive failed: %s" % type(err).__name__)
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            raise HAError("bad_response", "not JSON")
        if not isinstance(msg, dict):
            raise HAError("bad_response", "unexpected message shape")
        return msg

    def _authenticate(self) -> None:
        first = self.recv()
        if first.get("type") == "auth_ok":
            return
        if first.get("type") != "auth_required":
            raise HAError("bad_response", "expected auth_required, got %s" % first.get("type"))
        self.send({"type": "auth", "access_token": self.cfg.ha_token})
        reply = self.recv()
        if reply.get("type") == "auth_invalid":
            raise HAError("auth", "token rejected")
        if reply.get("type") != "auth_ok":
            raise HAError("bad_response", "unexpected auth reply %s" % reply.get("type"))

    def wait_result(self, msg_id: int) -> Dict[str, Any]:
        while True:
            msg = self.recv()
            if msg.get("id") == msg_id and msg.get("type") == "result":
                return msg


def _looks_like_pipeline_id(value: str) -> bool:
    # Pipeline IDs are 26 character ULIDs (Home Assistant writes them in lower case).
    return len(value) == 26 and value.isalnum()


def _resolve_pipeline(conn: _Connection) -> Optional[str]:
    wanted = conn.cfg.pipeline
    if not wanted:
        return None  # Home Assistant uses your preferred pipeline.
    if _looks_like_pipeline_id(wanted):
        return wanted
    key = (conn.cfg.ha_url, wanted.lower())
    now = time.monotonic()
    with _PIPELINE_CACHE_LOCK:
        cached = _PIPELINE_CACHE.get(key)
        if cached and now - cached[1] < _PIPELINE_CACHE_SECONDS:
            return cached[0]
    msg_id = conn.send({"type": "assist_pipeline/pipeline/list"})
    result = conn.wait_result(msg_id)
    if not result.get("success"):
        raise HAError("bad_response", "could not list pipelines")
    for pipeline in (result.get("result") or {}).get("pipelines") or []:
        if str(pipeline.get("name", "")).strip().lower() == wanted.lower() or pipeline.get("id") == wanted:
            with _PIPELINE_CACHE_LOCK:
                _PIPELINE_CACHE[key] = (pipeline["id"], now)
            return pipeline["id"]
    raise HAError("pipeline_not_found", "no pipeline named in config")


def _reply_from_conversation_result(result: Dict[str, Any], processed_locally: Optional[bool] = None) -> HAReply:
    response = result.get("response") or {}
    speech = ((response.get("speech") or {}).get("plain") or {}).get("speech") or ""
    return HAReply(
        speech=str(speech),
        conversation_id=result.get("conversation_id"),
        continue_conversation=bool(result.get("continue_conversation")),
        response_type=str(response.get("response_type") or ""),
        processed_locally=processed_locally,
    )


def _run_pipeline(conn: _Connection, text: str, conversation_id: Optional[str], device_id: Optional[str]) -> HAReply:
    pipeline_id = _resolve_pipeline(conn)
    message: Dict[str, Any] = {
        "type": "assist_pipeline/run",
        "start_stage": "intent",
        "end_stage": "intent",
        "input": {"text": text},
        "conversation_id": conversation_id,
        # Let HA stop the run on its side around the time we stop waiting.
        "timeout": max(1, int(conn.deadline.remaining()) + 2),
    }
    if pipeline_id:
        message["pipeline"] = pipeline_id
    if device_id:
        message["device_id"] = device_id
    msg_id = conn.send(message)

    while True:
        msg = conn.recv()
        if msg.get("id") != msg_id:
            continue
        if msg.get("type") == "result":
            if msg.get("success"):
                continue  # Subscription confirmed; events follow.
            error = msg.get("error") or {}
            code = error.get("code", "")
            if code == "pipeline-not-found":
                raise HAError("pipeline_not_found", code)
            if code == "unauthorized":
                raise HAError("auth", code)
            raise HAError("agent_failed", code or "pipeline rejected")
        if msg.get("type") != "event":
            continue
        event = msg.get("event") or {}
        etype = event.get("type")
        data = event.get("data") or {}
        if etype == "intent-end":
            return _reply_from_conversation_result(data.get("intent_output") or {}, data.get("processed_locally"))
        if etype == "error":
            code = data.get("code", "")
            if code == "timeout":
                raise HAError("timeout", "pipeline timeout")
            raise HAError("agent_failed", code or "pipeline error")
        if etype == "run-end":
            raise HAError("bad_response", "pipeline ended without an answer")


def _run_agent(conn: _Connection, text: str, conversation_id: Optional[str], device_id: Optional[str]) -> HAReply:
    message: Dict[str, Any] = {
        "type": "conversation/process",
        "text": text,
        "conversation_id": conversation_id,
        "agent_id": conn.cfg.agent_id,
    }
    if conn.cfg.language:
        message["language"] = conn.cfg.language
    if device_id:
        message["device_id"] = device_id
    msg_id = conn.send(message)
    result = conn.wait_result(msg_id)
    if not result.get("success"):
        code = (result.get("error") or {}).get("code", "")
        if code == "unauthorized":
            raise HAError("auth", code)
        raise HAError("agent_failed", code or "conversation rejected")
    return _reply_from_conversation_result(result.get("result") or {})


def converse(
    cfg: Config,
    text: str,
    conversation_id: Optional[str] = None,
    device_id: Optional[str] = None,
    timeout: Optional[float] = None,
) -> HAReply:
    """Send ``text`` to Home Assistant and return its answer, or raise HAError."""
    deadline = _Deadline(cfg.timeout_seconds if timeout is None else timeout)
    started = time.monotonic()
    with _Connection(cfg, deadline) as conn:
        connected = time.monotonic()
        if cfg.mode == "agent":
            reply = _run_agent(conn, text, conversation_id, device_id)
        else:
            reply = _run_pipeline(conn, text, conversation_id, device_id)
    LOGGER.info(
        "HA answered in %.2fs (connect %.2fs), type=%s, local=%s, continue=%s",
        time.monotonic() - started,
        connected - started,
        reply.response_type or "-",
        reply.processed_locally,
        reply.continue_conversation,
    )
    return reply
