# E-7 — CLI refit onto the channel contract

| | |
|---|---|
| Status | Design — approved, awaiting spec review |
| Date | 2026-07-19 |
| Roadmap item | `E-7` (§9.2) |
| Requirements served | FR-603 (CLI), FR-301/FR-302 (gate identity reaches the operator), US-2 (revise is finally reachable) |
| Depends on (shipped) | `2026-07-18-channel-contract-over-fr302-design.md` (E-6, `ae6108b`…`2e994e4`) |
| Scope guard | Refit the four existing verbs. **No new surface.** Nothing cross-run — that is E-8. |

## 1. Problem

E-6 landed a channel contract with **no consumer.** `render`/`translate` are
pure, tested, and unexercised by any real surface. E-6's own spec ordered this
increment first and said why:

> it validates the contract against a known-good surface before any new surface
> depends on it. If the CLI doesn't fit cleanly, the contract is wrong.

That test has now been run by inspection, and the CLI does **not** fit cleanly.
The contract survives; the CLI and the query feeding it do not. Three concrete
defects, in descending severity.

### 1.1 A stale round is a silent no-op with a success message

`cli.py:52` declares `--round` with `default=1`. `submit_gate_decision` is
keyed `(gate, round)` and first-decision-wins (`feature.py:348-353`).

After a REVISE, a gate is on round 2. An operator running
`approve --gate architecture` sends a decision for round **1** — already
decided, therefore dropped by the idempotency rule — while the CLI prints
`approved gate 'architecture' (round 1) on <id>` and the workflow keeps
waiting. The operator has no signal that nothing happened.

`default_translate` was written to make this unrepresentable:

> gate/round come from the pending item, so a reply can never land on the wrong
> round.

The fix is not a patch to the CLI's round handling. It is deleting the flag and
reading the round off the pending item — which is the refit.

### 1.2 The CLI cannot express REVISE

`GateOutcome` has APPROVE / REJECT / REVISE (`models.py:33-36`). The workflow
implements the revise loop, and US-2 is marked `[x]` on the strength of it.
`cli.py:175-183` offers only APPROVE and REJECT. A third of the gate vocabulary
has no operator surface, so the loop the roadmap claims as delivered can only
be driven by a test or a hand-written signal.

### 1.3 `pending_decisions()` over-reports answered clarify questions

Found while designing the verification step; this is a defect **in E-6**, not
in the CLI.

Clarify entries are popped only after *every* question is answered
(`feature.py:761-768`): `wait_condition` blocks until all answers are in, then
one loop pops them together. The `answer_question` signal (`feature.py:356-357`)
writes to `_question_answers` and never touches `_pending`.

So answering Q1 of 3 leaves Q1 listed as pending. `_pending` currently means
two different things depending on variant: *"not yet decided"* for gates (the
`finally` at `feature.py:405` pops promptly), *"belongs to a clarify round that
has not fully closed"* for questions.

Consequences: verification-by-re-query cannot work for clarify, and **E-8's
inbox would inherit the bug** — showing operators questions they have already
answered.

## 2. Non-goals

- **Anything cross-run.** No `inbox`, no listing across workflows (E-8).
- **A single-run `pending` / `show` verb.** That is E-8's shape; building it
  here risks building it twice.
- Notifications or push delivery (E-9). This increment is pull-only.
- Any change to `render`/`translate`. The contract is not what failed.
- Re-litigating gate policy, timeouts, or the revise loop's workflow mechanics.

## 3. Architecture

Three layers, with the new one in the middle:

```
cli.py            argparse shell: flags -> Selector + Reply, print result
  |
channels/transport.py   (NEW)  query / match / signal / verify
  |
channels/contract.py           render / translate  (pure, unchanged)
  |
pending.py + feature.py        PendingDecision, the two FR-302 signals
```

`contract.py`'s docstring states the boundary: *"Transport code invokes the
named signal with these args on the workflow handle."* Nothing owns that
transport today. E-7 writes it once rather than inline in the CLI, because
E-8 / E-10 / E-11 each need the identical sequence and would otherwise copy it.

### 3.1 Workflow-agnostic by construction

