# Schedules as Files + Nightly Reflect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `schedules/*.yaml` assets reconciled into Temporal Schedules by an explicit CLI apply, plus `schedules/nightly-reflect.yaml` that finally calls the registered-but-never-invoked `reflect()` activity over project banks.

**Architecture:** YAML assets in `schedules/` are the source of truth. `load_schedules()` parses and validates them fail-closed (mirroring `agents/loader.py`). A pure `plan_changes(desired, existing)` computes a create/update/noop/drift diff; a thin I/O layer applies it via the Temporal client. Because Temporal Schedules can only start *workflows*, a `ReflectWorkflow` wrapper loops the bank list and executes the existing `reflect` activity once per bank.

**Tech Stack:** Python 3.11+, `temporalio>=1.9` (Schedule API), `pydantic>=2.7`, `pyyaml>=6.0`, `pytest>=8` + `pytest-asyncio` (strict mode — every async test needs an explicit `@pytest.mark.asyncio`).

**Spec:** `docs/superpowers/specs/2026-07-16-schedules-as-files-and-nightly-reflect-design.md`

## Global Constraints

- **Scope is project banks only.** Do NOT add an org-bank schedule. `org_bank` has no writers (`src/sdlc/models.py:376`; every `_retain` call site in `feature.py` passes `cfg.memory.project_bank`), so `reflect(org)` would be a permanent no-op.
- **FR-404 stays `[ ]` ⚠️ partial** in `ROADMAP.md` after this ships. Do NOT mark it `[x]`.
- **Deletion is opt-in.** A server schedule with no matching yaml is reported as `drift`, never deleted, unless `--prune` is passed.
- **Only manage our own schedules.** Reconcile must ignore any Temporal schedule whose action workflow is not in `KNOWN_SCHEDULE_WORKFLOWS`, or unrelated schedules in the namespace will report as drift.
- **The `reflect` activity's raise-on-failure behaviour is deliberate and unchanged.** Unlike `recall_snapshot` (which degrades to an empty snapshot by design), `reflect` raises. A failed nightly reflect must be visible as a failed workflow, never a silent no-op.
- **Workflow imports** go inside `with workflow.unsafe.imports_passed_through():`, per `src/sdlc/workflows/feature.py:15`.
- **Never rename** activities or workflow classes after deploy — the name is the Temporal contract.
- Async tests require `@pytest.mark.asyncio`. Run tests with `pytest` from the repo root.

---

### Task 1: Schedule asset models + loader

**Files:**
- Modify: `src/sdlc/models.py` (append after `MemoryConfig`, ~line 378)
- Create: `src/sdlc/schedules/__init__.py`
- Create: `src/sdlc/schedules/loader.py`
- Test: `tests/test_schedule_loader.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `sdlc.models.ScheduleAction(workflow: str, banks: list[str], backend: Literal["fake","hindsight"] = "fake", base_url: str = "http://localhost:8088")`
  - `sdlc.models.ScheduleSpecAsset(cron: str, timezone: str = "UTC")`
  - `sdlc.models.ScheduleAsset(id: str, spec: ScheduleSpecAsset, action: ScheduleAction)`
  - `sdlc.models.KNOWN_SCHEDULE_WORKFLOWS: set[str]`
  - `sdlc.schedules.loader.ScheduleError(ValueError)`
  - `sdlc.schedules.loader.load_schedules(path: str | os.PathLike | None = None) -> list[ScheduleAsset]`
  - `sdlc.schedules.loader.SCHEDULES_DIR_ENV: str`, `DEFAULT_SCHEDULES_DIR: Path`

- [ ] **Step 1: Write the failing test**

Create `tests/test_schedule_loader.py`:

```python
"""schedules/*.yaml loader (E-12). Mirrors agents/loader.py's fail-closed
idiom: a malformed asset must never reach the Temporal client."""

from __future__ import annotations

import pytest

from sdlc.models import ScheduleAsset
from sdlc.schedules.loader import ScheduleError, load_schedules

VALID = """\
spec:
  cron: "0 3 * * *"
  timezone: UTC
action:
  workflow: ReflectWorkflow
  banks: ["project:default"]
  backend: hindsight
  base_url: "http://localhost:8088"
"""


def _write(tmp_path, name: str, body: str):
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_loads_valid_asset_and_takes_id_from_filename(tmp_path):
    _write(tmp_path, "nightly-reflect.yaml", VALID)
    assets = load_schedules(tmp_path)
    assert len(assets) == 1
    a = assets[0]
    assert isinstance(a, ScheduleAsset)
    assert a.id == "nightly-reflect"  # filename is the API
    assert a.spec.cron == "0 3 * * *"
    assert a.spec.timezone == "UTC"
    assert a.action.workflow == "ReflectWorkflow"
    assert a.action.banks == ["project:default"]
    assert a.action.backend == "hindsight"


def test_timezone_defaults_to_utc(tmp_path):
    _write(
        tmp_path,
        "s.yaml",
        """\
spec:
  cron: "0 3 * * *"
action:
  workflow: ReflectWorkflow
  banks: ["project:default"]
""",
    )
    assert load_schedules(tmp_path)[0].spec.timezone == "UTC"


