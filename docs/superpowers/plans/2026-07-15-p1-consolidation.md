# P1 Consolidation — End-to-End Proof + Honest Absolute Floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the wired `FeatureWorkflow` composes end-to-end (greenfield `IdeaBrief` → `deployed:` return) with a deterministic, offline, CI-runnable orchestration test, and make `security_no_critical` a real absolute merge-gate check so SC-5 stops being vacuous.

**Architecture:** The production path is unchanged. The end-to-end test runs the real `FeatureWorkflow` on a time-skipping `WorkflowEnvironment` with a single in-process worker; non-determinism is faked at two seams — (1) proposer **models** via Pydantic AI `TestModel(custom_output_args=...)` wrapped in same-named `TemporalAgent`s, and (2) git/subprocess **activities** via same-named `@activity.defn` fakes. A driver coroutine answers the clarify question and the architecture/plan/deploy gates via signals. Thread B adds a deterministic `security_scan` activity feeding an absolute gate check.

**Tech Stack:** Python ≥3.11, Pydantic v2, Pydantic AI 2.5.0 (`TestModel`, `TemporalAgent`), Temporal Python SDK (`temporalio.testing.WorkflowEnvironment`), pytest, pytest-asyncio.

## Global Constraints

- Python ≥3.11; Pydantic v2 models only (`from __future__ import annotations` in every new module).
- **Determinism boundary (ADR-1/§14):** nothing under `src/sdlc/workflows/` may import `subprocess`, HTTP clients, the memory client, or the harness package. `security_scan` is an **activity** (`src/sdlc/activities.py`), never called inline in workflow code.
- **Agent/toolset names are Temporal activity names.** Fake `TemporalAgent`s MUST reuse the exact production agent `name=` strings or activity dispatch will not match. The names are: `clarify_agent`, `architect_agent`, `planner_agent`, `qa_analyst_agent`, `reviewer_agent`, `merge_verdict_agent`.
- **Absolute-floor promotion is automatic:** `build_check(name, …)` in `src/sdlc/gate.py` forces any name in `ABSOLUTE_FLOOR = {"security_no_critical"}` to `CheckClass.ABSOLUTE` regardless of the requested class. Pass `CheckClass.ABSOLUTE` explicitly anyway for readability.
- Run tests with `python -m pytest` (Scripts dir may not be on PATH).
- **Test fixtures are `tests/fakes/`**, not `src/`. No production import may depend on `tests/`.
- Commit style: `feat(scope): …` / `test(scope): …`.
- The workflow class is `FeatureWorkflow` (docs call it `FactoryWorkflow` — do **not** rename; out of scope).

---

## File Structure

- **Create** `tests/fakes/__init__.py` — package marker.
- **Create** `tests/fakes/fake_agents.py` — build same-named `TemporalAgent`s bound to `TestModel` canned outputs; collect their activities. (Task 1)
- **Create** `tests/test_spike_agent_stub.py` — the mechanism spike; retained as a permanent smoke test. (Task 1)
- **Modify** `src/sdlc/models.py` — `SecurityFinding`, `SecurityReport`. (Task 2)
- **Modify** `src/sdlc/activities.py` — `SecurityScanInput`, `security_scan` activity. (Task 2)
- **Create** `tests/test_security_floor.py` — scanner unit tests + gate-wiring assertions. (Tasks 2, 3)
- **Modify** `src/sdlc/worker.py` — register `security_scan`. (Task 3)
- **Modify** `src/sdlc/workflows/feature.py` — run `security_scan` in the merge gate; append the absolute check. (Task 3)
- **Create** `tests/fakes/canned.py` — canned proposer artifacts + `greenfield_idea()` + `e2e_config()`. (Task 4)
- **Create** `tests/fakes/fake_activities.py` — same-named fakes for the git/subprocess activities. (Task 4)
- **Create** `tests/test_e2e_greenfield.py` — the P1 proof: driver + assertions. (Task 5)

---

### Task 1: Spike — prove the agent-stub mechanism across a time-skipping worker

Establishes the highest-risk unknown before any test infrastructure is built: that `TestModel(custom_output_args=...)`, wrapped in a same-named `TemporalAgent`, dispatches through Temporal's time-skipping worker and returns the canned typed output. Delivers the reusable `fake_agents.py` helper the e2e test depends on.

