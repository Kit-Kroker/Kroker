# E-31 Tier-A Held-Out Oracle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a benchmark-only held-out oracle that runs a hidden test suite against produced code through the E-30 `ToolchainAdapter`, grading it as fraction-passing — the first objective (Tier-A) benchmark grade.

**Architecture:** A new `grade_oracle` Temporal activity is invoked by `BenchmarkWorkflow` strictly *after* each `FeatureWorkflow` child, so the oracle never enters the run's context. It checks out the produced integration head into a throwaway detached worktree, copies the case's `oracle/` suite in uncommitted, runs it via a new `ToolchainAdapter.oracle_test_cmd` emitting JUnit XML, and parses fraction-passing. Two integrity checks ship alongside: an oracle-is-held-out assertion (oracle paths absent from the produced diff) and a manifest-vs-marker language-mismatch signal. The grade records as a `stage="oracle"` `BenchmarkRecord`, becoming its own report row.

**Tech Stack:** Python 3.14, Temporal (`temporalio`), Pydantic, `defusedxml`, `httpx` (ASGI test transport for the reference oracle), pytest + pytest-asyncio.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-23-held-out-oracle-design.md`. Every task implements part of it.
- **Determinism (ADR-13):** workflow code never touches subprocess/filesystem/network. All git/shell/FS I/O lives in the `grade_oracle` activity; `BenchmarkWorkflow` passes only serializable args and builds records with `workflow.now()` timestamps.
- **Fail-safe (mirrors `measure_coverage`/`judge_artifact`):** `grade_oracle` never raises past its boundary. Every failure mode returns `OracleGrade(score=None, ...)` with a `detail` string. A broken grader can never fail a benchmark cell.
- **Grade what was built:** language detection resolves by marker file (`detect()`), never the contract's claimed stack; a manifest-vs-marker mismatch is a recorded signal, not a crash.
- **Reference oracle language:** Python. The oracle drives an **ASGI** app object importable as `app:app`.
- **Additive:** oracle grading is gated on `CaseSpec.language` being set. The two existing oracle-less cases (`add-login`, `cat-cafe`) must run through `BenchmarkWorkflow` unchanged.
- **Reuse, don't duplicate:** reuse `sdlc.activities._git` and `sdlc.activities._bounded_shell`; reuse `sdlc.toolchain.adapters.detect`/`TOOLCHAINS`; do not reimplement git or shell plumbing.
- Run the full test suite with `python -m pytest -q` from the repo root (`D:\own\Kroker`). `slow`-marked tests build/exec subprocesses.

---

### Task 1: `ToolchainAdapter.oracle_test_cmd` — the JUnit-emitting run command

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py`
- Test: `tests/test_toolchain_adapters.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ToolchainAdapter.oracle_test_cmd(self, oracle_path: str, report_out: str) -> str` (abstract); `PythonToolchain.oracle_test_cmd` concrete. Runs *only* the tests under `oracle_path`, emitting a JUnit XML report at `report_out`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_toolchain_adapters.py`:

```python
def test_python_oracle_test_cmd_targets_path_and_emits_junit():
    cmd = PythonToolchain().oracle_test_cmd("oracle", "oracle-report.xml")
    assert cmd.startswith("pytest oracle")
    assert "--junitxml=oracle-report.xml" in cmd
    # never pollute the produced repo with a pytest cache
    assert "-p no:cacheprovider" in cmd
    # the oracle run is NOT coverage-instrumented (that is test_cmd's job)
    assert "--cov" not in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_toolchain_adapters.py::test_python_oracle_test_cmd_targets_path_and_emits_junit -v`
Expected: FAIL — `AttributeError: 'PythonToolchain' object has no attribute 'oracle_test_cmd'`.

- [ ] **Step 3: Add the abstract method and Python implementation**

In `src/sdlc/toolchain/adapters.py`, add the abstractmethod to `ToolchainAdapter` (after `lint_cmd`):

```python
    @abstractmethod
    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        """Run ONLY the tests under oracle_path (a path relative to the
        worktree root), emitting a JUnit XML report at report_out. The
        held-out oracle grader (benchmarks/oracle.py) reads tests/failures/
        errors/skipped from that report. Canonical JUnit XML keeps the grade
        language-agnostic, exactly as Cobertura does for coverage."""
```

And to `PythonToolchain` (after `lint_cmd`):

```python
    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        # -p no:cacheprovider: never write .pytest_cache into the produced
        # repo (keeps the throwaway worktree clean). --junitxml lands the
        # canonical report the grader parses.
        return (f"pytest {oracle_path} -q "
                f"--junitxml={report_out} -p no:cacheprovider")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_toolchain_adapters.py -v`
Expected: PASS (all, including the new test).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/toolchain/adapters.py tests/test_toolchain_adapters.py
git commit -m "feat(toolchain): oracle_test_cmd emits canonical JUnit XML (E-31)"
```

