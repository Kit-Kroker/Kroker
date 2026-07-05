# Design — Soft-Gate Confidence-Threshold Auto-Approval

| | |
|---|---|
| Status | Draft v1.0 |
| Date | 2026-07-05 |
| Related | `PRD.md` FR-301, OQ-1 (resolved by this design); `ARCHITECTURE.md` §5, ADR-4; `docs/feature-coverage-audit-2026-07-05.md` §2 (FR-301 gap) |

---

## 1. Problem

`docs/feature-coverage-audit-2026-07-05.md` found that `PipelineConfig.gates["plan"]` defaults to `GatePolicy.SOFT` (`models.py:289`), but `_gate()` in `src/sdlc/workflows/feature.py` is never called with an `auto_decision` argument at the architecture or plan call sites. The `SOFT` branch (`feature.py:270`) —

```python
elif policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
```

— is therefore dead code: `SOFT` behaves identically to `HARD` today. This silently breaks the PRD's stated contract ("soft = Clarifier/Architect/Planner auto-assumes above confidence threshold") and blocks P3's exit criterion (SC-6, confidence-gated soft gates measurable).

Separately, the merge gate's own soft path (`feature.py:735-744`) already consults `MergeVerdict.approve` but ignores `MergeVerdict.confidence` — a bare boolean where a threshold comparison was intended.

This resolves PRD **OQ-1** ("Clarifier confidence — numeric self-score vs. separate judge call?") in favor of self-score, per this design's Decision 1.

## 2. Scope

