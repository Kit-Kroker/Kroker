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

## §T018 (T018, plan T041 — re-capture from GraphWorkflow)

Worktree `../Kroker-020-2`, branch `020-delete-featureworkflow-2`, HEAD
`481bf756` (T017). `git diff --stat main -- src/` empty before the
re-capture, as the task requires. No commit of its own: T019 commits the
re-captured fixtures together with the gate script and the diff.

Commands and results (full outputs under the session scratchpad):

```text
$ SDLC_CAPTURE_HISTORIES=1 uv run pytest -m temporal tests/replay/test_capture_graph.py -q
..................                                                       [100%]
exit=0                                            (/tmp/opencode/t018-recapture-full.txt)

$ SDLC_CAPTURE_RESEARCH_RETAIN=1 uv run pytest -m temporal tests/replay/test_research_retain_replay.py -k capture -q
.                                                                       [100%]
exit=0                                            (/tmp/opencode/t018-research-retain.txt)

$ git status --short tests/replay/histories tests/replay/golden
```

Exactly 19 histories and 18 goldens modified, nothing else.
`golden/assessment_discover_risk.json` (AssessmentWorkflow) and the three
non-Feature histories (`architect_research_usage` GraphWorkflow,
`assessment_discover_risk` AssessmentWorkflow, `benchmark_one_cell`
BenchmarkWorkflow) untouched. `research_retain_grounded.json` now carries
`workflow: GraphWorkflow`, `source_commit: 481bf756...` (= HEAD); its pin
test `test_fixture_holds_the_grounded_retain_path` is green (RED was
confirmed first: it failed on the `workflow == "GraphWorkflow"` assertion
while the fixture still said FeatureWorkflow).

Test edit in `tests/replay/test_research_retain_replay.py`: capture test
switched to `GRAPH_STARTER` (both captures and the `"workflow"` field),
the fixture pin re-pointed to `"GraphWorkflow"`, and the two docstrings
that named FeatureWorkflow as the capture source updated to record the
020 T018 re-capture. Executor-made (mechanical re-capture edit, PR-1
T004/T005 convention), RED verified personally.

