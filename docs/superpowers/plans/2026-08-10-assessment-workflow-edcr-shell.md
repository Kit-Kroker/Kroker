# AssessmentWorkflow EDCR Shell (E-45) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the durable `AssessmentWorkflow` FR-911 specifies — the EDCR DAG (init → scan → discover → assess → **report** → generate → finish) with six phase bodies deliberately unbuilt — plus the Tier 2 admission rule narrowed to human approvals.

**Architecture:** One pure admission function at two strictnesses (`admits(triage, *, require_human)`) replaces what would otherwise be two divergent copies of E-42's rule. A pure `assessment/models.py` holds the artifact; `workflows/assessment.py` runs the DAG as explicit methods, with `init` executing a real `TriageWorkflow` child so the "a human admitted this tree" claim is replayable evidence rather than a caller's assertion. Unbuilt phases return `Measurement.not_collected` naming their owning E-item, so an assessment that assessed nothing says so.

**Tech Stack:** Python 3.12+, Pydantic v2, Temporal (`temporalio`), pytest (`-m temporal` for the workflow-environment suite).

**Spec:** `docs/superpowers/specs/2026-08-10-assessment-workflow-edcr-shell-design.md`

## Global Constraints

- **Purity.** `src/sdlc/assessment/models.py` and `src/sdlc/triage/admission.py` import **only** Pydantic, `..measurement`, and `..triage.models`. They must never import `models.py`, `activities.py`, or `temporalio` — the same rule `triage/models.py`, `measurement.py`, `grounding.py` and `capability/models.py` state in their own docstrings. A dependency there must appear as a reviewable import.
- **FR-915.** A phase that did not run gets `Measurement.not_collected(reason)`, **never** `Measurement.measured(0.0)`. `Measurement`'s validator already refuses a value on a non-measured state; do not work around it.
- **Determinism.** No `datetime.now()`, no `uuid4()`, no filesystem access inside `@workflow.defn` code. Timestamps come from `workflow.now()`; child ids derive from `workflow.info().workflow_id`.
- **Temporal imports.** Every non-stdlib import inside `workflows/assessment.py` goes inside `with workflow.unsafe.imports_passed_through():`, as `workflows/triage.py:20` and `workflows/tidyup.py:22` do.
- **Admission rule strictness:** Tier 0 (`tidyup`) = `require_human=False`; Tier 2 (`assessment`) = `require_human=True`.
- **Line length 79** (the codebase's prevailing style; `ruff` is configured for the repo).
- Comments explain *why*, citing FR/E/D identifiers, matching the density of `workflows/triage.py`. Do not add narration comments.

---

### Task 1: The one admission rule

**Files:**
- Create: `src/sdlc/triage/admission.py`
- Modify: `src/sdlc/tidyup/backlog.py:13` (import line) and `:17-27` (`admitted`)
- Test: `tests/test_assessment_admission.py`

**Interfaces:**
- Consumes: `RepoTriage`, `Verdict`, `ReadinessOverride` from `sdlc.triage.models` (already exist).
- Produces: `admits(triage: RepoTriage, *, require_human: bool) -> tuple[bool, str]` in `sdlc.triage.admission`. Task 3 calls it with `require_human=True`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_assessment_admission.py`:

```python
"""E-45 D2: FR-903's admission rule, at both strictnesses.

The `policy` rows are the FUTURE-CONSUMER TRAP workflows/tidyup.py:87-97
documents: TidyUpWorkflow's after-triage auto-approves its own OFF readiness
gate, so TidyUpReport.after.override.approved_by == "policy" -- a machine
placeholder. E-42's rule would admit that tree to a Tier 2 audit.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sdlc.measurement import Measurement
from sdlc.triage.admission import admits
from sdlc.triage.models import (
    Readiness,
    ReadinessOverride,
    RepoTriage,
    Verdict,
)


def _triage(verdict: Verdict, approved_by: str | None = None) -> RepoTriage:
    ok = Measurement.measured(1.0)
    override = None
    if approved_by is not None:
        override = ReadinessOverride(
            approved_by=approved_by,
            reviewer="alice",
            reason="known",
            decided_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            gate_round=1,
        )
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        readiness=Readiness(
            buildable=ok, runnable=ok, tests_present=ok, structure_discernible=ok, verdict=verdict
        ),
        override=override,
    )


@pytest.mark.parametrize(
    "verdict,approved_by,tier0,tier2",
    [
        (Verdict.READY, None, True, True),
        (Verdict.READY, "policy", True, True),
        (Verdict.NOT_READY, None, False, False),
        (Verdict.INDETERMINATE, None, False, False),
        (Verdict.NOT_READY, "policy", True, False),
        (Verdict.NOT_READY, "timeout", True, False),
        (Verdict.NOT_READY, "human", True, True),
        (Verdict.INDETERMINATE, "policy", True, False),
        (Verdict.INDETERMINATE, "human", True, True),
    ],
)
def test_admission_table(verdict, approved_by, tier0, tier2):
    t = _triage(verdict, approved_by)
    assert admits(t, require_human=False)[0] is tier0
    assert admits(t, require_human=True)[0] is tier2


def test_a_refusal_carries_its_reason():
    """The reason lands on the Assessment, so a refusal is legible without a
    Temporal replay."""
    ok, why = admits(_triage(Verdict.NOT_READY, "policy"), require_human=True)
    assert ok is False
    assert "policy" in why
    assert "not_ready" in why


def test_a_missing_override_says_so():
    ok, why = admits(_triage(Verdict.INDETERMINATE), require_human=True)
    assert ok is False
    assert "no override" in why


def test_reviewer_is_never_consulted():
    """`reviewer` is self-asserted (the gap FR-1004 closes). Only
    approved_by -- GateDecision.decided_by verbatim -- is trustworthy, so a
    named reviewer on a policy approval must not rescue it."""
    t = _triage(Verdict.NOT_READY, "policy")
    assert t.override.reviewer == "alice"
    assert admits(t, require_human=True)[0] is False


def test_tidyup_delegates_rather_than_restating():
    """backlog.admitted must not hold a second copy of the rule: two
    admission rules agree only by coincidence, which is the failure shape
    2026-07-16-registry-drives-every-role was written about."""
    import inspect

    from sdlc.tidyup import backlog

    assert "admits(" in inspect.getsource(backlog.admitted)
    assert "Verdict.READY" not in inspect.getsource(backlog.admitted)
    assert backlog.admitted(_triage(Verdict.NOT_READY, "policy")) is True
    assert backlog.admitted(_triage(Verdict.NOT_READY)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_assessment_admission.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.triage.admission'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/triage/admission.py`:

```python
"""FR-903 (E-45 D2): the ONE admission rule, at two strictnesses.

Pure -- Pydantic and triage/models.py only, like the rest of triage/.

Tier 0 (tidy-up) and Tier 2 (assessment) differ in whether a non-human
approval admits, and that difference is a PARAMETER rather than a second copy
of the rule. Two admission rules in two modules agree only by coincidence,
which is the failure shape 2026-07-16-registry-drives-every-role was written
about: an invariant that held only while two hardcoded lists matched.
"""

from __future__ import annotations

from .models import RepoTriage, Verdict


def admits(triage: RepoTriage, *, require_human: bool) -> tuple[bool, str]:
    """Whether this triage admits the repository to the caller's tier.

    Returns (admitted, reason). The reason is recorded on the artifact, so a
    refusal is legible without a Temporal replay.

    `reviewer` is deliberately NOT consulted: it is self-asserted (the gap
    FR-1004 closes), while approved_by carries GateDecision.decided_by
    VERBATIM and is therefore the field that can be trusted to distinguish a
    human act from "policy" (gate OFF) or "timeout" (on_timeout=APPROVE).
    """
    verdict = triage.readiness.verdict
    if verdict is Verdict.READY:
        return True, "verdict ready"
    override = triage.override
    if override is None:
        return False, f"verdict {verdict.value} and no override"
    if require_human and override.approved_by != "human":
        return False, (
            f"verdict {verdict.value}; override approved_by="
            f"{override.approved_by!r} is not a human act"
        )
    return True, (f"verdict {verdict.value} admitted by {override.approved_by} override")
```

- [ ] **Step 4: Rewrite `backlog.admitted` as a delegation**

In `src/sdlc/tidyup/backlog.py`, replace the body of `admitted` (`:17-27`):

```python
def admitted(triage: RepoTriage) -> bool:
    """D7. Tier 0's strictness of the ONE admission rule (E-45 D2).

    FR-903's gate blocks Tier 2, not tidy-up, so this is not automatic. It is
    adopted for a mechanical reason: on a repository that does not build,
    build_integration_green is an ABSOLUTE merge-gate check, so every fix run
    would produce a correct patch and then be blocked. That is N runs of model
    spend to learn what the build probe already reported.

    That argument does not care WHO approved, hence require_human=False.
    Tier 2 passes True, because an EDCR audit is expensive per-capability
    reasoning terminating in a bundle handed to a customer (FR-921), where "a
    human said proceed" is load-bearing.
    """
    ok, _ = admits(triage, require_human=False)
    return ok
```

Add the import beside the existing `..triage.models` one:

```python
from ..triage.admission import admits
```

and **remove `Verdict` from the `..triage.models` import** (`backlog.py:13`) — `admitted` was its only user, so it is now unused and `ruff` will flag it. The line becomes:

```python
from ..triage.models import (
    FixClass,
    RepoTriage,
    TriageFinding,
    finding_identity,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_assessment_admission.py tests/test_tidyup_backlog.py -v`
Expected: PASS (both files — the tidy-up backlog suite proves the delegation preserved Tier 0 behaviour)

- [ ] **Step 6: Lint**

Run: `python -m ruff check src/sdlc/triage/admission.py src/sdlc/tidyup/backlog.py`
Expected: no findings (in particular no `F401` unused `Verdict`)

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/triage/admission.py src/sdlc/tidyup/backlog.py tests/test_assessment_admission.py
git commit -m "feat(triage): one admission rule at two strictnesses (E-45 D2)"
```

---

### Task 2: The `Assessment` artifact

**Files:**
- Create: `src/sdlc/assessment/__init__.py` (empty), `src/sdlc/assessment/models.py`
- Test: `tests/test_assessment_models.py`

**Interfaces:**
- Consumes: `Measurement`, `CollectionState` from `sdlc.measurement`; `RepoTriage` from `sdlc.triage.models`.
- Produces, all imported by Task 3:
  - `PhaseId` (str Enum: `INIT SCAN DISCOVER ASSESS REPORT GENERATE FINISH`, declared in that order)
  - `PHASE_ORDER: tuple[PhaseId, ...]`
  - `PhaseResult(phase: PhaseId, collected: Measurement)`
  - `InitOutcome(result: PhaseResult, triage: RepoTriage | None = None)`
  - `Assessment(repo_dir, commit_sha, toolchain, triage, admitted, admission_reason, phases, terminal_status)`
  - `terminal_status(admitted: bool, phases: list[PhaseResult]) -> str`
  - Status constants `BLOCKED`, `NO_PHASES`, `PARTIAL`, `ASSESSED`

- [ ] **Step 1: Write the failing test**

Create `tests/test_assessment_models.py`:

```python
"""E-45: the assessment artifact and its derived status."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.models import (
    ASSESSED,
    BLOCKED,
    NO_PHASES,
    PARTIAL,
    PHASE_ORDER,
    Assessment,
    InitOutcome,
    PhaseId,
    PhaseResult,
    terminal_status,
)
from sdlc.measurement import Measurement
from sdlc.triage.models import Readiness, RepoTriage, Verdict


