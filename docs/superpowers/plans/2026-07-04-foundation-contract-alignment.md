# Foundation: Contract & Decision Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `src/sdlc/` into line with the resolved architecture decisions (review doc `docs/architecture-review-2026-07.md`) at the *contract and activity* level — GateDecision outcome enum, HarnessRunResult token capture, harness env allowlist, running-integration-branch git activities, and a real DeterministicQualityGate — all covered by pure unit tests plus a fake/real-git harness, with **no** live Temporal cluster or coding-CLI required to verify.

**Architecture:** This plan changes typed contracts (`models.py`), the harness adapter layer (`harness/adapters.py`), the git activities (`activities.py`), and adds a pure gate module (`gate.py`). It makes the *mechanisms* correct-by-spec. It deliberately does **not** rewire `FeatureWorkflow` control flow (the gate-revision loop, the integration setup/merge orchestration, the token-based fresh-session trigger) — those are Plan 2 ("P1 end-to-end greenfield slice"). Where a contract change forces a call-site edit in `cli.py`/`feature.py`/`roles.py`, we make the *minimal* edit needed to keep the package importing and internally consistent, and we mark the deferred runtime behavior explicitly.

**Tech Stack:** Python ≥3.11, Pydantic v2, `temporalio`, `pydantic-ai-slim`, `pytest`, `git` CLI. src-layout package installed with `pip install -e .[dev]`.

## Global Constraints