**Files:**
- Create: `tests/fakes/__init__.py`
- Create: `tests/fakes/fake_agents.py`
- Create: `tests/test_spike_agent_stub.py`

**Interfaces:**
- Consumes: `sdlc.agents.roles.AGENT_ACTIVITY_CONFIG`; `sdlc.agents.roles.t_clarify`; `sdlc.models.ClarifiedRequirements`.
- Produces: `fake_temporal_agent(name: str, output_type: type, value: BaseModel) -> TemporalAgent`; `fake_agent_activities(specs: list[tuple[str, type, BaseModel]]) -> list` (flat list of Temporal activity callables).

- [ ] **Step 1: Create the package marker**

Create `tests/fakes/__init__.py`:

```python
```

(Empty file.)

- [ ] **Step 2: Write the fake-agent helper**

Create `tests/fakes/fake_agents.py`:

```python
"""Deterministic, offline stand-ins for the proposer TemporalAgents.

Each fake reuses the PRODUCTION agent name so its generated Temporal
activity names match — the workflow's `t_<role>.run(...)` then dispatches
to the fake when only these activities are registered on the test worker.
The model is Pydantic AI's TestModel forced to emit a canned typed output.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalAgent
from pydantic_ai.models.test import TestModel

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG


def fake_temporal_agent(name: str, output_type: type, value: BaseModel) -> TemporalAgent:
    """A TemporalAgent whose model always returns `value` as `output_type`."""
    agent = Agent(
        TestModel(custom_output_args=value.model_dump(mode="json")),
        name=name,
        output_type=output_type,
    )
    return TemporalAgent(agent, activity_config=AGENT_ACTIVITY_CONFIG)


def fake_agent_activities(specs: list[tuple[str, type, BaseModel]]) -> list:
    """Flatten the Temporal activities for a list of (name, type, value)."""
    activities: list = []
    for name, output_type, value in specs:
        ta = fake_temporal_agent(name, output_type, value)
        activities.extend(ta.temporal_activities)
    return activities
```

- [ ] **Step 3: Write the failing spike test**

Create `tests/test_spike_agent_stub.py`:

```python
"""Spike + permanent smoke test: a same-named fake TemporalAgent dispatches
through a time-skipping Temporal worker and returns the canned typed output.
If this fails, the e2e agent seam (Task 5) cannot work — see the plan's
Task 1 fallback note."""

from __future__ import annotations

import uuid

import pytest
from temporalio import workflow
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.models import ClarifiedRequirements, OpenQuestion
from tests.fakes.fake_agents import fake_agent_activities

with workflow.unsafe.imports_passed_through():
    from sdlc.agents.roles import t_clarify

CANNED = ClarifiedRequirements(
    summary="CANNED-SUMMARY",
    functional_requirements=["fr1"],
    non_functional_requirements=[],
    out_of_scope=[],
    open_questions=[
        OpenQuestion(id="q1", question="?", why_it_matters="x", suggested_answer="yes")
    ],
)


@workflow.defn
class _OneShotWorkflow:
    @workflow.run
    async def run(self) -> str:
        reqs = (await t_clarify.run("hi")).output
        return reqs.summary


@pytest.mark.asyncio
async def test_fake_agent_dispatches_canned_output():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        acts = fake_agent_activities(
            [
                ("clarify_agent", ClarifiedRequirements, CANNED),
            ]
        )
        async with Worker(
            env.client,
            task_queue="spike",
            workflows=[_OneShotWorkflow],
            activities=acts,
            plugins=[PydanticAIPlugin()],
        ):
            result = await env.client.execute_workflow(
                _OneShotWorkflow.run, id=f"spike-{uuid.uuid4()}", task_queue="spike"
            )
    assert result == "CANNED-SUMMARY"
```

- [ ] **Step 4: Run the spike to verify it passes**

Run: `python -m pytest tests/test_spike_agent_stub.py -v`
Expected: PASS.