def _triage() -> RepoTriage:
    ok = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        toolchain="python",
        readiness=Readiness(
            buildable=ok,
            runnable=ok,
            tests_present=ok,
            structure_discernible=ok,
            verdict=Verdict.READY,
        ),
    )


def _phases(collected: set[PhaseId]) -> list[PhaseResult]:
    return [
        PhaseResult(
            phase=p,
            collected=(
                Measurement.measured(1.0) if p in collected else Measurement.not_collected("stub")
            ),
        )
        for p in PHASE_ORDER
    ]


def test_report_runs_after_assess_and_before_generate():
    """FR-911 deviation (a): the methodology numbers report 4th and assess
    5th, but reports render risk scores only assess produces."""
    order = list(PHASE_ORDER)
    assert order.index(PhaseId.ASSESS) < order.index(PhaseId.REPORT)
    assert order.index(PhaseId.REPORT) < order.index(PhaseId.GENERATE)


def test_phase_order_is_the_whole_dag_once():
    """Spelled out rather than compared against tuple(PhaseId), which would
    be tautological: this is the assertion that catches a reordering."""
    assert [p.value for p in PHASE_ORDER] == [
        "init",
        "scan",
        "discover",
        "assess",
        "report",
        "generate",
        "finish",
    ]
    assert len(set(PHASE_ORDER)) == len(PhaseId) == 7


def test_a_phase_that_did_not_run_carries_no_value():
    """FR-915: never Measurement.measured(0.0)."""
    with pytest.raises(ValidationError):
        PhaseResult(phase=PhaseId.SCAN, collected=Measurement(state="not_collected", value=0.0))


@pytest.mark.parametrize(
    "admitted,collected,expected",
    [
        (False, set(), BLOCKED),
        (False, set(PHASE_ORDER), BLOCKED),
        (True, {PhaseId.INIT}, NO_PHASES),
        (True, {PhaseId.INIT, PhaseId.SCAN}, PARTIAL),
        (True, set(PHASE_ORDER), ASSESSED),
    ],
)
def test_terminal_status_is_derived(admitted, collected, expected):
    """D6: E-46 landing flips the status with no workflow edit."""
    assert terminal_status(admitted, _phases(collected)) == expected


def test_admitted_without_a_triage_is_unrepresentable():
    """Admission is a function of a RepoTriage (FR-903), so this state is a
    contradiction rather than an edge case."""
    with pytest.raises(ValidationError):
        Assessment(
            repo_dir="/r",
            triage=None,
            admitted=True,
            admission_reason="",
            phases=_phases(set()),
            terminal_status=BLOCKED,
        )


