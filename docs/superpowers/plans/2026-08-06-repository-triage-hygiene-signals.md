# Repository Triage — Hygiene Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `RepoTriage` contracts, the per-signal activity seam, and three deterministic hygiene signals (build probe, secret scan, baseline practice) so a repository can be triaged at a pinned commit.

**Architecture:** A new `src/sdlc/triage/` subpackage following the `deploy/` precedent: a pure contracts module (`models.py`, importing only Pydantic and `measurement.py`), pure per-signal logic under `signals/`, and thin `@activity.defn` wrappers in `triage/activities.py`. Each signal is its own activity so one signal's crash or timeout yields `not_collected` for itself alone. Readiness dimensions travel in `SignalResult.metrics` and are merged by a single pure `compute_readiness`.

**Tech Stack:** Python ≥3.11, Pydantic v2, Temporal (`temporalio`), pytest + pytest-asyncio. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-08-06-repository-triage-hygiene-signals-design.md`

## Global Constraints

- **No new third-party dependencies.** Everything here is stdlib + Pydantic + what `pyproject.toml` already declares.
- **`src/sdlc/triage/models.py` must import only `pydantic` and `..measurement`.** No `models.py`, no `activities.py`, no `temporalio`. This mirrors `measurement.py` and `grounding.py`; a violation shows up as a reviewable import.
- **Adapters stay pure** (ADR-15): `ToolchainAdapter` methods return command strings and identity, never touch a subprocess. Filesystem access lives in module-level functions (`detect`, `detect_with_marker`) and in activities.
- **Never construct `Measurement` directly for a non-measured state.** Use `Measurement.not_collected(reason)` / `Measurement.unknown(reason)` — both require a reason.
- **A timeout or a skipped step is `not_collected`, never a measured `0.0`.**
- **Run git through `sdlc.activities._git`**, which applies the `-c safe.directory=*` bypass required on Windows.
- **Windows compatibility:** venv script dir is `Scripts` on win32 and `bin` elsewhere; use `os.path.join`, never hardcoded separators.
- **Tests that build a venv or run a real `pip install` MUST be marked `@pytest.mark.slow`** — `pyproject.toml:35` excludes them from the default run.
- Test command for a fast unit test: `pytest tests/test_x.py::test_y -v`. To run a `slow` test: `pytest tests/test_x.py -v -m slow`.

---

### Task 1: Triage contracts

**Files:**
- Create: `src/sdlc/triage/__init__.py` (empty)
- Create: `src/sdlc/triage/models.py`
- Test: `tests/test_triage_models.py`

**Interfaces:**
- Consumes: `sdlc.measurement.Measurement`, `sdlc.measurement.CollectionState`
- Produces: `FixClass`, `Verdict`, `TriageFinding`, `SignalResult`, `Readiness`, `RepoTriage` — all imported by every later task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_models.py`:

```python
"""E-41 contracts: a signal that did not run must not carry findings."""
import pytest
from pydantic import ValidationError

from sdlc.measurement import Measurement
from sdlc.triage.models import (
    FixClass, Readiness, RepoTriage, SignalResult, TriageFinding, Verdict,
)


def _finding(**kw):
    base = dict(signal="secrets", rule="r", severity="high", detail="d",
                fix_class=FixClass.JUDGEMENT)
    base.update(kw)
    return TriageFinding(**base)


def test_not_collected_may_not_carry_findings():
    with pytest.raises(ValidationError) as exc:
        SignalResult(signal="secrets", version=1,
                     collected=Measurement.not_collected("crashed"),
                     findings=[_finding()])
    assert "did not happen" in str(exc.value)


def test_unknown_may_carry_partial_findings():
    r = SignalResult(signal="secrets", version=1,
                     collected=Measurement.unknown("partial read"),
                     findings=[_finding()])
    assert len(r.findings) == 1


def test_measured_carries_findings():
    r = SignalResult(signal="secrets", version=1,
                     collected=Measurement.measured(1.0),
                     findings=[_finding()])
    assert r.findings[0].fix_class is FixClass.JUDGEMENT


def test_signal_result_defaults_are_empty():
    r = SignalResult(signal="baseline", version=1,
                     collected=Measurement.measured(0.0))
    assert r.findings == []
    assert r.metrics == {}


def test_repo_triage_holds_readiness_and_signals():
    readiness = Readiness(
        buildable=Measurement.measured(1.0),
        runnable=Measurement.measured(1.0),
        tests_present=Measurement.measured(3.0),
        structure_discernible=Measurement.measured(1.0),
        verdict=Verdict.READY)
    t = RepoTriage(repo_dir="/r", commit_sha="abc123",
                   toolchain="python", readiness=readiness)
    assert t.readiness.verdict is Verdict.READY
    assert t.signals == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_triage_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.triage'`

- [ ] **Step 3: Create the package and contracts**

Create an empty `src/sdlc/triage/__init__.py`.

Create `src/sdlc/triage/models.py`:

```python
"""FR-901/FR-902 (E-41): the triage artifact and its contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as measurement.py and
grounding.py must not: a dependency here would appear as a reviewable import.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..measurement import CollectionState, Measurement


class FixClass(str, Enum):
    """FR-904. MECHANICAL is a promise an E-44 child run can keep with a PR;
    everything it cannot is JUDGEMENT or STRUCTURAL. See spec D7 -- deleting a
    committed .env is mechanical, rotating the exposed credential is not."""
    MECHANICAL = "mechanical"
    JUDGEMENT = "judgement"
    STRUCTURAL = "structural"


class Verdict(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    INDETERMINATE = "indeterminate"


class TriageFinding(BaseModel):
    signal: str                                 # signal id, e.g. "secrets"
    rule: str                                   # which rule inside it
    severity: Literal["critical", "high", "medium", "low"]
    detail: str
    path: str = ""
    line: int | None = None
    evidence: str = ""                          # verbatim quote from path@commit_sha
    fix_class: FixClass


class SignalResult(BaseModel):
    """One signal's output. `collected` is a Measurement, not a bool: a signal
    that timed out reports not_collected and contributes nothing, which is
    distinguishable from a signal that ran and found nothing (FR-915)."""
    signal: str
    version: int                                # bump invalidates E-46's memo key
    collected: Measurement                      # MEASURED value = finding count
    findings: list[TriageFinding] = Field(default_factory=list)
    metrics: dict[str, Measurement] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _not_collected_has_no_findings(self) -> "SignalResult":
        if (self.collected.state is CollectionState.NOT_COLLECTED
                and self.findings):
            raise ValueError(
                f"{self.signal}: NOT_COLLECTED carries {len(self.findings)} "
                f"finding(s) -- those are findings from a run that did not "
                f"happen. Partial output is UNKNOWN.")
        return self


class Readiness(BaseModel):
    """FR-901's four dimensions. Every value is positive-is-good, so the
    verdict rule is uniform: buildable/runnable/structure_discernible are
    1.0 or 0.0, tests_present is a count."""
    buildable: Measurement
    runnable: Measurement
    tests_present: Measurement
    structure_discernible: Measurement
    verdict: Verdict


class RepoTriage(BaseModel):
    repo_dir: str
    commit_sha: str                             # triage is pinned at a commit
    toolchain: str | None = None                # None is a finding, not an error
    readiness: Readiness
    signals: list[SignalResult] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_triage_models.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/triage/__init__.py src/sdlc/triage/models.py tests/test_triage_models.py
git commit -m "feat(triage): RepoTriage contracts with a not-collected-carries-no-findings invariant"
```

---

### Task 2: `compute_readiness`

**Files:**
- Modify: `src/sdlc/triage/models.py` (append)
- Test: `tests/test_triage_readiness.py`

**Interfaces:**
- Consumes: `SignalResult`, `Readiness`, `Verdict` from Task 1.
- Produces:
  - `READINESS_KEYS: tuple[str, ...]` = `("buildable", "runnable", "tests_present", "structure_discernible")`
  - `M_BUILDABLE`, `M_RUNNABLE`, `M_TESTS_PRESENT`, `M_STRUCTURE` — the four key constants, used by Tasks 4 and 6 to populate `SignalResult.metrics`.
  - `compute_readiness(signals: list[SignalResult]) -> Readiness`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_readiness.py`:

```python
"""D4: an unmeasured dimension is never READY. The truth table is the point."""
import pytest

from sdlc.measurement import Measurement
from sdlc.triage.models import (
    M_BUILDABLE, M_RUNNABLE, M_STRUCTURE, M_TESTS_PRESENT,
    SignalResult, Verdict, compute_readiness,
)


def _sig(name, **metrics):
    return SignalResult(signal=name, version=1,
                        collected=Measurement.measured(0.0), metrics=metrics)


def _all_good():
    return [
        _sig("build_probe", **{M_BUILDABLE: Measurement.measured(1.0),
                               M_RUNNABLE: Measurement.measured(1.0)}),
        _sig("baseline", **{M_TESTS_PRESENT: Measurement.measured(4.0),
                            M_STRUCTURE: Measurement.measured(1.0)}),
    ]


def test_all_measured_and_positive_is_ready():
    assert compute_readiness(_all_good()).verdict is Verdict.READY


def test_a_measured_zero_is_not_ready():
    sigs = [
        _sig("build_probe", **{M_BUILDABLE: Measurement.measured(0.0),
                               M_RUNNABLE: Measurement.measured(1.0)}),
        _sig("baseline", **{M_TESTS_PRESENT: Measurement.measured(4.0),
                            M_STRUCTURE: Measurement.measured(1.0)}),
    ]
    assert compute_readiness(sigs).verdict is Verdict.NOT_READY


