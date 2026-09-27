# Agent-eval landscape — Harbor's peers and what the benchmark can take

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD line (same rule as BENCHMARK's "new scope" items). |
| Date | 2026-09-27 |
| Companion to | [`2026-09-26-harbor-framework-analysis.md`](2026-09-26-harbor-framework-analysis.md). That note's §3 numbering is referenced below as H-3.x. |
| Method | Web search for Harbor's peers, then each source's docs or abstract. Papers were read at **abstract level only**, and no peer's source code was read. Kroker anchors were checked against `main` @ `eb34fe1`. |

## 1. The field in one paragraph

Only two peers are real *runners* in Harbor's sense:

- **Inspect AI** (UK AISI): mature and actively developed.
- **HAL** (Princeton): archived 2026-07-01.

METR's task-standard defines tasks, not runs. `verifiers` (Prime Intellect) is
built for RL. The rest of the field is **methodology**: papers on
long-horizon and multi-turn coding tasks, on shrinking a corpus without losing
rank order, and on reading logs rather than trusting outcomes. Harbor itself
has become an aggregator: per *Harbor Adapters* (arXiv 2609.04298) it supports
22 agents and 80+ benchmarks. That strengthens H-3.1: most corpora below are
reachable through one Harbor importer.

## 2. Runners and task standards

### 2.1 Inspect AI — <https://inspect.aisi.org.uk/>

A Task is a Dataset plus a Solver plus a Scorer. Inspect also provides:

- Docker and Kubernetes sandboxes;
- `.eval` logs with a web viewer;
- eval sets that run large collections;
- epochs with reducers;
- per-sample limits on tokens, cost, time and messages.

What Kroker can take:

- **Model proxy (`sandbox_agent_bridge`).** An external agent (Claude Code,
  Codex) calls the model API through a proxy inside the sandbox, and the
  proxy relays each request to the eval's chosen provider. The effects:
  - cost and tokens are measured per request, whatever the agent reports;
  - changing the model is configuration only.

  Kroker gets usage from whatever each harness reports into
  `HarnessRunResult`. A proxy would make per-role dollars uniform across
  harnesses. It would also close the "economics axis is blind for that
  harness" risk for cursor (BENCHMARK §3.1). `.workspace/bin/glm-shim` is a
  rudimentary version of the same seam.
- **Epochs and reducers** (`mean`, `at_least_k`, `pass_at_k`): the missing
  repeat mechanism, see §4.3.
- **Per-sample limits:** see §4.5.

### 2.2 HAL — <https://github.com/princeton-pli/hal-harness>

HAL is a harness plus leaderboard that reports cost next to accuracy. It
tracks cost through Weave. The repo was archived on 2026-07-01; the
leaderboard is closed, and the team has moved to reliability analysis.

What Kroker can take:

- **Cost/accuracy Pareto frontier** instead of a weighted scalar. Kroker's
  composite (`weights: quality 0.6 / cost 0.2 / speed 0.2`,
  `benchmarks/config.yaml`) hides the trade-off behind chosen weights. A
  frontier plot over existing records hides nothing.

### 2.3 METR task-standard — <https://github.com/METR/task-standard>

The standard is a `TaskFamily` interface with these methods: `get_tasks`,
`get_instructions`, `install`, `start`, `score` and `aggregate_scores`. It
also offers:

- manual scoring;
- auxiliary VMs for scenarios that cannot run in a container;
- per-task permissions.

What Kroker can take:

- **Intermediate scoring**: scoring during the run, not only at the end. This
  is BENCHMARK §4.1's "grade at each gate" (post-clarify, post-architecture,
  post-plan, post-QA, post-merge). That grade was designed; I did not find it
  in code.

### 2.4 verifiers (Prime Intellect) — <https://github.com/PrimeIntellect-ai/verifiers>

The library provides several environment classes: `SingleTurnEnv`,
`MultiTurnEnv`, `ToolEnv`, `StatefulToolEnv` and `SandboxEnv`. Grading uses
Rubrics made of weighted reward functions, and `JudgeRubric` adds a judge.
Environments are shared through a hub.

