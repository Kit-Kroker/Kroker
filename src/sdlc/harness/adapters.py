"""Coding-harness abstraction.

A harness executes an autonomous coding task inside a git worktree.
Both adapters normalize to HarnessRunResult. They are invoked from a
Temporal *activity* (never from workflow code) — see activities.py.

Asymmetries handled here:
  * claude:   `claude -p "<prompt>" --output-format json`; stdin supported;
              resume with `--resume <session_id>` (scoped to cwd/worktree).
  * opencode: `opencode run "<prompt>" --format json -m provider/model`;
              prompt is a positional arg (there is NO -p flag);
              continue with `-s <session_id>`; optional `--attach <url>`
              to reuse a warm `opencode serve` instance.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models import HarnessKind, HarnessRunResult, HarnessSession, SessionEvent

SUMMARY_MAX = 4000  # keep Temporal payloads small

_log = logging.getLogger(__name__)

# Best-effort model → context window (tokens). Substring match; extend as
# needed. Used only to compute the context ceiling (Finding #7); unknown
# models fall back to the resume counter.
CONTEXT_WINDOWS = {
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
    "gpt-5": 400_000,
    "glm": 1_000_000,
}


def context_window_for(model: str | None) -> int | None:
    if not model:
        return None
    m = model.lower()
    for key, win in CONTEXT_WINDOWS.items():
        if key in m:
            return win
    return None


# Env allowlist (Finding #8): the harness receives ONLY these vars from the
# worker environment, plus credentials deliberately injected via req.env.
# Never the worker's full os.environ (that is a bigger secret channel than
# the prompt). Covers POSIX + Windows toolchain essentials.
ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP",
    "SYSTEMROOT", "SYSTEMDRIVE", "USERPROFILE", "PATHEXT", "COMSPEC",
    "GIT_EXEC_PATH", "GIT_SSH", "SSH_AUTH_SOCK",
)


def build_env(req_env: dict[str, str],
              allowlist: tuple[str, ...] = ENV_ALLOWLIST) -> dict[str, str]:
    """Curated child environment: allowlisted worker vars, then the
    request's injected (repo-scoped, short-TTL) credentials."""
    env = {k: os.environ[k] for k in allowlist if k in os.environ}
    env.update(req_env)
    return env


@dataclass
class HarnessRequest:
    prompt: str
    cwd: str                              # the task's git worktree
    model: str | None = None
    session_id: str | None = None         # resume/continue a prior run
    timeout_s: int = 3600
    env: dict[str, str] = field(default_factory=dict)
    extra_args: list[str] = field(default_factory=list)


def _log_live_event(line: str) -> None:
    """Best-effort live logging of one opencode --format json event line as
    it streams. Never raises: a line that doesn't parse (e.g. Claude Code's
    single final JSON payload, which isn't line-delimited) is silently
    skipped — parse-time failure logging is handled separately in parse()."""
    line = line.strip()
    if not line:
        return
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return
    if not isinstance(ev, dict):
        return
    ev_type = ev.get("type")
    session_id = ev.get("sessionID") or ev.get("session_id")
    if ev_type == "step_start":
        _log.info("harness step_start session_id=%s", session_id)
    elif ev_type == "step_finish":
        part = ev.get("part")
        if not isinstance(part, dict):
            part = {}
        tokens = part.get("tokens")
        if not isinstance(tokens, dict):
            tokens = {}
        _log.info("harness step_finish session_id=%s input_tokens=%s "
                  "output_tokens=%s cost_usd=%s", session_id,
                  tokens.get("input"), tokens.get("output"), part.get("cost"))
    elif ev_type == "text":
        part = ev.get("part")
        if not isinstance(part, dict):
            part = {}
        _log.debug("harness text session_id=%s chars=%d", session_id,
                   len(part.get("text") or ""))


