# E-32 Retro Stage (RunSummary + reflect + export) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pipeline stage 14 (retro): on every terminal path, emit a `RunSummary`, retain it + fire-and-forget `reflect(project_bank)`, and export `events.jsonl` + `report.html`.

**Architecture:** A pure in-workflow event trace (`self._trace: list[RunEvent]`) is populated at four existing chokepoints. After the pipeline body returns its terminal string, `run()` calls `_retro`, which builds a `RunSummary` from the trace via a pure aggregation function, retains it + reflects (gated on `memory.enabled`), and calls an export activity that writes the two files. All aggregation and rendering logic is pure and unit-tested outside the workflow; the workflow only wires it.

**Tech Stack:** Python 3, Pydantic v2, Temporal (`temporalio`), pytest + `pytest-asyncio`, Temporal `WorkflowEnvironment.start_time_skipping` for workflow tests.

## Global Constraints

- **Sandbox purity:** workflow code (`src/sdlc/workflows/feature.py`) performs no I/O and reads no env/clock directly — file writes and `os.environ` reads live in activities; time comes from `workflow.now()`. New pure models imported into the workflow must sit under `with workflow.unsafe.imports_passed_through():` and pull in no `temporalio`/agents/I/O.
- **Determinism:** the export root path is resolved inside the activity from `SDLC_EXPORT_ROOT` (default `./runs`); the workflow passes only `run_id`, the `RunSummary`, and the trace.
- **Best-effort retro:** `_retro` and the export activity swallow their own errors (log + continue). Neither may change the run's return string. The `run()` return type stays `str`.
- **Memory gating:** every memory call is gated on `cfg.memory.enabled` (default `False`); when disabled the retro memory block is a no-op, exactly like the rest of the pipeline.
- **Pydantic data converter:** all new models must serialize through `temporalio.contrib.pydantic.pydantic_data_converter` (plain `BaseModel`, JSON-friendly fields).
- **Naming:** the workflow class name `FeatureWorkflow` and `ReflectWorkflow` are Temporal contracts — never rename.

---

## File Structure

- `src/sdlc/observability/__init__.py` — new package marker.
- `src/sdlc/observability/trace.py` — `RunEventKind`, `RunEvent` (pure).
- `src/sdlc/observability/summary.py` — pure `build_run_summary(...)` aggregation.
- `src/sdlc/observability/export.py` — pure renderers `render_events_jsonl`, `render_report_html`.
- `src/sdlc/observability/activities.py` — `RunExportInput`, `export_run_artifacts` activity (file I/O).
- `src/sdlc/models.py` — `StageOutcome`, `ClarificationOutcome`, `GateOutcomeSummary`, `RunSummary`, `MemoryKind.RUN_SUMMARY`.
- `src/sdlc/workflows/feature.py` — extract `_pipeline`, add `run` wrapper, `self._trace`, `_emit`, chokepoint emits, `run_summary()` query, `_retro`.
- `src/sdlc/worker.py` — register `export_run_artifacts`.
- `tests/test_observability_trace.py`, `tests/test_run_summary_model.py`, `tests/test_run_summary_build.py`, `tests/test_observability_export.py`, `tests/test_export_activity.py`, `tests/test_retro_stage.py` — new tests.

---

## Task 1: `RunEvent` trace model

**Files:**
- Create: `src/sdlc/observability/__init__.py`
- Create: `src/sdlc/observability/trace.py`
- Test: `tests/test_observability_trace.py`

**Interfaces:**
- Produces: `RunEventKind(str, Enum)` with members `STAGE_STARTED`, `STAGE_ENDED`, `GATE_AWAITED`, `GATE_DECIDED`, `CLARIFICATION_ASKED`, `CLARIFICATION_ANSWERED`, `FIX_ATTEMPT`, `MEMORY_RETAINED`, `RUN_FINISHED`. `RunEvent(BaseModel)` with `seq: int`, `at: datetime`, `kind: RunEventKind`, `stage: str | None = None`, `data: dict[str, str] = {}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_observability_trace.py
from datetime import datetime, timezone

from sdlc.observability.trace import RunEvent, RunEventKind


def test_run_event_serializes_json_line():
    ev = RunEvent(
        seq=3,
        at=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        kind=RunEventKind.GATE_DECIDED,
        stage="architecture",
        data={"decided_by": "human", "approved": "true"},
    )
    dumped = ev.model_dump_json()
    back = RunEvent.model_validate_json(dumped)
    assert back == ev
    assert back.kind is RunEventKind.GATE_DECIDED
    assert back.data["approved"] == "true"


def test_run_event_kind_values_are_stable():
    assert RunEventKind.STAGE_ENDED.value == "stage_ended"
    assert RunEventKind.CLARIFICATION_ANSWERED.value == "clarification_answered"
    assert RunEventKind.RUN_FINISHED.value == "run_finished"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_observability_trace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.observability'`

- [ ] **Step 3: Create the package marker**

```python
# src/sdlc/observability/__init__.py
"""Observability: run trace, RunSummary aggregation, and export (E-32)."""
```

- [ ] **Step 4: Write the trace module**

```python
# src/sdlc/observability/trace.py
"""Domain run-trace types (E-32).

Pure pydantic, sandbox-safe: no temporalio, no I/O. The workflow accumulates
a list[RunEvent] in state (already durable in Temporal history); events.jsonl
is a rendering of it, not a second source of truth.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


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
    """One domain event. `data` is a flat str->str map so events.jsonl stays a
    stable, greppable line format; numeric values are stringified at emit."""
    seq: int
    at: datetime
    kind: RunEventKind
    stage: str | None = None
    data: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_observability_trace.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/observability/__init__.py src/sdlc/observability/trace.py tests/test_observability_trace.py
git commit -m "feat(observability): RunEvent domain trace model (E-32)"
```

---

## Task 2: `RunSummary` + sub-models + memory kind

