# Presentation: The Kroker Pipeline & Temporal

**Audience:** engineers who know Python and LLMs, but have never used Temporal.
**Length:** 55 minutes — fits a 60-minute slot with buffer. A 30-minute
cut-down is at the bottom.
**Goal:** the room leaves able to explain *why an agentic SDLC needs durable
execution, how it learns across runs, and how you tell whether it is actually
working.*

**One-line thesis:** *Agents are non-deterministic; orchestration, quality
judgement, and the record of what happened must not be.*

---

## Time budget — 55 min

| # | Section | Time | Clock |
|---|---|---|---|
| 1 | The problem | 3 min | 0:00 – 3:00 |
| 2 | Temporal in five minutes | 5 min | 3:00 – 8:00 |
| 3 | The pipeline as a state machine | 6 min | 8:00 – 14:00 |
| 4 | Where the two meet | 5 min | 14:00 – 19:00 |
| 5 | **Quality: how a merge is actually decided** | 7 min | 19:00 – 26:00 |
| 6 | **Shared memory: how the system learns** | 7 min | 26:00 – 33:00 |
| 7 | **Logging: three layers of record** | 6 min | 33:00 – 39:00 |
| 8 | **The heatmap: where the pipeline hurts** | 4 min | 39:00 – 43:00 |
| 9 | Live demo | 7 min | 43:00 – 50:00 |
| 10 | Takeaways + Q&A | 5 min | 50:00 – 55:00 |

Sections 3 and 4 are the compressible ones. **Never cut the demo** — it is
what makes durability believable.

---

## 1. The problem (3 min)

**Slide:** the stage DAG from `ARCHITECTURE.md` §3.

```
intake → constitution → context* → requirements → {clarify gate}
      → architecture → {arch gate} → planning → {plan gate}
      → code ⇄ review ⇄ qa (per task) → analyze → {merge gate}
      → PR + deploy → {deploy gate} → retro + reflect
```

Show it once. Do **not** explain the stages yet — let them see the size.

**Talking points**
- What Kroker is, in one sentence: idea → deployed feature. Pydantic AI agents
  propose typed artifacts; coding harnesses (`claude -p`, `opencode run`) act
  inside isolated git worktrees; humans hold gates.
- Then the numbers that create the problem: **one run is hours long**, makes
  tens of LLM calls, shells out to coding sessions that run for tens of
  minutes, and parks on a human approval that may arrive tomorrow morning.
- Close with the question that sets up the whole talk:
  > "You wrote this as a Python script. Your laptop reboots at stage 9.
  > What do you have?"

Answer: nothing. Not a partial result — nothing you can resume.

---

## 2. Temporal in five minutes (5 min)

Do not tour Temporal. Introduce exactly five concepts, each as the fix for a
pain that is already on the table.

| Pain from section 1 | Temporal concept |
|---|---|
| Process dies mid-run | **Workflow** — code whose every step is recorded to an event history and replayed on recovery |
| LLM call flakes, API returns 429 | **Activity** + `RetryPolicy` — the only place I/O is allowed, retried independently |
| Human approval takes 12 hours | **Signal** + `wait_condition` — a durable wait that costs nothing while parked |
| "What is it doing right now?" | **Query** — read workflow state from outside, no database needed |
| A coding session runs 40 minutes | **Heartbeating activity** — long work that proves it is still alive |

**The one rule they must leave with:**
> Workflow code is deterministic and does no I/O. Everything real — network,
> disk, subprocess, clock — happens in an activity.

**Why it works, in one breath:** the workflow's history is the source of
truth. On recovery, Temporal replays your workflow function against that
history; already-completed activities return their recorded results instead of
running again. That is why the function must be deterministic — and why
`random`, `datetime.now()`, and `open()` are banned inside it.

**Anticipate the objection:** "isn't this just a queue plus a state table?"
Yes — and you would write that state table yourself, wrongly, for every new
pipeline. Temporal makes it the programming model.

