# Analyst Stage (stage 9) + Traceability & Coverage Gate Checks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stage 9 (`analyze`) — a clean-context Analyst proposer emitting `AnalysisReport` — and wire the two advisory merge-gate checks it unlocks: `traceability` (fully enforced) and `coverage` (a minimal deterministic diff-scoped seam).

**Architecture:** The Analyst is a Pydantic-AI `Agent` wrapped in `TemporalAgent`, holding no tools/repo/session — identical construct to the existing Reviewer/QA analyst. It runs once, after the per-task loop and before the merge-gate evidence collection in `FeatureWorkflow`. The LLM *proposes* a criterion→test mapping; a pure workflow helper *enforces* completeness against the authoritative acceptance-criteria set from the plan (FR-106). Coverage is deterministic evidence produced by a new activity, not the LLM.

**Tech Stack:** Python 3, Pydantic v2, Pydantic AI (`TemporalAgent` + `TestModel` for fakes), Temporal Python SDK (`temporalio`), pytest / pytest-asyncio, `defusedxml` (hardened XML parsing for the coverage seam).

## Global Constraints

- **Determinism boundary:** nothing under `src/sdlc/workflows/` may import `subprocess`, HTTP clients, the memory client, or the harness package. All I/O lives in activities. (Enforced by `tests/test_factory_purity.py`.)
- **Claim-check discipline:** pipeline models stay small; large text (diffs, reports) travels by reference or truncated extract, never inline in full.
- **Clean-context validators (ADR-12):** the Analyst receives only orchestrator-assembled artifacts (criteria list + materialized diff + test output) — never an implementer's session or narrative.
- **Propose vs enforce (FR-106):** the LLM proposes the mapping; the workflow computes the verdict against the authoritative plan set. Never trust an LLM-emitted pass/fail.
- **Absolute floor untouched (SC-5):** both new checks are `CheckClass.ADVISORY`. Do not modify `gate.py` or any absolute check.
- **Agent/activity names are Temporal identities:** `analyst_agent`, `measure_coverage` — set once, never rename after deploy.
- **Coverage default off:** `PipelineConfig.coverage_threshold` defaults to `0.0`; `measure_coverage` returns `measured=False` when no coverage artifact exists, and the check then passes (no spurious human override).
- **Untrusted-XML hardening:** `coverage.xml` is generated inside a harness worktree (an untrusted boundary, per ARCHITECTURE.md §10). Parse it with `defusedxml.ElementTree`, never the stdlib `xml.etree.ElementTree` (XXE / billion-laughs).

---

## File Structure

| File | Responsibility | New/Modified |
|---|---|---|
| `src/sdlc/models.py` | `CriterionTrace`, `AnalysisReport`, `CoverageReport`; `PipelineConfig.coverage_threshold` | Modified |
| `src/sdlc/agents/roles.py` | `ANALYST_PROMPT`, `analyst_agent`, `t_analyst`, `PROMPT_SHAS["analyze"]`, `ALL_TEMPORAL_AGENTS` | Modified |
| `config/agents.yaml` | register `analyst` proposer role (FR-201) | Modified |
| `src/sdlc/activities.py` | `CoverageInput`, `measure_coverage` (Cobertura seam) | Modified |
| `src/sdlc/workflows/feature.py` | `untraced_criteria` helper; analyze stage; 2 advisory checks; stage record + retain | Modified |
| `src/sdlc/worker.py` | register `measure_coverage` activity | Modified |
| `tests/test_analyst_models.py` | model construction + defaults | New |
| `tests/test_untraced_criteria.py` | pure enforcement-helper unit tests | New |
| `tests/test_measure_coverage.py` | coverage seam unit tests | New |
| `tests/test_analyst_wiring.py` | agent registered, prompt sha, worker activity present | New |
| `tests/fakes/canned.py`, `tests/fakes/fake_activities.py` | Analyst spec + fake `measure_coverage` | Modified |
| `tests/test_e2e_greenfield.py` | assert analyze runs + both checks present, still ships | Modified |
| `ROADMAP.md` | flip stage 9 / FR-106 / gate / §8-item-2 | Modified |

---

## Task 1: Data models — `CriterionTrace`, `AnalysisReport`, `CoverageReport`, config field

**Files:**
- Modify: `src/sdlc/models.py` (add models near `ReviewReport` ~line 240; add field to `PipelineConfig` ~line 347)
- Test: `tests/test_analyst_models.py` (create)

**Interfaces:**
- Consumes: existing `ReviewFinding` (already in `models.py`).
- Produces:
  - `CriterionTrace(task_id: str, criterion: str, tests: list[str] = [])`
  - `AnalysisReport(traceability: list[CriterionTrace] = [], findings: list[ReviewFinding] = [], summary: str = "", confidence: float | None = None)`
  - `CoverageReport(measured: bool, diff_pct: float | None = None, detail: str = "")`
  - `PipelineConfig.coverage_threshold: float = 0.0`

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyst_models.py`:

```python
"""AnalysisReport / CriterionTrace / CoverageReport contracts + config field."""
from sdlc.models import (
    AnalysisReport, CoverageReport, CriterionTrace, PipelineConfig, ReviewFinding,
)


