import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from alexa_requests import envelope, intent, launch, query
from alexa_ha import config, skill
from conftest import SKILL_ID


def speech_of(resp):
    return resp["response"].get("outputSpeech", {}).get("ssml", "")


def test_one_shot_ask(ha, cfg):
    resp = skill.lambda_handler(query("turn on the living room lights"))
    assert speech_of(resp) == "<speak>The living room lights are on.</speak>"
    assert resp["response"]["shouldEndSession"] is True
    run = ha.runs()[0]
    assert run["input"]["text"] == "turn on the living room lights"
    assert run["device_id"] == "ha-device-living"  # room context
    assert run["conversation_id"].startswith("alexa-")


def test_unmapped_device_sends_no_device_id(ha, cfg):
    skill.lambda_handler(query("hi", device="amzn1.ask.device.UNKNOWN"))
    assert "device_id" not in ha.runs()[0]


def test_open_then_back_and_forth(ha, cfg):
    resp = skill.lambda_handler(launch())
    assert resp["response"]["shouldEndSession"] is False
    assert "reprompt" in resp["response"]
    attrs = resp["sessionAttributes"]

    resp = skill.lambda_handler(query("what is the temperature", new=False, attributes=attrs))
    assert resp["response"]["shouldEndSession"] is False
    attrs2 = resp["sessionAttributes"]
    resp = skill.lambda_handler(query("and in the bedroom", new=False, attributes=attrs2))
    runs = ha.runs()
    assert runs[0]["conversation_id"] == runs[1]["conversation_id"] == attrs["conversation_id"]

    resp = skill.lambda_handler(query("no thanks", new=False, attributes=resp["sessionAttributes"]))
    assert resp["response"]["shouldEndSession"] is True
    assert len(ha.runs()) == 2  # "no thanks" ended the chat without bothering HA


def test_a_new_open_starts_a_new_conversation(ha, cfg):
    a = skill.lambda_handler(launch(session_id="s1"))["sessionAttributes"]["conversation_id"]
    b = skill.lambda_handler(launch(session_id="s2"))["sessionAttributes"]["conversation_id"]
    assert a != b


def test_conversations_are_separate_per_device_and_person(ha, cfg):
    skill.lambda_handler(query("a", device="amzn1.ask.device.LIVING"))
    skill.lambda_handler(query("b", device="amzn1.ask.device.BEDROOM"))
    skill.lambda_handler(query("c", device="amzn1.ask.device.LIVING", person="amzn1.ask.person.SID"))
    skill.lambda_handler(query("d", device="amzn1.ask.device.LIVING", person="amzn1.ask.person.ASHA"))
    skill.lambda_handler(query("e", device="amzn1.ask.device.LIVING"))
    ids = [r["conversation_id"] for r in ha.runs()]
    assert len(set(ids[:4])) == 4
    assert ids[4] == ids[0]  # same device, same person: quick follow-ups keep context


def test_ha_question_keeps_the_mic_open_and_yes_no_go_to_ha(ha, cfg):
    ha.answer = "Do you want me to turn off the fan too?"
    ha.continue_conversation = True
    resp = skill.lambda_handler(query("turn off the lights"))
    assert resp["response"]["shouldEndSession"] is False
    ha.continue_conversation = False
    ha.answer = "Okay, leaving the fan on."
    resp = skill.lambda_handler(query("no", new=False, attributes=resp["sessionAttributes"]))
    assert speech_of(resp) == "<speak>Okay, leaving the fan on.</speak>"
    assert [r["input"]["text"] for r in ha.runs()] == ["turn off the lights", "no"]
    assert resp["response"]["shouldEndSession"] is True


def test_markdown_answer_is_spoken_cleanly(ha, cfg):
    ha.answer = "**Bedroom**: 26.5°C\n- Humidity: 55%"
    resp = skill.lambda_handler(query("bedroom climate"))
    assert speech_of(resp) == "<speak>Bedroom: 26.5 degrees Celsius. Humidity: 55 percent</speak>"


def test_empty_answer_says_done(ha, cfg):
    ha.answer = ""
    assert speech_of(skill.lambda_handler(query("lights on"))) == "<speak>Done.</speak>"


def test_slow_ha_gets_a_clear_message_in_time(ha, cfg):
    ha.delay = 5
    start = time.monotonic()
    resp = skill.lambda_handler(query("think hard"))
    assert time.monotonic() - start < 3
    assert "taking too long" in speech_of(resp)
    assert resp["response"]["shouldEndSession"] is True


def test_ha_down(cfg):
    skill.set_config(config.parse({"ha_url": "http://127.0.0.1:9", "ha_token": "t-123456789", "skill_id": SKILL_ID, "allow_insecure_http": True}))
    assert "can't reach Home Assistant" in speech_of(skill.lambda_handler(query("hi")))


