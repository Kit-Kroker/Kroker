# Operator Chat Surface (E-86) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the operator a browser chat that can start, check, and follow factory runs, backed by a reusable typed tool layer that E-11's MCP server will import rather than reimplement.

**Architecture:** A new `src/sdlc/operator/` package holds twelve plain async verb functions over the primitives that already exist — `channels/transport.py`, `dashboard/fleet.py`'s shared `FleetPoller`, and `board/store.py`. That package imports neither `pydantic_ai` nor `fastapi`. A single sibling module, `operator/agent.py`, wraps those functions in a Pydantic AI `FunctionToolset` (writes marked `requires_approval=True`) and serves them through `pydantic_ai.ui.create_web_app`, mounted at `/chat` on the existing uvicorn app behind `SDLC_CHAT_ENABLED`.

**Tech Stack:** Python 3.11+, `pydantic-ai-slim` 2.21.0 (`pydantic_ai.ui`, `pydantic_ai.toolsets`), `starlette` 1.3.1, `fastapi`, `pydantic` v2, `temporalio`, SQLite via `BoardStore`, `pytest` + `pytest-asyncio`.

**Spec:** `docs/superpowers/specs/2026-08-20-operator-chat-surface-design.md`

## Global Constraints

- **`src/sdlc/operator/tools.py`, `render.py`, `deps.py`, `errors.py` MUST NOT import `pydantic_ai` or `fastapi`.** Spec D3. Task 10 adds a test that fails the build if they do. Only `operator/agent.py` may import `pydantic_ai`.
- **Everything importable by tests lives under `src/`.** `pyproject`'s `packages.find` is rooted at `src`. `interfaces/chat/` holds assets and nothing importable.
- **Operator-facing strings are ASCII only.** House rule stated in `src/sdlc/channels/transport.py:12` — the Windows console cannot print non-ASCII. This overrides the `·` separators used illustratively in the spec's §5.4; use ` | `.
- **The agent never supplies a gate round.** `transport.resolve_key` derives it from the pending item. Spec D9.
- **`GateOutcome`** is `approve` / `reject` / `revise`; **`ProjectMode`** is `greenfield` / `brownfield`. Use the existing enums from `sdlc.models`, never string literals.
- **`read_artifact` cap: `32 * 1024` bytes** per call (spec D7). The board's HTTP `MAX_CONTENT_BYTES` of `512 * 1024` is a different consumer's cap; do not reuse it.
- **`follow` clamps `timeout_s` to `[5, 120]`** and refuses after **10** consecutive calls (spec §7).
- **Flag `SDLC_CHAT_ENABLED`, default off.** Value `"1"` enables. Anything else, including unset, means the mount does not happen (spec D10).
- **Never surface a traceback to the model.** Every failure path returns `ToolError` with a typed, actionable message (spec §11).
- **Run tests with:** `pytest <path> -v` from the repo root. The default `addopts` deselects `slow`/`temporal`/`docker`/`prompt_eval`; the one Temporal test in Task 11 needs `-m temporal`.
- **Commit on the branch `e86-operator-chat-surface`.**

---

## File Structure

| File | Responsibility |
|---|---|
| `src/sdlc/channels/contract.py` *(modify)* | Gains `ActorChannel` — the identity-carrying `Channel`, extracted so chat and dashboard share one implementation |
| `src/sdlc/dashboard/channel.py` *(modify)* | `DashboardChannel` becomes a thin subclass of `ActorChannel`; name and behaviour unchanged |
| `src/sdlc/operator/errors.py` | `ToolError` + board/transport exception translation |
| `src/sdlc/operator/deps.py` | `OperatorDeps` — injected collaborators and limits |
| `src/sdlc/operator/render.py` | Models → compact ASCII text; the orientation line |
| `src/sdlc/operator/tools.py` | The twelve verb functions. No framework imports |
| `src/sdlc/operator/agent.py` | The only `pydantic_ai` consumer: toolset, agent, web app, follow-counter reset |
| `interfaces/chat/agent.yaml` | Model + settings asset |
| `interfaces/chat/instructions.md` | System prompt asset |
| `interfaces/dashboard/api/main.py` *(modify)* | Conditional `/chat` mount |

**Deviation from the spec, deliberate, flagged here:** spec §6 says *"`ChatChannel` is a third `Channel` implementation beside `DashboardChannel`."* Reading `dashboard/channel.py` shows it contains nothing dashboard-specific — it is "a `Channel` carrying a self-asserted operator identity." Copying twenty lines to change one string would be the wrong call, so Task 1 extracts `ActorChannel` and both surfaces use it. `DashboardChannel` keeps its name, so E-10's tests and `dashboard/api.py` are untouched.

---

### Task 1: `ActorChannel` — one identity-carrying channel, two surfaces

**Files:**
- Modify: `src/sdlc/channels/contract.py` (append after `ReferenceChannel`)
- Modify: `src/sdlc/dashboard/channel.py:20-33`
- Test: `tests/test_actor_channel.py`

**Interfaces:**
- Consumes: `default_render`, `default_translate`, `PendingDecision`, `Reply`, `SignalCall`, `RenderedDecision` — all already in `contract.py`.
- Produces: `sdlc.channels.contract.ActorChannel(actor: str)` with `.render(d)` and `.translate(d, reply)`. `translate` stamps `call.decision.reviewer = self.actor` when a decision is present. `sdlc.dashboard.channel.DashboardChannel` remains importable and behaviourally identical.

- [ ] **Step 1: Write the failing test**

Create `tests/test_actor_channel.py`:

```python
"""ActorChannel stamps identity on GateDecision.reviewer, never decided_by."""

from sdlc.channels.contract import ActorChannel, Reply
from sdlc.dashboard.channel import DashboardChannel
from sdlc.models import GateOutcome
from sdlc.pending import ClarifyPending, StageGatePending

GATE = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


def test_gate_reply_carries_actor_as_reviewer():
    call = ActorChannel(actor="chat:mika").translate(GATE, Reply(outcome=GateOutcome.APPROVE))
    assert call.decision.reviewer == "chat:mika"


def test_actor_never_reaches_decided_by():
    call = ActorChannel(actor="chat:mika").translate(GATE, Reply(outcome=GateOutcome.APPROVE))
    assert call.decision.decided_by == "human"


def test_text_reply_has_no_decision_to_stamp():
    call = ActorChannel(actor="chat:mika").translate(Q1, Reply(text="yes"))
    assert call.signal == "answer_question"
    assert call.decision is None


def test_render_delegates_to_the_module_default():
    assert ActorChannel(actor="chat:mika").render(GATE).reply_kind == "gate"


def test_dashboard_channel_is_an_actor_channel():
    assert isinstance(DashboardChannel(actor="human:sam"), ActorChannel)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_actor_channel.py -v`
Expected: FAIL — `ImportError: cannot import name 'ActorChannel' from 'sdlc.channels.contract'`

- [ ] **Step 3: Add `ActorChannel` to `contract.py`**

Append to `src/sdlc/channels/contract.py`, after `ReferenceChannel`:

```python
class ActorChannel:
    """A Channel carrying a self-asserted operator identity (OQ-11).

    contract.py states that "a surface MAY override render for richer
    presentation"; this uses that extension point to carry identity without
    adding a parameter to the pure default_translate.

    The identity lands on GateDecision.reviewer, NEVER on decided_by:
    decided_by is Literal["human","policy","timeout"] and
    ReadinessOverride.approved_by carries it verbatim, so a free-string actor
    there would destroy the one signal that keeps "policy" legible as
    non-human. triage.py:115 sets reviewer for exactly this reason (FR-1004).

    Shared by every identity-bearing surface: the dashboard (E-10) and the
    chat surface (E-86) differ only in the actor string they pass.
    """

    def __init__(self, actor: str) -> None:
        self.actor = actor

    def render(self, d: PendingDecision) -> RenderedDecision:
        return default_render(d)

    def translate(self, d: PendingDecision, reply: Reply) -> SignalCall:
        call = default_translate(d, reply)
        if call.decision is not None:
            call.decision.reviewer = self.actor
        return call
```

- [ ] **Step 4: Reduce `DashboardChannel` to a subclass**

Replace the class body in `src/sdlc/dashboard/channel.py` (keep the module docstring, retarget its first line):

```python
"""The dashboard's Channel adapter (E-10).

The identity-carrying behaviour now lives in channels/contract.py's
ActorChannel, shared with the chat surface (E-86). This subclass exists so
the dashboard's adapter still has a name of its own at its own import path;
it adds nothing and is expected to stay empty.
"""

from __future__ import annotations

from ..channels.contract import ActorChannel


class DashboardChannel(ActorChannel):
    """Channel impl carrying a self-asserted operator identity (OQ-11)."""
```

- [ ] **Step 5: Run the new test and E-10's existing channel tests**

Run: `pytest tests/test_actor_channel.py tests/test_dashboard_channel.py tests/test_dashboard_api.py -v`
Expected: PASS — all of them. `test_dashboard_channel.py` is unmodified and must still pass; that is the proof the extraction changed no behaviour.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/channels/contract.py src/sdlc/dashboard/channel.py tests/test_actor_channel.py
git commit -m "refactor(channels): extract ActorChannel so chat and dashboard share one identity adapter"
```

---

### Task 2: `ToolError` and error translation

**Files:**
- Create: `src/sdlc/operator/__init__.py`
- Create: `src/sdlc/operator/errors.py`
- Test: `tests/test_operator_errors.py`

**Interfaces:**
- Consumes: `sdlc.board.store.{NotFoundError, ConflictError, InvalidTransition}`, `sdlc.channels.transport.{NoMatch, Ambiguous}`.
- Produces:
  - `ToolError(Exception)` with attribute `message: str`.
  - `translate(exc: Exception, *, hint: str = "") -> ToolError` — maps a known domain exception to a `ToolError` whose message is actionable and traceback-free. Re-raises nothing; always returns.
  - Decorator `guard(fn)` — wraps an async verb function so any known domain exception becomes a raised `ToolError` and any unknown exception becomes a `ToolError` naming the exception type only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_errors.py`:

```python
"""Domain exceptions become typed, actionable, traceback-free ToolErrors."""

import pytest

from sdlc.board.store import ConflictError, InvalidTransition, NotFoundError
from sdlc.channels.transport import Ambiguous, NoMatch
from sdlc.operator.errors import ToolError, guard, translate


def test_nomatch_tells_the_model_to_re_read():
    err = translate(NoMatch("no pending item with key 'Q9' on this run"))
    assert isinstance(err, ToolError)
    assert "Q9" in err.message
    assert "re-read" in err.message.lower()


def test_ambiguous_is_reported_as_needing_narrowing():
    err = translate(Ambiguous("ambiguous -- 2 gates pending:\n  a\n  b"))
    assert "narrow" in err.message.lower()


def test_board_not_found_keeps_the_stores_own_message():
    err = translate(NotFoundError("no project 'kroker'"))
    assert "no project 'kroker'" in err.message


def test_conflict_and_invalid_transition_are_distinguishable():
    assert "conflict" in translate(ConflictError("row_version")).message.lower()
    assert "transition" in translate(InvalidTransition("PENDING -> DONE")).message.lower()


def test_unknown_exception_leaks_no_detail():
    err = translate(RuntimeError("D:\\own\\Kroker\\secret\\path.py exploded"))
    assert "secret" not in err.message
    assert "RuntimeError" in err.message


def test_hint_is_appended_when_given():
    err = translate(NotFoundError("no project 'x'"), hint="call list_projects")
    assert "call list_projects" in err.message


@pytest.mark.asyncio
async def test_guard_converts_a_raised_domain_error():
    @guard
    async def boom():
        raise NotFoundError("no project 'x'")

    with pytest.raises(ToolError) as e:
        await boom()
    assert "no project 'x'" in e.value.message


@pytest.mark.asyncio
async def test_guard_passes_tool_errors_through_unchanged():
    @guard
    async def boom():
        raise ToolError("already typed")

    with pytest.raises(ToolError) as e:
        await boom()
    assert e.value.message == "already typed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.operator'`

