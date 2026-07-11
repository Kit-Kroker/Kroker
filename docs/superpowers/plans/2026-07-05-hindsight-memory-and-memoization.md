# Hindsight Memory + Memoization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the P3 memory layer (PRD FR-400/FR-401/FR-402, ARCHITECTURE.md §6) — recall/retain/reflect against a Hindsight-shaped backend, wired into `FeatureWorkflow` as `RecallSnapshot` stage inputs — plus the ADR-5 content-addressed memoization cache with a per-run watermark, so unchanged upstream proposer stages can be skipped on a dev-loop re-run.

**Architecture:** A `Memory` protocol (ABC) with two implementations — `FakeMemory` (in-process, for unit tests and CI, no external service) and `HindsightMemory` (real HTTP client). All backend I/O lives in Temporal activities (`memory/activities.py`); workflow code only ever calls those activities through two gated helpers, `_recall`/`_retain`, mirroring the existing `_record`/`_judge` benchmark-gating pattern in `feature.py`. A separate `memoization/` package implements the ADR-5 content-addressed cache (local filesystem, hash-named files — no new infra) and wraps the four upstream proposer stages (clarify, architect, plan, devops); `qa`/`merge_verdict` are deliberately NOT cached (cheap, and re-derived from a fresh diff every time — no ROI, see Task 10).

**Tech Stack:** Python 3.11, pydantic v2, temporalio, `httpx` (new dependency, real Hindsight client only).

## Global Constraints

- Memory access happens ONLY in activities — never directly in `workflows/feature.py` (ARCHITECTURE.md §2, "memory is I/O").
- Memory must never block or fail a run: `recall_snapshot` degrades to an empty `RecallSnapshot` on any backend error (logged); `_retain` swallows activity failures after Temporal's own retries are exhausted.
- Every new Temporal activity/workflow-visible model must go through the existing `pydantic_data_converter` — plain `@dataclass` for activity inputs (matches `activities.py` convention), `pydantic.BaseModel` for anything crossing into agent/workflow state.
- Follow the existing gated-helper purity pattern (`test_factory_purity.py`): memory activities must only be invoked through `_recall`/`_retain`, each starting with an `if not cfg.memory.enabled: return ...` guard — this repo already enforces an equivalent invariant for benchmarking and a reviewer will expect the same shape here.
- No YAML config loader exists yet (`PipelineConfig()` is constructed directly in `cli.py`) — do NOT invent one. Backend selection is a `MemoryConfig` field with an env var default, same convention as `SDLC_WORKTREES_ROOT` in `activities.py`.
- New Python files: no module or class docstring paragraphs beyond one short paragraph; no inline comments except where a non-obvious invariant needs explaining (matches the existing codebase style visible in `activities.py`/`harness/adapters.py`).

---

### Task 1: Memory models + config

**Files:**
- Modify: `src/sdlc/models.py`
- Test: `tests/test_memory_models.py`

**Interfaces:**
- Produces: `MemoryKind` (str Enum: `STAGE_SUMMARY`, `GOTCHA`, `GATE_FEEDBACK`), `RecallSnapshot(query_hash: str, bank: str, watermark: str, items: list[str], degraded: bool = False)`, `RetainItem(kind: MemoryKind, bank: str, text: str, metadata: dict[str, str])`, `MemoryConfig(enabled: bool = False, backend: Literal["fake","hindsight"] = "fake", base_url: str, org_bank: str, project_bank: str, watermark: str | None)`. `PipelineConfig.memory: MemoryConfig` and `PipelineConfig.memoization_enabled: bool = False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_models.py
from sdlc.models import (
    MemoryConfig, MemoryKind, PipelineConfig, RecallSnapshot, RetainItem,
)


def test_recall_snapshot_defaults_not_degraded():
    snap = RecallSnapshot(query_hash="abc", bank="project:x", watermark="3")
    assert snap.items == []
    assert snap.degraded is False


def test_retain_item_requires_kind_bank_text():
    item = RetainItem(kind=MemoryKind.GOTCHA, bank="org", text="did a thing",
                      metadata={"run_id": "r1"})
    assert item.kind is MemoryKind.GOTCHA
    assert item.metadata["run_id"] == "r1"


def test_pipeline_config_has_disabled_memory_by_default():
    cfg = PipelineConfig()
    assert cfg.memory.enabled is False
    assert cfg.memory.backend == "fake"
    assert cfg.memoization_enabled is False


def test_memory_config_project_bank_default_matches_org_default_shape():
    cfg = MemoryConfig()
    assert cfg.org_bank == "org"
    assert cfg.project_bank.startswith("project:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'RecallSnapshot' from 'sdlc.models'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/sdlc/models.py`, after the `MergeVerdict` class (before `class PipelineConfig`):

```python
class MemoryKind(str, Enum):
    STAGE_SUMMARY = "stage_summary"
    GOTCHA = "gotcha"
    GATE_FEEDBACK = "gate_feedback"


class RecallSnapshot(BaseModel):
    """Persisted, hashed recall result — FR-402: a declared stage input,
    never a live side-channel. `degraded=True` means the backend was
    unreachable; the pipeline proceeds with an empty snapshot rather than
    blocking on memory."""
    query_hash: str
    bank: str
    watermark: str
    items: list[str] = Field(default_factory=list)
    degraded: bool = False


class RetainItem(BaseModel):
    kind: MemoryKind
    bank: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    """FR-400. `watermark=None` means "capture fresh at run start"; setting
    it pins a run to a prior freeze point (ADR-5 explicit "refresh
    memory")."""
    enabled: bool = False
    backend: Literal["fake", "hindsight"] = "fake"
    base_url: str = "http://localhost:8088"
    org_bank: str = "org"
    project_bank: str = "project:default"
    watermark: str | None = None
```

Then add two fields to `PipelineConfig` (near `benchmark: BenchmarkConfig`):

```python
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    memoization_enabled: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py tests/test_memory_models.py
git commit -m "feat(memory): add RecallSnapshot/RetainItem/MemoryConfig contracts"
```

---

### Task 2: Memory protocol

**Files:**
- Create: `src/sdlc/memory/__init__.py`
- Create: `src/sdlc/memory/protocol.py`
- Test: `tests/test_memory_protocol.py`

