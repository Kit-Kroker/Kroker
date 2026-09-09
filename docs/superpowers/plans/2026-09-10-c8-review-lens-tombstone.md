# C8 — Lens-Absence Tombstones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a review lens that did not run distinguishable from one that approved, by recording a typed `LensOutcome` tombstone for each gating lens, carrying it in `TaskResult`, and grading it at the merge gate as a required advisory check.

**Architecture:** A new pure module `src/sdlc/stages/review/lenses.py` owns four things: the `GATING_LENSES` manifest, the `LensPresence` enum, the `LensOutcome` model (whose validator makes an absent-and-approved outcome unconstructible), and three pure functions — `classify_lens` (the single producer) plus `primary_admits` / `backstop_admits` (exact transcriptions of the two shipped admission rules). `code/step.py` classifies both lenses once per attempt, reads the predicates instead of `None`, and carries the outcomes on both `TaskResult` return sites. `merge/step.py` grades them through one new ADVISORY check, `review_lenses_present`, registered in `MERGE_REQUIRED_CHECKS` so C3's fail-closed synthesis covers it.

**Tech Stack:** Python 3, Pydantic v2, pytest, pytest-asyncio. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-09-c8-review-lens-tombstone-design.md` — approved at the user gate 2026-09-10 with five rulings recorded in its §8. Read the spec alongside this plan; every task below cites the spec section it implements.

## Global Constraints

- **The task layer never blocks on absence** (ruling OQ1). No presence state may cause a task to fail, quarantine, or enter the fix loop. `REVIEW-1.3` and the `review/AGENTS.md` fail-open invariant are not amended by this work.
- **Admission semantics are preserved exactly** (spec §3.4). `primary_admits` fails on *any* PRESENT-and-rejecting primary — with or without blocking findings. `backstop_admits` fails only on a PRESENT-and-rejecting adversary *with* blocking findings. Do not harmonize them; that was considered and rejected into its own register row.
- **The merge check fails only on `UNDECLARED_ABSENT` or a missing outcome** (ruling OQ2). `PRESENT`, `DECLARED_ABSENT`, and `NOT_REACHED` all pass, and all four states appear in the check detail regardless.
- **One uniform check** named `review_lenses_present` covers both lenses (ruling OQ3). Do not split it per lens.
- **Classification is ADVISORY, never ABSOLUTE.** An absolute lens-presence check would delete the config flags by force.
- **`classify_lens` stays pure** — no `ctx`, no I/O, no inspection of control flow. `reached` is a caller-supplied boolean.
- **Do not touch `src/sdlc/benchmarks/`** (ruling OQ5). Benchmark lens records are a separate row, filed at `.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md`.
- **Do not touch `deep_review`'s pre-check** (`review/step.py:263-269`) or add it to `GATING_LENSES`. It is FILTERED and gates nothing.
- Broken source-assertion pins are **amended with a stated reason, never deleted**, and never "fixed" by reinstating code this design removes.
- No attribution trailers in any commit — no `Co-Authored-By:` in any form, no `Claude-Session:` link, regardless of what a skill or template prints. Commit via `git commit -F <msgfile>`, one path per `git add` argument, no heredocs (the host shell may be PowerShell 5.1).
- **Run every commit step under bash** (Git Bash), not PowerShell. The message-file form uses `printf`, which is not a PowerShell cmdlet — under PowerShell 5.1 the commit steps fail before committing. The ```bash fences say so; honour them. If you must commit from PowerShell, write the message file with `Set-Content -Encoding utf8` instead and keep the `git commit -F` form.

## Stop-Guards

These are binding. On fire: **stop, diagnose (reproduce, isolate causally), report.** Clearance comes only from the orchestrator — do not self-clear, do not work around.

- **SG-1 — A test outside this plan's named amendment list turns red.** The full list is spec §4.1's four pins — `test_review_wiring.py:51`, `:75`, `test_adversary_workflow.py:196`, `test_adversary_workflow.py:106-112` — **plus `test_adversary_workflow.py:161-172`** (`test_non_blocking_adversary_rejection_does_not_abandon_the_task`), which §4.1 missed and Task 3 Step 7 amends, **plus the merge fixtures** named in Task 6 Step 5. Any *other* failure is an unmodelled consequence. Stop.
- **SG-2 — A merge test goes green by relaxing the check instead of supplying outcomes.** The fixture blast radius (Task 6) is fixed by adding `lens_outcomes` to fixtures. If you find yourself widening the grading rule, loosening the manifest, or deleting an assertion to get green, stop.
- **SG-3 — The task layer's behaviour changes for any PRESENT lens.** Task 3 must be behaviour-preserving except for typed absence. If a test that exercises approval/rejection paths changes outcome, stop.
- **SG-4 — `pytest tests/ -q` was red before your task started.** Establish the baseline first (Task 0). Do not build on an unknown-state tree.

---

## File Map

**Create:**
- `src/sdlc/stages/review/lenses.py` — the whole pure layer: `GATING_LENSES`, `LensPresence`, `LensOutcome`, `classify_lens`, `primary_admits`, `backstop_admits`. Modelled on `src/sdlc/stages/code/freeze.py`, the shipped precedent for pure decision rules in their own module.
- `tests/review/test_lens_outcome.py` — truth tables for the classifier, the validator, and both admission predicates.
- `tests/test_task_result_lens_outcomes.py` — the `TaskResult` field test (mirrors `tests/test_task_result_plan_drift.py` from E4).
- `tests/code/test_lens_tombstones.py` — task-layer integration: presence states across both return sites, the `:802` regression, the A1 `NOT_REACHED` case.
- `tests/merge/test_lens_presence_gate.py` — the merge check, its grading rule, manifest membership, and the waiver round-trip.

