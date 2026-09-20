# Bug Review: Replay-harness notify race (bug notify-flake)

- **Slug**: notify-flake
- **Worktree**: `D:/own/Kroker/.claude/worktrees/fix-notify-flake`
- **Branch**: `fix/notify-flake` at commit `2fcb991`
- **Base**: main `2c732e0`
- **Review Scope**: chain `b89e11e^..2fcb991` (8 commits: `b89e11e`, `45a7275`, `376dc93`, `a8f9ac6`, `dbae7e2`, `28223c3`, `5bcb39d`, `2fcb991`)
- **Reviewer**: Reviewer Seat (Antigravity)
- **Date**: 2026-09-21
- **Verdict**: **APPROVE**

---

## 1. Executive Summary

This review covers the remediation for bug `notify-flake` (task card `e75-notify-flake.md`). The bug caused nondeterministic workflow-task failures under full-file replay load (`NotFoundError: Activity function notify ... is not registered on this worker`), stemming from the replay harness worker executing bundles that omitted scheduled activities (`notify` across 13 scenarios / 34 schedulings, and `plan_research` in `research_greenfield`).

The fix on `fix/notify-flake` at `2fcb991` delivers:
1. **Harness-Only Registration**: Registers a no-op fake `fake_notify` (returning the `Results` contract with zero deliveries) and an empty-plan fake `fake_plan_research` across all 9 bundles that schedule them.
2. **Deterministic Contract Suite**: A consolidated 77-item contract test (`tests/replay/test_notify_registration_chaos.py`) adopting qa-chaos and qa-happy contracts, verifying registration completeness, contract fidelity, golden byte-identity freezing, and duplicate-name prevention.
3. **Honest Gate Reporting**: A well-reasoned `partial` verdict accepted under orchestrator ruling (2026-09-20) due to a separate, pre-existing race (`golden-tick-race`) that was proven at clean baseline `2c732e0` and recorded in an untracked follow-up card (`.workspace/tasks/golden-tick-race.md`).
4. **Exemplary Commit Hygiene**: 8 well-structured commits, completely free of git trailers.

---

## 2. Scope & Harness-Only Cleanliness

- **No Production Code Touched**: `git diff 2c732e0..2fcb991 --stat` confirms zero modifications under `src/`.
- **Harness Isolation**: Code changes are strictly confined to `tests/replay/scenarios.py` (40 insertions, 0 deletions) and test/doc files.
- **Fixture Integrity**: Zero modifications to `tests/replay/golden/*.json` or `tests/replay/histories/*.json`. Golden byte-identity is completely preserved.
- **Unrelated Working Tree Preservation**: The uncommitted change to `pyproject.toml` in the main checkout was correctly identified as belonging to a parallel user session and was not staged, committed, or reverted.
- **Out of Scope Adherence**: All designated out-of-scope concerns (sibling `./runs` readers, fail-edge fix axis E74-OQ-3, E75-OQ-2/3/4, E-9 notification feature work, T043, frontend) remained untouched.

---

## 3. Harness Fix & Contract Test Quality

### 3.1 Harness Fakes (`tests/replay/scenarios.py`)
- **`fake_notify`**:
  - Decorated with `@activity.defn(name="notify")` and takes `NotifyInput`.
  - Returns `Results()` (empty deliveries list).
  - Matches the critical invariant: `gates.py:166` iterates `out.results` outside the try/except block. A fake returning `None` or an incompatible structure would raise an `AttributeError` on the success path.
  - Correctly avoids registering the production transport (`sdlc.notify.activities.notify`).
- **`fake_plan_research`**:
  - Decorated with `@activity.defn(name="plan_research")` and takes `PlanInput`.
  - Returns empty `ResearchPlan()` (`sub_questions=[]`, default usage).
  - Because `sub_questions` is empty, `stages/research/step.py:256` triggers the deterministic degrade branch (`brief = _degraded_research_brief(...)`) without scheduling subsequent `research_subquestion` or `synthesize_brief` activities. This mirrors the previous unregistered expiry behavior, preserving exact golden command and trace projections.
- **Registration Coverage**:
  - Correctly registered across both helpers (`_base_activities`, `_budget_activities`) and all 7 inline bundles (`brownfield_happy`, `arch_timeout_reject`, `waves`, `seeded`, `research_greenfield`, `cancel_during_code`, `partial_awaiting_architecture`).