**Files:**
- Modify: `src/sdlc/models.py` (add models near the other run/memory models; add enum member to `MemoryKind` at `models.py:420`)
- Test: `tests/test_run_summary_model.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `StageOutcome(BaseModel)`: `stage: str`, `role: str`, `outcome: str`, `duration_s: float`, `cost_usd: float | None = None`, `fix_attempts: int = 0`.
  - `ClarificationOutcome(BaseModel)`: `question_id: str`, `question: str`, `answered_by: Literal["human", "suggested", "unanswered"]`.
  - `GateOutcomeSummary(BaseModel)`: `gate: str`, `round: int`, `policy: str`, `decided_by: str`, `approved: bool`, `confidence: float | None = None`, `overrides: list[str] = []`.
  - `RunSummary(BaseModel)`: `run_id: str`, `mode: str`, `outcome: str`, `terminal_stage: str`, `started_at: datetime`, `ended_at: datetime`, `duration_s: float`, `stages: list[StageOutcome] = []`, `clarifications: list[ClarificationOutcome] = []`, `gates: list[GateOutcomeSummary] = []`, `cost_usd_total: float | None = None`, `memory_enabled: bool = False`, `memory_watermark: str | None = None`, `memory_retains: int = 0`.
  - `MemoryKind.RUN_SUMMARY = "run_summary"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_summary_model.py
from datetime import datetime, timezone

from sdlc.models import (
    ClarificationOutcome, GateOutcomeSummary, MemoryKind, RunSummary,
    StageOutcome,
)


def test_run_summary_round_trips():
    s = RunSummary(
        run_id="r1", mode="greenfield", outcome="deployed:http://pr",
        terminal_stage="deploy",
        started_at=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc),
        duration_s=1800.0,
        stages=[StageOutcome(stage="clarify", role="clarify",
                             outcome="pass", duration_s=5.0)],
        clarifications=[ClarificationOutcome(
            question_id="q1", question="scope?", answered_by="human")],
        gates=[GateOutcomeSummary(gate="architecture", round=1, policy="hard",
                                  decided_by="human", approved=True,
                                  confidence=0.9, overrides=[])],
        cost_usd_total=1.23,
        memory_enabled=True, memory_watermark="7",
        memory_retains=4,
    )
    assert RunSummary.model_validate_json(s.model_dump_json()) == s


def test_memory_kind_has_run_summary():
    assert MemoryKind.RUN_SUMMARY.value == "run_summary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_summary_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'RunSummary'`

- [ ] **Step 3: Add `MemoryKind.RUN_SUMMARY`**

In `src/sdlc/models.py`, extend the `MemoryKind` enum (currently ends at
`RESEARCH_FINDING = "research_finding"`):

```python
class MemoryKind(str, Enum):
    STAGE_SUMMARY = "stage_summary"
    GOTCHA = "gotcha"
    GATE_FEEDBACK = "gate_feedback"
    RESEARCH_FINDING = "research_finding"    # verified grounded findings only
    RUN_SUMMARY = "run_summary"              # retro-stage per-run summary (E-32)
```

- [ ] **Step 4: Add the RunSummary models**

Append to `src/sdlc/models.py` (after `RetainItem` / near the memory models;
`datetime`, `Literal`, `Field`, `BaseModel` are already imported at the top):

```python
class StageOutcome(BaseModel):
    """One stage's line in a RunSummary, projected from its BenchmarkRecord."""
    stage: str
    role: str
    outcome: str            # BenchmarkOutcome value
    duration_s: float
    cost_usd: float | None = None
    fix_attempts: int = 0


class ClarificationOutcome(BaseModel):
    """SC-4 signal: was a surfaced question answered by a human (operator time),
    auto-filled from the clarifier's suggested_answer, or left unanswered."""
    question_id: str
    question: str
    answered_by: Literal["human", "suggested", "unanswered"]


class GateOutcomeSummary(BaseModel):
    """SC-6 + ARCHITECTURE §10 calibration signal: policy, who decided, the
    confidence available at decision time, and any advisory checks waved."""
    gate: str
    round: int
    policy: str             # GatePolicy value
    decided_by: str         # "human" | "policy" | "timeout"
    approved: bool
    confidence: float | None = None
    overrides: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Retro-stage (14) aggregate of one run (E-32). Retained to memory,
    exported to report.html, and exposed via the run_summary() query."""
    run_id: str
    mode: str
    outcome: str            # the run() return string
    terminal_stage: str
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

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_run_summary_model.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_run_summary_model.py
git commit -m "feat(models): RunSummary + StageOutcome/ClarificationOutcome/GateOutcomeSummary + RUN_SUMMARY kind (E-32)"
```

---

## Task 3: Pure `build_run_summary` aggregation

**Files:**
- Create: `src/sdlc/observability/summary.py`
- Test: `tests/test_run_summary_build.py`

**Interfaces:**
- Consumes: `RunEvent`/`RunEventKind` (Task 1); `RunSummary` and sub-models (Task 2).
- Produces:
  ```python
  def build_run_summary(
      *, run_id: str, mode: str, outcome: str,
      trace: list[RunEvent],
      memory_enabled: bool, memory_watermark: str | None,
  ) -> RunSummary: ...
  ```
  Aggregation rules (all derived from `trace`):
  - `stages`: one `StageOutcome` per `STAGE_ENDED` event, reading
    `data["role"]`, `data["outcome"]`, `float(data["duration_s"])`,
    `float(data["cost_usd"])` if present, `int(data.get("fix_attempts", "0"))`.
  - `clarifications`: one `ClarificationOutcome` per `CLARIFICATION_ASKED`,
    with `answered_by` taken from the matching `CLARIFICATION_ANSWERED`
    (`data["answered_by"]`) for the same `data["question_id"]`, else `"unanswered"`.
  - `gates`: one `GateOutcomeSummary` per `GATE_DECIDED`, **deduplicated by
    `(gate, round)` keeping the last occurrence** — the merge stage emits a bare
    `GATE_DECIDED` from `_gate` and then an enriched one carrying `overrides`, and
    last-wins keeps the enriched row; distinct revision rounds keep distinct keys.
    Read `data["gate"]`, `int(data["round"])`, `data["policy"]`,
    `data["decided_by"]`, `data["approved"] == "true"`, `float(data["confidence"])`
    if present, and `data["overrides"]` split on `,` when non-empty.
  - `terminal_stage`: `stage` of the last `STAGE_ENDED` event, else `"intake"`.
  - `started_at` = first event's `at`; `ended_at` = last event's `at`;
    `duration_s` = their difference in seconds. Callers always pass a non-empty
    trace — retro emits `RUN_FINISHED` before calling — so no empty-trace branch
    is needed.
  - `cost_usd_total`: sum of stage `cost_usd` values that are not None; `None`
    if none are present.
  - `memory_retains`: count of `MEMORY_RETAINED` events.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_summary_build.py
