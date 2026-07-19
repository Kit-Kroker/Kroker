# Cat café monitoring benchmark + qa/research judging (E-27)

**Date:** 2026-07-19
**Roadmap:** §9.1 `E-27` (new)
**Requirements:** No FR moves. Extends the FR-107 research stage and the benchmark
judge to meet at a scored rubric.
**Builds on:** `2026-07-04-pipeline-step-benchmarking-design.md` — the case/rubric/judge
machinery; `2026-07-17-research-agent-grounded-briefs-design.md` — the research agent this
finally scores.

## Problem

The benchmark suite has two golden cases, `todo-api-greenfield` and `add-login-greenfield`.
Both are deliberately tiny — one login route, four CRUD endpoints — and both describe
themselves as "sized for a single short factory run." Nothing in the suite exercises the
pipeline at a size where **planner decomposition is the load-bearing variable**, which is
the regime real work lives in.

The AI Starter Pack "Cat Café" kata is that workload: ten cats emitting collar telemetry
every five seconds, six activity classes to detect from telemetry plus zone geometry, a
live floor-plan view, per-cat risk analysis, and 24h movement history. It is large enough
to require decomposition and small enough to specify completely.

Authoring it surfaced a second gap. Only **three** rubric keys are wired to the LLM judge —
`feature.py` calls `self._judge(...)` at `:773` (`clarifier`), `:840` (`architect`) and
`:879` (`planner`). Two more stages produce judgeable artifacts and are not judged:

- **`qa`** — `t_qa.run()` (`feature.py:539`) emits a QA artifact per code-task attempt. It
  feeds the deterministic `stage="code"` record (`judge="contract"`, 1.0 iff tests passed
  and no issues) but is never scored against a rubric.
- **`research`** — the stage record at `:730` hardcodes `quality_score=None,
  judge="contract"` with no `_judge` call at all. `cfg.research_enabled` defaults `False`
  and `CaseSpec` has no field to flip it, so no benchmark cell has ever run the stage.

A `rubric-qa.md` or `rubric-research.md` authored today would be an inert file.

## Findings

1. **The kata has exactly one fact worth grounding, and it is load-bearing.** The
   requirement "risk analysis for each cat's life or health" and "marked in red" turns
   entirely on a real feline vital-sign threshold — resting respiratory rate, and where
   sustained elevation becomes a veterinary emergency. A model asked to invent that number
   will produce a confident, plausible, wrong one. This is precisely what FR-107 grounding
   is for, and it gives the research rubric something sharp to discriminate on: *was the
   risk threshold grounded in a citable source, or invented?* Most of the kata's other
   choices (SSE vs WebSocket, distance-to-zone, 24h storage) need no grounding — which is
   fine. One well-chosen grounding target beats a stage that searches for its own sake.

2. **Running research and scoring research are separable, and only the first improves the
   build.** Enabling the stage needs `CaseSpec.research_enabled` plus a real provider.
   Scoring it additionally needs the `_judge` call at `:730`. This design does both, but
   they are independent changes and the first carries the implementation benefit.

3. **`make_provider` accepts exactly `tavily` or `fake`** (`research/protocol.py`). The
   fake corpus is a CI fixture that raises in production, so `provider: fake` with research
   enabled is strictly worse than research off. `validate_registry` fails closed at boot
   when a `kind=research` role declares `provider: tavily` without a reachable
   `TAVILY_API_KEY` — a bad key surfaces at worker start, not mid-run.

4. **QA judging must add a record, not replace one.** `t_qa.run()` sits *inside* the task
   loop, so its cardinality is per-task-attempt, not once-per-run like the three wired
   stages. Its output already drives the deterministic `stage="code"` record. Overwriting
   that score with an LLM opinion would trade a deterministic signal for a soft one, so the
   qa rubric gets its own `stage="qa"` record alongside it. `scoring.py` aggregates by
   `(case_id, stage, harness, model)` with a mean, so N records per run aggregate natively.

5. **The kata's own simplifying license is part of the requirements.** "Generate this data
   randomly", "no collar data emulators", "keep it as simple as possible", "the rules are up
   to you" must be carried into the case description verbatim. Without them the architect
   designs a telemetry ingestion pipeline nobody asked for. Conversely the functional
   requirements must not shrink — all six activities, both tasks, all four zone types.

## Design

### 1. Case — `benchmarks/cases/cat-cafe-monitoring/`

`case.yaml`, mirroring `todo-api-greenfield`'s proven configuration:

```yaml
case_id: cat-cafe-monitoring
idea_summary: Real-time monitoring for a cat café — detect each cat's activity
  from smart-collar telemetry and show it live on the floor plan.
description: |
  <kata text: context, Task 1, Task 2 — verbatim and whole, including the
   simplifying license from Finding 5>
mode: greenfield
repo_url: D:/own/sdlc-scratch-repos/cat-cafe-monitoring
research_enabled: true
harnesses: [opencode]
models: [zai-coding-plan/glm-5.2]
judge_model: openai/gpt-5.2          # cross-family vs the zai author (ADR-6)
extra_args_by_model:
  zai-coding-plan/glm-5.2: [--variant, max]
rubrics:
  clarifier: rubric-clarifier.md
  architect: rubric-architect.md
  planner:   rubric-planner.md
  qa:        rubric-qa.md
  research:  rubric-research.md
```

One cell. The matrix stays at `1 × 1` because the goal is a working app plus a first set of
scores; widening to a cross-harness comparison is an edit to `harnesses:` once the case
itself is validated.

### 2. Five rubrics

Case-specific, following the existing rubrics' shape (weighted components summing to 1.0,
judge returns `{"score": <mean>, "components": {...}}`).

- **clarifier** — questions that materially change the design (activity thresholds, what
  "risk" means numerically, zone geometry and proximity radius, history retention); concrete
  one-click suggested answers; and **scope preservation** — a clarifier that quietly drops
  "fighting" or the 24h history scores badly. This component encodes the kata's
  "requirements must not be made smaller" constraint.
- **architect** — telemetry and zone data model; distance/proximity approach; a
  classification design covering all six activities; an explicit risk rule grounded in
  breathing rate; a real-time transport choice with rationale; 24h history storage; boring
  stack; alternatives documented.
- **planner** — the load-bearing rubric. Tasks independently implementable; frozen contracts
  at the seams; detection engine separable from UI; no single task swallowing the app;
  dependency-respecting order; each task sized for one harness attempt.
- **qa** — test strategy for a *randomized real-time* system: deterministic tests over
  seeded or injected telemetry; boundary cases per activity class; risk-flag cases;
  history-window edges.
- **research** — was the risk threshold grounded in a citable source rather than invented;
  do citations support the claims made; was search budget spent on decisions that needed
  grounding rather than on ones the model already knew.

### 3. Pipeline wiring

Three changes, all mirroring existing call sites:

1. **`CaseSpec.research_enabled: bool = False`** (`benchmarks/models.py`), threaded into the
   per-cell `PipelineConfig` in `_cell_config` (`benchmarks/workflow.py`). Default `False`
   keeps both existing cases unchanged.
2. **`feature.py:730`** — replace the hardcoded `quality_score=None, judge="contract"` with
   a `self._judge(cfg, brief.model_dump_json(), "research", ...)` call and carry its score
   onto the record.
3. **`feature.py` task loop** — add a `stage="qa"`, `role="qa"` record judged against the
   `qa` rubric key, alongside the existing `stage="code"` contract record (Finding 4).

And one config change: `agents/research/agent.yaml` `provider: fake` → `tavily`.

### 4. Configuration

`TAVILY_API_KEY` lives in `.env` (gitignored; verified via `git check-ignore`). A
placeholder is documented in the tracked `.env.example`. The key appears in no committed
file.

## Risk: grounding failure aborts the whole run

`feature.py:717` is fail-closed. If `verify_brief_activity` returns any violations, the
workflow returns `rejected:research.grounding` **immediately** — before clarify, architect,
plan or any code task. This is not a gate (gates are `OFF` for benchmark cells and would
auto-approve); it is a hard return.

So enabling research on this case introduces a new way for the run to produce no app at
all, and the failure would be attributable to the grounding verifier rather than to
anything about the kata. Two consequences:

- Treat the first execution as a smoke run. If it ends at `rejected:research.grounding`,
  that is the verifier, not the case — inspect the brief's violations before touching the
  rubrics or the description.
- This is the strongest argument yet for keeping `research_enabled` default `False` on
  `CaseSpec`: the two existing cases must not inherit a new abort path.

## Testing

- `_build_judge_input` returns a `JudgeInput` for the `qa` and `research` keys — pure, no
  Temporal environment needed.
- A case carrying a `qa` rubric produces a record with `judge="llm_judge"`; one without
  produces the graceful `score=None` fallback. Same for `research`.
- `research_enabled` defaults `False` and both existing cases still expand to unchanged
  per-cell configs.
- The `stage="code"` record's deterministic `judge="contract"` score is unchanged by the
  new `stage="qa"` record — pinning Finding 4.
- Case assets load: `load_case_assets("cat-cafe-monitoring", ...)` returns all five rubrics.

No test makes a real model or Tavily call; the judge seam is `_set_judge_fn`, as today.

## Out of scope

- Widening the matrix beyond one cell.
- Any change to the deterministic quality gate or `scoring.py` weights.
- Egress policy on research fetches — that is E-18, and this design increases its urgency
  by making the research stage actually run.
