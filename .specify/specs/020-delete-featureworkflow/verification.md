# Verification: Delete FeatureWorkflow After Grace-Retention (round 020)

Executor record. Commands run in the active worktree (PR-1: `../Kroker-020-1`
on `020-delete-featureworkflow`; PR-2: `../Kroker-020-2` on
`020-delete-featureworkflow-2`) unless a section says otherwise.

Note on pytest output: this environment's pytest prints no final
`N passed` summary line; exit status plus the progress line are the record.

## §Baseline (T002)

Worktree `../Kroker-020-1` created from `main` at `4f6fc2c3` on branch
`020-delete-featureworkflow`; `uv sync --frozen --extra dev` completed.

`uv run pytest -q` (fast tier) — 8 failures, the known-failure list every
later run is compared against:

```text
FAILED tests/test_benchmark_acceptance_stalled.py::test_sc003_recompute_stored_acceptance
FAILED tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-hone]
FAILED tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-particle-swarm-optimization]
FAILED tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-stocktrends]
FAILED tests/test_prompt_migration.py::test_prompt_shas_did_not_move
FAILED tests/test_read_fixtures_fresh.py::test_committed_recordings_equal_a_fresh_build
FAILED tests/test_read_fixtures_fresh.py::test_pristine_copy_passes_the_record_check
FAILED tests/test_todo_api_case_loads.py::test_todo_api_case_file_exists_and_loads
```

`uv run pytest -m temporal tests/replay -q` — exit 0, green (2026-11-10).

`uv run pytest tests/replay/test_feature_replay.py -q` — exit 0, green
(20 tests; `test_feature_replay.py` is fast-tier, so it also ran green
inside the `pytest -q` run above).

## §T006 (T006, plan T013, R-7, C2 — calibration pins on the live gate path)

qa-happy wrote the pin tests (tests only, no `src/` change); qa-chaos
adversarially reviewed them and found one live-path gap (no pin for
`auto_decision=auto` / `confidence=confidence` in the in-loop
`ctx.gate` call), which it then pinned as
`test_only_the_in_loop_gate_call_carries_auto_decision_and_confidence`.
Files: `tests/calibration/test_gate_requires_calibration.py`,
`tests/test_soft_gate_auto_approval.py`,
`tests/calibration/test_calibration_plumbing.py`.

Task-text note: the brief named a `judge_error` argument. No symbol
`judge_error` exists anywhere in `src/`; the C7 concern is the
calibration judge's failure degradation (`_calibration_verdict`'s
`except Exception` → `INSUFFICIENT`), which the pins cover via the
consult-path and lookup-failure tests.

Non-vacuousness proof (executor-run, scratch copy from
`git archive HEAD` + the three modified test files, both source files
restored before each mutation; each mutation applied exactly once):

```text
m1a author_model=author removed (in-loop call)  -> FAILED test_gate_requires_calibration.py::test_gate_node_plumbs_author_model_into_both_gate_calls
m1b author_model=author removed (final call)    -> FAILED test_gate_requires_calibration.py::test_gate_node_plumbs_author_model_into_both_gate_calls
m2 SOFT+confidence predicate deleted             -> FAILED test_soft_gate_auto_approval.py::test_gate_node_reads_calibration_only_under_the_verbatim_soft_predicate
                                                   FAILED test_soft_gate_auto_approval.py::test_the_consult_sits_inside_the_predicate_block_not_after_it
m3 precode plan-node resolved_model -> None      -> FAILED test_calibration_plumbing.py::test_precode_hands_the_resolved_model_to_both_producer_results
m4 author not read from stored payload           -> FAILED test_gate_requires_calibration.py::test_gate_node_takes_the_author_from_the_stored_payload
m5 auto_decision=auto removed (in-loop call)     -> FAILED test_gate_requires_calibration.py::test_only_the_in_loop_gate_call_carries_auto_decision_and_confidence
m6 confidence=confidence removed (in-loop call)  -> FAILED test_gate_requires_calibration.py::test_only_the_in_loop_gate_call_carries_auto_decision_and_confidence
restored -> 35 passed, exit 0
```