- **Python floor 3.11** (`pyproject.toml requires-python = ">=3.11"`). The dev machine reports 3.14.3, which may lack prebuilt wheels for `temporalio`/`pydantic-ai-slim`. If `pip install` fails to build, create and use a **3.12 or 3.13** virtualenv. Record the interpreter actually used.
- **src layout**: the package is `sdlc` under `src/`. Tests import `sdlc.*`; this requires the editable install. Never add `sys.path` hacks.
- **Follow the established codebase pattern**: activity inputs/outputs are `@dataclass`es (see `activities.py`); pipeline contracts are Pydantic `BaseModel`s (see `models.py`). Keep that split.
- **Temporal payload discipline**: keep model fields small; large blobs stay behind `ArtifactRef` (claim-check). Do not add large inline fields.
- **Security invariant (Finding #8)**: the harness environment is an **allowlist plus deliberately-injected credentials**, never `os.environ` passthrough. No test may assert full-env passthrough.
- **Out of scope for this plan (Plan 2)**: gate-revision control flow, round-scoped signal keys, integration-branch setup/merge *orchestration inside the workflow*, token-threshold fresh-session logic in the dev-task loop, soft-gate `MergeVerdict` consultation ordering. This plan builds the pieces those will use.
- TDD (test first, watch it fail, minimal impl, watch it pass), DRY, YAGNI, frequent commits.

---

## File Structure

| File | Responsibility | This plan |
|---|---|---|
| `pyproject.toml` | package + dev deps + pytest config | Modify |
| `tests/conftest.py` | shared fixtures (real-git repo) | Create |
| `tests/test_gate_decision.py` | GateDecision outcome/round contract | Create |
| `tests/test_harness_result.py` | HarnessRunResult token fields + ceiling | Create |
| `tests/test_harness_parse.py` | adapter JSON parsing of tokens | Create |
| `tests/test_env_allowlist.py` | env allowlist builder | Create |
| `tests/test_integration_activities.py` | running-integration-branch git activities | Create |
| `tests/test_quality_gate.py` | DeterministicQualityGate logic | Create |
| `tests/test_module_imports.py` | roles/workflow import smoke + MergeVerdict | Create |
| `src/sdlc/models.py` | pipeline contracts | Modify |
| `src/sdlc/harness/adapters.py` | harness abstraction, env, token parse | Modify |
| `src/sdlc/activities.py` | git worktree/integration/diff activities | Modify |
| `src/sdlc/gate.py` | pure DeterministicQualityGate | Create |
| `src/sdlc/agents/roles.py` | fix import; MergeVerdict agent | Modify |
| `src/sdlc/cli.py` | GateDecision construction | Modify |
| `src/sdlc/workflows/feature.py` | minimal contract-consistency edits only | Modify |

---

## Task 1: Test-harness bootstrap

Get a green `pytest` run and confirm the light modules import, so every later task can work test-first. No source-logic changes here beyond packaging.

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_bootstrap.py` (temporary sanity test, kept)

**Interfaces:**
- Produces: a `git_repo` pytest fixture — yields the path (str) to a fresh git repo with one commit on branch `main`, and points `SDLC_WORKTREES_ROOT` at a writable temp dir for the duration of the test.

- [ ] **Step 1: Add dev deps + pytest config to `pyproject.toml`**

Append to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Install the package editable with dev extras**

Run: `pip install -e .[dev]`
Expected: completes; `pytest --version` prints a version. If the build fails on Python 3.14, create a 3.12/3.13 venv (`py -3.12 -m venv .venv` on Windows or `python3.12 -m venv .venv`), activate it, and re-run. Record which interpreter you used.

- [ ] **Step 3: Write the `git_repo` fixture in `tests/conftest.py`**

```python
"""Shared test fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def run_git(args: list[str], cwd: str | Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A fresh git repo with one commit on `main`, plus a writable
    worktrees root so the activities never touch /var."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(["init", "-b", "main"], repo)
    run_git(["config", "user.email", "t@t.co"], repo)
    run_git(["config", "user.name", "sdlc-test"], repo)
    (repo / "README.md").write_text("seed\n")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-m", "seed"], repo)
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
    return str(repo)
```

- [ ] **Step 4: Write a bootstrap sanity test in `tests/test_bootstrap.py`**

```python
def test_light_modules_import():
    # These must import with only temporalio + pydantic present.
    import sdlc.models  # noqa: F401
    import sdlc.harness.adapters  # noqa: F401
    import sdlc.activities  # noqa: F401


def test_git_repo_fixture(git_repo):
    from pathlib import Path

    assert (Path(git_repo) / "README.md").read_text() == "seed\n"
```

- [ ] **Step 5: Run the bootstrap tests**

Run: `pytest tests/test_bootstrap.py -v`
Expected: 2 passed. (If `import sdlc.activities` fails, resolve the install before proceeding — later tasks depend on it.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/test_bootstrap.py
git commit -m "test: bootstrap pytest harness and git_repo fixture"
```

---

## Task 2: GateDecision outcome enum + round-scoped identity (Finding #6)

Replace the boolean `approved` with an `outcome ∈ {approve, reject, revise}` and add `round` + `guidance`, so "send back for revision" is expressible and idempotency can be scoped per round. Keep a derived `approved` property so existing `.approved` reads keep working (the revision *loop* itself is Plan 2).

**Files:**
- Modify: `src/sdlc/models.py:153-160` (the `GateDecision` model)
- Modify: `src/sdlc/cli.py:18,72-74` (construction site)
- Test: `tests/test_gate_decision.py`

**Interfaces:**
- Produces: `GateOutcome` (str Enum: `APPROVE="approve"`, `REJECT="reject"`, `REVISE="revise"`); `GateDecision{gate, round:int=1, outcome:GateOutcome, decided_by, reviewer?, comments?, guidance?, decided_at?}` with read-only `approved: bool` property (`outcome is APPROVE`); module function `gate_key(gate: str, round: int) -> str` returning `f"{gate}#{round}"`.
- Consumed by: `cli.py`, `feature.py` (Task 7), `gate.py` (Task 6 does not use it).

- [ ] **Step 1: Write the failing test in `tests/test_gate_decision.py`**

```python
from sdlc.models import GateDecision, GateOutcome, gate_key


def test_approve_outcome_sets_approved_property():
    d = GateDecision(gate="architecture", outcome=GateOutcome.APPROVE, decided_by="human")
    assert d.approved is True
    assert d.round == 1


def test_revise_and_reject_are_not_approved():
    revise = GateDecision(
        gate="architecture",
        outcome=GateOutcome.REVISE,
        decided_by="human",
        guidance="tighten scope",
    )
    reject = GateDecision(gate="architecture", outcome=GateOutcome.REJECT, decided_by="human")
    assert revise.approved is False
    assert reject.approved is False
    assert revise.guidance == "tighten scope"


def test_gate_key_is_round_scoped():
    assert gate_key("architecture", 1) == "architecture#1"
    assert gate_key("architecture", 2) == "architecture#2"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_gate_decision.py -v`
Expected: FAIL — `ImportError: cannot import name 'GateOutcome'` (and `gate_key`).

- [ ] **Step 3: Implement in `src/sdlc/models.py`**

Add a `GateOutcome` enum near the other enums (after `GatePolicy`, around line 31):

```python
class GateOutcome(str, Enum):
    APPROVE = "approve"  # proceed
    REJECT = "reject"  # terminal
    REVISE = "revise"  # loop back with guidance (Finding #6)
```

Replace the `GateDecision` class (currently lines 153-160) with:

```python
class GateDecision(BaseModel):
    gate: str  # "architecture", "merge", ...
    round: int = 1  # revision round (Finding #6)
    outcome: GateOutcome
    decided_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    comments: str | None = None
    guidance: str | None = None  # fed back into the agent on 'revise'
    decided_at: datetime | None = None

    @property
    def approved(self) -> bool:
        """Convenience for callers that only branch on go/no-go. `reject`
        and `revise` are both non-approvals; callers that must distinguish
        read `outcome` directly."""
        return self.outcome is GateOutcome.APPROVE


def gate_key(gate: str, round: int) -> str:
    """Round-scoped gate identity — 'first decision wins' applies per round."""
    return f"{gate}#{round}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_gate_decision.py -v`
Expected: 3 passed.

- [ ] **Step 5: Update the `cli.py` construction site**

In `src/sdlc/cli.py`, change the import on line 18 to include `GateOutcome`:

```python
from .models import GateDecision, GateOutcome, IdeaBrief, ProjectMode
```

Replace the `GateDecision(...)` construction (lines 72-74) with:

```python
(
    GateDecision(
        gate=args.gate,
        outcome=(GateOutcome.APPROVE if args.cmd == "approve" else GateOutcome.REJECT),
        decided_by="human",
        comments=args.comment,
    ),
)
```

- [ ] **Step 6: Verify `cli.py` still imports**

Run: `python -c "import sdlc.cli"`
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/models.py src/sdlc/cli.py tests/test_gate_decision.py
git commit -m "feat: GateDecision outcome enum + round-scoped identity"
```

---

## Task 3: HarnessRunResult token capture + context ceiling (Finding #7)

Give the harness result the token data the context-ceiling logic needs, and parse it out of the harness JSON the adapters already read for cost.

**Files:**
- Modify: `src/sdlc/models.py:124-133` (the `HarnessRunResult` model)
- Modify: `src/sdlc/harness/adapters.py` (parse token usage; fill context window)
- Test: `tests/test_harness_result.py`, `tests/test_harness_parse.py`

**Interfaces:**
- Produces: `HarnessRunResult` gains `input_tokens: int | None`, `output_tokens: int | None`, `context_window: int | None`, `compacted: bool = False`, and method `near_context_ceiling(fraction: float = 0.75) -> bool`.
- Produces: `adapters.context_window_for(model: str | None) -> int | None`.
- Consumed by: Plan 2's dev-task loop (not wired here).

- [ ] **Step 1: Write the failing test in `tests/test_harness_result.py`**

```python
from sdlc.models import HarnessKind, HarnessRunResult


def _res(**kw):
    base = dict(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="x")
    base.update(kw)
    return HarnessRunResult(**base)


def test_near_ceiling_true_when_input_exceeds_fraction():
    r = _res(input_tokens=160_000, context_window=200_000)
    assert r.near_context_ceiling(0.75) is True


def test_near_ceiling_false_below_fraction():
    r = _res(input_tokens=100_000, context_window=200_000)
    assert r.near_context_ceiling(0.75) is False


def test_compacted_always_ceiling():
    assert _res(compacted=True).near_context_ceiling() is True


def test_unknown_tokens_not_ceiling():
    assert _res().near_context_ceiling() is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_harness_result.py -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'input_tokens'` (or `AttributeError: near_context_ceiling`).

- [ ] **Step 3: Extend `HarnessRunResult` in `src/sdlc/models.py`**

Replace the `HarnessRunResult` class (currently lines 124-133) with:

```python
class HarnessRunResult(BaseModel):
    """Normalized result from any coding harness invocation."""

    harness: HarnessKind
    session_id: str | None = None
    exit_code: int
    summary: str  # harness's final text (truncated)
    cost_usd: float | None = None
    commit_sha: str | None = None  # checkpoint commit after the run
    diff_ref: ArtifactRef | None = None
    # Observability for the context-ceiling trigger (Finding #7):
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_window: int | None = None
    compacted: bool = False  # harness signalled a mid-run compaction

    def near_context_ceiling(self, fraction: float = 0.75) -> bool:
        """True when the run is at/over the usable context budget. A
        harness-signalled compaction always counts; otherwise compare
        input tokens to a fraction of the window. Unknown token data is
        treated as 'not at ceiling' so callers fall back to the resume
        counter rather than mis-triggering."""
        if self.compacted:
            return True
        if self.input_tokens is None or not self.context_window:
            return False
        return self.input_tokens > fraction * self.context_window
```

- [ ] **Step 4: Run the ceiling test to verify it passes**

Run: `pytest tests/test_harness_result.py -v`
Expected: 4 passed.

- [ ] **Step 5: Write the failing parse test in `tests/test_harness_parse.py`**

```python
import json

from sdlc.harness.adapters import (
    ClaudeCodeHarness,
    OpenCodeHarness,
    context_window_for,
)


def test_claude_parse_extracts_tokens_and_cost():
    payload = {
        "session_id": "abc",
        "total_cost_usd": 0.12,
        "result": "done",
        "usage": {"input_tokens": 1234, "output_tokens": 56},
    }
    res = ClaudeCodeHarness().parse(json.dumps(payload), 0)
    assert res.session_id == "abc"
    assert res.cost_usd == 0.12
    assert res.input_tokens == 1234
    assert res.output_tokens == 56


def test_opencode_parse_extracts_tokens():
    payload = {"sessionID": "xyz", "text": "ok", "usage": {"input_tokens": 10, "output_tokens": 2}}
    res = OpenCodeHarness().parse(json.dumps(payload), 0)
    assert res.session_id == "xyz"
    assert res.input_tokens == 10


def test_context_window_lookup_by_model():
    assert context_window_for("anthropic:claude-sonnet-4-6") == 200_000
    assert context_window_for("openai/gpt-5.2") == 400_000
    assert context_window_for(None) is None
    assert context_window_for("some-unknown-model") is None
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/test_harness_parse.py -v`
Expected: FAIL — `ImportError: cannot import name 'context_window_for'`.

- [ ] **Step 7: Add token parsing + window lookup in `src/sdlc/harness/adapters.py`**

After the `SUMMARY_MAX = 4000` line (line 25), add:

```python
# Best-effort model → context window (tokens). Substring match; extend as
# needed. Used only to compute the context ceiling (Finding #7); unknown
# models fall back to the resume counter.
CONTEXT_WINDOWS = {
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
    "gpt-5": 400_000,
}


def context_window_for(model: str | None) -> int | None:
    if not model:
        return None
    m = model.lower()
    for key, win in CONTEXT_WINDOWS.items():
        if key in m:
            return win
    return None
```

In `ClaudeCodeHarness.parse` (lines 104-116), extract usage. Replace the body with:

```python
def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
    session_id = cost = summary = None
    input_tokens = output_tokens = None
    try:
        payload = json.loads(stdout.strip().splitlines()[-1])
        session_id = payload.get("session_id")
        cost = payload.get("total_cost_usd")
        summary = payload.get("result") or payload.get("content")
        usage = payload.get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    except (json.JSONDecodeError, IndexError):
        summary = stdout
    return HarnessRunResult(
        harness=self.kind,
        session_id=session_id,
        exit_code=exit_code,
        summary=(summary or "")[:SUMMARY_MAX],
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
```

In `OpenCodeHarness.parse` (lines 139-150), do the same. Replace the body with:

```python
def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
    session_id = summary = None
    input_tokens = output_tokens = None
    try:
        payload = json.loads(stdout.strip().splitlines()[-1])
        session_id = payload.get("sessionID") or payload.get("session_id")
        summary = payload.get("text") or payload.get("result")
        usage = payload.get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    except (json.JSONDecodeError, IndexError):
        summary = stdout
    return HarnessRunResult(
        harness=self.kind,
        session_id=session_id,
        exit_code=exit_code,
        summary=(summary or "")[:SUMMARY_MAX],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
```

Fill `context_window` centrally in the base `run` method so both harnesses benefit. In `CodingHarness.run` (lines 48-80), change the final `return` (line 79-80) to:

```python
result = self.parse(stdout_b.decode(errors="replace"), proc.returncode or 0)
if result.context_window is None:
    result.context_window = context_window_for(req.model)
return result
```

> Note: opencode's exact usage JSON keys are not verified against a live run; the `usage.input_tokens` shape mirrors Claude's and is what the test fixture asserts. Confirm against real `opencode run --format json` output when Plan 2 integrates the live harness; adjust `.get(...)` keys if they differ.

- [ ] **Step 8: Run the parse tests to verify they pass**

Run: `pytest tests/test_harness_parse.py tests/test_harness_result.py -v`
Expected: 7 passed.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/models.py src/sdlc/harness/adapters.py tests/test_harness_result.py tests/test_harness_parse.py
git commit -m "feat: capture harness token usage + context-ceiling helper"
```

---

## Task 4: Harness env allowlist, not passthrough (Finding #8)

Stop handing the worker's whole environment to the harness. Build the child environment from a curated allowlist plus the request's deliberately-injected (repo-scoped, short-lived) credentials.

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (`run` method env; new `build_env`)
- Test: `tests/test_env_allowlist.py`

**Interfaces:**
- Produces: `adapters.ENV_ALLOWLIST: tuple[str, ...]`; `adapters.build_env(req_env: dict[str, str], allowlist: tuple[str, ...] = ENV_ALLOWLIST) -> dict[str, str]` — returns only allowlisted vars present in `os.environ`, then overlays `req_env`.

- [ ] **Step 1: Write the failing test in `tests/test_env_allowlist.py`**

```python
import sdlc.harness.adapters as ad


def test_build_env_excludes_non_allowlisted_secrets(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leakme")
    env = ad.build_env({"GITHUB_TOKEN": "scoped-short-lived"})
    assert env["PATH"] == "/usr/bin"
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env["GITHUB_TOKEN"] == "scoped-short-lived"


def test_build_env_injected_credentials_are_included():
    env = ad.build_env({"GITHUB_TOKEN": "x"})
    assert env["GITHUB_TOKEN"] == "x"


def test_build_env_only_includes_present_allowlisted_vars(monkeypatch):
    monkeypatch.delenv("LANG", raising=False)
    env = ad.build_env({})
    assert "LANG" not in env  # not set in os.environ → not fabricated
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_env_allowlist.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.harness.adapters' has no attribute 'build_env'`.

- [ ] **Step 3: Add the allowlist + builder in `src/sdlc/harness/adapters.py`**

After the `CONTEXT_WINDOWS`/`context_window_for` block from Task 3, add:

```python
# Env allowlist (Finding #8): the harness receives ONLY these vars from the
# worker environment, plus credentials deliberately injected via req.env.
# Never the worker's full os.environ (that is a bigger secret channel than
# the prompt). Covers POSIX + Windows toolchain essentials.
ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "USERPROFILE",
    "PATHEXT",
    "COMSPEC",
    "GIT_EXEC_PATH",
    "GIT_SSH",
    "SSH_AUTH_SOCK",
)


def build_env(
    req_env: dict[str, str], allowlist: tuple[str, ...] = ENV_ALLOWLIST
) -> dict[str, str]:
    """Curated child environment: allowlisted worker vars, then the
    request's injected (repo-scoped, short-TTL) credentials."""
    env = {k: os.environ[k] for k in allowlist if k in os.environ}
    env.update(req_env)
    return env
```

- [ ] **Step 4: Use it in `CodingHarness.run`**

In `src/sdlc/harness/adapters.py`, change the subprocess env (line 54) from:

```python
env = ({**os.environ, **req.env},)
```

to:

```python
env = (build_env(req.env),)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_env_allowlist.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_env_allowlist.py
git commit -m "feat: harness env allowlist instead of full-env passthrough"
```

---

## Task 5: Running-integration-branch git activities (Finding #1 — CRITICAL)

Make dependent tasks actually build on each other's code. Add a per-run integration branch that accumulates completed work; branch each task from the **current integration head**; merge back on success; anchor diffs to the branch point.

**Files:**
- Modify: `src/sdlc/activities.py` (`WORKTREES_ROOT` → configurable; `create_worktree` signature/return; `get_task_diff` anchor; new `setup_integration_branch`, `merge_into_integration`)
- Test: `tests/test_integration_activities.py`

**Interfaces:**
- Produces (all in `activities.py`):
  - `WorktreeInput{repo_path: str, run_id: str, task_id: str, from_ref: str}`
  - `WorktreeHandle{path: str, branch: str, branch_point: str}` (returned by `create_worktree`)
  - `IntegrationInput{repo_path: str, run_id: str, base_branch: str}`; `setup_integration_branch(inp) -> str` (integration head SHA)
  - `MergeInput{repo_path: str, run_id: str, task_branch: str}`; `MergeResult{merged: bool, conflict: bool, integration_head: str}`; `merge_into_integration(inp) -> MergeResult`
  - `DiffInput{worktree: str, branch_point: str, max_chars: int = 60_000}`; `get_task_diff(inp) -> dict` (unchanged return shape `{stat, patch, files}`)
- Consumed by: Plan 2's workflow orchestration; Task 7 updates `feature.py`'s call sites to the new signatures (still branching from base until Plan 2 wires setup/merge).

- [ ] **Step 1: Write the failing tests in `tests/test_integration_activities.py`**

```python
import asyncio
from pathlib import Path

from sdlc.activities import (
    DiffInput,
    IntegrationInput,
    MergeInput,
    WorktreeInput,
    create_worktree,
    get_task_diff,
    merge_into_integration,
    setup_integration_branch,
)
from tests.conftest import run_git

RUN = "run1"


def _add_commit(path: str, name: str, content: str, msg: str) -> None:
    (Path(path) / name).write_text(content)
    run_git(["add", "-A"], path)
    run_git(["commit", "-m", msg], path)


def test_dependent_task_sees_prior_task_code(git_repo):
    head = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )

    a = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head))
    )
    _add_commit(a.path, "a.txt", "from A\n", "A work")
    res = asyncio.run(
        merge_into_integration(MergeInput(repo_path=git_repo, run_id=RUN, task_branch=a.branch))
    )
    assert res.merged and not res.conflict

    # B branches from the UPDATED integration head → must see A's file.
    b = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id=RUN, task_id="B", from_ref=res.integration_head
            )
        )
    )
    assert (Path(b.path) / "a.txt").read_text() == "from A\n"


