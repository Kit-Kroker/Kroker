# E4 — Plan Drift Review Condition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `PlanDrift` — a deterministic per-task signal that is computed every code-stage run and currently read by nothing — into a fourth `CheckClass.ADVISORY` check at the merge gate, so drift a human never acknowledged blocks merge until they leave an audited reason.

**Architecture:** `TaskResult` gains a `plan_drift` field, populated once (reusing the existing `compute_plan_drift` call) at both places `code/step.py` returns a `TaskResult`. The merge stage aggregates `plan_drift` across all tasks with an "any task fires" rule, using a per-task threshold predicate, and adds one more `build_check(...)` entry to its existing checks list — the same list `review_severity`/`traceability`/`coverage` already live in. The new check joins `MERGE_REQUIRED_CHECKS` so C3's fail-closed synthesis covers it, and is waivable through the existing audited `GateOverride` mechanism with no new machinery.

**Tech Stack:** Python 3, Pydantic v2, pytest, pytest-asyncio. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-09-e4-plan-drift-review-condition-design.md`

## Global Constraints

- Do not mutate `DevTask.files_hint` anywhere in this plan.
- Do not introduce a new artifact type (e.g. `PlanAmendment`) or a structured `GateOverride.reason` schema. The amendment is the existing free-text `gate.comments`, applied uniformly to every advisory-blocking check exactly as it is today.
- Only `touched_unhinted` (unhinted touches) drives the threshold. `hinted_untouched` (over-hinting) is never used.
- Single-file tasks (`files_touched <= 1`) never flag, regardless of `touched_unhinted`.
- `plan_drift is None` (unmeasured — empty `files_hint` or empty diff) means the task contributes nothing to the aggregate; it is never a failure.
- Aggregation across tasks is "any task fires" — never averaged, never a majority vote.
- `results_list` in the merge stage is not filtered by `status`; a quarantined task's drift still counts, matching the existing `review_severity`/`untraced` precedent of reading all results unconditionally. Do not add a status filter.
- No attribution trailers in any commit. Commit via `git commit -F <msgfile>`, one path per `git add` argument, no heredocs.

---

## File Map

- Modify `src/sdlc/workflows/models.py` — add `plan_drift: PlanDrift | None` to `TaskResult`.
- Modify `src/sdlc/stages/code/step.py` — compute `plan_drift` once per attempt, populate both `TaskResult` return sites.
- Modify `src/sdlc/stages/merge/step.py` — Task 3 adds `_plan_drift_flags` (per-task predicate) and `_plan_drift_check` (aggregation + `CheckResult` builder); Task 4 wires the latter into the real checks list (one line).
- Modify `src/sdlc/gate.py` — Task 3 adds `"plan_drift": CheckClass.ADVISORY` to `MERGE_REQUIRED_CHECKS`, landed in the same commit as the helpers because the manifest-census test walks the whole file, not just the live checks list (see Task 3's "why the manifest edit lands here" note).
- Modify `src/sdlc/stages/merge/merge.md` — document the new check (MERGE-1.7) and update MERGE-1.3's advisory-check list and the failure-modes bullet.
- Modify `tests/conftest.py` — cosmetic, in Task 3: `required_checks` docstring says "seven passing checks"; it becomes eight once the manifest grows.
- Create `tests/test_task_result_plan_drift.py` — `TaskResult.plan_drift` field test.
- Modify `tests/code/test_code_slice_contract.py` — two new tests: `plan_drift` populated on the done path and on the quarantine path.
- Create `tests/merge/test_plan_drift_gate.py` — Task 3: predicate boundary tests, aggregation tests, manifest membership, waiver round-trip (all testable against `_plan_drift_check` directly, before the real checks list is wired). Task 4 appends one source-needle test pinning that the real checks list actually calls it.

---

### Task 1: `TaskResult` carries `PlanDrift`

**Files:**
- Modify: `src/sdlc/workflows/models.py:17` (import), `src/sdlc/workflows/models.py:52-62` (`TaskResult` class)
- Test: `tests/test_task_result_plan_drift.py` (new)

**Interfaces:**
- Consumes: `PlanDrift` from `src/sdlc/stages/plan/models.py` (existing — `files_hinted: int`, `files_touched: int`, `hinted_untouched: list[str]`, `touched_unhinted: list[str]`).
- Produces: `TaskResult.plan_drift: PlanDrift | None`, default `None` — read by Task 4's merge-gate aggregation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_task_result_plan_drift.py`:

```python
"""E4: TaskResult carries the plan-drift signal through to the merge gate."""

from sdlc.stages.plan.models import PlanDrift
from sdlc.workflows.models import TaskResult


def test_task_result_defaults_plan_drift_to_none():
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert tr.plan_drift is None


def test_task_result_accepts_a_plan_drift():
    drift = PlanDrift(
        files_hinted=2,
        files_touched=2,
        hinted_untouched=["b.py"],
        touched_unhinted=["c.py"],
    )
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b", plan_drift=drift)
    assert tr.plan_drift is drift
    assert tr.plan_drift.touched_unhinted == ["c.py"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_task_result_plan_drift.py -v`