def test_bad_cron_field_count_raises(tmp_path):
    _write(tmp_path, "bad.yaml", VALID.replace('"0 3 * * *"', '"0 3 * *"'))
    with pytest.raises(ScheduleError, match="cron"):
        load_schedules(tmp_path)


def test_unknown_workflow_raises(tmp_path):
    _write(tmp_path, "bad.yaml", VALID.replace("ReflectWorkflow", "NopeWorkflow"))
    with pytest.raises(ScheduleError, match="NopeWorkflow"):
        load_schedules(tmp_path)


def test_empty_banks_raises(tmp_path):
    _write(tmp_path, "bad.yaml", VALID.replace('["project:default"]', "[]"))
    with pytest.raises(ScheduleError):
        load_schedules(tmp_path)


def test_missing_banks_raises(tmp_path):
    _write(
        tmp_path,
        "bad.yaml",
        """\
spec:
  cron: "0 3 * * *"
action:
  workflow: ReflectWorkflow
""",
    )
    with pytest.raises(ScheduleError):
        load_schedules(tmp_path)


def test_error_names_the_offending_file(tmp_path):
    _write(tmp_path, "nightly-reflect.yaml", VALID.replace("ReflectWorkflow", "Nope"))
    with pytest.raises(ScheduleError, match="nightly-reflect.yaml"):
        load_schedules(tmp_path)


def test_empty_directory_returns_empty_list(tmp_path):
    assert load_schedules(tmp_path) == []


def test_missing_directory_returns_empty_list(tmp_path):
    assert load_schedules(tmp_path / "does-not-exist") == []


def test_assets_are_sorted_by_id(tmp_path):
    _write(tmp_path, "b-two.yaml", VALID)
    _write(tmp_path, "a-one.yaml", VALID)
    assert [a.id for a in load_schedules(tmp_path)] == ["a-one", "b-two"]


def test_env_var_overrides_default_dir(tmp_path, monkeypatch):
    _write(tmp_path, "s.yaml", VALID)
    monkeypatch.setenv("SDLC_SCHEDULES_DIR", str(tmp_path))
    assert len(load_schedules()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schedule_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.schedules'`

- [ ] **Step 3: Add the models**

Append to `src/sdlc/models.py`, immediately after `MemoryConfig` (which ends ~line 378) and before `class PipelineConfig`:

```python
KNOWN_SCHEDULE_WORKFLOWS = {"ReflectWorkflow"}


class ScheduleAction(BaseModel):
    """The start-workflow action of a schedule asset. Temporal Schedules can
    only start workflows, never activities — hence ReflectWorkflow."""

    workflow: str
    banks: list[str] = Field(min_length=1)
    backend: Literal["fake", "hindsight"] = "fake"
    base_url: str = "http://localhost:8088"

    @field_validator("workflow")
    @classmethod
    def _known_workflow(cls, v: str) -> str:
        if v not in KNOWN_SCHEDULE_WORKFLOWS:
            raise ValueError(f"unknown workflow {v!r}; known: {sorted(KNOWN_SCHEDULE_WORKFLOWS)}")
        return v


class ScheduleSpecAsset(BaseModel):
    cron: str
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def _cron_shape(cls, v: str) -> str:
        if len(v.split()) != 5:
            raise ValueError(
                f"cron must have 5 whitespace-separated fields, got {len(v.split())}: {v!r}"
            )
        return v


class ScheduleAsset(BaseModel):
    """One schedules/<id>.yaml. `id` comes from the filename, not the body —
    the filename is the API."""

    id: str
    spec: ScheduleSpecAsset
    action: ScheduleAction
```

Ensure `models.py`'s imports include `field_validator` and `Literal`. Check the existing import lines at the top; if absent, extend them:

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator
```

- [ ] **Step 4: Write the loader**

Create `src/sdlc/schedules/__init__.py`:

```python
```

(empty file)

Create `src/sdlc/schedules/loader.py`:

```python
"""Schedule assets (E-12). schedules/<id>.yaml is the source of truth; the
filename is the schedule id. Deliberately mirrors agents/loader.py's
fail-closed shape — a malformed asset raises here, during `schedules apply`,
rather than silently at 3am.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from ..models import ScheduleAsset

SCHEDULES_DIR_ENV = "SDLC_SCHEDULES_DIR"
# repo_root/schedules — loader.py is src/sdlc/schedules/loader.py, so three
# parents up from the file dir is the repo root.
DEFAULT_SCHEDULES_DIR = Path(__file__).resolve().parents[3] / "schedules"


class ScheduleError(ValueError):
    """A schedule asset that violates a structural invariant (bad cron,
    unknown workflow, empty bank list)."""


def load_schedules(path: str | os.PathLike | None = None) -> list[ScheduleAsset]:
    """Parse every *.yaml in the schedules dir into ScheduleAssets, sorted by
    id. Resolution order: explicit arg, then $SDLC_SCHEDULES_DIR, then the
    shipped default. A missing or empty directory yields []; a malformed asset
    raises ScheduleError."""
    resolved = Path(path or os.environ.get(SCHEDULES_DIR_ENV) or DEFAULT_SCHEDULES_DIR)
    if not resolved.is_dir():
        return []
    assets: list[ScheduleAsset] = []
    for f in sorted(resolved.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        try:
            assets.append(ScheduleAsset(id=f.stem, **data))
        except ValidationError as e:
            raise ScheduleError(f"{f.name}: {e}") from e
    return assets
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_schedule_loader.py -v`
Expected: PASS — 11 passed

- [ ] **Step 6: Run the full suite for regressions**

Run: `pytest`
Expected: PASS — no new failures (`models.py` changed, so many modules re-import)

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/models.py src/sdlc/schedules/ tests/test_schedule_loader.py
git commit -m "feat(schedules): ScheduleAsset models + fail-closed yaml loader (E-12)"
```

---

### Task 2: ReflectWorkflow + worker registration

**Files:**
- Create: `src/sdlc/workflows/reflect.py`
- Modify: `src/sdlc/worker.py:44` (import) and `:65` (workflows list)
- Test: `tests/test_reflect_workflow.py`
- Test: `tests/test_worker_registration.py` (append)

**Interfaces:**
- Consumes: `sdlc.memory.activities.reflect`, `sdlc.memory.activities.ReflectInput(bank, backend="fake", base_url="http://localhost:8088")` — both already exist.
- Produces:
  - `sdlc.workflows.reflect.ReflectScheduleInput(banks: list[str], backend: str = "fake", base_url: str = "http://localhost:8088")` — a Pydantic `BaseModel`, since Schedules serialize args through the pydantic data converter.
  - `sdlc.workflows.reflect.ReflectWorkflow` with `@workflow.run async def run(self, inp: ReflectScheduleInput) -> int` returning the count of banks reflected successfully.

**Why a wrapper exists at all:** Temporal Schedules start workflows, not activities. `reflect` is an `@activity.defn` (`src/sdlc/memory/activities.py:94`). This workflow contains no logic beyond the loop.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reflect_workflow.py`:

```python
"""ReflectWorkflow (E-13) — the wrapper that lets a Temporal Schedule reach
the reflect activity. Runs the REAL workflow on a time-skipping worker with a
faked reflect activity, following tests/test_e2e_greenfield.py's pattern."""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.memory.activities import ReflectInput

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.reflect import ReflectScheduleInput, ReflectWorkflow

TASK_QUEUE = "reflect-test"

REFLECTED: list[str] = []
FAIL_BANKS: set[str] = set()


@activity.defn(name="reflect")
async def fake_reflect(inp: ReflectInput) -> None:
    if inp.bank in FAIL_BANKS:
        raise RuntimeError(f"backend unreachable for {inp.bank}")
    REFLECTED.append(inp.bank)


@pytest.fixture(autouse=True)
def _reset():
    REFLECTED.clear()
    FAIL_BANKS.clear()
    yield


async def _run(env: WorkflowEnvironment, inp: ReflectScheduleInput) -> int:
    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[ReflectWorkflow], activities=[fake_reflect]
    ):
        return await env.client.execute_workflow(
            ReflectWorkflow.run, inp, id=f"reflect-{uuid.uuid4()}", task_queue=TASK_QUEUE
        )


