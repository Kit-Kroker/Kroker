"""E-15: the PreToolUse hook process contract (verified against 2.1.219)."""
import json
import subprocess
import sys

import pytest

from sdlc.harness.containment import Policy, Rule
from sdlc.harness.hook import decide, format_reason, main
from sdlc.models import ContainmentLayer

POLICY = Policy(version=1, rules=[
    Rule(id="no-out-of-worktree-write", layer=ContainmentLayer.HOOK,
         tools=["Write"], predicate="path_outside_worktree",
         reason="Writes are scoped to the task worktree."),
])


def test_allow_emits_an_allow_decision(tmp_path):
    out = decide({"tool_name": "Write",
                  "tool_input": {"file_path": f"{tmp_path}/a.py"}},
                 POLICY, str(tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_deny_carries_the_rule_id_in_the_reason(tmp_path):
    out = decide({"tool_name": "Write",
                  "tool_input": {"file_path": "/etc/passwd"}},
                 POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    # permission_denials carries no rule id, so it rides the reason string.
    assert hso["permissionDecisionReason"].startswith(
        "[no-out-of-worktree-write]")


def test_format_reason_round_trips():
    assert format_reason("r-1", "because") == "[r-1] because"


def test_missing_tool_name_allows_rather_than_crashing(tmp_path):
    out = decide({}, POLICY, str(tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_main_writes_json_to_stdout_and_exits_zero(tmp_path, capsys,
                                                   monkeypatch):
    pol = tmp_path / "p.yaml"
    pol.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8")
    payload = json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": "/etc/passwd"}})
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    rc = main(["--worktree", str(tmp_path), "--policy", str(pol)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_internal_failure_denies_never_allows(tmp_path, capsys, monkeypatch):
    """A hook that crashes open is worse than no hook at all."""
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not json"))
    rc = main(["--worktree", str(tmp_path), "--policy", "/nonexistent.yaml"])
    assert rc == 0                      # exit 0: the JSON carries the verdict
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_module_is_runnable_as_a_subprocess(tmp_path):
    """claude invokes this as a command; it must work with -m and no cwd
    assumptions, and must not import Temporal."""
    pol = tmp_path / "p.yaml"
    pol.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "sdlc.harness.hook",
         "--worktree", str(tmp_path), "--policy", str(pol)],
        input=json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": "/etc/passwd"}}),
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["hookSpecificOutput"][
        "permissionDecision"] == "deny"
