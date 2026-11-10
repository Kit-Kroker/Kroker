# Advisor answer 1 — 020 delete FeatureWorkflow

Read-only consult. Evidence: spec.md, `pipeline_child.py`, `dashboard/fleet.py`, `fleet_summary.py`,
`tests/replay/*`, `tests/durability/*`. Nothing else edited.

## Finding that shapes D1/D3/D4

Of the 22 checked-in histories, **18 are `FeatureWorkflow`**, 1 is `GraphWorkflow`
(`architect_research_usage`), 3 are other types. When the class goes, *every* Feature history is
unreplayable (`replayer()` in `test_feature_replay.py:29` and `_replayer()` in
`test_inflight_resume.py:44` both register `FeatureWorkflow`). So after this change the repo
would have **one** GraphWorkflow replay history. The spec's SC-004 phrase "GraphWorkflow
histories" overstates what exists. Fix that in D3.

## D1 — pipeline_child patch marker: **(a) `workflow.deprecate_patch(id)` + unconditional graph path**

Reason: the Q2 gate (no Running parent) licenses *live* safety only. It does not license
dropping the marker, because Temporal **replays history for queries on closed workflows too**:
`cli.py:753` queries `TidyUpWorkflow.report`, and benchmark/tidy parents are queried after they
close. A closed parent carrying `e74-graph-child:<id>` replays through this code on any cache
miss. (a) is the documented patched → deprecate_patch → (later) remove lifecycle and tolerates
histories with and without the marker. (b) rests on an SDK behaviour nobody has verified here.
(c) leaves a dead branch whose raise is itself a command-sequence difference on replay.

Residual risk to write into FR-008, not fix: a **closed pre-cutover parent that started a
FeatureWorkflow child has no marker**. Under (a) a query on it hits a nondeterminism error
(child type differs). Same class as Q1, accept, and record "`tidyup report` / benchmark status
on pre-cutover closed parents fails after deploy" in the analysis. The rest of the system does
not depend on it.

Proof test:

1. `test_benchmark_replay.py::test_benchmark_workflow_replays_one_cell_history` must stay green
   with `raise_on_replay_failure=True` on the unmodified `benchmark_one_cell.json` (it carries
   the marker). That is the primary proof.
2. Add one test that replays the same history with the `workflow.patched` call monkeypatched to
   `deprecate_patch`-only semantic being absent, i.e. run the real new code on a **stripped**
   copy of the history (marker event removed). It must also replay, proving deprecate_patch
   tolerates absence. Cheap, no new capture.
3. Do not add a TidyUp marker history; `execute_pipeline_child` is shared, so one is enough.

Keep `deprecate_patch` for at least as long as any benchmark/tidy parent history in the store
may be queried; there is no clean removal date, so record it as a standing item, not a todo.

## D2 — legacy row: **(a) additive `closed_legacy: list[LegacyRun]`**

Reason: (b) fabricates fields (cost, stage marks) that downstream code and the frontend would
treat as real. (c) puts a normal state into `errors`, violating FR-004 and SC-005 (zero errors).

Interface:

- `LegacyRun(run_id: str, status: str, close_time: datetime | None)`. Nothing else.
- `_scan_closed` currently returns `(id, type)`; widen it to a small dataclass
  `ClosedRef(id, type, status, close_time)` taken from the visibility `wf` object (fakes must
  supply `status`/`close_time`; default `None`, never raise).
- In `fleet_tick`: partition on `type == "FeatureWorkflow"` **exactly**. A `None` type (fake
  clients, old servers) stays on the queried path. Legacy ids are excluded from `closed_ids`
  before the gather, so zero handles are created for them; they also never enter `graph_closed`.
- Keep the open-run dedupe (`run_id in open_id_set`) for legacy ids too.
- Frontend (`http.ts`): optional `closed_legacy` defaulting to `[]`, so an older backend
  payload still parses. Render as "legacy run, summary unavailable" in the closed list, sorted
  by close time with the others.
- `/api/fleet/summary`: **do not count legacy rows**. `FleetSummaryWire.runs` is
  derived from graph facts (sha, arm, traversals) and a legacy row has none; `unreadable` means
  "tried and failed", which is wrong here. Counting them would make summary totals disagree with
  "graph runs" semantics. If a header needs a total closed count, compute it in the UI from
  `closed.length + closed_legacy.length`. Add a one-line comment at `fleet_summary.py` saying
  legacy rows are intentionally absent.
- Fleet cap (`open_errors`) is untouched: legacy rows are closed-only.

Tests: fake client with N closed Feature rows → N legacy rows, handle factory asserts zero
calls for those ids, `errors == []`; mixed Graph + Feature window; both the ordered and
unordered query paths; a `None`-typed row still queried.

## D3 — fixtures, per test

All three of these need a **GraphWorkflow history**, because a Feature history cannot replay
once the class is removed. Capture them in one session, from the same unmodified tree, before
any deletion lands (the capture helper uses `GRAPH_STARTER`, which stays).

