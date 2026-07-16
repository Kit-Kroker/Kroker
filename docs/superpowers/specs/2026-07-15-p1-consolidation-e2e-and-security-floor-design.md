# P1 Consolidation — Provable End-to-End Run + Honest Absolute Floor

| | |
|---|---|
| Status | Design v1.0 |
| Date | 2026-07-15 |
| Related | `PRD.md` (§9 P1, FR-106, FR-703, SC-5), `ARCHITECTURE.md` (§10, §14, ADR-14), `docs/feature-coverage-audit-2026-07-05.md` (now partly stale) |
| Supersedes context | Reviewer stage + agent registry landed since the 2026-07-05 audit (merged `b9455c3`), closing that audit's priorities #2/#3 |

---

## 1. Motivation

Delivery has gone breadth-first: P3 mechanisms (Hindsight memory, memoization/watermark, confidence-gated soft gates), P2 mechanisms (cross-harness review, fix loops), and benchmarking infra are all built — but **two P1 obligations are unmet**:

1. **The pipeline has never been driven start-to-finish.** `FeatureWorkflow` (the run orchestrator) has no test that takes an `IdeaBrief` through the wired stages to deploy. All `test_integration_*` files exercise *activities* in isolation. The 7 live stages (clarify → architecture → planning → code → qa → review → deploy) are unit-verified but never proven to **compose**. P1's exit criterion — "one project shipped end-to-end" — is therefore undemonstrated.
2. **The absolute floor is vacuous.** SC-5 promises "zero deploys past a failed *absolute* check," and `security_no_critical` is declared in `gate.py`'s `ABSOLUTE_FLOOR` — but nothing ever emits that check. The merge gate builds exactly three checks (`build_integration_green`, `lint_clean`, `review_severity`); the security floor never runs, so the project's strongest stated guarantee does not bite.

This design consolidates existing breadth into a **demonstrated, regression-guarded, honest P1**. It adds no new pipeline stages.

## 2. Goal

- **G1:** A CI-runnable, fully deterministic test that drives the real `FeatureWorkflow` from a greenfield `IdeaBrief` to a successful deploy, answering the clarify question and every gate via signals. This is the P1 "one project shipped end-to-end" artifact.
- **G2:** Make `security_no_critical` a real **absolute** merge-gate check: a minimal deterministic scanner emits a `SecurityReport`; a critical finding makes the gate terminal with no deploy. SC-5 stops being vacuous.

## 3. Scope decisions (settled in brainstorming)

- **Fidelity: orchestration-level.** The test runs the real workflow with non-determinism faked at two seams (activities + models). It proves the DAG, gate signals, ADR-14 integration branch, and merge gate compose. It deliberately does **not** exercise real git or real pytest — that was considered and rejected as a heavier, separate concern.
- **Security scanner: minimal-but-real.** A simple deterministic ruleset now, with a clean seam to swap a production SAST later. The load-bearing part is that the check is *built, classed absolute, and can fail* — not the scanner's sophistication.

## 4. Architecture

The production code path is unchanged. The end-to-end test substitutes implementations at two seams only:

```
FeatureWorkflow (REAL, on time-skipping WorkflowEnvironment)
   │
   ├── proposer stages ──► [MODEL SEAM] Pydantic AI model override
   │      t_clarify / t_architect / t_planner /        (FunctionModel/TestModel
   │      t_reviewer / t_qa / t_merge_verdict           → canned typed outputs)
   │
   └── side-effect stages ─► [ACTIVITY SEAM] fake @activity.defn impls
          run_coding_task, create_worktree, get_task_diff,
          merge_into_integration, run_tests, run_lint,
          security_scan (NEW), recall/retain/reflect, deploy
```

A single in-process worker registers the real `FeatureWorkflow` plus the fake activities. A driver coroutine polls `pending_gate()` / `status()` queries and sends `answer_question` + `submit_gate_decision` signals in stage order. Time-skipping makes gate reminder/timeout timers instant while keeping the wait mechanics real.

## 5. Components

### 5.1 `tests/fakes/canned_outputs.py`
One deterministic artifact per proposer, each self-consistent with the next stage's needs:
- `ClarifiedRequirements` with exactly one `OpenQuestion` (so the driver exercises `answer_question`).
- `ArchitectureSpec` with `confidence` set (above the plan gate threshold, to also exercise soft-approve where configured).
- `ImplementationPlan` with 1–2 `DevTask`s carrying a frozen `ValidationContract` (so the per-task loop and merge-gate lint/security use real contract fields).
- `ReviewReport(approve=True)`, `QAReport(tests_passed=True, issues=[])`, `MergeVerdict` (advisory).

