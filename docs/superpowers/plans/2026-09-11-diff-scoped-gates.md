# Diff-Scoped Merge Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the merge gate's four absolute checks judge what the change introduces, measured as a two-point multiset delta between a pinned base commit and the composed integration head, so pre-existing state on the base branch no longer decides a brownfield verdict.

**Architecture:** A new pure module (`src/sdlc/change_scope.py`) does the multiset arithmetic. A new vcs activity materializes a detached base worktree at the pinned `base_sha`. The security scan becomes a pure per-point scan plus one composing activity (`scoped_security_scan`). `run_integration_checks` computes scoped lint and scoped test reports. `merge.step` builds the unchanged four absolute checks from those typed reports. `FeatureWorkflow` pins `base_sha` at setup and passes it through.

**Tech Stack:** Python ≥ 3.11, Temporal Python SDK, Pydantic v2, pytest (+ pytest-asyncio), ruff, git.

**Spec:** `docs/superpowers/specs/2026-09-11-diff-scoped-gates-design.md` (DS1–DS12, approved unchanged 2026-09-11). Executors read the spec alongside this plan. The DS decisions are settled; do not re-litigate them.

## Global Constraints

- Python ≥ 3.11; **no new dependencies** (`pyproject.toml` untouched).
- **1000 physical lines per file**, no waiver (`scripts/check_file_size.py`).
- `src/sdlc/change_scope.py` is pure: standard library only — no `temporalio`, no Pydantic models from stages, no I/O (DS11).
- `MERGE_REQUIRED_CHECKS` and `ABSOLUTE_FLOOR` in `src/sdlc/gate.py` stay **byte-identical** (DS10).
- Check names stay `build_integration_green`, `lint_clean`, `security_scan_collected`, `security_no_critical` (DS10).
- Terminal status strings are unchanged: `rejected:merge:absolute-gate-failed:<names>` (DS10).
- A scoped report that is not `MEASURED` **never** reads as zero introduced (DS7).
- No exemption of any kind for fixtures, generated files, or test paths (DS4, DS9). New test fixtures assemble scanner-trigger text at runtime.
- The development host is Windows: every path that crosses a git/tool boundary is normalized to repo-relative POSIX form.
- Cross-stage calls are banned. The qa and merge slices may import `sdlc.change_scope`, `sdlc.vcs`, and `sdlc.toolchain` (horizontal packages).
- A behaviour change and its `<stage>.md` clauses ride in the **same commit** (root `AGENTS.md`, artifact boundary).
- Commits: subject + body only, **no attribution trailers of any kind** (no `Co-Authored-By`, no session links, no generated-by footers), even if a step below prints one. Commit with `git commit -F <msgfile>`; one path per `git add` argument; no heredocs.
- Commit message files (`.git/COMMIT_MSG_T<n>`) are written with the editor/Write tool, never with a shell heredoc; delete each one after its commit.
- **Per-task review gate (blocking):** you may not start task N+1 until the reviewer seat has replied approve/fixes-needed on task N's diff. Fixes-needed items are fixed and re-reviewed in task N.
- **Dogfood rule:** no source or test line added by this plan may match the security scanner's rules (`eval(`, `shell=True` in a `subprocess.` call, a secret-key assignment literal). Test code assembles such text at runtime. Task 10's smoke enforces this (SG-4).
- Verification before every commit: `pytest -q` (fast tier), `ruff check .`, `ruff format --check .`, `python scripts/check_file_size.py`, `python scripts/check_clauses.py`. Where a task adds `slow` or `temporal` tests, run those markers for the touched files too.

## Stop-guards (binding)

On any guard firing: **stop, diagnose (reproduce, isolate causally), report to the orchestrator. Clearance comes only from the orchestrator.** Do not work around a guard, and do not continue to the next task.

- **SG-1:** A test outside the files a task lists goes red, or a fast-tier test goes red and stays red after the task's own fix.
- **SG-2:** `git diff main -- src/sdlc/gate.py` is non-empty, or `tests/test_required_checks_manifest.py` fails.
- **SG-3:** Real tool output differs from the shapes this plan pins — pytest legacy JUnit (Task 4 Step 1), `ruff --output-format json` (Task 4 Step 1), or `pytest --collect-only -q` lines. Report the observed shape; do not adapt the parser silently.
- **SG-4 (dogfood):** Task 10's operator smoke — the scoped scan and scoped lint of this branch's HEAD against `main` — reports **any** introduced finding, or the security pre-existing count is not 4.
- **SG-5:** Any file exceeds 1000 lines, or `scripts/check_clauses.py` reports a clause without a test or a test citing a missing clause.
- **SG-6 (deploy):** Before this branch is deployed to a worker, a Temporal query shows any `FeatureWorkflow` or `TidyUpWorkflow` in `Running` state (see the replay decision). Do not deploy.

## Replay decision (DS11) — declared incompatible, not `workflow.patched`

This change replaces the `security_scan` command in `merge.step` with `scoped_security_scan`, inserts a new `prepare_base_worktree` command, and changes the `IntegrationChecks` payload schema. A workflow whose history already contains the old merge commands would fail replay with a non-determinism error.

**Decision: in-flight runs are declared incompatible; no `workflow.patched` branch.** Reasons:

1. A `patched` branch would keep the whole-tree gate alive as a second code path in `merge.step` — the exact semantics DS1 retires — solely for a fleet of zero-to-few demonstration runs.
2. `workflow.patched` cannot protect the payload change: a recorded `IntegrationChecks` result with `lint_clean`/`lint_detail` does not deserialize into the new model either way (`docs/framework.md`, "In-flight payload compatibility").
3. `src/` has no `workflow.patched` today; introducing the first one for a one-off transition adds a pattern with no second user.

Enforcement is mechanical, not a note: Task 7 (Step 7) records the rule in `src/sdlc/stages/merge/AGENTS.md` under "Temporal notes", and SG-6 makes the pre-deploy check binding. The check is
`temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='FeatureWorkflow' OR WorkflowType='TidyUpWorkflow')"`,
which must print nothing. Otherwise the operator terminates or finishes those runs first.

## File structure

| File | Responsibility | Task |
|---|---|---|
| `src/sdlc/change_scope.py` (new) | Pure identity normalization + multiset delta | 1 |
| `src/sdlc/vcs/integration.py` | `prepare_base_worktree` activity (+ `BaseWorktreeInput`, `BaseWorktree`) | 2 |
| `src/sdlc/vcs/git.py` | `get_task_diff` gains `renames` | 2 |
| `src/sdlc/vcs/__init__.py`, `src/sdlc/worker.py` | export + register the new vcs activity | 2 |
| `src/sdlc/stages/qa/models.py` | `SecurityFinding.line`; `ScopedSecurityReport` | 3 |
| `src/sdlc/stages/qa/activities.py` | pure `scan_paths`; `scoped_security_scan` replaces `security_scan` | 3 |
| `src/sdlc/stages/qa/qa.md`, `src/sdlc/stages/qa/AGENTS.md` | QA-1.5 update, new QA-1.6, DS9 convention | 3 |
| `src/sdlc/toolchain/junit.py` (new) | Parse pytest legacy JUnit into node-id outcomes | 4 |
| `src/sdlc/toolchain/adapters.py` | Adapter contract for scoped lint and scoped tests | 4 |
| `src/sdlc/stages/merge/models.py` | `LintFinding`, `ScopedLintReport`, `ScopedTestReport` | 5 |
| `src/sdlc/stages/merge/scoping.py` (new) | Activity-side helpers: scoped lint, scoped tests | 5, 6 |
| `src/sdlc/stages/merge/activities.py` | `run_integration_checks` returns the scoped reports | 5, 6 |
| `src/sdlc/stages/merge/step.py` | `base_sha` kwarg, new activity sequence, `build_absolute_checks` | 7 |
| `src/sdlc/workflows/feature.py` | pin `self._base_sha`; diff + merge use it | 7 |
| `src/sdlc/stages/merge/merge.md`, `src/sdlc/stages/merge/AGENTS.md` | MERGE-1.2 rewrite, new MERGE-1.10, replay note | 7, 9 |
| `tests/fakes/fake_activities.py` | fakes for the new activities / payloads | 7 |
| `PRD.md`, `ROADMAP.md`, `docs/roadmap/tier-0-triage.md` | Roadmap deltas table | 9 |

Tests: `tests/test_change_scope.py`, `tests/test_base_worktree.py`, `tests/test_scoped_security_scan.py`, `tests/test_toolchain_junit.py`, `tests/test_toolchain_scoped_contract.py`, `tests/test_scoped_lint.py`, `tests/test_scoped_tests.py`, `tests/merge/test_scoped_absolute_checks.py`, `tests/test_pinned_base_e2e.py`, `tests/test_diff_scoped_fixture_tier.py`, `tests/test_greenfield_equivalence.py`, plus edits to existing tests named per task.

---

### Task 1: `change_scope` — the pure multiset delta

**Files:**
- Create: `src/sdlc/change_scope.py`
- Test: `tests/test_change_scope.py`

**Interfaces:**
- Produces:
  - `FindingKey = tuple[str, str, str, str]` — `(tool, rule, path, line)`, already normalized
  - `normalize_path(path: str) -> str`
  - `normalize_line(text: str) -> str`
  - `rename_map(renames: Sequence[Sequence[str]]) -> dict[str, str]` — base path → head path
  - `delta(base: Sequence[T], head: Sequence[T], key: Callable[[T], FindingKey], renames: Mapping[str, str]) -> tuple[list[T], int, int]` — `(introduced head items, preexisting count, resolved count)`

- [ ] **Step 1: Write the failing tests**

```python
"""DS3: two-point multiset difference over a line-independent identity."""

import ast
import itertools
import pathlib

from sdlc.change_scope import delta, normalize_line, normalize_path, rename_map

# DS9: scanner-trigger text is assembled at runtime, never literal in source.
EVAL_S = "return " + "ev" + "al(s)"
EVAL_T = "return " + "ev" + "al(t)"


def _k(t):
    return t


def test_identical_finding_at_both_points_is_preexisting():
    f = ("sec", "dangerous-eval", "a.py", EVAL_S)
    assert delta([f], [f], _k, {}) == ([], 1, 0)


def test_second_identical_finding_in_one_file_is_introduced():
    """The multiset case: a set difference would read 2 - 1 as nothing."""
    f = ("sec", "dangerous-eval", "a.py", EVAL_S)
    introduced, pre, res = delta([f], [f, f], _k, {})
    assert introduced == [f] and pre == 1 and res == 0


def test_rename_maps_the_base_path_so_a_moved_finding_stays_preexisting():
    base = [("lint", "F401", "old.py", "import os")]
    head = [("lint", "F401", "new.py", "import os")]
    assert delta(base, head, _k, rename_map([["old.py", "new.py"]])) == ([], 1, 0)


def test_a_deleted_finding_counts_resolved_never_introduced():
    base = [("lint", "F401", "gone.py", "import os")]
    assert delta(base, [], _k, {}) == ([], 0, 1)


def test_an_edited_line_reads_introduced_the_fail_toward_blocking_direction():
    base = [("sec", "dangerous-eval", "a.py", EVAL_S)]
    head = [("sec", "dangerous-eval", "a.py", EVAL_T)]
    introduced, pre, res = delta(base, head, _k, {})
    assert introduced == head and pre == 0 and res == 1


def test_normalize_path_is_repo_relative_posix():
    assert normalize_path(".\\src\\a.py") == "src/a.py"
    assert normalize_path("./src/a.py") == "src/a.py"
    assert normalize_path("/src/a.py") == "src/a.py"


def test_normalize_line_collapses_whitespace():
    assert normalize_line("  x =\t f( s )  \n") == "x = f( s )"


def test_delta_is_order_independent():
    """NFR-10, per-module pattern: byte-identical across input order."""
    base = [("l", "F401", "a.py", "import os"), ("l", "E501", "b.py", "x")]
    head = [
        ("l", "F401", "a.py", "import os"),
        ("l", "F401", "a.py", "import os"),
        ("l", "E501", "c.py", "y"),
    ]
    expected = delta(base, head, _k, {})
    for b in itertools.permutations(base):
        for h in itertools.permutations(head):
            assert delta(list(b), list(h), _k, {}) == expected


def test_module_is_pure():
    tree = ast.parse(pathlib.Path("src/sdlc/change_scope.py").read_text(encoding="utf-8"))
    imported = {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    imported |= {
        (n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    }
    assert imported <= {"__future__", "collections", "typing"}, imported
    called = {
        n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "open" not in called
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_change_scope.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.change_scope'`

- [ ] **Step 3: Implement**

```python
"""DS3 (diff-scoped merge gates): two-point multiset difference.

A finding's identity is (tool, rule, path, normalized source line) — never a
line number, which moves whenever anything above it changes. Multiset, not
set: a second identical finding in one file is introduced. Base paths are
mapped through the change's renames before comparison.

Pure: standard library only. The qa and merge slices both consume it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import TypeVar

T = TypeVar("T")

# (tool, rule, path, line). Callers return components already normalized with
# normalize_path / normalize_line.
FindingKey = tuple[str, str, str, str]


def normalize_path(path: str) -> str:
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def normalize_line(text: str) -> str:
    return " ".join(text.split())


def rename_map(renames: Sequence[Sequence[str]]) -> dict[str, str]:
    return {normalize_path(old): normalize_path(new) for old, new in renames}


def delta(
    base: Sequence[T],
    head: Sequence[T],
    key: Callable[[T], FindingKey],
    renames: Mapping[str, str],
) -> tuple[list[T], int, int]:
    """Return (introduced head items, pre-existing count, resolved count)."""

    def base_key(item: T) -> FindingKey:
        tool, rule, path, line = key(item)
        return (tool, rule, renames.get(path, path), line)

    base_counts = Counter(base_key(b) for b in base)
    by_key: dict[FindingKey, list[T]] = {}
    for h in head:
        by_key.setdefault(key(h), []).append(h)

    introduced: list[T] = []
    preexisting = 0
    for k in sorted(by_key):
        items = sorted(by_key[k], key=repr)
        kept = min(len(items), base_counts.get(k, 0))
        preexisting += kept
        introduced.extend(items[kept:])
    resolved = sum(max(0, n - len(by_key.get(k, []))) for k, n in base_counts.items())
    return introduced, preexisting, resolved
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_change_scope.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

Message file `.git/COMMIT_MSG_T1` (subject + body, no trailers):
```
feat(gate): pure multiset delta for diff-scoped merge gates

DS3: introduced = head findings minus base findings over a
line-independent (tool, rule, path, line) identity, with renames
mapped on the base side. Pure, order-independent (NFR-10).
```
```
git add src/sdlc/change_scope.py
git add tests/test_change_scope.py
git commit -F .git/COMMIT_MSG_T1
```

---

### Task 2: vcs — the pinned base worktree and rename pairs

**Files:**
- Modify: `src/sdlc/vcs/integration.py` (append after `build_verification_branch`)
- Modify: `src/sdlc/vcs/git.py:96-105` (`get_task_diff`)
- Modify: `src/sdlc/vcs/__init__.py` (import, `ACTIVITIES`, `__all__`)
- Modify: `src/sdlc/worker.py:103-110` (import) and `:130-142` (registration list)
- Test: `tests/test_base_worktree.py`

**Interfaces:**
- Produces:
  - `BaseWorktreeInput(integration_wt: str, run_id: str, base_sha: str)` — dataclass
  - `BaseWorktree(path: str | None, reason: str = "")` — dataclass. `path is None` means "could not materialize"; downstream activities then return `NOT_COLLECTED` with `reason`
  - `prepare_base_worktree(inp: BaseWorktreeInput) -> BaseWorktree` — activity; never raises on a git failure
  - `get_task_diff(...)` result gains `"renames": list[list[str]]` — `[old, new]` pairs from `git diff -M --name-status`

- [ ] **Step 1: Write the failing tests**

```python
"""DS2/DS3: the disposable detached base worktree, and rename pairs."""

import os
import pathlib
import subprocess

import pytest

from sdlc.vcs import BaseWorktreeInput, DiffInput, get_task_diff, prepare_base_worktree

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "head")
    return repo, base


@pytest.fixture(autouse=True)
def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


@pytest.mark.asyncio
async def test_materializes_the_base_commit_detached(tmp_path):
    repo, base = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    assert wt.path is not None, wt.reason
    assert (pathlib.Path(wt.path) / "a.py").read_text(encoding="utf-8") == "v1\n"
    assert _git(wt.path, "rev-parse", "HEAD") == base


@pytest.mark.asyncio
async def test_a_retry_reuses_and_resets_but_keeps_the_provisioned_venv(tmp_path):
    repo, base = _repo(tmp_path)
    first = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    p = pathlib.Path(first.path)
    (p / "a.py").write_text("dirty\n", encoding="utf-8")
    (p / "stray.py").write_text("x\n", encoding="utf-8")
    (p / ".sdlc-venv").mkdir()
    again = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    assert os.path.normpath(again.path) == os.path.normpath(first.path)
    assert (p / "a.py").read_text(encoding="utf-8") == "v1\n"
    assert not (p / "stray.py").exists()
    assert (p / ".sdlc-venv").is_dir()


@pytest.mark.asyncio
async def test_no_base_sha_is_reported_not_raised(tmp_path):
    repo, _ = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", ""))
    assert wt.path is None and "base_sha" in wt.reason


@pytest.mark.asyncio
async def test_an_unknown_sha_is_reported_not_raised(tmp_path):
    repo, _ = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", "0" * 40))
    assert wt.path is None and wt.reason