---

### Task 2: Model additions — `BenchmarkScope.ORACLE`, `judge="oracle"`, `CaseSpec.language`

**Files:**
- Modify: `src/sdlc/benchmarks/models.py`
- Test: `tests/test_benchmark_models.py`

**Interfaces:**
- Produces: `BenchmarkScope.ORACLE == "oracle"`; `QualityScore.judge` accepts `"oracle"`; `CaseSpec.language: str | None = None`.

- [ ] **Step 1: Write the failing tests**

Add to the existing `tests/test_benchmark_models.py`. It already imports `BenchmarkScope`, `CaseSpec`, `QualityScore`, and `HarnessKind` — reuse those imports; do not re-add them. Append these tests:

```python
def test_oracle_scope_exists():
    assert BenchmarkScope.ORACLE.value == "oracle"


def test_quality_score_accepts_oracle_judge():
    q = QualityScore(score=0.5, judge="oracle")
    assert q.judge == "oracle"


def test_case_spec_language_defaults_none_and_accepts_value():
    base = dict(case_id="c", idea_summary="s",
                harnesses=[HarnessKind.OPENCODE],
                models=["zai-coding-plan/glm-5.2"],
                judge_model="openai/gpt-5.2")
    assert CaseSpec(**base).language is None
    assert CaseSpec(**base, language="python").language == "python"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_benchmark_models.py -v`
Expected: FAIL — `AttributeError: ORACLE` / validation error on `judge="oracle"` / `language`.

- [ ] **Step 3: Implement the model changes**

In `src/sdlc/benchmarks/models.py`:

Add to `BenchmarkScope`:

```python
class BenchmarkScope(str, Enum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"
    ORACLE = "oracle"
```

Widen `QualityScore.judge`:

```python
    judge: Literal["contract", "llm_judge", "human_override", "error", "oracle"]
```

Add the `language` field to `CaseSpec` (next to `research_enabled`):

```python
    # E-31: declares the held-out oracle's language. Set => this case opts
    # into oracle grading (BenchmarkWorkflow runs grade_oracle after the
    # child). Also the value the manifest-vs-marker mismatch signal compares
    # against. None => no oracle grade for this case.
    language: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_benchmark_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/models.py tests/test_benchmark_models.py
git commit -m "feat(benchmark): ORACLE scope, oracle judge, CaseSpec.language (E-31)"
```

---

### Task 3: Pure grading logic — `grade_from_junit`, `held_out_ok`, `language_match`

**Files:**
- Create: `src/sdlc/benchmarks/oracle.py`
- Test: `tests/test_oracle.py`

**Interfaces:**
- Consumes: nothing new (pure functions; `defusedxml`).
- Produces:
  - `grade_from_junit(xml_text: str) -> tuple[float | None, int, int, str]` → `(score, passed, graded_total, detail)`. `score = passed / graded_total`; `graded_total = tests - skipped`; `None` on unparseable/empty/zero-gradable.
  - `held_out_ok(changed_files: list[str], oracle_dirname: str = "oracle") -> bool` → False iff any produced-diff path is the oracle dir or under it.
  - `language_match(manifest: str, detected: str | None) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oracle.py`:

```python
"""Pure grading logic for the held-out oracle (E-31)."""
from sdlc.benchmarks.oracle import (
    grade_from_junit, held_out_ok, language_match,
)

JUNIT_MIXED = (
    '<testsuites><testsuite tests="4" failures="1" errors="1" skipped="0">'
    '<testcase name="a"/><testcase name="b"><failure/></testcase>'
    '<testcase name="c"><error/></testcase><testcase name="d"/>'
    '</testsuite></testsuites>'
)
JUNIT_ROOT_SUITE = (
    '<testsuite tests="2" failures="0" errors="0" skipped="0">'
    '<testcase name="a"/><testcase name="b"/></testsuite>'
)
JUNIT_WITH_SKIP = (
    '<testsuite tests="3" failures="0" errors="0" skipped="1">'
    '<testcase name="a"/><testcase name="b"/>'
    '<testcase name="c"><skipped/></testcase></testsuite>'
)


def test_grade_mixed_pass_fail_error():
    score, passed, total, _ = grade_from_junit(JUNIT_MIXED)
    assert (passed, total) == (2, 4)
    assert score == 0.5


def test_grade_all_pass_is_one():
    score, passed, total, _ = grade_from_junit(JUNIT_ROOT_SUITE)
    assert (score, passed, total) == (1.0, 2, 2)


def test_grade_excludes_skipped_from_denominator():
    score, passed, total, _ = grade_from_junit(JUNIT_WITH_SKIP)
    assert (passed, total) == (2, 2)   # skipped test dropped from both
    assert score == 1.0


def test_grade_malformed_returns_none():
    score, passed, total, detail = grade_from_junit("<not-xml")
    assert score is None and (passed, total) == (0, 0)
    assert "unparseable" in detail


def test_grade_empty_returns_none():
    assert grade_from_junit("")[0] is None


def test_grade_zero_gradable_returns_none():
    xml = '<testsuite tests="0" failures="0" errors="0" skipped="0"/>'
    score, _, _, detail = grade_from_junit(xml)
    assert score is None and "no gradable" in detail


def test_held_out_ok_true_when_no_oracle_paths():
    assert held_out_ok(["app.py", "src/store.py"]) is True


def test_held_out_ok_false_when_oracle_path_in_diff():
    assert held_out_ok(["app.py", "oracle/test_crud.py"]) is False
    assert held_out_ok(["oracle"]) is False


def test_language_match():
    assert language_match("python", "python") is True
    assert language_match("python", "typescript") is False
    assert language_match("python", None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_oracle.py -v`