**Interfaces:**
- Consumes: `RecallSnapshot`, `RetainItem` (Task 1).
- Produces: `Memory` ABC with `async recall(bank, query, filters, watermark) -> RecallSnapshot`, `async retain(item) -> None`, `async reflect(bank) -> None`, `async current_watermark(bank) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_protocol.py
import pytest

from sdlc.memory.protocol import Memory


def test_memory_is_abstract():
    with pytest.raises(TypeError):
        Memory()


def test_memory_declares_all_four_operations():
    for name in ("recall", "retain", "reflect", "current_watermark"):
        assert name in Memory.__abstractmethods__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.memory'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/memory/__init__.py
```
(empty — marks the package)

```python
# src/sdlc/memory/protocol.py
"""Memory backend abstraction. All access happens in activities
(memory/activities.py) — workflow code never imports this directly."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import RecallSnapshot, RetainItem


class Memory(ABC):
    @abstractmethod
    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot: ...

    @abstractmethod
    async def retain(self, item: RetainItem) -> None: ...

    @abstractmethod
    async def reflect(self, bank: str) -> None: ...

    @abstractmethod
    async def current_watermark(self, bank: str) -> str: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_protocol.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memory/__init__.py src/sdlc/memory/protocol.py tests/test_memory_protocol.py
git commit -m "feat(memory): add Memory backend protocol"
```

---

### Task 3: Scrub

**Files:**
- Create: `src/sdlc/memory/scrub.py`
- Test: `tests/test_memory_scrub.py`

**Interfaces:**
- Produces: `scrub(text: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_scrub.py
from sdlc.memory.scrub import scrub


def test_scrub_redacts_api_key():
    out = scrub("used key sk-abcdefghijklmnopqrstuvwx to call the api")
    assert "sk-abcdefghijklmnopqrstuvwx" not in out
    assert "[REDACTED_API_KEY]" in out


def test_scrub_redacts_email():
    out = scrub("contact maksim.shautsou.dev@gmail.com for access")
    assert "maksim.shautsou.dev@gmail.com" not in out
    assert "[REDACTED_EMAIL]" in out


def test_scrub_redacts_password_assignment():
    out = scrub("config had password=hunter2 in it")
    assert "hunter2" not in out


def test_scrub_leaves_ordinary_text_untouched():
    text = "the merge added a retry policy with 3 attempts"
    assert scrub(text) == text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_scrub.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.memory.scrub'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/memory/scrub.py
"""Best-effort secret/PII redaction before anything is retained. Not a
security boundary by itself — retained text still lands in an
operator-controlled Hindsight instance — but keeps obvious secrets out of
a long-lived memory store by default."""
from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
     "[REDACTED_EMAIL]"),
    (re.compile(r"(?i)(password|token|secret)\s*[:=]\s*\S+"),
     r"\1=[REDACTED]"),
]


def scrub(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_scrub.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memory/scrub.py tests/test_memory_scrub.py
git commit -m "feat(memory): add secret/PII scrub before retain"
```

---

### Task 4: Fake in-memory backend

**Files:**
- Create: `src/sdlc/memory/fake.py`
- Test: `tests/test_memory_fake.py`

**Interfaces:**
- Consumes: `Memory` (Task 2), `RecallSnapshot`/`RetainItem` (Task 1).
- Produces: `FakeMemory` — concrete `Memory` implementation, one shared instance safe to reuse across calls within a process (used by `memory/activities.py` in Task 5).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_fake.py
import pytest

from sdlc.memory.fake import FakeMemory
from sdlc.models import MemoryKind, RetainItem


@pytest.mark.asyncio
async def test_recall_empty_bank_returns_no_items():
    mem = FakeMemory()
    snap = await mem.recall("project:x", "query", {}, None)
    assert snap.items == []
    assert snap.degraded is False


@pytest.mark.asyncio
async def test_retain_then_recall_returns_it():
    mem = FakeMemory()
    await mem.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:x",
                                text="fixed a flaky test", metadata={}))
    snap = await mem.recall("project:x", "query", {}, None)
    assert snap.items == ["fixed a flaky test"]


@pytest.mark.asyncio
async def test_recall_filters_by_metadata():
    mem = FakeMemory()
    await mem.retain(RetainItem(kind=MemoryKind.STAGE_SUMMARY, bank="b",
                                text="clarify done", metadata={"stage": "clarify"}))
    await mem.retain(RetainItem(kind=MemoryKind.STAGE_SUMMARY, bank="b",
                                text="architect done", metadata={"stage": "architect"}))
    snap = await mem.recall("b", "q", {"stage": "architect"}, None)
    assert snap.items == ["architect done"]


@pytest.mark.asyncio
async def test_watermark_freezes_recall_against_later_retains():
    mem = FakeMemory()
    await mem.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="b", text="first",
                                metadata={}))
    watermark = await mem.current_watermark("b")
    await mem.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="b", text="second",
                                metadata={}))
    frozen = await mem.recall("b", "q", {}, watermark)
    live = await mem.recall("b", "q", {}, None)
    assert frozen.items == ["first"]
    assert live.items == ["first", "second"]


