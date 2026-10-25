# Contract: records, analyst prompt and replay (017)

The binding names are in [data-model.md](../data-model.md), and the
reasons in [research.md](../research.md).

## C-1. Analyst prompt (patched path only)

The prompt sections, in this order:
1. `Acceptance criteria (key, task_id, text):`, one line per criterion:
   `- [T01#3] [T01] <criterion text>`.
2. `Changed files (N):`, one path per line (inventory a), or a truncation
   note.
3. `Tests in the tree (N):`, one `path::[Class::]name` per line (inventory
   b), or a truncation note.
4. `Files changed per task:`, one `<task_id>: N files changed` (or
   `unknown`) per line (inventory d).
5. `Aggregate test output:`, unchanged.
6. `Integration diff stat:` and `Integration diff:`, unchanged, still under
   the 60,000-character cap.

Inventory (c) is never sent. `analyze.prompts.prompt_digest` has no
caller in `src/sdlc` today (grep), so analyze is not memoized and no salt
change is needed. If the builder finds a caller, the salt bumps
`analyst_prompt_v1` → `v2`.

The analyst instructions (`agents/analyst/instructions.md`) state:
- the four evidence forms;
- that a command never satisfies a criterion;
- to echo each criterion's key;
- to cite only test names from section 3 and paths from sections 2 and 4,
  or files known to exist;
- "never invent".

## C-2. Enforcement (pure, `enforce_traces`)

| Evidence | Valid iff |
|---|---|
| test name | normalized match in inventory (b) (research D-4) |
| `file` + `present` | path in inventory (c); if (c) is truncated and the path is missing, invalid |
| `file` + `absent` | path not in inventory (a), and containment holds |
| `task_unchanged` | inventory (d) count for the criterion's task is exactly 0; None (unknown) is invalid |
| `command` | never valid; counted |

Bucket = the first of test, file, command, empty that has a valid entry
(command: any entry). `untraced` = criteria in buckets command or empty.
The record's PASS rule is `untraced == 0`. The merge gate's
`untraced_criteria` check receives the same list (research D-1).

The error text, when failing:

```text
"<n> untraced criterion(s): <label>[ (command only)]; ...; ..." (first three, then "; ...")
```

## C-3. Records

- **Analyze:** `trace` set (patched path). On the unpatched path `trace`
  is None, and the record is exactly as today.
- **Plan:** `tasks_total`.
- **Merge:** `blocking_checks` on all four sites. On a pass it is `[]`.
- **Cell and oracle:** `stage_reach`, identical on both records of one run.
- **Oracle:** `components.exit_code`, `components.errors`, and the
  collection detail (FR-025, after FR-027).
- No field of any pre-017 record changes meaning. `cell_progress`,
  `grading_from_score` and the score of every record are unchanged.

## C-4. Acceptance verdict

`decide()` order: reference → floor → not-assessed checks → saturated →
**stalled** → degenerate → no weak arm → no_separation → pass.

**Stalled** fires iff all of these hold:
- every graded run of both arms has `stage_reach`;
- every run's partial credit is ≤ 0.05;
- all `last_stage` values are equal;
- for that stage, `last_stage_outcome != "pass"` or `last_stage !=
  final_stage`.

Its output is `(NOT_ASSESSED, Reason.STALLED, "not separable: stalled at
<stage>")`. `acceptance.yaml` gains `reason: stalled` only for new
verdicts. Every stored `acceptance.yaml` recomputes identically (SC-003).

## C-5. Research spend

- **Ledger:** every raising exit of `_research_subquestion_impl` with
  non-zero `run_usage` appends one line. It is best-effort, and the
  original exception always re-raises.
- **Fold (patched `017-research-ledger`):** exactly one
  `read_dead_attempt_usage` activity per execution, at whichever of two
  mutually exclusive sites the path reaches: before the grounding-violation
  record, or after the refine loop before the final record (research D-9). Totals are added once to `research_spend`, with `calls` equal to
  the ledger's count.
- **Trace:** each research spend folded in the stage (planner,
  sub-question, synthesis, ledger) emits one `MODEL_USAGE` event through `ctx.emit`, with
  role `research` and stage `research`, carrying the `_track_usage` field
  set. There are no `_role_usage` writes and no activation attribution. The
  `_check_budget` sum is unchanged (SC-005), and so is the E-75 §4.3
  invariant.
- **Surfaces (FR-034 as amended A-1).** Research spend appears in the run
  summary, the live `run_state` roles and total, the Cost tab total and
  benchmark records. It does not appear in `_check_budget`,
  `budget_counted_usd` or `graph_view` per-activation spend.

## C-6. Replay

| Marker | Taken in | Unpatched path |
|---|---|---|
| `017-analyze-evidence` | `analyze.step`, before the inventory activity | today's prompt, no activity, `untraced_criteria` |
| `017-research-ledger` | research `step`, before `read_dead_attempt_usage` | no ledger read; fan-out folds as today (the emission still happens: not a command) |
| `017-plan-drift-generated` | `code/step.py:778` via `_DRIFT_V2()` | `compute_plan_drift` unfiltered |

The parent `BenchmarkWorkflow` adds no command. `summarize_cell` gains one
optional argument, and its result gains one defaulted field. That replays
by SDK semantics (research D-6) and is proven by the `BenchmarkWorkflow`
history recorded at step 0.
`tests/replay/` histories are never re-recorded (`S/workflows/AGENTS.md`).