class CodingHarness(ABC):
    kind: HarnessKind

    @abstractmethod
    def build_cmd(self, req: HarnessRequest) -> list[str]: ...

    @abstractmethod
    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult: ...

    def normalise_session(self, stdout: str) -> HarnessSession:
        """Canonical transcript from this harness's stdout stream (ADR-16:
        normalisation is the adapter's job). Base default: metadata-only
        session with no events — a harness without a normaliser degrades
        to digest-of-nothing rather than failing capture."""
        return HarnessSession(harness=self.kind)

    async def run(self, req: HarnessRequest,
                  heartbeat=None) -> HarnessRunResult:
        cmd = self.build_cmd(req)
        # Resolve via PATH — Windows npm shims are .cmd files that
        # CreateProcess can't find without an explicit extension.
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd[0] = resolved
        _log.debug("harness start kind=%s model=%s session_id=%s cwd=%s",
                   self.kind.value, req.model, req.session_id, req.cwd)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=req.cwd,
            env=build_env(req.env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10_000_000,  # opencode text events can exceed the 64KB
                               # default StreamReader line limit
        )

        async def _pump() -> bytes:
            chunks: list[bytes] = []
            buf = b""
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    _log_live_event(line.decode(errors="replace"))
                if heartbeat:
                    heartbeat()          # keep the Temporal activity alive
            if buf.strip():
                _log_live_event(buf.decode(errors="replace"))
            return b"".join(chunks)

        async def _pump_stderr() -> str:
            # Drained concurrently with stdout — an unread stderr pipe can
            # fill its OS buffer and deadlock the child if it writes enough.
            chunks: list[bytes] = []
            size = 0
            assert proc.stderr is not None
            while True:
                chunk = await proc.stderr.read(65536)
                if not chunk:
                    break
                if size < SUMMARY_MAX:
                    chunks.append(chunk)
                    size += len(chunk)
            return b"".join(chunks).decode(errors="replace")[:SUMMARY_MAX]

        start = time.monotonic()
        try:
            stdout_b, stderr_s, _ = await asyncio.wait_for(
                asyncio.gather(_pump(), _pump_stderr(), proc.wait()),
                timeout=req.timeout_s,
            )
        except asyncio.TimeoutError:
            proc.kill()
            _log.warning("harness timeout kind=%s cwd=%s cmd=%s",
                        self.kind.value, req.cwd, cmd)
            raise
        except Exception:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise
        duration_s = time.monotonic() - start

        result = self.parse(stdout_b.decode(errors="replace"),
                            proc.returncode or 0)
        # E-38: keep the raw stream for activity-side capture. PrivateAttr —
        # never serialized, never enters workflow state.
        result._raw_stdout = stdout_b.decode(errors="replace")
        if result.context_window is None:
            result.context_window = context_window_for(req.model)

        _log.info("harness done kind=%s exit_code=%s session_id=%s "
                  "duration_s=%.1f input_tokens=%s output_tokens=%s cost_usd=%s",
                  self.kind.value, result.exit_code, result.session_id,
                  duration_s, result.input_tokens, result.output_tokens,
                  result.cost_usd)
        if result.exit_code != 0 or stderr_s:
            _log.warning("harness stderr kind=%s exit_code=%s stderr=%s",
                        self.kind.value, result.exit_code, stderr_s)
        return result