def test_phases_must_be_the_whole_dag_in_order():
    """Anything rendering the DAG relies on this, so the type enforces it."""
    with pytest.raises(ValidationError):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="ok",
            phases=_phases(set())[:3],
            terminal_status=NO_PHASES,
        )
    with pytest.raises(ValidationError):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="ok",
            phases=list(reversed(_phases(set()))),
            terminal_status=NO_PHASES,
        )


def test_a_refused_assessment_still_carries_the_triage():
    """E-44 D7's shape: not admitted is not empty-handed."""
    a = Assessment(
        repo_dir="/r",
        commit_sha="a" * 40,
        triage=_triage(),
        admitted=False,
        admission_reason="verdict not_ready",
        phases=_phases(set()),
        terminal_status=BLOCKED,
    )
    assert a.triage is not None
    assert a.triage.commit_sha == "a" * 40


def test_init_outcome_defaults_to_no_triage():
    out = InitOutcome(
        result=PhaseResult(phase=PhaseId.INIT, collected=Measurement.not_collected("child failed"))
    )
    assert out.triage is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_assessment_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/assessment/__init__.py` as an empty file.

Create `src/sdlc/assessment/models.py`:

```python
"""FR-911 (E-45): the EDCR assessment artifact.

Pure by design -- Pydantic, measurement.py and triage/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
triage/models.py and capability/models.py must not: a dependency here would
appear as a reviewable import.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ..measurement import CollectionState, Measurement
from ..triage.models import RepoTriage


class PhaseId(str, Enum):
    """The EDCR DAG in execution order.

    REPORT follows ASSESS deliberately -- FR-911 deviation (a). The source
    methodology numbers report 4th and assess 5th, but reports render risk
    scores only assess produces, and /finish requires all five reports
    complete. Declaration order IS the DAG order (see PHASE_ORDER), so there
    is no second list to disagree with this one.
    """

    INIT = "init"
    SCAN = "scan"
    DISCOVER = "discover"
    ASSESS = "assess"
    REPORT = "report"
    GENERATE = "generate"
    FINISH = "finish"


# Derived from the enum, never restated: a hand-written tuple beside the enum
# is a second registry, and this codebase has paid for one of those before.
PHASE_ORDER: tuple[PhaseId, ...] = tuple(PhaseId)

BLOCKED = "blocked:admission"
NO_PHASES = "admitted:no-phases-implemented"
PARTIAL = "assessed:partial"
ASSESSED = "assessed"


class PhaseResult(BaseModel):
    """One phase's outcome.

    `collected` is a Measurement, not a bool: a phase whose body is a later
    E-item reports not_collected naming that item, which is distinguishable
    from a phase that ran and found nothing (FR-915). There is deliberately
    NO generic payload field -- each later item adds its own TYPED field to
    Assessment, because an untyped bag would be a schema-less hole in the one
    artifact handed to a customer under FR-921.
    """

    phase: PhaseId
    collected: Measurement


class InitOutcome(BaseModel):
    """init's two halves: the phase row that lands in `phases`, and the
    artifact the admission rule reads. Separate because a failed triage child
    yields a row but no triage."""

    result: PhaseResult
    triage: RepoTriage | None = None


def terminal_status(admitted: bool, phases: list[PhaseResult]) -> str:
    """Derived, never assigned (D6), so E-46 landing changes the status with
    no workflow edit and no second place to update.

    Judged on post-init phases: init is the admission step, not an assessment
    of anything, so an admitted run whose every real phase is a stub reports
    NO_PHASES rather than a misleading ASSESSED.
    """
    if not admitted:
        return BLOCKED
    rest = [p for p in phases if p.phase is not PhaseId.INIT]
    done = [p for p in rest if p.collected.state is CollectionState.MEASURED]
    if not done:
        return NO_PHASES
    if len(done) < len(rest):
        return PARTIAL  # the seam FR-922's budgets (E-55) reuse
    return ASSESSED


class Assessment(BaseModel):
    repo_dir: str
    commit_sha: str = ""  # "" only when init failed to pin one
    toolchain: str | None = None
    # init's artifact -- in-history evidence (D3). None ONLY when the child
    # workflow itself failed, which is the one case where admission was never
    # consulted.
    triage: RepoTriage | None = None
    admitted: bool
    admission_reason: str  # admits()' reason, verbatim
    phases: list[PhaseResult] = Field(default_factory=list)
    terminal_status: str

    @model_validator(mode="after")
    def _no_triage_means_not_admitted(self) -> "Assessment":
        if self.triage is None and self.admitted:
            raise ValueError(
                "admitted with no triage -- admission is a function of a "
                "RepoTriage (FR-903), so this state is a contradiction"
            )
        return self

    @model_validator(mode="after")
    def _phases_are_the_whole_dag(self) -> "Assessment":
        got = tuple(p.phase for p in self.phases)
        if got != PHASE_ORDER:
            raise ValueError(
                f"phases must be the whole DAG in order -- expected "
                f"{[p.value for p in PHASE_ORDER]}, got "
                f"{[p.value for p in got]}"
            )
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_assessment_models.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Verify the purity constraint holds**

Run: `python -m ruff check src/sdlc/assessment/`
Then confirm no forbidden import: `python -m pytest tests/test_assessment_models.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/assessment/ tests/test_assessment_models.py
git commit -m "feat(assessment): Assessment artifact and derived terminal status (E-45)"
```

---

### Task 3: `AssessmentWorkflow`

**Files:**
- Create: `src/sdlc/workflows/assessment.py`
- Test: `tests/test_assessment_workflow.py`

**Interfaces:**
- Consumes: everything Task 2 produced; `admits` from Task 1; `GateHost` from `sdlc.workflows.gates`; `TriageInput`/`TriageWorkflow` from `sdlc.workflows.triage`; `GateSettings` from `sdlc.models`.
- Produces, imported by Tasks 4 and 5:
  - `AssessmentInput(repo_dir: str, commit: str = "HEAD", build_probe: bool = True, advisory_source: str = "none", gates: GateSettings = ...)`
  - `AssessmentWorkflow` with `@workflow.run run(self, inp: AssessmentInput) -> Assessment` and `@workflow.query assessment(self) -> Assessment | None`
  - Module-level pure helpers `unbuilt(phase) -> PhaseResult`, `skipped(phase) -> PhaseResult`, `assemble(repo_dir, init, admitted, reason, rest=None) -> Assessment`, and `PHASE_OWNER: dict[PhaseId, str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_assessment_workflow.py`:

```python
"""E-45. Pure helpers directly; sequencing through the workflow environment
lives in tests/test_assessment_workflow_e2e.py, following
tests/test_tidyup_workflow.py."""

from __future__ import annotations

import inspect

from sdlc.assessment.models import (
    ASSESSED,
    BLOCKED,
    NO_PHASES,
    PHASE_ORDER,
    PhaseId,
    PhaseResult,
    InitOutcome,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.models import GatePolicy
from sdlc.triage.models import Readiness, RepoTriage, Verdict
from sdlc.workflows.assessment import (
    PHASE_OWNER,
    AssessmentInput,
    AssessmentWorkflow,
    assemble,
    skipped,
    unbuilt,
)


def _triage() -> RepoTriage:
    ok = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        toolchain="python",
        readiness=Readiness(
            buildable=ok,
            runnable=ok,
            tests_present=ok,
            structure_discernible=ok,
            verdict=Verdict.READY,
        ),
    )


def _init(ok: bool = True) -> InitOutcome:
    if not ok:
        return InitOutcome(
            result=PhaseResult(
                phase=PhaseId.INIT, collected=Measurement.not_collected("triage child failed: boom")
            )
        )
    return InitOutcome(
        result=PhaseResult(phase=PhaseId.INIT, collected=Measurement.measured(1.0)),
        triage=_triage(),
    )


def test_input_defaults():
    inp = AssessmentInput(repo_dir="/r")
    assert inp.commit == "HEAD"
    assert inp.build_probe is True
    assert inp.advisory_source == "none"
    assert inp.gates.default_gate_policy is GatePolicy.HARD


def test_every_unbuilt_phase_names_the_item_that_owes_it():
    """An empty assessment says WHY it is empty on the face of the
    artifact."""
    for phase, owner in PHASE_OWNER.items():
        r = unbuilt(phase)
        assert r.collected.state is CollectionState.NOT_COLLECTED
        assert owner in r.collected.reason
        assert phase.value in r.collected.reason


def test_every_post_init_phase_has_an_owner():
    assert set(PHASE_OWNER) == set(PHASE_ORDER) - {PhaseId.INIT}


def test_assemble_fills_the_whole_dag_on_a_refusal():
    a = assemble("/r", _init(), False, "verdict not_ready")
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)
    assert a.terminal_status == BLOCKED
    assert a.admission_reason == "verdict not_ready"
    for p in a.phases:
        if p.phase is PhaseId.INIT:
            continue
        assert "not admitted" in p.collected.reason


def test_assemble_keeps_the_triage_on_a_refusal():
    """E-44 D7's shape: not admitted is not empty-handed -- the caller still
    gets the readiness verdict and every hygiene finding."""
    a = assemble("/r", _init(), False, "verdict not_ready")
    assert a.triage is not None
    assert a.commit_sha == "a" * 40
    assert a.toolchain == "python"


def test_assemble_on_a_failed_child_has_no_commit_and_is_not_admitted():
    a = assemble("/r", _init(ok=False), False, "triage child failed: boom")
    assert a.triage is None
    assert a.commit_sha == ""
    assert a.admitted is False
    assert a.terminal_status == BLOCKED


def test_assemble_on_an_admitted_run_reports_nothing_implemented():
    rest = [unbuilt(p) for p in PHASE_ORDER if p is not PhaseId.INIT]
    a = assemble("/r", _init(), True, "verdict ready", rest)
    assert a.admitted is True
    assert a.terminal_status == NO_PHASES
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_assemble_reports_assessed_once_every_phase_collects():
    """The status flips by itself when E-46..E-52 land -- no workflow edit."""
    rest = [
        PhaseResult(phase=p, collected=Measurement.measured(1.0))
        for p in PHASE_ORDER
        if p is not PhaseId.INIT
    ]
    assert assemble("/r", _init(), True, "verdict ready", rest).terminal_status == ASSESSED


def test_assemble_orders_phases_canonically_regardless_of_arrival():
    rest = list(reversed([unbuilt(p) for p in PHASE_ORDER if p is not PhaseId.INIT]))
    a = assemble("/r", _init(), True, "verdict ready", rest)
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_skipped_names_the_reason_it_did_not_run():
    r = skipped(PhaseId.SCAN)
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "not admitted" in r.collected.reason


def test_the_run_body_calls_the_phases_in_dag_order():
    """FR-911 deviation (a) is the thing most likely to be 'fixed' by someone
    reordering to match the source methodology's numbering. This guards the
    run body against that, since PHASE_ORDER alone would not catch it."""
    src = inspect.getsource(AssessmentWorkflow.run)
    calls = [
        "self._init(",
        "self._scan(",
        "self._discover(",
        "self._assess(",
        "self._report(",
        "self._generate(",
        "self._finish(",
    ]
    positions = [src.index(c) for c in calls]
    assert positions == sorted(positions)


def test_admission_is_checked_at_tier_two_strictness():
    src = inspect.getsource(AssessmentWorkflow.run)
    assert "require_human=True" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_assessment_workflow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.workflows.assessment'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/workflows/assessment.py`:

```python
"""AssessmentWorkflow (E-45) -- Tier 2's shell.

