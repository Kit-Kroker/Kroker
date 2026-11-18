"""026 T014 (FR-010/011, research R4 part 3): the per-task lint delta.

run_test_suite gains an optional lint pass: when `lint_base` names a base
commit, the head worktree and a disposable base worktree are linted with the
SAME binary and configuration (the merge gate's scoped_lint), and the delta
lands on `QAReport.lint`. Tests run first, exactly as today.

Finding: F401 (unused import). It is in ruff's default rule set, so the
fixture needs no config. PERF102 was the brief's first pick, but it is not in
the default set, and a `select = ["PERF"]` config would make the fixture
depend on a repo-owned config rather than on defaults.

Fixture: a Python repo (requirements.txt marker, so the adapter is detected)
with a base commit containing `a.py` (pre-existing F401). The task worktree
then commits `b.py` with a NEW F401. Test commands are shell `echo`/`true`,
so no venv is needed for the non-lint paths.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.qa.activities import QAInput, run_test_suite
from sdlc.vcs import IntegrationInput, WorktreeInput, create_worktree, setup_integration_branch
from sdlc.vcs.git import _git
from sdlc.vcs.worktree import _worktrees_root
from tests.conftest import run_git

BASE_A = "import os\n\n\ndef f():\n    return 1\n"  # pre-existing F401 (os)
HEAD_B = "import sys\n\n\ndef g():\n    return 2\n"  # the attempt's NEW F401 (sys)
PASSING = "true"  # a test command that passes and writes nothing


@pytest.fixture
def task_repo(git_repo, request):
    """main carries requirements.txt and a.py; a task worktree sits at main's
    tip, and the base sha is that tip. The attempt's commit adds b.py."""
    repo = Path(git_repo)
    # The marker makes the adapter (and the venv provisioning) real; a
    # no-lint test opts out so it never builds a venv.
    if getattr(request, "param", True):
        (repo / "requirements.txt").write_text("\n", encoding="utf-8")
    (repo / "a.py").write_text(BASE_A, encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-m", "base"], repo)
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-tl", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id="run-tl", task_id="T1", from_ref=setup.head_sha
            )
        )
    )
    return {"repo": git_repo, "wt": wt.path, "base_sha": setup.head_sha}


def _attempt(wt: str, base_sha: str) -> str:
    """The attempt's own commit: adds b.py. Returns the head sha."""
    Path(wt, "b.py").write_text(HEAD_B, encoding="utf-8")
    _git(["add", "-A"], wt)
    _git(["commit", "-m", "attempt"], wt)
    return _git(["rev-parse", "HEAD"], wt).stdout.strip()


def _run(**kw):
    return run_test_suite(QAInput(**kw))


# --- (1) no lint_base: lint absent, tests exactly as today -------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("task_repo", [False], indirect=True)
async def test_without_lint_base_tests_pass_and_lint_is_absent(task_repo):
    _attempt(task_repo["wt"], task_repo["base_sha"])
    report = await _run(worktree=task_repo["wt"], test_cmd=PASSING)
    assert report.tests_passed is True
    assert report.lint is None


# --- (2) the delta: exactly the attempt's new finding ------------------------


@pytest.mark.asyncio
@pytest.mark.slow
async def test_lint_delta_holds_exactly_the_new_finding(task_repo):
    _attempt(task_repo["wt"], task_repo["base_sha"])
    report = await _run(
        worktree=task_repo["wt"],
        test_cmd=PASSING,
        lint_base=task_repo["base_sha"],
        lint_key="run-tl/T1",
    )
    assert report.lint is not None
    assert report.lint.state is CollectionState.MEASURED
    assert [(f.rule, f.path) for f in report.lint.introduced] == [("F401", "b.py")]
    assert report.lint.introduced[0].line == "import sys"
    assert report.lint.preexisting >= 1  # the base's a.py finding is not introduced


# --- (3) the base is a sibling under the worktrees root, removed afterwards --


