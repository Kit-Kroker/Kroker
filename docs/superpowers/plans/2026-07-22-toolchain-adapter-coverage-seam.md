# E-30 — ToolchainAdapter + Coverage Seam (Python reference) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the deterministic quality gate a language-agnostic, marker-file-resolved toolchain adapter (Python reference), so a real coverage-instrumented test run lands `coverage.xml` in the integration worktree where the gate reads it — closing the FR-106 gap and turning `build_integration_green` into an actual integration test run.

**Architecture:** A `ToolchainAdapter` ABC + `TOOLCHAINS` registry beside `harness/adapters.py`, resolved by repo marker file. The adapter object is pure (produces command strings + identity only); execution lives in a new Temporal activity `run_integration_checks` that runs test(+coverage)+lint against the merged integration head. Coverage normalizes to Cobertura XML (existing `measure_coverage` reader unchanged); security normalizes to a SARIF-shaped `SecurityReport` seam (regex default kept, semgrep opt-in). Unknown languages degrade to the pre-E-30 path.

**Tech Stack:** Python 3.11+, Temporal (`temporalio`), pytest + pytest-asyncio, pytest-cov (new dev dep), coverage.py (Cobertura), `defusedxml` (existing).

**Spec:** `docs/superpowers/specs/2026-07-22-toolchain-adapter-coverage-seam-design.md`

## Global Constraints

- Adapter objects are **pure** — no subprocess/filesystem/network I/O; execution only inside Temporal activities (mirror `harness/adapters.py`; workflows never touch subprocesses).
- **Detection resolves by marker file in the produced repo, never the contract's claimed stack** (ADR-15).
- **Fail-safe / no-adapter degradation:** an unrecognized language behaves exactly as pre-E-30 (per-task aggregate green, standalone `run_lint`, `measured=False` coverage). Never block on an unknown language.
- **Green signal ≠ coverage signal:** a coverage-tooling failure (pytest exit code 4) degrades coverage to `measured=False`, never a false `build_integration_green` (ABSOLUTE) failure.
- **Gate readers unchanged:** `measure_coverage` (`activities.py:568`) and the `security_no_critical` check (`feature.py:1170`) are not modified.
- Canonical formats: **Cobertura XML** (coverage), **SARIF-shaped `SecurityReport`** (security).
- Requires-python `>=3.11`. Windows + POSIX (this repo runs on Windows).
- Anchors: **FR-108** (already added to `PRD.md`), FR-106, FR-104, FR-203, ADR-15, SC-5.