- [ ] **Step 3: Create the package and `errors.py`**

Create `src/sdlc/operator/__init__.py`:

```python
"""Operator-facing verbs over the channel contract (E-86).

The tool layer every operator surface shares. tools.py, render.py, deps.py
and errors.py import no web framework and no LLM library -- agent.py is the
only pydantic_ai consumer, and E-11's MCP server is its sibling. The
layering is asserted by tests/test_operator_layering.py, not merely
documented here.
"""
```

Create `src/sdlc/operator/errors.py`:

```python
"""Typed, model-actionable tool failures (E-86 spec 5.3, 11).

A traceback rendered into a chat UI leaks filesystem paths into a transcript
the model then echoes. Every failure a tool can produce therefore leaves this
module as a ToolError whose message is safe to show and specific enough for
the model to do something different next time.
"""

from __future__ import annotations

import functools

from ..board.store import ConflictError, InvalidTransition, NotFoundError
from ..channels.transport import Ambiguous, NoMatch


class ToolError(Exception):
    """A failure the model is expected to read and act on."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def translate(exc: Exception, *, hint: str = "") -> ToolError:
    """Map a known domain exception to a ToolError. Never raises."""
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, NoMatch):
        msg = (
            f"{exc.message}\nThis key is no longer pending; re-read the "
            f"inbox or the run and use a current key."
        )
    elif isinstance(exc, Ambiguous):
        msg = f"{exc.message}\nNarrow it by passing an exact key."
    elif isinstance(exc, NotFoundError):
        msg = str(exc)
    elif isinstance(exc, ConflictError):
        msg = f"board conflict: {exc}"
    elif isinstance(exc, InvalidTransition):
        msg = f"invalid board transition: {exc}"
    else:
        # Deliberately type-only: the message may carry paths or credentials.
        msg = f"the factory raised {type(exc).__name__}; the operator should check the server log"
    if hint:
        msg = f"{msg}\n{hint}"
    return ToolError(msg)


def guard(fn):
    """Wrap an async verb so every exception leaves it as a ToolError."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 -- funnelled into ToolError
            raise translate(e) from None

    return wrapper
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_errors.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/__init__.py src/sdlc/operator/errors.py tests/test_operator_errors.py
git commit -m "feat(operator): typed traceback-free tool errors"
```

---

### Task 3: `OperatorDeps`

**Files:**
- Create: `src/sdlc/operator/deps.py`
- Test: `tests/test_operator_deps.py`

**Interfaces:**
- Consumes: `sdlc.dashboard.fleet.FleetPoller`, `sdlc.board.store.BoardStore` (both as type hints only — the dataclass stores whatever it is handed, so tests pass fakes).
- Produces:

```python
@dataclass
class OperatorDeps:
    poller: Any
    board: Any
    starter: Any
    actor: str = "chat:unknown"
    max_artifact_bytes: int = 32 * 1024
    max_follow_calls: int = 10
    follow_calls: int = 0

    def reset_request_state(self) -> None: ...
    def note_follow(self) -> None:   # raises ToolError past the cap
    def note_other_tool(self) -> None:
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_deps.py`:

```python
"""OperatorDeps carries collaborators and enforces the follow-call brake."""

import pytest

from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError


def deps(**kw):
    return OperatorDeps(poller=object(), board=object(), starter=object(), **kw)


def test_defaults_match_the_spec():
    d = deps()
    assert d.max_artifact_bytes == 32 * 1024
    assert d.max_follow_calls == 10
    assert d.actor.startswith("chat:")


def test_follow_calls_accumulate():
    d = deps()
    d.note_follow()
    d.note_follow()
    assert d.follow_calls == 2


def test_refuses_past_the_cap_with_actionable_text():
    d = deps(max_follow_calls=2)
    d.note_follow()
    d.note_follow()
    with pytest.raises(ToolError) as e:
        d.note_follow()
    assert "report to the operator" in e.value.message


def test_any_other_tool_resets_the_streak():
    d = deps(max_follow_calls=2)
    d.note_follow()
    d.note_other_tool()
    d.note_follow()
    d.note_follow()  # streak restarted, so this is still allowed
    assert d.follow_calls == 2


def test_reset_request_state_clears_the_counter():
    d = deps()
    d.note_follow()
    d.reset_request_state()
    assert d.follow_calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_deps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.operator.deps'`

- [ ] **Step 3: Write `deps.py`**

```python
"""Injected collaborators and per-request limits for the operator tools.

Everything a verb needs arrives here rather than being imported, so a unit
test substitutes a fake poller and an in-memory BoardStore without a Temporal
client, an HTTP server, or a model.

follow_calls is a STREAK, not a total: note_other_tool() resets it. The brake
the spec asks for is on *consecutive* waits -- an agent that reports to the
operator and then waits again is behaving correctly, and only an agent that
waits forever without reporting is not. reset_request_state() additionally
zeroes it per HTTP request; agent.py installs that as ASGI middleware,
because create_web_app holds one deps object for the life of the mount.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ToolError


@dataclass
class OperatorDeps:
    poller: Any  # dashboard.fleet.FleetPoller
    board: Any  # board.store.BoardStore
    starter: Any  # async (IdeaBrief, PipelineConfig, str) -> str
    actor: str = "chat:unknown"
    max_artifact_bytes: int = 32 * 1024
    max_follow_calls: int = 10
    follow_calls: int = 0

    def reset_request_state(self) -> None:
        self.follow_calls = 0

    def note_follow(self) -> None:
        if self.follow_calls >= self.max_follow_calls:
            raise ToolError(
                f"refusing a {self.follow_calls + 1}th consecutive wait; "
                f"report to the operator before waiting again"
            )
        self.follow_calls += 1

    def note_other_tool(self) -> None:
        self.follow_calls = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_deps.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/deps.py tests/test_operator_deps.py
git commit -m "feat(operator): OperatorDeps with the consecutive-follow brake"
```

---

### Task 4: `render.py` — compact ASCII views and the orientation line

**Files:**
- Create: `src/sdlc/operator/render.py`
- Test: `tests/test_operator_render.py`

**Interfaces:**
- Consumes: `sdlc.models.{RunState, RunSummary}`, `sdlc.dashboard.fleet.FleetSnapshot`, `sdlc.channels.inbox.RunInbox`, `sdlc.channels.transport.describe`, `sdlc.channels.contract.default_render`.
- Produces:
  - `run_line(run: RunState, pending: Sequence[PendingDecision] = ()) -> str`
  - `summary_line(s: RunSummary) -> str`
  - `pending_block(d: PendingDecision) -> str`
  - `pending_for(snap: FleetSnapshot, run_id: str) -> list[PendingDecision]`
  - `runs_view(snap: FleetSnapshot, status: str) -> str`
  - `run_detail(run: RunState, pending: Sequence[PendingDecision]) -> str`
  - `inbox_view(snap: FleetSnapshot) -> str`
  - `orientation(snap: FleetSnapshot, cap: int = 20) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_render.py`:

```python
"""Compact ASCII rendering; the agent never sees a raw model dump."""

from datetime import datetime, timezone

from sdlc.channels.inbox import RunInbox
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.models import RunState
from sdlc.operator import render
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
GATE = StageGatePending(
    key="architecture#2", gate="architecture", round=2, spec_summary="two services, one queue"
)
Q1 = ClarifyPending(key="Q1", question="Which auth provider?", why_it_matters="drives the schema")


def a_run(run_id="feature-add-sso", **kw):
    base = dict(
        run_id=run_id,
        title="Add SSO",
        mode="brownfield",
        status="awaiting:architecture",
        started_at=AT,
        current_stage="architecture",
        cost_usd_total=4.12,
    )
    base.update(kw)
    return RunState(**base)


def test_run_line_is_ascii_only():
    line = render.run_line(a_run(), [GATE])
    assert line.isascii(), line


def test_run_line_names_run_stage_status_pending_and_cost():
    line = render.run_line(a_run(), [GATE])
    assert "feature-add-sso" in line
    assert "architecture" in line
    assert "awaiting:architecture" in line
    assert "round 2" in line
    assert "4.12" in line


def test_run_line_without_pending_says_so():
    assert "none" in render.run_line(a_run(), []).lower()


def test_missing_cost_is_not_reported_as_free():
    line = render.run_line(a_run(cost_usd_total=None), [])
    assert "0.00" not in line
    assert "unknown" in line.lower()


def test_pending_block_carries_key_title_and_reply_kind():
    block = render.pending_block(GATE)
    assert "architecture#2" in block
    assert "Gate: architecture (round 2)" in block
    assert "gate" in block


def test_pending_block_for_a_question_offers_the_suggestion_slot():
    assert "text" in render.pending_block(Q1)


def test_orientation_lists_one_line_per_open_run():
    snap = FleetSnapshot(
        at=AT,
        total_open_runs=2,
        runs=[a_run("r1"), a_run("r2")],
        inbox=[RunInbox(run_id="r1", pending=[GATE])],
    )
    out = render.orientation(snap)
    assert out.count("\n") >= 1
    assert "r1" in out and "r2" in out
    assert "round 2" in out  # r1's pending item is attached


def test_orientation_degrades_to_a_count_past_the_cap():
    snap = FleetSnapshot(at=AT, total_open_runs=30, runs=[a_run(f"r{i}") for i in range(30)])
    out = render.orientation(snap, cap=20)
    assert "30 open runs" in out
    assert "r29" not in out


def test_orientation_with_no_open_runs_says_so():
    assert "no open runs" in render.orientation(FleetSnapshot(at=AT)).lower()


def test_runs_view_open_excludes_closed_runs():
    snap = FleetSnapshot(at=AT, total_open_runs=1, runs=[a_run("r1")])
    assert "r1" in render.runs_view(snap, "open")


def test_inbox_view_groups_by_run():
    snap = FleetSnapshot(
        at=AT,
        total_open_runs=1,
        runs=[a_run("r1")],
        inbox=[RunInbox(run_id="r1", pending=[GATE, Q1])],
    )
    out = render.inbox_view(snap)
    assert "r1" in out
    assert "architecture#2" in out and "Q1" in out


def test_inbox_view_empty_is_explicit_about_having_checked():
    snap = FleetSnapshot(at=AT, total_open_runs=3, runs=[a_run("r1")])
    out = render.inbox_view(snap)
    assert "3" in out
    assert "nothing pending" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.operator.render'`

- [ ] **Step 3: Write `render.py`**

