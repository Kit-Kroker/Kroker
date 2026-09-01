"""E-15/E-16: adapter-side containment compilation and denial normalisation."""

import json
from pathlib import Path

from sdlc.harness.adapters import (
    ClaudeCodeHarness,
    HarnessRequest,
)
from sdlc.harness.containment import Policy, Rule
from sdlc.models import ContainmentLayer

SCOPED_WRITES_REASON = "[no-out-of-worktree-write] Writes are scoped."
DESTRUCTIVE_REASON = "[no-recursive-force-delete] Destructive."

POLICY = Policy(
    version=1,
    rules=[
        Rule(
            id="no-out-of-worktree-write",
            layer=ContainmentLayer.HOOK,
            tools=["Write", "Edit"],
            predicate="path_outside_worktree",
            reason="Writes are scoped to the task worktree.",
        ),
        Rule(
            id="no-recursive-force-delete",
            layer=ContainmentLayer.NATIVE,
            tools=["Bash"],
            predicate="command_matches",
            patterns=["rm -rf *"],
            reason="Destructive recursive delete.",
        ),
    ],
)


def test_claude_declares_both_layers():
    assert ClaudeCodeHarness().containment == frozenset(
        {ContainmentLayer.NATIVE, ContainmentLayer.HOOK}
    )


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
    assert "Bash" in matchers  # the native-layer rule's tool
    assert "Write" in matchers  # the hook-layer rule's tool


def test_apply_reports_full_coverage_for_claude(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    report = ClaudeCodeHarness().apply_containment(POLICY, req)
    assert report.enabled is True
    assert report.rules_unenforceable == []
    assert set(report.rules_enforced) == {"no-out-of-worktree-write", "no-recursive-force-delete"}


def test_normalise_denials_reads_permission_denials():
    """Shape captured from a live 2.1.219 run."""
    stream = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "s",
            "permission_denials": [
                {
                    "tool_name": "Write",
                    "tool_use_id": "toolu_01",
                    "tool_input": {"file_path": "C:\\etc\\passwd"},
                }
            ],
        }
    )
    denials = ClaudeCodeHarness().normalise_denials(stream)
    assert len(denials) == 1
    assert denials[0].tool == "Write"
    assert denials[0].layer is ContainmentLayer.HOOK
    assert denials[0].target == "C:\\etc\\passwd"


def test_normalise_denials_recovers_rule_id_from_the_hook_reason():
    stream = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "PreToolUse",
                    "hook_name": "PreToolUse:Write",
                    "exit_code": 0,
                    "outcome": "success",
                    "output": json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": SCOPED_WRITES_REASON,
                            }
                        }
                    ),
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "s",
                    "permission_denials": [
                        {
                            "tool_name": "Write",
                            "tool_use_id": "t1",
                            "tool_input": {"file_path": "/etc/passwd"},
                        }
                    ],
                }
            ),
        ]
    )
    d = ClaudeCodeHarness().normalise_denials(stream)[0]
    assert d.rule_id == "no-out-of-worktree-write"
    assert d.reason == "Writes are scoped."


def test_no_denials_on_a_clean_stream():
    stream = json.dumps(
        {"type": "result", "subtype": "success", "session_id": "s", "permission_denials": []}
    )
    assert ClaudeCodeHarness().normalise_denials(stream) == []


def test_denials_become_session_events_and_are_counted():
    from sdlc.harness.session import digest_of

    stream = "\n".join(
        [
            json.dumps(
                {"type": "system", "subtype": "init", "session_id": "s", "model": "claude-opus-4-8"}
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "s",
                    "permission_denials": [
                        {
                            "tool_name": "Write",
                            "tool_use_id": "t1",
                            "tool_input": {"file_path": "/etc/passwd"},
                        }
                    ],
                }
            ),
        ]
    )
    session = ClaudeCodeHarness().normalise_session(stream)
    assert [e.kind for e in session.events].count("tool_denied") == 1
    digest = digest_of(session)
    assert digest.denials == 1
    assert digest.tool_calls == 0  # a blocked call is not a tool call


def _settings_path(req: HarnessRequest) -> str:
    idx = req.extra_args.index("--settings")
    return req.extra_args[idx + 1]


from sdlc.harness.adapters import OpenCodeHarness
from sdlc.harness.containment import Action, digest_tool_input
from sdlc.models import ToolGrant

ESC_RULE = Rule(
    id="no-out-of-worktree-write",
    layer=ContainmentLayer.HOOK,
    action=Action.ESCALATE,
    tools=["Write"],
    predicate="path_outside_worktree",
    reason="scoped",
)
OUTSIDE = {"file_path": "/etc/passwd"}


def _req(tmp_path):
    from sdlc.harness.adapters import HarnessRequest

    return HarnessRequest(prompt="go", cwd=str(tmp_path))


def _settings_of(req) -> dict:
    path = req.extra_args[req.extra_args.index("--settings") + 1]
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_claude_declares_escalation_support():
    assert ClaudeCodeHarness().supports_escalation is True
    assert OpenCodeHarness().supports_escalation is False


def test_escalate_rules_are_reported_as_escalatable(tmp_path):
    report = ClaudeCodeHarness().apply_containment(
        Policy(version=1, rules=[ESC_RULE]), _req(tmp_path)
    )
    assert report.rules_escalatable == ["no-out-of-worktree-write"]


def test_opencode_reports_no_escalatable_rules(tmp_path):
    """Degradation must be visible: opencode has no hook, so an escalate
    rule cannot raise a gate there."""
    report = OpenCodeHarness().apply_containment(
        Policy(version=1, rules=[ESC_RULE]), _req(tmp_path)
    )
    assert report.rules_escalatable == []