def test_diff_anchors_to_branch_point_not_base(git_repo):
    head = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )
    a = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head))
    )
    _add_commit(a.path, "a.txt", "from A\n", "A work")
    res = asyncio.run(
        merge_into_integration(MergeInput(repo_path=git_repo, run_id=RUN, task_branch=a.branch))
    )

    b = asyncio.run(
        create_worktree(
            WorktreeInput(
                repo_path=git_repo, run_id=RUN, task_id="B", from_ref=res.integration_head
            )
        )
    )
    _add_commit(b.path, "b.txt", "from B\n", "B work")
    diff = asyncio.run(get_task_diff(DiffInput(worktree=b.path, branch_point=b.branch_point)))
    assert "b.txt" in diff["files"]
    assert "a.txt" not in diff["files"]  # A's change is upstream, not B's diff


def test_merge_conflict_is_detected_and_aborted(git_repo):
    head = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=git_repo, run_id=RUN, base_branch="main")
        )
    )
    # A and B branch from the same head and edit the SAME file.
    a = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="A", from_ref=head))
    )
    _add_commit(a.path, "shared.txt", "A version\n", "A edits shared")
    b = asyncio.run(
        create_worktree(WorktreeInput(repo_path=git_repo, run_id=RUN, task_id="B", from_ref=head))
    )
    _add_commit(b.path, "shared.txt", "B version\n", "B edits shared")

    ra = asyncio.run(
        merge_into_integration(MergeInput(repo_path=git_repo, run_id=RUN, task_branch=a.branch))
    )
    assert ra.merged is True
    rb = asyncio.run(
        merge_into_integration(MergeInput(repo_path=git_repo, run_id=RUN, task_branch=b.branch))
    )
    assert rb.conflict is True and rb.merged is False
    # Integration head unchanged after the aborted merge → equals A's merge head.
    assert rb.integration_head == ra.integration_head
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_integration_activities.py -v`
Expected: FAIL — `ImportError: cannot import name 'setup_integration_branch'`.

- [ ] **Step 3: Make the worktrees root configurable in `src/sdlc/activities.py`**

Change the imports/constant block near the top. Replace line 17 (`WORKTREES_ROOT = "/var/sdlc/worktrees"`) with:

```python
import os


