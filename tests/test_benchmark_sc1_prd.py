"""026 T009 (FR-006, research R3, amendment A-2): the PRD-aligned SC-1.

PRD §8: reach the merge gate "without human intervention beyond configured
gates (no unplanned escalations)".

    STAGE_GATES = {research, clarify, architecture, plan, merge, deploy}
    unplanned(g) := g.decided_by != "policy"
                    and (g.gate not in STAGE_GATES or g.policy == "soft")
    steered(g)   := g.gate in STAGE_GATES and g.decided_by != "policy"
                    and g.outcome is not approve
    hit          := reached merge (REACHED_PREFIXES; rejected:merge counts)
                    and no unplanned / steered gate before the first `merge`

`SC-1-strict` keeps the 025 rule (any human-decided gate before merge).
Companion file to test_benchmark_sc_rollup.py (near the size ceiling).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from sdlc.benchmarks.sc_rollup import (
    MIN_RUNS,
    build_sc_rollup,
    render_sc_rollup_html,
    render_sc_rollup_json,
    render_sc_rollup_markdown,
)
from sdlc.core.models import (
    ClarificationOutcome,
    GateOutcome,
    GateOutcomeSummary,
    RunSummary,
)

T = datetime(2026, 11, 18, 10, tzinfo=UTC)
STAGE_GATE_NAMES = ("research", "clarify", "architecture", "plan", "merge", "deploy")
APPROVE, REVISE = GateOutcome.APPROVE, GateOutcome.REVISE


def _gate(name, decided_by="human", policy="hard", outcome=APPROVE, rnd=1):
    return GateOutcomeSummary(
        gate=name,
        round=rnd,
        policy=policy,
        decided_by=decided_by,
        approved=outcome is APPROVE,
        outcome=outcome,
    )


def _run(run_id, gates=(), outcome="deployed:pr", clars=(), offset=0):
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome=outcome,
        terminal_stage="deploy",
        started_at=T + timedelta(hours=offset),
        ended_at=T + timedelta(hours=offset),
        duration_s=0.0,
        gates=list(gates),
        clarifications=list(clars),
    )


def _fleet(gates=(), **kw):
    """MIN_RUNS identical runs, so the rate is not floored to n/a."""
    return [_run(f"run-{i}", gates, offset=i, **kw) for i in range(MIN_RUNS)]


def _rate(rollup, criterion):
    return next(r for r in rollup.rates if r.criterion == criterion)


def _sc1(summaries, criterion="SC-1"):
    return _rate(build_sc_rollup(summaries, []), criterion)


# Attendant-serviced HARD stage gates: configured, planned, approved.
HARD_STAGE_APPROVED = (_gate("architecture"), _gate("plan"))


# --- the headline rule: one case per row of A-2 --------------------------

CASES = [
    pytest.param(HARD_STAGE_APPROVED, 1.0, id="hard_stage_gates_human_approved_hit"),
    pytest.param(
        (*HARD_STAGE_APPROVED, _gate("task:T-1", policy="soft")), 0.0, id="task_gate_human_miss"
    ),
    pytest.param(
        (_gate("task:T-1", decided_by="timeout", policy="soft"),),
        0.0,
        id="task_gate_timeout_miss",
    ),
    pytest.param((_gate("foo"),), 0.0, id="unknown_gate_human_miss_fail_closed"),
    pytest.param((_gate("tool_approval"),), 0.0, id="tool_approval_human_miss"),
    pytest.param((_gate("budget"),), 0.0, id="budget_human_miss"),
    pytest.param((_gate("architecture", policy="soft"),), 0.0, id="soft_stage_gate_human_miss"),
    pytest.param((_gate("plan", outcome=REVISE),), 0.0, id="hard_plan_revise_steering_miss"),
    pytest.param(
        (_gate("plan", outcome=GateOutcome.REJECT), _gate("plan", rnd=2)),
        0.0,
        id="hard_plan_reject_steering_miss",
    ),
    pytest.param(
        (
            _gate("task:T-1", decided_by="policy", policy="soft"),
            _gate("architecture", decided_by="policy", policy="soft", outcome=REVISE),
        ),
        1.0,
        id="policy_decided_gates_ignored_hit",
    ),
    pytest.param(
        (_gate("task:T-1", decided_by="some-reviewer", policy="soft"),),
        0.0,
        id="reviewer_named_decider_counts_as_human_miss",
    ),
    pytest.param(
        (
            *HARD_STAGE_APPROVED,
            _gate("merge", decided_by="some-reviewer", policy="soft", outcome=REVISE),
            _gate("merge", rnd=2),
        ),
        1.0,
        id="reviewer_override_at_merge_itself_hit",
    ),
    pytest.param(
        (*HARD_STAGE_APPROVED, _gate("merge"), _gate("task:T-9", policy="soft")),
        1.0,
        id="unplanned_gate_after_first_merge_entry_ignored_hit",
    ),
]


@pytest.mark.parametrize(("gates", "want"), CASES)
def test_sc1_prd_rule(gates, want):
    sc1 = _sc1(_fleet(gates))
    assert sc1.n == MIN_RUNS
    assert sc1.rate == want


def test_sc1_prd_rejected_at_merge_counts_as_reached():
    assert _sc1(_fleet(HARD_STAGE_APPROVED, outcome="rejected:merge")).rate == 1.0


def test_sc1_prd_not_reaching_merge_is_a_miss_even_with_planned_gates_only():
    assert _sc1(_fleet(HARD_STAGE_APPROVED, outcome="rejected:plan")).rate == 0.0


@pytest.mark.parametrize("answered_by", ["human", "suggested", "unanswered"])
@pytest.mark.parametrize(
    ("gates", "want"),
    [pytest.param((), 1.0, id="no_gates"), pytest.param(HARD_STAGE_APPROVED, 1.0, id="hard")],
)
def test_sc1_prd_clarifications_never_affect_sc1(gates, want, answered_by):
    clar = ClarificationOutcome(question_id="q1", question="q?", answered_by=answered_by)
    assert _sc1(_fleet(gates, clars=[clar])).rate == want


# --- SC-1-strict: the 025 rule, rendered beside the headline -------------


def test_sc1_strict_row_present_beside_sc1():
    rollup = build_sc_rollup(_fleet(HARD_STAGE_APPROVED), [])
    criteria = [r.criterion for r in rollup.rates]
    assert "SC-1-strict" in criteria
    assert criteria.index("SC-1-strict") == criteria.index("SC-1") + 1


def test_sc1_strict_misses_hard_human_stage_gates_the_headline_hits():
    rollup = build_sc_rollup(_fleet(HARD_STAGE_APPROVED), [])
    assert _rate(rollup, "SC-1").rate == 1.0
    strict = _rate(rollup, "SC-1-strict")
    assert (strict.rate, strict.n) == (0.0, MIN_RUNS)


def test_sc1_strict_keeps_the_025_rule_human_at_merge_itself_still_counts():
    gates = (_gate("architecture", decided_by="policy", policy="soft"), _gate("merge"))
    assert _sc1(_fleet(gates), "SC-1-strict").rate == 1.0


def test_sc1_strict_renders_in_every_format():
    rollup = build_sc_rollup(_fleet(HARD_STAGE_APPROVED), [])
    assert "| SC-1-strict |" in render_sc_rollup_markdown(rollup)
    assert "SC-1-strict" in render_sc_rollup_html(rollup)
    crits = [r["criterion"] for r in json.loads(render_sc_rollup_json(rollup))["rates"]]
    assert "SC-1-strict" in crits


# --- the exact 95% interval ----------------------------------------------


def _four_of_five():
    """4 hits, 1 miss (an unplanned task escalation); 10 planned gates."""
    runs = [_run(f"run-{i}", HARD_STAGE_APPROVED, offset=i) for i in range(4)]
    runs.append(_run("run-4", (*HARD_STAGE_APPROVED, _gate("task:T-1", policy="soft")), offset=4))
    return build_sc_rollup(runs, [])


def test_sc1_ci95_clopper_pearson_for_four_of_five():
    rollup = _four_of_five()
    assert _rate(rollup, "SC-1").rate == 0.8
    md = render_sc_rollup_markdown(rollup)
    row = next(line for line in md.splitlines() if line.startswith("| SC-1 |"))
    assert "0.80" in row
    assert "CI95 [0.28, 0.99]" in row
    assert "CI95 [0.28, 0.99]" in render_sc_rollup_html(rollup)
    assert "CI95 [0.28, 0.99]" in render_sc_rollup_json(rollup)


def test_sc1_ci95_reaches_one_on_all_hits():
    md = render_sc_rollup_markdown(build_sc_rollup(_fleet(HARD_STAGE_APPROVED), []))
    row = next(line for line in md.splitlines() if line.startswith("| SC-1 |"))
    assert "CI95 [0.48, 1.00]" in row


def test_sc1_ci95_reaches_zero_on_all_misses():
    md = render_sc_rollup_markdown(build_sc_rollup(_fleet((_gate("foo"),)), []))
    row = next(line for line in md.splitlines() if line.startswith("| SC-1 |"))
    assert "CI95 [0.00, 0.52]" in row


# --- the note --------------------------------------------------------------


def test_sc1_note_names_stage_gates_steering_and_planned_gate_count():
    note = _rate(_four_of_five(), "SC-1").note
    for name in STAGE_GATE_NAMES:
        assert name in note, name
    assert "steering" in note.lower()
    assert re.search(r"\b10 planned gates?\b", note), note
    assert "rejected:merge" in note  # reached still says what counts


# --- chaos / edge cases (026 T009, chaos QA) --------------------------------
#
# Clopper-Pearson extremes: verified by exact binomial bisection (no scipy)
# on 2026-11-18. 0/5 -> [0.0000, 0.5218], 4/5 -> [0.2836, 0.9949],
# 5/5 -> [0.4782, 1.0000]. The three CI95 tests above already pin these at 2
# decimals (0/5's upper bound is 0.52, not 0.48; 0.48 is 5/5's lower
# bound), so no duplicate pins are added here.


def test_sc1_edge_stage_gates_constant_is_exactly_the_allowlist():
    from sdlc.benchmarks.sc_rollup import STAGE_GATES

    assert set(STAGE_GATES) == set(STAGE_GATE_NAMES)
    assert len(STAGE_GATES) == len(STAGE_GATE_NAMES)  # no duplicates hiding in a list


def test_sc1_edge_soft_stage_gate_revise_is_one_disqualification_not_two():
    """A SOFT `architecture` gate a person REVISEd is unplanned (SOFT clause)
    AND steering. It is one miss for one run: n and the rate move by one."""
    runs = [_run(f"run-{i}", HARD_STAGE_APPROVED, offset=i) for i in range(4)]
    runs.append(_run("run-4", (_gate("architecture", policy="soft", outcome=REVISE),), offset=4))
    sc1 = _sc1(runs)
    assert (sc1.n, sc1.rate) == (MIN_RUNS, 0.8)


@pytest.mark.parametrize(
    ("gates", "want"),
    [
        pytest.param(
            (*HARD_STAGE_APPROVED, _gate("merge"), _gate("deploy", outcome=REVISE)),
            1.0,
            id="steering_after_first_merge_ignored_hit",
        ),
        pytest.param(
            (*HARD_STAGE_APPROVED, _gate("task:T-1", policy="soft")),
            0.0,
            id="no_merge_entry_every_gate_is_pre_merge_miss",
        ),
        pytest.param(
            (_gate("task:T-1", policy="soft"), _gate("merge"), _gate("task:T-2", policy="soft")),
            0.0,
            id="unplanned_before_merge_still_counts_when_another_follows_miss",
        ),
    ],
)
def test_sc1_edge_before_the_first_merge_entry(gates, want):
    """Only gates BEFORE the first `merge` entry count. A HARD clean merge
    opens no merge gate at all (A-3), so a run with no merge entry has every
    gate pre-merge."""
    assert _sc1(_fleet(gates)).rate == want


def test_sc1_edge_human_reject_at_merge_then_policy_approve_is_a_hit():
    """Merge round 1 human REJECT, round 2 policy approve, run ends
    rejected:merge. The rejection is AT merge, not before it: not steering."""
    gates = (
        *HARD_STAGE_APPROVED,
        _gate("merge", outcome=GateOutcome.REJECT),
        _gate("merge", decided_by="policy", rnd=2),
    )
    assert _sc1(_fleet(gates, outcome="rejected:merge")).rate == 1.0


def test_sc1_edge_timeout_reject_on_a_stage_gate_before_merge_is_a_miss():
    """`timeout` is a non-policy decider; a REJECT on a planned `plan` gate
    is therefore steering (A-3 also classes it infra in the fleet report)."""
    gates = (
        _gate("plan", decided_by="timeout", outcome=GateOutcome.REJECT),
        _gate("plan", rnd=2),
    )
    assert _sc1(_fleet(gates)).rate == 0.0


def test_sc1_edge_soft_policy_decided_gates_are_planned_hit():
    """The SOFT clause needs a non-policy decider: a SOFT stage gate the
    calibration ledger auto-approved is not an escalation."""
    gates = (
        _gate("architecture", decided_by="policy", policy="soft"),
        _gate("plan", decided_by="policy", policy="soft"),
    )
    rollup = build_sc_rollup(_fleet(gates), [])
    assert _rate(rollup, "SC-1").rate == 1.0
    assert _rate(rollup, "SC-1-strict").rate == 1.0