@pytest.mark.asyncio
async def test_get_task_diff_reports_rename_pairs(tmp_path):
    repo, _ = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "a.py", "b.py")
    _git(repo, "commit", "-q", "-m", "rename")
    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))
    assert d["renames"] == [["a.py", "b.py"]]
    assert "b.py" in d["files"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_base_worktree.py -q`
Expected: FAIL — `ImportError: cannot import name 'BaseWorktreeInput' from 'sdlc.vcs'`

- [ ] **Step 3: Implement `prepare_base_worktree`**

In `src/sdlc/vcs/integration.py`, extend the worktree import to
`from .worktree import _clear_worktree_dir, _ensure_worktree, _worktrees_root`, then append:

```python
# The provisioned per-worktree venv (stages/qa/activities.py _VENV_DIR_NAME).
# Kept across resets: re-provisioning it is the expensive part of a retry.
_KEEP_ON_CLEAN = ".sdlc-venv"


@dataclass
class BaseWorktreeInput:
    integration_wt: str  # any worktree of the repository; git worktree add runs here
    run_id: str
    base_sha: str  # FeatureWorkflow._base_sha, pinned at setup (DS2)


@dataclass
class BaseWorktree:
    path: str | None  # None = could not materialize; `reason` says why
    reason: str = ""


@activity.defn
async def prepare_base_worktree(inp: BaseWorktreeInput) -> BaseWorktree:
    """DS2/DS3: a disposable DETACHED worktree at the pinned base commit.

    Never raises on a git failure: the merge gate must fail CLOSED on an
    unmaterializable base (DS7), which it does by handing path=None to the
    scoped activities, which then report NOT_COLLECTED. Raising would instead
    fail the whole workflow. Idempotent across retries: a live worktree is
    reset to base_sha and cleaned (keeping the provisioned venv), the
    build_verification_branch pattern. Never pushed; never the operator's
    checkout.
    """
    if not inp.base_sha:
        return BaseWorktree(None, "no pinned base_sha was supplied to the merge gate")
    want = _git(["rev-parse", "--verify", "--quiet", f"{inp.base_sha}^{{commit}}"], inp.integration_wt)
    if want.returncode != 0:
        return BaseWorktree(None, f"base_sha {inp.base_sha!r} does not resolve to a commit")
    sha = want.stdout.strip()
    root = os.path.join(_worktrees_root(), inp.run_id or "local", "base")
    for cand in [root] + [f"{root}.{i}" for i in range(1, 8)]:
        cand = os.path.normpath(cand)
        live = os.path.isdir(cand) and _git(["rev-parse", "--is-inside-work-tree"], cand).returncode == 0
        if not live:
            if os.path.exists(cand):
                try:
                    _clear_worktree_dir(inp.integration_wt, cand)
                except OSError:
                    continue  # Windows CWD lock: try the next candidate
            add = _git(["worktree", "add", "--detach", cand, sha], inp.integration_wt)
            if add.returncode != 0:
                return BaseWorktree(None, f"git worktree add failed: {add.stderr.strip() or add.stdout.strip()}")
        for args in (
            ["checkout", "--detach", "--force", sha],
            ["reset", "--hard", sha],
            ["clean", "-fd", "-e", _KEEP_ON_CLEAN],
        ):
            r = _git(args, cand)
            if r.returncode != 0:
                return BaseWorktree(None, f"git {args[0]} failed in the base worktree: {r.stderr.strip() or r.stdout.strip()}")
        if _git(["rev-parse", "HEAD"], cand).stdout.strip() != sha:
            return BaseWorktree(None, "base worktree HEAD does not match base_sha after reset")
        return BaseWorktree(cand)
    return BaseWorktree(None, f"could not clear or create a base worktree near {root}")
```

Keep lines ≤ 100 characters (`ruff format` will wrap them).

- [ ] **Step 4: Add rename pairs to `get_task_diff`**

Replace the body of `get_task_diff` in `src/sdlc/vcs/git.py` with:

```python
    rng = f"{inp.branch_point}...HEAD"
    stat = _git(["diff", "--stat", rng], inp.worktree).stdout
    patch = _git(["diff", rng], inp.worktree).stdout
    files = _git(["diff", "--name-only", rng], inp.worktree).stdout.splitlines()
    # DS2: [old, new] for every rename git detected, so base-side finding
    # paths can be mapped before the multiset delta (change_scope.rename_map).
    renames = [
        [parts[1], parts[2]]
        for parts in (
            ln.split("\t")
            for ln in _git(["diff", "-M", "--name-status", rng], inp.worktree).stdout.splitlines()
        )
        if len(parts) == 3 and parts[0].startswith("R")
    ]
    return {"stat": stat, "patch": patch[: inp.max_chars], "files": files, "renames": renames}
```

- [ ] **Step 5: Export and register**

In `src/sdlc/vcs/__init__.py`, add `BaseWorktree`, `BaseWorktreeInput` and `prepare_base_worktree` to the `.integration` import, add `prepare_base_worktree` to `ACTIVITIES`, and add all three names to `__all__` (alphabetical).

In `src/sdlc/worker.py`, add `prepare_base_worktree` to the `from .vcs import (...)` block and to the list returned by `get_worker_activities()` directly after `build_verification_branch`.

- [ ] **Step 6: Run to verify it passes**

Run: `pytest tests/test_base_worktree.py tests/test_integration_checks_wiring.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

Message file `.git/COMMIT_MSG_T2`:
```
feat(vcs): pinned base worktree and rename pairs for scoped gates

DS2/DS3: prepare_base_worktree materializes a disposable detached
worktree at the run's pinned base commit and reports, never raises, a
git failure so the merge gate can fail closed. get_task_diff now
returns the rename pairs used to map base-side finding paths.
```
```
git add src/sdlc/vcs/integration.py
git add src/sdlc/vcs/git.py
git add src/sdlc/vcs/__init__.py
git add src/sdlc/worker.py
git add tests/test_base_worktree.py
git commit -F .git/COMMIT_MSG_T2
```

---

### Task 3: security — per-match pure scan and `scoped_security_scan`

**Files:**
- Modify: `src/sdlc/stages/qa/models.py` (`SecurityFinding`, new `ScopedSecurityReport`)
- Modify: `src/sdlc/stages/qa/activities.py:357-436` (rules block through `ACTIVITIES`)
- Modify: `src/sdlc/stages/qa/qa.md` (new clause QA-1.6)
- Modify: `src/sdlc/stages/qa/AGENTS.md` (activities, DS9 fixture convention)
- Test: `tests/test_scoped_security_scan.py`

**Interfaces:**
- Consumes: `change_scope.delta`, `normalize_path`, `normalize_line`, `rename_map` (Task 1); `prepare_base_worktree` (Task 2, tests only).
- Produces:
  - `SecurityFinding.line: str = ""` — the normalized source line
  - `ScopedSecurityReport(state, reason="", introduced: list[SecurityFinding]=[], preexisting: int=0, resolved: int=0)`, with property `introduced_critical -> int`
  - `scan_paths(root: str, paths: Sequence[str]) -> SecurityReport` — pure per-point scan
  - `ScopedSecurityScanInput(worktree: str, base_worktree: str | None, renames: list[list[str]] = [], base_reason: str = "")`
  - `scoped_security_scan(inp: ScopedSecurityScanInput) -> ScopedSecurityReport` — activity
- The old `security_scan` activity **stays in this task** (the merge step still calls it) and now delegates to `scan_paths`. Task 7 deletes it.

> **Fixture rule for this task and every later one (DS9):** new test code never writes scanner-trigger text literally. Assemble it at runtime (`"ev" + "al("`). **Do not edit** the existing literal fixture lines in `tests/test_security_floor.py` or `tests/test_triage_misconfig.py` (the `SECRET_KEY` literal at `:69`). Their normalized text is their baseline identity; editing one makes it read as introduced and trips SG-4.

- [ ] **Step 1: Write the failing tests**

```python
"""DS4/DS7: per-match scan over tracked content, two points, fail closed."""

import pathlib
import subprocess

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.qa.activities import (
    ScopedSecurityScanInput,
    scan_paths,
    scoped_security_scan,
)
from sdlc.stages.qa.models import ScopedSecurityReport
from sdlc.vcs import BaseWorktreeInput, prepare_base_worktree

EVAL = "ev" + "al("  # DS9: never literal in test source
SECRET = "AWS_SECRET_ACCESS_KEY" + ' = "' + "A" * 32 + '"'
GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _commit_all(repo: pathlib.Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    return r


async def _scoped(repo: pathlib.Path, base: str) -> ScopedSecurityReport:
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run", base))
    assert wt.path, wt.reason
    return await scoped_security_scan(
        ScopedSecurityScanInput(worktree=str(repo), base_worktree=wt.path)
    )


def test_scan_emits_one_finding_per_match_with_its_line(tmp_path):
    (tmp_path / "a.py").write_text(f"x = {EVAL}s)\ny = {EVAL}t)\n", encoding="utf-8")
    rep = scan_paths(str(tmp_path), ["a.py"])
    assert rep.state is CollectionState.MEASURED
    assert [f.line for f in rep.findings] == [f"x = {EVAL}s)", f"y = {EVAL}t)"]
    assert rep.critical == 2


def test_scan_skips_listed_paths_under_skip_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text(f"{EVAL}1)\n", encoding="utf-8")
    assert scan_paths(str(tmp_path), ["node_modules/x.js"]).findings == []


def test_an_unreadable_tracked_file_is_not_collected(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    def boom(self, *a, **k):
        raise OSError("locked")

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    rep = scan_paths(str(tmp_path), ["a.py"])
    assert rep.state is CollectionState.NOT_COLLECTED
    assert "a.py" in rep.reason


@pytest.mark.clause("QA-1.6")
@pytest.mark.asyncio
async def test_a_second_identical_finding_in_one_file_is_introduced(repo):
    (repo / "a.py").write_text(f"return {EVAL}s)\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    (repo / "a.py").write_text(f"return {EVAL}s)\nreturn {EVAL}s)\n", encoding="utf-8")
    _commit_all(repo, "head")
    rep = await _scoped(repo, base)
    assert rep.state is CollectionState.MEASURED
    assert rep.introduced_critical == 1 and rep.preexisting == 1


@pytest.mark.asyncio
async def test_untracked_files_and_venvs_are_never_scanned(repo):
    (repo / "ok.py").write_text("x = 1\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    (repo / "loose.py").write_text(f"{EVAL}1)\n", encoding="utf-8")
    (repo / ".sdlc-venv").mkdir()
    (repo / ".sdlc-venv" / "v.py").write_text(f"{EVAL}1)\n", encoding="utf-8")
    rep = await _scoped(repo, base)
    assert rep.state is CollectionState.MEASURED and rep.introduced == []


@pytest.mark.asyncio
async def test_a_planted_fixture_in_a_new_file_still_trips_the_floor(repo):
    (repo / "ok.py").write_text("x = 1\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    (repo / "planted.py").write_text(f"{SECRET}\nrun = {EVAL}s)\n", encoding="utf-8")
    _commit_all(repo, "head")
    rep = await _scoped(repo, base)
    assert {f.rule for f in rep.introduced} == {"hardcoded-secret", "dangerous-eval"}
    assert rep.introduced_critical == 2


@pytest.mark.asyncio
async def test_an_unmaterialized_base_is_not_collected(repo):
    rep = await scoped_security_scan(
        ScopedSecurityScanInput(worktree=str(repo), base_worktree=None, base_reason="lock")
    )
    assert rep.state is CollectionState.NOT_COLLECTED and "lock" in rep.reason
    assert rep.introduced == []


def test_a_not_collected_report_cannot_carry_findings():
    with pytest.raises(ValueError):
        ScopedSecurityReport(state=CollectionState.NOT_COLLECTED, reason="x", preexisting=3)
    with pytest.raises(ValueError):
        ScopedSecurityReport(state=CollectionState.NOT_COLLECTED)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_scoped_security_scan.py -q`
Expected: FAIL — `ImportError: cannot import name 'ScopedSecurityScanInput'`

- [ ] **Step 3: Models**

In `src/sdlc/stages/qa/models.py`: change the Pydantic import to `from pydantic import BaseModel, Field, model_validator`. Add `line: str = ""` as the last field of `SecurityFinding`, with the comment `# normalized source line: the DS3 identity text`. Then append:

```python
class ScopedSecurityReport(BaseModel):
    """DS4/DS7: the two-point security delta the merge gate reads.

    `security_scan_collected` reads `state` (both points collected);
    `security_no_critical` counts introduced criticals only. A report that is
    not MEASURED carries no counts at all, so it can never read as "zero
    introduced" (FR-915).
    """

    state: CollectionState
    reason: str = ""
    introduced: list[SecurityFinding] = Field(default_factory=list)
    preexisting: int = 0
    resolved: int = 0

    @property
    def introduced_critical(self) -> int:
        return sum(1 for f in self.introduced if f.severity == "critical")

    @model_validator(mode="after")
    def _unmeasured_carries_nothing(self) -> ScopedSecurityReport:
        if self.state is not CollectionState.MEASURED:
            if self.introduced or self.preexisting or self.resolved:
                raise ValueError(f"{self.state.value} report must not carry findings or counts")
            if not self.reason.strip():
                raise ValueError(f"{self.state.value} report requires a reason")
        return self
```

- [ ] **Step 4: The pure scan, the composing activity, the delegating old activity**

In `src/sdlc/stages/qa/activities.py`:

1. Add imports: `from collections.abc import Sequence`, `from dataclasses import dataclass, field` (replacing the bare `dataclass` import), `from ...change_scope import FindingKey, delta, normalize_line, normalize_path, rename_map`, `from ...vcs.git import _git`. Also add `ScopedSecurityReport` to the `.models` import.
2. Replace the body of `security_scan` (from the docstring through its `return`) and add the new code:

```python
def _skipped(rel: str) -> bool:
    return any(part in _SCAN_SKIP_DIRS for part in rel.split("/")[:-1])


def scan_paths(root: str, paths: Sequence[str]) -> SecurityReport:
    """DS4: the per-point scan, pure over an explicit path list.

    Pure filesystem read -- no network, no git, no directory walk -- so it is
    reproducible across Temporal retries. One finding PER MATCH, carrying the
    normalized source line (the DS3 identity text): `pattern.search` recorded
    at most one finding per (rule, file), which let a second identical finding
    in a file hide behind the first. A listed file that cannot be read makes
    the whole point NOT_COLLECTED rather than being skipped silently (DS7).
    """
    findings: list[SecurityFinding] = []
    unreadable: list[str] = []
    for rel in sorted({normalize_path(p) for p in paths}):
        if not rel.endswith(_SECURITY_SCAN_EXTENSIONS) or _skipped(rel):
            continue
        try:
            text = pathlib.Path(root, rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            unreadable.append(rel)
            continue
        for pattern, severity, rule, detail in _SECURITY_RULES:
            for m in pattern.finditer(text):
                start = text.rfind("\n", 0, m.start()) + 1
                end = text.find("\n", m.start())
                line = text[start : len(text) if end == -1 else end]
                findings.append(
                    SecurityFinding(
                        severity=severity,
                        rule=rule,
                        detail=detail,
                        path=rel,
                        line=normalize_line(line),
                    )
                )
    if unreadable:
        return SecurityReport(
            critical=0,
            state=CollectionState.NOT_COLLECTED,
            reason=f"{len(unreadable)} tracked file(s) unreadable: {unreadable[:5]}",
        )
    critical = sum(1 for f in findings if f.severity == "critical")
    return SecurityReport(critical=critical, findings=findings, state=CollectionState.MEASURED)


@activity.defn
async def security_scan(inp: SecurityScanInput) -> SecurityReport:
    """Whole-directory form, kept only until the merge step moves to
    scoped_security_scan (diff-scoped gates plan, Task 7)."""
    paths: list[str] = []
    for dirpath, dirnames, filenames in os.walk(inp.worktree):
        dirnames[:] = [d for d in dirnames if d not in _SCAN_SKIP_DIRS]
        paths.extend(
            os.path.relpath(os.path.join(dirpath, f), inp.worktree) for f in filenames
        )
    return scan_paths(inp.worktree, paths)


@dataclass
class ScopedSecurityScanInput:
    worktree: str  # the integration head
    base_worktree: str | None  # prepare_base_worktree's path; None = not materialized
    renames: list[list[str]] = field(default_factory=list)
    base_reason: str = ""  # why base_worktree is None


def _tracked(worktree: str) -> list[str] | None:
    r = _git(["ls-files", "-z"], worktree)
    if r.returncode != 0:
        return None
    return [p for p in r.stdout.split("\0") if p]


def _security_key(f: SecurityFinding) -> FindingKey:
    return ("security", f.rule, f.path, f.line)


def _not_collected(reason: str) -> ScopedSecurityReport:
    return ScopedSecurityReport(state=CollectionState.NOT_COLLECTED, reason=reason)


@activity.defn
async def scoped_security_scan(inp: ScopedSecurityScanInput) -> ScopedSecurityReport:
    """DS4: tracked content at both points, then the DS3 multiset delta.

    Git lives here and not in scan_paths: both trees are fixed commits (the
    detached base at base_sha, the integration head after its last merge), so a
    retry lists and reads the same bytes. Only the delta crosses the activity
    boundary, which keeps payloads bounded on a repository with thousands of
    pre-existing findings.
    """
    if inp.base_worktree is None:
        return _not_collected(f"base not materialized: {inp.base_reason or 'no reason given'}")
    points: dict[str, SecurityReport] = {}
    for label, wt in (("head", inp.worktree), ("base", inp.base_worktree)):
        paths = _tracked(wt)
        if paths is None:
            return _not_collected(f"git ls-files failed at the {label} point")
        rep = scan_paths(wt, paths)
        if rep.state is not CollectionState.MEASURED:
            return _not_collected(f"{label} point: {rep.reason}")
        points[label] = rep
    introduced, pre, res = delta(
        points["base"].findings, points["head"].findings, _security_key, rename_map(inp.renames)
    )
    return ScopedSecurityReport(
        state=CollectionState.MEASURED, introduced=introduced, preexisting=pre, resolved=res
    )


ACTIVITIES = [run_test_suite, run_lint, security_scan, scoped_security_scan]
```

Delete the old `ACTIVITIES = [...]` line this replaces.

- [ ] **Step 5: Contract — `qa.md` QA-1.6 and `AGENTS.md`**

Append to the Requirements section of `src/sdlc/stages/qa/qa.md`, after QA-1.5:

```markdown
### QA-1.6
The security scan measures the change, not the tree. `scan_paths` is a pure read over an explicit path list that emits one finding per match, each carrying its normalized source line. It skips paths under Kroker's own `_SCAN_SKIP_DIRS`, and any listed file it cannot read makes the point `NOT_COLLECTED`. `scoped_security_scan` lists tracked files (`git ls-files`) at the integration head and at the pinned base worktree, and returns a `ScopedSecurityReport`. `introduced` is the head-minus-base multiset over `(rule, path, line)`, with base paths mapped through the change's renames; pre-existing and resolved findings are counts. A report that is not `MEASURED` carries no findings and no counts. There is no exemption of any kind: pre-existing fixtures are pre-existing at the base, and new fixtures assemble their trigger text at runtime. [SC-5, FR-106, FR-915; diff-scoped gates DS4/DS7/DS9]
```

Append to the Failure modes list:

```markdown
- **Base not materialized / tracked file unreadable / `git ls-files` failed**: the scoped scan is `NOT_COLLECTED` with the reason, and the merge gate's absolute `security_scan_collected` fails.
```

In `src/sdlc/stages/qa/AGENTS.md`:
- In "Temporal notes", change the `ACTIVITIES` line to `ACTIVITIES = [run_test_suite, run_lint, security_scan, scoped_security_scan]`.
- In "Activities", replace the `security_scan` bullet with:
  - `` `scan_paths`: pure per-point scan over an explicit path list (one finding per match, with its line). ``
  - `` `scoped_security_scan`: tracked files at head and base, then the `change_scope` delta (DS4). ``
  - `` `security_scan`: transitional whole-directory form; removed when the merge step moves to `scoped_security_scan`. ``
- Add a section before "Tests":

```markdown
## Fixture convention (diff-scoped gates DS9)

The merge gate's security floor has no exemption for tests or fixtures. New test code never writes scanner-trigger text literally: assemble it at runtime (`"ev" + "al("`), or keep payloads in extensions the scanner does not read. Do not edit existing literal fixture lines — their normalized text is their baseline identity, and an edited line reads as introduced.
```

- [ ] **Step 6: Run to verify it passes**

Run: `pytest tests/test_scoped_security_scan.py tests/test_security_floor.py tests/qa -q && python scripts/check_clauses.py`
Expected: PASS. The existing `test_security_floor.py` scan tests still pass through the delegating `security_scan`.

- [ ] **Step 7: Commit**

Message file `.git/COMMIT_MSG_T3`:
```
feat(qa): per-match pure security scan and scoped_security_scan

DS4/DS7: the scan core reads an explicit path list and emits one
finding per match with its line, closing the one-finding-per-rule-
per-file leak; scoped_security_scan measures tracked content at the
integration head and the pinned base and returns only the delta.
QA-1.6 and the DS9 fixture convention ride in the same commit.
```
```
git add src/sdlc/stages/qa/models.py
git add src/sdlc/stages/qa/activities.py
git add src/sdlc/stages/qa/qa.md
git add src/sdlc/stages/qa/AGENTS.md
git add tests/test_scoped_security_scan.py
git commit -F .git/COMMIT_MSG_T3
```

---

### Task 4: toolchain — JUnit node ids and the scoped adapter contract

**Files:**
- Create: `src/sdlc/toolchain/junit.py`
- Modify: `src/sdlc/toolchain/adapters.py` (abstract contract on `ToolchainAdapter`; `PythonToolchain` implementation)
- Test: `tests/test_toolchain_junit.py`, `tests/test_toolchain_scoped_contract.py`
- Modify: `tests/test_toolchain_triage_extension.py:91-104` (`_Bare`) and `tests/test_triage_outliers.py:9-25` (`_NoParser`) — existing adapter test doubles that must implement the new abstract methods

**Interfaces:**
- Produces:
  - `testcase_outcomes(xml_text: str) -> dict[str, bool] | None` — `{pytest node id: passed}`. Skipped cases are dropped; returns `None` when the report is empty or unparseable.
  - On `ToolchainAdapter`:
    - `lint_policy_globs: tuple[str, ...]`
    - `suppression_pattern: str` — a regex; `""` means the linter has no suppression syntax
    - `lint_json_cmd() -> str`
    - `parse_lint(code: int, out: str, root: str) -> list[tuple[str, str, int]] | None` — `(rule, repo-relative POSIX path, 1-based row)`; `None` means the tool failed
    - `integration_test_cmd(junit_out: str, coverage: bool = True) -> str`
    - `collect_ids_cmd(paths: Sequence[str]) -> str`
    - `parse_collected_ids(out: str) -> set[str]`
    - `selected_tests_cmd(node_ids: Sequence[str], junit_out: str) -> str`
- `test_cmd` is **unchanged**, because triage's build probe (`triage/activities.py:483`) calls it. Only the merge gate moves to `integration_test_cmd`.

Pinned facts this task encodes (measured 2026-09-11 on the Windows host):
- pytest aborts the whole session on a collection error unless it is given `--continue-on-collection-errors`. That flag is required on **every** gate invocation: the full run, collect-only, and the targeted re-run.
- Legacy JUnit `file` uses `\` for ordinary testcases and `/` for collection errors. A class test has `classname="tests.test_a.TestC"`. A collection error has `classname=""` and `name="tests.test_broken"`.
- A node id that does not exist makes pytest reject the entire invocation (exit 4). Base re-runs therefore collect first (Task 6).
- `ruff --output-format json` prints absolute `filename`s. A missing path shows up as an `E902` finding, not as a non-zero exit.

- [ ] **Step 1: SG-3 shape pins against the real tools — write them first**

`tests/test_toolchain_scoped_contract.py`:

```python
"""SG-3: pin the real pytest/ruff shapes the scoped gate depends on."""

import os
import sysconfig
import textwrap

import pytest

from sdlc.process import _bounded_shell
from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter
from sdlc.toolchain.junit import testcase_outcomes

PY = PythonToolchain()

TESTS = textwrap.dedent(
    """
    import pytest
    class TestC:
        def test_y(self):
            assert False
    @pytest.mark.parametrize("n", [1, 2])
    def test_p(n):
        assert n == 1
    def test_ok():
        pass
    """
)


def _suite(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(TESTS, encoding="utf-8")
    (tmp_path / "tests" / "test_broken.py").write_text(
        "import nonexistent_mod_xyz\n\n\ndef test_z():\n    pass\n", encoding="utf-8"
    )


async def _sh(cmd, cwd):
    """Through the production shell path (never subprocess shell=True in test
    source: the regex scanner's shell-injection rule would flag it as
    introduced). `pytest`/`ruff` resolve from the test interpreter's scripts
    dir, as _ensure_python_env's PATH would."""
    env = dict(os.environ)
    env["PATH"] = sysconfig.get_path("scripts") + os.pathsep + env.get("PATH", "")
    return await _bounded_shell(cmd, str(cwd), 120, env=env)


@pytest.mark.asyncio
async def test_full_run_survives_a_collection_error_and_names_every_case(tmp_path):
    _suite(tmp_path)
    await _sh(PY.integration_test_cmd(".sdlc-junit.xml", coverage=False), tmp_path)
    outcomes = testcase_outcomes((tmp_path / ".sdlc-junit.xml").read_text(encoding="utf-8"))
    assert outcomes == {
        "tests/test_broken.py": False,
        "tests/test_a.py::TestC::test_y": False,
        "tests/test_a.py::test_p[1]": True,
        "tests/test_a.py::test_p[2]": False,
        "tests/test_a.py::test_ok": True,
    }


@pytest.mark.asyncio
async def test_collect_only_lists_node_ids(tmp_path):
    _suite(tmp_path)
    code, out = await _sh(PY.collect_ids_cmd(["tests/test_a.py"]), tmp_path)
    assert PY.parse_collected_ids(out) == {
        "tests/test_a.py::TestC::test_y",
        "tests/test_a.py::test_p[1]",
        "tests/test_a.py::test_p[2]",
        "tests/test_a.py::test_ok",
    }


@pytest.mark.asyncio
async def test_selected_run_reports_only_the_named_ids(tmp_path):
    _suite(tmp_path)
    ids = ["tests/test_a.py::TestC::test_y", "tests/test_a.py::test_p[2]", "tests/test_broken.py"]
    await _sh(PY.selected_tests_cmd(ids, "sel.xml"), tmp_path)
    outcomes = testcase_outcomes((tmp_path / "sel.xml").read_text(encoding="utf-8"))
    assert set(outcomes) == set(ids)
    assert not any(outcomes.values())


def _lint_tree(tmp_path, body: str):
    (tmp_path / "ruff.toml").write_text('[lint]\nselect = ["F401"]\n', encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(body, encoding="utf-8")


@pytest.mark.asyncio
async def test_ruff_json_parses_to_relative_rows(tmp_path):
    _lint_tree(tmp_path, "x = 1\nimport os\n")
    code, out = await _sh(PY.lint_json_cmd(), tmp_path)
    assert PY.parse_lint(code, out, str(tmp_path)) == [("F401", "pkg/m.py", 2)]


@pytest.mark.asyncio
async def test_a_clean_tree_is_an_empty_measured_list(tmp_path):
    _lint_tree(tmp_path, "x = 1\n")
    code, out = await _sh(PY.lint_json_cmd(), tmp_path)
    assert PY.parse_lint(code, out, str(tmp_path)) == []


def test_tool_failure_is_none_not_empty():
    assert PY.parse_lint(2, "error: boom", ".") is None
    e902 = '[{"code": "E902", "filename": "/x/a.py", "location": {"row": 1}}]'
    assert PY.parse_lint(0, e902, "/x") is None
    assert PY.parse_lint(0, "not json", ".") is None


def test_integration_cmd_drops_maxfail_but_test_cmd_keeps_it():
    cmd = PY.integration_test_cmd(".sdlc-junit.xml")
    assert "--maxfail" not in cmd
    for flag in ("--continue-on-collection-errors", "junit_family=legacy", "--junitxml="):
        assert flag in cmd
    assert "--maxfail=25" in PY.test_cmd(coverage=True)  # triage's probe is untouched


def test_the_scoped_contract_is_abstract():
    for name in (
        "lint_json_cmd",
        "parse_lint",
        "integration_test_cmd",
        "collect_ids_cmd",
        "parse_collected_ids",
        "selected_tests_cmd",
    ):
        assert name in ToolchainAdapter.__abstractmethods__, name


def test_python_declares_policy_paths_and_suppression_syntax():
    assert "pyproject.toml" in PY.lint_policy_globs and "ruff.toml" in PY.lint_policy_globs
    import re

    assert re.search(PY.suppression_pattern, "import os  # noqa: F401")
```

If any assertion in this file fails against the **real** tools for a reason other than "not implemented yet" (for example a different node-id shape, or ruff JSON wrapped in other output), **SG-3 fires**: stop and report the observed output.

`tests/test_toolchain_junit.py` (hand-written XML, pinning the Windows shapes above):

```python
from sdlc.toolchain.junit import testcase_outcomes

XML = """<?xml version="1.0"?><testsuites><testsuite tests="5">
<testcase classname="" name="tests.test_broken" file="tests/test_broken.py"><error/></testcase>
<testcase classname="tests.test_a.TestC" name="test_y" file="tests\\test_a.py"><failure/></testcase>
<testcase classname="tests.test_a" name="test_p[2]" file="tests\\test_a.py"><failure/></testcase>
<testcase classname="tests.test_a" name="test_ok" file="tests\\test_a.py"/>
<testcase classname="tests.test_a" name="test_skip" file="tests\\test_a.py"><skipped/></testcase>
</testsuite></testsuites>"""


def test_node_ids_are_posix_and_class_aware():
    assert testcase_outcomes(XML) == {
        "tests/test_broken.py": False,
        "tests/test_a.py::TestC::test_y": False,
        "tests/test_a.py::test_p[2]": False,
        "tests/test_a.py::test_ok": True,
    }


def test_missing_or_unparseable_report_is_none_not_empty():
    assert testcase_outcomes("") is None
    assert testcase_outcomes("<not xml") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_toolchain_junit.py tests/test_toolchain_scoped_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.toolchain.junit'`

- [ ] **Step 3: `src/sdlc/toolchain/junit.py`**

```python
"""pytest legacy-family JUnit -> {node id: passed} (diff-scoped gates DS6).

Node ids must be re-runnable, so the class segment is rebuilt from
`classname` minus the module path, and a collection error (classname="")
keys on its module file. `file` is normalized to POSIX: on Windows pytest
writes `\\` for ordinary cases and `/` for collection errors. Parsed with
defusedxml, because the report comes from untrusted code under test.
Returns None, never {}, for a missing or unparseable report, so the caller
fails closed instead of reading "no failures".
"""

from __future__ import annotations

import defusedxml.ElementTree as DET
from defusedxml.common import DefusedXmlException

from ..change_scope import normalize_path


def _node_id(tc) -> str:
    file_attr = normalize_path(tc.get("file") or "")
    name = tc.get("name", "")
    classname = tc.get("classname", "")
    if not classname:
        return file_attr or name.replace(".", "/") + ".py"
    module = file_attr[:-3].replace("/", ".") if file_attr.endswith(".py") else ""
    head = file_attr or classname.replace(".", "/") + ".py"
    parts = [head]
    if module and classname.startswith(module + "."):
        parts.extend(classname[len(module) + 1 :].split("."))
    parts.append(name)
    return "::".join(parts)


def testcase_outcomes(xml_text: str) -> dict[str, bool] | None:
    if not xml_text.strip():
        return None
    try:
        root = DET.fromstring(xml_text)
    except (DefusedXmlException, DET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    out: dict[str, bool] = {}
    for suite in suites:
        for tc in suite.iter("testcase"):
            if tc.find("skipped") is not None:
                continue
            node = _node_id(tc)
            failed = tc.find("failure") is not None or tc.find("error") is not None
            out[node] = out.get(node, True) and not failed
    return out
```

- [ ] **Step 4: The adapter contract**

In `src/sdlc/toolchain/adapters.py`, add the imports `import json`, `import re` and `from collections.abc import Sequence` (keep the existing `Sequence` import if present), plus `from ..change_scope import normalize_path`. Then add to `ToolchainAdapter`, after `lint_cmd`:

```python
    # Diff-scoped gates (DS5/DS6). Declarative, so a language adds no gate code
    # (FR-108). E-30a/b/c adapters must implement every method below.
    lint_policy_globs: tuple[str, ...] = ()
    suppression_pattern: str = ""  # regex; "" = no inline suppression syntax

    @abstractmethod
    def lint_json_cmd(self) -> str:
        """Machine-readable lint over the cwd; exit 0 whether or not it found anything."""

    @abstractmethod
    def parse_lint(self, code: int, out: str, root: str) -> list[tuple[str, str, int]] | None:
        """(rule, repo-relative POSIX path, 1-based row) per finding. None = the
        tool failed (or reported an I/O error), never "no findings"."""

    @abstractmethod
    def integration_test_cmd(self, junit_out: str, coverage: bool = True) -> str:
        """The merge gate's whole-suite run: NO early stop of any kind (an
        early stop hides introduced failures behind pre-existing ones), per-test
        JUnit at junit_out, and coverage.xml when coverage=True."""

    @abstractmethod
    def collect_ids_cmd(self, paths: Sequence[str]) -> str: ...

    @abstractmethod
    def parse_collected_ids(self, out: str) -> set[str]: ...

    @abstractmethod
    def selected_tests_cmd(self, node_ids: Sequence[str], junit_out: str) -> str: ...
```

Add to `PythonToolchain`, after `lint_cmd`:

```python
    lint_policy_globs = ("pyproject.toml", "ruff.toml", ".ruff.toml", "*/ruff.toml", "*/.ruff.toml")
    suppression_pattern = r"#\s*noqa\b"

    _PYTEST_GATE = (
        "pytest -q -p no:cacheprovider --continue-on-collection-errors "
        "-o junit_family=legacy"
    )

    def lint_json_cmd(self) -> str:
        return "ruff check --output-format json --exit-zero --no-cache ."

    def parse_lint(self, code: int, out: str, root: str) -> list[tuple[str, str, int]] | None:
        if code != 0:
            return None
        m = re.search(r"(?m)^\[", out)
        if m is None:
            return None
        try:
            rows = json.loads(out[m.start() :])
        except ValueError:
            return None
        found: list[tuple[str, str, int]] = []
        for row in rows:
            rule = row.get("code") or "syntax-error"
            if rule == "E902":  # ruff's I/O error: the tool could not read a file
                return None
            path = normalize_path(os.path.relpath(row["filename"], root))
            found.append((rule, path, int(row["location"]["row"])))
        return sorted(found)

    def integration_test_cmd(self, junit_out: str, coverage: bool = True) -> str:
        base = f"{self._PYTEST_GATE} --junitxml={junit_out}"
        return f"{base} --cov=. --cov-report=xml:coverage.xml" if coverage else base

    def collect_ids_cmd(self, paths: Sequence[str]) -> str:
        quoted = " ".join(f'"{p}"' for p in paths)
        return f"pytest --collect-only -q -p no:cacheprovider --continue-on-collection-errors {quoted}"

    def parse_collected_ids(self, out: str) -> set[str]:
        return {
            ln.strip()
            for ln in out.splitlines()
            if "::" in ln and not ln[:1].isspace() and not ln.startswith(("ERROR", "="))
        }

    def selected_tests_cmd(self, node_ids: Sequence[str], junit_out: str) -> str:
        quoted = " ".join(f'"{n}"' for n in node_ids)
        return f"{self._PYTEST_GATE} --junitxml={junit_out} {quoted}"
```

Double quotes, not `shlex.quote`: `create_subprocess_shell` runs `cmd.exe` on the Windows host, and `cmd.exe` does not honour single quotes.

**Shell safety (required).** Node ids and paths reaching `collect_ids_cmd` / `selected_tests_cmd` come from a JUnit report written by **untrusted code under test**. A crafted test name (for example `test_x["&del /q *&"]`) must never reach a shell. Add to `src/sdlc/toolchain/junit.py`:

```python
import re

_SHELL_SAFE = re.compile(r"^[A-Za-z0-9_./:\-\[\]]+$")


def shell_safe(node_id: str) -> bool:
    """A node id may be interpolated into a shell command only if it matches a
    strict allowlist. Callers treat an unsafe id as unattributable -- which,
    for the merge gate, means introduced (fail toward blocking)."""
    return bool(_SHELL_SAFE.fullmatch(node_id))
```

At the top of both `collect_ids_cmd` and `selected_tests_cmd` in `PythonToolchain`, add the guard below (import `shell_safe` from `.junit`):

```python
        unsafe = [p for p in node_ids if not shell_safe(p)]  # `paths` in collect_ids_cmd
        if unsafe:
            raise ValueError(f"refusing to shell-interpolate unsafe test ids: {unsafe[:3]}")
```

Then add this test to `tests/test_toolchain_junit.py`:

```python
import pytest

from sdlc.toolchain.adapters import PythonToolchain
from sdlc.toolchain.junit import shell_safe


def test_crafted_ids_never_reach_a_shell():
    evil = 'tests/t.py::test_x["&del /q *&"]'
    assert not shell_safe(evil)
    assert shell_safe("tests/test_a.py::TestC::test_p[2]")
    with pytest.raises(ValueError):
        PythonToolchain().selected_tests_cmd([evil], "o.xml")
    with pytest.raises(ValueError):
        PythonToolchain().collect_ids_cmd([evil])
```

- [ ] **Step 4b: Existing adapter test doubles implement the contract**

The gate contract is deliberately **abstract**, like `test_cmd` / `lint_cmd` / `oracle_test_cmd` already are. `adapters.py:37-39`'s "concrete defaults, not abstract" convention covers triage *facts*, where a missing value degrades to `not_collected`. A gate method that silently defaulted would let a new language adapter ship with no scoped gate at all, so its absence must fail at instantiation (`test_the_scoped_contract_is_abstract` pins this).

Add these six methods to `_Bare` in `tests/test_toolchain_triage_extension.py` and to `_NoParser` in `tests/test_triage_outliers.py`, directly after each class's `oracle_test_cmd`. The properties those files test are triage facts and are unaffected.

```python
    def lint_json_cmd(self) -> str:
        return "true"

    def parse_lint(self, code: int, out: str, root: str):
        return None

    def integration_test_cmd(self, junit_out: str, coverage: bool = True) -> str:
        return "true"

    def collect_ids_cmd(self, paths) -> str:
        return "true"

    def parse_collected_ids(self, out: str) -> set[str]:
        return set()

    def selected_tests_cmd(self, node_ids, junit_out: str) -> str:
        return "true"
```

Then run `grep -rn "(ToolchainAdapter)" tests src`. Every subclass it lists must be `PythonToolchain`, `_Bare`, or `_NoParser`; any other → SG-1.

- [ ] **Step 5: Run to verify they pass**

Run, one command per Bash call:
- `pytest tests/test_toolchain_junit.py tests/test_toolchain_scoped_contract.py tests/test_toolchain_triage_extension.py tests/test_triage_outliers.py -q`
- `pytest -q`

Expected: PASS

- [ ] **Step 6: Commit**

Message file `.git/COMMIT_MSG_T4`:
```
feat(toolchain): scoped lint/test adapter contract and JUnit node ids

DS5/DS6 (FR-108): machine-readable lint with a parser that tells
findings from tool failure, lint-policy globs and a suppression
pattern, and a whole-suite gate command with no early stop and
--continue-on-collection-errors. JUnit parsing rebuilds re-runnable
node ids. test_cmd is unchanged for triage's build probe.
```
```
git add src/sdlc/toolchain/junit.py
git add src/sdlc/toolchain/adapters.py
git add tests/test_toolchain_junit.py
git add tests/test_toolchain_scoped_contract.py
git add tests/test_toolchain_triage_extension.py
git add tests/test_triage_outliers.py
git commit -F .git/COMMIT_MSG_T4
```

---

### Task 5: merge — scoped lint report

**Files:**
- Modify: `src/sdlc/stages/merge/models.py` (new `LintFinding`, `ScopedLintReport`, `ScopedTestReport`)
- Create: `src/sdlc/stages/merge/scoping.py` (`scoped_lint` here; `scoped_tests` in Task 6)
- Modify: `src/sdlc/stages/merge/activities.py:109-186` (`IntegrationChecksInput`, `IntegrationChecks`, `run_integration_checks`)
- Test: `tests/test_scoped_lint.py`

**Interfaces:**
- Consumes: `change_scope.delta`, `rename_map`, `normalize_line` (Task 1); `ToolchainAdapter.lint_json_cmd` / `parse_lint` / `lint_policy_globs` / `suppression_pattern` (Task 4); `prepare_base_worktree` (Task 2, tests only).
- Produces:
  - `LintFinding(rule: str, path: str, line: str)`
  - `ScopedLintReport(state, reason="", introduced: list[LintFinding]=[], preexisting: int=0, resolved: int=0, policy_paths_changed: list[str]=[], suppressions_added: int=0)`
  - `ScopedTestReport(state, reason="", introduced: list[str]=[], preexisting: list[str]=[], preexisting_flaky: list[str]=[], head_failed: int=0, diagnostic: str="")`
  - `scoped_lint(adapter, head_wt: str, base_wt: str | None, base_reason: str, base_sha: str, renames: list[list[str]], env: dict[str, str] | None, timeout_s: int) -> ScopedLintReport` (async)
  - `IntegrationChecksInput` gains `base_worktree: str | None = None`, `base_reason: str = ""`, `base_sha: str = ""`, `renames: list[list[str]] = field(default_factory=list)`
  - `IntegrationChecks` gains `lint: ScopedLintReport | None = None` (`None` iff no toolchain adapter). **Transitional:** `lint_clean`, `lint_detail` and `qa` stay until Task 7 switches the step and deletes them.
- Both points are linted with **the same tool binary** (the head environment's `env`), each under its own tree's configuration (DS5).

- [ ] **Step 1: Write the failing tests**

```python
"""DS5/DS7: lint measured at both points; policy relaxation reported."""

import os
import pathlib
import subprocess
import sysconfig

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.merge.models import ScopedLintReport
from sdlc.stages.merge.scoping import scoped_lint
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.vcs import BaseWorktreeInput, prepare_base_worktree

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]
PY = PythonToolchain()
RUFF_F401 = '[lint]\nselect = ["F401"]\n'


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _commit(repo, msg) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = sysconfig.get_path("scripts") + os.pathsep + env.get("PATH", "")
    return env


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "ruff.toml").write_text(RUFF_F401, encoding="utf-8")
    (r / "legacy.py").write_text("import os\n", encoding="utf-8")  # pre-existing F401
    return r


async def _lint(repo, base) -> ScopedLintReport:
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run", base))
    renames = [
        [p[1], p[2]]
        for p in (
            ln.split("\t")
            for ln in _git(repo, "diff", "-M", "--name-status", f"{base}...HEAD").splitlines()
        )
        if len(p) == 3 and p[0].startswith("R")
    ]
    return await scoped_lint(PY, str(repo), wt.path, wt.reason, base, renames, _env(), 120)


@pytest.mark.asyncio
async def test_pre_existing_debt_is_counted_not_introduced(repo):
    base = _commit(repo, "base")
    (repo / "new.py").write_text("x = 1\n", encoding="utf-8")
    _commit(repo, "clean change")
    rep = await _lint(repo, base)
    assert rep.state is CollectionState.MEASURED, rep.reason
    assert rep.introduced == [] and rep.preexisting == 1


@pytest.mark.clause("MERGE-1.10")
@pytest.mark.asyncio
async def test_a_new_finding_is_introduced_with_its_line(repo):
    base = _commit(repo, "base")
    (repo / "new.py").write_text("import sys\n", encoding="utf-8")
    _commit(repo, "adds an unused import")
    rep = await _lint(repo, base)
    assert [(f.rule, f.path, f.line) for f in rep.introduced] == [("F401", "new.py", "import sys")]


@pytest.mark.asyncio
async def test_a_rename_keeps_debt_pre_existing(repo):
    base = _commit(repo, "base")
    _git(repo, "mv", "legacy.py", "moved.py")
    _commit(repo, "rename")
    rep = await _lint(repo, base)
    assert rep.introduced == [] and rep.preexisting == 1


@pytest.mark.asyncio
async def test_a_finding_caused_in_an_untouched_file_is_introduced(repo):
    """Case (x): the cross-file effect DS3 exists for."""
    (repo / "long.py").write_text("x = " + "1 + " * 40 + "1\n", encoding="utf-8")
    base = _commit(repo, "base")
    (repo / "ruff.toml").write_text('[lint]\nselect = ["F401", "E501"]\n', encoding="utf-8")
    _commit(repo, "enable E501")
    rep = await _lint(repo, base)
    assert [f.path for f in rep.introduced] == ["long.py"]
    assert rep.policy_paths_changed == ["ruff.toml"]


@pytest.mark.asyncio
async def test_policy_relaxation_and_suppression_are_reported_not_blocked(repo):
    """Case (ix): DS5's named residual."""
    base = _commit(repo, "base")
    (repo / "new.py").write_text("import sys  # noqa: F401\n", encoding="utf-8")
    _commit(repo, "suppressed")
    rep = await _lint(repo, base)
    assert rep.introduced == [] and rep.suppressions_added == 1


@pytest.mark.asyncio
async def test_an_unmaterialized_base_is_not_collected(repo):
    _commit(repo, "base")
    rep = await scoped_lint(PY, str(repo), None, "locked", "abc", [], _env(), 120)
    assert rep.state is CollectionState.NOT_COLLECTED and "locked" in rep.reason


@pytest.mark.asyncio
async def test_a_lint_tool_failure_is_not_collected(repo, monkeypatch):
    base = _commit(repo, "base")
    monkeypatch.setattr(PythonToolchain, "lint_json_cmd", lambda self: "ruff --no-such-flag")
    rep = await _lint(repo, base)
    assert rep.state is CollectionState.NOT_COLLECTED and rep.introduced == []


def test_unmeasured_reports_cannot_carry_counts():
    with pytest.raises(ValueError):
        ScopedLintReport(state=CollectionState.NOT_COLLECTED, reason="x", preexisting=1)
    with pytest.raises(ValueError):
        ScopedLintReport(state=CollectionState.NOT_COLLECTED)
```

`MERGE-1.10` does not exist until Task 7 adds it to `merge.md`, so `scripts/check_clauses.py` reports this test as citing a missing clause. **For this task only**, that one report is expected; Task 7 resolves it. Every other clause report is SG-5.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_scoped_lint.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.stages.merge.scoping'`

- [ ] **Step 3: Models**

In `src/sdlc/stages/merge/models.py`, change the imports to `from pydantic import BaseModel, Field, model_validator` and `from ...measurement import CollectionState, Measurement`, then append:

```python
def _unmeasured_is_empty(state: CollectionState, reason: str, **carried: object) -> None:
    """FR-915 at the type: an unmeasured delta carries nothing that could read
    as "zero introduced", and says why it is unmeasured."""
    if state is CollectionState.MEASURED:
        return
    loaded = [name for name, value in carried.items() if value]
    if loaded:
        raise ValueError(f"{state.value} report must not carry {loaded}")
    if not reason.strip():
        raise ValueError(f"{state.value} report requires a reason")


class LintFinding(BaseModel):
    rule: str
    path: str  # repo-relative POSIX
    line: str  # normalized source line: the DS3 identity text


class ScopedLintReport(BaseModel):
    """DS5/DS7: lint at the pinned base and the integration head. `lint_clean`
    passes iff MEASURED and `introduced` is empty. Policy relaxation is
    reported, never gated (DS5's named residual)."""

    state: CollectionState
    reason: str = ""
    introduced: list[LintFinding] = Field(default_factory=list)
    preexisting: int = 0
    resolved: int = 0
    policy_paths_changed: list[str] = Field(default_factory=list)
    suppressions_added: int = 0

    @model_validator(mode="after")
    def _fail_closed(self) -> ScopedLintReport:
        _unmeasured_is_empty(
            self.state,
            self.reason,
            introduced=self.introduced,
            preexisting=self.preexisting,
            resolved=self.resolved,
            policy_paths_changed=self.policy_paths_changed,
            suppressions_added=self.suppressions_added,
        )
        return self


class ScopedTestReport(BaseModel):
    """DS6/DS7: whole suite at head, targeted corroboration at base.
    `build_integration_green` passes iff MEASURED and `introduced` is empty."""

    state: CollectionState
    reason: str = ""
    introduced: list[str] = Field(default_factory=list)
    preexisting: list[str] = Field(default_factory=list)
    preexisting_flaky: list[str] = Field(default_factory=list)
    head_failed: int = 0
    diagnostic: str = ""

    @model_validator(mode="after")
    def _fail_closed(self) -> ScopedTestReport:
        _unmeasured_is_empty(
            self.state,
            self.reason,
            introduced=self.introduced,
            preexisting=self.preexisting,
            preexisting_flaky=self.preexisting_flaky,
            head_failed=self.head_failed,
        )
        return self
```

- [ ] **Step 4: `src/sdlc/stages/merge/scoping.py` — scoped lint**

```python
"""Activity-side helpers for the diff-scoped merge gate (DS5, DS6).

Called from run_integration_checks, never from workflow code: they run tools
and read files. Every failure to compute a delta returns a NOT_COLLECTED
report with its reason, so the absolute check fails closed (DS7).
"""

from __future__ import annotations

import fnmatch
import pathlib
import re

from ...change_scope import FindingKey, delta, normalize_line, rename_map
from ...measurement import CollectionState
from ...process import _bounded_shell
from ...toolchain.adapters import ToolchainAdapter
from ...vcs.git import _git
from .models import LintFinding, ScopedLintReport


def _lint_nc(reason: str) -> ScopedLintReport:
    return ScopedLintReport(state=CollectionState.NOT_COLLECTED, reason=reason)


async def _lint_point(
    adapter: ToolchainAdapter, wt: str, env: dict[str, str] | None, timeout_s: int
) -> list[LintFinding] | str:
    code, out = await _bounded_shell(adapter.lint_json_cmd(), wt, timeout_s, env=env)
    rows = adapter.parse_lint(code, out, wt)
    if rows is None:
        return f"lint tool failed (exit {code}): {out[-300:]}"
    lines: dict[str, list[str]] = {}
    found: list[LintFinding] = []
    for rule, path, row in rows:
        if path not in lines:
            try:
                lines[path] = (
                    pathlib.Path(wt, path).read_text(encoding="utf-8", errors="replace").splitlines()
                )
            except OSError:
                return f"could not read {path} to identify its lint finding"
        text = lines[path][row - 1] if 0 < row <= len(lines[path]) else ""
        found.append(LintFinding(rule=rule, path=path, line=normalize_line(text)))
    return found


def _policy_and_suppressions(
    adapter: ToolchainAdapter, head_wt: str, base_sha: str
) -> tuple[list[str], int] | str:
    rng = f"{base_sha}...HEAD"
    names = _git(["diff", "--name-only", rng], head_wt)
    patch = _git(["diff", "-U0", rng], head_wt)
    if names.returncode != 0 or patch.returncode != 0:
        return f"git diff against base {base_sha!r} failed"
    policy = sorted(
        n
        for n in names.stdout.splitlines()
        if any(fnmatch.fnmatch(n, g) for g in adapter.lint_policy_globs)
    )
    pattern = re.compile(adapter.suppression_pattern) if adapter.suppression_pattern else None
    added = sum(
        1
        for ln in patch.stdout.splitlines()
        if pattern is not None and ln.startswith("+") and not ln.startswith("+++")
        and pattern.search(ln)
    )
    return policy, added


def _lint_key(f: LintFinding) -> FindingKey:
    return ("lint", f.rule, f.path, f.line)


async def scoped_lint(
    adapter: ToolchainAdapter,
    head_wt: str,
    base_wt: str | None,
    base_reason: str,
    base_sha: str,
    renames: list[list[str]],
    env: dict[str, str] | None,
    timeout_s: int,
) -> ScopedLintReport:
    """DS5: the same binary (the head env's) lints both points, each under its
    own tree's configuration, so a version skew cannot manufacture a delta."""
    if base_wt is None:
        return _lint_nc(f"base not materialized: {base_reason or 'no reason given'}")
    head = await _lint_point(adapter, head_wt, env, timeout_s)
    if isinstance(head, str):
        return _lint_nc(f"head point: {head}")
    base = await _lint_point(adapter, base_wt, env, timeout_s)
    if isinstance(base, str):
        return _lint_nc(f"base point: {base}")
    extra = _policy_and_suppressions(adapter, head_wt, base_sha)
    if isinstance(extra, str):
        return _lint_nc(extra)
    introduced, pre, res = delta(base, head, _lint_key, rename_map(renames))
    return ScopedLintReport(
        state=CollectionState.MEASURED,
        introduced=introduced,
        preexisting=pre,
        resolved=res,
        policy_paths_changed=extra[0],
        suppressions_added=extra[1],
    )
```

- [ ] **Step 5: Wire into `run_integration_checks`**

In `src/sdlc/stages/merge/activities.py`:
- change `from dataclasses import dataclass` to `from dataclasses import dataclass, field`;
- extend the `.models` import with `ScopedLintReport`;
- add `from .scoping import scoped_lint`.

Add these fields to `IntegrationChecksInput`, after `changed_files`:

```python
    base_worktree: str | None = None  # prepare_base_worktree's path (DS2)
    base_reason: str = ""  # why base_worktree is None
    base_sha: str = ""
    renames: list[list[str]] = field(default_factory=list)
```

Add this field to `IntegrationChecks`:

```python
    lint: ScopedLintReport | None = None  # None iff no toolchain adapter
```

In `run_integration_checks`:
- In the Python `setup_error` branch, set `lint=ScopedLintReport(state=CollectionState.NOT_COLLECTED, reason=setup_error)` on the returned object. Add `from ...measurement import CollectionState` if it is not already imported.
- Before the final `return`, compute:

```python
    lint = await scoped_lint(
        adapter,
        inp.worktree,
        inp.base_worktree,
        inp.base_reason,
        inp.base_sha,
        inp.renames,
        env,
        inp.lint_timeout_s,
    )
```

  and pass `lint=lint` into the returned `IntegrationChecks`.

- [ ] **Step 6: Run to verify it passes**

Run: `pytest tests/test_scoped_lint.py tests/test_integration_checks.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

Message file `.git/COMMIT_MSG_T5`:
```
feat(merge): scoped lint report at the pinned base and the head

DS5/DS7: run_integration_checks now also lints the base worktree with
the head environment's binary and returns the multiset delta as a
typed ScopedLintReport, with policy paths changed and suppressions
added reported rather than gated. The step still reads the old
fields until the wiring task.
```
```
git add src/sdlc/stages/merge/models.py
git add src/sdlc/stages/merge/scoping.py
git add src/sdlc/stages/merge/activities.py
git add tests/test_scoped_lint.py
git commit -F .git/COMMIT_MSG_T5
```

---

### Task 6: merge — scoped test report

**Files:**
- Modify: `src/sdlc/stages/merge/scoping.py` (add `scoped_tests`)
- Modify: `src/sdlc/stages/merge/activities.py:161-186` (the head test run moves into `scoped_tests`)
- Test: `tests/test_scoped_tests.py`
- Modify: `tests/test_integration_checks.py` (the two `slow` tests get a real base — without one, `scoped_tests` is `NOT_COLLECTED` by DS6 rule 1)

**Interfaces:**
- Consumes:
  - `ToolchainAdapter.integration_test_cmd`, `collect_ids_cmd`, `parse_collected_ids`, `selected_tests_cmd`, `classify_test_exit`; `testcase_outcomes`, `shell_safe` (Task 4)
  - `ScopedTestReport` (Task 5)
  - `_stopped_early`, `_diagnostic_slice`, `_ensure_python_env` from `stages/qa/activities.py` (merge's activities already import the first two)
- Produces:
  - `scoped_tests(adapter, head_wt: str, base_wt: str | None, base_reason: str, renames: list[list[str]], env: dict[str, str] | None, provision_base: Callable[[], Awaitable[tuple[dict[str, str] | None, str | None]]], timeout_s: int) -> ScopedTestReport` (async)
  - `BASE_ATTEMPTS = 4` — 1 base run plus up to 3 corroborating re-runs (DS6)
  - `ID_CHUNK = 50` — node ids per command (the `cmd.exe` 8191-character line limit)
  - `IntegrationChecks` gains `tests: ScopedTestReport | None = None`. The transitional `qa` is derived from it until Task 7 deletes it.

DS6 rules, in order, for each head-failing id `n` (JUnit failure or error, collection errors included):
1. Unmaterialized base → the **whole report** is `NOT_COLLECTED`, even when head has no failures. This is the spec's Failure-modes row: an unbuildable base fails all three scoped checks.
2. Map `n`'s file part back through the renames (head path → base path).
3. `n` is not `shell_safe` → introduced; it never reaches a shell.
4. `n`'s file is absent at base, or `n` is not collected at base → introduced (a new test: zero flake tolerance).
5. Run the present ids at base; any failure → pre-existing.
6. Ids that passed: re-run at base, up to 3 more attempts in total (attempts 2–4). Any failure → `preexisting_flaky`. Pass on all 4 → introduced.
7. There is **no head retry**.

- [ ] **Step 1: Write the failing tests**

```python
"""DS6/DS7: whole suite at head, targeted corroboration at base."""

import os
import pathlib
import subprocess
import sysconfig
import textwrap

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.merge.scoping import scoped_tests
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.vcs import BaseWorktreeInput, prepare_base_worktree

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]
PY = PythonToolchain()


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _commit(repo, msg) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = sysconfig.get_path("scripts") + os.pathsep + env.get("PATH", "")
    return env


async def _provision():
    return _env(), None


def _write(repo: pathlib.Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body), encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / ".gitignore").write_text(".sdlc-junit*.xml\n*.count\ncoverage.xml\n", encoding="utf-8")
    _write(r, "tests/test_ok.py", "def test_ok():\n    assert True\n")
    return r


async def _scope(repo, base, provision=_provision):
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run", base))
    return await scoped_tests(PY, str(repo), wt.path, wt.reason, [], _env(), provision, 300)


@pytest.mark.asyncio
async def test_a_green_head_needs_no_base_run(repo, monkeypatch):
    base = _commit(repo, "base")
    called = []
    monkeypatch.setattr(
        PythonToolchain, "selected_tests_cmd", lambda self, ids, out: called.append(ids) or ""
    )
    rep = await _scope(repo, base)
    assert rep.state is CollectionState.MEASURED and rep.head_failed == 0 and not called


@pytest.mark.asyncio
async def test_a_failure_that_also_fails_at_base_is_pre_existing(repo):
    _write(repo, "tests/test_old.py", "def test_old():\n    assert False\n")
    base = _commit(repo, "base")
    _write(repo, "src_new.py", "x = 1\n")
    _commit(repo, "unrelated change")
    rep = await _scope(repo, base)
    assert rep.introduced == [] and rep.preexisting == ["tests/test_old.py::test_old"]


@pytest.mark.clause("MERGE-1.10")
@pytest.mark.asyncio
async def test_breaking_a_base_passing_test_is_introduced(repo):
    _write(repo, "tests/test_calc.py", "def test_calc():\n    assert 1 + 1 == 2\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_calc.py", "def test_calc():\n    assert 1 + 1 == 3\n")
    _commit(repo, "breaks it")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_calc.py::test_calc"]


@pytest.mark.asyncio
async def test_a_new_failing_test_is_introduced_with_zero_tolerance(repo):
    base = _commit(repo, "base")
    _write(repo, "tests/test_new.py", "def test_new():\n    assert False\n")
    _write(repo, "tests/test_ok.py", "def test_ok():\n    assert True\n\n\ndef test_added():\n    assert False\n")
    _commit(repo, "new tests")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_new.py::test_new", "tests/test_ok.py::test_added"]


@pytest.mark.asyncio
async def test_a_base_flaky_test_is_pre_existing_flaky(repo):
    """Case (vii): passes on base attempt 1, fails on attempt 2."""
    _write(
        repo,
        "tests/test_flaky.py",
        """
        import pathlib
        C = pathlib.Path(__file__).with_suffix(".count")
        def test_flaky():
            n = int(C.read_text()) if C.exists() else 0
            C.write_text(str(n + 1))
            assert n != 1
        """,
    )
    base = _commit(repo, "base")
    _write(repo, "tests/test_flaky.py", "def test_flaky():\n    assert False\n")
    _commit(repo, "head breaks it for real")
    rep = await _scope(repo, base)
    assert rep.preexisting_flaky == ["tests/test_flaky.py::test_flaky"]
    assert rep.introduced == []


@pytest.mark.asyncio
async def test_an_introduced_failure_behind_many_pre_existing_ones_is_seen(repo):
    """Case (iii): the --maxfail leak. 30 pre-existing failures sort first."""
    body = "\n".join(f"def test_a{i:02d}():\n    assert False\n" for i in range(30))
    _write(repo, "tests/test_aa_debt.py", body)
    _write(repo, "tests/test_zz.py", "def test_zz():\n    assert True\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_zz.py", "def test_zz():\n    assert False\n")
    _commit(repo, "breaks the last test")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_zz.py::test_zz"]
    assert len(rep.preexisting) == 30


@pytest.mark.asyncio
async def test_a_pre_existing_collection_error_is_pre_existing(repo):
    _write(repo, "tests/test_broken.py", "import nonexistent_mod_xyz\n")
    base = _commit(repo, "base")
    _write(repo, "other.py", "x = 1\n")
    _commit(repo, "unrelated")
    rep = await _scope(repo, base)
    assert rep.introduced == [] and rep.preexisting == ["tests/test_broken.py"]


@pytest.mark.asyncio
async def test_an_unsafe_id_is_introduced_without_reaching_a_shell(repo):
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_odd.py",
        """
        import pytest
        @pytest.mark.parametrize("v", [1], ids=["a&b"])
        def test_odd(v):
            assert False
        """,
    )
    _commit(repo, "odd id")
    rep = await _scope(repo, base)
    assert rep.introduced == ["tests/test_odd.py::test_odd[a&b]"]


@pytest.mark.asyncio
async def test_unmeasurable_heads_and_bases_fail_closed(repo, monkeypatch):
    base = _commit(repo, "base")
    rep = await scoped_tests(PY, str(repo), None, "locked", [], _env(), _provision, 300)
    assert rep.state is CollectionState.NOT_COLLECTED and "locked" in rep.reason

    async def broken():
        return None, "pip exploded"

    _write(repo, "tests/test_ok.py", "def test_ok():\n    assert False\n")
    _commit(repo, "fail")
    rep = await _scope(repo, base, provision=broken)
    assert rep.state is CollectionState.NOT_COLLECTED and "pip exploded" in rep.reason

    monkeypatch.setattr(
        PythonToolchain,
        "integration_test_cmd",
        lambda self, junit_out, coverage=True: 'python -c "pass"',
    )
    rep = await _scope(repo, base)
    assert rep.state is CollectionState.NOT_COLLECTED  # no JUnit report was written


@pytest.mark.asyncio
async def test_a_head_that_collects_no_tests_is_not_collected(repo):
    _git(repo, "rm", "-q", "tests/test_ok.py")
    base = _commit(repo, "base")
    rep = await _scope(repo, base)
    assert rep.state is CollectionState.NOT_COLLECTED
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_scoped_tests.py -q`
Expected: FAIL — `ImportError: cannot import name 'scoped_tests'`

- [ ] **Step 3: Implement `scoped_tests`**

Append to `src/sdlc/stages/merge/scoping.py`. Add `import os` and `from collections.abc import Awaitable, Callable` to its imports, plus:

```python
from ...stages.qa.activities import _diagnostic_slice, _stopped_early
from ...toolchain.junit import shell_safe, testcase_outcomes
from .models import ScopedTestReport
```

```python
JUNIT = ".sdlc-junit.xml"
BASE_JUNIT = ".sdlc-junit-base.xml"
BASE_ATTEMPTS = 4  # DS6: one base run plus up to three corroborating re-runs
ID_CHUNK = 50  # node ids per command: cmd.exe caps a command line at 8191 chars
_PYTEST_USAGE_ERROR = 4

Provision = Callable[[], Awaitable[tuple[dict[str, str] | None, str | None]]]


def _test_nc(reason: str) -> ScopedTestReport:
    return ScopedTestReport(state=CollectionState.NOT_COLLECTED, reason=reason)


def _read_report(wt: str, name: str) -> dict[str, bool] | None:
    try:
        return testcase_outcomes(pathlib.Path(wt, name).read_text(encoding="utf-8"))
    except OSError:
        return None


def _clear(wt: str, name: str) -> None:
    try:
        os.remove(os.path.join(wt, name))
    except FileNotFoundError:
        pass


async def _head_run(adapter, head_wt, env, timeout_s) -> tuple[dict[str, bool], str] | str:
    _clear(head_wt, JUNIT)
    code, out = await _bounded_shell(adapter.integration_test_cmd(JUNIT, True), head_wt, timeout_s, env=env)
    if code == _PYTEST_USAGE_ERROR:  # coverage tooling unavailable: honest run without it
        _clear(head_wt, JUNIT)
        code, out = await _bounded_shell(adapter.integration_test_cmd(JUNIT, False), head_wt, timeout_s, env=env)
    if code == -1:
        return f"head test run timed out after {timeout_s}s"
    if _stopped_early(out):
        return "head test run stopped early: tests after the stop never ran"
    kind = adapter.classify_test_exit(code)
    if kind == "no_tests":
        return "head test run collected no tests"
    outcomes = _read_report(head_wt, JUNIT)
    if outcomes is None:
        return f"head test run (exit {code}) wrote no parseable JUnit report"
    if kind == "failed_to_run" and all(outcomes.values()):
        return f"head test run failed to run (exit {code})"
    return outcomes, out


async def _base_outcomes(adapter, base_wt, ids, env, timeout_s) -> dict[str, bool] | str:
    merged: dict[str, bool] = {}
    for i in range(0, len(ids), ID_CHUNK):
        _clear(base_wt, BASE_JUNIT)
        # The exit code is ignored on purpose: every failing base test exits 1.
        # Attribution reads JUnit presence/absence; absence => introduced.
        await _bounded_shell(adapter.selected_tests_cmd(ids[i : i + ID_CHUNK], BASE_JUNIT), base_wt, timeout_s, env=env)
        got = _read_report(base_wt, BASE_JUNIT)
        if got is None:
            return "base re-run wrote no parseable JUnit report"
        merged.update(got)
    return merged


async def scoped_tests(
    adapter: ToolchainAdapter,
    head_wt: str,
    base_wt: str | None,
    base_reason: str,
    renames: list[list[str]],
    env: dict[str, str] | None,
    provision_base: Provision,
    timeout_s: int,
) -> ScopedTestReport:
    """DS6: the whole suite at head; attribution by targeted base corroboration."""
    if base_wt is None:
        return _test_nc(f"base not materialized: {base_reason or 'no reason given'}")
    head = await _head_run(adapter, head_wt, env, timeout_s)
    if isinstance(head, str):
        return _test_nc(head)
    outcomes, out = head
    failed = sorted(n for n, ok in outcomes.items() if not ok)
    if not failed:
        return ScopedTestReport(state=CollectionState.MEASURED)

    to_base_path = {new: old for old, new in rename_map(renames).items()}

    def to_base(nid: str) -> str:
        file, sep, rest = nid.partition("::")
        return to_base_path.get(file, file) + sep + rest

    introduced: list[str] = []
    present: dict[str, str] = {}  # base id -> head id
    for n in failed:
        b = to_base(n)
        file = b.partition("::")[0]
        if not shell_safe(b) or not os.path.isfile(os.path.join(base_wt, file)):
            introduced.append(n)
        else:
            present[b] = n

    base_env, err = await provision_base()
    if err:
        return _test_nc(f"base environment provisioning failed: {err}")

    needs_collect = sorted({b.partition("::")[0] for b in present if "::" in b})
    collected: set[str] = set()
    for i in range(0, len(needs_collect), ID_CHUNK):
        code, cout = await _bounded_shell(
            adapter.collect_ids_cmd(needs_collect[i : i + ID_CHUNK]), base_wt, timeout_s, env=base_env
        )
        if code not in (0, 1, 2, 5):
            return _test_nc(f"base collection failed (exit {code})")
        collected |= adapter.parse_collected_ids(cout)
    for b in [b for b in present if "::" in b and b not in collected]:
        introduced.append(present.pop(b))

    preexisting: list[str] = []
    flaky: list[str] = []
    passing = sorted(present)
    for attempt in range(1, BASE_ATTEMPTS + 1):
        if not passing:
            break
        got = await _base_outcomes(adapter, base_wt, passing, base_env, timeout_s)
        if isinstance(got, str):
            return _test_nc(got)
        still = []
        for b in passing:
            if b not in got:
                introduced.append(present[b])  # collected but never reported: unattributable
            elif not got[b]:
                (preexisting if attempt == 1 else flaky).append(present[b])
            else:
                still.append(b)
        passing = still
    introduced.extend(present[b] for b in passing)  # passed every base attempt

    return ScopedTestReport(
        state=CollectionState.MEASURED,
        introduced=sorted(introduced),
        preexisting=sorted(preexisting),
        preexisting_flaky=sorted(flaky),
        head_failed=len(failed),
        diagnostic=_diagnostic_slice(out),
    )
```

Wrap any line over 100 characters (`ruff format`).

- [ ] **Step 4: Wire into `run_integration_checks`**

In `src/sdlc/stages/merge/activities.py`:
- import `ScopedTestReport` from `.models` and `scoped_tests` from `.scoping`;
- add the field `tests: ScopedTestReport | None = None` to `IntegrationChecks`;
- in the `setup_error` branch, also set `tests=ScopedTestReport(state=CollectionState.NOT_COLLECTED, reason=setup_error)`;
- replace the old head test block (from `code, out = await _bounded_shell(adapter.test_cmd(coverage=True), ...` through the `qa = QAReport(...)` construction) with:

```python
    async def _provision_base():
        if adapter.kind is not ToolchainKind.PYTHON or inp.base_worktree is None:
            return env, None
        return await _ensure_python_env(inp.base_worktree, inp.setup_timeout_s)

    tests = await scoped_tests(
        adapter,
        inp.worktree,
        inp.base_worktree,
        inp.base_reason,
        inp.renames,
        env,
        _provision_base,
        inp.test_timeout_s,
    )
    # Transitional (removed in the step-wiring task): the step still reads qa.
    qa = QAReport(
        tests_passed=tests.state is CollectionState.MEASURED and tests.head_failed == 0,
        failing_tests=tests.introduced[:50],
        issues=[] if tests.head_failed == 0 else [tests.diagnostic or tests.reason],
    )
```

and pass `tests=tests` into the returned `IntegrationChecks`. Keep the `_PYTEST_USAGE_ERROR` constant in `activities.py` only if something still uses it; otherwise delete it there (it now lives in `scoping.py`).

- [ ] **Step 4b: Give the two slow integration tests a real base**

In `tests/test_integration_checks.py`, change both `slow` tests (`test_integration_checks_produces_real_coverage`, `test_integration_checks_installs_the_produced_projects_own_deps`) as follows:
- Add the `monkeypatch` fixture parameter.
- After writing the fixture files, make `tmp_path` a git repository with one commit. Run each of these via `subprocess.run([...], cwd=tmp_path, check=True)`:
  - `git init -q -b main`
  - `git add -A`
  - `git -c user.email=t@example.test -c user.name=t commit -q -m base`
- Set `monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path.parent / "wts"))`.
- Read `sha` with `git rev-parse HEAD`.
- Call `base = await prepare_base_worktree(BaseWorktreeInput(str(tmp_path), "run", sha))`.
- Pass `base_worktree=base.path, base_sha=sha` into `IntegrationChecksInput`.
- Replace `assert checks.qa.tests_passed is True` (and the `, checks.qa.issues` variant) with `assert checks.tests.state is CollectionState.MEASURED and checks.tests.head_failed == 0, checks.tests.reason`.
- Keep the `coverage.xml`, `.sdlc-venv` and `measure_coverage` assertions.
- Imports to add: `import subprocess`, `from sdlc.vcs import BaseWorktreeInput, prepare_base_worktree`.

Leave `test_integration_checks_degrades_without_adapter` alone in this task. Its `lint_clean`/`qa` assertions still hold until Task 7 deletes those fields.

- [ ] **Step 5: Run to verify it passes**

Run, one command per Bash call (never chain two pytest runs):
- `pytest tests/test_scoped_tests.py tests/test_scoped_lint.py -q`
- `pytest -m slow tests/test_integration_checks.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

