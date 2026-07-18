# E-6 — Channel contract over the FR-302 signal substrate

| | |
|---|---|
| Status | Design — approved, awaiting spec review |
| Date | 2026-07-18 |
| Roadmap item | `E-6` (§9.2) |
| Requirements served | FR-303, FR-305, FR-601, FR-602, US-1, US-7 (via later E-items); this increment lands the shared contract only |
| Scope guard | Contract + workflow query only. **No new surface.** E-7 refits the CLI as the proof. |

## 1. Problem

We track notifications (FR-303), a cross-run inbox (FR-305), the dashboard
backend (FR-601), and an MCP server (FR-602) as four independent unbuilt items.
They are one primitive wearing four hats: **render the pending decision, deliver
it, translate the reply into a signal.** We already own the hard half — FR-302
gives idempotent signals with `(gate, round)` identity and first-decision-wins,
so two channels racing the same gate are safe by construction.

The gap E-6 closes is that there is **no shared contract** for that primitive,
and — more concretely — **nothing renderable to build it on.** Today the
workflow exposes only:

- `status()` → `"awaiting:merge"` (a bare string)
- `pending_gate()` → the same string when it starts with `awaiting:`

A channel cannot render "Q1: Use OIDC or SAML?", a stage gate's revision
context, a task escalation's failing analysis, or a merge gate's check table
from those. The CLI is effectively blind: the operator must already know the
question text and gate name out of band (`cli.py:140-155`).

### 1.1 The substrate is exactly two signals

Grounding this in `feature.py`:

- `submit_gate_decision(GateDecision)` — idempotent per `(gate, round)`
  (`feature.py:332-338`).
- `answer_question(question_id, answer)` — `setdefault`, first-wins
  (`feature.py:340-342`).

Everything a human decides flows through these two. A **task escalation**
(US-3) is `self._gate(f"task:{task.id}", cfg)` (`feature.py:601`) — a gate. A
**merge override** is the merge gate itself; an APPROVE with comments records
`GateOverride`s (`feature.py:1041-1054`) — a gate. So the four item types the
mock dashboard imagines (`interfaces/dashboard/frontend/src/api/types.ts:83-88`:
clarify / gate / override / escalation) collapse onto **two signals**.

The consequence that shapes the whole contract: **`translate` has only two
targets**, even though *rendering* differs per decision type.

## 2. Non-goals

- No new surface (CLI refit is E-7, notify is E-9, dashboard is E-10, MCP is
  E-11, cross-run inbox is E-8).
- No `deliver` *implementation*; only the seam.
- No change to `submit_gate_decision` / `answer_question` semantics; no change
  to `status()` / `pending_gate()` (kept for backward compatibility).

## 3. Architecture — two layers across the sandbox boundary

```
feature.py  --(populates)-->  self._pending: dict[str, PendingDecision]
                                      │
              pending_decisions()  ◄──┘   (new @workflow.query)
                                      │
interfaces/channels/contract.py:     ▼
   Channel.render(PendingDecision) -> RenderedDecision      (present)
   Channel.translate(d, Reply)     -> SignalCall            (reply → signal)
   PushChannel.deliver(Rendered)   -> None                  (push surfaces only)
                                      │
              SignalCall  ──► handle.signal(submit_gate_decision | answer_question)
```

**Layer A — workflow-side (`src/sdlc/pending.py`, new).** Pydantic-only, so it
is importable inside the Temporal workflow sandbox. The source of truth for what
a human owes a decision on. New module (not `models.py`) because these types are
produced by `feature.py` and consumed by the interface layer, and `models.py`'s
gate cluster is already large.

**Layer B — interface-side (`interfaces/channels/contract.py`, new).** Imports
Layer A. Pure `render`/`translate`; `deliver` is an opt-in extension only push
surfaces implement. No surface is constructed here.

## 4. Layer A — workflow-side types

