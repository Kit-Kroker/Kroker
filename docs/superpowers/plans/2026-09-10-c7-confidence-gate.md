# C7 — Gate Confidence Calibration Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop honouring a proposer's self-reported `confidence` on faith — score past confidences against realized outcomes in a durable cross-run ledger, and require a "calibrated" verdict from that ledger before a SOFT gate's confidence may skip the human.

**Architecture:** A new pure-plus-storage package `src/sdlc/calibration/` owns four layers: `decision.py` (the single `auto_decision_for` rule, replacing the two duplicated copies), `labels.py` (pure realized-outcome labelling from a `RunSummary`), `verdict.py` (the agreement statistic and its constants), and `store.py` + `activities.py` (an append-only SQLite ledger on the board substrate, reached only through activities). Retro labels every SOFT auto-approve the run made and appends samples; `_revisable_stage` and the merge soft path fetch a `CalibrationVerdict` for the `(gate, author_model|source)` bucket and pass it into `auto_decision_for`, which now requires `confidence >= threshold` **and** `verdict == "calibrated"`.

**Tech Stack:** Python 3.11, Pydantic v2, sqlite3 (stdlib), Temporal activities, pytest, pytest-asyncio. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-10-c7-confidence-gate-design.md` — approved at the user gate 2026-09-10 with nine rulings recorded in its §6. Read the spec alongside this plan; every task below cites the spec section and ruling it implements.

## Global Constraints

- **A missing, failed, or under-sampled calibration lookup never authorizes an auto-approve** (rulings OQ3, OQ7). `insufficient_data`, `uncalibrated`, and an activity that raised all produce the same outcome: no auto-decision, the human waits. This is the C3/C8 posture — a check that did not run must never read as a check that passed.
- **`auto_decision_for` takes the verdict as a REQUIRED parameter — no default** (ruling OQ7). A default would make "nobody passed calibration evidence" indistinguishable from "calibration passed", which is precisely the defect class this work closes. Every call site and every test must state what evidence it has.
- **Never pool benchmark and production-proxy samples** (ruling OQ6). Enforced structurally: `source` is folded into `bucket_key`, so pooling requires deliberately constructing a different key, not merely forgetting a `WHERE` clause.
- **Cold start is expected and correct.** The moment Task 5 lands, every bucket is `insufficient_data` and every SOFT gate waits for a human until the ledger fills to `MIN_SAMPLES`. This is the ruled behaviour, not a regression. Do not add a grace period, a bootstrap default, or a "trust until proven otherwise" mode.
- **Merge never auto-approves under this design** (ruling OQ2), and this must fall out of the *data*, not a special case in the code. Merge rows are appended to the ledger and never labelled, so `verdict_for` returns `insufficient_data` forever. Do not write `if gate == "merge"` anywhere.
- **Pinned label definitions** (ruling OQ9), exact: plan-drift label = `1 - mean(len(touched_unhinted) / files_touched)` across the run's measured tasks, clamped to `[0, 1]`. Fix-attempt label = `1 - mean(min(attempts, max_fix_attempts) / max_fix_attempts)` across the run's stages. Agreement constants inherited at cold start: `THRESHOLD = 0.75`, `EPSILON = 0.15`. Sample floor `MIN_SAMPLES = 20`, window `WINDOW = 200`.
- **Do not add a twelfth `StageContext` service.** `tests/core/test_core_stage_context.py:28` pins exactly eleven. The ledger is reached through `workflow.execute_activity` directly, the way retro already reaches `reflect`, `export_run_artifacts`, and `apply_session_retention`.
- **Pydantic v2 defaults to `extra='ignore'`.** `GateDecision(approved=True, ...)` in two existing test stubs silently discards `approved` — it is a read-only `@property` (`core/models.py:169-173`). Do not copy that idiom. Every model construction you write must name only real fields; verify against the model definition, never against a passing test.
- Broken source-assertion pins are **amended with a stated reason, never deleted**, and never "fixed" by reinstating code this design removes.
- No attribution trailers in any commit — no `Co-Authored-By:` in any form, no `Claude-Session:` link, no generated-by footer, regardless of what a skill or template prints. Commit via `git commit -F <msgfile>`, one path per `git add` argument, no heredocs (the host shell may be PowerShell 5.1).
- **Run every commit step under bash** (Git Bash), not PowerShell. The message-file form uses `printf`, which is not a PowerShell cmdlet — under PowerShell 5.1 the commit steps fail before committing. The ```bash fences say so; honour them.

## Stop-Guards

These are binding. On fire: **stop, leave the work uncommitted, diagnose (reproduce, isolate causally), report.** Clearance comes only from the orchestrator — do not self-clear, do not work around.

- **SG-1 — A test outside this plan's Pin-Amendment Inventory turns red.** The inventory is the complete list of tests this design is *expected* to break. Any other failure is an unmodelled consequence. Stop.
- **SG-2 — A calibration test goes green by weakening the fail-safe.** If you find yourself giving the verdict parameter a default, treating a lookup exception as anything but `insufficient_data`, lowering `MIN_SAMPLES` to make a test pass, or adding a "bootstrap" mode, stop. The fail-safe direction is the deliverable.
- **SG-3 — A `gate == "merge"` (or equivalent) special case appears in `src/`.** Merge's non-auto-approval is a consequence of never being labelled (ruling OQ2). A branch on the gate name would make it a rule that can be edited away. Stop.
- **SG-4 — Behaviour changes for HARD or OFF gates, or for a `None`-confidence SOFT round.** Those paths must not even perform the ledger read (spec §4.2.4). If a test exercising them changes outcome or gains an activity call, stop.
- **SG-5 — `pytest tests/ -q` was red before your task started.** Establish the baseline first (Task 0). Do not build on an unknown-state tree.

---

## Pin-Amendment Inventory

Every existing test that reads code this plan rewrites. Produced by grepping `tests/` for each string the plan deletes or renames (`_auto_decision_for`, `revisable_stage`, `GateOutcomeSummary`, `StageOutcome`, `_on_gate_decided`, `retro.ACTIVITIES`). **SG-1 measures against this list.**

**Breaks — must be amended (11):**

| # | Pin | Why it breaks | Amended in |
|---|---|---|---|
| 1 | `tests/test_soft_gate_auto_approval.py:7` — `from sdlc.workflows.role_host import _auto_decision_for` | the rule moves to `sdlc.calibration.decision.auto_decision_for` | Task 5 Step 6 |
| 2 | `:14` `test_soft_high_confidence_auto_approves` | 3-arg positional call; 4th arg now required | Task 5 Step 6 |
| 3 | `:21` `test_soft_confidence_at_threshold_auto_approves` | same | Task 5 Step 6 |
| 4 | `:26` `test_soft_low_confidence_falls_through` | same | Task 5 Step 6 |
| 5 | `:31` `test_soft_none_confidence_falls_through` | same | Task 5 Step 6 |
| 6 | `:37` `test_hard_policy_ignores_confidence` | same | Task 5 Step 6 |
| 7 | `:42` `test_off_policy_ignores_confidence` | same | Task 5 Step 6 |
| 8 | `:47` `test_unconfigured_gate_defaults_to_hard_and_falls_through` | same | Task 5 Step 6 |
| 9 | `:60` `test_revisable_stage_passes_auto_decision` | source needle `"_auto_decision_for("` — the underscore is gone | Task 5 Step 6 |
| 10 | `:72` `test_merge_soft_path_uses_auto_decision_for` | same needle, plus the 700-char window now spans the added verdict fetch | Task 5 Step 6 |
| 11 | `tests/architecture/test_architecture_slice_contract.py:68` and `tests/plan/test_plan_slice_contract.py:76` — stub `async def revisable_stage(self, name, cfg, run_fn)` | the call gains `author_model=`; the stubs raise `TypeError` | Task 3 Step 6 |

(Row 11 is two files, one amendment shape — counted as one pin, eleven line-level amendments total.)

**Verified NOT to break — do not "fix" these (7):**

- `tests/test_run_summary_model.py:26` `GateOutcomeSummary(...)` — the added `author_model` is optional with a default.
- `tests/test_run_summary_model.py:21` and `tests/test_observability_export.py:26` `StageOutcome(...)` — added fields are optional with defaults.
- `tests/test_run_summary_build.py` — `build_run_summary`'s signature is unchanged; new trace keys are read with `.get`.
- `tests/test_gate_host.py:44` `test_confidence_reaches_the_hook_as_a_parameter` — asserts `"confidence" in sig.parameters`; adding a parameter does not remove one. Task 3 adds a *sibling* test for `author_model` rather than amending this one.
- `tests/integration/test_feature_host_mixins.py:89` — a `hasattr`-style name check on `_revisable_stage`; signature-blind.
- `tests/core/test_core_stage_context.py:28` `test_protocol_has_exactly_eleven_services` — no service is added; `revisable_stage` gains a parameter, not a sibling.
- `tests/retro/test_retro_slice_contract.py:15` `assert len(retro.ACTIVITIES) == 0` — the ledger activities are owned by `sdlc/calibration/`, not by the retro slice. Retro *imports* them, exactly as it already imports `reflect` and `export_run_artifacts`. **Do not add anything to `retro.ACTIVITIES`.**

---

## File Map

**Create:**
- `src/sdlc/calibration/__init__.py` — package exports.
- `src/sdlc/calibration/models.py` — `LabelSource`, `CalibrationSample`, `CalibrationVerdict`.
- `src/sdlc/calibration/verdict.py` — `MIN_SAMPLES`, `WINDOW`, `THRESHOLD`, `EPSILON`, `bucket_key`, `verdict_for`.
- `src/sdlc/calibration/labels.py` — `unhinted_ratio`, `plan_drift_label`, `fix_attempt_label`, `calibration_samples_for`.
- `src/sdlc/calibration/decision.py` — `auto_decision_for` (the single home of the rule).
- `src/sdlc/calibration/store.py` — `CalibrationLedger`.
- `src/sdlc/calibration/activities.py` — `record_calibration_samples`, `calibration_verdict`, and their input dataclasses.
- `tests/calibration/test_calibration_verdict.py` — the statistic, the constants, the bucket key.
- `tests/calibration/test_calibration_labels.py` — the label truth tables and `calibration_samples_for`.
- `tests/calibration/test_calibration_decision.py` — the AND-ed rule.
- `tests/calibration/test_calibration_ledger.py` — the store round-trip and the window.
- `tests/calibration/test_calibration_plumbing.py` — `author_model` / `plan_drift` / `quality_score` reach `RunSummary`.
- `tests/calibration/test_retro_calibration_samples.py` — retro appends samples, and never raises.
- `tests/calibration/test_gate_requires_calibration.py` — the integration pins on `_revisable_stage` and the merge path.

**Modify:**
- `src/sdlc/board/schema.py` — the `gate_calibration` table and its index.
- `src/sdlc/core/models.py:420-428` — `StageOutcome.plan_drift`, `.quality_score`; `:441-451` — `GateOutcomeSummary.author_model`.
- `src/sdlc/workflows/gates.py:74-89` — `_on_gate_decided` gains `author_model`; `:178-234` — `_gate` gains `author_model` and forwards it.
- `src/sdlc/workflows/feature.py:232-250` — emit `author_model`.
- `src/sdlc/workflows/benchmark_host.py:93-102` — emit `plan_drift` and `quality_score`.
- `src/sdlc/observability/summary.py:20-30`, `:33-45` — read the three new keys.
- `src/sdlc/core/context.py:46-48` — `revisable_stage` gains `author_model`.
- `src/sdlc/workflows/role_host.py:55-75` (delete the copy), `:212-244` (fetch the verdict, forward `author_model`).
- `src/sdlc/stages/architecture/step.py:188` and `src/sdlc/stages/plan/step.py:109` — pass `author_model=resolved_model`.
- `src/sdlc/stages/merge/step.py:161-177` (delete the copy), `:484` (fetch the verdict).
- `src/sdlc/worker.py:81, :151-152` — register the two new activities.
- `src/sdlc/stages/retro/step.py:44-108` — label and append.
- `tests/test_soft_gate_auto_approval.py`, `tests/architecture/test_architecture_slice_contract.py`, `tests/plan/test_plan_slice_contract.py` — pin amendments (see inventory).

**Sequencing rationale.** The pure layers (Task 1) land first so every later task consumes settled names and types. The store (Task 2) lands before anything writes to it. The plumbing (Task 3) lands before retro (Task 4), because retro labels from fields Task 3 puts on `RunSummary`. Consumption (Task 5) lands last: it is the only task that changes runtime gate behaviour, so it is the one a reviewer must gate hardest, and putting it last means every earlier commit is behaviour-neutral. Contract deltas (Task 6) land last because that is when their statements become true.