def test_criterion_trace_defaults_to_no_tests():
    t = CriterionTrace(task_id="t1", criterion="GET /hello returns 200")
    assert t.tests == []


def test_analysis_report_defaults_are_empty():
    r = AnalysisReport()
    assert r.traceability == []
    assert r.findings == []
    assert r.summary == ""
    assert r.confidence is None


def test_analysis_report_carries_findings_and_traces():
    r = AnalysisReport(
        traceability=[CriterionTrace(task_id="t1", criterion="c1", tests=["test_c1"])],
        findings=[ReviewFinding(assertion="c1", severity="low", detail="nit")],
        summary="ok", confidence=0.9)
    assert r.traceability[0].tests == ["test_c1"]
    assert r.findings[0].severity == "low"


def test_coverage_report_unmeasured():
    c = CoverageReport(measured=False)
    assert c.diff_pct is None


def test_pipeline_config_coverage_threshold_defaults_off():
    assert PipelineConfig().coverage_threshold == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyst_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'AnalysisReport'`.

- [ ] **Step 3: Add the models**

In `src/sdlc/models.py`, immediately after the `ReviewReport` class (after its `blocking_findings` property, ~line 240), add:

```python
class CriterionTrace(BaseModel):
    """One acceptance criterion and the test(s) the Analyst says verify it."""
    task_id: str
    criterion: str
    tests: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """Clean-context Analyst output (stage 9 / FR-106). Emitted from
    orchestrator-assembled inputs only — the authoritative acceptance-criteria
    list + materialized integration diff + aggregate test output. The Analyst
    holds no tools, no repo, no worker session.

    The Analyst PROPOSES the criterion->test mapping; the workflow ENFORCES
    completeness against the plan's criteria. This model never carries a
    pass/fail verdict. `findings` ride along for memory/observability and are
    NOT wired as a blocking gate check.
    """
    traceability: list[CriterionTrace] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class CoverageReport(BaseModel):
    """Diff-scoped coverage evidence for the advisory `coverage` check.
    `measured=False` means no coverage artifact was emitted by the run's test
    commands — the seam could not measure, so the check passes rather than
    forcing a spurious human override every run."""
    measured: bool
    diff_pct: float | None = None       # 0..100 over changed files
    detail: str = ""
```

Then in `PipelineConfig` (after `review_enabled`, ~line 387) add:

```python
    coverage_threshold: float = Field(default=0.0, ge=0.0, le=100.0)
    # FR-106: diff-scoped coverage (0..100) the advisory `coverage` check must
    # clear. Default 0.0 = effectively off until a project opts in AND its test
    # command emits a coverage artifact (see measure_coverage).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyst_models.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py tests/test_analyst_models.py
git commit -m "feat(analyst): AnalysisReport/CriterionTrace/CoverageReport models + coverage_threshold"
```

---

## Task 2: `untraced_criteria` enforcement helper (pure)

The pure function the workflow uses to *enforce* FR-106. Lives at module level in `feature.py` beside the existing `_merge_evidence_all_green` pure helper (~line 93) so it is importable and unit-testable without Temporal.

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (add module-level function ~line 105, after `_merge_evidence_all_green`)
- Test: `tests/test_untraced_criteria.py` (create)

**Interfaces:**
- Consumes: `AnalysisReport`, `CriterionTrace` (Task 1).
- Produces: `untraced_criteria(authoritative: list[tuple[str, str]], report: AnalysisReport) -> list[str]` — returns the `"{task_id}: {criterion}"` label for every authoritative `(task_id, criterion)` the report omits or maps to zero tests. Order preserved from `authoritative`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_untraced_criteria.py`:

```python
"""Pure FR-106 enforcement: the workflow, not the LLM, decides traceability."""
from sdlc.models import AnalysisReport, CriterionTrace
from sdlc.workflows.feature import untraced_criteria


def test_full_mapping_leaves_nothing_untraced():
    auth = [("t1", "GET /hello returns 200"), ("t1", "returns json")]
    report = AnalysisReport(traceability=[
        CriterionTrace(task_id="t1", criterion="GET /hello returns 200",
                       tests=["test_hello_200"]),
        CriterionTrace(task_id="t1", criterion="returns json",
                       tests=["test_hello_json"]),
    ])
    assert untraced_criteria(auth, report) == []


def test_criterion_mapped_to_zero_tests_is_untraced():
    auth = [("t1", "c1")]
    report = AnalysisReport(traceability=[
        CriterionTrace(task_id="t1", criterion="c1", tests=[])])
    assert untraced_criteria(auth, report) == ["t1: c1"]


def test_omitted_criterion_is_untraced_even_if_report_looks_clean():
    # Analyst "forgets" c2 entirely — enforcement must still flag it.
    auth = [("t1", "c1"), ("t1", "c2")]
    report = AnalysisReport(traceability=[
        CriterionTrace(task_id="t1", criterion="c1", tests=["test_c1"])])
    assert untraced_criteria(auth, report) == ["t1: c2"]


def test_mapping_for_wrong_task_does_not_count():
    auth = [("t2", "c1")]
    report = AnalysisReport(traceability=[
        CriterionTrace(task_id="t1", criterion="c1", tests=["test_c1"])])
    assert untraced_criteria(auth, report) == ["t2: c1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_untraced_criteria.py -q`