---

## 3. The pipeline as a state machine (6 min)

**Slide:** the DAG again, now readable.

- 15 stages, one `FactoryWorkflow` per run. `context` runs only in brownfield
  mode; greenfield skips it.
- **Two design rules shape everything:**
  1. *The model never acts outside a sandboxed, observed boundary.* Proposer
     agents emit schema-validated artifacts and hold no tools at all. Coding
     harnesses do act — but only inside a risk-classed git worktree, and only
     their **diff** is admitted as an artifact.
  2. *Memory is I/O.* All memory access happens in activities; recall results
     become persisted, hashed `RecallSnapshot` artifacts declared as stage
     inputs. Stages stay pure functions of hashed inputs.
- **The per-task loop** (creator/verifier discipline) — this is the setup for
  section 5, so do not skip it:
  1. At planning time, each task's acceptance criteria are frozen into a
     **Validation Contract** — machine-checkable assertions written *before any
     code exists*, so correctness is measured against requirements, not against
     whatever the implementer happened to build.
  2. Worktree + branch per task → harness session implements → tests run.
  3. **Clean-context validators**: the Reviewer and QA analyst see the task,
     the contract, the materialized diff, and the test output — never the
     worker's session or its self-reported narrative. *The doer has tools; the
     judge does not.*
  4. On failure the same harness session resumes with the issues (bounded:
     2 review / 3 QA repairs). Exhaustion escalates to a human gate.

---

## 4. Where the two meet (5 min)

Agent class → Temporal construct is **a rule, not a convention**:

| Agent class | Temporal construct | Ours |
|---|---|---|
| Automation — one LLM call | activity via `TemporalAgent` | Clarifier, Architect, Planner, Reviewer, QA analyst |
| Long-running — tools, iteration | heartbeating activity | Developer / Resolver harness runs |
| Conversational | external client ↔ signals / queries | operators via CLI, Slack, MCP |
| Proactive | workflow on a timer / Schedule | MaintenanceWorkflow, nightly reflect |
| Routing | deterministic workflow branch | intake (greenfield / brownfield / repair) |

**Concrete details** (`src/sdlc/workflows/feature.py`):

- **Timeouts are not one-size-fits-all.** A default activity gets 10 minutes
  and 3 attempts (`ACT`). A harness coding run gets hours plus a heartbeat
  timeout (`LONG_ACT`) — a long harness run would otherwise outlast a short
  heartbeat window and be killed as a false-dead worker.
- **Gates are just a durable wait.** Entering a gate publishes to the
  `pending_decisions` query, fires a notify activity, and parks on
  `wait_condition`. Gate identity is `(gate_name, round)` and signals are
  idempotent — *first decision per round wins*.
- **A decision is not a boolean**: `approve | reject | revise`.
- **Pydantic AI plugs straight in**: the worker connects with
  `plugins=[PydanticAIPlugin()]` and a `pydantic_data_converter`; wrapping a
  proposer in `TemporalAgent` offloads model calls and tool I/O to activities.

**Two honest "Temporal does not give you this" notes:**
- **Claim-check.** Every payload crosses the event history. Specs, diffs, and
  logs go to an artifact store; only a reference travels.
- **Memoization.** Temporal *replays*; it does not *skip*. Re-running after a
  prompt edit needs a content-addressed cache keyed on
  `hash(activity + inputs + prompt file + model id + upstream recall snapshot)`.

---

## 5. Quality: how a merge is actually decided (7 min)

**The framing line, before any detail:**
> "The obvious design is to ask a good model 'is this PR OK?'. We do not do
> that, and this section is why."

Quality is enforced at **two levels**, and the important thing is that neither
of them is an LLM holding a veto.

### 5a. Task level — judged against a contract, not against itself

