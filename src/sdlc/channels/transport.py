"""Transport for the channel contract (E-7).

``contract.py`` is pure by design: "Transport code invokes the named signal
with these args on the workflow handle." This module is that transport --
query, match, signal, verify -- written once so every surface (CLI now;
E-8 inbox, E-10 dashboard, E-11 MCP later) reuses it.

Signals and queries go by NAME. Nothing here imports a workflow class, so
the module stays workflow- and surface-agnostic: the same approve verb
reaches a feature run, a triage, or a tidy-up unchanged.

All operator-facing strings are ASCII: the Windows console cannot print
non-ASCII (see the `schedules list` arrow fix).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, TypeAdapter

from ..core.models import (
    GateOutcome,
)
from ..pending import ClarifyPending, PendingDecision
from .contract import Channel, ReferenceChannel, Reply

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
    if isinstance(d, ClarifyPending):
        return f"{d.key}: {d.question}"
    return f"{d.gate} (round {d.round})"


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


def match_key(pendings: Sequence[PendingDecision], key: str) -> PendingDecision:
    """Resolve a pending item by its exact resolution key, or raise NoMatch.

    match()'s sibling for surfaces that already hold the key -- the dashboard
    operator clicked a specific item, so Selector's reply_kind narrowing and
    ambiguity resolution would only introduce a way to hit the wrong one.
    Keys are unique by construction (question id, or gate_key(gate, round)),
    so there is no Ambiguous case here.
    """
    for d in pendings:
        if d.key == key:
            return d
    head = f"no pending item with key '{key}' on this run"
    if pendings:
        head += f"\ncurrently pending:\n{_listing(pendings)}"
    raise NoMatch(head, candidates=list(pendings))


async def resolve_key(handle, key: str) -> PendingDecision:
    """resolve()'s sibling: fetch what is pending and address one by key."""
    return match_key(await fetch_pending(handle), key)


def _name_of(d: PendingDecision) -> str:
    """Gate variants carry .gate; clarify falls back to its question id."""
    return getattr(d, "gate", None) or d.key


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


async def resolve(handle, selector: Selector, channel: Channel | None = None) -> PendingDecision:
    """Fetch what is pending and narrow it to the one item meant."""
    return match(await fetch_pending(handle), selector, channel)


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

    still = await fetch_pending(handle)
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
    if isinstance(pending, ClarifyPending):
        return f"answered {pending.key} on {run_id}"
    assert reply.outcome is not None
    return f"{_PAST[reply.outcome]} gate '{pending.gate}' (round {pending.round}) on {run_id}"