**Modify:**
- `src/sdlc/stages/review/__init__.py` — export the new names (REVIEW-1.5's export list).
- `src/sdlc/workflows/models.py:52-63` — `TaskResult.lens_outcomes`.
- `src/sdlc/stages/code/step.py` — `:335` (delete the duplicate pre-check), `:798` (predicate), `:801-813` (classify, delete the compound guard, predicate), `:827` and `:899` (populate both returns).
- `src/sdlc/workflows/task_host.py:311-360` — delete the two dead twins.
- `src/sdlc/stages/merge/step.py` — add `_lens_presence_check`, rewrite `review_severity` at `:323-328`, wire both into the checks list at `:350`.
- `src/sdlc/gate.py:86-97` — add `"review_lenses_present": CheckClass.ADVISORY` to `MERGE_REQUIRED_CHECKS`.
- `src/sdlc/stages/review/review.md` — REVIEW-1.6, plus the Failure-modes correction at `:36`.
- `src/sdlc/stages/review/AGENTS.md` — extend the fail-open invariant line.
- `src/sdlc/stages/code/code.md` — CODE-1.6.
- `src/sdlc/stages/code/AGENTS.md` — the `lenses.py` locality note.
- `src/sdlc/stages/merge/merge.md` — MERGE-1.8, MERGE-1.3's enumeration at `:17`, failure-modes bullet.
- `tests/review/test_review_wiring.py:51`, `:75` — amended pins.
- `tests/review/test_adversary_workflow.py:106-112`, `:161-172`, `:185-198` — amended pins.
- `tests/conftest.py:273-275` — `required_checks` docstring count.
- `tests/merge/test_merge_slice_contract.py:112, :171, :247, :291`; `tests/merge/test_merge_gate_wiring.py:97-117`; `tests/merge/test_plan_drift_gate.py:24, :119` — fixture `lens_outcomes`.

**Sequencing rationale.** The pure module lands first so every later task consumes settled names. Task-layer wiring precedes the merge gate because the merge check can only grade evidence the task layer produces. The manifest entry and the live checks-list wiring land in **one** commit (Task 6): adding a name to `MERGE_REQUIRED_CHECKS` without a producer makes `_synthesized` fail it for every merge test in between, so splitting them would leave a deliberately red intermediate commit. Contract deltas land with the slice whose behaviour they describe, and only once the statement they make is true.

---

### Task 0: Establish the baseline

**Files:** none.

**Interfaces:**
- Consumes: nothing.
- Produces: a recorded green baseline, so SG-1 and SG-4 have something to compare against.

- [ ] **Step 1: Confirm the branch**

Run: `git branch --show-current`
Expected: `c8-review-lens-tombstone`. If not, stop — you are on the wrong branch.

- [ ] **Step 2: Run the full suite and record the result**

Run: `pytest tests/ -q`
Expected: green. Record the summary line (counts) in your task notes.

If it is red before you have changed anything, **SG-4 fires**: stop and report which tests fail. Do not start Task 1 on an unknown-state tree.

---

### Task 1: The pure lens module

**Implements:** spec §3.1, §3.2, §3.4 (the predicates).

**Files:**
- Create: `src/sdlc/stages/review/lenses.py`
- Modify: `src/sdlc/stages/review/__init__.py`
- Test: `tests/review/test_lens_outcome.py` (new)

**Interfaces:**
- Consumes: `ReviewReport` from `src/sdlc/stages/review/models.py` (existing — has `approve: bool` and `blocking_findings: list[ReviewFinding]`).
- Produces, for every later task:
  - `GATING_LENSES: Final[frozenset[str]]` — `{"reviewer", "adversary"}`
  - `LensPresence` — `StrEnum` with `PRESENT`, `DECLARED_ABSENT`, `NOT_REACHED`, `UNDECLARED_ABSENT`
  - `LensOutcome` — Pydantic model, fields `lens: str`, `presence: LensPresence`, `approved: bool | None = None`, `has_blocking_findings: bool = False`, `reason: str = ""`
  - `classify_lens(lens: str, *, enabled: bool, agent_present: bool, reached: bool, report: ReviewReport | None) -> LensOutcome`
  - `primary_admits(o: LensOutcome) -> bool`
  - `backstop_admits(o: LensOutcome) -> bool`

**Context for the implementer:** This module is pure — no `ctx`, no I/O, no imports from other stages. It mirrors `src/sdlc/stages/code/freeze.py`, which holds C2's decision rules the same way. `Measurement` in `src/sdlc/measurement.py:29-45` is the repo's existing model-validator idiom for "a value we may not have, with the reason we do not have it"; `LensOutcome`'s validator follows the same shape. Read both before starting.

- [ ] **Step 1: Write the failing tests**

Create `tests/review/test_lens_outcome.py`:

```python
"""C8: lens-absence tombstones -- the pure layer.

A lens that did not run must be constructible only as an absence, never as
an approval. These tests pin the classifier's truth table (spec 3.2), the
model invariant (spec 3.1), and the two admission predicates as exact
transcriptions of shipped behaviour (spec 3.4).
"""

import pytest
from pydantic import ValidationError

from sdlc.stages.review.lenses import (
    GATING_LENSES,
    LensOutcome,
    LensPresence,
    backstop_admits,
    classify_lens,
    primary_admits,
)
from sdlc.stages.review.models import ReviewFinding, ReviewReport


def _approving() -> ReviewReport:
    return ReviewReport(approve=True)


def _rejecting_blocking() -> ReviewReport:
    """`blocking_findings` is a DERIVED property on ReviewReport -- it filters
    `findings` to severity critical/high. It cannot be passed to the
    constructor; drive it through severity."""
    return ReviewReport(
        approve=False,
        findings=[ReviewFinding(assertion="a1", severity="high", detail="broken")],
    )


def _rejecting_non_blocking() -> ReviewReport:
    return ReviewReport(
        approve=False,
        findings=[ReviewFinding(assertion="a1", severity="low", detail="nit")],
    )


def test_gating_lenses_holds_exactly_the_two_gating_lenses():
    """deep_review is FILTERED -- it gates nothing, so its absence cannot be
    read as approval and it is deliberately not graded."""
    assert GATING_LENSES == frozenset({"reviewer", "adversary"})


@pytest.mark.parametrize(
    "enabled,agent_present,reached,report,expected",
    [
        # flag off wins over everything -- the operator's declaration is the
        # truthful cause; path geometry and wiring are moot.
        (False, True, True, None, LensPresence.DECLARED_ABSENT),
        (False, False, False, None, LensPresence.DECLARED_ABSENT),
        # a missing agent on an enabled lens is a real misconfiguration, and
        # it is observable whether or not the run site was reached.
        (True, False, True, None, LensPresence.UNDECLARED_ABSENT),
        (True, False, False, None, LensPresence.UNDECLARED_ABSENT),
        # enabled, wired, never reached -- routine pipeline geometry (A1).
        (True, True, False, None, LensPresence.NOT_REACHED),
        # enabled, wired, reached, nothing came back -- the wiring broke.
        (True, True, True, None, LensPresence.UNDECLARED_ABSENT),
    ],
)
def test_classify_lens_truth_table(enabled, agent_present, reached, report, expected):
    outcome = classify_lens(
        "adversary",
        enabled=enabled,
        agent_present=agent_present,
        reached=reached,
        report=report,
    )
    assert outcome.presence is expected
    assert outcome.approved is None
    assert outcome.reason, "every absent state must carry a reason"


def test_classify_lens_present_carries_the_report_facts():
    outcome = classify_lens(
        "reviewer", enabled=True, agent_present=True, reached=True, report=_rejecting_blocking()
    )
    assert outcome.presence is LensPresence.PRESENT
    assert outcome.approved is False
    assert outcome.has_blocking_findings is True


def test_classify_lens_rejects_an_unreached_report():
    """reached=False with a report is incoherent -- refuse it rather than
    silently normalizing it into PRESENT."""
    with pytest.raises(ValueError):
        classify_lens(
            "adversary", enabled=True, agent_present=True, reached=False, report=_approving()
        )


@pytest.mark.parametrize(
    "presence",
    [
        LensPresence.DECLARED_ABSENT,
        LensPresence.NOT_REACHED,
        LensPresence.UNDECLARED_ABSENT,
    ],
)
def test_absent_outcome_cannot_claim_approval(presence):
    """The whole point of the row: absence is unconstructible as approval."""
    with pytest.raises(ValidationError):
        LensOutcome(lens="adversary", presence=presence, approved=True, reason="whatever")


@pytest.mark.parametrize(
    "presence",
    [
        LensPresence.DECLARED_ABSENT,
        LensPresence.NOT_REACHED,
        LensPresence.UNDECLARED_ABSENT,
    ],
)
def test_absent_outcome_requires_a_reason(presence):
    with pytest.raises(ValidationError):
        LensOutcome(lens="adversary", presence=presence)


def test_present_outcome_requires_an_approved_verdict():
    with pytest.raises(ValidationError):
        LensOutcome(lens="reviewer", presence=LensPresence.PRESENT)


@pytest.mark.parametrize(
    "report,admits",
    [
        (_approving(), True),
        (_rejecting_blocking(), False),
        # The F2 cell: a PRESENT primary rejecting with NO blocking findings
        # still fails, exactly as code/step.py:798 does today. Do not
        # harmonize this with backstop_admits.
        (_rejecting_non_blocking(), False),
    ],
)
def test_primary_admits_present_cells(report, admits):
    outcome = classify_lens(
        "reviewer", enabled=True, agent_present=True, reached=True, report=report
    )
    assert primary_admits(outcome) is admits


@pytest.mark.parametrize(
    "presence",
    [
        LensPresence.DECLARED_ABSENT,
        LensPresence.NOT_REACHED,
        LensPresence.UNDECLARED_ABSENT,
    ],
)
def test_both_predicates_admit_every_absent_state(presence):
    """Ruling OQ1: the task layer is non-blocking in every presence state.
    The tombstone changes what absence SAYS, never what the task layer DOES."""
    outcome = LensOutcome(lens="adversary", presence=presence, reason="because")
    assert primary_admits(outcome) is True
    assert backstop_admits(outcome) is True


@pytest.mark.parametrize(
    "report,admits",
    [
        (_approving(), True),
        (_rejecting_blocking(), False),
        # transcribes code/step.py:813's `or not adversary.blocking_findings`
        (_rejecting_non_blocking(), True),
    ],
)
def test_backstop_admits_present_cells(report, admits):
    outcome = classify_lens(
        "adversary", enabled=True, agent_present=True, reached=True, report=report
    )
    assert backstop_admits(outcome) is admits
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/review/test_lens_outcome.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'sdlc.stages.review.lenses'`.

- [ ] **Step 3: Write the module**

Create `src/sdlc/stages/review/lenses.py`:

```python
"""C8: lens-absence tombstones.

A lens that did not run must not be spelled the same way as a lens that
approved. This module is the single place that decides which of those two
things happened, and the single place that says what each verdict admits.

Pure by construction -- no ``ctx``, no I/O, no cross-stage imports -- so the
rules are table-testable, exactly like ``code/freeze.py`` holds C2's decision
rules. The model invariant mirrors ``Measurement`` (``sdlc/measurement.py``):
a value we may not have, with the reason we do not have it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, model_validator

from .models import ReviewReport

# The lenses whose presence is graded. deep_review is deliberately absent: it
# is post-decision at every call site and gates nothing, so its absence cannot
# be read as approval.
GATING_LENSES: Final[frozenset[str]] = frozenset({"reviewer", "adversary"})


class LensPresence(StrEnum):
    PRESENT = "present"
    DECLARED_ABSENT = "declared_absent"
    NOT_REACHED = "not_reached"
    UNDECLARED_ABSENT = "undeclared_absent"


class LensOutcome(BaseModel):
    """What one lens did on one task attempt.

    Carries FACTS, not a verdict: the two lenses apply genuinely different
    admission rules (see ``primary_admits`` / ``backstop_admits``), and folding
    them into one pre-computed "blocking" boolean is how a silent semantic
    change gets in.
    """

    lens: str
    presence: LensPresence
    approved: bool | None = None
    has_blocking_findings: bool = False
    reason: str = ""

    @model_validator(mode="after")
    def _facts_match_presence(self) -> LensOutcome:
        if self.presence is LensPresence.PRESENT:
            if self.approved is None:
                raise ValueError("PRESENT requires an approved verdict")
            return self
        # Every absent state. An absence that claims approval is exactly the
        # defect C8 exists to end -- make it unconstructible, not merely
        # discouraged.
        if self.approved is not None:
            raise ValueError(f"{self.presence} cannot carry an approved verdict")
        if not self.reason:
            raise ValueError(f"{self.presence} requires a reason")
        return self


def classify_lens(
    lens: str,
    *,
    enabled: bool,
    agent_present: bool,
    reached: bool,
    report: ReviewReport | None,
) -> LensOutcome:
    """The single producer of a tombstone.

    Derived from exactly the facts the runner's own pre-check consults, plus
    one the call site already knows, so the tombstone cannot disagree with the
    predicate that gated the run. ``reached`` is a caller-supplied boolean, not
    an inspection of control flow -- that is what keeps this pure.

    Order carries reasoning: ``enabled`` first, because an operator's
    declaration is the truthful cause and makes geometry moot; then
    ``agent_present``, because a missing agent on an enabled lens is a real
    misconfiguration observable whether or not the run site was reached, and
    hiding it behind NOT_REACHED would suppress a wiring defect on exactly the
    runs (quarantined ones) where lens coverage matters most.
    """
    if report is not None and not reached:
        raise ValueError("a lens that was not reached cannot have produced a report")

    if not enabled:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.DECLARED_ABSENT,
            reason=f"{lens} disabled by configuration",
        )
    if not agent_present:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.UNDECLARED_ABSENT,
            reason=f"{lens} enabled but no agent is configured",
        )
    if not reached:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.NOT_REACHED,
            reason=f"{lens} run site was never reached on this task",
        )
    if report is None:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.UNDECLARED_ABSENT,
            reason=f"{lens} ran but produced no report (raised, or returned nothing)",
        )
    return LensOutcome(
        lens=lens,
        presence=LensPresence.PRESENT,
        approved=bool(report.approve),
        has_blocking_findings=bool(report.blocking_findings),
    )


def primary_admits(outcome: LensOutcome) -> bool:
    """Transcribes ``review is None or review.approve`` (code/step.py:798).

    ANY rejection by a present primary fails the done path -- blocking findings
    or not. Deliberately NOT harmonized with ``backstop_admits``: loosening the
    primary's bar is a substantive change that belongs to its own register row.
    """
    return outcome.presence is not LensPresence.PRESENT or bool(outcome.approved)


def backstop_admits(outcome: LensOutcome) -> bool:
    """Transcribes ``adversary is None or adversary.approve or not
    adversary.blocking_findings`` (code/step.py:813)."""
    return (
        outcome.presence is not LensPresence.PRESENT
        or bool(outcome.approved)
        or not outcome.has_blocking_findings
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/review/test_lens_outcome.py -q`
Expected: PASS, all cases.

- [ ] **Step 5: Export the new names**

REVIEW-1.5 pins the slice's export list, so the new public names join it. Edit `src/sdlc/stages/review/__init__.py` — add to the imports:

```python
from .lenses import (
    GATING_LENSES,
    LensOutcome,
    LensPresence,
    backstop_admits,
    classify_lens,
    primary_admits,
)
```

and add `"GATING_LENSES"`, `"LensOutcome"`, `"LensPresence"`, `"backstop_admits"`, `"classify_lens"`, `"primary_admits"` to `__all__`, keeping it alphabetically sorted as it already is.

- [ ] **Step 6: Run the review suite**

Run: `pytest tests/review/ -q`
Expected: PASS. Nothing in `tests/review/` depends on the task-layer wiring yet, so all existing pins still hold at this point. If any fail, **SG-1 fires**.

- [ ] **Step 7: Commit**

Write the message to a file (no heredocs), then commit with one path per `git add`:

```bash
printf '%s\n' "feat(review): add typed lens-absence tombstones" "" "A review lens that did not run is spelled the same way as one that" "approved: every fail-open leg returns None and every consumer reads" "None as agreement. Add the pure layer that ends that conflation." "" "LensOutcome carries facts with a validator that makes an absent-and-" "approved outcome unconstructible. classify_lens is the single producer," "derived from the same facts the runner's pre-check consults plus a" "caller-supplied reached flag, so a tombstone cannot disagree with the" "predicate that gated the run. NOT_REACHED types the adversary's routine" "unreached geometry so UNDECLARED_ABSENT keeps meaning \"the wiring broke\"." "" "primary_admits and backstop_admits transcribe the two shipped admission" "rules exactly, including their asymmetry: any present-primary rejection" "fails, only a blocking adversary rejection does. Nothing is wired yet." > .git/C8_MSG
git add src/sdlc/stages/review/lenses.py
git add src/sdlc/stages/review/__init__.py
git add tests/review/test_lens_outcome.py
git commit -F .git/C8_MSG
```

---

### Task 2: `TaskResult` carries the outcomes

**Implements:** spec §3.3.

**Files:**
- Modify: `src/sdlc/workflows/models.py` (imports near `:17`, `TaskResult` at `:52-63`)
- Test: `tests/test_task_result_lens_outcomes.py` (new)

**Interfaces:**
- Consumes: `LensOutcome`, `LensPresence` from Task 1.
- Produces: `TaskResult.lens_outcomes: list[LensOutcome]`, default empty — read by Task 3 (populated) and Task 6 (graded).

**Context for the implementer:** `TaskResult` is a Temporal-visible model; `code/AGENTS.md` names `workflows/models.py` in the Rule 3 passthrough set. A defaulted field is safe for in-flight workflows — they deserialize with an empty list, which Task 6 grades as a **failure**, the correct side to fail on. Follow the existing field style: one field per line with a short trailing comment naming the row.

- [ ] **Step 1: Write the failing test**

Create `tests/test_task_result_lens_outcomes.py`:

```python
"""C8: TaskResult carries lens tombstones through to the merge gate."""

from sdlc.stages.review.lenses import LensOutcome, LensPresence
from sdlc.workflows.models import TaskResult


def test_task_result_defaults_to_no_lens_outcomes():
    """A producer that predates the field -- or an in-flight workflow crossing
    a deploy -- deserializes with an empty list. The merge gate grades that as
    a failure (Task 6); it must never read as 'all lenses fine'."""
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert tr.lens_outcomes == []


def test_task_result_carries_lens_outcomes():
    outcomes = [
        LensOutcome(lens="reviewer", presence=LensPresence.PRESENT, approved=True),
        LensOutcome(
            lens="adversary",
            presence=LensPresence.NOT_REACHED,
            reason="adversary run site was never reached on this task",
        ),
    ]
    tr = TaskResult(
        task_id="t1", status="done", attempts=1, branch="b", lens_outcomes=outcomes
    )
    assert [o.lens for o in tr.lens_outcomes] == ["reviewer", "adversary"]
    assert tr.lens_outcomes[1].presence is LensPresence.NOT_REACHED


def test_task_result_round_trips_lens_outcomes_through_json():
    """Temporal serializes this model; the tombstone must survive the trip."""
    tr = TaskResult(
        task_id="t1",
        status="quarantined",
        attempts=2,
        branch="b",
        lens_outcomes=[
            LensOutcome(
                lens="adversary",
                presence=LensPresence.UNDECLARED_ABSENT,
                reason="adversary ran but produced no report",
            )
        ],
    )
    restored = TaskResult.model_validate_json(tr.model_dump_json())
    assert restored.lens_outcomes[0].presence is LensPresence.UNDECLARED_ABSENT
    assert restored.lens_outcomes[0].approved is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_task_result_lens_outcomes.py -q`
Expected: FAIL — `test_task_result_defaults_to_no_lens_outcomes` errors with `AttributeError: 'TaskResult' object has no attribute 'lens_outcomes'`, and the other two fail validation on an unexpected keyword.

- [ ] **Step 3: Add the field**

In `src/sdlc/workflows/models.py`, add the import alongside the other stage-model imports near the top of the file:

```python
from ..stages.review.lenses import LensOutcome
```

Then add the field to `TaskResult`, after `deep_review` and before `plan_drift`:

```python
    lens_outcomes: list[LensOutcome] = Field(default_factory=list)  # C8: lens-absence tombstones
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_task_result_lens_outcomes.py -q`
Expected: PASS.

- [ ] **Step 5: Run the broader suite**

Run: `pytest tests/ -q`
Expected: PASS — a defaulted field breaks nothing yet. If an import cycle appears (`workflows/models.py` → `stages/review/lenses.py`), stop and report: **SG-1**. `lenses.py` imports only from `.models` inside its own slice, so a cycle would indicate something unmodelled.

- [ ] **Step 6: Commit**

```bash
printf '%s\n' "feat(workflows): carry lens tombstones on TaskResult" "" "The merge gate can only grade evidence the task layer produced, so the" "LensOutcome list needs a channel from code.step to merge.step. Defaulted" "to empty: a producer that predates the field deserializes with no" "outcomes, which the gate grades as a failure rather than a silent pass." > .git/C8_MSG
git add src/sdlc/workflows/models.py
git add tests/test_task_result_lens_outcomes.py
git commit -F .git/C8_MSG
```

---

### Task 3: Task-layer wiring — classify, read predicates, delete the compound guard

**Implements:** spec §3.2 (the `:335` collapse), §3.3, §3.4 (both predicates and the `:802` deletion), §3.7 (REVIEW-1.6, CODE-1.6).

**Files:**
- Modify: `src/sdlc/stages/code/step.py:325-350` (delete the duplicate pre-check), `:798` (predicate), `:800-813` (classify + delete the compound guard + predicate), `:827` and `:899` (both `TaskResult` returns)
- Modify: `tests/review/test_review_wiring.py:51`, `tests/review/test_adversary_workflow.py:185-198`
- Modify: `src/sdlc/stages/review/review.md`, `src/sdlc/stages/review/AGENTS.md`, `src/sdlc/stages/code/code.md`, `src/sdlc/stages/code/AGENTS.md`
- Test: `tests/code/test_lens_tombstones.py` (new)

**Interfaces:**
- Consumes: `classify_lens`, `primary_admits`, `backstop_admits`, `LensPresence` (Task 1); `TaskResult.lens_outcomes` (Task 2).
- Produces: every `TaskResult` out of `code.step` carries one outcome per name in `GATING_LENSES`. No new callable.

**Context for the implementer:** `code/step.py`'s `step()` runs a `while True:` fix loop. Each iteration runs the coding harness, QA, then the primary reviewer at `:736`, computes `task_passed` at `:750`, and then reaches the review block at `:798-813`. Two `return TaskResult(...)` statements sit inside that loop: `:827` (done) and `:899` (post-gate — `done` or `quarantined` depending on the operator). Both must carry the outcomes computed in the current iteration.

Three edits interlock and must land together:

1. The **duplicate pre-check** at `:335` inside `_run_adversary` is deleted. The runner at `review/step.py:185` already holds that rule; keeping a second copy means the classifier's inputs can drift from the predicate that gated the run, which is the failure the whole design exists to prevent.
2. The **compound guard** `if review is not None:` at `:802` is deleted. This reverses a recorded design position — see the docstring amendment in Step 5, and spec §3.4 for the four-point rebuttal.
3. The `None`-reads at `:798` and `:813` become predicate calls.

**Behaviour must be preserved except for typed absence.** If any approval or rejection path changes outcome, **SG-3 fires**.

- [ ] **Step 1: Write the failing tests**

Create `tests/code/test_lens_tombstones.py`. It reuses the fixture and patch pattern already used throughout `tests/code/test_code_slice_contract.py` — read that file's imports and `_StubCtx` first and mirror them exactly.

```python
"""C8: the task layer records what each lens did, and stops reading None as
approval. Ruling OQ1: none of this blocks the done path."""

from unittest.mock import AsyncMock, patch

import pytest

from sdlc.core.models import (
    DevTask,
    GateDecision,
    GateOutcome,
    HarnessKind,
    HarnessRunResult,
    PipelineConfig,
    ValidationContract,
)
from sdlc.stages.code import step as code
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.lenses import LensPresence
from sdlc.stages.review.models import DeepReviewReport, ReviewFinding, ReviewReport

from test_code_slice_contract import _StubCtx  # same stub the slice tests use

# Absolute, not relative: there is no tests/__init__.py and pytest runs in
# prepend import mode, so test modules are top-level. This is the repo's own
# sibling-import idiom (tests/test_memory_wiring.py:14 and four others).


def _presence(tr, lens):
    return {o.lens: o.presence for o in tr.lens_outcomes}[lens]


def _task(task_id):
    return DevTask(
        id=task_id,
        title="Implement feature",
        description="Write code",
        role="dev",
        acceptance_criteria=["Tests pass"],
        files_hint=["app.py"],
    )


def _run():
    return HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=0,
        commit_sha="c1",
        cost_usd=0.5,
        summary="success",
    )


@pytest.mark.asyncio
async def test_adversary_failure_is_tombstoned_and_does_not_block_done():
    """REVIEW-1.3 stands: the lens stays fail-open. What changes is that its
    absence is no longer spelled the same as its approval."""
    ctx = _StubCtx()
    cfg = PipelineConfig(adversarial_review_enabled=True)
    task = _task("task-adv-raise")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = ReviewReport(approve=True)
        mock_adv.return_value = None  # the runner's fail-open leg
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=object(),
            adversary_agent=object(),
        )

    assert tr.status == "done"
    assert _presence(tr, "adversary") is LensPresence.UNDECLARED_ABSENT
    assert _presence(tr, "reviewer") is LensPresence.PRESENT


@pytest.mark.asyncio
async def test_disabled_adversary_is_declared_absent():
    ctx = _StubCtx()
    cfg = PipelineConfig(adversarial_review_enabled=False)
    task = _task("task-adv-off")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = ReviewReport(approve=True)
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=object(),
            adversary_agent=None,
        )

    assert tr.status == "done"
    assert _presence(tr, "adversary") is LensPresence.DECLARED_ABSENT


@pytest.mark.asyncio
async def test_adversary_runs_when_the_primary_is_disabled():
    """Regression for the compound guard at code/step.py:802. 'No primary,
    adversary only' used to run NO lens at all -- the operator enabled a lens
    that silently never executed."""
    ctx = _StubCtx()
    cfg = PipelineConfig(review_enabled=False, adversarial_review_enabled=True)
    task = _task("task-no-primary")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = None  # review_enabled=False
        mock_adv.return_value = ReviewReport(approve=True)
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=None,
            adversary_agent=object(),
        )

    assert mock_adv.await_count == 1, "the adversary must run without a primary"
    assert tr.status == "done"
    assert _presence(tr, "reviewer") is LensPresence.DECLARED_ABSENT
    assert _presence(tr, "adversary") is LensPresence.PRESENT


@pytest.mark.asyncio
async def test_blocking_adversary_rejection_still_bites_without_a_primary():
    """Test above pins that the adversary RUNS on the new path; this pins that
    its rejection still routes to the fix loop there."""
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(
                gate="task:task-adv-blocks", outcome=GateOutcome.REJECT, decided_by="human"
            )
        ]
    )
    cfg = PipelineConfig(
        review_enabled=False, adversarial_review_enabled=True, max_fix_attempts=1
    )
    task = _task("task-adv-blocks")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = None
        mock_adv.return_value = ReviewReport(
            approve=False,
            findings=[ReviewFinding(assertion="a1", severity="critical", detail="unsafe")],
        )
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        # budget = cfg.max_fix_attempts + 1 = 2 (code/step.py:535), and the
        # blocking adversary rejection puts non-empty issues in the fix loop
        # (_fix_loop_issues unions the adversary's blocking findings), so a
        # SECOND attempt runs before the gate. Each attempt consumes two
        # execute_activity side effects -- run_test_suite then get_task_diff --
        # so four entries are required. Same shape as the repo's own
        # quarantine-path tests (test_code_slice_contract.py:277-282, :394-399).
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=None,
            adversary_agent=object(),
        )

    assert tr.status == "quarantined"
    assert _presence(tr, "adversary") is LensPresence.PRESENT


@pytest.mark.asyncio
async def test_unreached_adversary_is_not_reached_not_undeclared_absent():
    """Reviewer A1: the adversary's run site sits inside the approving block,
    so a task that never gets there never reached its lens. That is routine
    pipeline geometry, not broken wiring -- typing it NOT_REACHED is what keeps
    UNDECLARED_ABSENT meaning 'enabled, reached, and the wiring broke'."""
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(
                gate="task:task-unreached", outcome=GateOutcome.REJECT, decided_by="human"
            )
        ]
    )
    cfg = PipelineConfig(adversarial_review_enabled=True, max_fix_attempts=1)
    task = _task("task-unreached")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        # tests fail -> task_passed is False -> the approving block is skipped
        mock_qa.return_value = QAReport(tests_passed=False, issues=["boom"])
        mock_rev.return_value = ReviewReport(approve=True)
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        # Failing QA gives the fix loop non-empty issues, so a second attempt
        # runs before the budget-exhausted gate: four side effects, two per
        # attempt (test_code_slice_contract.py:277-282 is the same shape).
        mock_act.side_effect = [
            QAReport(tests_passed=False, issues=["boom"]),
            {"files": ["app.py"]},
            QAReport(tests_passed=False, issues=["boom"]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=object(),
            adversary_agent=object(),
        )

    assert tr.status == "quarantined"
    assert mock_adv.await_count == 0
    assert _presence(tr, "adversary") is LensPresence.NOT_REACHED
    assert _presence(tr, "reviewer") is LensPresence.PRESENT
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/code/test_lens_tombstones.py -q`
Expected: FAIL. `_presence` raises `KeyError` (no outcomes are recorded yet), and `test_adversary_runs_when_the_primary_is_disabled` fails on `mock_adv.await_count == 1` because the `:802` guard still suppresses it.

- [ ] **Step 3: Delete the duplicate pre-check in `_run_adversary`**

In `src/sdlc/stages/code/step.py`, delete these two lines from the top of `_run_adversary` (currently `:335-336`):

```python
    if not cfg.adversarial_review_enabled or adversary_agent is None:
        return None
```

The function now unconditionally delegates to `review_run_adversary`, whose own pre-check at `review/step.py:185` is the single remaining copy of the rule.

- [ ] **Step 4: Rewrite the review block**

Add to the imports inside `step()` (alongside the existing local imports at `:492-493`):

```python
    from ..review.lenses import backstop_admits, classify_lens, primary_admits
```

Replace `code/step.py:798-813` — from `review_ok = ...` down to and including the `if adversary is None or ...` line — with:

```python
        review_outcome = classify_lens(
            "reviewer",
            enabled=cfg.review_enabled,
            agent_present=reviewer_agent is not None,
            reached=True,  # the primary runs on every attempt (:736)
            report=review,
        )
        review_ok = primary_admits(review_outcome)

        adversary = None
        # Classified as unreached up front: the adversary's run site is inside
        # the approving block, so a task that never gets there never reached
        # its lens. Overwritten below if it does.
        adversary_outcome = classify_lens(
            "adversary",
            enabled=cfg.adversarial_review_enabled,
            agent_present=adversary_agent is not None,
            reached=False,
            report=None,
        )
        if task_passed and review_ok:
            adversary = await _run_adversary(
                ctx,
                cfg,
                contract,
                assertions,
                diff,
                qa_raw,
                task,
                adversary_agent=adversary_agent,
            )
            adversary_outcome = classify_lens(
                "adversary",
                enabled=cfg.adversarial_review_enabled,
                agent_present=adversary_agent is not None,
                reached=True,
                report=adversary,
            )
            if backstop_admits(adversary_outcome):
```

Note what is gone: the `if review is not None:` wrapper around the `_run_adversary` call. The adversary now runs on `task_passed and review_ok` alone. The body under `if backstop_admits(...)` — the deep review, the handoff, and the `done` return — keeps its existing indentation.

- [ ] **Step 5: Populate both `TaskResult` return sites**

At the done return (`:827`), add after `review=review,`:

```python
                    lens_outcomes=[review_outcome, adversary_outcome],
```

At the post-gate return (`:899`), add after `review=review,`:

```python
                lens_outcomes=[review_outcome, adversary_outcome],
```

Both sites are inside the same loop iteration, so both see the outcomes classified above.

- [ ] **Step 6: Run the new tests**

Run: `pytest tests/code/test_lens_tombstones.py -q`
Expected: PASS, all five.

- [ ] **Step 7: Amend the three broken review pins**

Run: `pytest tests/review/ -q`
Expected: exactly **three** failures — `test_pass_condition_requires_review_approval`, `test_adversary_never_runs_without_a_primary_reviewer`, and `test_non_blocking_adversary_rejection_does_not_abandon_the_task`. Any fourth failure means **SG-1 fires**.

The third one is a pin the ruled spec's §4.1 enumeration missed — flag that to the orchestrator as a recorded deviation from the spec's four-pin table, then amend it here. It is a real broken pin, not a surprise: `tests/review/test_adversary_workflow.py:161-172` asserts `"not adversary.blocking_findings"` appears in the 800 characters after the first `await _run_adversary`, which is exactly the `:813` expression Step 4 replaced with `backstop_admits(adversary_outcome)`.

In `tests/review/test_review_wiring.py`, replace the assertion at `:51`:

```python
def test_pass_condition_requires_review_approval():
    """C8: the success path reads a typed presence value instead of `review is
    None`, but the SEMANTICS are unchanged -- primary_admits fails on any
    present-and-rejecting primary, exactly as `review is None or
    review.approve` did."""
    src = SRC.read_text(encoding="utf-8")
    assert "review_ok = primary_admits(review_outcome)" in src, (
        "the task success path must require reviewer approval when review ran"
    )
```

In `tests/review/test_adversary_workflow.py`, replace `test_adversary_never_runs_without_a_primary_reviewer` (`:185-198`) with its reversal:

```python
def test_adversary_runs_without_a_primary_reviewer():
    """C8 REVERSES the earlier position that the adversary presupposes a first
    opinion. Decorrelation does not require a primary to exist -- the lens
    reads the same contract, diff and test output either way -- and the
    fail-open justification is about the adversary FAILING, not about the
    primary having run. The old guard meant 'primary off, adversary on' ran no
    lens at all while the operator believed one was running: C8's own defect,
    in a guard rather than a None-read. Nobody gets a surprise adversary --
    adversarial_review_enabled defaults to False, so this stays a two-flag
    opt-in."""
    src = _src()
    pred = src.find("if task_passed and review_ok:")
    call = src.find("await _run_adversary")
    assert pred != -1 and call > pred
    assert "review is not None" not in src[pred:call], (
        "the adversary must NOT be gated on primary-reviewer presence"
    )
```

In the same file, replace `test_non_blocking_adversary_rejection_does_not_abandon_the_task` (`:161-172`). Its invariant is unchanged and still enforced — it simply moved out of an inline expression and into a named predicate:

```python
def test_non_blocking_adversary_rejection_does_not_abandon_the_task():
    """A reject whose findings are all medium/low has no actionable instruction;
    it must be treated as agreement, not fall through to ``if not issues: break``
    which silently abandons a task that passed its gate. blocking_findings is
    actionable; the boolean alone is not -- same rule as the primary.

    C8 moved that rule from an inline ``not adversary.blocking_findings``
    expression into ``backstop_admits`` (review/lenses.py), which reads
    ``has_blocking_findings`` off the tombstone. The invariant is unchanged;
    only its home is. test_backstop_admits_present_cells pins the behaviour
    directly, this pins that the task layer still routes through it."""
    src = _src()
    idx = src.find("await _run_adversary")
    assert idx != -1
    gate = src[idx : idx + 800]
    assert "backstop_admits(adversary_outcome)" in gate
```

Note the dropped `self._run_adversary` fallback: Task 4 deletes the twin that
made it necessary, and the live wrapper is the only `_run_adversary` left.

**Do not satisfy this pin by reinstating `not adversary.blocking_findings` at
the call site.** The predicate is the single home of the rule now; a second
copy is the drift this design exists to prevent. **SG-2** covers it.

- [ ] **Step 8: Re-run the review suite**

Run: `pytest tests/review/ -q`
Expected: PASS.

- [ ] **Step 9: Update the review and code contracts**

These land here rather than in Task 1, because this is the task that makes their statements true.

In `src/sdlc/stages/review/review.md`, add after REVIEW-1.5:

```markdown
### REVIEW-1.6
Every lens in `GATING_LENSES` (`src/sdlc/stages/review/lenses.py`) yields a typed `LensOutcome` recording what it did: `PRESENT` with the report's verdict, or one of three absent states — `DECLARED_ABSENT` (the operator disabled it), `NOT_REACHED` (enabled, but its run site was never reached on this task), `UNDECLARED_ABSENT` (enabled and reached, but no report came back). `LensOutcome`'s validator makes an absent-and-approved outcome unconstructible, and every absent state carries a reason. `classify_lens` is the single producer, pure and derived from the same facts the runner's own pre-check consults, so a tombstone cannot disagree with the predicate that gated the run. Fail-open at the task layer is preserved and now explicit: `primary_admits` and `backstop_admits` admit every absent state, so absence never blocks delivery — it is graded at the merge gate instead (MERGE-1.8). [C8]
```

In the same file's "Failure modes" section, replace the first bullet — it overstates the primary's fail-open, since a raising primary propagates rather than returning `None`:

```markdown
- **Primary review absent**: the primary returns `None` in exactly two cases — `PipelineConfig.review_enabled=False`, or no reviewer agent configured. An exception inside the primary is *not* caught and propagates. Either absence is recorded as a `LensOutcome` (REVIEW-1.6) rather than read as approval.
```

and the adversary bullet:

```markdown
- **Adversary failure**: the adversary lens fails open: any exception logs a warning and returns `None`, which no longer reads as agreement — it is recorded as an `UNDECLARED_ABSENT` tombstone (REVIEW-1.6) that the merge gate grades.
```

In `src/sdlc/stages/review/AGENTS.md`, replace the fail-open invariant line:

```markdown
- Lenses are fail-open at the task layer: safety lenses must never fail task delivery. They are never *silent*, though — every gating lens records a `LensOutcome` tombstone (`lenses.py`), and the merge gate grades it.
- `lenses.py` holds the C8 tombstone types and decision rules as pure functions (no `ctx`, no I/O, table-testable); `step.py` does not duplicate them.
```

In `src/sdlc/stages/code/code.md`, add after CODE-1.5:

```markdown
### CODE-1.6
Every `TaskResult` the code stage returns — from both return sites, across all three statuses — carries one `LensOutcome` per name in `GATING_LENSES`, classified once per attempt. The task success condition reads those outcomes through `primary_admits` / `backstop_admits` rather than testing a report for `None`; no presence state blocks the done path. [C8]
```

In `src/sdlc/stages/code/AGENTS.md`, add to the Invariants list:

```markdown
- The C8 lens tombstones are classified here but defined in the review slice (`stages/review/lenses.py`); this slice never re-implements the presence rules or the admission predicates.
```

- [ ] **Step 10: Pin that the classifier reads the runner's own facts**

Spec 3.2's guarantee -- "the tombstone cannot disagree with the predicate that
gated the run" -- holds only while `classify_lens` is invoked with the same
config and agent facts the runner consults. Deleting the duplicate pre-check
(Step 3) is the structural half; this needle is the other half, in the repo's
established source-assertion style. Append to `tests/code/test_lens_tombstones.py`:

```python
def test_classifier_is_invoked_with_the_runners_own_predicate_facts():
    """C8 spec 3.2: if a call site classifies from facts other than the ones
    the runner's pre-check reads, the tombstone can drift away from what
    actually gated the run -- the quintuplicated-predicate failure, one layer
    down."""
    import pathlib

    src = pathlib.Path("src/sdlc/stages/code/step.py").read_text(encoding="utf-8")
    assert src.count("enabled=cfg.adversarial_review_enabled") == 2, (
        "both adversary classify_lens sites read the runner's own flag"
    )
    assert src.count("agent_present=adversary_agent is not None") == 2
    assert "enabled=cfg.review_enabled" in src
    assert "agent_present=reviewer_agent is not None" in src
```

Run: `pytest tests/code/test_lens_tombstones.py -q`
Expected: PASS.

- [ ] **Step 11: Run the full suite**

Run: `pytest tests/ -q`
Expected: PASS. The merge layer is untouched so far, so nothing there should move. If a merge test fails now, **SG-1 fires** — the fixture blast radius is not supposed to open until Task 6.

- [ ] **Step 12: Commit**

```bash
printf '%s\n' "feat(code): read lens tombstones instead of None-as-approval" "" "The task success condition stops spelling absence the same way as" "approval. Both lenses are classified once per attempt and the outcomes" "ride on both TaskResult return sites; review_ok and the adversary guard" "become primary_admits/backstop_admits, which transcribe the two shipped" "admission rules exactly -- including their asymmetry. No presence state" "blocks the done path, so REVIEW-1.3 is untouched." "" "Two deletions come with it. The duplicate adversary pre-check in the" "code wrapper is removed so the runner holds the only copy of the rule," "keeping the classifier's inputs from drifting away from the predicate" "that gated the run. And the compound guard that ran the adversary only" "when the primary produced a report is gone: it meant \"primary off," "adversary on\" ran no lens at all while the operator believed one was" "running. That reverses a recorded position; the amended test carries" "the argument." > .git/C8_MSG
git add src/sdlc/stages/code/step.py
git add tests/code/test_lens_tombstones.py
git add tests/review/test_review_wiring.py
git add tests/review/test_adversary_workflow.py
git add src/sdlc/stages/review/review.md
git add src/sdlc/stages/review/AGENTS.md
git add src/sdlc/stages/code/code.md
git add src/sdlc/stages/code/AGENTS.md
git commit -F .git/C8_MSG
```

---

### Task 4: Delete the dead `TaskHost` twins

**Implements:** spec §3.6b, ruling OQ4; reviewer note P1.

**Files:**
- Modify: `src/sdlc/workflows/task_host.py` (delete `_run_adversary` at `:311-333` and `_run_deep_review` at `:335-360`, plus their now-unused imports)
- Modify: `tests/review/test_adversary_workflow.py:106-112`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new. This is a deletion; the only visible effect is on source-concatenation tests.

**Context for the implementer:** `TaskHost._run_adversary` and `_run_deep_review` have no call sites — `_dev_task` (`:261`) delegates to `code.step`, which carries its own wrappers. They are two of the five copies of the absence predicate. With the dedup elevated to the mechanism in Task 3, leaving two unreachable copies would undercut it.

**Why this is its own task:** the deletion is behaviourally inert but textually disruptive. `tests/review/`'s pins concatenate `feature.py` + `task_host.py` + `review/step.py` + `code/step.py` and search the result with `str.find()`. Removing text from the middle changes which definition a `find()` lands on. Isolating the deletion makes any fallout unambiguous.

- [ ] **Step 1: Confirm the twins are dead**

Run: `grep -rn "_run_adversary\|_run_deep_review" src/ --include=*.py`
Expected: definitions and internal references in `task_host.py`, plus the live wrappers and their call sites in `code/step.py`. **No `self._run_adversary(` or `self._run_deep_review(` call anywhere.** If one exists, stop and report — the twins are not dead and this task's premise is wrong.

- [ ] **Step 2: Delete both methods**

In `src/sdlc/workflows/task_host.py`, delete the whole `_run_adversary` method (`:311-333`) and the whole `_run_deep_review` method (`:335-360`).

Then remove the imports that only they used — `run_adversary as review_run_adversary` (`:45`) and `run_deep_review as review_run_deep_review` (`:48`). Leave `t_adversary`, `t_reviewer`, and `t_deep_review` (`:21`, `:25`) alone: `_dev_task` passes them to `code.step` at `:304-306`.

- [ ] **Step 3: Verify nothing unused remains**

Run: `ruff check src/sdlc/workflows/task_host.py`
Expected: clean. An `F401 unused import` here means you left an import behind; remove it.

- [ ] **Step 4: Run the review suite and expect exactly one failure**

Run: `pytest tests/review/ -q`
Expected: exactly one failure — `test_adversary_is_fail_open`. Any other failure means **SG-1 fires**.

This failure is the one reviewer note P1 predicted, and it is a false alarm about a real invariant. The test locates the *first* `async def _run_adversary` in the concatenation and asserts `return None` appears within the following 2600 characters. That first match used to be the dead `task_host.py` twin, whose pre-check contained `return None`. Now it is the live `code/step.py` wrapper, whose pre-check Task 3 removed. Fail-open behaviour is unchanged — it lives in `run_adversary` at `review/step.py:186` and `:240`, which is where the assertion should have been pointing all along.

**Do not fix this by reinstating a pre-check.** That would undo Task 3 Step 3 and re-create the drift risk the design exists to close. **SG-2** covers this.

- [ ] **Step 5: Retarget the assertion at the code that actually implements fail-open**

In `tests/review/test_adversary_workflow.py`, replace `test_adversary_is_fail_open` (`:106-112`):

```python
def test_adversary_is_fail_open():
    """A failed lens counts as agreement at the task layer -- it must never
    fail a task (REVIEW-1.3 stands). C8 retargets this at run_adversary, which
    is where fail-open actually lives: the code-stage wrapper's duplicate
    pre-check was removed so the runner holds the only copy of the rule, and
    the dead task_host twin that this find() used to land on is gone."""
    src = STAGE_SRC.read_text(encoding="utf-8")
    idx = src.find("async def run_adversary")
    body = src[idx : idx + 2600]
    assert "return None" in body
    assert "raise" not in body
```

Note the change from `_src()` to `STAGE_SRC` — the same source the sibling `test_adversary_never_touches_the_session` already reads, so this test stops depending on concatenation order entirely.

- [ ] **Step 6: Run the full suite**

Run: `pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
printf '%s\n' "refactor(workflows): delete the dead TaskHost lens twins" "" "TaskHost._run_adversary and _run_deep_review have no call sites --" "_dev_task delegates to code.step, which carries its own wrappers. They" "were two of the five copies of the lens-absence predicate, and C8 makes" "single-sourcing that predicate the mechanism rather than hygiene, so" "unreachable duplicates undercut it." "" "The deletion is behaviourally inert but shifts the source-concatenation" "offsets that tests/review/ pins rely on. test_adversary_is_fail_open" "used to land on the twin's pre-check; it now reads run_adversary" "directly, which is where fail-open is actually implemented." > .git/C8_MSG
git add src/sdlc/workflows/task_host.py
git add tests/review/test_adversary_workflow.py
git commit -F .git/C8_MSG
```

---

### Task 5: The merge check helper

**Implements:** spec §3.5 (the grading rule), rulings OQ2 and OQ3.

**Files:**
- Modify: `src/sdlc/stages/merge/step.py` (add `_lens_presence_check` beside `_plan_drift_check` at `:97-117`)
- Test: `tests/merge/test_lens_presence_gate.py` (new)

**Interfaces:**
- Consumes: `GATING_LENSES`, `LensPresence` (Task 1); `TaskResult.lens_outcomes` (Task 2).
- Produces: `_lens_presence_check(results: list) -> CheckResult` — a check named `review_lenses_present`, `CheckClass.ADVISORY`. Task 6 wires it into the live checks list.

**Context for the implementer:** `merge/step.py` already has a private check-builder in exactly this shape — read `_plan_drift_check` (`:97-117`) first and follow it: a module-level function taking `results`, returning `build_check(name, passed, classification, detail=...)`, with a docstring that argues the aggregation rule. Like `review_severity` and `plan_drift`, this reads `results_list` **unfiltered by status** — a quarantined task's lens coverage counts too.

The grading rule is the OQ2 ruling and must be implemented exactly:

> Fail if a lens has **no outcome recorded at all**, or an outcome whose presence is `UNDECLARED_ABSENT`. `PRESENT`, `DECLARED_ABSENT`, and `NOT_REACHED` pass — and all four states are named in the detail regardless.

The no-outcome clause is load-bearing: without it a `TaskResult` with `lens_outcomes=[]` has no `UNDECLARED_ABSENT` entry to trip on and would sail through. A missing tombstone is graded as severely as a broken one.

- [ ] **Step 1: Write the failing tests**

Create `tests/merge/test_lens_presence_gate.py`:

```python
"""C8: the merge gate grades lens presence.

Ruling OQ2: fail only on UNDECLARED_ABSENT or a missing outcome. DECLARED_ABSENT
and NOT_REACHED pass and are still reported. Ruling OQ3: one uniform check.
"""

from sdlc.gate import CheckClass
from sdlc.stages.merge.step import _lens_presence_check
from sdlc.stages.review.lenses import LensOutcome, LensPresence
from sdlc.workflows.models import TaskResult


def _result(task_id: str, *outcomes: LensOutcome) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        status="done",
        attempts=1,
        branch="b",
        lens_outcomes=list(outcomes),
    )


def _present(lens: str) -> LensOutcome:
    return LensOutcome(lens=lens, presence=LensPresence.PRESENT, approved=True)


def _absent(lens: str, presence: LensPresence) -> LensOutcome:
    return LensOutcome(lens=lens, presence=presence, reason=f"{lens} {presence.value}")


def test_check_is_advisory_and_uniform_across_both_lenses():
    """OQ3: one check, not a per-lens pair."""
    check = _lens_presence_check([_result("t1", _present("reviewer"), _present("adversary"))])
    assert check.name == "review_lenses_present"
    assert check.classification is CheckClass.ADVISORY
    assert check.passed is True


def test_undeclared_absent_fails_and_names_the_lens():
    check = _lens_presence_check(
        [_result("t1", _present("reviewer"), _absent("adversary", LensPresence.UNDECLARED_ABSENT))]
    )
    assert check.passed is False
    assert "adversary" in check.detail
    assert "t1" in check.detail


def test_declared_absent_passes_but_is_still_reported():
    """The operator's declaration is honoured -- and never silent."""
    check = _lens_presence_check(
        [_result("t1", _present("reviewer"), _absent("adversary", LensPresence.DECLARED_ABSENT))]
    )
    assert check.passed is True
    assert "declared_absent" in check.detail
    assert "adversary" in check.detail


def test_not_reached_passes_but_is_still_reported():
    """Reviewer A1: routine pipeline geometry is not broken wiring."""
    check = _lens_presence_check(
        [_result("t1", _present("reviewer"), _absent("adversary", LensPresence.NOT_REACHED))]
    )
    assert check.passed is True
    assert "not_reached" in check.detail


def test_empty_outcomes_list_fails():
    """The empty-list defense. A producer that predates the field has no
    UNDECLARED_ABSENT entry to trip on, so the rule must fail on a MISSING
    outcome too -- otherwise it sails through."""
    check = _lens_presence_check([_result("t-legacy")])
    assert check.passed is False
    assert "no outcome recorded" in check.detail


def test_a_lens_missing_from_a_populated_list_fails():
    check = _lens_presence_check([_result("t1", _present("reviewer"))])
    assert check.passed is False
    assert "adversary" in check.detail


def test_any_task_fires():
    """Aggregation matches plan_drift: one bad task fails the run."""
    good = _result("t1", _present("reviewer"), _present("adversary"))
    bad = _result("t2", _present("reviewer"), _absent("adversary", LensPresence.UNDECLARED_ABSENT))
    assert _lens_presence_check([good, bad]).passed is False
    assert _lens_presence_check([good, good]).passed is True


def test_quarantined_tasks_are_graded_too():
    """Unfiltered by status, matching review_severity and plan_drift."""
    tr = TaskResult(
        task_id="t-q",
        status="quarantined",
        attempts=2,
        branch="b",
        lens_outcomes=[_present("reviewer"), _absent("adversary", LensPresence.UNDECLARED_ABSENT)],
    )
    assert _lens_presence_check([tr]).passed is False


def test_no_task_results_passes():
    check = _lens_presence_check([])
    assert check.passed is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/merge/test_lens_presence_gate.py -q`
Expected: collection error — `ImportError: cannot import name '_lens_presence_check'`.

- [ ] **Step 3: Write the helper**

In `src/sdlc/stages/merge/step.py`, add the import alongside the other stage-model imports at the top of the file:

```python
from ..review.lenses import GATING_LENSES, LensPresence
```

Then add this function immediately after `_plan_drift_check` (after `:117`):

```python
def _lens_presence_check(results: list) -> CheckResult:
    """C8: a lens that did not run must not be graded as one that approved.

    Ruling OQ2 -- fail only on UNDECLARED_ABSENT (the lens was asked for, was
    reached, and did not deliver) or on a MISSING outcome. The missing-outcome
    clause is what preserves the defense against an empty `lens_outcomes`
    list: a producer that predates the field has no UNDECLARED_ABSENT entry to
    trip on, so without it a task with no tombstones at all would pass. A
    missing tombstone is as severe as a broken one.

    DECLARED_ABSENT (the operator turned it off) and NOT_REACHED (the run site
    was never reached -- routine geometry on quarantined and budget-exhausted
    tasks) both pass, and every state is named in the detail regardless: the
    ruling honours operator intent and pipeline shape without letting either
    go silent.

    Ruling OQ3 -- one uniform check over both lenses; the detail names which.
    Unfiltered by status, matching review_severity and plan_drift.
    """
    failures: list[str] = []
    notes: list[str] = []
    for r in results:
        recorded = {o.lens: o for o in (getattr(r, "lens_outcomes", None) or [])}
        task_id = getattr(r, "task_id", "?")
        for lens in sorted(GATING_LENSES):
            outcome = recorded.get(lens)
            if outcome is None:
                failures.append(f"{task_id}/{lens}: no outcome recorded")
            elif outcome.presence is LensPresence.UNDECLARED_ABSENT:
                failures.append(f"{task_id}/{lens}: {outcome.presence.value} ({outcome.reason})")
            else:
                notes.append(f"{task_id}/{lens}: {outcome.presence.value}")
    return build_check(
        "review_lenses_present",
        not failures,
        CheckClass.ADVISORY,
        detail="; ".join(failures + notes) or "no task results to grade",
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/merge/test_lens_presence_gate.py -q`
Expected: PASS, all nine.

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -q`
Expected: PASS. The helper exists but is not yet wired into the checks list and not yet in the manifest, so no existing merge test can see it. If a merge test fails here, **SG-1 fires**.

- [ ] **Step 6: Commit**

```bash
printf '%s\n' "feat(merge): add the review_lenses_present check builder" "" "Grades the C8 tombstones: fail on UNDECLARED_ABSENT -- a lens that was" "asked for, was reached, and did not deliver -- or on a missing outcome." "DECLARED_ABSENT and NOT_REACHED pass and are still named in the detail," "so an operator's choice and the pipeline's own geometry stay visible" "without failing every merge." "" "The missing-outcome clause carries the empty-list defense: a TaskResult" "with no tombstones has no UNDECLARED_ABSENT entry to trip on, so without" "it a producer that predates the field would pass silently." "" "Not wired into the gate yet -- that lands with the manifest entry." > .git/C8_MSG
git add src/sdlc/stages/merge/step.py
git add tests/merge/test_lens_presence_gate.py
git commit -F .git/C8_MSG
```

---

### Task 6: Wire the gate — manifest, checks list, `review_severity`, fixtures

**Implements:** spec §3.5 (both checks), §3.7 (MERGE-1.8, MERGE-1.3), §4.1 (fixture blast radius).

**Files:**
- Modify: `src/sdlc/gate.py:86-97` (manifest entry)
- Modify: `src/sdlc/stages/merge/step.py:323-328` (`review_severity`), `:350` (checks list)
- Modify: `src/sdlc/stages/merge/merge.md`
- Modify: `tests/conftest.py:273-275`
- Modify: `tests/review/test_review_wiring.py:75`
- Modify: `tests/merge/test_merge_slice_contract.py`, `tests/merge/test_merge_gate_wiring.py`, `tests/merge/test_plan_drift_gate.py`
- Test: `tests/merge/test_lens_presence_gate.py` (append)

**Interfaces:**
- Consumes: `_lens_presence_check` (Task 5); `primary_admits` (Task 1).
- Produces: the finished feature. Nothing downstream consumes it.

**Context for the implementer:** These land in **one commit** on purpose. Adding a name to `MERGE_REQUIRED_CHECKS` without a producer makes `gate.py:_synthesized` fabricate a failing `MISCONFIGURED` check for every gate evaluation, so splitting the manifest entry from the checks-list wiring would leave a deliberately red intermediate commit. The `required_checks` fixture in `tests/conftest.py:284-288` is manifest-driven and picks the new name up automatically — only its docstring count is stale.

This is where the fixture blast radius opens. Every `TaskResult` built in `tests/merge/` without `lens_outcomes` now fails `review_lenses_present`. **Fix them by supplying outcomes, never by relaxing the check** — that is exactly what SG-2 guards.

- [ ] **Step 1: Write the failing tests**

Append to `tests/merge/test_lens_presence_gate.py`:

```python
def test_manifest_carries_the_new_check_as_advisory():
    """In MERGE_REQUIRED_CHECKS so C3's synthesis covers the case where the
    producer stops emitting it. ADVISORY, never ABSOLUTE -- an absolute
    presence check would delete the config flags by force."""
    from sdlc.gate import MERGE_REQUIRED_CHECKS

    assert MERGE_REQUIRED_CHECKS["review_lenses_present"] is CheckClass.ADVISORY


def test_absent_from_gate_input_synthesizes_a_misconfigured_failure():
    """C3's fail-closed synthesis, now covering this check."""
    from sdlc.gate import MERGE_REQUIRED_CHECKS, build_check, evaluate_quality_gate

    checks = [
        build_check(name, True, klass)
        for name, klass in MERGE_REQUIRED_CHECKS.items()
        if name != "review_lenses_present"
    ]
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "review_lenses_present" in report.blocking
    synthesized = next(c for c in report.checks if c.name == "review_lenses_present")
    assert "MISCONFIGURED" in synthesized.detail


def test_undeclared_absence_is_waivable_by_an_audited_override():
    """ADVISORY means the human who accepts a missing lens leaves a record."""
    from sdlc.gate import MERGE_REQUIRED_CHECKS, GateOverride, build_check, evaluate_quality_gate

    checks = [
        build_check(name, name != "review_lenses_present", klass)
        for name, klass in MERGE_REQUIRED_CHECKS.items()
    ]
    assert evaluate_quality_gate(checks).passed is False
    waived = evaluate_quality_gate(
        checks,
        [
            GateOverride(
                check="review_lenses_present",
                approved_by="operator",
                reason="adversary agent unavailable in this environment",
            )
        ],
    )
    assert waived.passed is True
    assert "review_lenses_present" in waived.overridden


def test_the_live_checks_list_produces_the_check():
    """Source needle: the helper must actually be called by merge.step, not
    merely exist. Without this the manifest entry alone would make every gate
    fail via synthesis."""
    import pathlib

    src = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")
    assert "_lens_presence_check(results_list)" in src


def test_review_severity_grades_only_present_lenses():
    """The merge gate stops reading absence as approval. It grades through
    primary_admits, so it cannot diverge from the task success condition on
    what 'approved' means."""
    import pathlib

    src = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")
    assert "r.review is None or r.review.approve" not in src
    assert "primary_admits" in src


def test_review_severity_still_fails_on_a_present_rejecting_reviewer():
    """Spec 4 test 9's behavioural half. The source needle above proves the old
    None-read is gone; this proves the new expression still BLOCKS, so the
    rewrite cannot have quietly turned review_severity into a check that passes
    everything. Reads the same generator the checks list builds."""
    rejecting = _result(
        "t1",
        LensOutcome(lens="reviewer", presence=LensPresence.PRESENT, approved=False),
        _present("adversary"),
    )
    approving = _result("t2", _present("reviewer"), _present("adversary"))

    def _severity(results):
        return all(
            primary_admits(o)
            for r in results
            for o in (getattr(r, "lens_outcomes", None) or [])
            if o.lens == "reviewer"
        )

    assert _severity([rejecting]) is False
    assert _severity([approving]) is True
    # An absent reviewer contributes nothing here -- that is
    # review_lenses_present's question, not this check's.
    assert _severity([_result("t3")]) is True
```

The import line at the top of this file grows to include `primary_admits`:

```python
from sdlc.stages.review.lenses import LensOutcome, LensPresence, primary_admits
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/merge/test_lens_presence_gate.py -q`
Expected: the five new tests fail — `KeyError: 'review_lenses_present'` on the manifest, and assertion failures on the two source needles.

- [ ] **Step 3: Add the manifest entry**

In `src/sdlc/gate.py`, add to `MERGE_REQUIRED_CHECKS` after `"review_severity"`:

```python
        "review_lenses_present": CheckClass.ADVISORY,
```

- [ ] **Step 4: Rewrite `review_severity` and wire the new check**

In `src/sdlc/stages/merge/step.py`, extend the import added in Task 5:

```python
from ..review.lenses import GATING_LENSES, LensPresence, primary_admits
```

Then extend the manifest's own comment (`gate.py:80-85`) so the new entry's
meaning is recorded where the constant lives, appended after the existing
"pressure point moved from the producer to this constant" sentence:

```python
# One entry grades evidence rather than a measurement: `review_lenses_present`
# (C8) says whether each gating lens produced a tombstone at all, so a lens
# that silently stopped running fails here instead of reading as approval.
```

Replace the `review_severity` builder at `:323-328`:

```python
        build_check(
            "review_severity",
            all(
                primary_admits(o)
                for r in results_list
                for o in (getattr(r, "lens_outcomes", None) or [])
                if o.lens == "reviewer"
            ),
            CheckClass.ADVISORY,
            detail="clean-context reviewer blocking findings (FR-204); "
            "absence is graded by review_lenses_present, not here",
        ),
```

Then add the new check to the same list, after `_plan_drift_check(results_list),` at `:350`:

```python
        _lens_presence_check(results_list),
```

Two checks, deliberately apart: "did the lens run?" and "did it approve?" are different questions, and one audited `GateOverride` should not waive both.

- [ ] **Step 5: Run the merge suite and survey the damage**

Run: `pytest tests/merge/ tests/review/ -q`
Expected: `tests/merge/test_lens_presence_gate.py` passes, and the fixture failures from §4.1 appear — `TaskResult`s built without `lens_outcomes` now fail `review_lenses_present`, plus `test_review_wiring.py:75`'s source needle.

Failures outside this list mean **SG-1 fires**:
- `tests/merge/test_merge_slice_contract.py:112, :171, :247, :291`
- `tests/merge/test_merge_gate_wiring.py:97-117`
- `tests/merge/test_plan_drift_gate.py:24, :119`
- `tests/review/test_review_wiring.py:75`

- [ ] **Step 6: Supply outcomes to the merge fixtures**

For each `TaskResult(...)` at the lines above, add a passing pair. Define this helper once at the top of each affected test module (after the imports):

```python
from sdlc.stages.review.lenses import LensOutcome, LensPresence


def _lenses_ran() -> list[LensOutcome]:
    """C8: both gating lenses accounted for, so review_lenses_present passes.
    Supply outcomes -- never relax the check to go green."""
    return [
        LensOutcome(lens="reviewer", presence=LensPresence.PRESENT, approved=True),
        LensOutcome(
            lens="adversary",
            presence=LensPresence.DECLARED_ABSENT,
            reason="adversary disabled by configuration",
        ),
    ]
```

and pass `lens_outcomes=_lenses_ran()` to each `TaskResult(...)` construction. In `tests/merge/test_plan_drift_gate.py:24` the construction is inside a factory function, so the single edit there covers every caller.

`DECLARED_ABSENT` for the adversary is the honest default for these fixtures: they do not configure an adversary, and under the OQ2 ruling that passes while staying visible in the detail.

- [ ] **Step 7: Amend the merge source pin**

In `tests/review/test_review_wiring.py`, replace the assertion at `:75`:

```python
    assert "primary_admits(o)" in block, (
        "review check grades PRESENT reviewer lenses through the same predicate "
        "the task success condition uses; absence is review_lenses_present's job"
    )
```

Note: the surrounding `block = src[idx : idx + 220]` slice may now be too short to contain the assertion — the rewritten builder is longer than the original. If the test fails on a slice boundary rather than on content, widen the slice to `src[idx : idx + 400]` and say so in the commit body.

- [ ] **Step 8: Update the conftest docstring**

In `tests/conftest.py:273-275`, the counts are stale — the manifest grew from eight to nine:

```python
    `required_checks()` -> nine passing checks.
    `required_checks(coverage=False)` -> the same nine with `coverage`
    failing at its manifest classification.
```

The fixture body itself is manifest-driven and needs no change.

- [ ] **Step 9: Update the merge contract**

In `src/sdlc/stages/merge/merge.md`, add after MERGE-1.7:

```markdown
### MERGE-1.8
`review_lenses_present` (C8) is a required advisory check over `GATING_LENSES` (`src/sdlc/stages/review/lenses.py`), evaluated across every task in `task_results` unconditionally — a quarantined task's lens coverage counts the same as a done task's, matching MERGE-1.3's existing treatment of `review_severity`. Each task's `LensOutcome` list is read from `TaskResult.lens_outcomes`, classified once in the code stage and carried through unchanged. "Required" here means *the check must be produced*, not *every lens must have run*: the check **fails** when a lens in the manifest has no outcome recorded at all, or an outcome whose presence is `UNDECLARED_ABSENT` (the lens was enabled, its run site was reached, and no report came back). `DECLARED_ABSENT` (operator disabled it) and `NOT_REACHED` (the run site was never reached on this task) **pass**, and every presence state is named in the check detail regardless — absence is honoured, never silent. The check fails if **any** task in the run trips it. Like every other advisory check, a failure is waivable only through the audited `GateOverride` path (MERGE-1.3). Separately, `review_severity` grades only `PRESENT` reviewer lenses, through the same `primary_admits` predicate the task success condition uses, so the two layers cannot diverge on what "approved" means. [C8]
```

Update MERGE-1.3's advisory enumeration at `:17` to read:

```markdown
On advisory gate failures (`review_severity`, `review_lenses_present`, `traceability`, `coverage`, `plan_drift`), the merge stage presents the blocking advisory checks to the human merge gate.
```

And add to the "Failure modes" list:

```markdown
- **Lens never ran**: a gating lens with no recorded outcome, or one that was enabled and reached but returned nothing, fails `review_lenses_present` — human-waivable through the audited override path (MERGE-1.8).
```

- [ ] **Step 10: Run the full suite**

Run: `pytest tests/ -q`
Expected: PASS. Compare the counts against the Task 0 baseline: the total should have grown by the new tests only, with no net losses.

- [ ] **Step 11: Lint and type-check**

Run: `ruff check src/ tests/` then `ruff format --check src/ tests/`
Expected: clean.

Run: `mypy src/`
Expected: no *new* errors. The repo carries roughly 122 known pre-existing mypy errors scoped to `src/`; compare against the Task 0 baseline rather than expecting zero.

- [ ] **Step 12: Commit**

```bash
printf '%s\n' "feat(merge): grade lens presence at the quality gate" "" "review_lenses_present joins MERGE_REQUIRED_CHECKS as an advisory check," "so C3's fail-closed synthesis covers a producer that stops emitting it," "and the audited GateOverride path covers a human who accepts a missing" "lens. Advisory, not absolute: an absolute presence check would delete" "the review config flags by force." "" "review_severity stops reading absence as approval -- it now grades only" "PRESENT reviewer lenses, through the same primary_admits predicate the" "task success condition uses, so the two layers cannot drift apart on" "what approved means. Presence and verdict stay separate checks: they" "answer different questions, and one override should not waive both." "" "The manifest entry and the checks-list wiring land together because a" "manifest name without a producer fails every gate by synthesis. Merge" "fixtures gain explicit lens outcomes rather than the check being" "relaxed to accommodate them." > .git/C8_MSG
git add src/sdlc/gate.py
git add src/sdlc/stages/merge/step.py
git add src/sdlc/stages/merge/merge.md
git add tests/merge/test_lens_presence_gate.py
git add tests/merge/test_merge_slice_contract.py
git add tests/merge/test_merge_gate_wiring.py
git add tests/merge/test_plan_drift_gate.py
git add tests/review/test_review_wiring.py
git add tests/conftest.py
git commit -F .git/C8_MSG
```

---

## Verification Checklist

Run before declaring the branch finished. Evidence before assertions — paste the actual output, do not assert from memory.

- [ ] `pytest tests/ -q` — green, count compared against the Task 0 baseline
- [ ] `ruff check src/ tests/` and `ruff format --check src/ tests/` — clean
- [ ] `mypy src/` — no new errors versus baseline
- [ ] `git log --format='%s%n%b' origin/main..HEAD | grep -i "co-authored\|claude-session"` — **no output**. Any hit means an attribution trailer slipped in; rewrite the message before the branch is integrated.
- [ ] `grep -rn "review is None or review.approve\|r.review is None" src/` — no output. Both `None`-as-approval reads are gone.
- [ ] `grep -rn "_run_adversary\|_run_deep_review" src/sdlc/workflows/task_host.py` — no output. The twins are gone.
- [ ] Spec §4 tests 1–11 all have a home: 1, 2, 2b → Task 1; 3, 4, 5, 5b, 5c, 6, 11 → Task 3; 7, 8, 8b, 8c, 9, 10 → Tasks 5 and 6 (test 9 in both halves — the source needle and the behavioural pin on a PRESENT rejecting reviewer).
- [ ] All **five** broken pins are amended, none deleted: `test_review_wiring.py:51` (Task 3), `test_adversary_workflow.py:196` (Task 3), `test_adversary_workflow.py:161-172` (Task 3), `test_adversary_workflow.py:106-112` (Task 4), `test_review_wiring.py:75` (Task 6). The third is **not** in spec §4.1's table — the orchestrator records that enumeration gap as a deviation from the ruled spec.
- [ ] `grep -rn "not adversary.blocking_findings" src/` — no output. The rule lives in `backstop_admits` alone; a second copy at the call site would be the drift SG-2 guards.