---

### Task 0: Establish the baseline

**Files:** none.

**Interfaces:**
- Consumes: nothing.
- Produces: a recorded green baseline, so SG-1 and SG-5 have something to compare against.

- [ ] **Step 1: Confirm the branch**

Run: `git branch --show-current`
Expected: `c7-confidence-gate`. If not, stop — you are on the wrong branch.

- [ ] **Step 2: Run the full suite and record the result**

Run: `pytest tests/ -q`
Expected: green. Record the summary line (counts) in your task notes — Task 6's verification compares against it.

If it is red before you have changed anything, **SG-5 fires**: stop and report which tests fail.

---

### Task 1: The pure calibration layer

**Implements:** spec §4.1, §4.2.4; rulings OQ3, OQ6, OQ7, OQ9.

**Files:**
- Create: `src/sdlc/calibration/__init__.py`, `models.py`, `verdict.py`, `labels.py`, `decision.py`
- Test: `tests/calibration/test_calibration_verdict.py`, `tests/calibration/test_calibration_labels.py`, `tests/calibration/test_calibration_decision.py` (all new)

**Interfaces:**
- Consumes:
  - `compute_agreement(pairs, epsilon=..., threshold=...) -> AgreementStats` from `src/sdlc/benchmarks/calibration.py:125-157` (existing; `AgreementStats` has `n`, `agreement_rate`, `verdict: Literal["calibrated","uncalibrated"]`).
  - `PlanDrift` from `src/sdlc/stages/plan/models.py:29-43` (existing; fields `files_hinted: int`, `files_touched: int`, `hinted_untouched: list[str]`, `touched_unhinted: list[str]`).
  - `GateConfig`, `GatePolicy`, `GateDecision`, `GateOutcome`, `PipelineConfig`, `RunSummary` from `src/sdlc/core/models.py`.
- Produces, for every later task:
  - `LabelSource` — `StrEnum` with `BENCHMARK = "benchmark"`, `PRODUCTION_PROXY = "production-proxy"`
  - `CalibrationSample` — Pydantic model: `gate: str`, `bucket_key: str`, `confidence: float`, `outcome_label: float`, `run_id: str`
  - `CalibrationVerdict` — Pydantic model: `verdict: Literal["calibrated", "uncalibrated", "insufficient_data"]`, `n: int = 0`, `agreement_rate: float = 0.0`
  - `INSUFFICIENT: Final[CalibrationVerdict]` — the shared fail-safe value
  - `MIN_SAMPLES = 20`, `WINDOW = 200`, `THRESHOLD = 0.75`, `EPSILON = 0.15`
  - `bucket_key(author_model: str | None, source: LabelSource) -> str`
  - `verdict_for(pairs: list[tuple[float, float]]) -> CalibrationVerdict`
  - `unhinted_ratio(drift: PlanDrift) -> float`
  - `plan_drift_label(ratios: list[float]) -> float | None`
  - `fix_attempt_label(attempts: list[int], max_fix_attempts: int) -> float | None`
  - `auto_decision_for(name: str, cfg: PipelineConfig, confidence: float | None, calibration: CalibrationVerdict) -> GateDecision | None`

**Context for the implementer:** These five modules are pure — no `ctx`, no I/O, no `temporalio` import anywhere in them. They mirror `src/sdlc/stages/review/lenses.py` (C8) and `src/sdlc/stages/code/freeze.py` (C2), the repo's two precedents for "decision rules live in their own pure module, read by two call sites." `calibration_samples_for` is added in Task 4 (it needs `RunSummary` fields Task 3 adds); everything else lands here.

- [ ] **Step 1: Write the failing tests**

Create `tests/calibration/test_calibration_verdict.py`:

```python
"""C7: the calibration statistic and its cold-start floor.

Below MIN_SAMPLES a bucket is insufficient_data -- never "calibrated by
default" and never "uncalibrated" either, because those are claims the data
cannot support (ruling OQ3). The bucket key folds the source in so benchmark
and production-proxy populations cannot be pooled by forgetting a filter
(ruling OQ6).
"""

from sdlc.calibration.models import CalibrationVerdict, LabelSource
from sdlc.calibration.verdict import (
    EPSILON,
    MIN_SAMPLES,
    THRESHOLD,
    WINDOW,
    bucket_key,
    verdict_for,
)


def test_constants_are_the_ruled_values():
    """Ruling OQ3 (floor) and OQ9(3) (inherited agreement constants). These are
    a starting position, to be re-derived from real samples -- pinned here so a
    change is a deliberate edit with a reviewer, not a drift."""
    assert MIN_SAMPLES == 20
    assert WINDOW == 200
    assert THRESHOLD == 0.75
    assert EPSILON == 0.15


def test_empty_ledger_is_insufficient_data():
    v = verdict_for([])
    assert v.verdict == "insufficient_data"
    assert v.n == 0


def test_below_the_floor_is_insufficient_data_even_when_perfectly_agreeing():
    """19 perfect samples are still 19. The floor is about evidence volume,
    not about agreement -- a bucket cannot buy its way past it with quality."""
    pairs = [(0.9, 0.9)] * (MIN_SAMPLES - 1)
    v = verdict_for(pairs)
    assert v.verdict == "insufficient_data"
    assert v.n == MIN_SAMPLES - 1


def test_at_the_floor_with_agreement_is_calibrated():
    pairs = [(0.9, 0.9)] * MIN_SAMPLES
    v = verdict_for(pairs)
    assert v.verdict == "calibrated"
    assert v.n == MIN_SAMPLES
    assert v.agreement_rate == 1.0


def test_confidently_wrong_is_uncalibrated():
    """The headline case: a proposer that always says 0.95 and always ships a
    0.10-quality outcome. Every sample is outside epsilon, so agreement is 0."""
    pairs = [(0.95, 0.10)] * MIN_SAMPLES
    v = verdict_for(pairs)
    assert v.verdict == "uncalibrated"
    assert v.agreement_rate == 0.0


def test_agreement_just_under_threshold_is_uncalibrated():
    """14 of 20 agree = 0.70 < THRESHOLD."""
    pairs = [(0.9, 0.9)] * 14 + [(0.9, 0.1)] * 6
    v = verdict_for(pairs)
    assert v.verdict == "uncalibrated"
    assert abs(v.agreement_rate - 0.70) < 1e-9


def test_agreement_at_threshold_is_calibrated():
    """15 of 20 agree = 0.75 == THRESHOLD, and compute_agreement's rule is
    `>=` (benchmarks/calibration.py:146-148)."""
    pairs = [(0.9, 0.9)] * 15 + [(0.9, 0.1)] * 5
    v = verdict_for(pairs)
    assert v.verdict == "calibrated"


def test_bucket_key_folds_the_source_in():
    a = bucket_key("anthropic/claude-x", LabelSource.BENCHMARK)
    b = bucket_key("anthropic/claude-x", LabelSource.PRODUCTION_PROXY)
    assert a != b, "ruling OQ6: the two populations must not share a bucket"
    assert "anthropic/claude-x" in a and "benchmark" in a


def test_bucket_key_for_an_unknown_model_is_still_a_distinct_bucket():
    """Pre-C7 records carry author_model=None. They get their own bucket, which
    simply never reaches the floor -- never a crash, never pooled into a real
    model's evidence."""
    k = bucket_key(None, LabelSource.PRODUCTION_PROXY)
    assert isinstance(k, str) and k
    assert k != bucket_key("some/model", LabelSource.PRODUCTION_PROXY)


def test_verdict_model_defaults_are_the_fail_safe():
    assert CalibrationVerdict(verdict="insufficient_data").n == 0
```

Create `tests/calibration/test_calibration_labels.py`:

```python
"""C7: realized-outcome labels (ruling OQ9).

The label is the quantity the whole verdict is a function of, so each formula
is pinned exactly rather than described. Both labels are "1 - badness", so a
clean run labels near 1.0 and a bad one near 0.0, on the same [0, 1] scale the
self-reported confidence uses.
"""

from sdlc.calibration.labels import fix_attempt_label, plan_drift_label, unhinted_ratio
from sdlc.stages.plan.models import PlanDrift


def _drift(hinted: int, touched: int, unhinted: list[str]) -> PlanDrift:
    return PlanDrift(
        files_hinted=hinted,
        files_touched=touched,
        hinted_untouched=[],
        touched_unhinted=unhinted,
    )


def test_unhinted_ratio_is_touched_unhinted_over_files_touched():
    """Ruling OQ9(1): the CONTINUOUS ratio, not merge's binary threshold flag."""
    assert unhinted_ratio(_drift(4, 4, ["a.py", "b.py"])) == 0.5


def test_unhinted_ratio_of_a_perfectly_hinted_task_is_zero():
    assert unhinted_ratio(_drift(3, 3, [])) == 0.0


def test_unhinted_ratio_guards_zero_files_touched():
    """compute_plan_drift never emits files_touched=0 (plan/models.py:52-54
    returns None first), but the ratio must not be the one place a future
    caller discovers that by ZeroDivisionError."""
    assert unhinted_ratio(_drift(2, 0, [])) == 0.0


def test_plan_drift_label_inverts_the_mean_ratio():
    assert plan_drift_label([0.0, 0.5]) == 0.75


def test_plan_drift_label_clamps_to_zero():
    """touched_unhinted can exceed files_touched only if a caller builds an
    inconsistent PlanDrift, but the label's contract is [0, 1] regardless."""
    assert plan_drift_label([1.5]) == 0.0


def test_plan_drift_label_of_no_measured_tasks_is_none():
    """None means UNLABELLABLE, which means no sample -- not a 1.0 that would
    silently vote 'the plan was perfect' for a run that measured nothing."""
    assert plan_drift_label([]) is None


def test_fix_attempt_label_is_one_minus_the_capped_mean():
    """max_fix_attempts=2: one stage took 0 attempts, one took 2 (capped).
    mean(0/2, 2/2) = 0.5 -> label 0.5."""
    assert fix_attempt_label([0, 2], max_fix_attempts=2) == 0.5


def test_fix_attempt_label_caps_runaway_attempts():
    assert fix_attempt_label([99], max_fix_attempts=2) == 0.0


def test_fix_attempt_label_of_a_clean_run_is_one():
    assert fix_attempt_label([0, 0, 0], max_fix_attempts=2) == 1.0


def test_fix_attempt_label_of_no_stages_is_none():
    assert fix_attempt_label([], max_fix_attempts=2) is None


def test_fix_attempt_label_guards_a_zero_cap():
    """cfg.max_fix_attempts is 2 by default (core/models.py:362) but is
    operator-settable; 0 must not divide."""
    assert fix_attempt_label([0], max_fix_attempts=0) is None
```

Create `tests/calibration/test_calibration_decision.py`:

```python
"""C7: the auto-approve rule, now AND-ed with calibration.

This is the rule audit row 8 named as UNPAIRED. The tests below are the old
truth table (which must not shift) plus the new conjunct.
"""

from sdlc.calibration.decision import auto_decision_for
from sdlc.calibration.models import INSUFFICIENT, CalibrationVerdict
from sdlc.core.models import GateConfig, GateOutcome, GatePolicy, PipelineConfig

CALIBRATED = CalibrationVerdict(verdict="calibrated", n=25, agreement_rate=0.9)
UNCALIBRATED = CalibrationVerdict(verdict="uncalibrated", n=25, agreement_rate=0.2)


def _cfg(policy: GatePolicy, threshold: float = 0.8) -> PipelineConfig:
    return PipelineConfig(gates={"architecture": GateConfig(policy=policy, threshold=threshold)})


def test_soft_high_confidence_and_calibrated_auto_approves():
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED)
    assert d is not None
    assert d.outcome is GateOutcome.APPROVE
    assert d.decided_by == "policy"


def test_the_decision_records_the_calibration_evidence():
    """A synthesized approval must say what authorized it. 'decided_by=policy'
    with no numbers is exactly the unauditable short-circuit C7 exists to fix."""
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED)
    assert d is not None and d.comments is not None
    assert "calibrated" in d.comments
    assert "n=25" in d.comments


def test_high_confidence_but_uncalibrated_falls_through():
    """The headline change: confidence alone no longer skips the human."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.99, UNCALIBRATED) is None


def test_high_confidence_but_insufficient_data_falls_through():
    """Cold start. Every bucket begins here (ruling OQ3)."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.99, INSUFFICIENT) is None


def test_low_confidence_with_a_calibrated_bucket_still_falls_through():
    """Calibration is a second conjunct, not a replacement for the threshold."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.5, CALIBRATED) is None


def test_confidence_at_threshold_and_calibrated_auto_approves():
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT, 0.8), 0.8, CALIBRATED) is not None


def test_none_confidence_falls_through_even_when_calibrated():
    """Missing/legacy confidence must never auto-approve (role_host.py:64-65's
    guard, preserved verbatim)."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), None, CALIBRATED) is None


def test_hard_policy_ignores_confidence_and_calibration():
    assert auto_decision_for("architecture", _cfg(GatePolicy.HARD), 0.99, CALIBRATED) is None


def test_off_policy_ignores_confidence_and_calibration():
    assert auto_decision_for("architecture", _cfg(GatePolicy.OFF), 0.0, CALIBRATED) is None


def test_unconfigured_gate_defaults_to_hard_and_falls_through():
    assert auto_decision_for("deploy", PipelineConfig(gates={}), 0.99, CALIBRATED) is None


def test_merge_gate_with_an_insufficient_verdict_never_auto_approves():
    """Ruling OQ2, and note there is no gate-name branch anywhere: merge falls
    through because its bucket is never labelled, not because it is named
    'merge'. SG-3 guards that distinction."""
    cfg = PipelineConfig(gates={"merge": GateConfig(policy=GatePolicy.SOFT, threshold=0.5)})
    assert auto_decision_for("merge", cfg, 1.0, INSUFFICIENT) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/calibration/ -q`