@pytest.mark.asyncio
async def test_reflect_is_a_noop_that_does_not_raise():
    mem = FakeMemory()
    await mem.reflect("b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_fake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.memory.fake'`

(If `pytest-asyncio` is not yet installed, add `pytest-asyncio>=0.24` to the `dev` extra in `pyproject.toml` and add `asyncio_mode = "auto"` under `[tool.pytest.ini_options]` before running — check first with `pip show pytest-asyncio`.)

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/memory/fake.py
"""In-memory Memory implementation — unit-test/CI double, no Hindsight
container required."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from ..models import RecallSnapshot, RetainItem
from .protocol import Memory


@dataclass
class _Entry:
    text: str
    metadata: dict[str, str]
    version: int


@dataclass
class FakeMemory(Memory):
    """The per-bank entry count IS the watermark: recalling against an
    earlier watermark reproduces an earlier recall even after later
    retains land — the freeze semantics ADR-5 relies on."""
    _entries: dict[str, list[_Entry]] = field(
        default_factory=lambda: defaultdict(list))

    async def current_watermark(self, bank: str) -> str:
        return str(len(self._entries[bank]))

    async def retain(self, item: RetainItem) -> None:
        bank_entries = self._entries[item.bank]
        bank_entries.append(_Entry(text=item.text, metadata=item.metadata,
                                   version=len(bank_entries) + 1))

    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot:
        cutoff = (int(watermark) if watermark is not None
                 else len(self._entries[bank]))
        matches = [
            e.text for e in self._entries[bank]
            if e.version <= cutoff
            and all(e.metadata.get(k) == v for k, v in filters.items())
        ]
        query_hash = hashlib.sha256(
            f"{bank}|{query}|{sorted(filters.items())}|{cutoff}".encode()
        ).hexdigest()
        return RecallSnapshot(query_hash=query_hash, bank=bank,
                              watermark=str(cutoff), items=matches[-10:])

    async def reflect(self, bank: str) -> None:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_fake.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memory/fake.py tests/test_memory_fake.py pyproject.toml
git commit -m "feat(memory): add FakeMemory in-process backend"
```

---

### Task 5: Memory activities

**Files:**
- Create: `src/sdlc/memory/activities.py`
- Test: `tests/test_memory_activities.py`

**Interfaces:**
- Consumes: `FakeMemory` (Task 4), `scrub` (Task 3), `RecallSnapshot`/`RetainItem` (Task 1).
- Produces: `@activity.defn` functions `recall_snapshot(RecallInput) -> RecallSnapshot`, `retain(RetainInput) -> None`, `capture_watermark(WatermarkInput) -> str`, `reflect(ReflectInput) -> None`, plus dataclasses `RecallInput`, `RetainInput`, `WatermarkInput`, `ReflectInput` (all carry `backend: str = "fake"`, `base_url: str = "http://localhost:8088"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_activities.py
import pytest

from sdlc.memory.activities import (
    RecallInput, RetainInput, WatermarkInput, capture_watermark,
    recall_snapshot, retain,
)
from sdlc.models import MemoryKind, RetainItem


def test_recall_snapshot_is_a_temporal_activity():
    assert getattr(recall_snapshot, "__temporal_activity_definition",
                  None) is not None


def test_retain_is_a_temporal_activity():
    assert getattr(retain, "__temporal_activity_definition", None) is not None


@pytest.mark.asyncio
async def test_retain_then_recall_round_trips_through_fake_backend():
    await retain(RetainInput(
        item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:x",
                        text="flaky test needed a retry", metadata={}),
        backend="fake"))
    snap = await recall_snapshot(RecallInput(bank="project:x", query="q",
                                             backend="fake"))
    assert snap.items == ["flaky test needed a retry"]
    assert snap.degraded is False


@pytest.mark.asyncio
async def test_retain_scrubs_secrets_before_storing():
    await retain(RetainInput(
        item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:scrub-test",
                        text="used sk-abcdefghijklmnopqrstuvwx to auth",
                        metadata={}),
        backend="fake"))
    snap = await recall_snapshot(RecallInput(bank="project:scrub-test",
                                             query="q", backend="fake"))
    assert "sk-abcdefghijklmnopqrstuvwx" not in snap.items[0]


@pytest.mark.asyncio
async def test_recall_snapshot_degrades_on_backend_error(monkeypatch):
    import sdlc.memory.activities as act_mod

    class _Boom:
        async def recall(self, *a, **kw):
            raise ConnectionError("hindsight unreachable")

    monkeypatch.setattr(act_mod, "_backend", lambda base_url, backend: _Boom())
    snap = await recall_snapshot(RecallInput(bank="b", query="q"))
    assert snap.degraded is True
    assert snap.items == []


@pytest.mark.asyncio
async def test_capture_watermark_reflects_retains():
    before = await capture_watermark(WatermarkInput(bank="project:wm",
                                                    backend="fake"))
    await retain(RetainInput(
        item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:wm",
                        text="x", metadata={}), backend="fake"))
    after = await capture_watermark(WatermarkInput(bank="project:wm",
                                                   backend="fake"))
    assert int(after) == int(before) + 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_activities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.memory.activities'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/memory/activities.py
"""Temporal activities wrapping the Memory backend. All memory I/O funnels
through here — workflow code never touches a backend directly
(ARCHITECTURE.md §2, 'memory is I/O')."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from temporalio import activity

from ..models import RecallSnapshot, RetainItem
from .fake import FakeMemory
from .protocol import Memory
from .scrub import scrub

logger = logging.getLogger(__name__)

_fake_singleton = FakeMemory()


def _backend(base_url: str, backend: str) -> Memory:
    if backend == "hindsight":
        from .hindsight_client import HindsightMemory
        return HindsightMemory(base_url=base_url)
    return _fake_singleton


@dataclass
class RecallInput:
    bank: str
    query: str
    filters: dict[str, str] = field(default_factory=dict)
    watermark: str | None = None
    backend: str = "fake"
    base_url: str = "http://localhost:8088"


@activity.defn
async def recall_snapshot(inp: RecallInput) -> RecallSnapshot:
    """Never raises: an unreachable backend degrades to an empty snapshot
    (logged) rather than blocking the pipeline on memory."""
    try:
        memory = _backend(inp.base_url, inp.backend)
        return await memory.recall(inp.bank, inp.query, inp.filters,
                                   inp.watermark)
    except Exception:
        logger.warning("recall degraded to empty snapshot", exc_info=True)
        query_hash = hashlib.sha256(
            f"{inp.bank}|{inp.query}|{sorted(inp.filters.items())}".encode()
        ).hexdigest()
        return RecallSnapshot(query_hash=query_hash, bank=inp.bank,
                              watermark=inp.watermark or "unknown",
                              items=[], degraded=True)


@dataclass
class RetainInput:
    item: RetainItem
    backend: str = "fake"
    base_url: str = "http://localhost:8088"


@activity.defn
async def retain(inp: RetainInput) -> None:
    """Raises on backend failure (unlike recall) so Temporal's own
    RetryPolicy retries in the background, per ARCHITECTURE.md §12."""
    memory = _backend(inp.base_url, inp.backend)
    scrubbed = inp.item.model_copy(update={"text": scrub(inp.item.text)})
    await memory.retain(scrubbed)


@dataclass
class WatermarkInput:
    bank: str
    backend: str = "fake"
    base_url: str = "http://localhost:8088"


@activity.defn
async def capture_watermark(inp: WatermarkInput) -> str:
    memory = _backend(inp.base_url, inp.backend)
    return await memory.current_watermark(inp.bank)


@dataclass
class ReflectInput:
    bank: str
    backend: str = "fake"
    base_url: str = "http://localhost:8088"


@activity.defn
async def reflect(inp: ReflectInput) -> None:
    memory = _backend(inp.base_url, inp.backend)
    await memory.reflect(inp.bank)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_activities.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memory/activities.py tests/test_memory_activities.py
git commit -m "feat(memory): add recall/retain/reflect/watermark activities"
```

---

### Task 6: Register memory activities in the worker

**Files:**
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_worker_registration.py` (extend existing file)

**Interfaces:**
- Consumes: `capture_watermark`, `recall_snapshot`, `reflect`, `retain` (Task 5).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_worker_registration.py`:

```python
def test_worker_module_imports_memory_activities():
    from sdlc import worker
    src = __import__("inspect").getsource(worker)
    for name in ("recall_snapshot", "retain", "capture_watermark", "reflect"):
        assert name in src, f"{name} missing from worker registration"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_worker_registration.py -v`
Expected: FAIL — `recall_snapshot` etc. not found in `worker.py` source.

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/worker.py`, add an import and extend the activities list:

```python
from .memory.activities import (
    capture_watermark, recall_snapshot, reflect, retain,
)
```

(add this import line next to `from .benchmarks.recorder import record_benchmark`)

In the `Worker(...)` call, extend the `activities=[...]` list:

```python
        activities=[
            create_worktree, setup_integration_branch, merge_into_integration,
            run_coding_task, run_test_suite, open_pull_request, deploy,
            evaluate_gate, get_task_diff, record_benchmark, judge_artifact,
            load_case_assets, finalize_benchmark_report,
            recall_snapshot, retain, capture_watermark, reflect,
            *agent_activities,
        ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_worker_registration.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/worker.py tests/test_worker_registration.py
git commit -m "feat(memory): register memory activities on the worker"
```

---

### Task 7: Gated `_recall`/`_retain` helpers + watermark capture in `FeatureWorkflow`

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Test: `tests/test_memory_purity.py`

**Interfaces:**
- Consumes: `RecallInput`, `RetainInput`, `WatermarkInput`, `capture_watermark`, `recall_snapshot`, `retain` (Task 5); `MemoryKind`, `RecallSnapshot`, `RetainItem` (Task 1).
- Produces: `FeatureWorkflow._recall(cfg, bank, query, filters) -> RecallSnapshot`, `FeatureWorkflow._retain(cfg, kind, bank, text, metadata) -> None`, `self._memory_watermark: str | None` set in `__init__` and populated at the top of `run()`.

This test mirrors `tests/test_factory_purity.py`'s AST-based structural check — write it first, matching that file's helper style (reuse its `_load_class`/`_methods`/`_activity_calls_in_method` pattern by importing them).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_purity.py
"""Structural purity check for memory wiring — same approach as
test_factory_purity.py's benchmark guard, applied to recall/retain."""
from __future__ import annotations

import ast

import pytest

from test_factory_purity import (
    FEATURE_PY, _activity_calls_in_method, _load_class, _methods,
)

_MEMORY_ACTIVITIES = {"recall_snapshot", "retain"}
_GATED_HELPERS = {"_recall", "_retain"}


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


def _is_memory_enabled_guard(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
        return False
    src = ast.unparse(test.operand)
    return src in ("cfg.memory.enabled",) and len(stmt.body) == 1 \
        and isinstance(stmt.body[0], ast.Return)


def test_recall_helper_is_guarded(feature_class):
    methods = _methods(feature_class)
    assert "_recall" in methods
    body = methods["_recall"].body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    assert any(_is_memory_enabled_guard(s) for s in body)


def test_retain_helper_is_guarded(feature_class):
    methods = _methods(feature_class)
    assert "_retain" in methods
    body = methods["_retain"].body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    assert any(_is_memory_enabled_guard(s) for s in body)


def test_memory_activities_only_called_through_gated_helpers(feature_class):
    methods = _methods(feature_class)
    for name, fn in methods.items():
        if name in _GATED_HELPERS:
            continue
        calls = _activity_calls_in_method(fn) & _MEMORY_ACTIVITIES
        assert not calls, (
            f"method {name!r} calls memory activity/activities {calls} "
            f"directly — must go through _recall/_retain")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_purity.py -v`
Expected: FAIL — `_recall`/`_retain` not found in `FeatureWorkflow`.

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/workflows/feature.py`, extend the `imports_passed_through()` block:

```python
    from ..memory.activities import (
        RecallInput, RetainInput, WatermarkInput, capture_watermark,
        recall_snapshot, retain,
    )
```

Extend the existing `from ..models import (...)` block to also import `MemoryKind` and `RecallSnapshot` (both alphabetically among the existing names).

Add a `MEM_ACT` config near `RECORD_ACT`:

```python
MEM_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
              retry_policy=RetryPolicy(maximum_attempts=5))
```

In `FeatureWorkflow.__init__`, add:

```python
        self._memory_watermark: str | None = None
```

Add two new methods, placed after `_judge` (before the signals/queries section):

```python
    # ------------------------------ memory -------------------------------

    async def _recall(self, cfg: PipelineConfig, bank: str, query: str,
                      filters: dict[str, str]) -> RecallSnapshot:
        if not cfg.memory.enabled:
            return RecallSnapshot(query_hash="", bank=bank,
                                  watermark="unknown", items=[])
        return await workflow.execute_activity(
            recall_snapshot,
            RecallInput(bank=bank, query=query, filters=filters,
                       watermark=self._memory_watermark,
                       backend=cfg.memory.backend, base_url=cfg.memory.base_url),
            **MEM_ACT)

    async def _retain(self, cfg: PipelineConfig, kind: MemoryKind, bank: str,
                      text: str, metadata: dict[str, str]) -> None:
        if not cfg.memory.enabled:
            return
        try:
            await workflow.execute_activity(
                retain,
                RetainInput(item=RetainItem(kind=kind, bank=bank, text=text,
                                            metadata=metadata),
                           backend=cfg.memory.backend,
                           base_url=cfg.memory.base_url),
                **MEM_ACT)
        except Exception:
            pass
```

At the top of `run()`, right after `cfg = cfg or PipelineConfig()`:

```python
        if cfg.memory.enabled:
            self._memory_watermark = cfg.memory.watermark or (
                await workflow.execute_activity(
                    capture_watermark,
                    WatermarkInput(bank=cfg.memory.project_bank,
                                  backend=cfg.memory.backend,
                                  base_url=cfg.memory.base_url),
                    **MEM_ACT))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_purity.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_memory_purity.py
git commit -m "feat(memory): add gated _recall/_retain helpers + run-start watermark"
```

---

### Task 8: Wire recall into proposer stages, retain into gate feedback + fix-loop gotchas

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Test: `tests/test_memory_wiring.py`

**Interfaces:**
- Consumes: `_recall`/`_retain` (Task 7).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_wiring.py
"""Structural check: every proposer stage recalls before running, retains
a stage summary after, gate decisions retain gate feedback, and the
fix-loop retains a gotcha on failure. AST-based like test_memory_purity.py
— a full time-skipping run would require faking the TemporalAgent
activity surface (see test_factory_purity.py's docstring for why that's
out of scope here)."""
from __future__ import annotations

import ast

import pytest

from test_factory_purity import FEATURE_PY, _load_class, _methods


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


def _calls_self_method(fn: ast.AST, method: str) -> bool:
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == method
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"):
            return True
    return False


def test_run_calls_recall_at_least_three_times_source_count(feature_class):
    methods = _methods(feature_class)
    src = ast.unparse(methods["run"])
    assert src.count("self._recall(") >= 3, (
        "expected recall before clarify/architect/plan at minimum")


def test_run_calls_retain_for_stage_summaries(feature_class):
    methods = _methods(feature_class)
    assert _calls_self_method(methods["run"], "_retain")


def test_gate_helper_retains_gate_feedback(feature_class):
    methods = _methods(feature_class)
    assert "_gate" in methods
    assert _calls_self_method(methods["_gate"], "_retain")


def test_dev_task_retains_gotcha_on_fix_loop(feature_class):
    methods = _methods(feature_class)
    assert "_dev_task" in methods
    assert _calls_self_method(methods["_dev_task"], "_retain")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_wiring.py -v`
Expected: FAIL — `run`, `_gate`, `_dev_task` don't call `self._recall`/`self._retain` yet.

- [ ] **Step 3: Write minimal implementation**

In `_gate`, retain gate feedback on every path. Replace the method body:

```python
    async def _gate(self, name: str, cfg: PipelineConfig,
                    auto_decision: GateDecision | None = None) -> GateDecision:
        """Durable HITL gate with policy-based auto-approval."""
        policy = cfg.gates.get(name, GatePolicy.HARD)

        if policy == GatePolicy.OFF:
            decision = GateDecision(gate=name, outcome=GateOutcome.APPROVE,
                                    decided_by="policy")
        elif policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
            decision = auto_decision
        else:
            self._status = f"awaiting:{name}"
            try:
                await workflow.wait_condition(
                    lambda: name in self._gate_decisions,
                    timeout=timedelta(hours=cfg.gate_timeout_hours),
                )
                decision = self._gate_decisions[name]
            except TimeoutError:
                decision = GateDecision(gate=name, outcome=GateOutcome.REJECT,
                                        decided_by="timeout")
            finally:
                self._status = "running"

        await self._retain(
            cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
            text=f"gate {name}: {decision.outcome.value}"
                f"{' — ' + decision.comments if decision.comments else ''}",
            metadata={"gate": name, "run_id": workflow.info().workflow_id})
        return decision
```

In `_dev_task`, retain a gotcha when QA fails (right after computing `issues`, before the resume/fresh-session branch). Insert after the `issues = "\n- ".join(...)` line:

```python
            await self._retain(
                cfg, MemoryKind.GOTCHA, cfg.memory.project_bank,
                text=f"task {task.id} ({task.title}) attempt {attempt} failed: "
                    f"{issues}",
                metadata={"task_id": task.id,
                         "run_id": workflow.info().workflow_id})
```

In `run()`, before the clarify stage call, recall and prepend to the prompt; after, retain a stage summary. Replace:

```python
        reqs = (await t_clarify.run(idea.model_dump_json())).output
```

with:

```python
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"clarify:{idea.title}",
            filters={"stage": "clarify"})
        reqs = (await t_clarify.run(
            idea.model_dump_json()
            + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
               if snapshot.items else ""))).output
