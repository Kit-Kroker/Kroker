"""026 T011 (research R4 part 1): scoped lint moves to a stage-neutral module.

`_lint_nc`, `_lint_point`, `_policy_and_suppressions`, `_lint_key`,
`scoped_lint`, `LintFinding` and `ScopedLintReport` move UNCHANGED from
`sdlc.stages.merge.{scoping,models}` to `sdlc.toolchain.lint_scope`, so the
per-task path (qa) can call it without importing another stage. Merge
re-imports and re-exports the same objects; the JSON wire format holds.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.measurement import CollectionState
from sdlc.toolchain import lint_scope

MOVED_FUNCTIONS = (
    "_lint_nc",
    "_lint_point",
    "_policy_and_suppressions",
    "_lint_key",
    "scoped_lint",
)
MOVED_MODELS = ("LintFinding", "ScopedLintReport")
WIRE_KEYS = {
    "state",
    "reason",
    "introduced",
    "preexisting",
    "resolved",
    "policy_paths_changed",
    "suppressions_added",
}


# --- identity: re-exported, not copied -------------------------------------


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_scoping_reexports_the_moved_function(name):
    from sdlc.stages.merge import scoping

    assert getattr(scoping, name) is getattr(lint_scope, name)


@pytest.mark.parametrize("name", MOVED_MODELS)
def test_merge_models_reexports_the_moved_model(name):
    from sdlc.stages.merge import models

    assert getattr(models, name) is getattr(lint_scope, name)


def test_merge_activities_still_import_scoped_lint_from_scoping():
    from sdlc.stages.merge import activities

    assert activities.scoped_lint is lint_scope.scoped_lint


@pytest.mark.parametrize("name", MOVED_FUNCTIONS + MOVED_MODELS)
def test_moved_object_is_defined_in_lint_scope(name):
    assert getattr(lint_scope, name).__module__ == "sdlc.toolchain.lint_scope"


# --- behavior snapshot: the move changed nothing -------------------------


def _measured():
    return lint_scope.ScopedLintReport(
        state=CollectionState.MEASURED,
        introduced=[lint_scope.LintFinding(rule="I001", path="a.py", line="x")],
        preexisting=2,
        resolved=1,
        policy_paths_changed=["pyproject.toml"],
        suppressions_added=1,
    )


def test_measured_report_round_trips_with_the_same_wire_keys():
    report = _measured()
    text = report.model_dump_json()
    assert set(json.loads(text)) == WIRE_KEYS
    assert json.loads(text)["introduced"] == [{"rule": "I001", "path": "a.py", "line": "x"}]
    assert lint_scope.ScopedLintReport.model_validate_json(text) == report


def test_moved_report_reads_json_the_merge_model_wrote():
    """The wire format crosses the move: merge's name parses lint_scope's JSON."""
    from sdlc.stages.merge.models import ScopedLintReport as MergeReport

    assert MergeReport.model_validate_json(_measured().model_dump_json()) == _measured()


def test_not_collected_without_a_reason_fails_closed():
    with pytest.raises(ValidationError, match="requires a reason"):
        lint_scope.ScopedLintReport(state=CollectionState.NOT_COLLECTED)


def test_not_collected_carrying_findings_fails_closed():
    with pytest.raises(ValidationError, match="must not carry"):
        lint_scope.ScopedLintReport(
            state=CollectionState.NOT_COLLECTED,
            reason="lint tool failed",
            introduced=[lint_scope.LintFinding(rule="I001", path="a.py", line="x")],
        )


def test_not_collected_with_a_reason_round_trips_empty():
    report = lint_scope.ScopedLintReport(state=CollectionState.NOT_COLLECTED, reason="no base")
    again = lint_scope.ScopedLintReport.model_validate_json(report.model_dump_json())
    assert again == report
    assert again.introduced == []
    assert again.state is CollectionState.NOT_COLLECTED


def test_lint_nc_builds_a_not_collected_report():
    report = lint_scope._lint_nc("why")
    assert (report.state, report.reason, report.introduced) == (
        CollectionState.NOT_COLLECTED,
        "why",
        [],
    )


def test_lint_key_is_the_ds3_identity():
    f = lint_scope.LintFinding(rule="E501", path="pkg/m.py", line="x = 1")
    assert lint_scope._lint_key(f) == ("lint", "E501", "pkg/m.py", "x = 1")


@pytest.mark.asyncio
async def test_scoped_lint_without_a_base_is_not_collected_and_names_why():
    report = await lint_scope.scoped_lint(
        adapter=None,  # never touched: the base check returns first
        head_wt="/nowhere",
        base_wt=None,
        base_reason="clone failed",
        base_sha="abc",
        renames=[],
        env=None,
        timeout_s=1,
    )
    assert report.state is CollectionState.NOT_COLLECTED
    assert report.reason == "base not materialized: clone failed"


# --- source guard: stage-neutral -----------------------------------------


def _imported_modules(source: str, package: str) -> set[str]:
    """Every imported module name, anywhere in the file (function bodies
    included), with relative imports resolved against `package`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = parts[: len(parts) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            found.add(module)
            # `from .. import stages` binds a submodule too
            found.update(f"{module}.{a.name}" for a in node.names)
    return found


def test_import_scanner_resolves_relative_imports():
    src = (
        "from ..stages.qa.activities import x\n"
        "from ..process import _bounded_shell\n"
        "def f():\n"
        "    import sdlc.stages.merge\n"
    )
    mods = _imported_modules(src, "sdlc.toolchain")
    assert "sdlc.stages.qa.activities" in mods
    assert "sdlc.process" in mods
    assert "sdlc.stages.merge" in mods


def test_lint_scope_imports_nothing_from_any_stage():
    path = Path(lint_scope.__file__)
    assert path.name == "lint_scope.py"
    mods = _imported_modules(path.read_text(encoding="utf-8"), "sdlc.toolchain")
    stages = sorted(m for m in mods if m == "sdlc.stages" or m.startswith("sdlc.stages."))
    assert stages == [], f"lint_scope must be stage-neutral; imports {stages}"


# --- chaos / edge cases (026 T011, chaos QA) --------------------------------
#
# Frozen from sdlc.stages.merge.{scoping,models} on 2026-11-18, BEFORE the
# move. After the move, scoping.scoped_lint IS lint_scope.scoped_lint, so
# comparing the two live objects would prove nothing; comparing against the
# pre-move snapshot proves the move changed no signature and no wire byte.

PRE_MOVE_SIGNATURES = {
    "_lint_nc": (False, "(reason: 'str') -> 'ScopedLintReport'"),
    "_lint_point": (
        True,
        "(adapter: 'ToolchainAdapter', wt: 'str', env: 'dict[str, str] | None', "
        "timeout_s: 'int') -> 'list[LintFinding] | str'",
    ),
    "_policy_and_suppressions": (
        False,
        "(adapter: 'ToolchainAdapter', head_wt: 'str', base_sha: 'str') "
        "-> 'tuple[list[str], int] | str'",
    ),
    "_lint_key": (False, "(f: 'LintFinding') -> 'FindingKey'"),
    "scoped_lint": (
        True,
        "(adapter: 'ToolchainAdapter', head_wt: 'str', base_wt: 'str | None', "
        "base_reason: 'str', base_sha: 'str', renames: 'list[list[str]]', "
        "env: 'dict[str, str] | None', timeout_s: 'int') -> 'ScopedLintReport'",
    ),
}

PRE_MOVE_WIRE = (
    '{"state":"measured","reason":"","introduced":['
    '{"rule":"PERF102","path":"pkg/a b.py","line":"for k, v in d.items():"},'
    '{"rule":"I001","path":"m.py","line":"import os, sys"}],'
    '"preexisting":3,"resolved":1,"policy_paths_changed":["pyproject.toml"],'
    '"suppressions_added":2}',
    '{"state":"not_collected","reason":"base not materialized: clone failed",'
    '"introduced":[],"preexisting":0,"resolved":0,"policy_paths_changed":[],'
    '"suppressions_added":0}',
)


@pytest.mark.parametrize("name", sorted(PRE_MOVE_SIGNATURES))
def test_move_only_signature_matches_the_pre_move_snapshot(name):
    import inspect

    fn = getattr(lint_scope, name)
    is_async, sig = PRE_MOVE_SIGNATURES[name]
    assert inspect.iscoroutinefunction(fn) is is_async
    assert str(inspect.signature(fn)) == sig


@pytest.mark.parametrize("wire", PRE_MOVE_WIRE, ids=["measured", "not_collected"])
def test_pre_move_wire_json_loads_and_redumps_byte_identical(wire):
    report = lint_scope.ScopedLintReport.model_validate_json(wire)
    assert report.model_dump_json() == wire
    # and merge's re-exported name reads it the same way
    from sdlc.stages.merge.models import ScopedLintReport as MergeReport

    assert MergeReport.model_validate_json(wire) == report


@pytest.mark.parametrize("banned", ["sdlc.stages.merge", "sdlc.workflows"])
def test_lint_scope_imports_neither_merge_nor_workflows(banned):
    mods = _imported_modules(
        Path(lint_scope.__file__).read_text(encoding="utf-8"), "sdlc.toolchain"
    )
    hits = sorted(m for m in mods if m == banned or m.startswith(banned + "."))
    assert hits == [], f"lint_scope imports {hits}"


@pytest.mark.parametrize(
    ("module", "names"),
    [
        ("sdlc.stages.merge.scoping", MOVED_FUNCTIONS),
        ("sdlc.stages.merge.models", MOVED_MODELS),
    ],
)
def test_merge_reexports_by_import_not_redefinition(module, names):
    """The merge modules import the moved names from lint_scope; none of them
    is defined (def / async def / class / assignment) there any more."""
    import importlib
    import inspect

    tree = ast.parse(inspect.getsource(importlib.import_module(module)))
    defined = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined.update(t.id for t in node.targets if isinstance(t, ast.Name))
    assert defined.isdisjoint(names), f"{module} redefines {sorted(defined & set(names))}"

    imported = {
        alias.asname or alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("lint_scope")
        for alias in node.names
    }
    assert set(names) <= imported, f"{module} does not import {sorted(set(names) - imported)}"


# --- 026 T017: parity proof (US A2 AS3) -------------------------------------
#
# One fixture tree, two call paths: the per-task lint (qa's run_test_suite,
# which materializes its own sibling base) and the merge lint
# (run_integration_checks, given a base worktree). Both run ruff from the same
# ambient env (the stubbed _ensure_python_env below), with the same command
# (adapter.lint_json_cmd()) and the same configuration resolution, so the
# introduced lists must be equal element-wise.

PARITY_BASE_A = "import os\n\n\ndef f():\n    return 1\n"  # pre-existing F401
PARITY_HEAD_B = "import sys\n\n\ndef g():\n    return 2\n"  # the attempt's F401
PARITY_LINT_CMD = "ruff check --output-format json --exit-zero --no-cache ."


@pytest.fixture
def parity_env(monkeypatch):
    """The host python3.14 lacks ensurepip, so venv provisioning fails here
    (see tests/qa/test_task_lint.py). Both paths get the same ambient env,
    which is the parity claim: the same ruff binary by construction."""

    async def ambient(worktree, timeout_s, *, shared=True):
        return None, None

    monkeypatch.setattr("sdlc.stages.qa.activities._ensure_python_env", ambient)
    monkeypatch.setattr("sdlc.stages.merge.activities._ensure_python_env", ambient)


@pytest.fixture
def parity_repo(git_repo):
    """main carries requirements.txt (adapter marker) and a.py (pre-existing
    F401). The task worktree sits at main's tip; the attempt commits b.py."""
    import asyncio

    from sdlc.vcs import IntegrationInput, WorktreeInput, create_worktree, setup_integration_branch
    from sdlc.vcs.git import _git
    from tests.conftest import run_git

    repo = Path(git_repo)
    (repo / "requirements.txt").write_text("\n", encoding="utf-8")
    (repo / "a.py").write_text(PARITY_BASE_A, encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-m", "base"], repo)
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id="run-par", base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id="run-par", task_id="T1", from_ref=setup.head_sha
            )
        )
    )
    Path(wt.path, "b.py").write_text(PARITY_HEAD_B, encoding="utf-8")
    _git(["add", "-A"], wt.path)
    _git(["commit", "-m", "attempt"], wt.path)
    return {"wt": wt.path, "base_sha": setup.head_sha}