from datetime import datetime, timedelta, timezone

from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _ev(seq, kind, stage=None, **data):
    return RunEvent(seq=seq, at=T0 + timedelta(seconds=seq), kind=kind,
                    stage=stage, data={k: str(v) for k, v in data.items()})


def test_clean_deploy_aggregates_stages_and_gate():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q1",
            question="scope?"),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="q1",
            answered_by="human"),
        _ev(2, RunEventKind.STAGE_ENDED, stage="clarify", role="clarify",
            outcome="pass", duration_s=2.0, cost_usd=0.10),
        _ev(3, RunEventKind.GATE_DECIDED, gate="architecture", round=1,
            policy="hard", decided_by="human", approved="true", confidence=0.9),
        _ev(4, RunEventKind.STAGE_ENDED, stage="architecture", role="architect",
            outcome="pass", duration_s=3.0, cost_usd=0.20),
        _ev(5, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(run_id="r1", mode="greenfield",
                          outcome="deployed:http://pr", trace=trace,
                          memory_enabled=False, memory_watermark=None)
    assert s.terminal_stage == "architecture"
    assert [x.stage for x in s.stages] == ["clarify", "architecture"]
    assert s.clarifications[0].answered_by == "human"
    assert s.gates[0].confidence == 0.9 and s.gates[0].approved is True
    assert abs(s.cost_usd_total - 0.30) < 1e-9
    assert s.duration_s == 5.0


def test_unanswered_clarification_and_override_gate():
    trace = [
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="q9",
            question="deadline?"),
        _ev(1, RunEventKind.GATE_DECIDED, gate="merge", round=1, policy="soft",
            decided_by="human", approved="true", overrides="coverage,traceability"),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(run_id="r2", mode="greenfield",
                          outcome="rejected:merge:advisory", trace=trace,
                          memory_enabled=True, memory_watermark="4")
    assert s.clarifications[0].answered_by == "unanswered"
    assert s.gates[0].overrides == ["coverage", "traceability"]
    assert s.cost_usd_total is None
    assert s.memory_enabled is True and s.memory_watermark == "4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_summary_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.observability.summary'`

- [ ] **Step 3: Write the aggregation module**

```python
# src/sdlc/observability/summary.py
"""Pure trace -> RunSummary aggregation (E-32). No I/O, no temporalio: unit-
testable outside the workflow, called once from the retro stage."""
from __future__ import annotations

from ..models import (
    ClarificationOutcome, GateOutcomeSummary, RunSummary, StageOutcome,
)
from .trace import RunEvent, RunEventKind


def _stage_outcome(ev: RunEvent) -> StageOutcome:
    d = ev.data
    cost = d.get("cost_usd")
    return StageOutcome(
        stage=ev.stage or d.get("stage", "?"),
        role=d.get("role", "?"),
        outcome=d.get("outcome", "?"),
        duration_s=float(d.get("duration_s", "0")),
        cost_usd=float(cost) if cost is not None else None,
        fix_attempts=int(d.get("fix_attempts", "0")),
    )


def _gate_outcome(ev: RunEvent) -> GateOutcomeSummary:
    d = ev.data
    conf = d.get("confidence")
    ov = d.get("overrides", "")
    return GateOutcomeSummary(
        gate=d.get("gate", "?"),
        round=int(d.get("round", "1")),
        policy=d.get("policy", "?"),
        decided_by=d.get("decided_by", "?"),
        approved=d.get("approved") == "true",
        confidence=float(conf) if conf is not None else None,
        overrides=[c for c in ov.split(",") if c],
    )


def build_run_summary(
    *, run_id: str, mode: str, outcome: str,
    trace: list[RunEvent],
    memory_enabled: bool, memory_watermark: str | None,
) -> RunSummary:
    stages = [_stage_outcome(e) for e in trace
              if e.kind is RunEventKind.STAGE_ENDED]

    # Dedup gates by (gate, round), last-wins: the merge stage emits a bare
    # GATE_DECIDED from _gate and then an enriched one carrying overrides;
    # distinct revision rounds keep distinct keys.
    gate_by_key: dict[tuple[str, int], GateOutcomeSummary] = {}
    for e in trace:
        if e.kind is RunEventKind.GATE_DECIDED:
            g = _gate_outcome(e)
            gate_by_key[(g.gate, g.round)] = g
    gates = list(gate_by_key.values())

    answered = {e.data.get("question_id"): e.data.get("answered_by", "unanswered")
                for e in trace if e.kind is RunEventKind.CLARIFICATION_ANSWERED}
    clarifications = [
        ClarificationOutcome(
            question_id=e.data.get("question_id", "?"),
            question=e.data.get("question", ""),
            answered_by=answered.get(e.data.get("question_id"), "unanswered"),
        )
        for e in trace if e.kind is RunEventKind.CLARIFICATION_ASKED
    ]

    terminal = next((e.stage for e in reversed(trace)
                     if e.kind is RunEventKind.STAGE_ENDED and e.stage),
                    "intake")
    costs = [s.cost_usd for s in stages if s.cost_usd is not None]
    started = trace[0].at
    ended = trace[-1].at
    retains = sum(1 for e in trace if e.kind is RunEventKind.MEMORY_RETAINED)

    return RunSummary(
        run_id=run_id, mode=mode, outcome=outcome, terminal_stage=terminal,
        started_at=started, ended_at=ended,
        duration_s=(ended - started).total_seconds(),
        stages=stages, clarifications=clarifications, gates=gates,
        cost_usd_total=(sum(costs) if costs else None),
        memory_enabled=memory_enabled, memory_watermark=memory_watermark,
        memory_retains=retains,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_summary_build.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/observability/summary.py tests/test_run_summary_build.py
git commit -m "feat(observability): pure build_run_summary trace aggregation (E-32)"
```

---

## Task 4: Pure export renderers (`events.jsonl` + `report.html`)

**Files:**
- Create: `src/sdlc/observability/export.py`
- Test: `tests/test_observability_export.py`

**Interfaces:**
- Consumes: `RunEvent` (Task 1), `RunSummary` (Task 2).
- Produces:
  - `render_events_jsonl(trace: list[RunEvent]) -> str` — one `RunEvent.model_dump_json()` per line, `seq`-ordered, trailing newline.
  - `render_report_html(summary: RunSummary) -> str` — a self-contained HTML string (inline CSS, no external refs) with a header, a stages table, a gates table, a clarifications list, and a cost/memory footer.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_observability_export.py
from datetime import datetime, timezone

from sdlc.models import (
    ClarificationOutcome, GateOutcomeSummary, RunSummary, StageOutcome,
)
from sdlc.observability.export import render_events_jsonl, render_report_html
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _summary():
    return RunSummary(
        run_id="r1", mode="greenfield", outcome="deployed:http://pr",
        terminal_stage="deploy", started_at=T0, ended_at=T0, duration_s=0.0,
        stages=[StageOutcome(stage="clarify", role="clarify", outcome="pass",
                             duration_s=2.0, cost_usd=0.1)],
        clarifications=[ClarificationOutcome(question_id="q1", question="scope?",
                                             answered_by="human")],
        gates=[GateOutcomeSummary(gate="merge", round=1, policy="soft",
                                  decided_by="human", approved=True,
                                  overrides=["coverage"])],
        cost_usd_total=0.1, memory_enabled=True, memory_watermark="3",
        memory_retains=2,
    )


def test_events_jsonl_is_one_line_per_event_seq_ordered():
    trace = [
        RunEvent(seq=1, at=T0, kind=RunEventKind.STAGE_ENDED, stage="clarify"),
        RunEvent(seq=0, at=T0, kind=RunEventKind.STAGE_STARTED, stage="clarify"),
    ]
    out = render_events_jsonl(trace)
    lines = out.splitlines()
    assert len(lines) == 2
    first = RunEvent.model_validate_json(lines[0])
    assert first.seq == 0  # sorted by seq
    assert RunEvent.model_validate_json(lines[1]).seq == 1


def test_report_html_is_self_contained_and_covers_sections():
    html = render_report_html(_summary())
    assert html.lstrip().startswith("<!doctype html>")
    # self-contained: no external resource references
    assert "http://" not in html.replace("deployed:http://pr", "")
    assert "src=" not in html and "href=" not in html
    for token in ("r1", "deployed:", "clarify", "merge", "scope?", "coverage"):
        assert token in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_observability_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.observability.export'`

- [ ] **Step 3: Write the export renderers**

```python
# src/sdlc/observability/export.py
"""Pure renderers for the retro export (E-32). No I/O: the activity in
activities.py owns the file writes; these turn state into strings.

report.html is deliberately a deterministic, dependency-free template — the
retro stage is `(deterministic + reflect)`, no LLM (SDLC-spec §58)."""
from __future__ import annotations

from html import escape

from ..models import RunSummary
from .trace import RunEvent


def render_events_jsonl(trace: list[RunEvent]) -> str:
    lines = [e.model_dump_json()
             for e in sorted(trace, key=lambda e: e.seq)]
    return "\n".join(lines) + ("\n" if lines else "")


def _row(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in cells) + "</tr>"


def render_report_html(s: RunSummary) -> str:
    stage_rows = "".join(
        _row([st.stage, st.role, st.outcome, f"{st.duration_s:.1f}s",
              "-" if st.cost_usd is None else f"${st.cost_usd:.4f}",
              str(st.fix_attempts)])
        for st in s.stages)
    gate_rows = "".join(
        _row([g.gate, str(g.round), g.policy, g.decided_by,
              "yes" if g.approved else "no",
              "-" if g.confidence is None else f"{g.confidence:.2f}",
              ", ".join(g.overrides) or "-"])
        for g in s.gates)
    clar_rows = "".join(
        _row([c.question_id, c.question, c.answered_by])
        for c in s.clarifications)
    cost = "-" if s.cost_usd_total is None else f"${s.cost_usd_total:.4f}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Run {escape(s.run_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} table{{border-collapse:collapse;margin:.5rem 0 1.5rem}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:left}}
th{{background:#f3f3f3}} .meta{{color:#555}}
</style></head><body>
<h1>Run {escape(s.run_id)}</h1>
<p class="meta">mode={escape(s.mode)} &middot; outcome=<b>{escape(s.outcome)}</b>
&middot; terminal_stage={escape(s.terminal_stage)}
&middot; duration={s.duration_s:.1f}s &middot; cost={cost}</p>
<h2>Stages</h2>
<table><tr><th>stage</th><th>role</th><th>outcome</th><th>duration</th>
<th>cost</th><th>fix_attempts</th></tr>{stage_rows}</table>
<h2>Gates</h2>
<table><tr><th>gate</th><th>round</th><th>policy</th><th>decided_by</th>
<th>approved</th><th>confidence</th><th>overrides</th></tr>{gate_rows}</table>
<h2>Clarifications</h2>
<table><tr><th>id</th><th>question</th><th>answered_by</th></tr>{clar_rows}</table>
<p class="meta">memory_enabled={s.memory_enabled}
&middot; watermark={escape(str(s.memory_watermark))}
&middot; retains={s.memory_retains}</p>
</body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_observability_export.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/observability/export.py tests/test_observability_export.py
git commit -m "feat(observability): pure events.jsonl + report.html renderers (E-32)"
```

---

## Task 5: `export_run_artifacts` activity

**Files:**
- Create: `src/sdlc/observability/activities.py`
- Test: `tests/test_export_activity.py`

**Interfaces:**
- Consumes: `RunEvent` (Task 1), `RunSummary` (Task 2), renderers (Task 4).
- Produces:
  - `RunExportInput(BaseModel)`: `run_id: str`, `summary: RunSummary`, `trace: list[RunEvent]`.
  - `@activity.defn async def export_run_artifacts(inp: RunExportInput) -> str` — resolves the root from `SDLC_EXPORT_ROOT` (default `./runs`), writes `<root>/<run_id>/events.jsonl` and `report.html`, returns the run directory path as a string. The determinism boundary: env + filesystem are read here, never in the workflow.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_activity.py
from datetime import datetime, timezone

import pytest

from sdlc.models import RunSummary
from sdlc.observability.activities import RunExportInput, export_run_artifacts
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_export_writes_both_files_under_export_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    summary = RunSummary(run_id="run-xyz", mode="greenfield",
                         outcome="deployed:pr", terminal_stage="deploy",
                         started_at=T0, ended_at=T0, duration_s=0.0)
    trace = [RunEvent(seq=0, at=T0, kind=RunEventKind.RUN_FINISHED)]
    out = await export_run_artifacts(
        RunExportInput(run_id="run-xyz", summary=summary, trace=trace))
    run_dir = tmp_path / "run-xyz"
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "report.html").exists()
    assert "run-xyz" in (run_dir / "report.html").read_text(encoding="utf-8")
    assert out == str(run_dir)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_activity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.observability.activities'`

