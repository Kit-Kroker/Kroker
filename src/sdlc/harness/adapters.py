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
import re
import shutil
import subprocess
import sys
import tempfile
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..models import (
    ContainmentLayer, ContainmentReport, HarnessKind, HarnessRunResult,
    HarnessSession, SessionEvent, ToolDenial,
)
from .containment import Policy, Predicate, Rule, target_of

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


def _split_reason(text: str) -> tuple[str, str]:
    """Split the hook's `[rule-id] reason` back apart."""
    if text.startswith("[") and "] " in text:
        rid, _, rest = text[1:].partition("] ")
        return rid, rest
    return "unknown", text


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
    cli: str = ""                          # executable name on PATH
    expected_version: str | None = None    # E-24 pin; None = declared-unpinned

    def version_cmd(self) -> list[str]:
        return [self.cli, "--version"]

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

    # ADR-17: what this CLI can actually enforce. A harness declaring an
    # empty set fails closed when containment is enabled, rather than
    # running unpoliced and looking contained.
    containment: frozenset[ContainmentLayer] = frozenset()

    def apply_containment(self, policy: Policy,
                          req: HarnessRequest) -> ContainmentReport:
        """Compile `policy` into this CLI's own mechanisms, mutating `req`.
        Base default: enforce nothing and say so."""
        return ContainmentReport(
            enabled=True, layers_active=[],
            rules_unenforceable=[r.id for r in policy.rules])

    def normalise_denials(self, stdout: str) -> list[ToolDenial]:
        """Blocked tool calls from this harness's stream (ADR-17, mirroring
        normalise_session). Base default: none reported."""
        return []

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
    cli = "claude"
    expected_version = "2.1.218"

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

    containment = frozenset({ContainmentLayer.NATIVE, ContainmentLayer.HOOK})

    def apply_containment(self, policy: Policy,
                          req: HarnessRequest) -> ContainmentReport:
        """Both layers, deliberately overlapping (spec §4a).

        `permissions.deny` is the floor a buggy hook cannot weaken (verified:
        a hook's `allow` cannot bypass a deny rule). The hook is the layer
        that is OBSERVABLE — a native deny blocks correctly but reports
        `permission_denials: []`, so every rule is ALSO hooked here.
        """
        hooks = [{
            "matcher": "|".join(sorted({t for r in policy.rules
                                        for t in r.tools})),
            "hooks": [{"type": "command", "command": self._hook_command(req)}],
        }] if policy.rules else []

        deny = [p for r in policy.rules if ContainmentLayer.NATIVE is r.layer
                for p in self._native_patterns(r)]

        doc = {"hooks": {"PreToolUse": hooks}, "permissions": {"deny": deny}}

        # OUTSIDE the worktree, always: writes inside the worktree are
        # permitted by design, so a settings file placed there is a file the
        # agent may rewrite — it could edit its own policy.
        fd, path = tempfile.mkstemp(prefix="sdlc-containment-",
                                    suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

        req.extra_args = [*req.extra_args, "--settings", path,
                          "--include-hook-events"]
        return ContainmentReport(
            enabled=True,
            layers_active=[ContainmentLayer.NATIVE, ContainmentLayer.HOOK],
            rules_enforced=[r.id for r in policy.rules],
            rules_unenforceable=[])

    @staticmethod
    def _hook_command(req: HarnessRequest) -> str:
        """Absolute interpreter path: the child's PATH is allowlisted and may
        resolve a different `python` than the worker's venv. Forward slashes
        because claude runs hooks through Git Bash on Windows."""
        exe = Path(sys.executable).as_posix()
        wt = Path(req.cwd).as_posix()
        return (f'"{exe}" -m sdlc.harness.hook --worktree "{wt}"')

    @staticmethod
    def _native_patterns(rule: Rule) -> list[str]:
        """Translate OUR pattern syntax into claude's `Tool(arg)` deny form.
        The policy author never writes CLI-specific syntax."""
        out: list[str] = []
        for tool in rule.tools:
            for pat in rule.patterns:
                out.append(f"{tool}({pat})")
        return out

    def normalise_denials(self, stdout: str) -> list[ToolDenial]:
        """`result.permission_denials` is the structured spine (tool_name /
        tool_use_id / tool_input). It carries no rule id, so the rule id is
        recovered from the `[rule-id] ` prefix the hook writes into the
        reason, surfaced in `hook_response.output`."""
        reasons: list[str] = []
        denials: list[ToolDenial] = []
        for ln in stdout.strip().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if (ev.get("subtype") == "hook_response"
                    and ev.get("hook_event") == "PreToolUse"):
                try:
                    hso = json.loads(ev.get("output") or "{}")
                    hso = hso.get("hookSpecificOutput") or {}
                except json.JSONDecodeError:
                    continue
                if hso.get("permissionDecision") == "deny":
                    reasons.append(hso.get("permissionDecisionReason") or "")
            elif ev.get("type") == "result":
                for i, pd in enumerate(ev.get("permission_denials") or []):
                    rule_id, reason = _split_reason(
                        reasons[i] if i < len(reasons) else "")
                    tool_input = pd.get("tool_input") or {}
                    denials.append(ToolDenial(
                        tool=pd.get("tool_name") or "unknown",
                        rule_id=rule_id, layer=ContainmentLayer.HOOK,
                        reason=reason,
                        target=target_of(pd.get("tool_name") or "",
                                         tool_input)))
        return denials

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
        # E-16: denials are part of the transcript, so the digest counts
        # them on clean-green runs too (the same reasoning as OQ-B7's
        # keep-aggregates-pre-truncation rule).
        for d in self.normalise_denials(stdout):
            events.append(SessionEvent(
                kind="tool_denied", tool=d.tool, target=d.target))
        return HarnessSession(harness=self.kind, session_id=session_id,
                              model=model, events=events, cost_usd=cost,
                              input_tokens=in_tok, output_tokens=out_tok)


class OpenCodeHarness(CodingHarness):
    kind = HarnessKind.OPENCODE
    cli = "opencode"
    expected_version = "1.18.4"

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

    # `--pure` (build_cmd) disables external plugins, which are opencode's
    # only hook mechanism. The native permission block is what remains.
    containment = frozenset({ContainmentLayer.NATIVE})

    def apply_containment(self, policy: Policy,
                          req: HarnessRequest) -> ContainmentReport:
        """Compile native-layer rules into opencode's `permission` config.

        opencode (1.18.4, verified) has NO `--config` flag and no config-path
        env var: it discovers `opencode.json` from the working directory
        (cwd = the task worktree). So unlike claude's out-of-worktree
        `--settings`, the deny config MUST live inside the worktree. It is
        self-protecting: the same compilation emits `permission.edit` denies
        for agent-config paths (incl. `opencode.json`) from the
        `no-agent-config-write` rule, so the agent cannot rewrite its own
        policy via the tools opencode gives it. `--auto` is "auto-approve
        what is NOT explicitly denied", so a `deny` here really bites.
        CAVEAT: this writes into a tracked repo file when one exists; the
        merge below preserves any existing keys.
        """
        perms: dict[str, dict[str, str]] = {}
        enforced: list[str] = []
        unenforceable: list[str] = []
        for rule in policy.rules:
            if ContainmentLayer.HOOK is rule.layer:
                unenforceable.append(rule.id)   # needs a hook we do not have
                continue
            if rule.predicate is Predicate.COMMAND_MATCHES:
                bucket = perms.setdefault("bash", {})
            elif rule.predicate is Predicate.PATH_MATCHES:
                bucket = perms.setdefault("edit", {})
            else:
                # native but needs per-call resolution (path_outside_worktree,
                # host_not_allowlisted) — a static config cannot express it.
                unenforceable.append(rule.id)
                continue
            for pat in rule.patterns:
                bucket[pat] = "deny"
            enforced.append(rule.id)

        # Merge into the worktree's opencode.json so an existing config
        # (e.g. the repo's plugin block) is preserved, not clobbered.
        path = Path(req.cwd) / "opencode.json"
        doc: dict = {}
        if path.is_file():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(doc, dict):
                    doc = {}
            except json.JSONDecodeError:
                doc = {}                       # JSONC/unparseable -> start fresh
        existing = doc.get("permission")
        if isinstance(existing, dict):
            for tool, rules in perms.items():
                existing.setdefault(tool, {}).update(rules)
            perms = existing
        doc["permission"] = perms
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

        return ContainmentReport(
            enabled=True, layers_active=[ContainmentLayer.NATIVE],
            rules_enforced=enforced, rules_unenforceable=unenforceable)

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
        cmd = ["cursor-agent", "-p", req.prompt,
               "--output-format", "stream-json"]
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
            cost = payload.get("total_cost_usd")   # ASSUMPTION: may be absent
                                                    # -> cursor cells are
                                                    # quality-only (spec §5)
            summary = payload.get("result") or payload.get("content")
            usage = payload.get("usage") or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
        else:
            _log.warning("cursor parse: no result event in stream, falling "
                         "back to raw stdout as summary")
            summary = stdout
        return HarnessRunResult(
            harness=self.kind, session_id=session_id, exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX], cost_usd=cost,
            input_tokens=input_tokens, output_tokens=output_tokens,
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


HARNESSES: dict[HarnessKind, CodingHarness] = {
    HarnessKind.CLAUDE_CODE: ClaudeCodeHarness(),
    HarnessKind.OPENCODE: OpenCodeHarness(),
    HarnessKind.CURSOR: CursorHarness(),
}


_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def check_harness_versions(
        harnesses: dict[HarnessKind, CodingHarness] | None = None) -> None:
    """E-24 (folded into E-35): warn when an installed harness CLI has drifted
    from its pinned version — the failure mode where a silent CLI upgrade
    breaks an adapter's parse. Never raises (a patch bump must not brick the
    worker). Skips silently when the CLI is absent (CI/fakes) or unpinned."""
    for h in (harnesses or HARNESSES).values():
        if not h.expected_version or not h.cli:
            continue
        if shutil.which(h.cli) is None:
            _log.debug("harness version check: %s not on PATH, skipping", h.cli)
            continue
        try:
            out = subprocess.run(h.version_cmd(), capture_output=True,
                                 text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            _log.debug("harness version check: %s --version failed: %s",
                       h.cli, e)
            continue
        m = _VERSION_RE.search(out.stdout or "")
        found = m.group(1) if m else None
        if found != h.expected_version:
            _log.warning("harness version drift: %s is %s, pinned %s "
                         "(adapter parse may break; capture a fresh transcript "
                         "and update the pin)", h.cli, found, h.expected_version)
        else:
            _log.debug("harness version ok: %s %s", h.cli, found)
