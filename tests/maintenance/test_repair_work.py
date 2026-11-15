"""US1 contract: ``repair_work_for`` authors work from a plan's actions (023b T017, RED).

Subject: ``sdlc.tidyup.backlog.repair_work_for(identity, finding, signal_version,
actions) -> SeededWork`` (NEW, beside ``seeded_work_for``; R12, B-FR-003).

Pinned by R12:
1. Exactly one plan task, whose acceptance criterion names the finding's signal,
   rule and version (the ``seeded_work_for`` criterion formula).
2. The task lists EVERY ``code_fix`` action's summary, in order. No ``ops`` action
   text appears anywhere in the returned work.
3. The description never says "Change nothing else". That sentence belongs to
   ``seeded_work_for`` alone, because multi-action work cannot promise it.
4. Deterministic: equal inputs give equal ``model_dump(mode="json")``.

``seeded_work_for`` itself is unchanged. Its existing tests in
``tests/test_tidyup_backlog.py`` are the check, and they pass at HEAD.

Each test imports ``repair_work_for`` inside its body. Before T018 each case
fails per test with ImportError, not at collection.
"""

from __future__ import annotations

from sdlc.maintenance.models import RepairAction
from sdlc.triage.models import TriageFinding
from tests.maintenance.conftest import env_file_findings

IDENTITY = "secrets:env_file_tracked:.gitignore"
SIGNAL_VERSION = 3


def _finding() -> TriageFinding:
    # env_file_findings()[1] is the mechanical half (.gitignore, env_file_tracked).
    return env_file_findings()[1]


def _code(summary: str, *paths: str) -> RepairAction:
    return RepairAction(kind="code_fix", summary=summary, target_paths=list(paths))


def _ops(summary: str) -> RepairAction:
    return RepairAction(kind="ops", summary=summary, ops_action="restart")


def _all_text(work) -> str:
    """Everything the task carries that a reviewer or harness would read."""
    task = work.plan.tasks[0]
    return "\n".join([task.title, task.description, *task.acceptance_criteria])


def test_returns_exactly_one_plan_task():
    from sdlc.tidyup.backlog import repair_work_for

    work = repair_work_for(
        IDENTITY,
        _finding(),
        SIGNAL_VERSION,
        [_code("remove .env from the index", ".env")],
    )
    assert len(work.plan.tasks) == 1


def test_acceptance_criterion_names_the_signal_rule_and_version():
    from sdlc.tidyup.backlog import repair_work_for

    f = _finding()
    work = repair_work_for(
        IDENTITY,
        f,
        SIGNAL_VERSION,
        [_code("remove .env from the index", ".env")],
    )
    criteria = " ".join(work.plan.tasks[0].acceptance_criteria)
    assert f.signal in criteria
    assert f.rule in criteria
    assert f"v{SIGNAL_VERSION}" in criteria


def test_description_lists_two_code_fix_summaries_in_order():
    from sdlc.tidyup.backlog import repair_work_for

    first = "remove .env from the index"
    second = "add .env to .gitignore"
    work = repair_work_for(
        IDENTITY,
        _finding(),
        SIGNAL_VERSION,
        [_code(first, ".env"), _code(second, ".gitignore")],
    )
    text = _all_text(work)
    assert first in text
    assert second in text
    assert text.index(first) < text.index(second)


def test_description_lists_three_code_fix_summaries_in_order():
    from sdlc.tidyup.backlog import repair_work_for

    summaries = [
        "remove .env from the index",
        "add .env to .gitignore",
        "rotate the exposed token in the sample config",
    ]
    work = repair_work_for(
        IDENTITY,
        _finding(),
        SIGNAL_VERSION,
        [_code(s, ".env") for s in summaries],
    )
    text = _all_text(work)
    positions = [text.index(s) for s in summaries]
    assert positions == sorted(positions)


def test_no_ops_action_appears_anywhere_in_the_returned_work():
    from sdlc.tidyup.backlog import repair_work_for

    ops_summary = "restart the production worker pool"
    work = repair_work_for(
        IDENTITY,
        _finding(),
        SIGNAL_VERSION,
        [_code("remove .env from the index", ".env"), _ops(ops_summary)],
    )
    assert ops_summary not in _all_text(work)


def test_description_never_says_change_nothing_else():
    from sdlc.tidyup.backlog import repair_work_for

    work = repair_work_for(
        IDENTITY,
        _finding(),
        SIGNAL_VERSION,
        [_code("remove .env from the index", ".env"), _code("add .env to .gitignore")],
    )
    assert "Change nothing else" not in _all_text(work)


def test_is_deterministic_for_equal_inputs():
    from sdlc.tidyup.backlog import repair_work_for

    actions = [_code("remove .env from the index", ".env"), _code("add .env to .gitignore")]
    first = repair_work_for(IDENTITY, _finding(), SIGNAL_VERSION, actions)
    second = repair_work_for(IDENTITY, _finding(), SIGNAL_VERSION, actions)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_code_fix_with_target_paths_authors_a_valid_work():
    """R12 does not pin files_hint: only that the work is produced and valid."""
    from sdlc.tidyup.backlog import repair_work_for

    work = repair_work_for(
        IDENTITY,
        _finding(),
        SIGNAL_VERSION,
        [_code("remove .env from the index", ".env", "config/settings.ini")],
    )
    assert len(work.plan.tasks) == 1


# ---------------------------------------------------------- EDGE (023b T017, RED) -- qa-chaos


def test_ops_only_actions_return_a_total_work_with_no_action_summaries():
    """Edge: the pure function is total. An ops-only list does not crash, and the
    single task carries the criterion but no ops summary text."""
    from sdlc.tidyup.backlog import repair_work_for

    ops_summary = "restart the production worker pool"
    f = _finding()
    work = repair_work_for(IDENTITY, f, SIGNAL_VERSION, [_ops(ops_summary)])

    assert len(work.plan.tasks) == 1
    criteria = " ".join(work.plan.tasks[0].acceptance_criteria)
    assert f.signal in criteria
    assert f.rule in criteria
    assert f"v{SIGNAL_VERSION}" in criteria
    assert ops_summary not in _all_text(work)


def test_criterion_falls_back_to_the_repository_when_the_finding_has_no_path():
    """Edge: a finding with no path names 'the repository', the same fallback
    seeded_work_for uses, in the acceptance criterion."""
    from sdlc.tidyup.backlog import repair_work_for

    f = _finding().model_copy(update={"path": None})
    work = repair_work_for(
        IDENTITY,
        f,
        SIGNAL_VERSION,
        [_code("remove .env from the index", ".env")],
    )
    criteria = " ".join(work.plan.tasks[0].acceptance_criteria)
    assert "`the repository`" in criteria
    assert "None" not in criteria