Expected: FAIL — `TaskResult` has no `plan_drift` field. `TaskResult` does not set `model_config = ConfigDict(extra="forbid")`, so Pydantic v2's default `extra="ignore"` behavior applies: passing `plan_drift=...` to the constructor is silently accepted and dropped, not raised as a `ValidationError`. Both tests fail the same way, at the attribute access: `AttributeError: 'TaskResult' object has no attribute 'plan_drift'`.

- [ ] **Step 3: Add the field**

In `src/sdlc/workflows/models.py`, change the import at line 17 from:

```python
from ..stages.plan.models import ImplementationPlan
```

to:

```python
from ..stages.plan.models import ImplementationPlan, PlanDrift
```

Then in the `TaskResult` class (currently lines 52-62), add the new field after `deep_review`:

```python
class TaskResult(BaseModel):
    task_id: str
    status: Literal["done", "failed", "quarantined"]
    attempts: int
    branch: str
    run: HarnessRunResult | None = None
    handoff: HandoffSummary | None = None  # FR-805
    qa: QAReport | None = None  # NEW: evidence for the merge gate
    review: ReviewReport | None = None  # FR-204: clean-context review evidence
    deep_review: DeepReviewReport | None = None  # E-39: advisory lens
    plan_drift: PlanDrift | None = None  # E4: drift evidence for the merge gate
    notes: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_task_result_plan_drift.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/models.py tests/test_task_result_plan_drift.py
git commit -F <msgfile>
```

Message body (write to a temp file, no attribution trailer):
```
feat(workflows): add plan_drift field to TaskResult

Carries the existing PlanDrift signal from the code stage through to
the merge gate so it can become a review condition (E4).
```

---

### Task 2: `code/step.py` computes drift once and populates both `TaskResult` returns

**Files:**
- Modify: `src/sdlc/stages/code/step.py:769` (compute once, store in a variable), `:826` (done-path `TaskResult`), `:897` (quarantine-path `TaskResult`)
- Test: `tests/code/test_code_slice_contract.py` (add two tests)

**Interfaces:**
- Consumes: `compute_plan_drift(task: DevTask, files_touched: list[str]) -> PlanDrift | None` (existing, `src/sdlc/stages/plan/models.py:51`, already imported in this file at line 48). `TaskResult.plan_drift` (Task 1).
- Produces: every `TaskResult` returned by `code.step` now carries `plan_drift` populated from the same diff used for the benchmark record — no double computation.

**Context for the implementer:** `code/step.py`'s `step()` function runs a `while True:` fix-loop. Each iteration computes a `diff` dict (with a `"files"` key), builds `task_passed`, then records a benchmark stage record that already calls `compute_plan_drift(task, diff.get("files", []))` inline (this call is not stored anywhere — it is discarded after the `stage_record(...)` call returns). Two `return TaskResult(...)` statements exist further down in the same loop iteration: one on the "done" path, one on the "quarantined after budget exhaustion" path (reached via `continue` back to the top of the loop on interim rejections, so both statements execute with the current iteration's `diff` and `task` in scope).

- [ ] **Step 1: Write the failing tests**

Open `tests/code/test_code_slice_contract.py`. Add these two tests after `test_code_step_executes_and_returns_task_result` (after line 168, before the `test_code_step_records_benchmark_records` function). They reuse the exact fixture/mocking pattern already in that file.

```python
@pytest.mark.clause("CODE-1.3")
@pytest.mark.asyncio
async def test_code_step_populates_plan_drift_on_done_path():
    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = DevTask(
        id="task-drift",
        title="Implement feature",
        description="Write code",
        role="dev",
        acceptance_criteria=["Tests pass"],
        files_hint=["app.py", "unused_hint.py"],
    )
    contract = ValidationContract(task_id="task-drift", assertions=["Tests pass"])

    run_result = HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=0,
        commit_sha="c1",
        cost_usd=0.5,
        summary="success",
    )
    qa_report = QAReport(tests_passed=True, issues=[])
    review_report = ReviewReport(approve=True, issues=[])
    deep_review = DeepReviewReport(verdict="LGTM", passed=True)
    handoff = HandoffSummary(
        task_id="task-drift",
        files_touched=["app.py"],
        what_changed=[HandoffClaim(text="done", evidence="session")],
    )

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = run_result
        mock_qa.return_value = qa_report
        mock_rev.return_value = review_report
        mock_deep.return_value = deep_review
        mock_ho.return_value = handoff
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),  # qa_raw
            {"files": ["app.py", "extra_unhinted.py"]},  # diff
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=contract,
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
        )

    assert tr.status == "done"
    assert tr.plan_drift is not None
    assert tr.plan_drift.touched_unhinted == ["extra_unhinted.py"]
    assert tr.plan_drift.hinted_untouched == ["unused_hint.py"]


@pytest.mark.clause("CODE-1.5")
@pytest.mark.asyncio
async def test_code_step_populates_plan_drift_on_quarantine_path():
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(gate="task:task-drift-q", outcome=GateOutcome.REJECT, decided_by="human")
        ]
    )
    cfg = PipelineConfig(max_fix_attempts=1)
    task = DevTask(
        id="task-drift-q",
        title="Buggy task",
        description="Fails",
        role="dev",
        acceptance_criteria=["works"],
        files_hint=["buggy.py"],
    )

    run_result = HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=1,
        commit_sha="c3",
        cost_usd=0.1,
        summary="failed",
    )
    qa_failing = QAReport(tests_passed=False, issues=["tests failed"])
    review_report = ReviewReport(approve=False, issues=["tests red"])

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = run_result
        mock_qa.return_value = qa_failing
        mock_rev.return_value = review_report
        mock_deep.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=False, issues=["failure"]),
            {"files": ["buggy.py"]},
            QAReport(tests_passed=False, issues=["failure"]),
            {"files": ["buggy.py", "other_unhinted.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            worktree="/worktree",
            notes=[],
            dev_agent=None,
            crew_layout=None,
            branch="buggy-branch",
        )

    assert tr.status == "quarantined"
    assert tr.plan_drift is not None
    assert tr.plan_drift.touched_unhinted == ["other_unhinted.py"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/code/test_code_slice_contract.py -k plan_drift -v`