`transport.py` signals and queries **by name** — `"answer_question"`,
`"submit_gate_decision"`, `"pending_decisions"` — and never imports
`FeatureWorkflow`. `SignalCall.signal` is already a
`Literal["answer_question", "submit_gate_decision"]`, which is exactly what
that field exists to carry.

## 4. `channels/transport.py`

```python
class Selector(BaseModel):
    """Which pending item the operator means."""
    reply_kind: Literal["text", "gate"]
    name: str | None = None    # gate name, or question id; None = "the only one"


class SubmitResult(BaseModel):
    confirmed: bool
    message: str                # ASCII only; see section 7


class NoMatch(Exception):    ...   # carries candidates for the CLI to print
class Ambiguous(Exception):  ...   # carries candidates


def match(pendings, selector, channel=ReferenceChannel()) -> PendingDecision   # PURE
async def resolve(handle, selector, channel=...) -> PendingDecision
async def submit(handle, pending, reply, channel=...) -> SubmitResult
```

### 4.1 `match` is pure

Every ambiguity and fail-closed rule lives in a function that takes a list and
returns an item, so all of it is unit-testable with no Temporal server.
`resolve` is only `query` + `match`.

```python
def match(pendings, selector, channel=ReferenceChannel()):
    cands = [d for d in pendings
             if channel.render(d).reply_kind == selector.reply_kind]
    if selector.name is not None:
        cands = [d for d in cands if _name_of(d) == selector.name]
    if not cands:
        raise NoMatch(selector, candidates=pendings)
    if len(cands) > 1:
        raise Ambiguous(selector, candidates=cands)
    return cands[0]


def _name_of(d: PendingDecision) -> str:
    # gate variants carry .gate; clarify falls back to its question id
    return getattr(d, "gate", None) or d.key
```

### 4.2 Filtering by `reply_kind`, not `isinstance`

Candidates are narrowed using `render(d).reply_kind`. That field's documented
job is *"tells the surface which affordance to offer"*, so "which pending items
accept approve/revise/reject" is precisely the question it answers. Transport
therefore holds no knowledge of the four variant types, and a fifth variant
added later needs no change here.

### 4.3 `submit`

```python
async def submit(handle, pending, reply, channel=ReferenceChannel()):
    call = channel.translate(pending, reply)
    if call.signal == "answer_question":
        await handle.signal(call.signal, args=[call.question_id, call.answer])
    else:
        await handle.signal(call.signal, call.decision)
    still = await handle.query("pending_decisions",
                               result_type=list[PendingDecision])
    confirmed = pending.key not in {d.key for d in still}
    return SubmitResult(confirmed=confirmed, message=...)
```

Revise verifies correctly for free: the workflow advances to round+1, so the
old `gate_key(gate, round)` is absent from the re-query regardless of what
replaced it.

**Signal processing is asynchronous.** A slow workflow can leave the item
present at re-query time even though the signal will land. Therefore
`confirmed=False` is reported as **"not confirmed"**, never "failed", and the
message names both plausible causes: another surface decided first
(first-decision-wins, which is correct behavior), or the workflow has not yet
processed the signal.

## 5. Workflow change (folded in)

Two lines, both in signal handlers, no stage logic touched:

```python
@workflow.signal
def answer_question(self, question_id: str, answer: str) -> None:
    self._question_answers.setdefault(question_id, answer)
    self._pending.pop(question_id, None)            # new

@workflow.signal
def submit_gate_decision(self, decision: GateDecision) -> None:
    key = gate_key(decision.gate, decision.round)
    if key not in self._gate_decisions:
        decision.decided_at = workflow.now()
        self._gate_decisions[key] = decision
    self._pending.pop(key, None)                    # new
```

The clarify line fixes §1.3. The gate line is redundant with the `finally` at
`feature.py:405` but makes `_pending` mean exactly one thing — **not yet
decided** — for every variant. Mutating workflow state in a signal handler is
deterministic and replay-safe; the handlers already mutate `_question_answers`
and `_gate_decisions`.

The existing pops stay. They are the correct cleanup on the timeout path, which
no signal reaches.

## 6. CLI surface

| verb | `--id` | selector | text | removed |
|---|---|---|---|---|
| `approve` | required | `--gate` optional | `--comment` optional | `--round` |
| `reject` | required | `--gate` optional | `--comment` optional | `--round` |
| `revise` **(new)** | required | `--gate` optional | `--comment` **required** | — |
| `answer` | required | `--q` optional | `--text` required | — |

