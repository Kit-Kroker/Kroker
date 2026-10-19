# S-batch 2026-10-19: eight triaged inbox tasks, one crew run

Triage 2026-10-19 (orchestrator): 15 S-sized inbox candidates read; 8
accepted to this batch, the rest deferred with reasons in their task files.
One task per commit, TDD (qa seats write the failing tests first), reviewer
gate per task BLOCKING. Branch `sbatch-2026-10-19` off main (a8361b85).

## Global stop-guards (binding; clearance only from the orchestrator)

- SG-1: NO golden re-records, NO fixture regeneration, NO
  SDLC_CAPTURE_HISTORIES runs. If a change moves anything a golden or a
  prompt-sha comparison reads — STOP and report.
- SG-2: `test_prompt_migration.py::test_prompt_shas_did_not_move` and 28
  other fast-tier failures are PRE-EXISTING on main (proven 2026-10-19 by
  reverting the FR-041 branch files in-tree; list:
  `.workspace/tmp/fr041-failures.txt`). A pre-existing failure is not
  yours to fix and not yours to cause to fail differently — if one of
  YOUR touched files is in that list, note it in the task report.
- SG-3: gates before every commit: `uv run pytest` (compare failures
  against the SG-2 list — no NEW failures), `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy`,
  `uv run python scripts/check_file_size.py`; replay tier is
  `uv run pytest -m temporal tests/replay` (run once at the end of the
  batch, before the last commit).
- SG-4: paths per task as listed; anything else → stop and report.
- SG-5: commit messages: subject + body, `git commit -F <msgfile>`, one
  path per git add, NO attribution trailers of any kind.

## Tasks

### T1 Judge: stop stacking SDK retries (`single_retry_layer`)

- File: `.workspace/tasks/2026-10-02-benchmark-judge-sdk-retry-stacking.md`
- Paths: `src/sdlc/benchmarks/judge.py`,
  `tests/durability/` (coverage + bound tests)
- Facts (verified by orchestrator): the judge agent is built in
  `_run_judge_agent` (`judge.py:186-207`) with `model = resolve_model(model)`
  whose docstring says "SDK retries keep their default" (`model_ids.py:90`);
  the wrapping activity allows 5 attempts (`benchmark_host.py:35`) → up to
  15 HTTP calls. The activity-level `_JUDGE_RETRY_DELAYS` backoff loop
  STAYS (it is the e9b732d1 hardening).
- Fix shape: make the judge's model resolve through the single-retry layer
  the way proposer sites do (`single_retry_layer()` capability or the
  resolver path it installs). Bound check: point the judge at the
  always-429 stub (`tests/durability/_http_stub.py`) and assert requests
  per judge call <= the activity budget.

### T2 check_ui wrapper: per-test timeout under load

- File: `.workspace/tasks/2026-10-03-check-ui-wrapper-timeout-flake.md`
- Paths: `scripts/check_ui.py`
- Fix shape: pass an explicit `--testTimeout` (decide the value from the
  recorded matrix: jsdom setup alone ~30 s in kroker-dev) or a
  deterministic warm-up in the wrapper — your call, justified in the
  commit body. Do NOT touch vitest configs or test files.

### T3 `get_task_diff` 60k cut carries a visible marker

- File: `.workspace/tasks/2026-10-03-silent-patch-cut-no-marker.md`
- Paths: `src/sdlc/vcs/git.py` (+ tests)
- Fix shape: copy the oracle's pattern (`benchmarks/oracle.py:107`): when
  the diff is cut, append a visible truncation marker; do not change what
  is kept. All four callers use the default — no caller changes expected.
- CAUTION: if any test compares prompts containing diffs, the marker can
  surface there — that is a NEW failure you must fix in the test's
  expectations only if the test is about this behaviour; otherwise STOP
  and report (SG-1).

### T4 Research SQ: dead `non_retryable_error_types`

- File: `.workspace/tasks/2026-10-05-dead-non-retryable-config-research-sq.md`
- Paths: `src/sdlc/stages/research/step.py` (+ test if the removal is
  behaviour-visible)
- Read the current sub-question handler shape first: the activity returns
  a degraded finding instead of raising on cap stops, so the workflow-side
  list cannot trigger. Remove the dead list, or if it is belt-and-braces
  against future handler refactors, keep it and document why in a comment.
  Decide and justify in the commit body.

### T5 Dashboard: fleet poll survives a failed first read

- File: `.workspace/tasks/2026-10-05-fleet-refresh-failure-stops-the-poll.md`
- Paths: `interfaces/dashboard/frontend/src/shared/fleet.store.ts`,
  `src/app/App.vue` (+ a component/store test)
- Fix shape: mirror 010's inbox treatment (research R-6): `refresh` never
  rejects, add `loaded` / `loadError`, a fleet view state for "could not
  be loaded", and start the poll unconditionally. UI gate for touched
  frontend: `python scripts/check_ui.py`.

### T6 Registry packaging test: probe env needs the dummy keys

- File: `.workspace/tasks/2026-10-05-registry-packaging-slow-test-needs-exa-key.md`
- Paths: `tests/test_registry_packaging.py`
- Test-only. Give the probe environment the same dummy keys
  `tests/conftest.py` sets for import-only (EXA_API_KEY at minimum; add
  others the run reveals). Keep `PATH: ""` and the out-of-repo cwd — they
  are what the test is about. Run the test (marker `slow`) to green.

### T7 Research agent: output retries above 1

- File: `.workspace/tasks/2026-10-05-research-agent-output-retries-1.md`
- Paths: where the research agent is constructed (follow
  `src/sdlc/agents/roles.py`; the assessment's live error string was
  "Exceeded maximum output retries (1)") (+ test)
- Fix shape: raise `output_retries` to a justified value (state the
  number and why in the commit body). The deeper "retry must not consume
  request budget" mechanism stays out of scope.

### T8 Research judge on the refine-crash path: confirm + wording

- File: `.workspace/tasks/2026-10-04-research-judge-uses-rebound-brief-on-refine-crash.md`
- Paths: `src/sdlc/stages/research/AGENTS.md` (or the nearest AGENTS.md
  that carries the imprecise bullet); a test ONLY if the confirmation
  shows a real mispairing (then STOP and report before fixing).
- Fix shape: trace which brief the judge call and the returned
  `ResearchOutcome` read on the path where a refine round's
  `synthesize_brief` returns and `_fold_research_usage` raises
  (`R/step.py`, `brief` vs `verified_brief` vs `brief_digest_val`).
  Expected outcome (hypothesis): the stage judges/returns the rebound
  unverified brief under the old digest — tighten the AGENTS.md wording
  to say exactly that. No behaviour change implied.

## Out of the batch (deferred at triage, do NOT touch)

attempt-budget tuning (needs Temporal-history evidence), gap-strings
(replay-fixture risk), gate-comment persistence (UI library contract),
ssh-agent socket (assessment path), mock-inbox key (deferred by 010 R-9),
role priced-calls (wire revision), 009 verify-helper (closed at triage —
lesson recorded in its task file).