def test_zero_tests_is_not_ready_not_indeterminate():
    sigs = [
        _sig("build_probe", **{M_BUILDABLE: Measurement.measured(1.0),
                               M_RUNNABLE: Measurement.measured(1.0)}),
        _sig("baseline", **{M_TESTS_PRESENT: Measurement.measured(0.0),
                            M_STRUCTURE: Measurement.measured(1.0)}),
    ]
    assert compute_readiness(sigs).verdict is Verdict.NOT_READY


@pytest.mark.parametrize("key", [M_BUILDABLE, M_RUNNABLE,
                                 M_TESTS_PRESENT, M_STRUCTURE])
def test_any_not_collected_dimension_forces_indeterminate(key):
    sigs = _all_good()
    for s in sigs:
        if key in s.metrics:
            s.metrics[key] = Measurement.not_collected("timed out")
    assert compute_readiness(sigs).verdict is Verdict.INDETERMINATE


@pytest.mark.parametrize("key", [M_BUILDABLE, M_RUNNABLE,
                                 M_TESTS_PRESENT, M_STRUCTURE])
def test_a_dimension_no_signal_reported_forces_indeterminate(key):
    sigs = _all_good()
    for s in sigs:
        s.metrics.pop(key, None)
    r = compute_readiness(sigs)
    assert r.verdict is Verdict.INDETERMINATE
    assert "no signal reported" in getattr(r, key).reason


def test_no_signals_at_all_is_indeterminate():
    assert compute_readiness([]).verdict is Verdict.INDETERMINATE


def test_unknown_dimension_forces_indeterminate():
    sigs = _all_good()
    sigs[0].metrics[M_BUILDABLE] = Measurement.unknown("garbled output")
    assert compute_readiness(sigs).verdict is Verdict.INDETERMINATE


def test_two_signals_reporting_the_same_key_is_an_error():
    sigs = _all_good()
    sigs[1].metrics[M_BUILDABLE] = Measurement.measured(1.0)
    with pytest.raises(ValueError) as exc:
        compute_readiness(sigs)
    assert "buildable" in str(exc.value)


def test_non_readiness_metric_keys_are_ignored():
    sigs = _all_good()
    sigs[0].metrics["install_seconds"] = Measurement.measured(12.0)
    assert compute_readiness(sigs).verdict is Verdict.READY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_triage_readiness.py -v`
Expected: FAIL — `ImportError: cannot import name 'M_BUILDABLE'`

- [ ] **Step 3: Append the implementation to `src/sdlc/triage/models.py`**

```python
# The four reserved metric keys carrying FR-901's readiness dimensions.
# Exactly ONE signal may report each: build_probe owns buildable/runnable,
# baseline owns tests_present/structure_discernible. A duplicate is FR-902's
# one-implementation rule being broken, so compute_readiness raises rather
# than silently preferring one producer.
M_BUILDABLE = "buildable"
M_RUNNABLE = "runnable"
M_TESTS_PRESENT = "tests_present"
M_STRUCTURE = "structure_discernible"
READINESS_KEYS: tuple[str, ...] = (
    M_BUILDABLE, M_RUNNABLE, M_TESTS_PRESENT, M_STRUCTURE)


def compute_readiness(signals: list[SignalResult]) -> Readiness:
    """The ONLY producer of Verdict (spec D4). No caller sets it, so the
    artifact cannot disagree with its own inputs.

    Any dimension that is not MEASURED -- because a signal reported
    not_collected/unknown, or because no signal reported it at all -- forces
    INDETERMINATE. An unmeasured dimension never reads as READY: that is the
    conflation E-40 removed from SecurityReport, and FR-903 gates the Tier 2
    audit on this verdict.
    """
    reported: dict[str, Measurement] = {}
    for sig in sorted(signals, key=lambda s: s.signal):
        for key, m in sig.metrics.items():
            if key not in READINESS_KEYS:
                continue                      # signals may carry other metrics
            if key in reported:
                raise ValueError(
                    f"readiness key {key!r} reported by more than one signal "
                    f"(second was {sig.signal!r}) -- exactly one signal owns "
                    f"each dimension (FR-902)")
            reported[key] = m

    dims = {
        key: reported.get(key)
        or Measurement.not_collected(f"no signal reported {key}")
        for key in READINESS_KEYS
    }

    if any(m.state is not CollectionState.MEASURED for m in dims.values()):
        verdict = Verdict.INDETERMINATE
    elif all((m.value or 0.0) > 0 for m in dims.values()):
        verdict = Verdict.READY
    else:
        verdict = Verdict.NOT_READY
    return Readiness(**dims, verdict=verdict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_triage_readiness.py -v`
Expected: PASS (15 tests, counting parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/triage/models.py tests/test_triage_readiness.py
git commit -m "feat(triage): compute_readiness, where an unmeasured dimension is never READY"
```

---

### Task 3: FR-108 toolchain adapter extension

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py`
- Test: `tests/test_toolchain_triage_extension.py`

**Interfaces:**
- Consumes: existing `ToolchainAdapter`, `PythonToolchain`, `TOOLCHAINS`, `detect`.
- Produces:
  - `ToolchainAdapter.install_cmd(marker: str) -> str | None`
  - `ToolchainAdapter.classify_test_exit(code: int) -> Literal["ran", "failed_to_run", "no_tests"]`
  - `ToolchainAdapter.test_globs: tuple[str, ...]`, `ToolchainAdapter.lockfiles: tuple[str, ...]`
  - `detect_with_marker(worktree: str) -> tuple[ToolchainAdapter, str] | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_toolchain_triage_extension.py`:

```python
"""E-41's additions to the FR-108 adapter. classify_test_exit carries the
weight: pytest exits 1 for test failures and 2/3/4 for collection errors, and
"the suite ran and failed" is a different readiness fact from "the suite could
not run".
"""
import pytest

from sdlc.toolchain.adapters import (
    PythonToolchain, ToolchainKind, detect, detect_with_marker,
)


def test_install_cmd_for_requirements_uses_the_requirements_file():
    assert PythonToolchain().install_cmd("requirements.txt") == (
        "pip install -r requirements.txt")


@pytest.mark.parametrize("marker", ["pyproject.toml", "setup.py", "setup.cfg"])
def test_install_cmd_for_packaging_markers_is_non_editable(marker):
    # Non-editable on purpose: `pip install -e .` writes *.egg-info into the
    # repository under audit; PEP 517 builds `pip install .` in a temp dir.
    assert PythonToolchain().install_cmd(marker) == "pip install ."


@pytest.mark.parametrize("code,expected", [
    (0, "ran"),            # all passed
    (1, "ran"),            # tests failed -- the suite still RAN
    (2, "failed_to_run"),  # interrupted
    (3, "failed_to_run"),  # internal error
    (4, "failed_to_run"),  # usage error
    (5, "no_tests"),       # nothing collected
])
def test_classify_test_exit(code, expected):
    assert PythonToolchain().classify_test_exit(code) == expected


def test_python_declares_test_globs_and_lockfiles():
    tc = PythonToolchain()
    assert "test_*.py" in tc.test_globs
    assert "uv.lock" in tc.lockfiles


def test_detect_with_marker_returns_which_marker_matched(tmp_path):
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    found = detect_with_marker(str(tmp_path))
    assert found is not None
    adapter, marker = found
    assert adapter.kind is ToolchainKind.PYTHON
    assert marker == "requirements.txt"


def test_detect_with_marker_is_none_for_unrecognized_tree(tmp_path):
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    assert detect_with_marker(str(tmp_path)) is None


def test_detect_still_returns_just_the_adapter(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert detect(str(tmp_path)).kind is ToolchainKind.PYTHON
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_toolchain_triage_extension.py -v`
Expected: FAIL — `ImportError: cannot import name 'detect_with_marker'`

- [ ] **Step 3: Extend `src/sdlc/toolchain/adapters.py`**

Add `Literal` to the typing import at the top of the file:

```python
from typing import Literal
```

Add these members to the `ToolchainAdapter` ABC, after the `markers` declaration and before `test_cmd`. All are concrete defaults, so E-30a/b/c stay unblocked:

```python
    # E-41 (FR-902). Concrete defaults, not abstract: a new adapter that has
    # not thought about triage yet degrades to "no install command" and the
    # probe records not_collected, rather than failing to instantiate.
    test_globs: tuple[str, ...] = ()
    lockfiles: tuple[str, ...] = ()

    def install_cmd(self, marker: str) -> str | None:
        """Dependency-install command for the marker detect_with_marker
        matched, or None where the language has none. Takes the marker
        because one adapter can serve several conventions (Python:
        pyproject.toml vs requirements.txt) and the adapter stays pure --
        it never looks at the filesystem to decide."""
        return None

    def classify_test_exit(
            self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]:
        """Whether the suite RAN, as distinct from whether it PASSED.

        Load-bearing for the triage `runnable` dimension: "tests ran and some
        failed" and "the suite could not be collected" are different readiness
        facts, and the exit-code mapping is per-language. The default is the
        conservative one for a language whose runner has not been mapped."""
        return "ran" if code == 0 else "failed_to_run"
```

Add to `PythonToolchain`, after the `markers` declaration:

```python
    test_globs = ("test_*.py", "*_test.py", "tests/**/*.py")
    # requirements.txt is deliberately NOT here: it is a manifest that may or
    # may not pin. Whether it pins is E-41a's dependency-health question.
    lockfiles = ("uv.lock", "poetry.lock", "Pipfile.lock")

    def install_cmd(self, marker: str) -> str | None:
        if marker == "requirements.txt":
            return "pip install -r requirements.txt"
        # Non-editable: `pip install -e .` writes *.egg-info into the tree
        # under audit, and triage must not mutate what it measures. PEP 517
        # builds `pip install .` in a temporary directory.
        return "pip install ."

    def classify_test_exit(
            self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]:
        # pytest exit codes: 0 ok, 1 tests failed, 2 interrupted,
        # 3 internal error, 4 usage error, 5 no tests collected.
        if code in (0, 1):
            return "ran"
        if code == 5:
            return "no_tests"
        return "failed_to_run"
```

Replace the module-level `detect` function at the bottom of the file with:

```python
def detect_with_marker(worktree: str) -> tuple[ToolchainAdapter, str] | None:
    """Return (adapter, the marker filename that matched) or None.

    E-41 needs to know WHICH marker matched, because install_cmd differs
    between a packaging marker and a requirements file while the adapter
    itself stays pure. detect() is the unchanged one-value form."""
    for adapter in TOOLCHAINS.values():
        for marker in adapter.markers:
            if os.path.isfile(os.path.join(worktree, marker)):
                return adapter, marker
    return None


def detect(worktree: str) -> ToolchainAdapter | None:
    """Return the first adapter whose marker file exists at the worktree root,
    or None for an unrecognized/absent marker (caller degrades gracefully).

    Resolves by what was BUILT (marker file), never the contract's claimed
    stack — a marker/claim mismatch is itself a signal (ADR-15)."""
    found = detect_with_marker(worktree)
    return found[0] if found else None
```

- [ ] **Step 4: Run the new and the existing adapter tests**

Run: `pytest tests/test_toolchain_triage_extension.py tests/test_toolchain_adapters.py -v`
Expected: PASS — both files. `detect`'s marker precedence is unchanged, so no existing assertion moves.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/toolchain/adapters.py tests/test_toolchain_triage_extension.py
git commit -m "feat(toolchain): install_cmd, classify_test_exit, test_globs, lockfiles, detect_with_marker"
```

---

### Task 4: `baseline` signal + activity

**Files:**
- Create: `src/sdlc/triage/signals/__init__.py` (empty)
- Create: `src/sdlc/triage/signals/baseline.py`
- Create: `src/sdlc/triage/activities.py`
- Test: `tests/test_triage_baseline.py`

**Interfaces:**
- Consumes: Task 1 contracts, Task 2's `M_TESTS_PRESENT` / `M_STRUCTURE`, Task 3's `detect_with_marker` and `ToolchainAdapter.test_globs` / `.lockfiles`.
- Produces:
  - `baseline.SIGNAL_ID = "baseline"`, `baseline.VERSION = 1`
  - `baseline.find_test_files(paths: Sequence[str], test_globs: Sequence[str]) -> list[str]` — **the single implementation of test discovery**; Task 6 imports it rather than writing a second one.
  - `baseline.evaluate(paths: Sequence[str], gitignore_text: str, toolchain: ToolchainAdapter | None) -> SignalResult`
  - `activities.TriageSignalInput` dataclass: `repo_dir: str`, `commit_sha: str`
  - `activities.tracked_paths(repo_dir: str, commit_sha: str) -> list[str]`
  - `activities.read_blob(repo_dir: str, commit_sha: str, path: str) -> str | None`
  - `@activity.defn async def triage_baseline(inp: TriageSignalInput) -> SignalResult`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_baseline.py`:

```python
"""Baseline practice over the tracked tree at a pinned commit."""
import subprocess

import pytest

from sdlc.measurement import CollectionState
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.triage.activities import (
    TriageSignalInput, read_blob, tracked_paths, triage_baseline,
)
from sdlc.triage.models import (
    FixClass, M_STRUCTURE, M_TESTS_PRESENT,
)
from sdlc.triage.signals import baseline


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True)


def _commit_repo(root, files: dict[str, str]) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "one"], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True).stdout.strip()