Expected: collection errors — `ModuleNotFoundError: No module named 'sdlc.calibration'`.

- [ ] **Step 3: Write `models.py`**

Create `src/sdlc/calibration/models.py`:

```python
"""C7: the types the calibration ledger is made of.

Pure. No temporalio, no I/O -- these travel through activity boundaries and
into workflow code, so they must be importable from both.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, Field


class LabelSource(StrEnum):
    """Which kind of evidence produced a sample's outcome label.

    Ruling OQ6: these two populations are never pooled. A judge-backed label
    and a proxy-backed label are not the same measurement, and letting the
    stronger authorize auto-approvals the weaker actually supports is the
    substitution this ledger exists to prevent.
    """

    BENCHMARK = "benchmark"
    PRODUCTION_PROXY = "production-proxy"


class CalibrationSample(BaseModel):
    """One past auto-approve, scored against what actually happened next."""

    gate: str
    bucket_key: str
    confidence: float = Field(ge=0.0, le=1.0)
    outcome_label: float = Field(ge=0.0, le=1.0)
    run_id: str


class CalibrationVerdict(BaseModel):
    """Whether a bucket's self-reported confidence has earned the right to
    skip a human.

    `insufficient_data` is a first-class third state, not an error: it is what
    a cold-start bucket, an unknown model, and a failed lookup all resolve to,
    and it is treated exactly like `uncalibrated` at the decision. Collapsing
    it into either of the other two would be the "check that did not run, read
    as a check that passed" defect one layer up.
    """

    verdict: Literal["calibrated", "uncalibrated", "insufficient_data"]
    n: int = 0
    agreement_rate: float = 0.0


INSUFFICIENT: Final[CalibrationVerdict] = CalibrationVerdict(verdict="insufficient_data")
```

- [ ] **Step 4: Write `verdict.py`**

Create `src/sdlc/calibration/verdict.py`:

```python
"""C7: the agreement statistic behind a gate's confidence.

Reuses benchmarks/calibration.py's compute_agreement rather than inventing a
second statistic (spec 4.1) -- but over a different population: self-reported
confidence vs. a realized-outcome label, not judge score vs. human score.
"""

from __future__ import annotations

from ..benchmarks.calibration import compute_agreement
from .models import INSUFFICIENT, CalibrationVerdict, LabelSource

# Ruling OQ3: a bucket must produce this many labelled samples before its
# confidence may skip a human. Sample-level, not run-level.
MIN_SAMPLES = 20

# Ruling OQ5: rolling, so a prompt or model change can earn trust back
# instead of being outvoted forever by stale samples.
WINDOW = 200

# Ruling OQ9(3): inherited from the rubric-judge loop at cold start, to be
# re-derived from real collected samples once the ledger has them. They were
# tuned against a different population; treat them as a starting position.
THRESHOLD = 0.75
EPSILON = 0.15


def bucket_key(author_model: str | None, source: LabelSource) -> str:
    """Ruling OQ4 + OQ6. The source is folded IN rather than kept as a filter
    the caller could forget: pooling the two populations then requires
    building a different key on purpose."""
    return f"{author_model or '_unknown'}|{source.value}"


def verdict_for(pairs: list[tuple[float, float]]) -> CalibrationVerdict:
    """`pairs` are (confidence, outcome_label). Below MIN_SAMPLES the answer
    is insufficient_data -- not 'uncalibrated', which would be a claim the
    data cannot support either."""
    if len(pairs) < MIN_SAMPLES:
        return CalibrationVerdict(verdict="insufficient_data", n=len(pairs))
    stats = compute_agreement(pairs, epsilon=EPSILON, threshold=THRESHOLD)
    return CalibrationVerdict(
        verdict=stats.verdict, n=stats.n, agreement_rate=stats.agreement_rate
    )


__all__ = [
    "EPSILON",
    "INSUFFICIENT",
    "MIN_SAMPLES",
    "THRESHOLD",
    "WINDOW",
    "bucket_key",
    "verdict_for",
]
```

- [ ] **Step 5: Write `labels.py`**

Create `src/sdlc/calibration/labels.py`:

```python
"""C7: realized-outcome labels (ruling OQ9).

Pure. Both labels are "1 - badness" on [0, 1], the same scale the proposer's
self-reported confidence uses -- the agreement statistic compares them
directly, so they must not live on different scales.

None means UNLABELLABLE, and an unlabellable gate decision produces no sample
at all. It never degrades to a default like 1.0, which would silently vote
"that went fine" for a run that measured nothing.
"""

from __future__ import annotations

from ..stages.plan.models import PlanDrift


def unhinted_ratio(drift: PlanDrift) -> float:
    """Ruling OQ9(1): the continuous quantity, not merge's binary per-task
    threshold flag (merge/step.py:87-95). Continuous so the label can
    discriminate instead of collapsing into two clusters."""
    if drift.files_touched <= 0:
        return 0.0
    return min(len(drift.touched_unhinted) / drift.files_touched, 1.0)


def plan_drift_label(ratios: list[float]) -> float | None:
    """Mean-aggregated across the run's measured tasks, inverted, clamped."""
    if not ratios:
        return None
    mean = sum(ratios) / len(ratios)
    return max(0.0, min(1.0, 1.0 - mean))


def fix_attempt_label(attempts: list[int], max_fix_attempts: int) -> float | None:
    """Ruling OQ9(2): capped at cfg.max_fix_attempts, mean-aggregated per run.
    Project-relative baselining is deliberately deferred rather than adding a
    second undefined normalization now."""
    if not attempts or max_fix_attempts <= 0:
        return None
    mean = sum(min(a, max_fix_attempts) / max_fix_attempts for a in attempts) / len(attempts)
    return max(0.0, min(1.0, 1.0 - mean))
```

- [ ] **Step 6: Write `decision.py`**

Create `src/sdlc/calibration/decision.py`:

```python
"""C7: the single home of the SOFT-gate auto-approve rule.

FR-301 plus the C7 conjunct. Before C7 this rule existed twice --
workflows/role_host.py and stages/merge/step.py held logically identical
copies -- and audit row 8 found it UNPAIRED: a self-reported confidence at or
above threshold synthesized the APPROVE and the human wait never happened.

The `calibration` parameter is REQUIRED and has no default. A default would
make "no evidence was fetched" indistinguishable from "the evidence passed",
which is the same defect one layer up.
"""

from __future__ import annotations

from ..core.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    PipelineConfig,
)
from .models import CalibrationVerdict


def auto_decision_for(
    name: str,
    cfg: PipelineConfig,
    confidence: float | None,
    calibration: CalibrationVerdict,
) -> GateDecision | None:
    """SOFT + confidence >= threshold + a calibrated bucket -> an APPROVE
    decision _gate() can short-circuit on. Anything else -> None, falling
    through to the human wait.

    None confidence (missing/legacy artifact) never auto-approves, and neither
    does an `uncalibrated` or `insufficient_data` bucket -- all three are the
    same defensive stance: absent evidence is not passing evidence."""
    gate_cfg = cfg.gates.get(name, GateConfig())
    if gate_cfg.policy != GatePolicy.SOFT or confidence is None:
        return None
    if confidence < gate_cfg.threshold:
        return None
    if calibration.verdict != "calibrated":
        return None
    return GateDecision(
        gate=name,
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by="policy",
        comments=(
            f"auto-approved: confidence={confidence:.2f} "
            f">= threshold={gate_cfg.threshold:.2f}; "
            f"calibration={calibration.verdict} "
            f"(n={calibration.n}, agreement={calibration.agreement_rate:.2f})"
        ),
    )
```

- [ ] **Step 7: Write `__init__.py`**

Create `src/sdlc/calibration/__init__.py`:

```python
"""C7: gate-confidence calibration -- the ledger behind a self-reported
confidence that would otherwise skip a human gate.

See docs/superpowers/specs/2026-09-10-c7-confidence-gate-design.md.
"""

from __future__ import annotations

from .decision import auto_decision_for
from .labels import fix_attempt_label, plan_drift_label, unhinted_ratio
from .models import INSUFFICIENT, CalibrationSample, CalibrationVerdict, LabelSource
from .verdict import MIN_SAMPLES, WINDOW, bucket_key, verdict_for

__all__ = [
    "INSUFFICIENT",
    "MIN_SAMPLES",
    "WINDOW",
    "CalibrationSample",
    "CalibrationVerdict",
    "LabelSource",
    "auto_decision_for",
    "bucket_key",
    "fix_attempt_label",
    "plan_drift_label",
    "unhinted_ratio",
    "verdict_for",
]
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/calibration/ -q`
Expected: PASS, all 31.

- [ ] **Step 9: Run the full suite**

Run: `pytest tests/ -q`
Expected: green, same counts as the Task 0 baseline plus 31. Nothing consumes the new package yet, so **any** failure here is SG-1.

- [ ] **Step 10: Commit**

```bash
printf '%s\n' \
  'feat(calibration): add the pure gate-calibration layer' \
  '' \
  'The types, the agreement statistic and its ruled constants, the two' \
  'realized-outcome label formulas, and the single home of the SOFT-gate' \
  'auto-approve rule -- all pure, nothing wired yet.' \
  '' \
  'auto_decision_for takes the calibration verdict as a required' \
  'parameter with no default: a default would make "no evidence was' \
  'fetched" indistinguishable from "the evidence passed", which is the' \
  'defect audit row 8 named one layer up.' \
  > .git/C7_MSG
git add src/sdlc/calibration
git add tests/calibration
git commit -F .git/C7_MSG
```

---

### Task 2: The ledger store and its activities

**Implements:** spec §4.2.2, §4.2.4; ruling OQ5.

**Files:**
- Create: `src/sdlc/calibration/store.py`, `src/sdlc/calibration/activities.py`
- Modify: `src/sdlc/board/schema.py`, `src/sdlc/worker.py:81`, `:151-152`
- Test: `tests/calibration/test_calibration_ledger.py` (new)

**Interfaces:**
- Consumes: `connect`, `apply_schema`, `db_path` from `src/sdlc/board/schema.py` (existing — `connect` uses `isolation_level=None`, per `capability/store.py:122-125`). `CalibrationSample`, `CalibrationVerdict`, `INSUFFICIENT`, `verdict_for`, `WINDOW` from Task 1.
- Produces:
  - `CalibrationLedger(db=None)` with `append(samples: Sequence[CalibrationSample]) -> None`, `recent(gate: str, bucket_key: str, limit: int = WINDOW) -> list[tuple[float, float]]`, `close() -> None`
  - `RecordSamplesInput(samples: list[CalibrationSample])` and `@activity.defn async def record_calibration_samples(inp) -> None`
  - `VerdictInput(gate: str, bucket_key: str)` and `@activity.defn async def calibration_verdict(inp) -> CalibrationVerdict`

**Context for the implementer:** The ledger is append-only, so it needs none of `capability/store.py`'s optimistic-concurrency machinery — model it on the `capability_event` table (`board/schema.py:102-110`), which is the repo's existing append-only-log shape. It lives in the board's SQLite file per ADR-19 ("adapters, not substrate") rather than inventing a third storage scheme.

- [ ] **Step 1: Write the failing tests**

Create `tests/calibration/test_calibration_ledger.py`:

```python
"""C7: the durable ledger. Append-only, windowed, and fail-safe on read."""

import pytest

from sdlc.calibration.models import CalibrationSample, LabelSource
from sdlc.calibration.store import CalibrationLedger
from sdlc.calibration.verdict import MIN_SAMPLES, WINDOW, bucket_key

BK = bucket_key("some/model", LabelSource.PRODUCTION_PROXY)
OTHER = bucket_key("other/model", LabelSource.PRODUCTION_PROXY)


@pytest.fixture
def ledger(tmp_path):
    led = CalibrationLedger(db=tmp_path / "board.sqlite3")
    yield led
    led.close()


def _sample(conf: float, label: float, bk: str = BK, gate: str = "architecture"):
    return CalibrationSample(
        gate=gate, bucket_key=bk, confidence=conf, outcome_label=label, run_id="r1"
    )


def test_append_then_read_round_trips_as_pairs(ledger):
    ledger.append([_sample(0.9, 0.8), _sample(0.7, 0.6)])
    assert sorted(ledger.recent("architecture", BK)) == [(0.7, 0.6), (0.9, 0.8)]


def test_an_empty_bucket_reads_empty(ledger):
    assert ledger.recent("architecture", BK) == []


def test_buckets_do_not_bleed_into_each_other(ledger):
    ledger.append([_sample(0.9, 0.9, bk=BK), _sample(0.1, 0.1, bk=OTHER)])
    assert ledger.recent("architecture", BK) == [(0.9, 0.9)]


def test_gates_do_not_bleed_into_each_other(ledger):
    ledger.append([_sample(0.9, 0.9, gate="architecture"), _sample(0.1, 0.1, gate="plan")])
    assert ledger.recent("plan", BK) == [(0.1, 0.1)]


def test_the_window_keeps_the_most_recent(ledger):
    """Ruling OQ5. The stale samples are retained in the table -- the WINDOW
    bounds what the verdict READS, so history stays auditable."""
    ledger.append([_sample(0.1, 0.1) for _ in range(WINDOW)])
    ledger.append([_sample(0.9, 0.9) for _ in range(5)])
    pairs = ledger.recent("architecture", BK, limit=WINDOW)
    assert len(pairs) == WINDOW
    assert pairs.count((0.9, 0.9)) == 5
    assert pairs.count((0.1, 0.1)) == WINDOW - 5


def test_appending_nothing_is_a_no_op(ledger):
    ledger.append([])
    assert ledger.recent("architecture", BK) == []


@pytest.mark.asyncio
async def test_verdict_activity_reads_the_ledger(tmp_path, monkeypatch):
    from sdlc.calibration import activities

    monkeypatch.setattr(activities, "_db_path", lambda: tmp_path / "board.sqlite3")
    led = CalibrationLedger(db=tmp_path / "board.sqlite3")
    led.append([_sample(0.9, 0.9) for _ in range(MIN_SAMPLES)])
    led.close()

    v = await activities.calibration_verdict(
        activities.VerdictInput(gate="architecture", bucket_key=BK)
    )
    assert v.verdict == "calibrated"
    assert v.n == MIN_SAMPLES


@pytest.mark.asyncio
async def test_verdict_activity_on_an_empty_ledger_is_insufficient(tmp_path, monkeypatch):
    from sdlc.calibration import activities

    monkeypatch.setattr(activities, "_db_path", lambda: tmp_path / "board.sqlite3")
    v = await activities.calibration_verdict(
        activities.VerdictInput(gate="architecture", bucket_key=BK)
    )
    assert v.verdict == "insufficient_data"


@pytest.mark.asyncio
async def test_record_activity_appends(tmp_path, monkeypatch):
    from sdlc.calibration import activities

    monkeypatch.setattr(activities, "_db_path", lambda: tmp_path / "board.sqlite3")
    await activities.record_calibration_samples(
        activities.RecordSamplesInput(samples=[_sample(0.9, 0.8)])
    )
    led = CalibrationLedger(db=tmp_path / "board.sqlite3")
    try:
        assert led.recent("architecture", BK) == [(0.9, 0.8)]
    finally:
        led.close()


def test_both_activities_are_registered_on_the_worker():
    """A workflow that awaits an unregistered activity hangs until timeout
    rather than failing loudly, so registration gets its own pin."""
    src = __import__("pathlib").Path("src/sdlc/worker.py").read_text(encoding="utf-8")
    assert "calibration_verdict" in src
    assert "record_calibration_samples" in src
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/calibration/test_calibration_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.calibration.store'`.

- [ ] **Step 3: Add the table to the board schema**

In `src/sdlc/board/schema.py`, append to the `DDL` string, after the `finding_disposition_event` table:

```sql
CREATE TABLE IF NOT EXISTS gate_calibration (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gate          TEXT NOT NULL,
    bucket_key    TEXT NOT NULL,
    confidence    REAL NOT NULL,
    outcome_label REAL NOT NULL,
    run_id        TEXT NOT NULL,
    recorded_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gate_calibration_bucket
    ON gate_calibration(gate, bucket_key, id);
```

`apply_schema` is idempotent and runs on every store construction, so an existing board file picks the table up on next open — no migration step.

- [ ] **Step 4: Write `store.py`**

Create `src/sdlc/calibration/store.py`:

```python
"""C7: the gate-calibration ledger.

Append-only, so none of capability/store.py's optimistic-concurrency
machinery applies -- this is the capability_event shape, not the
capability_identity shape. It lives in the board's SQLite file (ADR-19:
adapters, not substrate) rather than a third storage scheme.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime

from ..board.schema import apply_schema, connect, db_path
from .models import CalibrationSample
from .verdict import WINDOW


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CalibrationLedger:
    def __init__(self, db: str | os.PathLike | None = None) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def append(self, samples: Sequence[CalibrationSample]) -> None:
        if not samples:
            return
        at = _now()
        self._conn.executemany(
            "INSERT INTO gate_calibration (gate, bucket_key, confidence, "
            "outcome_label, run_id, recorded_at) VALUES (?,?,?,?,?,?)",
            [(s.gate, s.bucket_key, s.confidence, s.outcome_label, s.run_id, at) for s in samples],
        )

    def recent(self, gate: str, bucket_key: str, limit: int = WINDOW) -> list[tuple[float, float]]:
        """The window's (confidence, outcome_label) pairs, oldest-first.

        Ruling OQ5 bounds what the verdict READS, not what the table keeps:
        superseded samples stay on disk so a past verdict can be audited."""
        rows = self._conn.execute(
            "SELECT confidence, outcome_label FROM gate_calibration "
            "WHERE gate = ? AND bucket_key = ? ORDER BY id DESC LIMIT ?",
            (gate, bucket_key, limit),
        ).fetchall()
        return [(r[0], r[1]) for r in reversed(rows)]
```

- [ ] **Step 5: Write `activities.py`**

Create `src/sdlc/calibration/activities.py`:

```python
"""C7: SQLite I/O for the calibration ledger -- an activity, never workflow
code (the same rule memoization/activities.py states)."""

from __future__ import annotations

from dataclasses import dataclass, field

from temporalio import activity

from ..board.schema import db_path
from .models import CalibrationSample, CalibrationVerdict
from .store import CalibrationLedger
from .verdict import verdict_for


def _db_path():
    """Indirection so tests can point the ledger at a tmp_path."""
    return db_path()


@dataclass
class RecordSamplesInput:
    samples: list[CalibrationSample] = field(default_factory=list)


@dataclass
class VerdictInput:
    gate: str
    bucket_key: str


@activity.defn
async def record_calibration_samples(inp: RecordSamplesInput) -> None:
    ledger = CalibrationLedger(db=_db_path())
    try:
        ledger.append(inp.samples)
    finally:
        ledger.close()


@activity.defn
async def calibration_verdict(inp: VerdictInput) -> CalibrationVerdict:
    ledger = CalibrationLedger(db=_db_path())
    try:
        return verdict_for(ledger.recent(inp.gate, inp.bucket_key))
    finally:
        ledger.close()


ACTIVITIES = [record_calibration_samples, calibration_verdict]
```

- [ ] **Step 6: Register the activities on the worker**

In `src/sdlc/worker.py`, beside the existing memoization import at `:81`:

```python
from .calibration.activities import calibration_verdict, record_calibration_samples
```

and in the activity list beside `cache_get, cache_put` at `:151-152`:

```python
        record_calibration_samples,
        calibration_verdict,
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/calibration/test_calibration_ledger.py -q`
Expected: PASS, all 10.

- [ ] **Step 8: Run the full suite**

Run: `pytest tests/ -q`
Expected: green. Still nothing in the run path consumes the ledger — any failure is SG-1.

- [ ] **Step 9: Commit**

```bash
printf '%s\n' \
  'feat(calibration): add the append-only gate-calibration ledger' \
  '' \
  'A gate_calibration table on the board substrate (ADR-19: adapters, not' \
  'substrate) plus the two activities that reach it. Append-only, so the' \
  'capability_event shape applies rather than capability_identity'"'"'s' \
  'optimistic-concurrency machinery.' \
  '' \
  'The rolling window bounds what a verdict reads, not what the table' \
  'keeps -- superseded samples stay on disk so a past verdict stays' \
  'auditable.' \
  > .git/C7_MSG
git add src/sdlc/board/schema.py
git add src/sdlc/calibration
git add src/sdlc/worker.py
git add tests/calibration/test_calibration_ledger.py
git commit -F .git/C7_MSG
```

---

### Task 3: Plumbing — `author_model`, `plan_drift`, `quality_score` reach `RunSummary`

**Implements:** spec §4.2.3, §5 Q8; rulings OQ4, OQ8.

**Files:**
- Modify: `src/sdlc/core/models.py:420-428`, `:441-451`; `src/sdlc/workflows/gates.py:74-89`, `:178-234`; `src/sdlc/workflows/feature.py:232-250`; `src/sdlc/workflows/benchmark_host.py:93-102`; `src/sdlc/observability/summary.py:20-30`, `:33-45`; `src/sdlc/core/context.py:46-48`; `src/sdlc/workflows/role_host.py:212-244`; `src/sdlc/stages/architecture/step.py:188`; `src/sdlc/stages/plan/step.py:109`
- Modify (pin amendments): `tests/architecture/test_architecture_slice_contract.py:68`, `tests/plan/test_plan_slice_contract.py:76`
- Test: `tests/calibration/test_calibration_plumbing.py` (new)

**Interfaces:**
- Consumes: `unhinted_ratio` from Task 1.
- Produces, for Task 4:
  - `StageOutcome.plan_drift: float | None` — the per-stage mean unhinted ratio, `None` when unmeasured
  - `StageOutcome.quality_score: float | None` — `record.quality.score`, `None` outside benchmark mode
  - `GateOutcomeSummary.author_model: str | None`
  - `revisable_stage(name, cfg, run_fn, *, author_model: str)` on the `StageContext` Protocol and `RoleHost`

**Context for the implementer:** The judge score cannot ride `GATE_DECIDED` — that event fires from `_on_gate_decided` at the end of `_gate()` (`gates.py:234`), which returns *before* `ctx.judge` is called (`architecture/step.py:190-195`, `plan/step.py:111-116`). It rides `STAGE_ENDED` instead, which `benchmark_host.py:93-102` emits from a `BenchmarkRecord` that **already carries** both `plan_drift` (`benchmarks/models.py:157`) and `quality.score` (`:154`). No new computation reaches the emit — three more kwargs off an object it already holds.

`author_model` must be a *parameter* on the gate path, never instance state, for the reason `tests/test_gate_host.py:44` already documents for `confidence`: wave mode runs `_dev_task` concurrently, so a second gate opening while this one awaits a human would clobber a stashed value.

**Watch the stage-key trap:** `resolve_role_model(cfg, stage)` is keyed by `STAGE_ROLES` (`agents/roles.py:148-163`), whose keys are `"architect"` and `"plan"` — **not** the gate names `"architecture"` and `"plan"`. Do not call `resolve_role_model(cfg, name)` inside `_revisable_stage`; the gate name is the wrong keyspace and `"architecture"` would raise `KeyError`. Both stage steps already compute `resolved_model` (`architecture/step.py:81-85`, `plan/step.py:67-71`) — pass that in.

- [ ] **Step 1: Write the failing tests**

Create `tests/calibration/test_calibration_plumbing.py`:

```python
"""C7 ruling OQ8(a): the three label inputs reach RunSummary.

Before C7 retro could see only fix_attempts. plan_drift lived transiently on
a BenchmarkRecord and reached durable storage only in benchmark mode; the
judge score reached neither summary nor trace. Both now ride STAGE_ENDED,
which is emitted from a record that already carries them.
"""

import inspect
from datetime import UTC, datetime, timedelta

from sdlc.core.models import GateOutcomeSummary, StageOutcome
from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind
from sdlc.workflows.gates import GateHost

T0 = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _ev(seq, kind, stage=None, **data):
    return RunEvent(
        seq=seq,
        at=T0 + timedelta(seconds=seq),
        kind=kind,
        stage=stage,
        data={k: str(v) for k, v in data.items()},
    )


def test_stage_outcome_carries_the_two_new_labels_optionally():
    """Old records validate unchanged -- the fields default to None, which
    means UNMEASURED, not zero."""
    s = StageOutcome(stage="plan", role="planner", outcome="pass", duration_s=1.0)
    assert s.plan_drift is None
    assert s.quality_score is None


def test_gate_outcome_summary_carries_author_model_optionally():
    g = GateOutcomeSummary(
        gate="architecture", round=1, policy="soft", decided_by="policy", approved=True
    )
    assert g.author_model is None


def test_build_run_summary_reads_plan_drift_and_quality_score():
    trace = [
        _ev(
            1,
            RunEventKind.STAGE_ENDED,
            stage="planning",
            role="planner",
            outcome="pass",
            duration_s=1.0,
            fix_attempts=2,
            plan_drift=0.25,
            quality_score=0.8,
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.stages[0].plan_drift == 0.25
    assert s.stages[0].quality_score == 0.8
    assert s.stages[0].fix_attempts == 2


def test_build_run_summary_reads_author_model_off_the_gate_event():
    trace = [
        _ev(
            1,
            RunEventKind.GATE_DECIDED,
            gate="architecture",
            round=1,
            policy="soft",
            decided_by="policy",
            approved="true",
            confidence=0.9,
            author_model="anthropic/claude-x",
        ),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        trace=trace,
        memory_enabled=False,
        memory_watermark=None,
    )
    assert s.gates[0].author_model == "anthropic/claude-x"


def test_a_pre_c7_trace_still_builds():
    """No plan_drift, no quality_score, no author_model keys at all."""
    trace = [
        _ev(1, RunEventKind.STAGE_ENDED, stage="planning", role="planner",
            outcome="pass", duration_s=1.0),
        _ev(2, RunEventKind.GATE_DECIDED, gate="plan", round=1, policy="soft",
            decided_by="human", approved="true"),
        _ev(3, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(
        run_id="r1", mode="greenfield", outcome="deployed:x", trace=trace,
        memory_enabled=False, memory_watermark=None,
    )
    assert s.stages[0].plan_drift is None
    assert s.gates[0].author_model is None


def test_author_model_reaches_the_hook_as_a_parameter():
    """The sibling of test_confidence_reaches_the_hook_as_a_parameter
    (tests/test_gate_host.py:44), for the same wave-mode reason: gates
    interleave, so a stashed value would be clobbered by the next gate to
    open while this one awaits a human."""
    sig = inspect.signature(GateHost._on_gate_decided)
    assert "author_model" in sig.parameters
    assert not hasattr(GateHost(), "_last_gate_author_model")


def test_gate_takes_author_model():
    sig = inspect.signature(GateHost._gate)
    assert "author_model" in sig.parameters


def test_revisable_stage_takes_author_model():
    from sdlc.core.context import StageContext
    from sdlc.workflows.role_host import RoleHost

    assert "author_model" in inspect.signature(RoleHost._revisable_stage).parameters
    assert "author_model" in inspect.signature(StageContext.revisable_stage).parameters


def test_both_proposer_stages_pass_their_resolved_model():
    """The stage-key trap: resolve_role_model is keyed by STAGE_ROLES
    ('architect', 'plan'), not by the gate names ('architecture', 'plan'), so
    _revisable_stage must be HANDED the model rather than resolving it from
    the gate name."""
    import pathlib

    for path in (
        "src/sdlc/stages/architecture/step.py",
        "src/sdlc/stages/plan/step.py",
    ):
        src = pathlib.Path(path).read_text(encoding="utf-8")
        idx = src.find("revisable_stage(")
        assert idx != -1, path
        assert "author_model=resolved_model" in src[idx : idx + 200], path
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/calibration/test_calibration_plumbing.py -q`
Expected: FAIL — `StageOutcome` has no `plan_drift`, `GateHost._gate` has no `author_model` parameter.

- [ ] **Step 3: Extend the two summary models**

In `src/sdlc/core/models.py`, in `StageOutcome` (`:420-428`), after `fix_attempts: int = 0`:

```python
    # C7 (ruling OQ8): realized-outcome label inputs. None = NOT MEASURED,
    # never zero -- an unmeasured stage must produce no calibration sample
    # rather than vote "that went fine".
    plan_drift: float | None = None  # mean unhinted-touch ratio for the stage
    quality_score: float | None = None  # judge score; None outside benchmark mode
```

In `GateOutcomeSummary` (`:441-451`), after `confidence: float | None = None`:

```python
    # C7 (ruling OQ4): the proposer model whose confidence this is. Buckets
    # are per-(gate, model) because calibration is a property of the model,
    # not of the gate. None on pre-C7 records.
    author_model: str | None = None
```

- [ ] **Step 4: Emit the new keys**

In `src/sdlc/workflows/benchmark_host.py`, in `_record` (`:93-102`), extend the `STAGE_ENDED` emit:

```python
    async def _record(self, cfg: PipelineConfig, record: BenchmarkRecord) -> None:
        drift = record.plan_drift
        self._emit(  # type: ignore[attr-defined]
            RunEventKind.STAGE_ENDED,
            stage=record.stage,
            role=record.role,
            outcome=record.outcome.value,
            duration_s=str(record.speed.wall_clock_s),
            fix_attempts=str(record.fix_attempts),
            **({"cost_usd": str(record.cost.usd)} if record.cost.usd is not None else {}),
            **({"plan_drift": str(unhinted_ratio(drift))} if drift is not None else {}),
            **(
                {"quality_score": str(record.quality.score)}
                if record.quality.score is not None
                else {}
            ),
        )
```

Add the import **inside** the existing `workflow.unsafe.imports_passed_through()` block (`benchmark_host.py:15`), beside the `PlanDrift` import already at `:31` — a workflow-file import outside that block is sandboxed and will fail at runtime:

```python
    from ..calibration.labels import unhinted_ratio
```

(`retro/step.py` has no such block — it is a stage step, not a workflow class, and its existing `from ...memory.activities import ReflectInput, reflect` is the convention Task 4 follows there.)

In `src/sdlc/workflows/gates.py`, extend the hook signature (`:74-89`) — keep the whole existing docstring and add the parallel sentence:

```python
    async def _on_gate_decided(
        self,
        name: str,
        round: int,
        policy: GatePolicy,
        decision: GateDecision,
        confidence: float | None = None,
        author_model: str | None = None,
    ) -> None:
        """A gate has been decided, by a human, a policy, or a timeout.

        `confidence` is a PARAMETER, never instance state: gates interleave.
        Wave mode runs _dev_task concurrently (feature.py's asyncio.gather), so
        a second gate opening while this one awaits a human would overwrite a
        stashed value and silently drop RunSummary.gates[].confidence, which
        SC-6's calibration compare reads.

        `author_model` (C7) travels the same way and for the same reason: it
        is half of the calibration bucket key, so a clobbered value would file
        one model's sample under another's evidence.
        """
```

In `_gate` (`:178-187`), add the parameter, and forward it at `:234`:

```python
        confidence: float | None = None,
        author_model: str | None = None,
        default_policy: GatePolicy | None = None,
```

```python
        await self._on_gate_decided(name, round, policy, decision, confidence, author_model)
```

In `src/sdlc/workflows/feature.py`, `_on_gate_decided` (`:232-250`) — mirror the signature and emit the key:

```python
        confidence: float | None = None,
        author_model: str | None = None,
    ) -> None:
        conf = confidence
        self._emit(
            RunEventKind.GATE_DECIDED,
            stage=name,
            gate=name,
            round=str(round),
            policy=policy.value,
            decided_by=decision.decided_by,
            approved=("true" if decision.approved else "false"),
            **({"confidence": str(conf)} if conf is not None else {}),
            **({"author_model": author_model} if author_model else {}),
        )
```

- [ ] **Step 5: Read the new keys in the summary builder**

In `src/sdlc/observability/summary.py`, `_stage_outcome` (`:20-30`):

```python
def _stage_outcome(ev: RunEvent) -> StageOutcome:
    d = ev.data
    cost = d.get("cost_usd")
    drift = d.get("plan_drift")
    quality = d.get("quality_score")
    return StageOutcome(
        stage=ev.stage or d.get("stage", "?"),
        role=d.get("role", "?"),
        outcome=d.get("outcome", "?"),
        duration_s=float(d.get("duration_s", "0")),
        cost_usd=float(cost) if cost is not None else None,
        fix_attempts=int(d.get("fix_attempts", "0")),
        plan_drift=float(drift) if drift is not None else None,
        quality_score=float(quality) if quality is not None else None,
    )
```

and `_gate_outcome` (`:33-45`), after the `confidence` line:

```python
        author_model=d.get("author_model") or None,
```

- [ ] **Step 6: Thread `author_model` through `revisable_stage` and amend the two stubs**

In `src/sdlc/core/context.py` (`:46-48`):

```python
    def revisable_stage(
        self, name: str, cfg: Any, run_fn: Callable[[str | None], Awaitable[Any]], *,
        author_model: str = "",
    ) -> Awaitable[tuple[Any, Any]]: ...
```

In `src/sdlc/workflows/role_host.py`, `_revisable_stage` (`:212-214`):

```python
    async def _revisable_stage(
        self,
        name: str,
        cfg: PipelineConfig,
        run_fn: Callable[[str | None], Awaitable[StageT]],
        *,
        author_model: str = "",
    ) -> tuple[StageT, GateDecision]:
```

and add `author_model=author_model` to **both** `self._gate(...)` calls (the loop call at `:225-232` and the exhausted-rounds call at `:238-243`).

In `src/sdlc/stages/architecture/step.py:188`:

```python
    arch, gate = await ctx.revisable_stage(
        "architecture", cfg, _run_architect, author_model=resolved_model
    )
```

In `src/sdlc/stages/plan/step.py:109`:

```python
    plan_obj, gate = await ctx.revisable_stage(
        "plan", cfg, _run_plan, author_model=resolved_model
    )
```

**Pin amendment (inventory row 11).** In `tests/architecture/test_architecture_slice_contract.py:68`, widen the stub to accept the new keyword — the stub models the Protocol, so it tracks the Protocol:

```python
        async def revisable_stage(
            self, name: str, cfg: Any, run_fn: Any, *, author_model: str = ""
        ) -> tuple[ArchitectureSpec, GateDecision]:
```

Make the identical change at `tests/plan/test_plan_slice_contract.py:76` (return type `tuple[ImplementationPlan, GateDecision]`).

Do **not** also "fix" the `GateDecision(approved=True, ...)` construction in those stubs. It is a pre-existing `extra='ignore'` no-op, out of this plan's scope, and touching it widens the diff a reviewer must gate.

- [ ] **Step 7: Run the new tests**

Run: `pytest tests/calibration/test_calibration_plumbing.py -q`
Expected: PASS, all 9.

- [ ] **Step 8: Run the amended pins and their neighbours**

Run: `pytest tests/architecture/ tests/plan/ tests/test_gate_host.py tests/test_run_summary_build.py tests/test_run_summary_model.py tests/test_observability_export.py -q`
Expected: PASS. A failure in `test_gate_host.py`, `test_run_summary_*`, or `test_observability_export.py` means an "optional" field was not actually optional — **SG-1**.

- [ ] **Step 9: Run the full suite**

Run: `pytest tests/ -q`
Expected: green. Behaviour is unchanged so far: three new trace keys, three new optional model fields, one new keyword argument. Nothing reads them yet.

- [ ] **Step 10: Commit**

