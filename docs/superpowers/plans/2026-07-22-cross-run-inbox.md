# E-8 Cross-Run Inbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `sdlc inbox` CLI verb that lists every pending decision (clarify question, stage gate, task escalation, merge gate) across every currently-running `FeatureWorkflow` run, so an operator no longer has to already know a run's id to see what it's waiting on.

**Architecture:** A new `src/sdlc/channels/inbox.py` module is `resolve`'s sibling from E-6/E-7: it discovers open run ids via a server-side Temporal visibility filter (`WorkflowType='FeatureWorkflow' AND ExecutionStatus='Running'`), then concurrently fetches each run's `pending_decisions()` through the same query/validate path `transport.py` already uses for single-run resolution (promoted from private `_fetch` to public `fetch_pending`). A per-run failure is captured, not raised, so one bad run never hides everything else. The CLI verb is a thin `render_inbox(await fetch_inbox(client))` print, following the existing `status`/decision-verb dispatch pattern in `cli.py`.

**Tech Stack:** Python, Pydantic, temporalio (`Client.list_workflows`, `Client.get_workflow_handle`), pytest + pytest-asyncio.

## Global Constraints

- All CLI-printed output must be ASCII only (Windows console cannot print non-ASCII — existing constraint from E-7).
- This increment is read-only: no acting on an inbox item directly, no push delivery/notifications (E-9), no dashboard or MCP surface (E-10/E-11). Acting still goes through the existing `--id`-scoped `approve`/`reject`/`revise`/`answer` verbs.
- Closed (completed/terminated/timed-out) runs are excluded by the visibility query itself, not filtered client-side, and are out of scope — a closed run has nothing pending by definition.
- A single run's query failure must never abort the whole `inbox` command; it is captured and listed separately.
- No concurrency cap on the per-run fanout (fleet sizes in scope are small; do not add tuning for a problem that doesn't exist yet).

---

### Task 1: Promote `transport._fetch` to public `fetch_pending`

**Files:**
- Modify: `src/sdlc/channels/transport.py:129-160` (rename `_fetch` -> `fetch_pending`, update its two call sites)
- Test: `tests/test_channel_transport.py` (no new test — this is a pure rename; the existing `resolve`/`submit` tests already exercise the renamed function indirectly)

**Interfaces:**
- Consumes: nothing new.
- Produces: `fetch_pending(handle) -> list[PendingDecision]` (previously private `_fetch`), importable as `from sdlc.channels.transport import fetch_pending`. Task 3 depends on this name.

This is a no-behavior-change refactor (rename only), done first so later tasks import the final public name rather than a name that changes underneath them.

- [ ] **Step 1: Rename the function and its two call sites**

In `src/sdlc/channels/transport.py`, change:

```python
async def _fetch(handle) -> list[PendingDecision]:
    """Query by name and validate the discriminated union ourselves.

    Deliberately not `result_type=list[PendingDecision]`: TypeAdapter round-
    trips the Annotated union verifiably without a live server, so the
    behavior is pinned by unit tests rather than discovered in staging.
    """
    raw = await handle.query(PENDING_QUERY)
    return _PENDING_LIST.validate_python(raw)
```

to:

```python
async def fetch_pending(handle) -> list[PendingDecision]:
    """Query by name and validate the discriminated union ourselves.

    Deliberately not `result_type=list[PendingDecision]`: TypeAdapter round-
    trips the Annotated union verifiably without a live server, so the
    behavior is pinned by unit tests rather than discovered in staging.

    Public (not `_fetch`): E-8's cross-run inbox reuses this exact
    query/validate path across many handles instead of one.
    """
    raw = await handle.query(PENDING_QUERY)
    return _PENDING_LIST.validate_python(raw)
```

Then update the two call sites in the same file:

```python
async def resolve(handle, selector: Selector,
                  channel: Channel | None = None) -> PendingDecision:
    """Fetch what is pending and narrow it to the one item meant."""
    return match(await fetch_pending(handle), selector, channel)
```

```python
async def submit(handle, pending: PendingDecision, reply: Reply,
                 channel: Channel | None = None) -> SubmitResult:
    """Translate a reply to its signal, send it, and verify it landed."""
    ch = channel or ReferenceChannel()
    call = ch.translate(pending, reply)

    if call.signal == "answer_question":
        await handle.signal(call.signal, args=[call.question_id, call.answer])
    else:
        await handle.signal(call.signal, call.decision)

    still = await fetch_pending(handle)
    confirmed = pending.key not in {d.key for d in still}
    return SubmitResult(
        confirmed=confirmed,
        message=_message(handle.id, pending, reply, confirmed))
```

- [ ] **Step 2: Verify no other reference to the old private name survives**

Run: `grep -rn "_fetch\b" src/sdlc tests`
Expected: no output referencing a bare `_fetch(` call (only `fetch_pending` remains).

- [ ] **Step 3: Run the existing transport test suite to confirm no regression**

Run: `python -m pytest tests/test_channel_transport.py -v`
Expected: all tests pass (same count as before the rename — this is a pure refactor).

- [ ] **Step 4: Commit**

```bash
git add src/sdlc/channels/transport.py
git commit -m "refactor(channels): promote transport._fetch to public fetch_pending

E-8's cross-run inbox reuses this exact query/validate path across many
handles instead of one; renamed ahead of that so it lands with its final
public name."
```

---

### Task 2: `channels/inbox.py` data models and `render_inbox`

**Files:**
- Create: `src/sdlc/channels/inbox.py`
- Test: `tests/test_channel_inbox.py`

**Interfaces:**
- Consumes: `PendingDecision` from `sdlc.pending`; `describe` from `sdlc.channels.transport` (existing, used unchanged for per-item lines).
- Produces: `RunInbox`, `InboxError`, `Inbox` (pydantic models); `render_inbox(inbox: Inbox) -> str`. Task 3 populates `Inbox` instances; Task 4's CLI verb calls `render_inbox`.

This task builds the pure, dependency-free half first (models + rendering), fully TDD'd with hand-built `Inbox` values — no async, no Temporal, no stub client yet.

- [ ] **Step 1: Write the failing tests for `render_inbox`**

Create `tests/test_channel_inbox.py`:

```python
from __future__ import annotations

from sdlc.channels.inbox import Inbox, InboxError, RunInbox, render_inbox
from sdlc.pending import ClarifyPending, MergeGatePending, StageGatePending

ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1,
                        spec_summary="s")
MERGE = MergeGatePending(key="merge#2", gate="merge", round=2)
Q1 = ClarifyPending(key="Q1", question="Use OIDC or SAML?",
                    why_it_matters="auth")


def test_render_inbox_reports_no_open_runs():
    assert render_inbox(Inbox(total_open_runs=0)) == "no open runs"


def test_render_inbox_reports_nothing_pending_plural():
    assert render_inbox(Inbox(total_open_runs=3)) == \
        "nothing pending across 3 open runs"


def test_render_inbox_reports_nothing_pending_singular():
    assert render_inbox(Inbox(total_open_runs=1)) == \
        "nothing pending across 1 open run"


def test_render_inbox_lists_runs_grouped_with_pending_items():
    inbox = Inbox(total_open_runs=2, runs=[
        RunInbox(run_id="feature-add-sso", pending=[ARCH]),
        RunInbox(run_id="feature-fix-bug", pending=[Q1, MERGE]),
    ])
    text = render_inbox(inbox)
    assert text == (
        "feature-add-sso:\n"
        "  architecture (round 1)\n"
        "feature-fix-bug:\n"
        "  Q1: Use OIDC or SAML?\n"
        "  merge (round 2)"
    )


def test_render_inbox_appends_error_block_after_a_blank_line():
    inbox = Inbox(total_open_runs=2, runs=[
        RunInbox(run_id="feature-add-sso", pending=[ARCH]),
    ], errors=[
        InboxError(run_id="feature-stale-run", error="workflow not found"),
    ])
    text = render_inbox(inbox)
    assert text == (
        "feature-add-sso:\n"
        "  architecture (round 1)\n"
        "\n"
        "1 run could not be queried:\n"
        "  feature-stale-run: workflow not found"
    )


def test_render_inbox_pluralizes_the_error_count():
    inbox = Inbox(total_open_runs=2, errors=[
        InboxError(run_id="a", error="e1"),
        InboxError(run_id="b", error="e2"),
    ])
    text = render_inbox(inbox)
    assert text == (
        "2 runs could not be queried:\n"
        "  a: e1\n"
        "  b: e2"
    )


def test_render_inbox_shows_only_errors_when_nothing_confirmed_pending():
    """No 'nothing pending' line when some runs are in an unknown state --
    we genuinely don't know whether the errored runs had pending items."""
    inbox = Inbox(total_open_runs=1, errors=[
        InboxError(run_id="a", error="e1"),
    ])
    assert "nothing pending" not in render_inbox(inbox)


def test_render_inbox_output_is_ascii():
    inbox = Inbox(total_open_runs=1, runs=[
        RunInbox(run_id="r", pending=[Q1]),
    ])
    render_inbox(inbox).encode("ascii")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_channel_inbox.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.channels.inbox'`

- [ ] **Step 3: Create `src/sdlc/channels/inbox.py` with the models and `render_inbox`**

```python
"""Cross-run inbox (E-8): list every pending decision across every open
FeatureWorkflow run. resolve()'s sibling -- the same query/validate path
(``transport.fetch_pending``) applied to many handles instead of one the
caller already named.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..pending import PendingDecision
from .transport import describe


class RunInbox(BaseModel):
    """One open run with at least one pending decision."""
    run_id: str
    pending: list[PendingDecision] = Field(default_factory=list)


class InboxError(BaseModel):
    """An open run whose pending_decisions() query raised."""
    run_id: str
    error: str


class Inbox(BaseModel):
    """Result of fetching pending decisions across every open run.

    ``total_open_runs`` is tracked separately from ``runs`` because a run
    with nothing pending is dropped rather than listed -- without this
    count, "no runs listed" and "checked 3 runs, none had anything pending"
    would be indistinguishable.
    """
    total_open_runs: int = 0
    runs: list[RunInbox] = Field(default_factory=list)
    errors: list[InboxError] = Field(default_factory=list)


def render_inbox(inbox: Inbox) -> str:
    """ASCII-only text for the CLI. See tests/test_channel_inbox.py for the
    exact shape of every branch."""
    if inbox.total_open_runs == 0:
        return "no open runs"

    if not inbox.runs and not inbox.errors:
        noun = "run" if inbox.total_open_runs == 1 else "runs"
        return f"nothing pending across {inbox.total_open_runs} open {noun}"

    lines: list[str] = []
    for r in inbox.runs:
        lines.append(f"{r.run_id}:")
        lines += [f"  {describe(d)}" for d in r.pending]

    if inbox.errors:
        if lines:
            lines.append("")
        noun = "run" if len(inbox.errors) == 1 else "runs"
        lines.append(f"{len(inbox.errors)} {noun} could not be queried:")
        lines += [f"  {e.run_id}: {e.error}" for e in inbox.errors]

    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_channel_inbox.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/channels/inbox.py tests/test_channel_inbox.py
git commit -m "feat(channels): inbox data models and rendering (E-8)

RunInbox/InboxError/Inbox plus render_inbox, TDD'd against hand-built
Inbox values. Pure and dependency-free -- no Temporal client involved yet;
fetch_inbox (populating these from a live client) is the next task."
```

---

### Task 3: `list_open_run_ids` and `fetch_inbox`

**Files:**
- Modify: `src/sdlc/channels/inbox.py` (add the two async functions)
- Test: `tests/test_channel_inbox.py` (extend)

**Interfaces:**
- Consumes: `fetch_pending(handle) -> list[PendingDecision]` from `sdlc.channels.transport` (Task 1); `Inbox`/`RunInbox`/`InboxError` from Task 2.
- Produces: `list_open_run_ids(client) -> list[str]`; `fetch_inbox(client) -> Inbox`. Task 4's CLI verb calls `fetch_inbox`.

`client` here is duck-typed deliberately (not annotated as `temporalio.client.Client`): it only needs an async-iterable `list_workflows(query)` and a `get_workflow_handle(run_id)`, exactly like `transport.py` treats `handle` as duck-typed rather than importing `FeatureWorkflow`. This keeps the module workflow- and client-agnostic and lets tests use a plain stub with no `temporalio` server involved.

- [ ] **Step 1: Write the failing tests against a stub client**

Append to `tests/test_channel_inbox.py`:

```python
from types import SimpleNamespace

import pytest

from sdlc.channels.inbox import fetch_inbox, list_open_run_ids


class _StubHandle:
    """Returns one scripted pending_decisions() result, or raises."""

    def __init__(self, response=None, error=None):
        self._response = response if response is not None else []
        self._error = error

    async def query(self, name):
        assert name == "pending_decisions"
        if self._error is not None:
            raise self._error
        return self._response


class _StubClient:
    def __init__(self, handles: dict[str, _StubHandle]):
        self._handles = handles

    async def list_workflows(self, query):
        assert "FeatureWorkflow" in query
        assert "Running" in query
        for run_id in self._handles:
            yield SimpleNamespace(id=run_id)

    def get_workflow_handle(self, run_id):
        return self._handles[run_id]


def _raw(*items):
    return [i.model_dump(mode="json") for i in items]


@pytest.mark.asyncio
async def test_list_open_run_ids_returns_ids_from_the_visibility_query():
    client = _StubClient({"run-a": _StubHandle(), "run-b": _StubHandle()})
    assert await list_open_run_ids(client) == ["run-a", "run-b"]


@pytest.mark.asyncio
async def test_fetch_inbox_aggregates_pending_across_runs_and_drops_empty_ones():
    client = _StubClient({
        "run-a": _StubHandle(response=_raw(ARCH)),
        "run-b": _StubHandle(response=[]),          # nothing pending -> dropped
        "run-c": _StubHandle(response=_raw(Q1, MERGE)),
    })
    inbox = await fetch_inbox(client)
    assert inbox.total_open_runs == 3
    assert {r.run_id for r in inbox.runs} == {"run-a", "run-c"}
    assert inbox.errors == []
    by_id = {r.run_id: r.pending for r in inbox.runs}
    assert [d.key for d in by_id["run-c"]] == ["Q1", "merge#2"]


@pytest.mark.asyncio
async def test_fetch_inbox_isolates_a_failing_run_from_the_rest():
    client = _StubClient({
        "run-a": _StubHandle(response=_raw(ARCH)),
        "run-b": _StubHandle(error=RuntimeError("workflow not found")),
    })
    inbox = await fetch_inbox(client)
    assert inbox.total_open_runs == 2
    assert [r.run_id for r in inbox.runs] == ["run-a"]
    assert inbox.errors[0].run_id == "run-b"
    assert "workflow not found" in inbox.errors[0].error
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_channel_inbox.py -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_inbox' from 'sdlc.channels.inbox'`

- [ ] **Step 3: Add the two functions to `src/sdlc/channels/inbox.py`**

Add near the top of the file:

```python
import asyncio
```

Add after the `render_inbox` function:

```python
_OPEN_FEATURE_QUERY = "WorkflowType='FeatureWorkflow' AND ExecutionStatus='Running'"


async def list_open_run_ids(client) -> list[str]:
    """Every currently-running FeatureWorkflow id, via a server-side
    visibility filter -- ReflectWorkflow/BenchmarkWorkflow executions on the
    same task queue never expose pending_decisions, so they are excluded
    here rather than probed and discarded."""
    return [wf.id async for wf in client.list_workflows(_OPEN_FEATURE_QUERY)]


async def _fetch_one(client, run_id: str):
    """Never raises: an exception becomes the return value, so one run's
    failure can't take down asyncio.gather for the rest."""
    try:
        handle = client.get_workflow_handle(run_id)
        return await fetch_pending(handle)
    except Exception as e:  # noqa: BLE001 -- captured into Inbox.errors, not raised
        return e


async def fetch_inbox(client) -> Inbox:
    """Discover every open run, fetch each one's pending decisions
    concurrently, and aggregate. A run with nothing pending is dropped, not
    listed; a run whose query raised becomes an InboxError instead of
    aborting the whole fetch."""
    run_ids = await list_open_run_ids(client)
    results = await asyncio.gather(*(_fetch_one(client, rid) for rid in run_ids))

    inbox = Inbox(total_open_runs=len(run_ids))
    for run_id, outcome in zip(run_ids, results):
        if isinstance(outcome, Exception):
            inbox.errors.append(InboxError(run_id=run_id, error=str(outcome)))
        elif outcome:
            inbox.runs.append(RunInbox(run_id=run_id, pending=outcome))
    return inbox
```

Add the import of `fetch_pending` to the existing import block at the top of the file:

```python
from .transport import describe, fetch_pending
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_channel_inbox.py -v`
Expected: PASS (10 tests total: 7 from Task 2 + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/channels/inbox.py tests/test_channel_inbox.py
git commit -m "feat(channels): fetch_inbox aggregates pending decisions across runs (E-8)

list_open_run_ids filters to open FeatureWorkflow executions server-side
via Temporal visibility; fetch_inbox fans out fetch_pending concurrently
and isolates a per-run failure into Inbox.errors instead of aborting the
whole fetch. Tested against a stub client -- no live Temporal server
needed, matching how transport.py's resolve/submit are tested."
```

---

### Task 4: Wire the `inbox` verb into the CLI

**Files:**
- Modify: `src/sdlc/cli.py`
- Test: `tests/test_channel_transport.py` (extend with one parsing test, alongside the existing CLI-parsing tests for the decision verbs)

**Interfaces:**
- Consumes: `fetch_inbox`, `render_inbox` from `sdlc.channels.inbox` (Task 3).
- Produces: `sdlc inbox` CLI command.

`cli.py`'s `main()` builds its argparse parser and dispatches in one function
(there is no separate `build_parser()` to import, unlike
`add_decision_parsers` which the existing decision-verb tests reuse
directly). So this task's test pins the contract ("inbox" takes no
arguments) against a locally-built mirror parser rather than `main()`
itself, the same way `test_gate_verbs_no_longer_accept_round` etc. already
do in this file for the decision verbs. The real regression protection for
this task comes from Step 4's full-suite run plus the manual verification
at the end of this plan.

- [ ] **Step 1: Add the parsing test**

Append to `tests/test_channel_transport.py`:

```python
def test_inbox_verb_takes_no_arguments():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inbox")
    args = p.parse_args(["inbox"])
    assert args.cmd == "inbox"
```

This needs `argparse` imported in the test file; add `import argparse` near
the top alongside the existing `import pytest`.

- [ ] **Step 2: Run it to confirm the mirror parser behaves as intended**

Run: `python -m pytest tests/test_channel_transport.py::test_inbox_verb_takes_no_arguments -v`
Expected: PASS. (This pins the "no required arguments" contract; it does
not exercise `cli.py` itself, which Step 3 changes next.)

- [ ] **Step 3: Register the `inbox` subparser and dispatch in `cli.py`**

In `src/sdlc/cli.py`, add the subparser registration right after the `status` subparser:

```python
    st = sub.add_parser("status")
    st.add_argument("--id", required=True)

    sub.add_parser("inbox")
```

Add the dispatch branch **before** the generic `handle = client.get_workflow_handle_for(...)` line (that line assumes `args.id` exists, which `inbox` does not have) -- place it directly after the existing `eval` block and before that line:

```python
    if args.cmd == "eval":
        from .eval.cli import default_judge_model, run_capture, run_eval
        from .eval.compare import EvalError
        if args.target == "capture":
            paths = await run_capture(client, args.from_run, args.case)
            print(f"captured {len(paths)} fixtures:")
            for p in paths:
                print(f"  {p}")
            return
        try:
            judge = args.judge_model or default_judge_model()
            print(run_eval(args.target, against=args.against, case=args.case,
                           k=args.k, judge_model=judge))
        except EvalError as e:
            print(f"eval error: {e}")
            raise SystemExit(1)
        return

    if args.cmd == "inbox":
        from .channels.inbox import fetch_inbox, render_inbox
        print(render_inbox(await fetch_inbox(client)))
        return

    handle = client.get_workflow_handle_for(FeatureWorkflow.run, args.id)
```

Also add `inbox` to the module docstring's usage examples at the top of `cli.py`, next to `status`:

```python
  python -m sdlc.cli status  --id feature-add-sso
  python -m sdlc.cli inbox
```

- [ ] **Step 4: Run the parsing test and the full test suite**

Run: `python -m pytest tests/test_channel_transport.py tests/test_channel_inbox.py -v`
Expected: all PASS.

Run: `python -m pytest -q`
Expected: full suite passes (no regressions from the `_fetch` rename or the new dispatch branch).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/cli.py tests/test_channel_transport.py
git commit -m "feat(cli): add read-only 'inbox' verb listing pending decisions across runs (E-8)

sdlc inbox lists every pending clarify/gate/escalation across every open
FeatureWorkflow run. Read-only: acting on an item still goes through the
existing --id-scoped approve/reject/revise/answer verbs. Closes FR-305 and
FR-603's missing verb."
```

---

## Manual verification (not automated -- needs a live Temporal server)

The unit suite covers `render_inbox`, `list_open_run_ids`, and `fetch_inbox` entirely against stubs, deliberately not against `WorkflowEnvironment.start_time_skipping()` (per the spec, whether that lightweight test server implements the visibility `list_workflows` query at all is untested territory). Before considering E-8 fully proven end-to-end, start a local Temporal dev server and worker, start one or two `FeatureWorkflow` runs that reach a clarify/gate wait, and run `python -m sdlc.cli inbox` to confirm the real visibility query and live queries round-trip correctly. This mirrors how `sdlc start` and `sdlc schedules apply` (non-dry-run) are also not unit-tested for their live-network path in this codebase.