- [ ] **Step 3: Write the activity**

```python
# src/sdlc/observability/activities.py
"""Retro export activity (E-32). Owns the filesystem + env reads the workflow
must not do. Path resolution here (SDLC_EXPORT_ROOT) mirrors how
setup_integration_branch resolves the worktree root inside an activity."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

from ..models import RunSummary
from .export import render_events_jsonl, render_report_html
from .trace import RunEvent


class RunExportInput(BaseModel):
    run_id: str
    summary: RunSummary
    trace: list[RunEvent] = Field(default_factory=list)


@activity.defn
async def export_run_artifacts(inp: RunExportInput) -> str:
    root = Path(os.environ.get("SDLC_EXPORT_ROOT", "./runs"))
    run_dir = root / inp.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text(
        render_events_jsonl(inp.trace), encoding="utf-8")
    (run_dir / "report.html").write_text(
        render_report_html(inp.summary), encoding="utf-8")
    return str(run_dir)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_activity.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/observability/activities.py tests/test_export_activity.py
git commit -m "feat(observability): export_run_artifacts activity (E-32)"
```

---

## Task 6: Extract `_pipeline` (pure refactor, no behavior change)

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (the `@workflow.run def run` at `feature.py:667`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `async def _pipeline(self, idea: IdeaBrief, cfg: PipelineConfig) -> str` containing today's run body; `run()` delegates to it. No retro yet — this task must leave observable behavior identical so the existing e2e suite stays green.

- [ ] **Step 1: Confirm the existing e2e tests pass (baseline)**

Run: `python -m pytest tests/test_e2e_greenfield.py -v`
Expected: PASS (2 passed) — this is the regression baseline for the refactor.

- [ ] **Step 2: Rename `run` to `_pipeline` and add a thin `run` wrapper**

In `src/sdlc/workflows/feature.py`, the current method is:

```python
    @workflow.run
    async def run(self, idea: IdeaBrief,
                  cfg: PipelineConfig | None = None) -> str:
        cfg = cfg or PipelineConfig()
        if cfg.memory.enabled:
            ...  # (entire existing body through every `return "..."`)
```

Change it to move the body into `_pipeline` and add the wrapper. Keep the
`cfg = cfg or PipelineConfig()` line in `run()` and pass the resolved `cfg`
into `_pipeline` (so `_pipeline` receives a non-None `cfg`):

```python
    @workflow.run
    async def run(self, idea: IdeaBrief,
                  cfg: PipelineConfig | None = None) -> str:
        cfg = cfg or PipelineConfig()
        return await self._pipeline(idea, cfg)

    async def _pipeline(self, idea: IdeaBrief, cfg: PipelineConfig) -> str:
        if cfg.memory.enabled:
            self._memory_watermark = cfg.memory.watermark or (
                ...)
        # ... the rest of the existing body verbatim, unchanged ...
```

Concretely: delete the old `cfg = cfg or PipelineConfig()` line from the
moved body (it now lives in `run`), change the moved method's signature to
`async def _pipeline(self, idea: IdeaBrief, cfg: PipelineConfig) -> str:`, and
drop the `@workflow.run` decorator from it (it now decorates `run`). Every
existing `return "..."` inside the body stays exactly as is.

- [ ] **Step 3: Run the e2e suite to verify no behavior change**

Run: `python -m pytest tests/test_e2e_greenfield.py -v`
Expected: PASS (2 passed) — identical to the Step 1 baseline.

- [ ] **Step 4: Run the broader workflow-adjacent tests**

Run: `python -m pytest tests/test_gate_revision_loop.py tests/test_factory_purity.py -v`
Expected: PASS (no regressions from the extraction).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py
git commit -m "refactor(feature): extract _pipeline from run (E-32 prep, no behavior change)"
```

---

## Task 7: Wire the trace, retro stage, query, and worker registration

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Modify: `src/sdlc/worker.py:64-79` (register `export_run_artifacts`)
- Test: `tests/test_retro_stage.py`

**Interfaces:**
- Consumes: `build_run_summary` (Task 3), `RunExportInput`/`export_run_artifacts` (Task 5), `RunEvent`/`RunEventKind` (Task 1), `RunSummary` (Task 2), `reflect`/`ReflectInput` (existing `memory/activities.py`).
- Produces (on `FeatureWorkflow`): `self._trace: list[RunEvent]`, `self._seq: int`, `self._run_summary: RunSummary | None`; `_emit(...)`; `_retro(cfg, idea, result)`; `@workflow.query run_summary()`. `run()` now calls `_retro` after `_pipeline`.

- [ ] **Step 1: Write the failing workflow test**

```python
# tests/test_retro_stage.py
"""E-32 retro stage: fires on every terminal path, populates run_summary(),
and never lets an export failure change the run's outcome."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.models import GateDecision, GateOutcome
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

TASK_QUEUE = "retro"


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


async def _drive(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    for gate in ("architecture", "plan", "deploy"):
        await _wait_for_status(handle, f"awaiting:{gate}")
        await handle.signal(FeatureWorkflow.submit_gate_decision,
                            GateDecision(gate=gate, round=1,
                                         outcome=GateOutcome.APPROVE,
                                         decided_by="human"))


@pytest.mark.asyncio
async def test_retro_populates_run_summary_on_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    activities = [evaluate_gate, export_run_artifacts, *GIT_FAKES,
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow], activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config()],
                    id=f"retro-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result.startswith("deployed:"), result
    assert summary is not None
    assert summary.outcome == result
    assert summary.terminal_stage == "deploy"
    assert any(c.answered_by == "human" for c in summary.clarifications)
    assert any(g.gate == "architecture" for g in summary.gates)
    # export wrote the files
    run_dirs = list(tmp_path.iterdir())
    assert run_dirs and (run_dirs[0] / "report.html").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_retro_stage.py -v`
Expected: FAIL — `AttributeError: type object 'FeatureWorkflow' has no attribute 'run_summary'` (query not defined yet).

- [ ] **Step 3: Add imports and state fields**

In `src/sdlc/workflows/feature.py`, inside the
`with workflow.unsafe.imports_passed_through():` block, add the memory reflect
import to the existing `..memory.activities` import and add the observability
imports:

```python
    from ..memory.activities import (
        RecallInput, ReflectInput, RetainInput, WatermarkInput,
        capture_watermark, recall_snapshot, reflect, retain,
    )
    from ..observability.activities import RunExportInput, export_run_artifacts
    from ..observability.summary import build_run_summary
    from ..observability.trace import RunEvent, RunEventKind
```

Also add `RunSummary` to the existing `..models` import list.

In `__init__` (after `self._pending` at `feature.py:218`), add:

```python
        # E-32: append-only domain trace; source for RunSummary + events.jsonl.
        self._trace: list[RunEvent] = []
        self._seq: int = 0
        self._run_summary: RunSummary | None = None
```

- [ ] **Step 4: Add `_emit` and the `run_summary()` query**

Add near the other queries (after `pending_decisions` at `feature.py:375`):

```python
    @workflow.query
    def run_summary(self) -> RunSummary | None:
        """The retro-stage RunSummary; None until the run terminates (E-32)."""
        return self._run_summary
```

Add a helper near the memory helpers:

```python
    def _emit(self, kind: RunEventKind, stage: str | None = None,
              **data: str) -> None:
        """Append a domain event to the run trace. Pure state mutation — safe
        in workflow code (no I/O, deterministic seq + workflow.now())."""
        self._trace.append(RunEvent(seq=self._seq, at=workflow.now(),
                                    kind=kind, stage=stage, data=data))
        self._seq += 1
```

- [ ] **Step 5: Wire the four chokepoints**

**(a) `_record` — stage_ended (every stage boundary).** In `_record`
(`feature.py:250`), emit before the benchmarking early-return:

```python
    async def _record(self, cfg: PipelineConfig, record: BenchmarkRecord
                      ) -> None:
        self._emit(
            RunEventKind.STAGE_ENDED, stage=record.stage,
            role=record.role, outcome=record.outcome.value,
            duration_s=str(record.speed.wall_clock_s),
            fix_attempts=str(record.fix_attempts),
            **({"cost_usd": str(record.cost.usd)}
               if record.cost.usd is not None else {}))
        if not self._benchmarking(cfg):
            return
        await workflow.execute_activity(record_benchmark, record, **RECORD_ACT)
```

**(b) `_gate` — gate_awaited + gate_decided.** Thread an optional `confidence`
into `_gate`. Change the signature at `feature.py:379`:

```python
    async def _gate(self, name: str, cfg: PipelineConfig,
                    auto_decision: GateDecision | None = None,
                    round: int = 1,
                    context: GateContext | None = None,
                    confidence: float | None = None) -> GateDecision:
```

Emit `GATE_AWAITED` immediately before the `await workflow.wait_condition(...)`
in the human-wait branch, and `GATE_DECIDED` just before the existing
`_retain` at `feature.py:411` (which runs for all of OFF/SOFT/human/timeout
paths since they converge there). Insert before that retain:

```python
        self._emit(
            RunEventKind.GATE_DECIDED, stage=name,
            gate=name, round=str(round), policy=policy.value,
            decided_by=decision.decided_by,
            approved=("true" if decision.approved else "false"),
            **({"confidence": str(confidence)} if confidence is not None else {}))
```

And in the human-wait branch, right before `await workflow.wait_condition(`:

```python
            self._emit(RunEventKind.GATE_AWAITED, stage=name,
                       gate=name, round=str(round))
```

Pass `confidence` from `_revisable_stage` (`feature.py:432`): change that
`_gate(...)` call to also pass `confidence=getattr(artifact, "confidence", None)`.

**(c) merge-gate overrides.** In the merge stage, after `overrides` is built
(around `feature.py:1131`), emit the override list onto a dedicated
`GATE_DECIDED` enrichment so the summary sees waved checks. Immediately after
the `overrides = [...]` assignment, add:

```python
            self._emit(
                RunEventKind.GATE_DECIDED, stage="merge", gate="merge",
                round="1", policy="soft", decided_by=(gate.reviewer or "human"),
                approved="true",
                overrides=",".join(o.check for o in overrides))
```

**(d) clarify — asked/answered.** In the clarify stage (`feature.py:791`),
after computing `reqs`, emit one `CLARIFICATION_ASKED` per open question, then
after resolution emit `CLARIFICATION_ANSWERED` with `answered_by`. Replace the
`if reqs.open_questions:` block's internals so emits bracket the wait:

```python
        if reqs.open_questions:
            for q in reqs.open_questions:
                self._emit(RunEventKind.CLARIFICATION_ASKED, stage="clarify",
                           question_id=q.id, question=q.question)
            clarify_policy = cfg.gates.get("clarify", GateConfig()).policy
            if clarify_policy == GatePolicy.OFF:
                for q in reqs.open_questions:
                    q.answer = q.suggested_answer
            else:
                self._status = "awaiting:clarify"
                for p in clarify_pending(reqs.open_questions, set()):
                    self._pending[p.key] = p
                await workflow.wait_condition(
                    lambda: all(q.id in self._question_answers
                                for q in reqs.open_questions),
                    timeout=timedelta(hours=cfg.gate_timeout_hours),
                )
                for q in reqs.open_questions:
                    q.answer = self._question_answers.get(q.id)
                    self._pending.pop(q.id, None)
            for q in reqs.open_questions:
                answered = ("human" if q.id in self._question_answers
                            else "suggested" if q.answer is not None
                            else "unanswered")
                self._emit(RunEventKind.CLARIFICATION_ANSWERED, stage="clarify",
                           question_id=q.id, answered_by=answered)
```

**(e) `_dev_task` — fix_attempt.** In the attempt loop (`feature.py:515`), at
the top of each attempt after `_attempt_started = workflow.now()`, add:

```python
            self._emit(RunEventKind.FIX_ATTEMPT, stage="code",
                       task_id=task.id, attempt=str(attempt))
```

- [ ] **Step 6: Add `_retro` and call it from `run`**

Add the `_retro` method (near `_pipeline`). Note the `MEMORY_RETAINED` event
uses the data key `item` (not `kind` — that name is `_emit`'s own parameter),
and it is emitted *before* `build_run_summary` so the summary's `memory_retains`
count includes retro's own retain; `RUN_FINISHED` is emitted last so it is the
final trace event:

```python
    async def _retro(self, cfg: PipelineConfig, idea: IdeaBrief,
                     result: str) -> None:
        """Stage 14 (E-32). Best-effort: any failure is swallowed so the run's
        return string is never changed."""
        try:
            if cfg.memory.enabled:
                self._emit(RunEventKind.MEMORY_RETAINED, stage="retro",
                           item="run_summary")
            self._emit(RunEventKind.RUN_FINISHED, stage="retro", outcome=result)
            summary = build_run_summary(
                run_id=workflow.info().workflow_id,
                mode=idea.mode.value,
                outcome=result, trace=self._trace,
                memory_enabled=cfg.memory.enabled,
                memory_watermark=self._memory_watermark)
            self._run_summary = summary

            if cfg.memory.enabled:
                await self._retain(
                    cfg, MemoryKind.RUN_SUMMARY, cfg.memory.project_bank,
                    text=summary.model_dump_json(),
                    metadata={"run_id": workflow.info().workflow_id,
                              "stage": "retro"})
                try:
                    await workflow.execute_activity(
                        reflect,
                        ReflectInput(bank=cfg.memory.project_bank,
                                     backend=cfg.memory.backend,
                                     base_url=cfg.memory.base_url),
                        **MEM_ACT)
                except Exception:
                    pass

            try:
                await workflow.execute_activity(
                    export_run_artifacts,
                    RunExportInput(run_id=workflow.info().workflow_id,
                                   summary=summary, trace=self._trace),
                    **EXPORT_ACT)
            except Exception:
                pass
        except Exception:
            # Retro must never change the run outcome (best-effort stage).
            pass
```

Define `EXPORT_ACT` alongside the other activity-option constants near
`feature.py:66` (`ACT = dict(...)`). Export is best-effort — a single attempt,
no retry hammering:

```python
EXPORT_ACT = dict(start_to_close_timeout=timedelta(minutes=2),
                  retry_policy=RetryPolicy(maximum_attempts=1))
```

Note: the `MEMORY_RETAINED` emit is placed before `build_run_summary` so the
summary's `memory_retains` count includes the retro's own retain. Order the
two `_emit` calls so `RUN_FINISHED` is last in the trace.

Update `run` to call retro:

```python
    @workflow.run
    async def run(self, idea: IdeaBrief,
                  cfg: PipelineConfig | None = None) -> str:
        cfg = cfg or PipelineConfig()
        result = await self._pipeline(idea, cfg)
        await self._retro(cfg, idea, result)
        return result
```

- [ ] **Step 7: Register the export activity on the worker**

In `src/sdlc/worker.py`, add the import and the activity to the `activities=[...]`
list:

```python
from .observability.activities import export_run_artifacts
```

and add `export_run_artifacts,` to the `activities=[` list (e.g. after
`cache_get, cache_put,`).

- [ ] **Step 8: Run the retro test to verify it passes**

Run: `python -m pytest tests/test_retro_stage.py -v`
Expected: PASS (1 passed)

- [ ] **Step 9: Run the full workflow suite for regressions**

Run: `python -m pytest tests/test_e2e_greenfield.py tests/test_retro_stage.py tests/test_gate_revision_loop.py tests/test_factory_purity.py -v`
Expected: PASS (no regressions; retro fires on the existing deploy paths too).

- [ ] **Step 10: Commit**

```bash
git add src/sdlc/workflows/feature.py src/sdlc/worker.py tests/test_retro_stage.py
git commit -m "feat(feature): stage 14 retro — trace, RunSummary, reflect, export (E-32)"
```

---

## Task 8: Rejected-path coverage + export-failure isolation tests

**Files:**
- Modify: `tests/test_retro_stage.py` (add two tests)

**Interfaces:**
- Consumes: everything from Task 7.
- Produces: proof that retro fires on a `rejected:*` terminal path and that an export activity failure does not change the run's return string.

- [ ] **Step 1: Add the rejected-path test**

A run rejected at the clarify stage: drive it by signalling a REJECT-equivalent.
The simplest deterministic rejection with the canned fakes is the merge advisory
path is hard to force; instead reject at a stage gate by sending
`GateOutcome.REJECT` for `architecture`, which makes `_revisable_stage`'s final
gate return a non-approval → `_pipeline` returns `"rejected:architecture"`.
Append to `tests/test_retro_stage.py`:

```python
async def _drive_reject_arch(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    await _wait_for_status(handle, "awaiting:architecture")
    await handle.signal(FeatureWorkflow.submit_gate_decision,
                        GateDecision(gate="architecture", round=1,
                                     outcome=GateOutcome.REJECT,
                                     decided_by="human"))


@pytest.mark.asyncio
async def test_retro_fires_on_rejected_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    activities = [evaluate_gate, export_run_artifacts, *GIT_FAKES,
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow], activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config()],
                    id=f"retro-rej-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive_reject_arch(handle))
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result == "rejected:architecture", result
    assert summary is not None and summary.outcome == result
    assert summary.terminal_stage in ("clarify", "architecture")
```

- [ ] **Step 2: Run it to verify it passes**

Run: `python -m pytest tests/test_retro_stage.py::test_retro_fires_on_rejected_path -v`
Expected: PASS. (`e2e_config()` makes `architecture` a human gate — the existing
`test_e2e_greenfield.py::_drive` already waits on `awaiting:architecture` — so a
`REJECT` there deterministically drives `_pipeline` to `return "rejected:architecture"`,
after which `run()` still runs `_retro`.)

- [ ] **Step 3: Add the export-failure isolation test**

Register a **failing** export activity of the same name to prove retro swallows
it. Use a local activity that raises, registered under the real name via
`activity.defn(name=...)`:

```python
from temporalio import activity as _activity

from sdlc.observability.activities import RunExportInput  # add to imports


@_activity.defn(name="export_run_artifacts")
async def _boom_export(inp: RunExportInput) -> str:  # same name, always fails
    raise RuntimeError("disk full")


@pytest.mark.asyncio
async def test_export_failure_does_not_change_outcome(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    activities = [evaluate_gate, _boom_export, *GIT_FAKES,
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow], activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config()],
                    id=f"retro-boom-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result.startswith("deployed:"), result   # export failed, run didn't
    assert summary is not None                       # summary still built
```

Note: `_retro` calls export with `**EXPORT_ACT` (single attempt, Task 7), so the
failing activity raises into `_retro` on the first try and is swallowed — no
retry backoff, so the test stays fast.

- [ ] **Step 4: Run both new tests**

Run: `python -m pytest tests/test_retro_stage.py -v`
Expected: PASS (all retro tests).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS (no regressions across the suite).

- [ ] **Step 6: Commit**

```bash
git add tests/test_retro_stage.py
git commit -m "test(retro): rejected-path coverage + export-failure isolation (E-32)"
```

---

## Task 9: Roadmap + docs update

**Files:**
- Modify: `ROADMAP.md` (mark E-32 done; note E-22/E-23 folded in; update stage-14 line and SC-4/SC-6 notes)

**Interfaces:**
- Consumes: nothing.
- Produces: the tracker reflects reality (per ROADMAP's own discipline: §9 records what we've built once code says so).

- [ ] **Step 1: Update the stage-14 line (§1)**

In `ROADMAP.md`, change the stage 14 item from
`- [ ] **14 · retro** — reflect() ... never called ...` to a `[x]` entry noting
`RunSummary` + `reflect(project_bank)` per-run + `events.jsonl`/`report.html`
export now fire on every terminal path (E-32), with the org-bank writer half
still E-25.

- [ ] **Step 2: Mark E-32 / E-22 / E-23 in §9.6 and §9.8**

Change `- [ ] **E-32**` to `- [x] **E-32**` with a one-line landing note
referencing `docs/superpowers/plans/2026-07-22-retro-stage-run-summary.md` and
`docs/superpowers/specs/2026-07-22-retro-stage-run-summary-design.md`. Mark
`E-22` and `E-23` `[x]` noting they landed folded into E-32 (events.jsonl +
report.html rendered from `RunSummary`/trace).

- [ ] **Step 3: Update SC-4 / SC-6 notes (§4) and FR-404 (§2)**

Note that the per-run signal now accrues (retro stage emits `RunSummary` with
`clarifications[].answered_by` and `gates[].overrides`/`confidence`); the
cross-run *aggregation* into the SC-4/SC-6 rate remains the benchmark's job
(§9.8). Update FR-404 to reflect that the retro-stage `reflect()` call now
exists (project scope); org half still E-25.

- [ ] **Step 4: Verify no test references broke and commit**

Run: `python -m pytest -q`
Expected: PASS.

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): mark E-32 done; E-22/E-23 folded in; SC-4/SC-6 signal accrues (E-32)"
```

---

## Self-Review Notes (traceability to the spec)

- Spec §2 (control flow, every terminal path, no try/finally) → Task 6 (extract) + Task 7 Step 6 (`run` calls `_retro` after `_pipeline` returns) + Task 8 (rejected path).
- Spec §3.1 (`RunEvent`) → Task 1. §3.2 (`RunSummary` + sub-models) → Task 2. §3.3 (`MemoryKind.RUN_SUMMARY`) → Task 2.
- Spec §4 (4 chokepoints) → Task 7 Step 5 (a–e). Confidence threading → Step 5(b).
- Spec §5 (retain + reflect, gated, non-blocking) → Task 7 Step 6 `_retro`.
- Spec §6 (export activity, `SDLC_EXPORT_ROOT`, events.jsonl + report.html) → Tasks 4 + 5; worker registration Task 7 Step 7.
- Spec §7 (`run_summary()` query) → Task 7 Step 4.
- Spec §8 (testing: aggregation across 3 run shapes, render round-trip, workflow e2e on deploy + rejected, export-failure isolation, memory on/off) → Tasks 3, 4, 5, 7, 8.
- Spec §9 (file touch list) → File Structure section + per-task Files blocks.
- Spec §10 (out of scope) → not implemented by design; org-bank half stays E-25 (Task 9 notes).