Expected: FAIL — both assert `tr.plan_drift is not None` and currently `TaskResult(...)` is constructed without a `plan_drift` argument, so it defaults to `None` (Task 1 already landed the field; this task hasn't wired it yet).

- [ ] **Step 3: Compute once, populate both return sites**

In `src/sdlc/stages/code/step.py`, change line 769 from:

```python
                plan_drift=compute_plan_drift(task, diff.get("files", [])),
```

to reuse a variable computed just before the `stage_record(...)` call. Locate the block currently at lines 750-774:

```python
        task_passed = bool(qa_raw.tests_passed and not qa.issues and not drift.found)

        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="code",
                role=task.role,
                started=_attempt_started,
                ended=_now(),
                quality_score=(1.0 if task_passed else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS if task_passed else BenchmarkOutcome.FAIL),
                model=role_cfg.model or "",
                harness=role_cfg.harness,
                lead_harness=role_cfg.lead_harness,
                cost_usd=run.cost_usd,
                spend=code_spend,
                waste=WasteBag.from_digest(run.session_digest),
                plan_drift=compute_plan_drift(task, diff.get("files", [])),
                fix_attempts=attempt - 1,
                task_id=task.id,
                attempt=attempt - 1,
            ),
        )
```

Replace it with:

```python
        task_passed = bool(qa_raw.tests_passed and not qa.issues and not drift.found)
        plan_drift = compute_plan_drift(task, diff.get("files", []))

        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="code",
                role=task.role,
                started=_attempt_started,
                ended=_now(),
                quality_score=(1.0 if task_passed else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS if task_passed else BenchmarkOutcome.FAIL),
                model=role_cfg.model or "",
                harness=role_cfg.harness,
                lead_harness=role_cfg.lead_harness,
                cost_usd=run.cost_usd,
                spend=code_spend,
                waste=WasteBag.from_digest(run.session_digest),
                plan_drift=plan_drift,
                fix_attempts=attempt - 1,
                task_id=task.id,
                attempt=attempt - 1,
            ),
        )
```

Next, in the done-path `return TaskResult(...)` (currently lines 826-836):

```python
                return TaskResult(
                    task_id=task.id,
                    status="done",
                    attempts=attempt,
                    branch=branch,
                    run=run,
                    handoff=handoff,
                    qa=qa_raw,
                    review=review,
                    deep_review=deep,
                )
```

add `plan_drift=plan_drift,`:

```python
                return TaskResult(
                    task_id=task.id,
                    status="done",
                    attempts=attempt,
                    branch=branch,
                    run=run,
                    handoff=handoff,
                    qa=qa_raw,
                    review=review,
                    deep_review=deep,
                    plan_drift=plan_drift,
                )
```

Finally, in the quarantine-path `return TaskResult(...)` (currently lines 897-906):

```python
            return TaskResult(
                task_id=task.id,
                status="done" if decision.approved else "quarantined",
                attempts=attempt,
                branch=branch,
                qa=qa_raw,
                review=review,
                deep_review=deep,
                notes=decision.comments or "",
            )
```

add `plan_drift=plan_drift,`:

```python
            return TaskResult(
                task_id=task.id,
                status="done" if decision.approved else "quarantined",
                attempts=attempt,
                branch=branch,
                qa=qa_raw,
                review=review,
                deep_review=deep,
                notes=decision.comments or "",
                plan_drift=plan_drift,
            )
```

`plan_drift` is a loop-local variable recomputed every iteration (it is defined right before the block that both return statements sit inside, within the same `while True:` iteration), so both return sites always see the current attempt's drift, never a stale one from an earlier attempt.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/code/test_code_slice_contract.py -v`
Expected: PASS (all tests in the file, including the two new ones and the five pre-existing ones)

- [ ] **Step 5: Run the full code-stage test suite to check for regressions**

Run: `pytest tests/code/ tests/test_fix_loop_freeze.py tests/test_thaw_plumbing.py -v`
Expected: PASS, no regressions

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/stages/code/step.py tests/code/test_code_slice_contract.py
git commit -F <msgfile>
```

Message body:
```
feat(code): populate TaskResult.plan_drift on both return paths

Reuses the drift already computed for the benchmark record instead of
discarding it, so the merge gate can read it (E4).
```

---

### Task 3: Merge-stage threshold predicate and check builder

**Files:**
- Modify: `src/sdlc/stages/merge/step.py` — add imports and two new helper functions (placed after `_merge_evidence_all_green`, currently ending at line 81, and before `_auto_decision_for`, currently starting at line 84)
- Modify: `src/sdlc/gate.py:86-96` (`MERGE_REQUIRED_CHECKS`)
- Modify: `tests/conftest.py` (docstring only, cosmetic)
- Test: `tests/merge/test_plan_drift_gate.py` (new)

**Interfaces:**
- Consumes: `PlanDrift` (`src/sdlc/stages/plan/models.py`), `TaskResult.plan_drift` (Task 1/2), `build_check`/`CheckClass`/`CheckResult` (`src/sdlc/gate.py`, already imported in this file).
- Produces: `_plan_drift_flags(drift: PlanDrift) -> bool` and `_plan_drift_check(results: list) -> CheckResult` — Task 4 wires `_plan_drift_check` into the merge gate's real `checks` list.

**Why the manifest edit lands here, not in Task 4:** `tests/test_required_checks_manifest.py::test_the_manifest_pins_the_checks_the_merge_step_builds` AST-walks the *entire* `merge/step.py` file for every `build_check(...)` call and asserts that name set equals `set(MERGE_REQUIRED_CHECKS)`. `_plan_drift_check`'s body contains a `build_check("plan_drift", ...)` call — the moment that function exists anywhere in the file, the AST census includes `"plan_drift"`, whether or not anything actually calls `_plan_drift_check` yet. If the manifest entry landed in a later commit, this commit would leave the census and the manifest out of sync and the test red. So the manifest entry and the helper functions must land together.

- [ ] **Step 1: Write the failing tests**

Create `tests/merge/test_plan_drift_gate.py`:

```python
"""E4: plan drift as a merge-gate advisory check.

Only touched_unhinted drives the threshold -- hinted_untouched (over-hinting)
is harmless and ignored. Single-file tasks never flag (no calibration signal
at n=1). Aggregation across tasks is "any task fires", never averaged.
"""

from sdlc.gate import CheckClass
from sdlc.stages.merge.step import _plan_drift_check, _plan_drift_flags
from sdlc.stages.plan.models import PlanDrift
from sdlc.workflows.models import TaskResult


def _drift(files_touched: int, touched_unhinted: list[str], hinted_untouched=None) -> PlanDrift:
    return PlanDrift(
        files_hinted=files_touched,
        files_touched=files_touched,
        hinted_untouched=hinted_untouched or [],
        touched_unhinted=touched_unhinted,
    )


def _result(task_id: str, drift: PlanDrift | None) -> TaskResult:
    return TaskResult(task_id=task_id, status="done", attempts=1, branch="b", plan_drift=drift)


# -- _plan_drift_flags: per-task predicate --


def test_single_file_task_never_flags():
    drift = _drift(files_touched=1, touched_unhinted=["a.py"])
    assert _plan_drift_flags(drift) is False


def test_two_unhinted_touches_flags():
    drift = _drift(files_touched=2, touched_unhinted=["a.py", "b.py"])
    assert _plan_drift_flags(drift) is True


def test_one_unhinted_of_three_does_not_flag():
    drift = _drift(files_touched=3, touched_unhinted=["a.py"])
    assert _plan_drift_flags(drift) is False


def test_zero_unhinted_never_flags():
    drift = _drift(files_touched=5, touched_unhinted=[])
    assert _plan_drift_flags(drift) is False


def test_ratio_boundary_half_flags_via_ratio_alone():
    # 1 of 2 touched files unhinted: count (1) is below the >=2 arm, so this
    # isolates the ratio arm -- ratio == 0.5, at the threshold, must still flag.
    drift = _drift(files_touched=2, touched_unhinted=["a.py"])
    assert _plan_drift_flags(drift) is True


def test_hinted_untouched_is_ignored():
    # Heavy over-hinting, zero unhinted touches: must not flag.
    drift = _drift(files_touched=2, touched_unhinted=[], hinted_untouched=["x.py", "y.py", "z.py"])
    assert _plan_drift_flags(drift) is False


# -- _plan_drift_check: run-level aggregation and CheckResult shape --


def test_all_clean_passes():
    # _drift(2, ["a.py"]) would itself flag (1/2 = 0.5 ratio) -- use 3-touched
    # tasks so both results genuinely stay under threshold (1/3 = 0.33).
    results = [_result("t1", _drift(3, [])), _result("t2", _drift(3, ["a.py"]))]
    check = _plan_drift_check(results)
    assert check.name == "plan_drift"
    assert check.passed is True
    assert check.classification is CheckClass.ADVISORY


def test_one_drifted_task_fails_the_whole_check():
    results = [
        _result("t1", _drift(3, [])),
        _result("t2", _drift(2, ["a.py", "b.py"])),  # flags
    ]
    check = _plan_drift_check(results)
    assert check.passed is False
    assert "t2" in check.detail


def test_many_tasks_each_below_threshold_pass_by_design():
    """The aggregation is per-task 'any fires', not a fleet-wide average or
    sum -- ten tasks that each individually stay under the threshold pass,
    because none of them individually crosses it. This is the accepted
    shape of the check, not a bug: §5 of the spec chose per-task predicate
    + any-fires aggregation over a fleet-wide accumulator."""
    results = [_result(f"t{i}", _drift(3, ["a.py"])) for i in range(10)]
    # Each task individually: 1 unhinted of 3 touched -> ratio 0.33, count 1 -> no flag.
    check = _plan_drift_check(results)
    assert check.passed is True


def test_one_task_over_threshold_fails_even_among_many_clean_ones():
    """The complementary case: aggregation is 'any fires', so one drifted
    task among many clean ones still fails the check -- confirms failure
    isn't diluted by fleet size either."""
    results = [_result(f"t{i}", _drift(3, ["a.py"])) for i in range(9)]
    results.append(_result("t9", _drift(2, ["x.py", "y.py"])))  # flags
    check = _plan_drift_check(results)
    assert check.passed is False
    assert "t9" in check.detail


def test_unmeasured_drift_does_not_fail_the_check():
    results = [_result("t1", None), _result("t2", None)]
    check = _plan_drift_check(results)
    assert check.passed is True
    assert "unmeasured" in check.detail or "no task" in check.detail


def test_quarantined_task_drift_still_counts():
    """merge/step.py reads results_list unconditionally; a quarantined task's
    drift must not be filtered out (matches the review_severity precedent)."""
    quarantined = TaskResult(
        task_id="t1",
        status="quarantined",
        attempts=3,
        branch="b",
        plan_drift=_drift(2, ["a.py", "b.py"]),
    )
    check = _plan_drift_check([quarantined])
    assert check.passed is False
    assert "t1" in check.detail


# -- manifest membership (C3's fail-closed synthesis must cover plan_drift) --


def test_plan_drift_is_a_required_advisory_check():
    from sdlc.gate import MERGE_REQUIRED_CHECKS

    assert MERGE_REQUIRED_CHECKS["plan_drift"] is CheckClass.ADVISORY


def test_plan_drift_absent_from_gate_input_synthesizes_a_failing_check():
    from sdlc.gate import evaluate_quality_gate

    report = evaluate_quality_gate([])
    blocked = {c.name for c in report.checks if not c.passed}
    assert "plan_drift" in blocked


# -- waiver round-trip: rides the existing audited GateOverride path --


def test_plan_drift_failure_is_waivable_by_an_audited_override():
    from sdlc.gate import GateOverride, evaluate_quality_gate

    drifted = _result("t1", _drift(2, ["a.py"]))  # ratio 0.5 -> flags
    checks = [_plan_drift_check([drifted])]
    report = evaluate_quality_gate(
        checks,
        overrides=[
            GateOverride(check="plan_drift", approved_by="human", reason="known refactor spillover")
        ],
    )
    assert report.passed is False  # other required checks are still absent and unwaived
    assert "plan_drift" in report.overridden
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/merge/test_plan_drift_gate.py -v`
Expected: FAIL with `ImportError: cannot import name '_plan_drift_check' from 'sdlc.stages.merge.step'` (neither helper exists yet; `MERGE_REQUIRED_CHECKS["plan_drift"]` also does not exist yet, `KeyError`)

- [ ] **Step 3: Add the two helper functions and the manifest entry, together**

In `src/sdlc/stages/merge/step.py`, add the import. Change the imports block (around line 40-41):

```python
from ..qa.activities import LintInput, SecurityScanInput, run_lint, security_scan
from ..qa.models import SecurityReport
```

to:

```python
from ..plan.models import PlanDrift
from ..qa.activities import LintInput, SecurityScanInput, run_lint, security_scan
from ..qa.models import SecurityReport
```

Then add the two new functions immediately after `_merge_evidence_all_green` (which currently ends at line 81) and before `_auto_decision_for` (which currently starts at line 84):

```python
def _plan_drift_flags(drift: PlanDrift) -> bool:
    """E4: per-task threshold. Only unhinted touches count -- hinted_untouched
    (over-hinting) is harmless and files_hint is explicitly a hint, not a
    gate (plan/models.py PlanDrift docstring). Single-file tasks are exempt:
    there is no calibration signal at n=1."""
    if drift.files_touched <= 1:
        return False
    unhinted = len(drift.touched_unhinted)
    return unhinted >= 2 or (unhinted / drift.files_touched) >= 0.5


def _plan_drift_check(results: list) -> CheckResult:
    """E4: run-level aggregation is 'any task fires', not an average or a
    fleet-wide accumulator -- one task past its own threshold fails the
    check regardless of how many other tasks are clean, and many tasks each
    individually under threshold pass (that is the accepted shape of a
    per-task predicate, not a gap). Unfiltered by status: a quarantined
    task's drift counts too, matching the existing review_severity/untraced
    precedent of reading all results."""
    drifted = [
        r.task_id for r in results if r.plan_drift is not None and _plan_drift_flags(r.plan_drift)
    ]
    return build_check(
        "plan_drift",
        not drifted,
        CheckClass.ADVISORY,
        detail=(
            f"{len(drifted)} task(s) touched unhinted files beyond threshold: {drifted[:10]}"
            if drifted
            else "no task exceeded the plan-drift threshold (or drift is unmeasured)"
        ),
    )
```

`CheckResult` must also be importable in this module for the return type annotation. Check the existing `from ...gate import (...)` block (currently lines 29-35):

```python
from ...gate import (
    CheckClass,
    GateOverride,
    GateReport,
    QualityGateInput,
    build_check,
)
```

Add `CheckResult`:

```python
from ...gate import (
    CheckClass,
    CheckResult,
    GateOverride,
    GateReport,
    QualityGateInput,
    build_check,
)
```

Now the manifest entry. In `src/sdlc/gate.py`, change `MERGE_REQUIRED_CHECKS` (currently lines 86-96) from:

```python
MERGE_REQUIRED_CHECKS: Final[Mapping[str, CheckClass]] = MappingProxyType(
    {
        "build_integration_green": CheckClass.ABSOLUTE,
        "lint_clean": CheckClass.ABSOLUTE,
        "security_scan_collected": CheckClass.ABSOLUTE,
        "security_no_critical": CheckClass.ABSOLUTE,
        "review_severity": CheckClass.ADVISORY,
        "traceability": CheckClass.ADVISORY,
        "coverage": CheckClass.ADVISORY,
    }
)
```

to:

```python
MERGE_REQUIRED_CHECKS: Final[Mapping[str, CheckClass]] = MappingProxyType(
    {
        "build_integration_green": CheckClass.ABSOLUTE,
        "lint_clean": CheckClass.ABSOLUTE,
        "security_scan_collected": CheckClass.ABSOLUTE,
        "security_no_critical": CheckClass.ABSOLUTE,
        "review_severity": CheckClass.ADVISORY,
        "traceability": CheckClass.ADVISORY,
        "coverage": CheckClass.ADVISORY,
        "plan_drift": CheckClass.ADVISORY,
    }
)
```

Finally, update the docstring in `tests/conftest.py`'s `required_checks` fixture (currently around lines 272-273):

```python
    """Build the full MERGE_REQUIRED_CHECKS list, every check passing.

    `required_checks()` -> seven passing checks.
    `required_checks(coverage=False)` -> the same seven with `coverage`
    failing at its manifest classification.
```

to:

```python
    """Build the full MERGE_REQUIRED_CHECKS list, every check passing.

    `required_checks()` -> eight passing checks.
    `required_checks(coverage=False)` -> the same eight with `coverage`
    failing at its manifest classification.
```

`required_checks()` itself needs no code change — it is built by iterating `MERGE_REQUIRED_CHECKS.items()`, so it grows to eight checks automatically once the manifest does.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/merge/test_plan_drift_gate.py tests/test_required_checks_manifest.py -v`
Expected: PASS — 15 passed in `test_plan_drift_gate.py` (6 predicate tests + 6 aggregation tests + 2 manifest tests + 1 waiver test), and every test in `test_required_checks_manifest.py` still passes, including `test_the_manifest_pins_the_checks_the_merge_step_builds`: the AST census of `build_check(...)` names in `merge/step.py` now includes `"plan_drift"` (from inside `_plan_drift_check`'s body, even though nothing calls it yet), and `MERGE_REQUIRED_CHECKS` was extended in the same commit, so the two sets match at eight names each.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/stages/merge/step.py src/sdlc/gate.py tests/conftest.py tests/merge/test_plan_drift_gate.py
git commit -F <msgfile>
```

Message body:
```
feat(merge): add plan-drift threshold predicate, check builder, and manifest entry

Per-task predicate flags unhinted touches only (>=2 files, or >=50%
of files touched), exempting single-file tasks. Aggregation across
tasks is "any task fires". Joins MERGE_REQUIRED_CHECKS in the same
commit as the build_check call, so the AST census test that pins the
manifest to the checks the merge step builds stays green -- the
function's body is enough to enter that census even before anything
calls it. Not yet wired into the real checks list (E4, next commit).
```

---

### Task 4: Wire `plan_drift` into the merge gate's real checks list

**Files:**
- Modify: `src/sdlc/stages/merge/step.py` (checks list, currently lines 262-314)
- Modify: `tests/merge/test_plan_drift_gate.py` (one source-needle test, appended)

**Interfaces:**
- Consumes: `_plan_drift_check` (Task 3, already present in this module), `results_list` (already built earlier in `merge.step`, currently line 194-198).
- Produces: the merge gate's real `checks` list — the one `evaluate_gate` actually receives at runtime — now includes the `plan_drift` entry. No new `build_check(...)` literal is added by this task (that already happened in Task 3, inside `_plan_drift_check`'s body), so this task adds no new name to the AST census `test_the_manifest_pins_the_checks_the_merge_step_builds` walks — the census and the manifest are already in sync from Task 3 and stay in sync here.

This task is pure wiring: one line, no new predicate logic, no new manifest entry. Its own correctness is already covered by Task 3's unit tests against `_plan_drift_check` directly; what needs checking here is that the real `checks` list in `step()` actually calls it (Step 2's source-needle test), and that nothing already in `tests/merge/` breaks.

- [ ] **Step 1: Confirm the current checks list**

Read `src/sdlc/stages/merge/step.py`. The `checks = [...]` list (currently lines 262-314) ends with the `coverage` entry:

```python
        build_check(
            "coverage",
            (True if diff_coverage is None else diff_coverage >= cfg.coverage_threshold),
            CheckClass.ADVISORY,
            detail=(
                _as_str(getattr(cov_obj, "reason", None), "coverage unmeasured")
                if diff_coverage is None
                else f"diff coverage {diff_coverage:.1f}% vs "
                f"threshold {cfg.coverage_threshold:.1f}%"
            ),
        ),
    ]
```

Add `_plan_drift_check(results_list)` as one more list entry, right before the closing `]`:

```python
        build_check(
            "coverage",
            (True if diff_coverage is None else diff_coverage >= cfg.coverage_threshold),
            CheckClass.ADVISORY,
            detail=(
                _as_str(getattr(cov_obj, "reason", None), "coverage unmeasured")
                if diff_coverage is None
                else f"diff coverage {diff_coverage:.1f}% vs "
                f"threshold {cfg.coverage_threshold:.1f}%"
            ),
        ),
        _plan_drift_check(results_list),
    ]
