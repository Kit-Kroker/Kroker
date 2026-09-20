# e2e-proposer-hang — REGRESSION QA (chaos) findings

Seat: qa-chaos. Deliverable: `tests/test_assessment_workflow_e2e_proposer_hang_chaos.py`
(3 tests, all verified RED bounded on this worktree, 2026-09-20).

## The defect is TWO mechanisms, and the second one hides the first

**Mechanism 1 — the unbounded await (the hang, confirmed).**
`AGENT_ACTIVITY_CONFIG` sets no `retry_policy`, so proposer agent activities run
under Temporal's default UNLIMITED retries. An activity no worker serves fails
with a *retryable* `NotFoundError` and retries forever; `t_risk.run(...)` /
`t_discover.run(...)` never resolve and the assessment never completes.
Verified three ways on this worktree:

- A bare probe workflow (`await t_risk.run(...)` + a worker with no risk
  activities) wedged past a 45s bound.
- Chaos test T1's own log: `agent__risk_agent__model_request` NotFound
  retried for the entire 120s bound (the run produced ~300k lines of retry
  warnings).
- Chaos tests T2/T3: a *served* proposer whose model call raises a RETRYABLE
  error (the default classification) also loops forever under the production
  config. The sibling `test_discover_proposer_exception_fails_closed` only
  passes today because it builds its OWN config with `maximum_attempts=1`
  and `non_retryable=True` — it opts out of the defect.

**Mechanism 2 — a machine-global memo cache masks the hang (new finding).**
`memoization/cache.py:_cache_root()` defaults to
`%TEMP%\sdlc\memo_cache` (machine-global, cross-checkout, cross-run) and the
risk memo key is pure content (`project|tree_hash|map_digest|rules_sha|
prompt_sha|model`). The e2e `assessed_repo` fixture builds a byte-identical
tree every run, so any earlier run of the risk-proposer scenario anywhere on
the machine — including from the primary checkout — leaves a judged map
under the exact key the "hanging" test computes. `_assess` then HITS the
memo and never awaits the risk proposer at all.

Evidence (diagnostic run, workflow history, worker serving only the discover
fake): NO `agent__risk_agent__*` scheduled, NO `assess_risk`, NO
`verify_risk_refs` — yet `risk_memo_load` ran and the result came back with
`judgment=MEASURED(1.0, '')` that no run of this test produced
(`apply_judgment`'s fingerprint). The hang is therefore **cold-cache-only**:
tier position #102 is before the memo-warming test ever executes, and
"hangs ALONE" reproductions depend on what ran earlier on the machine. This
also explains why the same test passes on some machines/venvs and wedges on
others — it was never about temporalio 1.30 vs 1.31.

## Consequence for the existing tests (needs a decision)

Every proposer e2e test that does not isolate `SDLC_MEMOIZATION_CACHE_ROOT`
is cache-temperature dependent:

- `test_discover_proposer_judgment_and_verification` passes warm, wedges cold.
- `test_assessment_workflow_e2e_proposer_hang.py::test_unservable_risk_
  proposer_degrades_fail_closed_in_bounded_time` (qa-happy's RED) currently
  fails on this machine by ASSERTION (`judgment` MEASURED from the stale
  memo), not by timeout — and on a warm cache it will STILL fail the same
  way AFTER the mechanism-1 fix lands, because the memo hit legitimately
  skips `_judge`. Recommend the fix task (or a test-only follow-up) add
  `monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", tmp_path / "memo")`
  to the e2e module's proposer tests and the hang regression file; the
  chaos file does this in its `assessed_repo` fixture and is deterministic
  on any machine as a result.

## Chaos test inventory (all RED today, bounded by `asyncio.wait_for(120)`)

| Test | Edge | RED mechanism | Post-fix contract |
|---|---|---|---|
| `test_a_degraded_run_leaves_no_memo_poison_for_a_healthy_rerun` | stale state across runs | run 1 wedges on the unservable risk proposer | run 1 degrades fail-closed ("ran and failed"); P2-D3 refuses the store; run 2 (healthy proposer) re-judges — MEASURED, not the inherited degradation |
| `test_a_retryable_risk_proposer_failure_exhausts_and_degrades` | error path + reason boundary | retryable failure loops forever under `AGENT_ACTIVITY_CONFIG` | bounded exhaustion → RD7 degrade; reason says "ran and failed", never converges with "no risk proposer ran" |
| `test_a_retryable_discover_proposer_failure_fails_the_phase_closed` | discover-side twin (fail-closed, not degrade) | same loop on `_discover`'s await | phase NOT_COLLECTED "discover proposer failed"; ASSESS degrades "nothing to assess"; full phase list; `risk is None` |

Bound values: `RESULT_BUDGET_S=120` per result await (green runs of these
scenarios take 16-36s each); `pytest.mark.timeout(300)` module-wide, 420 on
the two-run test; per-test runs under a wall-clock wrapper with
temporal-test-server killed before and after every run.