### 3.2 Contract Test Suite (`tests/replay/test_notify_registration_chaos.py`)
- **Coverage**: 77 test items spanning all 16 scenarios (including `partial_awaiting_architecture` per orchestrator ruling):
  - 13 items: `test_notify_is_registered_by_every_scenario_that_schedules_it`
  - 16 items: `test_no_activity_other_than_notify_is_left_unregistered` (general sweep)
  - 2 items: `test_base_activities_registers_notify` and `test_budget_activities_registers_notify`
  - 16 items: `test_no_bundle_registers_a_name_twice`
  - 16 items: `test_core_activities_stay_registered`
  - 1 item: `test_goldens_schedule_notify_exactly_as_pinned` (freezes 16 files, 34 schedulings)
  - 13 items: `test_registered_notify_fake_honours_the_results_contract` (tests optional boundary fields `deadline=None`, `project=None` and validates `Results`)
- **Restored List-Shape Duplicate Guard (Commit `2fcb991`)**:
  - Commit `2fcb991` corrected a subtle flaw in `test_no_bundle_registers_a_name_twice`. In commit `376dc93`, the test inspected `list(_registered_map(name))`. Because `_registered_map` was a dictionary, duplicate activity names were deduplicated on dictionary insertion, rendering the test vacuous (`names.count(n) > 1` could never trigger).
  - Commit `2fcb991` restored the direct list comprehension over `_BY_NAME[name].activities()`, collecting raw names before deduplication and asserting both `len(names) == len(set(names))` and `not dupes`.
- **Fast Tier & Determinism**:
  - The suite runs purely via static inspection of scenario bundles and committed JSON fixtures without requiring a Temporal server daemon, timers, or network access.
  - RED-to-GREEN transition is fully verified: 29 RED / 48 green pre-fix -> 77/77 green post-fix.

---

## 4. Honest Partial-Verdict Documentation

- **Ruling Alignment**: The bug reports (`.specify/bugs/notify-flake/assessment.md`, `fix.md`, `test.md`) document the verification results with complete transparency.
- **Elimination of Target Flake**: Grep verification across all branch full-file logs confirms 0 occurrences of `NotFoundError: Activity function notify ... is not registered`. The race identified in the bug brief is completely eliminated.
- **Secondary Race Diagnosis (`golden-tick-race`)**:
  - Rather than artificially masking failures or attempting out-of-scope fixes, `test.md` thoroughly diagnoses the driver-vs-gate-schedule-tick race in `test_graph_golden.py`.
  - Baseline evidence confirms that at clean main `2c732e0`, full-file runs fail with the identical command divergence (`budget_arch_reject-sandboxed` index 11 diff: `'activity:publish_artifact_version' != 'timer'`).
  - Follow-up card created at `.workspace/tasks/golden-tick-race.md` and untracked via commit `5bcb39d` to respect `.gitignore` rules regarding the local `.workspace/` inbox.
- **Count Reconciliations**: Commit `2fcb991` updated `fix.md` to accurately state that the combined pre-fix run log contained 53 failures (29 from the chaos file + 24 from the then-separate happy file), while the pre-fix state of the current 77-item file is 29 RED / 48 green.

---

## 5. Commit Hygiene & Standards

- **Commit Chain**:
  1. `b89e11e` `test(replay): RED registration contracts for the notify flake`
  2. `45a7275` `test(replay): adopt qa-chaos RED contracts for the notify flake`
  3. `376dc93` `test(replay): consolidate the two RED contract files into one`
  4. `a8f9ac6` `fix(replay): register the activities the golden histories schedule`
  5. `dbae7e2` `docs(bug): notify-flake fix and verification reports (partial -- gate blocked by pre-existing tick race)`
  6. `28223c3` `docs(bug): golden-tick-race follow-up card; notify-flake gate adjusted per ruling`
  7. `5bcb39d` `docs(bug): untrack the tick-race card -- .workspace stays an untracked local inbox`
  8. `2fcb991` `test(replay): restore the duplicate-name guard's list shape; fix fix.md counts`
- **Trailers**:
  - `git log` inspection confirms zero trailers (no `Signed-off-by`, `Co-authored-by`, `Reviewed-by`, etc.) across all 8 commits.
- **File Lengths**:
  - All modified and authored files comply with the 1000 physical line repository limit (longest is `scenarios.py` at 647 lines).

---

## 6. Findings

### Blocking
None.

### Minor
None.

### Notes
- **Note 1 (Duplicate Name Guard Fix)**: Commit `2fcb991` effectively restored the teeth of `test_no_bundle_registers_a_name_twice`. Testing raw activity list definitions directly guarantees that accidental duplicate registrations (which cause Temporal worker construction failures) cannot slip into scenario bundles.
- **Note 2 (Untracked Follow-up Card Discipline)**: Untracking `.workspace/tasks/golden-tick-race.md` in `5bcb39d` preserves `.workspace/` as an untracked local inbox according to `.gitignore:4`, while embedding the diagnosis and mechanism within `.specify/bugs/notify-flake/test.md` preserves repo-level visibility.

---

## 7. Verdict

**APPROVE**

Branch `fix/notify-flake` at `2fcb991` is clean, strictly scoped, deterministically tested, and verified. Ready for integration.
