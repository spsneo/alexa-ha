import json
import os

from alexa_ha import skill

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(*path):
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return json.load(f)


def test_interaction_model_matches_code():
    model = load("skill-package", "interactionModels", "custom", "en-IN.json")["interactionModel"]["languageModel"]
    intents = {i["name"]: i for i in model["intents"]}
    query = intents[skill.QUERY_INTENT]
    assert query["slots"][0]["name"] == skill.QUERY_SLOT
    assert query["samples"] == ["{" + skill.QUERY_SLOT + "}"]
    assert skill.SETUP_INTENT in intents
    for required in ("AMAZON.HelpIntent", "AMAZON.StopIntent", "AMAZON.CancelIntent", "AMAZON.NavigateHomeIntent", "AMAZON.FallbackIntent"):
        assert required in intents
    slot_types = {t["name"] for t in model["types"]}
    assert query["slots"][0]["type"] in slot_types
    name = model["invocationName"]
    assert name == name.lower() and not any(w in name.split() for w in ("alexa", "amazon", "echo", "skill", "app"))


def test_manifest_is_english_india():
    manifest = load("skill-package", "skill.json")["manifest"]
    assert list(manifest["publishingInformation"]["locales"]) == ["en-IN"]
    assert {"name": "alexa::person_id:read"} in manifest["permissions"]


def test_real_settings_file_is_git_ignored():
    with open(os.path.join(ROOT, ".gitignore")) as f:
        assert "lambda/config.json" in f.read().splitlines()
