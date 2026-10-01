"""A local counting provider stub for the single-retry-layer tests (004 T008).

A real 127.0.0.1 HTTP server, NOT httpx/respx mocking: the provider SDKs use
httpx2, and the whole point of FR-008 is to count the HTTP requests the SDK
stack beneath one model request — an interceptor in the httpx layer would
answer a different question.

Serves anthropic-protocol bodies on ``/v1/messages`` and openai-protocol
bodies on ``/v1/chat/completions`` / ``/v1/responses``. Modes:

- ``always_429`` — every request answers 429 (rate-limit body, no
  retry-after header) so both the SDK retry layer and the engine attempt
  budget engage;
- ``fail_once`` — the first request answers 429, the rest answer a valid
  message (US3 scenario 2: one transient failure then success);
- ``always_400`` — every request answers 400 (non-retryable provider
  error, E7).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ANTHROPIC_429 = {
    "type": "error",
    "error": {"type": "rate_limit_error", "message": "stub: rate limited"},
}
_ANTHROPIC_400 = {
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "stub: bad request"},
}
_ANTHROPIC_VALID = {
    "id": "msg_stub",
    "type": "message",
    "role": "assistant",
    "model": "glm-5.2",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 1, "output_tokens": 1},
}

_OPENAI_429 = {
    "error": {
        "message": "stub: rate limited",
        "type": "rate_limit_error",
        "code": "rate_limit_exceeded",
    }
}
_OPENAI_400 = {
    "error": {"message": "stub: bad request", "type": "invalid_request_error", "code": None}
}
_OPENAI_CHAT_VALID = {
    "id": "chatcmpl-stub",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-5.2",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}
_OPENAI_RESPONSES_VALID = {
    "id": "resp_stub",
    "object": "response",
    "status": "completed",
    "output": [
        {
            "type": "message",
            "id": "msg_stub",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "ok"}],
        }
    ],
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


class ProviderStub:
    """Counting stub server. ``base_url`` is what ANTHROPIC_BASE_URL /
    OPENAI_BASE_URL should be set to."""

    def __init__(self, mode: str = "always_429") -> None:
        self.mode = mode
        self.count = 0
        self.requests: list[tuple[str, str]] = []  # (path, mode-at-request)
        self._lock = threading.Lock()
        stub = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _reply(self, status: int, body: dict[str, object]) -> None:
                payload = json.dumps(body).encode()
                self.send_response(status)
                # Deliberately NO retry-after: the SDK's retry decision must
                # be driven by the status code alone.
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                # self.path carries the query string ("?beta=true"); the
                # protocol pick is on the path alone.
                path = self.path.split("?", 1)[0]
                with stub._lock:
                    stub.count += 1
                    stub.requests.append((path, stub.mode))
                    mode = stub.mode
                anthropic = path.endswith("/v1/messages")
                if mode == "always_429":
                    self._reply(429, _ANTHROPIC_429 if anthropic else _OPENAI_429)
                    return
                if mode == "always_400":
                    self._reply(400, _ANTHROPIC_400 if anthropic else _OPENAI_400)
                    return
                if mode == "fail_once":
                    if stub.count == 1:
                        self._reply(429, _ANTHROPIC_429 if anthropic else _OPENAI_429)
                        return
                    if anthropic:
                        self._reply(200, _ANTHROPIC_VALID)
                    elif self.path.endswith("/v1/responses"):
                        self._reply(200, _OPENAI_RESPONSES_VALID)
                    else:
                        self._reply(200, _OPENAI_CHAT_VALID)
                    return
                self._reply(500, {"error": f"stub: unknown mode {mode!r}"})

            def log_message(self, *args: object) -> None:
                pass  # keep pytest output pristine

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> None:
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> ProviderStub:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