@pytest.mark.asyncio
async def test_each_bank_gets_its_own_reflect_execution():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        count = await _run(env, ReflectScheduleInput(banks=["project:a", "project:b", "project:c"]))
    assert count == 3
    assert REFLECTED == ["project:a", "project:b", "project:c"]


@pytest.mark.asyncio
async def test_one_failing_bank_does_not_skip_the_rest():
    FAIL_BANKS.add("project:b")
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with pytest.raises(Exception):
            await _run(env, ReflectScheduleInput(banks=["project:a", "project:b", "project:c"]))
    # b failed, but a and c still ran — the loop does not abort
    assert REFLECTED == ["project:a", "project:c"]


@pytest.mark.asyncio
async def test_a_failing_bank_fails_the_workflow_visibly():
    # The whole point of FR-404: a failed nightly reflect must be a visibly
    # failed workflow, never a silent no-op (spec: eve's failure mode).
    FAIL_BANKS.add("project:only")
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with pytest.raises(Exception) as ei:
            await _run(env, ReflectScheduleInput(banks=["project:only"]))
    assert "project:only" in str(ei.value)


@pytest.mark.asyncio
async def test_all_banks_succeeding_returns_full_count():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        count = await _run(env, ReflectScheduleInput(banks=["project:default"]))
    assert count == 1
    assert REFLECTED == ["project:default"]