Expected: FAIL — `ImportError: cannot import name 'untraced_criteria'`.

- [ ] **Step 3: Add the helper**

In `src/sdlc/workflows/feature.py`, after `_merge_evidence_all_green` (~line 104), add. Note: `AnalysisReport` must be added to the models import block (~line 48-54) — add `AnalysisReport,` there.

```python
def untraced_criteria(authoritative: list[tuple[str, str]],
                      report: "AnalysisReport") -> list[str]:
    """FR-106 enforcement (workflow-side, NOT the LLM's verdict).

    A criterion is traced iff the Analyst's report contains a CriterionTrace
    for that exact (task_id, criterion) with a non-empty `tests` list. Any
    authoritative criterion the report omits OR maps to zero tests is untraced.
    Enforced against the plan's authoritative set so an Analyst cannot hide a
    gap by forgetting to list a criterion. Returns "task_id: criterion" labels
    in authoritative order."""
    traced = {(t.task_id, t.criterion)
              for t in report.traceability if t.tests}
    return [f"{task_id}: {criterion}"
            for (task_id, criterion) in authoritative
            if (task_id, criterion) not in traced]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_untraced_criteria.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the purity guard (the workflow module must stay clean)**

Run: `python -m pytest tests/test_factory_purity.py -q`
Expected: PASS — the helper adds no forbidden imports.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_untraced_criteria.py
git commit -m "feat(analyst): pure untraced_criteria enforcement helper (FR-106)"
```

---

## Task 3: `measure_coverage` deterministic seam (Cobertura, diff-scoped)

**Files:**
- Modify: `pyproject.toml` (add `defusedxml` dependency)
- Modify: `src/sdlc/activities.py` (add `CoverageInput` dataclass + `measure_coverage` activity near `security_scan`, ~line 550)
- Test: `tests/test_measure_coverage.py` (create)

**Interfaces:**
- Consumes: `CoverageReport` (Task 1).
- Produces:
  - `CoverageInput(worktree: str, changed_files: list[str])` (dataclass, like `SecurityScanInput`).
  - `measure_coverage(inp: CoverageInput) -> CoverageReport` (`@activity.defn`).

Cobertura `coverage.xml` shape parsed: `<coverage><packages>...<classes><class filename="app/main.py" line-rate="0.8">`. Diff-scoped percentage = mean `line-rate * 100` over `<class>` elements whose `filename` matches a `changed_files` entry (suffix match, since coverage paths may be relative to a subdir). No file found / no match / parse error → `measured=False`.

**Security:** `coverage.xml` originates inside a harness worktree (untrusted, ARCHITECTURE.md §10). Parse with `defusedxml.ElementTree` — it blocks XXE (external entities) and billion-laughs (entity-expansion DoS) that the stdlib `xml.etree.ElementTree` is vulnerable to by default. A malformed/malicious file surfaces as `defusedxml`'s `ParseError`/`EntitiesForbidden`, which we catch and treat as `measured=False`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_measure_coverage.py`:

```python
"""measure_coverage: deterministic diff-scoped Cobertura seam."""
import pathlib

import pytest

from sdlc.activities import CoverageInput, measure_coverage

COBERTURA = """<?xml version="1.0" ?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class filename="app/main.py" line-rate="0.80"/>
        <class filename="app/util.py" line-rate="0.40"/>
      </classes>
    </package>
  </packages>
</coverage>
"""


@pytest.mark.asyncio
async def test_no_artifact_means_unmeasured(tmp_path):
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.measured is False
    assert r.diff_pct is None


@pytest.mark.asyncio
async def test_diff_scoped_percentage_over_changed_files(tmp_path):
    (tmp_path / "coverage.xml").write_text(COBERTURA, encoding="utf-8")
    # Only app/main.py changed -> 80%, ignoring app/util.py's 40%.
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.measured is True
    assert r.diff_pct == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_no_changed_file_in_report_means_unmeasured(tmp_path):
    (tmp_path / "coverage.xml").write_text(COBERTURA, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["other/thing.py"]))
    assert r.measured is False


# billion-laughs: entity expansion DoS. defusedxml must refuse it and we must
# degrade to measured=False, never hang or raise. (coverage.xml is generated
# in an untrusted harness worktree — ARCHITECTURE.md §10.)
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE coverage [
  <!ENTITY a "aaaaaaaaaa">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<coverage><packages><package><classes>
  <class filename="app/main.py" line-rate="0.8">&c;</class>
</classes></package></packages></coverage>
"""


@pytest.mark.asyncio
async def test_malicious_xml_degrades_to_unmeasured(tmp_path):
    (tmp_path / "coverage.xml").write_text(BILLION_LAUGHS, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.measured is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_measure_coverage.py -q`
