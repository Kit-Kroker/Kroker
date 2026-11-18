"""A minimal raw JSON-RPC 2.0 stdio client for the MCP parity tests
(022 T020, plan T040).

Test-only, no new dependency: json + subprocess + threading. It speaks
just enough MCP to drive the real kroker-mcp binary — initialize,
tools/list, tools/call, the E1 `elicitation/create` server request with
a scripted answer, the E2 `input_required` retry with
`requestState` + `inputResponses`, notifications/progress collection,
and cancellation. Frame shape notes: MRTR results carry
``resultType: "input_required"`` and the retry sends
``inputResponses``/``requestState`` as top-level tools/call params
(rmcp 3.10 model.rs; SEP-2322).
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from typing import Any

OLD_PROTOCOL = "2025-11-25"
MRTR_PROTOCOL = "2026-07-28"


class McpError(Exception):
    """A JSON-RPC error response or a dead server."""


class McpStdioClient:
    def __init__(self, argv: list[str], env: dict[str, str] | None = None) -> None:
        # 026 T026: child_env -- the server this spawns is the sdlc CLI
        # family; its env must carry PYTHON_DOTENV_DISABLED so an
        # operator's repo-root .env cannot reach it (research R7).
        from tests.conftest import child_env

        self.env = child_env(**(env or {}))
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=self.env,
            bufsize=0,
        )
        self._lock = threading.Lock()
        self._waiters: dict[Any, queue.Queue] = {}
        self._next_id = 0
        # E1 elicitation script: ("accept", confirm_value) | ("decline",)
        # | ("cancel",) — cancel answers with a JSON-RPC error.
        self.elicitation: tuple[Any, ...] = ("accept", True)
        self.elicited: list[dict[str, Any]] = []
        self.progress: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # ---- transport -----------------------------------------------------

    def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") is not None and ("result" in msg or "error" in msg):
                waiter = self._waiters.get(msg["id"])
                if waiter is not None:
                    waiter.put(msg)
            elif "method" in msg and "id" in msg:
                self._on_server_request(msg)
            elif "method" in msg:
                self.notifications.append(msg)
                if msg["method"] == "notifications/progress":
                    self.progress.append(msg["params"])

    def _on_server_request(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        if method == "elicitation/create":
            params = msg.get("params") or {}
            self.elicited.append(params)
            kind, *rest = self.elicitation
            if kind == "accept":
                confirm = rest[0] if rest else True
                result: dict[str, Any] = {
                    "action": "accept",
                    "content": {"confirm": confirm},
                }
                self._respond(msg["id"], result)
            elif kind == "decline":
                self._respond(msg["id"], {"action": "decline"})
            else:  # cancel: the request dies, as a client-side cancel would
                self._respond_error(msg["id"], -32801, "elicitation cancelled")
        else:
            self._respond_error(msg["id"], -32601, f"test client cannot serve {method}")

    def _respond(self, rid: Any, result: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "id": rid, "result": result})

    def _respond_error(self, rid: Any, code: int, message: str) -> None:
        self._send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})

    def _send(self, msg: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        with self._lock:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            self.proc.stdin.flush()

    def _request(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0):
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            q: queue.Queue = queue.Queue()
            self._waiters[rid] = q
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty as e:
            raise McpError(f"{method} timed out after {timeout}s") from e
        finally:
            with self._lock:
                self._waiters.pop(rid, None)
        if "error" in msg:
            raise McpError(f"{method}: {msg['error']}")
        return msg["result"]

    # ---- protocol ------------------------------------------------------

    def initialize(
        self,
        protocol_version: str = OLD_PROTOCOL,
        capabilities: dict[str, Any] | None = None,
        client_name: str = "parity-client",
    ) -> dict[str, Any]:
        caps = capabilities if capabilities is not None else {"elicitation": {}}
        result = self._request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": caps,
                "clientInfo": {"name": client_name, "version": "0.0.0"},
            },
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def list_tools(self) -> dict[str, Any]:
        return self._request("tools/list", {})

    def call_tool(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        progress_token: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"name": name}
        if args is not None:
            params["arguments"] = args
        if progress_token is not None or meta is not None:
            m = dict(meta or {})
            if progress_token is not None:
                m["progressToken"] = progress_token
            params["_meta"] = m
        return self._request("tools/call", params)

    def call_tool_mrtr(
        self,
        name: str,
        args: dict[str, Any] | None,
        responses: dict[str, Any],
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call; on an input_required result, retry with the given
        inputResponses keyed by input-request key and the echoed
        requestState. Returns the FIRST result (input_required included)
        so tests can assert on both rounds."""
        first = self.call_tool(name, args, meta=meta)
        if first.get("resultType") != "input_required":
            return first
        return self.call_tool_retry(name, args, responses, first.get("requestState"), meta=meta)

    def call_tool_retry(
        self,
        name: str,
        args: dict[str, Any] | None,
        responses: dict[str, Any],
        request_state: Any,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """One manual MRTR round: top-level inputResponses/requestState."""
        params: dict[str, Any] = {"name": name, "arguments": args or {}}
        params["inputResponses"] = responses
        params["requestState"] = request_state
        if meta is not None:
            params["_meta"] = meta
        return self._request("tools/call", params)

    def cancel(self, request_id: Any) -> None:
        self._send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": request_id, "reason": "test cancel"},
            }
        )

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
