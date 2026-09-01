# Completing the measurement instrument (design)

| | |
|---|---|
| Status | Design — approved in brainstorming 2026-08-03 |
| Roadmap item | Closes E-36's deferred follow-on; new scope for the SC rollup, the score command, and the experiment log |
| Design input | Abdullin's "quality is a trajectory" loop (test environment first, error heatmap as the prioritisation instrument, experiment log for rolled-back changes) |
| Anchors | `BENCHMARK.md` §4.1–4.4 (metrics beyond a pass rate); FR-704 / NFR-4 (run/benchmark export); ADR-11 / `BENCHMARK.md:51-56` (fixed, non-self-modifying instrument) |
| Depends on | E-31 (`ORACLE_TASK` records), E-32 (`RunSummary`), E-36 (heatmap precedent), E-37 (arms / `cell_id`), E-38 (`SessionDigest`) |

---

## 1. Why now

The premise of this work is ordering, not novelty: **the measurement
instrument should be finished before the next feature is coded**, so that
feature arrives into an environment that can already score it. Quality is a
trajectory, and a trajectory needs an instrument that exists on day one.

The factory already has most of one. What it does not have is the last hop in
four places, and in each case the data is already being produced and then
dropped:

| Gap | Evidence produced | Where it dies |
|---|---|---|
| Tool-call behaviour is invisible | `SessionDigest` (`harness/session.py:17`) | never reaches `BenchmarkRecord` (`benchmarks/models.py:68`) |
| No success-criteria numbers | `RunSummary` (`observability/summary.py:61`) | rendered to lossy HTML only (`observability/activities.py:30`) |
| Scoring is slow and split in two | records + summaries on disk | `report` and `history` are separate commands; `report` needs a Temporal import to load |
| Improvement cycle has no memory | benchmark reports per run | nothing records what was tried and rolled back |

E-36's roadmap entry says this explicitly: *"Session-derived waste (E-38) as a
heatmap input and calibration-as-CI-gate (OQ-B4) deliberately deferred."* This
design closes the first half of that deferral and three adjacent gaps that
share its seam.

### Non-goals

- **No new benchmark cases.** Corpus growth (OQ-B1) is separate work.
- **No faster full-matrix runs.** A cell is a whole `FeatureWorkflow`; that
  takes hours and this design does not pretend otherwise. See §5.
- **No calibration CI gate** (OQ-B4), **no E-31a diff-coverage anti-cheat**,
  **no grade-at-each-gate curve**, **no traceability-gap metric**. All remain
  open; all are named here only so the inventory is honest.
- **No dashboard.** The grids stay separate HTML files. A single tabbed
  dashboard is a follow-on that needs no rework of this design.
- **No automated rollback.** See §6.

---

## 2. Architecture

The organising rule: **execution writes evidence; scoring reads it.** Nothing
in the scoring path imports `temporalio` or contacts a server, so scoring runs
from a shell in seconds.

### 2.1 Evidence stores

| Store | Path | Written by | Status |
|---|---|---|---|
| Benchmark records | `runs/benchmarks/<bench_run_id>/<case>#<harness>#<model>.jsonl` | `record_benchmark` | exists; gains a `waste` field |
| Run summaries | `runs/<run_id>/summary.json` | `export_run_artifacts` | **new** |
| Sessions / transcripts | artifact store (`ArtifactStore`) | `run_coding_task` | exists; **deliberately not read at score time** |

The third store is excluded from scoring on purpose. OQ-B7 leaves the
full-transcript TTL open, so any aggregation that joins against transcripts
goes blind the moment retention prunes them. The bounded `SessionDigest` is
copied into the record instead. `records.jsonl` is the one durable measurement
substrate; it must stay self-sufficient and archivable.

### 2.2 Flow

```
FeatureWorkflow ─┬─> record_benchmark ──────> records.jsonl ─┐
                 └─> export_run_artifacts ──> summary.json ──┤
                                                             │
                              benchmarks/evidence.py <───────┘
                               (pure reader + join)
                                       │
      ┌──────────┬─────────────┬───────┴──────┬──────────────┐
   heatmap   task_matrix   error_matrix   waste_matrix    sc_rollup
   (exists)    (exists)      (exists)        (new)          (new)
                                       │
                            `sdlc benchmark score`
                        one output dir, seconds, no Temporal
```

### 2.3 Module boundaries

