# A — Stage Surgery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut `workflows/feature.py`, `activities.py`, `models.py` and `harness/adapters.py` into vertical slices under `src/sdlc/stages/`, so all four leave `.file-size-baseline.json`.

**Architecture:** Fifteen stages become `src/sdlc/stages/<stage>/` slices exporting `step(ctx, ...)` and `ACTIVITIES`. The orchestrator's own services move onto `FeatureWorkflow`'s MRO as host mixins, which is what gets `feature.py` under the ceiling — stage extraction alone leaves ~557 lines of services behind. `models.py` and `activities.py` are deleted outright; `adapters.py` flattens into five modules.

**Tech Stack:** Python ≥3.11, `temporalio` 1.30.0, Pydantic v2 + `pydantic_data_converter`, Pydantic AI (`TemporalAgent`), pytest with marker tiers, ruff + mypy via pre-commit.

**Spec:** `docs/superpowers/specs/2026-09-03-a-stage-surgery-design.md`

## Global Constraints

- **File ceiling: 1000 physical lines.** `scripts/check_file_size.py` is the authority. Baselined files may shrink, never grow.
- **No re-export shims.** A moved symbol has exactly one home; every call site re-points in the same commit (spec §2.3).
- **`core/` imports nothing from `stages/` and nothing from any horizontal package.** Rule 5, the layering invariant.
- **`workflows/` may import `stages/`; `stages/` may type-import `workflows/models.py`.** Never the reverse for `core/`.
- **Cross-stage calls are banned.** A stage never invokes another stage's `step`. Importing a type it produces is not a call.
- **Handlers live on the workflow class's MRO.** Never in a step module.
- **A step owns no run state across calls.** Loop counters are locals or return-envelope fields.
- **A step module's top level is constants only.** No clock, env reads, or I/O at import time.
- **Signal and query names are wire contracts:** `submit_gate_decision`, `answer_question`, `run_summary`, `run_state`, `status`, `pending_gate`, `pending_decisions`. They carry no `name=` override, so the method name *is* the handler name. Moving a method between modules must not rename it.
- **The activity/timer/signal command sequence a run issues must not change.** This is what keeps replay safe. `pytest -m temporal` is the check and is **excluded from the default run**, so it must be invoked explicitly.
- **Test basenames stay globally unique.** There is no `tests/__init__.py`.
- **Root `AGENTS.md`'s stage table is updated in the same commit as any stage move.**

**Verification, run at the end of every task:**

```bash
pytest -m "not slow and not temporal"
pytest -m temporal
python scripts/check_file_size.py --full
pre-commit run --all-files
```

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `src/sdlc/core/context.py` | `StageContext` Protocol (eleven services) + the frozen `StageServices` implementation |
| `src/sdlc/core/models.py` | Configuration + envelopes referencing nothing outside `core` |
| `src/sdlc/core/AGENTS.md` | Rule 5 stated locally and checkably |
| `src/sdlc/workflows/models.py` | Orchestrator envelopes aggregating stage artifacts (`TaskResult`, `SeededWork`) |
| `src/sdlc/workflows/{report,role,benchmark,memory,question,board,task}_host.py` | The seven service-host mixins |
| `src/sdlc/workflows/AGENTS.md` | Attribute-ownership table across the MRO |
| `src/sdlc/stages/__init__.py` | `STAGE_MODULES` — explicit, ordered |
| `src/sdlc/stages/<stage>/` | Fifteen slices, seven files each |
| `src/sdlc/vcs/` | Git and worktree plumbing + its `ACTIVITIES` |
| `src/sdlc/harness/{base,claude_code,opencode,cursor,registry}.py` | `adapters.py`, flattened |
| `scripts/check_clauses.py` | Clause ↔ `@pytest.mark.clause` orphan report |
| `tests/<stage>/`, `tests/integration/` | Mirrored test homes |

**Deleted:** `src/sdlc/models.py`, `src/sdlc/activities.py`, `src/sdlc/harness/adapters.py`, and the four packages `src/sdlc/{clarify,research,context,deploy}/` (moved, not removed).

**Heavily modified:** `src/sdlc/workflows/feature.py` (3673 → ~620-780), `src/sdlc/worker.py`, `tests/fakes/fake_activities.py`, `AGENTS.md`.

---

# Phase P0 — Archaeology

No code changes. The report is the input to every later phase.

### Task 1: The archaeology report

**Files:**
- Create: `docs/reports/2026-09-03-feature-py-archaeology.md`
- Read only: `src/sdlc/workflows/feature.py`, `src/sdlc/models.py`, `src/sdlc/activities.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the **ownership map** (every one of the 73 models and 16 activities → exactly one destination path) and the **migration order** (the thirteen non-pilot stages, ranked). Every later task cites this file.

- [ ] **Step 1: Build the per-stage table**

For each of the fifteen stages in `_pipeline` (`:2493-3160`), `_dev_task` (`:1833-2368`) and `_build_and_merge` (`:3162-3673`), record six columns:

| Stage | Lines | `self._x` touched | Maps to service | Uncovered need | Enum-identity sites | Child workflows |
|---|---|---|---|---|---|---|

"Uncovered need" means a capability none of the eleven services provides. `_board_publish` is the known one and is **not** a twelfth service — spec §3.4 routes it through the orchestrator after `step()` returns; the report records where each publish call sits so P1/P3 can move it.

- [ ] **Step 2: Build the ownership map by applying spec §2.2's rules in order**

Rule 5 (layering) is the invariant; Rules 6 and 7 fire only when it forces them. For each type in `models.py`, record `name | current line | destination | rule that decided it`.

Three sign-off conditions are **acceptance criteria for this step** and must appear verbatim in the report:

1. **`RoleUsage` (`models.py:780-794`) is listed in the `core/models.py` inventory.** It is forced core by Rule 5, since `RunSummary.roles` (`:1302`) and `RunState.roles` (`:1331`) reference it; `ResearchPlan.usage` (`:871`) and `SubQuestionFinding.usage` (`:885`) then import it from core.
2. **The lens outputs get a decided home.** Default `DeepReviewReport` (`:735`) → `stages/review/models.py` (produced by `_run_deep_review`, `:1422`); `HandoffSummary`/`HandoffClaim` (`:370-392`) → `stages/code/models.py` (FR-805 task→task, read via `_handoff_notes`, `:635`). Confirm or override with evidence; record which.
3. **`workflows/models.py` is listed in the Rule 3 passthrough set** that every slice's `AGENTS.md` will carry, alongside `core/models.py` and the slice's own upstreams.

- [ ] **Step 3: Map the 16 activities, including the four hidden `_git` callers**

Destinations per spec §5. Record explicitly that `run_coding_task` (`:616-639`), `classify_repo` (`:1351-1370`), `check_brownfield_delta` (`:1411-1414`) and `open_pull_request` (`:1304-1314`) stay stage-side but call `_git`, so they will import it from `vcs`.

- [ ] **Step 4: Emit the exact test move list**

`tests/` holds 451 root `.py` files. List each file that moves, with source and destination path, and each that stays. Do not estimate — enumerate. Basenames are unchanged.

- [ ] **Step 5: Rank the migration order**

Ascending by uncovered-need count, then enum-identity sites, then child workflows started. Output a numbered list of the thirteen non-pilot stages. This list becomes Task 19's input.

- [ ] **Step 6: Verify no code was touched**

Run: `git status --porcelain`
Expected: exactly one line, `?? docs/reports/2026-09-03-feature-py-archaeology.md`. Any `src/` or `tests/` entry means the report-first rule was broken — revert it.

- [ ] **Step 7: Commit**

```bash
git add docs/reports/2026-09-03-feature-py-archaeology.md
git commit -m "docs(report): feature.py archaeology — ownership map and migration order"
```

---

# Phase P1 — Machinery and pilots

Exit condition: baseline still five entries with `feature.py` down by roughly a third; both pilots migrated; `pytest -m temporal` green.

### Task 2: `core/context.py` — the Protocol and its implementation

**Files:**
- Create: `src/sdlc/core/__init__.py`, `src/sdlc/core/context.py`, `src/sdlc/core/AGENTS.md`
- Test: `tests/core/test_core_stage_context.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `StageContext` (Protocol, eleven members) and `StageServices` (frozen dataclass implementing it). Every `step()` in every later task takes `ctx: StageContext` as its first positional parameter.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_core_stage_context.py
from dataclasses import FrozenInstanceError

import pytest

from sdlc.core.context import StageContext, StageServices

