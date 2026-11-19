from sdlc.maintenance.gate import bears_human_required, risk_class
from sdlc.maintenance.models import (
    Incident,
    IncidentState,
    RepairAction,
    RepairPlan,
    RiskClass,
)
from sdlc.maintenance.render import gate_context_text, incidents_table
from tests.maintenance.conftest import build_break_finding


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


# --- FR-502 rendering: the gate context line and the incidents class column ---


def _incident(**kw) -> Incident:
    # Mirrors test_render.py's incident fixture (builders stay local to the
    # file per the us-suite rule; the conftest finding keeps the shape equal).
    base = dict(
        no=11,
        key="build_probe:build_failed::",
        kind="finding",
        finding=build_break_finding(),
        commit_sha="a" * 40,
        first_seen_cycle=2,
        last_seen_cycle=2,
        seen_count=1,
        state=IncidentState.AWAITING_DECISION,
        plan=None,
        plan_attempts=1,
        decision=None,
        note="",
    )
    base.update(kw)
    return Incident(**base)


MIXED_LINE = "human-required ops: rollback — a human must decide; policy cannot approve"


def test_gate_context_names_the_human_required_ops_for_a_mixed_plan():
    inc = _incident(
        plan=_plan(
            RepairAction(kind="code_fix", summary="pin the wheel", target_paths=["pyproject.toml"]),
            RepairAction(kind="ops", summary="roll the deploy back", ops_action="rollback"),
        )
    )
    assert MIXED_LINE in gate_context_text(inc)


def test_gate_context_dedupes_the_verbs_in_plan_order():
    # Two rollback actions render one `rollback`; order follows the plan.
    inc = _incident(
        plan=_plan(
            RepairAction(kind="ops", summary="r", ops_action="rollback"),
            RepairAction(kind="ops", summary="s", ops_action="scale"),
            RepairAction(kind="ops", summary="r2", ops_action="rollback"),
        )
    )
    line = next(
        ln for ln in gate_context_text(inc).splitlines() if ln.startswith("human-required ops:")
    )
    expected = "human-required ops: rollback, scale — a human must decide; policy cannot approve"
    assert line == expected


def test_gate_context_has_no_human_required_line_for_a_pure_code_fix_plan():
    inc = _incident(plan=_plan(RepairAction(kind="code_fix", summary="s", target_paths=["p.py"])))
    assert "human-required ops" not in gate_context_text(inc)


def test_incidents_table_renders_the_class_tag_for_a_mixed_plan():
    inc = _incident(
        no=12,
        plan=_plan(
            RepairAction(kind="code_fix", summary="pin the wheel", target_paths=["pyproject.toml"]),
            RepairAction(kind="ops", summary="roll the deploy back", ops_action="rollback"),
        ),
    )
    row = next(ln for ln in incidents_table([inc]).splitlines() if ln.startswith("INC-12"))
    tokens = row.split()
    assert tokens[-3].startswith("repair:12"), "the gate column precedes the class column"
    assert tokens[-2] == "rollback[HUMAN_REQUIRED]", "the class tag renders the enum NAME"
    assert tokens[-1] == "-", "child (no execution) closes the row after class"


def test_incidents_table_renders_a_dash_without_classed_actions():
    coded = _incident(
        no=13, plan=_plan(RepairAction(kind="code_fix", summary="s", target_paths=["p.py"]))
    )
    bare = _incident(no=14)
    out = incidents_table([coded, bare])
    for no in (13, 14):
        tokens = next(ln for ln in out.splitlines() if ln.startswith(f"INC-{no}")).split()
        assert tokens[-2] == "-", f"no classed actions — the class column is '-' (INC-{no})"
        assert tokens[-1] == "-", f"child stays last (INC-{no})"


def test_a_wide_class_column_still_renders_one_row_line():
    # Three classed verbs join to 72 chars of tags; the column is bounded like
    # `key` (:<44.44) so the row never wraps (the over-long-key precedent).
    inc = _incident(
        no=15,
        plan=_plan(
            RepairAction(kind="ops", summary="r", ops_action="rollback"),
            RepairAction(kind="ops", summary="s", ops_action="restart"),
            RepairAction(kind="ops", summary="c", ops_action="scale"),
        ),
    )
    rows = [ln for ln in incidents_table([inc]).splitlines() if ln.startswith("INC-15")]
    assert len(rows) == 1
    assert "rollback[HUMAN_REQUIRED], restart[HUMAN_REQU" in rows[0]  # bounded at 44