In scope: the **architecture**, **plan**, and **merge** gates — the three call sites that already route through `GatePolicy`-driven logic (`_gate()` / the merge stage's inline soft-path).

Out of scope: the **clarify** gate. It resolves open questions via a separate `answer_question` signal-wait (`feature.py:514-520`), never calls `_gate()`, and has no `GatePolicy` branch to wire — auto-accepting a suggested answer there is a distinct, unrelated mechanism the PRD describes separately (US-1) and is not addressed here.

## 3. Decisions

**Decision 1 — Confidence source: self-score on the artifact model.**
Add `confidence: float | None = None` to `ArchitectureSpec` and `ImplementationPlan`, filled in by the LLM as part of its normal structured-output call — no extra model call, no added latency/cost per gated stage. `MergeVerdict.confidence` already exists and simply starts being read.

*Trade-off accepted knowingly:* self-scored LLM confidence is known to be poorly calibrated (this is exactly the risk PRD's Risk table and SC-6 exist to monitor). A cross-family judge call would calibrate better but adds a second model family and an LLM call to every gated stage, not just benchmark runs. Ship self-score now; SC-6's retro-vs-override comparison is the intended feedback loop for revisiting this later — but that comparison requires the still-missing retro/reflect wiring (audit §1, stage 13), so calibration monitoring itself is a known follow-on gap, not solved by this design.

**Decision 2 — Threshold configuration: extend `GatePolicy` into a `GateConfig`.**
`PipelineConfig.gates: dict[str, GatePolicy]` becomes `dict[str, GateConfig]`, where:

```python
class GateConfig(BaseModel):
    policy: GatePolicy = GatePolicy.HARD
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
```

A `model_validator(mode="before")` on `GateConfig` (or a validator on the `gates` dict's construction) accepts a bare `GatePolicy` value and coerces it to `GateConfig(policy=that_value)` — so `gates={"architecture": GatePolicy.HARD}` (the shape used today, including in existing tests) keeps working without an explicit migration pass over every call site. `GatePolicy.HARD`/`OFF` behavior is completely unaffected by `threshold` — it's read only on the `SOFT` path.

**Decision 3 — Architecture/plan soft-approval is confidence-only.**
No `DeterministicQualityGate`-equivalent exists at architecture/plan (only merge has one, stage 11). The PRD's soft rule is "confidence >= threshold **AND** deterministic checks pass" — for architecture/plan, this design implements the confidence half only, and documents the gap explicitly rather than inventing a placeholder check. Closing it needs the missing Analyst/traceability stage (audit finding #9), which is out of scope here.

**Decision 4 — Merge gate is unified onto the same mechanism.**
The merge stage's existing soft branch (`feature.py:735-744`) changes from:
```python
if not verdict.approve:
```
to:
```python
if not verdict.approve or verdict.confidence < cfg.gates["merge"].threshold:
```
using the same `GateConfig.threshold` — one rule, one field, everywhere a soft policy exists.

## 4. Architecture

**New pure helper**, alongside `_gate()` in `feature.py`:

```python
def _auto_decision_for(name: str, cfg: PipelineConfig,
                       confidence: float | None) -> GateDecision | None:
    """SOFT + confidence >= threshold -> an APPROVE decision _gate() can
    short-circuit on. None confidence (missing/legacy artifact) or below
    threshold -> None, falling through to the human wait -- never a
    silent auto-approve on absent data (same defensive stance as
    HarnessRunResult.near_context_ceiling())."""
    gate_cfg = cfg.gates.get(name, GateConfig())
    if gate_cfg.policy != GatePolicy.SOFT or confidence is None:
        return None
    if confidence < gate_cfg.threshold:
        return None
    return GateDecision(gate=name, round=1, outcome=GateOutcome.APPROVE,
                        decided_by="policy",
                        comments=f"auto-approved: confidence={confidence:.2f} "
                                 f">= threshold={gate_cfg.threshold:.2f}")
```

`_gate()`'s existing signature (`auto_decision: GateDecision | None = None`) and SOFT branch are unchanged — they already do the right thing once a non-`None` `auto_decision` actually arrives.

`_revisable_stage(name, cfg, run_fn)` changes its inner loop from:
```python
decision = await self._gate(name, cfg, round=round)
```
to:
```python
auto = _auto_decision_for(name, cfg, getattr(artifact, "confidence", None))
decision = await self._gate(name, cfg, auto_decision=auto, round=round)
```
`getattr(..., "confidence", None)` keeps `_revisable_stage` generic across artifact types without a protocol/base-class change — it's already a duck-typed helper (`run_fn` returns `object`).

Merge stage: same helper call, `_auto_decision_for("merge", cfg, verdict.confidence if verdict.approve else None)` — an unapproved verdict is never eligible regardless of confidence — feeding into the existing "escalate to human gate" branch when it returns `None`.

## 5. Data flow

Proposer LLM emits `{artifact fields..., confidence}` in one structured call → workflow reads `artifact.confidence` → `_auto_decision_for` compares against `cfg.gates[name].threshold` → if eligible, builds an `APPROVE`/`decided_by="policy"` `GateDecision` → `_gate()` receives it as `auto_decision`, skips `wait_condition` entirely → **but still calls the existing `_retain(..., MemoryKind.GATE_FEEDBACK, ...)`** (`feature.py:287-293`, unchanged) — so every auto-approval is retained to memory exactly like a human decision, with no new plumbing needed for future calibration analysis once retro/reflect is wired.

## 6. Error handling

- **Missing confidence** (field omitted by the LLM despite being requested, or a memoization-cache hit from before this field existed): `confidence=None` → `_auto_decision_for` returns `None` → falls through to the human wait. Never auto-approves on absent data.
- **Cache/schema compatibility**: `confidence: float | None = None` has a default, so `output_type.model_validate_json(cached)` in `_cached_stage` (`feature.py:213-233`) still parses pre-existing cached JSON payloads that predate this field — they deserialize with `confidence=None`, which is the same safe "never auto-approve" fallback.
- **Out-of-range threshold**: `Field(ge=0.0, le=1.0)` on `GateConfig.threshold` — invalid config fails at `PipelineConfig` construction, not silently at gate time.
- **`GatePolicy` backward compatibility**: the before-validator coercion means existing code/tests passing a bare `GatePolicy` as a dict value keep working unchanged.

## 7. Testing

- **Pure-function unit tests** for `_auto_decision_for`: `SOFT` + confidence above/at/below threshold; `confidence=None`; `HARD`/`OFF` policy (must return `None` regardless of confidence) — style matches `tests/test_quality_gate.py`'s pure-function tests.
- **`GateConfig` coercion test**: `PipelineConfig(gates={"architecture": GatePolicy.HARD})` still produces a `GateConfig(policy=HARD)` with the default threshold.
- **AST/behavior tests** (style of `tests/test_merge_gate_wiring.py`, `tests/test_gate_revision_loop.py`): `_revisable_stage`'s gate calls pass `auto_decision=`; the merge stage's soft branch reads `verdict.confidence`.
- **Runtime test**: a fake `run_fn` producing an artifact with high confidence under `SOFT` policy resolves `_revisable_stage` without any signal being sent (i.e., `wait_condition` never blocks) — mirrors how existing tests exercise `_gate`/`_revisable_stage` without a live Temporal server.
- Update `PipelineConfig`'s default `gates` dict factory and any existing test that constructs `gates={...: GatePolicy.X}` directly, confirming the coercion path covers them (should need zero changes given Decision 2's backward-compat validator — this is a verification step, not a rewrite).

## 8. Known limitations (explicitly out of scope)

- Architecture/plan soft-approval is confidence-only (Decision 3) — the PRD's "AND deterministic checks pass" clause for these two gates isn't satisfiable until the Analyst/traceability stage exists.
- Self-scored confidence calibration (Decision 1's trade-off) has no active monitoring today — SC-6's retro comparison needs the still-unwired retro/reflect stage (audit §1, stage 13) to consume the `GATE_FEEDBACK` retains this design produces.
- The clarify gate's separate suggested-answer auto-accept mechanism (US-1) is untouched.
