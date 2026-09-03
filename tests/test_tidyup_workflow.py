"""E-44. Pure helpers directly; sequencing through the workflow, following
tests/test_triage_workflow.py."""

from __future__ import annotations

import pytest

from sdlc.core.models import (
    GatePolicy,
)
from sdlc.workflows.tidyup import (
    FixRunResult,
    TidyUpInput,
    TidyUpReport,
    branches_to_verify,
    fix_workflow_id,
    reached_a_pr,
    triage_gates,
    unrecognized_selection,
)


def test_input_defaults():
    inp = TidyUpInput(repo_dir="/r")
    assert inp.commit == "HEAD"
    assert inp.build_probe is True
    assert inp.max_fix_runs == 10


def test_fix_cfg_disables_the_deploy_gate():
    """D9: feature.py opens the deploy gate BEFORE checking deploy.enabled,
    and the default policy is HARD -- so an unconfigured tidy-up PR would
    park for 48h on a deploy that was never going to run."""
    inp = TidyUpInput(repo_dir="/r")
    assert inp.fix_cfg.gates["deploy"].policy is GatePolicy.OFF
    assert inp.fix_cfg.deploy.enabled is False


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("deployed:https://example/pr/1", True),
        ("merged-not-deployed:https://example/pr/1", True),
        ("merged-not-deployed:skipped:benchmark-run-has-no-remote", True),
        ("rejected:merge:soft-verdict", False),
        ("rejected:plan", False),
        ("rejected:budget", False),
        ("failed:plan-validation:cycle", False),
        ("", False),
    ],
)
def test_reached_a_pr(outcome, expected):
    """D6 step 6: 'produced a branch worth merging' is read off the return
    string, which is the only thing FeatureWorkflow gives a caller."""
    assert reached_a_pr(outcome) is expected


def test_branches_to_verify_keeps_accepted_order_and_drops_failures():
    runs = [
        FixRunResult(
            identity="a", workflow_id="w-fix-00", outcome="merged-not-deployed:u", branch="b0"
        ),
        FixRunResult(
            identity="b", workflow_id="w-fix-01", outcome="rejected:merge:soft-verdict", branch="b1"
        ),
        FixRunResult(identity="c", workflow_id="w-fix-02", outcome="deployed:u", branch="b2"),
    ]
    assert branches_to_verify(runs) == ["b0", "b2"]


def test_branches_to_verify_drops_a_run_with_no_branch():
    runs = [FixRunResult(identity="a", workflow_id="w", outcome="deployed:u", branch=None)]
    assert branches_to_verify(runs) == []


def test_fix_workflow_id_is_derived_and_stable():
    """D10: no uuid, no clock. Replay must produce the same id."""
    assert fix_workflow_id("tidyup-repo-x", 0) == "tidyup-repo-x-fix-00"
    assert fix_workflow_id("tidyup-repo-x", 7) == "tidyup-repo-x-fix-07"
    assert fix_workflow_id("tidyup-repo-x", 11) == "tidyup-repo-x-fix-11"


def test_report_defaults_are_honest_about_an_unmeasured_after():
    """TidyUpReport.before is required (a report always has a baseline); the
    after side is optional and None until the verification triage runs."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TidyUpReport(before=None, readiness_before=None)  # type: ignore[arg-type]


def test_before_triage_inherits_the_operators_gates():
    """The before-triage gates admission, so the operator's HARD readiness
    setting applies unchanged."""
    from sdlc.core.models import (
        GateConfig,
        GatePolicy,
        GateSettings,
    )

    hard = GateSettings(
        default_gate_policy=GatePolicy.HARD, gates={"readiness": GateConfig(policy=GatePolicy.HARD)}
    )
    assert triage_gates(hard, gating=True) is hard


def test_after_triage_never_parks_on_a_readiness_gate():
    """The after-triage only MEASURES the verification tree for the delta; it
    must not open a readiness gate and park 48h. With --no-build-probe the
    after-verdict is INDETERMINATE, which a HARD readiness gate would block
    on. OFF resolves automatically; the verdict is still recorded."""
    from sdlc.core.models import (
        GateConfig,
        GatePolicy,
        GateSettings,
    )

    hard = GateSettings(
        default_gate_policy=GatePolicy.HARD, gates={"readiness": GateConfig(policy=GatePolicy.HARD)}
    )
    after = triage_gates(hard, gating=False)
    assert after.default_gate_policy is GatePolicy.OFF


def test_unrecognized_selection_is_surfaced_not_dropped():
    """The CLI confirms the count it SENT; the workflow keeps only the subset
    in the backlog. The difference is surfaced in the report rather than
    dropped silently, so the two counts can be reconciled."""
    backlog = ["a", "b", "c"]
    assert unrecognized_selection(["a", "x", "y"], backlog) == ["x", "y"]


def test_unrecognized_selection_is_empty_when_no_signal_or_all_known():
    assert unrecognized_selection(None, ["a"]) == []
    assert unrecognized_selection(["a", "b"], ["a", "b"]) == []