```

`results_list` is already in scope at this point in `step()` — it is built earlier, at the current lines 194-198, before any of the checks are constructed.

- [ ] **Step 2: Write a source-needle test pinning the wiring itself**

Without this, nothing in the suite actually fails if the `_plan_drift_check(results_list)` line above were omitted: `test_the_manifest_pins_the_checks_the_merge_step_builds` is satisfied by Task 3 alone (the `build_check` call lives inside `_plan_drift_check`'s own body, whether or not `step()` calls that function), and every test in `tests/merge/` mocks `evaluate_gate` directly rather than exercising the real `checks` list. That is exactly C4/C8's shape — a check that was never actually invoked reading as one that ran — recreated for E4's own wiring. Pin it the same way `tests/merge/test_merge_gate_wiring.py:33` and `tests/test_security_floor.py:141` already pin other must-be-called sites: a source-text assertion.

Append to `tests/merge/test_plan_drift_gate.py`:

```python
# -- wiring: the real checks list in step() must actually call _plan_drift_check --


def test_merge_step_checks_list_calls_plan_drift_check():
    import pathlib

    src = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")
    assert "_plan_drift_check(results_list)" in src, (
        "merge/step.py's real checks list must call _plan_drift_check, or the "
        "check exists (and satisfies the manifest census) without ever running"
    )
