#!/usr/bin/env python3
"""Check your settings against Home Assistant from your own computer.

    pip install websocket-client
    python3 tools/check_ha.py "what time is it"

It reads lambda/config.json (or the HA_URL / HA_TOKEN / SKILL_ID environment
variables), lists your Assist pipelines, sends one sentence through the same
code the skill uses, and prints the answer and how long it took. The token is
never printed.
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lambda"))

from alexa_ha import config, ha_client, speech  # noqa: E402


def main() -> int:
    text = " ".join(sys.argv[1:]) or "what time is it"
    try:
        cfg = config.load()
    except config.ConfigError as err:
        print("Settings problem: %s" % err)
        return 1
    print("Home Assistant: %s (mode: %s)" % (cfg.ha_url, cfg.mode))

    try:
        with ha_client._Connection(cfg, ha_client._Deadline(cfg.timeout_seconds)) as conn:
            msg_id = conn.send({"type": "assist_pipeline/pipeline/list"})
            result = conn.wait_result(msg_id).get("result") or {}
    except ha_client.HAError as err:
        print("Could not connect: %s" % err)
        return 1
    preferred = result.get("preferred_pipeline")
    print("Pipelines:")
    chosen = None
    for p in result.get("pipelines", []):
        mark = " (preferred)" if p["id"] == preferred else ""
        print("  - %s  id=%s  agent=%s  prefer local=%s%s" % (p["name"], p["id"], p.get("conversation_engine"), p.get("prefer_local_intents"), mark))
        if (cfg.pipeline and cfg.pipeline.lower() in (p["name"].lower(), p["id"].lower())) or (not cfg.pipeline and p["id"] == preferred):
            chosen = p
    if cfg.mode == "pipeline":
        if not chosen:
            print("WARNING: pipeline %r not found." % cfg.pipeline)
        else:
            print("The skill will use: %s" % chosen["name"])
            if cfg.agent_id and chosen.get("conversation_engine") != cfg.agent_id:
                print("Note: that pipeline uses agent %s, not %s." % (chosen.get("conversation_engine"), cfg.agent_id))

    print("\nYou: %s" % text)
    start = time.monotonic()
    try:
        reply = ha_client.converse(cfg, text, conversation_id="alexa-check-ha")
    except ha_client.HAError as err:
        print("Failed after %.2fs: %s" % (time.monotonic() - start, err))
        return 1
    took = time.monotonic() - start
    print("Home Assistant: %s" % reply.speech)
    print("Alexa will say: %s" % speech.to_ssml(speech.clean_text(reply.speech, cfg.max_speech_chars), cfg.hindi_ssml))
    print("Took %.2fs (Alexa allows 8s; the skill gives up at %.1fs)." % (took, cfg.timeout_seconds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