Recap from section 3 in one sentence: the Validation Contract is frozen at
planning time, before any code exists, and the validators are clean-context.
That ordering is the whole trick — a judge that sees the implementation first
grades the implementation; a judge holding a contract written earlier grades
the *requirement*.

### 5b. Run level — `DeterministicQualityGate` (`src/sdlc/gate.py`)

**Pure code. No LLM.** It consumes typed evidence already produced by earlier
stages, reduced to `CheckResult`s, and returns a `GateReport`.

Six checks, in two classes:

| Check | Class | Evidence |
|---|---|---|
| `build_integration_green` | **ABSOLUTE** | aggregate of per-task pytest runs |
| `lint_clean` | **ABSOLUTE** | lint activity |
| `security_no_critical` | **ABSOLUTE** | security scan: `critical == 0` |
| `review_severity` | advisory | clean-context reviewer blocking findings |
| `traceability` | advisory | every acceptance criterion maps to ≥1 test |
| `coverage` | advisory | diff coverage vs configured threshold |

**The two classes mean genuinely different things:**
- **ABSOLUTE** — blocks the merge unconditionally. There is *no override path
  in the code*. An absolute failure returns
  `rejected:merge:absolute-gate-failed:<checks>` and the run is over.
- **ADVISORY** — blocks only until an **audited human override** is recorded.

**The floor.** `ABSOLUTE_FLOOR = {"security_no_critical"}`: that check is
forced to ABSOLUTE by `build_check()` even if a project's config asks for
advisory. A project can tune its own strictness; it cannot configure away
"no critical vulnerabilities". Worth saying out loud — it is the clearest
example of policy living in code rather than in a prompt.

**Where the human fits.** On advisory failure, the human merge gate *is* the
override mechanism. An `approve` records a `GateOverride{check, approved_by,
reason}` per waived check — so "we shipped at 71% coverage" is a named person,
a reason, and a timestamp in the run record, not a silently lowered threshold.
Those overrides are retained to memory as calibration signal.

**And the punchline about the LLM verdict.** There *is* an LLM `MergeVerdict`
agent. It is **not consulted by this gate**. It is only ever an advisory input
to a *soft* merge gate, and only *after* the deterministic gate has already
passed. Quote the module docstring if you want the room to believe you:

> "The advisory LLM `MergeVerdict` is NOT consulted here — it is only ever an
> advisory input to a SOFT merge gate, after this gate has already passed."

**The takeaway to land:**
> Absolute checks are code. Advisory checks are code plus an audited human.
> The model's opinion is never the thing standing between a diff and `main`.

---

## 6. Shared memory: how the system learns (7 min)

**The hand-off from section 5:** every gate decision you just watched — every
advisory override, every rejection — is retained as a learning signal. This
section is what happens to it.

**Backend:** Hindsight, self-hosted on Postgres. **Off by default**
(`SDLC_MEMORY_ENABLED`); with memory disabled, recall returns an empty
snapshot and the pipeline runs exactly as before. That is deliberate — it is
what makes a memory-on / memory-off comparison possible at all.

### 6a. The rule: memory is I/O

Workflow code never imports a backend. All access funnels through **four
activities** over a four-method `Memory` ABC:

| Activity | Method | When |
|---|---|---|
| `recall_snapshot` | `recall(bank, query, filters, watermark)` | before each agent stage |
| `retain` | `retain(item)` | stage success, fix-loop end, every gate decision |
| `capture_watermark` | `current_watermark(bank)` | once, at run start |
| `reflect` | `reflect(bank)` | retro, and nightly on a Schedule |

Two implementations behind the ABC: `FakeMemory` (tests, default) and
`HindsightMemory`. The workflow cannot tell them apart — that is the point.

**Banks, not bank sprawl:** `org` (cross-project) and `project:<repo>`.
Per-agent views come from **metadata filters** — `{kind, agent, stage, run_id,
task_id}` — not from creating a bank per agent.

### 6b. Recall is a declared stage input, not a side channel