Message file `.git/COMMIT_MSG_T6`:
```
feat(merge): scoped test report — whole suite at head, base attribution

DS6/DS7: the gate's head run no longer stops early and continues past
collection errors; failures are attributed by collecting and
re-running only the failing ids at the pinned base (up to four
attempts, no head retry), with unsafe or unknown ids counted as
introduced. Any failure to attribute is NOT_COLLECTED.
```
```
git add src/sdlc/stages/merge/scoping.py
git add src/sdlc/stages/merge/activities.py
git add tests/test_scoped_tests.py
git add tests/test_integration_checks.py
git commit -F .git/COMMIT_MSG_T6
```

---

### Task 7: wire the gate — pinned `base_sha`, scoped checks, contracts, fakes

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (`:211`, `:507`, `:723-727`, `:749-761`)
- Modify: `src/sdlc/workflows/AGENTS.md` (attribute-ownership table: a `_base_sha` row, per its Rule 1)
- Modify: `src/sdlc/stages/merge/step.py` (imports `:31-57`; `step` signature; `:260-346` check construction)
- Modify: `src/sdlc/stages/merge/activities.py` (`IntegrationChecks` loses `qa`, `lint_clean`, `lint_detail`; the no-adapter return)
- Modify: `src/sdlc/stages/qa/activities.py` (delete `security_scan` and `SecurityScanInput`; `ACTIVITIES`)
- Modify: `src/sdlc/stages/merge/merge.md`, `src/sdlc/stages/merge/AGENTS.md`, `src/sdlc/stages/qa/qa.md`, `src/sdlc/stages/qa/AGENTS.md`
- Modify: `tests/fakes/fake_activities.py`, `tests/merge/test_merge_slice_contract.py`, `tests/qa/test_qa_slice_contract.py`, `tests/test_security_floor.py`, `tests/test_integration_checks.py`
- Create: `tests/merge/test_scoped_absolute_checks.py`

