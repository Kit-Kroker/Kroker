"""Pure session helpers (E-38/ADR-16): waste digest, scrub, JSONL render.

No IO, no Temporal — activity code composes these; tests hit them directly.
"""

from __future__ import annotations

from collections import Counter

from pydantic import ValidationError

from ..memory.scrub import scrub
from ..models import HarnessSession, SessionDigest, SessionEvent

SKELETON_MAX = 200

_TOOL_KINDS = {"tool_call", "tool_result", "file_read", "file_write", "command"}


def digest_of(session: HarnessSession) -> SessionDigest:
    """BENCHMARK §4.3 aggregates, computed pre-truncation so they exist for
    every run — including clean-green runs whose full transcript is later
    downgraded (OQ-B7)."""
    reads: Counter[str] = Counter()
    writes: Counter[str] = Counter()
    d = SessionDigest(input_tokens=session.input_tokens, output_tokens=session.output_tokens)
    skeleton: list[str] = []
    for ev in session.events:
        if ev.kind in _TOOL_KINDS:
            d.tool_calls += 1
        if ev.kind == "file_read" and ev.target:
            d.file_reads += 1
            reads[ev.target] += 1
        elif ev.kind == "file_write" and ev.target:
            writes[ev.target] += 1
        elif ev.kind == "command" and ev.exit_code not in (0, None):
            d.failed_commands += 1
        elif ev.kind == "model_turn":
            d.model_turns += 1
        elif ev.kind == "compaction":
            d.compacted = True
        elif ev.kind == "tool_denied":
            d.denials += 1
        elif ev.kind == "tool_deferred":
            d.escalations += 1
        if ev.kind in _TOOL_KINDS and len(skeleton) < SKELETON_MAX:
            skeleton.append(f"{ev.tool or ev.kind} {ev.target or ''}".strip())
    d.file_rereads = sum(n - 1 for n in reads.values() if n > 1)
    d.files_written = len(writes)
    d.rewrite_churn = sum(1 for n in writes.values() if n > 1)
    d.decision_skeleton = skeleton
    return d


def scrub_session(session: HarnessSession) -> HarnessSession:
    """Apply the memory scrub to every payload-bearing field. Raises on
    internal failure — the caller (capture) is fail-closed and stores
    nothing in that case."""
    events = [
        ev.model_copy(
            update={
                "text": scrub(ev.text) if ev.text else ev.text,
                "target": scrub(ev.target) if ev.target else ev.target,
            }
        )
        for ev in session.events
    ]
    return session.model_copy(update={"events": events})


def session_to_jsonl(session: HarnessSession) -> str:
    """Header line (session metadata, no events) + one event per line —
    same idiom as events.jsonl (E-32)."""
    head = session.model_dump_json(exclude={"events"})
    lines = [head] + [ev.model_dump_json() for ev in session.events]
    return "\n".join(lines) + "\n"


def session_to_text(session: HarnessSession) -> str:
    """Canonical PLAIN-TEXT rendering of a session: one line per event, in the
    prose form the handoff/deep_review prompts describe.

    Code review #1: the store holds JSONL and load_session returns it raw, but
    eliciting and verifying prose evidence against raw JSONL drops legitimate
    claims (a model following its prompt quotes ``file_read oracle/test_app.py``
    which is not a substring of the JSON object). The model and the grounding
    verifier must see the SAME representation, and this is it: a faithful quote
    is a substring, because ``<kind> <target>`` matches the prompts' worked
    examples.
    """
    return _events_to_text(session.events)


def session_text_from_jsonl(jsonl: str) -> str:
    """Render the plain-text view directly from a stored JSONL transcript (the
    form ``load_session`` returns), so the verifier grounds on the same prose
    the model was shown.

    Tolerates a truncated trailing line: ``load_session`` byte-caps at
    ``DEEP_REVIEW_MAX_BYTES``, so the final event line can be cut mid-JSON;
    a partial line is skipped rather than crashing the render. The first line
    is the session-metadata header, not an event.
    """
    events: list[SessionEvent] = []
    for i, line in enumerate(jsonl.splitlines()):
        if i == 0 or not line.strip():
            continue  # header / blank
        try:
            events.append(SessionEvent.model_validate_json(line))
        except ValidationError:
            continue  # truncated/partial trailing line
    return _events_to_text(events)


def _events_to_text(events: list[SessionEvent]) -> str:
    lines = [_event_to_line(ev) for ev in events]
    return "\n".join(lines) + ("\n" if lines else "")


def _event_to_line(ev: SessionEvent) -> str:
    # Prose-style, matching the prompts' worked examples: '<kind> <target>'.
    if ev.target:
        lead = f"{ev.kind} {ev.target}"
    elif ev.tool:
        lead = f"{ev.kind} {ev.tool}"
    else:
        lead = ev.kind
    tail = ""
    if ev.kind == "command" and ev.exit_code is not None:
        tail = f" (exit {ev.exit_code})"
    if ev.text:
        tail = (tail + " " if tail else "") + ev.text
    return lead + tail