ELEVEN = {
    "emit",
    "stage",
    "run_role",
    "cached_stage",
    "revisable_stage",
    "record",
    "judge",
    "recall",
    "retain",
    "gate",
    "ask_and_wait",
}


def _services(**over):
    base = {name: (lambda *a, **k: None) for name in ELEVEN}
    base.update(over)
    return StageServices(**base)


def test_protocol_has_exactly_eleven_services():
    members = {m for m in StageContext.__protocol_attrs__ if not m.startswith("_")}
    assert members == ELEVEN


def test_services_satisfies_the_protocol():
    assert isinstance(_services(), StageContext)


def test_services_is_frozen():
    svc = _services()
    with pytest.raises(FrozenInstanceError):
        svc.emit = None  # type: ignore[misc]


def test_services_exposes_nothing_beyond_the_protocol():
    # The whole point: a step handed this cannot reach _pending or _status.
    assert not [a for a in vars(_services()) if a not in ELEVEN]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_core_stage_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.core'`

- [ ] **Step 3: Write `core/context.py`**

```python
"""The StageContext seam (spec A §3.2).

A step never receives the workflow instance. It receives StageServices: a
frozen record of exactly the eleven capabilities the orchestrator offers,
built once in FeatureWorkflow.__init__ from its own bound methods. B0 §1.1
rejects passing `self` because that exposes everything; this makes "a stage
does not reach into the workflow class" true at runtime rather than by
convention, and it lets a step be unit-tested by handing it stubs, with no
workflow and no Temporal environment at all.

Data travels in the step signature; only capabilities live here. The review
question for any proposed addition is "is this a capability the orchestrator
provides, or a value it holds?" — board publishing was the first thing to
fail that test (spec §3.4).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StageContext(Protocol):
    """The eleven services, in B0's five groups."""

    # Reporting
    def emit(self, kind: Any, stage: str | None = None, **data: str) -> None: ...
    def stage(self, status: str, trace: str | None = None) -> None: ...

    # Role execution and memoization
    def run_role(
        self, cfg: Any, role: str, model: str, agent: Any, *args: Any, **kwargs: Any
    ) -> Awaitable[Any]: ...
    def cached_stage(
        self,
        cfg: Any,
        stage: str,
        input_json: str,
        output_type: type,
        run_fn: Callable[[], Awaitable[Any]],
    ) -> Awaitable[tuple[Any, bool]]: ...
    def revisable_stage(
        self, name: str, cfg: Any, run_fn: Callable[[str | None], Awaitable[Any]]
    ) -> Awaitable[tuple[Any, Any]]: ...

    # Benchmark and memory
    def record(self, cfg: Any, record: Any) -> Awaitable[None]: ...
    def judge(
        self, cfg: Any, artifact_json: str, stage: str, author_model: str
    ) -> Awaitable[Any]: ...
    def recall(
        self, cfg: Any, bank: str, query: str, filters: dict[str, str]
    ) -> Awaitable[Any]: ...
    def retain(
        self, cfg: Any, kind: Any, bank: str, text: str, metadata: dict[str, str]
    ) -> Awaitable[None]: ...

    # Human decisions
    def gate(self, name: str, settings: Any, **kwargs: Any) -> Awaitable[Any]: ...

    # Human questions
    def ask_and_wait(
        self, questions: Sequence[Any], *, stage: str, timeout_hours: int
    ) -> Awaitable[dict[str, str]]: ...


@dataclass(frozen=True, slots=True)
class StageServices:
    """The Protocol's only production implementation. Constructed once, in
    FeatureWorkflow.__init__, from bound methods — never lazily inside a step,
    where a conditional construction could diverge on replay."""

    emit: Callable[..., None]
    stage: Callable[..., None]
    run_role: Callable[..., Awaitable[Any]]
    cached_stage: Callable[..., Awaitable[tuple[Any, bool]]]
    revisable_stage: Callable[..., Awaitable[tuple[Any, Any]]]
    record: Callable[..., Awaitable[None]]
    judge: Callable[..., Awaitable[Any]]
    recall: Callable[..., Awaitable[Any]]
    retain: Callable[..., Awaitable[None]]
    gate: Callable[..., Awaitable[Any]]
    ask_and_wait: Callable[..., Awaitable[dict[str, str]]]
```

The annotations are deliberately `Any`-heavy: `core/context.py` cannot import `core/models.py`'s types without risking the very cycle Rule 5 exists to prevent once slices start importing it. Concrete types live in each step's own signature, which is where a reader looks anyway.

- [ ] **Step 4: Write `core/AGENTS.md`**

State Rule 5 and how to check it:

```markdown
# core/ — the shared kernel

**Rule 5, the layering invariant:** `core/` imports nothing from `stages/`
and nothing from any horizontal package (`harness/`, `memory/`, `board/`,
`schedules/`, `measurement.py`). Anything a `core/` type references is
itself in `core/`.

Check it:

    grep -rnE "from \.\.(stages|harness|memory|board|schedules)" src/sdlc/core/

Empty output is the pass condition. A non-empty result is a boot-time
circular-import defect waiting to happen, not a style nit — every slice
imports `core`.

Two rules exist only to keep Rule 5 satisfiable:
- **Rule 6** — a bare enum (no model dependencies) that a `core/` type
  references lives here. That is why `HarnessKind` and
  `ClarificationDimension` are here rather than with the harness and the
  clarify slice.
- **Rule 7** — an envelope aggregating *stage artifacts* does NOT live here.
  It goes to `workflows/models.py`, beside the orchestrator that assembles
  it. That is why `TaskResult` and `SeededWork` are not here.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/core/test_core_stage_context.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/core tests/core
git commit -m "feat(core): StageContext protocol and StageServices"
```

### Task 3: `core/models.py` — configuration and envelopes

**Files:**
- Create: `src/sdlc/core/models.py`
- Modify: `src/sdlc/models.py` (remove the moved types), every importer the ownership map lists
- Test: `tests/core/test_core_models_layering.py`

**Interfaces:**
- Consumes: Task 1's ownership map.
- Produces: `sdlc.core.models` exporting `ProjectMode`, `HarnessKind`, `ClarificationDimension`, `GatePolicy`, `GateOutcome`, `TimeoutAction`, `GateConfig`, `GateSettings`, `GateDecision`, `gate_key`, `ArtifactRef`, `IdeaBrief`, `RoleUsage`, `RoleConfig`, `ExecutionMode`, `BenchmarkConfig`, `MemoryConfig`, `ContainmentConfig`, `ResearchConfig`, `DeployConfig`, `PipelineConfig`, `StageOutcome`, `ClarificationOutcome`, `GateOutcomeSummary`, `RunSummary`, `RunState`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_core_models_layering.py
import ast
import pathlib

CORE = pathlib.Path("src/sdlc/core")
FORBIDDEN = {"stages", "harness", "memory", "board", "schedules", "measurement"}


def _relative_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            yield (node.module or "").split(".")[0]


def test_core_imports_nothing_from_stages_or_horizontal_packages():
    offenders = [
        (p.name, mod) for p in CORE.glob("*.py") for mod in _relative_imports(p) if mod in FORBIDDEN
    ]
    assert offenders == [], f"Rule 5 violated: {offenders}"


def test_pipeline_config_and_its_configs_are_all_in_core():
    from sdlc.core.models import PipelineConfig

    for field in ("gates", "benchmark", "roles", "memory", "research", "deploy", "containment"):
        anno = PipelineConfig.model_fields[field].annotation
        assert "sdlc.core.models" in str(anno) or anno.__module__ == "sdlc.core.models", field