```

and after the clarify benchmark `_record` call, add:

```python
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"clarify: {reqs.summary}",
            metadata={"stage": "clarify", "run_id": workflow.info().workflow_id})
```

Repeat the same recall-before/retain-after shape for architect and plan. Replace:

```python
        arch = (await t_architect.run(
            f"mode={idea.mode.value}\n{reqs.model_dump_json()}")).output
```

with:

```python
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"architect:{idea.title}",
            filters={"stage": "architect"})
        arch = (await t_architect.run(
            f"mode={idea.mode.value}\n{reqs.model_dump_json()}"
            + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
               if snapshot.items else ""))).output
```

and after its `_record` call:

```python
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"architect: {arch.overview}",
            metadata={"stage": "architect", "run_id": workflow.info().workflow_id})
```

Replace:

```python
        plan = (await t_planner.run(arch.model_dump_json())).output
```

with:

```python
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"plan:{idea.title}",
            filters={"stage": "plan"})
        plan = (await t_planner.run(
            arch.model_dump_json()
            + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
               if snapshot.items else ""))).output
```

and after its `_record` call:

```python
        await self._retain(
            cfg, MemoryKind.STAGE_SUMMARY, cfg.memory.project_bank,
            text=f"plan: {len(plan.tasks)} tasks",
            metadata={"stage": "plan", "run_id": workflow.info().workflow_id})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_wiring.py tests/test_memory_purity.py tests/test_factory_purity.py -v`
Expected: PASS (all tests across the three files — re-running `test_factory_purity.py` guards against a benchmark-guard regression from this edit)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_memory_wiring.py
git commit -m "feat(memory): recall before clarify/architect/plan, retain stage summaries + gate feedback + fix-loop gotchas"
```