**Interfaces:**
- Consumes: everything from Tasks 2–6.
- Produces:
  - `merge.step(..., base_sha: str = "")`
  - pure helpers in `step.py`:
    - `tests_check(r: ScopedTestReport) -> CheckResult`
    - `lint_check(r: ScopedLintReport) -> CheckResult`
    - `security_checks(r: ScopedSecurityReport) -> list[CheckResult]` — `security_scan_collected` first, then `security_no_critical`
  - `FeatureWorkflow._base_sha: str`
  - `IntegrationChecks(toolchain: str | None = None, lint: ScopedLintReport | None = None, tests: ScopedTestReport | None = None)`

- [ ] **Step 1: Write the failing tests**

`tests/merge/test_scoped_absolute_checks.py`:

```python
"""DS7/DS10: the four absolute checks, built from scoped reports, fail closed."""

import ast
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.core.models import IdeaBrief, PipelineConfig, ProjectMode
from sdlc.measurement import CollectionState, Measurement
from sdlc.stages import merge
from sdlc.stages.merge.activities import IntegrationChecks
from sdlc.stages.merge.models import (
    CoverageReport,
    LintFinding,
    ScopedLintReport,
    ScopedTestReport,
)
from sdlc.stages.merge.step import lint_check, security_checks, tests_check
from sdlc.stages.qa.models import QAReport, ScopedSecurityReport, SecurityFinding
from sdlc.vcs import BaseWorktree
from sdlc.workflows.models import TaskResult
from tests.merge.test_merge_slice_contract import _lenses_ran, _StubCtx

M, NC = CollectionState.MEASURED, CollectionState.NOT_COLLECTED
CRIT = SecurityFinding(severity="critical", rule="dangerous-eval", detail="d", path="a.py", line="x")


def test_clean_deltas_pass_and_report_pre_existing_counts():
    t = tests_check(ScopedTestReport(state=M, preexisting=["t::a"]))
    lint = lint_check(ScopedLintReport(state=M, preexisting=7))
    col, crit = security_checks(ScopedSecurityReport(state=M, preexisting=4))
    assert t.passed and lint.passed and col.passed and crit.passed
    assert "1 pre-existing" in t.detail and "7 pre-existing" in lint.detail
    assert "4 pre-existing" in crit.detail


def test_introduced_findings_fail_and_are_named():
    t = tests_check(ScopedTestReport(state=M, introduced=["tests/t.py::t"], head_failed=1))
    lint = lint_check(
        ScopedLintReport(state=M, introduced=[LintFinding(rule="F401", path="a.py", line="import os")])
    )
    _, crit = security_checks(ScopedSecurityReport(state=M, introduced=[CRIT]))
    assert not t.passed and "tests/t.py::t" in t.detail
    assert not lint.passed and "F401" in lint.detail
    assert not crit.passed and "a.py" in crit.detail


def test_lint_detail_reports_policy_relaxation():
    lint = lint_check(ScopedLintReport(state=M, policy_paths_changed=["ruff.toml"], suppressions_added=2))
    assert lint.passed
    assert "1 policy path(s) changed" in lint.detail and "2 suppression(s) added" in lint.detail


def test_not_collected_fails_closed_and_no_critical_passes_vacuously():
    assert not tests_check(ScopedTestReport(state=NC, reason="r")).passed
    assert not lint_check(ScopedLintReport(state=NC, reason="r")).passed
    col, crit = security_checks(ScopedSecurityReport(state=NC, reason="base lock"))
    assert not col.passed and "base lock" in col.detail
    assert crit.passed  # vacuous by design: security_scan_collected carries the failure


def _results():
    return [
        TaskResult(
            task_id="t1",
            status="done",
            attempts=1,
            branch="b",
            qa=QAReport(tests_passed=True),
            lens_outcomes=_lenses_ran(),
        )
    ]


@pytest.mark.clause("MERGE-1.2")
@pytest.mark.clause("MERGE-1.10")
@pytest.mark.asyncio
async def test_an_unmaterialized_base_is_terminal_through_the_real_gate():
    """Failure-modes row 1, end to end through step and the REAL evaluate_gate."""
    ctx = _StubCtx()
    idea = IdeaBrief(title="F", description="d", repo_url="/r", mode=ProjectMode.BROWNFIELD)
    base = BaseWorktree(path=None, reason="WinError 32 lock")
    ichecks = IntegrationChecks(
        toolchain="python",
        lint=ScopedLintReport(state=NC, reason="base not materialized: WinError 32 lock"),
        tests=ScopedTestReport(state=NC, reason="base not materialized: WinError 32 lock"),
    )
    sec = ScopedSecurityReport(state=NC, reason="base not materialized: WinError 32 lock")
    with (
        patch("sdlc.stages.merge.step.prepare_base_worktree", new=AsyncMock(return_value=base)) as prep,
        patch("sdlc.stages.merge.step.run_integration_checks", new=AsyncMock(return_value=ichecks)),
        patch("sdlc.stages.merge.step.scoped_security_scan", new=AsyncMock(return_value=sec)),
        patch(
            "sdlc.stages.merge.step.measure_coverage",
            new=AsyncMock(return_value=CoverageReport(coverage=Measurement.not_collected("x"))),
        ),
    ):
        res = await merge.step(
            ctx,
            cfg=PipelineConfig(),
            task_results=_results(),
            integration_wt="/wt",
            idea=idea,
            base_sha="abc123",
        )
    assert res.startswith("rejected:merge:absolute-gate-failed:")
    for name in ("build_integration_green", "lint_clean", "security_scan_collected"):
        assert name in res
    assert ctx.gates_called == []
    assert prep.call_args.args[0].base_sha == "abc123"


def test_step_measures_base_first_and_uses_only_the_scoped_scan():
    tree = ast.parse(pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "step")
    calls = sorted(
        (c for c in ast.walk(fn) if isinstance(c, ast.Call)
         and isinstance(c.func, ast.Name) and c.func.id == "_exec_activity"),
        key=lambda c: (c.lineno, c.col_offset),
    )
    order = [c.args[0].id for c in calls if isinstance(c.args[0], ast.Name)]
    assert order.index("prepare_base_worktree") < order.index("run_integration_checks")
    assert order.index("scoped_security_scan") < order.index("evaluate_gate")
    assert "security_scan" not in order
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/merge/test_scoped_absolute_checks.py -q`
Expected: FAIL — `ImportError: cannot import name 'lint_check' from 'sdlc.stages.merge.step'`

