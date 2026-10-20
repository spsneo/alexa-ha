import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lambda"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from alexa_ha import config, skill  # noqa: E402
from fake_ha import FakeHA  # noqa: E402

SKILL_ID = "amzn1.ask.skill.test-0000"


@pytest.fixture
def ha():
    server = FakeHA()
    yield server
    server.close()


@pytest.fixture
def cfg(ha):
    c = config.parse(
        {
            "ha_url": ha.url,
            "ha_token": ha.token,
            "skill_id": SKILL_ID,
            "allow_insecure_http": True,
            "timeout_seconds": 2,
            "progressive_response_after_seconds": 0,
            "devices": {"amzn1.ask.device.LIVING": "ha-device-living"},
        }
    )
    skill.set_config(c)
    yield c
    skill.set_config(None)