---

### Task 9: Memoization content-addressed cache

**Files:**
- Create: `src/sdlc/memoization/__init__.py`
- Create: `src/sdlc/memoization/cache.py`
- Create: `src/sdlc/memoization/activities.py`
- Test: `tests/test_memoization_cache.py`

**Interfaces:**
- Produces: `content_key(stage, input_json, prompt_sha, model_id, upstream_recall_ref) -> str` (pure), `cache.get(key) -> str | None`, `cache.put(key, payload_json) -> None` (filesystem I/O), and activities `cache_get(CacheGetInput) -> str | None`, `cache_put(CachePutInput) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memoization_cache.py
import os

import pytest

from sdlc.memoization import cache
from sdlc.memoization.activities import CacheGetInput, CachePutInput, cache_get, cache_put
from sdlc.memoization.cache import content_key


@pytest.fixture(autouse=True)
def _isolated_cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))
    yield


def test_content_key_is_deterministic():
    a = content_key("clarify", '{"title":"x"}', "sha1", "model", "wm1")
    b = content_key("clarify", '{"title":"x"}', "sha1", "model", "wm1")
    assert a == b


def test_content_key_changes_with_any_input():
    base = content_key("clarify", '{"title":"x"}', "sha1", "model", "wm1")
    assert base != content_key("architect", '{"title":"x"}', "sha1", "model", "wm1")
    assert base != content_key("clarify", '{"title":"y"}', "sha1", "model", "wm1")
    assert base != content_key("clarify", '{"title":"x"}', "sha2", "model", "wm1")
    assert base != content_key("clarify", '{"title":"x"}', "sha1", "model2", "wm1")
    assert base != content_key("clarify", '{"title":"x"}', "sha1", "model", "wm2")


def test_cache_miss_returns_none():
    assert cache.get("nonexistent-key") is None


def test_cache_put_then_get_round_trips():
    cache.put("k1", '{"a": 1}')
    assert cache.get("k1") == '{"a": 1}'


def test_cache_get_is_a_temporal_activity():
    assert getattr(cache_get, "__temporal_activity_definition", None) is not None


@pytest.mark.asyncio
async def test_cache_activities_round_trip():
    await cache_put(CachePutInput(key="k2", payload_json='{"b": 2}'))
    result = await cache_get(CacheGetInput(key="k2"))
    assert result == '{"b": 2}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memoization_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.memoization'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/memoization/__init__.py
```
(empty)

