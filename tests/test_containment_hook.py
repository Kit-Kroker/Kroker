"""E-15: the PreToolUse hook process contract (verified against 2.1.219)."""

import json
import subprocess
import sys

from sdlc.harness.containment import Policy, Rule
from sdlc.harness.hook import decide, format_reason, main
from sdlc.harness.models import ContainmentLayer

POLICY = Policy(
    version=1,
    rules=[
        Rule(
            id="no-out-of-worktree-write",
            layer=ContainmentLayer.HOOK,
            tools=["Write"],
            predicate="path_outside_worktree",
            reason="Writes are scoped to the task worktree.",
        ),
    ],
)


def test_allow_emits_an_allow_decision(tmp_path):
    out = decide(
        {"tool_name": "Write", "tool_input": {"file_path": f"{tmp_path}/a.py"}},
        POLICY,
        str(tmp_path),
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_deny_carries_the_rule_id_in_the_reason(tmp_path):
    out = decide(
        {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}}, POLICY, str(tmp_path)
    )
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    # permission_denials carries no rule id, so it rides the reason string.
    assert hso["permissionDecisionReason"].startswith("[no-out-of-worktree-write]")


def test_format_reason_round_trips():
    assert format_reason("r-1", "because") == "[r-1] because"


def test_missing_tool_name_allows_rather_than_crashing(tmp_path):
    out = decide({}, POLICY, str(tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_main_writes_json_to_stdout_and_exits_zero(tmp_path, capsys, monkeypatch):
    pol = tmp_path / "p.yaml"
    pol.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8",
    )
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}})
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    rc = main(["--worktree", str(tmp_path), "--policy", str(pol)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_internal_failure_denies_never_allows(tmp_path, capsys, monkeypatch):
    """A hook that crashes open is worse than no hook at all."""
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not json"))
    rc = main(["--worktree", str(tmp_path), "--policy", "/nonexistent.yaml"])
    assert rc == 0  # exit 0: the JSON carries the verdict
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
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "sdlc.harness.hook",
            "--worktree",
            str(tmp_path),
            "--policy",
            str(pol),
        ],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}}),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


from sdlc.harness.containment import Action, digest_tool_input
from sdlc.harness.hook import sibling_count
from sdlc.harness.models import ToolGrant

ESC_POLICY = Policy(
    version=1,
    rules=[
        Rule(
            id="no-out-of-worktree-write",
            layer=ContainmentLayer.HOOK,
            action=Action.ESCALATE,
            tools=["Write"],
            predicate="path_outside_worktree",
            reason="Writes are scoped to the task worktree.",
        ),
    ],
)
OUTSIDE = {"file_path": "/etc/passwd"}


def _transcript(tmp_path, tool_use_ids):
    """One assistant message carrying `tool_use_ids` as parallel tool_use
    blocks — the shape claude writes to its session JSONL."""
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        json.dumps({"type": "user", "message": {"content": "go"}})
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "working"},
                        *(
                            {"type": "tool_use", "id": i, "name": "Write", "input": {}}
                            for i in tool_use_ids
                        ),
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return p


def _payload(tmp_path, tool_use_id="toolu_1", ids=("toolu_1",)):
    return {
        "tool_name": "Write",
        "tool_input": OUTSIDE,
        "tool_use_id": tool_use_id,
        "transcript_path": str(_transcript(tmp_path, ids)),
    }


def test_solo_escalate_call_defers(tmp_path):
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "defer"
    assert hso["permissionDecisionReason"].startswith("[no-out-of-worktree-write]")


def test_batched_escalate_call_denies_and_says_why(tmp_path):
    """defer is solo-only: the CLI would DISCARD it and acceptEdits would
    allow the call, so we must never emit it for a batched call."""
    out = decide(_payload(tmp_path, ids=("toolu_1", "toolu_2")), ESC_POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "escalation unavailable (batched)" in hso["permissionDecisionReason"]


def test_unreadable_transcript_denies(tmp_path):
    payload = {
        "tool_name": "Write",
        "tool_input": OUTSIDE,
        "tool_use_id": "toolu_1",
        "transcript_path": str(tmp_path / "gone.jsonl"),
    }
    out = decide(payload, ESC_POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "escalation unavailable (transcript)" in hso["permissionDecisionReason"]


def test_an_approved_grant_allows_exactly_that_call(tmp_path):
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=True,
        reason="approved by maks",
    )
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path), [grant])
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"


def test_a_rejecting_grant_denies_with_the_humans_words(tmp_path):
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=False,
        reason="write it inside the worktree instead",
    )
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path), [grant])
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "write it inside the worktree instead" in hso["permissionDecisionReason"]


def test_a_grant_for_another_call_does_not_leak(tmp_path):
    """An approval covers exactly one call — never a standing waiver."""
    grant = ToolGrant(
        tool_use_id="toolu_OTHER",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=True,
    )
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path), [grant])
    assert out["hookSpecificOutput"]["permissionDecision"] == "defer"


def test_a_deny_rule_never_defers(tmp_path):
    """E-16 behaviour is untouched by E-17."""
    out = decide(_payload(tmp_path), POLICY, str(tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "escalation unavailable" not in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_sibling_count_finds_the_message_holding_the_id(tmp_path):
    p = _transcript(tmp_path, ("toolu_1", "toolu_2", "toolu_3"))
    assert sibling_count(str(p), "toolu_2") == 3


def test_sibling_count_is_none_when_the_id_is_absent(tmp_path):
    p = _transcript(tmp_path, ("toolu_1",))
    assert sibling_count(str(p), "toolu_missing") is None


def test_sibling_count_survives_malformed_lines(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        "not json\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": "Write"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert sibling_count(str(p), "toolu_1") == 1


def test_sibling_count_is_none_for_a_missing_file(tmp_path):
    assert sibling_count(str(tmp_path / "nope.jsonl"), "toolu_1") is None


def test_main_accepts_a_grants_file(tmp_path, capsys, monkeypatch):
    pol = tmp_path / "p.yaml"
    pol.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    action: escalate\n"
        "    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8",
    )
    grants = tmp_path / "g.json"
    grants.write_text(
        json.dumps(
            [
                {
                    "tool_use_id": "toolu_1",
                    "tool": "Write",
                    "input_digest": digest_tool_input(OUTSIDE),
                    "rule_id": "r",
                    "approved": True,
                    "reason": "yes",
                }
            ]
        ),
        encoding="utf-8",
    )
    payload = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": OUTSIDE,
            "tool_use_id": "toolu_1",
            "transcript_path": str(_transcript(tmp_path, ("toolu_1",))),
        }
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    rc = main(["--worktree", str(tmp_path), "--policy", str(pol), "--grants", str(grants)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