This is the design decision to spend time on. A recall does not inject text
into a prompt and vanish. It produces a persisted, hashed artifact:

```python
RecallSnapshot(query_hash=..., bank=..., watermark=..., items=[...], degraded=False)
```

That snapshot is declared as a **stage input**. Which means: stages stay pure
functions of hashed inputs, and "why did this run behave differently?" is
answerable — you can diff the snapshots.

`query_hash` has exactly **one definition**, shared by `FakeMemory`,
`HindsightMemory`, and the degraded path. So a snapshot taken against the fake
and one taken against Hindsight are comparable — which is what makes the
memory-on/memory-off delta a real measurement rather than a vibe.

### 6c. The watermark — the idea worth the whole section

A run captures the bank's watermark **once, at run start**, and pins every
recall in that run to it.

Why it matters, in three consequences:
- **Nightly consolidation cannot shift the ground under a running pipeline.**
  Stage 12 sees the same memory stage 3 saw.
- **Re-runs are reproducible and cache-warm.** Default re-run reuses the
  watermark, so the memoization cache from section 4 is not busted by
  unrelated memory churn. An explicit "refresh memory" advances it.
- **No point-in-time reads needed from the backend.** Reusing the persisted
  snapshot *is* the freeze.

> "Memory that changes mid-run is not memory, it is a race condition."

### 6d. Failure behaviour is asymmetric — on purpose

Best single slide in this section. Four paths, four different choices:

| Operation | On failure | Why |
|---|---|---|
| `recall` | **never raises** — empty snapshot, `degraded=True`, logged | memory is advisory; an unreachable Hindsight must never block a run |
| `retain` (activity) | **raises** | so Temporal's `RetryPolicy` retries it in the background (30s, 5 attempts) |
| `_retain` (workflow) | **swallows** | a memory write can never fail a feature run |
| `ReflectWorkflow` | **fails loudly** if any bank fails | *"a silent no-op is the failure mode this whole feature exists to avoid"* |

The reflect case is the interesting inversion: everywhere else memory degrades
quietly, but a consolidation job that silently does nothing is worse than one
that pages you. Each bank is its own activity execution so one bank's outage
retries independently.

### 6e. What gets written, and what never does

Five kinds (`MemoryKind`): `stage_summary`, `gotcha` (fix-loop end: what
failed and what fixed it), `gate_feedback` (every human decision),
`research_finding` (verified grounded findings only), `run_summary` (retro).

Two guardrails to state plainly:
- **Scrub before store.** Regex redaction of API keys, AWS keys, emails, and
  `password/token/secret` assignments runs on every retain. Say the honest
  part out loud — the module says it itself: *"not a security boundary by
  itself"*, just a default that keeps obvious secrets out of a long-lived
  store.
- **Credentials never enter activity input.** Tenant and API key are read from
  the environment *inside* the activity, because `RecallInput` / `RetainInput`
  are serialized into Temporal history. Same instinct as claim-check: assume
  anything you pass as an argument is permanently on the record.

### 6f. The guardrail that ties back to section 5

> Memory is **advisory context**. Validators and contracts always outrank it.

Hard rules live in code — *failures become validators*. Memory learns the soft
rules: this codebase's conventions, which mistakes recur, what a reviewer keeps
rejecting. A `gotcha` can inform the next run; it can never wave through a
failed absolute check.

**Consolidation:** `reflect` turns raw retains into mental models — at retro
for the run, and nightly across the org via a Temporal Schedule. That nightly
job is `ReflectWorkflow`, which exists *only* because Temporal Schedules can
start workflows and never activities. Its class name is the live contract:
never rename it.

---

## 7. Logging: three layers of record (6 min)

**Slide:** three stacked boxes. The point is that they answer three different
questions and none of them replaces another.