**What Kroker can take: nothing new.** It overlaps Harbor's Rewardkit
(H-3.7), and Kroker's staged judge and typed vetoes (E-83) already cover it.

## 3. Methodology sources

### 3.1 EvoCode-Bench — arXiv 2605.24110

The benchmark has 26 tasks of 5–15 rounds each:

- the workspace persists across rounds;
- tests are cumulative, so everything that passed before must still pass.

It uses two metrics:

- **MT@4**: the multi-round score, allowing up to four attempts per round.
- **SR**: the single-round score, started from a pre-completed prior state.

SR exceeds MT@4 by **22–40 pp**. The best agent by SR ranked only third on
persistent execution.

This is a ready design for the multi-step case (H-3.4) on Kroker's brownfield
mode:

- round N is a separate factory run on top of round N−1's output;
- the round-N oracle includes every earlier oracle;
- the SR-vs-MT gap is the regression and context-loss signal, and it is also
  a memory-axis metric (BENCHMARK §3.3).

### 3.2 RoadmapBench — arXiv 2605.15846

The benchmark has 115 long-horizon tasks. Each is built from a real
open-source version upgrade: 17 repos, 5 languages, about 3,700 lines over 51
files per task. The best model solves 39.1%.

**What Kroker can take: a source of decomposition-forcing cases**, which is
BENCHMARK §5's top corpus gap. It could be imported the same way DevEval was
(`importers/deveval.py`).

### 3.3 Efficient Benchmarking of AI Agents — arXiv 2603.23749

Keeping only tasks whose historical pass rate is 30–70% cuts the corpus by
44–70%. Rank order stays stable, even under distribution shift. The method is
grounded in item response theory.

**What Kroker can take:** a sweep that skips cases which always pass or
always fail. Kroker's corpus is small (10 cases) and a full matrix run takes
hours. The pass rates can be computed from records the benchmark already
stores.

### 3.4 Log analysis is necessary for credible evaluation of AI agents — arXiv 2605.08545

Outcome-only scores misstate capability in three ways:

- shortcuts and benchmark artifacts;
- scaffold failures, which make scores poor predictors of real use;
- dangerous actions hidden behind a pass.

Log analysis on τ-bench Airline found pass^5 under-elicited by nearly 50%.

This paper validates the direction Kroker already takes with `deep_review`
(E-39), `WasteBag` and `HarnessSession` (E-38). It adds:

- **pass^k**: success in all k attempts, not in any of them. For a factory,
  reliability matters more than best-of-k.
- **The paper's threat taxonomy** as a ready-made vocabulary for
  `error_class`.

### 3.5 Docent (Transluce) — <https://transluce.org/docent>

Docent summarises, clusters and searches agent transcripts against a rubric
("where did the agent reward-hack"). It ingests Inspect logs natively.

**What Kroker can take:** an off-the-shelf tool for the session anti-cheat
layer (BENCHMARK §2 Tier A (ii)). It becomes usable once sessions export to
ATIF (H-3.7) or to the Inspect log format.

### 3.6 Every Eval Ever — arXiv 2606.14516

A shared schema and repository for eval results: 22k models, 2.3k benchmarks,
31 source formats.

**Low value for Kroker.** It would help only if cross-publishing numbers ever
matters.

### 3.7 Not relevant

- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) and
  [SWE-Gym](https://github.com/SWE-Gym/SWE-Gym): environments for training SWE
  agents with RL.
- [awesome-evals](https://github.com/benchflow-ai/awesome-evals): a curated
  index, useful for finding more sources.

## 4. Candidates, verified against `main`

### 4.1 Pass-rate case selection

Pass rates are computed from stored `BenchmarkRecord`s. The sweep then drops
cases with a pass rate outside 30–70%, with a flag to force a full run.

- **Source:** §3.3.
- **Status:** New. It needs only data already stored.

### 4.2 Cost/quality Pareto grid

A sixth grid in `sdlc benchmark score`, next to the existing five: `heatmap`,
`task-matrix`, `error-matrix`, `waste-matrix` and `sc-rollup`.

- **Source:** §2.2.
- **Status:** Extends. The grid modules are pure `build_*`/`render_*` pairs,
  and `score.py` owns all filesystem writes.

### 4.3 Repeats per cell, pass@k and pass^k

A search of `src/sdlc/benchmarks/` found no repeat mechanism. Each cell runs
once, and within a cell `CHILD_ACT` has `RetryPolicy(maximum_attempts=1)`.

- **Sources:** Inspect's epochs (§2.1), pass^k (§3.4).
- **Status:** Gap verified. It merges with H-3.6.

### 4.4 EvoCode-style multi-round case

See §3.1 for the design: brownfield rounds, cumulative oracles, and the
SR-vs-MT gap.

- **Source:** §3.1.
- **Status:** New. It refines H-3.4.

### 4.5 Cost and time ceiling per cell

**Time:** capped. `CHILD_ACT` has `start_to_close_timeout=4h`
(`src/sdlc/benchmarks/workflow.py:51`).

**Cost:** the mechanism exists but is not wired.

- `PipelineConfig.run_budget_usd` exists, defaults to `0.0` (off), and is
  enforced by `_check_budget` (`src/sdlc/workflows/role_host.py:165`).
- The check is a `budget` gate with `default_policy=GatePolicy.HARD`, and
  anything other than APPROVE ends the run.
- `_cell_config` does not set it.

**Unverified: how the budget gate behaves in unattended cells.**
`BenchmarkSpec.gate_policy` defaults to SOFT. The models.py comment says a
HARD gate "will block a cell on `gate_timeout_hours` (default 48h)", and that
`--gate-policy off` auto-approves every gate. So the budget gate would either
stall the cell or be waved through. Neither behaves like a ceiling. Wiring it
needs a benchmark-specific rule: a crossing must **end** the cell and record
`error_class=budget`.

- **Source:** Inspect's limits (§2.1).
- **Status:** Extends, with one open point.

### 4.6 Model proxy for cost accounting

- **Source:** §2.1.
- **Status:** New, medium size. The existing seam is `glm-shim`.

### 4.7 RoadmapBench as a case source

- **Source:** §3.2.
- **Status:** New. The template is `importers/deveval.py`, or it could come
  through a Harbor importer if Harbor packages RoadmapBench (not checked).

## 5. Suggested order, merged with the Harbor note

1. **Regrade (H-3.3)**, **pass-rate selection (4.1)** and the **Pareto grid
   (4.2)**. All three are cheap and run over existing data.
2. **Repeats and pass^k (4.3 = H-3.6)** and the **cost ceiling (4.5)**. Both
   are about whether matrix numbers can be trusted, and repeats multiply
   cost, so the ceiling should land first.
3. **Multi-round case (4.4 = H-3.4)**: covers decomposition and the memory
   axis.
4. **Harbor importer (H-3.1)**, RoadmapBench (4.7), and the factory as a
   Harbor agent (H-3.2). All of these need a decision on Docker in the
   benchmark loop.
5. **Model proxy (4.6)** and **Docent via ATIF export (§3.5)**.

## Sources

- [Inspect AI](https://inspect.aisi.org.uk/) · [agent bridge](https://inspect.aisi.org.uk/agent-bridge.html)
- [HAL harness](https://github.com/princeton-pli/hal-harness)
- [METR task-standard](https://github.com/METR/task-standard)
- [verifiers](https://github.com/PrimeIntellect-ai/verifiers)
- [EvoCode-Bench](https://arxiv.org/abs/2605.24110)
- [RoadmapBench](https://arxiv.org/abs/2605.15846)
- [Efficient Benchmarking of AI Agents](https://arxiv.org/abs/2603.23749)
- [Log analysis is necessary for credible evaluation of AI agents](https://arxiv.org/abs/2605.08545)
- [Docent](https://transluce.org/docent)
- [Every Eval Ever](https://arxiv.org/abs/2606.14516)
- [Harbor Adapters and Harbor-Index](https://arxiv.org/abs/2609.04298)
- [awesome-evals](https://github.com/benchflow-ai/awesome-evals)
