# E-32 — Retro stage (stage 14): `RunSummary` + reflect + export

| | |
|---|---|
| Date | 2026-07-22 |
| Roadmap item | E-32 (§9.8); §1 stage 14 |
| Anchors | FR-404, NFR-4, SC-4, SC-6, ADR §10 (calibration); folds **E-22** (`events.jsonl`) + **E-23** (`report.html`) |
| Status | Approved design — pre-plan |

## 1. Why

The 15-stage DAG has no stage 14. `reflect()` (`memory/activities.py:94`) and
`ReflectWorkflow` (nightly project consolidation, E-13) exist, but the
`FeatureWorkflow.run()` body returns from ~8 terminal points
(`deployed:…`, `merged-not-deployed:…`, `rejected:research|clarify|architecture|plan|merge:*`)
and **none of them** emits a run summary, calls `reflect()`, or exports a trace.

P3's phase exit is literally *"SC-4 and SC-6 measurable"*, and both are `—`
today. SC-4 (repeat-clarification <10% by run 10) and SC-6 (soft-gate override
<5%) need a per-run signal accumulated into memory, plus ARCHITECTURE §10's
"confidence vs human override" calibration compare. This stage produces that
signal, closes the learning loop, and — per the two folded items — renders the
`events.jsonl` + `report.html` export the spec (SDLC-spec-v2 §51, §153) assigns
to the retro stage.

**Scope decisions locked in brainstorming:**
- Retro fires on **every terminal path**, rejections included (rejected runs
  still carry clarifications + gate decisions worth learning from).
- E-32 **closes stage 14 completely**: `RunSummary` + `events.jsonl` +
  `report.html`. E-22/E-23 are folded in and marked done by this increment.
- Retro **retains the `RunSummary` and fire-and-forgets `reflect(project_bank)`**,
  both non-blocking and gated on `cfg.memory.enabled`. Nightly `reflect` (E-13)
  stays the org/cross-run half.

## 2. Control flow — the "every terminal path" guarantee

Extract today's `run()` body verbatim into `async def _pipeline(self, idea, cfg) -> str`.
`run()` becomes:

```python
@workflow.run
async def run(self, idea: IdeaBrief, cfg: PipelineConfig | None = None) -> str:
    cfg = cfg or PipelineConfig()
    result = await self._pipeline(idea, cfg)   # returns on EVERY terminal path
    await self._retro(cfg, idea, result)       # stage 14
    return result
```

Every terminal path in this workflow is a `return "<outcome>"` string, **not** a
raised exception. Capturing the returned result and *then* running retro
therefore covers all eight designed terminal outcomes.

**Why not `try/finally` around retro:** wrapping activities in a `finally` is a
determinism / duplication hazard during a *failing* workflow task in Temporal.
Genuine uncaught exceptions are crashes — Temporal retries the workflow task and
the run never reaches a terminal state — so there is no run to summarize.
Retro-on-crash is intentionally out of scope; result-capture-then-retro achieves
the selected "every terminal path" intent the Temporal-correct way.

`_retro` additionally **swallows its own errors** (log + continue, exactly like
`_retain`). A retro or export failure can never change the run's actual return
string. The return type stays `str` — benchmarks, CLI, and tests depend on it;
`RunSummary` is surfaced by query + export + memory, never as the return value.

## 3. Data model

### 3.1 `RunEvent` — the domain trace (backbone of `events.jsonl`)

New module `src/sdlc/observability/trace.py` (pure pydantic, sandbox-safe):

```python
class RunEventKind(str, Enum):
    STAGE_STARTED = "stage_started"
    STAGE_ENDED = "stage_ended"
    GATE_AWAITED = "gate_awaited"
    GATE_DECIDED = "gate_decided"
    CLARIFICATION_ASKED = "clarification_asked"
    CLARIFICATION_ANSWERED = "clarification_answered"
    FIX_ATTEMPT = "fix_attempt"
    MEMORY_RETAINED = "memory_retained"
    RUN_FINISHED = "run_finished"

class RunEvent(BaseModel):
    seq: int
    at: datetime
    kind: RunEventKind
    stage: str | None = None
    data: dict[str, str] = Field(default_factory=dict)
```

