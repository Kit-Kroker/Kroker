"""026 T011 (research R4 part 1): scoped lint moves to a stage-neutral module.

`_lint_nc`, `_lint_point`, `_policy_and_suppressions`, `_lint_key`,
`scoped_lint`, `LintFinding` and `ScopedLintReport` move UNCHANGED from
`sdlc.stages.merge.{scoping,models}` to `sdlc.toolchain.lint_scope`, so the
per-task path (qa) can call it without importing another stage. Merge
re-imports and re-exports the same objects; the JSON wire format holds.
"""

from __future__ import annotations

import ast
import json
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