- [ ] **Step 3: `FeatureWorkflow` pins and threads `base_sha`**

In `src/sdlc/workflows/feature.py`:
- `__init__`, directly after `self._integration_head: str = ""`, add:
  `self._base_sha: str = ""  # DS2: setup head, pinned; _integration_head advances per merge`
- after `self._integration_head = integration.head_sha` (`:507`), add:
  `self._base_sha = integration.head_sha`
- in the integration-diff fetch (`:725`), change `branch_point=idea.base_branch` to `branch_point=self._base_sha`
- in the `merge.step(...)` call, add `base_sha=self._base_sha,`

In `src/sdlc/workflows/AGENTS.md`, add this row to the attribute-ownership table, directly after the `_integration_head` row:

```markdown
| `_base_sha` | `FeatureWorkflow` | `FeatureWorkflow` (integration diff, `merge.step`) | `FeatureWorkflow.run` (once, at setup) | Setup head of the integration branch, pinned as the merge gate's baseline (diff-scoped gates DS2); distinct from the advancing `_integration_head` |
```

- [ ] **Step 4: `merge.step` builds the four absolute checks from the scoped reports**

In `src/sdlc/stages/merge/step.py`:
- Replace `from ..qa.activities import LintInput, SecurityScanInput, run_lint, security_scan` with `from ..qa.activities import LintInput, ScopedSecurityScanInput, run_lint, scoped_security_scan`.
- Replace `from ..qa.models import SecurityReport` with `from ..qa.models import ScopedSecurityReport`.
- Add `from ...vcs import BaseWorktree, BaseWorktreeInput, prepare_base_worktree`.
- Extend `.models` to `from .models import CoverageReport, MergeVerdict, ScopedLintReport, ScopedTestReport`.