Expected: FAIL — `ImportError: cannot import name 'CoverageInput'`.

- [ ] **Step 3: Add the `defusedxml` dependency**

In `pyproject.toml`, add to the `dependencies` list (after `"httpx>=0.27",`):

```toml
    "defusedxml>=0.7",
```

Then install it into the working environment:

Run: `python -m pip install "defusedxml>=0.7"`
Expected: `Successfully installed defusedxml-0.7.x` (or "already satisfied").

- [ ] **Step 4: Add the activity**

In `src/sdlc/activities.py`: add `CoverageReport` to the models import (~line 26, alongside `SecurityReport`), and add after the `security_scan` activity (~line 549). Use `defusedxml`, NOT the stdlib parser — `coverage.xml` comes from an untrusted worktree:

```python
import defusedxml.ElementTree as DET
from defusedxml.common import DefusedXmlException


@dataclass
class CoverageInput:
    worktree: str
    changed_files: list[str]


@activity.defn
async def measure_coverage(inp: CoverageInput) -> CoverageReport:
    """Diff-scoped coverage from a Cobertura coverage.xml already emitted into
    the worktree by the run's test commands (FR-106). Minimal deterministic
    seam — pure filesystem read, reproducible across retries. Real per-stack
    instrumentation replaces only this body.

    The file is generated inside a harness worktree (untrusted, ARCHITECTURE.md
    §10), so it is parsed with defusedxml to block XXE / entity-expansion DoS.

    measured=False (check passes as a no-op) when there is no coverage.xml, it
    is unparseable/malicious, or none of the changed files appear in it — an
    unbuilt measurement must never force a human override."""
    path = os.path.join(inp.worktree, "coverage.xml")
    if not os.path.isfile(path):
        return CoverageReport(measured=False,
                              detail="no coverage.xml (seam not measured)")
    try:
        root = DET.parse(path).getroot()
    except (DefusedXmlException, DET.ParseError, OSError):
        return CoverageReport(measured=False,
                              detail="coverage.xml unparseable or unsafe")
    rates: list[float] = []
    for cls in root.iter("class"):
        fname = cls.get("filename") or ""
        if any(fname == cf or fname.endswith("/" + cf) or cf.endswith("/" + fname)
               or cf.endswith(fname) for cf in inp.changed_files):
            try:
                rates.append(float(cls.get("line-rate", "0")) * 100.0)
            except ValueError:
                continue
    if not rates:
        return CoverageReport(
            measured=False,
            detail="no changed file found in coverage.xml (seam not measured)")
    pct = sum(rates) / len(rates)
    return CoverageReport(measured=True, diff_pct=pct,
                          detail=f"diff-scoped coverage {pct:.1f}% "
                                 f"over {len(rates)} changed file(s)")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_measure_coverage.py -q`
Expected: PASS (4 passed — includes the billion-laughs hardening case).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/sdlc/activities.py tests/test_measure_coverage.py
git commit -m "feat(analyst): measure_coverage diff-scoped Cobertura seam (defusedxml-hardened)"
```

---

## Task 4: Analyst agent + registry entry

**Files:**
- Modify: `src/sdlc/agents/roles.py` (prompt, agent, temporal wrapper, `PROMPT_SHAS`, `ALL_TEMPORAL_AGENTS`)
- Modify: `config/agents.yaml` (register `analyst` proposer)
- Test: `tests/test_analyst_wiring.py` (create — agent + prompt-sha portion; worker portion added in Task 5)

**Interfaces:**
- Consumes: `AnalysisReport` (Task 1).
- Produces: `analyst_agent` (Pydantic AI `Agent`, name `"analyst_agent"`), `t_analyst` (`TemporalAgent`), `PROMPT_SHAS["analyze"]`, membership in `ALL_TEMPORAL_AGENTS`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyst_wiring.py`:

```python
"""Analyst agent is defined, prompt-hashed, and in the temporal-agent list."""
from sdlc.agents.roles import (
    ALL_TEMPORAL_AGENTS, PROMPT_SHAS, analyst_agent, t_analyst,
)
from sdlc.models import AnalysisReport


def test_analyst_agent_named_and_typed():
    assert analyst_agent.name == "analyst_agent"
    assert analyst_agent.output_type is AnalysisReport


def test_analyze_prompt_is_hashed():
    assert "analyze" in PROMPT_SHAS
    assert len(PROMPT_SHAS["analyze"]) == 64  # sha256 hex


def test_analyst_in_all_temporal_agents():
    assert t_analyst in ALL_TEMPORAL_AGENTS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyst_wiring.py -q`
