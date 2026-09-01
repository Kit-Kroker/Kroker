# E-33 — Per-role cost attribution + run budget gate

| | |
|---|---|
| Date | 2026-07-23 |
| Roadmap item | E-33 (§9.8); folds E-19 (§9.5) |
| Anchors | **FR-701** (run-level budgets — counters *and* escalation), FR-704/NFR-4 (records), BENCHMARK.md §3.2 (dollars per role) |
| Status | Implemented (feat/e-33-cost-attribution) |

## 1. Why

Cost bookkeeping "exists in benchmarks only", and even there it is half blind:
`HarnessRunResult.cost_usd` (real dollars reported by the harness CLI) flows into
task-attempt `BenchmarkRecord`s and `STAGE_ENDED` events, but every proposer stage
calls `t_X.run(...)` and takes `.output`, **discarding `result.usage()`**
(`feature.py:911, 1006, 1046, …`). So `RunSummary.cost_usd_total` (E-32) counts
harness dollars only — the `opus-4-8` architect, the most expensive role per
BENCHMARK.md §3.2, is invisible.

The economics result E-33 exists to reproduce needs **dollars per role**, not
tokens: planner-family tokens cost multiples of worker-family tokens, so a token
count cannot say which role is expensive. Per Cursor's experiment ($1,339 vs
$10,565 on the same task), the deciding proposers are the cost, the executing
harness roles are the volume — this registry can already pair a frontier
architect with a cheaper dev harness, but nothing measures whether that trade
holds.

**Scope decisions locked in brainstorming:**
- **Measurement + enforcement**, not measurement only: E-33 also ships FR-701's
  run-level budget, checked at stage/task boundaries.
- **Enforcement = escalation through the existing FR-301/FR-302 gate machinery**
  (`_gate`), not a hard halt and not a parallel mechanism.
- **Pricing = `genai_prices` inside an activity.** Dollars now drive control flow
  (the gate fires on them), so the token→USD conversion must be
  replay-deterministic: activity results land in Temporal history, so a price-data
  update cannot change replayed math under an open workflow.
- **Approval grants one more budget increment** (threshold += `run_budget_usd`);
  every crossing re-gates at the next round. No signal-payload changes.
- **Capture = a single workflow-side egress helper** (Approach A): the workflow
  is the only place that both sees every proposer result and owns the budget
  decision.

## 2. Data model (`models.py`)

```python
class RoleUsage(BaseModel):
    """One role's accumulated model spend across the run (E-33)."""

    role: str  # "architect", "dev", "clarify", ...
    model: str  # last model seen for the role
    calls: int = 0  # agent runs / harness invocations
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None  # None = tokens known, price unknown
```

- `cost_usd=None` is load-bearing: **a pricing miss never discards tokens.**
  Token counts are facts from the run; dollars are a lookup that can fail.
  Accumulation adds priced calls into a float and leaves the field `None` until
  the first successful pricing.
- `RunSummary` gains `roles: list[RoleUsage]`, `budget_usd: float | None`
  (the configured budget, `None` when off), `budget_crossings: int`.
  `cost_usd_total` becomes complete — harness + proposer dollars.
- `PipelineConfig` gains `run_budget_usd: float = 0.0` — `0.0` = off, the same
  opt-in pattern as `coverage_threshold`. Named to distinguish it from the
  stage-scoped `research.max_cost_usd` (FR-701's first, narrower counters —
  unchanged by E-33).
- Proposer `BenchmarkRecord.cost` (`CostBag`) gets its existing, currently
  unused `usd` / `input_tokens` / `output_tokens` fields **filled**, so
  benchmark `mean_cost_usd` becomes real for proposer cells, not just
  harness cells.

## 3. Pricing activity (`activities.py`)

```python
class PriceUsageInput(BaseModel):
    model: str  # e.g. "anthropic:claude-opus-4-8"
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@activity.defn
async def price_usage(req: PriceUsageInput) -> float | None: ...
```

- Uses `genai_prices` (already installed as a pydantic-ai dependency,
  Pydantic-maintained tables) to compute USD from the token counts.
- **Never raises for a pricing miss**: unknown model / unmatched provider →
  `None`. A missing price must not fail a stage; the tokens still record.
- Model strings arrive in pydantic-ai `provider:model` form; the activity maps
  that onto `genai_prices`' reference before lookup.
- Short timeout, small retry cap — it is a local table lookup, not network I/O.

## 4. Workflow egress helper (`feature.py`) — the E-19 fold