The EDCR DAG (init -> scan -> discover -> assess -> report -> generate ->
finish) as a durable workflow, with six of seven phase bodies deliberately
unbuilt: scan is E-46, discover E-48, assess E-49, finish E-51, report and
generate E-52.

What ships now is the shape plus three invariants that are cheapest to install
before any phase produces findings: the admission rule narrowed to HUMAN
approvals (D2), phase state in workflow history rather than a ported
workflow.json (FR-911 deviation (b)), and FR-915's not_collected discipline
applied to phases so an assessment that assessed nothing says so (D5).

No LLM call lives here. Operator-run only: the init phase's TriageWorkflow
child executes the assessed repository's own build (NFR-9); E-57 and E-21 are
what remove that debt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..assessment.models import (
        PHASE_ORDER,
        Assessment,
        InitOutcome,
        PhaseId,
        PhaseResult,
        terminal_status,
    )
    from ..measurement import Measurement
    from ..models import GateSettings
    from ..triage.admission import admits
    from ..triage.models import RepoTriage
    from .gates import GateHost
    from .triage import TriageInput, TriageWorkflow


class AssessmentInput(BaseModel):
    """Mirrors TriageInput's knobs, which are the ones the child needs.

    max_gate_rounds is deliberately NOT surfaced: the readiness gate's REVISE
    loop belongs to the child, which owns its own bound.
    """

    repo_dir: str
    commit: str = "HEAD"
    build_probe: bool = True
    advisory_source: str = "none"
    gates: GateSettings = Field(default_factory=GateSettings)


# The E-item owing each unbuilt phase body, so an empty assessment says WHY
# it is empty rather than merely being empty.
PHASE_OWNER: dict[PhaseId, str] = {
    PhaseId.SCAN: "E-46",
    PhaseId.DISCOVER: "E-48",
    PhaseId.ASSESS: "E-49",
    PhaseId.REPORT: "E-52",
    PhaseId.GENERATE: "E-52",
    PhaseId.FINISH: "E-51",
}


def unbuilt(phase: PhaseId) -> PhaseResult:
    """A phase whose body is a later item. Never Measurement.measured(0.0):
    a phase that did not run has no value (FR-915)."""
    return PhaseResult(
        phase=phase,
        collected=Measurement.not_collected(
            f"{phase.value} not implemented ({PHASE_OWNER[phase]})"
        ),
    )


