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


# =========================================================================== #
# T024 (023b, RED): the merge decision and the verification verdict.
#
# Subjects: ``merge_reject_decision`` and ``classify_verification`` in
# ``sdlc.maintenance.execution`` (R4, R5, SC-B10). Both are deferred-imported
# inside each test body, so each case is RED on its own ImportError.
# =========================================================================== #


def _triage_pair(*, base=None, verify=None, base_nc=(), verify_nc=()):
    """Base and verify triages over one seeded identity (the .gitignore finding)."""
    from tests.maintenance.conftest import env_file_findings, make_triage

    f = env_file_findings()[1]
    base_t = make_triage(
        {"secrets": [f]} if base else None,
        not_collected=base_nc,
        commit_sha="a" * 40,
    )
    verify_t = make_triage(
        {"secrets": [f]} if verify else None,
        not_collected=verify_nc,
        commit_sha="b" * 40,
    )
    identity = f"{f.signal}:{f.rule}:{f.path}:{f.key}"
    return base_t, verify_t, identity


# ------------------------------------------------------- subject 1: merge_reject_decision


def test_merge_reject_decision_builds_a_reject_on_the_merge_gate():
    from sdlc.maintenance.execution import merge_reject_decision

    decision = merge_reject_decision(3, "persisted: the identity is still present")
    assert isinstance(decision, GateDecision)
    assert decision.gate == "merge"
    assert decision.round == 3
    assert decision.outcome is GateOutcome.REJECT
    assert decision.decided_by == "policy"


def test_merge_reject_decision_carries_the_verdict_verbatim_in_comments():
    from sdlc.maintenance.execution import merge_reject_decision

    verdict = "conflicted: fix branch failed to merge — see verify log"
    decision = merge_reject_decision(1, verdict)
    assert decision.comments == verdict


def test_merge_reject_decision_is_reject_for_every_verdict_it_is_given():
    from sdlc.maintenance.execution import merge_reject_decision

    for verdict in ("persisted", "new", "conflicted", "unverifiable"):
        assert merge_reject_decision(1, verdict).outcome is GateOutcome.REJECT


# -------------------------------------------------------- subject 2: classify_verification


def test_classify_identity_present_in_base_and_gone_in_verify_is_resolved():
    from sdlc.maintenance.execution import classify_verification

    base, verify, identity = _triage_pair(base=True, verify=False)
    assert classify_verification(base, verify, identity, False) == "resolved"


def test_classify_identity_present_in_both_is_persisted():
    from sdlc.maintenance.execution import classify_verification

    base, verify, identity = _triage_pair(base=True, verify=True)
    assert classify_verification(base, verify, identity, False) == "persisted"


def test_classify_identity_absent_in_base_and_present_in_verify_is_new():
    from sdlc.maintenance.execution import classify_verification

    base, verify, identity = _triage_pair(base=False, verify=True)
    assert classify_verification(base, verify, identity, False) == "new"


def test_classify_identity_whose_signal_is_not_collected_on_verify_is_unverifiable():
    """R4: UNVERIFIABLE stays verifying. An absence caused by a not-collected
    signal is not evidence that the fix worked."""
    from sdlc.maintenance.execution import classify_verification

    base, verify, identity = _triage_pair(base=True, verify=False, verify_nc=("secrets",))
    assert classify_verification(base, verify, identity, False) == "unverifiable"


def test_classify_identity_whose_signal_is_not_collected_on_base_is_unverifiable():
    """Pins compute_delta's behaviour for a base-side gap: UNVERIFIABLE, so the
    verdict cannot claim the identity is new or resolved."""
    from sdlc.maintenance.execution import classify_verification

    base, verify, identity = _triage_pair(base=False, verify=True, base_nc=("secrets",))
    assert classify_verification(base, verify, identity, False) == "unverifiable"


@pytest.mark.parametrize(
    ("base_present", "verify_present"),
    [(True, False), (True, True), (False, True)],
    ids=["resolved-shape", "persisted-shape", "new-shape"],
)
def test_conflicted_overrides_every_delta_to_conflicted(base_present, verify_present):
    """R4/R5: a fix branch that failed to merge is dirty whatever the triage says."""
    from sdlc.maintenance.execution import classify_verification

    base, verify, identity = _triage_pair(base=base_present, verify=verify_present)
    assert classify_verification(base, verify, identity, True) == "conflicted"


