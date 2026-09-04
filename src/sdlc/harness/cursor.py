"""Cursor harness adapter.

CLI asymmetries handled here:
  * cursor-agent: mirrors Claude Code's stream-json output;
                  headless run with `--force`.
"""

from __future__ import annotations

import json
import logging

from ..core.models import HarnessKind
from .base import SUMMARY_MAX, CodingHarness, HarnessRequest
from .models import (
    HarnessRunResult,
    HarnessSession,
    SessionEvent,
)

_log = logging.getLogger(__name__)


class CursorHarness(CodingHarness):
    kind = HarnessKind.CURSOR
    cli = "cursor-agent"
    # E-24 pin: None = declared-but-unpinned. Set once the CLI is installed
    # and a real `cursor-agent --version` can be captured. A None pin is
    # skipped by check_harness_versions (no spurious drift warning).
    expected_version = None

    def __init__(self, force: bool = True):
        # Headless auto-approve of edits/commands (≈ claude --permission-mode
        # acceptEdits / opencode --auto). Without it a non-interactive run
        # blocks on an approval that never arrives -> empty diff.
        self.force = force

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        # cursor-agent mirrors Claude Code's Agent-SDK stream-json output.
        cmd = ["cursor-agent", "-p", req.prompt, "--output-format", "stream-json"]
        if req.model:
            cmd += ["--model", req.model]
        if req.session_id:
            cmd += ["--resume", req.session_id]
        if self.force:
            cmd.append("--force")
        return cmd + req.extra_args

    # containment: inherits the base frozenset() — cursor-agent surfaces
    # neither a deny-config nor a hook flag, so it FAILS CLOSED when
    # containment is enabled (ADR-17). This is a deliberate, known cost:
    # cursor cells drop out of a contained benchmark sweep rather than
    # running unpoliced beside contained ones.

    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
        session_id = cost = summary = None
        input_tokens = output_tokens = None
        payload = None
        for ln in stdout.strip().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "result":
                payload = ev
        if payload is not None:
            session_id = payload.get("session_id")
            cost = payload.get("total_cost_usd")  # ASSUMPTION: may be absent
            # -> cursor cells are
            # quality-only (spec §5)
            summary = payload.get("result") or payload.get("content")
            usage = payload.get("usage") or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
        else:
            _log.warning(
                "cursor parse: no result event in stream, falling back to raw stdout as summary"
            )
            summary = stdout
        return HarnessRunResult(
            harness=self.kind,
            session_id=session_id,
            exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX],
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # Cursor tool name -> canonical event kind + which input field is the
    # target. ASSUMPTION (spec §5): confirm these names against a real
    # `cursor-agent --output-format stream-json` transcript before trusting
    # the live cursor axis. Unmapped tools degrade to a generic tool_call.
    _TOOL_MAP = {
        "read_file": ("file_read", "path"),
        "edit_file": ("file_write", "path"),
        "write": ("file_write", "path"),
        "run_terminal_cmd": ("command", "command"),
        "shell": ("command", "command"),
    }

    def normalise_session(self, stdout: str) -> HarnessSession:
        events: list[SessionEvent] = []
        session_id = model = None
        cost = in_tok = out_tok = None
        for ln in stdout.strip().splitlines():
            try:
                ev = json.loads(ln.strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            session_id = session_id or ev.get("session_id")
            etype = ev.get("type")
            if etype == "system":
                model = model or ev.get("model")
            elif etype in ("assistant", "user"):
                msg = ev.get("message") or {}
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text" and block.get("text"):
                        events.append(SessionEvent(kind="model_turn", text=block["text"]))
                    elif btype == "tool_use":
                        name = block.get("name") or "tool"
                        kind, field = self._TOOL_MAP.get(name, ("tool_call", ""))
                        inp = block.get("input") or {}
                        target = inp.get(field) if field else json.dumps(inp)[:500]
                        events.append(SessionEvent(kind=kind, tool=name, target=target))
                    elif btype == "tool_result":
                        content = block.get("content")
                        if isinstance(content, list):
                            content = " ".join(
                                c.get("text", "") for c in content if isinstance(c, dict)
                            )
                        events.append(
                            SessionEvent(
                                kind="tool_result",
                                exit_code=1 if block.get("is_error") else None,
                                text=(content or "")[:2000] or None,
                            )
                        )
            elif etype == "result":
                usage = ev.get("usage") or {}
                cost = ev.get("total_cost_usd")
                in_tok = usage.get("input_tokens")
                out_tok = usage.get("output_tokens")
                events.append(SessionEvent(kind="result", text=(ev.get("result") or "")[:2000]))
        return HarnessSession(
            harness=self.kind,
            session_id=session_id,
            model=model,
            events=events,
            cost_usd=cost,
            input_tokens=in_tok,
            output_tokens=out_tok,
        )