Expected: FAIL — `ModuleNotFoundError: sdlc.benchmarks.oracle`.

- [ ] **Step 3: Implement the pure functions**

Create `src/sdlc/benchmarks/oracle.py` with ONLY the pure logic for now (the activity is Task 4):

```python
"""Held-out oracle grade (E-31): run a hidden suite against produced code
through the E-30 ToolchainAdapter, graded as fraction passing.

This module holds the pure grading logic (grade_from_junit / held_out_ok /
language_match) and the grade_oracle Temporal activity (Task 4). The pure
functions never do I/O so they unit-test without a Temporal environment or a
git repo; the activity confines all git/shell/FS work.
"""
from __future__ import annotations

import defusedxml.ElementTree as DET


def grade_from_junit(xml_text: str) -> tuple[float | None, int, int, str]:
    """Parse a JUnit XML report into (score, passed, graded_total, detail).

    graded_total = tests - skipped (a skip is neither a pass nor a fail, so
    it is dropped from the denominator). passed = graded_total - failures -
    errors, clamped to [0, graded_total]. Returns score=None (excluded from
    the composite, never a fabricated pass/fail) when the report is empty,
    unparseable, or has zero gradable tests -- mirroring measure_coverage's
    measured=False discipline. Parsed with defusedxml: the report is produced
    by untrusted code in the integration worktree."""
    if not xml_text.strip():
        return None, 0, 0, "no junit report"
    try:
        root = DET.fromstring(xml_text)
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        tests = fails = errs = skips = 0
        for s in suites:
            tests += int(s.get("tests", "0") or "0")
            fails += int(s.get("failures", "0") or "0")
            errs += int(s.get("errors", "0") or "0")
            skips += int(s.get("skipped", "0") or "0")
    except Exception:
        return None, 0, 0, "junit report unparseable"
    graded = tests - skips
    if graded <= 0:
        return None, 0, 0, "oracle produced no gradable tests"
    passed = max(0, min(graded, graded - fails - errs))
    return passed / graded, passed, graded, f"{passed}/{graded} oracle tests passed"


def held_out_ok(changed_files: list[str], oracle_dirname: str = "oracle") -> bool:
    """False iff the produced diff authored anything at/under the oracle dir.

    The oracle is copied in UNCOMMITTED at grade time, so any oracle path in
    the produced diff means the model itself wrote there -- a held-out breach
    the record must surface loudly."""
    prefix = oracle_dirname + "/"
    return not any(f == oracle_dirname or f.startswith(prefix)
                   for f in changed_files)


def language_match(manifest: str, detected: str | None) -> bool:
    """Manifest-declared language vs the marker-detected one (ADR-15)."""
    return detected == manifest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_oracle.py -v`
Expected: PASS (all 10).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/oracle.py tests/test_oracle.py
git commit -m "feat(benchmark): pure oracle grading logic (junit/held-out/lang) (E-31)"
```

---

### Task 4: `grade_oracle` activity — checkout, run, parse, clean up

**Files:**
- Modify: `src/sdlc/benchmarks/oracle.py`
- Test: `tests/test_grade_oracle.py`

**Interfaces:**
- Consumes: `grade_from_junit`/`held_out_ok`/`language_match` (Task 3); `sdlc.activities._git`, `sdlc.activities._bounded_shell`; `sdlc.toolchain.adapters.detect`, `TOOLCHAINS`, `ToolchainKind`.
- Produces:
  - `OracleInput` dataclass: `case_id, repo_url, run_id, language, base_branch="main", test_timeout_s=600`.
  - `OracleGrade` dataclass: `score, passed, total, language_manifest, language_detected, language_match, held_out_ok, detail`.
  - `_cases_dir() -> pathlib.Path` (honors `SDLC_CASES_ROOT`, defaults to `<repo>/benchmarks/cases`).
  - `grade_oracle(inp: OracleInput) -> OracleGrade` (`@activity.defn`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_grade_oracle.py`:

```python
"""grade_oracle end-to-end: a hidden suite grades produced code through the
adapter (E-31). This is the proof the increment exists to deliver."""
import subprocess
import textwrap
from pathlib import Path

import pytest

from sdlc.benchmarks.oracle import OracleInput, grade_oracle

# A pure-stdlib ASGI app: importable with zero extra deps, drivable by
# httpx.ASGITransport. Returns 200 for any GET -- enough for a 1-pass/1-fail
# oracle.
FIXTURE_APP = textwrap.dedent('''
    async def app(scope, receive, send):
        assert scope["type"] == "http"
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"ok"})
''')

ORACLE_CONFTEST = textwrap.dedent('''
    import os, sys
    import httpx, pytest_asyncio
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    @pytest_asyncio.fixture
    async def client():
        import app as m
        transport = httpx.ASGITransport(app=m.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as c:
            yield c
''')

ORACLE_TEST = textwrap.dedent('''
    import pytest

    @pytest.mark.asyncio
    async def test_ok(client):
        r = await client.get("/")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_fail(client):
        r = await client.get("/")
        assert r.status_code == 404   # deliberately wrong -> one failure
''')


def _git(args, cwd):
    subprocess.run(["git", "-c", "safe.directory=*", *args], cwd=cwd,
                   check=True, capture_output=True)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_grade_oracle_grades_produced_code(tmp_path):
    # 1. a repo with a main commit, then produced code on the integration branch
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    # 2. a held-out oracle under a temp cases root
    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    monkeypatch_env = {"SDLC_CASES_ROOT": str(cases)}

    import os
    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ.update(monkeypatch_env)
    try:
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_id,
            language="python", base_branch="main"))
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old

    assert grade.total == 2
    assert grade.passed == 1
    assert grade.score == 0.5
    assert grade.held_out_ok is True
    assert grade.language_match is True
    assert grade.language_detected == "python"
    # throwaway worktree cleaned up: only the original repo worktree remains
    wt = subprocess.run(["git", "worktree", "list"], cwd=repo,
                        capture_output=True, text=True).stdout
    assert "oracle-" not in wt


@pytest.mark.asyncio
async def test_grade_oracle_missing_branch_returns_none(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "f").write_text("x")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    cases = tmp_path / "cases"
    (cases / "case" / "oracle").mkdir(parents=True)
    (cases / "case" / "oracle" / "test_x.py").write_text("def test_x():\n    assert True\n")

    import os
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo),
            run_id="never/ran#h#m", language="python"))
    finally:
        os.environ.pop("SDLC_CASES_ROOT", None)
    assert grade.score is None
    assert "no produced code" in grade.detail


@pytest.mark.asyncio
async def test_grade_oracle_unknown_language_returns_none(tmp_path):
    cases = tmp_path / "cases"
    (cases / "case" / "oracle").mkdir(parents=True)
    import os
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(tmp_path), run_id="r#h#m",
            language="cobol"))
    finally:
        os.environ.pop("SDLC_CASES_ROOT", None)
    assert grade.score is None
    assert "no toolchain adapter" in grade.detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_grade_oracle.py -v`
Expected: FAIL — `ImportError: cannot import name 'OracleInput' / 'grade_oracle'`.

- [ ] **Step 3: Implement the dataclasses and the activity**

Append to `src/sdlc/benchmarks/oracle.py`:

```python
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

from ..activities import _bounded_shell, _git
from ..toolchain.adapters import TOOLCHAINS, ToolchainKind, detect


@dataclass
class OracleInput:
    case_id: str
    repo_url: str
    run_id: str            # child workflow id -> sdlc/<run_id>/integration
    language: str          # manifest-declared (CaseSpec.language)
    base_branch: str = "main"
    test_timeout_s: int = 600


@dataclass
class OracleGrade:
    score: float | None
    passed: int
    total: int
    language_manifest: str
    language_detected: str | None
    language_match: bool
    held_out_ok: bool
    detail: str


def _cases_dir() -> Path:
    """Root holding benchmarks/cases/<case>/oracle/. Honors SDLC_CASES_ROOT
    (read at call time) so tests point it at a temp dir, mirroring
    recorder._root / activities._worktrees_root."""
    return Path(os.environ.get(
        "SDLC_CASES_ROOT",
        str(Path(__file__).resolve().parents[3] / "benchmarks" / "cases")))


def _grade(score, passed, total, lang, detected, held, detail) -> OracleGrade:
    return OracleGrade(
        score=score, passed=passed, total=total, language_manifest=lang,
        language_detected=detected, language_match=language_match(lang, detected),
        held_out_ok=held, detail=detail)


@activity.defn
async def grade_oracle(inp: OracleInput) -> OracleGrade:
    """Run the case's held-out oracle against produced code through the
    E-30 adapter. Held out by construction: invoked only by BenchmarkWorkflow,
    strictly AFTER the child that produced the code. Fail-safe -- every failure
    returns score=None with a detail; never raises past this boundary."""
    lang = inp.language
    oracle_src = _cases_dir() / inp.case_id / "oracle"
    if not oracle_src.is_dir():
        return _grade(None, 0, 0, lang, None, True, "no oracle dir for case")
    try:
        adapter = TOOLCHAINS[ToolchainKind(lang)]
    except (ValueError, KeyError):
        return _grade(None, 0, 0, lang, None, True,
                      f"no toolchain adapter for {lang!r}")

    parent = tempfile.mkdtemp(prefix="oracle-")
    wt = os.path.join(parent, "wt")
    branch = f"sdlc/{inp.run_id}/integration"
    try:
        # Detached checkout of the produced head: --detach sidesteps git's
        # "already checked out" if the run's integration worktree still exists.
        add = _git(["worktree", "add", "--detach", wt, branch], inp.repo_url)
        if add.returncode != 0:
            return _grade(None, 0, 0, lang, None, True,
                          "no produced code (integration branch absent)")

        det = detect(wt)
        detected = det.kind.value if det else None

        diff = _git(["diff", "--name-only", f"{inp.base_branch}...HEAD"], wt)
        changed = [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]
        held = held_out_ok(changed)

        shutil.copytree(oracle_src, os.path.join(wt, "oracle"))
        report = os.path.join(wt, "oracle-report.xml")
        await _bounded_shell(adapter.oracle_test_cmd("oracle", report),
                             wt, inp.test_timeout_s)
        try:
            xml_text = Path(report).read_text(encoding="utf-8")
        except OSError:
            xml_text = ""
        score, passed, total, detail = grade_from_junit(xml_text)
        return _grade(score, passed, total, lang, detected, held, detail)
    except Exception as e:  # fail-safe: a broken grader never fails a cell
        return _grade(None, 0, 0, lang, None, True, f"grade_oracle error: {e}")
    finally:
        _git(["worktree", "remove", "--force", wt], inp.repo_url)
        shutil.rmtree(parent, ignore_errors=True)
```

Note: the `import` block goes at the TOP of the file with the existing imports — move `import defusedxml.ElementTree as DET` and these together into one import section; do not leave imports mid-file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_grade_oracle.py -v`
Expected: PASS (3 tests; the first is `slow` — runs git + a pytest subprocess).

- [ ] **Step 5: Run the pure tests too (regression)**

Run: `python -m pytest tests/test_oracle.py -v`
Expected: PASS (imports still resolve after the append).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/oracle.py tests/test_grade_oracle.py
git commit -m "feat(benchmark): grade_oracle activity runs held-out suite (E-31)"
```

---

### Task 5: Wire `grade_oracle` into `BenchmarkWorkflow` + register the activity

**Files:**
- Modify: `src/sdlc/benchmarks/workflow.py`
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_benchmark_workflow.py`

**Interfaces:**
- Consumes: `grade_oracle`, `OracleInput`, `OracleGrade` (Task 4); `record_benchmark`; benchmark models.
- Produces: module-level pure helper `_oracle_record(cell: BenchmarkCell, grade: OracleGrade, bench_run_id: str, run_id: str, started: datetime, ended: datetime) -> BenchmarkRecord`. `BenchmarkWorkflow.run` calls `grade_oracle` after each child when `spec.language` is set.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_benchmark_workflow.py`:

```python
from datetime import datetime, timezone

from sdlc.benchmarks.models import BenchmarkCell, BenchmarkScope
from sdlc.benchmarks.oracle import OracleGrade
from sdlc.benchmarks.workflow import _oracle_record


def _grade(**kw):
    base = dict(score=0.5, passed=1, total=2, language_manifest="python",
                language_detected="python", language_match=True,
                held_out_ok=True, detail="1/2")
    base.update(kw)
    return OracleGrade(**base)


def _cell():
    return BenchmarkCell(case_id="todo-api", harness=HarnessKind.OPENCODE,
                         model="zai-coding-plan/glm-5.2")


def _rec(grade):
    t0 = datetime(2026, 7, 23, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=timezone.utc)
    return _oracle_record(_cell(), grade, "b1", "b1/todo-api#opencode#m", t0, t1)


def test_oracle_record_shape():
    r = _rec(_grade())
    assert r.scope is BenchmarkScope.ORACLE
    assert r.stage == "oracle" and r.role == "oracle"
    assert r.quality.judge == "oracle" and r.quality.score == 0.5
    assert r.quality.components["passed"] == 1.0
    assert r.quality.components["total"] == 2.0
    assert r.harness is HarnessKind.OPENCODE
    assert r.error is None


def test_oracle_record_flags_held_out_breach():
    r = _rec(_grade(held_out_ok=False))
    assert r.error is not None and "held-out" in r.error


def test_oracle_record_flags_language_mismatch():
    r = _rec(_grade(language_match=False, language_detected="typescript"))
    assert r.error is not None and "mismatch" in r.error


def test_oracle_record_none_score_is_fail():
    from sdlc.benchmarks.models import BenchmarkOutcome
    r = _rec(_grade(score=None, passed=0))
    assert r.outcome is BenchmarkOutcome.FAIL
    assert r.quality.score is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_benchmark_workflow.py -k oracle_record -v`
Expected: FAIL — `ImportError: cannot import name '_oracle_record'`.

- [ ] **Step 3: Implement `_oracle_record` and wire the workflow**

In `src/sdlc/benchmarks/workflow.py`, extend the imports inside the existing `with workflow.unsafe.imports_passed_through():` block:

```python
    from .models import (BenchmarkCell, BenchmarkOutcome, BenchmarkRecord,
                         BenchmarkScope, CaseSpec, QualityScore, SpeedBag)
    from .oracle import OracleGrade, OracleInput, grade_oracle
    from .recorder import record_benchmark
```

(Keep the existing `from .models import CaseSpec` — merge it into the line above rather than duplicating; also keep `judge`, `matrix`, `report` imports as they are. Add `from datetime import datetime` at the top with the existing `from datetime import timedelta` — combine into `from datetime import datetime, timedelta`.)

Add the timing config beside `CHILD_ACT`/`RECORD_ACT`:

```python
ORACLE_ACT = dict(start_to_close_timeout=timedelta(minutes=20),
                  retry_policy=RetryPolicy(maximum_attempts=1))
```

Add the module-level pure helper (below `_cell_config`):

```python
def _oracle_record(base_cell: BenchmarkCell, grade: OracleGrade,
                   bench_run_id: str, run_id: str,
                   started: datetime, ended: datetime) -> BenchmarkRecord:
    """Build the stage='oracle' record from a grade. An integrity breach
    (held-out or language mismatch) sets .error so it surfaces in the report's
    failure section -- loud, never silent."""
    err = None
    if not grade.held_out_ok:
        err = "held-out breach: oracle path in produced diff"
    elif not grade.language_match:
        err = (f"language mismatch: manifest={grade.language_manifest} "
               f"detected={grade.language_detected}")
    outcome = (BenchmarkOutcome.PASS if (grade.score or 0.0) >= 1.0
               else BenchmarkOutcome.FAIL)
    return BenchmarkRecord(
        run_id=run_id, bench_run_id=bench_run_id, case_id=base_cell.case_id,
        scope=BenchmarkScope.ORACLE, stage="oracle", role="oracle",
        harness=base_cell.harness, model=base_cell.model,
        quality=QualityScore(
            score=grade.score, judge="oracle",
            components={"passed": float(grade.passed),
                        "total": float(grade.total),
                        "held_out_ok": float(grade.held_out_ok),
                        "language_match": float(grade.language_match)}),
        speed=SpeedBag(wall_clock_s=(ended - started).total_seconds(),
                       started_at=started, ended_at=ended),
        outcome=outcome, error=err)
```

In `BenchmarkWorkflow.run`, inside `for cell in cells:`, AFTER the `try/except` child block (so grading runs whether the child passed OR was rejected), add:

```python
            if spec.language:
                started = workflow.now()
                grade = await workflow.execute_activity(
                    grade_oracle,
                    OracleInput(case_id=spec.case_id,
                                repo_url=spec.repo_url or "",
                                run_id=child_id, language=spec.language,
                                base_branch=idea.base_branch),
                    **ORACLE_ACT)
                await workflow.execute_activity(
                    record_benchmark,
                    _oracle_record(cell, grade, bench_run_id, child_id,
                                   started, workflow.now()),
                    **RECORD_ACT)
```

In `src/sdlc/worker.py`, import and register the activity:

```python
from .benchmarks.oracle import grade_oracle
```