```bash
printf '%s\n' \
  'feat(observability): carry the calibration label inputs into RunSummary' \
  '' \
  'Ruling OQ8(a). Retro could previously see only fix_attempts: plan_drift' \
  'lived transiently on a BenchmarkRecord and reached durable storage only' \
  'in benchmark mode, and the judge score reached neither summary nor' \
  'trace. Both now ride the STAGE_ENDED emit, which is built from a record' \
  'that already carries them -- three more kwargs off an object in hand.' \
  '' \
  'The judge score cannot ride GATE_DECIDED: that event fires from' \
  '_on_gate_decided at the end of _gate(), before ctx.judge runs.' \
  '' \
  'author_model (ruling OQ4) travels as a gate parameter rather than' \
  'instance state, for the same wave-mode interleaving reason confidence' \
  'already does -- a clobbered value would file one model'"'"'s sample under' \
  'another'"'"'s evidence. _revisable_stage is handed the model by its caller' \
  'rather than resolving it, because resolve_role_model is keyed by' \
  'STAGE_ROLES ("architect"), not by the gate name ("architecture").' \
  > .git/C7_MSG
git add src/sdlc/core/models.py
git add src/sdlc/core/context.py
git add src/sdlc/workflows/gates.py
git add src/sdlc/workflows/feature.py
git add src/sdlc/workflows/benchmark_host.py
git add src/sdlc/workflows/role_host.py
git add src/sdlc/observability/summary.py
git add src/sdlc/stages/architecture/step.py
git add src/sdlc/stages/plan/step.py
git add tests/architecture/test_architecture_slice_contract.py
git add tests/plan/test_plan_slice_contract.py
git add tests/calibration/test_calibration_plumbing.py
git commit -F .git/C7_MSG
```

---

### Task 4: Retro labels the run's auto-approves and appends samples

**Implements:** spec §4.2.1; rulings OQ1, OQ2, OQ6, OQ9.

**Files:**
- Modify: `src/sdlc/calibration/labels.py` (add `calibration_samples_for`), `src/sdlc/stages/retro/step.py:44-108`
- Test: `tests/calibration/test_retro_calibration_samples.py` (new), plus cases appended to `tests/calibration/test_calibration_labels.py`

**Interfaces:**
- Consumes: `RunSummary` with Task 3's fields; `plan_drift_label`, `fix_attempt_label`, `bucket_key`, `CalibrationSample`, `LabelSource` from Tasks 1 and 3; `record_calibration_samples`, `RecordSamplesInput` from Task 2.
- Produces: `calibration_samples_for(summary: RunSummary, *, max_fix_attempts: int, benchmarking: bool) -> list[CalibrationSample]` — pure.

**Context for the implementer:** `calibration_samples_for` is pure and takes a `RunSummary`, so it is fully testable without a workflow, a Temporal environment, or a stub context. Retro's job is three lines: call it, and if it returned anything, append via the activity inside a `try/except Exception: pass` — the shape retro already uses for `reflect` (`retro/step.py:60-69`), `export_run_artifacts` (`:72-84`) and `apply_session_retention` (`:86-104`).

**Retro's signature does not change** (ruling OQ8), and **nothing is added to `retro.ACTIVITIES`** — the activities belong to `sdlc/calibration/`, which retro imports the way it already imports `reflect`. `tests/retro/test_retro_slice_contract.py:15` pins that list at zero.

**The sample filter is narrower than "every `decided_by == 'policy'` row"** (spec §4.2.1): `GatePolicy.OFF` also synthesizes `decided_by="policy"` (`gates.py:195-198`), and the budget gate emits `GATE_DECIDED` too. Filter on `policy == "soft" and decided_by == "policy" and confidence is not None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/calibration/test_calibration_labels.py`:

```python
# --- calibration_samples_for (Task 4) -------------------------------------

from sdlc.calibration.labels import calibration_samples_for
from sdlc.calibration.models import LabelSource
from sdlc.calibration.verdict import bucket_key
from sdlc.core.models import GateOutcomeSummary, RunSummary, StageOutcome

_T = "2026-09-10T12:00:00+00:00"


def _summary(gates, stages=()) -> RunSummary:
    return RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        terminal_stage="merge",
        started_at=_T,
        ended_at=_T,
        duration_s=1.0,
        stages=list(stages),
        gates=list(gates),
    )


def _auto(gate: str, conf: float, model: str = "m/x") -> GateOutcomeSummary:
    return GateOutcomeSummary(
        gate=gate, round=1, policy="soft", decided_by="policy",
        approved=True, confidence=conf, author_model=model,
    )


def _stage(stage: str, role: str, **kw) -> StageOutcome:
    return StageOutcome(stage=stage, role=role, outcome="pass", duration_s=1.0, **kw)


def test_a_soft_auto_approved_plan_gate_yields_a_drift_labelled_sample():
    s = _summary([_auto("plan", 0.9)], [_stage("planning", "planner", plan_drift=0.25)])
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=False)
    assert len(samples) == 1
    assert samples[0].gate == "plan"
    assert samples[0].confidence == 0.9
    assert samples[0].outcome_label == 0.75
    assert samples[0].bucket_key == bucket_key("m/x", LabelSource.PRODUCTION_PROXY)


def test_an_architecture_gate_is_labelled_from_fix_attempts():
    s = _summary([_auto("architecture", 0.8)], [_stage("code", "dev", fix_attempts=1)])
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=False)
    assert len(samples) == 1
    assert samples[0].outcome_label == 0.5


def test_benchmarking_prefers_the_judge_score_and_tags_the_source():
    """Ruling OQ1 + OQ6: the stronger label wins, and lands in its own bucket."""
    s = _summary(
        [_auto("plan", 0.9)],
        [_stage("planning", "planner", plan_drift=0.9, quality_score=0.85)],
    )
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=True)
    assert samples[0].outcome_label == 0.85
    assert samples[0].bucket_key == bucket_key("m/x", LabelSource.BENCHMARK)


def test_a_human_decided_gate_is_not_a_sample():
    """Only auto-approves are calibration evidence: a human-decided gate has
    no 'would the human have caught it' counterfactual to score against."""
    g = GateOutcomeSummary(
        gate="plan", round=1, policy="soft", decided_by="human",
        approved=True, confidence=0.9, author_model="m/x",
    )
    s = _summary([g], [_stage("planning", "planner", plan_drift=0.0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_an_off_policy_approval_is_not_a_sample():
    """gates.py:195-198 synthesizes decided_by='policy' for OFF gates too. The
    filter must exclude them on purpose, not by accident of having no
    confidence to score."""
    g = GateOutcomeSummary(
        gate="plan", round=1, policy="off", decided_by="policy",
        approved=True, confidence=0.9, author_model="m/x",
    )
    s = _summary([g], [_stage("planning", "planner", plan_drift=0.0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_a_policy_approval_without_confidence_is_not_a_sample():
    g = GateOutcomeSummary(
        gate="plan", round=1, policy="soft", decided_by="policy",
        approved=True, confidence=None, author_model="m/x",
    )
    s = _summary([g], [_stage("planning", "planner", plan_drift=0.0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_the_merge_gate_is_never_labelled():
    """Ruling OQ2. Note the absence of any gate-name branch in the source: a
    merge auto-approve produces no sample because merge has no realized-outcome
    label defined, not because it is named 'merge'."""
    s = _summary([_auto("merge", 0.99)], [_stage("code", "dev", fix_attempts=0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_an_unlabellable_run_yields_nothing():
    """A plan gate with no measured drift anywhere: no sample, rather than a
    1.0 that would vote 'the plan was perfect' on no evidence."""
    s = _summary([_auto("plan", 0.9)], [_stage("planning", "planner")])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_a_pre_c7_gate_row_buckets_as_unknown_and_still_samples():
    g = GateOutcomeSummary(
        gate="plan", round=1, policy="soft", decided_by="policy",
        approved=True, confidence=0.9, author_model=None,
    )
    s = _summary([g], [_stage("planning", "planner", plan_drift=0.0)])
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=False)
    assert samples[0].bucket_key == bucket_key(None, LabelSource.PRODUCTION_PROXY)
```

Create `tests/calibration/test_retro_calibration_samples.py`:

```python
"""C7: retro appends the run's calibration samples -- best-effort, and never
at the cost of the run's outcome."""

from unittest.mock import AsyncMock, patch

import pytest

from sdlc.core.models import (
    GateOutcomeSummary,
    MemoryConfig,
    PipelineConfig,
    RunSummary,
    StageOutcome,
)
from sdlc.stages import retro

_T = "2026-09-10T12:00:00+00:00"


class _StubCtx:
    def __init__(self) -> None:
        self.emitted: list[tuple] = []

    def emit(self, kind, **kwargs) -> None:
        self.emitted.append((kind, kwargs))

    async def retain(self, *a, **k) -> None:
        return None


def _summary(gates=(), stages=()) -> RunSummary:
    return RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        terminal_stage="merge",
        started_at=_T,
        ended_at=_T,
        duration_s=1.0,
        stages=list(stages),
        gates=list(gates),
    )


def _auto_plan_gate() -> GateOutcomeSummary:
    return GateOutcomeSummary(
        gate="plan", round=1, policy="soft", decided_by="policy",
        approved=True, confidence=0.9, author_model="m/x",
    )


@pytest.mark.asyncio
async def test_retro_appends_one_sample_batch():
    """Side-effect budget: exactly ONE ledger activity call per run, carrying
    every sample -- not one call per gate. The other execute_activity calls in
    retro (export, retention) are counted too, so the assertion is on the
    ledger call specifically."""
    cfg = PipelineConfig(memory=MemoryConfig(enabled=False))
    summary = _summary(
        [_auto_plan_gate()],
        [StageOutcome(stage="planning", role="planner", outcome="pass",
                      duration_s=1.0, plan_drift=0.25)],
    )
    with patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as act:
        await retro.step(_StubCtx(), cfg=cfg, summary=summary, session_refs=[], trace=[])

    ledger_calls = [
        c for c in act.await_args_list
        if getattr(c.args[0], "__name__", "") == "record_calibration_samples"
    ]
    assert len(ledger_calls) == 1
    payload = ledger_calls[0].args[1]
    assert len(payload.samples) == 1
    assert payload.samples[0].outcome_label == 0.75


@pytest.mark.asyncio
async def test_retro_skips_the_ledger_when_there_is_nothing_to_record():
    """No auto-approves -> no activity call at all. An empty batch would be a
    pointless round-trip on every human-gated run, which is most of them."""
    cfg = PipelineConfig(memory=MemoryConfig(enabled=False))
    with patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as act:
        await retro.step(_StubCtx(), cfg=cfg, summary=_summary(), session_refs=[], trace=[])

    assert not [
        c for c in act.await_args_list
        if getattr(c.args[0], "__name__", "") == "record_calibration_samples"
    ]


@pytest.mark.asyncio
async def test_a_ledger_failure_does_not_change_the_run_outcome():
    """RETRO-1.4 still holds. A storage outage must not turn a deployed run
    into a failed one."""
    cfg = PipelineConfig(memory=MemoryConfig(enabled=False))
    summary = _summary(
        [_auto_plan_gate()],
        [StageOutcome(stage="planning", role="planner", outcome="pass",
                      duration_s=1.0, plan_drift=0.25)],
    )
    with patch(
        "temporalio.workflow.execute_activity",
        new_callable=AsyncMock,
        side_effect=RuntimeError("ledger down"),
    ):
        await retro.step(_StubCtx(), cfg=cfg, summary=summary, session_refs=[], trace=[])


def test_retro_owns_no_activities():
    """The ledger activities belong to sdlc/calibration/, which retro imports
    the way it already imports reflect. RETRO's slice list stays empty."""
    assert len(retro.ACTIVITIES) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/calibration/test_calibration_labels.py tests/calibration/test_retro_calibration_samples.py -q`
Expected: FAIL — `ImportError: cannot import name 'calibration_samples_for'`.

- [ ] **Step 3: Implement `calibration_samples_for`**

Append to `src/sdlc/calibration/labels.py`:

```python
# --- run-level labelling ---------------------------------------------------

# Ruling OQ2: `merge` is deliberately absent. It has no attributable
# post-merge outcome signal (spec 3), so a merge auto-approve produces no
# sample, its bucket never reaches the floor, and its SOFT auto-approve
# therefore never fires. That is a consequence of the data, not a branch on
# the gate name -- do not add one.
_DRIFT_GATES = frozenset({"plan"})
_FIX_ATTEMPT_GATES = frozenset({"architecture"})


def _judge_label(summary: RunSummary) -> float | None:
    scores = [s.quality_score for s in summary.stages if s.quality_score is not None]
    if not scores:
        return None
    return max(0.0, min(1.0, sum(scores) / len(scores)))


def calibration_samples_for(
    summary: RunSummary, *, max_fix_attempts: int, benchmarking: bool
) -> list[CalibrationSample]:
    """Pure. Every SOFT gate this run auto-approved on a self-reported
    confidence, scored against what the rest of the run then did.

    The filter is narrower than "decided_by == 'policy'": GatePolicy.OFF
    synthesizes that too (gates.py:195-198), and the budget gate emits its own
    GATE_DECIDED. Only a SOFT gate that had a confidence to honour is
    evidence about whether honouring confidence works.
    """
    source = LabelSource.BENCHMARK if benchmarking else LabelSource.PRODUCTION_PROXY
    judged = _judge_label(summary) if benchmarking else None
    drift = plan_drift_label([s.plan_drift for s in summary.stages if s.plan_drift is not None])
    fixes = fix_attempt_label([s.fix_attempts for s in summary.stages], max_fix_attempts)

    out: list[CalibrationSample] = []
    for g in summary.gates:
        if g.policy != "soft" or g.decided_by != "policy" or g.confidence is None:
            continue
        if g.gate in _DRIFT_GATES:
            label = judged if judged is not None else drift
        elif g.gate in _FIX_ATTEMPT_GATES:
            label = judged if judged is not None else fixes
        else:
            label = None
        if label is None:
            continue
        out.append(
            CalibrationSample(
                gate=g.gate,
                bucket_key=bucket_key(g.author_model, source),
                confidence=g.confidence,
                outcome_label=label,
                run_id=summary.run_id,
            )
        )
    return out
```