### 5.2 `tests/fakes/fake_activities.py`
Fake `@activity.defn` functions matching the production names/signatures the workflow calls, returning canned deterministic values without git or subprocess: harness run → a `HarnessRunResult` with populated token fields; repo ops → stable branch/worktree paths and a small canned diff dict; QA (`run_tests`/`run_lint`) → green; memory (`recall_snapshot`/`retain`/`reflect`) → empty snapshot / no-op; `security_scan` → clean report; `deploy` → success.

### 5.3 `tests/test_e2e_greenfield.py`
The P1 proof. Starts `FeatureWorkflow` with a greenfield `IdeaBrief`; driver answers the clarify question and approves clarify/architecture/plan/merge/deploy gates via idempotent signals; asserts:
- terminal status reaches **deploy** and the run result is success;
- the merge `GateReport` contains a **passing** `security_no_critical` check classed `ABSOLUTE`;
- the ADR-14 integration branch accumulated the (faked) task merge.

### 5.4 Thread B — security floor (production code)
- **Model** `SecurityReport { critical: int, findings: list[SecurityFinding] }` in `models.py` (alongside `QAReport`/`ReviewReport`).
- **Activity** `security_scan(worktree) -> SecurityReport` in `activities.py`: a minimal deterministic ruleset over the integration worktree/diff (obvious secret patterns, dangerous calls). Registered on the worker. Seam documented for a later real SAST.
- **Wiring** in `feature.py` §5a: run `security_scan` against `integration_worktree`, then append to the merge `checks` list (after `lint_clean`, before `review_severity`):
  `build_check("security_no_critical", report.critical == 0, CheckClass.ABSOLUTE, detail=...)`.
  The existing §5b absolute-blocking branch (`feature.py:823-841`) then makes it terminal for free — no override path.

## 6. Risk & the spike-first task

**Primary unknown:** whether a Pydantic AI **model override propagates across the `TemporalAgent` → activity boundary** inside a time-skipping worker (the model call executes in an activity, in-process here). This is the one thing that can invalidate the model seam.

**Mitigation:** the first task is a minimal spike — drive a *single* stubbed proposer stage to one gate and back, asserting the canned output surfaces. Only after the mechanism is proven do we build the full `canned_outputs` set and driver. **Fallback** if override doesn't cross the boundary: register replacement activities for the `TemporalAgent`-generated activity names (matched by agent `name=`), returning the canned typed outputs directly.

**Secondary risks:**
- *Signal/query race:* the driver must observe `pending_gate()` non-null before signaling; it polls the query under the time-skipping clock rather than sleeping wall-clock.
- *Fake-activity drift:* fakes share `models.py` return types with production, so a signature change breaks the fakes at import/type-check time rather than silently — this is intended.

## 7. Out of scope (documented, not dropped)

Real-git/real-pytest fidelity (rejected in favor of orchestration-level); renaming `FeatureWorkflow` → `FactoryWorkflow` (cosmetic doc drift); the still-missing stages (constitution, context/Cartographer, standalone requirements, analyze/Analyst, retro/reflect wiring); a production-grade SAST (minimal scanner + seam only); MCP server, dashboard backend, MaintenanceWorkflow/DAPER, two worker pools, run-level budgets, observability export. These remain post-P1 roadmap and are unaffected by this change.

## 8. Task outline (detailed steps deferred to the implementation plan)

1. **Spike:** prove the agent-stub mechanism on one stage → one gate → back.
2. `tests/fakes/canned_outputs.py` — deterministic proposer artifacts.
3. `tests/fakes/fake_activities.py` — fake activity impls.
4. **Thread B:** `SecurityReport` model + `security_scan` activity + `security_no_critical` absolute check wired into the merge gate; unit test that a critical finding blocks deploy (SC-5).
5. `tests/test_e2e_greenfield.py` — the full driver + assertions (the P1 proof), including a green `security_no_critical` in the passing run.
6. Full-suite run; confirm no regressions and the import-linter workflow-purity guard still passes.

## 9. Spec self-review

- **Placeholders:** none — every component names concrete files, models, and insertion points (`feature.py:807-819` checks list; `feature.py:823-841` terminal branch).
- **Consistency:** the security check is built ABSOLUTE and reuses the existing §5b terminal path, so G2 needs no new gate-decision logic; the e2e run (G1) passes it green, and the Thread-B unit test fails it red — the two assertions are complementary, not contradictory.
- **Scope:** single implementation plan; two tightly-coupled threads (the honest run must legitimately pass the honest floor). No decomposition needed.
- **Ambiguity:** "orchestration-level" and "minimal-but-real scanner" are pinned in §3 with the rejected alternatives named, so neither can be re-interpreted as high-fidelity or production-SAST.
