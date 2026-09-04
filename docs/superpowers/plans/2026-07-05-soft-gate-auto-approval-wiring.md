# Soft-Gate Confidence-Threshold Auto-Approval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `GatePolicy.SOFT` actually auto-approve the architecture, plan, and merge gates when a proposer's self-scored confidence clears a configurable per-gate threshold — closing the gap where `SOFT` today behaves identically to `HARD` (see `docs/feature-coverage-audit-2026-07-05.md` §2, FR-301).

**Architecture:** A new `GateConfig{policy, threshold}` replaces the bare `GatePolicy` values in `PipelineConfig.gates` (with backward-compatible coercion). A new pure helper `_auto_decision_for(name, cfg, confidence)` in `feature.py` decides whether a `SOFT` gate's confidence clears its threshold; it's called from `_revisable_stage` (architecture/plan) and the merge stage, feeding into the existing (currently dead) `auto_decision` parameter of `_gate()`. Confidence is self-scored by the LLM as a plain field on `ArchitectureSpec`/`ImplementationPlan` (no extra model call); `MergeVerdict.confidence` already exists and starts being read.

**Tech Stack:** Python ≥3.11, Pydantic v2, `temporalio`, `pydantic-ai-slim`, `pytest`, src-layout package (`pip install -e .[dev]`).

## Global Constraints

