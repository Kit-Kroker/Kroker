from sdlc.maintenance.gate import bears_human_required, risk_class
from sdlc.maintenance.models import RepairAction, RepairPlan, RiskClass


def _plan(*actions):
    return RepairPlan(
        analysis="a",
        actions=list(actions),
        self_confidence=0.9,
        floor=0.9,
        effective=0.9,
        author_model="m",
    )


def test_each_ops_verb_is_human_required():
    for verb in ("rollback", "restart", "scale"):
        a = RepairAction(kind="ops", summary="s", ops_action=verb)
        assert risk_class(a) == RiskClass.HUMAN_REQUIRED


def test_code_fix_has_no_class_confidence_governs():
    assert risk_class(RepairAction(kind="code_fix", summary="s", target_paths=["p.py"])) is None


def test_malformed_ops_action_fails_closed():
    # kind="ops" with ops_action=None has no model validator — the
    # classification must never let it pass as unclassed (Review Focus 2).
    assert risk_class(RepairAction(kind="ops", summary="s")) == RiskClass.HUMAN_REQUIRED


def test_bears_human_required_over_plan_shapes():
    assert (
        bears_human_required(
            _plan(
                RepairAction(kind="code_fix", summary="s", target_paths=["p.py"]),
                RepairAction(kind="ops", summary="s", ops_action="rollback"),
            )
        )
        is True
    )
    assert (
        bears_human_required(
            _plan(RepairAction(kind="code_fix", summary="s", target_paths=["p.py"]))
        )
        is False
    )
    assert bears_human_required(_plan()) is False  # Review Focus 3