Every grid module keeps the shape the existing three already have
(`heatmap.py:1-6`, `error_matrix.py:1-6`): pure `build_*` + `render_*_html` /
`render_*_json`, no I/O, no `temporalio` import. That is why those modules are
unit-testable without a worker, and the new ones inherit it.

- `benchmarks/evidence.py` (**new**) — owns all reads. Loads records for a
  selector (`--bench` / `--case` / `--all`) and run summaries, returns a typed
  `Evidence` bundle.
- `benchmarks/waste_matrix.py` (**new**) — pure aggregation + rendering.
- `benchmarks/sc_rollup.py` (**new**) — pure aggregation + rendering.
- `benchmarks/score.py` (**new**) — the one place that writes files. Kept out
  of `cli.py` so the CLI module stays argument-parsing plus thin dispatch.
- `benchmarks/experiments.py` (**new**) — experiment-log read/write + delta
  computation.

---

## 3. Deliverable A — tool-call waste reaches the instrument

### 3.1 Schema

`BenchmarkRecord` gains `waste: WasteBag | None = None`.
The default means every record already on disk parses unchanged.

```python
class WasteBag(BaseModel):
    """§4.3 coordination-and-waste aggregates for one coding attempt:
    activity that did not advance the goal. Projected from SessionDigest,
    minus the unbounded skeleton and the token fields CostBag already owns."""

    tool_calls: int = 0
    file_reads: int = 0
    file_rereads: int = 0  # same path read more than once
    files_written: int = 0  # distinct paths written
    rewrite_churn: int = 0  # paths written more than once
    failed_commands: int = 0  # command events with non-zero exit
    model_turns: int = 0
    denials: int = 0  # E-16 blocked tool calls
    escalations: int = 0  # E-17 calls that raised a gate
    compacted: bool = False

    @classmethod
    def from_digest(cls, d: SessionDigest | None) -> "WasteBag | None":
        """None when d is None. An absent session is 'not measured', never
        'measured zero' -- an all-zero bag is indistinguishable from a
        genuinely clean run, which §3.3's blank-not-zero rule forbids."""
```

`WasteBag` is a distinct model rather than embedding `SessionDigest` directly
because `SessionDigest.decision_skeleton` is up to 200 strings
(`session.py:12`) and would bloat a file meant to be scanned repeatedly, and
because its `input_tokens` / `output_tokens` already live on `CostBag`.

### 3.2 Population — one site

`workflows/feature.py:1035`, the `stage="code"` record, where
`run.session_digest` is already in scope beside `cost_usd=run.cost_usd`.
`_stage_record` (`feature.py:379`) gains a `waste: WasteBag | None = None`
parameter; every other call site keeps the default.

### 3.3 A limitation stated in the report, not buried

Sessions are captured only in `run_coding_task` (`activities.py:468`), which
serves harness roles. Proposer stages (clarify, architect, planner, qa,
reviewer, analyst) are direct model calls with no transcript, so their records
carry an empty `WasteBag` — **permanently, by construction, not pending
work**. The waste matrix is therefore a *coding-task* instrument.

Consequence for rendering: an empty bag renders **blank**, never `0`. A stage
that was never measured must not be displayed as a stage that scored perfectly.

### 3.4 The waste matrix

Rows are tasks, columns are `harness#model` arms, one stacked grid per waste
metric:

```
== tool_calls ==
task \ arm         claude#glm-5.2  opencode#glm-5.2  cursor#gpt-5.2
t01-schema                   12.0              14.5            11.0
t02-crud-endpoints           47.0              88.0            31.5
t03-auth                     22.5              29.0            19.0

== file_rereads ==  == rewrite_churn ==  == failed_commands ==
== denials ==       == escalations ==
```

**Which metrics get a grid: exactly six** — `tool_calls`, `file_rereads`,
`rewrite_churn`, `failed_commands`, `denials`, `escalations`. These are the
ones that measure work that did not advance the goal.

The other four `WasteBag` fields are carried on the record but **not
gridded**: `file_reads`, `files_written`, and `model_turns` measure volume
rather than waste (a task that legitimately touches more files is not
thrashing), and `compacted` is a boolean, so it renders as a per-arm count in
`report.md` instead. All four remain in `waste-matrix.json` for anyone
aggregating differently.

Redder is more waste. This mirrors `error_matrix.py` structurally, so the code
shape and the reader's mental model are shared.

