"""E-15: the other two harnesses. Unequal capability, reported not hidden."""

import json

from sdlc.harness.base import HarnessRequest
from sdlc.harness.containment import Policy, Rule
from sdlc.harness.cursor import CursorHarness
from sdlc.harness.models import ContainmentLayer
from sdlc.harness.opencode import OpenCodeHarness

POLICY = Policy(
    version=1,
    rules=[
        Rule(
            id="hook-only",
            layer=ContainmentLayer.HOOK,
            tools=["Write"],
            predicate="path_outside_worktree",
            reason="Writes are scoped to the task worktree.",
        ),
        Rule(
            id="native-ok",
            layer=ContainmentLayer.NATIVE,
            tools=["Bash"],
            predicate="command_matches",
            patterns=["rm -rf *"],
            reason="Destructive recursive delete.",
        ),
    ],
)


def test_opencode_declares_native_only():
    """--pure disables external plugins, which are opencode's only hook
    mechanism, so the native permission block is all it has."""
    assert OpenCodeHarness().containment == frozenset({ContainmentLayer.NATIVE})


def test_opencode_reports_hook_rules_as_unenforceable(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    report = OpenCodeHarness().apply_containment(POLICY, req)
    assert report.rules_enforced == ["native-ok"]
    assert report.rules_unenforceable == ["hook-only"]
    assert report.layers_active == [ContainmentLayer.NATIVE]


def test_opencode_writes_a_permission_deny_config(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    OpenCodeHarness().apply_containment(POLICY, req)
    doc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert doc["permission"]["bash"]["rm -rf *"] == "deny"


def test_opencode_merges_into_an_existing_config_without_clobbering(tmp_path):
    """Option A's load-bearing correctness property: the deny config lands in
    the worktree's opencode.json, which may already hold the repo's own keys
    (plugin block, prior denies). Those must be preserved, not overwritten."""
    pre = tmp_path / "opencode.json"
    pre.write_text(
        json.dumps({"plugin": ["x"], "permission": {"bash": {"old": "ask"}}}), encoding="utf-8"
    )
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    OpenCodeHarness().apply_containment(POLICY, req)
    doc = json.loads(pre.read_text(encoding="utf-8"))
    assert doc["plugin"] == ["x"]  # preserved
    assert doc["permission"]["bash"]["old"] == "ask"  # pre-existing kept
    assert doc["permission"]["bash"]["rm -rf *"] == "deny"  # new deny added


def test_cursor_declares_no_layers():
    assert CursorHarness().containment == frozenset()


def test_cursor_reports_everything_unenforceable(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    report = CursorHarness().apply_containment(POLICY, req)
    assert report.layers_active == []
    assert set(report.rules_unenforceable) == {"hook-only", "native-ok"}