def skipped(phase: PhaseId) -> PhaseResult:
    """A phase that exists but was never reached, because the repository was
    not admitted (FR-903 / ADR-18)."""
    return PhaseResult(
        phase=phase,
        collected=Measurement.not_collected("not run: repository not admitted (FR-903)"),
    )


def assemble(
    repo_dir: str,
    init: InitOutcome,
    admitted: bool,
    reason: str,
    rest: list[PhaseResult] | None = None,
) -> Assessment:
    """The ONLY constructor of an Assessment and the only caller of
    terminal_status: one place where the artifact is built means the derived
    status cannot disagree with the phase list it was derived from.

    Unreached phases are filled rather than omitted, so `phases` is always
    the whole DAG and anything rendering it can rely on that.
    """
    by_id = {p.phase: p for p in (rest or [])}
    phases = [init.result] + [
        by_id.get(p, skipped(p)) for p in PHASE_ORDER if p is not PhaseId.INIT
    ]
    t = init.triage
    return Assessment(
        repo_dir=repo_dir,
        commit_sha=t.commit_sha if t else "",
        toolchain=t.toolchain if t else None,
        triage=t,
        admitted=admitted,
        admission_reason=reason,
        phases=phases,
        terminal_status=terminal_status(admitted, phases),
    )


@workflow.defn
class AssessmentWorkflow(GateHost):
    """Inherits GateHost although it opens no gate of its own: status,
    pending_decisions and submit_gate_decision come free, and E-50's
    assessment gate checks will open gates here."""

    def __init__(self) -> None:
        super().__init__()
        self._assessment: Assessment | None = None

    @workflow.query
    def assessment(self) -> Assessment | None:
        """The artifact; None until the run terminates."""
        return self._assessment

    async def _init(self, inp: AssessmentInput) -> InitOutcome:
        """Phase 1. Runs TriageWorkflow as a CHILD (D3) rather than accepting
        a RepoTriage as input: the admission rule's whole subject is
        override.approved_by, and a caller-supplied artifact is a
        caller-supplied value for exactly that field. Running the child puts
        the verdict, the readiness gate and the human decision in THIS
        assessment's history, so the claim is replayable evidence.

        A child that raises degrades to a refusal, never a crashed
        assessment -- the shape TriageWorkflow._one established.
        """
        self._status = "triaging"
        try:
            triage: RepoTriage = await workflow.execute_child_workflow(
                TriageWorkflow.run,
                TriageInput(
                    repo_dir=inp.repo_dir,
                    commit=inp.commit,
                    build_probe=inp.build_probe,
                    advisory_source=inp.advisory_source,
                    gates=inp.gates,
                ),
                id=f"{workflow.info().workflow_id}-triage",
                task_queue=workflow.info().task_queue,
            )
        except Exception as e:  # noqa: BLE001
            return InitOutcome(
                result=PhaseResult(
                    phase=PhaseId.INIT,
                    collected=Measurement.not_collected(
                        f"triage child failed: {type(e).__name__}: {e}"[:300]
                    ),
                )
            )
        return InitOutcome(
            result=PhaseResult(phase=PhaseId.INIT, collected=Measurement.measured(1.0)),
            triage=triage,
        )

    async def _scan(self, inp: AssessmentInput) -> PhaseResult:
        """E-46 owns this body: S1-S5 / SS1-SS4 / QS1-QS4 signals, memoized
        on (tree hash, signal version) per FR-912."""
        return unbuilt(PhaseId.SCAN)

    async def _discover(self, inp: AssessmentInput) -> PhaseResult:
        """E-48 owns this body: D1-D8 discover proposers."""
        return unbuilt(PhaseId.DISCOVER)

    async def _assess(self, inp: AssessmentInput) -> PhaseResult:
        """E-49 owns this body: UnifiedRiskMap + risk proposers."""
        return unbuilt(PhaseId.ASSESS)

    async def _report(self, inp: AssessmentInput) -> PhaseResult:
        """E-52 owns this body: the five role reports."""
        return unbuilt(PhaseId.REPORT)

    async def _generate(self, inp: AssessmentInput) -> PhaseResult:
        """E-52 owns this body: the evidence bundle and its manifest."""
        return unbuilt(PhaseId.GENERATE)

    async def _finish(self, inp: AssessmentInput) -> PhaseResult:
        """E-51 owns this body: the 14 acceptance criteria as CheckResults."""
        return unbuilt(PhaseId.FINISH)

    def _done(self, a: Assessment) -> Assessment:
        self._assessment = a
        self._status = a.terminal_status
        return a

    @workflow.run
    async def run(self, inp: AssessmentInput) -> Assessment:
        init = await self._init(inp)
        if init.triage is None:
            # The child failed; admission was never consulted, and an
            # assessment that could not establish admission must never
            # proceed to assess.
            return self._done(assemble(inp.repo_dir, init, False, init.result.collected.reason))

        ok, why = admits(init.triage, require_human=True)
        if not ok:
            return self._done(assemble(inp.repo_dir, init, False, why))

        self._status = "running"
        rest = [
            await self._scan(inp),
            await self._discover(inp),
            await self._assess(inp),
            await self._report(inp),  # AFTER assess -- FR-911 dev. (a)
            await self._generate(inp),
            await self._finish(inp),
        ]
        return self._done(assemble(inp.repo_dir, init, True, why, rest))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_assessment_workflow.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Lint**

Run: `python -m ruff check src/sdlc/workflows/assessment.py`
Expected: no findings

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/assessment.py tests/test_assessment_workflow.py
git commit -m "feat(assessment): AssessmentWorkflow EDCR shell (E-45)"
```

---

### Task 4: Operator surface — CLI and worker registration

**Files:**
- Modify: `src/sdlc/cli.py` (imports ~`:16`, id helper after `tidyup_workflow_id` ~`:72`, parser after the `tidyup` block ~`:264`, handlers after the `tidyup` handler ~`:466`)
- Modify: `src/sdlc/worker.py:65` (import) and `:96-97` (`workflows=[...]`)
- Test: `tests/test_assessment_cli_wiring.py`

**Interfaces:**
- Consumes: `AssessmentInput`, `AssessmentWorkflow` from Task 3.
- Produces: `assess_workflow_id(repo: str, now: datetime | None = None) -> str` in `sdlc.cli`, returning `assess-<slug>-<YYYYmmddTHHMMSSZ>`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_assessment_cli_wiring.py`:

```python
"""E-45's operator surface. Mirrors tests/test_tidyup_cli_wiring.py."""

from datetime import datetime, timezone

import pytest

from sdlc.cli import assess_workflow_id, build_parser


def test_workflow_id_is_per_run_not_per_repository():
    """Same reason triage_workflow_id carries a stamp (E-42 D5): Temporal
    refuses to start a workflow whose id is already RUNNING, so a bare
    assess-<slug> would let one assessment parked on the child's readiness
    gate block the next."""
    now = datetime(2026, 8, 10, 10, 15, 0, tzinfo=timezone.utc)
    assert assess_workflow_id("/x/my-repo", now) == "assess-my-repo-20260810T101500Z"


def test_workflow_id_slugifies_the_basename():
    now = datetime(2026, 8, 10, 10, 15, 0, tzinfo=timezone.utc)
    assert assess_workflow_id("/x/My Repo!", now).startswith("assess-my-repo-")


def test_two_ids_for_one_repo_differ():
    a = assess_workflow_id("/x/r", datetime(2026, 8, 10, 10, 15, 0, tzinfo=timezone.utc))
    b = assess_workflow_id("/x/r", datetime(2026, 8, 10, 10, 16, 0, tzinfo=timezone.utc))
    assert a != b


def test_child_triage_id_does_not_collide_with_a_standalone_triage():
    """AssessmentWorkflow derives its child as <id>-triage."""
    now = datetime(2026, 8, 10, 10, 15, 0, tzinfo=timezone.utc)
    assert not assess_workflow_id("/x/r", now).startswith("triage-")


def test_worker_registers_the_workflow():
    import inspect

    from sdlc import worker

    assert "AssessmentWorkflow" in inspect.getsource(worker)


@pytest.mark.parametrize(
    "argv,expected",
    [
        (
            ["assess", "--repo", "/x/r"],
            {"repo": "/x/r", "commit": "HEAD", "no_build_probe": False, "advisory_source": "none"},
        ),
        (
            ["assess", "--repo", "/x/r", "--no-build-probe"],
            {"repo": "/x/r", "no_build_probe": True},
        ),
        (["assess", "--repo", "/x/r", "--commit", "abc123"], {"repo": "/x/r", "commit": "abc123"}),
        (["assess", "--repo", "/x/r", "--advisory-source", "osv"], {"advisory_source": "osv"}),
    ],
)
def test_parser_accepts_the_assess_flags(argv, expected):
    args = build_parser().parse_args(argv)
    assert args.cmd == "assess"
    for key, value in expected.items():
        assert getattr(args, key) == value


def test_parser_accepts_assess_show():
    args = build_parser().parse_args(["assess", "show", "--id", "assess-r-x"])
    assert args.cmd == "assess"
    assert args.assess_cmd == "show"
    assert args.id == "assess-r-x"


def test_bare_assess_has_no_subcommand():
    args = build_parser().parse_args(["assess", "--repo", "/x/r"])
    assert args.assess_cmd is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_assessment_cli_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name 'assess_workflow_id' from 'sdlc.cli'`

- [ ] **Step 3: Add the id helper and imports to `src/sdlc/cli.py`**

Add to the workflow imports block (beside `from .workflows.triage import ...`):

```python
from .workflows.assessment import AssessmentInput, AssessmentWorkflow
```

Add after `tidyup_workflow_id`:

```python
def assess_workflow_id(repo: str, now: datetime | None = None) -> str:
    """A distinct id per assessment RUN, for the same reason
    triage_workflow_id carries a stamp (E-42 D5): Temporal refuses to start a
    workflow whose id is already RUNNING, so a bare `assess-<slug>` would let
    one assessment parked on its child's readiness gate (HARD by default,
    48h) block the next assessment of that repository."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"assess-{slug(os.path.basename(repo))}-{stamp}"
```

- [ ] **Step 4: Add the parser block**

In `build_parser()`, after the `tidyup` block (immediately before `return p`):

```python
asr = sub.add_parser("assess")
asrsub = asr.add_subparsers(dest="assess_cmd")
asr.add_argument("--repo", help="path to an already-cloned repository")
asr.add_argument("--commit", default="HEAD")
asr.add_argument(
    "--no-build-probe",
    action="store_true",
    dest="no_build_probe",
    help="skip the one signal that executes the repo's own "
    "code; readiness becomes INDETERMINATE, so "
    "admission then requires a human override",
)
asr.add_argument(
    "--advisory-source",
    default="none",
    help="'osv' enables a declared outbound vulnerability lookup; default collects nothing",
)
ash = asrsub.add_parser("show")
ash.add_argument("--id", required=True)
```

Also extend the usage docstring at the top of `cli.py` (beside the `tidyup` lines):

```
  python -m sdlc.cli assess --repo /path/to/repo [--commit HEAD]
  python -m sdlc.cli assess show --id assess-myrepo-20260810T101500Z
```

- [ ] **Step 5: Add the handlers**

In `main()`, after the `tidyup` start handler:

```python
if args.cmd == "assess" and args.assess_cmd == "show":
    handle = client.get_workflow_handle(args.id)
    # Query by METHOD, not by name -- see the triage show handler.
    report = await handle.query(AssessmentWorkflow.assessment)
    print("no assessment yet" if report is None else report.model_dump_json(indent=2))
    return

if args.cmd == "assess":
    if not args.repo:
        raise SystemExit("assess requires --repo")
    repo = os.path.abspath(args.repo)
    wf_id = assess_workflow_id(repo)
    handle = await client.start_workflow(
        AssessmentWorkflow.run,
        AssessmentInput(
            repo_dir=repo,
            commit=args.commit,
            build_probe=not args.no_build_probe,
            advisory_source=args.advisory_source,
        ),
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    print(f"started {handle.id}")
    # The FR-903 gate opens on the CHILD, so the operator needs the
    # child's id -- `sdlc approve --id <parent>` reaches nothing.
    print(
        f"NOTE: the readiness gate opens on {wf_id}-triage; approve "
        f"with: sdlc approve --id {wf_id}-triage --gate readiness"
    )
    print(
        "NOTE: the build probe executes this repository's own code as "
        "the worker user. Operator-run only (NFR-9)."
    )
    return
```

- [ ] **Step 6: Register the workflow in `src/sdlc/worker.py`**

Add beside the other workflow imports:

```python
from .workflows.assessment import AssessmentWorkflow
```

and add `AssessmentWorkflow` to the `workflows=[...]` list:

```python
workflows = (
    [
        FeatureWorkflow,
        BenchmarkWorkflow,
        ReflectWorkflow,
        DeploymentWorkflow,
        TriageWorkflow,
        TidyUpWorkflow,
        AssessmentWorkflow,
    ],
)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_assessment_cli_wiring.py tests/test_tidyup_cli_wiring.py tests/test_triage_cli_wiring.py -v`
Expected: PASS (the neighbouring wiring suites prove the parser change broke nothing)

- [ ] **Step 8: Lint and commit**

```bash
python -m ruff check src/sdlc/cli.py src/sdlc/worker.py
git add src/sdlc/cli.py src/sdlc/worker.py tests/test_assessment_cli_wiring.py
git commit -m "feat(cli): sdlc assess / assess show, worker registration (E-45)"
```

---

### Task 5: Temporal end-to-end

**Files:**
- Create: `tests/test_assessment_workflow_e2e.py`

**Interfaces:**
- Consumes: `AssessmentInput`, `AssessmentWorkflow` (Task 3); `TriageWorkflow` and the triage activity input types; `GateDecision`/`GateOutcome`/`GatePolicy`/`GateSettings` from `sdlc.models`.
- Produces: nothing imported elsewhere.

**Note for the implementer:** the fake activities are the same ones `tests/test_triage_workflow_e2e.py:34-80` defines. They are repeated here in full rather than imported, because importing test fixtures across test modules is not this suite's pattern. `notify` is deliberately **not** registered: `GateHost._notify` uses a 5-second `schedule_to_start_timeout` and swallows the failure into `_on_notified`, which is why `test_triage_workflow_e2e.py` runs without it today.