def _worktrees_root() -> str:
    """Read at call time so tests can point it at a temp dir."""
    return os.environ.get("SDLC_WORKTREES_ROOT", "/var/sdlc/worktrees")
```

(Add `import os` with the other stdlib imports at the top if not already present — currently `activities.py` imports `asyncio` and `subprocess` only.)

- [ ] **Step 4: Rewrite `create_worktree` and add integration activities in `src/sdlc/activities.py`**

Replace the `WorktreeInput` dataclass and `create_worktree` (lines 20-36) with:

```python
@dataclass
class WorktreeInput:
    repo_path: str
    run_id: str
    task_id: str
    from_ref: str  # integration head SHA (ADR-14) — NOT base_branch


@dataclass
class WorktreeHandle:
    path: str
    branch: str
    branch_point: str  # SHA the task branched from (diff anchor)


@activity.defn
async def create_worktree(inp: WorktreeInput) -> WorktreeHandle:
    """Run-scoped worktree + branch, cut from the integration head."""
    path = f"{_worktrees_root()}/{inp.run_id}/{inp.task_id}"
    branch = f"sdlc/{inp.run_id}/{inp.task_id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, path, inp.from_ref],
        cwd=inp.repo_path,
        check=True,
        capture_output=True,
    )
    point = subprocess.run(
        ["git", "rev-parse", inp.from_ref], cwd=inp.repo_path, capture_output=True, text=True
    ).stdout.strip()
    return WorktreeHandle(path=path, branch=branch, branch_point=point)