@pytest.mark.asyncio
async def test_backend_and_base_url_reach_the_activity():
    seen: list[ReflectInput] = []

    @activity.defn(name="reflect")
    async def capturing(inp: ReflectInput) -> None:
        seen.append(inp)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[ReflectWorkflow], activities=[capturing]
        ):
            await env.client.execute_workflow(
                ReflectWorkflow.run,
                ReflectScheduleInput(
                    banks=["project:default"], backend="hindsight", base_url="http://mem:9000"
                ),
                id=f"reflect-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
    assert seen[0].backend == "hindsight"
    assert seen[0].base_url == "http://mem:9000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reflect_workflow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.workflows.reflect'`

- [ ] **Step 3: Write the workflow**

Create `src/sdlc/workflows/reflect.py`:

```python
"""ReflectWorkflow (FR-404, E-13) — the nightly memory-consolidation job.

Exists only because Temporal Schedules start workflows, never activities:
`reflect` is an @activity.defn. This wrapper holds no logic beyond looping the
bank list. Each bank is its own activity execution so one bank's backend
failure retries independently without re-reflecting the others.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from ..memory.activities import ReflectInput, reflect

# Reflect consolidates a whole bank — slower than the 30s recall/retain ops
# in feature.py's MEM_ACT, hence the longer ceiling.
REFLECT_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


class ReflectScheduleInput(BaseModel):
    banks: list[str] = Field(min_length=1)
    backend: str = "fake"
    base_url: str = "http://localhost:8088"


@workflow.defn
class ReflectWorkflow:
    """NEVER rename — the class name is the Temporal contract, and live
    Schedules reference it by name."""

    @workflow.run
    async def run(self, inp: ReflectScheduleInput) -> int:
        failed: list[str] = []
        for bank in inp.banks:
            try:
                await workflow.execute_activity(
                    reflect,
                    ReflectInput(bank=bank, backend=inp.backend, base_url=inp.base_url),
                    **REFLECT_ACT,
                )
            except Exception:
                # One unreachable bank must not skip the others, but the run
                # still fails below — a silent no-op is the failure mode this
                # whole feature exists to avoid.
                failed.append(bank)
        if failed:
            raise ApplicationError(
                f"reflect failed for banks: {', '.join(failed)}", non_retryable=True
            )
        return len(inp.banks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reflect_workflow.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Register the workflow on the worker**

In `src/sdlc/worker.py`, add the import next to the existing `from .workflows.feature import FeatureWorkflow` (line 44):

```python
from .workflows.feature import FeatureWorkflow
from .workflows.reflect import ReflectWorkflow
```

And extend the `workflows=` list (line 65):

```python
workflows = ([FeatureWorkflow, BenchmarkWorkflow, ReflectWorkflow],)
```

- [ ] **Step 6: Add the registration regression guard**

Append to `tests/test_worker_registration.py`:

```python
def test_worker_module_registers_reflect_workflow():
    # FR-404's original bug was a registered activity that nothing ever
    # called. reflect is only reachable if ReflectWorkflow is registered too.
    from sdlc import worker

    src = __import__("inspect").getsource(worker)
    assert "ReflectWorkflow" in src, "ReflectWorkflow missing from worker"


def test_reflect_workflow_is_reachable_from_the_reflect_activity():
    # the wrapper must actually call the activity — not just exist
    import inspect

    from sdlc.workflows import reflect as mod

    src = inspect.getsource(mod)
    assert "execute_activity" in src
    assert "reflect" in src
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_worker_registration.py tests/test_reflect_workflow.py -v`
Expected: PASS — 7 passed

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/workflows/reflect.py src/sdlc/worker.py tests/test_reflect_workflow.py tests/test_worker_registration.py
git commit -m "feat(schedules): ReflectWorkflow wrapper so a Schedule can reach reflect() (E-13)"
```

---

### Task 3: Pure reconcile diff

**Files:**
- Create: `src/sdlc/schedules/reconcile.py`
- Test: `tests/test_schedule_reconcile.py`

**Interfaces:**
- Consumes: `sdlc.models.ScheduleAsset` (Task 1).
- Produces:
  - `sdlc.schedules.reconcile.Change` — frozen dataclass `(action: str, id: str, reason: str)` where `action` ∈ `{"create", "update", "noop", "drift"}`.
  - `sdlc.schedules.reconcile.plan_changes(desired: list[ScheduleAsset], existing: dict[str, ScheduleAsset]) -> list[Change]`

**Why pure:** this is the whole interesting half of reconcile and it needs no Temporal client to test. Task 4 supplies `existing` from the server. Follows the codebase's existing pure-helper testing habit (`_cell_config`, `tests/test_benchmark_workflow.py:20`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_schedule_reconcile.py`:

```python
"""Pure yaml→server diff (E-12). No Temporal client involved: plan_changes is
a function of desired vs existing, so every reconcile rule is testable here."""

from __future__ import annotations

from sdlc.models import ScheduleAction, ScheduleAsset, ScheduleSpecAsset
from sdlc.schedules.reconcile import plan_changes


def asset(
    sid: str = "nightly-reflect", cron: str = "0 3 * * *", banks: list[str] | None = None
) -> ScheduleAsset:
    return ScheduleAsset(
        id=sid,
        spec=ScheduleSpecAsset(cron=cron),
        action=ScheduleAction(workflow="ReflectWorkflow", banks=banks or ["project:default"]),
    )


def _by_id(changes):
    return {c.id: c.action for c in changes}


def test_absent_on_server_is_create():
    assert _by_id(plan_changes([asset()], {})) == {"nightly-reflect": "create"}


def test_identical_is_noop():
    existing = {"nightly-reflect": asset()}
    assert _by_id(plan_changes([asset()], existing)) == {"nightly-reflect": "noop"}


def test_changed_cron_is_update():
    existing = {"nightly-reflect": asset(cron="0 4 * * *")}
    assert _by_id(plan_changes([asset()], existing)) == {"nightly-reflect": "update"}


def test_changed_banks_is_update():
    existing = {"nightly-reflect": asset(banks=["project:old"])}
    assert _by_id(plan_changes([asset()], existing)) == {"nightly-reflect": "update"}


def test_server_schedule_with_no_yaml_is_drift_not_delete():
    # Delete-by-default would turn "checked out an old branch and ran apply"
    # into an outage. Drift is reported; --prune (Task 4) deletes.
    existing = {"orphan": asset(sid="orphan")}
    changes = plan_changes([], existing)
    assert _by_id(changes) == {"orphan": "drift"}
    assert all(c.action != "delete" for c in changes)


def test_mixed_plan_covers_every_case():
    desired = [asset(sid="keep"), asset(sid="change", cron="0 5 * * *"), asset(sid="new")]
    existing = {
        "keep": asset(sid="keep"),
        "change": asset(sid="change", cron="0 9 * * *"),
        "gone": asset(sid="gone"),
    }
    assert _by_id(plan_changes(desired, existing)) == {
        "keep": "noop",
        "change": "update",
        "new": "create",
        "gone": "drift",
    }


def test_empty_both_sides_is_empty_plan():
    assert plan_changes([], {}) == []


def test_change_carries_a_human_reason():
    assert plan_changes([asset()], {})[0].reason


def test_plan_is_deterministically_ordered():
    desired = [asset(sid="b"), asset(sid="a")]
    existing = {"z": asset(sid="z"), "y": asset(sid="y")}
    ids = [c.id for c in plan_changes(desired, existing)]
    # desired order preserved, then drift sorted
    assert ids == ["b", "a", "y", "z"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schedule_reconcile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.schedules.reconcile'`

- [ ] **Step 3: Write the reconcile logic**

Create `src/sdlc/schedules/reconcile.py`:

```python
"""Pure yaml→server diff (E-12). Deliberately free of any Temporal client so
every reconcile rule is unit-testable; apply.py supplies `existing` and turns
Changes into API calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ScheduleAsset


@dataclass(frozen=True)
class Change:
    action: str  # create | update | noop | drift
    id: str
    reason: str = ""


def plan_changes(desired: list[ScheduleAsset], existing: dict[str, ScheduleAsset]) -> list[Change]:
    """Diff yaml assets against server state. Never emits a delete: a server
    schedule with no yaml is reported as drift, and only apply's explicit
    --prune turns that into a deletion."""
    changes: list[Change] = []
    desired_ids = {a.id for a in desired}
    for a in desired:
        current = existing.get(a.id)
        if current is None:
            changes.append(Change("create", a.id, "not on server"))
        elif current != a:
            changes.append(Change("update", a.id, "differs from server"))
        else:
            changes.append(Change("noop", a.id, "identical"))
    for sid in sorted(existing):
        if sid not in desired_ids:
            changes.append(Change("drift", sid, "on server, no yaml asset"))
    return changes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schedule_reconcile.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/schedules/reconcile.py tests/test_schedule_reconcile.py
git commit -m "feat(schedules): pure yaml-vs-server reconcile diff (E-12)"
```

---

### Task 4: Temporal translation + apply I/O + CLI

**Files:**
- Create: `src/sdlc/schedules/apply.py`
- Modify: `src/sdlc/cli.py` (docstring ~line 7; subparsers after the `status` parser ~line 56; dispatch before `handle = client.get_workflow_handle_for(...)` ~line 100)
- Test: `tests/test_schedule_apply.py`

**Interfaces:**
- Consumes: `ScheduleAsset` (Task 1), `ReflectScheduleInput` (Task 2), `plan_changes`/`Change` (Task 3), `sdlc.worker.TASK_QUEUE`.
- Produces:
  - `sdlc.schedules.apply.to_temporal(a: ScheduleAsset) -> temporalio.client.Schedule`
  - `sdlc.schedules.apply.from_temporal(sid: str, sched: Schedule) -> ScheduleAsset | None` — returns `None` for schedules we don't manage.
  - `sdlc.schedules.apply.fetch_existing(client) -> dict[str, ScheduleAsset]`
  - `sdlc.schedules.apply.apply_changes(client, desired, changes, prune: bool = False) -> list[str]` — returns human-readable result lines.
  - `sdlc.schedules.apply.format_plan(changes: list[Change]) -> str`

**Note:** `from_temporal` returning `None` for unmanaged schedules is the Global Constraint "only manage our own schedules" — without it, every unrelated schedule in the namespace reports as drift.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schedule_apply.py`:

```python
"""Asset↔Temporal translation and plan formatting (E-12). The round-trip test
covers both directions at once; fetch_existing/apply_changes are thin I/O and
are exercised against a live server only in manual runs."""

from __future__ import annotations

from temporalio.client import ScheduleActionStartWorkflow

from sdlc.models import ScheduleAction, ScheduleAsset, ScheduleSpecAsset
from sdlc.schedules.apply import format_plan, from_temporal, to_temporal
from sdlc.schedules.reconcile import Change


def asset(sid: str = "nightly-reflect") -> ScheduleAsset:
    return ScheduleAsset(
        id=sid,
        spec=ScheduleSpecAsset(cron="0 3 * * *", timezone="UTC"),
        action=ScheduleAction(
            workflow="ReflectWorkflow",
            banks=["project:default"],
            backend="hindsight",
            base_url="http://mem:9000",
        ),
    )


def test_round_trip_preserves_the_asset():
    a = asset()
    assert from_temporal(a.id, to_temporal(a)) == a


def test_to_temporal_sets_cron_and_timezone():
    sched = to_temporal(asset())
    assert sched.spec.cron_expressions == ["0 3 * * *"]
    assert sched.spec.time_zone_name == "UTC"


def test_to_temporal_starts_reflect_workflow_with_the_bank_list():
    sched = to_temporal(asset())
    assert isinstance(sched.action, ScheduleActionStartWorkflow)
    assert sched.action.workflow == "ReflectWorkflow"
    assert sched.action.args[0].banks == ["project:default"]
    assert sched.action.args[0].backend == "hindsight"


def test_from_temporal_ignores_schedules_we_do_not_manage():
    # An unrelated schedule in the namespace must not surface as drift.
    sched = to_temporal(asset())
    sched.action.workflow = "SomeoneElsesWorkflow"
    assert from_temporal("theirs", sched) is None


def test_format_plan_lists_every_change():
    out = format_plan(
        [Change("create", "a", "not on server"), Change("drift", "b", "on server, no yaml asset")]
    )
    assert "create" in out and "a" in out
    assert "drift" in out and "b" in out


def test_format_plan_of_empty_plan_says_so():
    assert "no schedules" in format_plan([]).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schedule_apply.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.schedules.apply'`

- [ ] **Step 3: Write apply.py**

Create `src/sdlc/schedules/apply.py`:

```python
"""Reconcile schedule assets into Temporal Schedules (E-12).

Files are the source of truth, but Schedules are server-side mutable state —
so applying is an explicit act with a visible diff (`--dry-run`), never a side
effect of a worker restart. See the spec's "explicit CLI apply" decision.
"""

from __future__ import annotations

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleUpdate,
)

from ..models import KNOWN_SCHEDULE_WORKFLOWS, ScheduleAsset
from ..workflows.reflect import ReflectScheduleInput
from .reconcile import Change, plan_changes


def _workflow_id(sid: str) -> str:
    return f"sched-{sid}"


def to_temporal(a: ScheduleAsset) -> Schedule:
    from ..worker import TASK_QUEUE

    return Schedule(
        action=ScheduleActionStartWorkflow(
            a.action.workflow,
            args=[
                ReflectScheduleInput(
                    banks=a.action.banks, backend=a.action.backend, base_url=a.action.base_url
                )
            ],
            id=_workflow_id(a.id),
            task_queue=TASK_QUEUE,
        ),
        spec=ScheduleSpec(cron_expressions=[a.spec.cron], time_zone_name=a.spec.timezone),
    )


def from_temporal(sid: str, sched: Schedule) -> ScheduleAsset | None:
    """Server Schedule → asset, or None if we don't manage it. Unmanaged
    schedules must be invisible to the diff, not reported as drift."""
    action = sched.action
    if not isinstance(action, ScheduleActionStartWorkflow):
        return None
    if action.workflow not in KNOWN_SCHEDULE_WORKFLOWS:
        return None
    if not action.args:
        return None
    inp = action.args[0]
    return ScheduleAsset(
        id=sid,
        spec={
            "cron": sched.spec.cron_expressions[0],
            "timezone": sched.spec.time_zone_name or "UTC",
        },
        action={
            "workflow": action.workflow,
            "banks": inp.banks,
            "backend": inp.backend,
            "base_url": inp.base_url,
        },
    )


async def fetch_existing(client: Client) -> dict[str, ScheduleAsset]:
    out: dict[str, ScheduleAsset] = {}
    async for entry in await client.list_schedules():
        desc = await client.get_schedule_handle(entry.id).describe()
        asset = from_temporal(entry.id, desc.schedule)
        if asset is not None:
            out[entry.id] = asset
    return out


def format_plan(changes: list[Change]) -> str:
    if not changes:
        return "no schedules to reconcile"
    return "\n".join(f"  {c.action:<7} {c.id:<24} ({c.reason})" for c in changes)


async def apply_changes(
    client: Client, desired: list[ScheduleAsset], changes: list[Change], prune: bool = False
) -> list[str]:
    """Execute a plan. Drift is only deleted when prune is True."""
    by_id = {a.id: a for a in desired}
    results: list[str] = []
    for c in changes:
        if c.action == "create":
            await client.create_schedule(c.id, to_temporal(by_id[c.id]))
            results.append(f"created {c.id}")
        elif c.action == "update":
            handle = client.get_schedule_handle(c.id)
            asset = by_id[c.id]
            # update() takes an updater that returns a ScheduleUpdate, never a
            # bare Schedule. The default-arg bind avoids the late-binding trap.
            await handle.update(lambda _inp, a=asset: ScheduleUpdate(schedule=to_temporal(a)))
            results.append(f"updated {c.id}")
        elif c.action == "drift":
            if prune:
                await client.get_schedule_handle(c.id).delete()
                results.append(f"deleted {c.id}")
            else:
                results.append(f"DRIFT {c.id} on server with no yaml asset (use --prune to delete)")
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schedule_apply.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Wire the CLI**

In `src/sdlc/cli.py`, extend the module docstring (after the `reject` line, ~line 7):

```
  python -m sdlc.cli schedules list
  python -m sdlc.cli schedules apply --dry-run
  python -m sdlc.cli schedules apply
```

Add the subparsers after the `status` parser block (~line 56, before the benchmark block):

```python
sc = sub.add_parser("schedules")
scsub = sc.add_subparsers(dest="sched_cmd", required=True)
scsub.add_parser("list")
sa = scsub.add_parser("apply")
sa.add_argument("--dry-run", action="store_true", help="print the plan without touching Temporal")
sa.add_argument(
    "--prune", action="store_true", help="delete server schedules that have no yaml asset"
)
```

`schedules list` reads local yaml only, so it must not require a Temporal connection. Change the client-connect guard (line 68) from:

```python
    if args.cmd != "benchmark":
```

to:

```python
    _local_only = (args.cmd == "benchmark"
                   or (args.cmd == "schedules" and args.sched_cmd == "list"))
    if not _local_only:
```

Add the dispatch immediately before `handle = client.get_workflow_handle_for(...)` (~line 100):

```python
if args.cmd == "schedules":
    from .schedules.apply import apply_changes, fetch_existing, format_plan
    from .schedules.loader import load_schedules
    from .schedules.reconcile import plan_changes

    desired = load_schedules()
    if args.sched_cmd == "list":
        if not desired:
            print("no schedule assets found")
            return
        for a in desired:
            print(
                f"{a.id:<24} {a.spec.cron!r} {a.spec.timezone} "
                f"→ {a.action.workflow} banks={a.action.banks}"
            )
        return
    existing = await fetch_existing(client)
    changes = plan_changes(desired, existing)
    if args.dry_run:
        print(format_plan(changes))
        return
    for line in await apply_changes(client, desired, changes, prune=args.prune):
        print(line)
    return
```

- [ ] **Step 6: Verify the CLI parses**

Run: `python -m sdlc.cli schedules list`
Expected: `no schedule assets found` (the `schedules/` dir doesn't exist until Task 5), with no Temporal connection attempted.

Run: `python -m sdlc.cli schedules apply --help`
Expected: help text listing `--dry-run` and `--prune`.

- [ ] **Step 7: Run the full suite**

Run: `pytest`
Expected: PASS — no new failures

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/schedules/apply.py src/sdlc/cli.py tests/test_schedule_apply.py
git commit -m "feat(schedules): sdlc schedules apply/list with dry-run diff (E-12)"
```

---

### Task 5: The nightly-reflect asset + roadmap amendments

**Files:**
- Create: `schedules/nightly-reflect.yaml`
- Modify: `ROADMAP.md` (§9.3 lines ~211-213; §4 FR-404 line ~82)
- Test: `tests/test_nightly_reflect_asset.py`

**Interfaces:**
- Consumes: `load_schedules` (Task 1), `to_temporal` (Task 4), `KNOWN_SCHEDULE_WORKFLOWS` (Task 1).
- Produces: the shipped `schedules/nightly-reflect.yaml` asset.

**This is the task that closes the project half of FR-404.** The roadmap amendments are part of it, not a follow-up — the spec's three findings contradict E-12/E-13 as written.

- [ ] **Step 1: Write the failing test**

Create `tests/test_nightly_reflect_asset.py`:

```python
"""The shipped nightly-reflect asset (E-13, FR-404). Guards the scope
boundary: project banks only — org_bank has no writers, so an org schedule
would be a permanent no-op behind a checked box."""

from __future__ import annotations

from pathlib import Path

from sdlc.schedules.apply import to_temporal
from sdlc.schedules.loader import DEFAULT_SCHEDULES_DIR, load_schedules

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_default_schedules_dir_points_at_the_repo_schedules_folder():
    assert DEFAULT_SCHEDULES_DIR == REPO_ROOT / "schedules"


def test_nightly_reflect_asset_ships_and_loads():
    assets = {a.id: a for a in load_schedules(DEFAULT_SCHEDULES_DIR)}
    assert "nightly-reflect" in assets


def test_nightly_reflect_targets_reflect_workflow_nightly():
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    assert a.action.workflow == "ReflectWorkflow"
    assert len(a.spec.cron.split()) == 5
    assert a.action.banks


def test_nightly_reflect_is_project_scoped_only():
    # Scope guard (spec: Findings §3). org_bank has no writers — every
    # _retain call site in feature.py passes cfg.memory.project_bank — so an
    # org bank here would consolidate nothing, nightly, forever.
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    for bank in a.action.banks:
        assert bank.startswith("project:"), (
            f"{bank!r} is not project-scoped; org reflect is out of scope "
            f"until something retains to org_bank"
        )


def test_shipped_asset_translates_to_a_temporal_schedule():
    a = {x.id: x for x in load_schedules(DEFAULT_SCHEDULES_DIR)}["nightly-reflect"]
    sched = to_temporal(a)
    assert sched.spec.cron_expressions == [a.spec.cron]
    assert sched.action.workflow == "ReflectWorkflow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nightly_reflect_asset.py -v`
Expected: FAIL — `KeyError: 'nightly-reflect'` (the asset doesn't exist yet)

- [ ] **Step 3: Create the asset**

Create `schedules/nightly-reflect.yaml`:

```yaml
# FR-404 — nightly memory consolidation. Project banks only: org_bank has no
# writers yet (every _retain in feature.py targets project_bank), so an org
# entry here would consolidate an empty bank forever. See ROADMAP §9.3.
#
# Applied with: python -m sdlc.cli schedules apply --dry-run
spec:
  cron: "0 3 * * *"
  timezone: UTC
action:
  workflow: ReflectWorkflow
  banks:
    - "project:default"
  backend: hindsight
  base_url: "http://localhost:8088"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_nightly_reflect_asset.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Verify the CLI sees it**

Run: `python -m sdlc.cli schedules list`
Expected: `nightly-reflect             '0 3 * * *' UTC → ReflectWorkflow banks=['project:default']`

- [ ] **Step 6: Amend ROADMAP.md §9.3**

Replace the E-12 and E-13 lines (~211-212) with:

```markdown
- [x] **E-12** `schedules/*.yaml` assets reconciled into Temporal Schedules via `sdlc schedules apply` (`--dry-run` shows the diff; drift is reported, `--prune` deletes). *Not worker boot as originally written: schedules are server-side mutable state, so a restart must not silently rewrite production scheduling. Spec: `docs/superpowers/specs/2026-07-16-schedules-as-files-and-nightly-reflect-design.md`.*
- [x] **E-13** `schedules/nightly-reflect.yaml` → `ReflectWorkflow` → the existing `reflect()` activity, **project banks only** (FR-404, partial). *Corrected from "invoking the existing `reflect()` activity": Temporal Schedules start workflows, not activities, hence the wrapper. Corrected from "project + org scope": see E-25.*
```

Add E-25 after the E-14 line (~213):

```markdown
- [ ] **E-25** Nothing retains to `org_bank` — `MemoryConfig` defines it (`models.py:376`) but every `_retain` call site in `feature.py` passes `project_bank`. Cross-project consolidation (`reflect(org)`, SDLC-spec §279) therefore has no writers, and the nightly schedule deliberately omits it. **This, not scheduling, is the remaining blocker on FR-404's org half.** Needs a decision on what belongs in an org bank — likely **(new scope)**.
```

- [ ] **Step 7: Amend ROADMAP.md §4 (FR-404)**

Replace the FR-404 line (~82) with:

```markdown
- [ ] ⚠️ **FR-404** nightly reflect — **project half live**: `schedules/nightly-reflect.yaml` → `ReflectWorkflow` → `reflect()`, applied via `sdlc schedules apply` (E-12/E-13). **Org half unmet**: nothing retains to `org_bank`, so `reflect(org)` would consolidate an empty bank (E-25). Not `[x]` until org has writers.
```

- [ ] **Step 8: Amend ROADMAP.md §8 item 3**

Replace item 3 (~line 170) with:

```markdown
3. ~~**retro/reflect wiring** (FR-404) — starts accumulating the SC-4/SC-6 calibration signal. Tasks: **E-12, E-13** (§9.3).~~ **Partially done** — schedule mechanism + nightly project reflect ship (E-12/E-13); plan `docs/superpowers/plans/2026-07-16-schedules-as-files-and-nightly-reflect.md`. Signal only accrues on runs with `memory.enabled=true` (defaults `False`). Org half blocked on **E-25**; the retro *stage* (§1 item 13, `RunSummary`) is still unbuilt.
```

- [ ] **Step 9: Run the full suite**

Run: `pytest`
Expected: PASS — no new failures

- [ ] **Step 10: Commit**

```bash
git add schedules/ ROADMAP.md tests/test_nightly_reflect_asset.py
git commit -m "feat(schedules): nightly-reflect asset + roadmap amendments (E-13, FR-404 partial)

Closes the project half of FR-404: reflect() is finally called. Amends E-12
(CLI apply, not worker boot) and E-13 (workflow wrapper; project banks only),
and adds E-25 for the org_bank-has-no-writers hole that the original E-13
phrasing would have papered over."
```

---

## Manual verification (after Task 5)

The test suite never touches a real Temporal server. Verify the reconcile path once by hand:

```bash
# terminal 1
temporal server start-dev

# terminal 2
python -m sdlc.cli schedules apply --dry-run    # expect: create nightly-reflect
python -m sdlc.cli schedules apply              # expect: created nightly-reflect
python -m sdlc.cli schedules apply --dry-run    # expect: noop  nightly-reflect
temporal schedule list                          # expect: nightly-reflect listed
```

Then edit the cron in `schedules/nightly-reflect.yaml` to `"0 4 * * *"` and re-run `--dry-run`; expect `update`. Revert the edit before committing.