**If it FAILS, diagnose before proceeding — this is the spike's purpose:**
- `WorkflowEnvironment.start_time_skipping()` errors downloading the test-server binary → the CI/dev box has no network for the one-time binary fetch. Blocker: obtain the `temporal` test-server binary (temporalio ships it) or pre-cache it; raise with the human before continuing.
- Result is empty/`None` or a validation error instead of `"CANNED-SUMMARY"` → the model seam did not cross the activity boundary. Fallback: instead of registering a fake `TemporalAgent`'s activities, register plain `@activity.defn` functions whose names equal the production agent activity names (introspect `t_clarify.temporal_activities[i].__name__`) returning `CANNED`. Update `fake_agent_activities` accordingly, keeping its signature stable.
- `PydanticAIPlugin` / data-converter errors → ensure both the `Worker` **and** the client use them (the test above sets the plugin on the worker and `pydantic_data_converter` on the env client).

- [ ] **Step 5: Commit**

```bash
git add tests/fakes/__init__.py tests/fakes/fake_agents.py tests/test_spike_agent_stub.py
git commit -m "test(e2e): spike + helper for time-skipping fake-agent dispatch"
```

---

### Task 2: SecurityReport contract + deterministic `security_scan` activity

**Files:**
- Modify: `src/sdlc/models.py` (add after `QAReport`, ~line 201)
- Modify: `src/sdlc/activities.py` (add near the QA activities, after `run_lint` ~line 500)
- Test: `tests/test_security_floor.py`

**Interfaces:**
- Produces: `SecurityFinding{severity: Literal["critical","high","medium","low"], rule: str, detail: str, path: str = ""}`; `SecurityReport{critical: int, findings: list[SecurityFinding] = []}`; `SecurityScanInput{worktree: str}`; `async def security_scan(inp: SecurityScanInput) -> SecurityReport`.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing test**

Create `tests/test_security_floor.py`:

```python
from __future__ import annotations

import pathlib

import pytest

from sdlc.activities import SecurityScanInput, security_scan
from sdlc.models import SecurityReport


def test_security_report_defaults_clean():
    r = SecurityReport(critical=0)
    assert r.findings == []
    assert r.critical == 0


@pytest.mark.asyncio
async def test_security_scan_clean_worktree(tmp_path: pathlib.Path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical == 0


@pytest.mark.asyncio
async def test_security_scan_flags_hardcoded_secret(tmp_path: pathlib.Path):
    (tmp_path / "cfg.py").write_text(
        'AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLEKEY1234567890abcd"\n', encoding="utf-8"
    )
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical >= 1
    assert any(f.severity == "critical" for f in report.findings)


@pytest.mark.asyncio
async def test_security_scan_flags_eval_of_input(tmp_path: pathlib.Path):
    (tmp_path / "danger.py").write_text("def run(s):\n    return eval(s)\n", encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_security_floor.py -v`
Expected: FAIL — `ImportError: cannot import name 'SecurityScanInput'`.

- [ ] **Step 3: Add the models**

In `src/sdlc/models.py`, immediately after the `QAReport` class add:

```python
class SecurityFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    rule: str  # which scanner rule matched
    detail: str
    path: str = ""


class SecurityReport(BaseModel):
    """Deterministic scanner evidence for the merge gate's absolute floor
    (FR-106/NFR-5/SC-5). `critical` is the count feeding the
    `security_no_critical` absolute check; a minimal ruleset now, seam to a
    real SAST later."""

    critical: int
    findings: list[SecurityFinding] = Field(default_factory=list)
```

(`Literal` and `Field` are already imported in `models.py`.)

- [ ] **Step 4: Add the scanner activity**

In `src/sdlc/activities.py`, after the `run_lint` activity add:

```python
# Minimal deterministic security ruleset (FR-106 absolute floor). Each entry
# is (compiled_regex, severity, rule_name, human_detail). Intentionally small
# and offline; the seam for a real SAST is this function's return type.
_SECURITY_RULES: list[tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"(?i)(aws_secret_access_key|secret_key)\s*=\s*['\"][A-Za-z0-9/+]{20,}['\"]"),
        "critical",
        "hardcoded-secret",
        "hardcoded credential/secret literal",
    ),
    (re.compile(r"\beval\s*\("), "critical", "dangerous-eval", "use of eval() on untrusted input"),
    (
        re.compile(r"subprocess\.[a-z_]+\([^)]*shell\s*=\s*True"),
        "high",
        "shell-injection",
        "subprocess call with shell=True",
    ),
]

_SECURITY_SCAN_EXTENSIONS = (".py", ".js", ".ts", ".go", ".rb", ".java")


@dataclass
class SecurityScanInput:
    worktree: str


@activity.defn
async def security_scan(inp: SecurityScanInput) -> SecurityReport:
    """Scan source files under the integration worktree against a minimal
    deterministic ruleset. Pure filesystem read — no network, no git — so it
    is reproducible across Temporal retries."""
    findings: list[SecurityFinding] = []
    root = inp.worktree
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fname in filenames:
            if not fname.endswith(_SECURITY_SCAN_EXTENSIONS):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                text = pathlib.Path(fpath).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = os.path.relpath(fpath, root)
            for pattern, severity, rule, detail in _SECURITY_RULES:
                if pattern.search(text):
                    findings.append(
                        SecurityFinding(severity=severity, rule=rule, detail=detail, path=rel)
                    )
    critical = sum(1 for f in findings if f.severity == "critical")
    return SecurityReport(critical=critical, findings=findings)
```

Add the imports `security_scan` needs at the top of `src/sdlc/activities.py` if absent: `import re`, `import pathlib` (verify — `os`, `dataclass`, `activity` are already imported). Add `SecurityReport, SecurityFinding` to the existing `from .models import (...)` block.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_security_floor.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py src/sdlc/activities.py tests/test_security_floor.py
git commit -m "feat(security): add SecurityReport + deterministic security_scan activity (FR-106)"
```

---

### Task 3: Wire `security_no_critical` as an absolute merge-gate check

**Files:**
- Modify: `src/sdlc/worker.py` (activity import ~line 30; activities list ~line 60)
- Modify: `src/sdlc/workflows/feature.py` (imports ~line 23-53; merge-gate evidence ~line 800-819)
- Test: `tests/test_security_floor.py` (extend)

**Interfaces:**
- Consumes: `security_scan`, `SecurityScanInput` (Task 2); `SecurityReport` (Task 2); `build_check`, `CheckClass` (already imported in `feature.py`); `self._integration_wt`.
- Produces: a `security_no_critical` **absolute** check appended to the merge gate's `checks` list, passing iff `report.critical == 0`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_security_floor.py`:

```python
from sdlc.gate import CheckClass, build_check, evaluate_quality_gate


def test_security_check_blocks_when_critical_present():
    checks = [
        build_check("build_integration_green", True, CheckClass.ABSOLUTE),
        build_check(
            "security_no_critical", False, CheckClass.ABSOLUTE, detail="1 critical finding"
        ),
    ]
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_security_check_absolute_even_if_requested_advisory():
    # ABSOLUTE_FLOOR promotion: an override cannot wave it through.
    from sdlc.gate import GateOverride

    checks = [build_check("security_no_critical", False, CheckClass.ADVISORY)]
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="security_no_critical", approved_by="human", reason="yolo")],
    )
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_feature_workflow_builds_security_check():
    import pathlib

    src = pathlib.Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8")
    assert (
        'build_check(\n                "security_no_critical"' in src
        or '"security_no_critical"' in src
    ), "merge gate must build the security_no_critical check"
    assert "security_scan" in src, "merge gate must run the security_scan activity"
```

- [ ] **Step 2: Run tests to verify the wiring ones fail**

Run: `python -m pytest tests/test_security_floor.py -v`
Expected: the two `evaluate_quality_gate` tests PASS (pure gate logic already supports it); `test_feature_workflow_builds_security_check` FAILs — `security_scan` not yet in `feature.py`.

- [ ] **Step 3: Register the activity on the worker**

In `src/sdlc/worker.py`, add `security_scan` to the activity import from `.activities`:

```python
from .activities import (
    create_worktree,
    deploy,
    evaluate_gate,
    get_task_diff,
    merge_into_integration,
    open_pull_request,
    run_coding_task,
    run_lint,
    run_test_suite,
    security_scan,
    setup_integration_branch,
)
```

And add `security_scan` to the `activities=[...]` list passed to `Worker` (next to `run_lint, run_test_suite`):