@dataclass
class IntegrationInput:
    repo_path: str
    run_id: str
    base_branch: str


@activity.defn
async def setup_integration_branch(inp: IntegrationInput) -> str:
    """Create sdlc/<run>/integration from base in its own worktree;
    return its head SHA. Task worktrees branch from this head."""
    branch = f"sdlc/{inp.run_id}/integration"
    path = f"{_worktrees_root()}/{inp.run_id}/integration"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, path, inp.base_branch],
        cwd=inp.repo_path,
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True
    ).stdout.strip()


@dataclass
class MergeInput:
    repo_path: str
    run_id: str
    task_branch: str


@dataclass
class MergeResult:
    merged: bool
    conflict: bool
    integration_head: str


@activity.defn
async def merge_into_integration(inp: MergeInput) -> MergeResult:
    """Merge a completed task branch into the run's integration branch.
    A merge conflict = a falsified `overlaps` declaration (Finding #1):
    abort cleanly and report it so the caller serializes/escalates."""
    ipath = f"{_worktrees_root()}/{inp.run_id}/integration"
    merge = subprocess.run(
        ["git", "merge", "--no-ff", "-m", f"merge {inp.task_branch}", inp.task_branch],
        cwd=ipath,
        capture_output=True,
        text=True,
    )
    if merge.returncode != 0:
        subprocess.run(["git", "merge", "--abort"], cwd=ipath, capture_output=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ipath, capture_output=True, text=True
        ).stdout.strip()
        return MergeResult(merged=False, conflict=True, integration_head=head)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ipath, capture_output=True, text=True
    ).stdout.strip()
    return MergeResult(merged=True, conflict=False, integration_head=head)
```

- [ ] **Step 5: Anchor `get_task_diff` to the branch point in `src/sdlc/activities.py`**

Replace the `DiffInput` dataclass and `get_task_diff` (lines 78-102) with:

```python
@dataclass
class DiffInput:
    worktree: str
    branch_point: str  # SHA the task branched from — NOT base_branch
    max_chars: int = 60_000


@activity.defn
async def get_task_diff(inp: DiffInput) -> dict:
    """Materialized diff for clean-context validators (FR-804), anchored to
    the task's branch point so a dependent task's diff shows only its own
    change — upstream work is invisible (Finding #1)."""
    rng = f"{inp.branch_point}...HEAD"
    stat = subprocess.run(
        ["git", "diff", "--stat", rng], cwd=inp.worktree, capture_output=True, text=True
    ).stdout
    patch = subprocess.run(
        ["git", "diff", rng], cwd=inp.worktree, capture_output=True, text=True
    ).stdout
    files = subprocess.run(
        ["git", "diff", "--name-only", rng], cwd=inp.worktree, capture_output=True, text=True
    ).stdout.splitlines()
    return {"stat": stat, "patch": patch[: inp.max_chars], "files": files}
```

- [ ] **Step 6: Register the new activities on the worker**

In `src/sdlc/worker.py`, update the import (lines 16-19) and the `activities=[...]` list (lines 37-41) to include `setup_integration_branch` and `merge_into_integration`:

Import block becomes:

```python
from .activities import (
    create_worktree,
    deploy,
    merge_into_integration,
    open_pull_request,
    run_coding_task,
    run_test_suite,
    setup_integration_branch,
)
```

Activities list becomes:

```python
activities = (
    [
        create_worktree,
        setup_integration_branch,
        merge_into_integration,
        run_coding_task,
        run_test_suite,
        open_pull_request,
        deploy,
        *agent_activities,
    ],
)
```

- [ ] **Step 7: Run the integration tests to verify they pass**

Run: `pytest tests/test_integration_activities.py -v`
Expected: 3 passed. (This includes the Finding #1 regression: `test_dependent_task_sees_prior_task_code`.)

- [ ] **Step 8: Verify the worker module still imports**

Run: `python -c "import sdlc.worker"`
Expected: exit 0 (imports `feature.py` → will still work after Task 7; if you run this before Task 7, expect it to fail only on the `feature.py` GateDecision edits — run it again at the end of Task 7).

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/activities.py src/sdlc/worker.py tests/test_integration_activities.py
git commit -m "feat: running integration branch + branch-point diffs (Finding #1)"
```