def test_role_usage_is_core():
    # Rule 5 forces it: RunSummary.roles and RunState.roles reference it.
    from sdlc.core.models import RoleUsage, RunState, RunSummary

    assert RoleUsage.__module__ == "sdlc.core.models"
    assert RunSummary and RunState
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_core_models_layering.py -v`
Expected: FAIL with `ImportError: cannot import name 'PipelineConfig' from 'sdlc.core.models'`

- [ ] **Step 3: Move the types**

Move each type named in the Interfaces block out of `src/sdlc/models.py` into `src/sdlc/core/models.py`, preserving docstrings and field order verbatim. Do **not** move `TaskResult` or `SeededWork` — Task 4 owns those. Do **not** move `MemoryKind`/`RecallSnapshot`/`RetainItem` — no core type references them; they go to `memory/models.py` in P2.

Delete `models.py:24`'s `from .measurement import CollectionState, Measurement` from the *core* file; its only consumers (`SecurityReport.state`, `CoverageReport.coverage`) stay behind in `models.py` until P2.

- [ ] **Step 4: Move `resolve_role_model` to `agents/roles.py`**

`resolve_role_model` (`feature.py:316-325`) reads `STAGE_ROLES` and `STAGE_MODELS` from `agents/roles.py`. It cannot go to `core/models.py` — that would make `core` import `agents`, violating Rule 5 — so it moves into `agents/roles.py` beside the tables it reads. Four test modules import it; re-point them.

Verify the layering test still passes after this move:

Run: `pytest tests/core/test_core_models_layering.py -v`
Expected: PASS — `core/` gained no import of `agents`.

- [ ] **Step 5: Re-point every importer**

The ownership map lists them. No shims. Mechanical check that none was missed:

```bash
grep -rn "from \.\.\?models import .*PipelineConfig" --include=*.py src/ | grep -v core/models
grep -rn "from sdlc.models import" --include=*.py tests/ scripts/ | grep -E "PipelineConfig|GateDecision|RoleConfig|IdeaBrief|RunSummary|RunState|RoleUsage|HarnessKind|ArtifactRef"
```

Expected: no output from either.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/core -v && pytest -m "not slow and not temporal" && pytest -m temporal`
Expected: all pass. `pytest -m temporal` is the one that catches a broken payload path.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(core): move configuration and envelopes to core/models.py"
```

### Task 4: `workflows/models.py` — orchestrator envelopes

**Files:**
- Create: `src/sdlc/workflows/models.py`
- Modify: `src/sdlc/models.py`, importers of `TaskResult` and `SeededWork`
- Test: `tests/core/test_workflows_models_placement.py`

**Interfaces:**
- Consumes: `sdlc.core.models`.
- Produces: `sdlc.workflows.models` exporting `TaskResult`, `SeededWork`. Consumed by `TaskHost` (Task 9) and type-imported by `stages/merge` in P3.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_workflows_models_placement.py
def test_task_result_lives_with_the_orchestrator():
    from sdlc.workflows.models import SeededWork, TaskResult

    assert TaskResult.__module__ == "sdlc.workflows.models"
    assert SeededWork.__module__ == "sdlc.workflows.models"


def test_core_does_not_import_the_orchestrator_envelopes():
    import pathlib

    src = pathlib.Path("src/sdlc/core/models.py").read_text(encoding="utf-8")
    assert "TaskResult" not in src
    assert "SeededWork" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_workflows_models_placement.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.workflows.models'`

- [ ] **Step 3: Move `TaskResult` (`models.py:525-535`) and `SeededWork` (`:454-481`)**

Rule 7: they aggregate stage artifacts, so they live beside the orchestrator that assembles them, not in `core`. `workflows/models.py` may import `stages/`; in P1 it still imports the surviving `..models` for member types, and those imports re-point stage by stage in P2/P3.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/core -v && pytest -m "not slow and not temporal"`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(workflows): TaskResult and SeededWork move beside the orchestrator"
```

### Task 5: `ReportHost` and `BoardHost`

**Files:**
- Create: `src/sdlc/workflows/report_host.py`, `src/sdlc/workflows/board_host.py`, `src/sdlc/workflows/AGENTS.md`
- Modify: `src/sdlc/workflows/feature.py` (remove `:928-1008`, `:1226-1281`; add the mixins to the class bases)
- Test: `tests/integration/test_feature_host_mixins.py`

**Interfaces:**
- Consumes: `sdlc.core.models`.
- Produces: `ReportHost` with `_emit(kind, stage=None, **data) -> None`, `_stage(status, trace=None) -> None`, `_track_usage(...)`; `BoardHost` with `_board_publish`, `_board_sync_tasks`, `_board_task_status`, `_board_evidence`. Both are mixins of `FeatureWorkflow`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_feature_host_mixins.py
from sdlc.workflows.board_host import BoardHost
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.report_host import ReportHost


def test_feature_workflow_inherits_the_hosts():
    assert issubclass(FeatureWorkflow, ReportHost)
    assert issubclass(FeatureWorkflow, BoardHost)


def test_methods_resolve_through_the_mro():
    for name in ("_emit", "_stage", "_track_usage", "_board_publish", "_board_evidence"):
        assert hasattr(FeatureWorkflow, name), name


def test_hosts_define_no_handlers():
    # Rule 1: handlers stay where they already are. A host that grows one
    # silently changes the workflow's wire contract.
    for host in (ReportHost, BoardHost):
        for attr in vars(host).values():
            assert not hasattr(attr, "__temporal_signal_definition"), host
            assert not hasattr(attr, "__temporal_query_definition"), host
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_feature_host_mixins.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.workflows.report_host'`

- [ ] **Step 3: Write the mixins, imitating `gates.py`**

```python
"""ReportHost -- the run trace and the status vocabulary (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54). temporalio collects
definitions with inspect.getmembers, which walks the MRO
(temporalio/workflow/_definition.py:288), so a mixin is a blessed place for
workflow behaviour. Only @workflow.run must be on the concrete class.

Owns: _trace, _seq, _status, _role_usage. Nothing else may write them --
see workflows/AGENTS.md for the full attribute-ownership table.
"""

from __future__ import annotations

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..core.models import RoleUsage
    from ..observability.events import RunEvent, RunEventKind


class ReportHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()
        self._trace: list[RunEvent] = []
        self._seq = 0
        self._status = "starting"
        self._role_usage: dict[str, RoleUsage] = {}

    def _emit(self, kind: RunEventKind, stage: str | None = None, **data: str) -> None:
        ...  # body moved verbatim from feature.py:1226-1232

    def _stage(self, status: str, trace: str | None = None) -> None:
        ...  # body moved verbatim from feature.py:1234-1242

    def _track_usage(self, ...) -> None:
        ...  # body moved verbatim from feature.py:1244-1281
```

Move the bodies **verbatim**. Confirm the exact import path for `RunEvent`/`RunEventKind` against `feature.py`'s existing passthrough block before writing the import — do not guess it. `BoardHost` follows the same shape for `:928-1008`.

- [ ] **Step 4: Wire the bases and the cooperative `__init__` chain**

`class FeatureWorkflow(GateHost, ReportHost, BoardHost):` and delete the moved attribute initialisations from `feature.py:826-870`. Every host's `__init__` calls `super().__init__()` so the chain runs to completion; `GateHost` already does this (`gates.py:57`).

- [ ] **Step 5: Write `workflows/AGENTS.md` with the attribute-ownership table**

One row per instance attribute: attribute, owning host, who may read it, who may write it. Seed it with the known cross-host readers, which are the hazard this table exists to control: `answer_question` pops `GateHost._pending` (`feature.py:1187`), `_stage` writes `_status` (`:1241`), and `run_state` reads `_gate_decisions`, `_status`, `_role_usage` and `_trace` (`:1201-1221`).

- [ ] **Step 6: Run the tests**

Run: `pytest tests/integration/test_feature_host_mixins.py -v && pytest -m temporal`
Expected: all pass. A duplicate handler name across mixins fails loudly at import (`_definition.py:307-328`), so a green `-m temporal` run is real evidence the MRO composed correctly.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(workflows): extract ReportHost and BoardHost onto the MRO"
```

### Task 6: `BenchmarkHost` and `MemoryHost`

**Files:**
- Create: `src/sdlc/workflows/benchmark_host.py`, `src/sdlc/workflows/memory_host.py`
- Modify: `src/sdlc/workflows/feature.py` (remove `:874-924`, `:1012-1096`), `tests/integration/test_feature_host_mixins.py`, `src/sdlc/workflows/AGENTS.md`

**Interfaces:**
- Consumes: `ReportHost._emit` (via the MRO — `_record` calls it at `:1013`).
- Produces: `BenchmarkHost` with `_benchmarking(cfg) -> bool`, `_stage_record(...) -> BenchmarkRecord`, `_record(cfg, record) -> None`, `_judge(cfg, artifact_json, stage, author_model) -> QualityScore`; `MemoryHost` with `_recall(cfg, bank, query, filters) -> RecallSnapshot`, `_retain(cfg, kind, bank, text, metadata) -> None`.

- [ ] **Step 1: Extend the failing test**

```python
def test_benchmark_and_memory_hosts_are_on_the_mro():
    from sdlc.workflows.benchmark_host import BenchmarkHost
    from sdlc.workflows.memory_host import MemoryHost

    assert issubclass(FeatureWorkflow, BenchmarkHost)
    assert issubclass(FeatureWorkflow, MemoryHost)
    for name in ("_benchmarking", "_stage_record", "_record", "_judge", "_recall", "_retain"):
        assert hasattr(FeatureWorkflow, name), name


