# CLI Refit onto the Channel Contract (E-7) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the operator CLI's `answer`/`approve`/`reject` verbs through the E-6 channel contract, deriving each gate's round from the pending item instead of a `--round` flag that defaults to 1, and add the missing `revise` verb.

**Architecture:** A new `src/sdlc/channels/transport.py` owns the Temporal round-trips that `contract.py` deliberately excludes — query `pending_decisions`, match one item against a selector, translate a reply, signal, re-query to verify. It signals and queries **by name**, never importing `FeatureWorkflow`, so E-8/E-10/E-11 reuse it unchanged. `cli.py` becomes a thin argparse shell over it (ADR-8). Two lines in `feature.py`'s signal handlers make `_pending` mean exactly one thing — *not yet decided* — for every variant.

**Tech Stack:** Python 3.14, Pydantic v2 (`TypeAdapter`, discriminated unions), Temporal (`temporalio` 1.30.0), argparse, pytest 8 + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-07-19-cli-refit-onto-channel-contract-design.md`
**Depends on (shipped):** `2026-07-18-channel-contract-over-fr302-design.md` (E-6, `ae6108b`…`2e994e4`).

## Global Constraints

- **All CLI output is ASCII.** A prior fix replaced `→` with `->` in `schedules list` because the Windows console encoding could not print it. Every new printed string, including exception messages that reach the terminal, is ASCII-only. No arrows, no em-dashes, no smart quotes — use `--` and `->`.
- **`transport.py` never imports `FeatureWorkflow`** or anything from `sdlc.workflows`. Signals and queries go by string name (`"answer_question"`, `"submit_gate_decision"`, `"pending_decisions"`). `SignalCall.signal` already carries the literal name.
- **Do not modify `src/sdlc/channels/contract.py`.** `render`/`translate` are not what failed. If a task seems to need a contract change, stop and escalate.
- **Do not add a listing/inbox verb.** No `pending`, no `inbox`, no cross-run anything. That is E-8 and building it here risks building it twice.
- **Run tests with the repo venv:** `env\Scripts\python.exe -m pytest`. There is no CI workflow; local pytest is the gate.
- **Async tests use the explicit marker** `@pytest.mark.asyncio`. There is no `asyncio_mode = auto` in `pyproject.toml`, so an unmarked `async def test_` silently no-ops.
- Gate identity is `gate_key(gate, round)` -> `f"{gate}#{round}"` (`models.py:405-407`). Never construct it by hand in new code; import `gate_key`.

---

## File Structure

| file | responsibility |
|---|---|
| `src/sdlc/channels/transport.py` | **new.** Selector/result types, pure `match`, and the async `resolve`/`submit` round-trips. The only place that knows how a reply reaches Temporal. |
| `src/sdlc/cli.py` | argparse shell: flags -> `Selector` + `Reply`, print the result. Holds no signalling logic. |
| `src/sdlc/workflows/feature.py` | two lines in signal handlers so `_pending` tracks *undecided*, not *unclosed*. |
| `tests/test_channel_transport.py` | **new.** Pure `match` tests, then `resolve`/`submit` against a stub handle. |
| `tests/test_pending_wiring.py` | extended with the `_pending` accuracy regressions. |

---

### Task 1: `_pending` tracks undecided items

Fixes spec §1.3 — an E-6 bug where answering Q1 of 3 leaves Q1 listed as pending, because the pop only runs after `wait_condition` releases for *all* questions. Everything downstream (verification in Task 3, E-8's inbox) depends on this being accurate.

**Files:**
- Modify: `src/sdlc/workflows/feature.py:347-357`
- Test: `tests/test_pending_wiring.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `FeatureWorkflow.pending_decisions()` now returns only items with no decision/answer recorded. Task 3's `submit` verification relies on this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pending_wiring.py`. Note the existing imports at the top of that file already include `StageGatePending` and `FeatureWorkflow`; add the others.