Extend that file's imports to cover the new names:

```python
from ..core.models import RunSummary
from ..stages.plan.models import PlanDrift
from .models import CalibrationSample, LabelSource
from .verdict import bucket_key
```

Add `calibration_samples_for` to `src/sdlc/calibration/__init__.py`'s import line and `__all__`.

- [ ] **Step 4: Wire retro**

In `src/sdlc/stages/retro/step.py`, add to the imports:

```python
from ...calibration.activities import RecordSamplesInput, record_calibration_samples
from ...calibration.labels import calibration_samples_for
```

and add an activity config beside the existing two:

```python
_LEDGER_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(maximum_attempts=3),
)
```

Insert this block after the `apply_session_retention` block (`:86-104`), still inside the outer `try`:

```python
        # C7: score this run's SOFT auto-approves against what actually
        # happened, so the next run's confidence has something behind it.
        # Best-effort like the export above -- a ledger outage must never
        # change a run's outcome (RETRO-1.4).
        try:
            samples = calibration_samples_for(
                summary,
                max_fix_attempts=cfg.max_fix_attempts,
                benchmarking=cfg.benchmark.case_id is not None,
            )
            if samples:
                await workflow.execute_activity(
                    record_calibration_samples,
                    RecordSamplesInput(samples=samples),
                    **_LEDGER_ACT,
                )
        except Exception:
            pass
```

- [ ] **Step 5: Run the new tests**

Run: `pytest tests/calibration/ -q`
Expected: PASS, all 54.

- [ ] **Step 6: Run the retro suite**

Run: `pytest tests/retro/ -q`
Expected: PASS. A failure in `test_retro_step_never_raises_on_activity_failure` or `test_slice_exports_step_and_activities` means the best-effort envelope or the `ACTIVITIES` rule was broken — **SG-1**.

- [ ] **Step 7: Run the full suite**

Run: `pytest tests/ -q`
Expected: green. The ledger now fills, but nothing reads it — gate behaviour is still unchanged.

- [ ] **Step 8: Commit**

```bash
printf '%s\n' \
  'feat(retro): label the run'"'"'s soft auto-approves into the ledger' \
  '' \
  'calibration_samples_for is pure over a RunSummary: every SOFT gate the' \
  'run auto-approved on a self-reported confidence, scored against what' \
  'the rest of the run then did. Retro appends the batch through the' \
  'ledger activity inside the same best-effort envelope it already uses' \
  'for reflect, export and retention -- RETRO-1.4 holds, a ledger outage' \
  'never changes a run outcome.' \
  '' \
  'The filter is narrower than decided_by == "policy": GatePolicy.OFF' \
  'synthesizes that too, and the budget gate emits its own GATE_DECIDED.' \
  'Only a SOFT gate that had a confidence to honour is evidence about' \
  'whether honouring confidence works.' \
  '' \
  'merge is absent from the label maps (ruling OQ2) rather than special-' \
  'cased by name: it has no attributable post-merge signal, so it yields' \
  'no samples and its bucket never reaches the floor.' \
  > .git/C7_MSG
git add src/sdlc/calibration
git add src/sdlc/stages/retro/step.py
git add tests/calibration/test_calibration_labels.py
git add tests/calibration/test_retro_calibration_samples.py
git commit -F .git/C7_MSG
```

---

### Task 5: The gates consult the ledger

**Implements:** spec §4.2.4, §4.2.5, §4.3; rulings OQ2, OQ7.

**Files:**
- Modify: `src/sdlc/workflows/role_host.py:55-75` (delete), `:212-244`; `src/sdlc/stages/merge/step.py:161-177` (delete), `:466-490`
- Modify (pin amendments): `tests/test_soft_gate_auto_approval.py`
- Test: `tests/calibration/test_gate_requires_calibration.py` (new)

**Interfaces:**
- Consumes: `auto_decision_for`, `bucket_key`, `INSUFFICIENT`, `LabelSource` from Task 1; `calibration_verdict`, `VerdictInput` from Task 2.
- Produces: nothing later tasks consume — this is the behaviour change.

**Context for the implementer:** This is the only task that changes runtime gate behaviour, and it changes it in one direction only: an auto-approve that would have fired may now not fire. Nothing that waited before can start skipping.

The verdict read is **conditioned on SOFT-with-confidence** (spec §4.2.4). HARD gates, OFF gates, `None`-confidence rounds and the exhausted-rounds final gate must not perform the activity call at all — that is what keeps §4.3's "untouched" claim a property of the call site rather than a claim about `auto_decision_for`'s internals. **SG-4** guards it.

A lookup failure resolves to `INSUFFICIENT`, never an exception: the retry policy makes an outage rare, and when it happens the gate waits for a human rather than failing the stage.

Merge uses its own `_exec_activity` helper (`merge/step.py:232-238`), which already handles the in-workflow / out-of-workflow split — do not call `workflow.execute_activity` directly from the merge step.

- [ ] **Step 1: Write the failing tests**

Create `tests/calibration/test_gate_requires_calibration.py`:

```python
"""C7: the gate paths consult the ledger before honouring a confidence.

This is audit row 8's fix at the two call sites. The tests are source-level
where they pin wiring and behavioural where they pin the decision, because
the decision itself is already covered by test_calibration_decision.py.
"""

import pathlib

ROLE_HOST = pathlib.Path("src/sdlc/workflows/role_host.py")
MERGE = pathlib.Path("src/sdlc/stages/merge/step.py")


def test_the_rule_has_exactly_one_home():
    """Before C7 this rule existed twice, logically identical. Plumbing a new
    conjunct through two copies is how they drift apart again."""
    assert "def auto_decision_for(" not in ROLE_HOST.read_text(encoding="utf-8")
    assert "def _auto_decision_for(" not in ROLE_HOST.read_text(encoding="utf-8")
    assert "def _auto_decision_for(" not in MERGE.read_text(encoding="utf-8")


def test_both_call_sites_import_the_shared_rule():
    for path in (ROLE_HOST, MERGE):
        src = path.read_text(encoding="utf-8")
        assert "auto_decision_for" in src, path
        assert "calibration" in src, path


def test_revisable_stage_conditions_the_lookup_on_soft_with_confidence():
    """SG-4: HARD, OFF and None-confidence rounds must not pay for an
    activity call, and must not gain a dependency on the ledger being up."""
    src = ROLE_HOST.read_text(encoding="utf-8")
    idx = src.find("async def _revisable_stage")
    assert idx != -1
    body = src[idx:]
    assert "confidence is not None" in body
    assert "GatePolicy.SOFT" in body


def test_revisable_stage_still_passes_the_auto_decision_into_the_gate():
    src = ROLE_HOST.read_text(encoding="utf-8")
    assert "auto_decision=auto" in src


def test_no_gate_name_is_special_cased():
    """SG-3, ruling OQ2. Merge stops auto-approving because it is never
    labelled, not because the code knows its name."""
    for path in (ROLE_HOST, MERGE, pathlib.Path("src/sdlc/calibration/decision.py")):
        src = path.read_text(encoding="utf-8")
        assert '== "merge"' not in src, path


def test_a_lookup_failure_degrades_to_insufficient_not_an_exception():
    src = ROLE_HOST.read_text(encoding="utf-8")
    idx = src.find("_calibration_verdict")
    assert idx != -1
    assert "INSUFFICIENT" in src[idx : idx + 900]
    assert "except Exception" in src[idx : idx + 900]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/calibration/test_gate_requires_calibration.py -q`
Expected: FAIL — `role_host.py` still defines `_auto_decision_for`.

- [ ] **Step 3: Rewrite `role_host.py`'s auto-decision path**

Delete `_auto_decision_for` entirely (`:55-75`). Add to the `workflow.unsafe.imports_passed_through()` block:

```python
    from ..calibration.activities import VerdictInput, calibration_verdict
    from ..calibration.decision import auto_decision_for
    from ..calibration.models import INSUFFICIENT, CalibrationVerdict, LabelSource
    from ..calibration.verdict import bucket_key
```

Add an activity config beside `PRICE_ACT`:

```python
# C7: a calibration read that cannot answer must not fail the stage. Three
# attempts, then the caller degrades to INSUFFICIENT and the human waits.
CALIB_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=3)
)
```

Add this method to `RoleHost`, above `_revisable_stage`:

```python
    async def _calibration_verdict(
        self, cfg: PipelineConfig, gate: str, author_model: str
    ) -> CalibrationVerdict:
        """C7. A lookup that cannot answer is INSUFFICIENT, not an exception:
        the gate then waits for a human, which is the same fail-safe direction
        as a None confidence. A storage outage must not fail the run."""
        source = (
            LabelSource.BENCHMARK
            if cfg.benchmark.case_id is not None
            else LabelSource.PRODUCTION_PROXY
        )
        try:
            return await workflow.execute_activity(
                calibration_verdict,
                VerdictInput(gate=gate, bucket_key=bucket_key(author_model, source)),
                **CALIB_ACT,
            )
        except Exception:
            return INSUFFICIENT
```

Replace the body of the `_revisable_stage` loop (`:222-235`) with:

```python
        for round in range(1, cfg.max_gate_rounds + 1):
            artifact = await run_fn(guidance)
            confidence = getattr(artifact, "confidence", None)
            # SG-4: HARD, OFF and None-confidence rounds never reach the
            # ledger -- they cannot auto-approve regardless, so a read would
            # buy a dependency on storage for nothing.
            auto = None
            if confidence is not None and cfg.gates.get(name, GateConfig()).policy is GatePolicy.SOFT:
                calibration = await self._calibration_verdict(cfg, name, author_model)
                auto = auto_decision_for(name, cfg, confidence, calibration)
            decision = await self._gate(  # type: ignore[attr-defined]
                name,
                cfg.gate_settings(),
                auto_decision=auto,
                round=round,
                context=GateContext(spec_summary=_spec_summary(artifact)),
                confidence=confidence,
                author_model=author_model,
            )
            if decision.outcome is not GateOutcome.REVISE:
                return artifact, decision
            guidance = decision.guidance or decision.comments
```

Extend the method docstring's FR-301 sentence:

```
        Past that, escalate to a final human gate (the configured policy still
        applies, but no auto_decision is passed, so SOFT also waits) (FR-301).
        C7: even inside the loop, SOFT auto-approval additionally requires a
        `calibrated` verdict for this gate's (gate, author_model) bucket —
        confidence alone no longer ends the review.
```

- [ ] **Step 4: Rewrite the merge soft path**

In `src/sdlc/stages/merge/step.py`, delete `_auto_decision_for` (`:161-177`). Add to the imports:

```python
from ...calibration.activities import VerdictInput, calibration_verdict
from ...calibration.decision import auto_decision_for
from ...calibration.models import INSUFFICIENT, LabelSource
from ...calibration.verdict import bucket_key
```

Replace the consult at `:483-490` with:

```python
            verdict: MergeVerdict = getattr(role_output, "output", role_output)
            confidence = verdict.confidence if verdict.approve else None
            auto = None
            if confidence is not None:
                # Ruling OQ2: merge samples are appended but never labelled,
                # so this resolves to insufficient_data and the human gate
                # below always fires. No branch on the gate name (SG-3) --
                # the behaviour comes from the ledger being empty for merge.
                source = (
                    LabelSource.BENCHMARK
                    if cfg.benchmark.case_id is not None
                    else LabelSource.PRODUCTION_PROXY
                )
                try:
                    calibration = await _exec_activity(
                        calibration_verdict,
                        VerdictInput(
                            gate="merge", bucket_key=bucket_key(merge_model, source)
                        ),
                        **_ACT,
                    )
                except Exception:
                    calibration = INSUFFICIENT
                auto = auto_decision_for("merge", cfg, confidence, calibration)
            if auto is None:
                gate = await ctx.gate(
                    "merge", cfg.gate_settings(), context=GateContext(checks=gate_report.checks)
                )
                if not gate.approved:
                    return "rejected:merge:soft-verdict"
```