```python
# src/sdlc/pending.py
from typing import Literal
from pydantic import BaseModel
from .gate import CheckResult          # reused, not redefined

class PendingDecision(BaseModel):
    """Base for the discriminated union returned by pending_decisions()."""
    key: str          # resolution key: question_id, or gate_key(gate, round)
    kind: Literal["clarify", "stage_gate", "task_escalation", "merge_gate"]

class ClarifyPending(PendingDecision):        # reply -> answer_question
    kind: Literal["clarify"] = "clarify"
    question: str
    why_it_matters: str
    suggested_answer: str | None = None

class StageGatePending(PendingDecision):      # reply -> submit_gate_decision
    kind: Literal["stage_gate"] = "stage_gate"
    gate: str
    round: int
    spec_summary: str

class TaskEscalationPending(PendingDecision): # reply -> submit_gate_decision
    kind: Literal["task_escalation"] = "task_escalation"
    gate: str
    round: int
    task_id: str
    analysis: str
    attempts: int

class MergeGatePending(PendingDecision):      # reply -> submit_gate_decision
    kind: Literal["merge_gate"] = "merge_gate"
    gate: str
    round: int
    checks: list[CheckResult] = []
    verdict: str | None = None
```

`CheckResult` is reused from `gate.py` (`gate.py:27-32`) — already
pydantic/sandbox-safe. No new check-row type.

> **Serialization note (for the plan):** the query must be typed as a
> *discriminated union* so subclass fields survive the pydantic data converter,
> not as the bare base class. Define
> `PendingItem = Annotated[ClarifyPending | StageGatePending |
> TaskEscalationPending | MergeGatePending, Field(discriminator="kind")]` and
> return `list[PendingItem]`. Returning `list[PendingDecision]` (the base) would
> drop each variant's extra fields on the wire.

`GateContext` is the optional bundle a caller hands to `_gate`. `_gate` selects
the variant by gate name (`merge` → `MergeGatePending`, `task:*` →
`TaskEscalationPending`, else `StageGatePending`):

```python
class GateContext(BaseModel):
    spec_summary: str | None = None      # stage gates
    checks: list[CheckResult] = []       # merge gate
    verdict: str | None = None           # merge gate
    analysis: str | None = None          # task escalation
    attempts: int | None = None          # task escalation
    task_id: str | None = None           # task escalation
```

## 5. Layer B — interface types and the Protocol

```python
# interfaces/channels/contract.py
from typing import Literal, Protocol
from pydantic import BaseModel
from sdlc.models import GateDecision, GateOutcome
from sdlc.pending import PendingDecision

class RenderedDecision(BaseModel):        # surface-neutral presentation
    key: str
    title: str
    body: str
    reply_kind: Literal["text", "gate"]   # text=answer; gate=approve/revise/reject
    suggested: str | None = None          # suggested answer / default
    rows: list[tuple[str, str]] = []      # extra display rows (e.g. check table)

class Reply(BaseModel):                   # what a surface collects from the operator
    outcome: GateOutcome | None = None    # gate replies
    text: str | None = None               # answer text, or comment/guidance

class SignalCall(BaseModel):              # translate's output; transport invokes it
    signal: Literal["answer_question", "submit_gate_decision"]
    question_id: str | None = None        # answer_question
    answer: str | None = None             # answer_question
    decision: GateDecision | None = None  # submit_gate_decision

class Channel(Protocol):
    def render(self, d: PendingDecision) -> RenderedDecision: ...
    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall: ...

class PushChannel(Channel, Protocol):
    async def deliver(self, r: RenderedDecision) -> None: ...
```

### 5.1 Shared default behavior

Default rendering is identical across surfaces (a CLI and a Slack channel render
the *same* `RenderedDecision`; they differ only in how they *display* it and how
they collect a `Reply` — that display/collect transport is the surface's own
code, not the contract). So E-6 ships module-level reference functions:

```python
def default_render(d: PendingDecision) -> RenderedDecision: ...
def default_translate(d: PendingDecision, reply: Reply) -> SignalCall: ...
```

A surface's `Channel` implementation delegates to these; it *may* override
`render` for richer presentation (e.g. Slack blocks). `default_translate`:

- `ClarifyPending` → `SignalCall(signal="answer_question",
  question_id=d.key, answer=reply.text)`.
- any gate variant → `SignalCall(signal="submit_gate_decision",
  decision=GateDecision(gate=d.gate, round=d.round, outcome=reply.outcome,
  decided_by="human", comments=reply.text, guidance=reply.text if REVISE))`.

`translate` copies `d.gate`/`d.round` into the `GateDecision`, so a reply can
never land on the wrong round.

## 6. Workflow-side wiring (the load-bearing change)

1. `self._pending: dict[str, PendingDecision] = {}` on the workflow.

2. **Clarify wait** (`feature.py:718-734`). `reqs.open_questions` is currently a
   local variable the workflow never stores. Before `wait_condition`, stash one
   `ClarifyPending` per unanswered question into `self._pending`; remove each on
   answer (or clear all after the wait resolves).

3. **`_gate`** (`feature.py:354-389`) gains `context: GateContext | None = None`.
   Before `wait_condition` it builds the right variant into
   `self._pending[key]`; the existing `finally` clears it. The four call sites
   pass context:
   - architecture / planning (`_revisable_stage`, `feature.py:404,411`) →
     `GateContext(spec_summary=...)`.
   - task escalation (`feature.py:601`) → `GateContext(task_id=task.id,
     analysis=..., attempts=...)`.
   - merge (`feature.py` merge gate) → `GateContext(checks=gate_report.checks,
     verdict=...)`.

4. New `@workflow.query pending_decisions() -> list[PendingDecision]` returning
   `list(self._pending.values())`. `status()` / `pending_gate()` unchanged.

Populating `self._pending` from within the workflow keeps the render source
deterministic and durable (it is reconstructed from history on replay like any
other workflow state).

## 7. Error handling

- `pending_decisions()` returns `[]` when nothing is pending.
- Stale or duplicate replies are already safe under FR-302
  (`submit_gate_decision` first-wins per `(gate, round)`; `answer_question`
  `setdefault`), so `translate`/the contract adds **no** extra guard.
- Round drift is prevented structurally: the pending item carries its `round`
  and `translate` copies it into the emitted `GateDecision`.

## 8. Testing

- **Pure unit (no Temporal):** `default_render` and `default_translate` for all
  four variants — assert `RenderedDecision` fields, and that each gate outcome
  (`approve`/`revise`/`reject`) round-trips to the correct `GateDecision`
  (right gate, round, outcome, guidance on revise); clarify round-trips to
  `answer_question(question_id, answer)`.
- **Reference channel:** a small in-module `ReferenceChannel` proving the
  `Channel` Protocol is implementable; doubles as the test fixture.
- **Workflow query test:** using existing `tests/fakes/`, drive the workflow to
  the clarify wait and to a gate wait, and assert `pending_decisions()` returns
  the correct variant with populated context (e.g. merge gate carries
  `checks`).

## 9. Files

| File | Change |
|---|---|
| `src/sdlc/pending.py` | **new** — `PendingDecision` union + `GateContext` |
| `src/sdlc/workflows/feature.py` | `self._pending`, populate at clarify + `_gate`, thread `GateContext` through 4 call sites, `pending_decisions()` query |
| `interfaces/channels/__init__.py` | **new** — package |
| `interfaces/channels/contract.py` | **new** — `RenderedDecision`, `Reply`, `SignalCall`, `Channel`, `PushChannel`, `default_render`, `default_translate`, `ReferenceChannel` |
| `tests/` | pure contract tests + workflow query test |

## 10. What this unblocks

- **E-7** refits the existing CLI (`answer`/`approve`/`reject`) onto the
  contract — the deliberate first consumer, validating the contract against a
  known-good surface before any new surface depends on it.
- **E-8** cross-run inbox becomes a query over `pending_decisions()` across
  run handles.
- **E-9/E-10/E-11** implement `PushChannel.deliver` (notify, dashboard, MCP)
  against a settled contract.
