"""OpenCode harness adapter.

CLI asymmetries handled here:
  * opencode: `opencode run "<prompt>" --format json -m provider/model`;
              prompt is a positional arg (there is NO -p flag);
              continue with `-s <session_id>`; optional `--attach <url>`
              to reuse a warm `opencode serve` instance.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..core.models import HarnessKind
from .base import SUMMARY_MAX, CodingHarness, HarnessRequest
from .containment import (
    Policy,
    Predicate,
)
from .models import (
    ContainmentLayer,
    ContainmentReport,
    HarnessRunResult,
    HarnessSession,
    SessionEvent,
    ToolGrant,
)

_log = logging.getLogger(__name__)


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
        # `--`: opencode's yargs parser reads a prompt starting with '-'
        # (e.g. a crew SKILL.md's YAML frontmatter fence, "---\nname: ...")
        # as an unrecognized option rather than the positional message,
        # which empties the required message array and opencode exits 1
        # dumping its own --help to stderr -- confirmed by reproducing it
        # verbatim against a live opencode 1.18.4. `--` is the POSIX
        # end-of-options marker yargs honors, forcing everything after it
        # to be positional regardless of leading characters.
        cmd.append("--")
        cmd.append(req.prompt)  # positional, must come last
        return cmd

    # `--pure` (build_cmd) disables external plugins, which are opencode's
    # only hook mechanism. The native permission block is what remains.
    containment = frozenset({ContainmentLayer.NATIVE})

    def apply_containment(
        self, policy: Policy, req: HarnessRequest, grants: list[ToolGrant] | None = None
    ) -> ContainmentReport:
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
                unenforceable.append(rule.id)  # needs a hook we do not have
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
                doc = {}  # JSONC/unparseable -> start fresh
        existing = doc.get("permission")
        if isinstance(existing, dict):
            for tool, rules in perms.items():
                existing.setdefault(tool, {}).update(rules)
            perms = existing
        doc["permission"] = perms
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

        return ContainmentReport(
            enabled=True,
            layers_active=[ContainmentLayer.NATIVE],
            rules_enforced=enforced,
            rules_unenforceable=unenforceable,
        )

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
        input_tokens: int | None = 0
        output_tokens: int | None = 0
        cost: float | None = 0.0
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
            _log.warning(
                "opencode parse: no events parsed from stdout "
                "(parsed_any=False); falling back to raw stdout"
            )
        summary = "\n".join(text_parts) if parsed_any else stdout
        return HarnessRunResult(
            harness=self.kind,
            session_id=session_id,
            exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX],
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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
                events.append(SessionEvent(kind="model_turn", text=part["text"][:2000]))
            elif etype == "tool":
                name = (part.get("tool") or "tool").lower()
                kind, field = self._TOOL_MAP.get(name, ("tool_call", ""))
                state = part.get("state") or {}
                inp = state.get("input") or {}
                target = inp.get(field) if field else json.dumps(inp)[:500]
                events.append(
                    SessionEvent(
                        kind=kind,
                        tool=name,
                        target=target,
                        exit_code=1 if state.get("status") == "error" else None,
                    )
                )
            elif etype == "step_finish":
                tokens = part.get("tokens") or {}
                if isinstance(tokens.get("input"), (int, float)):
                    in_tok += tokens["input"]
                    saw_tokens = True
                if isinstance(tokens.get("output"), (int, float)):
                    out_tok += tokens["output"]
                    saw_tokens = True
                if isinstance(part.get("cost"), (int, float)):
                    cost += part["cost"]
                    saw_cost = True
        return HarnessSession(
            harness=self.kind,
            session_id=session_id,
            events=events,
            input_tokens=in_tok if saw_tokens else None,
            output_tokens=out_tok if saw_tokens else None,
            cost_usd=cost if saw_cost else None,
        )