**Known red window T018 → T021 (fast tier, by construction of the plan).**
The re-captured fixtures are GraphWorkflow histories, but `replayer()`'s
default tuple keeps FeatureWorkflow until T021 swaps it. Until then these
legs fail with `Workflow class GraphWorkflow is not registered on this
worker` — a registration gap, never a command-sequence change (SG-2/SG-3
intact; §T019's gate is the behavioural proof):

```text
FAILED tests/replay/test_feature_replay.py::test_feature_workflow_replays_captured_history[<the 18 scenario ids>]
FAILED tests/replay/test_research_retain_replay.py::test_retain_decisions_do_not_depend_on_page_files[present|absent|overwritten]
```

`test_feature_replay.py` is deleted by T021 and the default tuple gains
GraphWorkflow there, closing the window before the next full `pytest -q`
comparison (T026). The tasks' commanded runs between T018 and T021 are all
`-m temporal` selections, which do not collect these unmarked tests.

Note on a first capture attempt: one full capture run exited 1 with all 36
fixture files written and no failed ids in pytest's `lastfailed` cache; a
`tail -5` pipe had clipped the summary. A clean re-run (above) exited 0
with 18/18 passed, and the run-1 stash was dropped only after run 2
succeeded.

### §T018 qa-chaos findings, dispositioned

qa-chaos's adversarial pass (report: scratchpad `qa-chaos-t018-report.md`)
confirmed all six claims (19/19 histories re-provenanced, 18/18 goldens
differ only in `workflow`/`source_commit` with zero nested diffs, untouched
files equal HEAD, no durability change, `src/` clean) and raised two
findings:

1. **`read_dead_attempt_usage` appears once in the re-captured
   `research_retain_grounded.json` history; the d51eef5-era fixture did
   not schedule it.** Control experiment: a scratch tree from
   `git archive HEAD` (FeatureWorkflow capture path, unmodified by this
   round) captured the same scenario from **FeatureWorkflow at HEAD** — it
   schedules `read_dead_attempt_usage` too. The delta is drift since the
   009-era fixture (the activity post-dates d51eef5 and was never
   re-recorded), not a Feature-vs-Graph behavioural difference; the
   Graph-vs-Feature activity-set difference at HEAD is empty. SG-3's
   substance (retain decisions independent of page files) is unaffected;
   the 1/1/3 retain-shape pin is green.
2. **The new histories carry this capture host's identity
   (`118474@maksim` / `119829@maksim`).** Precedent: every committed
   history carries its capture host's `uid@hostname` on the
   workflow-start event (`76557@578983243cbc`, `8@81b9e475e609`,
   `5208@7eab75073822` — earlier captures ran in containers); the owner's
   name is already in the git log. Fixtures are written only by the
   capture tests (020 T032 codifies this), so no hand-scrub. Left as-is.

## §T019 (T019, plan T042, FR-011, SC-003 — golden diff gate)

qa-happy wrote `tests/test_check_golden_rebaseline.py` first (9 cases on
the pure core, `tests/test_check_file_size.py` convention: no git, no
tree writes). RED verified personally: collection error
`ModuleNotFoundError: No module named 'scripts.check_golden_rebaseline'`.
The executor then implemented `scripts/check_golden_rebaseline.py`
(no arguments; per golden, `git show HEAD:<path>` vs working tree;
`ALLOWED_KEYS = {workflow, source_commit}`; exits 1 naming file and key;
also names goldens deleted from the tree or absent from HEAD).

```text
$ uv run pytest tests/test_check_golden_rebaseline.py -q
.........                                                               [100%]
$ uv run ruff check scripts/check_golden_rebaseline.py tests/test_check_golden_rebaseline.py
All checks passed!
$ uv run python scripts/check_golden_rebaseline.py
golden re-baseline gate: 19 goldens differ only in ['source_commit', 'workflow']
exit 0
```

Non-vacuousness (executor-run mutation check): with one golden's `trace`
mutated, the gate exits 1 with
`tests/replay/golden/greenfield_happy.json: trace`; after byte-identical
restore (cmp-verified) it exits 0 again.

`git diff tests/replay/golden/` written to
`F/golden-rebaseline.diff`: 18 files, 359 lines, and zero +/- content
lines outside the `workflow`/`source_commit` pairs (grep-verified).

**Exit 0 — not a STOP.** Committed with the re-captured fixtures per the
task's instruction (one commit: fixtures + script + test + diff).

qa-chaos adversarial pass (report: scratchpad `qa-chaos-t019-report.md`):
the diff artefact regenerates byte-identical, the script's only
comparison is the tested core, usage guard exits 2, none of the 9 cases
vacuous. Findings and dispositions:
- **F1 type-blind equality (fixed):** Python `1 == True`, `1 == 1.0`,
  `0 == False`, so a JSON type change passed the gate. qa-happy pinned
  it RED-first (`test_a_json_type_change_is_reported`,
  `test_nan_values_are_not_a_diff_when_identical` — both failed against
  the old core), then the executor switched `golden_diffs` to canonical
  JSON comparison (`json.dumps(..., sort_keys=True)`), which also makes
  key order a non-diff and identical NaNs equal (F2). 13/13 green after.
- **F3 empty corpus (fixed):** `check()` now exits 1 when there are no
  goldens to gate.
- F4 (post-commit the gate passes vacuously against the new HEAD) is by
  design; `F/golden-rebaseline.diff` is the durable record. F5/F6
  (non-JSON HEAD content or a git failure gives a traceback or a
  misleading "not in HEAD" message) fail closed and stay. F7 (namespace
  package import) matches the existing `scripts.check_file_size`
  convention.

## §T020 (T020, plan T043 — replay suite re-pointed at GraphWorkflow)

qa-happy authored all edits (report: scratchpad `qa-happy-t020-report.md`),
executor reviewed the diffs personally. Files:

- **NEW `tests/replay/test_graph_replay.py`** (US4 proof): parametrised
  over `SCENARIOS`; each history replays through
  `replayer(GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow)` with
  `raise_on_replay_failure=True`. No temporal mark (follows
  `test_feature_replay.py`). 18 passed. Non-vacuousness: in a scratch
  copy of HEAD the tuple was changed to drop GraphWorkflow → 18 failed
  with the registration error (qa-happy, scratch deleted after).
- `tests/replay/test_fixtures_present.py`: expects
  `workflow == "GraphWorkflow"`; renamed
  `test_fixture_is_present_and_from_graph_workflow`; 19 passed.
- `tests/durability/test_inflight_resume.py`: `_replayer()` and the live
  worker register GraphWorkflow; the live start uses
  `GraphWorkflow.run` + `build_run_input(...)` mirroring
  `harness._start_graph`. `test_old_prefix_replays_on_new_code` green.
- `tests/durability/test_priced_usage_parity.py`: live leg `GRAPH_STARTER`;
  the frozen side is the RAW T007 fixture (no map); comparison kept
  exact; dead `_recorded_price_tuple` removed.
- `tests/replay/test_graph_golden_chaos.py`: the activity-skew filter
  (`build_trace_inventory`/`read_dead_attempt_usage`) deleted — after the
  T018 re-capture the pairs come from one capture and equality holds
  outright. 36 passed.
- `tests/review/test_review_step_shadowing_chaos.py`: `_replay_chain`
  registers GraphWorkflow. 3 passed.
- `tests/replay/test_architect_research_usage_replay.py`: **untouched**
  — never imported FeatureWorkflow; already graph-native and green.

**Commanded verification** `pytest -m temporal tests/replay
tests/durability tests/review -q` (exit 1, exactly four failures, all
the same known 6th-tuple drift — live/re-captured `(zai:glm-5.3,
314, 28, 0, 0)` vs frozen anchor `(zai:glm-5.3, 195, 24, 0, 0)`):

```text
FAILED tests/durability/test_priced_usage_parity.py::test_live_priced_usage_matches_the_frozen_recording   [known baseline 1/3]
FAILED tests/durability/test_priced_usage_parity.py::test_pinned_tuples_match_the_recorded_history          [inherits the same drift — recorded by test id per the 2026-11-10 ruling]
FAILED tests/durability/test_provider_payload_parity.py::test_provider_request_messages_match_the_frozen_capture  [known baseline 2/3]
FAILED tests/durability/test_wire_neutrality.py::test_no_override_wire_equals_the_frozen_baseline           [known baseline 3/3]
```

Everything else in the three trees is green. No new failure outside the
ruling's sanctioned set: the 3 §Baseline-addendum ids plus one re-pointed
anchor test inheriting the identical drift, recorded here by id.

Fast tier after T020 (`pytest -q`, 29 failures = 8 §Baseline ids + the
21 remaining T018→T021 window members: `test_feature_replay.py` ×18 and
`test_research_retain_replay.py` ×3, both closed by T021). The T020
re-points closed the other 22 window failures (fixtures_present ×18,
inflight_resume ×1, review_step_shadowing_chaos ×3). `ruff check .`,
`ruff format --check .` (1913 files), `mypy` (412 files) and
`scripts/check_file_size.py` all clean.

qa-happy also noted the anchor question (refresh 195→314 vs investigate):
settled by the orchestrator ruling — no re-record; the drift is era drift
(the live FeatureWorkflow leg at 4f6fc2c3 already produced 314/28, per
§Baseline addendum), not a graph delta.

## §T021 (T021, plan T044 — Feature replay retired)

Mechanical deletion task (pure-deletion convention, PR-1 T004/T005
precedent; executor-direct, verified by the suites):

- deleted `tests/replay/test_feature_replay.py` and
  `tests/replay/test_capture_feature.py` (`git rm`). Collateral noted:
  the file also carried `test_replayer_matches_the_production_worker_effect`
  (the sandbox/passthrough pin is independently held by
  `tests/durability/test_sandbox_module_marking.py`) and the assessment
  replay leg (assessment histories remain replay-covered by the capture
  twin's round trip; T003's reviewer-approved classification ruled the
  file delete with `test_graph_replay.py` as counterpart).
- `tests/replay/harness.py`: `_start_feature`, `_feature_workflows` and
  `FEATURE_STARTER` deleted; `_default_replay_workflows()` swaps its
  FeatureWorkflow member for GraphWorkflow (per the T004 comment's own
  schedule), closing the research-retain replay legs.
- `tests/replay/test_graph_golden.py`: the memo-parity test drops its
  FeatureWorkflow leg (renamed
  `test_memo_key_inputs_match_the_pinned_keys`) and asserts the live
  GraphWorkflow keys `== MEMO_PARITY_KEYS` outright, plus the watermark
  check; module docstring re-anchored to the re-baselined goldens.
  (Process note: the executor's first harness edit mangled the file —
  it briefly deleted `replayer()` with the Feature block — caught
  immediately by an `ast.parse` + symbol grep and repaired before any
  test run; the committed state is the repaired one.)

```text
$ uv run pytest -m temporal tests/replay -q
exit=0, no FAILED, no ERROR                          (/tmp/opencode/t021-verify.txt)
$ uv run ruff check / format --check (harness.py, test_graph_golden.py)
clean
```

**Known fast-tier state after T021 until T026's migrate commit:**
`pytest -q` is interrupted by exactly two collection errors —
`tests/test_model_forwarding.py` (imports `FEATURE_STARTER`) and
`tests/durability/test_wire_neutrality.py` (via `wire_dump.py`, same
import). Both are `migrate`-class in the T003 inventory and are
re-pointed by T026's migrate commit, by design. No test executes while
they are broken, so T026's per-commit `pytest -q` comparison is
meaningful only from its migrate commit onward (recorded there).

## §T022/§T023 (plans T046 — replay-safe restart, R-1)

T022 (qa-happy authored, RED verified personally): the stripped-marker
replay test in `tests/replay/test_benchmark_replay.py` and the rewritten
`tests/graph_workflow/test_pipeline_child_upgrade.py`. qa-happy
corrected two of the brief's assumptions: on fresh (non-replay)
executions `workflow.patched()` returns True, so the new-parent
integration test is a regression guard (passes today), not a RED test;
and the on_graph unit test's RED is the patched()-outside-workflow call.

T023 (executor implemented): `S/workflows/pipeline_child.py` replaces
`if workflow.patched(...)` with `workflow.deprecate_patch(...)`, starts
GraphWorkflow unconditionally, deletes the else branch and the
FeatureWorkflow import; docstring records the deprecation and the
standing item.

TDD evidence (the strip needed two executor corrections before the RED
reason was the task's predicted one — a patched() first-encounter
issues BOTH a marker and a TemporalChangeVersion upsert, so the strip
must drop the marker AND the no-new-information upserts, rewriting the
lists of later upserts that legitimately re-list the patch):

```text
RED (src stashed, pre-T023, final test shape):
  TMPRL1100: child workflow type of scheduled event 'GraphWorkflow'
  does not match child workflow type of command 'FeatureWorkflow'
GREEN (T023 src): .... [100%] exit 0
  (test_benchmark_workflow_replays_one_cell_history,
   test_replays_with_the_e74_marker_stripped,
   test_a_new_parent_starts_graph_children_and_its_history_replays,
   test_on_graph_fires_once_with_content_sha_before_the_child_starts)
```

The on_graph unit test now also pins the R-1 call itself:
`deprecate_patch("e74-graph-child:child-1")` exactly once (it
monkeypatches the workflow-only API, as the unit test runs outside a
workflow). `ruff check`/`format --check` on the three files,
`scripts/check_file_size.py`, and `mypy` (412 files) all clean.

## §T024 (T024, plan T045, FR-005 — FeatureWorkflow leaves the inbox types)

qa-happy authored the tests first (report: scratchpad
`qa-happy-t024-report.md`); six tests RED against the then-src, all with
the same assertion tail (`FeatureWorkflow` still in the visibility
query). One brief deviation accepted as correct: the Crew assertion
lives in the fetch_inbox-specific tests, because `list_open_run_ids`'s
default is Graph-only (the executor's brief had over-specified the
shared stub). Executor then changed `S/channels/inbox.py`:
`list_open_run_ids` default `("GraphWorkflow",)`; `fetch_inbox` uses
`("GraphWorkflow", "CrewTaskWorkflow")`; module and function docstrings
record the 020 change and point at the fleet's legacy rows for closed
FeatureWorkflow runs.

```text
RED:  6 failed, 11 passed   (FeatureWorkflow-in-query on all six)
GREEN: ......................... [100%]  (17/17 across both files)
```

Fleet callers unaffected (`dashboard/fleet.py` uses the no-types default
and lists RUNS; its closed-legacy queries are PR-1's and untouched):
`tests/test_dashboard_fleet*.py` 52/52 green. ruff/format clean.

## §T025 (T025, plan T050, FR-003 — FeatureWorkflow deleted)

Executor-direct deletion (T021 precedent), pin first:
`test_worker_registers_the_post_020_workflow_set` (ast-pins the
`Worker(...)` workflows literal to the eight remaining names) was RED
against the then-src (`FeatureWorkflow` still registered), then
`S/workflows/feature.py` was `git rm`'d and `S/worker.py` lost its
import, its registration and the docstring's FeatureWorkflow mention.

```text
RED:  test_worker_registers_the_post_020_workflow_set (assertion on
      'FeatureWorkflow' not in registered)
GREEN: pytest tests/test_worker_registration.py
         tests/graph_workflow/test_cold_import.py
         tests/graph_workflow/test_store_import_pin.py -q
      ........... [100%] exit 0
```

`import sdlc.worker` OK (with the CI dummy keys the registry requires —
bare import fails closed on EXA_API_KEY by design). ruff, format,
mypy (411 files — feature.py gone), check_file_size clean. Pre-check:
the only `src/` import of `workflows.feature` was worker.py; the three
other mentions (sc_rollup.py, notify/render.py, plan/validation.py) are
comments/docstrings only — T033's sweep rewords them. The wider
`tests/` fallout (delete/migrate classes) is T026's, per the inventory.

## §T026 (T026, plan T070 — the classification executed)

Three commits by class, plus what earlier tasks already executed:
- **delete (2 rows)** — executed by T021's commit `7b10e5c9`
  (`test_feature_replay.py`, `test_capture_feature.py`, counterparts
  named in that commit's body). No files remained for a T026 delete
  commit.
- **migrate + repoint (this T026, 54 + 5 files)** — see below.
- **comment-only (11 files)** — prose reworded where it would mislead
  post-deletion; historically-accurate mentions kept.

Executor-direct mechanical sweep (PR-1 T004/T005 convention) with
qa-happy executing nine inventory rows as batch A (report: scratchpad
`qa-happy-t026a-report.md`); everything else executor-made. Notable
judgment calls, all verified green in real temporal runs:
- `test_feature_brownfield_stages.py` became a pure fakes module
  (SCAN_FAKES/BROWNFIELD_SPECS/fake_resolve_tree verbatim — see the
  incident note below); its full-run rows cite the brownfield/intake
  goldens.
- `test_research_e2e.py` drives GraphWorkflow by NAME (status/
  answer_question/submit_gate_decision); by-name `run_summary` queries
  are validated with `RunSummary.model_validate`, `pending_decisions`
  with `TypeAdapter(PendingDecision)` (by-name queries return raw JSON).
- `test_gate_timeout_action.py`'s HOLD row registers a quiet notify
  fake: under GraphWorkflow the HOLD reminder calls the shared gate
  host's notify activity (module-level imports — `activity.defn`
  resolves annotations at registration, outside function scope).
- `wire_dump.py` re-points to GRAPH_STARTER but the frozen
  `wire_no_override.json` is KEPT per the orchestrator ruling (no
  re-record of frozen baselines); `test_wire_neutrality` keeps its
  known failing id.
- `test_seeded_work.py`: the FW.run third-argument pin became the
  catalog pin (`select_graph(...) is SHIPPED["seeded"]`,
  `build_run_input(...).seeded == seeded`); the temporal skip proof is
  deleted citing the `seeded` golden. Same citation pattern for
  `test_feature_delta_gate.py`'s exhausted-retries row (delta_failed
  golden) and the brownfield full-run rows.
- The `FEATURE_PY` cluster (factory_purity + memoization/memory
  wiring/purity) moved to GRAPH_MODULES scans; the graph-modules memory
  sweep flags direct `execute_activity(recall_snapshot|retain)`
  scheduling only — `ctx.recall/ctx.retain` via the host is sanctioned.
- `test_analyst_stage_wiring.py`'s ordering row became an edge-
  reachability assertion on the shipped graph (node lists are
  normalized alphabetically, so index order would be vacuous).
- Five by-path readers the T003 grep classes missed were fixed the same
  way: `test_review_wiring.py`, `test_deep_review_wiring.py` (feature.py
  dropped from the SRC concat), `test_feature_residual.py` (ceiling row
  deleted with the file), `test_module_imports.py` (imports graph),
  `test_role_model_resolution.py` (raw-lookup scan over graph.py +
  graph_nodes). Plus the orchestrator-flagged `test_merge_gate_wiring.py`
  (delegation reader → postplan.py) and the inventory's
  `test_integration_checks_wiring.py` (`merge_node`), `test_adversary_
  workflow.py` (feature.py term dropped), `test_waste_population_
  wiring.py`, `test_run_state_query.py` (canonical-name scan over
  graph_nodes), `test_clarify_stage_wiring.py` (requirements-publish
  owner → precode).

### §T026 verification

- Fast tier `pytest -q`: **exactly the 8 §Baseline ids** (diffed
  against the T002 list) — the T021 import window is closed.
- Temporal tier, chunked per the orchestrator's instruction after the
  unchunked run wedged (see incident): every directory green
  (deploy 8, durability 19, graph_workflow 23, replay 56 incl. the
  18 switch-gated skips, research, retro, crew, triage, model-
  forwarding, assessment/benchmark e2e, and the 13 re-pointed root
  e2e files) with exactly the four known priced-usage drift failures:
  the three §Baseline-addendum ids plus
  `test_pinned_tuples_match_the_recorded_history` (recorded by test id
  per the 2026-11-10 ruling). No hangs; `--timeout=180 --timeout-method=thread`
  stood guard on every chunk.
- ruff check/format over the tree, mypy (411 files),
  `scripts/check_file_size.py`: clean.

### §T026 incident: the wedged full-suite run (and the bug it exposed)

The unchunked `pytest -m temporal` wedged at 32% for 82 min (0.8% CPU,
blocked on temporal-test-server); the orchestrator ordered it killed
and the tier re-run in chunks. Chunking isolated the wedge to
`tests/replay/test_graph_golden.py` (2 tests in 600 s; single tests
5.6 s standalone) → `test_graph_workflow_reproduces_the_golden_trace
[brownfield_happy-unsandboxed]` hung. **Root cause: executor error in
T026's first rewrite of `tests/test_feature_brownfield_stages.py`** —
the hand-rebuilt fakes module invented ScanSignalId values
(S5/S6/S7/S8/CI1 for QS1–QS4/SS…) and wrote `confidence=` for
`confidence_contribution=`, silently changing the brownfield scenario's
fakes that `scenarios.py` imports. Fixed by rebuilding the kept region
byte-verbatim from HEAD (`git show`), verified IDENTICAL by diff;
the brownfield golden passes again and the whole file is 32/32 green.
The four early failures in the wedged run were the four known drift
ids (positions 16, 17, 18, 25 = priced×2, provider_payload,
wire_neutrality) — class (a) throughout; nothing was class (b) (no
main-check needed — no unexplained failure remained).

## §T031 / §PR-2 (T031, plan T059) — executor STOP follows

All commands in `../Kroker-020-2` at HEAD `d4470879`:

```text
$ uv run pytest -q
exactly the 8 §Baseline ids (diffed against the T002 list)      (/tmp/opencode/t031-fast.txt)

$ pytest -m temporal tests/durability tests/replay tests/graph_workflow -q
   (chunked per the orchestrator's standing order, --timeout=180 --timeout-method=thread)
   durability: exit 1, exactly the four known priced-usage drift ids
     (test_live_priced_usage_matches_the_frozen_recording,
      test_pinned_tuples_match_the_recorded_history  [ruling-recorded inheritor],
      test_provider_request_messages_match_the_frozen_capture,
      test_no_override_wire_equals_the_frozen_baseline)
   replay:        exit 0                                (/tmp/opencode/t031-replay.txt)
   graph_workflow: exit 0                                (/tmp/opencode/t031-graph.txt)

$ uv run python scripts/check_clauses.py
243 clauses declared, 9 untested (the pre-existing set), 0 dangling

$ uv run ruff check . && uv run ruff format --check . && uv run mypy
All checks passed! · 1910 files already formatted ·
Success: no issues found in 411 source files

$ cd interfaces/dashboard/frontend && npm ci && npm test
Test Files 52 passed (52) · Tests 630 passed (630)   (vitest; node_modules
installed fresh in this worktree — the PR-1 install lived in ../Kroker-020-1)

$ python -c "import sdlc.worker"      (CI dummy keys)
worker import OK
```

No STOP condition is met: no gate FAIL, the golden re-baseline diff is
provenance-only (§T019), and the durability failures are exactly the
known baseline plus its ruled inheritor. **Executor STOP after T034
stands; T035–T037 are orchestrator-only.**

## §T032 (plan T080, FR-013)

`S/workflows/AGENTS.md`: the "Grace edits while FeatureWorkflow is
registered (E-74 U6)" section deleted; every ownership row's
FeatureWorkflow readers/writers re-homed to GraphWorkflow (the four
orphaned attributes — `_base_sha`, `_integration_wt`, `_codebase_map`,
`_integration_head` — re-homed to GraphWorkflow's precode nodes); rule
4 names `GraphWorkflow` and `GateHost`. `T/replay/AGENTS.md` created
with the three replay rules (capture-tests-only writers; GraphWorkflow
re-baselines with the projection diff attached; SG-2/SG-3 stand,
including the never-re-record rule for frozen durability anchors).
Reviewer APPROVE (a6f8c514).

## §SC-002 (T033, plan T081, FR-014)

Every non-historical `FeatureWorkflow` mention under `src/`, the living
docs (`docs/framework.md`, `docs/reference/foundation.md`), the stage
`.md` contracts, `ROADMAP.md`, `PRD.md`, `ARCHITECTURE.md` and root
`AGENTS.md` reworded. ROADMAP FR-1203 records the deletion as done
(2026-11-10, fixtures re-baselined, legacy rows via the fleet
partition); the pipeline-as-data follow-up line records it done; the
obsolete "workflow class is FeatureWorkflow" cosmetic TODO is closed;
ARCHITECTURE's component table, no-switch-back note, tidy-up execute
note and file tree updated (feature.py's tree line deleted); the
user-visible `--help` string in `S/cli.py` reworded. Kept verbatim by
the task's own instruction: E-74 "Landed" prose, PRD OQ-10's resolution
text, and the epic-history lines (ROADMAP P1/FR-904/NFR-9 narrations,
tier docs, mode write-ups, docs/reports).

`grep -rn FeatureWorkflow src/` after the sweep — exactly the SC-002
allowed list, nothing else:

```text
src/sdlc/dashboard/fleet.py:20,63,91,123,211,216,217
src/sdlc/workflows/pipeline_child.py:7          (docstring)
src/sdlc/channels/transport.py:143,146,151,157,167
src/sdlc/core/models.py:512,555,558             (field comments)
```

(Verbatim output retained at scratchpad `sc002-grep.txt`; 16 lines.)
ruff/format clean over `src/sdlc/`; clauses gate unchanged (243/0).

## Gate-2 (T036), 2026-11-10T23:26:47Z

Runbook commands run via `docker exec kroker-temporal-1 temporal ... --address 127.0.0.1:7233 --namespace default`. HEAD `e6b82d4a`.

```
$ date -u
2026-11-10T23:26:47Z
$ docker inspect
891351c9f8a2a043f38586fcdffe26f33818a5f173597f7c984e018e0dd250b4 2026-11-10T15:33:23.878559431Z
$ git rev-parse HEAD
e6b82d4adb98b78c1aad85528ec9fe09aa831a21
$ G0 count
Total: 0
$ G0 schedule list
  ScheduleId  Action  Paused  NextRunTime  LastRunTime
$ G1
$ G2
```

**Result:** G1 and G2 empty, no schedules. G0 count is 0, so pass rule 1 is a literal FAIL (same container as run 1, started 2026-11-10T15:33:23Z). Accepted, not overridden silently: the user ruled in gate 1 that this host store is the only store, and explicitly said go for T036 and the restart. Worker built locally from `main` (`docker compose build worker`) before the gate; restart follows immediately.

### Gate-2 rerun, 2026-11-11T14:59:51Z (first run went stale)

Same container. `workflow count` Total: 0, `schedule list` empty, `workflow list --query "ExecutionStatus='Running'"` empty (covers G1 and G2). Same accepted empty-store exception as above. Worker started immediately after.

## Worker restart (T037), 2026-11-11

`docker compose build worker` from main `e6b82d4a`, then `docker compose up -d worker`. Container `kroker-worker-1` Up; `temporal task-queue describe --task-queue ai-sdlc` shows workflow and activity pollers (`1@5bd1c64557eb`). `docker logs` printed nothing (the "worker running on task queue" line did not appear; pollers are the evidence instead). Dashboard fleet / SC-005 check not yet run.

## Close-out (T038), 2026-11-11

Evidence on `main` after the PR-2 fast-forward and worker restart.

| SC | Result | Evidence |
|----|--------|----------|
| SC-001 | Pass with caveat | Gate 1 (T016, before any deletion commit; first deleting commit is T025 `41c95893`), gate 2 (2026-11-10T23:26Z) and its rerun (2026-11-11T14:59Z, minutes before the worker start). Both gates show G1/G2 empty. G0 count was 0 on both: a literal pass-rule-1 FAIL, accepted by the user's "this host is the only store" ruling. |
| SC-002 | Pass | `grep -rn FeatureWorkflow src/` returns only `dashboard/fleet.py` (closed-run filter, 020 contract §1), `channels/transport.py` (`LegacyRunError`), `workflows/pipeline_child.py` (patch comment) and `core/models.py` comments. `import sdlc.worker` exposes 8 workflow classes (Assessment, Benchmark, CrewTask, Deployment, Graph, Reflect, TidyUp, Triage); no FeatureWorkflow. |
| SC-003 | Pass | §T019: `scripts/check_golden_rebaseline.py` gate plus `golden-rebaseline.diff`. |
| SC-004 | Pass | `pytest -m temporal tests/replay`: 35 passed, 21 skipped (all skips are capture-on-demand tests), 0 failed. |
| SC-005 | Pass (fake client) | `tests/test_dashboard_fleet.py`, `test_cli_legacy_run.py`, `test_operator_errors.py`, `test_worker_registration.py`: 57 passed. Not exercised live: the compose store holds 0 workflows, so there are no legacy rows to render. |
| SC-006 | Pass | ruff, ruff format, mypy and `check_file_size.py` clean; fast tier shows exactly the 8 known failures and no new ones. |
| SC-007 | Pass | §T032: `workflows/AGENTS.md` rewritten and `tests/replay/AGENTS.md` added; no test enforces the grace-edit rule. |

Open items: the "worker running on task queue" log line did not appear (pollers on `ai-sdlc` confirmed instead); the 3 durability and 8 fast-tier failures remain the known baseline.