| Layer | Answers | Where |
|---|---|---|
| **1. Temporal event history** | "What did the machinery do?" | Temporal server |
| **2. Domain run trace** | "What did the *pipeline* do?" | `RunEvent` in workflow state → `events.jsonl` |
| **3. Logfire spans** | "Where is the time and money going?" | env-gated, off by default |

### Layer 1 — Temporal event history

Activity scheduled → started → completed, every retry, every signal. Perfect
fidelity, and it is what replay is built on. But it is *infrastructure*
vocabulary: it will tell you `execute_activity(run_coding_task)` took 31
minutes and retried once. It will not tell you the run was on its second QA
repair of task 4.

### Layer 2 — the domain run trace (E-32, `observability/trace.py`)

A `list[RunEvent]` accumulated **in workflow state** — which means it is
already durable in Temporal history; `events.jsonl` is a *rendering* of it,
not a second source of truth. Say that explicitly, it is the design decision
worth defending.

The event vocabulary is the pipeline's own:

```
stage_started · stage_ended · gate_awaited · gate_decided · gate_notified
clarification_asked · clarification_answered · fix_attempt
tool_escalation · model_usage · memory_retained · run_finished
```

Two deliberate constraints:
- `data` is a flat `dict[str, str]` — numbers are stringified at emit — so
  `events.jsonl` stays a stable, greppable line format.
- Emitting is a **pure state mutation**: append with a monotonic `seq` and
  `workflow.now()`. Safe inside workflow code precisely because it does no I/O.

At retro, this trace is aggregated into a `RunSummary` (pure function, unit
testable outside the workflow) and rendered to a dependency-free
`report.html`: stages with duration/cost/fix-attempts, gates with
policy/decider/confidence/overrides, clarifications, and per-role usage. The
retro stage is deterministic + reflect — **no LLM writes your run report.**

### Layer 3 — Logfire (E-38, `observability/logfire_setup.py`)

- **Env-gated on `LOGFIRE_TOKEN`.** Absent → every call is a `nullcontext` and
  `logfire` is never even imported. Observability is optional, never a hard
  dependency.
- When live: `logfire.configure(...)` + `logfire.instrument_pydantic_ai()` at
  worker boot, so agent model calls are traced without touching agent code.
- Hand-placed spans where the money and the mystery are: `harness.run` and
  `session.capture`.
- **The rule that matters, and the one to say slowly:**
  > Span attributes are metadata only — counts, durations, sizes, ids.
  > **Never transcript payloads.** The scrub-before-store invariant applies to
  > telemetry too.

That last point is the one experienced people in the room will respect: an
agent transcript is exactly the kind of thing that leaks secrets into a
third-party observability vendor if you are careless.

---

## 8. The heatmap: where the pipeline hurts (4 min)

**Slide:** the rendered `heatmap.html` — cases down the side, the 15 stages
across the top, cells green→red.

**What it measures: rework density.** Not pass rate — *how much the pipeline
had to redo itself*.

```
density = (gate_rejects + fix_attempts + oracle_fails) / n_runs
```

- **Rework outcomes are `FAIL`, `ESCALATED`, and `REVISED`.** Including
  `REVISED` is the subtle one: a revise round re-enters a stage, so it *is*
  rework even though nothing failed outright.
- `fix_attempts` accumulate per record; `oracle_fails` come from the
  case-level oracle scope. Task-level oracle records are deliberately skipped
  so the same failure is not counted twice.
- Cells are coloured by ratio to the max observed density (`hsl` 120°→0°,
  green to red), so the map is always relative to the worst cell in the sweep.
- Cases are rendered once for all, then again grouped **by language** — that
  is how you separate "our planner is weak" from "our Go support is weak".

**Why this is the most useful artifact in the repo:** it converts a pile of
`BenchmarkRecord`s into one question a team can act on — *which stage is
costing us the most rework, and is it the same stage across every case?* A
hot `planning` column means the plans are bad. A hot `code` row on one case
only means that case is hard. A hot `review` column across everything means
the reviewer model is miscalibrated, not that the code is bad.