Expected: FAIL — `ImportError: cannot import name 'analyst_agent'`.

- [ ] **Step 3: Add the agent**

In `src/sdlc/agents/roles.py`:

Add `AnalysisReport` to the models import block (~line 24-31):

```python
from ..models import (
    AnalysisReport,
    ArchitectureSpec,
    ClarifiedRequirements,
    ImplementationPlan,
    MergeVerdict,
    QAReport,
    ReviewReport,
)
```

Add the prompt after `REVIEWER_PROMPT` (~line 114):

```python
ANALYST_PROMPT = (
    "You are a clean-context release analyst. You receive ONLY: the run's "
    "acceptance criteria (each tagged with its task id), the materialized "
    "integration diff, and the aggregate test output. You never see, and "
    "must never request, any implementer's summary, reasoning, or session. "
    "For EACH acceptance criterion, populate a CriterionTrace with the exact "
    "test name(s) in the diff/test output that verify it; leave 'tests' empty "
    "if nothing does — do NOT invent a test name. Copy each criterion's "
    "task_id and text verbatim so it matches the plan. Report any "
    "integration-level concerns as 'findings'. Set a calibrated 0.0-1.0 "
    "confidence. You do not decide pass/fail — you only propose the mapping."
)
```

Add the agent after `reviewer_agent` (~line 167):

```python
analyst_agent = Agent(
    MODEL,
    name="analyst_agent",
    output_type=AnalysisReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=ANALYST_PROMPT,
)
```

Add to `PROMPT_SHAS` (~line 185):

```python
    "analyze": hashlib.sha256(ANALYST_PROMPT.encode()).hexdigest(),
```

Add the temporal wrapper after `t_reviewer` (~line 198) and into `ALL_TEMPORAL_AGENTS`:

```python
t_analyst = TemporalAgent(analyst_agent, activity_config=AGENT_ACTIVITY_CONFIG)
```

```python
ALL_TEMPORAL_AGENTS = [t_clarify, t_architect, t_planner, t_qa,
                       t_reviewer, t_analyst, t_merge_verdict, t_devops]
```

- [ ] **Step 4: Register in the versioned registry (FR-201)**

In `config/agents.yaml`, under `roles:`, add (proposer, no harness — like `reviewer`; not load-bearing for the agent, which binds `roles.MODEL`, but completes the FR-201 registry):

```yaml
  analyst:
    kind: proposer                # clean-context stage-9 analyst (FR-106)
    model: anthropic:glm-5.2
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_analyst_wiring.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Confirm the registry still boots (validator unaffected)**

Run: `python -c "from sdlc.agents.loader import load_registry, validate_registry; validate_registry(load_registry()); print('registry ok')"`
Expected: prints `registry ok` (adding a proposer role does not violate the developer/reviewer family rule).

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/agents/roles.py config/agents.yaml tests/test_analyst_wiring.py
git commit -m "feat(analyst): analyst_agent proposer + prompt + registry entry"
```

---

## Task 5: Register `measure_coverage` on the worker

**Files:**
- Modify: `src/sdlc/worker.py` (import + activities list)
- Test: extend `tests/test_analyst_wiring.py`

**Interfaces:**
- Consumes: `measure_coverage` (Task 3). `t_analyst` already reaches the worker via `ALL_TEMPORAL_AGENTS` (Task 4) — no separate registration needed for the agent.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analyst_wiring.py`:

```python
def test_measure_coverage_registered_on_worker():
    # The worker's activity list is assembled in main(); assert the callable
    # is imported into the worker module and included alongside security_scan.
    import inspect

    import sdlc.worker as w

    assert hasattr(w, "measure_coverage")
    src = inspect.getsource(w.main)
    assert "measure_coverage" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyst_wiring.py::test_measure_coverage_registered_on_worker -q`
Expected: FAIL — `AttributeError: module 'sdlc.worker' has no attribute 'measure_coverage'`.

- [ ] **Step 3: Register the activity**

In `src/sdlc/worker.py`, add `measure_coverage` to the activities import (~line 28-32):

```python
from .activities import (
    create_worktree, deploy, evaluate_gate, get_task_diff,
    measure_coverage, merge_into_integration, open_pull_request,
    run_coding_task, run_lint, run_test_suite, security_scan,
    setup_integration_branch,
)
```

And into the `activities=[...]` list in `main()` (~line 66-68), next to `security_scan`:

```python
            run_coding_task, run_lint, run_test_suite, security_scan,
            measure_coverage,
            open_pull_request, deploy,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyst_wiring.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the worker-registration guard (if it enumerates activities)**

Run: `python -m pytest tests/test_worker_registration.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/worker.py tests/test_analyst_wiring.py
git commit -m "feat(analyst): register measure_coverage activity on the worker"
```

---

## Task 6: Wire the analyze stage into `FeatureWorkflow`