```

Run: `pytest tests/merge/test_plan_drift_gate.py::test_merge_step_checks_list_calls_plan_drift_check -v`
Expected: FAIL before Step 1's edit lands, PASS after — run it now to confirm it fails first if you have not yet made the Step 1 edit; if Step 1 is already applied, skip straight to confirming it passes.

- [ ] **Step 3: Run the existing merge test suite to confirm nothing breaks**

Run: `pytest tests/merge/ tests/test_required_checks_manifest.py -v`
Expected: PASS — every pre-existing test in `tests/merge/test_merge_gate_wiring.py` and `tests/merge/test_merge_slice_contract.py` constructs `TaskResult`s without `plan_drift` (defaults to `None`, contributes nothing to `_plan_drift_check`, so none of those tests newly fail), `test_the_manifest_pins_the_checks_the_merge_step_builds` is unaffected — this task adds no new `build_check(...)` literal, only a call to the one Task 3 already added — and the new source-needle test from Step 2 passes.

- [ ] **Step 4: Run the full test suite for regressions**

Run: `pytest tests/ -x -q`
Expected: PASS. Pay particular attention to any test that hand-builds a merge-gate `checks` list without going through `required_checks()` — those now need eight entries to pass a from-scratch `evaluate_quality_gate([])`-style absence check, but tests that mock `evaluate_gate` itself (like `test_merge_slice_contract.py`) are unaffected because they never reach the real `checks` list.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/stages/merge/step.py tests/merge/test_plan_drift_gate.py
git commit -F <msgfile>
```