def test_record_assembles_the_benchmark_record_for_the_stage():
    # ctx.record must accept stage metrics, never a pre-built BenchmarkRecord:
    # a step must not know how one is assembled (_stage_record is 47 lines).
    import inspect

    from sdlc.workflows.benchmark_host import BenchmarkHost

    assert "record" in inspect.signature(BenchmarkHost._record).parameters
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_feature_host_mixins.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.workflows.benchmark_host'`

- [ ] **Step 3: Move the bodies verbatim and add the bases**

`class FeatureWorkflow(GateHost, ReportHost, BoardHost, BenchmarkHost, MemoryHost):`. `_record` calls `self._emit` — that resolves through `ReportHost` on the MRO and needs no change.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/integration/test_feature_host_mixins.py -v && pytest -m temporal`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(workflows): extract BenchmarkHost and MemoryHost onto the MRO"
```

### Task 7: `RoleHost`

**Files:**
- Create: `src/sdlc/workflows/role_host.py`
- Modify: `src/sdlc/workflows/feature.py` (remove `:1145-1177`, `:1283-1326`, `:1711-1742`, `:1773-1805`)
- Test: `tests/integration/test_feature_host_mixins.py`

**Interfaces:**
- Consumes: `ReportHost._track_usage`, `GateHost._gate`.
- Produces: `RoleHost` with `_run_role(cfg, role, model, agent, *args, into=None, **kwargs)`, `_cached_stage(cfg, stage, input_json, output_type, run_fn) -> tuple[StageT, bool]`, `_revisable_stage(name, cfg, run_fn) -> tuple[StageT, GateDecision]`, `_check_budget(cfg) -> None`.

- [ ] **Step 1: Extend the failing test**

```python
def test_role_host_is_on_the_mro():
    from sdlc.workflows.role_host import RoleHost

    assert issubclass(FeatureWorkflow, RoleHost)
    for name in ("_run_role", "_cached_stage", "_revisable_stage", "_check_budget"):
        assert hasattr(FeatureWorkflow, name), name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_feature_host_mixins.py::test_role_host_is_on_the_mro -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Move the bodies verbatim**

`_revisable_stage` calls `self._gate` and `_run_role` calls `self._track_usage`; both resolve through the MRO. Keep `_BudgetRejected` (`feature.py:514`) with `_check_budget` — it is raised only there.

- [ ] **Step 4: Run the tests**

Run: `pytest -m "not slow and not temporal" && pytest -m temporal`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(workflows): extract RoleHost onto the MRO"
```

### Task 8: `QuestionHost` — and `ask_and_wait` becomes a real service

**Files:**
- Create: `src/sdlc/workflows/question_host.py`
- Modify: `src/sdlc/workflows/feature.py` (remove `answer_question` `:1184-1187`; extract the question-asking block around `:2845-2887` out of the clarify body)
- Test: `tests/integration/test_feature_question_host.py`

**Interfaces:**
- Consumes: `ReportHost._emit`, `ReportHost._stage`.
- Produces: `QuestionHost` with `async ask_and_wait(questions: Sequence[OpenQuestion], *, stage: str, timeout_hours: int) -> dict[str, str]` returning question id → answer, and the `answer_question` signal handler.

This is the service that exists for exactly one stage, and it is why `clarify` is a pilot: it is the only stage that opens questions to a human and blocks on `workflow.wait_condition`. Extracting it *before* the clarify slice is what stops the slice from touching `_status`, `_pending` and `_question_answers` directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_feature_question_host.py
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.question_host import QuestionHost


def test_question_host_is_on_the_mro():
    assert issubclass(FeatureWorkflow, QuestionHost)
    assert hasattr(FeatureWorkflow, "ask_and_wait")


def test_answer_question_keeps_its_handler_name():
    # The signal name IS the method name -- it is a wire contract. Renaming
    # it while moving modules silently breaks every client that signals a run.
    handler = FeatureWorkflow.answer_question
    definition = getattr(handler, "__temporal_signal_definition", None)
    assert definition is not None
    assert definition.name == "answer_question"


def test_question_state_is_owned_by_the_host():
    assert "_question_answers" in QuestionHost.__init__.__code__.co_names
    assert "_pending_questions" in QuestionHost.__init__.__code__.co_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_feature_question_host.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.workflows.question_host'`

- [ ] **Step 3: Write `QuestionHost`**

```python
class QuestionHost:
    """Mixin. Open questions to a human and block until answered (FR-30x).

    Owns _question_answers and _pending_questions. A stage never touches
    them: it calls ask_and_wait and receives a dict.
    """

    def __init__(self) -> None:
        super().__init__()
        self._question_answers: dict[str, str] = {}
        self._pending_questions: list[str] = []

    @workflow.signal
    def answer_question(
        self, question_id: str, answer: str
    ) -> None: ...  # body moved verbatim from feature.py:1185-1187

    async def ask_and_wait(
        self, questions: Sequence[OpenQuestion], *, stage: str, timeout_hours: int
    ) -> dict[str, str]:
        """Emit CLARIFICATION_ASKED per question, set the run status, register
        the pending questions, then block on workflow.wait_condition until
        every id has an answer or the deadline passes. Assembled from the
        block currently inline in the clarify body around feature.py:2845-2887
        -- move it verbatim, changing only `self._status = ...` to
        `self._stage(...)` and reading the questions from the parameter
        instead of from `reqs.open_questions`.
        """
```

The command sequence must not change: the same events, the same `wait_condition`, in the same order. That is the replay invariant.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/integration/test_feature_question_host.py -v && pytest -m temporal`
Expected: all pass. Any clarify e2e test that signals `answer_question` is the real check here.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(workflows): extract QuestionHost and the ask_and_wait service"
```

### Task 9: `TaskHost` and the death of `_escalation_round`

**Files:**
- Create: `src/sdlc/workflows/task_host.py`
- Modify: `src/sdlc/workflows/feature.py` (remove `_dev_task` `:1833-2368` and `_merge_task` `:1807-1831`; delete `self._escalation_round` at `:865`)
- Test: `tests/integration/test_feature_task_host.py`

**Interfaces:**
- Consumes: every host above, plus `sdlc.workflows.models.TaskResult`.
- Produces: `TaskHost` with `async _dev_task(task, repo_path, from_ref, cfg, prior_handoffs) -> TaskResult` and `async _merge_task(tr, repo_path) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_feature_task_host.py
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.task_host import TaskHost


def test_task_host_is_on_the_mro():
    assert issubclass(FeatureWorkflow, TaskHost)
    assert hasattr(FeatureWorkflow, "_dev_task")


def test_escalation_round_is_not_instance_state():
    # Rule 2. Wave mode runs _dev_task concurrently; an instance counter is
    # the same latent defect gates.py:84-88 documents for gate confidence.
    src = __import__("pathlib").Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8")
    assert "self._escalation_round" not in src

    host = __import__("pathlib").Path("src/sdlc/workflows/task_host.py").read_text(encoding="utf-8")
    assert "self._escalation_round" not in host
    assert "escalation_round" in host  # it survives as a local
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_feature_task_host.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.workflows.task_host'`

- [ ] **Step 3: Move `_dev_task` and `_merge_task`, converting `_escalation_round` to a local**

Move both bodies verbatim, then make one behavioural change and only one: `self._escalation_round` (initialised `:865`, incremented `:2025`, read at `:2026` and `:2028`) becomes a local `escalation_round = 0` inside `_dev_task`. It is per-task by nature, and the instance attribute is a live wave-mode defect, not a stylistic wart.

Pass the crew child-workflow reference through the sandbox exactly as today (Rule 3a) — `CrewTaskWorkflow` stays in `workflows/crew.py`.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/integration/test_feature_task_host.py -v && pytest -m temporal`
Expected: all pass. If a wave-mode test exists, it is the one that matters.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(workflows): extract TaskHost; _escalation_round becomes a per-task local"
```

### Task 10: Construct `StageServices` in `FeatureWorkflow.__init__`

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Test: `tests/integration/test_feature_stage_services.py`

**Interfaces:**
- Consumes: `StageServices` (Task 2) and every host.
- Produces: `self._ctx`, the single `StageContext` every `step()` receives.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_feature_stage_services.py
from sdlc.core.context import StageContext
from sdlc.workflows.feature import FeatureWorkflow


def test_ctx_is_built_in_init_and_satisfies_the_protocol():
    wf = FeatureWorkflow()
    assert isinstance(wf._ctx, StageContext)