```python
import datetime as dt

from sdlc.models import GateDecision, GateOutcome
from sdlc.pending import ClarifyPending


def test_answer_question_pops_only_that_question():
    wf = FeatureWorkflow()
    for qid in ("Q1", "Q2"):
        wf._pending[qid] = ClarifyPending(key=qid, question=f"{qid}?", why_it_matters="w")

    wf.answer_question("Q1", "Use OIDC")

    assert [d.key for d in wf.pending_decisions()] == ["Q2"]
    assert wf._question_answers == {"Q1": "Use OIDC"}


def test_answer_question_is_still_first_answer_wins():
    wf = FeatureWorkflow()
    wf._pending["Q1"] = ClarifyPending(key="Q1", question="q", why_it_matters="w")

    wf.answer_question("Q1", "first")
    wf.answer_question("Q1", "second")

    assert wf._question_answers["Q1"] == "first"
    assert wf.pending_decisions() == []


def test_submit_gate_decision_pops_that_gate(monkeypatch):
    from sdlc.workflows import feature as feat

    monkeypatch.setattr(
        feat.workflow, "now", lambda: dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    )

    wf = FeatureWorkflow()
    wf._pending["architecture#2"] = StageGatePending(
        key="architecture#2", gate="architecture", round=2, spec_summary="s"
    )

    wf.submit_gate_decision(
        GateDecision(gate="architecture", round=2, outcome=GateOutcome.APPROVE, decided_by="human")
    )

    assert wf.pending_decisions() == []
    assert wf._gate_decisions["architecture#2"].outcome is GateOutcome.APPROVE
```

`submit_gate_decision` calls `workflow.now()`, which raises outside a workflow context — hence the monkeypatch. `answer_question` touches no Temporal API, so its tests need none.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env\Scripts\python.exe -m pytest tests/test_pending_wiring.py -v`
Expected: `test_answer_question_pops_only_that_question` FAILS with `assert ['Q1', 'Q2'] == ['Q2']`. `test_submit_gate_decision_pops_that_gate` FAILS on the non-empty `pending_decisions()`. The two pre-existing tests in the file still pass.

- [ ] **Step 3: Add the pops**

In `src/sdlc/workflows/feature.py`, the two signal handlers become:

```python
@workflow.signal
def submit_gate_decision(self, decision: GateDecision) -> None:
    # Idempotent per (gate, round): first decision for a round wins.
    key = gate_key(decision.gate, decision.round)
    if key not in self._gate_decisions:
        decision.decided_at = workflow.now()
        self._gate_decisions[key] = decision
    # _pending means "not yet decided" for every variant (E-7).
    self._pending.pop(key, None)


@workflow.signal
def answer_question(self, question_id: str, answer: str) -> None:
    self._question_answers.setdefault(question_id, answer)
    self._pending.pop(question_id, None)
```

The pop sits **outside** the `if` in `submit_gate_decision`: a decision that lost the first-wins race still means the item is not pending.

Leave the existing pops at `feature.py:405` and `feature.py:768` alone. They are the correct cleanup on the timeout path, which no signal reaches.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env\Scripts\python.exe -m pytest tests/test_pending_wiring.py -v`
Expected: PASS, 7 passed.

- [ ] **Step 5: Run the full suite for replay-safety regressions**

Run: `env\Scripts\python.exe -m pytest`
Expected: no new failures versus the pre-task baseline. Mutating workflow state in a signal handler is deterministic and replay-safe; the handlers already mutate `_question_answers` and `_gate_decisions`.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_pending_wiring.py
git commit -m "fix(pending): _pending tracks undecided items, not unclosed rounds (E-7)

answer_question never popped _pending, so answering one of N clarify
questions left it listed as pending until every question was answered.
pending_decisions() therefore over-reported, and E-8's inbox would have
inherited it. Pop in both signal handlers so _pending means exactly one
thing for every variant."
```

---

### Task 2: `Selector` and the pure `match`

All ambiguity and fail-closed rules live in a function that takes a list and returns an item, so they are testable with no Temporal server.

**Files:**
- Create: `src/sdlc/channels/transport.py`
- Test: `tests/test_channel_transport.py`

**Interfaces:**
- Consumes: `PendingDecision` (`sdlc.pending`), `Channel`/`ReferenceChannel` (`sdlc.channels.contract`).
- Produces: `Selector(reply_kind, name)`, `describe(d) -> str`, `match(pendings, selector, channel=None) -> PendingDecision`, exceptions `NoMatch`/`Ambiguous` (both subclass `SelectorError`, which carries `.message: str` and `.candidates: list[PendingDecision]`). Task 3 wraps `match`; Task 4 catches the exceptions and prints `.message`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_channel_transport.py`:

```python
from __future__ import annotations

import pytest

from sdlc.channels.transport import (
    Ambiguous,
    NoMatch,
    Selector,
    describe,
    match,
)
from sdlc.pending import (
    ClarifyPending,
    MergeGatePending,
    StageGatePending,
    TaskEscalationPending,
)

ARCH = StageGatePending(key="architecture#2", gate="architecture", round=2, spec_summary="s")
MERGE = MergeGatePending(key="merge#1", gate="merge", round=1)
Q1 = ClarifyPending(key="Q1", question="OIDC or SAML?", why_it_matters="auth")
Q2 = ClarifyPending(key="Q2", question="Which DB?", why_it_matters="storage")
TASK = TaskEscalationPending(
    key="task:T1#1", gate="task:T1", round=1, task_id="T1", analysis="flaky", attempts=3
)


def test_match_single_gate_without_name():
    got = match([ARCH, Q1], Selector(reply_kind="gate"))
    assert got is ARCH


def test_match_carries_the_pending_round_not_a_default():
    got = match([ARCH], Selector(reply_kind="gate", name="architecture"))
    assert got.round == 2


def test_match_filters_by_reply_kind():
    got = match([ARCH, Q1], Selector(reply_kind="text"))
    assert got is Q1


def test_match_by_gate_name():
    got = match([ARCH, MERGE], Selector(reply_kind="gate", name="merge"))
    assert got is MERGE


def test_match_by_question_id():
    got = match([Q1, Q2], Selector(reply_kind="text", name="Q2"))
    assert got is Q2


def test_match_task_escalation_by_prefixed_gate_name():
    got = match([ARCH, TASK], Selector(reply_kind="gate", name="task:T1"))
    assert got is TASK


def test_ambiguous_lists_only_same_kind_candidates():
    with pytest.raises(Ambiguous) as e:
        match([ARCH, MERGE, Q1], Selector(reply_kind="gate"))
    assert e.value.candidates == [ARCH, MERGE]
    assert "architecture (round 2)" in e.value.message
    assert "merge (round 1)" in e.value.message
    assert "OIDC" not in e.value.message


def test_no_match_on_unknown_name_lists_what_is_pending():
    with pytest.raises(NoMatch) as e:
        match([ARCH], Selector(reply_kind="gate", name="planning"))
    assert "planning" in e.value.message
    assert "architecture (round 2)" in e.value.message


def test_no_match_on_empty_pending():
    with pytest.raises(NoMatch) as e:
        match([], Selector(reply_kind="gate"))
    assert e.value.candidates == []


def test_messages_are_ascii():
    with pytest.raises(Ambiguous) as e:
        match([ARCH, MERGE], Selector(reply_kind="gate"))
    e.value.message.encode("ascii")  # raises UnicodeEncodeError if not


def test_describe_gate_and_clarify():
    assert describe(ARCH) == "architecture (round 2)"
    assert describe(Q1) == "Q1: OIDC or SAML?"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env\Scripts\python.exe -m pytest tests/test_channel_transport.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'sdlc.channels.transport'`.

- [ ] **Step 3: Write the module**

Create `src/sdlc/channels/transport.py`:

```python
"""Transport for the channel contract (E-7).

``contract.py`` is pure by design: "Transport code invokes the named signal
with these args on the workflow handle." This module is that transport --
query, match, signal, verify -- written once so every surface (CLI now;
E-8 inbox, E-10 dashboard, E-11 MCP later) reuses it.

Signals and queries go by NAME. Nothing here imports FeatureWorkflow, so the
module stays workflow- and surface-agnostic.

All operator-facing strings are ASCII: the Windows console cannot print
non-ASCII (see the `schedules list` arrow fix).
"""

from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel

from ..pending import PendingDecision
from .contract import Channel, ReferenceChannel

PENDING_QUERY = "pending_decisions"


class Selector(BaseModel):
    """Which pending item the operator means.

    ``name`` is a gate name or a question id; ``None`` means "the only pending
    item of this reply_kind", which fails closed when there is more than one.
    """

    reply_kind: Literal["text", "gate"]
    name: str | None = None


class SelectorError(Exception):
    """Base for selector resolution failures. ``message`` is a fully formatted
    multi-line ASCII block the surface can print verbatim."""

    def __init__(self, message: str, candidates: Sequence[PendingDecision] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.candidates = list(candidates)


class NoMatch(SelectorError):
    """Nothing pending answers this selector. Nothing was signalled."""


class Ambiguous(SelectorError):
    """More than one pending item answers this selector. Nothing was
    signalled -- the surface must narrow it."""


def describe(d: PendingDecision) -> str:
    """One ASCII line naming a pending item, for listings."""
    gate = getattr(d, "gate", None)
    if gate is not None:
        return f"{gate} (round {d.round})"
    return f"{d.key}: {d.question}"


def _listing(candidates: Sequence[PendingDecision]) -> str:
    return "\n".join(f"  {describe(d)}" for d in candidates)


def _noun(reply_kind: str) -> str:
    return "gate" if reply_kind == "gate" else "question"


def match(
    pendings: Sequence[PendingDecision], selector: Selector, channel: Channel | None = None
) -> PendingDecision:
    """Resolve a selector to exactly one pending item, or raise.

    Candidates are narrowed by ``render(d).reply_kind`` rather than isinstance:
    that field's documented job is telling a surface which affordance to offer,
    so it is precisely the question being asked here. This module therefore
    holds no knowledge of the pending variant types.
    """
    ch = channel or ReferenceChannel()
    noun = _noun(selector.reply_kind)

    cands = [d for d in pendings if ch.render(d).reply_kind == selector.reply_kind]
    if selector.name is not None:
        cands = [d for d in cands if _name_of(d) == selector.name]

    if not cands:
        if selector.name is not None:
            head = f"no pending {noun} named '{selector.name}' on this run"
        else:
            head = f"nothing pending for a {noun} reply on this run"
        if pendings:
            head += f"\ncurrently pending:\n{_listing(pendings)}"
        raise NoMatch(head, candidates=list(pendings))

    if len(cands) > 1:
        raise Ambiguous(
            f"ambiguous -- {len(cands)} {noun}s pending:\n{_listing(cands)}", candidates=cands
        )

    return cands[0]


def _name_of(d: PendingDecision) -> str:
    """Gate variants carry .gate; clarify falls back to its question id."""
    return getattr(d, "gate", None) or d.key
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env\Scripts\python.exe -m pytest tests/test_channel_transport.py -v`
Expected: PASS, 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/channels/transport.py tests/test_channel_transport.py
git commit -m "feat(channels): Selector and pure match over pending decisions (E-7)

match() resolves a selector to exactly one pending item or fails closed
with an ASCII listing, never guessing. Pure, so every ambiguity rule is
testable without a Temporal server. Candidates are filtered by
render().reply_kind rather than isinstance, keeping transport free of
the pending variant types."
```

---

### Task 3: `resolve` and `submit` round-trips

Adds the async half: fetch pending items, dispatch the translated signal, re-query to verify it landed.

**Files:**
- Modify: `src/sdlc/channels/transport.py`
- Modify: `pyproject.toml:19-20`
- Test: `tests/test_channel_transport.py`

**Interfaces:**
- Consumes: `match`, `Selector` (Task 2); `Reply`, `ReferenceChannel` (`sdlc.channels.contract`); the accurate `_pending` from Task 1.
- Produces: `SubmitResult(confirmed: bool, message: str)`, `async resolve(handle, selector, channel=None) -> PendingDecision`, `async submit(handle, pending, reply, channel=None) -> SubmitResult`. Task 4 calls exactly these two.

- [ ] **Step 1: Declare pytest-asyncio**

`tests/` already uses `@pytest.mark.asyncio` (e.g. `tests/test_memoization_cache.py:44`) but `pyproject.toml` declares only `pytest>=8`. It is installed in this venv by chance. This task's tests make that load-bearing, so declare it:

```toml
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_channel_transport.py`:

```python
from sdlc.channels.contract import Reply
from sdlc.channels.transport import SubmitResult, resolve, submit
from sdlc.models import GateOutcome


class StubHandle:
    """Records signals; returns scripted query results, one per call.

    Results are raw JSON-shaped dicts, matching what a by-name query returns
    through pydantic_data_converter before validation.
    """

    def __init__(self, id: str, responses):
        self.id = id
        self._responses = list(responses)
        self.signals = []

    async def query(self, name, *a, **kw):
        assert name == "pending_decisions"
        return self._responses.pop(0)

    async def signal(self, name, arg=None, *, args=()):
        self.signals.append((name, arg, list(args)))


