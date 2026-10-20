import time

import pytest

from alexa_ha import config, ha_client


def make_cfg(ha, **extra):
    raw = {"ha_url": ha.url, "ha_token": ha.token, "skill_id": "x.skill", "allow_insecure_http": True, "timeout_seconds": 2}
    raw.update(extra)
    return config.parse(raw)


def test_pipeline_run_text_in_text_out(ha):
    reply = ha_client.converse(make_cfg(ha), "turn on the lights", conversation_id="alexa-abc", device_id="dev1")
    assert reply.speech == "The living room lights are on."
    assert reply.conversation_id == "alexa-abc"
    run = ha.runs()[0]
    assert run["type"] == "assist_pipeline/run"
    assert run["start_stage"] == "intent" and run["end_stage"] == "intent"
    assert run["input"] == {"text": "turn on the lights"}
    assert run["device_id"] == "dev1"
    assert "pipeline" not in run  # preferred pipeline


def test_pipeline_by_name_is_resolved(ha):
    ha_client._PIPELINE_CACHE.clear()
    ha_client.converse(make_cfg(ha, pipeline="jev + sonnet"), "hi")
    assert ha.runs()[0]["pipeline"] == "01jpreferred00000000000000"


def test_pipeline_by_id_skips_lookup(ha):
    ha_client.converse(make_cfg(ha, pipeline="01jother000000000000000000"), "hi")
    assert not any(m.get("type") == "assist_pipeline/pipeline/list" for m in ha.received)
    assert ha.runs()[0]["pipeline"] == "01jother000000000000000000"


def test_unknown_pipeline_name(ha):
    ha_client._PIPELINE_CACHE.clear()
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(make_cfg(ha, pipeline="Nope"), "hi")
    assert err.value.kind == "pipeline_not_found"


def test_pipeline_not_found_from_ha(ha):
    ha.result_error = "pipeline-not-found"
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(make_cfg(ha, pipeline="01jgone0000000000000000000"), "hi")
    assert err.value.kind == "pipeline_not_found"


def test_agent_mode(ha):
    reply = ha_client.converse(make_cfg(ha, mode="agent", language="en"), "hi", conversation_id="c1")
    run = ha.runs()[0]
    assert run["type"] == "conversation/process"
    assert run["agent_id"] == "conversation.jev"
    assert run["language"] == "en"
    assert reply.speech


def test_bad_token(ha):
    ha.token = "something-else-123"
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(make_cfg(ha, ha_token="wrong-token-123456"), "hi")
    assert err.value.kind == "auth"


def test_http_401_is_auth(ha):
    ha.http_status = 401
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(make_cfg(ha), "hi")
    assert err.value.kind == "auth"


def test_http_502_is_unreachable(ha):
    ha.http_status = 502
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(make_cfg(ha), "hi")
    assert err.value.kind == "unreachable"


def test_slow_home_assistant_times_out_on_time(ha):
    ha.delay = 3
    start = time.monotonic()
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(make_cfg(ha, timeout_seconds=1), "hi")
    assert err.value.kind == "timeout"
    assert time.monotonic() - start < 1.5


def test_pipeline_error_event(ha):
    ha.pipeline_error = "intent-failed"
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(make_cfg(ha), "hi")
    assert err.value.kind == "agent_failed"


def test_nothing_listening():
    cfg = config.parse({"ha_url": "http://127.0.0.1:9", "ha_token": "t-123456789", "skill_id": "s", "allow_insecure_http": True})
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(cfg, "hi")
    assert err.value.kind == "unreachable"


def test_unresolvable_host():
    cfg = config.parse({"ha_url": "https://does-not-exist.invalid", "ha_token": "t-123456789", "skill_id": "s"})
    with pytest.raises(ha_client.HAError) as err:
        ha_client.converse(cfg, "hi", timeout=2)
    assert err.value.kind in ("unreachable", "timeout")