Insert stage 9 between the end of the task loop and the merge-gate evidence collection, and append the two advisory checks. This is the load-bearing task.

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (imports; new stage block before `# 5. MERGE` at ~line 787; two `build_check` appends in the `checks` list ~line 811)
- Test: `tests/test_analyst_stage_wiring.py` (create)

**Interfaces:**
- Consumes: `t_analyst` (Task 4), `untraced_criteria` (Task 2), `measure_coverage`/`CoverageInput` (Task 3), `get_task_diff`/`DiffInput` (existing), `AnalysisReport`/`CoverageReport` (Task 1), `plan.tasks`, `done` (dict of `TaskResult`), `self._integration_wt`, `idea.base_branch`.
- Produces: an `analysis: AnalysisReport` in scope, plus `traceability` and `coverage` entries in the `checks` list passed to `evaluate_gate`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyst_stage_wiring.py` — a source-level assertion that the stage is wired (a full workflow re-run is covered by the e2e in Task 7; this task guards the specific wiring cheaply):

```python
"""The analyze stage is wired into FeatureWorkflow before the merge gate,
and both advisory checks are built from its output."""
import inspect

from sdlc.workflows import feature


def test_analyze_stage_calls_analyst_and_builds_both_checks():
    src = inspect.getsource(feature.FeatureWorkflow.run)
    # Analyst invoked
    assert "t_analyst.run(" in src
    # Enforcement helper used (not an LLM verdict)
    assert "untraced_criteria(" in src
    # Both advisory checks appended
    assert 'build_check(\n                "traceability"' in src or \
           'build_check("traceability"' in src
    assert '"coverage"' in src
    assert "measure_coverage" in src


def test_analyze_runs_before_merge_evidence():
    src = inspect.getsource(feature.FeatureWorkflow.run)
    assert src.index("t_analyst.run(") < src.index("evaluate_gate")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyst_stage_wiring.py -q`
Expected: FAIL — `t_analyst.run(` not found in source.

- [ ] **Step 3: Add imports**

In `src/sdlc/workflows/feature.py`:

- Add `measure_coverage, CoverageInput` to the activities import block (~line 16-23):

```python
        QAInput, SecurityScanInput, WorktreeInput, create_worktree, deploy,
        evaluate_gate, get_task_diff, measure_coverage, merge_into_integration,
        open_pull_request, run_coding_task, run_lint, run_test_suite,
        security_scan, setup_integration_branch,
    )
```

  and `CoverageInput` where the input dataclasses are imported (same block — add `CoverageInput,` to the first line):

```python
        CodingTaskInput, CoverageInput, DeployInput, DiffInput, IntegrationHandle,
```

- Add `t_analyst` to the roles import (~line 24-27):

```python
    from ..agents.roles import (
        MODEL, PROMPT_SHAS, t_analyst, t_architect, t_clarify,
        t_merge_verdict, t_planner, t_qa, t_reviewer,
    )
```

- Add `AnalysisReport, CoverageReport` to the models import (~line 48-54): `AnalysisReport,` (added in Task 2) and `CoverageReport,`.

- [ ] **Step 4: Insert the analyze stage block**

In `src/sdlc/workflows/feature.py`, immediately **before** the `# 5. MERGE ...` comment (~line 787), insert the stage. `done` and `plan` are already in scope here.

```python
        # 4b. ANALYZE (stage 9) — clean-context Analyst proposes the
        # criterion->test mapping; the workflow enforces it (FR-106). Runs on
        # the integrated whole, before the merge gate.
        self._status = "analyzing"
        _an_started = workflow.now()
        integration_diff = await workflow.execute_activity(
            get_task_diff,
            DiffInput(worktree=self._integration_wt,
                      branch_point=idea.base_branch),
            **ACT)
        authoritative: list[tuple[str, str]] = [
            (t.id, c) for t in plan.tasks for c in t.acceptance_criteria]
        _criteria_lines = "\n".join(f"- [{tid}] {crit}"
                                    for tid, crit in authoritative)
        _qa_lines = "\n".join(
            f"- {r.task_id}: tests_passed={r.qa.tests_passed if r.qa else 'n/a'}"
            f" failing={r.qa.failing_tests if r.qa else []}"
            for r in done.values())
        analysis: AnalysisReport = (await t_analyst.run(
            "Acceptance criteria (task_id in brackets):\n" + _criteria_lines
            + "\nAggregate test output:\n" + _qa_lines
            + f"\nIntegration diff stat:\n{integration_diff['stat']}"
            + f"\nIntegration diff:\n{integration_diff['patch']}")).output
        untraced = untraced_criteria(authoritative, analysis)
        cov: CoverageReport = await workflow.execute_activity(
            measure_coverage,
            CoverageInput(worktree=self._integration_wt,
                          changed_files=integration_diff["files"]),
            **ACT)
        await self._record(cfg, self._stage_record(
            cfg, stage="analyze", role="analyst",
            started=_an_started, ended=workflow.now(),
            quality_score=(1.0 if not untraced else 0.0),
            judge="contract",
            outcome=(BenchmarkOutcome.PASS if not untraced
                     else BenchmarkOutcome.FAIL),
            model="anthropic:glm-5.2"))
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"analyze: {len(authoritative)} criteria, "
                 f"{len(untraced)} untraced. {analysis.summary}",
            metadata={"stage": "analyze",
                      "run_id": workflow.info().workflow_id})
        if untraced:
            await self._retain(
                cfg, MemoryKind.GOTCHA, cfg.memory.project_bank,
                text=f"untraced acceptance criteria at merge: {untraced}",
                metadata={"stage": "analyze",
                          "run_id": workflow.info().workflow_id})
```