---

## Task 6: DeterministicQualityGate — absolute vs advisory (Finding #5)

Add the pure, deterministic gate the specs describe (and the skeleton lacks). It consumes typed check results and decides pass/fail: absolute checks are never overridable; advisory checks block only until an audited human override is recorded; the critical-security check is a floor that can't be demoted.

**Files:**
- Create: `src/sdlc/gate.py`
- Modify: `src/sdlc/activities.py` (thin `@activity.defn` wrapper)
- Test: `tests/test_quality_gate.py`

**Interfaces:**
- Produces (in `gate.py`):
  - `CheckClass` (str Enum: `ABSOLUTE="absolute"`, `ADVISORY="advisory"`)
  - `CheckResult{name: str, passed: bool, classification: CheckClass, detail: str = ""}`
  - `GateOverride{check: str, approved_by: str, reason: str}`
  - `GateReport{passed: bool, blocking: list[str], overridden: list[str], checks: list[CheckResult]}`
  - `ABSOLUTE_FLOOR: frozenset[str]` (contains `"security_no_critical"`)
  - `build_check(name: str, passed: bool, requested: CheckClass, detail: str = "") -> CheckResult` (upgrades floor names to ABSOLUTE)
  - `evaluate_quality_gate(checks: list[CheckResult], overrides: list[GateOverride] | None = None) -> GateReport`
- Consumed by: Plan 2's merge-gate wiring.

- [ ] **Step 1: Write the failing tests in `tests/test_quality_gate.py`**

```python
from sdlc.gate import (
    CheckClass,
    GateOverride,
    build_check,
    evaluate_quality_gate,
)


def test_absolute_failure_blocks_unconditionally():
    checks = [build_check("lint", False, CheckClass.ABSOLUTE)]
    rep = evaluate_quality_gate(
        checks, overrides=[GateOverride(check="lint", approved_by="alice", reason="whatever")]
    )
    assert rep.passed is False
    assert "lint" in rep.blocking  # override ignored for absolute
    assert rep.overridden == []


def test_advisory_failure_blocks_without_override():
    rep = evaluate_quality_gate([build_check("coverage", False, CheckClass.ADVISORY)])
    assert rep.passed is False
    assert "coverage" in rep.blocking


def test_advisory_failure_passes_with_override():
    checks = [build_check("coverage", False, CheckClass.ADVISORY)]
    rep = evaluate_quality_gate(
        checks, overrides=[GateOverride(check="coverage", approved_by="alice", reason="legacy gap")]
    )
    assert rep.passed is True
    assert rep.overridden == ["coverage"]
    assert rep.blocking == []


def test_security_floor_cannot_be_demoted():
    c = build_check("security_no_critical", False, CheckClass.ADVISORY)
    assert c.classification is CheckClass.ABSOLUTE
    rep = evaluate_quality_gate(
        [c],
        overrides=[GateOverride(check="security_no_critical", approved_by="alice", reason="yolo")],
    )
    assert rep.passed is False


def test_all_pass_is_clean():
    checks = [
        build_check("lint", True, CheckClass.ABSOLUTE),
        build_check("coverage", True, CheckClass.ADVISORY),
    ]
    rep = evaluate_quality_gate(checks)
    assert rep.passed is True
    assert rep.blocking == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_quality_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.gate'`.

- [ ] **Step 3: Implement `src/sdlc/gate.py`**

```python
"""DeterministicQualityGate (Finding #5).

Pure code — no LLM. Consumes typed evidence (proposer ReviewReport /
AnalysisReport findings, coverage number, lint, traceability) reduced to
CheckResults, and decides pass/fail:

  * absolute checks  — block the merge unconditionally; never overridable.
  * advisory checks  — block only until an audited human override is recorded.

The critical-security check is a floor: it is forced ABSOLUTE even if a
project's config marks it advisory. The advisory LLM `MergeVerdict` is NOT
consulted here — it is only ever an advisory input to a SOFT merge gate,
after this gate has already passed.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CheckClass(str, Enum):
    ABSOLUTE = "absolute"  # never overridable (lint, build, critical security)
    ADVISORY = "advisory"  # overridable by an audited human decision


class CheckResult(BaseModel):
    name: str
    passed: bool
    classification: CheckClass
    detail: str = ""


class GateOverride(BaseModel):
    """An audited human override of a failed advisory check."""

    check: str
    approved_by: str  # human identity (retained as calibration signal)
    reason: str


class GateReport(BaseModel):
    passed: bool
    blocking: list[str] = Field(default_factory=list)  # check names still blocking
    overridden: list[str] = Field(default_factory=list)  # advisory checks waved through
    checks: list[CheckResult]


# Never demotable to advisory, whatever a project configures.
ABSOLUTE_FLOOR: frozenset[str] = frozenset({"security_no_critical"})


def build_check(name: str, passed: bool, requested: CheckClass, detail: str = "") -> CheckResult:
    """Construct a CheckResult, forcing floor checks to ABSOLUTE."""
    classification = CheckClass.ABSOLUTE if name in ABSOLUTE_FLOOR else requested
    return CheckResult(name=name, passed=passed, classification=classification, detail=detail)


def evaluate_quality_gate(
    checks: list[CheckResult],
    overrides: list[GateOverride] | None = None,
) -> GateReport:
    override_names = {o.check for o in (overrides or [])}
    blocking: list[str] = []
    overridden: list[str] = []
    for c in checks:
        if c.passed:
            continue
        if c.classification is CheckClass.ABSOLUTE:
            blocking.append(c.name)  # absolute: override ignored
        elif c.name in override_names:
            overridden.append(c.name)  # advisory: audited waiver
        else:
            blocking.append(c.name)
    return GateReport(passed=not blocking, blocking=blocking, overridden=overridden, checks=checks)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_quality_gate.py -v`
Expected: 5 passed.