def test_bad_token_message(ha, cfg):
    ha.token = "rotated-token-123"
    assert "access token" in speech_of(skill.lambda_handler(query("hi")))


def test_ha_error_inside_open_session_keeps_it_open(ha, cfg):
    attrs = skill.lambda_handler(launch())["sessionAttributes"]
    ha.pipeline_error = "intent-failed"
    resp = skill.lambda_handler(query("hi", new=False, attributes=attrs))
    assert "couldn't handle" in speech_of(resp)
    assert resp["response"]["shouldEndSession"] is False


def test_other_skills_are_rejected(ha, cfg):
    resp = skill.lambda_handler(query("hi", skill_id="amzn1.ask.skill.someone-else"))
    assert resp["response"] == {}
    assert ha.runs() == []


def test_replayed_requests_are_rejected(ha, cfg):
    event = query("hi")
    event["request"]["timestamp"] = "2020-01-01T00:00:00Z"
    assert skill.lambda_handler(event)["response"] == {}
    assert ha.runs() == []


def test_missing_settings_are_spoken_not_crashed():
    skill.set_config(None)
    skill._CONFIG_ERROR = config.ConfigError("ha_url is not set", "The skill doesn't know your Home Assistant address yet.")
    skill._CONFIG_LOADED = True
    try:
        assert "address" in speech_of(skill.lambda_handler(query("hi")))
    finally:
        skill.set_config(None)


def test_garbage_event_does_not_crash(cfg):
    assert skill.lambda_handler({})["response"] == {}  # wrong skill id
    assert skill.lambda_handler(None)["response"] == {}


def test_internal_error_is_spoken(cfg, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(skill.ha_client, "converse", boom)
    assert "something went wrong" in speech_of(skill.lambda_handler(query("hi")))


def test_stop_help_fallback_and_session_end(ha, cfg):
    assert skill.lambda_handler(intent("AMAZON.StopIntent"))["response"]["shouldEndSession"] is True
    help_resp = skill.lambda_handler(intent("AMAZON.HelpIntent"))
    assert help_resp["response"]["shouldEndSession"] is False
    fb = skill.lambda_handler(intent("AMAZON.FallbackIntent"))
    assert "didn't catch" in speech_of(fb) and fb["response"]["shouldEndSession"] is False
    ended = envelope({"type": "SessionEndedRequest", "reason": "USER_INITIATED"})
    assert skill.lambda_handler(ended) == {"version": "1.0", "response": {}}
    assert ha.runs() == []


def test_empty_query(ha, cfg):
    event = query("")
    resp = skill.lambda_handler(event)
    assert "didn't catch" in speech_of(resp)
    assert ha.runs() == []


def test_setup_info_card(ha, cfg):
    resp = skill.lambda_handler(intent("SetupInfoIntent", device="amzn1.ask.device.NEW"))
    card = resp["response"]["card"]["content"]
    assert "amzn1.ask.device.NEW" in card and "not yet" in card
    assert ha.runs() == []


def test_token_never_logged(ha, cfg, caplog):
    skill.set_config(config.parse({"ha_url": ha.url, "ha_token": ha.token, "skill_id": SKILL_ID, "allow_insecure_http": True,
                                   "log_level": "DEBUG", "log_utterances": True}))
    with caplog.at_level(logging.DEBUG):
        skill.lambda_handler(query("hi"))
        logging.getLogger("x").info("leak %s and Bearer abc.def and %s", ha.token, "eyJa.eyJb.sig")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert ha.token not in text
    assert "eyJa.eyJb.sig" not in text
    assert "Bearer abc.def" not in text
    assert "Heard: 'hi'" in text


class _Capture(BaseHTTPRequestHandler):
    posts = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Capture.posts.append((self.path, self.headers["Authorization"], json.loads(body)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


def test_progressive_response_when_ha_is_slow(ha, cfg):
    server = HTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        cfg.progressive_response_after_seconds = 0.3
        ha.delay = 0.8
        _Capture.posts.clear()
        resp = skill.lambda_handler(query("slow one", api_endpoint="http://127.0.0.1:%d" % server.server_port))
        assert "lights are on" in speech_of(resp)
        assert len(_Capture.posts) == 1
        path, auth, body = _Capture.posts[0]
        assert path == "/v1/directives" and auth.startswith("Bearer ")
        assert body["directive"] == {"type": "VoicePlayer.Speak", "speech": "<speak>One moment.</speak>"}
        assert body["header"]["requestId"] == "amzn1.echo-api.request.1"

        _Capture.posts.clear()
        ha.delay = 0
        skill.lambda_handler(query("fast one", api_endpoint="http://127.0.0.1:%d" % server.server_port))
        assert _Capture.posts == []
    finally:
        server.shutdown()