Add these pure helpers above `step`:

```python
_M = CollectionState.MEASURED


def _listed(items: list[str], limit: int = 10) -> str:
    return f"; introduced: {items[:limit]}" + (" ..." if len(items) > limit else "") if items else ""


def tests_check(r: ScopedTestReport) -> CheckResult:
    """DS6/DS7: rendered from typed fields, never parsed back."""
    if r.state is not _M:
        return build_check("build_integration_green", False, CheckClass.ABSOLUTE, f"not collected: {r.reason}")
    detail = (
        f"{len(r.introduced)} introduced; {len(r.preexisting)} pre-existing; "
        f"{len(r.preexisting_flaky)} pre-existing flaky" + _listed(r.introduced)
    )
    return build_check("build_integration_green", not r.introduced, CheckClass.ABSOLUTE, detail)


def lint_check(r: ScopedLintReport) -> CheckResult:
    if r.state is not _M:
        return build_check("lint_clean", False, CheckClass.ABSOLUTE, f"not collected: {r.reason}")
    detail = (
        f"{len(r.introduced)} introduced; {r.preexisting} pre-existing; {r.resolved} resolved; "
        f"{len(r.policy_paths_changed)} policy path(s) changed; "
        f"{r.suppressions_added} suppression(s) added"
        + _listed([f"{f.rule} {f.path}: {f.line}" for f in r.introduced])
    )
    return build_check("lint_clean", not r.introduced, CheckClass.ABSOLUTE, detail)


def security_checks(r: ScopedSecurityReport) -> list[CheckResult]:
    """security_no_critical passes vacuously on NOT_COLLECTED by design:
    security_scan_collected is the conjunct that fails closed (DS7)."""
    collected = build_check(
        "security_scan_collected",
        r.state is _M,
        CheckClass.ABSOLUTE,
        r.reason or "collected at the base and the head",
    )
    crit = build_check(
        "security_no_critical",
        r.introduced_critical == 0,
        CheckClass.ABSOLUTE,
        f"{r.introduced_critical} introduced critical; {len(r.introduced)} introduced; "
        f"{r.preexisting} pre-existing; {r.resolved} resolved"
        + _listed([f"{f.rule} {f.path}: {f.line}" for f in r.introduced]),
    )
    return [collected, crit]
```

Add `base_sha: str = ""` to `step`'s keyword arguments (after `changed_files`). Then replace everything from `ichecks: IntegrationChecks = await _exec_activity(` through the `build_check("security_no_critical", ...)` entry of `checks` with:

```python
    renames = (
        [list(p) for p in integration_diff.get("renames", [])]
        if isinstance(integration_diff, dict)
        else []
    )
    base: BaseWorktree = await _exec_activity(
        prepare_base_worktree,
        BaseWorktreeInput(
            integration_wt=integration_wt, run_id=_workflow_id() or "local", base_sha=base_sha
        ),
        **_ACT,
    )
    base_path = base.path if isinstance(getattr(base, "path", None), str) else None
    base_reason = _as_str(getattr(base, "reason", ""), "base worktree unavailable")

    ichecks: IntegrationChecks = await _exec_activity(
        run_integration_checks,
        IntegrationChecksInput(
            worktree=integration_wt,
            changed_files=changed_files,
            base_worktree=base_path,
            base_reason=base_reason,
            base_sha=base_sha,
            renames=renames,
        ),
        **_INTEG_ACT,
    )
    if getattr(ichecks, "toolchain", None) is not None:
        t_rep = getattr(ichecks, "tests", None)
        l_rep = getattr(ichecks, "lint", None)
        absolute = [
            tests_check(
                t_rep
                if isinstance(t_rep, ScopedTestReport)
                else ScopedTestReport(state=CollectionState.NOT_COLLECTED, reason="no scoped test report")
            ),
            lint_check(
                l_rep
                if isinstance(l_rep, ScopedLintReport)
                else ScopedLintReport(state=CollectionState.NOT_COLLECTED, reason="no scoped lint report")
            ),
        ]
    else:
        # No toolchain adapter: today's fallback, unchanged (DS10, named limitation).
        lint_commands = (
            next(
                (
                    t.contract.lint_commands
                    for t in plan.tasks
                    if getattr(t, "contract", None) and getattr(t.contract, "lint_commands", None)
                ),
                None,
            )
            if plan and getattr(plan, "tasks", None)
            else None
        )
        lint_cmd = _contract_shell_cmd(lint_commands, DEFAULT_LINT_CMD)
        l_clean, l_detail = await _exec_activity(
            run_lint, LintInput(worktree=integration_wt, lint_cmd=lint_cmd), **_ACT
        )
        absolute = [
            build_check(
                "build_integration_green",
                _merge_evidence_all_green(results_list),
                CheckClass.ABSOLUTE,
                detail="no toolchain adapter: aggregate of per-task QA runs",
            ),
            build_check(
                "lint_clean",
                _as_bool(l_clean, True),
                CheckClass.ABSOLUTE,
                detail=_as_str(l_detail, ""),
            ),
        ]

    cov: CoverageReport = await _exec_activity(
        measure_coverage,
        CoverageInput(worktree=integration_wt, changed_files=changed_files),
        **_ACT,
    )

    sec = await _exec_activity(
        scoped_security_scan,
        ScopedSecurityScanInput(
            worktree=integration_wt,
            base_worktree=base_path,
            renames=renames,
            base_reason=base_reason,
        ),
        **_ACT,
    )
    if not isinstance(sec, ScopedSecurityReport):
        sec = ScopedSecurityReport(state=CollectionState.NOT_COLLECTED, reason="no scoped security report")

    cov_obj = getattr(cov, "coverage", None)
    diff_coverage = (
        cov_obj.value
        if cov_obj is not None and getattr(cov_obj, "state", None) is CollectionState.MEASURED
        else None
    )

    checks = [
        *absolute,
        *security_checks(sec),
```

