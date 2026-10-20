"""Alexa request handling.

Nothing about a conversation is kept in module globals: everything that
belongs to one person on one device travels in the Alexa session or is
derived from the request, so warm Lambda containers can't leak context
between rooms or people.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from . import config as config_module
from . import ha_client, logs, messages, speech
from .config import Config, ConfigError
from .progressive import ProgressiveResponse

LOGGER = logging.getLogger(__name__)

QUERY_INTENT = "QueryIntent"
QUERY_SLOT = "query"
SETUP_INTENT = "SetupInfoIntent"
MAX_REQUEST_AGE_SECONDS = 150

END_PHRASES = {
    "no", "nope", "no thanks", "no thank you", "nothing", "nothing else", "that's all", "that is all",
    "that's it", "bye", "goodbye", "good bye", "bye bye", "stop", "cancel", "exit", "quit", "done",
    "i'm done", "all done", "thanks", "thank you", "thank you bye", "ok bye", "okay bye", "bas", "bas karo",
}

_CONFIG: Optional[Config] = None
_CONFIG_ERROR: Optional[ConfigError] = None
_CONFIG_LOADED = False


def get_config() -> Config:
    """Load settings once per container. Raises ConfigError if they are unusable."""
    global _CONFIG, _CONFIG_ERROR, _CONFIG_LOADED
    if not _CONFIG_LOADED:
        try:
            _CONFIG = config_module.load()
            _CONFIG_ERROR = None
        except ConfigError as err:
            _CONFIG, _CONFIG_ERROR = None, err
        _CONFIG_LOADED = True
    if _CONFIG_ERROR is not None:
        raise _CONFIG_ERROR
    assert _CONFIG is not None
    return _CONFIG


def set_config(cfg: Optional[Config]) -> None:
    """For tests and tools."""
    global _CONFIG, _CONFIG_ERROR, _CONFIG_LOADED
    _CONFIG, _CONFIG_ERROR, _CONFIG_LOADED = cfg, None, cfg is not None


# ---------------------------------------------------------------- responses


def build_response(
    speech_text: str,
    cfg: Optional[Config] = None,
    end_session: bool = True,
    reprompt: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    card: Optional[Tuple[str, str]] = None,
) -> Dict[str, Any]:
    hindi = cfg.hindi_ssml if cfg else True
    max_chars = cfg.max_speech_chars if cfg else 2500
    response: Dict[str, Any] = {"shouldEndSession": end_session}
    if speech_text:
        response["outputSpeech"] = {"type": "SSML", "ssml": speech.to_ssml(speech.clean_text(speech_text, max_chars), hindi)}
    if reprompt and not end_session:
        response["reprompt"] = {
            "outputSpeech": {"type": "SSML", "ssml": speech.to_ssml(speech.clean_text(reprompt, max_chars), hindi)}
        }
    if card:
        response["card"] = {"type": "Simple", "title": card[0], "content": card[1]}
    return {"version": "1.0", "sessionAttributes": attributes or {}, "response": response}


def _empty_response() -> Dict[str, Any]:
    return {"version": "1.0", "response": {}}


# ---------------------------------------------------------------- request helpers


def _get(d: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def _application_id(event: Dict[str, Any]) -> Optional[str]:
    return _get(event, "context", "System", "application", "applicationId") or _get(
        event, "session", "application", "applicationId"
    )


def _is_fresh(timestamp: Optional[str], now: Optional[float] = None) -> bool:
    if not timestamp:
        return False
    try:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = time.time() if now is None else now
    return abs(now - ts.timestamp()) <= MAX_REQUEST_AGE_SECONDS


def _who(event: Dict[str, Any]) -> Tuple[str, bool]:
    """The person speaking (voice profile) if Alexa recognised them, else the account."""
    person = _get(event, "context", "System", "person", "personId")
    if person:
        return person, True
    return _get(event, "context", "System", "user", "userId") or _get(event, "session", "user", "userId") or "", False


def _device(event: Dict[str, Any]) -> str:
    return _get(event, "context", "System", "device", "deviceId") or ""


def conversation_id_for(device: str, who: str, scope: str) -> str:
    """A stable, opaque conversation ID for this device + person (+ scope).

    Home Assistant accepts IDs we choose and forgets a conversation after a
    few minutes of silence, so quick follow-ups ("ask ... to make it
    dimmer") keep their context, while different devices and people never
    share one.
    """
    digest = hashlib.sha256(("%s|%s|%s" % (device, who, scope)).encode("utf-8")).hexdigest()
    return "alexa-" + digest[:32]


def _speech_for_error(cfg: Config, err: ha_client.HAError) -> str:
    key = "error_" + err.kind
    if key not in messages.DEFAULTS:
        key = "error_internal"
    return messages.get(cfg.messages, key)


# ---------------------------------------------------------------- handlers


def _ask_home_assistant(event: Dict[str, Any], cfg: Config, text: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    in_conversation = bool(attributes.get("launched")) or bool(attributes.get("ha_asked"))

    if in_conversation and not attributes.get("ha_asked") and text.strip().lower().rstrip(".!") in END_PHRASES:
        return build_response(messages.get(cfg.messages, "goodbye"), cfg)

    device = _device(event)
    who, _ = _who(event)
    conversation_id = attributes.get("conversation_id") or conversation_id_for(device, who, "one-shot")
    ha_device_id = cfg.devices.get(device)

    if cfg.log_utterances:
        LOGGER.info("Heard: %r", text)
    else:
        LOGGER.info("Heard %d characters", len(text))
    if not ha_device_id:
        LOGGER.info("Alexa device %s is not mapped to a Home Assistant device", device)

    system = _get(event, "context", "System") or {}
    progress_ssml = speech.to_ssml(speech.clean_text(messages.get(cfg.messages, "progress")), False)
    try:
        with ProgressiveResponse(
            cfg.progressive_response_after_seconds,
            system.get("apiEndpoint"),
            system.get("apiAccessToken"),
            _get(event, "request", "requestId"),
            progress_ssml,
        ):
            reply = ha_client.converse(cfg, text, conversation_id=conversation_id, device_id=ha_device_id)
    except ha_client.HAError as err:
        LOGGER.warning("Home Assistant call failed: %s", err)
        spoken = _speech_for_error(cfg, err)
        if in_conversation:
            return build_response(spoken, cfg, end_session=False, reprompt=messages.get(cfg.messages, "reprompt"), attributes=attributes)
        return build_response(spoken, cfg)

    answer = reply.speech.strip() or messages.get(cfg.messages, "done")
    if cfg.log_utterances:
        LOGGER.info("Answer: %r", answer)

    new_attributes = dict(attributes)
    new_attributes["conversation_id"] = reply.conversation_id or conversation_id
    new_attributes["ha_asked"] = reply.continue_conversation

    if reply.continue_conversation:
        # HA asked a question; listen for the answer without needing the invocation name.
        return build_response(answer, cfg, end_session=False, reprompt=answer, attributes=new_attributes)
    if attributes.get("launched"):
        return build_response(answer, cfg, end_session=False, reprompt=messages.get(cfg.messages, "reprompt"), attributes=new_attributes)
    return build_response(answer, cfg, attributes=new_attributes)


def _setup_info(event: Dict[str, Any], cfg: Config, attributes: Dict[str, Any]) -> Dict[str, Any]:
    device = _device(event)
    who, recognised = _who(event)
    mapped = cfg.devices.get(device)
    lines = [
        "Alexa device ID:",
        device or "(not available)",
        "",
        "Mapped to Home Assistant device: %s" % (mapped or "not yet. Add it under \"devices\" in config.json."),
        "Voice profile recognised: %s" % ("yes" if recognised else "no (conversations are per device only)"),
        "Mode: %s, pipeline: %s" % (cfg.mode, cfg.pipeline or "your preferred pipeline"),
    ]
    LOGGER.info("Setup info requested on device %s (mapped=%s, voice profile=%s)", device, bool(mapped), recognised)
    end = not attributes.get("launched")
    return build_response(
        messages.get(cfg.messages, "setup_info"),
        cfg,
        end_session=end,
        reprompt=None if end else messages.get(cfg.messages, "reprompt"),
        attributes=attributes,
        card=("alexa-ha setup details", "\n".join(lines)),
    )


def handle_event(event: Dict[str, Any]) -> Dict[str, Any]:
    request = event.get("request") or {}
    request_type = request.get("type", "")

    try:
        cfg = get_config()
    except ConfigError as err:
        logs.setup("INFO")
        LOGGER.error("Skill settings problem: %s", err)
        if request_type == "SessionEndedRequest":
            return _empty_response()
        return build_response(err.spoken)

    logs.setup(cfg.log_level, secrets=[cfg.ha_token, _get(event, "context", "System", "apiAccessToken") or ""])

    # Only answer requests from our own skill, and only recent ones.
    app_id = _application_id(event)
    if app_id != cfg.skill_id:
        LOGGER.warning("Rejected request for a different skill ID")
        return _empty_response()
    if not _is_fresh(request.get("timestamp")):
        LOGGER.warning("Rejected stale or undated request")
        return _empty_response()

    attributes = dict(_get(event, "session", "attributes") or {})
    LOGGER.info("Request %s %s", request_type, _get(request, "intent", "name") or "")

    if request_type == "LaunchRequest":
        device = _device(event)
        who, _ = _who(event)
        session_id = _get(event, "session", "sessionId") or str(time.time())
        attributes = {
            "launched": True,
            "conversation_id": conversation_id_for(device, who, session_id),
        }
        return build_response(
            messages.get(cfg.messages, "welcome"),
            cfg,
            end_session=False,
            reprompt=messages.get(cfg.messages, "reprompt"),
            attributes=attributes,
        )

    if request_type == "IntentRequest":
        intent = request.get("intent") or {}
        name = intent.get("name", "")
        if name == QUERY_INTENT:
            text = str(_get(intent, "slots", QUERY_SLOT, "value") or "").strip()
            if not text:
                return build_response(
                    messages.get(cfg.messages, "not_understood"),
                    cfg,
                    end_session=False,
                    reprompt=messages.get(cfg.messages, "reprompt"),
                    attributes=attributes,
                )
            return _ask_home_assistant(event, cfg, text, attributes)
        if name == SETUP_INTENT:
            return _setup_info(event, cfg, attributes)
        if name == "AMAZON.HelpIntent":
            attributes["launched"] = True
            attributes.setdefault("conversation_id", conversation_id_for(_device(event), _who(event)[0], _get(event, "session", "sessionId") or ""))
            return build_response(
                messages.get(cfg.messages, "help"),
                cfg,
                end_session=False,
                reprompt=messages.get(cfg.messages, "reprompt"),
                attributes=attributes,
            )
        if name in ("AMAZON.StopIntent", "AMAZON.CancelIntent", "AMAZON.NoIntent", "AMAZON.NavigateHomeIntent"):
            return build_response(messages.get(cfg.messages, "goodbye"), cfg)
        # AMAZON.FallbackIntent and anything unexpected.
        return build_response(
            messages.get(cfg.messages, "not_understood"),
            cfg,
            end_session=False,
            reprompt=messages.get(cfg.messages, "reprompt"),
            attributes=attributes,
        )

    if request_type == "SessionEndedRequest":
        reason = request.get("reason")
        error = request.get("error") or {}
        if error:
            LOGGER.warning("Session ended: %s %s %s", reason, error.get("type"), error.get("message"))
        else:
            LOGGER.info("Session ended: %s", reason)
        return _empty_response()

    if request_type == "System.ExceptionEncountered":
        LOGGER.warning("Alexa reported an error: %s", _get(request, "error", "type"))
        return _empty_response()

    return build_response(messages.get(cfg.messages, "not_understood"), cfg)


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    try:
        return handle_event(event or {})
    except Exception:
        LOGGER.exception("Unexpected error")
        return build_response(messages.DEFAULTS["error_internal"])