def _rules(result):
    return {f.rule for f in result.findings}


# ---- pure logic -------------------------------------------------------

def test_find_test_files_matches_all_three_python_conventions():
    paths = ["test_a.py", "b_test.py", "tests/unit/test_c.py",
             "src/app.py", "docs/test_notes.md"]
    found = baseline.find_test_files(paths, PythonToolchain().test_globs)
    assert set(found) == {"test_a.py", "b_test.py", "tests/unit/test_c.py"}


def test_clean_repo_yields_no_findings():
    paths = ["pyproject.toml", "uv.lock", "README.md", "src/app.py",
             "tests/test_app.py", ".github/workflows/ci.yml", ".gitignore"]
    r = baseline.evaluate(paths, ".env\n__pycache__/\n", PythonToolchain())
    assert r.findings == []
    assert r.collected.state is CollectionState.MEASURED
    assert r.metrics[M_TESTS_PRESENT].value == 1.0
    assert r.metrics[M_STRUCTURE].value == 1.0


def test_vibe_repo_yields_the_expected_rule_set():
    # No toolchain resolved (no JS adapter until E-30b), so no_lockfile is
    # deliberately absent: we cannot name a lockfile for a stack we do not
    # recognize, and inventing one would be a finding we cannot justify.
    paths = ["package.json", "src/App.jsx", ".env"]
    r = baseline.evaluate(paths, "", None)
    assert _rules(r) == {"no_ci", "gitignore_missing", "no_readme",
                         "no_tests", "no_env_example"}


def test_no_lockfile_fires_only_when_a_toolchain_declares_lockfiles():
    paths = ["pyproject.toml", "README.md", "src/a.py", "tests/test_a.py",
             ".github/workflows/ci.yml", ".gitignore"]
    r = baseline.evaluate(paths, ".env\n", PythonToolchain())
    assert _rules(r) == {"no_lockfile"}


def test_gitignore_present_but_not_covering_env():
    paths = ["pyproject.toml", "uv.lock", "README.md", "src/a.py",
             "tests/test_a.py", ".github/workflows/ci.yml", ".gitignore"]
    r = baseline.evaluate(paths, "__pycache__/\n*.log\n", PythonToolchain())
    assert _rules(r) == {"gitignore_missing_env"}
    assert next(f for f in r.findings).fix_class is FixClass.MECHANICAL


def test_no_tests_is_structural_not_mechanical():
    r = baseline.evaluate(["pyproject.toml", "src/a.py"], "", PythonToolchain())
    f = next(f for f in r.findings if f.rule == "no_tests")
    assert f.fix_class is FixClass.STRUCTURAL
    assert r.metrics[M_TESTS_PRESENT].value == 0.0


