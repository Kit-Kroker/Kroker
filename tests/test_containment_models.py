"""E-15/E-16: containment model contracts."""
from sdlc.models import (
    ContainmentConfig, ContainmentLayer, ContainmentReport,
    HarnessKind, HarnessRunResult, PipelineConfig, SessionDigest, ToolDenial,
)


def test_layer_is_str_enum_with_two_members():
    assert ContainmentLayer.NATIVE == "native"
    assert ContainmentLayer.HOOK == "hook"
    assert len(list(ContainmentLayer)) == 2


def test_tool_denial_round_trips():
    d = ToolDenial(tool="Write", rule_id="no-out-of-worktree-write",
                   layer=ContainmentLayer.HOOK, reason="scoped to worktree",
                   target="/etc/passwd")
    assert ToolDenial.model_validate_json(d.model_dump_json()) == d


def test_containment_report_defaults_to_disabled():
    r = ContainmentReport()
    assert r.enabled is False
    assert r.layers_active == []
    assert r.rules_enforced == []
    assert r.rules_unenforceable == []


def test_harness_run_result_defaults_have_no_denials():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0,
                         summary="ok")
    assert r.denials == []
    assert r.containment is None


def test_session_digest_counts_denials():
    assert SessionDigest().denials == 0


def test_pipeline_config_containment_is_off_by_default():
    cfg = PipelineConfig()
    assert cfg.containment_enabled is False
    assert cfg.containment.strict is False
    assert cfg.containment.policy_path is None