- [ ] **Step 1: Write the failing test**

Create `tests/test_assessment_workflow_e2e.py`:

```python
"""E-45 end to end. Two workflows, no fan-out -- materially lighter than the
TidyUpWorkflow e2e P5 deferred for host contention.

Scenario (a) is the load-bearing one: it is the FUTURE-CONSUMER TRAP
workflows/tidyup.py:87-97 documents, executed end to end.
"""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.assessment.models import (
    BLOCKED,
    NO_PHASES,
    PHASE_ORDER,
    PhaseId,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.models import (
    GateDecision,
    GateOutcome,
    GatePolicy,
    GateSettings,
)
from sdlc.triage.activities import (
    TriageDependencyInput,
    TriagePin,
    TriagePinInput,
    TriageProbeInput,
    TriageSignalInput,
)
from sdlc.triage.models import SignalResult, Verdict
from sdlc.workflows.assessment import AssessmentInput, AssessmentWorkflow
from sdlc.workflows.triage import TriageWorkflow

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "assess-test"


def _ok(signal: str, version: int, metrics=None) -> SignalResult:
    return SignalResult(
        signal=signal, version=version, collected=Measurement.measured(0.0), metrics=metrics or {}
    )


@activity.defn(name="triage_resolve_commit")
async def fake_pin(inp: TriagePinInput) -> TriagePin:
    return TriagePin(commit_sha="a" * 40, toolchain="python")


@activity.defn(name="triage_baseline")
async def fake_baseline(inp: TriageSignalInput) -> SignalResult:
    return _ok("baseline", 2, {"tests_present": Measurement.measured(3.0)})


@activity.defn(name="triage_scaffold")
async def fake_scaffold(inp: TriageSignalInput) -> SignalResult:
    return _ok("scaffold", 1, {"structure_discernible": Measurement.measured(1.0)})


@activity.defn(name="triage_build_probe")
async def fake_probe(inp: TriageProbeInput) -> SignalResult:
    return _ok(
        "build_probe",
        1,
        {"buildable": Measurement.measured(1.0), "runnable": Measurement.measured(1.0)},
    )


@activity.defn(name="triage_secrets")
async def fake_secrets(inp: TriageSignalInput) -> SignalResult:
    return _ok("secrets", 2)


@activity.defn(name="triage_misconfig")
async def fake_misconfig(inp: TriageSignalInput) -> SignalResult:
    return _ok("misconfig", 1)


@activity.defn(name="triage_outliers")
async def fake_outliers(inp: TriageSignalInput) -> SignalResult:
    return _ok("outliers", 1)


@activity.defn(name="triage_dependencies")
async def fake_deps(inp: TriageDependencyInput) -> SignalResult:
    return _ok("dependencies", 1)


ACTIVITIES = [
    fake_pin,
    fake_baseline,
    fake_scaffold,
    fake_probe,
    fake_secrets,
    fake_misconfig,
    fake_outliers,
    fake_deps,
]
WORKFLOWS = [AssessmentWorkflow, TriageWorkflow]


async def _await_child_gate(env, child_id):
    """Poll the child until its readiness gate is pending. The child may not
    have started yet, so a query failure is a retry, not an error."""
    while True:
        try:
            items = await env.client.get_workflow_handle(child_id).query(
                TriageWorkflow.pending_decisions
            )
            if items:
                return items
        except Exception:  # noqa: BLE001 -- not started
            pass
        await env.sleep(1)


async def test_a_policy_approved_tree_is_refused():
    """Scenario (a). --no-build-probe forces INDETERMINATE by construction,
    and gates OFF makes the child auto-approve its own readiness gate with
    decided_by='policy'. E-42's rule would admit this; Tier 2 must not."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES
        ):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir="/r",
                    build_probe=False,
                    gates=GateSettings(default_gate_policy=GatePolicy.OFF),
                ),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()

    assert result.admitted is False
    assert result.terminal_status == BLOCKED
    assert result.triage.readiness.verdict is Verdict.INDETERMINATE
    assert result.triage.override is not None
    assert result.triage.override.approved_by == "policy"
    assert "policy" in result.admission_reason
    # Not admitted is not empty-handed (E-44 D7): the caller still gets the
    # verdict and every hygiene finding.
    assert result.commit_sha == "a" * 40
    assert [p.phase for p in result.phases] == list(PHASE_ORDER)
    for p in result.phases:
        if p.phase is PhaseId.INIT:
            continue
        assert p.collected.state is CollectionState.NOT_COLLECTED
        assert "not admitted" in p.collected.reason


async def test_a_human_override_admits_the_same_tree():
    """Scenario (b). Identical tree, decided by a human on the CHILD's gate."""
    wf_id = f"assess-{uuid.uuid4()}"
    child_id = f"{wf_id}-triage"  # _init derives it exactly this way
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES
        ):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r", build_probe=False),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )

            items = await _await_child_gate(env, child_id)
            assert items[0].gate == "readiness"

            await env.client.get_workflow_handle(child_id).signal(
                TriageWorkflow.submit_gate_decision,
                GateDecision(
                    gate="readiness",
                    round=1,
                    outcome=GateOutcome.APPROVE,
                    decided_by="human",
                    reviewer="alice",
                    comments="scope understood",
                ),
            )
            result = await handle.result()

    assert result.admitted is True
    assert result.triage.override.approved_by == "human"
    assert result.terminal_status == NO_PHASES
    assert [p.phase for p in result.phases] == list(PHASE_ORDER)
    # Every phase body is a later item, and the artifact says which.
    assert "E-46" in result.phases[1].collected.reason
    assert result.phases[1].phase is PhaseId.SCAN


async def test_a_ready_repo_is_admitted_with_no_gate():
    """The happy path: the build probe reports a buildable repo, the child
    opens no gate at all, and the shell runs the whole DAG."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES
        ):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r"),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()

    assert result.triage.readiness.verdict is Verdict.READY
    assert result.triage.override is None
    assert result.admitted is True
    assert result.admission_reason == "verdict ready"
    assert result.terminal_status == NO_PHASES
    assert result.toolchain == "python"


async def test_the_assessment_query_serves_the_artifact():
    """FR-911: phase state lives in workflow history -- the result plus this
    query ARE the record, and no workflow.json is written."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES
        ):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r"),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.result()
            served = await handle.query(AssessmentWorkflow.assessment)
            status = await handle.query(AssessmentWorkflow.status)

    assert served is not None
    assert served.commit_sha == "a" * 40
    assert status == NO_PHASES
```

- [ ] **Step 2: Run the e2e suite**

Run: `python -m pytest tests/test_assessment_workflow_e2e.py -v -m temporal`
Expected: PASS (4 tests). First run downloads the Temporal test server if it is not cached — allow several minutes.

- [ ] **Step 3: If a test hangs on the child gate**

