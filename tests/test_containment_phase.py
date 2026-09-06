"""C2 Task 1: phase vocabulary, the repair parameter, and drift-set accessors."""

from __future__ import annotations

import pytest

from sdlc.harness.containment import (
    Action,
    ContainmentError,
    Phase,
    Policy,
    Predicate,
    Rule,
    drift_globs,
    evaluate,
    has_repair_rule,
    load_policy,
    repair_patterns,
)
from sdlc.harness.hook import decide
from sdlc.harness.models import ContainmentLayer


def _freeze_rule() -> Rule:
    return Rule(
        id="no-test-edit-during-repair",
        layer=ContainmentLayer.NATIVE,
        action=Action.DENY,
        phase=Phase.REPAIR,
        tools=["Write", "Edit", "NotebookEdit"],
        predicate=Predicate.PATH_MATCHES,
        patterns=["tests/**", "**/tests/**"],
        reason="Tests are frozen during repair.",
    )


def _always_rule() -> Rule:
    return Rule(
        id="no-agent-config-write",
        layer=ContainmentLayer.NATIVE,
        tools=["Write", "Edit"],
        predicate=Predicate.PATH_MATCHES,
        patterns=["**/.claude/**"],
        reason="The agent may not rewrite its own permission config.",
    )


WT = "/wt"


@pytest.mark.parametrize(
    "rule,target,repair,expect_allow",
    [
        # The freeze rule is INERT on pass 1 and BITES during repair.
        (_freeze_rule(), "tests/test_a.py", False, True),
        (_freeze_rule(), "tests/test_a.py", True, False),
        # A phase-less (ALWAYS) rule is unaffected by the repair bit.
        (_always_rule(), "/wt/.claude/settings.json", False, False),
        (_always_rule(), "/wt/.claude/settings.json", True, False),
        # A repair rule still only matches its own patterns.
        (_freeze_rule(), "src/app.py", True, True),
    ],
)
def test_evaluate_respects_phase(rule, target, repair, expect_allow):
    policy = Policy(version=1, rules=[rule])
    verdict = evaluate(policy, "Write", {"file_path": target}, WT, repair=repair)
    assert verdict.allow is expect_allow


def test_repair_defaults_to_false_so_existing_callers_are_unchanged():
    """Every pre-C2 call site omits `repair`; omitting it must mean pass 1."""
    policy = Policy(version=1, rules=[_freeze_rule()])
    assert evaluate(policy, "Write", {"file_path": "tests/test_a.py"}, WT).allow is True


def test_rule_without_phase_key_defaults_to_always(tmp_path):
    """Old-policy compat: a YAML with no `phase` anywhere parses and behaves
    all-always, so no version bump is needed."""
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: r1\n"
        "    layer: native\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: legacy\n",
        encoding="utf-8",
    )
    policy = load_policy(p)
    assert policy.rules[0].phase is Phase.ALWAYS
    assert policy.drift_paths == []
    # An ALWAYS rule fires in both phases.
    for repair in (False, True):
        assert (
            evaluate(policy, "Write", {"file_path": "tests/x.py"}, WT, repair=repair).allow is False
        )


def test_unknown_phase_value_is_a_containment_error(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: r1\n"
        "    layer: native\n"
        "    phase: sometimes\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: bad\n",
        encoding="utf-8",
    )
    with pytest.raises(ContainmentError):
        load_policy(p)


def test_drift_paths_parse_and_compose_the_drift_set(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "drift_paths:\n"
        "  - 'pyproject.toml'\n"
        "  - '**/pyproject.toml'\n"
        "rules:\n"
        "  - id: freeze\n"
        "    layer: native\n"
        "    phase: repair\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: frozen\n",
        encoding="utf-8",
    )
    policy = load_policy(p)
    assert policy.drift_paths == ["pyproject.toml", "**/pyproject.toml"]
    assert repair_patterns(policy) == ["tests/**"]
    # D = G then C, order-stable, de-duplicated.
    assert drift_globs(policy) == ["tests/**", "pyproject.toml", "**/pyproject.toml"]
    assert has_repair_rule(policy) is True


@pytest.mark.parametrize(
    "value",
    [
        # A scalar: `list()` would shred it into 14 one-character globs that
        # pass pydantic's list[str] and match nothing.
        "pyproject.toml",
        # A non-string element: without the guard this escapes as a pydantic
        # ValidationError, which is not a ContainmentError.
        "[1, 2]",
        # A mapping: `list()` would yield its keys.
        "{a: 1}",
    ],
)
def test_malformed_drift_paths_is_a_containment_error(tmp_path, value):
    p = tmp_path / "containment.yaml"
    p.write_text(f"version: 1\ndrift_paths: {value}\nrules: []\n", encoding="utf-8")
    with pytest.raises(ContainmentError):
        load_policy(p)


def test_drift_globs_dedupes_without_reordering():
    policy = Policy(
        version=1,
        rules=[
            Rule(
                id="freeze",
                layer=ContainmentLayer.NATIVE,
                phase=Phase.REPAIR,
                tools=["Write"],
                predicate=Predicate.PATH_MATCHES,
                patterns=["tests/**", "conftest.py"],
                reason="frozen",
            )
        ],
        drift_paths=["conftest.py", "pyproject.toml"],
    )
    assert drift_globs(policy) == ["tests/**", "conftest.py", "pyproject.toml"]


def test_has_repair_rule_false_when_policy_carries_none():
    assert has_repair_rule(Policy(version=1, rules=[_always_rule()])) is False


def test_repair_patterns_ignores_always_rules():
    policy = Policy(version=1, rules=[_always_rule(), _freeze_rule()])
    assert repair_patterns(policy) == ["tests/**", "**/tests/**"]


# --- hook ---------------------------------------------------------------


def _payload(target: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": target}, "tool_use_id": "tu_1"}


def test_hook_decide_allows_test_write_on_pass_one():
    policy = Policy(version=1, rules=[_freeze_rule()])
    out = decide(_payload("tests/test_a.py"), policy, WT, repair=False)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_hook_decide_denies_test_write_during_repair():
    policy = Policy(version=1, rules=[_freeze_rule()])
    out = decide(_payload("tests/test_a.py"), policy, WT, repair=True)
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    # The rule id must ride the reason -- normalise_denials reads it back out.
    assert hso["permissionDecisionReason"].startswith("[no-test-edit-during-repair] ")