qa-chaos ran the same class of mutations independently (m1–m4 plus the
m5/m6 gap before it was pinned) with the same outcome. Green on the real
source: 35 passed, exit 0; `ruff check` clean on the three files.

### §Baseline addendum (recorded at T007)

The T002 baseline covered the fast tier and `tests/replay` only. The
durability temporal tier was first run at T007 and carries **3
pre-existing failures on `main`** (each reproduced in the primary
checkout `/home/maksim/work/Kroker` at `4f6fc2c3`, untouched by this
branch — all three are live-capture-vs-frozen-recording comparisons
already drifted on `main`):

```text
FAILED tests/durability/test_priced_usage_parity.py::test_live_priced_usage_matches_the_frozen_recording
FAILED tests/durability/test_provider_payload_parity.py::test_provider_request_messages_match_the_frozen_capture
FAILED tests/durability/test_wire_neutrality.py::test_no_override_wire_equals_the_frozen_baseline
```

The priced-usage drift: live 6th tuple `('zai:glm-5.3', 314, 28, 0, 0)`
vs frozen `('zai:glm-5.3', 195, 24, 0, 0)`. **Flagged for T020/T026**:
re-pointing the live leg against the pre-e74 anchors (T007 fixture,
wire baseline) will meet this same drift; needs an orchestrator ruling
before Phase 6.

## §T007 (T007, plan T014, R-5 — pinned constants)

qa-happy authored, qa-chaos adversarially verified (4 mutations, each
failing exactly its pin; fixture confirmed raw — `_RECORDED_MODEL_MAP`
is not applied and is in fact inert for `price_usage` today).

1. `tests/durability/fixtures/priced_usage_pre_e74.json` — 6 raw
   `price_usage` tuples from the current FeatureWorkflow
   `greenfield_happy` recording. One-off extraction command (scratchpad
   script, not committed):
   `EXA_API_KEY=test-dummy ANTHROPIC_API_KEY=test-dummy OPENAI_API_KEY=test-dummy ZAI_API_KEY=test-dummy PYTHONPATH=. uv run python <scratchpad>/extract_priced_usage.py`
2. `test_pinned_tuples_match_the_recorded_history` — fixture equals the
   decoded recorded history, raw. Green.
3. `MEMO_PARITY_KEYS` in `tests/replay/test_graph_golden.py` — 3
   `content_key` tuples (clarify, architect, plan) frozen verbatim from
   one run of the FeatureWorkflow leg (temporary MEMO_DUMP print, removed
   after; constant generated with ast.literal_eval).
4. Both live legs asserted `== MEMO_PARITY_KEYS` (green on two runs).

Commanded verification `pytest -m temporal tests/durability
tests/replay/test_graph_golden.py -q`: exit 1 with exactly the 3
pre-existing §Baseline addendum failures; both new pinned tests green.
Pinned tests are temporal-marked (`-m ""` selects them when run alone).

## §PR-1 (T014, plan T019) — executor STOP follows this record

Quickstart §1, in full (worktree `../Kroker-020-1`):

```text
pytest tests/test_dashboard_fleet.py tests/test_dashboard_fleet_marks.py \
       tests/test_dashboard_fleet_summary.py tests/test_read_fixtures_fresh.py \
       tests/test_channel_inbox.py tests/test_inbox_query.py -q
  -> only the 2 pre-existing test_read_fixtures_fresh failures (of the 8 known)
pytest tests/calibration tests/test_soft_gate_auto_approval.py -q
  -> 21 passed
(cd interfaces/dashboard/frontend && npm test -- src/api/http.test.ts)
  -> 37 passed (legacy row renders "legacy run, summary unavailable")
pytest -q && ruff check . && ruff format --check . && mypy
  -> ruff check: pass; ruff format --check: 1909 files formatted; mypy: clean
```

Expected §1 behaviours are pinned in the suites: a fake closed
`FeatureWorkflow` row yields one `closed_legacy` entry with zero handle
calls and `errors == []` (test_t008a), a None-typed row is still queried
(test_t008d), the frontend renders the legacy title (http.test.ts).

