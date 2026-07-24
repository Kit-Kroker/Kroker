"""E-15/E-16: adapter-side containment compilation and denial normalisation."""
import json
from pathlib import Path

from sdlc.harness.adapters import (
    ClaudeCodeHarness, HarnessRequest,
)
from sdlc.harness.containment import Policy, Rule
from sdlc.models import ContainmentLayer

POLICY = Policy(version=1, rules=[
    Rule(id="no-out-of-worktree-write", layer=ContainmentLayer.HOOK,
         tools=["Write", "Edit"], predicate="path_outside_worktree",
         reason="Writes are scoped to the task worktree."),
    Rule(id="no-recursive-force-delete", layer=ContainmentLayer.NATIVE,
         tools=["Bash"], predicate="command_matches",
         patterns=["rm -rf *"], reason="Destructive recursive delete."),
])


def test_claude_declares_both_layers():
    assert ClaudeCodeHarness().containment == frozenset(
        {ContainmentLayer.NATIVE, ContainmentLayer.HOOK})


def test_apply_writes_settings_outside_the_worktree(tmp_path):
    wt = tmp_path / "worktree"
    wt.mkdir()
    req = HarnessRequest(prompt="p", cwd=str(wt))
    ClaudeCodeHarness().apply_containment(POLICY, req)

    settings = _settings_path(req)
    assert Path(settings).is_file()
    # The agent may write anywhere inside the worktree, so its own policy
    # file must not live there.
    assert wt not in Path(settings).parents


def test_apply_emits_hook_and_native_layers(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    ClaudeCodeHarness().apply_containment(POLICY, req)
    doc = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))

    assert doc["hooks"]["PreToolUse"], "hook layer missing"
    assert doc["permissions"]["deny"], "native layer missing"


def test_native_layer_rule_also_runs_through_the_hook(tmp_path):
    """Spec section 4a: `layer` is a MINIMUM, so a native rule is ALSO
    hooked on a harness that has a hook — otherwise its denial would be
    unobservable (permission_denials is empty for native denies)."""
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    ClaudeCodeHarness().apply_containment(POLICY, req)
    doc = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))

    matchers = "|".join(e["matcher"] for e in doc["hooks"]["PreToolUse"])
    assert "Bash" in matchers          # the native-layer rule's tool
    assert "Write" in matchers         # the hook-layer rule's tool


def test_apply_reports_full_coverage_for_claude(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    report = ClaudeCodeHarness().apply_containment(POLICY, req)
    assert report.enabled is True
    assert report.rules_unenforceable == []
    assert set(report.rules_enforced) == {
        "no-out-of-worktree-write", "no-recursive-force-delete"}


def test_normalise_denials_reads_permission_denials():
    """Shape captured from a live 2.1.219 run."""
    stream = json.dumps({
        "type": "result", "subtype": "success", "session_id": "s",
        "permission_denials": [{
            "tool_name": "Write",
            "tool_use_id": "toolu_01",
            "tool_input": {"file_path": "C:\\etc\\passwd"},
        }],
    })
    denials = ClaudeCodeHarness().normalise_denials(stream)
    assert len(denials) == 1
    assert denials[0].tool == "Write"
    assert denials[0].layer is ContainmentLayer.HOOK
    assert denials[0].target == "C:\\etc\\passwd"


def test_normalise_denials_recovers_rule_id_from_the_hook_reason():
    stream = "\n".join([
        json.dumps({
            "type": "system", "subtype": "hook_response",
            "hook_event": "PreToolUse", "hook_name": "PreToolUse:Write",
            "exit_code": 0, "outcome": "success",
            "output": json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason":
                    "[no-out-of-worktree-write] Writes are scoped.",
            }}),
        }),
        json.dumps({
            "type": "result", "subtype": "success", "session_id": "s",
            "permission_denials": [{
                "tool_name": "Write", "tool_use_id": "t1",
                "tool_input": {"file_path": "/etc/passwd"}}],
        }),
    ])
    d = ClaudeCodeHarness().normalise_denials(stream)[0]
    assert d.rule_id == "no-out-of-worktree-write"
    assert d.reason == "Writes are scoped."


def test_no_denials_on_a_clean_stream():
    stream = json.dumps({"type": "result", "subtype": "success",
                         "session_id": "s", "permission_denials": []})
    assert ClaudeCodeHarness().normalise_denials(stream) == []


def test_denials_become_session_events_and_are_counted():
    from sdlc.harness.session import digest_of
    stream = "\n".join([
        json.dumps({"type": "system", "subtype": "init", "session_id": "s",
                    "model": "claude-opus-4-8"}),
        json.dumps({"type": "result", "subtype": "success", "session_id": "s",
                    "permission_denials": [{
                        "tool_name": "Write", "tool_use_id": "t1",
                        "tool_input": {"file_path": "/etc/passwd"}}]}),
    ])
    session = ClaudeCodeHarness().normalise_session(stream)
    assert [e.kind for e in session.events].count("tool_denied") == 1
    digest = digest_of(session)
    assert digest.denials == 1
    assert digest.tool_calls == 0      # a blocked call is not a tool call


def _settings_path(req: HarnessRequest) -> str:
    idx = req.extra_args.index("--settings")
    return req.extra_args[idx + 1]