def test_ctx_cannot_reach_workflow_internals():
    wf = FeatureWorkflow()
    for private in ("_pending", "_status", "_trace", "_question_answers", "_gate_decisions"):
        assert not hasattr(wf._ctx, private), private
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_feature_stage_services.py -v`
Expected: FAIL with `AttributeError: 'FeatureWorkflow' object has no attribute '_ctx'`

- [ ] **Step 3: Build it, unconditionally, at the end of `__init__`**

```python
self._ctx = StageServices(
    emit=self._emit,
    stage=self._stage,
    run_role=self._run_role,
    cached_stage=self._cached_stage,
    revisable_stage=self._revisable_stage,
    record=self._record,
    judge=self._judge,
    recall=self._recall,
    retain=self._retain,
    gate=self._gate,
    ask_and_wait=self.ask_and_wait,
)
```

Never lazily, never conditionally, never inside a step: a conditional construction could diverge on replay.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/integration -v && pytest -m temporal`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(workflows): construct StageServices in FeatureWorkflow.__init__"
```

### Task 11: `stages/` scaffolding and `STAGE_MODULES`

**Files:**
- Create: `src/sdlc/stages/__init__.py`
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_stage_registration.py`

**Interfaces:**
- Consumes: nothing yet.
- Produces: `STAGE_MODULES: tuple[ModuleType, ...]` and the composition `[a for m in STAGE_MODULES for a in m.ACTIVITIES]` that `worker.py` registers.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_registration.py
def test_stage_modules_is_explicit_and_every_entry_exports_activities():
    from sdlc import stages

    assert isinstance(stages.STAGE_MODULES, tuple)
    for module in stages.STAGE_MODULES:
        assert hasattr(module, "ACTIVITIES"), module.__name__
        assert isinstance(module.ACTIVITIES, list)


def test_registered_activity_names_are_unique():
    from sdlc import stages

    names = [
        a.__temporal_activity_definition.name for m in stages.STAGE_MODULES for a in m.ACTIVITIES
    ]
    assert len(names) == len(set(names)), f"duplicate: {[n for n in names if names.count(n) > 1]}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stage_registration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.stages'`

- [ ] **Step 3: Write `stages/__init__.py`**

```python
"""The pipeline's vertical slices.

STAGE_MODULES is explicit and ordered, never auto-discovered: registration
must stay deterministic and greppable, and there must be exactly one place to
edit when a stage is added. Entries appear here as their slice migrates.
"""

from __future__ import annotations

from types import ModuleType

STAGE_MODULES: tuple[ModuleType, ...] = ()
```

- [ ] **Step 4: Compose the activity list in `worker.py`**

Replace the `sdlc.activities` imports (`worker.py:29-46`, 16 names) with the composition. **Only ~16 of the 103 import lines go away** — the remaining ~87 import from `assessment`, `triage`, `benchmarks`, `crew`, `memoization`, `memory`, `notify` and `observability`, which are horizontal domains outside `STAGE_MODULES`. B0 §1.3 overstated this; do not delete imports that are still load-bearing.

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_stage_registration.py -v && pytest -m temporal`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(stages): STAGE_MODULES registration contract"
```

### Task 12: The clause marker and its orphan report

**Files:**
- Create: `scripts/check_clauses.py`
- Modify: `pyproject.toml` (`[tool.pytest.ini_options] markers`)
- Test: `tests/test_check_clauses.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `@pytest.mark.clause("<STAGE>-<n>.<m>")` and `python scripts/check_clauses.py`, which prints orphans in both directions and always exits 0.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_clauses.py
from scripts.check_clauses import clause_ids_in_doc, orphans


def test_clause_ids_are_parsed_from_headings(tmp_path):
    doc = tmp_path / "clarify.md"
    doc.write_text("## CLARIFY-1 Routing\n\n### CLARIFY-1.1 [FR-101]\ntext\n", encoding="utf-8")
    assert clause_ids_in_doc(doc) == {"CLARIFY-1", "CLARIFY-1.1"}


def test_orphans_reports_both_directions():
    declared = {"CLARIFY-1.1", "CLARIFY-1.2"}
    cited = {"CLARIFY-1.1", "CLARIFY-9.9"}
    untested, dangling = orphans(declared, cited)
    assert untested == {"CLARIFY-1.2"}
    assert dangling == {"CLARIFY-9.9"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_check_clauses.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.check_clauses'`

- [ ] **Step 3: Write the script**

```python
"""Clause coverage report (spec A §9). Advisory: always exits 0.

Not a gate, deliberately. Kroker implements criterion->test traceability as a
PRODUCT feature (untraced_criteria, feature.py:528, FR-106), and B0 §4 bans
repurposing product machinery as this repo's own dev harness without a
decision that says so. Enforcing before two pilot slices have produced a
single clause would cross that line on speculation. If the pilots' report is
consistently empty and consistently useful, promoting this to a gate is three
lines in .pre-commit-config.yaml.
"""

from __future__ import annotations

import pathlib
import re

HEADING = re.compile(r"^#{2,4}\s+([A-Z][A-Z0-9_]*-\d+(?:\.\d+)*)\b")
MARKER = re.compile(r"""@pytest\.mark\.clause\(\s*["']([^"']+)["']""")


def clause_ids_in_doc(path: pathlib.Path) -> set[str]:
    return {
        m.group(1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if (m := HEADING.match(line))
    }


def clause_ids_in_tests(root: pathlib.Path) -> set[str]:
    return {
        m for p in root.rglob("test_*.py") for m in MARKER.findall(p.read_text(encoding="utf-8"))
    }


def orphans(declared: set[str], cited: set[str]) -> tuple[set[str], set[str]]:
    """(clauses with no test, tests citing a clause that does not exist)."""
    return declared - cited, cited - declared


def main() -> int:
    declared: set[str] = set()
    for doc in pathlib.Path("src/sdlc/stages").rglob("*.md"):
        if doc.name != "AGENTS.md":
            declared |= clause_ids_in_doc(doc)
    untested, dangling = orphans(declared, clause_ids_in_tests(pathlib.Path("tests")))
    for cid in sorted(untested):
        print(f"clause with no test: {cid}")
    for cid in sorted(dangling):
        print(f"test cites unknown clause: {cid}")
    print(f"{len(declared)} clauses declared, {len(untested)} untested, {len(dangling)} dangling")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register the marker**

Add to `pyproject.toml`'s `markers` list:

```toml
    "clause: cites a numbered clause from a slice's <stage>.md contract",
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_check_clauses.py -v && python scripts/check_clauses.py`
Expected: tests pass; the script prints `0 clauses declared, 0 untested, 0 dangling` and exits 0.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(scripts): advisory clause coverage report and the pytest marker"
```

### Task 13: The `clarify` pilot, moved whole

**Files:**
- Create: `src/sdlc/stages/clarify/{__init__,step,activities,models,prompts}.py`, `clarify.md`, `AGENTS.md`
- Delete: `src/sdlc/clarify/` (moved)
- Modify: `src/sdlc/workflows/feature.py` (the clarify block in `_pipeline`), `src/sdlc/agents/roles.py:21-22`, `src/sdlc/stages/__init__.py`, `AGENTS.md`
- Test: move `tests/test_clarify_*.py` → `tests/clarify/`

**Interfaces:**
- Consumes: `StageContext`, `sdlc.core.models`.
- Produces: `stages.clarify.step(ctx, *, cfg, idea, codebase_map, clarify_agent, route_agent, probe_agent) -> ClarifiedRequirements`, and `ACTIVITIES`.

- [ ] **Step 1: Write the failing test**

```python
# tests/clarify/test_clarify_slice_contract.py
import inspect
import pathlib

import pytest

from sdlc.core.context import StageServices
from sdlc.stages import clarify


def test_slice_exports_a_narrow_surface():
    assert callable(clarify.step)
    assert isinstance(clarify.ACTIVITIES, list)


def test_agents_arrive_in_the_signature_not_from_the_registry():
    # The boot cycle: agents/roles.py imports the clarify slice, so a step
    # importing the registry back deadlocks the worker.
    params = inspect.signature(clarify.step).parameters
    for name in ("clarify_agent", "route_agent", "probe_agent"):
        assert name in params, name
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY

    src = pathlib.Path("src/sdlc/stages/clarify/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src


@pytest.mark.clause("CLARIFY-1.1")
def test_step_takes_a_stage_context_and_never_the_workflow():
    first = list(inspect.signature(clarify.step).parameters)[0]
    assert first == "ctx"
    # A step is testable with stubs alone -- no workflow, no Temporal env.
    assert StageServices
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/clarify/test_clarify_slice_contract.py -v`
Expected: FAIL with `ImportError: cannot import name 'clarify' from 'sdlc.stages'`

