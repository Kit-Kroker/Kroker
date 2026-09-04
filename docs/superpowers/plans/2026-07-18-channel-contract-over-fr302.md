# E-6 Channel Contract over FR-302 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a shared channel contract — a structured `pending_decisions()` workflow query plus a pure `render`/`translate` adapter — so every future surface (CLI refit, notify, dashboard, MCP) renders pending human decisions and maps replies to the two FR-302 signals through one seam, with no new surface built here.

**Architecture:** Two layers across the workflow-sandbox boundary. **Layer A** (`src/sdlc/pending.py`, pydantic-only, imported inside the Temporal workflow) is the source of truth for what a human owes a decision on: a discriminated `PendingDecision` union (4 variants) plus pure builders. The workflow populates a `self._pending` registry at each wait point and exposes it via a new `pending_decisions()` query. **Layer B** (`src/sdlc/channels/contract.py`, NOT imported by the workflow) is the adapter: pure `render(PendingDecision)->RenderedDecision` and `translate(PendingDecision, Reply)->SignalCall`, with `deliver` an opt-in `PushChannel` extension.

**Tech Stack:** Python 3.11+, Pydantic v2, Temporal (`temporalio`), pytest.

> **DEVIATION FROM SPEC (location).** The spec places Layer B at
> `interfaces/channels/contract.py`. `pyproject.toml` packages only `src/`
> (`where = ["src"]`) and `interfaces/` contains no Python, so that path is not
> importable without build/pytest config changes. This plan places Layer B at
> **`src/sdlc/channels/`** instead — importable as `sdlc.channels` with zero
> config, following the repo's existing subpackage pattern (`memoization/`,
> `memory/`, `harness/`, `research/`). The sandbox boundary the spec cares about
> is preserved: the workflow imports `sdlc.pending` (Layer A) but never
> `sdlc.channels` (Layer B), so ADR-13 purity is unaffected.

## Global Constraints

- Python `from __future__ import annotations` at the top of every new module (repo convention).
- Layer A (`sdlc/pending.py`) MUST import only pydantic + `sdlc.models` + `sdlc.gate` — no agents, no I/O, no `temporalio` — so it stays importable inside `workflow.unsafe.imports_passed_through()`.
- The workflow's two signals are unchanged: `submit_gate_decision(GateDecision)` and `answer_question(question_id, answer)`. `translate` emits only these two.
- `status()` and `pending_gate()` queries stay exactly as they are (backward compatible).
- Reuse `CheckResult` from `sdlc.gate` — do NOT define a new check-row type.
- Reuse `gate_key` from `sdlc.models` for gate-decision keys.
- Run tests with `python -m pytest` from the repo root (`D:\own\Kroker`).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/sdlc/pending.py` (new) | Layer A: `PendingDecision` union (4 variants), `GateContext`, pure builders `clarify_pending`/`gate_pending` |
| `src/sdlc/workflows/feature.py` (modify) | `self._pending` registry, `pending_decisions()` query, populate at clarify wait + thread `GateContext` through `_gate` and its 4 call sites |
| `src/sdlc/channels/__init__.py` (new) | Layer B package marker + public exports |
| `src/sdlc/channels/contract.py` (new) | Layer B: `RenderedDecision`/`Reply`/`SignalCall`, `default_render`/`default_translate`, `Channel`/`PushChannel` Protocols, `ReferenceChannel` |
| `tests/test_pending_types.py` (new) | Union construction + discriminated-union serialization round-trip |
| `tests/test_pending_builders.py` (new) | `clarify_pending`/`gate_pending` behavior |
| `tests/test_pending_wiring.py` (new) | `pending_decisions()` query + feature.py wiring assertions |
| `tests/test_channel_contract.py` (new) | `render`/`translate` across all 4 variants + Protocol satisfaction |

---

## Task 1: Layer A types — `PendingDecision` union + `GateContext`

**Files:**
- Create: `src/sdlc/pending.py`
- Test: `tests/test_pending_types.py`

**Interfaces:**
- Consumes: `CheckResult` from `sdlc.gate`; `gate_key` from `sdlc.models` (used in Task 2, imported here).
- Produces: `ClarifyPending`, `StageGatePending`, `TaskEscalationPending`, `MergeGatePending` (each a `BaseModel` with a `kind` `Literal` discriminator and a `key: str`); `PendingDecision` (an `Annotated[Union[...], Field(discriminator="kind")]` alias); `GateContext` (BaseModel with optional render fields).

- [ ] **Step 1: Write the failing test**

Create `tests/test_pending_types.py`:

```python
from __future__ import annotations