class ClaudeCodeHarness(CodingHarness):
    kind = HarnessKind.CLAUDE_CODE

    def __init__(self, allowed_tools: str = "Read,Edit,Write,Bash",
                 permission_mode: str = "acceptEdits"):
        self.allowed_tools = allowed_tools
        self.permission_mode = permission_mode

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        cmd = [
            "claude", "-p", req.prompt,
            # E-38: stream-json emits the full event stream (transcript
            # source) AND a final `result` event with the same fields the
            # old plain-json payload carried. --verbose is required by the
            # CLI for stream-json in print mode.
            "--output-format", "stream-json", "--verbose",
            "--allowedTools", self.allowed_tools,
            "--permission-mode", self.permission_mode,
        ]
        if req.model:
            cmd += ["--model", req.model]
        if req.session_id:
            cmd += ["--resume", req.session_id]
        return cmd + req.extra_args

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
            cost = payload.get("total_cost_usd")
            summary = payload.get("result") or payload.get("content")
            usage = payload.get("usage") or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
        else:
            _log.warning("claude parse: no result event in stream, falling "
                         "back to raw stdout as summary")
            summary = stdout
        return HarnessRunResult(
            harness=self.kind, session_id=session_id, exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX], cost_usd=cost,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )

    # tool name -> canonical event kind + which input field is the target
    _TOOL_MAP = {
        "Read": ("file_read", "file_path"),
        "Write": ("file_write", "file_path"),
        "Edit": ("file_write", "file_path"),
        "Bash": ("command", "command"),
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
                        events.append(SessionEvent(kind="model_turn",
                                                   text=block["text"]))
                    elif btype == "tool_use":
                        name = block.get("name") or "tool"
                        kind, field = self._TOOL_MAP.get(name, ("tool_call", ""))
                        inp = block.get("input") or {}
                        target = inp.get(field) if field else json.dumps(inp)[:500]
                        events.append(SessionEvent(kind=kind, tool=name,
                                                   target=target))
                    elif btype == "tool_result":
                        content = block.get("content")
                        if isinstance(content, list):
                            content = " ".join(
                                c.get("text", "") for c in content
                                if isinstance(c, dict))
                        events.append(SessionEvent(
                            kind="tool_result",
                            exit_code=1 if block.get("is_error") else None,
                            text=(content or "")[:2000] or None))
            elif etype == "result":
                usage = ev.get("usage") or {}
                cost = ev.get("total_cost_usd")
                in_tok = usage.get("input_tokens")
                out_tok = usage.get("output_tokens")
                events.append(SessionEvent(kind="result",
                                           text=(ev.get("result") or "")[:2000]))
        return HarnessSession(harness=self.kind, session_id=session_id,
                              model=model, events=events, cost_usd=cost,
                              input_tokens=in_tok, output_tokens=out_tok)


class OpenCodeHarness(CodingHarness):
    kind = HarnessKind.OPENCODE

    def __init__(self, attach_url: str | None = None):
        # Point at a running `opencode serve` to skip MCP cold boots.
        self.attach_url = attach_url

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        cmd = ["opencode", "run"]
        # --pure: skip external plugins. The user's global config loads the
        # superpowers plugin, whose brainstorming skill auto-activates on
        # "creative work" and makes the model ask clarifying questions
        # instead of implementing -> the non-interactive coding activity
        # stalls waiting for an answer that never comes. Config-level
        # plugin:[] does NOT work here — opencode auto-discovers installed
        # plugins from its cache regardless of the plugin array, so the
        # skills persist (confirmed via `opencode debug config`). --pure is
        # the only mechanism that actually excludes them, and it keeps the
        # built-in Read/Write/Edit/Bash tools (verified end-to-end).
        # --auto: non-interactive; without it every tool call blocks on a
        # permission approval that never arrives -> empty diff. Mirrors
        # claude's --permission-mode acceptEdits.
        cmd += ["--pure", "--auto"]
        if req.model:
            cmd += ["-m", req.model]
        if req.session_id:
            cmd += ["-s", req.session_id]
        if self.attach_url:
            cmd += ["--attach", self.attach_url]
        cmd += ["--format", "json"]
        cmd += req.extra_args
        cmd.append(req.prompt)            # positional, must come last
        return cmd

    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
        """Parse opencode's ``--format json`` event stream.

        opencode emits one JSON object per line: ``step_start``, one or more
        ``text`` chunks, then ``step_finish``. The content lives in
        ``part.text`` on ``text`` events; tokens/cost live in ``part`` on the
        ``step_finish`` event. Walking the whole stream (not just the last
        line) is required — the last line is ``step_finish`` with no text."""
        session_id = None
        text_parts: list[str] = []
        # opencode emits one step_finish per step (tool call / turn), each
        # reporting that step's own tokens/cost, not a running total — so
        # these must be summed across every step_finish, not just the first.
        input_tokens = output_tokens = 0
        cost = 0.0
        saw_tokens = saw_cost = False
        parsed_any = False
        for ln in stdout.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                _log.debug("opencode parse: skipping malformed line: %s", ln[:200])
                continue
            parsed_any = True
            session_id = session_id or ev.get("sessionID") or ev.get("session_id")
            part = ev.get("part") or {}
            if ev.get("type") == "text" and part.get("text"):
                text_parts.append(part["text"])
            if ev.get("type") == "step_finish":
                tokens = part.get("tokens") or {}
                if isinstance(tokens.get("input"), (int, float)):
                    input_tokens += tokens["input"]
                    saw_tokens = True
                if isinstance(tokens.get("output"), (int, float)):
                    output_tokens += tokens["output"]
                    saw_tokens = True
                if isinstance(part.get("cost"), (int, float)):
                    cost += part["cost"]
                    saw_cost = True
        input_tokens = input_tokens if saw_tokens else None
        output_tokens = output_tokens if saw_tokens else None
        cost = cost if saw_cost else None
        if not parsed_any:
            _log.warning("opencode parse: no events parsed from stdout "
                         "(parsed_any=False); falling back to raw stdout")
        summary = "\n".join(text_parts) if parsed_any else stdout
        return HarnessRunResult(
            harness=self.kind, session_id=session_id, exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX], cost_usd=cost,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )

    # opencode tool name -> canonical kind + target field in state.input
    _TOOL_MAP = {
        "read": ("file_read", "filePath"),
        "write": ("file_write", "filePath"),
        "edit": ("file_write", "filePath"),
        "bash": ("command", "command"),
    }

    def normalise_session(self, stdout: str) -> HarnessSession:
        events: list[SessionEvent] = []
        session_id = None
        in_tok = out_tok = 0
        cost = 0.0
        saw_tokens = saw_cost = False
        for ln in stdout.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            session_id = session_id or ev.get("sessionID") or ev.get("session_id")
            part = ev.get("part") or {}
            etype = ev.get("type")
            if etype == "text" and part.get("text"):
                events.append(SessionEvent(kind="model_turn",
                                           text=part["text"][:2000]))
            elif etype == "tool":
                name = (part.get("tool") or "tool").lower()
                kind, field = self._TOOL_MAP.get(name, ("tool_call", ""))
                state = part.get("state") or {}
                inp = state.get("input") or {}
                target = inp.get(field) if field else json.dumps(inp)[:500]
                events.append(SessionEvent(
                    kind=kind, tool=name, target=target,
                    exit_code=1 if state.get("status") == "error" else None))
            elif etype == "step_finish":
                tokens = part.get("tokens") or {}
                if isinstance(tokens.get("input"), (int, float)):
                    in_tok += tokens["input"]; saw_tokens = True
                if isinstance(tokens.get("output"), (int, float)):
                    out_tok += tokens["output"]; saw_tokens = True
                if isinstance(part.get("cost"), (int, float)):
                    cost += part["cost"]; saw_cost = True
        return HarnessSession(
            harness=self.kind, session_id=session_id, events=events,
            input_tokens=in_tok if saw_tokens else None,
            output_tokens=out_tok if saw_tokens else None,
            cost_usd=cost if saw_cost else None)


HARNESSES: dict[HarnessKind, CodingHarness] = {
    HarnessKind.CLAUDE_CODE: ClaudeCodeHarness(),
    HarnessKind.OPENCODE: OpenCodeHarness(),
}