**Implementation note worth one sentence:** `heatmap.py` is pure aggregation
and rendering — no I/O, no `temporalio`. The finalize activity owns every file
write. Same discipline as `observability/export.py`, and the reason both are
trivially unit-testable.

---

## 9. Live demo (7 min)

### Before the talk — non-negotiable prep

- [ ] `temporal server start-dev` running; Temporal UI open at
      `localhost:8233` in a **separate browser tab**, font already zoomed.
- [ ] `python -m sdlc.worker` running in a visible terminal.
- [ ] **A run already started and parked at the architecture gate.** A cold run
      will not reach a gate in six minutes. Start it 20–30 minutes before.
- [ ] **A finished benchmark run with `heatmap.html` on disk**, browser tab
      open. Generate it beforehand — the sample runs currently under `runs/`
      do not all contain a finalized heatmap.
- [ ] A `report.html` / `events.jsonl` from a completed run, open in a tab.
- [ ] Screenshots of every demo step saved as backup slides.
- [ ] Terminal font size ≥ 18pt.

### The script

**Step 1 — start a run (30s).** Show the command, then switch to the
already-parked run rather than waiting on this one.

```bash
python -m sdlc.cli start --title "Add SSO" --mode brownfield --repo git@...
# started feature-add-sso
```

**Step 2 — the event history (60s).** Temporal UI → the running workflow.
Scroll: activity scheduled → started → completed, one row per real side effect.
> "This is the run. Not a log *about* the run — the run itself."

**Step 3 — the durability moment (90s). This is the demo.**

```bash
Ctrl-C                    # kill the worker mid-run
python -m sdlc.worker     # bring it back
```

Completed activities are not re-executed. Let the silence sit before you
explain it.
> "No checkpoint code. No state table. The history *is* the checkpoint."

**Step 4 — the human gate (90s).**

```bash
python -m sdlc.cli status --id feature-add-sso     # awaiting: architecture
python -m sdlc.cli inbox                           # everything owed a decision
python -m sdlc.cli approve --id feature-add-sso --gate architecture \
    --comment "OIDC, not SAML"
```

> "It was parked for 20 minutes. It could have been parked for a week — same
> code, same cost. That is one `await`."

**Step 5 — the record and the map (90s).** Switch to the pre-opened tabs:
- `events.jsonl` — grep one line, show the flat domain vocabulary.
- `report.html` — the deterministic retro: stages, gates, overrides, cost.
- `heatmap.html` — hover a hot cell, read the tooltip aloud: *"N rejects, N
  fix-attempts over N runs = density/run."*

### If the demo breaks

Say "this is why I brought screenshots," switch to the backups, keep talking.
**Do not debug on stage.**

---

## 10. Takeaways + Q&A (5 min)

1. **Agents are non-deterministic; orchestration must not be.** Workflow vs
   activity is exactly that boundary.
2. **Nor is quality judgement.** Absolute checks are code, advisory checks are
   code plus an audited human, and the LLM verdict never blocks a merge.
3. **Nor is memory.** Recall is a hashed, persisted, watermark-pinned stage
   input — advisory context that can inform the next run and never override a
   validator.
4. **Nor is the record.** Three layers — Temporal history, domain trace,
   optional spans — and the heatmap turns them into the one question worth
   asking: where does this pipeline keep having to redo itself?

### Q&A prep