```python
(
    run_coding_task,
    run_lint,
    run_test_suite,
    security_scan,
)
(
    open_pull_request,
    deploy,
)
```

- [ ] **Step 4: Run the scanner and append the check in the merge gate**

In `src/sdlc/workflows/feature.py`, add `security_scan` and `SecurityScanInput` to the `from ..activities import (...)` block (kept inside the existing import section used by the workflow).

In `run()`, in the merge-evidence assembly (section 5a, right after the `lint_clean, lint_detail = await workflow.execute_activity(run_lint, ...)` call, ~line 804), add:

```python
security: SecurityReport = await workflow.execute_activity(
    security_scan, SecurityScanInput(worktree=integration_worktree), **ACT
)
```

Then append a third entry to the `checks = [...]` list (after the `lint_clean` check, before `review_severity`):

```python
(
    build_check(
        "security_no_critical",
        security.critical == 0,
        CheckClass.ABSOLUTE,
        detail=f"{security.critical} critical finding(s)",
    ),
)
```

Add `SecurityReport` to the `from ..models import (...)` block in `feature.py` if not already present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_security_floor.py -v`
Expected: PASS (all).

- [ ] **Step 6: Run the workflow-purity guard**

Run: `python -m pytest tests/test_factory_purity.py -v`
Expected: PASS — `security_scan` is an activity; workflow code imports only its reference and `SecurityScanInput`, importing no `subprocess`/HTTP directly.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/worker.py src/sdlc/workflows/feature.py tests/test_security_floor.py
git commit -m "feat(merge): wire security_no_critical absolute check into the quality gate (SC-5)"
```

---

### Task 4: Canned proposer artifacts + fake git/subprocess activities

**Files:**
- Create: `tests/fakes/canned.py`
- Create: `tests/fakes/fake_activities.py`

**Interfaces:**
- Consumes: pipeline models from `sdlc.models`; activity input/output dataclasses from `sdlc.activities`.
- Produces (`canned.py`): `greenfield_idea() -> IdeaBrief`; `e2e_config() -> PipelineConfig`; `AGENT_SPECS: list[tuple[str, type, BaseModel]]`; `CLARIFIED`, `ARCH`, `PLAN`, `QA_OK`, `REVIEW_OK`, `MERGE_OK` module constants; `QUESTION_IDS: list[str]`.
- Produces (`fake_activities.py`): `GIT_FAKES: list` — same-named `@activity.defn` fakes for `setup_integration_branch`, `create_worktree`, `run_coding_task`, `get_task_diff`, `run_test_suite`, `run_lint`, `merge_into_integration`, `open_pull_request`, `deploy`, `security_scan`.

- [ ] **Step 1: Write the canned artifacts**

Create `tests/fakes/canned.py`:

```python
"""Deterministic inputs + proposer outputs for the greenfield e2e run.

Every value is self-consistent with the next stage's needs: one open
question (exercises answer_question), a single dev task with a frozen
contract, and clean QA/review so the run reaches deploy.
"""

from __future__ import annotations

from sdlc.models import (
    ArchitectureDecision,
    ArchitectureSpec,
    ClarifiedRequirements,
    DevTask,
    GateConfig,
    GatePolicy,
    IdeaBrief,
    ImplementationPlan,
    MemoryConfig,
    MergeVerdict,
    OpenQuestion,
    PipelineConfig,
    ProjectMode,
    QAReport,
    ReviewReport,
    ValidationContract,
)

QUESTION_IDS = ["q1"]

CLARIFIED = ClarifiedRequirements(
    summary="Add a greeting endpoint.",
    functional_requirements=["GET /hello returns 200"],
    non_functional_requirements=["p95 < 100ms"],
    out_of_scope=["auth"],
    open_questions=[
        OpenQuestion(
            id="q1",
            question="Anonymous access ok?",
            why_it_matters="scopes auth work",
            suggested_answer="yes",
        )
    ],
)

ARCH = ArchitectureSpec(
    overview="Single FastAPI service with one route.",
    decisions=[
        ArchitectureDecision(title="Framework", choice="FastAPI", rationale="matches team stack")
        if "title" in ArchitectureDecision.model_fields
        else ArchitectureDecision.model_construct()
    ],
    new_components=["app/main.py"],
    confidence=0.95,
)

PLAN = ImplementationPlan(
    tasks=[
        DevTask(
            id="t1",
            title="Implement /hello",
            description="Add GET /hello route returning 200.",
            acceptance_criteria=["GET /hello returns 200"],
            contract=ValidationContract(
                task_id="t1",
                assertions=["GET /hello returns 200"],
                test_commands=["pytest -q"],
                lint_commands=["ruff check ."],
                stack="Python/FastAPI",
            ),
        )
    ],
    confidence=0.95,
)

QA_OK = QAReport(tests_passed=True, coverage_pct=100.0)
REVIEW_OK = ReviewReport(approve=True, confidence=0.95)
MERGE_OK = MergeVerdict(approve=True, confidence=0.95, rationale="clean")

AGENT_SPECS = [
    ("clarify_agent", ClarifiedRequirements, CLARIFIED),
    ("architect_agent", ArchitectureSpec, ARCH),
    ("planner_agent", ImplementationPlan, PLAN),
    ("qa_analyst_agent", QAReport, QA_OK),
    ("reviewer_agent", ReviewReport, REVIEW_OK),
    ("merge_verdict_agent", MergeVerdict, MERGE_OK),
]


def greenfield_idea() -> IdeaBrief:
    return IdeaBrief(
        title="Hello service",
        description="Add /hello",
        mode=ProjectMode.GREENFIELD,
        repo_url="/fake/repo",
        base_branch="main",
    )


def e2e_config() -> PipelineConfig:
    """Hermetic P1 config: memory + memoization off (no support activities
    scheduled), every gate HARD (driver approves each explicitly)."""
    hard = GateConfig(policy=GatePolicy.HARD)
    return PipelineConfig(
        gates={"clarify": hard, "architecture": hard, "plan": hard, "merge": hard, "deploy": hard},
        memory=MemoryConfig(enabled=False),
        memoization_enabled=False,
        review_enabled=True,
    )
```

> **Note on `ArchitectureDecision`:** its field names were not pinned in the spec. Before running, open `src/sdlc/models.py`, read the real `ArchitectureDecision` fields, and replace the `ARCH.decisions` construction with a plain `ArchitectureDecision(<real fields>)`. Delete the defensive `model_construct()` fallback once the real fields are used — it is a guard against an unknown shape, not final code.

- [ ] **Step 2: Write the fake git/subprocess activities**

Create `tests/fakes/fake_activities.py`:

```python
"""Same-named fakes for every git/subprocess activity the FeatureWorkflow
calls. Registered on the e2e worker INSTEAD of the production activities, so
the run touches no real git, subprocess, or network. Names must match the
production activity names for Temporal dispatch."""

from __future__ import annotations

from temporalio import activity

from sdlc.activities import (
    CodingTaskInput,
    DeployInput,
    DiffInput,
    IntegrationHandle,
    IntegrationInput,
    LintInput,
    MergeInput,
    MergeResult,
    PROpenInput,
    QAInput,
    SecurityScanInput,
    WorktreeHandle,
    WorktreeInput,
)
from sdlc.models import HarnessRunResult, QAReport, SecurityReport


@activity.defn(name="setup_integration_branch")
async def fake_setup_integration_branch(inp: IntegrationInput) -> IntegrationHandle:
    return IntegrationHandle(head_sha="deadbeef", worktree_path="/fake/integ")


@activity.defn(name="create_worktree")
async def fake_create_worktree(inp: WorktreeInput) -> WorktreeHandle:
    return WorktreeHandle(
        path=f"/fake/wt/{inp.task_id}",
        branch=f"sdlc/{inp.run_id}/{inp.task_id}",
        branch_point="deadbeef",
    )


@activity.defn(name="run_coding_task")
async def fake_run_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    return HarnessRunResult(
        harness=inp.harness,
        session_id="s1",
        exit_code=0,
        summary="implemented",
        commit_sha="cafe1234",
        input_tokens=1000,
        output_tokens=200,
        context_window=200000,
    )


@activity.defn(name="get_task_diff")
async def fake_get_task_diff(inp: DiffInput) -> dict:
    return {
        "stat": " app/main.py | 3 +++",
        "patch": "diff --git a/app/main.py b/app/main.py\n+ok\n",
        "files": ["app/main.py"],
    }


@activity.defn(name="run_test_suite")
async def fake_run_test_suite(inp: QAInput) -> QAReport:
    return QAReport(tests_passed=True, coverage_pct=100.0)


@activity.defn(name="run_lint")
async def fake_run_lint(inp: LintInput) -> tuple[bool, str]:
    return True, "clean"


@activity.defn(name="merge_into_integration")
async def fake_merge_into_integration(inp: MergeInput) -> MergeResult:
    return MergeResult(merged=True, conflict=False, integration_head="feed0001")


@activity.defn(name="open_pull_request")
async def fake_open_pull_request(inp: PROpenInput) -> str:
    return "https://example.test/pr/1"


@activity.defn(name="deploy")
async def fake_deploy(inp: DeployInput) -> str:
    return "deploy ok"


@activity.defn(name="security_scan")
async def fake_security_scan(inp: SecurityScanInput) -> SecurityReport:
    return SecurityReport(critical=0, findings=[])


GIT_FAKES = [
    fake_setup_integration_branch,
    fake_create_worktree,
    fake_run_coding_task,
    fake_get_task_diff,
    fake_run_test_suite,
    fake_run_lint,
    fake_merge_into_integration,
    fake_open_pull_request,
    fake_deploy,
    fake_security_scan,
]
```

