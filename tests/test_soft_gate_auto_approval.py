from sdlc.calibration.decision import auto_decision_for
from sdlc.calibration.models import CalibrationVerdict
from sdlc.core.models import (
    GateConfig,
    GateOutcome,
    GatePolicy,
    PipelineConfig,
)
from sdlc.validators import Verdict

VACUOUS = Verdict.vacuous()


def _cfg(policy: GatePolicy, threshold: float = 0.8) -> PipelineConfig:
    return PipelineConfig(gates={"architecture": GateConfig(policy=policy, threshold=threshold)})


# C7: the rule now takes a calibration verdict, with no default; ADR-24 adds
# the deterministic verdict the same way. These tests predate both and assert
# the confidence-vs-threshold half of the rule, so they supply a calibrated
# bucket and a vacuous verdict and keep asserting exactly what they always
# did. The new conjuncts have their own truth tables in
# tests/calibration/test_calibration_decision.py.
CALIBRATED = CalibrationVerdict(verdict="calibrated", n=25, agreement_rate=0.9)


def test_soft_high_confidence_auto_approves():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED, VACUOUS)
    assert decision is not None
    assert decision.outcome is GateOutcome.APPROVE
    assert decision.decided_by == "policy"


def test_soft_confidence_at_threshold_auto_approves():
    decision = auto_decision_for(
        "architecture", _cfg(GatePolicy.SOFT, 0.8), 0.8, CALIBRATED, VACUOUS
    )
    assert decision is not None


def test_soft_low_confidence_falls_through():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.5, CALIBRATED, VACUOUS)
    assert decision is None


def test_soft_none_confidence_falls_through():
    """Missing/legacy confidence must never auto-approve."""
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), None, CALIBRATED, VACUOUS)
    assert decision is None


def test_hard_policy_ignores_confidence():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.HARD), 0.99, CALIBRATED, VACUOUS)
    assert decision is None


def test_off_policy_ignores_confidence():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.OFF), 0.0, CALIBRATED, VACUOUS)
    assert decision is None


def test_unconfigured_gate_defaults_to_hard_and_falls_through():
    decision = auto_decision_for("deploy", PipelineConfig(gates={}), 0.99, CALIBRATED, VACUOUS)
    assert decision is None


import pathlib

# _revisable_stage lives on RoleHost (spec A Task 7); the merge soft path
# lives in src/sdlc/stages/merge/step.py (Task 20.7).
SRC = pathlib.Path("src/sdlc/workflows/role_host.py")
MERGE_SRC = pathlib.Path("src/sdlc/stages/merge/step.py")


def test_revisable_stage_passes_auto_decision():
    """C7 moved the rule to sdlc/calibration/decision.py and dropped the
    leading underscore (it is a shared module API now, not a file-private
    helper). What this pins is unchanged: _revisable_stage must COMPUTE the
    auto-decision and PASS it to _gate, not just call the rule."""
    src = SRC.read_text(encoding="utf-8")
    assert "auto_decision_for(" in src, (
        "_revisable_stage must call auto_decision_for to compute an "
        "auto_decision from the artifact's confidence (FR-301)"
    )
    assert "auto_decision=auto" in src, (
        "_revisable_stage must pass auto_decision=auto into self._gate()"
    )


def test_merge_soft_path_uses_auto_decision_for():
    """C7: same needle without the underscore, and a wider window -- the soft
    path now fetches a calibration verdict between the MergeVerdict call and
    the decision (ADR-24 then added the clean-verdict handoff on top), so the
    two are further apart than 1400 characters."""
    src = MERGE_SRC.read_text(encoding="utf-8")
    idx = src.rfind('"merge_verdict"')
    assert idx != -1, "merge stage no longer calls merge_verdict"
    tail = src[idx : idx + 1800]
    assert "auto_decision_for(" in tail, (
        "merge gate's soft path must route through auto_decision_for so "
        "verdict.confidence is checked against cfg.gates['merge'].threshold "
        "and against the bucket's calibration, not just verdict.approve"
    )


# ---------------------------------------------------------------------------
# ADR-24: the deterministic conjunct at the legacy call site. No graph node
# calls _revisable_stage (kept per 020 FR-006), but it must behave exactly
# like the gate node: provider verdict by gate name, blocked conjunct -> no
# auto_decision reaches the gate.
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

from sdlc.calibration.models import CalibrationVerdict as _CalibrationVerdict  # noqa: E402
from sdlc.core.models import GateDecision as _GateDecision  # noqa: E402
from sdlc.core.models import GateOutcome as _GateOutcome
from sdlc.stages.plan.models import DevTask as _DevTask  # noqa: E402
from sdlc.stages.plan.models import ImplementationPlan as _Plan
from sdlc.workflows.role_host import RoleHost as _RoleHost  # noqa: E402