- [ ] **Step 5: Run the new tests**

Run: `pytest tests/calibration/test_gate_requires_calibration.py -q`
Expected: PASS, all 6.

- [ ] **Step 6: Amend the ten `test_soft_gate_auto_approval.py` pins**

Run: `pytest tests/test_soft_gate_auto_approval.py -q`
Expected: **ten** failures (inventory rows 1-10) — an import error plus the source needles. Any *eleventh* failure anywhere is **SG-1**.

Replace the import at `:7`:

```python
from sdlc.calibration.decision import auto_decision_for
from sdlc.calibration.models import INSUFFICIENT, CalibrationVerdict
```

Add below `_cfg`:

```python
# C7: the rule now takes a calibration verdict, with no default. These tests
# predate C7 and assert the confidence-vs-threshold half of the rule, so they
# supply a calibrated bucket and keep asserting exactly what they always did.
# The new conjunct has its own truth table in
# tests/calibration/test_calibration_decision.py.
CALIBRATED = CalibrationVerdict(verdict="calibrated", n=25, agreement_rate=0.9)
```

Replace each of the seven call sites (`:15`, `:22`, `:27`, `:33`, `:38`, `:43`, `:48`) with the same call plus the fourth argument, renamed to the un-underscored function. For example, `:14-18` becomes:

```python
def test_soft_high_confidence_auto_approves():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED)
    assert decision is not None
    assert decision.outcome is GateOutcome.APPROVE
    assert decision.decided_by == "policy"
```

Apply the same mechanical change to the other six, changing nothing else about them.

Then amend the two source needles. At `:60`:

```python
def test_revisable_stage_passes_auto_decision():
    """C7 moved the rule to sdlc/calibration/decision.py and dropped the
    leading underscore (it is a shared module API now, not a file-private
    helper). What this pins is unchanged: _revisable_stage must COMPUTE the
    auto-decision and PASS it to _gate, not just call the rule."""
    src = SRC.read_text(encoding="utf-8")
    assert "auto_decision_for(" in src, (
        "_revisable_stage must call auto_decision_for to compute an "
        "auto_decision from the artifact's confidence (FR-301)"
    )
    assert "auto_decision=auto" in src, (
        "_revisable_stage must pass auto_decision=auto into self._gate()"
    )
```

At `:72`:

```python
def test_merge_soft_path_uses_auto_decision_for():
    """C7: same needle without the underscore, and a wider window -- the soft
    path now fetches a calibration verdict between the MergeVerdict call and
    the decision, so the two are further apart than 700 characters."""
    src = MERGE_SRC.read_text(encoding="utf-8")
    idx = src.rfind('"merge_verdict"')
    assert idx != -1, "merge stage no longer calls merge_verdict"
    tail = src[idx : idx + 1400]
    assert "auto_decision_for(" in tail, (
        "merge gate's soft path must route through auto_decision_for so "
        "verdict.confidence is checked against cfg.gates['merge'].threshold "
        "and against the bucket's calibration, not just verdict.approve"
    )
```

**Do not** satisfy these by re-adding a local `_auto_decision_for` to either file. One home is the deliverable; **SG-2** covers it.

- [ ] **Step 7: Re-run the amended pins**

Run: `pytest tests/test_soft_gate_auto_approval.py -q`
Expected: PASS, all 9.

- [ ] **Step 8: Run the full suite**

Run: `pytest tests/ -q`
Expected: green. Any failure not in the Pin-Amendment Inventory is **SG-1** — in particular a merge or architecture integration test that changes outcome means an auto-approve that used to fire has stopped firing somewhere the plan did not model.

- [ ] **Step 9: Commit**

```bash
printf '%s\n' \
  'feat(gates): require a calibrated bucket before honouring confidence' \
  '' \
  'Audit row 8'"'"'s fix. A SOFT gate'"'"'s auto-approve now needs both' \
  'confidence >= threshold AND a calibrated verdict for the gate'"'"'s' \
  '(gate, author_model) bucket. Uncalibrated, insufficient_data, and a' \
  'failed lookup all resolve the same way: no auto-decision, the human' \
  'waits.' \
  '' \
  'The two logically identical copies of the rule collapse into' \
  'calibration/decision.py. Plumbing a new conjunct through two copies is' \
  'how they drift apart again.' \
  '' \
  'The ledger read is conditioned on SOFT-with-confidence, so HARD, OFF,' \
  'None-confidence rounds and the exhausted-rounds final gate neither pay' \
  'for the activity call nor gain a dependency on storage being up.' \
  '' \
  'Cold start is expected: every bucket begins insufficient_data, so soft' \
  'gates wait for a human until the ledger fills to MIN_SAMPLES. Merge' \
  'stays there permanently because it is never labelled (ruling OQ2) --' \
  'a consequence of the data, not a branch on the gate name.' \
  > .git/C7_MSG
git add src/sdlc/workflows/role_host.py
git add src/sdlc/stages/merge/step.py
git add tests/test_soft_gate_auto_approval.py
git add tests/calibration/test_gate_requires_calibration.py
git commit -F .git/C7_MSG
```

---

### Task 6: Contract deltas

**Implements:** spec §4.3, §6.

**Files:**
- Modify: `src/sdlc/stages/merge/merge.md`, `src/sdlc/stages/retro/retro.md`, `src/sdlc/calibration/AGENTS.md` (create)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

**Context for the implementer:** These land last because this is the commit at which their statements become true. Check the existing clause numbering in each file first (`grep -n '^### '`) and continue the sequence — do not guess a number.

- [ ] **Step 1: Find the next clause numbers**

Run: `grep -n '^### ' src/sdlc/stages/merge/merge.md src/sdlc/stages/retro/retro.md`
Record the highest clause in each file; the new clauses take the next integer.

- [ ] **Step 2: Add the merge clause**

Append to `src/sdlc/stages/merge/merge.md` after its last clause (substitute the real number for `N`):

```markdown
### MERGE-1.N
The MergeVerdict's `confidence` can no longer skip the human merge gate on its own. Under SOFT policy the soft path fetches a `CalibrationVerdict` for the `(merge, author_model|source)` bucket (`sdlc/calibration/`) and auto-approves only when the bucket is `calibrated` **and** the confidence clears the configured threshold. The merge bucket is never labelled — there is no attributable post-merge outcome signal in this codebase, and the deploy stage is off by default and unlinked to the gate decision — so in practice the merge gate always waits for a human under SOFT. That is a property of the ledger being empty for `merge`, not a rule keyed on the gate's name; adding such a rule would make it editable away. [C7]
```

- [ ] **Step 3: Add the retro clause**

Append to `src/sdlc/stages/retro/retro.md` after its last clause:

```markdown
### RETRO-1.N
Retro scores the run's own SOFT auto-approvals. For every gate in `RunSummary.gates` with `policy == "soft"`, `decided_by == "policy"` and a non-`None` confidence, it computes a realized-outcome label from the run's retained signals — plan-drift ratio for the plan gate, capped fix-attempt ratio for the architecture gate, the judge score in preference to either when benchmarking — and appends `(gate, bucket_key, confidence, outcome_label)` to the calibration ledger. Best-effort like every other retro side effect: a ledger outage is swallowed and the run's outcome is unchanged (RETRO-1.4). Gates a human decided are not evidence, and neither are OFF-policy approvals, which carry `decided_by == "policy"` too. [C7]
```

- [ ] **Step 4: Add the package's AGENTS.md**

Create `src/sdlc/calibration/AGENTS.md`:

```markdown
# calibration/ — editing rules

This package exists because of audit row 8: a proposer's self-reported
`confidence` could skip a human gate with nothing behind it. See
`docs/superpowers/specs/2026-09-10-c7-confidence-gate-design.md`.

**`auto_decision_for` takes the calibration verdict as a required parameter.**
Do not give it a default. A default makes "no evidence was fetched"
indistinguishable from "the evidence passed" — the same defect, one layer up.

**`insufficient_data` is not an error state.** Cold-start buckets, unknown
models, and failed lookups all resolve to it, and it is treated exactly like
`uncalibrated` at the decision. Never collapse it into either neighbour.

**Never pool `LabelSource` populations.** The source is folded into
`bucket_key` so pooling requires building a different key on purpose. A
judge-backed label and a proxy-backed label are not the same measurement.

**No gate name is special-cased.** The merge gate does not auto-approve
because it is never labelled, not because any code knows its name. Keep it
that way — a named rule is a rule someone can delete.

**`labels.py`, `verdict.py`, `decision.py` and `models.py` are pure.** No
`temporalio`, no I/O, no `ctx`. SQLite lives in `store.py`, reached only
through `activities.py`.

**The agreement constants are a starting position.** `THRESHOLD` and
`EPSILON` are inherited from the rubric-judge loop, which tuned them against
a different population (ruling OQ9(3)). Re-derive them from real collected
samples; do not treat the current values as settled.
```

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -q`
Expected: green. Some repos pin contract-clause counts; if a clause test fails, it is an expected consequence of adding a clause — amend it with a stated reason, and note the amendment to the orchestrator as an addition to the Pin-Amendment Inventory.

- [ ] **Step 6: Commit**

```bash
printf '%s\n' \
  'docs(contracts): state the calibration requirement in the slice contracts' \
  '' \
  'MERGE and RETRO clauses for what C7 changed, plus an AGENTS.md for the' \
  'new package covering the four invariants a future editor is most likely' \
  'to erode: the required verdict parameter, insufficient_data as a real' \
  'state rather than an error, the never-pooled label sources, and the' \
  'absence of any gate-name special case.' \
  > .git/C7_MSG
git add src/sdlc/stages/merge/merge.md
git add src/sdlc/stages/retro/retro.md
git add src/sdlc/calibration/AGENTS.md
git commit -F .git/C7_MSG
```

---

## Verification Checklist

Run before declaring the branch finished. Evidence before assertions — paste the actual output, do not assert from memory.

- [ ] `pytest tests/ -q` — green, count compared against the Task 0 baseline (expect +~70 tests)
- [ ] `ruff check src/ tests/` and `ruff format --check src/ tests/` — clean
- [ ] `mypy src/` — no new errors versus baseline
- [ ] `git log --format='%s%n%b' origin/main..HEAD | grep -i "co-authored\|claude-session\|generated with"` — **no output**. Any hit means an attribution trailer slipped in; rewrite the message before the branch is integrated.
- [ ] `grep -rn "def _auto_decision_for" src/` — **no output**. Both copies are gone; the rule has one home.
- [ ] `grep -rn '== "merge"' src/sdlc/calibration/ src/sdlc/workflows/role_host.py` — **no output** (SG-3). Merge's behaviour comes from the data.
- [ ] `grep -rn "calibration" src/sdlc/worker.py` — both activities registered. An unregistered activity hangs a workflow until timeout instead of failing loudly.
- [ ] `python -c "import inspect, sdlc.calibration.decision as d; print(inspect.signature(d.auto_decision_for))"` — the `calibration` parameter has **no default**.
- [ ] All **11** inventory pins are amended, none deleted: `tests/test_soft_gate_auto_approval.py` rows 1-10 (Task 5 Step 6), the two `revisable_stage` stubs in row 11 (Task 3 Step 6). If you amended anything else, it was outside the inventory — report it as an SG-1 that was cleared, with the reason.
- [ ] Spec §4.2's five pieces all have a home: labelling → Task 4; ledger storage → Task 2; `bucket_key` → Tasks 1 and 3; the verdict lookup → Tasks 2 and 5; the de-duplication → Task 5.
- [ ] All nine rulings in spec §6 have a home: OQ1 → Task 4 (`source` tagging); OQ2 → Task 4 (`_DRIFT_GATES`/`_FIX_ATTEMPT_GATES` exclude merge) and Task 6 (MERGE clause); OQ3 → Task 1 (`MIN_SAMPLES`); OQ4 → Tasks 1 and 3 (`bucket_key`, `author_model`); OQ5 → Tasks 1 and 2 (`WINDOW`, `recent`); OQ6 → Task 1 (source folded into the key); OQ7 → Task 1 (binary check in `decision.py`); OQ8 → Task 3 (`STAGE_ENDED`/`RunSummary`); OQ9 → Task 1 (`labels.py`, the constants).