**Pre-work (fold into Task 1's commit):** `PRD.md` FR-108 and the spec file are already written but uncommitted. Stage and commit them with Task 1.

---

### Task 1: `ToolchainAdapter` package — interface, Python adapter, `detect()`

**Files:**
- Create: `src/sdlc/toolchain/__init__.py`
- Create: `src/sdlc/toolchain/adapters.py`
- Test: `tests/test_toolchain_adapters.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `class ToolchainKind(str, Enum)` with `PYTHON = "python"`.
  - `class ToolchainAdapter(ABC)` with `kind: ToolchainKind`, `marker: str`, `test_cmd(self, coverage: bool = True) -> str`, `lint_cmd(self) -> str`, `build_cmd(self) -> str | None`.
  - `class PythonToolchain(ToolchainAdapter)`.
  - `TOOLCHAINS: dict[ToolchainKind, ToolchainAdapter]`.
  - `detect(worktree: str) -> ToolchainAdapter | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_toolchain_adapters.py`:

```python
"""ToolchainAdapter: pure command/identity resolution (ADR-15, FR-108)."""

from sdlc.toolchain.adapters import (
    PythonToolchain,
    TOOLCHAINS,
    ToolchainKind,
    detect,
)


def test_detect_python_by_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.PYTHON


def test_detect_returns_none_on_bare_dir(tmp_path):
    assert detect(str(tmp_path)) is None


def test_python_test_cmd_is_coverage_instrumented_by_default():
    cmd = PythonToolchain().test_cmd()
    assert "--cov" in cmd and "coverage.xml" in cmd


def test_python_test_cmd_plain_omits_coverage():
    cmd = PythonToolchain().test_cmd(coverage=False)
    assert "--cov" not in cmd and cmd.startswith("pytest")


def test_python_lint_cmd():
    assert PythonToolchain().lint_cmd() == "ruff check ."


def test_python_build_cmd_is_none():
    assert PythonToolchain().build_cmd() is None


def test_registry_has_python_marker():
    assert TOOLCHAINS[ToolchainKind.PYTHON].marker == "pyproject.toml"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_toolchain_adapters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.toolchain'`.

- [ ] **Step 3: Create the package**

Create `src/sdlc/toolchain/__init__.py` (empty file):

```python
```

Create `src/sdlc/toolchain/adapters.py`:

```python
"""Language-agnostic toolchain adapters (ADR-15, FR-108).

A ToolchainAdapter resolves the deterministic quality gate's stack-specific
verification commands (test / lint / build) from the produced repository's
marker file, so the gate grades whatever language was actually built.
Structurally identical to harness/adapters.py: an ABC + concrete adapters +
a module-level registry dict.

The adapter object is PURE — it produces command strings and identity only,
never runs a subprocess. Execution lives in Temporal activities
(activities.py), exactly as CodingHarness never runs in workflow code.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from enum import Enum


class ToolchainKind(str, Enum):
    PYTHON = "python"
    # GO / TS / RUST are added by E-30a/b/c — each is the N-th adapter,
    # identical in shape, added on demand as the case corpus needs it.


class ToolchainAdapter(ABC):
    kind: ToolchainKind
    marker: str  # marker filename at the repo root detect() resolves by

    @abstractmethod
    def test_cmd(self, coverage: bool = True) -> str:
        """Test command. With coverage=True it MUST emit a Cobertura
        coverage.xml at the worktree root, where measure_coverage reads.
        coverage=False is the honest green-signal fallback when coverage
        tooling is unavailable (see run_integration_checks)."""

    @abstractmethod
    def lint_cmd(self) -> str: ...

    def build_cmd(self) -> str | None:
        """Separate build step, or None where the language has none (Python)."""
        return None


class PythonToolchain(ToolchainAdapter):
    kind = ToolchainKind.PYTHON
    marker = "pyproject.toml"

    def test_cmd(self, coverage: bool = True) -> str:
        # --maxfail bounds output like the per-task QA command. pytest-cov
        # drives coverage.py; --cov-report=xml writes Cobertura to coverage.xml
        # at cwd (the integration worktree measure_coverage reads).
        base = "pytest -q --maxfail=25"
        if coverage:
            return f"{base} --cov=. --cov-report=xml:coverage.xml"
        return base

    def lint_cmd(self) -> str:
        return "ruff check ."


TOOLCHAINS: dict[ToolchainKind, ToolchainAdapter] = {
    ToolchainKind.PYTHON: PythonToolchain(),
}


def detect(worktree: str) -> ToolchainAdapter | None:
    """Return the first adapter whose marker file exists at the worktree root,
    or None for an unrecognized/absent marker (caller degrades gracefully).

    Resolves by what was BUILT (marker file), never the contract's claimed
    stack — a marker/claim mismatch is itself a signal (ADR-15)."""
    for adapter in TOOLCHAINS.values():
        if os.path.isfile(os.path.join(worktree, adapter.marker)):
            return adapter
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_toolchain_adapters.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit (includes the pre-written PRD + spec)**

```bash
git add PRD.md docs/superpowers/specs/2026-07-22-toolchain-adapter-coverage-seam-design.md \
        src/sdlc/toolchain/__init__.py src/sdlc/toolchain/adapters.py \
        tests/test_toolchain_adapters.py
git commit -m "feat(toolchain): ToolchainAdapter + Python reference, detect() (E-30)

PRD FR-108 (language-agnostic toolchain) + ADR-15 design spec land with the
pure adapter layer. Marker-file resolution, coverage-instrumented test_cmd.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: SARIF → `SecurityReport` normalizer seam

**Files:**
- Create: `src/sdlc/toolchain/sarif.py`
- Test: `tests/test_sarif.py`

**Interfaces:**
- Consumes: `SecurityFinding`, `SecurityReport` from `sdlc.models`.
- Produces:
  - `findings_from_sarif(doc: dict) -> list[SecurityFinding]`.
  - `report_from_sarif(doc: dict) -> SecurityReport`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sarif.py`:

```python
"""SARIF -> SecurityReport normalizer seam (ADR-15 security, FR-108)."""

import pytest

from sdlc.toolchain.sarif import findings_from_sarif, report_from_sarif

WELL_FORMED = {
    "runs": [
        {
            "results": [
                {
                    "level": "error",
                    "ruleId": "py.eval",
                    "message": {"text": "use of eval"},
                    "locations": [{"physicalLocation": {"artifactLocation": {"uri": "app/x.py"}}}],
                },
                {"level": "warning", "ruleId": "py.shell", "message": {"text": "shell=True"}},
            ]
        }
    ]
}


def test_wellformed_maps_severity_and_fields():
    fs = findings_from_sarif(WELL_FORMED)
    assert len(fs) == 2
    assert fs[0].severity == "critical" and fs[0].rule == "py.eval"
    assert fs[0].path == "app/x.py" and "eval" in fs[0].detail
    assert fs[1].severity == "high" and fs[1].path == ""


def test_report_counts_critical():
    r = report_from_sarif(WELL_FORMED)
    assert r.critical == 1 and len(r.findings) == 2


@pytest.mark.parametrize(
    "bad",
    [
        {},
        None,
        "nope",
        {"runs": "x"},
        {"runs": [1, 2]},
        {"runs": [{"results": "x"}]},
        {"runs": [{"results": [42]}]},
    ],
)
def test_malformed_sarif_is_failsafe_empty(bad):
    assert findings_from_sarif(bad) == []


def test_report_from_malformed_is_zero_critical():
    r = report_from_sarif({"runs": [{"results": "x"}]})
    assert r.critical == 0 and r.findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sarif.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.toolchain.sarif'`.

- [ ] **Step 3: Create the normalizer**

Create `src/sdlc/toolchain/sarif.py`:

```python
"""SARIF -> SecurityReport normalizer (ADR-15 security seam, FR-108).

The canonical security-finding shape is SecurityReport/SecurityFinding
(models.py); the gate's security_no_critical check reads it unchanged. Today's
default security_scan keeps its offline regex ruleset; an OPT-IN semgrep path
shells `semgrep --sarif` and feeds its output through findings_from_sarif ->
the SAME SecurityReport. This module is only the normalizer half of that seam.

Fail-safe: a malformed/partial SARIF yields [] (never raises), mirroring
measure_coverage's measured=False discipline — a broken scan must never
fabricate a blocking finding OR crash the gate.
"""

from __future__ import annotations

from ..models import SecurityFinding, SecurityReport

# SARIF result.level -> our severity scale (SecurityFinding.severity Literal).
# semgrep emits "error" for its blocking rules, so error -> critical keeps the
# SC-5 absolute floor biting. Unknown levels fall back to "high" (conservative).
_LEVEL_TO_SEVERITY = {
    "error": "critical",
    "warning": "high",
    "note": "medium",
    "none": "low",
}


def _first_location_path(res: dict) -> str:
    locs = res.get("locations")
    if not isinstance(locs, list) or not locs:
        return ""
    loc = locs[0]
    if not isinstance(loc, dict):
        return ""
    phys = loc.get("physicalLocation")
    if not isinstance(phys, dict):
        return ""
    art = phys.get("artifactLocation")
    if not isinstance(art, dict):
        return ""
    return str(art.get("uri", "") or "")


def findings_from_sarif(doc: dict) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    if not isinstance(doc, dict):
        return findings
    runs = doc.get("runs")
    if not isinstance(runs, list):
        return findings
    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for res in results:
            if not isinstance(res, dict):
                continue
            severity = _LEVEL_TO_SEVERITY.get(res.get("level", "warning"), "high")
            message = res.get("message")
            detail = message.get("text", "") if isinstance(message, dict) else ""
            findings.append(
                SecurityFinding(
                    severity=severity,
                    rule=str(res.get("ruleId") or "sarif"),
                    detail=str(detail or ""),
                    path=_first_location_path(res),
                )
            )
    return findings


def report_from_sarif(doc: dict) -> SecurityReport:
    findings = findings_from_sarif(doc)
    critical = sum(1 for f in findings if f.severity == "critical")
    return SecurityReport(critical=critical, findings=findings)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sarif.py -q`
Expected: PASS (all parametrized cases + the 3 named tests pass).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/toolchain/sarif.py tests/test_sarif.py
git commit -m "feat(toolchain): SARIF -> SecurityReport normalizer seam (E-30)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `run_integration_checks` activity + coverage tooling dep (end-to-end proof)

**Files:**
- Modify: `pyproject.toml:20` (add `pytest-cov` to the `dev` extra)
- Modify: `src/sdlc/activities.py` (import `detect`; add `_bounded_shell`, `IntegrationChecksInput`, `IntegrationChecks`, `run_integration_checks`)
- Test: `tests/test_integration_checks.py`

**Interfaces:**
- Consumes: `detect` (Task 1), `QAReport` (existing), `measure_coverage`/`CoverageInput` (existing).
- Produces:
  - `@dataclass IntegrationChecksInput` — `worktree: str`, `changed_files: list[str]`, `test_timeout_s: int = 600`, `lint_timeout_s: int = 300`.
  - `@dataclass IntegrationChecks` — `toolchain: str | None`, `qa: QAReport`, `lint_clean: bool`, `lint_detail: str`.
  - `async def run_integration_checks(inp: IntegrationChecksInput) -> IntegrationChecks` (a `@activity.defn`).

- [ ] **Step 1: Add the coverage tooling dev dependency**

Modify `pyproject.toml` line 20:

```toml
dev = ["pytest>=8", "pytest-asyncio>=0.24", "pytest-cov>=5"]
```

Then install it into the environment:

Run: `python -m pip install -e ".[dev]"`
Expected: installs `pytest-cov` and `coverage`. Verify: `python -c "import pytest_cov, coverage; print('ok')"` prints `ok`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_integration_checks.py`:

```python
"""run_integration_checks: the end-to-end coverage seam (E-30, FR-106/FR-108).

Proves the artifact now crosses into the worktree measure_coverage reads."""

import pytest

from sdlc.activities import (
    CoverageInput,
    IntegrationChecksInput,
    measure_coverage,
    run_integration_checks,
)

PYPROJECT = "[project]\nname = 'fixture'\nversion = '0.0.0'\n"
MODULE = "def covered():\n    return 1\n\n\ndef uncovered():\n    return 2\n"
TESTFILE = "from mod import covered\n\n\ndef test_covered():\n    assert covered() == 1\n"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_integration_checks_produces_real_coverage(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "mod.py").write_text(MODULE, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTFILE, encoding="utf-8")

    checks = await run_integration_checks(
        IntegrationChecksInput(worktree=str(tmp_path), changed_files=["mod.py"])
    )

    assert checks.toolchain == "python"
    assert checks.qa.tests_passed is True
    assert (tmp_path / "coverage.xml").is_file(), "coverage.xml must be emitted"

    # The gate reader now finds the artifact and measures a diff-scoped %.
    cov = await measure_coverage(CoverageInput(worktree=str(tmp_path), changed_files=["mod.py"]))
    assert cov.measured is True
    assert 0.0 < (cov.diff_pct or 0.0) < 100.0  # covered + uncovered => partial


@pytest.mark.asyncio
async def test_integration_checks_degrades_without_adapter(tmp_path):
    # No marker file -> no adapter -> caller falls back to the pre-E-30 path.
    checks = await run_integration_checks(
        IntegrationChecksInput(worktree=str(tmp_path), changed_files=[])
    )
    assert checks.toolchain is None
    assert checks.lint_clean is True  # not linted => never blocking
    assert checks.qa.tests_passed is False  # signals "no integration run here"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_integration_checks.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_integration_checks'`.

- [ ] **Step 4: Add the import**

In `src/sdlc/activities.py`, after the existing `from .harness.adapters import HARNESSES, HarnessRequest` line (`:28`), add:

```python
from .toolchain.adapters import detect
```

- [ ] **Step 5: Implement the helper + activity**

Append to `src/sdlc/activities.py` (after `measure_coverage`, before `open_pull_request` / `PROpenInput`):

```python
async def _bounded_shell(cmd: str, cwd: str, timeout_s: int) -> tuple[int, str]:
    """Run a shell command bounded by timeout_s, combining stdout+stderr.
    On timeout: kill and return (-1, message). See run_test_suite's docstring
    for why an unbounded shell command is dangerous in an activity."""
    proc = await asyncio.create_subprocess_shell(
        cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"command timed out after {timeout_s}s (cmd: {cmd!r})"
    return (proc.returncode or 0), out_b.decode(errors="replace")


@dataclass
class IntegrationChecksInput:
    worktree: str
    changed_files: list[str]
    test_timeout_s: int = 600
    lint_timeout_s: int = 300


@dataclass
class IntegrationChecks:
    toolchain: str | None  # ToolchainKind value, or None if undetected
    qa: QAReport
    lint_clean: bool
    lint_detail: str


# pytest usage-error exit code: unrecognized args (e.g. --cov when pytest-cov is
# absent) => 4, distinct from 1 (tests failed). A MISSING coverage plugin must
# degrade coverage to measured=False, never falsely fail the ABSOLUTE
# build_integration_green check — so on a 4 we re-run WITHOUT coverage for the
# honest green signal (FR-108 green-signal invariant).
_PYTEST_USAGE_ERROR = 4


@activity.defn
async def run_integration_checks(inp: IntegrationChecksInput) -> IntegrationChecks:
    """FR-108/ADR-15: resolve the toolchain by marker file and run
    coverage-instrumented tests + lint against the merged integration head.
    Emits coverage.xml into inp.worktree, where measure_coverage reads — the
    FR-106 gap this closes.

    toolchain=None (unrecognized marker) => tests/lint NOT re-run here; the
    workflow falls back to the per-task aggregate + standalone run_lint, exactly
    as before E-30. Never blocks on a language it doesn't know."""
    adapter = detect(inp.worktree)
    if adapter is None:
        return IntegrationChecks(
            toolchain=None,
            qa=QAReport(tests_passed=False, issues=["no toolchain adapter for this worktree"]),
            lint_clean=True,
            lint_detail="no toolchain adapter (not linted)",
        )

    code, out = await _bounded_shell(
        adapter.test_cmd(coverage=True), inp.worktree, inp.test_timeout_s
    )
    if code == _PYTEST_USAGE_ERROR:
        # Coverage tooling unavailable — get the honest green signal without it.
        prefix = (
            "coverage instrumentation unavailable (pytest usage error); coverage left unmeasured\n"
        )
        code, out = await _bounded_shell(
            adapter.test_cmd(coverage=False), inp.worktree, inp.test_timeout_s
        )
        out = prefix + out
    failing = [ln.split(" ")[0] for ln in out.splitlines() if ln.startswith("FAILED")]
    qa = QAReport(
        tests_passed=code == 0,
        failing_tests=failing[:50],
        issues=[] if code == 0 else [out[-2000:]],
    )

    lcode, ldetail = await _bounded_shell(adapter.lint_cmd(), inp.worktree, inp.lint_timeout_s)
    return IntegrationChecks(
        toolchain=adapter.kind.value, qa=qa, lint_clean=lcode == 0, lint_detail=ldetail[-2000:]
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_integration_checks.py -q`
Expected: PASS (2 passed). If the `slow` test is filtered by default config, run it explicitly: `python -m pytest tests/test_integration_checks.py -q -m slow` (the repo's `addopts` is `-q` only; markers are not deselected by default, so both run).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/sdlc/activities.py tests/test_integration_checks.py
git commit -m "feat(activities): run_integration_checks emits coverage.xml in integration (E-30)

Closes the FR-106 gap: coverage-instrumented tests run against the merged
integration head, landing coverage.xml where measure_coverage reads. Adds
pytest-cov dev dep; exit-4 fallback keeps the green signal honest.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire stage 12 to the adapter + register the activity

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (imports `:16-24`; add `INTEG_ACT`; move `measure_coverage` out of analyze; rewrite the merge-evidence block `:1148-1162`)
- Modify: `src/sdlc/worker.py` (import `:28-31` + activities list `:71-72`)
- Test: `tests/test_integration_checks_wiring.py`

**Interfaces:**
- Consumes: `run_integration_checks`, `IntegrationChecksInput`, `IntegrationChecks` (Task 3); existing `measure_coverage`, `_merge_evidence_all_green`, `run_lint`, `security_scan`.
- Produces: no new public symbols — a wiring change. Post-condition: `run_integration_checks` is called in `_pipeline` before `measure_coverage`, which is called before `evaluate_gate`; `build_integration_green` uses the integration run when an adapter is detected.

- [ ] **Step 1: Write the failing wiring tests**

Create `tests/test_integration_checks_wiring.py`:

```python
"""E-30: stage-12 wires the toolchain adapter and the worker registers it."""

import ast
import inspect
import pathlib

FEATURE = pathlib.Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8")


def _pipeline_src() -> str:
    tree = ast.parse(FEATURE)
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_pipeline":
            src = ast.get_source_segment(FEATURE, n)
            assert src is not None
            return src
    raise AssertionError("_pipeline not found")


def test_merge_stage_runs_integration_checks_then_coverage_then_gate():
    src = _pipeline_src()
    r = src.find("run_integration_checks")
    m = src.find("measure_coverage")
    g = src.find("evaluate_gate")
    assert r != -1, "merge stage must call run_integration_checks"
    assert m != -1 and g != -1
    assert r < m, "coverage must be measured AFTER the integration test run"
    assert m < g, "coverage must be measured before the gate is evaluated"


def test_measure_coverage_called_exactly_once_in_pipeline():
    # It moved from analyze to merge — must not be left in both places.
    assert _pipeline_src().count("measure_coverage(") == 1


def test_worker_registers_run_integration_checks():
    from sdlc import worker

    assert "run_integration_checks" in inspect.getsource(worker)


def test_feature_imports_run_integration_checks():
    assert "run_integration_checks" in FEATURE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_integration_checks_wiring.py -q`
Expected: FAIL — `run_integration_checks` not found in `_pipeline`/worker.

- [ ] **Step 3: Add the workflow imports**

In `src/sdlc/workflows/feature.py`, replace the activity import block (`:16-24`):

```python
from ..activities import (
    CodingTaskInput,
    CoverageInput,
    DeployInput,
    DiffInput,
    IntegrationChecks,
    IntegrationChecksInput,
    IntegrationHandle,
    IntegrationInput,
    LintInput,
    MergeInput,
    PROpenInput,
    QAInput,
    SecurityScanInput,
    WorktreeInput,
    create_worktree,
    deploy,
    evaluate_gate,
    get_task_diff,
    measure_coverage,
    merge_into_integration,
    open_pull_request,
    run_coding_task,
    run_integration_checks,
    run_lint,
    run_test_suite,
    security_scan,
    setup_integration_branch,
)
```

- [ ] **Step 4: Add the `INTEG_ACT` timeout constant**

In `src/sdlc/workflows/feature.py`, after the `EXPORT_ACT = ...` block (`:95-96`), add:

```python
# E-30: run_integration_checks runs a real test suite + lint against the merged
# integration head. Generous start_to_close (> the activity's internal test
# 600s + fallback 600s + lint 300s worst case); 2 attempts like the per-task
# test run. It does not heartbeat, so no heartbeat_timeout.
INTEG_ACT = dict(
    start_to_close_timeout=timedelta(minutes=30), retry_policy=RetryPolicy(maximum_attempts=2)
)
```

- [ ] **Step 5: Remove `measure_coverage` from the analyze block**

In `src/sdlc/workflows/feature.py`, delete these lines from the analyze stage (currently `:1114-1118`):

```python
cov: CoverageReport = await workflow.execute_activity(
    measure_coverage,
    CoverageInput(worktree=self._integration_wt, changed_files=integration_diff["files"]),
    **ACT,
)
```

(The analyze-stage record and retains below use only `untraced`, not `cov`, so nothing else in that block breaks.)

- [ ] **Step 6: Rewrite the merge-evidence block**

In `src/sdlc/workflows/feature.py`, replace the block that currently reads (`:1148-1162`):

```python
integration_worktree = self._integration_wt
# Same stack-awareness as the per-task QA command: use the plan's
# own lint_commands rather than assuming a Python toolchain against
# whatever stack the architecture actually chose.
lint_commands = next(
    (t.contract.lint_commands for t in plan.tasks if t.contract and t.contract.lint_commands), None
)
lint_cmd = _contract_shell_cmd(lint_commands, DEFAULT_LINT_CMD)
lint_clean, lint_detail = await workflow.execute_activity(
    run_lint, LintInput(worktree=integration_worktree, lint_cmd=lint_cmd), **ACT
)
security: SecurityReport = await workflow.execute_activity(
    security_scan, SecurityScanInput(worktree=integration_worktree), **ACT
)
all_tests_green = _merge_evidence_all_green(list(done.values()))
```

with:

```python
integration_worktree = self._integration_wt
# E-30/FR-108/ADR-14: run the toolchain adapter (coverage-instrumented
# tests + lint) against the merged integration head — a REAL
# integration-green signal, and the coverage.xml measure_coverage reads.
# No adapter for the built language => degrade to the pre-E-30 path
# (per-task aggregate green + the plan's own lint command).
ichecks: IntegrationChecks = await workflow.execute_activity(
    run_integration_checks,
    IntegrationChecksInput(worktree=integration_worktree, changed_files=integration_diff["files"]),
    **INTEG_ACT,
)
if ichecks.toolchain is not None:
    all_tests_green = ichecks.qa.tests_passed
    lint_clean, lint_detail = ichecks.lint_clean, ichecks.lint_detail
else:
    lint_commands = next(
        (t.contract.lint_commands for t in plan.tasks if t.contract and t.contract.lint_commands),
        None,
    )
    lint_cmd = _contract_shell_cmd(lint_commands, DEFAULT_LINT_CMD)
    lint_clean, lint_detail = await workflow.execute_activity(
        run_lint, LintInput(worktree=integration_worktree, lint_cmd=lint_cmd), **ACT
    )
    all_tests_green = _merge_evidence_all_green(list(done.values()))

# Coverage is read AFTER the integration test run that emits
# coverage.xml (E-30 closes the FR-106 gap: the artifact now lands where
# the seam reads). measured=False stays a no-op advisory pass.
cov: CoverageReport = await workflow.execute_activity(
    measure_coverage,
    CoverageInput(worktree=integration_worktree, changed_files=integration_diff["files"]),
    **ACT,
)

security: SecurityReport = await workflow.execute_activity(
    security_scan, SecurityScanInput(worktree=integration_worktree), **ACT
)
```

- [ ] **Step 7: Register the activity in the worker**

In `src/sdlc/worker.py`, update the `from .activities import (...)` block (`:28-33`) to include `run_integration_checks` in the imported names, e.g. change the line `run_coding_task, run_lint, run_test_suite, security_scan,` (`:31`) to:

```python
(
    run_coding_task,
    run_integration_checks,
    run_lint,
    run_test_suite,
)
(security_scan,)
```

Then in the `activities=[...]` list, change the line `run_coding_task, run_lint, run_test_suite, security_scan,` (`:71`) to:

```python
(
    run_coding_task,
    run_integration_checks,
    run_lint,
    run_test_suite,
)
(security_scan,)
```

- [ ] **Step 8: Run the wiring tests + full suite**

Run: `python -m pytest tests/test_integration_checks_wiring.py -q`
Expected: PASS (4 passed).

Run: `python -m pytest tests/test_merge_gate_wiring.py tests/test_worker_registration.py tests/test_analyst_stage_wiring.py tests/test_factory_purity.py -q`
Expected: PASS (no regression — existing merge/worker/analyst wiring still holds; `measure_coverage` still precedes `evaluate_gate`).

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/workflows/feature.py src/sdlc/worker.py \
        tests/test_integration_checks_wiring.py
git commit -m "feat(workflow): stage-12 grades via ToolchainAdapter; real integration-green (E-30)

run_integration_checks runs test(+coverage)+lint on the merged integration
head; build_integration_green becomes a real run (per-task aggregate is the
no-adapter fallback). measure_coverage moves after it so coverage.xml exists.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Record ADR-15 + update ROADMAP / status docs

**Files:**
- Modify: `ARCHITECTURE.md` (append ADR-15 in §12)
- Modify: `ROADMAP.md` (§6 ADR-15 `[x]`; §9.8 E-30 `[x]` with landed note; FR-108 line in §2; §1 stage 12 / FR-106 coverage note)

**Interfaces:** docs only — no code symbols.

- [ ] **Step 1: Append ADR-15 to `ARCHITECTURE.md` §12**

Locate the ADR list in `ARCHITECTURE.md` §12 (after ADR-14) and add:

```markdown
- **ADR-15 — Language-agnostic toolchain by marker file.** The gate's
  stack-specific verification (build / test / lint / coverage / security) is
  performed by a `ToolchainAdapter` resolved from the produced repository's
  **marker file** (`pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml`),
  structurally identical to the harness adapter (ADR-2/3): a `TOOLCHAINS`
  registry beside `HARNESSES`, normalizing into the gate's canonical evidence
  formats — **Cobertura XML** for coverage and a **SARIF-shaped
  `SecurityReport`** for the absolute security floor. The gate readers
  (`measure_coverage`, `security_no_critical`) are unchanged and
  language-neutral; adding a language changes neither workflow nor gate code
  (cf. ADR-2/FR-203). Detection resolves by **what was built** (marker file),
  not by the contract's claimed stack — a marker/claim mismatch is itself a
  signal (the toolchain analogue of the criterion→test traceability gap, and
  the anti-cheat stance E-31 extends).
```

- [ ] **Step 2: Mark ADR-15 in `ROADMAP.md` §6**

After the `ADR-14` line in `ROADMAP.md §6`, add:

```markdown
- [x] **ADR-15** Language-agnostic toolchain by marker file (`src/sdlc/toolchain/`) — Python reference adapter end-to-end; Go/TS/Rust are E-30a/b/c.
```

- [ ] **Step 3: Mark E-30 done in `ROADMAP.md` §9.8**

Change the `- [ ] **E-30 (new scope; ADR-15)** ...` bullet's checkbox to `- [x]` and append a landed note sentence:

```markdown
  *Landed:* PRD FR-108 + ADR-15; `src/sdlc/toolchain/` (adapter + Python
  reference + SARIF seam) and the `run_integration_checks` activity close the
  FR-106 gap (coverage.xml now crosses into the integration worktree) and make
  `build_integration_green` a real integration run. Spec
  `docs/superpowers/specs/2026-07-22-toolchain-adapter-coverage-seam-design.md`,
  plan `docs/superpowers/plans/2026-07-22-toolchain-adapter-coverage-seam.md`.
  Go/TS/Rust adapters (E-30a/b/c) and the held-out oracle (E-31) remain open.
```

- [ ] **Step 4: Update the FR-106 / stage-12 coverage note in `ROADMAP.md` §1**

In the §1 `12 · quality_gate` bullet, update the coverage clause to note the gap is closed: replace the parenthetical explaining that `coverage.xml` "never lands where `measure_coverage` looks" with a note that E-30's `run_integration_checks` now runs coverage-instrumented tests in the integration worktree, so the artifact lands where the seam reads (Python adapter; other languages via E-30a/b/c).

Also add an FR-108 line under §2 Pipeline (FR-100), after FR-107:

```markdown
- [x] **FR-108 (new scope; ADR-15)** language-agnostic toolchain adapter — `ToolchainAdapter`/`TOOLCHAINS` resolved by marker file, canonical Cobertura + SARIF, Python reference end-to-end; `run_integration_checks` closes the FR-106 coverage-crossing gap. Go/TS/Rust = E-30a/b/c.
```

- [ ] **Step 5: Verify no doc build/link breakage & full suite green**

Run: `python -m pytest -q`
Expected: PASS (whole suite green; the E-30 tests included).

- [ ] **Step 6: Commit**

```bash
git add ARCHITECTURE.md ROADMAP.md
git commit -m "docs: record ADR-15, mark E-30/FR-108 landed (E-30)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- Spec §2 ADR-15 → Task 5 Step 1/2. ✓
- Spec §3 toolchain package (interface, PythonToolchain, detect, registry) → Task 1. ✓
- Spec §4.1 Cobertura coverage, reader unchanged → Task 3 (adapter emits `coverage.xml`; `measure_coverage` untouched) + Task 4 (reordered so artifact exists). ✓
- Spec §4.2 SARIF seam, regex default kept → Task 2 (normalizer); regex `security_scan` deliberately untouched (semgrep opt-in path is a documented follow-on, not this increment). ✓
- Spec §5 workflow wiring (run in integration, `build_integration_green` real, no-adapter fallback, coverage after run) → Task 4. ✓
- Spec §5 green-signal-not-corrupted-by-coverage-tooling invariant → Task 3 (exit-4 fallback). ✓
- Spec §6 tests (adapter units, SARIF, e2e coverage seam, degradation) → Tasks 1/2/3/4. ✓
- Spec §7 out-of-scope (E-30a/b/c, E-31, real semgrep, per-task QA) → not implemented, noted in Task 5 landed note. ✓
- PRD FR-108 already written → committed in Task 1. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". Every code step shows full code. Task 5 Step 4 describes a prose edit to an existing note but names the exact clause and the replacement intent; acceptable for a doc-copy edit (the target text is the `coverage via deterministic Cobertura seam (...)` parenthetical in §1). ✓

**3. Type consistency:**
- `ToolchainKind.PYTHON.value == "python"` — used in Task 3 (`adapter.kind.value`) and asserted in Task 3 test (`checks.toolchain == "python"`). ✓
- `test_cmd(coverage: bool = True)` defined Task 1, called `test_cmd(coverage=True/False)` Task 3. ✓
- `IntegrationChecks(toolchain, qa, lint_clean, lint_detail)` defined Task 3, consumed Task 4 (`ichecks.toolchain`, `.qa.tests_passed`, `.lint_clean`, `.lint_detail`). ✓
- `IntegrationChecksInput(worktree, changed_files, ...)` defined Task 3, constructed Task 4. ✓
- `detect(worktree) -> ToolchainAdapter | None` defined Task 1, used Task 3. ✓
- `findings_from_sarif` / `report_from_sarif` defined Task 2 — consumed only by the future opt-in semgrep path (not wired this increment); tests in Task 2 cover them directly. ✓
