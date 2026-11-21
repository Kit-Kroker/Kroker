# AGENTS.md — code

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: code stage accepts task, contract, and worktree, executing independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Handlers live on the workflow class's MRO, never in this slice.
- The slice exports `step`, `prompt_digest`, and `ACTIVITIES = [run_coding_task, load_drift_globs]`.
- `freeze.py` holds the C2 freeze/thaw decision rules as pure functions (no `ctx`, no I/O, table-testable); `step.py` re-exports them, so existing `from ...code.step import _next_anchor` sites keep working. Audit recorders (`_record_escalation`, `_record_thaw`) stay in `step.py`.
- All tool escalations and approvals are recorded to benchmarks and trace events.
- `run_coding_task`'s checkpoint commit failing is logged at WARNING and never raised (CODE-1.7): `commit_sha` stays `None` and the C2 anchor does not advance. `sdlc doctor`'s git-identity check is the pre-run guard for the usual cause; keep its FAIL text in step with this behaviour.
- Safe lint autofix runs inside `run_coding_task`, before the checkpoint commit, and never raises (CODE-1.8). It skips repair-fenced paths on a repair attempt.
- `attempt_failure.py` holds the pure classifiers (`attempt_failure`, `_qa_failure`, `_lint_ok`, `_lint_input`) behind `task_passed` and `BenchmarkRecord.failure`. The attempt's cause goes in `failure`, never in `error` (CODE-1.10). `_lint_ok` is the only place that decides a lint finding fails a task: fences are report-only and an unmeasured lint passes (CODE-1.9).
- The C8 lens tombstones are classified here but defined in the review slice (`stages/review/lenses.py`); this slice never re-implements the presence rules or the admission predicates.
- QA and review stages are invoked clean-context, validating against the frozen contract.
- (FR-702) The attempt fetches the diff once via `get_task_diff` → `CodeArtifact`, stores the run's claim-check on `run.diff_ref`, and materializes prompt patch text through the `load_diff` bounded read-back (a `patch_ref=None` artifact — propose arm / legacy fakes — means empty patch text and NO read-back command, Review Focus 3). `_run_handoff` lives in `handoff.py` (moved for the file-size ceiling; imported here as `_run_handoff`).
- The review loop's reviewer label is the run's resolved model
  (`resolve_role_model(cfg, "review")`), never the registry default: under a
  `reviewer` override the label, the priced model and the model that serves
  the call must agree, or `_run_role`'s guard fails the call (004, FR-002).

## Temporal notes for this slice

- `ACTIVITIES = [run_coding_task, load_drift_globs]`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `harness`, `crew`.
- Long-running harness activities use heartbeat timeouts and retry policies.
- Eager exports in `__init__.py` ensure worker boot registers activities and models without sandbox errors.

## State

- `StageContext` provides access to `gate`, `record`, `retain`, `emit`, `judge`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/code/ -q