The rest of the `checks` list (`review_severity`, and the entries after it) and everything below stay as they are. Delete the now-unused locals (`all_tests_green`, `lint_clean`, `lint_detail`, `sec_state`, `sec_crit`, `sec_reason`, `security`). The fallback's `build_check("build_integration_green", ...)` and `build_check("lint_clean", ...)` keep their literal first arguments, so `test_the_manifest_pins_the_checks_the_merge_step_builds` still sees every manifest name.

- [ ] **Step 5: Retire the transitional pieces**

- In `src/sdlc/stages/merge/activities.py`, `IntegrationChecks` becomes exactly:

```python
class IntegrationChecks(BaseModel):
    toolchain: str | None = None  # ToolchainKind value, or None if undetected
    lint: ScopedLintReport | None = None  # None iff no toolchain adapter
    tests: ScopedTestReport | None = None  # None iff no toolchain adapter
```

  The no-adapter branch returns `IntegrationChecks(toolchain=None)`. The `setup_error` branch returns `toolchain`, plus `lint` and `tests` both `NOT_COLLECTED` with `reason=setup_error`. Delete the transitional `qa = QAReport(...)` block and any import it leaves unused.
- In `src/sdlc/stages/qa/activities.py`, delete `SecurityScanInput` and the `security_scan` activity. Set `ACTIVITIES = [run_test_suite, run_lint, scoped_security_scan]`.
- Run `grep -rn "SecurityScanInput\|\bsecurity_scan\b\|lint_clean=\|\.qa\.tests_passed\|lint_detail" src tests`. Every remaining hit must be one of: a check-name string, `scan_paths`/`scoped_security_scan`, or something this step updates below. Anything else → SG-1.

- [ ] **Step 6: Update fakes and existing tests**

`tests/fakes/fake_activities.py`:
- Imports: replace `SecurityScanInput` with `ScopedSecurityScanInput` in the qa import, and `SecurityReport` with `ScopedSecurityReport`. Add `BaseWorktree` and `BaseWorktreeInput` to the `sdlc.vcs` import. Drop `QAReport` from the qa-models import only if it becomes unused (it is still used by `fake_run_test_suite`).
- `fake_get_task_diff` returns an extra key `"renames": []`.
- Replace `fake_security_scan` with:

```python
@activity.defn(name="scoped_security_scan")
async def fake_scoped_security_scan(inp: ScopedSecurityScanInput) -> ScopedSecurityReport:
    return ScopedSecurityReport(state=CollectionState.MEASURED)


@activity.defn(name="prepare_base_worktree")
async def fake_prepare_base_worktree(inp: BaseWorktreeInput) -> BaseWorktree:
    return BaseWorktree(path="/fake/base")
```

- `fake_run_integration_checks` returns `IntegrationChecks(toolchain=None)` and keeps its comment.
- In `GIT_FAKES`, replace `fake_security_scan` with `fake_scoped_security_scan, fake_prepare_base_worktree`.
- Run `grep -rn "\"security_scan\"\|'security_scan'" tests`, and rename every `git_fakes_except(...)` / patch target to `scoped_security_scan`.

`tests/merge/test_merge_slice_contract.py`: in all four `with (...)` blocks, replace
`patch("sdlc.stages.merge.step.security_scan", new_callable=AsyncMock),`
with
`patch("sdlc.stages.merge.step.scoped_security_scan", new_callable=AsyncMock),`
`patch("sdlc.stages.merge.step.prepare_base_worktree", new_callable=AsyncMock),`

`tests/qa/test_qa_slice_contract.py`: in `test_slice_exports_step_and_activities`, change `"security_scan"` to `"scoped_security_scan"` in the expected name set.

`tests/test_security_floor.py`:
- change the import `from sdlc.stages.qa.activities import SecurityScanInput, security_scan` to `from sdlc.stages.qa.activities import scan_paths`;
- add a helper after the imports:

```python
def _files(root: pathlib.Path) -> list[str]:
    return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
```

- in each of the **seven** scan tests (`:28`, `:38`, `:45`, `:55`, `:62`, `:82`, `:96`), replace `await security_scan(SecurityScanInput(worktree=str(tmp_path)))` with `scan_paths(str(tmp_path), _files(tmp_path))`, and drop `@pytest.mark.asyncio` / `async` from those seven functions.
- leave `test_feature_workflow_builds_security_check` (`:141-149`) unchanged: it keeps passing because `"security_scan"` is a substring of `scoped_security_scan`. Do not "fix" it.

**Do not touch any line that writes fixture content** (DS9 and SG-4). The venv-pruning tests keep their meaning: the listed paths include `.sdlc-venv/...`, `node_modules/...` and the rest, and `scan_paths` must still skip them.

`tests/test_integration_checks.py`: the two `slow` tests were converted in Task 6. In `test_integration_checks_degrades_without_adapter`, replace the `lint_clean` and `qa` assertions with `assert checks.toolchain is None and checks.lint is None and checks.tests is None`.

- [ ] **Step 7: Contracts in the same commit**

In `src/sdlc/stages/merge/merge.md`, replace the MERGE-1.2 paragraph (keep the following "absent … see MERGE-1.6" line) with:

```markdown
### MERGE-1.2
On any absolute gate failure (`build_integration_green`, `lint_clean`, `security_scan_collected`, `security_no_critical`), the merge stage fails closed immediately with `rejected:merge:absolute-gate-failed:...`, retains gate feedback memory, records a failing benchmark record, and terminates without offering human override or consulting MergeVerdict. The absolute checks judge **the change, not the tree**. `build_integration_green`, `lint_clean` and `security_no_critical` fail only on what the change introduces relative to the run's pinned base commit. `security_scan_collected` fails when the security delta could not be computed at both points (MERGE-1.10). Findings pre-existing at the base are reported in each check's detail and never block. [SC-5, FR-106, FR-915; diff-scoped gates DS1]
```

Append after MERGE-1.9:

```markdown
### MERGE-1.10
The merge gate measures against the run's pinned base. `base_sha` is `setup_integration_branch`'s head SHA, captured once at setup. The integration diff is `base_sha...HEAD`, and `prepare_base_worktree` materializes the base as a disposable detached worktree.

Lint and security are measured over tracked content at both points. Findings are compared as a multiset over `(tool, rule, path, normalized line)`, with base paths mapped through the diff's renames.

Tests run as the whole suite at the head with no early stop and continuing past collection errors. Each head failure is attributed at the base: a failure on any of up to four base attempts makes it pre-existing (or pre-existing flaky). Passing every attempt, being absent at the base, or having an id unsafe to pass to a shell makes it introduced. There is no head retry.

Each scoped report carries a `CollectionState`, and a check passes only when its report is `MEASURED` and `introduced` is empty. Any failure to compute a delta is `NOT_COLLECTED` and an absolute failure: a base that cannot be materialized, a tool failure at either point, an unreadable tracked file, or a head run that stopped early, wrote no report, or collected no tests. `security_no_critical` passes vacuously on `NOT_COLLECTED`; `security_scan_collected` is the conjunct that fails closed. The no-toolchain fallback (contract lint command, per-task QA aggregate) is unchanged. [SC-5, FR-106, FR-108, FR-915; diff-scoped gates DS2–DS7, DS10]
```

Append to "Failure modes":

```markdown
- **Base not measurable**: the base worktree cannot be materialized, a tool fails at either point, a tracked file is unreadable, or the head test run stops early, writes no report, or collects no tests — the affected scoped report is `NOT_COLLECTED` and its absolute check fails, terminally (MERGE-1.10).
- **Introduced finding**: a lint finding, critical security finding or failing test the change introduced — terminal; pre-existing findings are reported, not blocking (MERGE-1.2).
```

In `src/sdlc/stages/merge/AGENTS.md`:
- Under "Invariants", add: `- The absolute checks judge the change: each is built from a scoped report (\`ScopedTestReport\`, \`ScopedLintReport\`, \`ScopedSecurityReport\`) measured between the pinned \`base_sha\` and the integration head, and passes only when that report is MEASURED with nothing introduced (MERGE-1.10).`
- In the Rule 3 passthrough line, replace `` `stages/qa/activities.py` (`run_lint`, `security_scan`), `stages/qa/models.py` (`SecurityReport`) `` with `` `stages/qa/activities.py` (`run_lint`, `scoped_security_scan`), `stages/qa/models.py` (`ScopedSecurityReport`), `vcs` (`prepare_base_worktree`) ``.
- Under "Temporal notes for this slice", add:

```markdown
- **Replay: diff-scoped gates (2026-09-11) is declared incompatible with in-flight runs — no `workflow.patched`.** The change replaced `security_scan` with `scoped_security_scan`, inserted `prepare_base_worktree`, and changed the `IntegrationChecks` payload. Before deploying a worker built from it, `temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='FeatureWorkflow' OR WorkflowType='TidyUpWorkflow')"` must print nothing; terminate or finish those runs first. Rationale: a patched branch would keep the retired whole-tree gate alive as a second code path, and could not protect the payload change anyway.
```

In `src/sdlc/stages/qa/qa.md`, QA-1.5: change `(\`run_test_suite\`, \`run_lint\`, \`security_scan\`)` to `(\`run_test_suite\`, \`run_lint\`, \`scoped_security_scan\`)`.

In `src/sdlc/stages/qa/AGENTS.md`: set `ACTIVITIES = [run_test_suite, run_lint, scoped_security_scan]` and delete the transitional `security_scan` bullet.

- [ ] **Step 8: Run to verify**

Run each separately, one command per Bash call (never chain two pytest runs):
- `pytest -q`
- `pytest -m temporal tests/test_e2e_greenfield.py -q`
- `pytest -m slow tests/test_integration_checks.py -q`
- `python scripts/check_clauses.py`
- `python scripts/check_file_size.py`

Expected: all PASS. `check_clauses.py` is clean: MERGE-1.10 now exists and is cited.

- [ ] **Step 9: Commit**

Message file `.git/COMMIT_MSG_T7`:
```
feat(merge): the absolute checks judge the change, not the tree

DS1/DS2/DS7: FeatureWorkflow pins base_sha at setup and the merge
step builds build_integration_green, lint_clean and the security pair
from scoped reports measured between that base and the integration
head. Manifest, names, statuses and the no-override rule are
unchanged; the no-toolchain fallback is unchanged. MERGE-1.2 is
rewritten, MERGE-1.10 added, and the slice records that in-flight
runs are declared incompatible rather than patched.
```
```
git add src/sdlc/workflows/feature.py
git add src/sdlc/workflows/AGENTS.md
git add src/sdlc/stages/merge/step.py
git add src/sdlc/stages/merge/activities.py
git add src/sdlc/stages/qa/activities.py
git add src/sdlc/stages/merge/merge.md
git add src/sdlc/stages/merge/AGENTS.md
git add src/sdlc/stages/qa/qa.md
git add src/sdlc/stages/qa/AGENTS.md
git add tests/fakes/fake_activities.py
git add tests/merge/test_merge_slice_contract.py
git add tests/merge/test_scoped_absolute_checks.py
git add tests/qa/test_qa_slice_contract.py
git add tests/test_security_floor.py
git add tests/test_integration_checks.py
git commit -F .git/COMMIT_MSG_T7
```

Also `git add` any other test file the Step 5/6 greps required you to edit, one path per argument.

---

### Task 8: verification tier — fixture repository, greenfield equivalence, pinned base, manifest

These tests exercise the finished gate end to end. Implementation defects they expose are fixed in the task that owns the code, re-running that task's tests; a fix that needs a new DS decision is SG-1.

**Files:**
- Create: `tests/test_diff_scoped_fixture_tier.py` (`slow`)
- Create: `tests/test_greenfield_equivalence.py` (`slow`)
- Create: `tests/test_pinned_base_e2e.py` (`temporal`)
- Modify: `tests/test_required_checks_manifest.py` (append one test)

**Interfaces:**
- Consumes: `prepare_base_worktree`, `get_task_diff` (Task 2); `scoped_security_scan`, `scan_paths` (Task 3); `run_integration_checks`, `IntegrationChecksInput` (Tasks 5–6); `tests_check`, `lint_check`, `security_checks` (Task 7); `FeatureWorkflow._base_sha` wiring (Task 7).

- [ ] **Step 1: The shared gate driver and the fixture-repository tier (cases i–x)**

`tests/test_diff_scoped_fixture_tier.py`:

```python
"""DS12 pre-flight: the scoped gate on a throwaway repo shaped like this one.

Pre-existing at base: a "rule table" whose detail string trips the eval rule,
a secret-shaped fixture, lint debt, and 26 failing tests that sort before a
passing one. Trigger text is assembled at runtime (DS9).
"""

import pathlib
import subprocess

import pytest

from sdlc.measurement import CollectionState
from sdlc.stages.merge.activities import IntegrationChecksInput, run_integration_checks
from sdlc.stages.merge.step import lint_check, security_checks, tests_check
from sdlc.stages.qa.activities import ScopedSecurityScanInput, scoped_security_scan
from sdlc.vcs import BaseWorktreeInput, DiffInput, get_task_diff, prepare_base_worktree

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]

EVAL = "ev" + "al("
SECRET = "AWS_SECRET_ACCESS_KEY" + ' = "' + "B" * 32 + '"'
GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


def git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def commit(repo, msg) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def write(repo: pathlib.Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


async def gate(repo: pathlib.Path, base: str):
    """(verdicts by check name, test report, lint report, security report)."""
    diff = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "tier", base))
    ichecks = await run_integration_checks(
        IntegrationChecksInput(
            worktree=str(repo),
            changed_files=diff["files"],
            base_worktree=wt.path,
            base_reason=wt.reason,
            base_sha=base,
            renames=diff["renames"],
        )
    )
    sec = await scoped_security_scan(
        ScopedSecurityScanInput(
            worktree=str(repo), base_worktree=wt.path, renames=diff["renames"], base_reason=wt.reason
        )
    )
    checks = [tests_check(ichecks.tests), lint_check(ichecks.lint), *security_checks(sec)]
    return {c.name: c.passed for c in checks}, ichecks.tests, ichecks.lint, sec


ALL_PASS = {
    "build_integration_green": True,
    "lint_clean": True,
    "security_scan_collected": True,
    "security_no_critical": True,
}


@pytest.fixture
def repo(tmp_path, monkeypatch) -> tuple[pathlib.Path, str]:
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    write(r, ".gitignore", ".sdlc-venv/\n.sdlc-junit*.xml\ncoverage.xml\n*.count\n")
    write(r, "pyproject.toml", "[project]\nname = 'tier'\nversion = '0.0.0'\n")
    write(r, "ruff.toml", '[lint]\nselect = ["F401"]\n')
    write(r, "rules.py", f'DETAIL = "use of {EVAL}) on untrusted input"\n')
    write(r, "tests/test_fixture_floor.py", f"FIXTURE = {SECRET!r}\n\n\ndef test_f():\n    pass\n")
    write(r, "legacy.py", "import os\n")
    write(r, "calc.py", "def add(a, b):\n    return a + b\n")
    debt = "\n".join(f"def test_a{i:02d}():\n    assert False\n" for i in range(26))
    write(r, "tests/test_aa_debt.py", debt)
    write(r, "tests/test_zz.py", "from calc import add\n\n\ndef test_zz():\n    assert add(1, 1) == 2\n")
    return r, commit(r, "base")


async def test_i_empty_change_passes_with_pre_existing_counts(repo):
    r, base = repo
    verdicts, t, lint, sec = await gate(r, base)
    assert verdicts == ALL_PASS
    assert len(t.preexisting) == 26 and lint.preexisting == 1 and sec.preexisting == 2


async def test_ii_second_eval_in_the_same_file_blocks(repo):
    r, base = repo
    write(r, "rules.py", f'DETAIL = "use of {EVAL}) on untrusted input"\nx = {EVAL}"1")\n')
    commit(r, "second eval")
    verdicts, *_, sec = await gate(r, base)
    assert verdicts["security_no_critical"] is False and sec.introduced_critical == 1


async def test_iii_a_break_behind_26_pre_existing_failures_blocks(repo):
    r, base = repo
    write(r, "calc.py", "def add(a, b):\n    return a - b\n")
    commit(r, "breaks add")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is False
    assert t.introduced == ["tests/test_zz.py::test_zz"]


async def test_iv_rename_only_introduces_nothing(repo):
    r, base = repo
    git(r, "mv", "rules.py", "rule_table.py")
    git(r, "mv", "legacy.py", "old_legacy.py")
    commit(r, "renames")
    verdicts, _, lint, sec = await gate(r, base)
    assert verdicts == ALL_PASS and lint.introduced == [] and sec.introduced == []


async def test_v_deleting_a_file_with_a_finding_resolves_it(repo):
    r, base = repo
    git(r, "rm", "-q", "legacy.py")
    commit(r, "delete legacy")
    verdicts, _, lint, _ = await gate(r, base)
    assert verdicts["lint_clean"] is True and lint.resolved == 1


async def test_vi_a_new_failing_test_blocks_without_tolerance(repo):
    r, base = repo
    write(r, "tests/test_new.py", "def test_new():\n    assert False\n")
    commit(r, "new failing test")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is False
    assert t.introduced == ["tests/test_new.py::test_new"]


async def test_vii_a_base_flaky_test_is_pre_existing_flaky(repo):
    r, _ = repo
    write(
        r,
        "tests/test_flaky.py",
        "import pathlib\nC = pathlib.Path(__file__).with_suffix('.count')\n\n\n"
        "def test_flaky():\n    n = int(C.read_text()) if C.exists() else 0\n"
        "    C.write_text(str(n + 1))\n    assert n != 1\n",
    )
    base = commit(r, "base with flaky test")
    write(r, "tests/test_flaky.py", "def test_flaky():\n    assert False\n")
    commit(r, "head breaks it")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is True
    assert t.preexisting_flaky == ["tests/test_flaky.py::test_flaky"]


async def test_viii_passing_four_of_four_at_base_then_failing_is_introduced(repo):
    r, base = repo
    write(r, "tests/test_zz.py", "def test_zz():\n    assert False\n")
    commit(r, "breaks test_zz")
    verdicts, t, *_ = await gate(r, base)
    assert verdicts["build_integration_green"] is False
    assert t.introduced == ["tests/test_zz.py::test_zz"]


async def test_ix_policy_edit_and_noqa_pass_and_are_reported(repo):
    r, base = repo
    write(r, "ruff.toml", '[lint]\nselect = ["F401"]\nignore = []\n')
    write(r, "calc.py", "import sys  # noqa: F401\n\n\ndef add(a, b):\n    return a + b\n")
    commit(r, "relaxes nothing visible, adds a suppression")
    verdicts, _, lint, _ = await gate(r, base)
    assert verdicts["lint_clean"] is True
    assert lint.policy_paths_changed == ["ruff.toml"] and lint.suppressions_added == 1


async def test_x_a_finding_caused_in_an_untouched_file_blocks(repo):
    r, base = repo
    write(r, "ruff.toml", '[lint]\nselect = ["F401", "E501"]\nline-length = 5\n')
    commit(r, "tightens policy")
    verdicts, _, lint, _ = await gate(r, base)
    assert verdicts["lint_clean"] is False
    assert {f.path for f in lint.introduced} >= {"calc.py"}
```

Scope note for (x): the policy change is the only edit, and the new E501 findings land in files the change did not touch (`calc.py`, `rules.py`, …). That is the cross-file effect DS3 exists for.

- [ ] **Step 2: Greenfield equivalence (DS8)**

`tests/test_greenfield_equivalence.py`:

```python
"""DS8: on an empty base the scoped verdict equals the whole-tree verdict."""

import os
import subprocess
import sys

import pytest

from sdlc.stages.qa.activities import _SCAN_SKIP_DIRS, scan_paths
from tests.test_diff_scoped_fixture_tier import EVAL, commit, gate, git, write

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]

TREES = {
    "clean": {"app.py": "def f():\n    return 1\n", "tests/test_app.py": "def test_f():\n    pass\n"},
    "lint": {"app.py": "import os\n", "tests/test_app.py": "def test_f():\n    pass\n"},
    "critical": {"app.py": f"x = {EVAL}'1')\n", "tests/test_app.py": "def test_f():\n    pass\n"},
    "failing": {"app.py": "x = 1\n", "tests/test_app.py": "def test_f():\n    assert False\n"},
    "no_tests": {"app.py": "x = 1\n"},
}


def whole_tree_verdict(root) -> dict[str, bool]:
    """The pre-change semantics, recomputed as an oracle: tree-wide lint,
    tree-wide scan (walk minus skip dirs), whole-suite pytest exit 0."""
    def run(*args: str) -> int:
        return subprocess.run(
            [sys.executable, "-m", *args], cwd=root, capture_output=True
        ).returncode

    paths: list[str] = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in _SCAN_SKIP_DIRS]
        paths.extend(os.path.relpath(os.path.join(d, f), root) for f in files)
    scan = scan_paths(str(root), paths)
    return {
        "build_integration_green": run("pytest", "-q", "-p", "no:cacheprovider") == 0,
        "lint_clean": run("ruff", "check", "--no-cache", ".") == 0,
        "security_scan_collected": True,
        "security_no_critical": scan.critical == 0,
    }


@pytest.mark.parametrize("name", sorted(TREES))
async def test_empty_base_scoped_verdict_equals_whole_tree(name, tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    write(r, ".gitignore", ".sdlc-venv/\n.sdlc-junit*.xml\ncoverage.xml\n")
    base = commit(r, "empty base")  # no source: the greenfield case
    write(r, "pyproject.toml", "[project]\nname = 'g'\nversion = '0.0.0'\n")
    write(r, "ruff.toml", '[lint]\nselect = ["F401"]\n')
    for rel, body in TREES[name].items():
        write(r, rel, body)
    commit(r, "the run's output")
    scoped, *_ = await gate(r, base)
    assert scoped == whole_tree_verdict(r), name
```

- [ ] **Step 3: Pinned base through the real workflow (Temporal)**

`tests/test_pinned_base_e2e.py` — the harness is copied from `tests/test_task_gate_revise_loop.py:124-191`:

```python
"""DS2: the gate's diff and base come from the setup SHA, never the branch
name and never the advancing integration head."""

from __future__ import annotations

import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.core.models import GateConfig, GatePolicy
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from sdlc.stages.merge.activities import evaluate_gate
from sdlc.vcs import BaseWorktree, BaseWorktreeInput, DiffInput
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import git_fakes_except

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

DIFFS: list[DiffInput] = []
BASES: list[BaseWorktreeInput] = []


@activity.defn(name="get_task_diff")
async def recording_diff(inp: DiffInput) -> dict:
    DIFFS.append(inp)
    return {"stat": "", "patch": "", "files": ["app/main.py"], "renames": []}


@activity.defn(name="prepare_base_worktree")
async def recording_base(inp: BaseWorktreeInput) -> BaseWorktree:
    BASES.append(inp)
    return BaseWorktree(path="/fake/base")


@activity.defn(name="notify")
async def _noop_notify(inp: NotifyInput) -> Results:
    return Results(results=[])


async def test_the_merge_gate_reads_the_setup_sha(tmp_path, monkeypatch):
    DIFFS.clear()
    BASES.clear()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.gates = {n: GateConfig(policy=GatePolicy.OFF) for n in ("clarify", "architecture", "plan", "merge", "deploy")}
    cfg.default_gate_policy = GatePolicy.OFF
    async with await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter) as env:
        async with Worker(
            env.client,
            task_queue="pinned",
            workflows=[FeatureWorkflow, DeploymentWorkflow],
            activities=[
                evaluate_gate,
                export_run_artifacts,
                _noop_notify,
                recording_diff,
                recording_base,
                *git_fakes_except("get_task_diff", "prepare_base_worktree"),
                *fake_agent_activities(AGENT_SPECS),
            ],
            plugins=[PydanticAIPlugin()],
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[greenfield_idea(), cfg, None],
                id=f"pinned-{uuid.uuid4()}",
                task_queue="pinned",
            )
            with env.auto_time_skipping_disabled():
                for qid in QUESTION_IDS:
                    await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
            await handle.result()

    integ = [d for d in DIFFS if d.worktree == "/fake/integ"]
    assert integ, "the integration diff was never fetched"
    # fake setup_integration_branch returns head_sha="deadbeef"; the fake merge
    # advances the integration head to "feed0001"; idea.base_branch is "main".
    assert {d.branch_point for d in integ} == {"deadbeef"}
    assert [b.base_sha for b in BASES] == ["deadbeef"]
    assert BASES[0].integration_wt == "/fake/integ"
```

The values are verified: `greenfield_idea()` has `base_branch="main"` (`tests/fakes/canned.py:115`); `fake_setup_integration_branch` returns `head_sha="deadbeef"`, and `fake_merge_into_integration` advances the head to `"feed0001"` (`tests/fakes/fake_activities.py:55-57, 102-104`). The assertion therefore pins the setup SHA and excludes both the branch name and the advanced head.

- [ ] **Step 4: Manifest unchanged (DS10, SG-2)**

Append to `tests/test_required_checks_manifest.py`:

```python
def test_diff_scoped_gates_left_the_manifest_byte_identical():
    """DS10: the change moved what the checks measure, never which checks
    exist or how they are classified."""
    assert dict(MERGE_REQUIRED_CHECKS) == {
        "build_integration_green": CheckClass.ABSOLUTE,
        "lint_clean": CheckClass.ABSOLUTE,
        "security_scan_collected": CheckClass.ABSOLUTE,
        "security_no_critical": CheckClass.ABSOLUTE,
        "review_severity": CheckClass.ADVISORY,
        "review_lenses_present": CheckClass.ADVISORY,
        "traceability": CheckClass.ADVISORY,
        "coverage": CheckClass.ADVISORY,
        "plan_drift": CheckClass.ADVISORY,
    }
    assert ABSOLUTE_FLOOR == frozenset({"security_no_critical", "security_scan_collected"})
```

Then run `git diff main -- src/sdlc/gate.py`: it must print nothing (SG-2).

- [ ] **Step 5: Run the tier**

Run, **one command per Bash call** — never chain two pytest runs:
- `pytest -m slow tests/test_diff_scoped_fixture_tier.py -q`
- `pytest -m slow tests/test_greenfield_equivalence.py -q`
- `pytest -m temporal tests/test_pinned_base_e2e.py -q`
- `pytest tests/test_required_checks_manifest.py -q`

Expected: all PASS. The slow tests provision venvs with `pip`, so they need network access.

- [ ] **Step 6: Commit**

Message file `.git/COMMIT_MSG_T8`:
```
test(gate): verification tier for diff-scoped merge gates

Fixture-repository cases (i)-(x) against a repo shaped like this one,
greenfield equivalence against the whole-tree oracle, the pinned base
through the real FeatureWorkflow, and the manifest pinned
byte-identical.
```
```
git add tests/test_diff_scoped_fixture_tier.py
git add tests/test_greenfield_equivalence.py
git add tests/test_pinned_base_e2e.py
git add tests/test_required_checks_manifest.py
git commit -F .git/COMMIT_MSG_T8
```

---

### Task 9: roadmap deltas — PRD, ROADMAP, tier-0

Docs only; no code. Each edit **appends** to the existing entry and leaves historical text standing (the ROADMAP records what was true when written; corrections are dated).

**Files:**
- Modify: `PRD.md:157-166` (FR-106), `PRD.md:175-188` (FR-108)
- Modify: `ROADMAP.md` — the P2 note (ends at `:121`), `:235` (stage 12), `:249` (FR-106), `:251` (FR-108), `:340` (FR-915), `:393` (NFR-10), `:409` (SC-5)
- Modify: `docs/roadmap/tier-0-triage.md` — the E-41 entry (ends at `:42`) and the E-44 entry (ends at `:107`)

- [ ] **Step 1: PRD FR-106 amendment**

In `PRD.md` FR-106, replace the sentence — it is line-wrapped across `PRD.md:158-160`; replace the whole wrapped span and re-wrap to the file's ~80-column width —
`Absolute checks (lint clean, no critical security finding, build/integration green) SHALL block the merge unconditionally — no policy or human override.`
with
`Absolute checks — the change introduces no lint finding, no critical security finding, and no failing test, each measured against the run's pinned base commit — SHALL block the merge unconditionally; no policy or human override. Findings pre-existing at the base SHALL be reported, not gated.`

- [ ] **Step 2: PRD FR-108 addition**

Append to FR-108, after `...off the critical path.`:
` Adapters SHALL also supply the diff-scoped gate's contract: machine-readable lint with a parser that distinguishes findings from tool failure, lint-policy path globs, an inline-suppression pattern, a whole-suite gate test command with no early stop, and selected-test re-runs with per-test JUnit.`

- [ ] **Step 3: ROADMAP**

- P2 — insert a new paragraph directly after the one ending `…needs its own spec — it is not a patch.`:

```markdown
  **2026-09-11 — re-verified and specified.** On `main` at `0aeb25e`, `ruff check .` passes: the 1142 figure predates the dev-tooling baseline (`5903a31`). The 4 criticals include the scanner's own rule table (`qa/activities.py:368`). The never-overridable rule lives at `gate.py:7` / `evaluate_quality_gate`; the `gate.py:86` citation above is stale. Two further whole-tree leaks were found in the same pass: the integration run's `--maxfail=25` hid failures behind pre-existing ones, and a single collection error aborted the whole suite. The absolute checks now judge the change against the run's pinned base — spec `docs/superpowers/specs/2026-09-11-diff-scoped-gates-design.md`, plan `docs/superpowers/plans/2026-09-11-diff-scoped-gates.md`. P2 stays open until the demonstration (spec DS12). New follow-ups: scoped checks per task (shift-left); a lint-policy fence in the harness sandbox; semgrep/SARIF wiring with fingerprint identity.
```

- `:235` (stage 12) — append: ` **Diff-scoped (2026-09-11):** the four absolute checks are built from scoped reports measured between the pinned base and the integration head (MERGE-1.10); pre-existing findings are reported, not gated.`
- `:249` (FR-106) — append: ` Absolute checks judge the change against the run's pinned base (PRD FR-106 amended 2026-09-11, diff-scoped gates).`
- `:251` (FR-108) — append: ` **2026-09-11:** the adapter contract gains scoped lint (parser, policy globs, suppression pattern) and scoped tests (no-early-stop gate command, selected-id re-runs with JUnit); E-30a/b/c must implement them.`
- `:340` (FR-915) — append: ` **Diff-scoped gates adds three consumers:** \`ScopedLintReport\`, \`ScopedTestReport\` and \`ScopedSecurityReport\` carry \`CollectionState\`, and a delta that cannot be computed never reads as zero introduced.`
- `:393` (NFR-10) — append: ` **Diff-scoped gates (2026-09-11):** one more pure module (\`change_scope.py\`) carries its own order-independence assertion (\`test_delta_is_order_independent\`).`
- `:409` (SC-5) — append: ` Text unchanged by diff-scoped gates (2026-09-11): its absolute checks are FR-106's amended ones, judging the change against the pinned base.`

- [ ] **Step 4: tier-0**

In `docs/roadmap/tier-0-triage.md`, after the E-41 entry's plan line (`:42`), add:

```markdown
  **Gap recorded 2026-09-11 (diff-scoped gates DS1):** no triage signal measures lint or `eval`-class code patterns. Now that the merge gate reports pre-existing findings without gating them, debt of those two classes has no measuring owner. Recorded as a follow-up; not built.
```

After the E-44 entry's last line (`:107`), add:

```markdown
  **Unblocked 2026-09-11 (diff-scoped gates DS1):** fix runs are brownfield `FeatureWorkflow` children, so under the whole-tree merge floor a one-finding fix could not land on a repository carrying any other debt. The scoped gate judges only what the fix introduces.
```

- [ ] **Step 5: Verify and commit**

Run: `python scripts/check_file_size.py && python scripts/check_clauses.py`
Expected: PASS.

Message file `.git/COMMIT_MSG_T9`:
```
docs: roadmap deltas for diff-scoped merge gates

Amends PRD FR-106 (absolute checks judge the change against the
pinned base) and FR-108 (the scoped adapter contract), corrects the
P2 note's stale figures, and records the FR-915/NFR-10/SC-5
consequences, the E-41 ownership gap, and E-44's unblocking.
```
```
git add PRD.md
git add ROADMAP.md
git add docs/roadmap/tier-0-triage.md
git commit -F .git/COMMIT_MSG_T9
```

---

### Task 10: dogfood smoke and final verification (no commit)

The branch must pass the gate it builds (DS9, DS12).

- [ ] **Step 1: Operator smoke — this branch against `main` (SG-4)**

Write this to a scratch file **outside the repository** (for example `%TEMP%\smoke_scoped.py`), then run it with `python <path>` from the repository root. Never commit it.

```python
import asyncio
import os
import subprocess
import sysconfig

from sdlc.stages.merge.scoping import scoped_lint
from sdlc.stages.qa.activities import ScopedSecurityScanInput, scoped_security_scan
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.vcs import BaseWorktreeInput, DiffInput, get_task_diff, prepare_base_worktree


async def main() -> None:
    base = subprocess.run(
        ["git", "merge-base", "main", "HEAD"], capture_output=True, encoding="utf-8", check=True
    ).stdout.strip()
    diff = await get_task_diff(DiffInput(worktree=".", branch_point=base))
    wt = await prepare_base_worktree(BaseWorktreeInput(".", "smoke", base))
    assert wt.path, wt.reason
    sec = await scoped_security_scan(
        ScopedSecurityScanInput(worktree=".", base_worktree=wt.path, renames=diff["renames"])
    )
    env = dict(os.environ)
    env["PATH"] = sysconfig.get_path("scripts") + os.pathsep + env["PATH"]
    lint = await scoped_lint(PythonToolchain(), ".", wt.path, "", base, diff["renames"], env, 600)
    print("security:", sec.state, "introduced", [(f.rule, f.path) for f in sec.introduced],
          "pre-existing", sec.preexisting)
    print("lint:", lint.state, "introduced", [(f.rule, f.path) for f in lint.introduced],
          "pre-existing", lint.preexisting, "policy", lint.policy_paths_changed,
          "suppressions", lint.suppressions_added)


asyncio.run(main())
```

Expected:
- security `MEASURED`, `introduced []`, `pre-existing 4`;
- lint `MEASURED`, `introduced []`;
- `suppressions` counts only `# noqa` lines this branch genuinely added. Report the number.

Anything else → **SG-4: stop and report.** Typical causes: a test fixture written literally (DS9), or an edited fixture line in `tests/test_security_floor.py`.

- [ ] **Step 2: Full verification**

Run each separately, one command per Bash call:
- `pytest -q`
- `pytest -m slow tests/test_integration_checks.py tests/test_diff_scoped_fixture_tier.py tests/test_greenfield_equivalence.py -q`
- `pytest -m temporal tests/test_e2e_greenfield.py tests/test_pinned_base_e2e.py tests/test_task_gate_revise_loop.py -q`
- `ruff check .`
- `ruff format --check .`
- `mypy` — the error count must not exceed `main`'s (run `mypy` on a `main` checkout for the comparison, and report both counts)
- `python scripts/check_file_size.py`
- `python scripts/check_clauses.py`
- `git diff main -- src/sdlc/gate.py` — must print nothing (SG-2)

- [ ] **Step 3: Report to the orchestrator**

Report:
- the commit list (Tasks 1–9);
- the smoke output from Step 1;
- every verification result, with the two mypy counts;
- the inbox tasks filed under `.workspace/tasks/` for anything found mid-run;
- the SG-6 pre-deploy query, restated verbatim for the operator.

Integration — verification, fast-forward of `main`, and push — belongs to the orchestrator.
