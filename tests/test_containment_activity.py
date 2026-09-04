"""E-15: fail-closed wiring in run_coding_task."""

import json
from pathlib import Path

import pytest

from sdlc.core.models import (
    HarnessKind,
)
from sdlc.harness.base import HarnessRequest
from sdlc.harness.claude_code import ClaudeCodeHarness
from sdlc.harness.containment import ContainmentError
from sdlc.harness.cursor import CursorHarness
from sdlc.harness.models import (
    ContainmentLayer,
    ToolGrant,
)
from sdlc.harness.opencode import OpenCodeHarness
from sdlc.harness.registry import HARNESSES
from sdlc.stages.code.activities import CodingTaskInput, _resolve_containment

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
    inp = CodingTaskInput(
        harness=None,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_policy_path=_policy(tmp_path),
    )
    policy, report = _resolve_containment(ClaudeCodeHarness(), inp)
    assert [r.id for r in policy.rules] == ["hook-only"]
    assert report.layers_active == [ContainmentLayer.NATIVE, ContainmentLayer.HOOK]


def test_zero_layer_harness_refuses_to_start(tmp_path):
    inp = CodingTaskInput(
        harness=None,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_policy_path=_policy(tmp_path),
    )
    with pytest.raises(ContainmentError, match="cannot enforce"):
        _resolve_containment(CursorHarness(), inp)


def test_partial_coverage_runs_but_records_the_gap(tmp_path):
    inp = CodingTaskInput(
        harness=None,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_policy_path=_policy(tmp_path),
    )
    _, report = _resolve_containment(OpenCodeHarness(), inp)
    assert report.rules_unenforceable == ["hook-only"]


def test_strict_promotes_partial_coverage_to_a_refusal(tmp_path):
    inp = CodingTaskInput(
        harness=None,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_strict=True,
        containment_policy_path=_policy(tmp_path),
    )
    with pytest.raises(ContainmentError, match="unenforceable"):
        _resolve_containment(OpenCodeHarness(), inp)


def test_missing_policy_fails_closed(tmp_path):
    inp = CodingTaskInput(
        harness=None,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_policy_path=str(tmp_path / "absent.yaml"),
    )
    with pytest.raises(ContainmentError):
        _resolve_containment(ClaudeCodeHarness(), inp)


def test_grants_reach_the_compiled_hook_command(tmp_path, monkeypatch):
    """The activity's job is to get the workflow's decision to the hook."""
    policy = tmp_path / "containment.yaml"
    policy.write_text(
        "version: 1\nrules:\n"
        "  - id: no-out-of-worktree-write\n    layer: hook\n"
        "    action: escalate\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: scoped\n",
        encoding="utf-8",
    )
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest="deadbeef",
        rule_id="no-out-of-worktree-write",
        approved=True,
    )
    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="go",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_policy_path=str(policy),
        grants=[grant],
    )
    req = HarnessRequest(prompt="go", cwd=str(tmp_path))
    _, report = _resolve_containment(HARNESSES[HarnessKind.CLAUDE_CODE], inp, req)
    settings = json.loads(
        Path(req.extra_args[req.extra_args.index("--settings") + 1]).read_text(encoding="utf-8")
    )
    hook_cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--grants" in hook_cmd
    assert report.rules_escalatable == ["no-out-of-worktree-write"]


def test_coding_task_input_defaults_to_no_grants(tmp_path):
    inp = CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="go", worktree=str(tmp_path))
    assert inp.grants == []
