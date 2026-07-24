"""E-15: fail-closed wiring in run_coding_task."""
import pytest

from sdlc.activities import CodingTaskInput, _resolve_containment
from sdlc.harness.adapters import ClaudeCodeHarness, CursorHarness, OpenCodeHarness
from sdlc.harness.containment import ContainmentError
from sdlc.models import ContainmentLayer

POLICY_YAML = """
version: 1
rules:
  - id: hook-only
    layer: hook
    tools: [Write]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."
"""


def _policy(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(POLICY_YAML, encoding="utf-8")
    return str(p)


def test_disabled_returns_no_policy_and_no_report(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path))
    policy, report = _resolve_containment(ClaudeCodeHarness(), inp)
    assert policy is None
    assert report is None


def test_enabled_loads_the_policy(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=_policy(tmp_path))
    policy, report = _resolve_containment(ClaudeCodeHarness(), inp)
    assert [r.id for r in policy.rules] == ["hook-only"]
    assert report.layers_active == [ContainmentLayer.NATIVE,
                                    ContainmentLayer.HOOK]


def test_zero_layer_harness_refuses_to_start(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=_policy(tmp_path))
    with pytest.raises(ContainmentError, match="cannot enforce"):
        _resolve_containment(CursorHarness(), inp)


def test_partial_coverage_runs_but_records_the_gap(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=_policy(tmp_path))
    _, report = _resolve_containment(OpenCodeHarness(), inp)
    assert report.rules_unenforceable == ["hook-only"]


def test_strict_promotes_partial_coverage_to_a_refusal(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True, containment_strict=True,
                          containment_policy_path=_policy(tmp_path))
    with pytest.raises(ContainmentError, match="unenforceable"):
        _resolve_containment(OpenCodeHarness(), inp)


def test_missing_policy_fails_closed(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=str(tmp_path / "absent.yaml"))
    with pytest.raises(ContainmentError):
        _resolve_containment(ClaudeCodeHarness(), inp)
