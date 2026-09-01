"""E-15/E-16: policy asset parsing and resolution."""

from pathlib import Path

import pytest

from sdlc.harness.containment import (
    Action,
    ContainmentError,
    Predicate,
    load_policy,
)
from sdlc.models import ContainmentLayer

GOOD = """
version: 1
rules:
  - id: no-out-of-worktree-write
    layer: hook
    tools: [Write, Edit]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."
  - id: no-recursive-force-delete
    layer: native
    tools: [Bash]
    predicate: command_matches
    patterns: ["rm -rf *"]
    reason: "Destructive recursive delete."
"""


def _write(tmp_path, text):
    p = tmp_path / "containment.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_loads_rules_in_declared_order(tmp_path):
    pol = load_policy(_write(tmp_path, GOOD))
    assert [r.id for r in pol.rules] == ["no-out-of-worktree-write", "no-recursive-force-delete"]
    assert pol.rules[0].layer is ContainmentLayer.HOOK
    assert pol.rules[0].predicate is Predicate.PATH_OUTSIDE_WORKTREE
    assert pol.rules[1].patterns == ["rm -rf *"]


def test_rejects_unsupported_version(tmp_path):
    with pytest.raises(ContainmentError, match="version"):
        load_policy(_write(tmp_path, "version: 2\nrules: []\n"))


def test_rejects_unknown_predicate(tmp_path):
    bad = GOOD.replace("path_outside_worktree", "rm_everything")
    with pytest.raises(ContainmentError, match="rm_everything"):
        load_policy(_write(tmp_path, bad))


def test_rejects_duplicate_rule_id(tmp_path):
    dup = (
        GOOD
        + """
  - id: no-out-of-worktree-write
    layer: hook
    tools: [Write]
    predicate: path_outside_worktree
    reason: "dup"
"""
    )
    with pytest.raises(ContainmentError, match="duplicate"):
        load_policy(_write(tmp_path, dup))


def test_rejects_missing_file_with_actionable_message(tmp_path):
    with pytest.raises(ContainmentError, match="containment policy"):
        load_policy(str(tmp_path / "absent.yaml"))


def test_env_var_resolves_when_no_arg(tmp_path, monkeypatch):
    path = _write(tmp_path, GOOD)
    monkeypatch.setenv("SDLC_CONTAINMENT_POLICY", path)
    assert len(load_policy().rules) == 2


def test_shipped_asset_parses_and_covers_fr703():
    """The repo's own policy must load and cover FR-703's three clauses."""
    pol = load_policy()
    ids = {r.id for r in pol.rules}
    assert "no-out-of-worktree-write" in ids
    assert "no-recursive-force-delete" in ids
    assert "no-agent-config-write" in ids
    assert "egress-allowlist" in ids


def test_rules_default_to_deny(tmp_path):
    """Every rule that landed with E-16 keeps its exact behaviour."""
    p = tmp_path / "p.yaml"
    p.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8",
    )
    policy = load_policy(p)
    assert policy.rules[0].action is Action.DENY


def test_escalate_action_parses(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    action: escalate\n"
        "    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8",
    )
    assert load_policy(p).rules[0].action is Action.ESCALATE


def test_escalate_on_a_native_rule_is_refused(tmp_path):
    """permissions.deny strictly beats a hook allow (E-15 §0), so a natively
    compiled rule could never be approved — the gate would be theatre."""
    p = tmp_path / "p.yaml"
    p.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: native\n    action: escalate\n"
        "    tools: [Bash]\n"
        "    predicate: command_matches\n    patterns: ['rm -rf *']\n"
        "    reason: nope\n",
        encoding="utf-8",
    )
    with pytest.raises(ContainmentError, match="escalate"):
        load_policy(p)


def test_shipped_asset_escalates_only_the_out_of_worktree_write():
    """The mechanism must run on the DEFAULT policy, not only in tests
    (E-27's lesson), and the hard denials must stay hard."""
    policy = load_policy(Path(__file__).parents[1] / "policy" / "containment.yaml")
    by_action = {r.id: r.action for r in policy.rules}
    assert by_action["no-out-of-worktree-write"] is Action.ESCALATE
    assert by_action["no-recursive-force-delete"] is Action.DENY
    assert by_action["no-agent-config-write"] is Action.DENY
    assert by_action["egress-allowlist"] is Action.DENY