Full fast tier vs the §Baseline list: **exactly the same 8 ids, nothing
new** (test_benchmark_acceptance_stalled, test_deveval_corpus ×3,
test_prompt_migration, test_read_fixtures_fresh ×2,
test_todo_api_case_loads).

`pytest -m temporal tests/replay tests/durability -q`: `tests/replay`
fully green — **`tests/replay/test_feature_replay.py` is green** (it is
fast-tier and also green there); the only failures are the 3
pre-existing §Baseline-addendum durability drifts.

Two comparison fixes landed under T014 (both found by the §Baseline
comparison):
- `interfaces/dashboard/frontend/src/api/__fixtures__/fleet-snapshot.json`
  regenerated with `python scripts/dump_dashboard_fixtures.py` (the
  additive `closed_legacy: []` wire field; never hand-edited);
- `tests/test_tidyup_cli_wiring.py::test_approve_reaches_a_tidyup_workflow_unchanged`
  narrowed to its documented intent (transport **imports** nothing
  workflow-specific): transport legitimately names FeatureWorkflow since
  T013's LegacyRunError check, as SC-002's allowed list anticipates.

**Integration note (for T015)**: from PR-1 on, closed FeatureWorkflow
rows render as `closed_legacy` rows ("legacy run, summary unavailable")
and are never queried, while the type is still registered (Q1 = A).
PR-1 changed nothing any registered workflow executes.

Environment note: the machine had no Node; a userspace Node v22.20.0
was installed at `~/.local/node` (symlinked into `~/.local/bin`) to run
vitest.

**Executor STOP: hands back to the orchestrator for T015 (fast-forward)
and T016 (gate run 1). T017 resumes only on a gate PASS.**




## Gate-1 (T016), run by the orchestrator 2026-11-10

Target: compose dev server `kroker-temporal-1` on `127.0.0.1:7233`, namespace
`default`, **freshly created on this host** (no docker volumes or images
existed before; volume `kroker_temporal-state` created at 15:33:23Z).
The `temporal` CLI was run inside the server container. `main` = `0e38a6db`
(PR-1 fast-forwarded, 2026-11-10).

Verbatim output:

```
$ date -u
2026-11-10T15:33:42Z
$ docker inspect -f ... kroker-temporal-1
891351c9f8a2a043f38586fcdffe26f33818a5f173597f7c984e018e0dd250b4 2026-11-10T15:33:23.878559431Z
$ git rev-parse HEAD
0e38a6dbbb349b2387daab9f7859dfe7c5b906e4
$ G0 count
Total: 0
$ G0 schedule list
  ScheduleId  Action  Paused  NextRunTime  LastRunTime
$ G1
$ G2
```

**Result: FAIL (pass rule 1).** G1 and G2 are empty, but G0 reports
`Total: 0` workflows and no schedules, and the runbook says a store with
zero workflows is the wrong store. No override. Substantively nothing is
running on this store, but this store has never held a run, so the gate
says nothing about the store the 2026-10-02 triage queried (it was on the
earlier Windows host, `D:/own/Kroker/runs`). T017 does not start until the
user rules on which store the restarted worker will point at.

## Orchestrator rulings (2026-11-10)

1. **Gate-1 store ruling (user, option 1):** this host's compose store
   (`kroker-temporal-1`, volume `kroker_temporal-state`) is the only store
   the restarted worker will use. The earlier Windows-host store is out of
   scope. Pass rule 1 (`Total: 0` = wrong store) is therefore treated as an
   **accepted exception for this store**: the store is correct and empty,
   so nothing can be stranded. G1 and G2 were empty. **Gate-1 is cleared;
   T017 may start.** Gate run 2 (T036) is still required, under 1 hour
   before the worker restart, and the restart still needs the user's
   explicit go.
2. **Durability drift (orchestrator, seat-level):** the three
   §Baseline-addendum failures are a known failing baseline. This round
   does not re-record frozen baselines. PR-2 must keep exactly these three
   failing and add no others. A re-pointed test (T020/T026) that inherits
   the same drift is recorded by test id against this baseline, not fixed
   by editing a frozen recording.