def _raw(*items):
    return [i.model_dump(mode="json") for i in items]


@pytest.mark.asyncio
async def test_resolve_validates_the_discriminated_union():
    h = StubHandle("run-1", [_raw(ARCH, Q1)])
    got = await resolve(h, Selector(reply_kind="gate"))
    assert isinstance(got, StageGatePending)
    assert got.gate == "architecture" and got.round == 2


@pytest.mark.asyncio
async def test_submit_gate_sends_decision_with_the_pending_round():
    h = StubHandle("run-1", [_raw()])  # nothing left pending
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.APPROVE, text="lgtm"))

    name, arg, _ = h.signals[0]
    assert name == "submit_gate_decision"
    assert arg.gate == "architecture" and arg.round == 2
    assert arg.outcome is GateOutcome.APPROVE and arg.comments == "lgtm"
    assert res.confirmed is True
    assert res.message == "approved gate 'architecture' (round 2) on run-1"


@pytest.mark.asyncio
async def test_submit_clarify_sends_answer_question_positionally():
    h = StubHandle("run-1", [_raw()])
    res = await submit(h, Q1, Reply(text="Use OIDC"))

    name, arg, args = h.signals[0]
    assert name == "answer_question"
    assert arg is None and args == ["Q1", "Use OIDC"]
    assert res.message == "answered Q1 on run-1"


@pytest.mark.asyncio
async def test_submit_revise_reports_revision_requested():
    h = StubHandle("run-1", [_raw()])
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.REVISE, text="split it"))

    _, arg, _ = h.signals[0]
    assert arg.outcome is GateOutcome.REVISE and arg.guidance == "split it"
    assert res.confirmed is True
    assert "revision requested on" in res.message


@pytest.mark.asyncio
async def test_submit_not_confirmed_when_item_survives_the_requery():
    h = StubHandle("run-1", [_raw(ARCH)])  # still pending afterwards
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.APPROVE))

    assert res.confirmed is False
    assert res.message.startswith("not confirmed:")
    assert "decided it first" in res.message
    assert "failed" not in res.message  # never claims failure
    res.message.encode("ascii")


@pytest.mark.asyncio
async def test_submit_confirms_when_a_different_item_remains():
    h = StubHandle("run-1", [_raw(Q1)])  # unrelated item still pending
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.APPROVE))
    assert res.confirmed is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `env\Scripts\python.exe -m pytest tests/test_channel_transport.py -v`
Expected: `ImportError: cannot import name 'SubmitResult'`.

- [ ] **Step 4: Implement the round-trips**

**Replace** two existing import lines at the top of
`src/sdlc/channels/transport.py` and add one new line — do not duplicate them:

```python
from pydantic import BaseModel, TypeAdapter  # was: BaseModel only
from .contract import Channel, ReferenceChannel, Reply  # was: no Reply

from ..models import GateOutcome  # new
```

Then append to the module:

```python
_PENDING_LIST = TypeAdapter(list[PendingDecision])

_PAST = {
    GateOutcome.APPROVE: "approved",
    GateOutcome.REJECT: "rejected",
    GateOutcome.REVISE: "revision requested on",
}


class SubmitResult(BaseModel):
    """Outcome of one reply. ``confirmed`` is False when the item is still
    pending after the signal -- not an error (see ``message``)."""

    confirmed: bool
    message: str


async def _fetch(handle) -> list[PendingDecision]:
    """Query by name and validate the discriminated union ourselves.

    Deliberately not `result_type=list[PendingDecision]`: TypeAdapter round-
    trips the Annotated union verifiably without a live server, so the
    behavior is pinned by unit tests rather than discovered in staging.
    """
    raw = await handle.query(PENDING_QUERY)
    return _PENDING_LIST.validate_python(raw)


async def resolve(handle, selector: Selector, channel: Channel | None = None) -> PendingDecision:
    """Fetch what is pending and narrow it to the one item meant."""
    return match(await _fetch(handle), selector, channel)


async def submit(
    handle, pending: PendingDecision, reply: Reply, channel: Channel | None = None
) -> SubmitResult:
    """Translate a reply to its signal, send it, and verify it landed."""
    ch = channel or ReferenceChannel()
    call = ch.translate(pending, reply)

    if call.signal == "answer_question":
        await handle.signal(call.signal, args=[call.question_id, call.answer])
    else:
        await handle.signal(call.signal, call.decision)

    still = await _fetch(handle)
    confirmed = pending.key not in {d.key for d in still}
    return SubmitResult(confirmed=confirmed, message=_message(handle.id, pending, reply, confirmed))


def _message(run_id: str, pending: PendingDecision, reply: Reply, confirmed: bool) -> str:
    if not confirmed:
        # Signal processing is asynchronous, so this is never reported as a
        # failure: the dominant cause is another surface winning the race,
        # which is FR-302 working as designed.
        return (
            f"not confirmed: {describe(pending)} still pending -- another "
            f"surface may have decided it first, or the workflow has not "
            f"processed the signal yet."
        )
    gate = getattr(pending, "gate", None)
    if gate is not None:
        return f"{_PAST[reply.outcome]} gate '{gate}' (round {pending.round}) on {run_id}"
    return f"answered {pending.key} on {run_id}"
```

