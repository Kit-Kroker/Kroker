# E-33 Per-Role Cost Attribution + Run Budget Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture every model call's tokens/dollars, attribute them per role in `RunSummary`/reports/benchmark records, and gate the run on a configurable USD budget through the existing FR-301/FR-302 gate machinery.

**Architecture:** A single workflow-side egress helper (`_run_role`) wraps all 8 proposer `t_X.run()` call sites, reading the until-now-discarded `result.usage()`; harness dollars join through the same accumulator in `_dev_task`. Token→USD conversion runs in a `price_usage` activity (genai-prices) so dollars are replay-deterministic — required because the budget gate branches on them. A `MODEL_USAGE` trace event feeds the retro-stage role rollup; the budget gate reuses `_gate` with `(gate="budget", round=N)` identity.

**Tech Stack:** Python 3.12, Temporal (`temporalio`), pydantic-ai 2.x (`TemporalAgent`), `genai-prices` (Pydantic's price tables), pytest + `WorkflowEnvironment.start_time_skipping`.

**Spec:** `docs/superpowers/specs/2026-07-23-per-role-cost-attribution-design.md`

## Global Constraints

- Workflow code stays deterministic: **no `genai_prices` import, no I/O in `feature.py`** — pricing only via `execute_activity(price_usage, ...)`.
- `price_usage` / `compute_price` **never raise for a pricing miss** — unknown model → `None`. Tokens are never discarded because pricing failed.
- The `_run_role` pricing call is wrapped in `try/except Exception` — pricing *infrastructure* failure must not fail a stage either (`usd = None`).
- Budget gate policy defaults to **HARD regardless of `cfg.default_gate_policy`** (setting a budget is the opt-in); overridable via `cfg.gates["budget"]`.
- Approve grants **one more increment**: `threshold += cfg.run_budget_usd`. Reject/timeout → terminal `"rejected:budget"` — and **retro must still run** (the `_BudgetRejected` catch sits in `run()`, before `_retro`).
- `REVISE` on the budget gate is treated as reject (nothing to revise).
- `RunEvent.data` is a **flat `str -> str` map**: stringify every number at emit; omit `cost_usd` key when `None` (existing pattern at `feature.py:281`).
- `_check_budget` is only called from **serial** points (stage boundaries + the task loop after merges), never inside `_dev_task` — wave-mode `asyncio.gather` must not race gate rounds.
- Research *provider* spend (Tavily fees) stays stage-scoped — out of E-33 (spec §4).
- New config knob is `run_budget_usd: float = 0.0` — `0.0` = off, matching the `coverage_threshold` opt-in pattern.
- Line style: match the repo — ~79-col, module docstrings explaining the *why*, comments referencing E-/FR- numbers.
- Run the full suite (`python -m pytest -q`) before the final task; every existing test must stay green.

---

### Task 0: Branch

- [ ] **Step 1: Create the feature branch**

```bash
git checkout -b feat/e-33-cost-attribution
```

---

### Task 1: `RoleUsage` model, config knob, `RunSummary` fields, pure merge helper

**Files:**
- Modify: `src/sdlc/models.py` (three edits: `PipelineConfig`, new `RoleUsage`, `RunSummary`)
- Create: `src/sdlc/observability/usage.py`
- Test: `tests/test_role_usage.py`

**Interfaces:**
- Produces: `RoleUsage` (pydantic model, fields exactly as below), `PipelineConfig.run_budget_usd: float`, `RunSummary.roles: list[RoleUsage]`, `RunSummary.budget_usd: float | None`, `RunSummary.budget_crossings: int`, and `merge_usage(bag, *, model, input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0, cost_usd=None) -> None` in `sdlc.observability.usage`. Later tasks import all of these by these exact names.

- [ ] **Step 1: Write the failing test**

Create `tests/test_role_usage.py`:

```python
"""E-33: RoleUsage accumulation semantics + RunSummary/config fields."""
from sdlc.models import PipelineConfig, RoleUsage, RunSummary
from sdlc.observability.usage import merge_usage


def test_role_usage_defaults():
    u = RoleUsage(role="architect", model="anthropic:claude-opus-4-8")
    assert u.calls == 0
    assert u.input_tokens == 0
    assert u.cost_usd is None       # None = no priced call yet


def test_merge_usage_accumulates_tokens_and_calls():
    u = RoleUsage(role="qa", model="m1")
    merge_usage(u, model="m1", input_tokens=100, output_tokens=10)
    merge_usage(u, model="m2", input_tokens=50, output_tokens=5,
                cache_read_tokens=7, cache_write_tokens=3)
    assert u.calls == 2
    assert u.input_tokens == 150
    assert u.output_tokens == 15
    assert u.cache_read_tokens == 7
    assert u.cache_write_tokens == 3
    assert u.model == "m2"          # last model seen wins
    assert u.cost_usd is None       # no priced call → stays None


def test_merge_usage_prices_sum_and_none_never_zeroes():
    u = RoleUsage(role="dev", model="m")
    merge_usage(u, model="m", cost_usd=0.5)
    merge_usage(u, model="m", cost_usd=None)   # unpriced call
    merge_usage(u, model="m", cost_usd=0.25)
    assert u.cost_usd == 0.75


def test_pipeline_config_budget_defaults_off():
    assert PipelineConfig().run_budget_usd == 0.0


def test_run_summary_carries_roles_and_budget():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    s = RunSummary(run_id="r1", mode="greenfield", outcome="deployed:ok",
                   terminal_stage="deploy", started_at=now, ended_at=now,
                   duration_s=0.0)
    assert s.roles == []
    assert s.budget_usd is None
    assert s.budget_crossings == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_role_usage.py -v`
Expected: FAIL — `ImportError: cannot import name 'RoleUsage'`.

- [ ] **Step 3: Add `RoleUsage` + `RunSummary` fields to `src/sdlc/models.py`**

Insert directly above `class StageOutcome` (models.py, near line 617):

```python
class RoleUsage(BaseModel):
    """One role's accumulated model spend across the run (E-33).

    cost_usd None is load-bearing: tokens are facts from the run; dollars
    are a lookup that can fail. A pricing miss must never discard tokens,
    so the field stays None until the first successfully priced call."""
    role: str                       # "architect", "dev", "clarify", ...
    model: str                      # last model seen for the role
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
```

In `class RunSummary`, after the `gates:` line add:

```python
    roles: list[RoleUsage] = Field(default_factory=list)   # E-33 rollup
```

and after the `cost_usd_total:` line add:

```python
    budget_usd: float | None = None     # configured run budget; None = off
    budget_crossings: int = 0           # budget-gate rounds raised (E-33)
```

- [ ] **Step 4: Add the config knob to `PipelineConfig`**

Directly under the `coverage_threshold` field block (models.py:611-614) add:

```python
    run_budget_usd: float = Field(default=0.0, ge=0.0)
    # E-33/FR-701: run-level USD budget. 0.0 = off (the coverage_threshold
    # opt-in pattern). When crossed, the workflow raises a hard "budget"
    # gate; approve grants one more increment of this amount.
```

- [ ] **Step 5: Create `src/sdlc/observability/usage.py`**

```python
"""Pure RoleUsage accumulation (E-33). No I/O, no temporalio: shared by the
workflow's in-state accumulator and the retro-stage trace rollup, and unit-
testable outside the workflow sandbox."""
from __future__ import annotations

from ..models import RoleUsage


def merge_usage(bag: RoleUsage, *, model: str,
                input_tokens: int = 0, output_tokens: int = 0,
                cache_read_tokens: int = 0, cache_write_tokens: int = 0,
                cost_usd: float | None = None) -> None:
    """Fold one model call into a role's bag. cost_usd=None (unpriced call)
    leaves bag.cost_usd untouched — never zeroes an existing sum."""
    bag.model = model or bag.model
    bag.calls += 1
    bag.input_tokens += input_tokens
    bag.output_tokens += output_tokens
    bag.cache_read_tokens += cache_read_tokens
    bag.cache_write_tokens += cache_write_tokens
    if cost_usd is not None:
        bag.cost_usd = (bag.cost_usd or 0.0) + cost_usd
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_role_usage.py tests/test_run_summary_model.py -v`
Expected: all PASS (the existing `test_run_summary_model.py` proves no regression to `RunSummary`).

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/models.py src/sdlc/observability/usage.py tests/test_role_usage.py
git commit -m "feat(models): RoleUsage + run_budget_usd + RunSummary role/budget fields (E-33)"
```

---

### Task 2: `price_usage` activity (genai-prices), dependency, worker + fakes registration

**Files:**
- Create: `src/sdlc/pricing.py`
- Modify: `pyproject.toml` (dependencies list, line 5-14)
- Modify: `src/sdlc/worker.py` (import + activities list)
- Modify: `tests/fakes/fake_activities.py` (append to `GIT_FAKES`)
- Test: `tests/test_price_usage.py`

**Interfaces:**
- Produces: `PriceUsageInput(model: str, input_tokens: int = 0, output_tokens: int = 0, cache_read_tokens: int = 0, cache_write_tokens: int = 0)`, pure `compute_price(inp) -> float | None`, and activity `price_usage(inp: PriceUsageInput) -> float | None` in `sdlc.pricing`. Task 3 executes the activity by function reference; tests exclude/replace it by identity (`a is not price_usage`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_price_usage.py`:

```python
"""E-33: token->USD pricing. Verified against genai-prices' bundled tables —
offline, deterministic, no network."""
from sdlc.pricing import PriceUsageInput, compute_price, price_usage


def test_known_anthropic_model_prices_positive():
    usd = compute_price(PriceUsageInput(
        model="anthropic:claude-opus-4-8",
        input_tokens=1000, output_tokens=100))
    assert usd is not None and usd > 0


def test_provider_hint_falls_back_unhinted():
    # The registry routes glm through an anthropic-compatible endpoint;
    # genai-prices knows the model only under its real provider. The
    # unhinted retry must find it.
    usd = compute_price(PriceUsageInput(
        model="anthropic:glm-5.2", input_tokens=1000, output_tokens=100))
    assert usd is not None and usd > 0


def test_slash_form_model_string_parses():
    usd = compute_price(PriceUsageInput(
        model="zai-coding-plan/glm-5.2", input_tokens=1000, output_tokens=100))
    assert usd is not None and usd > 0


def test_unknown_model_returns_none_never_raises():
    assert compute_price(PriceUsageInput(
        model="totally-unknown-xyz", input_tokens=10)) is None


def test_price_usage_is_a_temporal_activity():
    assert getattr(price_usage, "__temporal_activity_definition",
                   None) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_price_usage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.pricing'`.

- [ ] **Step 3: Add the dependency**

In `pyproject.toml` `dependencies` (line 5-14), after `"defusedxml>=0.7",` add:

```toml
    "genai-prices>=0.0.60",
```

Then run: `pip install -e . --quiet` (already satisfied — genai-prices ships with pydantic-ai — but the direct import now has a declared dep).

- [ ] **Step 4: Create `src/sdlc/pricing.py`**

```python
"""Token->USD pricing (E-33). Activity-only by design: dollars drive the
budget gate, so the conversion must be replay-deterministic — the lookup
runs in an activity whose result lands in Temporal history, never inline
in workflow code (a genai-prices data update must not change replayed
math under an open workflow)."""
from __future__ import annotations

from pydantic import BaseModel
from temporalio import activity


class PriceUsageInput(BaseModel):
    model: str                      # registry form: "anthropic:claude-opus-4-8"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def compute_price(inp: PriceUsageInput) -> float | None:
    """Pure lookup. None = unknown model/provider — NEVER raises: a missing
    price must not fail a stage; the tokens still record (spec §3).

    The registry's model strings carry a routing provider ("anthropic:" for
    an anthropic-compatible endpoint), which may not be the pricing
    provider — so a hinted miss retries unhinted (glm via zhipuai)."""
    import genai_prices

    usage = genai_prices.Usage(
        input_tokens=inp.input_tokens,
        output_tokens=inp.output_tokens,
        cache_read_tokens=inp.cache_read_tokens,
        cache_write_tokens=inp.cache_write_tokens)
    provider: str | None = None
    ref = inp.model
    for sep in (":", "/"):
        if sep in ref:
            provider, ref = ref.split(sep, 1)
            break
    for prov in dict.fromkeys((provider, None)):   # hinted, then unhinted
        try:
            calc = genai_prices.calc_price(usage, model_ref=ref,
                                           provider_id=prov)
            return float(calc.total_price)
        except Exception:
            continue
    return None


@activity.defn
async def price_usage(inp: PriceUsageInput) -> float | None:
    return compute_price(inp)
```

- [ ] **Step 5: Register on the worker**

In `src/sdlc/worker.py`: after the `from .observability.activities import export_run_artifacts` import (line 46) add:

```python
from .pricing import price_usage
```

and in the `activities=[...]` list, after `export_run_artifacts,` add:

```python
            price_usage,
```

- [ ] **Step 6: Register in the test fakes**

In `tests/fakes/fake_activities.py`: add to the imports at the top:

```python
from sdlc.pricing import price_usage
```

and append it to `GIT_FAKES` (line 97-102) — it is real but offline and
deterministic, which is the list's actual contract:

```python
GIT_FAKES = [
    fake_setup_integration_branch, fake_create_worktree, fake_run_coding_task,
    fake_get_task_diff, fake_run_test_suite, fake_run_lint,
    fake_merge_into_integration, fake_open_pull_request, fake_deploy,
    fake_security_scan, fake_measure_coverage, fake_run_integration_checks,
    price_usage,   # E-33: real activity — pure local table lookup, no network
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_price_usage.py tests/test_worker_registration.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/pricing.py pyproject.toml src/sdlc/worker.py tests/fakes/fake_activities.py tests/test_price_usage.py
git commit -m "feat(pricing): price_usage activity via genai-prices (E-33)"
```

---

### Task 3: `MODEL_USAGE` event, `_run_role` egress helper, refit 8 proposer sites + harness join

**Files:**
- Modify: `src/sdlc/observability/trace.py` (`RunEventKind`)
- Modify: `src/sdlc/workflows/feature.py` (imports, `PRICE_ACT`, `__init__` state, two new helpers, 8 call-site refits, `_dev_task` harness join)
- Test: `tests/test_model_usage_capture.py`

**Interfaces:**
- Consumes: `price_usage`/`PriceUsageInput` (Task 2), `RoleUsage`/`merge_usage` (Task 1).
- Produces: `RunEventKind.MODEL_USAGE = "model_usage"`; workflow state `self._role_usage: dict[str, RoleUsage]`; `self._track_usage(*, role, model, input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0, cost_usd=None, into=None)`; `async _run_role(cfg, role, model, agent, *args, into=None, **kwargs) -> AgentRunResult`. Task 4 calls `_check_budget` at the sites this task touches; Task 6 passes `into=` cells.

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_usage_capture.py` (mirrors the `test_retro_stage.py` idiom):

```python
"""E-33: every proposer call and every harness attempt emits a MODEL_USAGE
event, visible in the exported events.jsonl."""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.models import GateDecision, GateOutcome
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

TASK_QUEUE = "usage"


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


async def _drive(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    for gate in ("architecture", "plan", "deploy"):
        await _wait_for_status(handle, f"awaiting:{gate}")
        await handle.signal(FeatureWorkflow.submit_gate_decision,
                            GateDecision(gate=gate, round=1,
                                         outcome=GateOutcome.APPROVE,
                                         decided_by="human"))


@pytest.mark.asyncio
async def test_model_usage_events_exported(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    activities = [evaluate_gate, export_run_artifacts, *GIT_FAKES,
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow],
                              activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config()],
                    id=f"usage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver
    assert result.startswith("deployed:"), result
    run_dir = next(tmp_path.iterdir())
    events = [json.loads(line) for line in
              (run_dir / "events.jsonl").read_text().splitlines()]
    usage = [e for e in events if e["kind"] == "model_usage"]
    roles = {e["data"]["role"] for e in usage}
    # every proposer the happy path exercises, plus the harness join
    assert {"clarify", "architect", "planner", "qa", "reviewer",
            "analyst", "dev"} <= roles, roles
    for e in usage:
        assert e["data"]["calls"] == "1"
        int(e["data"]["input_tokens"])       # stringified ints parse
        int(e["data"]["output_tokens"])
    dev = next(e for e in usage if e["data"]["role"] == "dev")
    # fake_run_coding_task reports 1000/200
    assert dev["data"]["input_tokens"] == "1000"
    assert dev["data"]["output_tokens"] == "200"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_model_usage_capture.py -v`
Expected: FAIL — no `model_usage` events found (empty `usage` list → set-inclusion assertion fails).

- [ ] **Step 3: Add the event kind**

In `src/sdlc/observability/trace.py`, add to `RunEventKind` after `FIX_ATTEMPT`:

```python
    MODEL_USAGE = "model_usage"
```

- [ ] **Step 4: Wire the workflow — imports, activity options, state**

In `src/sdlc/workflows/feature.py`:

(a) Inside the `workflow.unsafe.imports_passed_through()` block add:

```python
    from ..observability.usage import merge_usage
    from ..pricing import PriceUsageInput, price_usage
```

and add `RoleUsage` to the existing `from ..models import (...)` list.

(b) Near `VERIFY_ACT` (line ~92) add:

```python
# E-33: pricing is a deterministic local table lookup — retrying cannot
# change the outcome (VERIFY_ACT rationale); the caller treats failure as
# "price unknown", so 1 attempt, short timeout.
PRICE_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                 retry_policy=RetryPolicy(maximum_attempts=1))
```

(c) In `__init__`, next to `self._session_refs` (line ~242) add:

```python
        # E-33: per-role spend accumulated across the run; budget state.
        self._role_usage: dict[str, RoleUsage] = {}
        self._budget_threshold: float = 0.0
        self._budget_crossings: int = 0
```

- [ ] **Step 5: Add the two helpers**

In `feature.py`, directly after `_emit` (line ~421) add:

```python
    def _track_usage(self, *, role: str, model: str,
                     input_tokens: int = 0, output_tokens: int = 0,
                     cache_read_tokens: int = 0, cache_write_tokens: int = 0,
                     cost_usd: float | None = None,
                     into: RoleUsage | None = None) -> None:
        """Fold one model call into the run's per-role accumulator and emit
        a MODEL_USAGE event. Pure state mutation — safe in workflow code.
        `into` additionally folds the same delta into a caller-held bag
        (per-stage benchmark records)."""
        bag = self._role_usage.setdefault(
            role, RoleUsage(role=role, model=model))
        for target in (bag, into) if into is not None else (bag,):
            merge_usage(target, model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_read_tokens=cache_read_tokens,
                        cache_write_tokens=cache_write_tokens,
                        cost_usd=cost_usd)
        self._emit(
            RunEventKind.MODEL_USAGE, role=role, model=model, calls="1",
            input_tokens=str(input_tokens), output_tokens=str(output_tokens),
            cache_read_tokens=str(cache_read_tokens),
            cache_write_tokens=str(cache_write_tokens),
            **({"cost_usd": str(cost_usd)} if cost_usd is not None else {}))

    async def _run_role(self, cfg: PipelineConfig, role: str, model: str,
                        agent, *args, into: RoleUsage | None = None,
                        **kwargs):
        """E-33 single model-egress point (folds E-19): run a proposer
        agent, capture its usage, price it (replay-safe: in an activity),
        accumulate per role. Returns the AgentRunResult — callers keep
        taking .output. Pricing failure of ANY kind degrades to usd=None;
        it must never fail the stage."""
        result = await agent.run(*args, **kwargs)
        u = result.usage()
        usd: float | None = None
        if u.input_tokens or u.output_tokens:
            try:
                usd = await workflow.execute_activity(
                    price_usage,
                    PriceUsageInput(
                        model=model,
                        input_tokens=u.input_tokens or 0,
                        output_tokens=u.output_tokens or 0,
                        cache_read_tokens=u.cache_read_tokens or 0,
                        cache_write_tokens=u.cache_write_tokens or 0),
                    **PRICE_ACT)
            except Exception:
                usd = None
        self._track_usage(
            role=role, model=model,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=u.cache_read_tokens or 0,
            cache_write_tokens=u.cache_write_tokens or 0,
            cost_usd=usd, into=into)
        return result
```

- [ ] **Step 6: Refit the 8 proposer call sites**

Each is a mechanical rewrite `(await t_X.run(PROMPT...)).output` →
`(await self._run_role(cfg, ROLE, MODEL, t_X, PROMPT...)).output`. The
prompt expressions stay byte-identical; only the wrapper changes.

| Line (pre-edit) | Old call | New call prefix |
|---|---|---|
| 599 | `(await t_qa.run(` | `(await self._run_role(cfg, "qa", STAGE_MODELS["qa"], t_qa,` |
| 610 | `(await t_reviewer.run(` | `(await self._run_role(cfg, "reviewer", STAGE_MODELS.get("review", "unknown"), t_reviewer,` |
| 850 | `(await t_research.run(` | `(await self._run_role(cfg, "research", STAGE_MODELS.get("research", "unknown"), t_research,` |
| 911 | `(await t_clarify.run(` | `(await self._run_role(cfg, "clarify", STAGE_MODELS["clarify"], t_clarify,` |
| 1006 | `(await t_architect.run(prompt, deps=architect_deps)).output` | `(await self._run_role(cfg, "architect", STAGE_MODELS["architect"], t_architect, prompt, deps=architect_deps)).output` |
| 1046 | `(await t_planner.run(prompt)).output` | `(await self._run_role(cfg, "planner", STAGE_MODELS["plan"], t_planner, prompt)).output` |
| 1143 | `(await t_analyst.run(` | `(await self._run_role(cfg, "analyst", STAGE_MODELS["analyze"], t_analyst,` |
| 1300 | `(await t_merge_verdict.run(` | `(await self._run_role(cfg, "merge_verdict", STAGE_MODELS.get("merge_verdict", "unknown"), t_merge_verdict,` |

Keyword `deps=` arguments (research line 851, architect line 1006) pass
through `**kwargs` unchanged.

- [ ] **Step 7: Harness join in `_dev_task`**

In `_dev_task`, immediately after the `run = await workflow.execute_activity(run_coding_task, ...)` call (after the `session_ref` append, line ~582) add:

```python
            # E-33 harness join: the harness reports REAL dollars (CLI
            # total_cost_usd) — no pricing activity needed. Accumulate
            # under the executing role.
            self._track_usage(
                role="dev", model=role_cfg.model,
                input_tokens=run.input_tokens or 0,
                output_tokens=run.output_tokens or 0,
                cost_usd=run.cost_usd)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_model_usage_capture.py -v`
Expected: PASS.

Run: `python -m pytest tests/test_retro_stage.py tests/test_e2e_greenfield.py tests/test_factory_purity.py -v`
Expected: all PASS (existing workflow paths unchanged; purity test proves no new I/O in workflow code).

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/observability/trace.py src/sdlc/workflows/feature.py tests/test_model_usage_capture.py
git commit -m "feat(workflow): _run_role egress captures per-role usage, MODEL_USAGE events (E-33, folds E-19)"
```

---

### Task 4: Budget gate

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (`_gate` signature, `_check_budget` + `_BudgetRejected`, `run()` catch, `_pipeline` threshold init, 6 serial check sites)
- Test: `tests/test_budget_gate.py`

**Interfaces:**
- Consumes: `_track_usage` state (`self._role_usage`), `_gate` (existing), `GateContext(spec_summary=...)` → `StageGatePending` (existing).
- Produces: module-level `class _BudgetRejected(Exception)` in `feature.py`; `async _check_budget(cfg) -> None` (raises `_BudgetRejected`); `_gate(..., default_policy: GatePolicy | None = None)`. Terminal outcome string `"rejected:budget"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_budget_gate.py`:

```python
"""E-33: the run-budget gate — crossings re-gate per increment, approve
extends, reject terminates with retro intact, default-off changes nothing
(the whole existing suite is that last proof)."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.models import GateDecision, GateOutcome
from sdlc.observability.activities import export_run_artifacts
from sdlc.pricing import PriceUsageInput, price_usage as real_price_usage
from tests.fakes.canned import (
    AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

TASK_QUEUE = "budget"


@activity.defn(name="price_usage")
async def fixed_price(inp: PriceUsageInput) -> float | None:
    return 1.0    # every proposer call costs exactly $1


def _activities():
    fakes = [a for a in GIT_FAKES if a is not real_price_usage]
    return [evaluate_gate, export_run_artifacts, fixed_price, *fakes,
            *fake_agent_activities(AGENT_SPECS)]


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


async def _signal_gate(handle, gate, round, outcome):
    await handle.signal(FeatureWorkflow.submit_gate_decision,
                        GateDecision(gate=gate, round=round, outcome=outcome,
                                     decided_by="human"))


@pytest.mark.asyncio
async def test_budget_crossings_regate_and_approve_extends(tmp_path,
                                                           monkeypatch):
    """budget=$1.50, $1/call. Happy-path metered calls in order: clarify,
    architect, planner, qa, reviewer, analyst (merge_verdict skipped —
    merge gate is HARD not SOFT; fake dev harness carries no dollars).
    Crossings: $2>=1.5 (r1, after architecture), $3>=3.0 (r2, after plan),
    $5>=4.5 (r3, task loop), $6>=6.0 (r4, after analyst)."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.run_budget_usd = 1.5
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow],
                              activities=_activities(),
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg],
                    id=f"budget-{uuid.uuid4()}", task_queue=TASK_QUEUE)

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question,
                                            args=[qid, "yes"])
                    await _wait_for_status(handle, "awaiting:architecture")
                    await _signal_gate(handle, "architecture", 1,
                                       GateOutcome.APPROVE)
                    for rnd in (1, 2):
                        await _wait_for_status(handle, "awaiting:budget")
                        await _signal_gate(handle, "budget", rnd,
                                           GateOutcome.APPROVE)
                        if rnd == 1:
                            await _wait_for_status(handle, "awaiting:plan")
                            await _signal_gate(handle, "plan", 1,
                                               GateOutcome.APPROVE)
                    for rnd in (3, 4):
                        await _wait_for_status(handle, "awaiting:budget")
                        await _signal_gate(handle, "budget", rnd,
                                           GateOutcome.APPROVE)
                    await _wait_for_status(handle, "awaiting:deploy")
                    await _signal_gate(handle, "deploy", 1,
                                       GateOutcome.APPROVE)

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result.startswith("deployed:"), result
    budget_gates = [g for g in summary.gates if g.gate == "budget"]
    assert {g.round for g in budget_gates} == {1, 2, 3, 4}
    assert all(g.approved for g in budget_gates)


@pytest.mark.asyncio
async def test_budget_reject_terminates_with_retro(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.run_budget_usd = 0.5      # first metered call ($1, clarify) crosses
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow],
                              activities=_activities(),
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg],
                    id=f"budget-rej-{uuid.uuid4()}", task_queue=TASK_QUEUE)

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question,
                                            args=[qid, "yes"])
                    await _wait_for_status(handle, "awaiting:budget")
                    await _signal_gate(handle, "budget", 1,
                                       GateOutcome.REJECT)

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result == "rejected:budget", result
    assert summary is not None            # retro ran on the budget path
    assert summary.outcome == "rejected:budget"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_budget_gate.py -v`
Expected: FAIL — `timed out waiting for 'awaiting:budget'` (the config knob exists since Task 1, but nothing raises the gate yet).

- [ ] **Step 3: Give `_gate` a per-gate default policy**

In `feature.py` `_gate` (line 423): add parameter `default_policy: GatePolicy | None = None` after `confidence`, and change the policy lookup to:

```python
        policy = cfg.gates.get(
            name,
            GateConfig(policy=default_policy or cfg.default_gate_policy),
        ).policy
```

- [ ] **Step 4: Add `_BudgetRejected` + `_check_budget`**

At module level in `feature.py` (after the `_long_act` helper, before the workflow class):

```python
class _BudgetRejected(Exception):
    """Raised at a budget-gate reject; caught in run() so the terminal
    outcome is the ordinary string "rejected:budget" and retro still runs."""
```

On the workflow class, directly after `_run_role` add:

```python
    async def _check_budget(self, cfg: PipelineConfig) -> None:
        """E-33/FR-701 run-budget enforcement. Called at SERIAL points only
        (stage boundaries + the task loop after merges) — never inside a
        wave-mode gather, so gate rounds cannot race. Approve grants one
        more increment; the while-loop re-gates a spend that jumped
        multiple increments at once."""
        if cfg.run_budget_usd <= 0:
            return
        total = sum(u.cost_usd or 0.0 for u in self._role_usage.values())
        while total >= self._budget_threshold:
            self._budget_crossings += 1
            rows = "\n".join(
                f"  {u.role} ({u.model}): ${u.cost_usd:.4f}"
                for u in self._role_usage.values()
                if u.cost_usd is not None)
            decision = await self._gate(
                "budget", cfg, round=self._budget_crossings,
                context=GateContext(spec_summary=(
                    f"Run cost ${total:.4f} >= budget "
                    f"${self._budget_threshold:.2f}\n{rows}")),
                default_policy=GatePolicy.HARD)
            if decision.outcome is not GateOutcome.APPROVE:
                # REVISE has nothing to revise here — any non-approve
                # terminates (spec §5).
                raise _BudgetRejected()
            self._budget_threshold += cfg.run_budget_usd
```

- [ ] **Step 5: Catch in `run()`, init the threshold**

Replace `run()` (line 727-732) with:

```python
    async def run(self, idea: IdeaBrief,
                  cfg: PipelineConfig | None = None) -> str:
        cfg = cfg or PipelineConfig()
        self._budget_threshold = cfg.run_budget_usd    # E-33
        try:
            result = await self._pipeline(idea, cfg)
        except _BudgetRejected:
            result = "rejected:budget"
        await self._retro(cfg, idea, result)
        return result
```

- [ ] **Step 6: Insert the serial check sites**

Add `await self._check_budget(cfg)` at exactly these six points in `_pipeline`:

1. **After the clarify stage record + retain** (after the `await self._retain(... text=f"clarify: {reqs.summary}" ...)` call, line ~960).
2. **After the research stage record blocks** — at the end of the `if cfg.research_enabled ...` research section, after the `else:` branch's PASS record (line ~901), dedented to run for both FAIL and PASS outcomes.
3. **After the architecture stage record + retain**, before `if not gate.approved: return "rejected:architecture"` (line ~1029).
4. **After the plan stage record + retain** (the block analogous to architecture, after plan's `_retain`).
5. **In the task loop** (`while remaining:`, line ~1091): in the SERIAL branch after the `if tr.status == "done": ... _merge_task ...` block, and in the wave branch after the batch's sequential merges — i.e. once per loop iteration in each mode, immediately before the loop's end.
6. **After the analyst stage record + retains** (after the `untraced` retain block, line ~1168).

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_budget_gate.py -v`
Expected: both PASS. If the crossing rounds in test 1 misalign, print `summary.gates` and re-derive the crossing table against the check sites — the canned path is deterministic, so the fix is adjusting the test's expected rounds, never sleeping/retrying.

Run: `python -m pytest tests/test_retro_stage.py tests/test_e2e_greenfield.py tests/test_gate_config.py tests/test_gate_revision_loop.py -v`
Expected: all PASS (budget off by default → no behavior change).

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_budget_gate.py
git commit -m "feat(workflow): run-budget gate via FR-301/302 machinery, rejected:budget terminal (E-33)"
```

---

### Task 5: Retro rollup, budget fields in `RunSummary`, report.html role table

**Files:**
- Modify: `src/sdlc/observability/summary.py` (`build_run_summary` + new `_role_rollup`)
- Modify: `src/sdlc/workflows/feature.py` (`_retro`'s `build_run_summary` call)
- Modify: `src/sdlc/observability/export.py` (`render_report_html`)
- Test: `tests/test_run_summary_build.py` (extend), `tests/test_observability_export.py` (extend)

**Interfaces:**
- Consumes: `MODEL_USAGE` events (Task 3), `RoleUsage`/`merge_usage` (Task 1).
- Produces: `build_run_summary(..., budget_usd: float | None = None)` filling `roles`, `budget_usd`, `budget_crossings`, and `cost_usd_total` = role-rollup sum.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_summary_build.py`:

```python
def _usage_event(seq, role, model, in_t, out_t, usd=None):
    from datetime import datetime, timezone
    from sdlc.observability.trace import RunEvent, RunEventKind
    data = {"role": role, "model": model, "calls": "1",
            "input_tokens": str(in_t), "output_tokens": str(out_t),
            "cache_read_tokens": "0", "cache_write_tokens": "0"}
    if usd is not None:
        data["cost_usd"] = str(usd)
    return RunEvent(seq=seq, at=datetime.now(timezone.utc),
                    kind=RunEventKind.MODEL_USAGE, data=data)


def test_role_rollup_aggregates_model_usage_events():
    from sdlc.observability.summary import build_run_summary
    trace = [
        _usage_event(0, "clarify", "m1", 100, 10, usd=0.5),
        _usage_event(1, "clarify", "m1", 50, 5),          # unpriced call
        _usage_event(2, "dev", "m2", 1000, 200, usd=2.0),
    ]
    s = build_run_summary(run_id="r", mode="greenfield", outcome="deployed:x",
                          trace=trace, memory_enabled=False,
                          memory_watermark=None, budget_usd=5.0)
    roles = {u.role: u for u in s.roles}
    assert roles["clarify"].calls == 2
    assert roles["clarify"].input_tokens == 150
    assert roles["clarify"].cost_usd == 0.5     # None call didn't zero it
    assert roles["dev"].cost_usd == 2.0
    assert s.cost_usd_total == 2.5              # rollup sum, not stage sum
    assert s.budget_usd == 5.0


def test_budget_crossings_counted_from_gate_events():
    from datetime import datetime, timezone
    from sdlc.observability.summary import build_run_summary
    from sdlc.observability.trace import RunEvent, RunEventKind
    now = datetime.now(timezone.utc)
    trace = [
        RunEvent(seq=0, at=now, kind=RunEventKind.GATE_DECIDED,
                 data={"gate": "budget", "round": "1", "policy": "hard",
                       "decided_by": "human", "approved": "true"}),
        RunEvent(seq=1, at=now, kind=RunEventKind.GATE_DECIDED,
                 data={"gate": "budget", "round": "2", "policy": "hard",
                       "decided_by": "human", "approved": "false"}),
    ]
    s = build_run_summary(run_id="r", mode="greenfield",
                          outcome="rejected:budget", trace=trace,
                          memory_enabled=False, memory_watermark=None)
    assert s.budget_crossings == 2
    assert s.budget_usd is None                 # not passed → off
```

Append to `tests/test_observability_export.py`:

```python
def test_report_html_renders_role_table():
    from datetime import datetime, timezone
    from sdlc.models import RoleUsage, RunSummary
    from sdlc.observability.export import render_report_html
    now = datetime.now(timezone.utc)
    s = RunSummary(run_id="r1", mode="greenfield", outcome="deployed:x",
                   terminal_stage="deploy", started_at=now, ended_at=now,
                   duration_s=1.0,
                   roles=[RoleUsage(role="architect", model="anthropic:o",
                                    calls=2, input_tokens=1500,
                                    output_tokens=300, cost_usd=1.25)],
                   budget_usd=5.0, budget_crossings=1)
    html = render_report_html(s)
    assert "architect" in html
    assert "$1.2500" in html
    assert "budget" in html.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_run_summary_build.py tests/test_observability_export.py -v`
Expected: the three new tests FAIL (`TypeError: unexpected keyword argument 'budget_usd'`; missing role table). Existing tests in both files still PASS.

- [ ] **Step 3: Implement the rollup in `summary.py`**

In `src/sdlc/observability/summary.py`: extend the models import to include `RoleUsage`, add `from .usage import merge_usage`, then add above `build_run_summary`:

```python
def _role_rollup(trace: list[RunEvent]) -> list[RoleUsage]:
    bags: dict[str, RoleUsage] = {}
    for e in trace:
        if e.kind is not RunEventKind.MODEL_USAGE:
            continue
        d = e.data
        role = d.get("role", "?")
        model = d.get("model", "?")
        bag = bags.setdefault(role, RoleUsage(role=role, model=model))
        cost = d.get("cost_usd")
        merge_usage(
            bag, model=model,
            input_tokens=int(d.get("input_tokens", "0")),
            output_tokens=int(d.get("output_tokens", "0")),
            cache_read_tokens=int(d.get("cache_read_tokens", "0")),
            cache_write_tokens=int(d.get("cache_write_tokens", "0")),
            cost_usd=float(cost) if cost is not None else None)
    return list(bags.values())
```

Change `build_run_summary`'s signature to add `budget_usd: float | None = None` (keyword-only, after `memory_watermark`). In the body, replace the `costs = ...` line and the `cost_usd_total=` argument:

```python
    roles = _role_rollup(trace)
    role_costs = [u.cost_usd for u in roles if u.cost_usd is not None]
    budget_crossings = sum(
        1 for e in trace
        if e.kind is RunEventKind.GATE_DECIDED
        and e.data.get("gate") == "budget")
```

and in the returned `RunSummary(...)`:

```python
        roles=roles,
        cost_usd_total=(sum(role_costs) if role_costs else None),
        budget_usd=budget_usd, budget_crossings=budget_crossings,
```

(The old `costs = [s.cost_usd for s in stages ...]` line is deleted — the role rollup is complete by construction and avoids double-counting harness dollars that appear in both a stage record and a MODEL_USAGE event.)

- [ ] **Step 3b: Update the existing stage-sum assertion**

`tests/test_run_summary_build.py:35` asserts `cost_usd_total == 0.30` summed
from `STAGE_ENDED` events — semantics Task 5 deliberately replaces (rollup
sum; stage-event sums would double-count harness dollars). Update that test:
in its trace list, after the two `STAGE_ENDED` events, add matching usage
events (using the `_usage_event` helper added in Step 1):

```python
        _usage_event(6, "clarify", "m", 100, 10, usd=0.10),
        _usage_event(7, "architect", "m", 200, 20, usd=0.20),
```

(give them seq values after the existing events and re-number `RUN_FINISHED`
if needed — seq ordering only matters for `started/ended`, which come from
first/last positions, so appending is simplest: keep `RUN_FINISHED` last).
The `abs(s.cost_usd_total - 0.30) < 1e-9` assertion then still holds. The
second test's `cost_usd_total is None` assertion holds unchanged (no usage
events in its trace).

- [ ] **Step 4: Pass the budget from `_retro`**

In `feature.py` `_retro`, extend the `build_run_summary(...)` call (line ~743) with:

```python
                budget_usd=(cfg.run_budget_usd
                            if cfg.run_budget_usd > 0 else None),
```

- [ ] **Step 5: Render the role table in `export.py`**

In `render_report_html`, after the `clar_rows` block add:

```python
    role_rows = "".join(
        _row([u.role, u.model, str(u.calls),
              str(u.input_tokens), str(u.output_tokens),
              "-" if u.cost_usd is None else f"${u.cost_usd:.4f}"])
        for u in s.roles)
```

In the HTML template, after the Clarifications table insert:

```python
<h2>Cost by role</h2>
<table><tr><th>role</th><th>model</th><th>calls</th><th>in_tokens</th>
<th>out_tokens</th><th>cost</th></tr>{role_rows}</table>
```

and extend the trailing `.meta` paragraph with:

```python
&middot; budget={"-" if s.budget_usd is None else f"${s.budget_usd:.2f}"}
&middot; budget_crossings={s.budget_crossings}
```

(f-string nesting: compute `budget = "-" if s.budget_usd is None else f"${s.budget_usd:.2f}"` next to the existing `cost = ...` line and interpolate `{budget}`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_run_summary_build.py tests/test_observability_export.py tests/test_retro_stage.py tests/test_budget_gate.py tests/test_model_usage_capture.py -v`
Expected: all PASS. (`test_budget_gate.py` asserts `summary.gates` rounds — now also implicitly exercises `budget_crossings`.)

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/observability/summary.py src/sdlc/observability/export.py src/sdlc/workflows/feature.py tests/test_run_summary_build.py tests/test_observability_export.py
git commit -m "feat(observability): per-role cost rollup in RunSummary + report.html (E-33)"
```

---

### Task 6: Fill proposer `BenchmarkRecord.cost` (CostBag)

**Files:**
- Modify: `src/sdlc/observability/usage.py` (add `cost_bag_from_spend`)
- Modify: `src/sdlc/workflows/feature.py` (`_stage_record` + spend cells at 6 record sites)
- Test: `tests/test_role_usage.py` (extend)

**Interfaces:**
- Consumes: `RoleUsage`, `_run_role(..., into=...)` (Task 3), `CostBag` (existing, `sdlc.benchmarks.models`).
- Produces: `cost_bag_from_spend(spend: RoleUsage | None, cost_usd: float | None = None) -> CostBag` in `sdlc.observability.usage`; `_stage_record(..., spend: RoleUsage | None = None)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_role_usage.py`:

```python
def test_cost_bag_from_spend():
    from sdlc.observability.usage import cost_bag_from_spend
    u = RoleUsage(role="clarify", model="m", calls=1,
                  input_tokens=100, output_tokens=10, cost_usd=0.5)
    bag = cost_bag_from_spend(u)
    assert bag.usd == 0.5
    assert bag.input_tokens == 100
    assert bag.output_tokens == 10


def test_cost_bag_explicit_usd_wins_and_none_spend_degrades():
    from sdlc.observability.usage import cost_bag_from_spend
    u = RoleUsage(role="dev", model="m", input_tokens=100)
    assert cost_bag_from_spend(u, cost_usd=2.0).usd == 2.0   # harness $ wins
    empty = cost_bag_from_spend(None, cost_usd=None)
    assert empty.usd is None and empty.input_tokens is None
    zero = cost_bag_from_spend(RoleUsage(role="x", model="m"))
    assert zero.input_tokens is None       # cache-hit cell: zeros → None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_role_usage.py -v`
Expected: new tests FAIL — `ImportError: cannot import name 'cost_bag_from_spend'`.

- [ ] **Step 3: Add `cost_bag_from_spend` to `usage.py`**

```python
def cost_bag_from_spend(spend: RoleUsage | None,
                        cost_usd: float | None = None):
    """CostBag for a stage's BenchmarkRecord (E-33, spec §2). Explicit
    cost_usd (harness-reported dollars) wins over the spend's priced sum.
    A zero-token spend (memoization cache hit — the closure never ran)
    degrades to None fields, matching pre-E-33 records."""
    from ..benchmarks.models import CostBag
    if spend is None:
        return CostBag(usd=cost_usd)
    return CostBag(
        usd=cost_usd if cost_usd is not None else spend.cost_usd,
        input_tokens=spend.input_tokens or None,
        output_tokens=spend.output_tokens or None)
```

(Local import: `benchmarks.models` must not become an import-time dependency of the observability package — mirrors how `usage.py` stays workflow-sandbox-safe.)

- [ ] **Step 4: Thread `spend` through `_stage_record`**

In `feature.py`: add `from ..observability.usage import cost_bag_from_spend, merge_usage` (extend the Task 3 import). In `_stage_record` (line 250), add parameter `spend: RoleUsage | None = None` after `cost_usd`, and replace `cost=CostBag(usd=cost_usd),` with:

```python
            cost=cost_bag_from_spend(spend, cost_usd),
```

- [ ] **Step 5: Create spend cells at the 6 proposer record sites**

Pattern — declare the cell before the agent call, pass `into=` at the `_run_role` call, pass `spend=` at the `_stage_record` call:

1. **clarify** (~line 905): before `async def _run_clarify():` add
   `clarify_spend = RoleUsage(role="clarify", model=STAGE_MODELS["clarify"])`;
   inside the closure pass `into=clarify_spend`; at the clarify
   `_stage_record` (line ~951) add `spend=clarify_spend`. On a memoization
   cache hit the closure never runs → zero cell → `None` fields (correct:
   no spend).
2. **research** (~line 848): `research_spend = RoleUsage(role="research", model=STAGE_MODELS.get("research", "unknown"))` before the `t_research` call; `into=research_spend`; add `spend=research_spend` to **both** the FAIL record (line ~876) and the PASS record (line ~896).
3. **architect** (~line 990, before `_revisable_stage`): `arch_spend = RoleUsage(role="architect", model=STAGE_MODELS["architect"])` declared before `async def _run_architect(...)`; `into=arch_spend` at the `_run_role` call inside `_produce`; `spend=arch_spend` at the architecture `_stage_record`. REVISE rounds accumulate into the same cell — the stage record carries the stage's full spend across rounds.
4. **plan** (~line 1038): same pattern with `plan_spend = RoleUsage(role="planner", model=STAGE_MODELS["plan"])`.
5. **qa** (in `_dev_task`, inside the attempt loop ~line 598): `qa_spend = RoleUsage(role="qa", model=STAGE_MODELS["qa"])` fresh per attempt, `into=qa_spend`, and `spend=qa_spend` on the **qa** record (line ~638). The **code** record keeps `cost_usd=run.cost_usd` (harness dollars) and gains no spend cell.
6. **analyst** (~line 1141): `analyst_spend = RoleUsage(role="analyst", model=STAGE_MODELS["analyze"])`, `into=analyst_spend`, `spend=analyst_spend` on the analyze record.

(reviewer and merge_verdict have no per-stage records — their spend lands in the role rollup only; the merge record stays `model="deterministic"`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_role_usage.py tests/test_budget_gate.py tests/test_model_usage_capture.py tests/test_e2e_greenfield.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/observability/usage.py src/sdlc/workflows/feature.py tests/test_role_usage.py
git commit -m "feat(benchmarks): fill proposer CostBag from per-stage spend (E-33)"
```

---

### Task 7: Full suite, docs follow-through, roadmap

**Files:**
- Modify: `ROADMAP.md` (§9.8 E-33, §9.5 E-19, §2 FR-701)
- Modify: `PRD.md` (FR-701 line)
- Modify: `BENCHMARK.md` (§3.2 note)
- Modify: `docs/superpowers/specs/2026-07-23-per-role-cost-attribution-design.md` (status line)

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass, no new warnings-as-errors. Fix anything that fails before touching docs.

- [ ] **Step 2: Update `ROADMAP.md`**

- §9.8 `- [ ] **E-33**` → `- [x] **E-33**`, appending to the item text:
  `*Landed:* single workflow egress (\`_run_role\`) + \`MODEL_USAGE\` events + \`price_usage\` activity (genai-prices, replay-safe) + \`RunSummary.roles\` rollup + report.html role table + proposer CostBag fill, **and FR-701's run-level budget gate** (\`run_budget_usd\`, hard gate via FR-301/302, approve = one more increment, reject = \`rejected:budget\` with retro intact). Research provider spend stays stage-scoped. Spec \`docs/superpowers/specs/2026-07-23-per-role-cost-attribution-design.md\`, plan \`docs/superpowers/plans/2026-07-23-per-role-cost-attribution.md\`.`
- §9.5 E-19: mark `- [x]` with note `*Folded into E-33:* \`_run_role\` is the single egress point; run-level counters live in \`RunSummary.roles\`.`
- §2 FR-701: update the line to note run-level counters + budget escalation landed (E-33); stage-scoped research budgets unchanged; mark `[ ] ⚠️` → `[x]` only if PRD's FR-701 wording is fully satisfied — it is (counters + escalation), so `[x]` with the research-provider-spend caveat in the note.
- §9.8 suggested-ordering line: mark E-33 ✓.

- [ ] **Step 3: Update `PRD.md` FR-701 and `BENCHMARK.md` §3.2**

- PRD FR-701: append: run-level token/cost counters and a `run_budget_usd` budget gate (escalate-through-gate on crossing) landed 2026-07-23 (E-33); stage-scoped research budgets (FR-107) unchanged.
- BENCHMARK.md §3.2: after the "dollars per role" paragraph add a one-liner: *E-33 landed this: `RunSummary.roles` carries per-role dollars on every run; proposer `BenchmarkRecord.cost` is now populated, so `mean_cost_usd` is real for proposer cells.*

- [ ] **Step 4: Update the spec status**

In the spec's header table: `| Status | Approved design — pre-plan |` → `| Status | Implemented (feat/e-33-cost-attribution) |`.

- [ ] **Step 5: Commit**

```bash
git add ROADMAP.md PRD.md BENCHMARK.md docs/superpowers/specs/2026-07-23-per-role-cost-attribution-design.md docs/superpowers/plans/2026-07-23-per-role-cost-attribution.md
git commit -m "docs: mark E-33 landed (folds E-19), FR-701 run budget shipped"
```

- [ ] **Step 6: Finish the branch**

Use the superpowers:finishing-a-development-branch skill (merge vs PR decision belongs to the human).
