"""Build Alexa request envelopes the way Alexa sends them."""

from datetime import datetime, timezone

from conftest import SKILL_ID


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def envelope(request, device="amzn1.ask.device.LIVING", person=None, user="amzn1.ask.account.USER",
             session_id="amzn1.echo-api.session.1", new=True, attributes=None, skill_id=SKILL_ID,
             api_endpoint=None):
    system = {
        "application": {"applicationId": skill_id},
        "user": {"userId": user},
        "device": {"deviceId": device, "supportedInterfaces": {}},
        "apiEndpoint": api_endpoint or "https://api.amazonalexa.com",
        "apiAccessToken": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl",
    }
    if person:
        system["person"] = {"personId": person}
    request.setdefault("requestId", "amzn1.echo-api.request.1")
    request.setdefault("timestamp", now_iso())
    request.setdefault("locale", "en-IN")
    return {
        "version": "1.0",
        "session": {
            "new": new,
            "sessionId": session_id,
            "application": {"applicationId": skill_id},
            "attributes": attributes or {},
            "user": {"userId": user},
        },
        "context": {"System": system},
        "request": request,
    }


def query(text, **kw):
    return envelope({"type": "IntentRequest", "intent": {"name": "QueryIntent", "confirmationStatus": "NONE",
                     "slots": {"query": {"name": "query", "value": text, "confirmationStatus": "NONE"}}}}, **kw)


def intent(name, **kw):
    return envelope({"type": "IntentRequest", "intent": {"name": name, "confirmationStatus": "NONE"}}, **kw)


def launch(**kw):
    return envelope({"type": "LaunchRequest"}, **kw)