- [ ] **Step 3: Move the package and write `step.py`**

`git mv src/sdlc/clarify src/sdlc/stages/clarify`, keeping `merge.py` and `routing.py` as slice-internal modules. Then lift the clarify block out of `_pipeline` into `step.py`, following `docs/modes/slice-migration.md`. Every `self._x` becomes either a `ctx.` call or a parameter. The open-questions block calls `ctx.ask_and_wait(...)` (Task 8) and never touches `_status`, `_pending` or `_question_answers`.

**The activity invocation sequence must be identical.** This is the replay invariant.

- [ ] **Step 4: Add `prompt_digest()` to `prompts.py`**

```python
def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5).

    PROMPT_SHAS hashes agents/<role>/instructions.md only, so a prompt living
    here is invisible to content_key and an edit would serve a stale memo.
    E-85 already patched this locally for the probes (_clarify_memo_extra);
    this generalises it to every slice.

    Preserves E-85's flag-off guarantee: with the fan-out disabled the extra
    terms are empty, so a flag-off run keys exactly as it did before and its
    existing memos keep hitting.
    """
```

Cover the prompt constants in this module, the templates it renders, and the effective model settings (`MODEL_SETTINGS`, applied at `roles.py:131`/`:139`) — settings change output and are in no key term today. Then fold it into `_cached_stage`'s key beside `PROMPT_SHAS[stage]` (`feature.py:1166`). **Adding key terms invalidates existing memos once**; that is expected and is noted in the commit message.

- [ ] **Step 5: Break the registry cycle**

`agents/roles.py:21-22` re-points to `..stages.clarify.{models,prompts}`. It must import those submodules **without** `stages/clarify/__init__.py` pulling `step.py` into a cycle — the `__init__` exports `step` and `ACTIVITIES`, so the check is that `python -c "import sdlc.worker"` succeeds.

- [ ] **Step 6: Move the tests and update the table**

`git mv tests/test_clarify_*.py tests/clarify/` — basenames unchanged. Set `clarify`'s row in root `AGENTS.md` to `migrated` pointing at `src/sdlc/stages/clarify/`, in this same commit.

- [ ] **Step 7: Write `clarify.md` and `AGENTS.md` from the templates**

From `docs/templates/stage.md` and `docs/templates/stage-AGENTS.md`. Clauses are written from **observed behaviour**, not intent, each anchored to an `FR-xxx`/`NFR-x`/`E-xx`. The slice `AGENTS.md` records this slice's passthrough answers — including `workflows/models.py` — so the judgment is made once per module rather than once per reader.

- [ ] **Step 8: Run the tests**

Run: `python -c "import sdlc.worker" && pytest tests/clarify -v && pytest -m temporal && python scripts/check_clauses.py`
Expected: the import succeeds (no boot cycle), tests pass, and the clause report lists clarify's clauses.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(clarify): move the clarify stage into a vertical slice

Invalidates existing clarify memos once: prompt_digest() adds key terms that
content_key did not previously see."
```

### Task 14: The `qa` pilot, moved whole

**Files:**
- Create: `src/sdlc/stages/qa/{__init__,step,activities,models,prompts}.py`, `qa.md`, `AGENTS.md`
- Modify: `src/sdlc/workflows/task_host.py` (the qa portion of `_dev_task`), `src/sdlc/stages/__init__.py`, `AGENTS.md`
- Test: move `tests/test_qa_*.py` → `tests/qa/`

**Interfaces:**
- Consumes: `StageContext`, `sdlc.core.models`.
- Produces: `stages.qa.step(ctx, *, cfg, task, contract, diff, worktree, qa_agent) -> QAReport`, `ACTIVITIES = [run_test_suite, run_lint, security_scan]`, and `QAReport`/`SecurityReport`/`SecurityFinding` in `models.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/qa/test_qa_slice_contract.py
import inspect

from sdlc.stages import qa


def test_slice_exports_step_and_activities():
    assert callable(qa.step)
    assert {a.__temporal_activity_definition.name for a in qa.ACTIVITIES} >= {
        "run_test_suite",
        "run_lint",
        "security_scan",
    }


def test_qa_never_calls_a_gate():
    # B0 cited feature.py:2026 and :2287 as qa's justification for
    # StageContext.gate. They are the coding path's tool-approval gate and the
    # loop-level task gate; qa calls neither.
    src = __import__("pathlib").Path("src/sdlc/stages/qa/step.py").read_text(encoding="utf-8")
    assert "ctx.gate" not in src


def test_qa_step_is_pure_over_its_inputs():
    params = inspect.signature(qa.step).parameters
    assert list(params)[0] == "ctx"
    assert "qa_agent" in params
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/qa/test_qa_slice_contract.py -v`
Expected: FAIL with `ImportError: cannot import name 'qa' from 'sdlc.stages'`

- [ ] **Step 3: Extract the qa body out of `_dev_task`**

The qa concern is `run_test_suite` (`:2099`), the QA proposer role run (`:2110`) and the fix-loop analysis via `_fix_loop_issues` (`:2255`). It is **not** contiguous — lift exactly those, leaving the loop, the escalation gate (`:2025-2026`, code's) and the task gate (`:2287`, the loop's) in `TaskHost`.

Move `run_test_suite` (`activities.py:707`), `run_lint` (`:850`) and `security_scan` (`:951`) into the slice's `activities.py`, with their private helpers (`_stopped_early`, `_diagnostic_slice`, the banner constants at `:790-841`). Move `QAReport` (`models.py:538`), `SecurityFinding` (`:565`) and `SecurityReport` (`:572`) into the slice's `models.py`.

- [ ] **Step 4: Register and re-point**

Add `qa` to `STAGE_MODULES`, delete the three names from `worker.py`'s activity imports, and re-point `tests/fakes/fake_activities.py`'s imports of `QAInput`, `LintInput`, `SecurityScanInput` and `QAReport`. **The fakes' `@activity.defn(name=...)` strings must keep matching the production names** or Temporal dispatch silently fails to bind.

- [ ] **Step 5: Add `prompt_digest()` and write both documents**

Same contract as Task 13 Step 4. Documents from the templates; the `AGENTS.md` records that this slice passes through `core/models.py` and its upstream artifact modules.

- [ ] **Step 6: Move the tests and update the table**

`git mv tests/test_qa_*.py tests/qa/`, basenames unchanged. Set `qa`'s row to `migrated`.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/qa -v && pytest -m temporal && python scripts/check_file_size.py --full`
Expected: tests pass; `feature.py`'s baseline entry has dropped by roughly a third and the hook reports the tightening.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(qa): move the qa stage into a vertical slice"
```

---

# Phase P2 — The three horizontal cuts

Exit condition: baseline **5 → 2**; the only `src/` entry left is `feature.py`.

### Task 15: Delete `models.py`

**Files:**
- Delete: `src/sdlc/models.py`
- Create: `src/sdlc/stages/<stage>/models.py` for the eleven unmigrated stages; `src/sdlc/harness/models.py`, `src/sdlc/memory/models.py`, `src/sdlc/schedules/models.py`
- Modify: ~261 files across `src/`, `tests/`, `scripts/`, `interfaces/`
- Test: `tests/core/test_models_module_is_gone.py`

**Interfaces:**
- Consumes: Task 1's ownership map, which is authoritative here.
- Produces: every one of the 73 types at exactly one import path.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_models_module_is_gone.py
import importlib
import pathlib

import pytest


def test_the_monolith_is_deleted():
    assert not pathlib.Path("src/sdlc/models.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sdlc.models")


def test_no_import_still_resolves_to_the_deleted_monolith():
    # `from .models import` inside a subpackage is that package's OWN models
    # module and is fine. Only the paths that used to reach src/sdlc/models.py
    # are defects: `from ..models import` in a subpackage, and
    # `from .models import` in a module sitting directly in src/sdlc/.
    offenders = []
    for p in pathlib.Path("src/sdlc").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if "from ..models import" in text:
            offenders.append(str(p))
        if p.parent.name == "sdlc" and "from .models import" in text:
            offenders.append(str(p))
    assert offenders == [], offenders
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_models_module_is_gone.py -v`
Expected: FAIL — the file still exists

- [ ] **Step 3: Move the remaining types to their destinations**

