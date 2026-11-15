"""US1 contract: the ``may_execute`` guard matrix (023b T015, RED).

Subject: ``sdlc.maintenance.execution.may_execute(incident, plan, decision, cfg)
-> Refusal | None`` (NEW pure module; R6, B-FR-002, B-FR-017, SC-B02/SC-B03).

``may_execute`` is the only gate between an approved incident and a child start.
The fix class is read from ``incident.finding.fix_class``: the plan records no
fix class of its own. Every test imports ``may_execute`` and ``Refusal`` inside
the test body, so before T016 each case fails per test with
ModuleNotFoundError instead of breaking collection.

The ``Refusal`` shape is pinned here as a small model with an ``outcome`` text.
The ops-only human refusal's outcome is pinned VERBATIM.

No I/O anywhere in the guard: purity is pinned by calling it twice on equal
inputs and comparing results.
"""

from __future__ import annotations

import pytest

from sdlc.core.models import GateDecision, GateOutcome
from sdlc.maintenance.models import Incident, MaintenanceConfig, RepairAction, RepairPlan
from sdlc.triage.models import FixClass, TriageFinding

OPS_REFUSAL_OUTCOME = "not executed — ops proposal only"


# --------------------------------------------------------------------------- builders


def _cfg(threshold: float = 0.8) -> MaintenanceConfig:
    return MaintenanceConfig(
        project="demo",
        repo_dir="/srv/repos/demo",
        build_probe=False,
        threshold=threshold,
    )


def _finding(fix_class: FixClass) -> TriageFinding:
    return TriageFinding(
        signal="secrets",
        rule="env_file_tracked",
        severity="high",
        detail=".env is tracked; add it to .gitignore and remove it from the index.",
        path=".gitignore",
        fix_class=fix_class,
    )


def _incident(
    fix_class: FixClass = FixClass.MECHANICAL,
    *,
    consecutive_seen: int = 2,
    reopens: int = 0,
) -> Incident:
    return Incident(
        no=1,
        key="secrets:env_file_tracked:.gitignore",
        kind="finding",
        finding=_finding(fix_class),
        commit_sha="a" * 40,
        first_seen_cycle=1,
        last_seen_cycle=2,
        consecutive_seen=consecutive_seen,
        reopens=reopens,
    )


def _code(i: int = 0) -> RepairAction:
    return RepairAction(kind="code_fix", summary=f"fix {i}", target_paths=[".gitignore"])


def _ops() -> RepairAction:
    return RepairAction(kind="ops", summary="restart the worker", ops_action="restart")


def _plan(actions: list[RepairAction], *, floor: float, self_confidence: float = 0.9) -> RepairPlan:
    # RepairPlan requires effective == min(self_confidence, floor) (023a FR-010).
    return RepairPlan(
        analysis="The .env file is tracked and holds a live token.",
        actions=actions,
        self_confidence=self_confidence,
        floor=floor,
        effective=min(self_confidence, floor),
        author_model="claude-sonnet-5-5",
    )


def _decision(decided_by: str) -> GateDecision:
    return GateDecision(
        gate="merge",
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by=decided_by,
    )


# --------------------------------------------------------------- policy: REFUSED (1-7)