Revise verifies correctly for free: the workflow advances to round+1, so `architecture#2` is absent from the re-query regardless of what replaced it.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env\Scripts\python.exe -m pytest tests/test_channel_transport.py -v`
Expected: PASS, 18 passed.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/channels/transport.py tests/test_channel_transport.py pyproject.toml
git commit -m "feat(channels): resolve/submit round-trips with landed-verification (E-7)

submit translates, signals by name, then re-queries: the success message
now means the decision is actually gone from pending. Reports 'not
confirmed' rather than 'failed', since asynchronous signal processing and
a lost first-wins race are both benign. Queries validate the union with
TypeAdapter so the behavior is unit-pinned, not server-dependent."
```

---

### Task 4: Refit the CLI verbs

**Files:**
- Modify: `src/sdlc/cli.py:1-13` (docstring), `:47-58` (parsers), `:175-188` (dispatch)
- Test: `tests/test_channel_transport.py` (CLI-level parser tests)

**Interfaces:**
- Consumes: `Selector`, `resolve`, `submit`, `NoMatch`, `Ambiguous` (Tasks 2-3); `Reply` (`sdlc.channels.contract`).
- Produces: the operator surface. No later task consumes it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_channel_transport.py`:

```python
import sdlc.cli


def _parse(argv):
    """Build the CLI parser the same way main() does, and parse argv."""
    import argparse

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sdlc.cli.add_decision_parsers(sub)
    return p.parse_args(argv)


def test_gate_verbs_no_longer_accept_round():
    with pytest.raises(SystemExit):
        _parse(["approve", "--id", "X", "--round", "2"])


def test_gate_selector_is_optional():
    args = _parse(["approve", "--id", "X"])
    assert args.cmd == "approve" and args.gate is None


def test_revise_verb_exists_and_takes_comment():
    args = _parse(["revise", "--id", "X", "--comment", "split it"])
    assert args.cmd == "revise" and args.comment == "split it"


def test_answer_question_id_is_optional_but_text_required():
    args = _parse(["answer", "--id", "X", "--text", "yes"])
    assert args.q is None and args.text == "yes"
    with pytest.raises(SystemExit):
        _parse(["answer", "--id", "X"])


def test_selector_for_builds_gate_and_text_selectors():
    a = _parse(["approve", "--id", "X", "--gate", "merge"])
    sel, reply = sdlc.cli.selector_for(a)
    assert sel.reply_kind == "gate" and sel.name == "merge"
    assert reply.outcome is GateOutcome.APPROVE

    a = _parse(["answer", "--id", "X", "--q", "Q1", "--text", "yes"])
    sel, reply = sdlc.cli.selector_for(a)
    assert sel.reply_kind == "text" and sel.name == "Q1"
    assert reply.text == "yes"


