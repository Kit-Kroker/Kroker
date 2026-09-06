"""Claude Code harness adapter.

CLI asymmetries handled here:
  * claude:   `claude -p "<prompt>" --output-format stream-json --verbose`;
              stdin supported; resume with `--resume <session_id>` (scoped to cwd/worktree).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from ..core.models import HarnessKind
from ..memory.scrub import scrub
from .base import SUMMARY_MAX, CodingHarness, HarnessRequest, _split_reason
from .containment import (
    Action,
    Phase,
    Policy,
    Rule,
    digest_tool_input,
    is_declined_reason,
    target_of,
)
from .models import (
    ContainmentLayer,
    ContainmentReport,
    DeferredToolUse,
    HarnessRunResult,
    HarnessSession,
    SessionEvent,
    ToolDenial,
    ToolGrant,
)

_log = logging.getLogger(__name__)


class ClaudeCodeHarness(CodingHarness):
    kind = HarnessKind.CLAUDE_CODE
    cli = "claude"
    expected_version = "2.1.218"

    def __init__(
        self, allowed_tools: str = "Read,Edit,Write,Bash", permission_mode: str = "acceptEdits"
    ):
        self.allowed_tools = allowed_tools
        self.permission_mode = permission_mode

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        cmd = [
            "claude",
            "-p",
            req.prompt,
            # E-38: stream-json emits the full event stream (transcript
            # source) AND a final `result` event with the same fields the
            # old plain-json payload carried. --verbose is required by the
            # CLI for stream-json in print mode.
            "--output-format",
            "stream-json",
            "--verbose",
            "--allowedTools",
            self.allowed_tools,
            "--permission-mode",
            self.permission_mode,
        ]
        if req.model:
            cmd += ["--model", req.model]
        if req.session_id:
            cmd += ["--resume", req.session_id]
        return cmd + req.extra_args

    containment = frozenset({ContainmentLayer.NATIVE, ContainmentLayer.HOOK})
    supports_escalation = True

    def apply_containment(
        self, policy: Policy, req: HarnessRequest, grants: list[ToolGrant] | None = None
    ) -> ContainmentReport:
        """Both layers, deliberately overlapping (E-15 spec §4a).

        `permissions.deny` is the floor a buggy hook cannot weaken (verified:
        a hook's `allow` cannot bypass a deny rule). The hook is the layer
        that is OBSERVABLE — a native deny blocks correctly but reports
        `permission_denials: []`, so every rule is ALSO hooked here.

        E-17: an ESCALATE rule is hook-only by construction (load_policy
        refuses `escalate` + `layer: native`), because a native deny would
        block the very call the human approved.
        """
        grants_path = self._write_grants(grants)
        # C2: rules whose phase does not match this invocation are compiled
        # into NEITHER layer. Filtering the MATCHER too (not just the deny
        # list) keeps a pass-1 settings file byte-identical to pre-C2: with
        # no repair rules active, no Write/Edit pays a hook spawn that could
        # only ever return allow.
        active = [r for r in policy.rules if r.phase is not Phase.REPAIR or req.repair]
        hooks = (
            [
                {
                    "matcher": "|".join(sorted({t for r in active for t in r.tools})),
                    "hooks": [
                        {
                            "type": "command",
                            "command": self._hook_command(req, policy.source_path, grants_path),
                        }
                    ],
                }
            ]
            if active
            else []
        )

        deny = [
            p
            for r in active
            if ContainmentLayer.NATIVE is r.layer
            for p in self._native_patterns(r)
        ]

        doc = {"hooks": {"PreToolUse": hooks}, "permissions": {"deny": deny}}

        # OUTSIDE the worktree, always: writes inside the worktree are
        # permitted by design, so a settings file placed there is a file the
        # agent may rewrite — it could edit its own policy.
        fd, path = tempfile.mkstemp(prefix="sdlc-containment-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

        req.extra_args = [*req.extra_args, "--settings", path, "--include-hook-events"]
        return ContainmentReport(
            enabled=True,
            layers_active=[ContainmentLayer.NATIVE, ContainmentLayer.HOOK],
            rules_enforced=[r.id for r in active],
            rules_unenforceable=[],
            rules_escalatable=[r.id for r in active if r.action is Action.ESCALATE],
        )

    @staticmethod
    def _write_grants(grants: list[ToolGrant] | None) -> str | None:
        """Grants live outside the worktree for the same reason the settings
        file does: the agent may write anywhere inside it, so an in-worktree
        grants file would be a file it could forge."""
        if not grants:
            return None
        fd, path = tempfile.mkstemp(prefix="sdlc-grants-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump([g.model_dump() for g in grants], fh)
        return path

    @staticmethod
    def _hook_command(
        req: HarnessRequest, source_path: Path | None = None, grants_path: str | None = None
    ) -> str:
        """Absolute interpreter path: the child's PATH is allowlisted and may
        resolve a different `python` than the worker's venv. Forward slashes
        because claude runs hooks through Git Bash on Windows. The policy
        path is passed explicitly because the hook's cwd is the worktree (a
        temp dir), where repo-root discovery would fail."""
        exe = Path(sys.executable).as_posix()
        # write_root, not cwd, when the two differ: the hook's --worktree IS
        # the confinement root (`_abs_under(target, worktree)`), and cwd is
        # only where the process runs.
        wt = Path(req.write_root or req.cwd).as_posix()
        cmd = f'"{exe}" -m sdlc.harness.hook --worktree "{wt}"'
        if source_path is not None:
            cmd += f' --policy "{Path(source_path).as_posix()}"'
        if grants_path is not None:
            cmd += f' --grants "{Path(grants_path).as_posix()}"'
        # C2: activates `phase: repair` rules for this invocation. The hook
        # command line lives in the OUT-OF-WORKTREE settings file, so the
        # agent cannot flip it.
        if req.repair:
            cmd += " --repair"
        return cmd

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
            if ev.get("subtype") == "hook_response" and ev.get("hook_event") == "PreToolUse":
                try:
                    hso = json.loads(ev.get("output") or "{}")
                    hso = hso.get("hookSpecificOutput") or {}
                except json.JSONDecodeError:
                    continue
                if hso.get("permissionDecision") == "deny":
                    reasons.append(hso.get("permissionDecisionReason") or "")
            elif ev.get("type") == "result":
                for i, pd in enumerate(ev.get("permission_denials") or []):
                    rule_id, reason = _split_reason(reasons[i] if i < len(reasons) else "")
                    tool_input = pd.get("tool_input") or {}
                    denials.append(
                        ToolDenial(
                            tool=pd.get("tool_name") or "unknown",
                            rule_id=rule_id,
                            layer=ContainmentLayer.HOOK,
                            reason=reason,
                            escalation_declined=is_declined_reason(reason),
                            target=target_of(pd.get("tool_name") or "", tool_input),
                        )
                    )
        return denials

    def normalise_deferral(self, stdout: str) -> DeferredToolUse | None:
        """The `result` event carries `stop_reason: "tool_deferred"` plus a
        structured `deferred_tool_use` (verified against 2.1.220). The rule
        id and reason come from the hook's own defer event, the same channel
        normalise_denials reads."""
        rule_id, reason = "unknown", ""
        deferred = None
        for ln in stdout.strip().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            if ev.get("subtype") == "hook_response" and ev.get("hook_event") == "PreToolUse":
                try:
                    hso = json.loads(ev.get("output") or "{}")
                    hso = hso.get("hookSpecificOutput") or {}
                except json.JSONDecodeError:
                    continue
                if hso.get("permissionDecision") == "defer":
                    rule_id, reason = _split_reason(hso.get("permissionDecisionReason") or "")
            elif ev.get("type") == "result" and ev.get("stop_reason") == "tool_deferred":
                deferred = ev.get("deferred_tool_use") or {}
        if not deferred:
            return None
        tool = deferred.get("name") or "unknown"
        tool_input = deferred.get("input") or {}
        raw_target = target_of(tool, tool_input)
        return DeferredToolUse(
            tool_use_id=deferred.get("id") or "",
            tool=tool,
            input_digest=digest_tool_input(tool_input),
            rule_id=rule_id,
            reason=reason,
            # Scrubbed here, not later: this target is rendered into a gate a
            # HUMAN reads, an exposure denial targets never had.
            target=scrub(raw_target) if raw_target else raw_target,
        )

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
            _log.warning(
                "claude parse: no result event in stream, falling back to raw stdout as summary"
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
        # E-16: denials are part of the transcript, so the digest counts
        # them on clean-green runs too (the same reasoning as OQ-B7's
        # keep-aggregates-pre-truncation rule).
        for d in self.normalise_denials(stdout):
            events.append(SessionEvent(kind="tool_denied", tool=d.tool, target=d.target))

        deferred = self.normalise_deferral(stdout)
        if deferred is not None:
            events.append(
                SessionEvent(kind="tool_deferred", tool=deferred.tool, target=deferred.target)
            )
        return HarnessSession(
            harness=self.kind,
            session_id=session_id,
            model=model,
            events=events,
            cost_usd=cost,
            input_tokens=in_tok,
            output_tokens=out_tok,
        )