from pydantic import TypeAdapter

from sdlc.gate import CheckClass, CheckResult
from sdlc.pending import (
    ClarifyPending,
    GateContext,
    MergeGatePending,
    PendingDecision,
    StageGatePending,
    TaskEscalationPending,
)

_ADAPTER = TypeAdapter(list[PendingDecision])


def test_variants_construct_with_defaults():
    c = ClarifyPending(key="Q1", question="OIDC or SAML?", why_it_matters="auth")
    assert c.kind == "clarify" and c.suggested_answer is None
    m = MergeGatePending(key="merge#1", gate="merge", round=1)
    assert m.kind == "merge_gate" and m.checks == [] and m.verdict is None


def test_discriminated_union_round_trip_preserves_subclass_fields():
    items: list[PendingDecision] = [
        ClarifyPending(key="Q1", question="q", why_it_matters="w", suggested_answer="s"),
        StageGatePending(
            key="architecture#1", gate="architecture", round=1, spec_summary="the spec"
        ),
        TaskEscalationPending(
            key="task:t1#1", gate="task:t1", round=1, task_id="t1", analysis="unmet", attempts=3
        ),
        MergeGatePending(
            key="merge#1",
            gate="merge",
            round=1,
            checks=[
                CheckResult(name="lint_clean", passed=False, classification=CheckClass.ABSOLUTE)
            ],
            verdict="advisory",
        ),
    ]
    wire = _ADAPTER.dump_json(items)
    back = _ADAPTER.validate_json(wire)
    assert back == items
    # subclass-specific field survived the wire, not just the base fields
    assert isinstance(back[3], MergeGatePending)
    assert back[3].checks[0].name == "lint_clean"


def test_gate_context_defaults_are_empty():
    ctx = GateContext()
    assert ctx.checks == [] and ctx.spec_summary is None and ctx.attempts is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pending_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.pending'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/pending.py`:

```python
"""Structured pending-decision types (E-6).

Workflow-side source of truth for what a human owes a decision on. Pure
pydantic so it imports inside the Temporal workflow sandbox
(``workflow.unsafe.imports_passed_through``): no agents, no I/O, no
``temporalio``. The interface/adapter layer (``sdlc.channels``) renders these;
it never reaches into workflow internals.

All four variants collapse to just two FR-302 signals on reply:
``clarify`` -> ``answer_question``; every gate variant -> ``submit_gate_decision``.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .gate import CheckResult
from .models import OpenQuestion, gate_key


class ClarifyPending(BaseModel):
    """An open clarify question awaiting a human answer -> answer_question."""

    kind: Literal["clarify"] = "clarify"
    key: str  # the question id
    question: str
    why_it_matters: str
    suggested_answer: str | None = None


class StageGatePending(BaseModel):
    """An architecture/planning gate awaiting a decision -> submit_gate_decision."""

    kind: Literal["stage_gate"] = "stage_gate"
    key: str  # gate_key(gate, round)
    gate: str
    round: int
    spec_summary: str


class TaskEscalationPending(BaseModel):
    """A task the fix loop could not close, escalated to a human."""

    kind: Literal["task_escalation"] = "task_escalation"
    key: str
    gate: str
    round: int
    task_id: str
    analysis: str
    attempts: int


class MergeGatePending(BaseModel):
    """The merge gate awaiting a decision, carrying the quality-check table."""

    kind: Literal["merge_gate"] = "merge_gate"
    key: str
    gate: str
    round: int
    checks: list[CheckResult] = Field(default_factory=list)
    verdict: str | None = None


PendingDecision = Annotated[
    Union[ClarifyPending, StageGatePending, TaskEscalationPending, MergeGatePending],
    Field(discriminator="kind"),
]


class GateContext(BaseModel):
    """Optional render context a caller hands to ``_gate``; the gate name
    selects which variant is built from it."""

    spec_summary: str | None = None  # stage gates
    checks: list[CheckResult] = Field(default_factory=list)  # merge gate
    verdict: str | None = None  # merge gate
    analysis: str | None = None  # task escalation
    attempts: int | None = None  # task escalation
    task_id: str | None = None  # task escalation
```