def test_revise_reply_carries_comment_as_text():
    a = _parse(["revise", "--id", "X", "--comment", "split it"])
    _, reply = sdlc.cli.selector_for(a)
    assert reply.outcome is GateOutcome.REVISE and reply.text == "split it"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env\Scripts\python.exe -m pytest tests/test_channel_transport.py -v`
Expected: `AttributeError: module 'sdlc.cli' has no attribute 'add_decision_parsers'`.

- [ ] **Step 3: Extract the parsers and the selector mapping**

In `src/sdlc/cli.py`, add these two module-level functions after `slug()`. Extracting them is what makes the parser testable without running `main()`.

```python
_OUTCOME = {
    "approve": GateOutcome.APPROVE,
    "reject": GateOutcome.REJECT,
    "revise": GateOutcome.REVISE,
}

DECISION_CMDS = ("approve", "reject", "revise", "answer")


def add_decision_parsers(sub) -> None:
    """The four human-in-the-loop verbs. No --round: the round is read off
    the pending item, so a reply can never land on a stale round (E-7)."""
    for name in ("approve", "reject", "revise"):
        g = sub.add_parser(name)
        g.add_argument("--id", required=True)
        g.add_argument(
            "--gate", default=None, help="gate name; omit if exactly one gate is pending"
        )
        g.add_argument(
            "--comment", default=None, help="comment; required for revise (becomes guidance)"
        )

    a = sub.add_parser("answer")
    a.add_argument("--id", required=True)
    a.add_argument("--q", default=None, help="question id; omit if exactly one is pending")
    a.add_argument("--text", required=True)


def selector_for(args):
    """Map parsed args to the surface-neutral (Selector, Reply) pair."""
    from .channels.contract import Reply
    from .channels.transport import Selector

    if args.cmd == "answer":
        return Selector(reply_kind="text", name=args.q), Reply(text=args.text)
    return (
        Selector(reply_kind="gate", name=args.gate),
        Reply(outcome=_OUTCOME[args.cmd], text=args.comment),
    )
```

Replace the existing parser block at `cli.py:47-58` (the `for name in ("approve", "reject")` loop and the `answer` parser) with a single call, keeping the `start` parser above it and `status` below:

```python
    add_decision_parsers(sub)
```

- [ ] **Step 4: Run the parser tests to verify they pass**

Run: `env\Scripts\python.exe -m pytest tests/test_channel_transport.py -v`
Expected: PASS, 25 passed.

- [ ] **Step 5: Route the dispatch through transport**

Replace the dispatch block at `cli.py:175-188` (the `if args.cmd in ("approve", "reject")` / `elif args.cmd == "answer"` branches) with:

```python
if args.cmd in DECISION_CMDS:
    from .channels.transport import Ambiguous, NoMatch, resolve, submit

    selector, reply = selector_for(args)
    try:
        pending = await resolve(handle, selector)
    except (NoMatch, Ambiguous) as e:
        print(e.message)
        if isinstance(e, Ambiguous):
            flag = "--q" if args.cmd == "answer" else "--gate"
            print(f"re-run with {flag} <name>")
        raise SystemExit(1)
    print((await submit(handle, pending, reply)).message)
    return

if args.cmd == "status":
    print(await handle.query(FeatureWorkflow.status))
```

The `elif` chain becomes two `if` blocks because the decision branch now returns.

Add the `revise` guard next to the existing `eval capture` validation at `cli.py:90-93`, so it fails before connecting to Temporal:

```python
    if args.cmd == "revise" and not args.comment:
        print("revise requires --comment <guidance>")
        raise SystemExit(1)
```

The CLI no longer constructs a `GateDecision` — `default_translate` does. Drop
it from the import at `cli.py:26`, keeping the rest:

```python
from .models import GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
```

Verify nothing else in the file references it — `git grep -n GateDecision --
src/sdlc/cli.py` must return nothing.

- [ ] **Step 6: Update the module docstring**

Replace lines 5-7 of `src/sdlc/cli.py`:

```python
  python -m sdlc.cli answer  --id feature-add-sso --q Q1 --text "Use OIDC"
  python -m sdlc.cli approve --id feature-add-sso --gate architecture
  python -m sdlc.cli revise  --id feature-add-sso --gate architecture --comment "split task 3"
  python -m sdlc.cli reject  --id feature-add-sso --gate merge --comment "..."
