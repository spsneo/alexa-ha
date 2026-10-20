"""Skill settings.

Settings come from ``config.json`` next to ``lambda_function.py`` (create it
from ``config.example.json`` in the Alexa developer console code editor), and
can be overridden by environment variables when you host the Lambda yourself.
``config.json`` is git-ignored so secrets never reach the public repository.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

# Environment variable -> setting name.
ENV_OVERRIDES = {
    "HA_URL": "ha_url",
    "HA_TOKEN": "ha_token",
    "SKILL_ID": "skill_id",
    "HA_PIPELINE": "pipeline",
    "HA_MODE": "mode",
    "HA_AGENT_ID": "agent_id",
    "HA_LANGUAGE": "language",
    "LOG_LEVEL": "log_level",
    "LOG_UTTERANCES": "log_utterances",
}


class ConfigError(Exception):
    """The settings are missing or invalid. ``spoken`` is safe to say aloud."""

    def __init__(self, message: str, spoken: str):
        super().__init__(message)
        self.spoken = spoken


@dataclass
class Config:
    ha_url: str
    ha_token: str
    skill_id: str
    # "pipeline" runs your Assist pipeline (same as a Voice PE).
    # "agent" talks to one conversation agent directly, skipping the pipeline.
    mode: str = "pipeline"
    # Pipeline name or ID. Empty means your preferred pipeline in Home Assistant.
    pipeline: str = ""
    # Only used when mode is "agent".
    agent_id: str = "conversation.jev"
    language: str = ""
    # Alexa device ID -> Home Assistant device ID, so HA knows which room you are in.
    devices: Dict[str, str] = field(default_factory=dict)
    # Total time we wait for Home Assistant. Alexa gives up at 8 seconds.
    timeout_seconds: float = 6.5
    connect_timeout_seconds: float = 3.0
    # Say a short "one moment" if HA has not answered after this many seconds. 0 turns it off.
    progressive_response_after_seconds: float = 3.0
    # Wrap Devanagari text in a Hindi <lang> tag so the voice reads it in Hindi.
    hindi_ssml: bool = True
    max_speech_chars: int = 2500
    log_level: str = "INFO"
    # Log what you said and what HA answered. Off by default for privacy.
    log_utterances: bool = False
    allow_insecure_http: bool = False
    messages: Dict[str, str] = field(default_factory=dict)

    @property
    def websocket_url(self) -> str:
        if self.ha_url.startswith("https://"):
            return "wss://" + self.ha_url[len("https://"):] + "/api/websocket"
        return "ws://" + self.ha_url[len("http://"):] + "/api/websocket"

    def __repr__(self) -> str:  # never print the token
        return "Config(ha_url=%r, mode=%r, pipeline=%r, agent_id=%r, devices=%d)" % (
            self.ha_url,
            self.mode,
            self.pipeline,
            self.agent_id,
            len(self.devices),
        )


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_float(name: str, value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ConfigError(
            "%s must be a number" % name,
            "The skill setting %s is not a number. Please fix config dot json." % name.replace("_", " "),
        )


def load_raw(path: str = CONFIG_FILE, environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    raw: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError) as err:
            raise ConfigError(
                "config.json could not be read: %s" % type(err).__name__,
                "The skill's config dot json file is not valid JSON. Please fix it and deploy again.",
            )
        if not isinstance(raw, dict):
            raise ConfigError("config.json must be a JSON object", "The skill's config dot json file is not valid.")
    environ = os.environ if environ is None else environ
    for env_name, key in ENV_OVERRIDES.items():
        if environ.get(env_name):
            raw[key] = environ[env_name]
    return raw


def parse(raw: Dict[str, Any]) -> Config:
    ha_url = str(raw.get("ha_url") or "").strip().rstrip("/")
    ha_token = str(raw.get("ha_token") or "").strip()
    skill_id = str(raw.get("skill_id") or "").strip()

    if not ha_url or "YOUR" in ha_url:
        raise ConfigError("ha_url is not set", "The skill doesn't know your Home Assistant address yet. Add ha url to config dot json.")
    if not ha_token or "YOUR" in ha_token:
        raise ConfigError("ha_token is not set", "The skill doesn't have a Home Assistant token yet. Add ha token to config dot json.")
    if not skill_id or "YOUR" in skill_id:
        raise ConfigError("skill_id is not set", "The skill ID is not set yet. Add skill ID to config dot json.")

    allow_http = _as_bool(raw.get("allow_insecure_http", False))
    if ha_url.endswith("/api"):
        ha_url = ha_url[: -len("/api")]
    if not ha_url.startswith("https://") and not (allow_http and ha_url.startswith("http://")):
        raise ConfigError("ha_url must start with https://", "Your Home Assistant address must start with https.")

    mode = str(raw.get("mode") or "pipeline").strip().lower()
    if mode not in ("pipeline", "agent"):
        raise ConfigError("mode must be 'pipeline' or 'agent'", "The skill setting mode must be pipeline or agent.")

    devices = raw.get("devices") or {}
    if not isinstance(devices, dict):
        raise ConfigError("devices must be an object", "The devices setting in config dot json is not valid.")
    # Keys starting with "_" are comments/examples.
    devices = {str(k).strip(): str(v).strip() for k, v in devices.items() if not str(k).startswith("_") and v}

    messages = raw.get("messages") or {}
    if not isinstance(messages, dict):
        messages = {}

    cfg = Config(
        ha_url=ha_url,
        ha_token=ha_token,
        skill_id=skill_id,
        mode=mode,
        pipeline=str(raw.get("pipeline") or "").strip(),
        agent_id=str(raw.get("agent_id") or "conversation.jev").strip(),
        language=str(raw.get("language") or "").strip(),
        devices=devices,
        timeout_seconds=_as_float("timeout_seconds", raw.get("timeout_seconds", 6.5)),
        connect_timeout_seconds=_as_float("connect_timeout_seconds", raw.get("connect_timeout_seconds", 3.0)),
        progressive_response_after_seconds=_as_float(
            "progressive_response_after_seconds", raw.get("progressive_response_after_seconds", 3.0)
        ),
        hindi_ssml=_as_bool(raw.get("hindi_ssml", True)),
        max_speech_chars=int(_as_float("max_speech_chars", raw.get("max_speech_chars", 2500))),
        log_level=str(raw.get("log_level") or "INFO").strip().upper(),
        log_utterances=_as_bool(raw.get("log_utterances", False)),
        allow_insecure_http=allow_http,
        messages={str(k): str(v) for k, v in messages.items()},
    )
    # Alexa stops waiting at 8 seconds; leave room for our own work and the network back to Alexa.
    cfg.timeout_seconds = max(1.0, min(cfg.timeout_seconds, 7.0))
    cfg.connect_timeout_seconds = max(0.5, min(cfg.connect_timeout_seconds, cfg.timeout_seconds))
    return cfg


def load(path: str = CONFIG_FILE, environ: Optional[Dict[str, str]] = None) -> Config:
    return parse(load_raw(path, environ))