def test_policy_refuses_a_judgement_fix_class_even_above_threshold():
    """(1) A judgement finding is human-gated by construction, even when the
    plan's numbers would clear the threshold on their own."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.JUDGEMENT),
        _plan([_code()], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_refuses_a_structural_fix_class_even_above_threshold():
    """(2) A structural finding is refused for policy approval."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.STRUCTURAL),
        _plan([_code()], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_refuses_a_mixed_plan_of_ops_and_code_fix():
    """(3) One ops action in the plan makes it mixed, and mixed is never policy-approved."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL),
        _plan([_code(), _ops()], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_refuses_an_ops_only_plan():
    """(4) An ops-only plan is never executable. B-FR-017: ops are proposal only."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL),
        _plan([_ops()], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_refuses_when_seen_only_once():
    """(5) A mechanical all-code_fix plan still needs a second consecutive detect."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, consecutive_seen=1),
        _plan([_code()], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_refuses_after_a_reopen():
    """(6) A reopened incident (reopens == 1) goes back to a human."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, reopens=1),
        _plan([_code()], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_refuses_effective_exactly_at_threshold():
    """(7) The threshold comparison is strict: effective == threshold is refused."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL),
        _plan([_code()], floor=0.8, self_confidence=0.9),  # effective 0.8 == threshold 0.8
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


# ------------------------------------------------- policy: REFUSED AT threshold 0.55 (8-9)


def test_policy_refuses_a_reproduced_judgement_plan_at_low_threshold():
    """(8) At threshold 0.55 a reproduced judgement plan (floor 0.60) clears the
    threshold on its own, so only the fix-class gate can refuse it."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.JUDGEMENT, consecutive_seen=2),
        _plan([_code()], floor=0.6, self_confidence=0.9),  # effective 0.6 > 0.55
        _decision("policy"),
        _cfg(threshold=0.55),
    )
    assert refusal is not None


def test_policy_refuses_an_unreproduced_mechanical_plan_at_low_threshold():
    """(9) Mechanical, unreproduced (consecutive_seen 1, floor 0.80): effective
    0.8 > 0.55 clears the threshold, so only the reproduction gate refuses it."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, consecutive_seen=1),
        _plan([_code()], floor=0.8, self_confidence=0.9),  # effective 0.8 > 0.55
        _decision("policy"),
        _cfg(threshold=0.55),
    )
    assert refusal is not None


# ------------------------------------------------------------- policy: ACCEPTED


def test_policy_accepts_a_reproduced_mechanical_code_fix_plan_above_threshold():
    """Accepted: mechanical, every action code_fix, consecutive_seen >= 2,
    reopens == 0, effective > threshold."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, consecutive_seen=2, reopens=0),
        _plan([_code()], floor=0.6, self_confidence=0.9),  # effective 0.6 > 0.55
        _decision("policy"),
        _cfg(threshold=0.55),
    )
    assert refusal is None


# ------------------------------------------------------------------ human path


@pytest.mark.parametrize(
    ("fix_class", "actions"),
    [
        (FixClass.MECHANICAL, [_code()]),
        (FixClass.JUDGEMENT, [_code()]),
        (FixClass.MECHANICAL, [_code(), _ops()]),
    ],
    ids=["mechanical-code", "judgement-code", "mixed"],
)
def test_human_accepts_any_plan_with_at_least_one_code_fix(fix_class, actions):
    """A human approval executes any plan that carries at least one code_fix."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(fix_class, consecutive_seen=1),
        _plan(actions, floor=0.6),
        _decision("human"),
        _cfg(threshold=0.8),
    )
    assert refusal is None


def test_human_refuses_an_ops_only_plan_with_the_verbatim_outcome():
    """B-FR-017 / SC-B03: an ops-only plan is refused even for a human, and the
    outcome text is pinned verbatim."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL),
        _plan([_ops()], floor=0.9),
        _decision("human"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None
    assert refusal.outcome == OPS_REFUSAL_OUTCOME


@pytest.mark.parametrize(
    "actions",
    [[_code()], [_ops()], [_code(), _ops()]],
    ids=["code-only", "ops-only", "mixed"],
)
def test_timeout_is_never_executable_whatever_the_plan(actions):
    """A timeout decision never executes anything: it returns a refusal, never None."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, consecutive_seen=2),
        _plan(actions, floor=0.9),
        _decision("timeout"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


# ---------------------------------------------------------------------- purity


def test_may_execute_is_pure_equal_inputs_equal_results():
    """Purity: the guard has no I/O, so the same inputs give the same result."""
    from sdlc.maintenance.execution import may_execute

    args = (
        _incident(FixClass.MECHANICAL, consecutive_seen=1),
        _plan([_code()], floor=0.8),
        _decision("policy"),
        _cfg(threshold=0.55),
    )
    first = may_execute(*args)
    second = may_execute(*args)
    assert first == second


# ------------------------------------------------------ EDGE (023b T015, RED) -- qa-chaos


def test_policy_refuses_an_empty_plan_even_when_every_other_gate_passes():
    """Edge: an empty plan executes nothing, so a policy approval is refused even
    for a mechanical, reproduced, high-confidence incident."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, consecutive_seen=2, reopens=0),
        _plan([], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_refuses_at_the_reopen_bound():
    """Edge: at reopens == max_reopens (2) a policy approval is refused, not
    only after the first reopen."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, consecutive_seen=2, reopens=2),
        _plan([_code()], floor=0.9),
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is not None


def test_policy_accepts_effective_just_above_threshold():
    """Edge, the strict-inequality boundary from above: effective == threshold
    + 0.001 is accepted, where effective == threshold is refused (case 7)."""
    from sdlc.maintenance.execution import may_execute

    refusal = may_execute(
        _incident(FixClass.MECHANICAL, consecutive_seen=2, reopens=0),
        _plan([_code()], floor=0.801, self_confidence=0.9),  # effective 0.801 > 0.8
        _decision("policy"),
        _cfg(threshold=0.8),
    )
    assert refusal is None
