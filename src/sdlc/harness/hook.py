"""PreToolUse hook process (E-15, FR-703).

Invoked by the harness CLI once per tool call, so it is deliberately thin
and import-light: it must NOT import Temporal, pydantic_ai, or sdlc.cli.
All policy logic lives in containment.py, which is pure and testable
without a subprocess.

Contract, verified live against claude 2.1.219: read the hook payload as
JSON on stdin, write one JSON object to stdout, exit 0. The
permissionDecisionReason reaches the model verbatim.
"""
from __future__ import annotations

import argparse
import json
import sys

from .containment import Policy, evaluate, load_policy, target_of

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


def decide(payload: dict, policy: Policy, worktree: str) -> dict:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return _decision("allow")
    verdict = evaluate(policy, tool, tool_input, worktree)
    if verdict.allow:
        return _decision("allow")
    return _decision(
        "deny", format_reason(verdict.rule_id or "unknown",
                              verdict.reason or "denied by containment policy"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sdlc.harness.hook")
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--policy", default=None)
    args = ap.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        policy = load_policy(args.policy)
        out = decide(payload, policy, args.worktree)
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
