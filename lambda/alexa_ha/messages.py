"""Things the skill says itself. Override any of them with "messages" in config.json."""

DEFAULTS = {
    "welcome": "Hi, Home Assistant is listening. What would you like?",
    "reprompt": "Anything else?",
    "help": (
        "Just say what you'd say to your Home Assistant, like, turn on the living room lights, "
        "or, what's the temperature outside. Say stop when you're done. What would you like?"
    ),
    "goodbye": "Okay.",
    "not_understood": "Sorry, I didn't catch that. Please say it again.",
    "done": "Done.",
    "progress": "One moment.",
    "setup_info": "I've sent this device's setup details to the Alexa app.",
    "error_timeout": "Home Assistant is taking too long to answer. Please try again.",
    "error_unreachable": "I can't reach Home Assistant right now. Please check that it's online.",
    "error_auth": "Home Assistant didn't accept the skill's access token. Please check the token in the skill settings.",
    "error_pipeline_not_found": "I couldn't find the Assist pipeline named in the skill settings.",
    "error_agent_failed": "Home Assistant couldn't handle that request. Please try again.",
    "error_bad_response": "Home Assistant sent an answer I couldn't understand.",
    "error_internal": "Sorry, something went wrong in the skill.",
}


def get(overrides: dict, key: str) -> str:
    return (overrides or {}).get(key) or DEFAULTS[key]