**Aggregation.** Waste sums across attempts within a run — total thrash spent
on a task is the meaningful quantity, not the per-attempt average — then means
over runs, the same per-run normalisation `error_matrix.py:56` uses.

**No `tasks.yaml` dependency.** Rows come from `task_id` observed in the
records, ordered by `tasks.yaml` when one exists and alphabetically otherwise.
So the waste matrix works on every case immediately, including
`cat-cafe-monitoring`, which has no `tasks.yaml` today.

---

## 4. Deliverable B — cross-run success-criteria rollup

`export_run_artifacts` (`observability/activities.py:24`) gains one write:
`summary.json` beside `events.jsonl`. `RunSummary` is already fully typed and
already built on every terminal path; today it is only rendered into HTML.

`benchmarks/sc_rollup.py` scans `runs/*/summary.json` plus the benchmark
records and computes four rates. **The roadmap names these criteria but not
their formulas; the definitions below are choices, and they are the
load-bearing decisions of this section.**

### SC-1 — unattended reach (target ≥80%)

The criterion is *reaching* the merge gate, not passing it.

**Reached** — `RunSummary.outcome` starts with `deployed:`,
`merged-not-deployed:`, or `rejected:merge` (`feature.py:1757`, `1791`,
`1828`, `1836`). Every earlier terminal — `rejected:research`,
`rejected:architecture`, `rejected:plan`, `failed:dependency-cycle`,
`failed:quarantined-tasks` — did not reach it.

**Unattended** — walking `RunSummary.gates` in trace order and stopping at the
gate named `"merge"` (`feature.py:1754`), no earlier gate has
`decided_by == "human"`. A human answering the merge gate itself does not
disqualify the run, because by then it had already reached the gate.

A run counts iff both hold. Denominator: all runs. `RunSummary.terminal_stage`
is deliberately *not* used — it is the last stage that emitted `STAGE_ENDED`
(`summary.py:91`), which is a weaker signal than the run's own return string.

### SC-3 — fix-loop success (target ≥70%)

From benchmark records grouped by `(run_id, task_id)` on `stage="code"`: a fix
loop existed where `fix_attempts > 0`; it succeeded if the final attempt's
outcome is `PASS`. Rate = successes / loops. Records rather than `RunSummary`,
because per-attempt granularity exists only there.

### SC-4 — repeat clarification (target <10% by run 10)

Measured as `answered_by == "human"` / all clarifications, as a series ordered
by run start time.

**This is a proxy, and the rendered report labels it as one.** It measures
"questions memory could not answer", which is the intent of the criterion, but
it is not literal text-level repeat detection. Literal detection needs
cross-run question matching, and `ClarificationOutcome.question_id`
(`models.py:813`) is not established as stable across runs. Literal repeat
detection is a named follow-on, not a silent substitution.

### SC-6 — soft-gate override (target <5%)

Over gates with `policy == "soft"`: override rate = `decided_by == "human"` /
soft gates. Reported alongside a **second, separate** number — waved advisory
checks, from `gates[].overrides` — because those are different failures and
one average would hide both.

### The denominator rule

Every rate renders with its `n`, and renders `n/a` below a floor of **5 runs**
rather than emitting a percentage. A single successful run displaying "100%"
would be quoted as a result; that is the failure mode the calibration trust
level already exists to prevent elsewhere in this instrument.

---

## 5. Deliverable C — `sdlc benchmark score`

```
sdlc benchmark score [--bench ID | --case ID | --all] [--out DIR] [--weights q,c,s]
```

One command replacing `report` and `history`, writing a full set into one
directory: `report.md`, `heatmap.{html,json}`, `task-matrix.{html,json}`,
`error-matrix.{html,json}`, `waste-matrix.{html,json}`,
`sc-rollup.{html,json}`.

**Selectors** (exactly one required): `--bench` scopes to one matrix run;
`--case` scans every `bench_run_id` for that case (today's `history`
behaviour, via `report.py:43::scan_case_records`); `--all` scans everything.

**`--out`** defaults to `<benchmarks_root>/<selector>/score/`, where
`benchmarks_root` is `recorder._root()` (`SDLC_BENCHMARKS_ROOT`, default
`runs/benchmarks`) and `<selector>` is the `bench_run_id`, `_case/<case_id>`,
or `_all`. Re-running overwrites in place — the score directory is derived
output, and the evidence it derives from is what gets archived.