def test_identity_absent_from_both_triages_is_absent_at_base():
    """Owner ruling (T025, in lieu of an explicit R4/R5 trigger): collected
    on both sides but present in NEITHER triage means compute_delta has no
    opinion — the fault the incident recorded does not exist at the
    verification base, so nothing was verified. data-model §transitions
    pins the consequence (verifying -> resolved_externally: stale, not
    proven fixed); this pin fixes the trigger T026 builds on."""
    from sdlc.maintenance.execution import classify_verification

    base, verify, identity = _triage_pair(base=False, verify=False)
    assert classify_verification(base, verify, identity, False) == "absent_at_base"


# ------------------------------------------------- subject 3: SC-B10 outcome scan


def _gatedecision_builders() -> dict[str, object]:
    """Every public function in execution.py whose return annotation names
    GateDecision. Discovered from annotations, so a new builder is found
    automatically; nothing is hand-listed here."""
    import inspect
    import typing

    from sdlc.maintenance import execution

    found = {}
    for name, fn in inspect.getmembers(execution, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != execution.__name__:
            continue
        hint = typing.get_type_hints(fn).get("return")
        if hint is not None and "GateDecision" in repr(hint):
            found[name] = fn
    return found


#: Sample arguments for each discovered builder. A new builder fails the set
#: check below until it is added here with a sample, so the scan cannot rot.
_SCAN_SAMPLES = {
    "merge_reject_decision": lambda m: m.merge_reject_decision(2, "persisted"),
}


def test_every_gatedecision_builder_is_discovered_and_sampled():
    """The discovered set equals the sampled set: a new builder cannot escape
    the outcome scan below without also being sampled here."""
    found = _gatedecision_builders()
    assert found, "execution.py must expose at least one GateDecision builder"
    assert set(found) == set(_SCAN_SAMPLES)


def test_no_gatedecision_builder_ever_builds_an_outcome_other_than_reject():
    """SC-B10: the loop only ever sends a child REJECT."""
    from sdlc.maintenance import execution

    found = _gatedecision_builders()
    assert found, "an empty scan would pass vacuously: at least one builder must exist"
    for name in found:
        decision = _SCAN_SAMPLES[name](execution)
        assert decision.outcome is GateOutcome.REJECT, f"{name} built {decision.outcome}"


# ------------------------------------------------------------ EDGE (023b T024) -- qa-chaos


def test_merge_reject_decision_pins_every_field_for_round_three_and_a_distinct_verdict():
    """Edge: full-shape pin. Round 3 and a distinct verdict must come through
    every field; the fields the builder leaves unset stay at their defaults."""
    from sdlc.maintenance.execution import merge_reject_decision

    verdict = "new: a second identity appeared on the verification branch"
    decision = merge_reject_decision(3, verdict)
    assert decision.model_dump(exclude={"decided_at"}) == {
        "gate": "merge",
        "round": 3,
        "outcome": GateOutcome.REJECT,
        "decided_by": "policy",
        "reviewer": None,
        "comments": verdict,
        "guidance": None,
        "thaw_tests": False,
    }


def test_classify_selects_the_given_identity_not_the_first_delta_row():
    """Edge: with two identities in the delta, the wrapper picks by identity. The
    given one persisted; the other was resolved. Order must not decide it."""
    from sdlc.maintenance.execution import classify_verification
    from tests.maintenance.conftest import env_file_findings, make_triage

    keep, gone = env_file_findings()[0], env_file_findings()[1]
    base_t = make_triage({"secrets": [keep, gone]}, commit_sha="a" * 40)
    verify_t = make_triage({"secrets": [keep]}, commit_sha="b" * 40)
    keep_id = f"{keep.signal}:{keep.rule}:{keep.path}:{keep.key}"
    gone_id = f"{gone.signal}:{gone.rule}:{gone.path}:{gone.key}"

    assert classify_verification(base_t, verify_t, keep_id, False) == "persisted"
    assert classify_verification(base_t, verify_t, gone_id, False) == "resolved"


def test_conflicted_overrides_a_not_collected_shape_to_conflicted():
    """Edge: precedence. A conflicted merge is 'conflicted' even when the verify
    side is not collected (which alone would read as unverifiable)."""
    from sdlc.maintenance.execution import classify_verification

    base_t, verify_t, identity = _triage_pair(base=True, verify=False, verify_nc=("secrets",))
    assert classify_verification(base_t, verify_t, identity, True) == "conflicted"