def test_escalate_rules_never_reach_the_native_deny_list(tmp_path):
    """A native deny beats a hook allow, so a natively denied rule could
    never be approved."""
    req = _req(tmp_path)
    ClaudeCodeHarness().apply_containment(Policy(version=1, rules=[ESC_RULE]), req)
    assert _settings_of(req)["permissions"]["deny"] == []


def test_grants_are_written_outside_the_worktree_and_passed_to_the_hook(tmp_path):
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=True,
        reason="ok",
    )
    req = _req(tmp_path)
    ClaudeCodeHarness().apply_containment(Policy(version=1, rules=[ESC_RULE]), req, [grant])
    hook_cmd = _settings_of(req)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--grants" in hook_cmd
    grants_path = Path(hook_cmd.split('--grants "')[1].split('"')[0])
    # The agent may write anywhere inside its worktree, so a grants file
    # placed there would be a file it could forge.
    assert tmp_path not in grants_path.parents
    assert json.loads(grants_path.read_text(encoding="utf-8"))[0]["tool_use_id"] == "toolu_1"


def test_no_grants_means_no_grants_flag(tmp_path):
    req = _req(tmp_path)
    ClaudeCodeHarness().apply_containment(Policy(version=1, rules=[ESC_RULE]), req)
    hook_cmd = _settings_of(req)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--grants" not in hook_cmd


def test_normalise_deferral_reads_a_pinned_result_event():
    """Pinned against claude 2.1.220's real output: a honoured defer ends the
    run with stop_reason tool_deferred and a structured deferred_tool_use."""
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "PreToolUse",
                    "output": json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "defer",
                                "permissionDecisionReason": SCOPED_WRITES_REASON,
                            }
                        }
                    ),
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "stop_reason": "tool_deferred",
                    "result": "",
                    "session_id": "sess-1",
                    "permission_denials": [],
                    "deferred_tool_use": {"id": "toolu_1", "name": "Write", "input": OUTSIDE},
                }
            ),
        ]
    )
    d = ClaudeCodeHarness().normalise_deferral(stdout)
    assert d is not None
    assert d.tool_use_id == "toolu_1"
    assert d.tool == "Write"
    assert d.rule_id == "no-out-of-worktree-write"
    assert d.target == "/etc/passwd"
    assert d.input_digest == digest_tool_input(OUTSIDE)


def test_normalise_deferral_is_none_on_an_ordinary_run():
    stdout = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "stop_reason": "completed",
            "result": "done",
            "session_id": "sess-1",
        }
    )
    assert ClaudeCodeHarness().normalise_deferral(stdout) is None


def test_declined_escalations_are_marked_on_the_denial():
    """Without this marker the BATCHED outcome would always count zero."""
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "PreToolUse",
                    "output": json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": "[no-out-of-worktree-write] escalation "
                                "unavailable (batched): Writes are scoped.",
                            }
                        }
                    ),
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "s",
                    "permission_denials": [
                        {"tool_name": "Write", "tool_use_id": "toolu_1", "tool_input": OUTSIDE}
                    ],
                }
            ),
        ]
    )
    denials = ClaudeCodeHarness().normalise_denials(stdout)
    assert len(denials) == 1
    assert denials[0].escalation_declined is True
    assert denials[0].rule_id == "no-out-of-worktree-write"


def test_an_ordinary_denial_is_not_marked_declined():
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "PreToolUse",
                    "output": json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": DESTRUCTIVE_REASON,
                            }
                        }
                    ),
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "s",
                    "permission_denials": [
                        {
                            "tool_name": "Bash",
                            "tool_use_id": "toolu_9",
                            "tool_input": {"command": "rm -rf /"},
                        }
                    ],
                }
            ),
        ]
    )
    assert ClaudeCodeHarness().normalise_denials(stdout)[0].escalation_declined is False


DEFER_STDOUT = "\n".join(
    [
        json.dumps(
            {
                "type": "system",
                "subtype": "hook_response",
                "hook_event": "PreToolUse",
                "output": json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "defer",
                            "permissionDecisionReason": SCOPED_WRITES_REASON,
                        }
                    }
                ),
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "stop_reason": "tool_deferred",
                "result": "",
                "session_id": "sess-1",
                "permission_denials": [],
                "deferred_tool_use": {"id": "toolu_1", "name": "Write", "input": OUTSIDE},
            }
        ),
    ]
)


def test_a_deferral_becomes_a_session_event_and_a_digest_count():
    """Clean-green runs must still report escalations — the same reason
    tool_denied is in the transcript (OQ-B7's keep-the-aggregates rule)."""
    from sdlc.harness.session import digest_of

    session = ClaudeCodeHarness().normalise_session(DEFER_STDOUT)
    assert [e.kind for e in session.events].count("tool_deferred") == 1
    assert digest_of(session).escalations == 1


def test_a_deferral_target_is_scrubbed():
    """Unlike a denial target, this one is rendered into a gate a HUMAN
    reads, so it is scrubbed where it is built."""
    stdout = DEFER_STDOUT.replace(
        json.dumps(OUTSIDE), json.dumps({"file_path": "/tmp/x", "content": "y"})
    )
    d = ClaudeCodeHarness().normalise_deferral(stdout)
    assert d is not None
    # scrub() is identity for text carrying no secret; the point of the test
    # is that the value passed THROUGH scrub, asserted by patching it.
    from unittest.mock import patch

    with patch("sdlc.harness.adapters.scrub", side_effect=lambda s: f"SCRUBBED:{s}") as m:
        d2 = ClaudeCodeHarness().normalise_deferral(stdout)
    assert m.called
    assert d2.target.startswith("SCRUBBED:")