**`--weights`** takes three floats as `quality,cost,speed`, e.g.
`--weights 0.6,0.2,0.2`. They are used as given; `scoring.py:87` already
renormalises over whichever axes have data in each group, so they need not sum
to 1.

### What makes it fast and runnable

**Lazy Temporal import.** `benchmarks/cli.py:13-14` imports `temporalio.client`
and the pydantic data converter at module level, so every benchmark subcommand
pays for it today. Those move inside `_run_matrix`. `score` then needs no
client, no worker, and no running Temporal server.

**Graceful degradation, not aborts.** `dispatch_history` currently raises when
a case has no `tasks.yaml` (`cli.py:92`) — and only `todo-api-greenfield` has
one, so `cat-cafe-monitoring` cannot produce a history at all. Under `score`,
a missing input emits the grids that do have data, notes the skipped ones in
`report.md`, and exits 0. A gap in the corpus is not a crash.

**`--weights` finally does something.** `benchmarks/models.py:1-6` states the
three dimensions are "kept RAW — never pre-normalized — so the reporter can
recompute under different weights without re-running." Nothing exposes that:
`CompositeWeights()` is hardcoded at `report.py:135` and `cli.py:72`, and the
`weights:` block in `benchmarks/config.yaml` is read by nobody (`eval/cli.py:22`
reads only `default_judge_model`). `score` reads `config.yaml` weights;
`--weights` overrides them.

### What this does not make fast

A benchmark cell is a full `FeatureWorkflow` child with a four-hour timeout
(`workflow.py:34`). Evaluating an architecture change that touches prompts,
models, or schemas requires fresh runs and takes hours. This design states that
plainly rather than implying otherwise. The instrument has three loops:

| Loop | Command | Cost | Answers |
|---|---|---|---|
| Prompt A/B, one stage | `sdlc eval <role>` | seconds | did this prompt edit help on a captured fixture |
| Re-score stored evidence | `sdlc benchmark score` | seconds | what do the runs I already have say, under these weights |
| Full matrix | `sdlc benchmark run` | hours | what does this architecture change do end-to-end |

---

## 6. Deliverable D — the experiment log

### Storage

`benchmarks/experiments/<date>-<slug>.yaml`, **committed to git** — not under
`runs/`, which is disposable output. The entire value is that negative results
survive; a rolled-back experiment that is not in version control gets re-tried
by whoever forgot.

```yaml
id: 2026-08-04-planner-decompose-prompt
axis: prompt            # prompt | model | harness | schema | tool_org | memory
change: "planner instructions.md: require explicit inter-task contracts"
commit: 4f2a91c         # the change under test
hypothesis: "fewer cross-task integration failures on cat-cafe"
baseline: bench-cat-cafe-1754000000
candidate: bench-cat-cafe-1754400000
verdict: rollback       # keep | rollback -- WRITTEN BY A HUMAN
notes: "quality flat, tool_calls +38% on t02. Not worth the tokens."
deltas:                 # written by `experiment compare`, frozen at decision time
  - {case: cat-cafe-monitoring, stage: code, arm: "claude#glm-5.2",
     quality: 0.0, cost_usd: +0.41, wall_s: +122.0, composite: -0.02,
     tool_calls: +38.0, n: 2, note: within-noise}
```