- [ ] **Step 5: Add a thin activity wrapper in `src/sdlc/activities.py`**

At the end of `activities.py`, add (imports at top: add `from .gate import CheckResult, GateOverride, GateReport, evaluate_quality_gate`):

```python
@dataclass
class QualityGateInput:
    checks: list[CheckResult]
    overrides: list[GateOverride] | None = None


@activity.defn
async def evaluate_gate(inp: QualityGateInput) -> GateReport:
    """Activity wrapper over the pure DeterministicQualityGate."""
    return evaluate_quality_gate(inp.checks, inp.overrides)
```

Register it on the worker: add `evaluate_gate` to the `from .activities import (...)` block and the `activities=[...]` list in `src/sdlc/worker.py` (alongside the Task 5 additions).

- [ ] **Step 6: Verify activities + worker still import**

Run: `python -c "import sdlc.activities, sdlc.worker"`
Expected: exit 0 (after Task 7 the `feature.py` chain is clean; if run before Task 7, defer this check to Task 7).

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/gate.py src/sdlc/activities.py src/sdlc/worker.py tests/test_quality_gate.py
git commit -m "feat: DeterministicQualityGate with absolute/advisory checks (Finding #5)"
```

---

## Task 7: MergeVerdict split + module coherence (Finding #4/#5) and fix the broken roles import

Split the *LLM* release-judgment out of `GateDecision` into an advisory `MergeVerdict` proposer, fix the pre-existing broken import in `roles.py`, and make the minimal `feature.py` edits so the whole package imports and is contract-consistent. **No workflow control-flow changes** — the integration setup/merge orchestration, gate-revision loop, and token-threshold logic stay for Plan 2.

**Files:**
- Modify: `src/sdlc/models.py` (add `MergeVerdict`)
- Modify: `src/sdlc/agents/roles.py:15` (fix `.models` → `..models`; `quality_gate_agent` → `merge_verdict_agent`)
- Modify: `src/sdlc/workflows/feature.py` (imports; `_gate` policy/timeout constructors; `create_worktree`/`get_task_diff` call sites to new signatures; merge call site)
- Test: `tests/test_module_imports.py`

**Interfaces:**
- Produces: `models.MergeVerdict{approve: bool, confidence: float, rationale: str, concerns: list[str]}`; `roles.merge_verdict_agent`, `roles.t_merge_verdict`.
- Consumes: `WorktreeHandle`, `MergeResult`, `DiffInput.branch_point` (Task 5); `GateOutcome` (Task 2).

- [ ] **Step 1: Write the failing test in `tests/test_module_imports.py`**

```python
def test_merge_verdict_model():
    from sdlc.models import MergeVerdict

    v = MergeVerdict(approve=True, confidence=0.9, rationale="clean build")
    assert v.approve is True
    assert v.confidence == 0.9
    assert v.concerns == []


def test_roles_and_workflow_import_cleanly():
    import importlib

    roles = importlib.import_module("sdlc.agents.roles")
    assert hasattr(roles, "t_merge_verdict")
    assert not hasattr(roles, "t_gate")  # renamed away
    importlib.import_module("sdlc.workflows.feature")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_module_imports.py -v`
Expected: FAIL — `ImportError: cannot import name 'MergeVerdict'` (and the roles import currently errors on `from .models`).

- [ ] **Step 3: Add `MergeVerdict` to `src/sdlc/models.py`**

After the `GateDecision` class / `gate_key` function (Task 2), add:

```python
class MergeVerdict(BaseModel):
    """Advisory LLM proposer output (Finding #5). Consulted only under a
    SOFT merge policy, and only AFTER the DeterministicQualityGate passes.
    It can approve an already-clean build; it can never bypass the gate."""

    approve: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    concerns: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Fix the import bug and rename the agent in `src/sdlc/agents/roles.py`**

Change line 15 from `from .models import (` to `from ..models import (`. In that import list, replace `GateDecision` with `MergeVerdict`. Remove `IdeaBrief` if it is unused after this change is applied (it is imported but not referenced — drop it to keep the import clean).

Replace the `quality_gate_agent` definition (lines 85-95) with:

```python
merge_verdict_agent = Agent(
    MODEL,
    name="merge_verdict_agent",
    output_type=MergeVerdict,
    system_prompt=(
        "You are an ADVISORY release reviewer, consulted only after the "
        "deterministic quality gate has already passed. Given the QA report, "
        "reviewer summary and diff stats, give a confidence-scored opinion on "
        "whether the merge should proceed. You cannot block a merge on your "
        "own and you cannot approve one the deterministic gate failed; you "
        "only advise. Be conservative and list concrete concerns."
    ),
)
```

Update the Temporal-wrapping block (lines 108-116). Replace `t_gate = TemporalAgent(quality_gate_agent)` with `t_merge_verdict = TemporalAgent(merge_verdict_agent)`, and update `ALL_TEMPORAL_AGENTS`:

```python
t_merge_verdict = TemporalAgent(merge_verdict_agent)
...
ALL_TEMPORAL_AGENTS = [t_clarify, t_architect, t_planner, t_qa, t_merge_verdict, t_devops]
```

- [ ] **Step 5: Update `feature.py` imports and gate constructors**

In `src/sdlc/workflows/feature.py`:

Change the activities import (lines 15-19) to the new names:

```python
from .activities import (
    CodingTaskInput,
    DeployInput,
    DiffInput,
    PROpenInput,
    QAInput,
    WorktreeInput,
    create_worktree,
    deploy,
    get_task_diff,
    open_pull_request,
    run_coding_task,
    run_test_suite,
)
```
(unchanged — `WorktreeInput`/`DiffInput`/`create_worktree`/`get_task_diff` still exist; only their fields changed.)

Change the roles import (lines 20-22) from `t_gate` to `t_merge_verdict`:

```python
from .agents.roles import (
    t_architect,
    t_clarify,
    t_merge_verdict,
    t_planner,
    t_qa,
)
```

Change the models import (lines 23-26) to add `GateOutcome` and `MergeVerdict`:

```python
from .models import (
    DevTask,
    ExecutionMode,
    GateDecision,
    GateOutcome,
    GatePolicy,
    HandoffSummary,
    IdeaBrief,
    MergeVerdict,
    PipelineConfig,
    TaskResult,
)
```