`data` is `dict[str, str]` deliberately — a flat, JSON-line-friendly payload;
numeric fields are stringified at emit and parsed by the reader. Keeps
`events.jsonl` a stable, greppable line format and the model trivially
serializable.

The trace lives in workflow state (`self._trace: list[RunEvent]`), which is
already durable in Temporal history. The export is a **rendering** of it, not a
second source of truth — consistent with SDLC-spec §153 ("Temporal event history
is the record of truth; `events.jsonl` + `report.html` become an export").
Rejected: reconstructing the trace by reading raw Temporal history at retro time
— the raw history is low-level and the domain event is what the export needs.

### 3.2 `RunSummary` — the aggregate (drives `report.html` + the SC signal)

Added to `src/sdlc/models.py`:

```python
class StageOutcome(BaseModel):
    stage: str
    role: str
    outcome: str            # BenchmarkOutcome value
    duration_s: float
    cost_usd: float | None = None
    fix_attempts: int = 0

class ClarificationOutcome(BaseModel):
    question_id: str
    question: str
    answered_by: Literal["human", "suggested", "unanswered"]  # SC-4 signal

class GateOutcomeSummary(BaseModel):
    gate: str
    round: int
    policy: str             # GatePolicy value
    decided_by: str         # "human" | "policy" | "timeout"
    approved: bool
    confidence: float | None = None                          # §10 calibration
    overrides: list[str] = Field(default_factory=list)       # advisory checks waved (SC-6)

class RunSummary(BaseModel):
    run_id: str
    mode: str               # IdeaBrief.mode
    outcome: str            # the run() return string
    terminal_stage: str     # last stage reached
    started_at: datetime
    ended_at: datetime
    duration_s: float
    stages: list[StageOutcome] = Field(default_factory=list)
    clarifications: list[ClarificationOutcome] = Field(default_factory=list)
    gates: list[GateOutcomeSummary] = Field(default_factory=list)
    cost_usd_total: float | None = None
    memory_enabled: bool = False
    memory_watermark: str | None = None
    memory_retains: int = 0
```

**How the SC signal lands:**
- **SC-4** (repeat clarifications): `clarifications[].answered_by` distinguishes
  a human answer (costs operator time) from a `suggested` auto-fill (the
  clarifier's own `suggested_answer`, taken under an OFF clarify policy) from an
  `unanswered` (timed-out) one; the retained `RunSummary` is what a later run's
  aggregation compares against to detect a repeat by run 10. (No path today
  auto-answers a *surfaced* question directly from recall — recall feeds the
  clarifier prompt, which may reduce how many questions are surfaced at all.)
- **SC-6** (soft-gate override): `gates[].overrides` (advisory checks a human
  waved through) and `gates[].decided_by` give the override rate; `confidence` vs
  `approved`/`decided_by` gives the §10 calibration compare (predicted confidence
  vs actual human decision).

### 3.3 Memory kind

`MemoryKind.RUN_SUMMARY = "run_summary"` added to the enum (`models.py:420`).

## 4. Instrumentation — 4 chokepoints, no stage rewrite

A private `_emit(self, kind, stage=None, **data)` appends a `RunEvent`
(monotonic `seq`, `at=workflow.now()`) to `self._trace`. Wired only at existing
seams:

1. **`_record()`** — already called at every stage boundary (`feature.py:411,
   610, 820, 888, 927, 1025, 1032, 1101, 1106, 1159, 1185`). It emits a
   `STAGE_ENDED` event (stage, role, outcome, duration_s, cost, fix_attempts)
   **before** the `_benchmarking(cfg)` early-return, so the trace is captured
   even when benchmarking is off. The benchmarking activity call is unchanged.
2. **`_gate()`** — the single resolution point for human / policy / timeout.
   Emits `GATE_AWAITED` on entering the wait and `GATE_DECIDED` on resolution
   (gate, round, policy, decided_by, approved, confidence). `confidence` is not
   carried by `GateDecision`; it is the artifact confidence the caller already
   computes for the soft-gate `_auto_decision_for` path, threaded into the gate
   call so the emit records it — `None` for hard/off gates that have no
   confidence input.
3. **`answer_question` signal + the clarify stage** — `CLARIFICATION_ASKED` when
   an open question is surfaced, `CLARIFICATION_ANSWERED` (with `answered_by`)
   when resolved.
4. **`_dev_task` fix loop** — `FIX_ATTEMPT` per attempt (task_id, attempt,
   resolved).

`_retro` reads `self._trace` + existing state (`self._gate_decisions`,
`self._question_answers`) to build the `RunSummary`; `overrides` come from the
merge stage, which already computes the local `overrides` list — it emits them
onto the `GATE_DECIDED` event's `data`.

## 5. Memory (gated, non-blocking)

Inside `_retro`, when `cfg.memory.enabled`:
1. `retain(RunSummary.model_dump_json())` as `kind=RUN_SUMMARY`, `bank=project_bank`.
2. fire-and-forget `reflect(project_bank)`.

Both go through the existing `_retain`-style error-swallowing path — a memory
backend failure logs and continues. When memory is disabled (the default) this
whole block is a no-op, exactly like the rest of the pipeline's memory usage.

## 6. Export (folds E-22 + E-23)

New `src/sdlc/observability/` module and one activity
`export_run_artifacts(RunExportInput)`. File I/O lives in the activity, never in
workflow code.

- **`events.jsonl`** — one `RunEvent` per line, in `seq` order, from `self._trace`.
- **`report.html`** — a self-contained, deterministic HTML template (no LLM) over
  `RunSummary`: header (run_id, mode, outcome, duration), a stages table, a gate
  table (policy / decided_by / confidence / overrides), a clarifications section,
  a fix-loop section, and the cost/memory footer. Inline CSS, no external assets.

**Path resolution stays in the activity.** The workflow passes `run_id`,
`RunSummary`, and the trace; the activity resolves `SDLC_EXPORT_ROOT` from env
(default `./runs`) and writes `<root>/<run_id>/{events.jsonl, report.html}` —
same determinism discipline as the integration-worktree path being resolved in
`setup_integration_branch`, so the workflow never reads env or computes a path.
Export is best-effort: a failure logs and does not fail retro.

## 7. Query surface

New `@workflow.query def run_summary(self) -> RunSummary | None` — `None` until
retro has run, the built `RunSummary` after. Lets the CLI / channels / tests read
the summary without parsing the exported files.

## 8. Testing

**Unit:**
- `RunSummary` aggregation from a synthetic `self._trace` covering: a
  rejected-at-clarify run, a soft-gate-override run, and a clean `deployed:` run
  — asserting `clarifications[].answered_by` and `gates[].overrides`/`confidence`
  are populated as SC-4/SC-6 require.
- `report.html` renders every section and is self-contained (no external refs);
  `events.jsonl` round-trips (`RunEvent` per line, `seq`-ordered).
- `export_run_artifacts` resolves `SDLC_EXPORT_ROOT` and writes both files.

**Workflow (extend the existing fake-activity e2e):**
- Retro fires and `run_summary()` returns populated data on a `deployed:` run.
- Retro fires on a `rejected:merge:*` run (proves every-terminal-path coverage).
- A raised export/retro failure does **not** change the run's return string.
- With `memory.enabled=True`, `retain(RUN_SUMMARY)` + `reflect(project_bank)` are
  invoked; with it disabled, neither is.

## 9. File touch list

- `src/sdlc/models.py` — `RunSummary`, `StageOutcome`, `ClarificationOutcome`,
  `GateOutcomeSummary`, `MemoryKind.RUN_SUMMARY`.
- `src/sdlc/observability/__init__.py`, `trace.py` (`RunEvent`, `RunEventKind`),
  `export.py` (renderers), `activities.py` (`export_run_artifacts` +
  `RunExportInput`).
- `src/sdlc/workflows/feature.py` — extract `_pipeline`, add `run` wrapper,
  `_retro`, `_emit`, `self._trace`, `run_summary()` query, `_emit` calls at the 4
  chokepoints.
- Worker registration for the new activity.
- Tests under `tests/` (+ fakes as needed).

## 10. Out of scope (explicit)

- Retro-on-crash (uncaught exceptions — Temporal retries, no terminal state).
- Org-bank writers / `reflect(org)` from the retro stage — stays **E-25**.
- The actual SC-4/SC-6 *aggregation across runs* — this stage produces the
  per-run signal; computing the cross-run rate is the benchmark's job (§9.8).
- Changing the `run()` return contract.
