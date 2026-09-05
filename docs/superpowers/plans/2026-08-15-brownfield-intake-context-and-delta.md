# E-84 Brownfield Intake, Context, and the Checked Delta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `IdeaBrief.mode` load-bearing — a brownfield feature run verifies its repository, builds a `CodebaseMap` from the assessment tier's own scan, and has its architecture delta checked against the real tree before a plan exists.

**Architecture:** `AssessmentWorkflow._scan`'s body lifts to a shared `scan_tree()` that `FeatureWorkflow` calls with `triage=None`, so both tiers extract through one code path and one memo. A pure `project()` turns `ScanResult` into a prompt-sized `CodebaseMap`; a pure `check_delta()` resolves the Architect's `added`/`modified`/`removed` paths against the tree at the pinned commit, supplied activity-side.

**Tech Stack:** Python 3.12, Pydantic v2, Temporal (`temporalio`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-15-brownfield-intake-context-and-delta-design.md`

## Global Constraints

- **Pure modules stay pure.** `context/classify.py`, `context/project.py`, `context/delta.py`, `context/render.py` import Pydantic, `measurement`, `gate`, and assessment *models* only. Never `temporalio`, never `activities.py`. A dependency here must show up as a reviewable import.
- **Dependency direction is one-way:** `context/` imports `models.py`; `models.py` never imports `context/`. `BrownfieldDelta` therefore lives in root `models.py` (spec D2).
- **Every pure module carries an order-independence test** — byte-identical `model_dump_json()` across shuffled inputs, 5 shuffles, following `tests/test_discover_apply.py:150` (NFR-10).
- **`Measurement` never defaults to zero.** A signal that did not collect yields `Measurement.not_collected(reason)`; `MEASURED` requires a finite value (FR-915).
- **Paths are repo-relative POSIX.** Forward slashes, no leading `./`, no leading separator. Normalization must never match on basename or suffix (spec D9).
- **Check name:** `brownfield_delta_grounded`. It is **not** added to `ABSOLUTE_FLOOR` — that frozenset governs the merge gate; this check fails its own stage.
- **Run the full suite before each commit:** `python -m pytest -q` (temporal e2e tests are marked and excluded by default).

---

### Task 1: Intake contracts and the classify rule

**Files:**
- Create: `src/sdlc/context/__init__.py`
- Create: `src/sdlc/context/models.py`
- Create: `src/sdlc/context/classify.py`
- Test: `tests/test_context_classify.py`

**Interfaces:**
- Consumes: `ProjectMode` from `sdlc.models`.
- Produces: `RepoObservation`, `IntakeVerdict`, `classify(observed: RepoObservation, declared: ProjectMode) -> IntakeVerdict`.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D3: intake verifies the declared mode; the asymmetry is the point."""

from __future__ import annotations

from sdlc.context.classify import classify
from sdlc.context.models import RepoObservation
from sdlc.models import ProjectMode


def _repo(**over) -> RepoObservation:
    base = dict(
        is_git_repo=True, base_branch_resolves=True, commit_sha="a" * 40, source_file_count=12
    )
    return RepoObservation(**{**base, **over})


def test_a_healthy_brownfield_repo_is_admitted():
    v = classify(_repo(), ProjectMode.BROWNFIELD)
    assert v.ok is True
    assert v.mode is ProjectMode.BROWNFIELD
    assert v.warning == ""


def test_brownfield_against_a_non_repository_fails_closed():
    v = classify(_repo(is_git_repo=False), ProjectMode.BROWNFIELD)
    assert v.ok is False
    assert "not a git repository" in v.reason


def test_brownfield_against_an_empty_tree_fails_closed():
    v = classify(_repo(source_file_count=0), ProjectMode.BROWNFIELD)
    assert v.ok is False
    assert "no source files" in v.reason


def test_brownfield_needs_its_base_branch_to_resolve():
    v = classify(_repo(base_branch_resolves=False), ProjectMode.BROWNFIELD)
    assert v.ok is False
    assert "base branch" in v.reason


def test_greenfield_against_a_populated_tree_warns_but_continues():
    """D3's asymmetry: the greenfield claim carries no invariant, and failing
    it would break existing runs and benchmark cases for nothing."""
    v = classify(_repo(source_file_count=40), ProjectMode.GREENFIELD)
    assert v.ok is True
    assert "40 source file(s)" in v.warning


def test_greenfield_against_an_empty_tree_is_silent():
    v = classify(_repo(source_file_count=0), ProjectMode.GREENFIELD)
    assert v.ok is True
    assert v.warning == ""


def test_a_failing_verdict_keeps_the_declared_mode():
    """The verdict reports what was declared; it never silently reclassifies."""
    v = classify(_repo(is_git_repo=False), ProjectMode.BROWNFIELD)
    assert v.mode is ProjectMode.BROWNFIELD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context_classify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.context'`

- [ ] **Step 3: Write the implementation**

`src/sdlc/context/__init__.py`:

```python
"""E-84: brownfield intake and the codebase map (FR-102, DAG stages 0 and 2)."""
```

`src/sdlc/context/models.py`:

```python
"""E-84 contracts. Pure -- Pydantic, measurement, and assessment models only.

BrownfieldDelta is deliberately NOT here: it is a field of ArchitectureSpec, so
it lives in root models.py. Siting it here would invert the dependency
direction (D2) and open the cycle models.py -> context -> assessment -> triage
-> models.py.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..models import ProjectMode


class RepoObservation(BaseModel):
    """What stage 0's activity saw. Facts only -- the verdict is classify's.

    `source_file_count` counts SOURCE_EXTENSIONS blobs, the same definition
    E-47b's coverage denominator uses: intake decides a repository is mappable
    and the scan decides what it can map, so two definitions of "has code"
    would let a repository pass intake and then produce an empty map.
    """

    is_git_repo: bool
    base_branch_resolves: bool
    commit_sha: str = ""
    source_file_count: int = 0
    reason: str = ""


class IntakeVerdict(BaseModel):
    """Stage 0's output. `mode` is what was DECLARED -- intake verifies a
    declaration, it never reclassifies behind the operator's back."""

    mode: ProjectMode
    ok: bool
    warning: str = ""
    reason: str = ""
```

`src/sdlc/context/classify.py`:

```python
"""E-84 D3: verify the declared mode against the repository.

Deterministic and no-LLM, which is what SDLC-spec-v2's stage 0 row
("mode in {greenfield, brownfield} resolved") can mean when IdeaBrief.mode is
already a required field: the mode is declared, and this decides whether the
declaration survives contact with the tree.
"""

from __future__ import annotations

from ..models import ProjectMode
from .models import IntakeVerdict, RepoObservation


def classify(observed: RepoObservation, declared: ProjectMode) -> IntakeVerdict:
    """The verdict for a declared mode against an observed repository.

    The asymmetry between the two modes is deliberate (D3). A brownfield run
    without a tree is not a weaker run but an ungrounded one -- the map, the
    delta and the check all rest on it, so it fails closed. Greenfield means
    only that "the Architect owns stack + file tree" (ARCHITECTURE.md:85),
    which stays coherent against a repository holding a README, a licence, CI
    config, or a previous run's work. Failing that would break existing runs
    for no invariant, so it warns.
    """
    if declared is ProjectMode.BROWNFIELD:
        if not observed.is_git_repo:
            return IntakeVerdict(
                mode=declared,
                ok=False,
                reason=f"brownfield declared, but the path is not a git "
                f"repository{_because(observed)}",
            )
        if not observed.base_branch_resolves:
            return IntakeVerdict(
                mode=declared,
                ok=False,
                reason=f"brownfield declared, but the base branch does not "
                f"resolve{_because(observed)}",
            )
        if observed.source_file_count == 0:
            return IntakeVerdict(
                mode=declared,
                ok=False,
                reason="brownfield declared, but the tree has no source files "
                "-- there is nothing to map",
            )
        return IntakeVerdict(mode=declared, ok=True)

    warning = ""
    if observed.is_git_repo and observed.source_file_count > 0:
        warning = (
            f"greenfield declared against a tree holding "
            f"{observed.source_file_count} source file(s); the "
            f"Architect owns the file tree and will not see them"
        )
    return IntakeVerdict(mode=declared, ok=True, warning=warning)


def _because(observed: RepoObservation) -> str:
    return f": {observed.reason}" if observed.reason.strip() else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_context_classify.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/context/ tests/test_context_classify.py
git commit -m "feat(context): intake verifies the declared mode, asymmetrically (E-84 D3)"
```

---

### Task 2: The `classify_repo` activity

**Files:**
- Modify: `src/sdlc/activities.py` (append; it already owns `setup_integration_branch`)
- Modify: `src/sdlc/worker.py:28-33` (import) and `:125-141` (registration list)
- Test: `tests/test_context_classify_activity.py`

**Interfaces:**
- Consumes: `RepoObservation` from Task 1; `SOURCE_EXTENSIONS` from `sdlc.assessment.scan.sources`.
- Produces: `RepoProbeInput(repo_dir: str, base_branch: str)`, `async def classify_repo(inp: RepoProbeInput) -> RepoObservation`.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D3: the observation half of intake, against real git repositories."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.activities import RepoProbeInput, classify_repo


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def empty_repo(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    _git("init", "-b", "main", cwd=d)
    _git("config", "user.email", "t@t.t", cwd=d)
    _git("config", "user.name", "t", cwd=d)
    (d / "README.md").write_text("# hi\n")
    _git("add", ".", cwd=d)
    _git("commit", "-m", "init", cwd=d)
    return d


@pytest.fixture
def source_repo(empty_repo):
    (empty_repo / "app.py").write_text("x = 1\n")
    (empty_repo / "util.ts").write_text("export const y = 2;\n")
    _git("add", ".", cwd=empty_repo)
    _git("commit", "-m", "code", cwd=empty_repo)
    return empty_repo


@pytest.mark.asyncio
async def test_a_repo_with_source_is_observed_as_such(source_repo):
    got = await classify_repo(RepoProbeInput(repo_dir=str(source_repo), base_branch="main"))
    assert got.is_git_repo is True
    assert got.base_branch_resolves is True
    assert got.source_file_count == 2
    assert len(got.commit_sha) == 40


@pytest.mark.asyncio
async def test_readme_only_is_not_source(empty_repo):
    """SOURCE_EXTENSIONS, not "any file" -- a docs-only repo has nothing to
    map, and intake must agree with the scan about that."""
    got = await classify_repo(RepoProbeInput(repo_dir=str(empty_repo), base_branch="main"))
    assert got.is_git_repo is True
    assert got.source_file_count == 0


@pytest.mark.asyncio
async def test_a_missing_path_is_not_a_repo_and_never_raises(tmp_path):
    got = await classify_repo(RepoProbeInput(repo_dir=str(tmp_path / "nope"), base_branch="main"))
    assert got.is_git_repo is False
    assert got.reason != ""


@pytest.mark.asyncio
async def test_a_missing_base_branch_is_reported_not_raised(source_repo):
    got = await classify_repo(RepoProbeInput(repo_dir=str(source_repo), base_branch="nonexistent"))
    assert got.is_git_repo is True
    assert got.base_branch_resolves is False
    assert got.reason != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context_classify_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'RepoProbeInput' from 'sdlc.activities'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/activities.py`. Match the file's existing `_git`/subprocess helpers — if a module-level git helper already exists, call it instead of re-declaring one.

```python
class RepoProbeInput(BaseModel):
    repo_dir: str
    base_branch: str = "main"


@activity.defn
async def classify_repo(inp: RepoProbeInput) -> RepoObservation:
    """E-84 D3: observe a repository. Facts only; classify() decides.

    Never raises. An unreachable path, a missing branch and a broken git are
    all observations intake turns into a verdict with a reason -- raising here
    would make "the path is wrong" indistinguishable from "the worker died",
    which is the retry policy's business, not intake's.
    """
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=inp.repo_dir,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return RepoObservation(
            is_git_repo=False,
            base_branch_resolves=False,
            reason=(probe.stderr.strip() or f"{inp.repo_dir!r} is not reachable")[:300],
        )

    rev = subprocess.run(
        ["git", "rev-parse", "--verify", f"{inp.base_branch}^{{commit}}"],
        cwd=inp.repo_dir,
        capture_output=True,
        text=True,
    )
    if rev.returncode != 0:
        return RepoObservation(
            is_git_repo=True,
            base_branch_resolves=False,
            reason=(rev.stderr.strip() or f"branch {inp.base_branch!r} does not resolve")[:300],
        )
    commit_sha = rev.stdout.strip()

    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit_sha],
        cwd=inp.repo_dir,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return RepoObservation(
            is_git_repo=True,
            base_branch_resolves=True,
            commit_sha=commit_sha,
            reason=(listing.stderr.strip() or "could not list the tree")[:300],
        )

    count = sum(1 for p in listing.stdout.splitlines() if p.strip().endswith(SOURCE_EXTENSIONS))
    return RepoObservation(
        is_git_repo=True, base_branch_resolves=True, commit_sha=commit_sha, source_file_count=count
    )
```

Add the imports at the top of `activities.py`:

```python
from .assessment.scan.sources import SOURCE_EXTENSIONS
from .context.models import RepoObservation
```

- [ ] **Step 4: Register the activity on the worker**

In `src/sdlc/worker.py`, add `classify_repo` to the `from .activities import (...)` block (line 28) keeping alphabetical order, and add it to the `activities=[...]` list (around line 125) beside `setup_integration_branch`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_context_classify_activity.py -v && python -m pytest -q`
Expected: PASS (4 new tests); full suite green

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/activities.py src/sdlc/worker.py tests/test_context_classify_activity.py
git commit -m "feat(context): classify_repo observes, never raises (E-84 D3)"
```

---

### Task 3: `CodebaseMap` and the projection

**Files:**
- Modify: `src/sdlc/context/models.py` (append the map contracts)
- Create: `src/sdlc/context/project.py`
- Test: `tests/test_context_project.py`

**Interfaces:**
- Consumes: `ScanResult`, `ScanCandidate`, `CandidateMember`, `MemberKind`, `Confidence`, `ScanSignalId`, `TestabilityFinding`, `CoverageRecord` from `sdlc.assessment.scan.models`; `CONTRACT_KINDS` from `sdlc.assessment.discover.models`.
- Produces: `MapModule`, `MapContract`, `HotSpot`, `CodebaseMap`, `project(scan: ScanResult, tree_hash: str, commit_sha: str) -> CodebaseMap`, `map_digest(m: CodebaseMap) -> str`.

**Note on `CONTRACT_KINDS`:** import it, do not restate it. `discover/models.py:146-155` defines it as "something the system DOES, reachable from outside the capability", which is exactly the spec's stage-2 sense of *contracts*. That file's warning is against *deriving* one set from another when the two mean different things; here they mean the same thing, so one definition with one authority is the point.

- [ ] **Step 1: Write the failing test**

```python
"""E-84: ScanResult -> CodebaseMap. The map is what the Architect reads."""

from __future__ import annotations

import random

from sdlc.assessment.scan.models import (
    SCAN_ORDER,
    CandidateMember,
    Confidence,
    CoverageRecord,
    MemberKind,
    ScanCandidate,
    ScanResult,
    ScanSignalId,
    ScanSignalResult,
    SignalSource,
    TestabilityFinding,
    family_of,
)
from sdlc.context.project import map_digest, project
from sdlc.measurement import CollectionState, Measurement


def _row(sid: ScanSignalId, ok: bool = True) -> ScanSignalResult:
    m = Measurement.measured(1.0) if ok else Measurement.not_collected(f"{sid.value} could not run")
    return ScanSignalResult(
        signal=sid, family=family_of(sid), version=1, source=SignalSource.COMPUTED, collected=m
    )


def _scan(
    *, s5_ok=True, qs2_ok=True, qs3_ok=True, candidates=None, testability=(), coverage=()
) -> ScanResult:
    ok = {ScanSignalId.S5: s5_ok, ScanSignalId.QS2: qs2_ok, ScanSignalId.QS3: qs3_ok}
    return ScanResult(
        signals=[_row(sid, ok.get(sid, True)) for sid in SCAN_ORDER],
        candidates=list(candidates or []),
        testability=list(testability),
        coverage=list(coverage),
    )


def _candidate(cid="C-01", name="payments") -> ScanCandidate:
    return ScanCandidate(
        candidate_id=cid,
        name=name,
        sources=["s1-1"],
        confidence=Confidence.LOW,
        members=[
            CandidateMember(
                kind=MemberKind.HTTP_ROUTE,
                value="POST /api/payments",
                path="src/payments/api.py",
                line=12,
            ),
            CandidateMember(
                kind=MemberKind.FILE_PATH,
                value="src/payments/store.py",
                path="src/payments/store.py",
            ),
        ],
    )


def test_modules_come_from_the_merged_candidates():
    m = project(_scan(candidates=[_candidate()]), "tree1", "c" * 40)
    assert [x.name for x in m.modules] == ["payments"]
    assert m.modules[0].member_paths == ("src/payments/api.py", "src/payments/store.py")
    assert m.collected.state is CollectionState.MEASURED


def test_contracts_are_the_externally_reachable_members_only():
    """CONTRACT_KINDS: a route is a contract, a file path is not."""
    m = project(_scan(candidates=[_candidate()]), "tree1", "c" * 40)
    assert [c.value for c in m.contracts] == ["POST /api/payments"]
    assert m.contracts[0].path == "src/payments/api.py"
    assert m.contracts[0].line == 12


def test_s5_not_collected_yields_an_empty_map_that_says_why():
    """FR-915: an empty module list must not read as "no modules"."""
    m = project(_scan(s5_ok=False), "tree1", "c" * 40)
    assert m.modules == ()
    assert m.modules_collected.state is CollectionState.NOT_COLLECTED
    assert "S5" in m.modules_collected.reason
    assert m.collected.state is CollectionState.NOT_COLLECTED


def test_hot_spots_carry_their_source():
    finding = TestabilityFinding(
        severity="blocks",
        pattern="static-clock-access",
        detail="reads the wall clock directly",
        recommended_seam="inject a clock",
        path="src/payments/api.py",
        line=9,
    )
    record = CoverageRecord(
        scope="file",
        path="src/payments/store.py",
        covered=Measurement.measured(12.0),
        source="report",
        tool="cobertura",
        confidence=Confidence.HIGH,
    )
    m = project(
        _scan(candidates=[_candidate()], testability=[finding], coverage=[record]),
        "tree1",
        "c" * 40,
    )
    assert {h.source for h in m.hot_spots} == {"testability", "coverage"}
    assert m.hot_spots_collected.state is CollectionState.MEASURED


def test_hot_spots_not_collected_when_neither_contributor_ran():
    m = project(_scan(candidates=[_candidate()], qs2_ok=False, qs3_ok=False), "tree1", "c" * 40)
    assert m.hot_spots == ()
    assert m.hot_spots_collected.state is CollectionState.NOT_COLLECTED
    assert "QS2" in m.hot_spots_collected.reason
    assert "QS3" in m.hot_spots_collected.reason


def test_a_partial_contributor_still_measures_and_stays_inspectable():
    """QS3 ran, QS2 did not: hot spots exist, and each record's `source`
    is what makes the partiality visible rather than hidden."""
    finding = TestabilityFinding(
        severity="smell", pattern="p", detail="d", recommended_seam="s", path="src/a.py"
    )
    m = project(
        _scan(candidates=[_candidate()], testability=[finding], qs2_ok=False), "tree1", "c" * 40
    )
    assert [h.source for h in m.hot_spots] == ["testability"]
    assert m.hot_spots_collected.state is CollectionState.MEASURED


def test_projection_is_order_independent():
    """NFR-10: byte-identical whatever order the records arrive in."""
    cands = [_candidate("C-01", "payments"), _candidate("C-02", "orders")]
    findings = [
        TestabilityFinding(
            severity="smell", pattern=f"p{i}", detail="d", recommended_seam="s", path=f"src/{i}.py"
        )
        for i in range(4)
    ]
    first = project(
        _scan(candidates=cands, testability=findings), "tree1", "c" * 40
    ).model_dump_json()
    for _ in range(5):
        c, f = cands[:], findings[:]
        random.shuffle(c)
        random.shuffle(f)
        assert (
            project(_scan(candidates=c, testability=f), "tree1", "c" * 40).model_dump_json()
            == first
        )


def test_the_digest_moves_with_content_and_not_with_order():
    cands = [_candidate("C-01", "payments"), _candidate("C-02", "orders")]
    a = map_digest(project(_scan(candidates=cands), "tree1", "c" * 40))
    b = map_digest(project(_scan(candidates=cands[::-1]), "tree1", "c" * 40))
    c = map_digest(project(_scan(candidates=[_candidate("C-01", "billing")]), "tree1", "c" * 40))
    assert a == b
    assert a != c
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context_project.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.context.project'`

- [ ] **Step 3: Append the contracts to `src/sdlc/context/models.py`**

```python
from typing import Literal

from pydantic import Field, model_validator

from ..assessment.scan.models import Confidence, MemberKind
from ..measurement import CollectionState, Measurement


class MapModule(BaseModel):
    """One S5-merged candidate, as the Architect sees it."""

    model_config = {"frozen": True}
    name: str
    member_paths: tuple[str, ...] = ()
    confidence: Confidence


class MapContract(BaseModel):
    """One externally-reachable member: a route, a command, a topic."""

    model_config = {"frozen": True}
    kind: MemberKind
    value: str
    path: str
    line: int | None = None


class HotSpot(BaseModel):
    """A place the Architect should look before proposing a change.

    `source` is what keeps partial collection inspectable: when QS3 ran and
    QS2 did not, the hot spots that exist say which signal produced them
    rather than presenting as a complete set.
    """

    model_config = {"frozen": True}
    path: str
    source: Literal["testability", "coverage"]
    reason: str
    metric: Measurement


class CodebaseMap(BaseModel):
    """FR-102's stage 2 artifact: modules, contracts and hot spots extracted
    from the tree at a pinned commit.

    Deliberately does NOT carry the tree's path list. The delta resolves
    against git activity-side (D8) because a large repository's full listing
    would bloat every run's history against ADR-10 and push this past the
    Architect's context_budget_tokens (FR-801).
    """

    tree_hash: str
    commit_sha: str
    modules: tuple[MapModule, ...] = ()
    contracts: tuple[MapContract, ...] = ()
    hot_spots: tuple[HotSpot, ...] = ()
    modules_collected: Measurement
    contracts_collected: Measurement
    hot_spots_collected: Measurement
    collected: Measurement

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "CodebaseMap":
        if self.collected.state is not CollectionState.MEASURED:
            if self.modules or self.contracts or self.hot_spots:
                raise ValueError(
                    f"collected={self.collected.state.value} carries no "
                    f"payload, but modules/contracts/hot_spots are present "
                    f"-- a context stage that did not collect has nothing to "
                    f"show (FR-915)"
                )
        return self
```

- [ ] **Step 4: Write `src/sdlc/context/project.py`**

```python
"""E-84: ScanResult -> CodebaseMap.

A projection, not an extraction. Every fact here was produced by the scan
signals E-46 built; this module chooses which of them the Architect needs and
in what order. Building a second extractor over the same tree would yield two
maps that can disagree about one repository, with no rule for which is right
(D1).

Pure: no temporalio, no activities, no I/O.
"""

from __future__ import annotations

import hashlib

from ..assessment.discover.models import CONTRACT_KINDS
from ..assessment.scan.models import ScanResult, ScanSignalId
from ..measurement import CollectionState, Measurement
from .models import CodebaseMap, HotSpot, MapContract, MapModule


def _row_collected(scan: ScanResult, sid: ScanSignalId) -> Measurement:
    """One signal's collection state, or a not_collected naming its absence."""
    row = next((r for r in scan.signals if r.signal is sid), None)
    if row is None:
        return Measurement.not_collected(f"{sid.value} is not present in this scan")
    return row.collected


def _reason(m: Measurement, sid: ScanSignalId) -> str:
    return f"{sid.value}: {m.reason or m.state.value}"


def project(scan: ScanResult, tree_hash: str, commit_sha: str) -> CodebaseMap:
    """The map for one scanned tree.

    Modules and contracts share ONE collection state because they share one
    source: both are read off S5's merged candidates, so a claim that
    contracts collected while modules did not would be a claim about nothing.
    Hot spots have their own, because QS2 and QS3 degrade independently.
    """
    s5 = _row_collected(scan, ScanSignalId.S5)
    if s5.state is CollectionState.MEASURED:
        modules = tuple(
            sorted(
                (
                    MapModule(
                        name=c.name,
                        member_paths=tuple(sorted({m.path for m in c.members if m.path})),
                        confidence=c.confidence,
                    )
                    for c in scan.candidates
                ),
                key=lambda x: (x.name, x.member_paths),
            )
        )
        contracts = tuple(
            sorted(
                (
                    MapContract(kind=m.kind, value=m.value, path=m.path, line=m.line)
                    for c in scan.candidates
                    for m in c.members
                    if m.kind in CONTRACT_KINDS
                ),
                key=lambda x: (x.kind.value, x.value, x.path, x.line or 0),
            )
        )
        members = Measurement.measured(float(len(modules)))
        contracts_collected = Measurement.measured(float(len(contracts)))
    else:
        modules, contracts = (), ()
        members = Measurement.not_collected(f"no modules: {_reason(s5, ScanSignalId.S5)}")
        contracts_collected = Measurement.not_collected(
            f"no contracts: {_reason(s5, ScanSignalId.S5)}"
        )

    qs2 = _row_collected(scan, ScanSignalId.QS2)
    qs3 = _row_collected(scan, ScanSignalId.QS3)
    if qs2.state is CollectionState.MEASURED or qs3.state is CollectionState.MEASURED:
        spots: list[HotSpot] = []
        if qs3.state is CollectionState.MEASURED:
            spots.extend(
                HotSpot(
                    path=f.path,
                    source="testability",
                    reason=f"{f.severity}: {f.pattern}",
                    metric=Measurement.measured(float(_SEVERITY_RANK[f.severity])),
                )
                for f in scan.testability
            )
        if qs2.state is CollectionState.MEASURED:
            spots.extend(
                HotSpot(
                    path=r.path,
                    source="coverage",
                    reason=f"coverage from {r.source}{' (' + r.tool + ')' if r.tool else ''}",
                    metric=r.covered,
                )
                for r in scan.coverage
                if r.scope == "file" and r.covered.state is CollectionState.MEASURED
            )
        hot_spots = tuple(sorted(spots, key=lambda h: (h.path, h.source, h.reason)))
        hot_collected = Measurement.measured(float(len(hot_spots)))
    else:
        hot_spots = ()
        hot_collected = Measurement.not_collected(
            f"no hot spots: {_reason(qs2, ScanSignalId.QS2)}; {_reason(qs3, ScanSignalId.QS3)}"
        )

    # The map's defining content is its modules: without them there is nothing
    # for the delta to be grounded against, which is what D6 fails closed on.
    collected = (
        Measurement.measured(float(len(modules)))
        if members.state is CollectionState.MEASURED
        else Measurement.not_collected(members.reason)
    )
    return CodebaseMap(
        tree_hash=tree_hash,
        commit_sha=commit_sha,
        modules=modules,
        contracts=contracts,
        hot_spots=hot_spots,
        modules_collected=members,
        contracts_collected=contracts_collected,
        hot_spots_collected=hot_collected,
        collected=collected,
    )


_SEVERITY_RANK = {"blocks": 3, "impedes": 2, "smell": 1}


def map_digest(m: CodebaseMap) -> str:
    """A canonical digest for the architect memo key (D11).

    Digests the model rather than hand-listing fields, following brief_digest
    and E-48's context_digest: a field added later cannot escape the key.
    Canonical because project() sorts every collection it emits, which
    test_projection_is_order_independent asserts as byte-identical JSON.
    """
    return hashlib.sha256(m.model_dump_json().encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_context_project.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/context/models.py src/sdlc/context/project.py tests/test_context_project.py
git commit -m "feat(context): CodebaseMap, projected from the scan not re-extracted (E-84 D1)"
```

---

### Task 4: The bounded prompt rendering

**Files:**
- Create: `src/sdlc/context/render.py`
- Test: `tests/test_context_render.py`

**Interfaces:**
- Consumes: `CodebaseMap` from Task 3.
- Produces: `render_for_prompt(m: CodebaseMap, *, max_modules: int = 40, max_contracts: int = 60, max_hot_spots: int = 25) -> str`.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D12: the map is persisted complete and rendered bounded."""

from __future__ import annotations

from sdlc.assessment.scan.models import Confidence, MemberKind
from sdlc.context.models import CodebaseMap, HotSpot, MapContract, MapModule
from sdlc.context.render import render_for_prompt
from sdlc.measurement import Measurement


def _map(modules=(), contracts=(), hot_spots=(), collected=None) -> CodebaseMap:
    ok = collected or Measurement.measured(float(len(modules)))
    return CodebaseMap(
        tree_hash="t",
        commit_sha="c" * 40,
        modules=tuple(modules),
        contracts=tuple(contracts),
        hot_spots=tuple(hot_spots),
        modules_collected=ok,
        contracts_collected=ok,
        hot_spots_collected=ok,
        collected=ok,
    )


def _module(n: int) -> MapModule:
    return MapModule(name=f"cap{n:03d}", member_paths=(f"src/{n}.py",), confidence=Confidence.LOW)


def test_a_small_map_renders_whole_with_no_marker():
    out = render_for_prompt(_map(modules=[_module(1), _module(2)]))
    assert "cap001" in out and "cap002" in out
    assert "more" not in out


def test_truncation_announces_itself():
    """The model must be told it is seeing a subset; silence would let it
    conclude the repository has exactly max_modules modules."""
    out = render_for_prompt(_map(modules=[_module(i) for i in range(50)]), max_modules=10)
    assert "cap000" in out
    assert "… 40 more" in out


def test_a_not_collected_section_says_so_rather_than_showing_nothing():
    m = _map(collected=Measurement.not_collected("S5 could not run"))
    out = render_for_prompt(m)
    assert "not_collected" in out
    assert "S5 could not run" in out


def test_rendering_is_deterministic():
    modules = [_module(i) for i in range(50)]
    first = render_for_prompt(_map(modules=modules), max_modules=10)
    for _ in range(5):
        assert render_for_prompt(_map(modules=modules), max_modules=10) == first


def test_contracts_and_hot_spots_truncate_independently():
    contracts = [
        MapContract(kind=MemberKind.HTTP_ROUTE, value=f"GET /{i}", path=f"src/{i}.py")
        for i in range(30)
    ]
    spots = [
        HotSpot(
            path=f"src/{i}.py", source="testability", reason="r", metric=Measurement.measured(1.0)
        )
        for i in range(30)
    ]
    out = render_for_prompt(
        _map(contracts=contracts, hot_spots=spots), max_contracts=5, max_hot_spots=3
    )
    assert "… 25 more" in out
    assert "… 27 more" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.context.render'`

- [ ] **Step 3: Write the implementation**

```python
"""E-84 D12: the Architect's view of the map.

ARCHITECTURE.md:169-171 requires this in as many words -- high-volume
exploration "uses programmatic access -- tools that filter and extract --
rather than streaming the corpus through the context window" -- and FR-801
enforces a per-role context_budget_tokens at prompt assembly regardless.

Truncation is deterministic because an unstable rendering would make the
architect memo key unstable and NFR-10's reproducibility claim false. The
input is already totally sorted by project(); this only cuts.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..measurement import CollectionState, Measurement
from .models import CodebaseMap


def _section(title: str, rows: Sequence[str], collected: Measurement, limit: int) -> list[str]:
    if collected.state is not CollectionState.MEASURED:
        return [f"{title}: {collected.state.value} -- {collected.reason}"]
    if not rows:
        return [f"{title}: none found"]
    shown = list(rows[:limit])
    out = [f"{title} ({len(rows)}):"]
    out.extend(f"  - {r}" for r in shown)
    if len(rows) > limit:
        out.append(f"  … {len(rows) - limit} more")
    return out


def render_for_prompt(
    m: CodebaseMap, *, max_modules: int = 40, max_contracts: int = 60, max_hot_spots: int = 25
) -> str:
    lines = [f"CodebaseMap at commit {m.commit_sha[:12]} (tree {m.tree_hash[:12]})"]
    lines += _section(
        "modules",
        [f"{x.name} [{x.confidence.value}] {', '.join(x.member_paths[:5])}" for x in m.modules],
        m.modules_collected,
        max_modules,
    )
    lines += _section(
        "contracts",
        [
            f"{x.kind.value} {x.value} ({x.path}{':' + str(x.line) if x.line else ''})"
            for x in m.contracts
        ],
        m.contracts_collected,
        max_contracts,
    )
    lines += _section(
        "hot spots",
        [f"{x.path} [{x.source}] {x.reason}" for x in m.hot_spots],
        m.hot_spots_collected,
        max_hot_spots,
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_context_render.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/context/render.py tests/test_context_render.py
git commit -m "feat(context): the prompt rendering is bounded and announces its cuts (E-84 D12)"
```

---

### Task 5: Extract `scan_tree()` — one extraction path

**Files:**
- Create: `src/sdlc/workflows/scanning.py`
- Modify: `src/sdlc/workflows/assessment.py:373-478` (`_scan` becomes a delegation)
- Test: `tests/test_scan_tree_shared.py`

**Interfaces:**
- Consumes: everything `_scan` already imports (`assessment_resolve_tree`, `SCAN_ACTIVITIES`, `SCAN_SIGNALS`, `WAVES`, `run_or_degrade`, `inherited_halves`, `merge`, `fold_row`, `upstream_for`, `_inherited_row`, `_merged_row`, `skipped_scan_signal`).
- Produces: `async def scan_tree(repo_dir: str, commit_sha: str, triage: RepoTriage | None = None) -> ScanOutcome`.

**This is a behaviour-preserving refactor.** The assertion that it worked is that `tests/test_assessment_scan_phase.py` and every other assessment test stay green without modification. Do not change signal logic in this task.

`ScanOutcome` (carrying `PhaseResult(phase=PhaseId.SCAN, …)`) stays the shared return type. The feature path reads only `.scan`, `.tree_hash`, and `.result.collected`, ignoring the phase label — one type shared beats a parallel type plus a conversion.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D1/D5: one extraction path, and it runs without a triage."""

from __future__ import annotations

import inspect

from sdlc.workflows import scanning


def test_scan_tree_is_importable_and_triage_is_optional():
    sig = inspect.signature(scanning.scan_tree)
    assert list(sig.parameters) == ["repo_dir", "commit_sha", "triage"]
    assert sig.parameters["triage"].default is None


def test_the_assessment_phase_delegates_rather_than_duplicating():
    """D1: two copies of the fan-out would agree only by coincidence -- the
    reason fanout.py exists at all. _scan must call scan_tree, not re-run the
    waves itself."""
    from sdlc.workflows.assessment import AssessmentWorkflow

    src = inspect.getsource(AssessmentWorkflow._scan)
    assert "scan_tree(" in src
    assert "for wave in WAVES" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scan_tree_shared.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.workflows.scanning' has no attribute 'scan_tree'` (and the module does not exist)

- [ ] **Step 3: Create `src/sdlc/workflows/scanning.py`**

Move the body of `_scan` (assessment.py:381-478) verbatim, with four changes: `inp.repo_dir` → `repo_dir`, `triage.commit_sha` → `commit_sha`, the inherited halves guarded on `triage is None`, and the SS2 fallback reason distinguishing "no triage supplied" from "no half".

```python
"""E-84 D1: the scan fan-out, shared by both tiers.

AssessmentWorkflow calls this with a RepoTriage; FeatureWorkflow's brownfield
context stage calls it with triage=None. One function means the audit tier and
the pipeline physically cannot produce two different maps of one tree, because
they run the same waves against the same memo -- and a brownfield run over a
tree an assessment already scanned pays nothing.

Workflow-context code: it calls workflow.execute_activity and must only be
invoked from inside a workflow.
"""

from __future__ import annotations

import asyncio

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..assessment.activities import (
        AssessmentTree,
        AssessmentTreeInput,
        assessment_resolve_tree,
    )
    from ..assessment.scan.inherit import inherited_halves
    from ..assessment.scan.merge import merge
    from ..assessment.scan.models import (
        SCAN_ORDER,
        ScanResult,
        ScanSignalId,
        SignalOutput,
    )
    from ..assessment.scan.registry import SCAN_SIGNALS, WAVES
    from ..measurement import CollectionState, Measurement
    from ..triage.models import RepoTriage
    from .fanout import run_or_degrade


async def scan_tree(
    repo_dir: str, commit_sha: str, triage: RepoTriage | None = None
) -> "ScanOutcome":
    """Thirteen signals over one pinned tree.

    `triage=None` is a supported call, not a degraded one: inherit.py gives
    every inherited category an explicit absent branch, so the five signals
    with an inherited half (SS1, SS2, SS3, QS1, QS4) report not_collected
    naming the missing triage signal, while S1-S5 -- which take no inherited
    half at all -- are unaffected. Requiring a triage would have meant
    requiring a human-approved Tier 2 admission before any brownfield feature
    run, making P2 depend on P6 (D5).

    Nothing here executes the scanned repository's code: every signal reads
    blob bytes at the pinned commit (NFR-9).
    """
    # ... the body of AssessmentWorkflow._scan, lines 381-478, with:
    #   inp.repo_dir     -> repo_dir
    #   triage.commit_sha -> commit_sha
    #   halves = inherited_halves(triage) if triage is not None else {}
    #   the SS2/synthesis fallback reason:
    #       f"{sid.value} is purely inherited and no triage was supplied"
    #       when triage is None, else the existing
    #       f"{sid.value} has no activity and no inherited half"
```

Keep `ScanOutcome`, `PhaseResult`, `PhaseId`, `skipped_scan_signal`, `_inherited_row`, `_merged_row`, `upstream_for` and `fold_row` where they are and import them; moving them too would widen a refactor that must stay behaviour-preserving. If any of those are module-private to `assessment.py`, move only those helpers into `scanning.py` and import them back into `assessment.py` so there is still exactly one definition.

- [ ] **Step 4: Reduce `AssessmentWorkflow._scan` to a delegation**

```python
async def _scan(self, inp: AssessmentInput, triage: RepoTriage) -> ScanOutcome:
    """Phase 2 (E-46). The fan-out moved to workflows/scanning.py with
    E-84, so the pipeline's brownfield context stage runs the identical
    thirteen signals over the identical memo (E-84 D1)."""
    return await scan_tree(inp.repo_dir, triage.commit_sha, triage)
```

Add `from .scanning import scan_tree` to `assessment.py`'s
`workflow.unsafe.imports_passed_through()` block, and delete the imports that
only the moved body used.

- [ ] **Step 5: Run the full suite to prove the refactor changed nothing**

Run: `python -m pytest tests/test_scan_tree_shared.py tests/test_assessment_scan_phase.py -v && python -m pytest -q`
Expected: PASS — new tests pass, and every pre-existing assessment test passes **unmodified**. If any assessment test needed editing, the refactor was not behaviour-preserving; revert and redo.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/scanning.py src/sdlc/workflows/assessment.py tests/test_scan_tree_shared.py
git commit -m "refactor(scan): lift the fan-out to a shared scan_tree, triage optional (E-84 D1/D5)"
```

---

### Task 6: `BrownfieldDelta` and the grounding check

**Files:**
- Modify: `src/sdlc/models.py:256-263` (`ArchitectureSpec`) — add `BrownfieldDelta` above it
- Create: `src/sdlc/context/delta.py`
- Test: `tests/test_context_delta.py`

**Interfaces:**
- Consumes: `CheckResult`, `CheckClass`, `build_check` from `sdlc.gate`.
- Produces: `BrownfieldDelta` (in `sdlc.models`), `DELTA_CHECK = "brownfield_delta_grounded"`, `normalize_path(p: str) -> str`, `check_delta(delta: BrownfieldDelta | None, paths: frozenset[str]) -> CheckResult`.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D7/D8/D9: three classes, opposite rules, no rescue by basename."""

from __future__ import annotations

import random

from sdlc.context.delta import DELTA_CHECK, check_delta, normalize_path
from sdlc.gate import CheckClass
from sdlc.models import BrownfieldDelta

TREE = frozenset({"src/payments/api.py", "src/payments/store.py", "tests/test_api.py", "README.md"})


def test_a_grounded_delta_passes():
    got = check_delta(
        BrownfieldDelta(
            added=["src/payments/refund.py"],
            modified=["src/payments/api.py"],
            removed=["src/payments/store.py"],
        ),
        TREE,
    )
    assert got.passed is True
    assert got.name == DELTA_CHECK
    assert got.classification is CheckClass.ABSOLUTE


def test_modifying_a_file_that_does_not_exist_fails():
    got = check_delta(BrownfieldDelta(modified=["src/payments/ghost.py"]), TREE)
    assert got.passed is False
    assert "src/payments/ghost.py" in got.detail
    assert "modified" in got.detail


def test_removing_a_file_that_does_not_exist_fails():
    got = check_delta(BrownfieldDelta(removed=["nope.py"]), TREE)
    assert got.passed is False
    assert "removed" in got.detail


def test_adding_a_file_that_already_exists_fails():
    """D8: the contradiction is the same species and the check is free."""
    got = check_delta(BrownfieldDelta(added=["src/payments/api.py"]), TREE)
    assert got.passed is False
    assert "already exists" in got.detail


def test_a_missing_delta_fails_rather_than_passing_vacuously():
    """D7: ArchitectureSpec cannot see the mode, so the stage enforces it
    here -- and an absent delta must never read as a grounded one."""
    got = check_delta(None, TREE)
    assert got.passed is False
    assert "no delta" in got.detail.lower()


def test_an_empty_delta_fails():
    got = check_delta(BrownfieldDelta(), TREE)
    assert got.passed is False
    assert "names no files" in got.detail


def test_windows_separators_and_dot_slash_normalize():
    got = check_delta(
        BrownfieldDelta(modified=["src\\payments\\api.py", "./tests/test_api.py"]), TREE
    )
    assert got.passed is True


def test_a_basename_match_is_not_a_match():
    """D9: normalization aggressive enough to rescue a wrong path is
    normalization that launders fabrication into a pass. Pinned as a test so
    a future 'helpful' relaxation trips it."""
    got = check_delta(BrownfieldDelta(modified=["api.py"]), TREE)
    assert got.passed is False
    got = check_delta(BrownfieldDelta(modified=["other/payments/api.py"]), TREE)
    assert got.passed is False


def test_normalize_leaves_a_clean_path_alone():
    assert normalize_path("src/payments/api.py") == "src/payments/api.py"
    assert normalize_path("/src/api.py") == "src/api.py"


def test_every_unresolvable_path_is_named_not_just_the_first():
    got = check_delta(BrownfieldDelta(modified=["a.py", "b.py"], removed=["c.py"]), TREE)
    for p in ("a.py", "b.py", "c.py"):
        assert p in got.detail


def test_the_detail_is_order_independent():
    """NFR-10: the same failure reads identically however the lists arrive,
    because the detail becomes re-prompt guidance and an unstable string
    would move the architect memo key."""
    paths = ["a.py", "b.py", "c.py", "d.py"]
    first = check_delta(BrownfieldDelta(modified=paths), TREE).detail
    for _ in range(5):
        shuffled = paths[:]
        random.shuffle(shuffled)
        assert check_delta(BrownfieldDelta(modified=shuffled), TREE).detail == first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context_delta.py -v`
Expected: FAIL — `ImportError: cannot import name 'BrownfieldDelta' from 'sdlc.models'`

- [ ] **Step 3: Add `BrownfieldDelta` to `src/sdlc/models.py`, above `ArchitectureSpec`**

```python
class BrownfieldDelta(BaseModel):
    """FR-102's delta: what an architecture change does to a real tree.

    Three classes rather than one flat list because they have OPPOSITE
    grounding rules -- a modified path must exist and an added path must not
    (E-84 D8) -- and a single list cannot carry that distinction.
    """

    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
```

Then modify `ArchitectureSpec`:

```python
class ArchitectureSpec(BaseModel):
    overview: str
    decisions: list[ArchitectureDecision]
    affected_modules: list[str] = Field(default_factory=list)  # brownfield
    new_components: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    spec_ref: ArtifactRef | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301
    delta: BrownfieldDelta | None = None  # E-84, brownfield

    @model_validator(mode="after")
    def _affected_modules_follow_the_delta(self) -> "ArchitectureSpec":
        """E-84 D7: one authority for what changed.

        `affected_modules` predates the typed delta and is documented as the
        delta in docs/agents-schema.html. When a delta is present it is the
        authority and this field is derived from it; when it is absent
        (greenfield, and the seeded specs tidyup/backlog.py:103 and the
        benchmark fixtures write) the field is left exactly as given.
        """
        if self.delta is not None:
            derived = sorted(set(self.delta.modified) | set(self.delta.removed))
            if list(self.affected_modules) != derived:
                object.__setattr__(self, "affected_modules", derived)
        return self
```

Note: if `ArchitectureSpec` is a frozen model, use `model_config` mutation rules already in force elsewhere in the file — check a neighbouring validator that assigns (e.g. `models.py:527`) and follow its idiom rather than introducing `object.__setattr__` if a plain assignment works.

- [ ] **Step 4: Write `src/sdlc/context/delta.py`**

```python
"""E-84 D8/D9: is the architecture delta grounded in the real tree?

The roadmap's framing of the BrownKit port is that its value is
enforceability -- gates "graded by the model that produced the artifacts"
become "CheckResults computed by pure code". An affected_modules list the
Architect wrote about files it never read is the defect FR-914 and SC-7 exist
to prevent, one stage earlier.

Pure: the caller supplies the path set. The activity that reads git lives in
activities.py, so this stays testable against a frozenset.
"""

from __future__ import annotations

from ..gate import CheckClass, CheckResult, build_check
from ..models import BrownfieldDelta

DELTA_CHECK = "brownfield_delta_grounded"


def normalize_path(path: str) -> str:
    """Repo-relative POSIX form.

    Conservative on purpose (D9). This never matches on basename or suffix:
    src/app.py and tests/app.py are different files, and a check that accepts
    either has stopped verifying the claim it reports on. The forward-slash
    rule is not incidental -- the development host is Windows and git reports
    POSIX paths, so a separator mismatch is the likeliest way this check fails
    for a reason that has nothing to do with the Architect.
    """
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def check_delta(delta: BrownfieldDelta | None, paths: frozenset[str]) -> CheckResult:
    """Resolve every claimed path against the tree at the pinned commit.

    `paths` is EVERY file in the tree, not the map's attributed files.
    Attribution is best-effort -- E-47b's floor defaults to 0.90 and its
    reference table has a pinned known false positive -- so resolving against
    it would fail the Architect for naming a real config file the scan never
    attributed. A false accusation of fabrication is the most expensive
    possible error for a check whose purpose is trust.
    """
    if delta is None:
        return build_check(
            DELTA_CHECK,
            False,
            CheckClass.ABSOLUTE,
            "no delta proposed: a brownfield architecture must state what it "
            "adds, modifies and removes against the existing tree",
        )
    if not (delta.added or delta.modified or delta.removed):
        return build_check(
            DELTA_CHECK,
            False,
            CheckClass.ABSOLUTE,
            "the delta names no files: an architecture that changes nothing "
            "cannot be planned or implemented",
        )

    known = {normalize_path(p) for p in paths}
    problems: list[str] = []
    for label, claimed in (("modified", delta.modified), ("removed", delta.removed)):
        problems.extend(
            f"{label} {p!r} does not exist at the pinned commit"
            for p in claimed
            if normalize_path(p) not in known
        )
    problems.extend(
        f"added {p!r} already exists at the pinned commit"
        for p in delta.added
        if normalize_path(p) in known
    )

    if problems:
        return build_check(DELTA_CHECK, False, CheckClass.ABSOLUTE, "; ".join(sorted(problems)))
    return build_check(
        DELTA_CHECK,
        True,
        CheckClass.ABSOLUTE,
        f"{len(delta.added)} added, {len(delta.modified)} modified, "
        f"{len(delta.removed)} removed -- all resolve",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_context_delta.py -v && python -m pytest -q`
Expected: PASS (11 new tests); full suite green — in particular `tests/test_tidyup_backlog.py` and the benchmark seed tests, which write `affected_modules` on delta-less specs

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py src/sdlc/context/delta.py tests/test_context_delta.py
git commit -m "feat(context): the delta is three classes with opposite rules (E-84 D7/D8/D9)"
```

---

### Task 7: The tree-listing activity

**Files:**
- Modify: `src/sdlc/activities.py` (append)
- Modify: `src/sdlc/worker.py` (import + registration)
- Test: `tests/test_context_delta_activity.py`

**Interfaces:**
- Consumes: `check_delta`, `BrownfieldDelta`, `CheckResult`.
- Produces: `DeltaCheckInput(repo_dir: str, commit_sha: str, delta: BrownfieldDelta | None)`, `async def check_brownfield_delta(inp: DeltaCheckInput) -> CheckResult`.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D8: resolution happens against git, activity-side."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.activities import DeltaCheckInput, check_brownfield_delta
from sdlc.models import BrownfieldDelta


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "r"
    (d / "src").mkdir(parents=True)
    _git("init", "-b", "main", cwd=d)
    _git("config", "user.email", "t@t.t", cwd=d)
    _git("config", "user.name", "t", cwd=d)
    (d / "src" / "api.py").write_text("x = 1\n")
    _git("add", ".", cwd=d)
    _git("commit", "-m", "init", cwd=d)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True
    ).stdout.strip()
    return d, sha


@pytest.mark.asyncio
async def test_a_real_path_resolves(repo):
    d, sha = repo
    got = await check_brownfield_delta(
        DeltaCheckInput(
            repo_dir=str(d), commit_sha=sha, delta=BrownfieldDelta(modified=["src/api.py"])
        )
    )
    assert got.passed is True


@pytest.mark.asyncio
async def test_a_fabricated_path_fails(repo):
    d, sha = repo
    got = await check_brownfield_delta(
        DeltaCheckInput(
            repo_dir=str(d), commit_sha=sha, delta=BrownfieldDelta(modified=["src/ghost.py"])
        )
    )
    assert got.passed is False
    assert "src/ghost.py" in got.detail


@pytest.mark.asyncio
async def test_an_unresolvable_commit_fails_closed(repo):
    """A check that cannot read the tree must never report a pass -- that is
    the malformed-SARIF hole FR-915 exists to close."""
    d, _ = repo
    got = await check_brownfield_delta(
        DeltaCheckInput(
            repo_dir=str(d), commit_sha="0" * 40, delta=BrownfieldDelta(modified=["src/api.py"])
        )
    )
    assert got.passed is False
    assert "could not list" in got.detail.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context_delta_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'DeltaCheckInput'`

- [ ] **Step 3: Write the implementation (append to `activities.py`)**

```python
class DeltaCheckInput(BaseModel):
    repo_dir: str
    commit_sha: str
    delta: BrownfieldDelta | None = None


@activity.defn
async def check_brownfield_delta(inp: DeltaCheckInput) -> CheckResult:
    """E-84 D8: supply the tree's path list, then run the pure check.

    The listing stays here rather than travelling to the workflow: a large
    repository's full path set inline would bloat every brownfield run's
    history against ADR-10, and would push CodebaseMap past the Architect's
    context_budget_tokens (FR-801).
    """
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", inp.commit_sha],
        cwd=inp.repo_dir,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return build_check(
            DELTA_CHECK,
            False,
            CheckClass.ABSOLUTE,
            f"could not list the tree at {inp.commit_sha[:12]}: {listing.stderr.strip()[:200]}",
        )
    paths = frozenset(p for p in listing.stdout.splitlines() if p.strip())
    return check_delta(inp.delta, paths)
```

Add to `activities.py`'s imports:

```python
from .context.delta import DELTA_CHECK, check_delta
from .gate import CheckClass, CheckResult, build_check
from .models import BrownfieldDelta
```

(`gate` and `models` imports may already be present — extend the existing lines rather than adding duplicates.)

- [ ] **Step 4: Register on the worker**

Add `check_brownfield_delta` to `worker.py`'s `from .activities import (...)` block and to the `activities=[...]` list.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_context_delta_activity.py -v && python -m pytest -q`
Expected: PASS (3 new tests); full suite green

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/activities.py src/sdlc/worker.py tests/test_context_delta_activity.py
git commit -m "feat(context): resolve the delta against git, activity-side (E-84 D8)"
```

---

### Task 8: Wire stages 0 and 2 into `FeatureWorkflow`

**Files:**
- Modify: `src/sdlc/workflows/feature.py:1684-1720` (`_pipeline`), plus the workflow's import block
- Test: `tests/test_feature_brownfield_stages.py`

**Interfaces:**
- Consumes: `classify_repo`, `RepoObservation`, `classify`, `scan_tree`, `project`, `map_digest`.
- Produces: `FeatureWorkflow._context(idea, cfg, repo_path, commit_sha) -> CodebaseMap`; `self._codebase_map: CodebaseMap | None` set for the architecture stage; run terminates `rejected:intake` / `rejected:context` on the D3/D6 failures.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D3/D4/D6/D13: the brownfield branch, wired."""

from __future__ import annotations

import inspect

from sdlc.workflows.feature import FeatureWorkflow


def test_the_pipeline_reads_the_mode():
    """Before E-84, IdeaBrief.mode was written by three callers and read by
    nothing in src/sdlc/. That is the defect this task closes."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "ProjectMode.BROWNFIELD" in src or "classify(" in src


def test_context_runs_after_the_integration_branch_is_cut():
    """D4: the map must describe the tree the work is actually based on, so
    it pins integration.head_sha rather than the base branch's tip."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert src.index("setup_integration_branch") < src.index("_context(")


def test_seeded_runs_still_short_circuit_before_context():
    """D13: tidy-up children declare BROWNFIELD and have no Architect call to
    ground, so they must not pay for a map nothing reads (E-44 D1)."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert src.index("if seeded is not None") < src.index("_context(")
```

Add the behavioural half to the existing temporal-marked suite (the file that already drives `FeatureWorkflow` end to end with fakes — follow `tests/test_e2e_greenfield.py`'s worker setup):

```python
@pytest.mark.temporal
async def test_a_brownfield_run_against_a_non_repository_stops_at_intake(...):
    """D3: fails closed before any model call."""
    # drive FeatureWorkflow with IdeaBrief(mode=BROWNFIELD,
    # repo_url=str(tmp_path / "not-a-repo")) and assert the terminal status
    # names intake, and that no architect activity was executed.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_feature_brownfield_stages.py -v`
Expected: FAIL — `AssertionError` on the mode assertion (`_pipeline` does not mention the mode)

- [ ] **Step 3: Write the implementation**

In `feature.py`'s `workflow.unsafe.imports_passed_through()` block add:

```python
    from ..activities import classify_repo, RepoProbeInput
    from ..context.classify import classify
    from ..context.models import CodebaseMap
    from ..context.project import map_digest, project
    from ..context.render import render_for_prompt
    from ..models import ProjectMode
    from .scanning import scan_tree
```

Add the constant beside the other activity option dicts:

```python
# Deterministic given a tree; the retry covers FS/git blips only. Mirrors
# assessment's TREE_ACT, which probes the same way.
INTAKE_ACT = dict(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)
```

Two insertions, in this order:

1. **Intake** replaces line 1694 (`repo_path = idea.repo_url or …`), i.e. it
   runs before `setup_integration_branch`. A repository that fails intake must
   not have a branch cut in it.
2. **Context** goes after the seeded short-circuit block (currently ending at
   line 1719), so a seeded run returns before reaching it (D13). That places it
   after `setup_integration_branch` too, which is what D4 requires — the map
   pins `self._integration_head`.

The intake step:

```python
repo_path = idea.repo_url or "/var/sdlc/repo"

# 0. INTAKE (E-84 D3) -- deterministic, no model call. IdeaBrief.mode
# is declared by the operator; this verifies the declaration against
# the tree and fails closed when brownfield has nothing to map.
self._status = "intake"
observed = await workflow.execute_activity(
    classify_repo, RepoProbeInput(repo_dir=repo_path, base_branch=idea.base_branch), **INTAKE_ACT
)
verdict = classify(observed, idea.mode)
if verdict.warning:
    self._event(RunEventKind.STAGE, {"stage": "intake", "warning": verdict.warning})
if not verdict.ok:
    return f"rejected:intake ({verdict.reason})"
```

(Use whatever `self._event` / trace helper `_pipeline` already uses for
`RunEvent`s — match the surrounding code rather than introducing a new one, and
match how other terminal paths format their `rejected:` strings.)

Then, after the seeded short-circuit block (currently ending line 1719):

```python
# 2. CONTEXT (E-84 D1/D4/D6) -- brownfield only. Pinned to the
# integration head, which is the branch point the work is based on.
self._codebase_map: CodebaseMap | None = None
if idea.mode is ProjectMode.BROWNFIELD:
    self._status = "mapping"
    self._codebase_map = await self._context(repo_path, self._integration_head)
    if self._codebase_map.collected.state is not CollectionState.MEASURED:
        # D6: proceeding would silently drop the delta check exactly
        # when the ground is weakest -- the shape of the
        # malformed-SARIF-reads-as-clean hole (FR-915).
        return f"rejected:context ({self._codebase_map.collected.reason})"
```

And the method:

```python
async def _context(self, repo_path: str, commit_sha: str) -> CodebaseMap:
    """Stage 2 (E-84). The same thirteen signals the audit tier runs, over
    the same memo, with no triage (D1/D5).

    Nothing here executes the repository's code: every signal reads blob
    bytes at the pinned commit (NFR-9).
    """
    out = await scan_tree(repo_path, commit_sha, None)
    if out.scan is None:
        return CodebaseMap(
            tree_hash=out.tree_hash or "",
            commit_sha=commit_sha,
            modules_collected=out.result.collected,
            contracts_collected=out.result.collected,
            hot_spots_collected=out.result.collected,
            collected=out.result.collected,
        )
    return project(out.scan, out.tree_hash, commit_sha)
```

Declare `self._codebase_map: CodebaseMap | None = None` in `__init__` too, so
the attribute exists on every path (greenfield and seeded included).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_feature_brownfield_stages.py -v && python -m pytest -q`
Expected: PASS; full suite green, including the greenfield e2e — a greenfield run must reach exactly the same stages as before

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_feature_brownfield_stages.py
git commit -m "feat(brownfield): stages 0 and 2 wired, mode is load-bearing at last (E-84 D3/D4/D6)"
```

---

### Task 9: The delta check in the architecture stage

**Files:**
- Modify: `src/sdlc/models.py` (`PipelineConfig`, near line 1066)
- Modify: `src/sdlc/workflows/feature.py:1970-2021` (`_run_architect`)
- Test: `tests/test_feature_delta_gate.py`

**Interfaces:**
- Consumes: `check_brownfield_delta`, `DeltaCheckInput`, `map_digest`, `render_for_prompt`, `self._codebase_map`.
- Produces: `PipelineConfig.max_delta_retries: int = 1`; the architecture stage fails with `rejected:architecture_delta` after the bound.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D10/D11: the check re-prompts once, then fails closed."""

from __future__ import annotations

import inspect

from sdlc.models import PipelineConfig
from sdlc.workflows.feature import FeatureWorkflow


def test_the_retry_bound_is_configurable_and_defaults_to_one():
    assert PipelineConfig().max_delta_retries == 1


def test_the_delta_retry_does_not_spend_gate_rounds():
    """D10: _revisable_stage's rounds are FR-301 GATE rounds. Spending them on
    machine retries would arrive at the human gate with the revision budget
    consumed, and would count machine retries as human rounds in the
    RunSummary.gates[] signal SC-6 reads."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    arch = src[src.index("_run_architect") : src.index("_revisable_stage")]
    assert "max_delta_retries" in arch
    assert "max_gate_rounds" not in arch


def test_the_map_digest_enters_the_architect_memo_key():
    """D11: a changed tree invalidates architecture and nothing else."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "map_digest" in src


def test_greenfield_memo_key_is_unchanged():
    """D11: no existing greenfield memo may be invalidated by this work."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    key = src[src.index('cfg, "architect",') :]
    assert 'reqs.model_dump_json() + (guidance or "")' in key
```

Add the behavioural test to the temporal suite:

```python
@pytest.mark.temporal
async def test_a_fabricated_module_fails_the_run_before_planning(...):
    """The SC-7-shaped case that justifies the design: an Architect stub that
    names a module absent from the tree must not reach the planner."""
    # Drive a brownfield FeatureWorkflow against a real fixture repo with an
    # architect fake returning delta.modified=["src/does_not_exist.py"].
    # Assert: terminal status names architecture_delta, the planner activity
    # never ran, and the failure detail names the fabricated path.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_feature_delta_gate.py -v`
Expected: FAIL — `AttributeError: 'PipelineConfig' object has no attribute 'max_delta_retries'`

- [ ] **Step 3: Add the knob to `PipelineConfig`**

Beside `max_gate_rounds` (models.py:1066):

```python
max_delta_retries: int = 1  # E-84: bounded re-prompt when the
# brownfield delta names a path
# that does not resolve. NOT a
# gate round (FR-301) -- this is a
# validation retry (FR-202), and
# spending gate rounds on machine
# retries would consume the
# human's revision budget
```

- [ ] **Step 4: Wire the check into `_run_architect`**

Replace the prompt construction and the `_cached_stage` call (feature.py:1970-2021):

```python
async def _run_architect(guidance: str | None):
    ctx = ""
    digest = ""
    if self._codebase_map is not None:
        digest = map_digest(self._codebase_map)
        ctx = (
            "\nThe existing codebase (extracted at the pinned "
            "commit; propose a delta against it):\n" + render_for_prompt(self._codebase_map)
        )
    prompt = (
        f"mode={idea.mode.value}\n{reqs.model_dump_json()}{ctx}"
        + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items) if snapshot.items else "")
        + (f"\nRevision guidance from reviewer:\n{guidance}" if guidance else "")
    )

    # ... architect_deps unchanged ...

    async def _produce():
        return (
            await self._run_role(
                cfg,
                "architect",
                resolve_role_model(cfg, "architect"),
                t_architect,
                prompt,
                deps=architect_deps,
                into=arch_spend,
            )
        ).output

    # D10/D11: the map digest joins the memo key in brownfield only,
    # so greenfield keys are byte-identical to before. Machine
    # guidance is already part of the key (it is appended below), so
    # each retry re-prompts rather than re-serving the cached spec.
    attempt = 0
    extra = ""
    while True:
        arch, _ = await self._cached_stage(
            cfg,
            "architect",
            reqs.model_dump_json() + (guidance or "") + digest + extra,
            ArchitectureSpec,
            _produce,
        )
        if self._codebase_map is None:
            return arch
        checked = await workflow.execute_activity(
            check_brownfield_delta,
            DeltaCheckInput(
                repo_dir=repo_path, commit_sha=self._codebase_map.commit_sha, delta=arch.delta
            ),
            **INTAKE_ACT,
        )
        if checked.passed:
            return arch
        if attempt >= cfg.max_delta_retries:
            raise ApplicationError(
                f"architecture delta is not grounded: {checked.detail}", non_retryable=True
            )
        attempt += 1
        extra = (
            f"\nThe previous delta was rejected: "
            f"{checked.detail}\nEvery modified or removed path "
            f"must already exist in the codebase map above, and "
            f"every added path must not."
        )
```

Three notes for the implementer.

`_produce` closes over `prompt`, which is built once — rebuild it inside the
loop so `extra` reaches the model, or thread `extra` through `_produce`; a
retry that re-sends the identical prompt is a wasted call.

`ApplicationError` is **not** currently imported in `feature.py` (unlike
`CollectionState`, `timedelta` and `RetryPolicy`, which are). Either add
`from temporalio.exceptions import ApplicationError` or, better, match how the
surrounding code signals a terminal stage failure — if `_pipeline` already
returns `rejected:*` strings for its other terminal paths, return
`f"rejected:architecture_delta ({checked.detail})"` and thread the failure out
of `_run_architect` rather than raising through `_revisable_stage`.

`_run_architect` is a closure inside `_pipeline`, so `repo_path` is already in
scope for the `DeltaCheckInput`; no new parameter is needed.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_feature_delta_gate.py -v && python -m pytest -q`
Expected: PASS; full suite green

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py src/sdlc/workflows/feature.py tests/test_feature_delta_gate.py
git commit -m "feat(brownfield): the delta check re-prompts once, then fails closed (E-84 D10/D11)"
```

---

### Task 10: Teach the Architect the delta

**Files:**
- Modify: `agents/architect/instructions.md`
- Test: `tests/test_architect_brownfield_prompt.py`

**Interfaces:**
- Consumes: nothing new — the map arrives in the prompt from Task 9.
- Produces: no code; a prompt asset whose bytes hash into `PROMPT_SHAS`.

**Expected cost, stated so it is not a surprise:** the loader reads one
`instructions.md` per role, so this edit moves `PROMPT_SHAS["architect"]` and
invalidates **every** project's architect memo once — greenfield included. One
time, and correct.

- [ ] **Step 1: Write the failing test**

```python
"""E-84 D13: the Architect is told what a delta is and what grounds it."""

from __future__ import annotations

from pathlib import Path

TEXT = Path("agents/architect/instructions.md").read_text(encoding="utf-8")


def test_the_brownfield_branch_exists():
    lower = TEXT.lower()
    assert "brownfield" in lower
    assert "delta" in lower


def test_the_three_classes_are_named():
    for word in ("added", "modified", "removed"):
        assert word in TEXT.lower()


def test_the_grounding_rule_is_stated_in_both_directions():
    """The check enforces it either way, so the prompt must say it either
    way -- a model told only half the rule fails the other half."""
    lower = TEXT.lower()
    assert "must already exist" in lower
    assert "must not" in lower


def test_the_guardrail_is_present():
    """Ported verbatim from E-48's clause list: delivery channels and
    deployment boundaries are not capabilities."""
    assert "not capabilities" in TEXT.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_architect_brownfield_prompt.py -v`
Expected: FAIL — "brownfield" is absent from the instructions

- [ ] **Step 3: Append the brownfield section to `agents/architect/instructions.md`**

Match the file's existing voice and heading depth. Content to cover:

```markdown
## Brownfield runs

When the prompt carries `mode=brownfield`, a `CodebaseMap` follows it: the
modules, contracts and hot spots extracted from the repository at a pinned
commit. It may be truncated — a `… N more` line means exactly that, and you
should not conclude the repository contains only what you were shown.

In brownfield you MUST populate `delta`:

- `modified` — files that already exist and that your design changes
- `removed` — files that already exist and that your design deletes
- `added` — files that do not yet exist and that your design creates

Every `modified` and `removed` path **must already exist** in the codebase map.
Every `added` path **must not**. Both directions are checked by code against
the real tree before planning starts; a path that does not resolve fails the
stage. Do not guess a path because it looks plausible — if the map does not
show the file you need, design against what it does show.

Delivery channels and deployment boundaries are not capabilities: a REST
controller and a CLI entry point that call the same service are one capability
with two channels, not two.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_architect_brownfield_prompt.py -v && python -m pytest -q`
Expected: PASS. If a test asserts a specific `PROMPT_SHAS` value, it must be updated in this commit — that is the intended invalidation, not a regression.

- [ ] **Step 5: Commit**

```bash
git add agents/architect/instructions.md tests/test_architect_brownfield_prompt.py
git commit -m "feat(architect): brownfield emits a grounded delta (E-84 D13)"
```

---

### Task 11: Update the roadmap

**Files:**
- Modify: `ROADMAP.md`

Only after every preceding task is green. The tracker's rule is that `[x]` means implemented and wired, verified against code.

- [ ] **Step 1: Apply the spec's "Roadmap deltas" table**

Work through the table in the spec's `## Roadmap deltas` section and apply each row: FR-102 → `[x]`; §1 stage 0 and stage 2 → `[x]`; the §1 header count 9 → **11 of 15**; P2's note (brownfield half closes, E-75 remains); ADR-11's stage count; NFR-9 and NFR-10 notes; SC-7's architecture clause; §7's `_pipeline` note. Add E-84 as a new item with its spec and plan paths, in the section §11 sits in.

Update the `Last verified` header row with today's date, the E-item, and what it was verified against — following the existing entries' format exactly.

- [ ] **Step 2: Record the two observations the spec names**

E-48's landing is still unrecorded in the tracker (it is marked `[ ]` at §11 while its code is merged), and E-82 is shipped code absent from every E-item list. Add both, or leave them for a dedicated tracker pass — but do not silently mark E-48 done inside an E-84 commit.

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): E-84 lands -- FR-102 closes, 11 of 15 stages live"
```

---

## Self-Review

**Spec coverage.** D1 → Task 5. D2 → Tasks 1/3/6 (placement) . D3 → Tasks 1/2/8. D4 → Task 8. D5 → Task 5. D6 → Task 8. D7 → Task 6. D8 → Tasks 6/7. D9 → Task 6. D10 → Task 9. D11 → Task 9. D12 → Task 4. D13 → Tasks 8 (seeded skip) and 10 (prompt). Contracts → Tasks 1/3/6. Failure modes → covered by tests in Tasks 1, 3, 6, 7, 8, 9. Testing section → Tasks 1–11. Roadmap deltas → Task 11.

**Type consistency.** `project(scan, tree_hash, commit_sha)` is defined in Task 3 and called with those three arguments in Task 8. `check_delta(delta, paths)` is defined in Task 6 and called in Task 7. `map_digest(m)` defined in Task 3, used in Task 9. `DELTA_CHECK` defined in Task 6, used in Tasks 6 and 7. `RepoProbeInput`/`RepoObservation` defined in Tasks 1–2, used in Task 8. `scan_tree(repo_dir, commit_sha, triage)` defined in Task 5, called in Task 8. `CollectionState` is used in Task 8's `_pipeline` snippet and is already imported at `feature.py:50`; `timedelta` and `RetryPolicy`, which Task 8's `INTAKE_ACT` needs, are already imported at lines 11 and 14.

**Known judgement calls left to the implementer**, flagged rather than hidden: whether `ArchitectureSpec` permits validator assignment (Task 6, Step 3), how `_pipeline` formats terminal `rejected:` strings and whether it catches `ApplicationError` (Tasks 8 and 9), and whether the `_produce` closure needs rebuilding for the retry prompt (Task 9, Step 4). Each names what to check and which neighbouring code to follow.