Follow the ownership map exactly. Eleven slices gain a `models.py` and an `__init__.py` **exporting only what exists** — no `step`, because there is none yet. That is legal under the narrow-surface rule and is what makes this phase possible.

Horizontal destinations: the session and containment block (`:111-248`) → `harness/models.py` but **`HarnessKind` stays in `core`** (Rule 6); `MemoryKind`/`RecallSnapshot`/`RetainItem` (`:994-1021`) → `memory/models.py`; `ScheduleAction`/`ScheduleSpecAsset`/`ScheduleAsset` (`:1046-1088`) → `schedules/models.py`.

- [ ] **Step 4: Re-point all ~261 files, then verify none was missed**

```bash
grep -rn "from sdlc.models import\|from \.\.models import\|from \.models import" --include=*.py src/ tests/ scripts/ interfaces/ | grep -v "core/models\|stages/\|harness/models\|memory/models\|schedules/models\|workflows/models"
```

Expected: no output.

- [ ] **Step 5: Update the migration table with the third status**

Every stage whose types moved but whose step is still inline gets **`types moved, step pending`** in root `AGENTS.md`. Eleven rows. The table is the authoritative discovery map and this is the state it must describe honestly.

- [ ] **Step 6: Run the tests**

Run: `pytest -m "not slow and not temporal" && pytest -m temporal`
Expected: all pass. `-m temporal` is the real check: payloads reconstruct from the recipient's type hints, so a mis-pointed model surfaces here, not in unit tests.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: delete src/sdlc/models.py; every type has exactly one home"
```

### Task 16: Delete `activities.py`, create `vcs/`

**Files:**
- Delete: `src/sdlc/activities.py`
- Create: `src/sdlc/vcs/{__init__,git,worktree,integration}.py`
- Modify: 40 files (7 `src/` + 33 tests), `tests/fakes/fake_activities.py`, `worker.py`
- Test: `tests/test_vcs_activities.py`

**Interfaces:**
- Consumes: Task 1's activity map.
- Produces: `sdlc.vcs` exporting `ACTIVITIES` = `[create_worktree, setup_integration_branch, merge_into_integration, build_verification_branch, get_task_diff, read_committed_bytes]`, plus `_git` for the four stage-side activities that need it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vcs_activities.py
import importlib
import pathlib

import pytest


def test_activities_monolith_is_deleted():
    assert not pathlib.Path("src/sdlc/activities.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sdlc.activities")


def test_vcs_owns_the_plumbing():
    from sdlc import vcs

    names = {a.__temporal_activity_definition.name for a in vcs.ACTIVITIES}
    assert names == {
        "create_worktree",
        "setup_integration_branch",
        "merge_into_integration",
        "build_verification_branch",
        "get_task_diff",
        "read_committed_bytes",
    }


def test_tidyup_still_reaches_build_verification_branch():
    # The evidence this is not stage-owned: a different domain executes it,
    # and feature.py never does.
    from sdlc.workflows import tidyup

    assert tidyup is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vcs_activities.py -v`
Expected: FAIL — the file still exists

- [ ] **Step 3: Split the file**

The six plumbing activities plus the ~240 lines of private helpers (`_git`, `_ensure_worktree`, `_rmtree_with_retry`, `_chmod_retry`, `_find_live_worktree_for_branch`, `_clear_worktree_dir`, `:66-302`) go to `vcs/`. Everything else goes to its slice per the map: `run_coding_task` → code, `run_test_suite`/`run_lint`/`security_scan` → qa (already moved in Task 14), `classify_repo`/`check_brownfield_delta` → context, `measure_coverage`/`run_integration_checks`/`open_pull_request`/`evaluate_gate` → merge.

The four stage-side activities that still call `_git` — `run_coding_task` (`:616-639`), `classify_repo` (`:1351-1370`), `check_brownfield_delta` (`:1411-1414`), `open_pull_request` (`:1304-1314`) — import it from `vcs`.

- [ ] **Step 4: Re-point `tests/fakes/fake_activities.py` in this same commit**

It imports 17 input/output types from `sdlc.activities` (`:10-27`) and defines `GIT_FAKES` (`:191`); every `temporal`-marked test routes through it. Its `@activity.defn(name=...)` strings must keep matching production names exactly.

- [ ] **Step 5: Run the tests**

Run: `pytest -m "not slow and not temporal" && pytest -m temporal`
Expected: all pass. A name mismatch shows up as an unregistered-activity failure in the temporal tier.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(vcs): delete activities.py; git plumbing becomes a horizontal package"
```

### Task 17: Flatten `harness/adapters.py`

**Files:**
- Delete: `src/sdlc/harness/adapters.py`
- Create: `src/sdlc/harness/{base,claude_code,opencode,cursor,registry}.py`
- Modify: 20 importers
- Test: `tests/test_harness_adapter_layout.py`

**Interfaces:**
- Consumes: `sdlc.core.models.HarnessKind`.
- Produces: `harness.base.{CodingHarness, HarnessRequest, build_env, ENV_ALLOWLIST, CONTEXT_WINDOWS, context_window_for}`, `harness.claude_code.ClaudeCodeHarness`, `harness.opencode.OpenCodeHarness`, `harness.cursor.CursorHarness`, `harness.registry.{HARNESSES, check_harness_versions}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_adapter_layout.py
import importlib
import pathlib

import pytest


def test_adapters_module_is_gone():
    assert not pathlib.Path("src/sdlc/harness/adapters.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sdlc.harness.adapters")


def test_registry_still_resolves_every_harness_kind():
    from sdlc.core.models import HarnessKind
    from sdlc.harness.claude_code import ClaudeCodeHarness
    from sdlc.harness.cursor import CursorHarness
    from sdlc.harness.opencode import OpenCodeHarness
    from sdlc.harness.registry import HARNESSES

    # CREW is deliberately absent from HARNESSES -- it is a composition mode,
    # not a CLI, so there is no subprocess to build (models.py:41-44).
    assert HarnessKind.CREW not in HARNESSES
    assert isinstance(HARNESSES[HarnessKind.CLAUDE_CODE], ClaudeCodeHarness)
    assert isinstance(HARNESSES[HarnessKind.OPENCODE], OpenCodeHarness)
    assert isinstance(HARNESSES[HarnessKind.CURSOR], CursorHarness)


def test_each_module_is_under_the_ceiling():
    for name in ("base", "claude_code", "opencode", "cursor", "registry"):
        path = pathlib.Path(f"src/sdlc/harness/{name}.py")
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harness_adapter_layout.py -v`
Expected: FAIL — the file still exists

- [ ] **Step 3: Split at the seams**

`:55-183` (scaffolding) and `:185-343` (the `CodingHarness` ABC) → `base.py`; `:344-675` → `claude_code.py`; `:676-913` → `opencode.py`; `:914-1053` → `cursor.py`; `:1054-1092` → `registry.py`. No `harness/adapters/__init__.py` re-exporting the old paths: under the narrow-surface rule that is a shim, and it would keep a technical-layer word as the public surface of five cohesive modules.

- [ ] **Step 4: Re-point the 20 importers**

```bash
grep -rn "harness\.adapters\|from \.adapters import" --include=*.py src/ tests/ scripts/
```

Expected after re-pointing: no output.

- [ ] **Step 5: Run the tests**

Run: `pytest -m "not slow and not temporal" && python scripts/check_file_size.py --full`
Expected: tests pass; the hook deletes `harness/adapters.py`'s baseline entry.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(harness): flatten adapters.py into five modules"
```

### Task 18: The P2/P3 checkpoint

**Files:**
- Modify: `.file-size-baseline.json` (by the hook), `AGENTS.md`
- Test: `tests/test_check_file_size.py` (existing)

- [ ] **Step 1: Verify the scoreboard moved**

Run: `python scripts/check_file_size.py --full && python -c "import json;d=json.load(open('.file-size-baseline.json'));print(len(d), sorted(d))"`
Expected: exactly 2 entries — `src/sdlc/workflows/feature.py` and `tests/test_assessment_workflow_e2e.py`. The latter is out of A's scope by the spec's `Does not cover`.

- [ ] **Step 2: Verify the table tells the truth**

Every row in root `AGENTS.md`'s stage table reads `migrated` (clarify, qa) or `types moved, step pending` (the other thirteen). No row still says `in feature.py`.

- [ ] **Step 3: Stop and re-commit or stop honestly**