def _renames(wt: str, base_sha: str) -> list[list[str]]:
    """The same rename map the per-task path computes from `git diff -M`."""
    from sdlc.vcs.git import _git

    out = _git(["diff", "-M", "--name-status", f"{base_sha}...HEAD"], wt).stdout
    rows = (ln.split("\t") for ln in out.splitlines())
    return [[p[1], p[2]] for p in rows if len(p) == 3 and p[0].startswith("R")]


def _introduced(report) -> list[tuple[str, str, str]]:
    return [(f.rule, f.path, f.line) for f in report.lint.introduced]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_parity_task_and_merge_paths_report_the_same_introduced_list(parity_repo, parity_env):
    """Element-wise equal introduced lists and equal preexisting counts for the
    same base and head, through the two real activities."""
    from sdlc.stages.merge.activities import IntegrationChecksInput, run_integration_checks
    from sdlc.stages.qa.activities import QAInput, run_test_suite
    from sdlc.vcs.integration import materialize_base
    from sdlc.vcs.worktree import _worktrees_root

    wt, base_sha = parity_repo["wt"], parity_repo["base_sha"]
    task = await run_test_suite(
        QAInput(worktree=wt, test_cmd="true", lint_base=base_sha, lint_key="run-par/base-T1")
    )
    merge_base = materialize_base(
        wt, base_sha, os.path.join(_worktrees_root(), "run-par", "merge-base")
    )
    merge = await run_integration_checks(
        IntegrationChecksInput(
            worktree=wt,
            changed_files=["b.py"],
            base_worktree=merge_base.path,
            base_reason=merge_base.reason,
            base_sha=base_sha,
            renames=_renames(wt, base_sha),
        )
    )

    assert task.lint is not None and merge.lint is not None
    assert task.lint.state is CollectionState.MEASURED
    assert merge.lint.state is CollectionState.MEASURED
    assert _introduced(task) == _introduced(merge) == [("F401", "b.py", "import sys")]
    assert task.lint.preexisting == merge.lint.preexisting >= 1