and add `grade_oracle` to the `activities=[...]` list (next to `record_benchmark, judge_artifact`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_benchmark_workflow.py -v`
Expected: PASS (existing + 4 new oracle_record tests).

- [ ] **Step 5: Verify the worker still imports cleanly**

Run: `python -c "import sdlc.worker"`
Expected: no output, exit 0 (registration import resolves; `grade_oracle` is a valid activity).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/workflow.py src/sdlc/worker.py tests/test_benchmark_workflow.py
git commit -m "feat(benchmark): run+record grade_oracle after each cell (E-31)"
```

---

### Task 6: Reference oracle — `todo-api-greenfield` case + hidden suite

**Files:**
- Modify: `benchmarks/cases/todo-api-greenfield/case.yaml`
- Create: `benchmarks/cases/todo-api-greenfield/oracle/conftest.py`
- Create: `benchmarks/cases/todo-api-greenfield/oracle/test_crud.py`
- Test: `tests/test_reference_oracle.py`

**Interfaces:**
- Consumes: `_cases_dir()` resolves `benchmarks/cases/todo-api-greenfield/oracle/` in production (no env override).
- Produces: a Python/ASGI held-out oracle for the CRUD contract; `CaseSpec.language: python` on the case.

- [ ] **Step 1: Amend the case manifest and description**

Edit `benchmarks/cases/todo-api-greenfield/case.yaml`. Add `language: python` (top-level, after `mode:`), and extend the `description` block with the frozen interface contract so the oracle can drive the produced app:

Add this paragraph to the end of the `description:` block:

```
  Implement in Python. Expose an ASGI application object importable as
  `app:app` (module `app.py` at the repo root, attribute named `app`)
  serving the CRUD routes over HTTP:
    POST   /todos      {title}       -> 201 {id, title, done}
    GET    /todos                    -> 200 [ ... ]
    GET    /todos/{id}               -> 200 {id, title, done} | 404
    PUT    /todos/{id}  {title,done} -> 200 {id, title, done} | 404
    DELETE /todos/{id}               -> 204 ; subsequent GET -> 404
  Storage and framework are your choice, as long as the app is ASGI and
  importable as `app:app`.
```

And add the field:

```yaml
language: python
```

- [ ] **Step 2: Create the held-out oracle conftest**

Create `benchmarks/cases/todo-api-greenfield/oracle/conftest.py`:

```python
"""Held-out oracle fixtures for todo-api-greenfield (E-31). Never seen by the
run: copied into the produced worktree only at grade time. Drives the frozen
ASGI contract (app:app) via httpx, so it stays framework-agnostic within ASGI."""
import os
import sys

import httpx
import pytest_asyncio

# The produced repo root is the parent of this oracle/ dir once copied in.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest_asyncio.fixture
async def client():
    import app as produced          # contract: module app.py exposes `app`
    transport = httpx.ASGITransport(app=produced.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://testserver") as c:
        yield c
```

- [ ] **Step 3: Create the held-out CRUD oracle**

Create `benchmarks/cases/todo-api-greenfield/oracle/test_crud.py`:

```python
"""Black-box CRUD oracle: exercises the frozen HTTP contract, not internals.
Fraction passing is the objective (Tier-A) grade."""
import pytest


@pytest.mark.asyncio
async def test_create_returns_id_and_echoes_title(client):
    r = await client.post("/todos", json={"title": "buy milk"})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "buy milk" and "id" in body


@pytest.mark.asyncio
async def test_list_contains_created_item(client):
    await client.post("/todos", json={"title": "a"})
    r = await client.get("/todos")
    assert r.status_code == 200
    assert any(t["title"] == "a" for t in r.json())


@pytest.mark.asyncio
async def test_get_by_id_roundtrips(client):
    created = (await client.post("/todos", json={"title": "x"})).json()
    r = await client.get(f"/todos/{created['id']}")
    assert r.status_code == 200 and r.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_update_reflects_changes(client):
    created = (await client.post("/todos", json={"title": "x"})).json()
    r = await client.put(f"/todos/{created['id']}",
                         json={"title": "y", "done": True})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "y" and body["done"] is True


@pytest.mark.asyncio
async def test_delete_then_get_is_404(client):
    created = (await client.post("/todos", json={"title": "x"})).json()
    assert (await client.delete(f"/todos/{created['id']}")).status_code == 204
    assert (await client.get(f"/todos/{created['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_get_missing_is_404(client):
    r = await client.get("/todos/999999")
    assert r.status_code == 404
```

- [ ] **Step 4: Write a test proving the case loads with the oracle wired**

Create `tests/test_reference_oracle.py`:

```python
"""The todo-api reference oracle is authored and wired (E-31)."""
from pathlib import Path

from sdlc.benchmarks.cli import load_case_spec

CASE = "benchmarks/cases/todo-api-greenfield"


def test_case_declares_python_language():
    spec = load_case_spec(f"{CASE}/case.yaml")
    assert spec.language == "python"


def test_oracle_suite_files_exist():
    o = Path(CASE) / "oracle"
    assert (o / "conftest.py").is_file()
    assert (o / "test_crud.py").is_file()


def test_oracle_is_not_committed_into_a_produced_layout():
    # sanity: the oracle lives under benchmarks/cases, never in a src tree
    assert Path(CASE, "oracle").is_dir()
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_reference_oracle.py -v`
Expected: PASS (3).

- [ ] **Step 6: Verify the oracle suite is syntactically collectable**

Run: `python -m pytest benchmarks/cases/todo-api-greenfield/oracle --collect-only -q`
Expected: pytest collects 6 test items (collection may warn about the missing `app` module at fixture time — that is fine; `--collect-only` does not import fixtures). If collection ERRORS on a syntax problem, fix it. If it errors only because `app` cannot be imported, that is expected here and acceptable.

- [ ] **Step 7: Commit**

```bash
git add benchmarks/cases/todo-api-greenfield/ tests/test_reference_oracle.py
git commit -m "feat(benchmark): todo-api held-out oracle + ASGI contract (E-31)"
```

---

### Task 7: Documentation — mark E-31 landed

**Files:**
- Modify: `ROADMAP.md`
- Modify: `docs/BENCHMARK.md` (if it tracks E-31 status inline)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the roadmap**

In `ROADMAP.md`, flip E-31 from `[ ]` to `[x]` (§9.8) and append a landed-note mirroring E-30's style, e.g.:

```
- [x] **E-31 (new scope)** Tier-A held-out oracle in benchmark cases:
  `benchmarks/cases/<case>/oracle/` run against produced code through the
  case's `ToolchainAdapter` (E-30), graded as fraction passing by the
  benchmark-only `grade_oracle` activity (`src/sdlc/benchmarks/oracle.py`),
  invoked by `BenchmarkWorkflow` strictly after each child (held out by
  construction). Ships the fraction-passing grade + manifest `language:`
  adapter dispatch + manifest-vs-marker mismatch signal + oracle-is-held-out
  assertion; the "built evenly" overfit check is deferred to **E-31a**.
  JUnit XML via `ToolchainAdapter.oracle_test_cmd`; todo-api is the Python
  reference oracle (ASGI `app:app` contract). Spec
  `docs/superpowers/specs/2026-07-23-held-out-oracle-design.md`, plan
  `docs/superpowers/plans/2026-07-23-held-out-oracle.md`.
```

Also update the §9.8 suggested-ordering line and any SC-1 note that referenced E-31 as the vehicle for the unattended-reach grade, to read as landed. Add **E-31a** as a new `[ ]` follow-on line (anti-cheat B, "built evenly, not to the test").

- [ ] **Step 2: Update BENCHMARK.md if needed**

Grep for `E-31` in `docs/BENCHMARK.md`; if it lists E-31 as open, update the status line to landed and point at the spec/plan. (Skip if no reference.)

Run: `grep -n "E-31" docs/BENCHMARK.md` (skip the edit if no matches).

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md docs/BENCHMARK.md
git commit -m "docs(roadmap): mark E-31 held-out oracle landed; add E-31a (E-31)"
```

---

## Final verification

- [ ] **Run the full suite (excluding slow):** `python -m pytest -q -m "not slow"` — all green.
- [ ] **Run the slow oracle proof:** `python -m pytest tests/test_grade_oracle.py -q` — the end-to-end grade passes (this is the increment's proof).
- [ ] **Confirm additivity:** `python -m pytest tests/test_benchmark_workflow.py -q` — existing cell-config tests unchanged; the two oracle-less cases are untouched.
- [ ] **Worker import:** `python -c "import sdlc.worker"` — clean.

## Self-review notes (for the implementer)

- The reference oracle grades a *live* cell only when the produced app's runtime deps are importable in the worker environment (the "no venv per cell" seam shared with `run_integration_checks`). The Task-4 fixture app is pure-stdlib ASGI precisely so the *mechanism* proof needs zero extra deps; a specific todo-api cell that imports e.g. `fastapi` grades only if that dep is present. This is a known constraint, not a bug — note it, don't try to build per-cell venvs here.
- `grade_oracle` reuses `_git`/`_bounded_shell` from `activities.py`; do not fork them.
- Keep all imports at the top of `oracle.py` — Step 3 of Task 4 appends code that references `os`/`shutil`/`tempfile`/`Path`/`activity`; consolidate them with the Task-3 `defusedxml` import rather than scattering imports mid-file.