The `axis` field makes the log itself aggregatable later ("prompt tweaks have
won 3 of 11 times").

### Commands

- `sdlc benchmark experiment new --name X --baseline <bench_id>` — scaffolds
  the file with baseline scores frozen in.
- `sdlc benchmark experiment compare --experiment X --candidate <bench_id>` —
  fills `deltas`, prints the table. **It does not write `verdict`.**

### The tool computes the delta; the human writes the verdict

`BENCHMARK.md:51-56` commits this project to the ADR-11 stance: the instrument
is fixed and versioned, changed only through reviewed diffs, never
self-modifying. An auto-verdict would quietly promote the instrument to
decision-maker, which is the one thing that document rules out.

### The delta is a table, not a scalar

Per `(case, stage, arm)`: quality, cost, wall-clock, composite — plus the SC
rates and every waste metric. Cursor's finding was that behavioural differences
dwarf score differences; a single composite delta would hide exactly the
tool-call regression the example above rolls back on.

### Honesty about noise

With one run per cell, a delta *is* noise. `compare` prints `n` beside every
delta and marks any cell with `n < 3` as `within-noise`. No p-values on n=2 —
statistical theatre over a three-case corpus is worse than no claim.

### Rollback is not automated

The tool records the decision; the operator reverts the commit. Automating a
git revert off a benchmark number is precisely the self-modifying loop ADR-11
excludes.

---

## 7. Error handling

The instrument's failure stance is **degrade and report, never crash and never
silently zero**. An observability tool that can fail a run, or that reports a
missing measurement as a good one, is worse than no tool.

| Condition | Behaviour |
|---|---|
| `session_digest` is `None` on a coding attempt | empty `WasteBag`; renders blank, not `0` |
| Corrupt / partial `records.jsonl` line | skipped, as `recorder.py:77` already does |
| Missing / malformed `summary.json` | that run is excluded from SC rates; `n` drops; noted in `report.md` |
| Missing `tasks.yaml` | task and error matrices skipped with a note; waste matrix still renders |
| `n` below the floor for an SC rate | `n/a`, never a percentage |
| No records at all for a selector | empty report, exit 0 — an empty corpus is a fact, not an error |
| `experiment compare` against a missing `bench_id` | hard error, non-zero exit — a comparison against nothing is a wrong answer, not a degraded one |

Note the deliberate asymmetry in the last row: reporting degrades, comparison
does not. A silent half-comparison would produce a verdict on partial data.

---

## 8. Testing

Every new module is pure, so the bulk is unit tests with hand-built records —
the pattern in `tests/test_benchmark_heatmap.py` and
`tests/test_benchmark_report.py`.

- **`WasteBag.from_digest`** — populated digest, `None` digest, and the
  fields-drift guard: a digest field with no bag counterpart is a conscious
  choice, so the test asserts the intended mapping explicitly.
- **Record round-trip** — a `records.jsonl` line written *before* this change
  (no `waste` key) still parses. This is the backward-compatibility invariant
  and it gets a named test.
- **Waste matrix** — row derivation with and without `tasks.yaml`; sum across
  attempts then mean over runs; blank-vs-zero rendering for absent sessions.
- **SC rollup** — one focused test per rate against a hand-built
  `RunSummary` set, plus the denominator floor returning `n/a`.
- **`score` degradation** — missing `tasks.yaml`, missing `summary.json`, and
  an empty selector all exit 0 with the expected partial output.
- **Import purity** — `waste_matrix`, `sc_rollup`, and `evidence` import
  without `temporalio`, extending the existing `tests/test_e36_imports.py`
  precedent.
- **Experiment log** — scaffold, compare fills `deltas` and leaves `verdict`
  untouched, `within-noise` marking at `n < 3`, hard error on a missing
  `bench_id`.
- **Not covered by unit tests:** that the waste numbers are *correct* for a
  real harness run. That requires a live run and is verified once, manually,
  against a single `cat-cafe-monitoring` cell — recorded in the plan as an
  explicit manual verification step, not asserted in CI.

---

## 9. Sequencing

1. **`WasteBag` + record population + backward-compat test.** Write path
   first; nothing can be rendered before evidence exists.
2. **`summary.json` write.** One line, unblocks the rollup.
3. **`evidence.py` + `score.py` + the `score` command**, emitting the three
   grids that already exist (heatmap, task matrix, error matrix), with lazy
   Temporal import and graceful degradation. At this point the loop is already
   one command and already fast; the two new grids slot into the same writer.
4. **`waste_matrix.py`**, wired into `score`.
5. **`sc_rollup.py`**, wired into `score`.
6. **Experiment log.** Last, because it compares scores and needs them stable.

Steps 1–2 are write-path changes that only pay off later; they must land
first, and any run performed between step 1 and step 4 already accumulates
waste evidence that step 4 can read retroactively.

---

## 10. Open questions carried forward

- **OQ-B7** — full-transcript TTL. Unaffected by this design (that is the point
  of denormalising the digest), but still open.
- **OQ-B1** — minimum trustworthy corpus size. This design makes the
  under-powered case *visible* (the `n` floor, the `within-noise` marking)
  without resolving it.
- **OQ-B4** — calibration as a CI gate. Still deferred.
- **Literal repeat-clarification detection** — needs a question identity that
  survives across runs. Named in §4, not built.
- **Waste for proposer stages** — would need transcript capture outside
  `run_coding_task`. Not scoped; the limitation is documented in the report
  output rather than hidden.