> **Note on input dataclass names:** the fakes import `CodingTaskInput`, `DiffInput`, `QAInput`, `LintInput`, `PROpenInput`, `DeployInput`, `IntegrationHandle`, `WorktreeHandle`, `MergeResult` from `sdlc.activities`. These are the real dataclasses defined there (verified). If any import fails, grep `src/sdlc/activities.py` for the exact class name and fix the import — do not stub a parallel type.

- [ ] **Step 3: Verify the fakes import cleanly**

Run: `python -c "import tests.fakes.fake_activities as f; import tests.fakes.canned as c; print(len(f.GIT_FAKES), len(c.AGENT_SPECS))"`
Expected: `10 6`

- [ ] **Step 4: Commit**

```bash
git add tests/fakes/canned.py tests/fakes/fake_activities.py
git commit -m "test(e2e): canned proposer artifacts + fake git/subprocess activities"
```

---

### Task 5: The greenfield end-to-end proof

The P1 "one project shipped end-to-end" artifact: drives the real `FeatureWorkflow` from a greenfield `IdeaBrief` to `deployed:...`, answering the clarify question and the architecture/plan/deploy gates, asserting the merge gate ran the absolute `security_no_critical` check green.

**Files:**
- Create: `tests/test_e2e_greenfield.py`

**Interfaces:**
- Consumes: `fake_agent_activities` (Task 1); `GIT_FAKES` (Task 4); `greenfield_idea`, `e2e_config`, `AGENT_SPECS`, `QUESTION_IDS` (Task 4); `FeatureWorkflow` and its signals `answer_question` / `submit_gate_decision`, query `pending_gate` (existing).
- Produces: the passing end-to-end test.

- [ ] **Step 1: Write the driver + end-to-end test**

Create `tests/test_e2e_greenfield.py`:

```python
"""P1 end-to-end proof (orchestration-level, offline, deterministic).

Runs the REAL FeatureWorkflow on a time-skipping worker with faked model +
activity seams, drives it through every gate via signals, and asserts it
reaches `deployed:`."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate  # pure — reused, not faked
from sdlc.gate import CheckClass
from sdlc.models import GateDecision, GateOutcome
from tests.fakes.canned import (
    AGENT_SPECS,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES
from tests.fakes.fake_agents import fake_agent_activities

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow

TASK_QUEUE = "e2e"


async def _wait_for_status(handle, target: str, timeout_s: float = 10.0):
    """Poll pending_gate() until it reports `target` (e.g. 'awaiting:plan')."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        gate = await handle.query(FeatureWorkflow.pending_gate)
        if gate == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for status {target!r}")


async def _drive(handle):
    # 1. clarify — answer the one open question
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    # 2. architecture, plan, deploy gates — approve each (merge auto-passes
    #    clean, so it never enters awaiting:merge).
    for gate in ("architecture", "plan", "deploy"):
        await _wait_for_status(handle, f"awaiting:{gate}")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=gate, round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
        )


@pytest.mark.asyncio
async def test_greenfield_run_ships_end_to_end():
    activities = [evaluate_gate, *GIT_FAKES, *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[FeatureWorkflow],
            activities=activities,
            plugins=[PydanticAIPlugin()],
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[greenfield_idea(), e2e_config()],
                id=f"e2e-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            driver = asyncio.create_task(_drive(handle))
            result = await handle.result()
            await driver

    assert result.startswith("deployed:"), result
```