Message body:
```
feat(merge): wire plan_drift into the merge gate's real checks list

One-line addition: _plan_drift_check(results_list) joins the checks
list evaluate_gate actually receives at runtime. Predicate, aggregation,
and manifest membership landed in the prior commit; this is pure
wiring, pinned by a source-needle test so an omitted call can't pass
silently -- the shape C4/C8 named for other lenses, closed here too (E4).
```

---

### Task 5: Document the new check in the merge stage contract

**Files:**
- Modify: `src/sdlc/stages/merge/merge.md`

**Interfaces:**
- None — documentation only, no code interfaces change.

- [ ] **Step 1: Update MERGE-1.3's advisory-check list**

In `src/sdlc/stages/merge/merge.md`, change MERGE-1.3 (currently):

```
### MERGE-1.3
On advisory gate failures (`review_severity`, `traceability`, `coverage`), the merge stage presents the blocking advisory checks to the human merge gate. If rejected, it terminates with `rejected:merge:advisory`. If approved, audited `GateOverride`s are recorded, the gate is re-evaluated, and a revised benchmark record is recorded. [SC-5, FR-204, FR-106]
An advisory check that is *absent* from the gate input is an advisory failure by this same route, and reaches the human gate carrying its `MISCONFIGURED` detail — see MERGE-1.6.
```

