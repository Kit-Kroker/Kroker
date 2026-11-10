"""C7 ruling OQ8(a): the three label inputs reach RunSummary.

Before C7 retro could see only fix_attempts. plan_drift lived transiently on
a BenchmarkRecord and reached durable storage only in benchmark mode; the
judge score reached neither summary nor trace. Both now ride STAGE_ENDED,
which is emitted from a record that already carries them.
"""

import inspect
from datetime import UTC, datetime, timedelta

from sdlc.core.models import GateOutcomeSummary, StageOutcome
from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind
from sdlc.workflows.gates import GateHost

T0 = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _ev(seq, kind, stage=None, **data):
    return RunEvent(
        seq=seq,
        at=T0 + timedelta(seconds=seq),
        kind=kind,
        stage=stage,
        data={k: str(v) for k, v in data.items()},
    )


def test_stage_outcome_carries_the_new_label_inputs_optionally():
    """Old records validate unchanged -- the fields default to None, which
    means UNMEASURED, not zero."""
    s = StageOutcome(stage="plan", role="planner", outcome="pass", duration_s=1.0)
    assert s.plan_drift is None
    assert s.quality_score is None
    assert s.quality_judge is None


def test_gate_outcome_summary_carries_author_model_optionally():
    g = GateOutcomeSummary(
        gate="architecture", round=1, policy="soft", decided_by="policy", approved=True
    )
    assert g.author_model is None


def test_build_run_summary_reads_plan_drift_and_quality_score():
    trace = [
        _ev(
            1,
            RunEventKind.STAGE_ENDED,
            stage="code",
            role="dev",
            outcome="pass",
            duration_s=1.0,
            fix_attempts=2,
            plan_drift=0.25,
            quality_score=0.8,
            quality_judge="contract",
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.stages[0].plan_drift == 0.25
    assert s.stages[0].quality_score == 0.8
    assert s.stages[0].fix_attempts == 2


def test_the_judge_identity_travels_with_the_score():
    """Without it, a CONTRACT 1.0 pass-fail value and a rubric judge score are
    indistinguishable downstream, and the weaker one silently stands in for
    the stronger (ruling OQ1)."""
    trace = [
        _ev(
            1,
            RunEventKind.STAGE_ENDED,
            stage="plan",
            role="planner",
            outcome="pass",
            duration_s=1.0,
            quality_score=0.85,
            quality_judge="llm_judge",
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.stages[0].quality_judge == "llm_judge"


def test_build_run_summary_reads_author_model_off_the_gate_event():
    trace = [
        _ev(
            1,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="soft",
            decided_by="policy",
            approved="true",
            confidence=0.9,
            author_model="anthropic/claude-x",
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.gates[0].author_model == "anthropic/claude-x"


def test_a_pre_c7_trace_still_builds():
    """No plan_drift, no quality_score, no quality_judge, no author_model keys
    at all."""
    trace = [
        _ev(
            1,
            RunEventKind.STAGE_ENDED,
            stage="plan",
            role="planner",
            outcome="pass",
            duration_s=1.0,
        ),
        _ev(
            2,
            RunEventKind.GATE_DECIDED,
            gate="plan",
            round=1,
            policy="soft",
            decided_by="human",
            approved="true",
        ),
        _ev(3, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.stages[0].plan_drift is None
    assert s.stages[0].quality_judge is None
    assert s.gates[0].author_model is None


def test_author_model_reaches_the_hook_as_a_parameter():
    """The sibling of test_confidence_reaches_the_hook_as_a_parameter
    (tests/test_gate_host.py:44), for the same wave-mode reason: gates
    interleave, so a stashed value would be clobbered by the next gate to
    open while this one awaits a human."""
    sig = inspect.signature(GateHost._on_gate_decided)
    assert "author_model" in sig.parameters
    assert not hasattr(GateHost(), "_last_gate_author_model")


def test_gate_takes_author_model():
    sig = inspect.signature(GateHost._gate)
    assert "author_model" in sig.parameters


def test_revisable_stage_takes_author_model():
    from sdlc.core.context import StageContext
    from sdlc.workflows.role_host import RoleHost

    assert "author_model" in inspect.signature(RoleHost._revisable_stage).parameters
    assert "author_model" in inspect.signature(StageContext.revisable_stage).parameters


def test_both_proposer_stages_pass_their_resolved_model():
    """The stage-key trap: resolve_role_model is keyed by STAGE_ROLES
    ('architect', 'plan'), not by the gate names ('architecture', 'plan'), so
    the composition must be HANDED the model rather than resolving it from
    the gate name. 020 T028: the step() composites are gone; the handoff
    now lives in the graph's precode nodes (mirroring the T006 pins)."""
    import pathlib

    precode = pathlib.Path("src/sdlc/workflows/graph_nodes/precode.py").read_text(encoding="utf-8")
    for stage, fn in (("architect", "architect_node"), ("plan", "plan_node")):
        idx = precode.find(f"async def {fn}")
        assert idx != -1, fn
        node_src = precode[idx : idx + 1600]
        assert f'resolve_role_model(cfg, "{stage}")' in node_src, (
            f"{fn} must resolve the {stage} model by its stage key"
        )


def test_precode_hands_the_resolved_model_to_both_producer_results():
    """020 T006 (plan T013): the live producers store the model they resolved.
    gate_node reads that stored author_model for ctx.gate(author_model=...), so
    both precode nodes must return prep.resolved_model on their NodeResult.
    The architecture node is the 'spec' port, the plan node is the 'plan' port."""
    import pathlib

    src = pathlib.Path("src/sdlc/workflows/graph_nodes/precode.py").read_text(encoding="utf-8")
    assert 'return NodeResult(port="spec", payload=spec, author_model=prep.resolved_model)' in src
    assert 'return NodeResult(port="plan", payload=plan, author_model=prep.resolved_model)' in src