| Test | Decision | Reason |
|---|---|---|
| `test_research_retain_replay.py` (009 proof) | **(a)** new `research_retain_grounded_graph.json`, header `workflow: GraphWorkflow`, `source_commit`, and a `provenance` note "replaces the FeatureWorkflow capture of 009 T002". Re-point the capture test to `GRAPH_STARTER` and the `replayer` import to a helper that survives. | It is the only proof the retain path survives replay-with-missing-page-files. A golden projection cannot show that. Do not delete or demote it. |
| `durability/test_inflight_resume.py` (HISTORY_NAME = greenfield_happy) | **(a)** point at the new `greenfield_happy_graph.json`; `_replayer()` registers `GraphWorkflow`. | Its whole point is replay of a truncated real history; (b) cannot do that. |
| `durability/test_priced_usage_parity.py` | **(a)** capture with `GRAPH_STARTER`, compare to the new history, **and** first extract the recorded `price_usage` tuples from the old history into a small checked-in JSON constant. | A fresh capture compared to a same-tree recording is tautological on day one. The extracted pre-migration tuples keep the one cross-time guarantee (prices did not drift since pre-E-74). |
| `test_graph_golden_chaos.py` baseline | **(a)** re-point `load_history` to `greenfield_happy_graph.json` | Same history serves three tests; capture once. |
| `test_graph_golden.py:112` memo_parity (Feature vs Graph) | **migrate**: drop the Feature leg, assert Graph keys against a pinned expected list taken from the Feature run before deletion | This test compares two starters; with one gone it must pin the value, not delete the check. Not in the brief, easy to miss. |

Also: move `replayer()` out of `test_feature_replay.py` (research_retain imports it) into
`tests/replay/harness.py` before deleting that file. And since GraphWorkflow replay coverage is
thin, add 2 to 3 more Graph histories for the gate-heavy scenarios (`plan_revise_approve`,
`arch_timeout_reject`, `cancel_during_code`) via `GRAPH_STARTER`. This is the cheapest way to keep
FR-008's "retained histories pass" claim meaningful. Mark as a recommendation; the spec only
requires the three above.

## D4 — golden re-baseline: **(b) in effect, with (a) as a one-time check**

Reason: `test_graph_golden.py:31` already captures with `GRAPH_STARTER` and compares to the
committed golden on every run, so parity is continuously proven. Regenerating adds nothing but a
chance to silently accept drift.

- Run the regeneration once locally, to a scratch dir, and diff `commands` and `close` against
  committed. Attach that empty diff to the review (it is SC-003 evidence). Do not commit it.
- Commit only: the `workflow` field in each golden (19 files, `FeatureWorkflow` → `GraphWorkflow`)
  **plus** `source_commit` untouched, and the provenance docs. If you would rather not touch 19
  files for a label, leave the files byte-identical and state provenance in
  `tests/replay/AGENTS.md`/harness docstring. I prefer that: fewer files, no hand-edit risk
  under FR-011's "no golden edited by hand". Only caveat: `test_fixtures_present.py` must not key
  on the `workflow` field.
- Anything non-empty in `commands` or `close` stays a STOP, as the spec says.

## D5 — ordering: **two PRs, with a correction to the split**

Move the **inbox open-type removal out of PR-1**. While `FeatureWorkflow` is still registered
and possibly Running, removing it from `fetch_inbox`/`list_open_run_ids` hides those runs'
pending gate decisions from the inbox and fleet during the drain. That is exactly when a human
may need to see them. It is not harmless.

- **PR-1 (safe while Feature is registered):** fleet `closed_legacy` + frontend row; test
  migrations that do not depend on the deletion; GraphWorkflow history captures (D3); relocated
  `replayer()` helper; `deprecate_patch` switch (D1) with the new replay tests. All additive or
  behaviour-preserving for Graph. Note PR-1's legacy skip does change closed Feature rows
  from "summary shown" to "legacy row" while the type is still registered; accept (Q1 = A), say
  so in the PR.
- **Gate run 1 (FR-001):** between the PRs, recorded in `verification.md`.
- **PR-2:** inbox open-type removal, class/module/registration deletion, `step()` composites,
  test deletions, AGENTS.md and docs. Merge only on gate-1 empty.
- **Gate re-run (FR-002) sits at deploy, not at merge.** For a compose-deployed worker the
  registered set changes only when the container is rebuilt and restarted, not when main moves.
  Merge is reversible by not deploying; the restart is the irreversible step. So: run both queries
  immediately before `docker compose up` for the worker, record output, time and store id, and
  abort on non-empty. Confirm nothing (CI, watchtower, a deploy-on-merge hook) auto-deploys on
  merge; if something does, the merge itself becomes the gated step and the gate must run before
  merge.
- One PR is acceptable only if the team will not deploy between merge and gate; two PRs makes
  the fleet and fixture work reviewable on its own and keeps the large deletion diff mechanical.

## Items to add to the plan

- FR-008: closed pre-cutover Tidy/Benchmark parents fail on query after deploy (D1 residual).
- SC-004: replace "GraphWorkflow histories" with the actual list after D3 captures.
- `test_graph_golden.py:112` memo_parity migration (D3).
- Confirm no auto-deploy on merge (D5).