to:

```
### MERGE-1.3
On advisory gate failures (`review_severity`, `traceability`, `coverage`, `plan_drift`), the merge stage presents the blocking advisory checks to the human merge gate. If rejected, it terminates with `rejected:merge:advisory`. If approved, audited `GateOverride`s are recorded, the gate is re-evaluated, and a revised benchmark record is recorded. [SC-5, FR-204, FR-106]
An advisory check that is *absent* from the gate input is an advisory failure by this same route, and reaches the human gate carrying its `MISCONFIGURED` detail — see MERGE-1.6.
```

- [ ] **Step 2: Add MERGE-1.7 documenting the new check's semantics**

After MERGE-1.6 (which currently ends the `## Requirements` section, right before `## Failure modes`), add a new requirement:

```
### MERGE-1.7
`plan_drift` (E4) is a required advisory check, evaluated across every task in `task_results` unconditionally — a quarantined task's drift counts the same as a done task's, matching MERGE-1.3's existing treatment of `review_severity`. A task's `PlanDrift` is read from `TaskResult.plan_drift`, computed once in the code stage from `compute_plan_drift` (`src/sdlc/stages/plan/models.py`) and carried through unchanged. Per task, drift trips the check only when `touched_unhinted` (files touched but not hinted in the plan) has at least 2 entries, or is at least half of `files_touched`; `hinted_untouched` (over-hinting) never trips it, and a task with one or zero files touched is exempt. `plan_drift is None` (an empty `files_hint` or an empty diff — "not measured") never trips the check. The check fails if **any** task in the run trips it — the aggregation is not an average, so many tasks each drifting a little cannot outweigh one task drifting past the threshold on its own. Like every other advisory check, a `plan_drift` failure is waivable only through the audited `GateOverride` path (MERGE-1.3); the override's `reason` is the record of why the drift was acceptable — there is no separate plan-amendment artifact, and `DevTask.files_hint` is never mutated by this check. [E4]
```

