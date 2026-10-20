import json

import pytest

from alexa_ha import config

BASE = {"ha_url": "https://abc.ui.nabu.casa/", "ha_token": "tok-123456789", "skill_id": "amzn1.ask.skill.1"}


def test_defaults():
    cfg = config.parse(dict(BASE))
    assert cfg.ha_url == "https://abc.ui.nabu.casa"
    assert cfg.websocket_url == "wss://abc.ui.nabu.casa/api/websocket"
    assert cfg.mode == "pipeline" and cfg.pipeline == ""
    assert cfg.agent_id == "conversation.jev"
    assert cfg.timeout_seconds <= 7


@pytest.mark.parametrize("missing", ["ha_url", "ha_token", "skill_id"])
def test_required(missing):
    raw = dict(BASE)
    raw[missing] = ""
    with pytest.raises(config.ConfigError) as err:
        config.parse(raw)
    assert err.value.spoken


def test_placeholders_count_as_missing():
    with pytest.raises(config.ConfigError):
        config.parse(dict(BASE, ha_token="YOUR-LONG-LIVED-ACCESS-TOKEN"))


def test_http_refused():
    with pytest.raises(config.ConfigError):
        config.parse(dict(BASE, ha_url="http://192.168.1.2:8123"))


def test_timeout_is_capped():
    assert config.parse(dict(BASE, timeout_seconds=30)).timeout_seconds == 7.0


def test_example_devices_are_ignored(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(dict(BASE, devices={"_example": "x", "amzn1.ask.device.A": "dev"})))
    assert config.load(str(p), environ={}).devices == {"amzn1.ask.device.A": "dev"}


def test_env_overrides(tmp_path):
    cfg = config.load(str(tmp_path / "missing.json"), environ={"HA_URL": "https://h.example", "HA_TOKEN": "env-token-1234", "SKILL_ID": "s", "HA_PIPELINE": "Jev + Sonnet"})
    assert cfg.ha_url == "https://h.example" and cfg.pipeline == "Jev + Sonnet"


def test_repr_hides_token():
    assert "tok-123456789" not in repr(config.parse(dict(BASE)))


def test_example_file_parses_but_needs_filling():
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "lambda", "config.example.json")
    raw = config.load_raw(path, environ={})
    with pytest.raises(config.ConfigError):
        config.parse(raw)
