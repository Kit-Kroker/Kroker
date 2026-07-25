"""PreToolUse hook process (E-15/E-17, FR-703).

Invoked by the harness CLI once per tool call, so it is deliberately thin
and import-light: it must NOT import Temporal, pydantic_ai, or sdlc.cli.
All policy logic lives in containment.py, which is pure and testable
without a subprocess.

Contract, verified live against claude 2.1.219: read the hook payload as
JSON on stdin, write one JSON object to stdout, exit 0. The
permissionDecisionReason reaches the model verbatim.

E-17: an ESCALATE rule defers instead of denying, but ONLY when the call is
solo — `defer` is discarded by the CLI when the assistant message carries
sibling tool_use blocks, and the call would then fall through to
acceptEdits. Every other path denies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..models import ToolGrant
from .containment import (
    ESCALATION_UNAVAILABLE, Action, Policy, evaluate, load_grants,
    load_policy, match_grant,
)

_EVENT = "PreToolUse"


def format_reason(rule_id: str, reason: str) -> str:
    """`result.permission_denials` carries tool_name/tool_use_id/tool_input
    but NO reason or rule id, so the rule id rides the reason string and
    normalise_denials reads it back out."""
    return f"[{rule_id}] {reason}"


def _decision(decision: str, reason: str | None = None) -> dict:
    hso: dict = {"hookEventName": _EVENT, "permissionDecision": decision}
    if reason is not None:
        hso["permissionDecisionReason"] = reason
    return {"hookSpecificOutput": hso}


def sibling_count(transcript_path: str | None, tool_use_id: str) -> int | None:
    """How many tool_use blocks share the assistant message that issued
    `tool_use_id`. None means we could not determine it.

    `defer` is solo-only: the CLI discards a defer whose message carries
    siblings, and the call then falls through to the ordinary permission
    pipeline — which under acceptEdits ALLOWS it. So an undeterminable count
    must be treated as batched, never as solo.

    There is no race: the assistant message is complete before any of its
    tool calls dispatch. Scanned newest-first because the message we want is
    the most recent one.
    """
    if not transcript_path or not tool_use_id:
        return None
    try:
        lines = Path(transcript_path).read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        message = ev.get("message")
        content = (message or {}).get("content") if isinstance(
            message, dict) else ev.get("content")
        if not isinstance(content, list):
            continue
        blocks = [b for b in content
                  if isinstance(b, dict) and b.get("type") == "tool_use"]
        if any(b.get("id") == tool_use_id for b in blocks):
            return len(blocks)
    return None


def _escalate(payload: dict, tool: str, tool_input: dict, rule_id: str,
              reason: str, grants: list[ToolGrant]) -> dict:
    """Decide an ESCALATE match. Every branch that is not a clean defer or a
    granted allow ends in a deny — degradation is always toward deny."""
    tool_use_id = payload.get("tool_use_id") or ""
    grant = match_grant(grants, tool, tool_use_id, tool_input)
    if grant is not None:
        if grant.approved:
            return _decision("allow", format_reason(
                rule_id, f"approved: {grant.reason}" if grant.reason
                else "approved"))
        return _decision("deny", format_reason(
            rule_id, f"rejected: {grant.reason}" if grant.reason
            else "rejected"))

    siblings = sibling_count(payload.get("transcript_path"), tool_use_id)
    if siblings is None:
        return _decision("deny", format_reason(
            rule_id, f"{ESCALATION_UNAVAILABLE} (transcript): {reason}"))
    if siblings > 1:
        return _decision("deny", format_reason(
            rule_id, f"{ESCALATION_UNAVAILABLE} (batched): {reason}"))
    return _decision("defer", format_reason(rule_id, reason))


def decide(payload: dict, policy: Policy, worktree: str,
           grants: list[ToolGrant] | None = None) -> dict:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return _decision("allow")
    verdict = evaluate(policy, tool, tool_input, worktree)
    if verdict.allow:
        return _decision("allow")
    rule_id = verdict.rule_id or "unknown"
    reason = verdict.reason or "denied by containment policy"
    if verdict.action is Action.ESCALATE:
        return _escalate(payload, tool, tool_input, rule_id, reason,
                         grants or [])
    return _decision("deny", format_reason(rule_id, reason))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sdlc.harness.hook")
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--policy", default=None)
    ap.add_argument("--grants", default=None)
    args = ap.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        policy = load_policy(args.policy)
        grants = load_grants(args.grants)
        out = decide(payload, policy, args.worktree, grants)
    except Exception as e:                        # noqa: BLE001
        # Fail CLOSED. A hook that crashes open is worse than no hook: the
        # run would look contained while enforcing nothing.
        out = _decision(
            "deny", f"[containment-error] containment hook failed: {e}")

    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