Note: `OpenQuestion` and `gate_key` are imported now because Task 2's builders live in this same file and use them; importing them here keeps the module's dependency surface visible from the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pending_types.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/pending.py tests/test_pending_types.py
git commit -m "feat(channels): PendingDecision union + GateContext (E-6 Layer A types)"
```

---

## Task 2: Pure builders — `clarify_pending` and `gate_pending`

**Files:**
- Modify: `src/sdlc/pending.py` (append builders)
- Test: `tests/test_pending_builders.py`

**Interfaces:**
- Consumes: `OpenQuestion` (fields `id`, `question`, `why_it_matters`, `suggested_answer`), `gate_key`, and the Task 1 variant types.
- Produces:
  - `clarify_pending(open_questions: list[OpenQuestion], answered_ids: set[str]) -> list[ClarifyPending]` — one per still-unanswered question.
  - `gate_pending(name: str, round: int, context: GateContext | None) -> PendingDecision` — picks the variant: `name == "merge"` -> `MergeGatePending`; `name.startswith("task:")` -> `TaskEscalationPending`; else -> `StageGatePending`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pending_builders.py`:

```python
from __future__ import annotations

from sdlc.gate import CheckClass, CheckResult
from sdlc.models import OpenQuestion
from sdlc.pending import (
    GateContext,
    MergeGatePending,
    StageGatePending,
    TaskEscalationPending,
    clarify_pending,
    gate_pending,
)


def _q(qid, ans=None):
    return OpenQuestion(id=qid, question=f"{qid}?", why_it_matters="w", suggested_answer="sugg")


def test_clarify_pending_skips_answered():
    qs = [_q("Q1"), _q("Q2"), _q("Q3")]
    out = clarify_pending(qs, {"Q2"})
    assert [p.key for p in out] == ["Q1", "Q3"]
    assert out[0].question == "Q1?" and out[0].suggested_answer == "sugg"


def test_gate_pending_merge_variant_carries_checks():
    ctx = GateContext(
        checks=[CheckResult(name="coverage", passed=False, classification=CheckClass.ADVISORY)],
        verdict="v",
    )
    p = gate_pending("merge", 1, ctx)
    assert isinstance(p, MergeGatePending)
    assert p.key == "merge#1" and p.checks[0].name == "coverage" and p.verdict == "v"


def test_gate_pending_task_variant_from_prefix():
    p = gate_pending("task:t7", 1, GateContext(analysis="unmet", attempts=3))
    assert isinstance(p, TaskEscalationPending)
    assert p.task_id == "t7" and p.analysis == "unmet" and p.attempts == 3
    assert p.key == "task:t7#1"


def test_gate_pending_defaults_to_stage_variant():
    p = gate_pending("architecture", 2, GateContext(spec_summary="s"))
    assert isinstance(p, StageGatePending)
    assert p.gate == "architecture" and p.round == 2 and p.spec_summary == "s"


def test_gate_pending_tolerates_missing_context():
    p = gate_pending("planning", 1, None)
    assert isinstance(p, StageGatePending) and p.spec_summary == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pending_builders.py -v`
Expected: FAIL — `ImportError: cannot import name 'clarify_pending'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/pending.py`:

```python
def clarify_pending(
    open_questions: list[OpenQuestion],
    answered_ids: set[str],
) -> list[ClarifyPending]:
    """One ClarifyPending per still-unanswered open question."""
    return [
        ClarifyPending(
            key=q.id,
            question=q.question,
            why_it_matters=q.why_it_matters,
            suggested_answer=q.suggested_answer,
        )
        for q in open_questions
        if q.id not in answered_ids
    ]


def gate_pending(
    name: str,
    round: int,
    context: GateContext | None,
) -> PendingDecision:
    """Build the render variant a gate wait should surface. The gate name is
    the discriminator: 'merge' -> MergeGatePending, 'task:<id>' ->
    TaskEscalationPending, anything else -> StageGatePending."""
    key = gate_key(name, round)
    ctx = context or GateContext()
    if name == "merge":
        return MergeGatePending(
            key=key, gate=name, round=round, checks=ctx.checks, verdict=ctx.verdict
        )
    if name.startswith("task:"):
        return TaskEscalationPending(
            key=key,
            gate=name,
            round=round,
            task_id=ctx.task_id or name.removeprefix("task:"),
            analysis=ctx.analysis or "",
            attempts=ctx.attempts or 0,
        )
    return StageGatePending(key=key, gate=name, round=round, spec_summary=ctx.spec_summary or "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pending_builders.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/pending.py tests/test_pending_builders.py
git commit -m "feat(channels): pure clarify_pending/gate_pending builders (E-6)"
```