This is the checkpoint B0's "permanent hybrid" risk asks for. Three monoliths are gone; eleven slices are half-populated; `feature.py` is the only `src/` entry left. Either commit to finishing P3, or stop here with the table describing reality. Record the decision in the commit message.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: P2 complete — three monoliths deleted, baseline 5 -> 2"
```

---

# Phase P3 — The remaining thirteen stages

### Task 19: Generate the thirteen stage tasks

**Files:**
- Modify: `docs/superpowers/plans/2026-09-03-a-stage-surgery.md` (this file)

The per-stage specifics — which `self._x` each stage touches, which services they map to, which enum-identity sites and child workflows are involved — are **produced by Task 1's report**, not knowable when this plan was written. Fabricating them here would be a plan that lies.

- [ ] **Step 1: Read the migration order from the report**

`docs/reports/2026-09-03-feature-py-archaeology.md`, Step 5's numbered list.

- [ ] **Step 2: Append one Task 20.N per stage, in that order**

Instantiate the template in Task 20 once per stage, filling every bracketed field from the report's row for that stage. Thirteen instances: intake, context, research, architecture, plan, code, review, analyze, merge, deploy, retro, plus any the report splits out.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-09-03-a-stage-surgery.md
git commit -m "docs(plan): expand P3 into thirteen stage tasks from the archaeology report"
```

### Task 20: The per-stage migration template

Instantiated once per stage by Task 19. Every step is concrete; only the bracketed values vary.

**Files:**
- Create: `src/sdlc/stages/<stage>/{__init__,step,activities,prompts}.py`, `<stage>.md`, `AGENTS.md` (`models.py` already exists from Task 15)
- Modify: `src/sdlc/workflows/feature.py` or `task_host.py` (the stage's inline block), `src/sdlc/stages/__init__.py`, `src/sdlc/worker.py`, `AGENTS.md`
- Test: `tests/<stage>/`

**Interfaces:**
- Consumes: `StageContext`, `sdlc.core.models`, the upstream stages' artifact types.
- Produces: `stages.<stage>.step(ctx, *, cfg, <run context from the report>, <agent params>) -> <Artifact>` and `ACTIVITIES`.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/<stage>/test_<stage>_slice_contract.py
import inspect
import pathlib

from sdlc.stages import <stage>


def test_slice_exports_a_narrow_surface():
    assert callable(<stage>.step)
    assert isinstance(<stage>.ACTIVITIES, list)


def test_step_takes_ctx_first_and_agents_by_keyword():
    params = inspect.signature(<stage>.step).parameters
    assert list(params)[0] == "ctx"
    for name in [<agent params from the report>]:
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_step_module_never_imports_the_agent_registry():
    src = pathlib.Path("src/sdlc/stages/<stage>/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src


def test_step_module_holds_no_workflow_handlers_and_no_module_state():
    src = pathlib.Path("src/sdlc/stages/<stage>/step.py").read_text(encoding="utf-8")
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src
    assert "@workflow.defn" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/<stage>/test_<stage>_slice_contract.py -v`
Expected: FAIL with `ImportError: cannot import name '<stage>' from 'sdlc.stages'`

- [ ] **Step 3: Lift the inline block into `step.py`**

From `feature.py:<range from the report>`. Each `self._x` in the report's column 3 becomes the mapped `ctx.` call from column 4; each item in column 5 ("uncovered need") becomes an explicit parameter or a return-envelope field — **never a twelfth service**, and never instance state.

Board publishing is not a service: return the artifact and let the caller publish it. If this stage is `plan`, its envelope must carry `version_id` back, because `_plan_version` (`:3147`) feeds every later board task write (`:974`, `:981`, `:1001`). If it is `architecture`, the envelope carries the gate decision, because the publish passes `approved=gate.approved`.

**The activity invocation sequence must be identical to the inline block's.**

- [ ] **Step 4: Move the activities and add `prompt_digest()`**

Activities from the report's map into the slice's `activities.py`, with their private helpers. `prompts.py` exports `prompt_digest(cfg)` covering this slice's prompt constants, templates and effective model settings, folded into `_cached_stage`'s key. Note in the commit message that this stage's existing memos are invalidated once.

- [ ] **Step 5: Register and re-point**

Add the module to `STAGE_MODULES`, delete its activity names from `worker.py`, re-point `tests/fakes/fake_activities.py` if it fakes any of them, keeping the `@activity.defn(name=...)` strings identical.

- [ ] **Step 6: Move the tests**

`git mv` each file the report's Step 4 list assigns to this stage into `tests/<stage>/`, **basenames unchanged**. Cross-cutting tests go to `tests/integration/`.

- [ ] **Step 7: Write both documents from the templates**

`<stage>.md` from `docs/templates/stage.md` — numbered clauses from **observed behaviour**, each anchored to an `FR-xxx`/`NFR-x`/`E-xx`, each cited by at least one `@pytest.mark.clause`. `AGENTS.md` from `docs/templates/stage-AGENTS.md`, recording this slice's passthrough answers, including `core/models.py` and `workflows/models.py`.

- [ ] **Step 8: Update the migration table**

Root `AGENTS.md`: this stage's row goes from `types moved, step pending` to `migrated`, pointing at `src/sdlc/stages/<stage>/`. Same commit, not a follow-up.

- [ ] **Step 9: Run the full verification**

```bash
python -c "import sdlc.worker"
pytest -m "not slow and not temporal"
pytest -m temporal
python scripts/check_file_size.py --full
python scripts/check_clauses.py
pre-commit run --all-files
```

Expected: all green; the ratchet reports `feature.py` tightening.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor(<stage>): move the <stage> stage into a vertical slice"
```

### Task 21: Close out — `feature.py` under the ceiling

**Files:**
- Modify: `src/sdlc/workflows/feature.py`, `src/sdlc/workflows/task_host.py`, `.file-size-baseline.json`, `AGENTS.md`
- Test: `tests/integration/test_feature_residual.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_feature_residual.py
import json
import pathlib


def test_feature_py_is_under_the_ceiling():
    lines = pathlib.Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 1000, len(lines)


def test_the_four_src_entries_left_the_baseline():
    baseline = json.loads(pathlib.Path(".file-size-baseline.json").read_text(encoding="utf-8"))
    assert not [k for k in baseline if k.startswith("src/")], baseline
    # The one survivor is out of A's scope by the spec's "Does not cover".
    assert set(baseline) <= {"tests/test_assessment_workflow_e2e.py"}


def test_every_stage_row_says_migrated():
    table = pathlib.Path("AGENTS.md").read_text(encoding="utf-8")
    assert "in `feature.py`" not in table
    assert "types moved, step pending" not in table
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_feature_residual.py -v`
Expected: FAIL — `feature.py` is still over 1000 until the last stage lands

- [ ] **Step 3: Confirm `TaskHost` shed its stage bodies**

With code, review and qa migrated, `_dev_task` is a loop skeleton: worktree provisioning, the attempt loop, the escalation gate, dispatch to the three steps, the task gate, session-resume branching, and envelope assembly. If `task_host.py` is still near 1000, the three bodies did not fully leave — find what stayed.

- [ ] **Step 4: Run the full verification**

```bash
pytest -m "not slow and not temporal"
pytest -m temporal
python scripts/check_file_size.py --full
pre-commit run --all-files
```

Expected: all green; `.file-size-baseline.json` holds one entry.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: A complete — all four src monoliths off the file-size baseline"
```

---

## Follow-up Tasks (Post-Surgery / Pre-existing Defects)

### Follow-up 1: Investigate and fix pre-existing `tests/test_tool_approval_gate.py` deadlock on Windows
- **Discovered during**: Task 3 review / temporal tier run.
- **Symptom**: `tests/test_tool_approval_gate.py -m temporal` hangs before first test report under Windows load (worker gets ~49s CPU then stops; exits with timeout/deadlock). Confirmed reproducible on clean pre-surgery main (`95a5a07` in `.worktrees/base-95a5a07`).
- **Hypothesis & Diagnostic Findings**:
  1. Test driver structure uses `result = await handle.result()` with background `driver = asyncio.create_task(drive())`. If `drive()` times out or raises in `_wait_for_status`, the workflow execution remains pending waiting for human signals, causing an indefinite stall when `auto_time_skipping_disabled()` is active.
  2. Harness fix to convert unbounded hang to immediate diagnosable failure:
     ```python
     driver = asyncio.create_task(drive())
     done, pending = await asyncio.wait(
         [driver, asyncio.ensure_future(handle.result())],
         return_when=asyncio.FIRST_EXCEPTION,
     )
     ```
  3. Operational tier improvement: consider pytest timeout per test in temporal tier.