```python
# src/sdlc/memoization/cache.py
"""Content-addressed activity cache — the ADR-5 memoization module.
Local filesystem, hash-named files (no new infra): same content in, same
content out, regardless of which run asked."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def _cache_root() -> Path:
    default = os.path.join(tempfile.gettempdir(), "sdlc", "memo_cache")
    return Path(os.environ.get("SDLC_MEMOIZATION_CACHE_ROOT", default))


def content_key(stage: str, input_json: str, prompt_sha: str, model_id: str,
                upstream_recall_ref: str) -> str:
    """Pure function of its arguments — safe to call from workflow code."""
    payload = "|".join([stage, input_json, prompt_sha, model_id,
                        upstream_recall_ref])
    return hashlib.sha256(payload.encode()).hexdigest()


def get(key: str) -> str | None:
    path = _cache_root() / f"{key}.json"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def put(key: str, payload_json: str) -> None:
    root = _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{key}.json").write_text(payload_json, encoding="utf-8")
```

```python
# src/sdlc/memoization/activities.py
"""Temporal activities wrapping the local cache — filesystem I/O must
happen in an activity, never workflow code."""
from __future__ import annotations

from dataclasses import dataclass

from temporalio import activity

from . import cache


@dataclass
class CacheGetInput:
    key: str


@activity.defn
async def cache_get(inp: CacheGetInput) -> str | None:
    return cache.get(inp.key)


@dataclass
class CachePutInput:
    key: str
    payload_json: str


@activity.defn
async def cache_put(inp: CachePutInput) -> None:
    cache.put(inp.key, inp.payload_json)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memoization_cache.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memoization/ tests/test_memoization_cache.py
git commit -m "feat(memoization): add content-addressed cache + cache_get/cache_put activities"
```

---

### Task 10: Wire memoization into clarify/architect/plan/devops stages

**Files:**
- Modify: `src/sdlc/agents/roles.py`
- Modify: `src/sdlc/worker.py`
- Modify: `src/sdlc/workflows/feature.py`
- Test: `tests/test_memoization_wiring.py`