```python
"""Models -> compact ASCII text for the agent (E-86 spec 5.4).

The agent must never receive a JSON dump of RunState: it costs tokens
proportional to fields nobody asked about, and it invites the model to quote
internal field names back at the operator. Every read verb returns text from
this module instead.

ASCII only, per channels/transport.py:12 -- the same strings can reach a
Windows console through the CLI or a log line.
"""

from __future__ import annotations

from typing import Sequence

from ..channels.contract import default_render
from ..channels.inbox import RunInbox
from ..dashboard.fleet import FleetSnapshot
from ..models import RunState, RunSummary
from ..pending import PendingDecision

ORIENTATION_CAP = 20


def _cost(v: float | None) -> str:
    # None is not zero: RunState documents that a pricing miss must never
    # read as a free run.
    return "cost unknown" if v is None else f"${v:.2f}"


def _pending_summary(pending: Sequence[PendingDecision]) -> str:
    if not pending:
        return "pending: none"
    parts = []
    for d in pending:
        gate = getattr(d, "gate", None)
        parts.append(f"{gate} (round {d.round})" if gate else d.key)
    return "pending: " + ", ".join(parts)


def run_line(run: RunState, pending: Sequence[PendingDecision] = ()) -> str:
    return " | ".join(
        [
            run.run_id,
            run.mode,
            f"stage {run.current_stage or 'not started'}",
            run.status,
            _pending_summary(pending),
            _cost(run.cost_usd_total),
        ]
    )


def summary_line(s: RunSummary) -> str:
    return " | ".join(
        [
            s.run_id,
            "closed",
            getattr(s, "status", "closed"),
            _cost(getattr(s, "cost_usd_total", None)),
        ]
    )


def pending_block(d: PendingDecision) -> str:
    r = default_render(d)
    lines = [
        f"key: {r.key}",
        f"title: {r.title}",
        f"reply with: {r.reply_kind}",
        f"detail: {r.body}",
    ]
    if r.suggested:
        lines.append(f"suggested: {r.suggested}")
    lines.extend(f"  {name}: {value}" for name, value in r.rows)
    return "\n".join(lines)


def pending_for(snap: FleetSnapshot, run_id: str) -> list[PendingDecision]:
    for item in snap.inbox:
        if item.run_id == run_id:
            return list(item.pending)
    return []


def runs_view(snap: FleetSnapshot, status: str) -> str:
    lines: list[str] = []
    if status in ("open", "all"):
        lines += [run_line(r, pending_for(snap, r.run_id)) for r in snap.runs]
    if status in ("closed", "all"):
        lines += [summary_line(c) for c in snap.closed]
    if not lines:
        return f"no {status} runs"
    head = f"{len(lines)} {status} run(s):"
    return "\n".join([head, *lines])


def run_detail(run: RunState, pending: Sequence[PendingDecision]) -> str:
    blocks = [
        run_line(run, pending),
        f"title: {run.title}",
        f"started: {run.started_at.isoformat()}",
    ]
    if run.repo_url:
        blocks.append(f"repo: {run.repo_url}")
    if run.budget_usd is not None:
        blocks.append(f"budget: ${run.budget_usd:.2f} ({run.budget_crossings} crossing(s))")
    for d in pending:
        blocks.append("--\n" + pending_block(d))
    return "\n".join(blocks)


def _inbox_run_block(item: RunInbox) -> str:
    return "\n".join([f"run: {item.run_id}", *(pending_block(d) for d in item.pending)])


def inbox_view(snap: FleetSnapshot) -> str:
    if not snap.inbox:
        return f"checked {snap.total_open_runs} open run(s); nothing pending a decision"
    blocks = [_inbox_run_block(i) for i in snap.inbox]
    head = f"{len(snap.inbox)} of {snap.total_open_runs} open run(s) owe a decision:"
    return "\n\n".join([head, *blocks])


def orientation(snap: FleetSnapshot, cap: int = ORIENTATION_CAP) -> str:
    if not snap.runs:
        return "no open runs"
    if len(snap.runs) > cap:
        return f"{snap.total_open_runs} open runs -- too many to list; call list_runs for detail"
    lines = [run_line(r, pending_for(snap, r.run_id)) for r in snap.runs]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_render.py -v`
Expected: PASS (12 tests)

If `summary_line` fails because `RunSummary` lacks `status` or `cost_usd_total`, read the model at `src/sdlc/models.py` and use its real field names — `getattr` defaults are there to keep the module importable, not as an excuse to guess. Fix the function and the test together.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/render.py tests/test_operator_render.py
git commit -m "feat(operator): compact ASCII rendering and the orientation line"
```

---

### Task 5: Live-run read verbs — `list_runs`, `get_run`, `inbox`

**Files:**
- Create: `src/sdlc/operator/tools.py`
- Test: `tests/test_operator_tools_runs.py`

**Interfaces:**
- Consumes: `OperatorDeps` (Task 3), `render` (Task 4), `guard`/`ToolError` (Task 2), `FleetSnapshot`.
- Produces:
  - `async def list_runs(deps: OperatorDeps, status: str = "open") -> str`
  - `async def get_run(deps: OperatorDeps, run_id: str) -> str`
  - `async def inbox(deps: OperatorDeps) -> str`
  - Every verb in this module takes `deps` as its first positional parameter and takes no `RunContext` — that is what keeps `pydantic_ai` out of the module. Task 10's `_bind` strips `deps` when building the toolset.

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_tools_runs.py`:

```python
"""Live-run read verbs over a fake poller. No Temporal, no server, no model."""

from datetime import datetime, timezone

import pytest

from sdlc.channels.inbox import RunInbox
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.models import RunState
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
GATE = StageGatePending(
    key="architecture#2", gate="architecture", round=2, spec_summary="two services"
)
Q1 = ClarifyPending(key="Q1", question="Which auth provider?", why_it_matters="drives the schema")


class FakePoller:
    def __init__(self, snap):
        self.snap = snap

    async def snapshot(self):
        return self.snap


def a_run(run_id="feature-add-sso"):
    return RunState(
        run_id=run_id,
        title="Add SSO",
        mode="brownfield",
        status="awaiting:architecture",
        started_at=AT,
        current_stage="architecture",
        cost_usd_total=4.12,
    )


@pytest.fixture
def deps():
    snap = FleetSnapshot(
        at=AT,
        total_open_runs=1,
        runs=[a_run()],
        inbox=[RunInbox(run_id="feature-add-sso", pending=[GATE, Q1])],
    )
    return OperatorDeps(poller=FakePoller(snap), board=None, starter=None)


@pytest.mark.asyncio
async def test_list_runs_renders_text_not_json(deps):
    out = await tools.list_runs(deps)
    assert "feature-add-sso" in out
    assert "{" not in out


@pytest.mark.asyncio
async def test_list_runs_rejects_an_unknown_status(deps):
    with pytest.raises(ToolError) as e:
        await tools.list_runs(deps, status="sideways")
    assert "open" in e.value.message and "closed" in e.value.message


@pytest.mark.asyncio
async def test_get_run_includes_every_pending_item(deps):
    out = await tools.get_run(deps, "feature-add-sso")
    assert "architecture#2" in out
    assert "Q1" in out


@pytest.mark.asyncio
async def test_get_run_unknown_id_is_a_tool_error_naming_the_id(deps):
    with pytest.raises(ToolError) as e:
        await tools.get_run(deps, "feature-nope")
    assert "feature-nope" in e.value.message


@pytest.mark.asyncio
async def test_inbox_reuses_the_snapshot(deps):
    out = await tools.inbox(deps)
    assert "architecture#2" in out


@pytest.mark.asyncio
async def test_reads_reset_the_follow_streak(deps):
    deps.note_follow()
    await tools.list_runs(deps)
    assert deps.follow_calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_tools_runs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.operator.tools'`

- [ ] **Step 3: Write the first slice of `tools.py`**

```python
"""The operator's twelve verbs (E-86).

Plain async functions taking OperatorDeps first. No pydantic_ai, no fastapi:
agent.py adapts these for the chat surface and E-11's MCP server will adapt
the same functions, so anything framework-shaped belongs in the adapter and
not here. tests/test_operator_layering.py enforces it.

Reads return rendered ASCII text (render.py). read_artifact, follow, and the
three writes return typed models, because their fields -- truncated,
next_offset, timed_out, confirmed -- carry meaning the model must branch on
rather than read prose about.
"""

from __future__ import annotations

from .deps import OperatorDeps
from .errors import ToolError, guard
from . import render

_STATUSES = ("open", "closed", "all")


@guard
async def list_runs(deps: OperatorDeps, status: str = "open") -> str:
    """List factory runs. status is one of open, closed, all."""
    deps.note_other_tool()
    if status not in _STATUSES:
        raise ToolError(f"unknown status {status!r}; use one of {', '.join(_STATUSES)}")
    return render.runs_view(await deps.poller.snapshot(), status)


@guard
async def get_run(deps: OperatorDeps, run_id: str) -> str:
    """Detail for one run, including every decision it is waiting on."""
    deps.note_other_tool()
    snap = await deps.poller.snapshot()
    for r in snap.runs:
        if r.run_id == run_id:
            return render.run_detail(r, render.pending_for(snap, run_id))
    for c in snap.closed:
        if c.run_id == run_id:
            return render.summary_line(c)
    raise ToolError(
        f"no run {run_id!r} among {len(snap.runs)} open and "
        f"{len(snap.closed)} recently closed runs; call list_runs"
    )


@guard
async def inbox(deps: OperatorDeps) -> str:
    """Every decision the factory is waiting on, across all open runs."""
    deps.note_other_tool()
    return render.inbox_view(await deps.poller.snapshot())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_tools_runs.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/tools.py tests/test_operator_tools_runs.py
git commit -m "feat(operator): list_runs, get_run and inbox over the shared poller"
```

---

### Task 6: Board read verbs — `list_projects`, `get_project`, `list_tasks`, `project_events`

**Files:**
- Modify: `src/sdlc/operator/tools.py` (append)
- Test: `tests/test_operator_tools_board.py`

**Interfaces:**
- Consumes: `BoardStore.{list_projects, get_project, list_artifacts, get_artifact, list_tasks, list_events, stats}`. Note `list_tasks(project, plan_version, *, status=None, run_id=None)` takes `plan_version` as a **required positional** — the tool resolves it from the current `plan` artifact when the caller omits it, the way `board/api.py:_current_plan_version` does.
- Produces:
  - `async def list_projects(deps) -> str`
  - `async def get_project(deps, project: str) -> str`
  - `async def list_tasks(deps, project: str, plan_version: int | None = None, status: str | None = None) -> str`
  - `async def project_events(deps, project: str, since: int = 0) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_tools_board.py`:

```python
"""Board read verbs against a real BoardStore on a temp sqlite file."""

import pytest

from sdlc.board.store import BoardStore
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError


@pytest.fixture
def store(tmp_path):
    s = BoardStore(tmp_path / "board.db")
    s.ensure_project("kroker", repo="git@example.com:kroker.git")
    yield s
    s.close()


@pytest.fixture
def deps(store):
    return OperatorDeps(poller=None, board=store, starter=None)


@pytest.mark.asyncio
async def test_list_projects_names_key_and_repo(deps):
    out = await tools.list_projects(deps)
    assert "kroker" in out
    assert "example.com" in out


@pytest.mark.asyncio
async def test_list_projects_empty_is_explicit(tmp_path):
    s = BoardStore(tmp_path / "empty.db")
    try:
        out = await tools.list_projects(OperatorDeps(poller=None, board=s, starter=None))
        assert "no projects" in out.lower()
    finally:
        s.close()


@pytest.mark.asyncio
async def test_get_project_lists_artifact_keys_so_read_artifact_has_a_source(deps):
    out = await tools.get_project(deps, "kroker")
    assert "kroker" in out


@pytest.mark.asyncio
async def test_get_project_unknown_is_a_tool_error(deps):
    with pytest.raises(ToolError) as e:
        await tools.get_project(deps, "nope")
    assert "nope" in e.value.message


@pytest.mark.asyncio
async def test_list_tasks_without_a_plan_says_so_instead_of_raising_typeerror(deps):
    with pytest.raises(ToolError) as e:
        await tools.list_tasks(deps, "kroker")
    assert "plan" in e.value.message.lower()


@pytest.mark.asyncio
async def test_list_tasks_rejects_an_unknown_status(deps):
    with pytest.raises(ToolError) as e:
        await tools.list_tasks(deps, "kroker", plan_version=1, status="sideways")
    assert "sideways" in e.value.message


@pytest.mark.asyncio
async def test_project_events_empty_is_explicit(deps):
    out = await tools.project_events(deps, "kroker")
    assert "no events" in out.lower()


@pytest.mark.asyncio
async def test_board_reads_reset_the_follow_streak(deps):
    deps.note_follow()
    await tools.list_projects(deps)
    assert deps.follow_calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_tools_board.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.operator.tools' has no attribute 'list_projects'`

- [ ] **Step 3: Append the board verbs to `tools.py`**

Add these imports at the top of `tools.py`:

```python
from ..board.models import TaskStatus
from ..board.store import NotFoundError
```

Append:

```python
def _current_plan_version(deps: OperatorDeps, project: str) -> int:
    """The plan version list_tasks defaults to, resolved the way
    board/api.py:_current_plan_version does."""
    try:
        art = deps.board.get_artifact(project, "plan")
    except NotFoundError as e:
        raise ToolError(
            f"project {project!r} has no plan artifact yet, so it has no "
            f"tasks; call get_project to see what it does have"
        ) from None
    if art.current_version is None:
        raise ToolError(
            f"project {project!r} has a plan artifact with no current "
            f"version; pass plan_version explicitly"
        )
    return art.current_version


@guard
async def list_projects(deps: OperatorDeps) -> str:
    """Every project the board knows about."""
    deps.note_other_tool()
    rows = deps.board.list_projects()
    if not rows:
        return "no projects on the board"
    return "\n".join(f"{key} | {repo or 'no repo'}" for key, repo in rows)


@guard
async def get_project(deps: OperatorDeps, project: str) -> str:
    """One project: its repo, its artifact keys, and its task counters.

    The artifact keys listed here are the ONLY keys read_artifact accepts.
    """
    deps.note_other_tool()
    key, repo = deps.board.get_project(project)
    artifacts = deps.board.list_artifacts(project)
    stats = deps.board.stats(project)
    lines = [f"project: {key}", f"repo: {repo or 'no repo'}"]
    if artifacts:
        lines.append("artifacts:")
        lines += [
            f"  {a.key} | {a.status.value} | "
            f"version {a.current_version if a.current_version else '-'}"
            for a in artifacts
        ]
    else:
        lines.append("artifacts: none published yet")
    lines.append(f"tasks: {stats.tasks_by_status or 'none'}")
    lines.append(
        f"fix attempts: {stats.total_fix_attempts} | "
        f"with error: {stats.tasks_with_error} | "
        f"diverged: {stats.diverged_tasks}"
    )
    return "\n".join(lines)


@guard
async def list_tasks(
    deps: OperatorDeps, project: str, plan_version: int | None = None, status: str | None = None
) -> str:
    """Tasks for a project's plan. Defaults to the current plan version."""
    deps.note_other_tool()
    deps.board.get_project(project)
    version = plan_version if plan_version is not None else _current_plan_version(deps, project)
    want = None
    if status is not None:
        try:
            want = TaskStatus(status)
        except ValueError:
            allowed = ", ".join(s.value for s in TaskStatus)
            raise ToolError(f"unknown task status {status!r}; use one of {allowed}") from None
    rows = deps.board.list_tasks(project, version, status=want)
    if not rows:
        return f"no tasks in plan {version} of {project!r}"
    lines = [f"plan {version} of {project!r}, {len(rows)} task(s):"]
    lines += [
        f"  {t.task_id} | {t.status.value} "
        f"(authoritative {t.authoritative_status.value}) | "
        f"attempts {t.fix_attempts}"
        f"{' | error: ' + t.error if t.error else ''}"
        for t in rows
    ]
    return "\n".join(lines)


@guard
async def project_events(deps: OperatorDeps, project: str, since: int = 0) -> str:
    """The board's durable timeline for a project, oldest first."""
    deps.note_other_tool()
    deps.board.get_project(project)
    rows = deps.board.list_events(project, since=since)
    if not rows:
        return f"no events for {project!r} after id {since}"
    lines = [f"{len(rows)} event(s) for {project!r}:"]
    lines += [
        f"  #{e.id} {e.at.isoformat()} | {e.subject} | {e.actor} | "
        f"{e.authority.value} | {e.from_status or '-'} -> "
        f"{e.to_status or '-'}{' | ' + e.detail if e.detail else ''}"
        for e in rows
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_tools_board.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/tools.py tests/test_operator_tools_board.py
git commit -m "feat(operator): board read verbs with plan-version resolution"
```

---

### Task 7: `read_artifact` — capped, paged, no fishing

**Files:**
- Modify: `src/sdlc/operator/tools.py` (append)
- Test: `tests/test_operator_read_artifact.py`

**Interfaces:**
- Consumes: `BoardStore.{get_artifact, list_versions, get_version}`, `sdlc.artifacts.store.ref_to_path`.
- Produces:

```python
class ArtifactRead(BaseModel):
    project: str
    key: str
    version_id: int
    n: int
    sha256: str
    content: str
    total_bytes: int
    truncated: bool
    next_offset: int | None

async def read_artifact(deps, project: str, key: str,
                        version_id: int | None = None,
                        offset: int = 0) -> ArtifactRead
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_read_artifact.py`:

```python
"""read_artifact: 32 KB budget, offset paging, no fishing, pruned blobs."""

import pytest

from sdlc.board.store import BoardStore
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError

BIG = "x" * (80 * 1024)


@pytest.fixture
def deps(tmp_path):
    blob = tmp_path / "spec.md"
    blob.write_text(BIG, encoding="utf-8")
    store = BoardStore(tmp_path / "board.db")
    store.ensure_project("kroker")
    store.publish_artifact_version(
        "kroker",
        "spec",
        run_id="feature-x",
        uri=blob.as_uri(),
        sha256="deadbeef",
        actor="workflow:feature-x",
    )
    try:
        yield OperatorDeps(poller=None, board=store, starter=None)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_first_page_is_capped_at_the_deps_budget(deps):
    got = await tools.read_artifact(deps, "kroker", "spec")
    assert len(got.content) == deps.max_artifact_bytes
    assert got.truncated is True
    assert got.next_offset == deps.max_artifact_bytes
    assert got.total_bytes == len(BIG)


@pytest.mark.asyncio
async def test_paging_reaches_the_end_and_stops(deps):
    offset, seen = 0, 0
    for _ in range(10):
        got = await tools.read_artifact(deps, "kroker", "spec", offset=offset)
        seen += len(got.content)
        if got.next_offset is None:
            break
        offset = got.next_offset
    assert seen == len(BIG)
    assert got.truncated is False


@pytest.mark.asyncio
async def test_a_small_artifact_is_not_marked_truncated(deps, tmp_path):
    small = tmp_path / "plan.md"
    small.write_text("short", encoding="utf-8")
    deps.board.publish_artifact_version(
        "kroker",
        "plan",
        run_id="feature-x",
        uri=small.as_uri(),
        sha256="cafe",
        actor="workflow:feature-x",
    )
    got = await tools.read_artifact(deps, "kroker", "plan")
    assert got.content == "short"
    assert got.truncated is False
    assert got.next_offset is None


@pytest.mark.asyncio
async def test_unknown_key_is_refused_and_points_at_get_project(deps):
    with pytest.raises(ToolError) as e:
        await tools.read_artifact(deps, "kroker", "invented")
    assert "get_project" in e.value.message


@pytest.mark.asyncio
async def test_offset_past_the_end_is_a_tool_error_not_an_empty_read(deps):
    with pytest.raises(ToolError) as e:
        await tools.read_artifact(deps, "kroker", "spec", offset=len(BIG) + 10)
    assert "offset" in e.value.message.lower()


@pytest.mark.asyncio
async def test_pruned_blob_reports_metadata_instead_of_crashing(deps, tmp_path):
    gone = tmp_path / "gone.md"
    gone.write_text("temp", encoding="utf-8")
    deps.board.publish_artifact_version(
        "kroker",
        "arch",
        run_id="feature-x",
        uri=gone.as_uri(),
        sha256="beef",
        actor="workflow:feature-x",
    )
    gone.unlink()
    with pytest.raises(ToolError) as e:
        await tools.read_artifact(deps, "kroker", "arch")
    assert "pruned" in e.value.message.lower()
    assert "beef" in e.value.message


@pytest.mark.asyncio
async def test_read_artifact_resets_the_follow_streak(deps):
    deps.note_follow()
    await tools.read_artifact(deps, "kroker", "spec")
    assert deps.follow_calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_read_artifact.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.operator.tools' has no attribute 'read_artifact'`

If `publish_artifact_version`'s keyword names differ from the ones used above, read its signature at `src/sdlc/board/store.py:115` and fix the fixture. The production code under test does not change.

- [ ] **Step 3: Append `read_artifact` to `tools.py`**

Add to the imports:

```python
from pydantic import BaseModel

from ..artifacts.store import ref_to_path
```

Append:

```python
class ArtifactRead(BaseModel):
    """One page of an artifact body.

    truncated and next_offset exist so the model knows it is holding a
    fragment: without them it fills the gap by inventing the rest.
    """

    project: str
    key: str
    version_id: int
    n: int
    sha256: str
    content: str
    total_bytes: int
    truncated: bool
    next_offset: int | None = None


@guard
async def read_artifact(
    deps: OperatorDeps, project: str, key: str, version_id: int | None = None, offset: int = 0
) -> ArtifactRead:
    """Read one page of a published artifact.

    key MUST be one of the artifact keys get_project listed for this project.
    Large artifacts are paged: when truncated is true, call again with
    offset=next_offset. Summarize what you read; do not quote it whole.
    """
    deps.note_other_tool()
    deps.board.get_project(project)
    # Refuse before touching the blob store: an unknown key is the model
    # fishing, and the answer is to go back to get_project, not to search.
    try:
        art = deps.board.get_artifact(project, key)
    except NotFoundError:
        raise ToolError(
            f"project {project!r} has no artifact {key!r}; call get_project "
            f"and use one of the keys it lists"
        ) from None

    if version_id is None:
        if art.current_version is None:
            raise ToolError(f"artifact {key!r} in {project!r} has no published version")
        version_id = art.current_version
    v = deps.board.get_version(project, version_id)
    if v.key != key:
        raise ToolError(f"version {version_id} belongs to {v.key!r}, not {key!r}")

    path = ref_to_path(v)
    if not path.exists():
        # Metadata outlives the blob (board/api.py:126): the row and its
        # sha256 are still authoritative history when runs/ has been pruned.
        raise ToolError(
            f"the blob for {key!r} version {version_id} was pruned from the "
            f"claim-check store; sha256 {v.sha256}, uri {v.uri}"
        )

    data = path.read_bytes()
    if offset < 0:
        raise ToolError("offset must be zero or positive")
    if offset and offset >= len(data):
        raise ToolError(
            f"offset {offset} is past the end of {key!r} "
            f"({len(data)} bytes); the previous page was the last one"
        )

    window = data[offset : offset + deps.max_artifact_bytes]
    end = offset + len(window)
    truncated = end < len(data)
    return ArtifactRead(
        project=project,
        key=key,
        version_id=v.id,
        n=v.n,
        sha256=v.sha256,
        content=window.decode("utf-8", errors="replace"),
        total_bytes=len(data),
        truncated=truncated,
        next_offset=end if truncated else None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_read_artifact.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/tools.py tests/test_operator_read_artifact.py
git commit -m "feat(operator): read_artifact with a 32KB budget, paging and no fishing"
```

---

### Task 8: `follow` — the bounded wait

**Files:**
- Modify: `src/sdlc/operator/tools.py` (append)
- Test: `tests/test_operator_follow.py`

**Interfaces:**
- Consumes: `FleetPoller.subscribe()` (async context manager yielding an `asyncio.Queue` of `FleetSnapshot`), `OperatorDeps.note_follow`.
- Produces:

```python
MIN_TIMEOUT_S = 5
MAX_TIMEOUT_S = 120

class ChangeReport(BaseModel):
    run_id: str | None
    timed_out: bool
    changed: list[str]
    detail: str

async def follow(deps, run_id: str | None = None, timeout_s: int = 60) -> ChangeReport
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_follow.py`:

```python
"""follow: run-scoped fingerprints, early return, clamping, and the brake."""

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from sdlc.channels.inbox import RunInbox
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.models import RunState
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError
from sdlc.pending import StageGatePending

AT = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
GATE = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")


def a_run(run_id="r1", stage="dev", status="running"):
    return RunState(
        run_id=run_id,
        title="Add SSO",
        mode="brownfield",
        status=status,
        started_at=AT,
        current_stage=stage,
    )


def snap(runs, inbox=(), at=AT):
    return FleetSnapshot(at=at, total_open_runs=len(runs), runs=list(runs), inbox=list(inbox))


class ScriptedPoller:
    """Feeds a fixed list of snapshots to every subscriber, then idles."""

    def __init__(self, first, rest):
        self.first = first
        self.rest = list(rest)

    async def snapshot(self):
        return self.first

    @contextlib.asynccontextmanager
    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        for s in self.rest:
            q.put_nowait(s)
        yield q


def deps_for(poller, **kw):
    return OperatorDeps(poller=poller, board=None, starter=None, **kw)


@pytest.mark.asyncio
async def test_returns_when_the_followed_run_advances_a_stage():
    p = ScriptedPoller(snap([a_run(stage="dev")]), [snap([a_run(stage="qa")])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is False
    assert "qa" in got.detail
    assert any("stage" in c for c in got.changed)


@pytest.mark.asyncio
async def test_returns_immediately_on_a_new_pending_decision():
    p = ScriptedPoller(snap([a_run()]), [snap([a_run()], [RunInbox(run_id="r1", pending=[GATE])])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is False
    assert "architecture" in got.detail


@pytest.mark.asyncio
async def test_returns_when_the_run_leaves_the_open_set():
    p = ScriptedPoller(snap([a_run()]), [snap([])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is False
    assert "closed" in got.detail.lower()


@pytest.mark.asyncio
async def test_another_runs_movement_does_not_end_a_scoped_follow():
    p = ScriptedPoller(
        snap([a_run("r1"), a_run("r2")]), [snap([a_run("r1"), a_run("r2", stage="qa")])]
    )
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is True


@pytest.mark.asyncio
async def test_unscoped_follow_reports_any_runs_movement():
    p = ScriptedPoller(
        snap([a_run("r1"), a_run("r2")]), [snap([a_run("r1"), a_run("r2", stage="qa")])]
    )
    got = await tools.follow(deps_for(p), timeout_s=5)
    assert got.timed_out is False
    assert "r2" in got.detail


@pytest.mark.asyncio
async def test_a_clock_only_snapshot_is_not_a_change():
    later = AT + timedelta(seconds=30)
    p = ScriptedPoller(snap([a_run()]), [snap([a_run()], at=later)])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is True


@pytest.mark.asyncio
async def test_timeout_is_clamped_to_the_floor_and_ceiling():
    p = ScriptedPoller(snap([a_run()]), [])
    assert tools._clamp(1) == tools.MIN_TIMEOUT_S
    assert tools._clamp(9999) == tools.MAX_TIMEOUT_S
    assert tools._clamp(60) == 60


@pytest.mark.asyncio
async def test_unknown_run_is_refused_before_waiting():
    p = ScriptedPoller(snap([a_run("r1")]), [])
    with pytest.raises(ToolError) as e:
        await tools.follow(deps_for(p), run_id="nope", timeout_s=5)
    assert "nope" in e.value.message


@pytest.mark.asyncio
async def test_eleventh_consecutive_follow_is_refused():
    p = ScriptedPoller(snap([a_run()]), [])
    d = deps_for(p, max_follow_calls=2)
    d.note_follow()
    d.note_follow()
    with pytest.raises(ToolError) as e:
        await tools.follow(d, run_id="r1", timeout_s=5)
    assert "report to the operator" in e.value.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_follow.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.operator.tools' has no attribute 'follow'`

- [ ] **Step 3: Append `follow` to `tools.py`**

Add to the imports:

```python
import asyncio
import json
```

Append:

```python
MIN_TIMEOUT_S = 5
MAX_TIMEOUT_S = 120


class ChangeReport(BaseModel):
    """What moved while we waited, or that nothing did."""

    run_id: str | None = None
    timed_out: bool = False
    changed: list[str] = []
    detail: str = ""


def _clamp(timeout_s: int) -> int:
    return max(MIN_TIMEOUT_S, min(MAX_TIMEOUT_S, int(timeout_s)))


def _projection(snap, run_id: str | None) -> str:
    """A stable fingerprint of the part of the fleet being followed.

    Scoped to one run on purpose: a fleet-wide fingerprint moves whenever ANY
    run moves, so a scoped follow against it would return instantly and
    forever. `at` is excluded for the reason dashboard/api.py excludes it --
    the clock is not a change.
    """
    runs = [r for r in snap.runs if run_id is None or r.run_id == run_id]
    inbox = [i for i in snap.inbox if run_id is None or i.run_id == run_id]
    payload = {
        "runs": [json.loads(r.model_dump_json()) for r in runs],
        "inbox": [json.loads(i.model_dump_json()) for i in inbox],
        "closed": sorted(c.run_id for c in snap.closed),
    }
    return json.dumps(payload, sort_keys=True)


def _describe_change(before, after, run_id: str | None) -> tuple[list[str], str]:
    changed: list[str] = []
    before_runs = {r.run_id: r for r in before.runs}
    after_runs = {r.run_id: r for r in after.runs}
    scope = [run_id] if run_id is not None else sorted(set(before_runs) | set(after_runs))
    lines: list[str] = []
    for rid in scope:
        was, now = before_runs.get(rid), after_runs.get(rid)
        if was is not None and now is None:
            changed.append(f"{rid}:closed")
            lines.append(f"{rid} is no longer open -- it closed")
            continue
        if now is None:
            continue
        if was is None:
            changed.append(f"{rid}:appeared")
            lines.append(f"{rid} appeared: {render.run_line(now)}")
            continue
        if was.current_stage != now.current_stage:
            changed.append(f"{rid}:stage")
            lines.append(f"{rid} stage {was.current_stage} -> {now.current_stage}")
        if was.status != now.status:
            changed.append(f"{rid}:status")
            lines.append(f"{rid} status {was.status} -> {now.status}")
    before_keys = {(i.run_id, d.key) for i in before.inbox for d in i.pending}
    for item in after.inbox:
        if run_id is not None and item.run_id != run_id:
            continue
        for d in item.pending:
            if (item.run_id, d.key) not in before_keys:
                changed.append(f"{item.run_id}:pending")
                lines.append(f"{item.run_id} is now waiting on:\n{render.pending_block(d)}")
    if not lines:
        lines.append("something changed that this report does not name; call get_run for detail")
    return changed, "\n".join(lines)


def _is_terminal_change(changed: list[str]) -> bool:
    """Pending decisions and closures end the wait immediately; a stage
    advance is reported too, but only because the fingerprint moved."""
    return any(c.endswith(":pending") or c.endswith(":closed") for c in changed)


@guard
async def follow(
    deps: OperatorDeps, run_id: str | None = None, timeout_s: int = 60
) -> ChangeReport:
    """Wait until something changes, then report what.

    Waits on one run when run_id is given, otherwise on the whole fleet.
    Returns as soon as a run needs a decision or finishes. Report to the
    operator between waits; consecutive waits are capped.
    """
    deps.note_follow()
    timeout_s = _clamp(timeout_s)
    before = await deps.poller.snapshot()
    if run_id is not None and not any(r.run_id == run_id for r in before.runs):
        raise ToolError(
            f"{run_id!r} is not an open run, so there is nothing to wait for; call list_runs"
        )

    baseline = _projection(before, run_id)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    async with deps.poller.subscribe() as q:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return ChangeReport(
                    run_id=run_id, timed_out=True, detail=f"nothing changed in {timeout_s}s"
                )
            try:
                snap = await asyncio.wait_for(q.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return ChangeReport(
                    run_id=run_id, timed_out=True, detail=f"nothing changed in {timeout_s}s"
                )
            if _projection(snap, run_id) == baseline:
                continue
            changed, detail = _describe_change(before, snap, run_id)
            return ChangeReport(run_id=run_id, timed_out=False, changed=changed, detail=detail)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_follow.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/tools.py tests/test_operator_follow.py
git commit -m "feat(operator): follow, a run-scoped bounded wait with two brakes"
```

---

### Task 9: The three write verbs

**Files:**
- Modify: `src/sdlc/operator/tools.py` (append)
- Test: `tests/test_operator_writes.py`

**Interfaces:**
- Consumes: `transport.{resolve_key, submit, SubmitResult}`, `contract.{Reply, default_render}`, `ActorChannel` (Task 1), `sdlc.models.{IdeaBrief, PipelineConfig, GateOutcome, ProjectMode}`, `sdlc.cli.slug`, `OperatorDeps.starter`.
- Produces:

```python
class ReplyReceipt(BaseModel):
    run_id: str
    key: str
    confirmed: bool
    detail: str

async def start_run(deps, title: str, mode: ProjectMode,
                    description: str = "", repo: str | None = None) -> str
async def answer_question(deps, run_id: str, key: str, text: str) -> ReplyReceipt
async def decide_gate(deps, run_id: str, key: str, outcome: GateOutcome,
                      text: str = "") -> ReplyReceipt
```

`start_run` returns the workflow id it created. The `deps.poller._client_or_connect()` call used to obtain a handle mirrors `dashboard/api.py:_handle`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_operator_writes.py`:

```python
"""Write verbs: kind enforcement, derived rounds, receipts, actor identity."""

import pytest

from sdlc.channels.transport import SubmitResult
from sdlc.models import GateOutcome, ProjectMode
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError
from sdlc.pending import ClarifyPending, StageGatePending

GATE = StageGatePending(key="architecture#2", gate="architecture", round=2, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


class FakeHandle:
    def __init__(self, run_id, pending):
        self.id = run_id
        self._pending = list(pending)


class FakeClient:
    def __init__(self, handle):
        self._handle = handle

    def get_workflow_handle(self, run_id):
        return self._handle


class FakePoller:
    def __init__(self, handle):
        self._handle = handle

    async def _client_or_connect(self):
        return FakeClient(self._handle)


@pytest.fixture
def submitted():
    return []


@pytest.fixture
def deps(monkeypatch, submitted):
    handle = FakeHandle("feature-add-sso", [GATE, Q1])

    async def fake_resolve_key(h, key):
        for d in h._pending:
            if d.key == key:
                return d
        from sdlc.channels.transport import NoMatch

        raise NoMatch(f"no pending item with key '{key}' on this run")

    async def fake_submit(h, pending, reply, channel=None):
        call = channel.translate(pending, reply)
        submitted.append((h.id, pending.key, reply, call))
        return SubmitResult(confirmed=True, message=f"ok on {h.id}")

    monkeypatch.setattr(tools, "resolve_key", fake_resolve_key)
    monkeypatch.setattr(tools, "submit", fake_submit)
    started = []

    async def fake_starter(idea, cfg, wf_id):
        started.append((idea, cfg, wf_id))
        return wf_id

    d = OperatorDeps(poller=FakePoller(handle), board=None, starter=fake_starter, actor="chat:mika")
    d.started = started
    return d


@pytest.mark.asyncio
async def test_decide_gate_returns_a_confirmed_receipt(deps, submitted):
    got = await tools.decide_gate(deps, "feature-add-sso", "architecture#2", GateOutcome.APPROVE)
    assert got.confirmed is True
    assert got.run_id == "feature-add-sso"
    assert got.key == "architecture#2"


@pytest.mark.asyncio
async def test_decide_gate_never_types_the_round(deps, submitted):
    await tools.decide_gate(deps, "feature-add-sso", "architecture#2", GateOutcome.APPROVE)
    _, _, _, call = submitted[0]
    assert call.decision.round == 2  # from the pending item, not typed


@pytest.mark.asyncio
async def test_decide_gate_stamps_the_actor_as_reviewer(deps, submitted):
    await tools.decide_gate(
        deps, "feature-add-sso", "architecture#2", GateOutcome.REVISE, text="split the queue"
    )
    _, _, _, call = submitted[0]
    assert call.decision.reviewer == "chat:mika"
    assert call.decision.decided_by == "human"
    assert call.decision.guidance == "split the queue"


@pytest.mark.asyncio
async def test_decide_gate_refuses_a_question_key(deps):
    with pytest.raises(ToolError) as e:
        await tools.decide_gate(deps, "feature-add-sso", "Q1", GateOutcome.APPROVE)
    assert "answer_question" in e.value.message


@pytest.mark.asyncio
async def test_answer_question_refuses_a_gate_key(deps):
    with pytest.raises(ToolError) as e:
        await tools.answer_question(deps, "feature-add-sso", "architecture#2", "sure")
    assert "decide_gate" in e.value.message


@pytest.mark.asyncio
async def test_answer_question_sends_the_text(deps, submitted):
    got = await tools.answer_question(deps, "feature-add-sso", "Q1", "Okta")
    assert got.confirmed is True
    _, _, reply, call = submitted[0]
    assert call.signal == "answer_question"
    assert call.answer == "Okta"


@pytest.mark.asyncio
async def test_stale_key_is_a_tool_error_telling_the_model_to_re_read(deps):
    with pytest.raises(ToolError) as e:
        await tools.answer_question(deps, "feature-add-sso", "Q9", "x")
    assert "re-read" in e.value.message.lower()


@pytest.mark.asyncio
async def test_unconfirmed_is_reported_not_raised(deps, monkeypatch):
    async def unconfirmed(h, pending, reply, channel=None):
        return SubmitResult(confirmed=False, message="not confirmed: still pending")

    monkeypatch.setattr(tools, "submit", unconfirmed)
    got = await tools.decide_gate(deps, "feature-add-sso", "architecture#2", GateOutcome.APPROVE)
    assert got.confirmed is False
    assert "not confirmed" in got.detail


@pytest.mark.asyncio
async def test_start_run_builds_the_workflow_id_from_the_title(deps):
    run_id = await tools.start_run(
        deps, title="Add SSO", mode=ProjectMode.BROWNFIELD, repo="git@example.com:k.git"
    )
    assert run_id.startswith("feature-")
    idea, _, wf_id = deps.started[0]
    assert wf_id == run_id
    assert idea.repo_url == "git@example.com:k.git"
    assert idea.mode is ProjectMode.BROWNFIELD


@pytest.mark.asyncio
async def test_start_run_requires_a_repo_for_brownfield(deps):
    with pytest.raises(ToolError) as e:
        await tools.start_run(deps, title="Add SSO", mode=ProjectMode.BROWNFIELD)
    assert "repo" in e.value.message.lower()


@pytest.mark.asyncio
async def test_start_run_reports_a_duplicate_id_clearly(deps):
    async def already(idea, cfg, wf_id):
        raise RuntimeError("Workflow execution already started")

    deps.starter = already
    with pytest.raises(ToolError) as e:
        await tools.start_run(deps, title="Add SSO", mode=ProjectMode.GREENFIELD)
    assert "already" in e.value.message.lower()


@pytest.mark.asyncio
async def test_writes_reset_the_follow_streak(deps):
    deps.note_follow()
    await tools.answer_question(deps, "feature-add-sso", "Q1", "Okta")
    assert deps.follow_calls == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_operator_writes.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.operator.tools' has no attribute 'decide_gate'`

- [ ] **Step 3: Append the write verbs to `tools.py`**

Add to the imports (module-level names so tests can monkeypatch them):

```python
from ..channels.contract import ActorChannel, Reply, default_render
from ..channels.transport import resolve_key, submit
from ..cli import slug
from ..models import GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
```

Append:

```python
class ReplyReceipt(BaseModel):
    """The outcome of one reply, in the words transport already chose.

    confirmed=False is informational, never an error: the dominant cause is
    another surface winning the race, which is FR-302 working as designed
    (transport._message). Repeat detail to the operator verbatim.
    """

    run_id: str
    key: str
    confirmed: bool
    detail: str


async def _handle(deps: OperatorDeps, run_id: str):
    client = await deps.poller._client_or_connect()
    return client.get_workflow_handle(run_id)


async def _reply(
    deps: OperatorDeps, run_id: str, key: str, reply: Reply, want: str
) -> ReplyReceipt:
    handle = await _handle(deps, run_id)
    pending = await resolve_key(handle, key)
    kind = default_render(pending).reply_kind
    if kind != want:
        right = "answer_question" if kind == "text" else "decide_gate"
        raise ToolError(f"key {key!r} on {run_id} takes a {kind} reply; use {right}")
    result = await submit(handle, pending, reply, channel=ActorChannel(actor=deps.actor))
    return ReplyReceipt(run_id=run_id, key=key, confirmed=result.confirmed, detail=result.message)


@guard
async def answer_question(deps: OperatorDeps, run_id: str, key: str, text: str) -> ReplyReceipt:
    """Answer a clarification question the run is waiting on.

    key must come from get_run or inbox; do not invent one.
    """
    deps.note_other_tool()
    return await _reply(deps, run_id, key, Reply(text=text), want="text")


@guard
async def decide_gate(
    deps: OperatorDeps, run_id: str, key: str, outcome: GateOutcome, text: str = ""
) -> ReplyReceipt:
    """Approve, reject, or request revision on a gate the run is waiting on.

    key must come from get_run or inbox. The gate round is taken from the
    pending item -- never supply one. With outcome=revise, text is the
    guidance the pipeline loops back with.
    """
    deps.note_other_tool()
    return await _reply(deps, run_id, key, Reply(outcome=outcome, text=text or None), want="gate")


@guard
async def start_run(
    deps: OperatorDeps,
    title: str,
    mode: ProjectMode,
    description: str = "",
    repo: str | None = None,
) -> str:
    """Start a new feature run. Returns the run id.

    Brownfield runs need a repo url; greenfield runs must not be given one.
    """
    deps.note_other_tool()
    if mode is ProjectMode.BROWNFIELD and not repo:
        raise ToolError(
            "a brownfield run needs repo set to the repository url; ask the "
            "operator which repository this is for"
        )
    idea = IdeaBrief(title=title, description=description, mode=mode, repo_url=repo)
    wf_id = f"feature-{slug(title)}"
    try:
        await deps.starter(idea, PipelineConfig(), wf_id)
    except Exception as e:  # noqa: BLE001 -- narrowed into ToolError
        if "already started" in str(e).lower():
            raise ToolError(
                f"a run with id {wf_id!r} already exists; call get_run on it, "
                f"or start this one under a different title"
            ) from None
        raise
    return wf_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_operator_writes.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/operator/tools.py tests/test_operator_writes.py
git commit -m "feat(operator): approval-bound write verbs with derived rounds"
```

---

### Task 10: The agent, the assets, and the layering test

**Files:**
- Create: `src/sdlc/operator/agent.py`
- Create: `interfaces/chat/agent.yaml`
- Create: `interfaces/chat/instructions.md`
- Test: `tests/test_operator_agent.py`
- Test: `tests/test_operator_layering.py`

**Interfaces:**
- Consumes: everything from Tasks 2–9; `pydantic_ai.{Agent, RunContext}`, `pydantic_ai.toolsets.FunctionToolset`, `pydantic_ai.ui.create_web_app`.
- Produces:
  - `READ_TOOLS: tuple` and `WRITE_TOOLS: tuple` — the verb functions, split by whether they need approval.
  - `load_chat_config(root: Path | None = None) -> ChatConfig` with fields `model: str`, `max_tokens: int`, `instructions: str`.
  - `build_toolset() -> FunctionToolset[OperatorDeps]`
  - `build_agent(cfg: ChatConfig | None = None) -> Agent[OperatorDeps, str]`
  - `build_chat_app(deps: OperatorDeps, cfg: ChatConfig | None = None)` — the Starlette app, wrapped so `deps.reset_request_state()` runs per HTTP request.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_operator_layering.py`:

```python
"""Spec D3: the tool layer must stay framework-free so E-11 can reuse it."""

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "sdlc" / "operator"
FORBIDDEN = ("pydantic_ai", "fastapi", "starlette")


def imported_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_agent_py_may_know_about_frameworks():
    for path in SRC.glob("*.py"):
        if path.name == "agent.py":
            continue
        offenders = imported_roots(path) & set(FORBIDDEN)
        assert not offenders, f"{path.name} imports {offenders}"


def test_agent_py_is_the_one_that_does():
    assert "pydantic_ai" in imported_roots(SRC / "agent.py")
```

Create `tests/test_operator_agent.py`:

```python
"""Toolset shape, approval flags, asset loading, and per-request reset."""

import asyncio

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.operator import agent as chat_agent
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps


def test_twelve_tools_nine_read_three_write():
    assert len(chat_agent.READ_TOOLS) == 9
    assert len(chat_agent.WRITE_TOOLS) == 3
    names = {f.__name__ for f in chat_agent.READ_TOOLS + chat_agent.WRITE_TOOLS}
    assert names == {
        "list_runs",
        "get_run",
        "follow",
        "inbox",
        "list_projects",
        "get_project",
        "list_tasks",
        "project_events",
        "read_artifact",
        "start_run",
        "answer_question",
        "decide_gate",
    }


def test_only_the_writes_require_approval():
    ts = chat_agent.build_toolset()
    approval = {name: t.requires_approval for name, t in ts.tools.items()}
    assert approval["decide_gate"] is True
    assert approval["answer_question"] is True
    assert approval["start_run"] is True
    assert approval["list_runs"] is False
    assert approval["follow"] is False


def test_binding_hides_deps_from_the_model_schema():
    ts = chat_agent.build_toolset()
    assert "deps" not in ts.tools["get_run"].function_schema.json_schema["properties"]
    assert "run_id" in ts.tools["get_run"].function_schema.json_schema["properties"]


def test_chat_config_loads_the_versioned_assets():
    cfg = chat_agent.load_chat_config()
    assert cfg.model
    assert cfg.instructions.strip()
    assert "key" in cfg.instructions.lower()


def test_missing_asset_directory_is_a_clear_error(tmp_path):
    with pytest.raises(chat_agent.ChatConfigError) as e:
        chat_agent.load_chat_config(tmp_path)
    assert "agent.yaml" in str(e.value)


def test_empty_instructions_are_refused(tmp_path):
    (tmp_path / "agent.yaml").write_text("model: anthropic:claude-sonnet-4-6\n", encoding="utf-8")
    (tmp_path / "instructions.md").write_text("   \n", encoding="utf-8")
    with pytest.raises(chat_agent.ChatConfigError) as e:
        chat_agent.load_chat_config(tmp_path)
    assert "empty" in str(e.value)


@pytest.mark.asyncio
async def test_the_orientation_line_reaches_the_prompt(monkeypatch):
    class FakePoller:
        async def snapshot(self):
            from datetime import datetime, timezone

            from sdlc.dashboard.fleet import FleetSnapshot
            from sdlc.models import RunState

            at = datetime(2026, 8, 20, tzinfo=timezone.utc)
            return FleetSnapshot(
                at=at,
                total_open_runs=1,
                runs=[
                    RunState(
                        run_id="r1", title="t", mode="greenfield", status="running", started_at=at
                    )
                ],
            )

    deps = OperatorDeps(poller=FakePoller(), board=None, starter=None)
    a = chat_agent.build_agent()
    with a.override(model=TestModel()):
        result = await a.run("hello", deps=deps)
    assert result.output is not None


@pytest.mark.asyncio
async def test_each_http_request_clears_the_follow_streak():
    deps = OperatorDeps(poller=None, board=None, starter=None)
    deps.note_follow()
    app = chat_agent._ResetPerRequest(_noop_asgi, deps)
    await app({"type": "http"}, _recv, _send)
    assert deps.follow_calls == 0


async def _noop_asgi(scope, receive, send):
    return None


async def _recv():
    return {"type": "http.request"}


async def _send(message):
    return None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_operator_agent.py tests/test_operator_layering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.operator.agent'`

- [ ] **Step 3: Write the assets**

Create `interfaces/chat/agent.yaml`:

```yaml
# The operator chat agent (E-86). Not a registry role: agents/loader.py's
# KNOWN_ROLES is closed by design, and ADR-6 family inequality does not apply
# to a surface that decorrelates from nothing. See spec D5.
model: anthropic:claude-sonnet-4-6
max_tokens: 64000
```

Create `interfaces/chat/instructions.md`:

```markdown
You are the operator console for an agentic SDLC factory. The person you are
talking to is a human running long-lived Temporal workflows that build
software. Your job is to let them start runs, check on them, and wait for
them without leaving the conversation.

## How to work

- Answer from the orientation summary when it already contains the answer.
  Call a tool when it does not.
- Report what the tools return. Do not soften a failure, invent a stage that
  is not listed, or estimate a cost the tools reported as unknown.
- Be brief. The operator is scanning, not reading.

## Keys

Every reply is addressed to a `key`. Keys come only from `get_run` or
`inbox`. Never construct, guess, or reuse a key from earlier in the
conversation without re-reading it — a key that has been answered is gone,
and using a stale one is an error you will be told to recover from by
re-reading.

Never mention a gate round number in a tool call. The round is taken from
the pending item; supplying one is impossible and asking the operator for one
is a mistake.

## Writing

`start_run`, `answer_question`, and `decide_gate` change what the factory is
doing, and each one asks the operator to confirm before it runs. State plainly
what you are about to do and let the confirmation happen. If the operator
declines, say that nothing was sent and stop — do not try a different route to
the same action.

When a receipt comes back with `confirmed` false, repeat its `detail` to the
operator as written. It usually means another surface decided first, which is
normal and not a failure.

## Waiting

`follow` waits for something to happen. Use it when the operator asks you to
watch a run. It returns as soon as a run needs a decision or finishes. Report
what changed between waits; do not wait repeatedly in silence.

## Artifacts

`read_artifact` returns a fragment, not a file. Only read keys that
`get_project` listed. When `truncated` is true, either page with
`next_offset` or tell the operator what you have. Summarize; quote only the
lines that matter. Never paste an artifact body into the conversation whole.
```

- [ ] **Step 4: Write `agent.py`**

```python
"""The chat surface's Pydantic AI agent (E-86).

The ONLY module in sdlc/operator that imports pydantic_ai. tools.py stays
framework-free so E-11's MCP server can import the same functions; this file
is the chat-shaped adapter, and mcp.py will be its sibling.

Two things here are load-bearing and non-obvious:

* _bind rewrites each verb's signature to swap `deps` for a RunContext.
  Pydantic AI derives a tool's JSON schema from the signature, so the
  rewrite is what keeps `deps` out of the schema the model sees.
* _ResetPerRequest zeroes the follow streak per HTTP request. create_web_app
  holds ONE deps object for the life of the mount, so without this the brake
  would be per-process rather than per-conversation-turn.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.ui import create_web_app

from . import render, tools
from .deps import OperatorDeps

ASSET_DIR = Path(__file__).resolve().parents[3] / "interfaces" / "chat"

READ_TOOLS = (
    tools.list_runs,
    tools.get_run,
    tools.follow,
    tools.inbox,
    tools.list_projects,
    tools.get_project,
    tools.list_tasks,
    tools.project_events,
    tools.read_artifact,
)
WRITE_TOOLS = (tools.start_run, tools.answer_question, tools.decide_gate)


class ChatConfigError(Exception):
    """The chat assets are missing or unusable. Never fatal to the dashboard;
    main.py catches this and skips the mount."""


@dataclass
class ChatConfig:
    model: str
    max_tokens: int
    instructions: str


def load_chat_config(root: Path | None = None) -> ChatConfig:
    root = Path(root) if root is not None else ASSET_DIR
    cfg_file = root / "agent.yaml"
    if not cfg_file.is_file():
        raise ChatConfigError(
            f"missing {cfg_file}: the chat surface needs an agent.yaml naming its model"
        )
    data = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
    model = data.get("model")
    if not model:
        raise ChatConfigError(f"{cfg_file} declares no model")
    prompt_file = root / "instructions.md"
    if not prompt_file.is_file():
        raise ChatConfigError(f"missing {prompt_file}")
    instructions = prompt_file.read_text(encoding="utf-8")
    if not instructions.strip():
        raise ChatConfigError(
            f"{prompt_file} is empty -- an empty system prompt is a boot-time "
            f"bug, not a runtime surprise"
        )
    return ChatConfig(
        model=model, max_tokens=int(data.get("max_tokens", 64000)), instructions=instructions
    )


def _bind(fn):
    """Adapt `fn(deps, ...)` into `tool(ctx, ...)` without leaking deps.

    __signature__ and __annotations__ are both rewritten because Pydantic AI
    reads the signature to build the schema and the annotations to resolve
    types.
    """
    sig = inspect.signature(fn)
    rest = [p for name, p in sig.parameters.items() if name != "deps"]

    async def tool(ctx: RunContext[OperatorDeps], **kwargs):
        return await fn(ctx.deps, **kwargs)

    ctx_param = inspect.Parameter(
        "ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=RunContext[OperatorDeps]
    )
    tool.__name__ = fn.__name__
    tool.__doc__ = fn.__doc__
    tool.__signature__ = sig.replace(parameters=[ctx_param, *rest])
    tool.__annotations__ = {p.name: p.annotation for p in rest}
    tool.__annotations__["ctx"] = RunContext[OperatorDeps]
    tool.__annotations__["return"] = sig.return_annotation
    return tool


def build_toolset() -> FunctionToolset:
    ts: FunctionToolset = FunctionToolset()
    for fn in READ_TOOLS:
        ts.add_function(_bind(fn), name=fn.__name__)
    for fn in WRITE_TOOLS:
        # The model proposes; the operator disposes (spec D4).
        ts.add_function(_bind(fn), name=fn.__name__, requires_approval=True)
    return ts


def build_agent(cfg: ChatConfig | None = None) -> Agent:
    cfg = cfg or load_chat_config()
    agent: Agent = Agent(
        cfg.model,
        deps_type=OperatorDeps,
        toolsets=[build_toolset()],
        model_settings=ModelSettings(max_tokens=cfg.max_tokens),
        instructions=cfg.instructions,
    )

    @agent.instructions
    async def _orientation(ctx: RunContext[OperatorDeps]) -> str:
        """One line per open run, recomputed each turn (spec 5.4)."""
        if ctx.deps is None or ctx.deps.poller is None:
            return ""
        try:
            snap = await ctx.deps.poller.snapshot()
        except Exception:  # noqa: BLE001 -- orientation is a nicety
            return "fleet state unavailable right now; use the tools"
        return "Current fleet:\n" + render.orientation(snap)

    return agent


class _ResetPerRequest:
    """ASGI wrapper clearing per-request tool state before the app runs."""

    def __init__(self, app, deps: OperatorDeps) -> None:
        self.app = app
        self.deps = deps

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            self.deps.reset_request_state()
        return await self.app(scope, receive, send)


def build_chat_app(deps: OperatorDeps, cfg: ChatConfig | None = None):
    """The mountable Starlette app: chat UI at /, API under /api."""
    cfg = cfg or load_chat_config()
    app = create_web_app(build_agent(cfg), deps=deps)
    return _ResetPerRequest(app, deps)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_operator_agent.py tests/test_operator_layering.py -v`
Expected: PASS

If `test_only_the_writes_require_approval` or `test_binding_hides_deps_from_the_model_schema` fails on attribute names (`ts.tools`, `.requires_approval`, `.function_schema`), inspect the installed API rather than guessing:

```bash
python -c "from pydantic_ai.toolsets import FunctionToolset; ts=FunctionToolset(); print([a for a in dir(ts) if not a.startswith('__')])"
```

Adjust the **test's** accessor to the real attribute. Do not weaken the assertion — the property being checked (writes are approval-gated, `deps` is absent from the schema) is the point of the task.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/operator/agent.py interfaces/chat tests/test_operator_agent.py tests/test_operator_layering.py
git commit -m "feat(operator): the chat agent, its versioned assets, and the layering guard"
```

---

### Task 11: Mount behind the flag, and the one Temporal proof

**Files:**
- Modify: `interfaces/dashboard/api/main.py`
- Test: `tests/test_chat_mount.py`
- Test: `tests/test_operator_e2e.py`
- Modify: `ROADMAP.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `build_chat_app`, `ChatConfigError`, `OperatorDeps`, the existing `poller` and `_start` in `main.py`.
- Produces: `interfaces.dashboard.api.main.mount_chat(app, poller) -> bool` — returns whether the mount happened, so it is testable without importing the module for its side effects.

- [ ] **Step 1: Write the failing test**

Create `tests/test_chat_mount.py`:

```python
"""The chat mount is opt-in and can never take the dashboard down."""

import pytest
from fastapi import FastAPI

from interfaces.dashboard.api import main


class FakePoller:
    async def snapshot(self):
        raise AssertionError("mounting must not query Temporal")


def test_unset_flag_means_no_mount(monkeypatch):
    monkeypatch.delenv("SDLC_CHAT_ENABLED", raising=False)
    app = FastAPI()
    assert main.mount_chat(app, FakePoller()) is False
    assert not any(getattr(r, "path", "") == "/chat" for r in app.routes)


def test_flag_set_to_anything_else_means_no_mount(monkeypatch):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "yes")
    assert main.mount_chat(FastAPI(), FakePoller()) is False


def test_flag_on_mounts_the_app(monkeypatch):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")
    app = FastAPI()
    assert main.mount_chat(app, FakePoller()) is True
    assert any(getattr(r, "path", "") == "/chat" for r in app.routes)


def test_a_broken_chat_config_skips_the_mount_instead_of_raising(monkeypatch, caplog):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")

    def boom(*a, **kw):
        from sdlc.operator.agent import ChatConfigError

        raise ChatConfigError("missing agent.yaml")

    monkeypatch.setattr(main, "build_chat_app", boom)
    app = FastAPI()
    assert main.mount_chat(app, FakePoller()) is False
    assert not any(getattr(r, "path", "") == "/chat" for r in app.routes)


def test_any_unexpected_error_also_skips_the_mount(monkeypatch):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")

    def boom(*a, **kw):
        raise RuntimeError("no api key")

    monkeypatch.setattr(main, "build_chat_app", boom)
    assert main.mount_chat(FastAPI(), FakePoller()) is False


def test_mounting_configures_logfire(monkeypatch):
    """Spec 12: the chat surface's traces come from instrument_pydantic_ai(),
    which lives inside configure(). A no-op without LOGFIRE_TOKEN."""
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")
    called = []
    monkeypatch.setattr(main, "configure_logfire", lambda: called.append(True) or False)
    main.mount_chat(FastAPI(), FakePoller())
    assert called == [True]
```

Create `tests/test_operator_e2e.py`, modelled directly on `tests/test_dashboard_e2e.py` — read that file first, it explains why `start_local` and not `start_time_skipping`:

```python
"""E-86 e2e: the verbs answer against a real workflow through a real poller.

The part no fake can prove for this module is that OperatorDeps' collaborators
are the real ones -- FleetPoller fanning out over a live client, and _handle
resolving a real workflow handle. Signal TRANSLATION is pinned by
tests/test_operator_writes.py and by transport's own suite; driving
FeatureWorkflow to a pending gate would need the full activity fake set, which
is test_e2e_greenfield.py's job and not this test's.

Marked temporal: each such test spawns its own dev-server subprocess
(pyproject's addopts excludes them from the default run).
"""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.dashboard.fleet import FleetPoller
from sdlc.models import IdeaBrief, PipelineConfig, ProjectMode
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.workflows.feature import FeatureWorkflow

pytestmark = pytest.mark.temporal


@pytest.mark.asyncio
async def test_verbs_answer_against_a_live_run():
    from temporalio.contrib.pydantic import pydantic_data_converter

    async with await WorkflowEnvironment.start_local(data_converter=pydantic_data_converter) as env:
        async with Worker(
            env.client, task_queue="chat-e2e", workflows=[FeatureWorkflow], activities=[]
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[
                    IdeaBrief(title="Add SSO", description="d", mode=ProjectMode.GREENFIELD),
                    PipelineConfig(),
                    None,
                ],
                id="feature-add-sso",
                task_queue="chat-e2e",
            )
            poller = FleetPoller(lambda: env.client)
            deps = OperatorDeps(poller=poller, board=None, starter=None, actor="chat:test")
            try:
                listed = await tools.list_runs(deps)
                assert "feature-add-sso" in listed

                detail = await tools.get_run(deps, "feature-add-sso")
                assert "Add SSO" in detail
                assert "intake" in detail
                # None must not become 0.00: nothing has been priced yet.
                assert "cost unknown" in detail

                # _handle reaches a real workflow handle through the poller's
                # client -- the path every write verb takes before signalling.
                live = await tools._handle(deps, "feature-add-sso")
                assert live.id == "feature-add-sso"

                # Nothing is pending on a run parked at intake, so a scoped
                # wait must time out rather than report a phantom change.
                report = await tools.follow(deps, run_id="feature-add-sso", timeout_s=5)
                assert report.timed_out is True
            finally:
                await poller.aclose()
                await handle.cancel()
```

**Deviation from spec §13, flagged:** the spec says this test proves `decide_gate` signals a workflow. Reaching a pending gate requires the full activity fake set, and `test_dashboard_e2e.py` documents why that belongs in the e2e suite rather than here. This test proves the collaborator wiring instead — the real gap a fake leaves — and the signal translation stays pinned by Task 9's unit tests over `transport.submit`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_mount.py -v`
Expected: FAIL — `AttributeError: module has no attribute 'mount_chat'`

- [ ] **Step 3: Add the mount to `main.py`**

Append to `interfaces/dashboard/api/main.py`, before `__all__`:

```python
from sdlc.board.store import BoardStore
from sdlc.observability.logfire_setup import configure as configure_logfire
from sdlc.operator.agent import ChatConfigError, build_chat_app
from sdlc.operator.deps import OperatorDeps

log = logging.getLogger(__name__)


def mount_chat(target, fleet_poller) -> bool:
    """Mount the operator chat surface at /chat when enabled (E-86).

    Opt-in and fail-soft, both deliberately. The dashboard is the surface
    operators depend on; it must never fail to boot because the chat agent
    has no API key, no assets, or a bad model id. Returns whether it mounted
    so the caller (and the tests) can tell.
    """
    if os.environ.get("SDLC_CHAT_ENABLED") != "1":
        return False
    try:
        # instrument_pydantic_ai() lives inside configure(); calling it here
        # is what gives the chat surface per-conversation traces beside the
        # pipeline's (spec 12). It is a no-op without a Logfire token.
        configure_logfire()
        deps = OperatorDeps(
            poller=fleet_poller, board=BoardStore(), starter=_start, actor="chat:local"
        )
        target.mount("/chat", build_chat_app(deps))
    except ChatConfigError as e:
        log.warning("chat surface not mounted: %s", e)
        return False
    except Exception as e:  # noqa: BLE001 -- never fatal to the dashboard
        log.warning("chat surface not mounted: %s: %s", type(e).__name__, e)
        return False
    log.info("chat surface mounted at /chat")
    return True


mount_chat(app, poller)
```

Add `import logging` to the imports at the top of the file.

- [ ] **Step 4: Run the mount tests, then the whole fast suite**

Run: `pytest tests/test_chat_mount.py -v`
Expected: PASS (5 tests)

Run: `pytest -q`
Expected: PASS — the full fast suite, unchanged from before this branch except for the new tests. Any pre-existing failure here is not yours; confirm it fails on `main` before touching it.

- [ ] **Step 5: Document the flag**

Append to `.env.example`:

```
# Operator chat surface (E-86). Set to 1 to mount the Pydantic AI chat agent
# at /chat on the dashboard app. Off by default: it spends tokens and lets a
# model propose gate decisions. Needs the model provider key its
# interfaces/chat/agent.yaml names.
SDLC_CHAT_ENABLED=0
```

- [ ] **Step 6: Update the roadmap**

In `ROADMAP.md` §9.2, amend the E-11 line to end with:

```
*Re-exports `sdlc/operator/tools.py` (E-86) rather than reimplementing the verbs.*
```

And add after it:

```
- [x] **E-86** Operator chat surface — a Pydantic AI agent over the same tool layer, served by `pydantic_ai.ui.create_web_app` and mounted at `/chat` beside the board and dashboard routers. Twelve verbs in `src/sdlc/operator/` (nine reads, three approval-gated writes), a run-scoped bounded `follow`, and a 32 KB paged `read_artifact`. Shipped behind `SDLC_CHAT_ENABLED`, default off. Closes the chat half of US-7; FR-602 stays open until E-11's MCP server ships. Spec `docs/superpowers/specs/2026-08-20-operator-chat-surface-design.md`, plan `docs/superpowers/plans/2026-08-20-operator-chat-surface.md`.
```

In §2 FR-600, amend **FR-602**'s line to note the tool layer now exists and only the MCP adapter is missing.

In §2 FR-700, append to **FR-703**'s egress ledger (spec §14):

```
*2026-08-20 (E-86):* the operator chat surface adds two declared egresses, both off unless `SDLC_CHAT_ENABLED=1` — the chat agent's model provider, and a one-time `cdn.jsdelivr.net` fetch of the `@pydantic/ai-chat-ui` HTML, cached on disk thereafter. `create_web_app(html_source=...)` pointing at a vendored file removes the CDN dependency for an air-gapped deployment; it is not vendored today.
```

- [ ] **Step 7: Commit**

```bash
git add interfaces/dashboard/api/main.py tests/test_chat_mount.py tests/test_operator_e2e.py .env.example ROADMAP.md
git commit -m "feat(chat): mount the operator chat surface behind SDLC_CHAT_ENABLED"
```

---

## Verification before calling this done

- [ ] `pytest -q` passes.
- [ ] `pytest -m temporal tests/test_operator_e2e.py -v` passes. It spawns its own dev-server subprocess; a skip is not a pass.
- [ ] With `SDLC_CHAT_ENABLED` unset, `uvicorn interfaces.dashboard.api.main:app --host 127.0.0.1 --port 8500` serves the dashboard exactly as before and `/chat` 404s.
- [ ] With `SDLC_CHAT_ENABLED=1` and a provider key set, `/chat` serves the UI, "what's running?" answers without a tool call, and approving a gate shows a confirmation card carrying the workflow's own pending text before anything is signalled.