| Question | Short answer |
|---|---|
| "Why not Airflow / Prefect / Celery?" | Those orchestrate *tasks*. We need a workflow that parks for a day on a human signal, resumes a subprocess session, and replays deterministically. |
| "What if the LLM output is garbage?" | It never reaches orchestration unvalidated: typed `output_type` for proposers, diff-only admission for harnesses, clean-context validators against a pre-frozen contract. |
| "So an LLM can still approve a merge?" | No. The deterministic gate runs first; `MergeVerdict` is advisory input to a *soft* gate afterwards. Absolute failures have no override path at all. |
| "Who can override coverage?" | A human, at the merge gate, and it is recorded as `GateOverride{check, approved_by, reason}` and retained as calibration signal. |
| "Isn't the event history huge?" | Hence claim-check: payloads to the artifact store, references travel. |
| "Does Logfire see our code / prompts?" | No. Metadata-only span attributes by rule; off entirely without `LOGFIRE_TOKEN`. |
| "Does memory make runs unreproducible?" | No — the watermark pins every recall in a run to one freeze point, and the snapshot is persisted and hashed. Re-runs reuse it by default. |
| "What if Hindsight is down?" | Recall degrades to an empty snapshot flagged `degraded=True` and the run proceeds. Retains retry in the background. Only the nightly reflect fails loudly. |
| "Can memory make the agent do something wrong?" | It can make it *propose* something wrong — it cannot make it *ship* something wrong. Validators and contracts outrank memory; absolute checks are unaffected by it. |
| "How do you know memory helps at all?" | Snapshot identity is one shared hash across fake and real backends, so a memory-on/memory-off benchmark delta is directly comparable. |
| "Why is `REVISED` counted as rework?" | A revise round re-enters the stage. It costs a full stage execution even though nothing hard-failed. |
| "How do you stop parallel agents colliding?" | Serial by default. Worktrees prevent file collisions, not architectural divergence. |

---

## The 30-minute cut

If you cannot get the full slot, this is the running order. Everything still
appears, but §5–§8 drop to one idea each.

| # | Section | Time | What survives |
|---|---|---|---|
| 1 | The problem | 3 min | the DAG + "laptop reboots at stage 9" |
| 2 | Temporal in five minutes | 5 min | all five concepts + the determinism rule |
| 3 | Pipeline + per-task loop | 4 min | the two design rules + the Validation Contract |
| 4 | Where the two meet | 3 min | the mapping table only |
| 5 | Quality | 4 min | absolute vs advisory + the floor + "the LLM verdict never blocks" |
| 6 | Shared memory | 3 min | memory is I/O · the watermark · advisory-only |
| 7 | Logging | 2 min | the three-layer table + the metadata-only rule |
| 8 | Heatmap | 2 min | the density formula + the picture |
| 9 | Demo | 3 min | steps 3 and 4 only — kill the worker, approve the gate |
| 10 | Takeaways + Q&A | 1 min | the four "must not be non-deterministic" lines |

---

## Parked topics (say "out of scope" and move on)

- **Memory / Hindsight** — banks, recall filters, watermarks, nightly reflect.
- **The full benchmark harness** — four measurement axes, SC-1..6, drift.
- **DAPER maintenance loop.**
- **Model tiering and cost attribution per role.**
- **`HarnessSession` transcripts** (ADR-16) and the `deep_review` lens.

---

## Source material

| Slide content | Source |
|---|---|
| Stage DAG, component table, agent→construct mapping | `ARCHITECTURE.md` §1–§4 |
| Gate mechanics, signals, revision loop | `ARCHITECTURE.md` §5 |
| Timeouts, retries, `wait_condition`, queries, check assembly | `src/sdlc/workflows/feature.py` |
| Quality gate classes, floor, overrides | `src/sdlc/gate.py` |
| Run trace vocabulary | `src/sdlc/observability/trace.py` |
| Retro rendering (`report.html`, `events.jsonl`) | `src/sdlc/observability/export.py`, `summary.py` |
| Logfire gating and spans | `src/sdlc/observability/logfire_setup.py`, `activities.py` |
| Rework density, colours, language grouping | `src/sdlc/benchmarks/heatmap.py` |
| Heatmap file writes | `src/sdlc/benchmarks/report.py` |
| Demo commands | `src/sdlc/cli.py`, `README.md` |