**Interfaces:**
- Consumes: `content_key`, `cache_get`, `cache_put`, `CacheGetInput`, `CachePutInput` (Task 9).
- Produces: `roles.PROMPT_SHAS: dict[str, str]` (stage name -> sha256 of that stage's system prompt, so an edited prompt busts the cache); `FeatureWorkflow._cached_stage(cfg, stage, input_json, model_id, output_type, run_fn) -> tuple[BaseModel, bool]`.

Scoping decision (ADR-5 ROI note): only clarify/architect/plan/devops are cached — they're upstream of the code stage and the ones a dev-loop re-run after a prompt/config edit actually skips. `qa`/`merge_verdict` are cheap, and are re-derived from a freshly generated diff on every task attempt anyway, so caching them has no ROI and is deliberately out of scope.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memoization_wiring.py
from __future__ import annotations

import ast

import pytest

from test_factory_purity import FEATURE_PY, _load_class, _methods
from sdlc.agents.roles import PROMPT_SHAS


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


def test_prompt_shas_cover_the_four_cached_stages():
    for stage in ("clarify", "architect", "plan", "devops"):
        assert stage in PROMPT_SHAS
        assert len(PROMPT_SHAS[stage]) == 64  # sha256 hex digest


def test_cached_stage_helper_exists(feature_class):
    methods = _methods(feature_class)
    assert "_cached_stage" in methods


def test_run_uses_cached_stage_for_clarify_architect_plan(feature_class):
    methods = _methods(feature_class)
    src = ast.unparse(methods["run"])
    assert src.count("self._cached_stage(") >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memoization_wiring.py -v`
Expected: FAIL — `PROMPT_SHAS` doesn't exist, `_cached_stage` doesn't exist.

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/agents/roles.py`, extract each cached stage's `system_prompt` string to a named constant, pass it to `Agent(...)`, and hash the four cached ones. Replace the `clarify_agent = Agent(...)` block through `devops_agent = Agent(...)` with (system prompt text unchanged, just pulled into constants):

```python
CLARIFY_PROMPT = (
    "You are a requirements analyst. Given a feature idea, extract "
    "functional and non-functional requirements, define what is out of "
    "scope, and list ONLY the open questions whose answers materially "
    "change the design (Definition-of-Ready style). For each question "
    "include a suggested answer so the human can approve or override."
)
ARCHITECT_PROMPT = (
    "You are a software architect. Produce an architecture spec with "
    "explicit, numbered decisions and rationale. In BROWNFIELD mode, "
    "ground every decision in the provided codebase map and list the "
    "affected modules as a delta (added / modified / removed). In "
    "GREENFIELD mode, decide stack, project structure and key ADRs. "
    "Prefer boring technology; flag risks explicitly."
)
PLAN_PROMPT = (
    "You are a tech lead. Decompose the approved architecture into "
    "small, independently mergeable dev tasks with acceptance criteria "
    "and dependency edges. For EVERY task, compile its acceptance "
    "criteria into a ValidationContract: concrete, checkable assertions "
    "and test commands, written before any code exists — correctness "
    "will be judged against this contract, not the implementation. "
    "Declare 'overlaps': modules any two tasks both touch (overlapping "
    "tasks will be serialized). Each task must be completable by a "
    "coding agent in one focused session. Include dedicated 'test' "
    "tasks and 'devops' tasks (CI, infra, deploy config) where needed."
)
QA_PROMPT = (
    "You are a clean-context QA validator. You receive ONLY: the task's "
    "frozen ValidationContract, test output, and the materialized diff. "
    "You never see, and must never request, the implementer's summary "
    "or reasoning. Judge whether the diff satisfies each contract "
    "assertion — not whether tests merely pass. List concrete issues "
    "per unmet assertion."
)
MERGE_VERDICT_PROMPT = (
    "You are an ADVISORY release reviewer, consulted only after the "
    "deterministic quality gate has already passed. Given the QA report, "
    "reviewer summary and diff stats, give a confidence-scored opinion on "
    "whether the merge should proceed. You cannot block a merge on your "
    "own and you cannot approve one the deterministic gate failed; you "
    "only advise. Be conservative and list concrete concerns."
)
DEVOPS_PROMPT = (
    "You are a DevOps engineer. Given the architecture and repo state, "
    "produce the pipeline/infra tasks needed to ship this feature: "
    "CI updates, migrations, feature flags, deploy and rollback steps."
)

clarify_agent = Agent(
    MODEL, name="clarify_agent", output_type=ClarifiedRequirements,
    system_prompt=CLARIFY_PROMPT,
)

architect_agent = Agent(
    MODEL, name="architect_agent", output_type=ArchitectureSpec,
    system_prompt=ARCHITECT_PROMPT,
)

planner_agent = Agent(
    MODEL, name="planner_agent", output_type=ImplementationPlan,
    model_settings=PLAN_MODEL_SETTINGS, system_prompt=PLAN_PROMPT,
)

qa_analyst_agent = Agent(
    MODEL, name="qa_analyst_agent", output_type=QAReport,
    system_prompt=QA_PROMPT,
)

merge_verdict_agent = Agent(
    MODEL, name="merge_verdict_agent", output_type=MergeVerdict,
    system_prompt=MERGE_VERDICT_PROMPT,
)

devops_agent = Agent(
    MODEL, name="devops_agent", output_type=ImplementationPlan,
    model_settings=PLAN_MODEL_SETTINGS, system_prompt=DEVOPS_PROMPT,
)

PROMPT_SHAS: dict[str, str] = {
    "clarify": hashlib.sha256(CLARIFY_PROMPT.encode()).hexdigest(),
    "architect": hashlib.sha256(ARCHITECT_PROMPT.encode()).hexdigest(),
    "plan": hashlib.sha256(PLAN_PROMPT.encode()).hexdigest(),
    "devops": hashlib.sha256(DEVOPS_PROMPT.encode()).hexdigest(),
}
```

Add `import hashlib` to the top of `roles.py`.

In `src/sdlc/worker.py`, register the memoization activities:

```python
from .memoization.activities import cache_get, cache_put
```

and add `cache_get, cache_put,` to the `activities=[...]` list (next to the memory activities added in Task 6).

In `src/sdlc/workflows/feature.py`, extend the `imports_passed_through()` block:

```python
    from ..agents.roles import PROMPT_SHAS
    from ..memoization.activities import (
        CacheGetInput, CachePutInput, cache_get, cache_put,
    )
    from ..memoization.cache import content_key
```

Add `_cached_stage` after `_retain` in the memory section:

```python
    async def _cached_stage(self, cfg: PipelineConfig, stage: str,
                            input_json: str, model_id: str,
                            output_type: type, run_fn) -> tuple[object, bool]:
        """Skips `run_fn()` (a no-arg async callable invoking the proposer
        agent) when an identical (stage, input, prompt, model,
        upstream-recall-watermark) combination was already computed — the
        ADR-5 dev-loop cache. Returns (output, was_cache_hit)."""
        if not cfg.memoization_enabled:
            return await run_fn(), False
        key = content_key(stage, input_json, PROMPT_SHAS[stage], model_id,
                          self._memory_watermark or "none")
        cached = await workflow.execute_activity(
            cache_get, CacheGetInput(key=key), **MEM_ACT)
        if cached is not None:
            return output_type.model_validate_json(cached), True
        result = await run_fn()
        await workflow.execute_activity(
            cache_put,
            CachePutInput(key=key, payload_json=result.model_dump_json()),
            **MEM_ACT)
        return result, False
```

Wire it into `run()` — replace the clarify call built in Task 8 with:

```python
        reqs, _ = await self._cached_stage(
            cfg, "clarify", idea.model_dump_json(), MODEL,
            ClarifiedRequirements,
            lambda: self._run_clarify(idea, cfg, snapshot))
```

This requires extracting the actual agent call into a small helper (needed because `_cached_stage`'s `run_fn` must be a no-arg callable, but the clarify call needs `snapshot`/`idea`/`cfg` in scope — a closure over locals already in scope is enough, no new method needed). Simplify instead of adding `_run_clarify`: since `snapshot`, `idea` are already in scope at the call site, define the closure inline:

```python
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"clarify:{idea.title}",
            filters={"stage": "clarify"})

        async def _run_clarify():
            return (await t_clarify.run(
                idea.model_dump_json()
                + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                   if snapshot.items else ""))).output

        reqs, _ = await self._cached_stage(
            cfg, "clarify", idea.model_dump_json(), MODEL,
            ClarifiedRequirements, _run_clarify)
```

Apply the same closure pattern to architect and plan (`_run_architect`/`_run_plan`, output types `ArchitectureSpec`/`ImplementationPlan`, stage names `"architect"`/`"plan"`, model `MODEL`):

```python
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"architect:{idea.title}",
            filters={"stage": "architect"})

        async def _run_architect():
            return (await t_architect.run(
                f"mode={idea.mode.value}\n{reqs.model_dump_json()}"
                + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                   if snapshot.items else ""))).output

        arch, _ = await self._cached_stage(
            cfg, "architect", reqs.model_dump_json(), MODEL,
            ArchitectureSpec, _run_architect)
```

```python
        snapshot = await self._recall(
            cfg, cfg.memory.project_bank, query=f"plan:{idea.title}",
            filters={"stage": "plan"})

        async def _run_plan():
            return (await t_planner.run(
                arch.model_dump_json()
                + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                   if snapshot.items else ""))).output

        plan, _ = await self._cached_stage(
            cfg, "plan", arch.model_dump_json(), MODEL,
            ImplementationPlan, _run_plan)
```

`devops_agent` is not currently invoked anywhere in `feature.py` (it's defined in `roles.py` but unused by the workflow today) — leave its wiring for whichever future task actually calls it; `PROMPT_SHAS["devops"]` exists now so that task doesn't need to touch `roles.py` again.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_memoization_wiring.py tests/test_memory_wiring.py tests/test_memory_purity.py tests/test_factory_purity.py -v`
Expected: PASS across all four files

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/agents/roles.py src/sdlc/worker.py src/sdlc/workflows/feature.py tests/test_memoization_wiring.py
git commit -m "feat(memoization): cache clarify/architect/plan stage outputs keyed on prompt+input+model+watermark"
```

---

### Task 11: Real Hindsight HTTP client

**Files:**
- Create: `src/sdlc/memory/hindsight_client.py`
- Modify: `pyproject.toml` (add `httpx` dependency)
- Test: `tests/test_hindsight_client.py`

**Interfaces:**
- Consumes: `Memory` (Task 2), `RecallSnapshot`/`RetainItem` (Task 1).
- Produces: `HindsightMemory(base_url: str, timeout_s: float = 10.0)` implementing `Memory` over HTTP.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hindsight_client.py
import httpx
import pytest

from sdlc.memory.hindsight_client import HindsightMemory
from sdlc.models import MemoryKind, RetainItem


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_recall_posts_query_and_parses_snapshot():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/banks/project:x/recall"
        return httpx.Response(200, json={
            "query_hash": "abc123", "watermark": "5",
            "items": ["memory item one"],
        })

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    snap = await client.recall("project:x", "q", {}, None)
    assert snap.query_hash == "abc123"
    assert snap.watermark == "5"
    assert snap.items == ["memory item one"]


@pytest.mark.asyncio
async def test_retain_posts_kind_text_metadata():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={})

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    await client.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:x",
                                   text="t", metadata={}))
    assert seen["path"] == "/v1/banks/project:x/retain"