```

- [ ] **Step 7: Verify the CLI imports and the help text is right**

Run: `env\Scripts\python.exe -m sdlc.cli approve --help`
Expected: shows `--id`, `--gate`, `--comment`. **No `--round`.**

Run: `env\Scripts\python.exe -m sdlc.cli revise --id X`
Expected: prints `revise requires --comment <guidance>`, exit code 1, and **no Temporal connection attempt** (no connection error in the output).

- [ ] **Step 8: Run the full suite**

Run: `env\Scripts\python.exe -m pytest`
Expected: all pass, no new failures.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/cli.py tests/test_channel_transport.py
git commit -m "feat(cli): refit decision verbs onto the channel contract (E-7)

approve/reject/answer now resolve the pending item first and read the
round off it, so --round is gone along with the silent no-op it caused:
approving a round-2 gate used to send a decision for round 1, get deduped,
and still print success. Adds the revise verb, which GateOutcome has had
all along with no way to reach it. Selectors are optional and fail closed
with a listing when ambiguous."
```

---

### Task 5: Record the increment

**Files:**
- Modify: `ROADMAP.md:6` (last-verified), `:253-254` (E-6/E-7), `:301` (§9.7 ordering), `:105` (FR-603)

**Interfaces:**
- Consumes: nothing. Documentation only.
- Produces: nothing.

- [ ] **Step 1: Check E-7 off in §9.2**

Replace the `E-7` bullet at `ROADMAP.md:254`:

```markdown
- [x] **E-7** Refit the existing CLI (`answer`/`approve`/`reject`) onto the contract.
  *Ordered first deliberately: it validates the contract against a known-good
  surface before any new surface depends on it.* **The contract held; the CLI and
  the query did not.** Three defects fell out: `--round` defaulted to 1, so a
  post-REVISE approve was silently deduped under a success message; `revise` had
  no verb despite `GateOutcome.REVISE` and US-2 marked done; and
  `pending_decisions()` over-reported answered clarify questions because
  `answer_question` never popped `_pending` (an E-6 bug, fixed here before E-8
  could inherit it). Adds `channels/transport.py` — query/match/signal/verify —
  so E-8/E-10/E-11 do not each reimplement it. Spec:
  `docs/superpowers/specs/2026-07-19-cli-refit-onto-channel-contract-design.md`.
```

- [ ] **Step 2: Update the §9.7 ordering**

Replace item 3 at `ROADMAP.md:301`:

```markdown
3. ~~**E-6**~~ landed (`feat/channel-contract`) → ~~**E-7**~~ landed
   (`feat/cli-channel-refit`) → **E-8** — the CLI refit proved the contract;
   E-8 is the first *new* capability it buys.
```

- [ ] **Step 3: Update FR-603**

Replace `ROADMAP.md:105`:

```markdown
- [ ] ⚠️ **FR-603** CLI — `start/status/answer/approve/revise/reject/benchmark` ✅
  (`revise` landed with E-7; gate rounds are now derived from the pending item,
  not typed by the operator); missing cross-run `inbox` (FR-305).
```

- [ ] **Step 4: Update the last-verified date**

Replace `ROADMAP.md:6`:

```markdown
| Last verified | 2026-07-19 (against `src/sdlc/`, `interfaces/`, `tests/`, `config/`, `agents/`) |
```

- [ ] **Step 5: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): E-7 CLI refit landed; contract validated"
```

- [ ] **Step 6: Final verification before merge**

Run: `env\Scripts\python.exe -m pytest`
Expected: all pass.

Run: `git log --oneline main..HEAD`
Expected: 6 commits — spec, then Tasks 1-5.

Then use `superpowers:finishing-a-development-branch` to decide how the branch integrates.

---

## Notes for the implementer

**Why `--round` is deleted with no escape hatch.** Deciding a gate that is not currently pending is no longer possible. Nothing in the repo relies on it — verified by grep; only gitignored `.superpowers/` scratch docs mention the flag. Tests and benchmarks signal handles directly and never go through the CLI, so they are unaffected.

**Why `submit` re-queries instead of trusting the signal.** `await handle.signal(...)` returning means the signal is durably recorded, not that the workflow has processed it. The re-query is what makes the printed success mean something. It can produce a false "not confirmed" on a slow workflow, which is exactly why the wording says *not confirmed* and names both causes rather than claiming failure.

**If `match` seems to need `isinstance`,** re-read spec §4.2 first. Filtering by `render(d).reply_kind` is deliberate: it keeps transport free of the four variant types so a fifth needs no change here.