_CALIBRATED = _CalibrationVerdict(verdict="calibrated", n=25, agreement_rate=0.9)


def _plan(*task_ids: str, confidence: float = 0.95) -> _Plan:
    return _Plan(
        tasks=[
            _DevTask(
                id=t,
                title="t",
                description="d",
                acceptance_criteria=[],
                files_hint=[],
                covers=[],
            )
            for t in task_ids
        ],
        confidence=confidence,
    )


class _RecordingHost:
    """Duck-typed host: _revisable_stage touches only _calibration_verdict
    and _gate, so a plain object stands in for the RoleHost mixin."""

    def __init__(self, outcome: _GateOutcome):
        self.gate_kwargs: list[dict] = []
        self._outcome = outcome

    async def _calibration_verdict(self, cfg, gate, author_model):
        return _CALIBRATED

    async def _gate(self, name, settings, **kw):
        self.gate_kwargs.append(kw)
        return _GateDecision(
            gate=name, round=kw["round"], outcome=self._outcome, decided_by="human"
        )


def _run_revisable(host, artifact):
    async def run_fn(guidance):
        return artifact

    # plan is SOFT at threshold 0.8 in the default PipelineConfig; the plan's
    # confidence (0.95) and the calibrated bucket clear the other conjuncts,
    # so the verdict is the only thing that can block.
    return asyncio.run(
        _RoleHost._revisable_stage(host, "plan", PipelineConfig(), run_fn, author_model="m")
    )


def test_revisable_stage_blocks_the_auto_decision_on_a_failed_verdict():
    host = _RecordingHost(_GateOutcome.APPROVE)
    _run_revisable(host, _plan("t1", "t2", "t1"))  # duplicate ids -> ok=False
    assert host.gate_kwargs[0]["auto_decision"] is None


def test_revisable_stage_auto_approves_when_the_provider_passes():
    host = _RecordingHost(_GateOutcome.APPROVE)
    _run_revisable(host, _plan("t1", "t2"))
    auto = host.gate_kwargs[0]["auto_decision"]
    assert auto is not None and auto.outcome is _GateOutcome.APPROVE
    assert auto.decided_by == "policy"


# ---------------------------------------------------------------------------
# 020 T006 (SG-4) on the live path: gate_node reads the ledger ONLY under the
# verbatim SOFT + confidence predicate. HARD, OFF and None-confidence rounds
# must never reach the calibration read.
# ---------------------------------------------------------------------------

import pathlib  # noqa: E402

GATE_NODE = pathlib.Path("src/sdlc/workflows/graph_nodes/gate.py")
PREDICATE = (
    "if confidence is not None and cfg.gates.get(name, GateConfig()).policy is GatePolicy.SOFT:"
)
CONSULT = "calibration = await nc.host._calibration_verdict(cfg, name, author)"


def _gate_node_body() -> str:
    src = GATE_NODE.read_text(encoding="utf-8")
    idx = src.find("async def gate_node(")
    assert idx != -1
    return src[idx:]


def test_gate_node_reads_calibration_only_under_the_verbatim_soft_predicate():
    body = _gate_node_body()
    assert PREDICATE in body
    assert CONSULT in body
    assert body.index(PREDICATE) < body.index(CONSULT)


def test_the_consult_sits_inside_the_predicate_block_not_after_it():
    """Indentation pins the nesting: the consult is inside the `if` (12 spaces),
    so a HARD or None-confidence round skips the read entirely."""
    lines = _gate_node_body().splitlines()
    consult_line = next(line for line in lines if CONSULT in line)
    predicate_line = next(line for line in lines if PREDICATE in line)
    indent = lambda s: len(s) - len(s.lstrip())  # noqa: E731
    assert indent(consult_line) == indent(predicate_line) + 4


def test_the_final_round_reads_no_calibration_and_passes_no_confidence():
    """The docstring's 'final round reads nothing': the else branch carries no
    auto decision, no calibration and no confidence."""
    body = _gate_node_body()
    final = body[body.index("    else:\n        decision = await nc.ctx.gate(") :]
    final = final[: final.index(")\n") + 2]
    assert "auto" not in final
    assert "calibration" not in final
    assert "confidence" not in final


def test_the_calibration_read_is_the_only_one_on_the_live_path():
    assert _gate_node_body().count("_calibration_verdict(") == 1
