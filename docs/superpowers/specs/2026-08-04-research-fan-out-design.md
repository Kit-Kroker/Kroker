# Research Fan-Out — Design

| | |
|---|---|
| Status | Approved |
| Date | 2026-08-04 |
| Supersedes parts of | `2026-07-17-research-agent-grounded-briefs-design.md`, `2026-07-29-research-agent-exa-harness-design.md` |
| Prior art | [temporal-community/durable-research-fleet](https://github.com/temporal-community/durable-research-fleet) |

---

## 1. Problem

The research stage (`feature.py:1314-1405`) is a single `t_research` agent run.
Decomposition happens inside one agent turn: `ResearchBrief.sub_questions` is an
output field, never a unit of work. Three consequences:

1. **Depth.** One global budget pool (`max_searches=5`) means an early
   sub-question can drain the run and later ones get nothing. Breadth and depth
   compete for the same five searches.
2. **Control.** A sub-question is not visible in Temporal history, not
   individually retryable, and not individually budgeted. One failure degrades
   the entire stage to `_degraded_research_brief` (`feature.py:227`).
3. **Corroboration and conflict are unreachable.** A single investigation
   cannot disagree with itself, so cross-source contradictions surface only by
   accident.

This design makes decomposition workflow-owned and the sub-question the unit of
work, parallelism, retry, and budget.

## 2. Scope

**In:** three new activities (`plan_research`, `research_subquestion`,
`synthesize_brief`), a refine round wired to the existing gate, per-sub-question
budget scoping, and concurrency-safety fixes that fan-out makes load-bearing.

**Out:** worker-pool autoscaling, mid-run resume payloads (§6.2), changes to the
agent itself, the toolset, `verify.py`, `budget_store`'s locking, or the retain
path. This is orchestration *around* the existing research core, not through it.

**Unchanged defaults:** `research_enabled = False`. Nothing changes for existing
runs until the flag is turned on.

## 3. Architecture

```
plan_research(idea)                          → ResearchPlan(sub_questions, usage)
  ↓
gather(research_subquestion(sq) for sq in ...)   ← N parallel activities
  ↓                                                return_exceptions=True
synthesize_brief(idea, partials)             → ResearchBrief
  ↓
verify_brief_activity(brief, run_id)         → list[Violation]     (unchanged)
  ↓ clean
gate("research", round=n)  → approve | reject | revise ─┐
                                                         └→ replan + second wave
```

New module: `src/sdlc/research/stage.py`. All three activities registered in
`worker.py`.

### 3.1 `plan_research`

One schema-constrained model call returning `list[SubQuestion]` (existing model:
`id`, `question`). Width is enforced by slicing to `max_sub_questions`, not by
asking the model nicely.

> DRF measured that the planner **always returns the top of the requested
> range**, even for a yes/no lookup ("Did AWS Lambda raise its 15-minute
> timeout?" planned 6 sub-questions). The config value, not the question, decides
> the width.

### 3.2 `research_subquestion`

Runs the plain `research_agent.run()` **in-process** — not the `TemporalAgent`.
This is the pattern `research/toolset.py::research_subquery` already establishes
for the architect's mid-run call: inside an activity, pydantic-ai falls back to
plain in-process execution, so `deps.budget` accumulates within the run and
`budget_store` enforces the persisted caps underneath.

Returns a `SubQuestionFinding` carrying its own `RoleUsage` (§7).

### 3.3 `synthesize_brief`

Merges N partials into one `ResearchBrief`, preserving the SGR field order that
`tests/test_research_models.py` pins. Split between deterministic assembly and
model judgment — see §5.

## 4. Budget

Today's numbers cannot simply be divided: `max_searches=5` across 4
sub-questions is **1 search each**, shallower than the status quo. Fan-out only
buys depth if the per-unit budget is real. The existing fields are therefore
**reinterpreted as per-sub-question**, with a new run-level ceiling:

```python
class ResearchConfig(BaseModel):
    max_sub_questions: int = 4          # NEW — hard slice
    max_searches: int = 5               # now PER sub-question
    max_fetches: int = 10               # now PER sub-question
    max_cost_usd: float = 1.0           # now PER sub-question
    max_run_cost_usd: float = 4.0       # NEW — hard run ceiling
    max_requests: int = 40              # unchanged, per sub-question
    max_refine_rounds: int = 1          # NEW — see §6
```

`budget_store.budget_path(run_id)` gains a scope parameter →
`runs/<id>/research/budget-<scope>.json`. Each sub-question charges **two
scopes**: its own `sq-<id>` and the shared `run`. Whichever trips first raises
`BudgetExceeded`. Per-scope prevents hogging; run scope prevents blowout. The
existing lock mechanism is unchanged and already designed for this contention.

**Accepted cost change:** a research-enabled run's ceiling moves from $1 to $4.
This is the price of depth and was approved explicitly.

## 5. Merge semantics

### 5.1 Deterministic — code assembles

| Field | Rule |
|---|---|
| `sub_questions` | Union in plan order; ids offset across rounds so round-2 ids cannot collide with round-1 |
| `sources_consulted` | Dedupe by URL, first-seen wins for `assessment` / `relevance` |
| `grounded_findings` | Concatenate; dedupe **only** exact `(source_url, quote, claim)` triples |
| `inferred_findings` | Concatenate |
| `gaps` | Concatenate, plus one synthesized `Gap` per permanently-failed sub-question |

The `grounded_findings` rule is load-bearing in both directions:

- Two sub-questions grounding the **same claim from different sources** is
  corroboration — the most valuable thing fan-out produces. Never collapse it.
- Exact triple duplicates **must** be dropped, because `brief_digest`
  (`verify.py:88-92`) hashes `sorted((source_url, claim) ...)` as a **list**, not
  a set. A duplicated pair changes the digest, and the digest feeds clarify's
  memo key. Left alone, fan-out would silently degrade memoization hit rate.

### 5.2 Model-written — one call over merged material

- `contradictions` — carries through within-sub-question ones verbatim, and adds
  **cross-sub-question** ones: two independent investigations reaching
  conflicting conclusions. Structurally unreachable today.
- `summary`
- `confidence` — assigned over the whole. **Not** an average of per-sub-question
  confidences, which would be a number with no meaning.

### 5.3 Hard constraint

**Synthesis may not add to `grounded_findings`.** It assembles them; it never
authors them. A fabricated quote at merge time would be caught by
`verify_brief`, but only by turning a normal run into a fail-closed stage
failure. Structure comes from code, prose from the model.

The synthesis prompt receives the merged, numbered source list **before** the
model writes, so references cannot drift — DRF's `synthesize` docstring records
that building the list afterward made citations structurally impossible.

## 6. Refine round

`GateOutcome.REVISE` (`models.py:38`), `_gate(round=...)` with
`gate_key(name, round)`, and `GateDecision.guidance` ("fed back into the agent on
'revise'") already exist. The research stage currently collapses revise into
reject via `if not gate.approved`. This wires the third outcome.

```python
round_n = 1
while True:
    violations = await execute_activity(verify_brief_activity, [brief, run_id])
    if violations:                       # fail closed — unchanged
        ...
        break
    gate = await self._gate("research", cfg, round=round_n)
    if gate.outcome == GateOutcome.APPROVE: break
    if gate.outcome == GateOutcome.REJECT:  return "rejected:research"
    if round_n > cfg.research.max_refine_rounds: break   # proceed with what we have
    round_n += 1
    more   = await execute_activity(replan_research, idea, gate.guidance,
                                    brief.gaps, brief.contradictions)
    parts += await gather(...)                            # NEW sub-questions only
    brief  = await execute_activity(synthesize_brief, idea, parts)   # re-merge ALL
```

Four properties:

1. **Round-1 findings are never discarded.** The refine wave researches only new
   sub-questions and re-merges over the accumulated set. This is what makes a
   refine cheap relative to a rerun.
2. **The refine seed is structured.** DRF seeds only a human free-text note; we
   pass `guidance + gaps + unresolved contradictions`, targeting exactly what
   round 1 could not resolve. This is the payoff of the SGR brief model.
3. **No new budget machinery.** The run-scope counter persists across rounds, so
   round 2 draws down the same `max_run_cost_usd`. New sub-questions get fresh
   `sq-` scopes, which is correct — they are genuinely new work.
4. **Re-verification runs over the whole merged brief every round.** Pure and
   local, so nearly free, and it closes the hole where a round-2 finding could
   slip in unverified.

**Exhausting refine rounds proceeds with the current brief**, not a rejection —
consistent with the 2026-07-20 decision at `feature.py:1372` that research
degrades a run but never stops it.

## 7. Usage accounting — E-33 amendment

`_run_role` (`feature.py:668`) is the single model-egress point: it runs the
agent, prices usage in an activity, and accumulates per role. Fan-out moves the
model call **activity-side**, so `_run_role` can no longer wrap it.

The amendment, adopted from DRF (`research_types.py:20-30`, learned by shipping
a plan that displayed `tokens: 0`):

> **If an activity calls a model, its return type must carry usage.**

`ResearchPlan` and `SubQuestionFinding` each carry a `RoleUsage`. The workflow
folds every one through the existing `_track_usage`. E-33's *intent* — one
accounting path, priced replay-safely — is preserved; only the call site moves.

## 8. Failure semantics

| Failure | Behavior |
|---|---|
| Planner fails | Fall back to one sub-question = the whole idea. Fan-out failure degrades to exactly today's behavior, never worse. |
| One sub-question fails permanently | Its `Gap` enters the merged brief; siblings survive. (`gather(..., return_exceptions=True)`) |
| **All** sub-questions fail | `_degraded_research_brief`, `_status = "research_failed"`, pipeline continues on the idea alone (`feature.py:1372`). |
| `BudgetExceeded` in one sub-question | Caught in-activity; returns a partial finding with the shortfall in `gaps`. Matches `ResearchConfig`'s documented contract. |
| Grounding violations post-synthesis | Unchanged: fail closed, `brief_digest_val = ""`, skip retain, stage `FAIL`. |

### 8.1 Retry classification

`BudgetExceeded` and provider refusals go in
`RetryPolicy.non_retryable_error_types`. The budget counter is **persisted**, so
an escaping `BudgetExceeded` would retry against a cap that stays exhausted —
six guaranteed failures with backoff. Same class as the `read_repo` fix in
`tests/test_research_tools.py`; fan-out makes it N× more likely to fire.

Retry policy otherwise follows DRF: `initial_interval=2s`,
`backoff_coefficient=2.0`, `maximum_interval=60s`, `maximum_attempts=6` — tuned
for 429s under concurrent load, where Temporal is the only retry layer.

## 9. Concurrency safety

Fan-out turns three theoretical races into routine ones.

**9.1 Atomic page writes.** Two sub-questions fetching the same URL both write
`runs/<id>/research/pages/<sha256>.txt`. Content is identical so intent is
benign, but `verify_brief` reading a half-written file yields a spurious
`quote_not_found` — which fails the stage closed. Write to `<sha256>.txt.tmp`,
then `os.replace()`.

**9.2 No retries beneath Temporal.** Confirm the Exa and model clients do not
retry internally. DRF sets `max_retries=0` explicitly; nested retry turns a 429
storm into an activity that looks hung rather than one that fails where Temporal
can see it.

**9.3 Worker capacity.** No worker changes are needed. `worker.py:77` sets no
`max_concurrent_activities`, so the SDK default of 100 already permits N=4-5
concurrent activities in the single container; they are I/O-bound model calls.

The real ceiling is **CodeMode sandboxes** (`agents/research/agent.py:44`) — N
concurrent agent runs mean N concurrent sandboxes in one container. If that
binds, the escape hatch is horizontal (`docker compose up --scale worker=3`).
Reach for it because of sandbox capacity, never to "enable" fan-out.

> DRF's `MAX_CONCURRENT_ACTIVITIES=1` is **not** copied. It exists to force one
> activity per Cloud Run instance so an autoscaler visibly scales on a
> projector. Copying it would give us five containers doing what one does now.

## 10. Heartbeating

Each `research_subquestion` gets a timer heartbeat: 15s tick,
`heartbeat_timeout=60s`, `start_to_close=1200s`, plus
`except asyncio.CancelledError: activity.heartbeat(state); raise` to record state
on graceful shutdown. Invariant: `interval < heartbeat_timeout < start_to_close`.

This converts "worker dies, server waits out `start_to_close`" into "detected in
~60s". Liveness is decoupled from call duration, which matters because a
sub-question legitimately runs for minutes.

**Resume payloads are deferred.** DRF carries a bounded `partial_summary` in
heartbeat details and re-prompts the retry to continue from it. That depends on
`llm.complete`'s `on_progress` firing at `pause_turn` boundaries; a Pydantic AI
`agent.run()` offers no equivalent seam without reworking the agent. Their own
measurement is the argument for deferring: `research_types.py:44-48` records that
`resumed` is *"correct and tested, but dormant… every real sub-question completes
in one round."* We take the heartbeat for liveness and skip the payload.

## 11. Prompt caching

The sub-question system prompt must be **byte-identical across the burst** and
marked `cache_control: ephemeral`, so N parallel calls share one cached prefix at
~0.1× input price. Fan-out multiplies input cost by N, making this the single
largest cost lever here.

**Trap:** a prefix under 512 tokens is silently not cached —
`cache_creation_input_tokens` just stays 0, with no error. DRF guards this with
`test_research_prompt_is_cacheable`; we need the equivalent. Never interpolate
per-sub-question content into the cached prefix.

## 12. What we deliberately do not take from DRF

Worker pools, `terraform/`, the `progress` query + web console,
`VersioningBehavior.PINNED`, `MAX_CONCURRENT_ACTIVITIES=1`, and the 2-hour
accept-on-timeout review. Our `GateConfig` (`models.py:716-724`, with
`TimeoutAction.HOLD`) is already richer than their timeout-accepts-for-you.

DRF has **no grounding verification and no budget at all** — it trusts the
model's prose and citation numbers, bounded only by width × effort. Our
`verify.py` substring check, the grounded/inferred split, `brief_digest`, the
persisted `budget_store`, and Hindsight retain are all stronger and all
preserved. We import the orchestration and resilience layer; we keep our
epistemics layer intact.

**Possible follow-up, not in scope:** DRF's durability counters
(`interruptions`, `saved_subquestions`, `saved_tokens` — "work a non-durable
agent would have redone") are demo instrumentation in their context, but may be
a real metric for the harness-waste benchmark instrument. Evaluate separately.

## 13. Testing

- **Merge semantics (pure, no model):** corroboration preserved across differing
  sources; exact triples deduped; `brief_digest` stable under duplicate input;
  SGR field order unchanged.
- **Failure tiers:** planner failure degrades to single sub-question; one
  sub-question failure preserves siblings and emits a `Gap`; total failure
  degrades the stage without stopping the pipeline.
- **Budget:** per-`sq` scope caps one sub-question without starving others; run
  scope trips across the sum; `BudgetExceeded` is classified non-retryable.
- **Concurrency:** concurrent writers to one page path never expose a partial
  read to `verify_brief`.
- **Refine:** round-2 ids never collide with round-1; round-1 findings survive
  re-merge; re-verification covers round-2 findings; exhaustion proceeds rather
  than rejects.
- **Caching:** the sub-question prefix is byte-identical across a burst and over
  512 tokens.

Sub-question activities are tested against the `fake` provider and `TestModel`;
no test in this design requires network or a live model.