def test_parity_both_paths_resolve_the_same_adapter_and_command(parity_repo):
    """Fast, no ruff run: both paths resolve the one PYTHON adapter instance,
    its lint command is the exact one both scoped paths run, and both reach
    the moved scoped_lint (by identity; merge goes through scoping's re-export,
    pinned by T011)."""
    import sdlc.stages.merge.activities as merge_act
    import sdlc.stages.qa.activities as qa_act
    from sdlc.toolchain.adapters import TOOLCHAINS, ToolchainKind, detect

    wt = parity_repo["wt"]
    adapter = detect(wt)
    assert adapter is TOOLCHAINS[ToolchainKind.PYTHON]
    assert detect(wt) is adapter  # the same object on every call
    assert adapter.lint_json_cmd() == PARITY_LINT_CMD

    assert qa_act.scoped_lint is lint_scope.scoped_lint
    assert merge_act.scoped_lint is lint_scope.scoped_lint

    qa_src = inspect.getsource(qa_act._task_scoped_lint)
    merge_src = inspect.getsource(merge_act.run_integration_checks)
    assert "detect(inp.worktree)" in qa_src
    assert "detect(inp.worktree)" in merge_src
    assert "scoped_lint(" in qa_src and "scoped_lint(" in merge_src


@pytest.mark.asyncio
@pytest.mark.slow
async def test_parity_unmeasured_paths_both_report_not_collected(parity_repo, parity_env):
    """An unresolvable base: the task path reports NOT_COLLECTED and the task
    still passes (never fails a task); the merge path, with no base worktree,
    reports NOT_COLLECTED too and fails closed at merge."""
    from sdlc.stages.merge.activities import IntegrationChecksInput, run_integration_checks
    from sdlc.stages.qa.activities import QAInput, run_test_suite

    wt, base_sha = parity_repo["wt"], parity_repo["base_sha"]
    task = await run_test_suite(
        QAInput(worktree=wt, test_cmd="true", lint_base="de" * 20, lint_key="run-par/base-T1")
    )
    merge = await run_integration_checks(
        IntegrationChecksInput(
            worktree=wt,
            changed_files=["b.py"],
            base_worktree=None,
            base_reason="clone failed",
            base_sha=base_sha,
            renames=[],
        )
    )

    assert task.tests_passed is True
    for label, lint in (("task", task.lint), ("merge", merge.lint)):
        assert lint is not None, label
        assert lint.state is CollectionState.NOT_COLLECTED, label
        assert lint.reason, label
        assert lint.introduced == [], label