Confirm the child id matches `f"{workflow.info().workflow_id}-triage"` in `_init`, and that both workflows are registered on the same task queue. Do **not** add `notify` to `activities` — its absence is expected and swallowed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_assessment_workflow_e2e.py
git commit -m "test(assessment): temporal e2e -- policy refused, human admitted (E-45)"
```

---

### Task 6: Roadmap, and the three stale comments this closes

**Files:**
- Modify: `ROADMAP.md` (§0 P6 line ~`:102`, §2 FR-911 ~`:211`, §2 FR-903 ~`:206`, §11 E-45 ~`:901-916`, header `Last verified` ~`:6`)
- Modify: `src/sdlc/workflows/tidyup.py:87-97` (the `FUTURE-CONSUMER TRAP` comment)
- Modify: `src/sdlc/workflows/triage.py:104-109` (`override_from`'s docstring)
- Test: none new — this task is documentation and comment truth

- [ ] **Step 1: Correct the `FUTURE-CONSUMER TRAP` comment in `workflows/tidyup.py`**

Replace the trap paragraph on `TidyUpReport.after` with the closed-out version:

```python
    # The after-triage measures, it does not gate, so triage_gates(...,
    # gating=False) auto-approves its readiness gate. When the verify tree is
    # not READY, RepoTriage.override is therefore set with approved_by ==
    # "policy" -- a machine placeholder, not a human act. Harmless to
    # compute_delta (it reads signals, not the override) and to the report
    # (readiness_after is the computed verdict).
    #
    # CLOSED by E-45: Tier 2's admission rule is
    # admits(..., require_human=True), which refuses a "policy" or "timeout"
    # approval, so applying it to THIS field can no longer admit a tree
    # nobody approved. Keep approved_by legible for the same reason.
```

- [ ] **Step 2: Correct `override_from`'s note in `workflows/triage.py`**

Change the trailing sentence of its docstring from *"E-45 may narrow its admission rule to human approvals"* to a statement of fact:

```python
    """FR-903. Every APPROVE records an override -- one rule, no special
    cases -- with approved_by carrying decided_by VERBATIM, so "policy"
    (gate OFF) and "timeout" (on_timeout=APPROVE) stay legible as non-human.
    E-45's Tier 2 admission rule (triage/admission.py, require_human=True)
    refuses both; what this refuses to do is discard the distinction."""
```

- [ ] **Step 3: Update `ROADMAP.md` §11's E-45 entry**

Replace the `- [ ] **E-45 — ...**` bullet (keeping its two deviations and the `/enrich`/`/gate`/`/validate` note) with the landed version:

```markdown
- [x] **E-45 — `AssessmentWorkflow` EDCR DAG shell** → FR-911. *Landed
  2026-08-10.* init → scan → discover → assess → **report** → generate →
  finish, with six phase bodies deliberately unbuilt (scan E-46, discover
  E-48, assess E-49, finish E-51, report/generate E-52), each reporting
  `not_collected` naming the item that owes it. Two deliberate deviations
  from the source methodology: **(a)** `report` runs *after* `assess` —
  reports render risk scores only `assess` produces; **(b)** `workflow.json`
  is **not ported** — its `phases[].status/started_at/completed_at` is a
  hand-rolled durable state machine, which is what Temporal history already
  is. `/enrich`, `/gate` and `/validate` are not stages (→ E-56, E-50, E-53).
  Three sub-decisions the one-line description did not contain:
  **(D2)** the **admission rule is one function at two strictnesses** —
  `triage/admission.py:admits(triage, *, require_human)`, with Tier 0's
  `backlog.admitted` delegating at `False` and Tier 2 passing `True`. This
  closes the `FUTURE-CONSUMER TRAP` `workflows/tidyup.py` documented: the
  after-triage auto-approves its own OFF gate, so
  `TidyUpReport.after.override.approved_by == "policy"`, and E-42's broader
  rule would have admitted a tree nobody approved. Two copies of the rule
  would agree only by coincidence, so the strictness is a parameter.
  **(D3)** `init` runs a **`TriageWorkflow` child** and never accepts a
  `RepoTriage` as input — the rule's whole subject is `override.approved_by`,
  and a caller-supplied artifact is a caller-supplied value for exactly that
  field. **(D6)** `terminal_status` is **derived**, so E-46 landing flips
  `admitted:no-phases-implemented` → `assessed:partial` with no workflow
  edit. Spec
  `docs/superpowers/specs/2026-08-10-assessment-workflow-edcr-shell-design.md`,
  plan `docs/superpowers/plans/2026-08-10-assessment-workflow-edcr-shell.md`.
```

- [ ] **Step 4: Update the §2 requirement lines**

FR-911 (`:211`) becomes partial rather than unstarted:

```markdown
- [ ] ⚠️ **FR-911** `AssessmentWorkflow` EDCR DAG, report-after-assess, no
  phase-status file (E-45) — **the DAG and both deviations landed 2026-08-10**;
  six of seven phase bodies are stubs reporting `not_collected` with the E-item
  that owes them, so an assessment that assessed nothing says so (FR-915).
  `/enrich` as a declared stage input remains E-56.
```

Append to FR-903 (`:206`), after the existing sentence about E-45's admission rule:

```markdown
  *2026-08-10 (E-45):* the rule is now one function at two strictnesses
  (`triage/admission.py`). Tier 2 requires `approved_by == "human"`, so a
  `policy` (gate OFF) or `timeout` approval no longer admits an audit; Tier 0
  keeps the broader rule for the build-economics reason `backlog.admitted`
  documents.
```

- [ ] **Step 5: Update §0's P6 line**

```markdown
- [ ] ⚠️ **P6** — Capability & risk audit (Tier 2) + evidence bundle → *one repository audited end-to-end with SC-7 held and a bundle handed over*
  **Opened 2026-08-10** with E-45's DAG shell; every phase body remains unbuilt (§11, E-46…E-56). Gated on P5's readiness verdict (FR-903), not merely sequenced after it — and the gate now requires a **human** approval to admit a tree that is not READY.
```

- [ ] **Step 6: Update the header's `Last verified` line**

Prepend to the parenthetical in `ROADMAP.md:6`:

```
2026-08-10 (E-45 against `src/sdlc/{assessment,workflows/assessment.py,triage/admission.py}` + unit/e2e tests green);
```

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS, with no new failures relative to the pre-task baseline. Then:
Run: `python -m pytest tests/ -q -m temporal`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add ROADMAP.md src/sdlc/workflows/tidyup.py src/sdlc/workflows/triage.py
git commit -m "docs: E-45 lands -- FR-911 shell, FR-903 narrowed to human approvals"
```

---

## Verification checklist

Before claiming the work complete, run and paste the output of:

```bash
python -m pytest tests/test_assessment_admission.py tests/test_assessment_models.py \
                 tests/test_assessment_workflow.py tests/test_assessment_cli_wiring.py -v
python -m pytest tests/test_assessment_workflow_e2e.py -v -m temporal
python -m pytest tests/ -q
python -m ruff check src/sdlc/
```

All four must pass. `tests/test_tidyup_backlog.py` passing is the specific evidence that Task 1's delegation preserved Tier 0's behaviour.