---

## Task 3: Workflow wiring — registry, query, clarify + gate population

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Test: `tests/test_pending_wiring.py`

**Interfaces:**
- Consumes: `GateContext`, `PendingDecision`, `clarify_pending`, `gate_pending` from `sdlc.pending`.
- Produces:
  - `FeatureWorkflow._pending: dict[str, PendingDecision]` (instance attr).
  - `FeatureWorkflow.pending_decisions() -> list[PendingDecision]` (`@workflow.query`).
  - `FeatureWorkflow._gate(...)` gains a keyword param `context: GateContext | None = None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pending_wiring.py`:

```python
from __future__ import annotations

import pathlib

from sdlc.pending import StageGatePending
from sdlc.workflows.feature import FeatureWorkflow

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_new_workflow_has_empty_pending_registry():
    wf = FeatureWorkflow()
    assert wf.pending_decisions() == []


def test_pending_decisions_query_returns_registry_values():
    wf = FeatureWorkflow()
    p = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="x")
    wf._pending[p.key] = p
    assert wf.pending_decisions() == [p]


def test_gate_accepts_context_param():
    import inspect

    sig = inspect.signature(FeatureWorkflow._gate)
    assert "context" in sig.parameters


def test_feature_source_wires_pending_population():
    src = SRC.read_text(encoding="utf-8")
    # the query exists and is registered
    assert "def pending_decisions(" in src
    # clarify wait and gate wait both populate the registry
    assert "clarify_pending(" in src
    assert "gate_pending(" in src
    assert "self._pending" in src
    # gate population is cleared on resolution
    assert "self._pending.pop(" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pending_wiring.py -v`
Expected: FAIL — `AttributeError: 'FeatureWorkflow' object has no attribute 'pending_decisions'` (and the source-assertion tests fail).

- [ ] **Step 3a: Add the import**

In `src/sdlc/workflows/feature.py`, inside the `with workflow.unsafe.imports_passed_through():` block, after the `from ..models import (...)` group (ends `feature.py:56`), add:

```python
from ..pending import (
    GateContext,
    PendingDecision,
    clarify_pending,
    gate_pending,
)
```

- [ ] **Step 3b: Add the registry attr + query**

In `FeatureWorkflow.__init__` (`feature.py:194-203`), after `self._question_answers` line, add:

```python
        # E-6: structured pending-decision registry, keyed by resolution key
        # (question id, or gate_key(gate, round)). Rendered by sdlc.channels.
        self._pending: dict[str, PendingDecision] = {}
```

After the `pending_gate` query (`feature.py:348-350`), add:

```python
    @workflow.query
    def pending_decisions(self) -> list[PendingDecision]:
        """Structured items a human currently owes a decision on (E-6).
        Empty when nothing is awaiting. Rendered by sdlc.channels."""
        return list(self._pending.values())
```

- [ ] **Step 3c: Thread context through `_gate`**

Change the `_gate` signature (`feature.py:354-356`) to add `context`:

```python
    async def _gate(self, name: str, cfg: PipelineConfig,
                    auto_decision: GateDecision | None = None,
                    round: int = 1,
                    context: GateContext | None = None) -> GateDecision:
```

In the waiting `else` branch (`feature.py:368-381`), populate before waiting and clear in `finally`:

```python
        else:
            self._pending[key] = gate_pending(name, round, context)
            self._status = f"awaiting:{name}"
            try:
                await workflow.wait_condition(
                    lambda: key in self._gate_decisions,
                    timeout=timedelta(hours=cfg.gate_timeout_hours),
                )
                decision = self._gate_decisions[key]
            except TimeoutError:
                decision = GateDecision(gate=name, round=round,
                                        outcome=GateOutcome.REJECT,
                                        decided_by="timeout")
            finally:
                self._status = "running"
                self._pending.pop(key, None)
```

- [ ] **Step 3d: Populate the clarify wait**

Replace the clarify wait block (`feature.py:726-734`, the `else:` under `if clarify_policy == GatePolicy.OFF`) with:

```python
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
```

- [ ] **Step 3e: Pass context at the stage-gate call sites**

In `_revisable_stage` (`feature.py:399-412`), add a summary helper and pass context. Replace the loop body's `_gate` call and the final `_gate` call:

```python
guidance: str | None = None
for round in range(1, cfg.max_gate_rounds + 1):
    artifact = await run_fn(guidance)
    auto = _auto_decision_for(name, cfg, getattr(artifact, "confidence", None))
    decision = await self._gate(
        name,
        cfg,
        auto_decision=auto,
        round=round,
        context=GateContext(spec_summary=_spec_summary(artifact)),
    )
    if decision.outcome is not GateOutcome.REVISE:
        return artifact, decision
    guidance = decision.guidance or decision.comments
# Exhausted: one final HARD gate decides accept-anyway vs abandon.
artifact = await run_fn(guidance)
decision = await self._gate(
    name,
    cfg,
    round=cfg.max_gate_rounds + 1,
    context=GateContext(spec_summary=_spec_summary(artifact)),
)
return artifact, decision
```

Add this module-level helper next to `_auto_decision_for` (near `feature.py:180`, module scope, not a method):

```python
def _spec_summary(artifact: object) -> str:
    """Best-effort one-field summary of a proposer artifact for gate render.
    ClarifiedRequirements has `summary`; ArchitectureSpec has `overview`;
    fall back to the type name so the field is never empty."""
    return (
        getattr(artifact, "summary", None)
        or getattr(artifact, "overview", None)
        or type(artifact).__name__
    )
```

- [ ] **Step 3f: Pass context at the task-escalation call site**

Replace the escalation gate call (`feature.py:600-601`):

```python
# Escalate: human decides whether to accept, retry, or quarantine.
analysis = "\n- ".join(qa.issues or qa.failing_tests) if qa else ""
decision = await self._gate(
    f"task:{task.id}",
    cfg,
    context=GateContext(task_id=task.id, analysis=analysis, attempts=cfg.max_fix_attempts + 1),
)
```

- [ ] **Step 3g: Pass context at the two merge-gate call sites**

Replace the advisory merge gate call (`feature.py:1047`):

```python
gate = await self._gate("merge", cfg, context=GateContext(checks=gate_report.checks))
```

Replace the soft-verdict merge gate call (`feature.py:1074`):

```python
gate = await self._gate("merge", cfg, context=GateContext(checks=gate_report.checks))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pending_wiring.py -v`
Expected: PASS (4 tests).

Then run the workflow's existing tests to confirm no regression in the gate/clarify paths:

Run: `python -m pytest tests/test_gate_revision_loop.py tests/test_factory_purity.py tests/test_e2e_greenfield.py -v`
Expected: PASS (existing behavior unchanged; `_gate`'s new param is keyword-optional).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_pending_wiring.py
git commit -m "feat(channels): pending_decisions() query + populate clarify/gate waits (E-6)"
```

---

## Task 4: Layer B — the channel contract (`render`/`translate`)

**Files:**
- Create: `src/sdlc/channels/__init__.py`
- Create: `src/sdlc/channels/contract.py`
- Test: `tests/test_channel_contract.py`

**Interfaces:**
- Consumes: `PendingDecision` and the four variant classes from `sdlc.pending`; `GateDecision`, `GateOutcome` from `sdlc.models`.
- Produces:
  - `RenderedDecision` (BaseModel: `key`, `title`, `body`, `reply_kind: Literal["text","gate"]`, `suggested: str|None`, `rows: list[tuple[str,str]]`).
  - `Reply` (BaseModel: `outcome: GateOutcome|None`, `text: str|None`).
  - `SignalCall` (BaseModel: `signal: Literal["answer_question","submit_gate_decision"]`, `question_id`, `answer`, `decision: GateDecision|None`).
  - `default_render(d) -> RenderedDecision`, `default_translate(d, reply) -> SignalCall`.
  - `Channel` / `PushChannel` runtime-checkable Protocols; `ReferenceChannel` concrete implementation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_channel_contract.py`:

```python
from __future__ import annotations

from sdlc.channels.contract import (
    Channel,
    ReferenceChannel,
    Reply,
    default_render,
    default_translate,
)
from sdlc.gate import CheckClass, CheckResult
from sdlc.models import GateOutcome
from sdlc.pending import (
    ClarifyPending,
    MergeGatePending,
    StageGatePending,
    TaskEscalationPending,
)


def test_render_clarify_is_text_reply_with_suggestion():
    r = default_render(
        ClarifyPending(key="Q1", question="OIDC?", why_it_matters="auth", suggested_answer="yes")
    )
    assert r.reply_kind == "text" and r.key == "Q1"
    assert "OIDC?" in r.title and r.body == "auth" and r.suggested == "yes"


def test_render_merge_gate_tabulates_checks():
    r = default_render(
        MergeGatePending(
            key="merge#1",
            gate="merge",
            round=1,
            checks=[
                CheckResult(
                    name="lint_clean",
                    passed=False,
                    classification=CheckClass.ABSOLUTE,
                    detail="3 errs",
                )
            ],
        )
    )
    assert r.reply_kind == "gate"
    assert r.rows and r.rows[0][0] == "lint_clean" and "FAIL" in r.rows[0][1]


def test_translate_clarify_maps_to_answer_question():
    d = ClarifyPending(key="Q1", question="q", why_it_matters="w")
    call = default_translate(d, Reply(text="Use OIDC"))
    assert call.signal == "answer_question"
    assert call.question_id == "Q1" and call.answer == "Use OIDC"
    assert call.decision is None


def test_translate_stage_gate_approve_maps_to_gate_decision():
    d = StageGatePending(key="architecture#2", gate="architecture", round=2, spec_summary="s")
    call = default_translate(d, Reply(outcome=GateOutcome.APPROVE, text="lgtm"))
    assert call.signal == "submit_gate_decision"
    dec = call.decision
    assert dec.gate == "architecture" and dec.round == 2
    assert dec.outcome is GateOutcome.APPROVE and dec.decided_by == "human"
    assert dec.comments == "lgtm" and dec.guidance is None


def test_translate_revise_carries_guidance():
    d = TaskEscalationPending(
        key="task:t1#1", gate="task:t1", round=1, task_id="t1", analysis="a", attempts=2
    )
    call = default_translate(d, Reply(outcome=GateOutcome.REVISE, text="try X"))
    assert call.decision.outcome is GateOutcome.REVISE
    assert call.decision.guidance == "try X"


def test_reference_channel_satisfies_protocol_and_round_trips():
    ch = ReferenceChannel()
    assert isinstance(ch, Channel)
    d = StageGatePending(key="planning#1", gate="planning", round=1, spec_summary="p")
    assert ch.render(d).reply_kind == "gate"
    assert ch.translate(d, Reply(outcome=GateOutcome.REJECT)).signal == "submit_gate_decision"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_channel_contract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.channels'`.

- [ ] **Step 3a: Create the package**

Create `src/sdlc/channels/__init__.py`:

```python
"""Channel contract (E-6) — the adapter layer between the workflow's
structured pending decisions and any surface (CLI, notify, dashboard, MCP).

Not imported by the workflow: keeping delivery/render code out of the
sandbox preserves ADR-13 purity. Surfaces import from here; the workflow
imports only sdlc.pending.
"""

from __future__ import annotations

from .contract import (
    Channel,
    PushChannel,
    ReferenceChannel,
    RenderedDecision,
    Reply,
    SignalCall,
    default_render,
    default_translate,
)

__all__ = [
    "Channel",
    "PushChannel",
    "ReferenceChannel",
    "RenderedDecision",
    "Reply",
    "SignalCall",
    "default_render",
    "default_translate",
]
```

- [ ] **Step 3b: Write the contract**

Create `src/sdlc/channels/contract.py`:

```python
"""Pure render/translate for the channel contract (E-6).

render(PendingDecision) -> RenderedDecision   : surface-neutral presentation.
translate(PendingDecision, Reply) -> SignalCall: map a reply to ONE of the two
                                                 FR-302 signals.

No I/O. Delivery is a separate opt-in PushChannel capability. The module-level
default_render/default_translate are the reference behavior every surface
reuses; a surface MAY override render for richer presentation.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ..models import GateDecision, GateOutcome
from ..pending import (
    ClarifyPending,
    MergeGatePending,
    PendingDecision,
    StageGatePending,
    TaskEscalationPending,
)


class RenderedDecision(BaseModel):
    """What a surface displays. reply_kind tells the surface which affordance
    to offer: 'text' = free-text answer; 'gate' = approve/revise/reject."""

    key: str
    title: str
    body: str
    reply_kind: Literal["text", "gate"]
    suggested: str | None = None
    rows: list[tuple[str, str]] = Field(default_factory=list)


class Reply(BaseModel):
    """What a surface collects from the operator, surface-neutral."""

    outcome: GateOutcome | None = None  # gate replies
    text: str | None = None  # answer text, or comment/guidance


class SignalCall(BaseModel):
    """translate's output. Transport code invokes the named signal with these
    args on the workflow handle. Only ever one of the two FR-302 signals."""

    signal: Literal["answer_question", "submit_gate_decision"]
    question_id: str | None = None  # answer_question
    answer: str | None = None  # answer_question
    decision: GateDecision | None = None  # submit_gate_decision


def default_render(d: PendingDecision) -> RenderedDecision:
    if isinstance(d, ClarifyPending):
        return RenderedDecision(
            key=d.key,
            title=f"Clarify: {d.question}",
            body=d.why_it_matters,
            reply_kind="text",
            suggested=d.suggested_answer,
        )
    if isinstance(d, StageGatePending):
        return RenderedDecision(
            key=d.key,
            title=f"Gate: {d.gate} (round {d.round})",
            body=d.spec_summary,
            reply_kind="gate",
        )
    if isinstance(d, TaskEscalationPending):
        return RenderedDecision(
            key=d.key,
            title=f"Task escalation: {d.task_id} (attempt {d.attempts})",
            body=d.analysis,
            reply_kind="gate",
        )
    if isinstance(d, MergeGatePending):
        return RenderedDecision(
            key=d.key,
            title=f"Merge gate (round {d.round})",
            body=d.verdict or "Deterministic quality gate result",
            reply_kind="gate",
            rows=[
                (
                    c.name,
                    f"{'ok' if c.passed else 'FAIL'} "
                    f"[{c.classification.value}] {c.detail}".rstrip(),
                )
                for c in d.checks
            ],
        )
    raise TypeError(f"unhandled pending decision: {type(d)!r}")


def default_translate(d: PendingDecision, reply: Reply) -> SignalCall:
    if isinstance(d, ClarifyPending):
        return SignalCall(signal="answer_question", question_id=d.key, answer=reply.text)
    # every gate variant -> submit_gate_decision; gate/round come from the
    # pending item, so a reply can never land on the wrong round.
    guidance = reply.text if reply.outcome is GateOutcome.REVISE else None
    return SignalCall(
        signal="submit_gate_decision",
        decision=GateDecision(
            gate=d.gate,
            round=d.round,
            outcome=reply.outcome,
            decided_by="human",
            comments=reply.text,
            guidance=guidance,
        ),
    )


@runtime_checkable
class Channel(Protocol):
    """Every surface adapter: present a pending decision, map a reply to a
    signal. Both pure; delivery is a separate concern (see PushChannel)."""

    def render(self, d: PendingDecision) -> RenderedDecision: ...
    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall: ...


@runtime_checkable
class PushChannel(Channel, Protocol):
    """A surface that actively delivers (Slack notify, dashboard push).
    Pull surfaces (CLI, MCP) implement only Channel."""

    async def deliver(self, r: RenderedDecision) -> None: ...


class ReferenceChannel:
    """Minimal Channel — the test double and the pattern E-7's CLI refit
    follows. Delegates to the module defaults."""

    def render(self, d: PendingDecision) -> RenderedDecision:
        return default_render(d)

    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall:
        return default_translate(d, reply)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_channel_contract.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/channels/ tests/test_channel_contract.py
git commit -m "feat(channels): pure render/translate Channel contract + ReferenceChannel (E-6 Layer B)"
```

---

## Task 5: Full-suite verification + roadmap update

**Files:**
- Modify: `ROADMAP.md` (mark E-6 done)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: PASS — all new tests plus the existing suite green. If any pre-existing workflow test fails, confirm it is unrelated to `_gate`/clarify (the only touched paths); a failure in `test_e2e_greenfield`, `test_gate_revision_loop`, or `test_factory_purity` IS related and must be fixed before proceeding.

- [ ] **Step 2: Update the roadmap**

In `ROADMAP.md` §9.2, change the E-6 line from `[ ]` to `[x]` and append a note. Replace:

```markdown
- [ ] **E-6** Define the channel contract over the FR-302 signal substrate: render pending decision → deliver → translate reply to signal. Contract only; no new surfaces.
```

with:

```markdown
- [x] **E-6** Channel contract over the FR-302 signal substrate: a structured `pending_decisions()` workflow query (Layer A, `sdlc/pending.py`) feeding a pure `render`/`translate` adapter (Layer B, `sdlc/channels/contract.py`), with `deliver` an opt-in `PushChannel`. All four render variants (clarify / stage gate / task escalation / merge gate) collapse to the two FR-302 signals on reply. Contract only — no new surface; E-7 refits the CLI as the proof. *Layer B landed under `sdlc/channels/` not `interfaces/channels/`: `pyproject` packages only `src/`. Spec: `docs/superpowers/specs/2026-07-18-channel-contract-over-fr302-design.md`.*
```

Also update §9.7 ordering item 3 to reflect E-6 done (strike E-6, leave E-7/E-8):

Replace:

```markdown
3. **E-6 → E-7 → E-8** — contract, then CLI refit as proof, then the first new capability.
```

with:

```markdown
3. ~~**E-6**~~ landed (`feat/channel-contract`) → **E-7 → E-8** — CLI refit as proof, then the first new capability.
```

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): E-6 channel contract landed"
```

---

## Self-Review

**Spec coverage:**
- Spec §3 two layers → Tasks 1–2 (Layer A), Task 4 (Layer B). ✅
- Spec §4 `PendingDecision` union + `GateContext`, `CheckResult` reuse, discriminated-union serialization note → Task 1 (union alias with `Field(discriminator="kind")`, round-trip test asserts subclass fields survive). ✅
- Spec §5 `RenderedDecision`/`Reply`/`SignalCall`, `Channel`/`PushChannel`, shared defaults, round-copy → Task 4. ✅
- Spec §6 wiring: `self._pending`, clarify population, `_gate` context + 4 call sites, `pending_decisions()` query, `status`/`pending_gate` unchanged → Task 3 (steps 3b–3g). ✅
- Spec §7 error handling: query returns `[]` (Task 3 test), FR-302 first-wins unchanged, round carried+copied (Task 4 test) → ✅
- Spec §8 testing: pure unit render/translate (Task 4), reference channel (Task 4), workflow query test (Task 3) → ✅
- Spec §9 files → File Structure table (with documented location deviation) → ✅

**Placeholder scan:** No TBD/TODO; every code step shows complete code; no "add error handling" hand-waves. ✅

**Type consistency:** `clarify_pending(open_questions, answered_ids)` / `gate_pending(name, round, context)` signatures identical across Tasks 2, 3. `GateContext` fields (`spec_summary`/`checks`/`verdict`/`analysis`/`attempts`/`task_id`) consistent between Tasks 1, 3. `SignalCall.signal` literals match the workflow's actual signal names (`answer_question`, `submit_gate_decision`). `default_render`/`default_translate` names consistent Tasks 4 exports ↔ `ReferenceChannel` delegation ↔ `__init__` re-export. ✅

**Note on `qa` scope (Task 3f):** `qa` is bound by the fix-loop `for` iteration (`feature.py:509`); on the escalation path the loop has run at least once, so `qa` is in scope with the last attempt's report. `qa.issues`/`qa.failing_tests` are `QAReport` fields (`models.py:193-198`).
