"""PIN: RESEARCH_SQ_ACT's non-retryable list stays paired with the handler
catch that makes it dead code (sbatch-2026-10-19 T4; task
.workspace/tasks/2026-10-05-dead-non-retryable-config-research-sq.md).

T4's decision is KEEP + document: ``_research_subquestion_impl`` catches
``(BudgetExceeded, UsageLimitExceeded)`` and degrades to a finding instead
of raising, so Temporal never sees those types and the activity's
``non_retryable_error_types`` cannot fire today — it is belt-and-braces
against a future handler refactor that lets a cap stop escape (the counter
is disk-persisted, so a retry would burn 6 attempts against a cap that
stays exhausted; stages/research/AGENTS.md, Budget enforcement).

That rationale is a PAIRING, and pairing drifts silently: adding a catch
type without naming it non-retryable (or editing the RetryPolicy list
alone) quietly changes which escapes retry. This test pins the pairing
from three independent sides — the RetryPolicy list, the handler's except
clauses (extracted from source, not from memory of them), and the
recorded replay history — so any unilateral edit fails here.

Green on main by design (the T4 deliverable is a source comment, not a
behaviour change; this file is the enforced form of that comment).
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from sdlc.stages.research.stage import _research_subquestion_impl
from sdlc.stages.research.step import RESEARCH_SQ_ACT

_HISTORY = Path("tests/replay/histories/research_retain_grounded.json")


def _caught_names(handler: ast.ExceptHandler) -> set[str] | None:
    """The plain names an except clause catches: ``except (A, B)`` ->
    {A, B}, ``except A`` -> {A}. None for shapes this pin does not reason
    about (bare ``except:``, attribute/call types) — a clause like that
    simply never participates in the selection below."""
    node = handler.type
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Tuple) and all(isinstance(el, ast.Name) for el in node.elts):
        return {el.id for el in node.elts}  # type: ignore[union-attr]
    return None


def test_sq_non_retryable_list_stays_paired_with_the_catch_and_the_replay():
    policy = set(RESEARCH_SQ_ACT["retry_policy"].non_retryable_error_types)

    # Side 1: the handler's cap catch. Select the except clauses that
    # mention a type the RetryPolicy names, then demand set equality with
    # the policy — a clause gaining or losing a name, or the catch
    # disappearing (or going bare/complex) so nothing is selected, is
    # exactly the silent drift this pin exists to catch.
    clauses = [
        names
        for names in (
            _caught_names(h)
            for h in ast.walk(ast.parse(inspect.getsource(_research_subquestion_impl)))
            if isinstance(h, ast.ExceptHandler)
        )
        if names is not None and names & policy
    ]
    assert clauses, (
        f"no except clause in _research_subquestion_impl catches any of "
        f"{sorted(policy)} — the degrade-not-raise contract broke, and "
        f"RESEARCH_SQ_ACT's non_retryable_error_types is no longer dead "
        f"belt-and-braces but live retry policy"
    )
    caught: set[str] = set().union(*clauses)
    assert caught == policy, (
        f"the cap catch {sorted(caught)} and RESEARCH_SQ_ACT's "
        f"non_retryable_error_types {sorted(policy)} drifted apart — every "
        f"caught-and-degraded cap type must be named non-retryable (or an "
        f"escape retries a persisted, still-exhausted cap) and every "
        f"non-retryable name must be one the handler degrades"
    )

    # Side 2: the recorded replay history (009, captured once). The
    # ScheduleActivity command embeds the policy list, so an edit to
    # RESEARCH_SQ_ACT desynchronises code and fixture. SG-1: reconcile by
    # ruling, never by re-recording the fixture.
    history = json.loads(_HISTORY.read_text(encoding="utf-8"))
    scheduled = [
        ev.get("activityTaskScheduledEventAttributes", {})
        for ev in history.get("history", {}).get("events", [])
    ]
    sq_schedules = [
        attrs
        for attrs in scheduled
        if attrs.get("activityType", {}).get("name") == "research_subquestion"
    ]
    assert sq_schedules, (
        f"{_HISTORY} schedules no research_subquestion — the fixture no "
        f"longer exercises this activity; that is fixture drift, not a "
        f"policy change (SG-1)"
    )
    for attrs in sq_schedules:
        recorded = set(attrs.get("retryPolicy", {}).get("nonRetryableErrorTypes") or [])
        assert recorded == policy, (
            f"the recorded history's retryPolicy carries {sorted(recorded)} "
            f"but RESEARCH_SQ_ACT now names {sorted(policy)} — the replay "
            f"fixture disagrees with the code; SG-1 forbids re-recording, "
            f"so this is an orchestrator ruling, not a regeneration"
        )