- [ ] **Step 2: Run the end-to-end test**

Run: `python -m pytest tests/test_e2e_greenfield.py -v`
Expected: PASS — `result == "deployed:https://example.test/pr/1"`.

**If it hangs or fails:**
- Hangs at a status that never arrives → the canned artifact for that stage is malformed (e.g. the plan produced zero tasks, or QA/review not clean). Print `await handle.query(FeatureWorkflow.status)` in the driver loop to see where it parked.
- `awaiting:merge` appears unexpectedly → an advisory check failed; confirm `fake_run_lint` returns `True` and `fake_security_scan` returns `critical=0`, and that every task's `review`/`qa` is clean.
- Activity-not-registered error → an activity name in the workflow has no fake; add a same-named fake to `GIT_FAKES` (re-check the activity list in `src/sdlc/worker.py`).

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — no regressions across the existing suite plus the new spike, security-floor, and e2e tests.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_greenfield.py
git commit -m "test(e2e): greenfield run ships end-to-end through FeatureWorkflow (P1)"
```

---

## Self-Review

**Spec coverage** (`docs/superpowers/specs/2026-07-15-p1-consolidation-e2e-and-security-floor-design.md`):
- §2 G1 (CI-runnable end-to-end run → deploy) → Tasks 1 (mechanism), 4 (fixtures), 5 (driver + assertion). ✅
- §2 G2 (`security_no_critical` real absolute check; critical blocks deploy) → Tasks 2 (model + scanner), 3 (wiring + gate tests). ✅
- §4 model seam (Pydantic AI `TestModel` in same-named `TemporalAgent`) → Task 1 helper, Task 4 `AGENT_SPECS`. ✅
- §4 activity seam (same-named `@activity.defn` fakes) → Task 4 `GIT_FAKES`. ✅
- §5.1 canned artifacts (one open question, 1 task with contract, clean QA/review) → Task 4 `canned.py`. ✅
- §5.3 assertions (reaches deploy; merge gate has passing absolute `security_no_critical`) → Task 5 asserts `deployed:`; the green `security_no_critical` is exercised because Task 3 makes it a mandatory absolute check the run must pass. ✅
- §6 spike-first risk mitigation → Task 1 is the spike, with the documented fallback. ✅
- §3 minimal-but-real scanner + seam → Task 2 `_SECURITY_RULES` + `SecurityReport` return-type seam. ✅
- Out-of-scope items (§7) are not touched: no new stages, no rename, no real SAST, no real git. ✅

**Placeholder scan:** Two `> Note` callouts (Task 4) flag fields the spec left unpinned (`ArchitectureDecision` shape; activity input class names) and give an exact resolution step rather than a vague "handle it" — the engineer reads the real model and substitutes. All code steps show complete code. No TBD/TODO.

**Type consistency:** `SecurityReport{critical, findings}` / `SecurityFinding{severity, rule, detail, path}` are defined in Task 2 and consumed identically in Tasks 3 (`security.critical == 0`) and 4 (`SecurityReport(critical=0, findings=[])`). `SecurityScanInput{worktree}` matches its uses in Tasks 2, 3, 4. `fake_agent_activities(specs)` (Task 1) is called with `AGENT_SPECS` (Task 4) and consumed in Task 5. `GIT_FAKES` (Task 4) is consumed in Task 5. Agent names in `AGENT_SPECS` match the Global Constraints list and the production `name=` strings. `GateDecision`/`GateOutcome.APPROVE`, `pending_gate`, `answer_question`, `submit_gate_decision` match the real `FeatureWorkflow` signatures (verified against `feature.py:297-315`).
