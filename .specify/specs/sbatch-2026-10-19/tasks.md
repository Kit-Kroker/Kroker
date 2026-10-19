# Tasks: S-batch 2026-10-19

Spec: `spec.md` beside this file (task details, stop-guards SG-1..SG-5 —
binding). Branch `sbatch-2026-10-19` off main. Commit per task; reviewer
gate per task is BLOCKING; qa seats write the failing tests first.

- [x] T1 Judge: stop stacking SDK retries (single_retry_layer) — 037fa55f
- [x] T2 check_ui wrapper per-test timeout under load — 614f258c
- [x] T3 get_task_diff 60k cut carries a visible marker — 9148ca66
- [x] T4 Research SQ: dead non_retryable_error_types — 25c02bbd (KEEP, documented + pinned)
- [x] T5 Dashboard: fleet poll survives a failed first read — 3379c6e3
- [x] T6 Registry packaging test: probe env dummy keys — 0796cb09
- [x] T7 Research agent: output retries above 1 — 28ccd85c (output:3)
- [x] T8 Research judge on the refine-crash path: confirm + wording — da700b82

After T8: run the replay tier once (`uv run pytest -m temporal
tests/replay`), then file per-task findings to `.workspace/tasks/` and
report. Scribe: no living-docs changes expected; if a doc statement is
falsified by a task, file it as a report for the orchestrator (the
FR-041 precedent), do not edit outside your task paths.