`--comment` covers all three gate verbs: `default_translate` already routes it
to `guidance` when the outcome is REVISE, so the CLI needs no special case. It
is required for `revise` because guidance-free revise gives the workflow
nothing to act on.

Selectors are optional, and omitting one means *"the only pending item of this
kind"*. Several clarify questions pending at once is the normal case, so
`answer --id X` with no `--q` will usually be ambiguous — and that is correct:
it fails closed and lists the questions rather than guessing.

`--round` is deleted with no escape hatch. Deciding a gate that is not
currently pending is no longer possible; nothing in the repo relies on it
(verified: only gitignored `.superpowers/` scratch docs reference the flag).

```
$ sdlc approve --id X
approved gate 'architecture' (round 2) on X

$ sdlc approve --id X
ambiguous -- 2 gates pending:
  architecture (round 2)
  merge (round 1)
re-run with --gate <name>

$ sdlc approve --id X --gate architecture
not confirmed: 'architecture' round 2 still pending -- another surface may
have decided it first, or the workflow has not processed the signal yet.
```

## 7. Error handling

- `NoMatch` / `Ambiguous` print the candidate list and `exit 1` **without
  signalling.** Nothing is sent on an unresolved selector.
- A run with an empty `pending_decisions()` is `NoMatch`, reported as "nothing
  awaiting a decision on `<id>`".
- `confirmed=False` exits **0** with the not-confirmed message. It is not an
  error: the dominant cause is another surface having decided first, which is
  FR-302 working as designed.
- **All CLI output is ASCII.** A prior fix replaced `→` with `->` in
  `schedules list` because the Windows console encoding could not print it
  (`.superpowers/sdd/fix-report.md`). This increment adds new printed output
  and inherits that constraint.

## 8. Testing

- `tests/test_channel_transport.py` — pure `match()`: exact hit, no match,
  ambiguous, `reply_kind` filtering, `task:<id>` gate names, clarify-by-id. No
  Temporal.
- `submit()` against a stub handle that records signal calls and returns
  scripted `pending_decisions` results, covering the confirmed and
  not-confirmed paths and both signal dispatches.
- Extend `tests/test_pending_wiring.py` — answering one of N questions removes
  **only** that one from `pending_decisions()` (§5, and the regression E-8
  would otherwise inherit).
- A gate-round regression: a round-2 pending gate plus `approve` with no
  `--round` produces a `GateDecision` with `round=2`. This is §1.1 pinned.
- CLI arg parsing and exit codes, following `tests/test_eval_cli.py`.

## 9. Files

| file | change |
|---|---|
| `src/sdlc/channels/transport.py` | new — `Selector`, `SubmitResult`, `match`, `resolve`, `submit` |
| `src/sdlc/cli.py` | refit four verbs, add `revise`, delete `--round`, update docstring |
| `src/sdlc/workflows/feature.py` | two lines in signal handlers (§5) |
| `tests/test_channel_transport.py` | new |
| `tests/test_pending_wiring.py` | extend |

## 10. Implementation risk — resolved during planning

The open question was whether querying **by name** round-trips the
`Annotated`-discriminated `PendingDecision` union through
`pydantic_data_converter`, with a `TypeAdapter` fallback if
`result_type=list[PendingDecision]` did not deserialize cleanly.

**Resolved: use the `TypeAdapter` path unconditionally.** It was verified
locally — `TypeAdapter(list[PendingDecision])` dumps and revalidates a mixed
`ClarifyPending` / `StageGatePending` list, preserving both the concrete types
and `round`. `result_type` was not adopted, because confirming it requires a
live server, which would make the deserialization behavior untestable in the
unit suite. The `TypeAdapter` path is pinned by ordinary tests instead.

`temporalio` 1.30.0's `WorkflowHandle.query` and `.signal` both accept a
string name (verified against the installed signatures), so signalling and
querying by name needs no workflow import.

## 11. What this unblocks

E-8 (cross-run inbox) becomes `resolve`'s sibling: the same `match` over
`pending_decisions()` results gathered from many handles instead of one. E-10
and E-11 supply their own `render` and reuse `submit` unchanged. Whether that
claim holds is the next falsification test.