- [ ] **Step 5: Append the two advisory checks**

In the `checks = [ ... ]` list (~line 811-827), after the `review_severity` `build_check(...)` and before the closing `]`, add:

```python
            build_check(
                "traceability", not untraced, CheckClass.ADVISORY,
                detail=(f"{len(untraced)} criterion(s) without a test: "
                        f"{untraced[:10]}" if untraced
                        else "every acceptance criterion traces to >=1 test")),
            build_check(
                "coverage",
                (True if not cov.measured
                 else (cov.diff_pct or 0.0) >= cfg.coverage_threshold),
                CheckClass.ADVISORY,
                detail=(cov.detail if not cov.measured
                        else f"diff coverage {cov.diff_pct:.1f}% vs threshold "
                             f"{cfg.coverage_threshold:.1f}%")),
```

- [ ] **Step 6: Run the wiring test + purity guard**

Run: `python -m pytest tests/test_analyst_stage_wiring.py tests/test_factory_purity.py -q`
Expected: PASS. (If the source-substring assertions in Step 1 are brittle against your exact formatting, adjust the test's expected substrings to match the code you wrote — the intent is: `t_analyst.run(`, `untraced_criteria(`, `"traceability"`, `"coverage"`, `measure_coverage` all present, and analyze precedes `evaluate_gate`.)

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_analyst_stage_wiring.py
git commit -m "feat(analyst): wire stage-9 analyze + traceability/coverage advisory checks"
```

---

## Task 7: Fakes + end-to-end proof

Extend the deterministic offline e2e so the real `FeatureWorkflow` runs the new stage and still ships, and the gate report carries both new checks.

**Files:**
- Modify: `tests/fakes/canned.py` (add `AnalysisReport` import + `ANALYSIS_OK` + spec)
- Modify: `tests/fakes/fake_activities.py` (add `fake_measure_coverage` + into `GIT_FAKES`)
- Modify: `tests/test_e2e_greenfield.py` (assert both checks present via a query, still `deployed:`)

**Interfaces:**
- Consumes: `AnalysisReport`, `CriterionTrace` (Task 1); the canned `PLAN` single task `t1` with criterion `"GET /hello returns 200"`; `measure_coverage`/`CoverageInput`/`CoverageReport` (Task 3).
- Produces: `analyst_agent` fake spec matching the plan's criteria (so `untraced == []`); `fake_measure_coverage` returning `measured=False` (coverage check passes as no-op).

- [ ] **Step 1: Add the canned Analyst output**

In `tests/fakes/canned.py`, add to the models import (~line 9-14): `AnalysisReport, CriterionTrace,`. Then after `REVIEW_OK` (~line 52) add — the mapping MUST match `PLAN`'s authoritative `(t1, "GET /hello returns 200")` so enforcement finds it traced:

```python
ANALYSIS_OK = AnalysisReport(
    traceability=[CriterionTrace(
        task_id="t1", criterion="GET /hello returns 200",
        tests=["test_hello_returns_200"])],
    summary="all criteria traced", confidence=0.95)
```

Add to `AGENT_SPECS` (~line 55-62), after the `reviewer_agent` entry:

```python
    ("analyst_agent", AnalysisReport, ANALYSIS_OK),
```

- [ ] **Step 2: Add the fake coverage activity**

In `tests/fakes/fake_activities.py`, add to the activities/models imports (~line 9-14): `CoverageInput` from `sdlc.activities`, `CoverageReport` from `sdlc.models`. Then add before `GIT_FAKES`:

```python
@activity.defn(name="measure_coverage")
async def fake_measure_coverage(inp: CoverageInput) -> CoverageReport:
    # No coverage artifact in this offline run -> unmeasured, check passes.
    return CoverageReport(measured=False, detail="fake: unmeasured")
```

Add `fake_measure_coverage` to the `GIT_FAKES` list.

- [ ] **Step 3: Run the e2e to verify it still ships**

Run: `python -m pytest tests/test_e2e_greenfield.py -q`
Expected: PASS — the run reaches `deployed:` with the analyze stage now in the path. (If it fails with a missing-activity dispatch error for `measure_coverage`, confirm Step 2 added it to `GIT_FAKES`; if `analyst_agent` is unregistered, confirm Step 1 added it to `AGENT_SPECS`.)

- [ ] **Step 4: Assert both checks reach the gate**

The workflow exposes the gate report only via its return value / stage records, not a live query, so assert at the source-wiring level is already covered (Task 6). Add one behavioral assertion to `tests/test_e2e_greenfield.py`: introduce an Analyst fake variant that omits the criterion and confirm the run still ships (advisory, threshold path) — proving the advisory check does not hard-block. Append:

```python
@pytest.mark.asyncio
async def test_untraced_criterion_is_advisory_not_blocking(monkeypatch):
    """An Analyst that maps nothing still ships end-to-end under HARD merge:
    traceability is ADVISORY, so the human merge gate (auto-approved here via
    the driver) waves it through — it never becomes a terminal absolute block."""
    from sdlc.models import AnalysisReport
    from tests.fakes import canned

    empty = ("analyst_agent", AnalysisReport, AnalysisReport(summary="none"))
    specs = [s for s in AGENT_SPECS if s[0] != "analyst_agent"] + [empty]
    activities = [evaluate_gate, *GIT_FAKES, *fake_agent_activities(specs)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                    env.client, task_queue=TASK_QUEUE,
                    workflows=[FeatureWorkflow], activities=activities,
                    plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config()],
                    id=f"e2e-untraced-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive_with_merge(handle))
                result = await handle.result()
                await driver
    assert result.startswith("deployed:"), result
```

Add a merge-approving driver variant near `_drive` (~line 44). With an untraced criterion the advisory gate fails, so the workflow enters `awaiting:merge` — the driver must approve merge too:

```python
async def _drive_with_merge(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    for gate in ("architecture", "plan", "merge", "deploy"):
        await _wait_for_status(handle, f"awaiting:{gate}")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=gate, round=1, outcome=GateOutcome.APPROVE,
                         decided_by="human"))