@pytest.mark.asyncio
async def test_current_watermark_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/banks/project:x/watermark"
        return httpx.Response(200, json={"watermark": "9"})

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    wm = await client.current_watermark("project:x")
    assert wm == "9"


@pytest.mark.asyncio
async def test_recall_raises_on_http_error_so_the_activity_can_degrade():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await client.recall("project:x", "q", {}, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hindsight_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.memory.hindsight_client'` (and `httpx` not installed yet)

- [ ] **Step 3: Write minimal implementation**

Add `"httpx>=0.27",` to `dependencies` in `pyproject.toml`, then run `pip install -e .` (or `pip install httpx>=0.27` directly in the dev environment).

```python
# src/sdlc/memory/hindsight_client.py
"""Real Hindsight (vectorize-io) HTTP client — the integration seam noted
in ARCHITECTURE.md §6/§8. Swap this module or `base_url` without touching
workflow code; callers only ever see the Memory protocol."""
from __future__ import annotations

import httpx

from ..models import RecallSnapshot, RetainItem
from .protocol import Memory


class HindsightMemory(Memory):
    def __init__(self, base_url: str, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url,
                                         timeout=timeout_s)

    async def current_watermark(self, bank: str) -> str:
        resp = await self._client.get(f"/v1/banks/{bank}/watermark")
        resp.raise_for_status()
        return resp.json()["watermark"]

    async def retain(self, item: RetainItem) -> None:
        resp = await self._client.post(
            f"/v1/banks/{item.bank}/retain",
            json={"kind": item.kind.value, "text": item.text,
                 "metadata": item.metadata},
        )
        resp.raise_for_status()

    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot:
        resp = await self._client.post(
            f"/v1/banks/{bank}/recall",
            json={"query": query, "filters": filters,
                 "watermark": watermark},
        )
        resp.raise_for_status()
        payload = resp.json()
        return RecallSnapshot(
            query_hash=payload["query_hash"], bank=bank,
            watermark=payload["watermark"], items=payload.get("items", []),
        )

    async def reflect(self, bank: str) -> None:
        resp = await self._client.post(f"/v1/banks/{bank}/reflect")
        resp.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hindsight_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all tests pass, including every test added in Tasks 1–11.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/memory/hindsight_client.py pyproject.toml tests/test_hindsight_client.py
git commit -m "feat(memory): add real Hindsight HTTP client (httpx)"
```

---

## Deliberately out of scope (flagged, not silently dropped)

- **`reflect` scheduling** — the nightly consolidation job itself (a cron/Temporal-schedule trigger calling the `reflect` activity per bank) is not wired up; only the activity exists. Needs a decision on whether it's a `temporalio` Schedule or an external cron hitting the CLI.
- **`config/memory.yaml` loader** — no YAML config loading exists anywhere in this codebase yet (`PipelineConfig()` is constructed directly); `MemoryConfig` fields are set programmatically for now, consistent with everything else in `PipelineConfig`.
- **Devops stage wiring into `FeatureWorkflow.run`** — `devops_agent`/`t_devops` are defined but never called from the workflow today; that's a pre-existing gap, not something this plan should paper over. `PROMPT_SHAS["devops"]` is ready for whenever that wiring lands.
- **Real Hindsight REST contract validation** — Task 11's client assumes a plausible REST shape (`POST /v1/banks/{bank}/recall|retain|reflect`, `GET /v1/banks/{bank}/watermark`). Confirm against the actual vectorize-io Hindsight API docs before pointing `backend="hindsight"` at a real instance; adjust `hindsight_client.py` only (no other file should need to change, since everything else depends on the `Memory` protocol).
