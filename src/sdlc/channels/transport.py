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

    def __init__(self, message: str,
                 candidates: Sequence[PendingDecision] = ()) -> None:
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


def match(pendings: Sequence[PendingDecision], selector: Selector,
          channel: Channel | None = None) -> PendingDecision:
    """Resolve a selector to exactly one pending item, or raise.

    Candidates are narrowed by ``render(d).reply_kind`` rather than isinstance:
    that field's documented job is telling a surface which affordance to offer,
    so it is precisely the question being asked here. This module therefore
    holds no knowledge of the pending variant types.
    """
    ch = channel or ReferenceChannel()
    noun = _noun(selector.reply_kind)

    cands = [d for d in pendings
             if ch.render(d).reply_kind == selector.reply_kind]
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
            f"ambiguous -- {len(cands)} {noun}s pending:\n{_listing(cands)}",
            candidates=cands)

    return cands[0]


def _name_of(d: PendingDecision) -> str:
    """Gate variants carry .gate; clarify falls back to its question id."""
    return getattr(d, "gate", None) or d.key
