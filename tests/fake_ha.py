"""A tiny fake Home Assistant WebSocket server for tests.

It speaks the same auth handshake, ``assist_pipeline/run`` (intent stage
only), ``assist_pipeline/pipeline/list`` and ``conversation/process`` as the
real thing, and records what it received.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from websockets.sync.server import serve

PIPELINES = [
    {"id": "01jpreferred00000000000000", "name": "Jev + Sonnet", "conversation_engine": "conversation.jev", "prefer_local_intents": True},
    {"id": "01jother000000000000000000", "name": "Home Assistant", "conversation_engine": "conversation.home_assistant", "prefer_local_intents": False},
]


class FakeHA:
    def __init__(self, token: str = "good-token-123456"):
        self.token = token
        self.delay = 0.0
        self.answer = "The living room lights are on."
        self.response_type = "action_done"
        self.continue_conversation = False
        self.pipeline_error: Optional[str] = None  # error event code
        self.result_error: Optional[str] = None  # error on the run command itself
        self.http_status: Optional[int] = None
        self.received: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self._server = serve(self._handler, "127.0.0.1", 0, process_request=self._process_request)
        self.port = self._server.socket.getsockname()[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d" % self.port

    def close(self) -> None:
        self._server.shutdown()

    def runs(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [m for m in self.received if m.get("type") in ("assist_pipeline/run", "conversation/process")]

    def _process_request(self, connection, request):
        if self.http_status:
            return connection.respond(self.http_status, "nope\n")
        return None

    def _handler(self, ws) -> None:
        ws.send(json.dumps({"type": "auth_required", "ha_version": "2026.10.0"}))
        auth = json.loads(ws.recv())
        with self.lock:
            self.received.append(auth)
        if auth.get("access_token") != self.token:
            ws.send(json.dumps({"type": "auth_invalid", "message": "Invalid access token or password"}))
            return
        ws.send(json.dumps({"type": "auth_ok", "ha_version": "2026.10.0"}))
        try:
            for raw in ws:
                msg = json.loads(raw)
                with self.lock:
                    self.received.append(msg)
                self._dispatch(ws, msg)
        except Exception:
            pass

    def _conversation_result(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "response": {
                "speech": {"plain": {"speech": self.answer, "extra_data": None}},
                "card": {},
                "language": "en",
                "response_type": self.response_type,
                "data": {"targets": [], "success": [], "failed": []},
            },
            "conversation_id": msg.get("conversation_id") or "01JNEWCONVERSATION00000000",
            "continue_conversation": self.continue_conversation,
        }

    def _dispatch(self, ws, msg: Dict[str, Any]) -> None:
        mid = msg.get("id")
        mtype = msg.get("type")
        if mtype == "assist_pipeline/pipeline/list":
            ws.send(json.dumps({"id": mid, "type": "result", "success": True,
                                "result": {"pipelines": PIPELINES, "preferred_pipeline": PIPELINES[0]["id"]}}))
            return
        if mtype == "conversation/process":
            time.sleep(self.delay)
            ws.send(json.dumps({"id": mid, "type": "result", "success": True, "result": self._conversation_result(msg)}))
            return
        if mtype == "assist_pipeline/run":
            if self.result_error:
                ws.send(json.dumps({"id": mid, "type": "result", "success": False,
                                    "error": {"code": self.result_error, "message": "Pipeline not found"}}))
                return
            ws.send(json.dumps({"id": mid, "type": "result", "success": True, "result": None}))

            def event(etype: str, data: Any) -> None:
                ws.send(json.dumps({"id": mid, "type": "event", "event": {"type": etype, "data": data, "timestamp": "now"}}))

            event("run-start", {"pipeline": msg.get("pipeline") or PIPELINES[0]["id"], "language": "en", "conversation_id": msg.get("conversation_id")})
            event("intent-start", {"engine": "conversation.jev", "language": "en", "intent_input": msg["input"]["text"],
                                   "conversation_id": msg.get("conversation_id"), "device_id": msg.get("device_id"), "prefer_local_intents": True})
            time.sleep(self.delay)
            if self.pipeline_error:
                event("error", {"code": self.pipeline_error, "message": "boom"})
                event("run-end", None)
                return
            event("intent-progress", {"chat_log_delta": {"content": "partial"}})
            event("intent-end", {"processed_locally": False, "intent_output": self._conversation_result(msg)})
            event("run-end", None)
            return
        ws.send(json.dumps({"id": mid, "type": "result", "success": False, "error": {"code": "unknown_command", "message": "Unknown command."}}))
