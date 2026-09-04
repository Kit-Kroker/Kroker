"""E-15/E-16: containment model contracts."""

from sdlc.core.models import (
    HarnessKind,
    PipelineConfig,
)
from sdlc.harness.models import (
    ContainmentLayer,
    ContainmentReport,
    DeferredToolUse,
    EscalationOutcome,
    HarnessRunResult,
    SessionDigest,
    ToolDenial,
    ToolGrant,
)


def test_layer_is_str_enum_with_two_members():
    assert ContainmentLayer.NATIVE == "native"
    assert ContainmentLayer.HOOK == "hook"
    assert len(list(ContainmentLayer)) == 2


def test_tool_denial_round_trips():
    d = ToolDenial(
        tool="Write",
        rule_id="no-out-of-worktree-write",
        layer=ContainmentLayer.HOOK,
        reason="scoped to worktree",
        target="/etc/passwd",
    )
    assert ToolDenial.model_validate_json(d.model_dump_json()) == d


def test_containment_report_defaults_to_disabled():
    r = ContainmentReport()
    assert r.enabled is False
    assert r.layers_active == []
    assert r.rules_enforced == []
    assert r.rules_unenforceable == []


def test_harness_run_result_defaults_have_no_denials():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="ok")
    assert r.denials == []
    assert r.containment is None


def test_session_digest_counts_denials():
    assert SessionDigest().denials == 0


def test_pipeline_config_containment_is_off_by_default():
    cfg = PipelineConfig()
    assert cfg.containment_enabled is False
    assert cfg.containment.strict is False
    assert cfg.containment.policy_path is None


def test_tool_grant_round_trips_through_json():
    """Grants travel on CodingTaskInput through the Temporal payload
    converter, so they must survive model_validate_json."""
    g = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest="deadbeef",
        rule_id="no-out-of-worktree-write",
        approved=True,
        reason="fine by me",
    )
    assert ToolGrant.model_validate_json(g.model_dump_json()) == g


def test_deferred_tool_use_target_is_optional():
    d = DeferredToolUse(
        tool_use_id="toolu_1", tool="Write", input_digest="deadbeef", rule_id="r", reason="why"
    )
    assert d.target is None


def test_tool_denial_declines_default_to_false():
    """E-16 denials must keep their exact shape and meaning."""
    d = ToolDenial(tool="Write", rule_id="r", layer=ContainmentLayer.HOOK, reason="nope")
    assert d.escalation_declined is False


def test_harness_run_result_has_no_deferral_by_default():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="")
    assert r.deferred is None


def test_escalations_are_capped_at_three_by_default():
    assert PipelineConfig().max_tool_escalations == 3


def test_escalation_outcome_distinguishes_never_asked_from_refused():
    """BATCHED is the measurable size of the solo-only hole; folding it into
    REJECTED would make it uncountable."""
    assert EscalationOutcome.BATCHED != EscalationOutcome.REJECTED
    assert EscalationOutcome.TIMEOUT != EscalationOutcome.REJECTED