# --- chaos / edge cases (026 T017, chaos QA): parity edges -------------------
#
# Both paths run the same ruff from the same stubbed env, so these must PASS
# on the implemented move. A failure here means the two paths diverged.

LONG_LINE = 'VALUE = "this line is deliberately longer than forty columns"\n'


async def _base_and_worktree(git_repo, run_id: str, base_files: dict[str, str]) -> tuple[str, str]:
    """A base commit with `base_files` (plus a Python marker) and a task
    worktree at its tip. Returns (worktree path, base sha)."""
    from sdlc.vcs import IntegrationInput, WorktreeInput, create_worktree, setup_integration_branch
    from tests.conftest import run_git

    repo = Path(git_repo)
    (repo / "requirements.txt").write_text("\n", encoding="utf-8")
    for rel, text in base_files.items():
        (repo / rel).write_text(text, encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-m", "base"], repo)
    setup = await setup_integration_branch(
        IntegrationInput(repo_path=git_repo, run_id=run_id, base_branch="main")
    )
    wt = await create_worktree(
        WorktreeInput(repo_path=git_repo, run_id=run_id, task_id="T1", from_ref=setup.head_sha)
    )
    return wt.path, setup.head_sha


async def _both_paths(wt: str, base_sha: str, run_id: str, changed: list[str]):
    """Run the per-task path and the merge path on the same base and head."""
    from sdlc.stages.merge.activities import IntegrationChecksInput, run_integration_checks
    from sdlc.stages.qa.activities import QAInput, run_test_suite
    from sdlc.vcs.integration import materialize_base
    from sdlc.vcs.worktree import _worktrees_root

    task = await run_test_suite(
        QAInput(worktree=wt, test_cmd="true", lint_base=base_sha, lint_key=f"{run_id}/base-T1")
    )
    merge_base = materialize_base(
        wt, base_sha, os.path.join(_worktrees_root(), run_id, "merge-base")
    )
    merge = await run_integration_checks(
        IntegrationChecksInput(
            worktree=wt,
            changed_files=changed,
            base_worktree=merge_base.path,
            base_reason=merge_base.reason,
            base_sha=base_sha,
            renames=_renames(wt, base_sha),
        )
    )
    return task, merge


@pytest.mark.asyncio
@pytest.mark.slow
async def test_parity_rename_keeps_a_base_finding_preexisting_on_both_paths(git_repo, parity_env):
    """The base's a.py has F401. The attempt only renames it to new_name.py with
    the same line. Both paths consume the same `git diff -M` rename map, so the
    finding is preexisting on both and the two introduced lists match (empty)."""
    from sdlc.vcs.git import _git

    wt, base_sha = await _base_and_worktree(git_repo, "run-ren", {"a.py": PARITY_BASE_A})
    _git(["mv", "a.py", "new_name.py"], wt)
    _git(["commit", "-m", "rename"], wt)
    assert _renames(wt, base_sha) == [["a.py", "new_name.py"]]  # the rename is really there

    task, merge = await _both_paths(wt, base_sha, "run-ren", ["new_name.py"])

    assert task.lint.state is merge.lint.state is CollectionState.MEASURED
    assert _introduced(task) == _introduced(merge) == []
    assert task.lint.preexisting == merge.lint.preexisting >= 1


def test_parity_report_only_filter_lives_only_in_attempt_failure():
    """The fence is applied in code/attempt_failure._lint_ok, never in a lint
    path. The per-task lint and the merge lint both report every finding, and
    merge has no report-only concept at all."""
    import sdlc.stages.merge.activities as merge_act
    import sdlc.stages.qa.activities as qa_act

    assert "lint_report_only" not in inspect.getsource(qa_act._task_scoped_lint)
    assert "report_only" not in inspect.getsource(merge_act.run_integration_checks)
    merge_file = Path(merge_act.__file__).read_text(encoding="utf-8")
    assert "report_only" not in merge_file


@pytest.mark.asyncio
@pytest.mark.slow
async def test_parity_repo_own_ruff_config_is_honored_identically(git_repo, parity_env):
    """The repo's own ruff.toml (committed in the base, so not a policy change)
    selects E501 with a 40-column limit, a non-default rule. Both paths resolve
    the same configuration and report the same introduced finding."""
    ruff_toml = 'line-length = 40\n[lint]\nselect = ["E501"]\n'
    wt, base_sha = await _base_and_worktree(
        git_repo, "run-cfg", {"a.py": "x = 1\n", "ruff.toml": ruff_toml}
    )
    Path(wt, "b.py").write_text(LONG_LINE, encoding="utf-8")
    from sdlc.vcs.git import _git

    _git(["add", "-A"], wt)
    _git(["commit", "-m", "attempt"], wt)

    task, merge = await _both_paths(wt, base_sha, "run-cfg", ["b.py"])

    assert task.lint.state is merge.lint.state is CollectionState.MEASURED
    assert _introduced(task) == _introduced(merge)
    assert [(rule, path) for rule, path, _ in _introduced(task)] == [("E501", "b.py")]