In `_gate` (lines 65-87), update the two `GateDecision(...)` constructors:
- Line 71: `return GateDecision(gate=name, outcome=GateOutcome.APPROVE, decided_by="policy")`
- Lines 83-84: `return GateDecision(gate=name, outcome=GateOutcome.REJECT, decided_by="timeout")`

(The `auto_decision.approved` read on line 73 keeps working via the property.)

- [ ] **Step 6: Update the `create_worktree` / `get_task_diff` call sites in `_dev_task`**

In `_dev_task` (lines 89-188), update the worktree creation (lines 100-105) to the new signature and capture the handle:

```python
role_cfg = cfg.roles.get(task.role, cfg.roles["dev"])
handle = await workflow.execute_activity(
    create_worktree,
    WorktreeInput(
        repo_path=repo_path,
        run_id=workflow.info().workflow_id,
        task_id=task.id,
        from_ref=base_branch,
    ),
    **ACT,
)
worktree = handle.path
```

> Plan 2 note: `from_ref=base_branch` is transitional — every task still branches from base until Plan 2 adds `setup_integration_branch` at run start and threads the integration head + `merge_into_integration` between tasks. The activities are ready; the orchestration is not wired here.

Update the diff call (lines 139-143) to anchor on the branch point:

```python
            diff = await workflow.execute_activity(
                get_task_diff,
                DiffInput(worktree=worktree, branch_point=handle.branch_point),
                **ACT,
            )
```

Replace the three `branch=f"sdlc/{task.id}"` literals (lines 158, 186) with `handle.branch` so the recorded branch matches the run-scoped name:
- Line 157-159 `TaskResult(...)`: `branch=handle.branch,`
- Line 182-188 `TaskResult(...)`: `branch=handle.branch,`

- [ ] **Step 7: Update the merge-gate call site in `run`**

In `run` (lines 262-268), replace the `t_gate` consultation with the advisory `MergeVerdict` converted into an auto `GateDecision`:

```python
# 5. MERGE gate — advisory MergeVerdict only informs the SOFT path.
# (Plan 2 runs the DeterministicQualityGate before this consult.)
verdict: MergeVerdict = (
    await t_merge_verdict.run(
        "Advisory only. Given these task results, should the merge "
        f"proceed? Task results: {[r.model_dump() for r in done.values()]}"
    )
).output
auto = GateDecision(
    gate="merge",
    outcome=(GateOutcome.APPROVE if verdict.approve else GateOutcome.REJECT),
    decided_by="policy",
    comments=verdict.rationale,
)
gate = await self._gate("merge", cfg, auto_decision=auto)
if not gate.approved:
    return "rejected:merge"
```

- [ ] **Step 8: Run the import-smoke test to verify it passes**

Run: `pytest tests/test_module_imports.py -v`
Expected: 2 passed.

- [ ] **Step 9: Verify the whole package imports end-to-end**

Run: `python -c "import sdlc.cli, sdlc.worker, sdlc.workflows.feature, sdlc.agents.roles"`
Expected: exit 0.

- [ ] **Step 10: Commit**

```bash
git add src/sdlc/models.py src/sdlc/agents/roles.py src/sdlc/workflows/feature.py tests/test_module_imports.py
git commit -m "feat: MergeVerdict advisory proposer + fix roles import + wire new activity signatures"
```

---

## Task 8: Full green run + review-doc bookkeeping

Confirm the whole suite passes together and record which review-doc code to-dos this plan discharged (so Plan 2 starts from an accurate ledger).

**Files:**
- Modify: `docs/architecture-review-2026-07.md` (annotate discharged code to-dos)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: all tests pass (bootstrap 2, gate_decision 3, harness_result 4, harness_parse 3, env_allowlist 3, integration_activities 3, quality_gate 5, module_imports 2 = 25 passed). If any fail, fix before proceeding — do not annotate the review doc until green.

- [ ] **Step 2: Annotate discharged to-dos in the review doc**

In `docs/architecture-review-2026-07.md`, append a short subsection under "Open follow-ups" (or a new "Implementation status" section) noting that Findings #1, #4, #5, #6 (contract), #7, #8 (env allowlist) have their *contract/activity-level* code to-dos implemented by `docs/superpowers/plans/2026-07-04-foundation-contract-alignment.md`, and that the following remain for Plan 2 (workflow orchestration): running-integration setup/merge wiring, gate-revision loop with round-scoped signal keys, token-threshold fresh-session trigger, DeterministicQualityGate wired ahead of the merge gate, `pre_tool` hook + credential injection + tiered isolation launch path.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture-review-2026-07.md
git commit -m "docs: record Foundation plan discharge of review-doc code to-dos"
```

---

## Self-Review

**Spec coverage** (chosen Foundation scope → task):
- GateDecision outcome enum + (gate, round) identity → Task 2 ✓
- HarnessRunResult token fields + ceiling → Task 3 ✓
- Env allowlist on the harness request → Task 4 ✓
- Running-integration-branch activities (`from_ref` worktree, `merge_into_integration`, branch-point diff) → Task 5 ✓
- DeterministicQualityGate (absolute vs advisory) → Task 6 ✓
- Forced-by-contract consistency (MergeVerdict split, broken-import fix, call-site sweep) → Tasks 2/7 ✓

**Deferred to Plan 2 (explicitly, not gaps):** integration setup/merge orchestration in the workflow; gate-revision loop + round-scoped signal keys; token-threshold fresh-session trigger; DeterministicQualityGate wired before the merge gate; `pre_tool` hook, credential injection, tiered isolation launch path; memoization/watermark cache; Hindsight memory; dashboard/MCP/DAPER.

**Type consistency:** `GateOutcome` used identically in `models.py`, `cli.py`, `feature.py`. `WorktreeHandle.branch_point` → `DiffInput.branch_point` names match. `MergeResult.integration_head` → `create_worktree(from_ref=...)` chain is consistent. `MergeVerdict{approve, confidence, rationale, concerns}` matches its test and its `feature.py` consumer (`verdict.approve`, `verdict.rationale`).

**Placeholder scan:** every code step contains real code; every run step has an exact command and expected result. No TBD/TODO left.