```

- [ ] **Step 5: Run the full e2e file**

Run: `python -m pytest tests/test_e2e_greenfield.py -q`
Expected: PASS (2 passed) — the clean run ships, and the untraced-but-advisory run also ships after a human merge approval.

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS (no regressions). Pay attention to `test_merge_gate_wiring.py` and `test_worker_registration.py` — if either enumerates expected checks/activities explicitly, update it to include `traceability`, `coverage`, and `measure_coverage`.

- [ ] **Step 7: Commit**

```bash
git add tests/fakes/canned.py tests/fakes/fake_activities.py tests/test_e2e_greenfield.py
git commit -m "test(analyst): e2e proof stage-9 analyze ships; advisory traceability non-blocking"
```

---

## Task 8: Roadmap updates

**Files:**
- Modify: `ROADMAP.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Update the tracker**

In `ROADMAP.md`:

- §1 stage **9 · analyze** — change `[ ]` to `[x]`: "Analyst clean-context proposer (`t_analyst`) emits `AnalysisReport`; workflow enforces criterion→test traceability against the plan's authoritative criteria (FR-106)."
- §1 stage **11 · quality_gate** — remove "coverage and traceability checks still unbuilt"; note both now built, coverage via a deterministic Cobertura seam (`measured=False` ⇒ no-op until a project emits coverage + sets `coverage_threshold`).
- §2 **FR-106** — change `⚠️` note: traceability enforced ✅; coverage wired as a deterministic diff-scoped seam ✅ (real instrumentation future work).
- §8 item **2 (Analyze/Analyst stage)** — mark done, pointer to `docs/superpowers/specs/2026-07-16-analyst-stage-traceability-coverage-design.md` and this plan.
- Update the header "Last verified" date to `2026-07-16`.

- [ ] **Step 2: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): stage-9 analyze + traceability/coverage checks done"
```

---

## Self-Review Notes (author checklist — verified before handoff)

- **Spec coverage:** §2 placement → Task 6; §3 models → Task 1; §4 enforcement (`untraced_criteria` + two checks) → Tasks 2 & 6; §5 coverage seam → Task 3; §6 agent + registry → Task 4 (+ worker Task 5); §7 stage record + memory → Task 6; §8 tests → Tasks 1–3, 6, 7; §9 roadmap → Task 8. All covered.
- **Type consistency:** `AnalysisReport`, `CriterionTrace`, `CoverageReport`, `CoverageInput`, `measure_coverage`, `untraced_criteria`, `analyst_agent`, `t_analyst`, `PROMPT_SHAS["analyze"]` used identically across tasks.
- **Enforcement not trust:** traceability check derives from `untraced_criteria(authoritative, analysis)` (workflow), never from an LLM boolean — FR-106 honored.
- **Advisory only:** both checks are `CheckClass.ADVISORY`; `gate.py` and the absolute floor are untouched — SC-5 preserved.
- **Coverage no-op safety:** `measured=False` ⇒ check passes; the fake returns `measured=False`, so the primary e2e ships without a spurious merge gate.
```