def test_structure_not_collected_without_a_toolchain():
    r = baseline.evaluate(["src/a.py", "README.md"], "", None)
    m = r.metrics[M_STRUCTURE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "marker" in m.reason


def test_structure_is_zero_when_toolchain_resolves_but_no_source_exists():
    r = baseline.evaluate(["pyproject.toml", "README.md"], "",
                          PythonToolchain())
    assert r.metrics[M_STRUCTURE].value == 0.0


def test_env_example_present_suppresses_the_finding():
    r = baseline.evaluate([".env", ".env.example", "pyproject.toml"], "",
                          PythonToolchain())
    assert "no_env_example" not in _rules(r)


@pytest.mark.parametrize("ci_path", [
    ".github/workflows/ci.yml", ".github/workflows/ci.yaml",
    ".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml",
])
def test_each_ci_convention_is_recognized(ci_path):
    r = baseline.evaluate(["pyproject.toml", ci_path], "", PythonToolchain())
    assert "no_ci" not in _rules(r)


# ---- git seam + activity ---------------------------------------------

def test_tracked_paths_excludes_untracked_and_ignored(tmp_path):
    sha = _commit_repo(tmp_path, {
        "pyproject.toml": "[project]\n", ".gitignore": ".env\n"})
    (tmp_path / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (tmp_path / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    paths = tracked_paths(str(tmp_path), sha)
    assert set(paths) == {"pyproject.toml", ".gitignore"}


def test_read_blob_returns_none_for_a_missing_path(tmp_path):
    sha = _commit_repo(tmp_path, {"pyproject.toml": "[project]\n"})
    assert read_blob(str(tmp_path), sha, "nope.py") is None
    assert read_blob(str(tmp_path), sha, "pyproject.toml") == "[project]\n"


@pytest.mark.asyncio
async def test_activity_reports_on_a_vibe_repo(tmp_path):
    sha = _commit_repo(tmp_path, {
        "package.json": '{"name":"app"}\n', "src/App.jsx": "export default 1\n"})
    r = await triage_baseline(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.signal == "baseline"
    assert r.collected.state is CollectionState.MEASURED
    assert "no_tests" in _rules(r)


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _commit_repo(tmp_path, {"pyproject.toml": "[project]\n"})
    r = await triage_baseline(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_triage_baseline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.triage.signals'`

- [ ] **Step 3: Write `src/sdlc/triage/signals/baseline.py`**

Create an empty `src/sdlc/triage/signals/__init__.py` first, then:

```python
"""FR-902: missing baseline practice. Pure logic over a list of tracked paths.

Owns test discovery for the whole triage tier (find_test_files) -- build_probe
imports it. BrownKit ships bash, PowerShell and Python copies of its detectors;
FR-902's "exactly one implementation per signal" applies to our own code too,
and a second copy of test discovery inside the probe is the same failure at
smaller scale.
"""
from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Sequence

from ...measurement import Measurement
from ...toolchain.adapters import ToolchainAdapter
from ..models import (
    FixClass, M_STRUCTURE, M_TESTS_PRESENT, SignalResult, TriageFinding,
)

SIGNAL_ID = "baseline"
VERSION = 1

# A deliberate floor, not a judgement about structure quality (spec D8/§8):
# E-41b's generator-scaffold detection is what sharpens it. Until then a
# repository that is entirely untouched scaffolding passes this dimension.
_SOURCE_EXTENSIONS = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs",
                      ".java", ".rb", ".php", ".cs", ".kt", ".swift")

_CI_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml",
             ".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml",
             "azure-pipelines.yml", ".travis.yml")

_ENV_EXAMPLES = (".env.example", ".env.sample", ".env.template")


def find_test_files(paths: Sequence[str],
                    test_globs: Sequence[str]) -> list[str]:
    """Every tracked path matching one of the adapter's test conventions.

    Matches against the full posix-style repo-relative path AND the basename,
    because conventions come in both shapes ("tests/**/*.py" is a path glob,
    "test_*.py" is a basename glob)."""
    out: list[str] = []
    for p in paths:
        base = posixpath.basename(p)
        for glob in test_globs:
            if fnmatch.fnmatch(p, glob) or fnmatch.fnmatch(base, glob):
                out.append(p)
                break
    return out


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path)


def evaluate(paths: Sequence[str], gitignore_text: str,
             toolchain: ToolchainAdapter | None) -> SignalResult:
    """Static baseline checks. `paths` are repo-relative posix paths tracked at
    the pinned commit; `gitignore_text` is "" when no .gitignore is tracked."""
    tracked = set(paths)
    findings: list[TriageFinding] = []

    has_ci = any(fnmatch.fnmatch(p, g) for p in tracked for g in _CI_GLOBS)
    if not has_ci:
        findings.append(_finding(
            "no_ci", "medium",
            "No CI configuration found; nothing runs the suite on push.",
            FixClass.JUDGEMENT))

    if ".gitignore" not in tracked:
        findings.append(_finding(
            "gitignore_missing", "medium",
            "No .gitignore; build output and local env files are one "
            "`git add -A` away from being committed.",
            FixClass.MECHANICAL, path=".gitignore"))
    elif not any(line.strip().startswith(".env")
                 for line in gitignore_text.splitlines()):
        findings.append(_finding(
            "gitignore_missing_env", "high",
            ".gitignore does not cover .env files, which is how credentials "
            "reach a repository in the first place.",
            FixClass.MECHANICAL, path=".gitignore"))

    if not any(posixpath.basename(p).lower().startswith("readme")
               for p in tracked if "/" not in p):
        findings.append(_finding(
            "no_readme", "low", "No README at the repository root.",
            FixClass.JUDGEMENT))

    lockfiles = toolchain.lockfiles if toolchain else ()
    if lockfiles and not any(lf in tracked for lf in lockfiles):
        findings.append(_finding(
            "no_lockfile", "medium",
            f"No lockfile ({', '.join(lockfiles)}); dependency resolution is "
            f"not reproducible.",
            FixClass.JUDGEMENT))

    test_files = find_test_files(
        sorted(tracked), toolchain.test_globs if toolchain else ())
    if not test_files:
        findings.append(_finding(
            "no_tests", "high",
            "No test files found. Writing a suite is design work, not a "
            "mechanical patch.",
            FixClass.STRUCTURAL))

    env_referenced = (".env" in tracked
                      or any(line.strip().startswith(".env")
                             for line in gitignore_text.splitlines()))
    if env_referenced and not any(e in tracked for e in _ENV_EXAMPLES):
        findings.append(_finding(
            "no_env_example", "low",
            "The project uses a .env but ships no .env.example, so required "
            "configuration is undiscoverable.",
            FixClass.MECHANICAL))

    if toolchain is None:
        structure = Measurement.not_collected(
            "no toolchain marker resolved, so structure is not assessable")
    else:
        has_source = any(p.endswith(_SOURCE_EXTENSIONS) for p in tracked)
        structure = Measurement.measured(1.0 if has_source else 0.0)

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={
            M_TESTS_PRESENT: Measurement.measured(float(len(test_files))),
            M_STRUCTURE: structure,
        })
```

- [ ] **Step 4: Write `src/sdlc/triage/activities.py`**

```python
"""E-41 signal activities (FR-902). One activity per signal, deliberately:
a signal that crashes or times out yields not_collected for ITSELF while every
other signal still reports (spec D3).

Findings are read from the pinned commit through git, never from the working
checkout (spec D6): a gitignored local .env cannot produce a false positive,
untracked build output produces no noise, and every evidence citation is true
against path@sha by construction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from temporalio import activity

from ..activities import _git
from ..measurement import Measurement
from ..toolchain.adapters import detect_with_marker
from .models import SignalResult
from .signals import baseline

_log = logging.getLogger(__name__)


@dataclass
class TriageSignalInput:
    repo_dir: str
    commit_sha: str


def tracked_paths(repo_dir: str, commit_sha: str) -> list[str]:
    """Repo-relative posix paths tracked at commit_sha. Raises RuntimeError
    when the sha does not resolve -- the activity turns that into
    not_collected, which is the only honest report for a tree we cannot read."""
    proc = _git(["ls-tree", "-r", "--name-only", commit_sha], cwd=repo_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-tree failed for {commit_sha}: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


def read_blob(repo_dir: str, commit_sha: str, path: str) -> str | None:
    """The file's bytes at the pinned commit, or None when the path does not
    resolve to a blob. Mirrors activities.read_committed_bytes -- same `git
    cat-file -t` guard, because `git show sha:dir` exits 0 with a tree
    listing, which is not the file's bytes."""
    ref = f"{commit_sha}:{path}"
    kind = _git(["cat-file", "-t", ref], cwd=repo_dir)
    if kind.returncode != 0 or kind.stdout.strip() != "blob":
        return None
    proc = _git(["show", ref], cwd=repo_dir)
    return proc.stdout if proc.returncode == 0 else None


@activity.defn
async def triage_baseline(inp: TriageSignalInput) -> SignalResult:
    """FR-902 baseline practice. Never raises: an unreadable tree is a
    not_collected report, not a failed triage."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        gitignore = ""
        if ".gitignore" in paths:
            gitignore = read_blob(inp.repo_dir, inp.commit_sha,
                                  ".gitignore") or ""
        found = detect_with_marker(inp.repo_dir)
        return baseline.evaluate(paths, gitignore,
                                 found[0] if found else None)
    except Exception as exc:                       # noqa: BLE001 -- see docstring
        _log.warning("triage baseline signal failed: %s", exc)
        return SignalResult(
            signal=baseline.SIGNAL_ID, version=baseline.VERSION,
            collected=Measurement.not_collected(
                f"baseline signal raised: {type(exc).__name__}: {exc}"))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_triage_baseline.py -v`
Expected: PASS (18 tests, counting parametrized cases)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/triage/signals/__init__.py src/sdlc/triage/signals/baseline.py src/sdlc/triage/activities.py tests/test_triage_baseline.py
git commit -m "feat(triage): baseline practice signal over the pinned tree"
```

---

### Task 5: `secrets` signal + activity

**Files:**
- Create: `src/sdlc/triage/signals/secrets.py`
- Modify: `src/sdlc/triage/activities.py` (append the activity)
- Test: `tests/test_triage_secrets.py`

**Interfaces:**
- Consumes: Task 1 contracts; Task 4's `tracked_paths`, `read_blob`, `TriageSignalInput`.
- Produces:
  - `secrets.SIGNAL_ID = "secrets"`, `secrets.VERSION = 1`
  - `secrets.scan_text(path: str, text: str) -> list[TriageFinding]`
  - `secrets.env_file_findings(paths: Sequence[str]) -> list[TriageFinding]`
  - `secrets.MAX_BLOB_BYTES = 1_000_000`
  - `@activity.defn async def triage_secrets(inp: TriageSignalInput) -> SignalResult`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_secrets.py`:

```python
"""The highest-yield vibe-code signal, and the one where a false positive
costs the most trust.
"""
import subprocess

import pytest

from sdlc.grounding import Profile, verify_quote
from sdlc.measurement import CollectionState
from sdlc.triage.activities import TriageSignalInput, read_blob, triage_secrets
from sdlc.triage.models import FixClass
from sdlc.triage.signals import secrets


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True)


def _commit_repo(root, files: dict[str, str]) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "one"], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True).stdout.strip()


def _rules(findings):
    return {f.rule for f in findings}


# ---- provider patterns ------------------------------------------------

@pytest.mark.parametrize("line,rule", [
    ('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"', "aws_access_key_id"),
    ('t = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"', "github_token"),
    ('k = "AIzaSyD-0123456789abcdefghijklmnopqrstu"', "google_api_key"),
    ('s = "xoxb-123456789012-abcdefghijklmnop"', "slack_token"),
    ("-----BEGIN RSA PRIVATE KEY-----", "private_key"),
])
def test_provider_patterns_are_critical(line, rule):
    found = secrets.scan_text("src/config.py", line)
    assert rule in _rules(found)
    f = next(f for f in found if f.rule == rule)
    assert f.severity == "critical"
    assert f.fix_class is FixClass.JUDGEMENT   # rotation is not mechanical


def test_finding_carries_the_matched_line_and_number():
    text = "import os\n\nAWS_KEY = \"AKIAIOSFODNN7EXAMPLE\"\n"
    f = next(f for f in secrets.scan_text("c.py", text)
             if f.rule == "aws_access_key_id")
    assert f.line == 3
    assert "AKIAIOSFODNN7EXAMPLE" in f.evidence
    assert f.path == "c.py"


# ---- generic rule + entropy gate --------------------------------------

def test_generic_rule_ignores_a_low_entropy_placeholder():
    assert secrets.scan_text("s.py", 'password = "changeme"') == []


def test_generic_rule_ignores_a_short_value():
    assert secrets.scan_text("s.py", 'api_key = "abc123"') == []


def test_generic_rule_flags_a_high_entropy_value_at_low_severity():
    found = secrets.scan_text(
        "s.py", 'API_KEY = "f3Kq9Zx2Lm7Rv4Tn8Wb1Yc6Hd5Jg0Ps"')
    assert _rules(found) == {"generic_secret_assignment"}
    assert found[0].severity == "low"


# ---- client-bundle reachability ---------------------------------------

@pytest.mark.parametrize("var", [
    "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY",
    "VITE_STRIPE_SECRET_KEY",
    "REACT_APP_PRIVATE_KEY",
    "EXPO_PUBLIC_API_SECRET",
    "GATSBY_SERVICE_ROLE_TOKEN",
])
def test_client_inlined_secret_named_vars_are_critical(var):
    found = secrets.scan_text("src/lib/db.ts", f"const k = process.env.{var};")
    assert "client_bundle_secret" in _rules(found)
    f = next(f for f in found if f.rule == "client_bundle_secret")
    assert f.severity == "critical"
    assert var in f.detail


def test_public_prefixed_but_not_secret_named_var_is_not_flagged():
    found = secrets.scan_text(
        "src/a.ts", "const u = process.env.NEXT_PUBLIC_API_URL;")
    assert "client_bundle_secret" not in _rules(found)


def test_secret_named_but_not_client_prefixed_var_is_not_client_flagged():
    found = secrets.scan_text(
        "server/a.ts", "const k = process.env.SUPABASE_SERVICE_ROLE_KEY;")
    assert "client_bundle_secret" not in _rules(found)


# ---- committed .env ----------------------------------------------------

def test_committed_env_splits_into_two_findings():
    found = secrets.env_file_findings([".env", "src/a.py"])
    by_rule = {f.rule: f for f in found}
    assert by_rule["secret_committed"].fix_class is FixClass.JUDGEMENT
    assert "rotat" in by_rule["secret_committed"].detail.lower()
    assert by_rule["env_file_tracked"].fix_class is FixClass.MECHANICAL


def test_env_rule_names_do_not_collide_with_baseline():
    # baseline owns "gitignore_missing_env" (the .gitignore does not cover
    # .env); secrets owns "env_file_tracked" (a .env is IN the index). Two
    # conditions, two names -- one rule id must mean one thing.
    assert {f.rule for f in secrets.env_file_findings([".env"])} == {
        "secret_committed", "env_file_tracked"}


def test_no_env_tracked_means_no_env_findings():
    assert secrets.env_file_findings(["src/a.py"]) == []


# ---- activity ----------------------------------------------------------

@pytest.mark.asyncio
async def test_activity_finds_the_canonical_vibe_repo_leak(tmp_path):
    sha = _commit_repo(tmp_path, {
        ".env": "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiJ9\n",
        "src/db.ts": "export const k = "
                     "process.env.NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY;\n",
    })
    r = await triage_secrets(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.collected.state is CollectionState.MEASURED
    assert {"secret_committed", "client_bundle_secret"} <= _rules(r.findings)
    assert r.metrics == {}          # secrets feeds no readiness dimension


@pytest.mark.asyncio
async def test_gitignored_local_env_produces_no_finding(tmp_path):
    # D6: enumeration from the tracked tree, not the worktree.
    sha = _commit_repo(tmp_path, {".gitignore": ".env\n",
                                  "src/a.py": "x = 1\n"})
    (tmp_path / ".env").write_text(
        'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    r = await triage_secrets(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.findings == []


@pytest.mark.asyncio
async def test_every_evidence_quote_verifies_against_the_pinned_bytes(tmp_path):
    # D5: the drift guard, and FR-914's first commit-source caller.
    sha = _commit_repo(tmp_path, {
        "src/config.py": 'import os\nAWS = "AKIAIOSFODNN7EXAMPLE"\n'})
    r = await triage_secrets(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.findings
    for f in r.findings:
        if not f.evidence or not f.path:
            continue
        blob = read_blob(str(tmp_path), sha, f.path)
        assert blob is not None
        assert verify_quote(f.evidence, blob, Profile.VERBATIM_BYTES)


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _commit_repo(tmp_path, {"src/a.py": "x = 1\n"})
    r = await triage_secrets(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []


@pytest.mark.asyncio
async def test_binary_blob_is_skipped_not_crashed(tmp_path):
    sha = _commit_repo(tmp_path, {"src/a.py": "x = 1\n"})
    (tmp_path / "logo.bin").write_bytes(b"\x00\x01\x02AKIAIOSFODNN7EXAMPLE")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "two"], tmp_path)
    sha2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                          capture_output=True, encoding="utf-8",
                          check=True).stdout.strip()
    r = await triage_secrets(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha=sha2))
    assert r.collected.state is CollectionState.MEASURED
    assert r.findings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_triage_secrets.py -v`
Expected: FAIL — `ImportError: cannot import name 'secrets' from 'sdlc.triage.signals'`

- [ ] **Step 3: Write `src/sdlc/triage/signals/secrets.py`**

```python
"""FR-902: committed credentials, including the ones reachable from a client
bundle -- the highest-yield vibe-code finding, and the one no generic secret
scanner looks for.

Fix classes follow spec D7: removing a committed .env is MECHANICAL, but the
leaked credential itself is JUDGEMENT, because rotation is a human act. A PR
that deletes .env while the key stays live has produced the appearance of
remediation, which is worse than an open finding.

Stated bound (spec §7): client-bundle reachability is decided by CONVENTION --
build-time-inlined env prefixes -- not by dataflow. We do no taint tracking, so
a secret imported into a client component from a non-prefixed source is a false
negative. Naming that surface is what keeps the finding trustworthy.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..models import FixClass, TriageFinding

SIGNAL_ID = "secrets"
VERSION = 1

# Blobs larger than this are skipped: a minified bundle or a checked-in asset
# costs more to regex than the finding is worth, and E-41d owns size outliers.
MAX_BLOB_BYTES = 1_000_000

_ENV_EXAMPLES = (".env.example", ".env.sample", ".env.template")

# (rule, pattern, detail). All critical, all JUDGEMENT: a matched provider
# credential must be rotated, and rotation is not something a PR can do.
_PROVIDER_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}"),
     "AWS access key id committed to the repository."),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
     "GitHub token committed to the repository."),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
     "GitHub fine-grained PAT committed to the repository."),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
     "Google API key committed to the repository."),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
     "Slack token committed to the repository."),
    ("private_key",
     re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
     "Private key material committed to the repository."),
)

# Prefixes whose values frameworks INLINE INTO THE CLIENT BUNDLE at build time.
# The name is the whole signal: a service-role JWT is byte-indistinguishable
# from any other JWT, so only the variable's name says it must never ship.
_CLIENT_BUNDLE_VAR = re.compile(
    r"\b((?:NEXT_PUBLIC|VITE|REACT_APP|NUXT_PUBLIC|EXPO_PUBLIC|PUBLIC|GATSBY)"
    r"_[A-Z0-9_]*(?:SECRET|SERVICE_ROLE|PRIVATE_KEY)[A-Z0-9_]*)\b")

_GENERIC_ASSIGNMENT = re.compile(
    r"""(?i)\b(?:secret|token|password|passwd|api[_-]?key)\b\s*[:=]\s*"""
    r"""["']([^"'\s]{8,})["']""")


def _looks_random(value: str) -> bool:
    """Entropy gate for the generic rule. Without it, `password = "changeme"`
    floods every report and the signal stops being read; with it the rule
    keeps its narrow job of catching a real-looking literal. Deliberately
    crude -- charset diversity and length, not a Shannon threshold, because an
    arbitrary bit-count is no more defensible and much harder to explain in a
    finding."""
    return len(value) >= 16 and len(set(value)) >= 10


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", line: int | None = None,
             evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         line=line, evidence=evidence)


def scan_text(path: str, text: str) -> list[TriageFinding]:
    """Every rule against one file's bytes. `evidence` is the matched line,
    which is verbatim in `text` by construction -- verified in the activity
    against the pinned commit as a drift guard (spec D5)."""
    findings: list[TriageFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        quote = line.strip()[:400]
        for rule, pattern, detail in _PROVIDER_RULES:
            if pattern.search(line):
                findings.append(_finding(
                    rule, "critical",
                    f"{detail} Rotate the credential; deleting the file does "
                    f"not revoke it.",
                    FixClass.JUDGEMENT, path, lineno, quote))
        for match in _CLIENT_BUNDLE_VAR.finditer(line):
            var = match.group(1)
            findings.append(_finding(
                "client_bundle_secret", "critical",
                f"{var} is a build-time-inlined public variable whose name "
                f"says it holds a secret. Frameworks embed these in the "
                f"client bundle, so the value ships to every browser.",
                FixClass.JUDGEMENT, path, lineno, quote))
        for match in _GENERIC_ASSIGNMENT.finditer(line):
            if _looks_random(match.group(1)):
                findings.append(_finding(
                    "generic_secret_assignment", "low",
                    "A secret-named variable is assigned a high-entropy "
                    "literal. Verify whether it is a live credential.",
                    FixClass.JUDGEMENT, path, lineno, quote))
    return findings


def env_file_findings(paths: Sequence[str]) -> list[TriageFinding]:
    """A tracked .env, split into the two halves of spec D7."""
    tracked = set(paths)
    env_files = sorted(p for p in tracked
                       if p == ".env" or (p.startswith(".env.")
                                          and p not in _ENV_EXAMPLES))
    if not env_files:
        return []
    listed = ", ".join(env_files)
    return [
        _finding(
            "secret_committed", "critical",
            f"{listed} is committed. Every value in it must be treated as "
            f"disclosed and rotated -- removing the file does not revoke "
            f"anything.",
            FixClass.JUDGEMENT, path=env_files[0]),
        # NOT "gitignore_missing_env" -- baseline owns that name for a
        # different condition (.gitignore exists but does not cover .env).
        # One rule id must mean one thing across the whole tier.
        _finding(
            "env_file_tracked", "high",
            f"{listed} is tracked; add it to .gitignore and remove it from "
            f"the index so the next secret does not follow it in.",
            FixClass.MECHANICAL, path=".gitignore"),
    ]
```

- [ ] **Step 4: Append the activity to `src/sdlc/triage/activities.py`**

Add `secrets` to the signals import:

```python
from .signals import baseline, secrets
```

Add these imports at the top:

```python
from ..grounding import Profile, verify_quote
```

Append:

```python
@activity.defn
async def triage_secrets(inp: TriageSignalInput) -> SignalResult:
    """FR-902 secret scan over the tracked tree at the pinned commit.

    Every emitted finding's evidence is re-verified against the bytes it cites
    (spec D5). For these deterministic rules the quote is verbatim by
    construction, so this is a DRIFT guard -- it catches a citation that no
    longer resolves at that path and sha -- not a hallucination guard. It
    becomes load-bearing when E-48's LLM proposers cite the same way, and it
    is FR-914's first commit-source consumer.
    """
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        findings = list(secrets.env_file_findings(paths))
        for path in paths:
            blob = read_blob(inp.repo_dir, inp.commit_sha, path)
            if blob is None or len(blob) > secrets.MAX_BLOB_BYTES:
                continue
            if "\x00" in blob:                     # binary; nothing to quote
                continue
            for finding in secrets.scan_text(path, blob):
                if finding.evidence and not verify_quote(
                        finding.evidence, blob, Profile.VERBATIM_BYTES):
                    _log.warning(
                        "triage secrets: dropping unverifiable evidence for "
                        "%s at %s", finding.rule, path)
                    continue
                findings.append(finding)
        return SignalResult(
            signal=secrets.SIGNAL_ID, version=secrets.VERSION,
            collected=Measurement.measured(float(len(findings))),
            findings=findings)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage secrets signal failed: %s", exc)
        return SignalResult(
            signal=secrets.SIGNAL_ID, version=secrets.VERSION,
            collected=Measurement.not_collected(
                f"secrets signal raised: {type(exc).__name__}: {exc}"))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_triage_secrets.py -v`
Expected: PASS (24 tests, counting parametrized cases)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/triage/signals/secrets.py src/sdlc/triage/activities.py tests/test_triage_secrets.py
git commit -m "feat(triage): secret scan incl. client-bundle reachability, evidence verified at the pinned commit"
```

---

### Task 6: `build_probe` signal + activity

**Files:**
- Create: `src/sdlc/triage/signals/build_probe.py`
- Modify: `src/sdlc/triage/activities.py` (append the activity)
- Test: `tests/test_triage_build_probe.py`

**Interfaces:**
- Consumes: Task 1 contracts, Task 2's `M_BUILDABLE` / `M_RUNNABLE`, Task 3's `detect_with_marker` / `install_cmd` / `classify_test_exit`, `sdlc.activities._bounded_shell`.
- Produces:
  - `build_probe.SIGNAL_ID = "build_probe"`, `build_probe.VERSION = 1`
  - `build_probe.StepOutcome` dataclass: `code: int`, `output: str`
  - `build_probe.interpret(toolchain_found: bool, install: StepOutcome | None, build: StepOutcome | None, test: StepOutcome | None, test_verdict: str | None) -> SignalResult` — the pure decision table
  - `@activity.defn async def triage_build_probe(inp: TriageProbeInput) -> SignalResult`
  - `activities.TriageProbeInput` dataclass: `repo_dir`, `commit_sha`, `install_timeout_s=600`, `build_timeout_s=300`, `test_timeout_s=600`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_build_probe.py`:

```python
"""The probe's decision table is pure and tested without a subprocess; the
one end-to-end test builds a real venv and is marked slow.
"""
import subprocess

import pytest

from sdlc.measurement import CollectionState
from sdlc.triage.models import M_BUILDABLE, M_RUNNABLE
from sdlc.triage.signals import build_probe as bp
from sdlc.triage.signals.build_probe import StepOutcome

TIMEOUT = StepOutcome(code=-1, output="command timed out after 600s")
OK = StepOutcome(code=0, output="")
FAIL = StepOutcome(code=1, output="ERROR: could not resolve dependency")


def _rules(r):
    return {f.rule for f in r.findings}


def test_no_toolchain_marker_is_a_finding_not_an_error():
    r = bp.interpret(toolchain_found=False, install=None, build=None,
                     test=None, test_verdict=None)
    assert _rules(r) == {"no_toolchain_marker"}
    assert r.collected.state is CollectionState.MEASURED
    for key in (M_BUILDABLE, M_RUNNABLE):
        assert r.metrics[key].state is CollectionState.NOT_COLLECTED
        assert "marker" in r.metrics[key].reason


def test_green_install_and_tests_is_measured_one_on_both():
    r = bp.interpret(True, install=OK, build=None, test=OK,
                     test_verdict="ran")
    assert r.metrics[M_BUILDABLE].value == 1.0
    assert r.metrics[M_RUNNABLE].value == 1.0
    assert r.findings == []


def test_failing_tests_still_count_as_runnable():
    # exit 1 = tests ran and failed. Runnable is about whether the suite
    # executes, not whether it passes.
    r = bp.interpret(True, install=OK, build=None,
                     test=StepOutcome(code=1, output="2 failed"),
                     test_verdict="ran")
    assert r.metrics[M_RUNNABLE].value == 1.0


def test_install_failure_is_measured_zero_and_a_finding():
    r = bp.interpret(True, install=FAIL, build=None, test=None,
                     test_verdict=None)
    assert r.metrics[M_BUILDABLE].value == 0.0
    assert "install_failed" in _rules(r)


def test_install_failure_leaves_runnable_not_collected():
    # Running a suite whose deps are absent measures the failed install a
    # second time, not runnability.
    r = bp.interpret(True, install=FAIL, build=None, test=None,
                     test_verdict=None)
    m = r.metrics[M_RUNNABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "install failed" in m.reason


def test_install_timeout_is_not_collected_not_a_measured_failure():
    r = bp.interpret(True, install=TIMEOUT, build=None, test=None,
                     test_verdict=None)
    m = r.metrics[M_BUILDABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "timed out" in m.reason
    assert "install_failed" not in _rules(r)


def test_build_failure_makes_buildable_zero():
    r = bp.interpret(True, install=OK, build=FAIL, test=None,
                     test_verdict=None)
    assert r.metrics[M_BUILDABLE].value == 0.0
    assert "build_failed" in _rules(r)


def test_no_tests_collected_leaves_runnable_not_collected():
    r = bp.interpret(True, install=OK, build=None,
                     test=StepOutcome(code=5, output="no tests ran"),
                     test_verdict="no_tests")
    m = r.metrics[M_RUNNABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "no tests" in m.reason
    # baseline owns the no_tests FINDING; the probe must not double-report it.
    assert "no_tests" not in _rules(r)


def test_suite_that_cannot_be_collected_is_measured_zero():
    r = bp.interpret(True, install=OK, build=None,
                     test=StepOutcome(code=3, output="INTERNALERROR"),
                     test_verdict="failed_to_run")
    assert r.metrics[M_RUNNABLE].value == 0.0
    assert "tests_failed_to_run" in _rules(r)


def test_test_timeout_is_not_collected():
    r = bp.interpret(True, install=OK, build=None, test=TIMEOUT,
                     test_verdict=None)
    assert r.metrics[M_RUNNABLE].state is CollectionState.NOT_COLLECTED


def test_no_install_command_leaves_buildable_not_collected():
    r = bp.interpret(True, install=None, build=None, test=OK,
                     test_verdict="ran")
    m = r.metrics[M_BUILDABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "install command" in m.reason


def test_finding_output_is_capped():
    huge = StepOutcome(code=1, output="x" * 100_000)
    r = bp.interpret(True, install=huge, build=None, test=None,
                     test_verdict=None)
    f = next(f for f in r.findings if f.rule == "install_failed")
    assert len(f.detail) <= bp.MAX_DETAIL_CHARS + 200


# ---- end to end --------------------------------------------------------

@pytest.mark.slow
@pytest.mark.asyncio
async def test_probe_runs_a_real_repo_end_to_end(tmp_path):
    from sdlc.triage.activities import TriageProbeInput, triage_build_probe

    def _run(args, cwd):
        return subprocess.run(args, cwd=cwd, capture_output=True,
                              encoding="utf-8", check=True)

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "probe-fixture"\nversion = "0.1.0"\n'
        'requires-python = ">=3.11"\n', encoding="utf-8")
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n",
                                     encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8")
    _run(["git", "init", "-q"], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "T"], tmp_path)
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "one"], tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                         capture_output=True, encoding="utf-8",
                         check=True).stdout.strip()

    r = await triage_build_probe(TriageProbeInput(
        repo_dir=str(tmp_path), commit_sha=sha))

    assert r.metrics[M_BUILDABLE].value == 1.0
    assert r.metrics[M_RUNNABLE].value == 1.0
    # D8: the probe must not have written into the repository under audit.
    assert not (tmp_path / ".sdlc-venv").exists()
    assert not list(tmp_path.glob("*.egg-info"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_triage_build_probe.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_probe' from 'sdlc.triage.signals'`

- [ ] **Step 3: Write `src/sdlc/triage/signals/build_probe.py`**

```python
"""FR-901/FR-902: does this repository build, and does its suite run?

The pure decision table lives here; the subprocess work is in the activity.
Two rules run through every branch (spec §6):

  * a TIMEOUT is not_collected, never a measured failure -- a timeout is an
    absent measurement, not a negative result;
  * a failed install leaves `runnable` not_collected and skips the test step
    entirely, because running a suite whose dependencies are missing measures
    the failed install a second time.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...measurement import Measurement
from ..models import (
    FixClass, M_BUILDABLE, M_RUNNABLE, SignalResult, TriageFinding,
)

SIGNAL_ID = "build_probe"
VERSION = 1

# Captured output is tail-capped before it enters the artifact: a failing
# `pip install` can emit megabytes, and the artifact is a report, not a log.
MAX_DETAIL_CHARS = 4000

TIMEOUT_CODE = -1          # _bounded_shell's sentinel


@dataclass
class StepOutcome:
    code: int
    output: str


def _tail(text: str) -> str:
    return text[-MAX_DETAIL_CHARS:]


def _finding(rule: str, severity: str, detail: str,
             fix_class: FixClass) -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class)


def interpret(toolchain_found: bool,
              install: StepOutcome | None,
              build: StepOutcome | None,
              test: StepOutcome | None,
              test_verdict: str | None) -> SignalResult:
    """The whole decision table, pure.

    `install`/`build`/`test` are None when the step did not run: no adapter
    command for it, or an earlier step made it meaningless. `test_verdict` is
    the adapter's classify_test_exit output, or None when the suite did not
    run or timed out.
    """
    findings: list[TriageFinding] = []

    if not toolchain_found:
        findings.append(_finding(
            "no_toolchain_marker", "high",
            "No recognized toolchain marker file at the repository root, so "
            "the build and the suite cannot be probed. Establishing a "
            "recognizable project layout is design work.",
            FixClass.STRUCTURAL))
        return SignalResult(
            signal=SIGNAL_ID, version=VERSION,
            collected=Measurement.measured(float(len(findings))),
            findings=findings,
            metrics={
                M_BUILDABLE: Measurement.not_collected(
                    "no toolchain marker resolved"),
                M_RUNNABLE: Measurement.not_collected(
                    "no toolchain marker resolved"),
            })

    # --- buildable -----------------------------------------------------
    install_ok = False
    if install is None:
        buildable = Measurement.not_collected(
            "adapter declares no install command for this marker")
    elif install.code == TIMEOUT_CODE:
        buildable = Measurement.not_collected(f"install: {install.output}")
    elif install.code != 0:
        buildable = Measurement.measured(0.0)
        findings.append(_finding(
            "install_failed", "critical",
            f"Dependency install failed (exit {install.code}). "
            f"{_tail(install.output)}",
            FixClass.JUDGEMENT))
    else:
        install_ok = True
        buildable = Measurement.measured(1.0)

    if install_ok and build is not None:
        if build.code == TIMEOUT_CODE:
            buildable = Measurement.not_collected(f"build: {build.output}")
        elif build.code != 0:
            buildable = Measurement.measured(0.0)
            findings.append(_finding(
                "build_failed", "critical",
                f"Build failed (exit {build.code}). {_tail(build.output)}",
                FixClass.JUDGEMENT))

    # --- runnable ------------------------------------------------------
    if install is not None and not install_ok:
        # Deliberate: the test step is skipped, not merely ignored.
        runnable = Measurement.not_collected(
            "install failed, so a test run would re-measure that rather than "
            "runnability")
    elif test is None:
        runnable = Measurement.not_collected(
            "adapter declares no test command")
    elif test.code == TIMEOUT_CODE:
        runnable = Measurement.not_collected(f"tests: {test.output}")
    elif test_verdict == "no_tests":
        # baseline owns the no_tests FINDING; reporting it here too would be
        # the two-implementations failure FR-902 forbids.
        runnable = Measurement.not_collected(
            "no tests were collected, so runnability was not measured")
    elif test_verdict == "failed_to_run":
        runnable = Measurement.measured(0.0)
        findings.append(_finding(
            "tests_failed_to_run", "high",
            f"The test suite could not be collected or crashed the runner "
            f"(exit {test.code}). {_tail(test.output)}",
            FixClass.JUDGEMENT))
    else:
        runnable = Measurement.measured(1.0)

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={M_BUILDABLE: buildable, M_RUNNABLE: runnable})
```

- [ ] **Step 4: Append the activity to `src/sdlc/triage/activities.py`**

Add to the imports at the top of the file:

```python
import os
import shutil
import sys
import tempfile

from ..activities import _bounded_shell
from .signals import baseline, build_probe, secrets
```

Append:

```python
@dataclass
class TriageProbeInput:
    repo_dir: str
    commit_sha: str
    install_timeout_s: int = 600
    build_timeout_s: int = 300
    test_timeout_s: int = 600


def _venv_env(venv_dir: str) -> dict[str, str]:
    bin_dir = "Scripts" if sys.platform.startswith("win") else "bin"
    venv_bin = os.path.join(venv_dir, bin_dir)
    env = dict(os.environ)
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_dir
    env.pop("PYTHONHOME", None)
    return env


@activity.defn
async def triage_build_probe(inp: TriageProbeInput) -> SignalResult:
    """FR-901's buildable/runnable dimensions.

    THIS EXECUTES THE TRIAGED REPOSITORY'S OWN CODE -- postinstall hooks,
    setup.py, build scripts -- as the worker user, with network access, and
    FR-703's egress policy is tool-level so it does not see a socket opened
    from inside that call. The trust boundary is the OPERATOR'S
    AUTHORIZATION (spec D2). E-57 (untrusted-input threat model) and E-21
    (container tier) are what remove this debt; until they land, triage must
    not be offered self-serve (NFR-9).

    Runs in a throwaway clone at the pinned commit, never the operator's
    checkout (spec D8): the artifact claims to describe commit_sha, and
    `pip install` plus a test run write into whatever directory they are
    given. The venv lives outside the clone for the same reason.

    Configure with retry_policy=RetryPolicy(maximum_attempts=1): a ten-minute
    timeout retried three times is a thirty-minute triage, and a deterministic
    build failure does not become a success on attempt two.
    """
    workdir = tempfile.mkdtemp(prefix="sdlc-triage-")
    clone = os.path.join(workdir, "repo")
    venv_dir = os.path.join(workdir, "venv")
    try:
        code, out = await _bounded_shell(
            f'git clone --local --quiet "{inp.repo_dir}" "{clone}"',
            workdir, 300)
        if code != 0:
            raise RuntimeError(f"clone failed: {out[-1000:]}")
        code, out = await _bounded_shell(
            f'git -c advice.detachedHead=false checkout --quiet '
            f'"{inp.commit_sha}"', clone, 120)
        if code != 0:
            raise RuntimeError(f"checkout of {inp.commit_sha} failed: "
                               f"{out[-1000:]}")

        found = detect_with_marker(clone)
        if found is None:
            return build_probe.interpret(False, None, None, None, None)
        adapter, marker = found

        code, out = await _bounded_shell(
            f'"{sys.executable}" -m venv "{venv_dir}"', workdir, 300)
        if code != 0:
            raise RuntimeError(f"venv creation failed: {out[-1000:]}")
        env = _venv_env(venv_dir)

        install = None
        install_command = adapter.install_cmd(marker)
        if install_command is not None:
            code, out = await _bounded_shell(
                install_command, clone, inp.install_timeout_s, env=env)
            install = build_probe.StepOutcome(code=code, output=out)

        build = None
        build_command = adapter.build_cmd()
        if build_command is not None and install is not None \
                and install.code == 0:
            code, out = await _bounded_shell(
                build_command, clone, inp.build_timeout_s, env=env)
            build = build_probe.StepOutcome(code=code, output=out)

        test = None
        verdict = None
        if install is None or install.code == 0:
            # The runner itself is installed AFTER the project's own install,
            # so its exit code never masks an install failure. A project that
            # does not declare pytest is a dependency-health finding (E-41a),
            # not a reason to leave runnability unmeasured.
            await _bounded_shell(
                "pip install -q pytest", clone, inp.install_timeout_s, env=env)
            code, out = await _bounded_shell(
                adapter.test_cmd(coverage=False), clone, inp.test_timeout_s,
                env=env)
            test = build_probe.StepOutcome(code=code, output=out)
            if code != build_probe.TIMEOUT_CODE:
                verdict = adapter.classify_test_exit(code)

        return build_probe.interpret(True, install, build, test, verdict)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage build probe failed: %s", exc)
        return SignalResult(
            signal=build_probe.SIGNAL_ID, version=build_probe.VERSION,
            collected=Measurement.not_collected(
                f"build probe raised: {type(exc).__name__}: {exc}"))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
```

- [ ] **Step 5: Run the fast tests**

Run: `pytest tests/test_triage_build_probe.py -v`
Expected: PASS (12 tests). The `slow` end-to-end test is excluded by the default `addopts`.

- [ ] **Step 6: Run the slow end-to-end test**

Run: `pytest tests/test_triage_build_probe.py -v -m slow`
Expected: PASS (1 test). It builds a real venv and runs a real `pip install`, so it takes tens of seconds.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/triage/signals/build_probe.py src/sdlc/triage/activities.py tests/test_triage_build_probe.py
git commit -m "feat(triage): build/run probe in a throwaway clone at the pinned commit"
```

---

### Task 7: Signal registry, worker registration, docs

**Files:**
- Create: `src/sdlc/triage/registry.py`
- Modify: `src/sdlc/worker.py:28-33` (imports) and `src/sdlc/worker.py:88-111` (activities list)
- Modify: `ROADMAP.md`
- Test: `tests/test_triage_registry.py`

**Interfaces:**
- Consumes: all three signal modules and their activities.
- Produces: `SignalSpec`, `SIGNALS: dict[str, SignalSpec]` — E-42's `TriageWorkflow` iterates this to know what to run.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_registry.py`:

```python
"""The registry is the one place that says which signals exist. It must not
be able to drift from the modules it names."""
from sdlc.triage import activities as triage_activities
from sdlc.triage.registry import SIGNALS, SignalSpec
from sdlc.triage.signals import baseline, build_probe, secrets

_MODULES = {"baseline": baseline, "secrets": secrets,
            "build_probe": build_probe}


def test_registry_covers_exactly_the_three_signals():
    assert set(SIGNALS) == set(_MODULES)


def test_each_spec_matches_its_module_id_and_version():
    for signal_id, spec in SIGNALS.items():
        module = _MODULES[signal_id]
        assert spec.id == module.SIGNAL_ID
        assert spec.version == module.VERSION


def test_each_spec_names_a_real_activity_function():
    for spec in SIGNALS.values():
        fn = getattr(triage_activities, spec.activity, None)
        assert callable(fn), f"{spec.activity} is not defined"


def test_every_registered_signal_is_registered_on_the_worker():
    from sdlc import worker
    import inspect

    source = inspect.getsource(worker)
    for spec in SIGNALS.values():
        assert spec.activity in source, (
            f"{spec.activity} is not registered in worker.py")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_triage_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.triage.registry'`

- [ ] **Step 3: Write `src/sdlc/triage/registry.py`**

```python
"""The declared set of triage signals (FR-902).

One entry per signal, and `version` is what E-46 will fold into its
`(tree hash, signal version)` memo key -- bumping a signal's version
invalidates exactly that signal's cached result and nothing else.
"""
from __future__ import annotations

from pydantic import BaseModel

from .signals import baseline, build_probe, secrets


class SignalSpec(BaseModel):
    id: str
    version: int
    activity: str          # the @activity.defn name in triage/activities.py


SIGNALS: dict[str, SignalSpec] = {
    baseline.SIGNAL_ID: SignalSpec(
        id=baseline.SIGNAL_ID, version=baseline.VERSION,
        activity="triage_baseline"),
    secrets.SIGNAL_ID: SignalSpec(
        id=secrets.SIGNAL_ID, version=secrets.VERSION,
        activity="triage_secrets"),
    build_probe.SIGNAL_ID: SignalSpec(
        id=build_probe.SIGNAL_ID, version=build_probe.VERSION,
        activity="triage_build_probe"),
}
```

- [ ] **Step 4: Register the activities in `src/sdlc/worker.py`**

Add this import after the `from .research.verify import verify_brief_activity` line:

```python
from .triage.activities import (
    triage_baseline, triage_build_probe, triage_secrets,
)
```

Add to the `activities=[...]` list, after the `synthesize_brief,` line:

```python
            triage_baseline, triage_secrets, triage_build_probe,
```

- [ ] **Step 5: Run the registry test and the whole fast suite**

Run: `pytest tests/test_triage_registry.py -v`
Expected: PASS (4 tests)

Run: `pytest`
Expected: PASS — the full fast suite, with no regressions from the `detect`/`detect_with_marker` refactor in Task 3.

- [ ] **Step 6: Update `ROADMAP.md`**

Replace the `E-41` bullet in §10 (currently starting `- [ ] **E-41 — deterministic hygiene signals**`) with:

```markdown
- [ ] ⚠️ **E-41 — deterministic hygiene signals** → FR-902, FR-108.
  *Contracts + seam + three signals landed (2026-08-06):* `src/sdlc/triage/`
  ships `RepoTriage`/`TriageFinding`/`Readiness` (closing the half **E-40**
  deferred here), a one-activity-per-signal seam, and **build probe**,
  **secret scan** (including client-bundle-reachable credentials) and
  **baseline practice**. Readiness is three-valued: any dimension that is not
  MEASURED forces `INDETERMINATE`, so an unmeasured repository can never read
  as ready for the FR-903 gate. The build probe **executes the triaged
  repository's own code** in a throwaway clone at the pinned commit — an
  operator-authorization trust boundary, not a solved one (see NFR-9; removed
  by E-57/E-21). Remaining four families are **E-41a–d**. Spec
  `docs/superpowers/specs/2026-08-06-repository-triage-hygiene-signals-design.md`,
  plan `docs/superpowers/plans/2026-08-06-repository-triage-hygiene-signals.md`.
- [ ] **E-41a** dependency health — unpinned / known-vulnerable / unused /
  duplicated, behind the FR-108 adapter.
- [ ] **E-41b** dead and generator-scaffold code. Also sharpens
  `structure_discernible`, which E-41 ships as a deliberate floor (a repository
  that is entirely untouched scaffolding currently passes it).
- [ ] **E-41c** framework-default misconfiguration — unauthenticated routes,
  permissive CORS, world-readable storage.
- [ ] **E-41d** size and duplication outliers.
```

In §10, replace the `E-40` bullet's closing sentence — `**`RepoTriage` deferred to E-41**, where the signals that populate it are designed. FR-915 stays open until then.` — with:

```markdown
  **`RepoTriage` landed with E-41** (2026-08-06), where the signals that
  populate it are designed. FR-915's triage half is therefore closed.
```

In §2, replace the FR-902 line with:

```markdown
- [ ] ⚠️ **FR-902** hygiene signal set via FR-108 adapters, one implementation
  per signal — three of seven landed (build probe, secrets incl. client-bundle
  reachability, baseline practice); dependency health, dead/scaffold code,
  framework misconfig and size/duplication outliers are E-41a–d.
```

In §2, append to the FR-901 line: `*Artifact landed with E-41 (2026-08-06); the stage and the readiness gate are E-42.*`

In §2, append to the FR-914 line, replacing `stays open until an assessment stage consumes the `read_committed_bytes` commit source`: `the commit source gained its first consumer with E-41's secrets signal (2026-08-06), which re-verifies every emitted evidence quote against the pinned commit; stays open until an LLM-proposing assessment stage cites the same way, which is where the check stops being a drift guard.`

In §3, append to the NFR-9 line: `**E-41's build probe is the first stage that knowingly executes a foreign repository's code** (bounded, in a throwaway clone, as the worker user with network access). Operator-run only until E-57/E-21.`

- [ ] **Step 7: Commit**

```bash
git add -f src/sdlc/triage/registry.py src/sdlc/worker.py tests/test_triage_registry.py ROADMAP.md
git commit -m "feat(triage): signal registry, worker registration, roadmap update

Closes E-40's deferred RepoTriage half and lands three of E-41's seven signal
families. E-41a-d opened for the rest."
```

---

## Self-Review Notes

Checked against the spec, 2026-08-06:

- **Spec coverage.** §3 layout → Tasks 1/4/5/6/7. §4 contracts → Tasks 1–2. §5 adapter extension → Task 3. §6 build probe (clone, bounds, timeout and install-failure rules) → Task 6. §7 secrets (both rule classes, D7 split) → Task 5. §8 baseline (incl. `find_test_files` single implementation) → Task 4. §9 error handling → per-activity `except` in Tasks 4/5/6; the `maximum_attempts=1` requirement is documented in `triage_build_probe`'s docstring, since the retry policy is set by E-42's workflow, which is out of scope here. §10 all seven test obligations → obligations 1–6 are covered across Tasks 1/2/4/5, obligation 7 (`classify_test_exit` mapping) is Task 3. §12 roadmap consequences → Task 7 Step 6.
- **Known gap, deliberate.** The spec's `RepoTriage` assembly (one artifact combining all three `SignalResult`s plus `compute_readiness`) has no task: nothing assembles it until E-42's `TriageWorkflow`, and building an assembler with no caller would be the mistake D1 warns about. `RepoTriage` and `compute_readiness` are both defined and tested, so E-42 assembles rather than designs.
- **Type consistency.** `SignalResult.metrics` keys use the `M_*` constants everywhere (Tasks 2/4/6). `StepOutcome` is used identically in `build_probe.interpret` and `triage_build_probe`. `TriageSignalInput` (baseline, secrets) and `TriageProbeInput` (probe) are distinct because only the probe carries timeouts.