- **Spec is the source of truth:** `docs/superpowers/specs/2026-07-05-soft-gate-auto-approval-design.md`. Every decision below cites its section.
- **Scope:** architecture, plan, and merge gates only. The **clarify** gate is explicitly out of scope (design §2) — it uses a separate `answer_question` signal-wait, not `_gate()`.
- **Backward compatibility:** `PipelineConfig(gates={"architecture": GatePolicy.HARD})` (today's shape, used in `tests/test_gate_revision_loop.py:18` and elsewhere via `PipelineConfig()` defaults) must keep working unchanged after `gates` becomes `dict[str, GateConfig]`.
- **No silent auto-approval on missing data:** `confidence=None` (omitted by the LLM, or a legacy memoization-cache hit predating this field) must always fall through to the human wait, never auto-approve.
- **Established patterns:** activity inputs/outputs are `@dataclass`es (`activities.py`); pipeline contracts are Pydantic `BaseModel`s (`models.py`); pure logic lives outside the workflow class where practical. `_merge_evidence_all_green` (`feature.py:91-98`) is the precedent for a module-level pure function that's unit-tested by direct import, without a live Temporal server — `_auto_decision_for` follows the same pattern.
- **Workflow determinism:** nothing under `workflows/` may import `subprocess`, `httpx`, the memory client, or the harness package (enforced by `tests/test_factory_purity.py`, `tests/test_memory_purity.py` AST checks). This plan adds no such imports.
- TDD (failing test first), DRY, YAGNI, frequent commits — matches this repo's existing `test_merge_gate_wiring.py` / `test_gate_revision_loop.py` convention: AST/pure-function test → minimal implementation → runtime/behavior test → commit.

---

## File Structure

| File | Responsibility | This plan |
|---|---|---|
| `src/sdlc/models.py` | `GateConfig` model; `confidence` fields on `ArchitectureSpec`/`ImplementationPlan`; `PipelineConfig.gates` type change + coercion | Modify (Task 1) |
| `src/sdlc/workflows/feature.py` | `_auto_decision_for` helper; `_gate()`'s `cfg.gates.get(...)` read; `_revisable_stage` wiring; merge-stage soft-path wiring | Modify (Tasks 2–4) |
| `tests/test_gate_config.py` | `GateConfig` coercion + threshold bounds; confidence field defaults | Create (Task 1) |
| `tests/test_soft_gate_auto_approval.py` | `_auto_decision_for` pure-function behavior; AST wiring checks for `_revisable_stage` and the merge stage | Create (Tasks 2–4) |

---

## Task 1: `GateConfig` model, confidence fields, backward-compatible `PipelineConfig.gates`

**Files:**
- Modify: `src/sdlc/models.py`
- Create: `tests/test_gate_config.py`

**Interfaces:**
- Produces: `GateConfig{policy: GatePolicy, threshold: float}` (`models.py`); `ArchitectureSpec.confidence: float | None`; `ImplementationPlan.confidence: float | None`; `PipelineConfig.gates: dict[str, GateConfig]`.
- Consumes: existing `GatePolicy` enum (`models.py:27-30`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gate_config.py`:

```python
import pytest
from pydantic import ValidationError

from sdlc.models import (
    ArchitectureSpec,
    GateConfig,
    GatePolicy,
    ImplementationPlan,
    PipelineConfig,
)


def test_gate_config_defaults():
    gc = GateConfig()
    assert gc.policy == GatePolicy.HARD
    assert gc.threshold == 0.8


def test_gate_config_threshold_bounds():
    with pytest.raises(ValidationError):
        GateConfig(threshold=1.5)
    with pytest.raises(ValidationError):
        GateConfig(threshold=-0.1)


def test_pipeline_config_coerces_bare_gate_policy():
    """Backward compatibility: existing call sites and tests construct
    gates={"architecture": GatePolicy.HARD} — this must keep working
    after `gates` becomes dict[str, GateConfig]."""
    cfg = PipelineConfig(gates={"architecture": GatePolicy.HARD})
    assert isinstance(cfg.gates["architecture"], GateConfig)
    assert cfg.gates["architecture"].policy == GatePolicy.HARD
    assert cfg.gates["architecture"].threshold == 0.8  # default


def test_pipeline_config_default_gates_are_gate_config():
    cfg = PipelineConfig()
    assert isinstance(cfg.gates["plan"], GateConfig)
    assert cfg.gates["plan"].policy == GatePolicy.SOFT


def test_architecture_spec_confidence_defaults_to_none():
    spec = ArchitectureSpec(overview="x", decisions=[])
    assert spec.confidence is None


def test_implementation_plan_confidence_defaults_to_none():
    plan = ImplementationPlan(tasks=[])
    assert plan.confidence is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_gate_config.py -v`
Expected: FAIL — `GateConfig` doesn't exist (`ImportError`); `ArchitectureSpec`/`ImplementationPlan` have no `confidence` field.

- [ ] **Step 3: Add `GateConfig` and the confidence fields**

In `src/sdlc/models.py`, add after the `GateOutcome` enum (after line 36):

```python
class GateConfig(BaseModel):
    """Per-gate policy + the confidence bar a SOFT gate must clear to
    auto-approve (FR-301). threshold is read only when policy == SOFT."""

    policy: GatePolicy = GatePolicy.HARD
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)

    @classmethod
    def _coerce(cls, v: "GateConfig | GatePolicy | str") -> "GateConfig":
        if isinstance(v, GateConfig):
            return v
        return cls(policy=GatePolicy(v))
```

Add `confidence: float | None = None` to `ArchitectureSpec` (after `spec_ref`, line 86) and to `ImplementationPlan` (after `tasks`, line 126):

```python
class ArchitectureSpec(BaseModel):
    overview: str
    decisions: list[ArchitectureDecision]
    affected_modules: list[str] = Field(default_factory=list)  # brownfield
    new_components: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    spec_ref: ArtifactRef | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301


class ImplementationPlan(BaseModel):
    tasks: list[DevTask]
    plan_ref: ArtifactRef | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301
```

- [ ] **Step 4: Make `PipelineConfig.gates` a `dict[str, GateConfig]` with coercion**

In `src/sdlc/models.py`, change the `PipelineConfig.gates` field (lines 286-292):

```python
class PipelineConfig(BaseModel):
    execution_mode: ExecutionMode = ExecutionMode.SERIAL
    max_session_resumes: int = 3
    gates: dict[str, GateConfig] = Field(
        default_factory=lambda: {
            "clarify": GateConfig(policy=GatePolicy.HARD),
            "architecture": GateConfig(policy=GatePolicy.HARD),
            "plan": GateConfig(policy=GatePolicy.SOFT),
            "merge": GateConfig(policy=GatePolicy.HARD),
            "deploy": GateConfig(policy=GatePolicy.HARD),
        }
    )
```

Add a `field_validator` on `gates` (below the field, still inside `PipelineConfig`) that coerces bare `GatePolicy`/`str` values per-key, so `gates={"architecture": GatePolicy.HARD}` and mixed dicts both work:

```python
    @field_validator("gates", mode="before")
    @classmethod
    def _coerce_gates(cls, v):
        if not isinstance(v, dict):
            return v
        return {k: GateConfig._coerce(gv) for k, gv in v.items()}
```

Add `field_validator` to the existing `from pydantic import BaseModel, Field` import line (top of file):

```python
from pydantic import BaseModel, Field, field_validator
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_gate_config.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Run the full suite to check for regressions**

Run: `pytest -q`
Expected: PASS. (`tests/test_gate_revision_loop.py::test_pipeline_config_has_max_gate_rounds` and every other `PipelineConfig()`-default-constructing test are unaffected since defaults now build `GateConfig` instances transparently.)

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/models.py tests/test_gate_config.py
git commit -m "feat(gates): add GateConfig{policy,threshold} + proposer confidence fields (FR-301)"
```

---

## Task 2: `_auto_decision_for` pure helper + update `_gate()` to read `GateConfig`

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Create: `tests/test_soft_gate_auto_approval.py`

**Interfaces:**
- Consumes: `GateConfig`, `GatePolicy`, `GateDecision`, `GateOutcome` (already imported from `..models` at `feature.py:47-52` — add `GateConfig` to that import list).
- Produces: `_auto_decision_for(name: str, cfg: PipelineConfig, confidence: float | None) -> GateDecision | None`, a module-level function in `feature.py` (same pattern as `_merge_evidence_all_green`, `feature.py:91-98`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_soft_gate_auto_approval.py`:

```python
from sdlc.models import GateConfig, GateOutcome, GatePolicy, PipelineConfig
from sdlc.workflows.feature import _auto_decision_for


def _cfg(policy: GatePolicy, threshold: float = 0.8) -> PipelineConfig:
    return PipelineConfig(gates={"architecture": GateConfig(policy=policy, threshold=threshold)})


def test_soft_high_confidence_auto_approves():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9)
    assert decision is not None
    assert decision.outcome is GateOutcome.APPROVE
    assert decision.decided_by == "policy"


def test_soft_confidence_at_threshold_auto_approves():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT, 0.8), 0.8)
    assert decision is not None


def test_soft_low_confidence_falls_through():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.5)
    assert decision is None


def test_soft_none_confidence_falls_through():
    """Missing/legacy confidence must never auto-approve."""
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT), None)
    assert decision is None


def test_hard_policy_ignores_confidence():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.HARD), 0.99)
    assert decision is None


def test_off_policy_ignores_confidence():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.OFF), 0.0)
    assert decision is None


def test_unconfigured_gate_defaults_to_hard_and_falls_through():
    decision = _auto_decision_for("deploy", PipelineConfig(gates={}), 0.99)
    assert decision is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_soft_gate_auto_approval.py -v`
Expected: FAIL — `_auto_decision_for` not defined in `sdlc.workflows.feature`.

- [ ] **Step 3: Add `_auto_decision_for` and update `_gate()`**

In `src/sdlc/workflows/feature.py`, add `GateConfig` to the `..models` import (line 47-52 becomes):

```python
from ..models import (
    ArchitectureSpec,
    ClarifiedRequirements,
    DevTask,
    ExecutionMode,
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    HandoffSummary,
    IdeaBrief,
    ImplementationPlan,
    MemoryKind,
    MergeVerdict,
    PipelineConfig,
    RecallSnapshot,
    RetainItem,
    RoleConfig,
    TaskResult,
    gate_key,
)
```

Add the helper as a module-level function, directly below `_merge_evidence_all_green` (after line 98, before `@workflow.defn`):

```python
def _auto_decision_for(
    name: str, cfg: PipelineConfig, confidence: float | None
) -> GateDecision | None:
    """FR-301: SOFT + confidence >= threshold -> an APPROVE decision _gate()
    can short-circuit on. None confidence (missing/legacy artifact) or below
    threshold -> None, falling through to the human wait -- never a silent
    auto-approve on absent data (same defensive stance as
    HarnessRunResult.near_context_ceiling())."""
    gate_cfg = cfg.gates.get(name, GateConfig())
    if gate_cfg.policy != GatePolicy.SOFT or confidence is None:
        return None
    if confidence < gate_cfg.threshold:
        return None
    return GateDecision(
        gate=name,
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by="policy",
        comments=f"auto-approved: confidence={confidence:.2f} "
        f">= threshold={gate_cfg.threshold:.2f}",
    )
```

Update `_gate()`'s policy read (`feature.py:263`), replacing:

```python
        policy = cfg.gates.get(name, GatePolicy.HARD)
```

with:

```python
        policy = cfg.gates.get(name, GateConfig()).policy
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_soft_gate_auto_approval.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `pytest -q`
Expected: PASS. `_gate()`'s behavior is unchanged for every existing caller — none pass `auto_decision` yet, so this step only changes *how* `policy` is read, not what gates do.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_soft_gate_auto_approval.py
git commit -m "feat(gates): add _auto_decision_for helper; read GateConfig in _gate()"
```

---

## Task 3: Wire `_revisable_stage` (architecture, plan) to auto-approve on confidence

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Modify: `tests/test_soft_gate_auto_approval.py`

**Interfaces:**
- Consumes: `_auto_decision_for` (Task 2).
- Produces: `_revisable_stage` now passes `auto_decision=` into its `_gate()` call for rounds `1..max_gate_rounds` (the final, exhausted-rounds gate call intentionally still omits it, unchanged from today — an exhausted revision loop always waits for a real human decision).

- [ ] **Step 1: Write the failing AST test**

Append to `tests/test_soft_gate_auto_approval.py`:

```python
import pathlib

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_revisable_stage_passes_auto_decision():
    src = SRC.read_text(encoding="utf-8")
    assert "_auto_decision_for(" in src, (
        "_revisable_stage must call _auto_decision_for to compute an "
        "auto_decision from the artifact's confidence (FR-301)"
    )
    # The auto_decision must actually reach _gate(), not just be computed.
    assert "auto_decision=auto" in src, (
        "_revisable_stage must pass auto_decision=auto into self._gate()"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_soft_gate_auto_approval.py::test_revisable_stage_passes_auto_decision -v`
Expected: FAIL — neither string present yet.

- [ ] **Step 3: Wire `_revisable_stage`**

In `src/sdlc/workflows/feature.py`, replace the body of `_revisable_stage` (the loop's two inner lines, currently):

```python
        for round in range(1, cfg.max_gate_rounds + 1):
            artifact = await run_fn(guidance)
            decision = await self._gate(name, cfg, round=round)
            if decision.outcome is not GateOutcome.REVISE:
                return artifact, decision
            guidance = decision.guidance or decision.comments
```

with:

```python
for round in range(1, cfg.max_gate_rounds + 1):
    artifact = await run_fn(guidance)
    auto = _auto_decision_for(name, cfg, getattr(artifact, "confidence", None))
    decision = await self._gate(name, cfg, auto_decision=auto, round=round)
    if decision.outcome is not GateOutcome.REVISE:
        return artifact, decision
    guidance = decision.guidance or decision.comments
```

(`getattr(artifact, "confidence", None)` keeps `_revisable_stage` generic across artifact types without a shared base class — it's already duck-typed, `run_fn` returns `object`. The final exhausted-round `_gate()` call below the loop is deliberately left unchanged: it always waits for a human, regardless of policy, matching the existing "one final gate decides accept-anyway vs abandon" comment.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_soft_gate_auto_approval.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS. `ArchitectureSpec`/`ImplementationPlan` instances built anywhere without `confidence` set default to `None` → `_auto_decision_for` returns `None` → identical behavior to before this task for every existing test.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_soft_gate_auto_approval.py
git commit -m "feat(gates): wire confidence-threshold auto-approval into architecture/plan gates (FR-301)"
```

---

## Task 4: Unify the merge gate's soft path onto the same threshold

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Modify: `tests/test_soft_gate_auto_approval.py`

**Interfaces:**
- Consumes: `_auto_decision_for` (Task 2), `MergeVerdict.confidence` (already exists, `models.py:239`).
- Produces: the merge stage's soft-path branch now calls `_auto_decision_for("merge", cfg, ...)` instead of checking only `verdict.approve`.

- [ ] **Step 1: Write the failing AST test**

Append to `tests/test_soft_gate_auto_approval.py`:

```python
def test_merge_soft_path_uses_auto_decision_for():
    src = SRC.read_text(encoding="utf-8")
    # Find the merge stage's soft-path block (after the MergeVerdict call)
    # and confirm it consults _auto_decision_for rather than a bare
    # verdict.approve check alone.
    idx = src.find("t_merge_verdict.run(")
    assert idx != -1, "merge stage no longer calls t_merge_verdict"
    tail = src[idx : idx + 700]
    assert "_auto_decision_for(" in tail, (
        "merge gate's soft path must route through _auto_decision_for so "
        "verdict.confidence is checked against cfg.gates['merge'].threshold, "
        "not just verdict.approve"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_soft_gate_auto_approval.py::test_merge_soft_path_uses_auto_decision_for -v`
Expected: FAIL — `_auto_decision_for` not present in that window (only `verdict.approve` is checked).

- [ ] **Step 3: Wire the merge stage**

In `src/sdlc/workflows/feature.py`, replace the merge stage's soft-path block (currently):

```python
if cfg.gates.get("merge", GatePolicy.HARD) == GatePolicy.SOFT:
    verdict: MergeVerdict = (
        await t_merge_verdict.run(
            "Advisory only — the deterministic gate already passed. "
            f"Task results: {[r.model_dump() for r in done.values()]}"
        )
    ).output
    if not verdict.approve:
        # Soft policy + negative verdict = escalate to human.
        gate = await self._gate("merge", cfg)
        if not gate.approved:
            return "rejected:merge:soft-verdict"
```

with:

```python
if cfg.gates.get("merge", GateConfig()).policy == GatePolicy.SOFT:
    verdict: MergeVerdict = (
        await t_merge_verdict.run(
            "Advisory only — the deterministic gate already passed. "
            f"Task results: {[r.model_dump() for r in done.values()]}"
        )
    ).output
    auto = _auto_decision_for("merge", cfg, verdict.confidence if verdict.approve else None)
    if auto is None:
        # Soft policy + (negative verdict OR confidence below
        # threshold) = escalate to human.
        gate = await self._gate("merge", cfg)
        if not gate.approved:
            return "rejected:merge:soft-verdict"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_soft_gate_auto_approval.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS. When `verdict.approve` is `True` and confidence is high enough, behavior is unchanged from before (falls through without waiting); the only behavior change is a *negative* one previously missed — a `True`-but-low-confidence verdict now correctly escalates instead of silently proceeding.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_soft_gate_auto_approval.py
git commit -m "feat(gates): unify merge soft-path onto the confidence-threshold check (FR-301)"
```

---

## Task 5: Full-suite verification pass

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -q`
Expected: PASS, all tests (the pre-existing suite plus the ~21 new tests added across Tasks 1–4).

- [ ] **Step 2: Confirm no purity/determinism regressions**

Run: `pytest tests/test_factory_purity.py tests/test_memory_purity.py -v`
Expected: PASS — this plan adds no `subprocess`/`httpx`/memory-client/harness imports to `workflows/feature.py`.

- [ ] **Step 3: Spot-check the audit doc's flagged gap is closed**

Run:
```bash
python -c "
from sdlc.models import PipelineConfig, GatePolicy
from sdlc.workflows.feature import _auto_decision_for
cfg = PipelineConfig()
print('plan gate policy:', cfg.gates['plan'].policy, 'threshold:', cfg.gates['plan'].threshold)
print('auto-approve at confidence=0.95:', _auto_decision_for('plan', cfg, 0.95))
print('auto-approve at confidence=0.5:', _auto_decision_for('plan', cfg, 0.5))
"
```
Expected output: policy `GatePolicy.SOFT`, threshold `0.8`; the first call prints a `GateDecision` with `outcome=<GateOutcome.APPROVE...>`; the second prints `None`.

- [ ] **Step 4: Update the audit doc's FR-301 line**

In `docs/feature-coverage-audit-2026-07-05.md`, under "Human-in-the-loop (FR-300)", change the FR-301 row's status from `⚠️ Partial — **soft gates don't actually auto-approve**` to reference this fix, e.g. append a line: `**Update 2026-07-05:** wired via docs/superpowers/plans/2026-07-05-soft-gate-auto-approval-wiring.md — architecture/plan/merge soft gates now auto-approve on confidence >= threshold.` Leave the "confidence threshold" numeric-field description and the recommendation section otherwise intact (the deterministic-check-for-architecture/plan gap, priority recommendation #2 review stage, and #3 agents.yaml registry are all still open).

- [ ] **Step 5: Commit**

```bash
git add docs/feature-coverage-audit-2026-07-05.md
git commit -m "docs: mark FR-301 soft-gate auto-approval gap as closed"
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-07-05-soft-gate-auto-approval-design.md`):
- Decision 1 (self-scored confidence field) → Task 1. ✅
- Decision 2 (`GateConfig` + backward-compat coercion) → Task 1. ✅
- Decision 3 (confidence-only for architecture/plan, documented gap) → Task 3 wires it; the design's §8 "known limitations" note is already in the committed spec, not re-litigated here. ✅
- Decision 4 (merge unified onto the same threshold) → Task 4. ✅
- §6 error handling (missing confidence never auto-approves; cache compatibility; out-of-range threshold; `GatePolicy` backward compat) → covered by `test_soft_gate_auto_approval.py`'s `None`-confidence test, `test_gate_config.py`'s bounds + coercion tests, and Task 1 Step 3's `confidence: float | None = None` default (safe for old cache payloads). ✅
- §7 testing list (pure-fn tests, `GateConfig` coercion test, AST tests, runtime-style test) → all present across Tasks 1–4. ✅

**2. Placeholder scan:** every step has literal code or an exact command; no "TBD"/"add validation"/"similar to Task N" language.

**3. Type consistency:** `GateConfig`, `_auto_decision_for`, `GateDecision`, `GateOutcome.APPROVE`, `cfg.gates[name].threshold`/`.policy` are used identically across Tasks 1–4 and match the names defined in Task 1/2. `_revisable_stage`'s `getattr(artifact, "confidence", None)` matches the `confidence: float | None` fields added to `ArchitectureSpec`/`ImplementationPlan` in Task 1. The merge stage's `verdict.confidence` matches the pre-existing `MergeVerdict.confidence: float` field (not newly added — already in `models.py:239`).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-05-soft-gate-auto-approval-wiring.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
