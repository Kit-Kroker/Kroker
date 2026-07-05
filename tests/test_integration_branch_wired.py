"""ADR-14 wiring: FeatureWorkflow must drive a single integration branch
that accumulates completed task work; each task branches from the current
integration head and merges back on success. Tests are AST-based (matching
the project's structural-purity convention — see test_factory_purity.py)."""
import ast
import pathlib

import pytest

SRC = pathlib.Path("src/sdlc/workflows/feature.py")
ACT = pathlib.Path("src/sdlc/activities.py")


@pytest.fixture(scope="module")
def feature_src():
    return SRC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def feature_tree(feature_src):
    return ast.parse(feature_src)


def _fn(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name:
            return n
    raise AssertionError(f"function {name} not found")


def test_workflow_calls_setup_integration_branch(feature_src):
    assert "setup_integration_branch" in feature_src, (
        "FeatureWorkflow.run must call setup_integration_branch at run start")


def test_workflow_calls_merge_into_integration(feature_src):
    assert "merge_into_integration" in feature_src, (
        "on task completion, run_one must merge the task branch back into "
        "the integration branch (ADR-14)")


def test_dev_task_branches_from_integration_head(feature_src):
    """`from_ref` passed to create_worktree must not be idea.base_branch."""
    # The wiring passes self._integration_head, not idea.base_branch, as
    # the from_ref into _dev_task.
    assert "_integration_head" in feature_src


def test_integration_handle_dataclass_returned_by_setup_activity():
    """Resolution A: setup_integration_branch returns IntegrationHandle,
    not a bare SHA string — the workflow needs the worktree path too."""
    src = ACT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls_names = {n.name for n in ast.walk(tree)
                 if isinstance(n, ast.ClassDef)}
    assert "IntegrationHandle" in cls_names, (
        "activities.py must define an IntegrationHandle dataclass "
        "(Resolution A: workflow needs the worktree path)")


def test_integration_handle_has_head_sha_and_worktree_path():
    src = ACT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "IntegrationHandle")
    fields = {t.target.id for t in cls.body
              if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)}
    assert {"head_sha", "worktree_path"}.issubset(fields), (
        f"IntegrationHandle must expose head_sha and worktree_path; "
        f"found {sorted(fields)}")


def test_workflow_threads_worktree_path_not_repo_path(feature_src):
    """Resolution C: the merge-gate's lint+PR worktree is the integration
    worktree (self._integration_wt), NOT idea.repo_url / repo_path."""
    assert "_integration_wt" in feature_src, (
        "merge stage must use the integration worktree path "
        "(self._integration_wt), not the bare repo_path")


def test_run_one_does_not_merge(feature_tree, feature_src):
    """Resolution B: merge_into_integration is NOT inside run_one — it
    races the integration branch in wave mode (concurrent gather). run_one
    must execute the task only; merges happen after the gather/await."""
    run_one = _fn(feature_tree, "run_one")
    body = ast.get_source_segment(feature_src, run_one)
    assert body is not None
    assert "merge_into_integration" not in body, (
        "run_one must NOT merge (Resolution B: wave-mode race). "
        "Merge happens in a separate _merge_task helper, after run_one.")


def test_merge_task_helper_exists(feature_tree):
    """Resolution B: a _merge_task helper carries the merge + conflict
    check + head update, called from both SERIAL and wave paths."""
    methods = {n.name for n in ast.walk(feature_tree)
               if isinstance(n, ast.AsyncFunctionDef)}
    assert "_merge_task" in methods, (
        "_merge_task helper missing — both SERIAL and wave paths must "
        "funnel merges through it (Resolution B)")


def test_merge_task_helper_calls_merge_activity(feature_tree, feature_src):
    helper = _fn(feature_tree, "_merge_task")
    body = ast.get_source_segment(feature_src, helper)
    assert body is not None and "merge_into_integration" in body, (
        "_merge_task must call the merge_into_integration activity")
