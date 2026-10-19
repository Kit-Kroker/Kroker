"""Pins for the research sub-question retry policy (T4, sbatch-2026-10-19).

``RESEARCH_SQ_ACT`` names ``BudgetExceeded`` / ``UsageLimitExceeded``
non-retryable, yet the activity handler catches both and returns a
degraded finding — the workflow-side list is dead code TODAY, and the
batch decision (spec T4) is to KEEP it. Two keep-reasons:

1. belt-and-braces: a future handler refactor that narrows the catch
   would otherwise burn the activity's 6 attempts against a persisted,
   already-exhausted budget cap — the exact guaranteed-failure retry the
   handler's degrade comment exists to prevent;
2. replay: tests/replay/histories/research_retain_grounded.json embeds
   ``nonRetryableErrorTypes [BudgetExceeded, UsageLimitExceeded]`` in the
   recorded ScheduleActivity command for research_subquestion; removing
   the list changes the command and breaks the never-re-recorded replay
   tier (SG-1 territory).

Both pins PASS on main by design — this is a decision pin, not a RED
test. The first fails loudly if anyone removes the list without reading
this file; the second pins the FACT the decision rests on (the handler
really does catch both), so a future removal of that catch flips the
pairing this file guards: the list goes live again and the keep/drop
decision must be revisited, not assumed.
"""

from __future__ import annotations

import ast
import inspect

from sdlc.stages.research.step import RESEARCH_SQ_ACT

_EXPECTED = ["BudgetExceeded", "UsageLimitExceeded"]


def test_sq_non_retryable_error_types_are_pinned():
    """The list stays exactly [BudgetExceeded, UsageLimitExceeded].

    It is dead today (the handler catches both and degrades — see the
    companion pin), and it stays anyway: belt-and-braces against a future
    handler refactor that re-raises into a persisted exhausted cap, and
    the recorded ScheduleActivity command in
    tests/replay/histories/research_retain_grounded.json embeds these
    exact nonRetryableErrorTypes (SG-1). Removing or reordering them is a
    decision change, not a cleanup.
    """
    policy = RESEARCH_SQ_ACT["retry_policy"]
    assert list(policy.non_retryable_error_types) == _EXPECTED, (
        f"RESEARCH_SQ_ACT retry policy changed to "
        f"{policy.non_retryable_error_types!r}; the pin "
        "expects exactly ['BudgetExceeded', 'UsageLimitExceeded'] — read this "
        "file's docstring (belt-and-braces + replay history) before touching it"
    )


def test_the_handler_still_catches_both_cap_stops():
    """The list's deadness is a FACT at pin time: _research_subquestion_impl
    has an except clause naming BOTH BudgetExceeded and UsageLimitExceeded
    and never re-raises them (it degrades). If someone removes or narrows
    that catch, this pin fires: the non-retryable list goes live again and
    the KEEP decision documented above is stale — revisit it, don't ride it.
    """
    from sdlc.stages.research import stage as research_stage

    src = inspect.getsource(research_stage._research_subquestion_impl)
    caught: list[set[str]] = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            t = handler.type
            if t is None:
                continue
            names = t.elts if isinstance(t, ast.Tuple) else [t]
            caught.append({n.id for n in names if isinstance(n, ast.Name)})
    assert {"BudgetExceeded", "UsageLimitExceeded"} in caught, (
        "no except clause in _research_subquestion_impl catches both "
        "BudgetExceeded and UsageLimitExceeded — the pairing this file pins "
        "has changed: either the degrade path moved (update this pin AND the "
        "dead-list decision) or the catch was narrowed (the list is live "
        "again; revisit the KEEP decision)"
    )
