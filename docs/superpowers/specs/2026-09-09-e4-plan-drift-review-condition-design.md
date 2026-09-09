# E4 — plan drift becomes a review condition

**Date:** 2026-09-09
**Status:** approved design, ready for planning
**Scope:** one row from the external-ideas register (`docs/reports/external-ideas-2026-09.md`, section E, E4). A bounded code change: wire an already-computed, already-discarded signal into the merge gate as a new `CheckClass.ADVISORY` check.
**Satisfies:** no FR moves. Extends the `MERGE_REQUIRED_CHECKS` manifest C3 introduced; follows the `coverage`/`traceability` precedent exactly.
**Baseline:** `main` at `24d4b29`.
**Does not cover:** any mutation of `DevTask.files_hint`, any new artifact type, any structured/validated override-reason field, any change to the plan stage's `revisable_stage` human gate, any change to review-stage ordering.

---

## 1. Problem

`compute_plan_drift` (`src/sdlc/stages/plan/models.py:51`) is pure and already called once per task, at `src/sdlc/stages/code/step.py:769`. Its result — a `PlanDrift` recording which hinted files went untouched and which touched files were unhinted — is attached only to the benchmark record and read by nothing else. The C4 pairing audit named this gap explicitly: the plan stage has no analogue to the architect's `check_brownfield_delta` grounding, and this row is its own register entry rather than folded into that audit.

The register's own wording overstates what is buildable here: "plan↔diff sync **enforced**" reads as a hard guarantee. `PlanDrift`'s docstring is explicit that `files_hint` is "a hint, never a gate" and that a wrong guess is a normal outcome measuring planner calibration, not correctness. This spec does not build enforcement. It builds **acknowledgment**: drift becomes visible at the one place in the pipeline a human already reviews advisory failures, and passing it through silently requires the same audited trail every other advisory override already leaves. Where this document says "flag" it means an ADVISORY check at the merge gate, not a block with no escape hatch.

## 2. Landing site

The merge gate's checks list (`src/sdlc/stages/merge/step.py:262-314`) already carries three `CheckClass.ADVISORY` checks — `review_severity`, `traceability`, `coverage` — each backed by an audited `GateOverride` (`gate.py:46`) when it blocks. `plan_drift` becomes a fourth, same mechanism, same waiver path. No new gate machinery, no change to `evaluate_quality_gate`, no review-stage reordering.

## 3. `TaskResult` carries the signal

`TaskResult` (`src/sdlc/workflows/models.py:52`) gets a new field:

```python
plan_drift: PlanDrift | None = None  # E4: drift evidence for the merge gate
```

`TaskResult` has exactly two construction sites in `src/` (verified: `rg "TaskResult\("`), both in `src/sdlc/stages/code/step.py` — the done path (`:826`) and the human-approved-after-budget-exhaustion path (`:897`). **Both** populate `plan_drift` from the drift value already computed at `:769` (reuse the same call — do not compute it twice). Missing either site means an approved-but-drifted task fails open, invisible to the check below.

## 4. The per-task predicate

```python
def _plan_drift_flags(drift: PlanDrift) -> bool:
    if drift.files_touched <= 1:
        return False  # no calibration signal at n=1
    unhinted = len(drift.touched_unhinted)
    return unhinted >= 2 or (unhinted / drift.files_touched) >= 0.5
```

- Only `touched_unhinted` counts. `hinted_untouched` (over-hinting) is ignored — it is harmless and `files_hint` already disclaims precision.
- Single-file tasks are exempt: one unhinted touch on a one-file task is a 100% ratio with zero calibration value.
- `>= 2 OR ratio >= 0.5` tolerates one off-hint file (a moved helper, refactor spillover) while catching systematic off-plan work. This threshold is a judgment call, not derived from data; revisit if it proves noisy or silent in practice.

## 5. Run-level aggregation

**Any task fires.** The check fails if any task in `results_list` has a `plan_drift` that trips §4 — not an average, not a majority. This matches the shape of the existing `untraced` reduction (`merge/step.py:207`, collected across all tasks) rather than diluting a single drifted task into a fleet-wide mean.

**Quarantined tasks count, deliberately.** `results_list` (`merge/step.py:194-198`) is built with no status filter, and `review_severity`'s existing precedent reads all results regardless of `status`. `plan_drift` follows the same precedent: a quarantined task's drift still fires the check. The alternative — filtering to `status == "done"` — would mean work that never landed leaves no drift trail at all, which is the wrong default for a signal about planner calibration. This is a deliberate choice, not an oversight; a future spec may special-case quarantined tasks if this proves wrong.

The check:

```python
drifted = [r.task_id for r in results_list if r.plan_drift and _plan_drift_flags(r.plan_drift)]
build_check(
    "plan_drift",
    not drifted,
    CheckClass.ADVISORY,
    detail=(
        f"{len(drifted)} task(s) touched unhinted files beyond threshold: {drifted[:10]}"
        if drifted
        else "no task exceeded the plan-drift threshold"
    ),
)
```

## 6. `None` handling and the manifest

`compute_plan_drift` returns `None` when either `task.files_hint` or `files_touched` is empty (`models.py:55`) — "a prediction that was never made cannot be adhered to." Per the `coverage` precedent (`merge/step.py:303-312`, `None` diff_coverage → pass with detail), a task with `plan_drift is None` is **not measured**, not flagged: it contributes nothing to `drifted` above, same as an omitted hint always has.

**Named bypass, accepted, not fixed here:** a task whose plan never hinted any files is invisible to this check for its entire life. This is consistent with `files_hint` being optional everywhere else in the pipeline and is not a defect this spec closes.

`plan_drift` joins `MERGE_REQUIRED_CHECKS` (`gate.py:86`) as `CheckClass.ADVISORY`, alongside `review_severity`/`traceability`/`coverage`:

```python
"plan_drift": CheckClass.ADVISORY,
```

This is required so C3's fail-closed synthesis covers it: a build that stops producing the check (a future refactor that drops the `build_check` call) fails as `MISCONFIGURED` rather than silently passing, exactly the hole C3 closed for the other three. The manifest entry must be added in the **same commit** as the check itself — a check present in code but absent from the manifest is not itself a gap (C3 only synthesizes for a name declared required that the input omits), but shipping them separately would leave a window where the check exists without the fail-closed backstop.

## 7. What "committed plan amendment" means here

The register text says "drift without a committed plan amendment is a review flag." This spec does **not** introduce a new `PlanAmendment` artifact or mutate `DevTask.files_hint`. `GateOverride.reason` is constructed uniformly across every advisory-blocking check in one pass (`merge/step.py:364-367`: `reason = gate.comments or "advisory override"`, applied identically to `review_severity`, `traceability`, `coverage`, and now `plan_drift`) — there is no per-check structured field, and adding one would require new parsing machinery this row does not justify. A structured `actual_files` + `cause` requirement was considered and dropped: it cannot be enforced without a validation site that does not exist, which would itself be an unpaired requirement — exactly the shape of gap the C4 audit exists to catch.

The amendment **is** `gate.comments`: the human merge reviewer's free-text reason, recorded and attributed the same way every other advisory override already is. This delivers **drift-requires-acknowledgment**, not **plan↔diff sync enforced**. If E4 is ever promoted to hard-gating or a real amendment artifact is wanted, that is future work with its own spec — this row's job is closing the "computed and read by nothing" gap cheaply, per the register's own framing.

## 8. Contract text

`src/sdlc/stages/merge/merge.md` gets a clause alongside the existing MERGE-1.x advisory-check language (§ wherever `review_severity`/`traceability`/`coverage` are documented), naming `plan_drift` as a fourth required-advisory check, its `None`-is-unmeasured semantics, and the any-task-fires aggregation. The `MERGE_REQUIRED_CHECKS` manifest comment in `gate.py` is unchanged in substance (it already states the general rule); no per-check comment is required beyond the dict entry itself, consistent with the three existing advisory rows.

## 9. Testing

- **Predicate unit tests** for `_plan_drift_flags`: `files_touched == 1` exempt regardless of `touched_unhinted`; `touched_unhinted == 2, files_touched == 2` flags; `touched_unhinted == 1, files_touched == 3` does not flag; `touched_unhinted == 0` never flags.
- **Merge-gate integration test**: a `results_list` with one drifted task and one clean task fires `plan_drift` with the drifted task's id in `detail`; an all-clean list does not fire; a list where every task has `plan_drift is None` passes with the "unmeasured" detail, not a synthesized failure.
- **Manifest-membership test**: `plan_drift` is present in `MERGE_REQUIRED_CHECKS` at `CheckClass.ADVISORY`, and a `checks` list omitting it synthesizes a failing `MISCONFIGURED` result (exercises the existing C3 machinery against the new name — this is the test that replaces the originally-proposed structured-reason round-trip test, which is moot once §7 dropped structured reasons).
- **Waiver test**: a `plan_drift`-blocking `checks` list, combined with a `GateOverride(check="plan_drift", ...)`, re-evaluates clean — confirms the check rides the existing override path with no special-casing.

## 10. Out of scope, explicitly

- Mutating `DevTask.files_hint` or any other plan artifact.
- A new `PlanAmendment` type or any structured override-reason schema.
- Changing `files_hint`'s advisory ("hint, never a gate") status anywhere else in the pipeline.
- Filtering quarantined tasks out of the aggregation (§5's deliberate choice).
- Tuning the §4 threshold from production data — it is a documented judgment call, not a derived constant.