@pytest.mark.asyncio
@pytest.mark.slow
async def test_base_worktree_is_a_sibling_under_the_root_and_is_removed(task_repo, monkeypatch):
    import sdlc.toolchain.lint_scope as lint_scope

    _attempt(task_repo["wt"], task_repo["base_sha"])
    seen: dict[str, str] = {}
    real = lint_scope.scoped_lint
    sig = inspect.signature(real)

    async def spy(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        base_wt = bound.arguments["base_wt"]
        seen["base"] = base_wt
        seen["existed_during"] = os.path.isdir(base_wt) if base_wt else False
        return await real(*args, **kwargs)

    monkeypatch.setattr("sdlc.stages.qa.activities.scoped_lint", spy, raising=False)

    await _run(worktree=task_repo["wt"], test_cmd=PASSING, lint_base=task_repo["base_sha"])

    base = seen.get("base")
    assert base, "scoped_lint was never handed a base worktree"
    assert seen["existed_during"] is True
    root = Path(_worktrees_root()).resolve()
    base_p = Path(base).resolve()
    assert root in base_p.parents  # under the worktrees root, never /tmp
    assert base_p.parent == Path(task_repo["wt"]).resolve().parent  # a sibling
    assert not base_p.exists()  # removed in the finally


# --- (4) an unmaterializable base: NOT_COLLECTED, tests unaffected ----------


@pytest.mark.asyncio
@pytest.mark.slow
async def test_unresolvable_base_is_not_collected_and_tests_still_pass(task_repo):
    _attempt(task_repo["wt"], task_repo["base_sha"])
    report = await _run(worktree=task_repo["wt"], test_cmd=PASSING, lint_base="de" * 20)
    assert report.tests_passed is True
    assert report.lint is not None
    assert report.lint.state is CollectionState.NOT_COLLECTED
    assert report.lint.reason  # says why
    assert report.lint.introduced == []


# --- (5) report-only paths: present in the report, not filtered here --------


@pytest.mark.asyncio
@pytest.mark.slow
async def test_report_only_paths_stay_in_the_report_not_filtered_here(task_repo):
    _attempt(task_repo["wt"], task_repo["base_sha"])
    plain = await _run(worktree=task_repo["wt"], test_cmd=PASSING, lint_base=task_repo["base_sha"])
    fenced = await _run(
        worktree=task_repo["wt"],
        test_cmd=PASSING,
        lint_base=task_repo["base_sha"],
        lint_report_only=["b.py"],
    )
    assert [f.path for f in fenced.lint.introduced] == ["b.py"]
    assert fenced.lint.introduced == plain.lint.introduced  # T016 filters, not run_test_suite


# --- (6) order: tests run before lint, same verdict with or without lint ----


@pytest.mark.asyncio
@pytest.mark.slow
async def test_tests_run_before_lint_and_the_verdict_is_unchanged(task_repo, monkeypatch, tmp_path):
    import sdlc.toolchain.lint_scope as lint_scope

    _attempt(task_repo["wt"], task_repo["base_sha"])
    marker = tmp_path / "order.txt"
    real = lint_scope.scoped_lint

    async def spy(*args, **kwargs):
        with marker.open("a", encoding="utf-8") as fh:
            fh.write("lint\n")
        return await real(*args, **kwargs)

    monkeypatch.setattr("sdlc.stages.qa.activities.scoped_lint", spy, raising=False)
    cmd = f"echo tests >> {marker}"

    with_lint = await _run(worktree=task_repo["wt"], test_cmd=cmd, lint_base=task_repo["base_sha"])
    assert marker.read_text(encoding="utf-8").splitlines() == ["tests", "lint"]

    marker.unlink()
    without = await _run(worktree=task_repo["wt"], test_cmd=cmd)
    assert with_lint.tests_passed is without.tests_passed is True
    assert with_lint.failing_tests == without.failing_tests == []


# --- chaos / edge cases (026 T014, chaos QA) --------------------------------
#
# Every lint-path test here provisions the venv, so it is slow-marked like
# the rest of this file. The no-marker case opts out of the marker (indirect
# param False) and never builds one.


def _spy_bases(monkeypatch) -> list[str]:
    """Record the base_wt handed to scoped_lint on each call (still runs it)."""
    import sdlc.toolchain.lint_scope as lint_scope

    seen: list[str] = []
    real = lint_scope.scoped_lint
    sig = inspect.signature(real)

    async def spy(*args, **kwargs):
        base = sig.bind(*args, **kwargs).arguments["base_wt"]
        if base:
            seen.append(base)
        return await real(*args, **kwargs)

    monkeypatch.setattr("sdlc.stages.qa.activities.scoped_lint", spy, raising=False)
    return seen


@pytest.mark.asyncio
@pytest.mark.slow
async def test_edge_same_lint_key_twice_is_idempotent_and_leaves_no_base(task_repo, monkeypatch):
    """Two sequential calls with one lint_key both measure, and each base
    dir is gone afterwards, so the second never trips on 'already exists'."""
    _attempt(task_repo["wt"], task_repo["base_sha"])
    bases = _spy_bases(monkeypatch)
    kw = {"worktree": task_repo["wt"], "test_cmd": PASSING, "lint_base": task_repo["base_sha"]}

    first = await _run(**kw, lint_key="run-tl/T1")
    second = await _run(**kw, lint_key="run-tl/T1")

    assert first.lint.state is second.lint.state is CollectionState.MEASURED
    assert second.lint.introduced == first.lint.introduced
    assert len(bases) == 2
    assert not any(os.path.exists(b) for b in bases)


@pytest.mark.asyncio
@pytest.mark.parametrize("task_repo", [False], indirect=True)
async def test_edge_no_python_marker_means_no_lint_and_tests_still_run(task_repo):
    """detect() is None without a marker: no adapter, no lint run. Per-task
    lint is a Python-only contract; the tests still run exactly as today."""
    _attempt(task_repo["wt"], task_repo["base_sha"])
    report = await _run(worktree=task_repo["wt"], test_cmd=PASSING, lint_base=task_repo["base_sha"])
    assert report.tests_passed is True
    assert report.lint is None


@pytest.mark.asyncio
@pytest.mark.slow
async def test_edge_test_failure_and_introduced_finding_both_surface(task_repo):
    """A failing suite does not hide the lint delta, and a lint finding does
    not change the test verdict: the two are independent surfaces."""
    _attempt(task_repo["wt"], task_repo["base_sha"])
    failing_cmd = "echo 'FAILED tests/test_b.py::test_g - boom' && exit 1"

    alone = await _run(worktree=task_repo["wt"], test_cmd=failing_cmd)
    both = await _run(
        worktree=task_repo["wt"], test_cmd=failing_cmd, lint_base=task_repo["base_sha"]
    )

    assert both.tests_passed is False
    assert both.failing_tests == alone.failing_tests != []
    assert both.lint is not None
    assert both.lint.state is CollectionState.MEASURED
    assert [(f.rule, f.path) for f in both.lint.introduced] == [("F401", "b.py")]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_edge_empty_report_only_list_matches_none(task_repo):
    """An empty fence list filters nothing: the report keeps every introduced
    finding, exactly as it does with the argument omitted."""
    _attempt(task_repo["wt"], task_repo["base_sha"])
    omitted = await _run(
        worktree=task_repo["wt"], test_cmd=PASSING, lint_base=task_repo["base_sha"]
    )
    empty = await _run(
        worktree=task_repo["wt"],
        test_cmd=PASSING,
        lint_base=task_repo["base_sha"],
        lint_report_only=[],
    )
    assert [f.path for f in empty.lint.introduced] == ["b.py"]
    assert empty.lint.introduced == omitted.lint.introduced


@pytest.mark.asyncio
@pytest.mark.slow
async def test_edge_rename_keeps_a_base_finding_preexisting(task_repo):
    """The base's a.py carries F401. The attempt renames it to new_name.py
    with the same line. Renames from `git diff -M` must map the head path
    back, so the finding is PREEXISTING, never introduced."""
    wt = task_repo["wt"]
    _git(["mv", "a.py", "new_name.py"], wt)
    _git(["commit", "-m", "rename"], wt)

    report = await _run(worktree=wt, test_cmd=PASSING, lint_base=task_repo["base_sha"])

    assert report.lint is not None
    assert report.lint.state is CollectionState.MEASURED
    assert report.lint.introduced == []
    assert report.lint.preexisting >= 1