```python
async def _run_role(self, cfg, role: str, agent, *args, **kwargs):
    result = await agent.run(*args, **kwargs)
    usage = result.usage()
    usd = await workflow.execute_activity(price_usage, ...)
    self._accumulate(role, model, usage, usd)  # + emits MODEL_USAGE event
    await self._check_budget(cfg)
    return result  # callers still take .output
```

- All 8 proposer call sites (`t_clarify`, `t_architect`, `t_planner`, `t_qa`,
  `t_reviewer`, `t_analyst`, `t_merge_verdict`, `t_research`) refit onto it.
  This helper **is** E-19's "single model egress point" expressed in workflow
  terms — one place sees every proposer result.
- **Harness join:** in `_dev_task`, each `HarnessRunResult` already carries real
  CLI dollars and token fields; accumulate under role `dev` through the same
  `_accumulate` + `_check_budget` path (no pricing activity — the harness
  reports dollars directly). One event kind feeds everything downstream.
- New `RunEventKind.MODEL_USAGE` event carrying
  `role / model / calls / input_tokens / output_tokens / cache_* / cost_usd`
  (stringified, per the flat-`str->str` trace contract).
- The judge (`judge_artifact`) and memory activities are **not** metered here:
  the judge is benchmark-only overhead billed to the bench, not the run, and
  memory calls are not model spend. Stated so the boundary is a decision, not
  an accident.

**Known gap (stated, out of scope):** research *provider* spend (Tavily
search/fetch fees, `research/deps.py`) accrues in activity-side deps and never
returns to the workflow. It stays stage-scoped under `research.max_cost_usd`.
Joining it needs the research toolset to return its budget ledger — a later
increment.

## 5. Budget gate

`_check_budget(cfg)` runs after every accumulation (each proposer stage, each
harness task attempt):

- No-op unless `cfg.run_budget_usd > 0`.
- Threshold starts at `run_budget_usd`; on `total >= threshold` the workflow
  raises the **existing** `_gate("budget", round=N)` where `N` = crossing
  count. `(gate, round)` identity, first-decision-wins, pending rendering, and
  the timeout path all hold unchanged (FR-302).
- **Policy defaults to hard for this gate** regardless of
  `default_gate_policy`: setting a budget *is* the opt-in to being asked.
  Overridable via `cfg.gates["budget"]` like any gate.
- **Approve** → `threshold += cfg.run_budget_usd` (one more full allowance);
  run continues; the next crossing re-gates at round N+1, so runaway spend
  keeps re-asking.
- **Reject / timeout** → terminal `"rejected:budget"` through the normal
  terminal path — **retro still runs**, so the RunSummary records exactly
  where the money went.
- **Revise** → treated as reject (there is no artifact to revise); the render
  offers approve/reject only.
- The pending item renders as a `StageGatePending` whose body is the per-role
  spend table (spent vs budget) — it flows through the E-6 channel contract
  and the E-7 CLI with **zero contract changes**.

## 6. Retro & reporting

- `build_run_summary` (`observability/summary.py`) stays **pure over the
  trace**: the role rollup aggregates `MODEL_USAGE` events per role;
  `cost_usd_total` = rollup sum, complete by construction. Per-stage
  `StageOutcome.cost_usd` is unchanged (stage view and role view coexist).
- `budget_usd` / `budget_crossings` come from config + the count of
  `GATE_DECIDED` events with `gate="budget"`.
- `report.html` (`observability/export.py`) gains a per-role table:
  role, model, calls, tokens (in/out/cache), `$`.
- `events.jsonl` carries `MODEL_USAGE` lines for free (same flat format).

## 7. Testing

- **Pricing activity:** known model → positive USD; unknown model → `None`,
  no exception.
- **Summary rollup:** synthetic trace with `MODEL_USAGE` events → correct
  per-role aggregation, `cost_usd_total`, `None`-price handling.
- **Workflow (existing `tests/fakes/`):**
  - budget off → no gate, no behavior change;
  - crossing fires the gate; approve extends threshold and the run completes;
  - second crossing re-gates at round 2;
  - reject → `rejected:budget` terminal **and** retro/export still ran;
  - timeout → reject (existing `_gate` path).
- **`_run_role` passthrough:** `TestModel` usage accumulates; output reaches
  the caller unchanged; a `None` price leaves tokens recorded.

## 8. Documentation follow-through

- ROADMAP §9.8: mark E-33 landed (folding E-19), note enforcement shipped
  (FR-701's escalation half at run scope).
- ROADMAP §9.5 E-19: mark folded into E-33.
- PRD FR-701 line: run-level counters + budget escalation now exist;
  stage-scoped research budgets unchanged.
- BENCHMARK.md §3.2: economics axis now fed by real per-role dollars.