- [ ] **Step 3: Update the failure-modes bullet**

Change the "Advisory gate rejection" bullet in `## Failure modes` (currently):

```
- **Advisory gate rejection**: Failing review approval, untraced criteria, or below-threshold diff coverage rejected by the human reviewer.
```

to:

```
- **Advisory gate rejection**: Failing review approval, untraced criteria, below-threshold diff coverage, or unacknowledged plan drift rejected by the human reviewer.
```

- [ ] **Step 4: Verify the doc renders sensibly**

Run: `pytest tests/merge/ -k clause -v` (no functional coverage of markdown prose, but confirms the `pytest.mark.clause("MERGE-1.x")` markers already in the test suite still collect cleanly after the edit)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/stages/merge/merge.md
git commit -F <msgfile>
```

Message body:
```
docs(merge): document the plan_drift advisory check (MERGE-1.7)

Names the threshold, the any-task-fires aggregation, the None/quarantined
handling, and that the audited GateOverride reason is the plan-amendment
record E4 asked for -- no new artifact type. Extends MERGE-1.3's list.
```

---

## Final verification

- [ ] Run the full suite once more end to end: `pytest tests/ -q`
- [ ] Run lint: `ruff check .`
- [ ] Run format check: `ruff format --check .`
- [ ] Run type check: `mypy src/`
- [ ] Confirm no `DevTask.files_hint` mutation was introduced: `git diff main -- src/sdlc/stages/plan/models.py` should be empty (Task 1-5 never touch this file).
- [ ] Confirm five commits exist on the branch, each independently green.
