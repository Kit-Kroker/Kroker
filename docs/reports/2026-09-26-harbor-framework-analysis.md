# Harbor framework — what the benchmark can take

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD line (same rule as BENCHMARK's "new scope" items). |
| Date | 2026-09-26 |
| Source | [`harbor-framework/harbor`](https://github.com/harbor-framework/harbor) (the Terminal-Bench 2.0 harness) and its docs at [docs.harborframework.com](https://docs.harborframework.com/llms.txt) |
| Method | Read the docs pages on tasks, verifier, separate verifier, multi-step, regrade, job configs, metrics, custom agents, ATIF and Rewardkit. Harbor's source code was **not** read. Kroker anchors were checked against `main` @ `eb34fe1` (`src/sdlc/benchmarks/`, `benchmarks/cases/`). |

## 1. What Harbor is

Harbor evaluates **one agent in a sandbox**. A task is a directory:

```
my-task/
├── instruction.md        # what the agent is told
├── task.toml             # metadata, timeouts, network policy, resources, artifacts
├── environment/          # Dockerfile | docker-compose.yaml | Apptainer.def
├── solution/solve.sh     # reference solution (run by the built-in `oracle` agent)
└── tests/test.sh         # verifier; writes /logs/verifier/reward.txt or reward.json
```

A **job** crosses agents × models × tasks. Each crossing is a **trial** that
runs in a local Docker container or on a cloud provider (Daytona, Modal,
etc.). Beyond the core loop, Harbor provides:

- **Separate verifier.** The verifier can run in its own environment, with
  the agent's declared artifacts handed over explicitly.
- **Regrade.** A new verifier can be run against recorded outputs. No agent
  environment is started, so there is no new agent cost.
- **Multi-step tasks.** A `steps/` directory holds sequential steps. Each
  step has its own tests, and `min_reward` stops the run early when a step
  scores too low.
- **Retries and attempts.** A job sets `n_attempts`, and `retry` does
  exponential backoff filtered by exception type.
- **Simulated user.** A `user_agent` can drive a multi-turn conversation
  with the agent.
- **ATIF.** A JSON trajectory format (v1.7), with support for embedded
  subagent trajectories.
- **Rewardkit.** A library of verifier criteria, including LLM and
  agent-as-judge, with `weighted-mean`, `all-pass` and `required-pass`
  aggregation.
- **Registry.** Ready-made datasets, among them Terminal-Bench 2.0,
  SWE-Bench and Aider Polyglot.

## 2. Why Harbor cannot be the runner

Harbor and Kroker measure different systems. Kroker's system under test is the
multi-stage Temporal pipeline. Harbor's model has no place for most of what
Kroker measures:

- the per-stage gates;
- the ADR-6 family-decorrelated judge;
- the case × stage heatmap;
- the per-role cost from `RunSummary.roles`;
- session-derived waste (`WasteBag`).

Inside Harbor the factory would be a black box that returns one reward.

There is also a practical limit. Benchmark runs cannot run in parallel with
live pipeline runs, and the task queue name `ai-sdlc` is hardcoded. Harbor's
main strength, thousands of parallel cloud sandboxes, therefore does not help
until that changes.

So Harbor is a **source of datasets, format conventions and mechanisms**,
plus one integration point (§3.2). It is not a replacement for
`BenchmarkWorkflow`.

## 3. Candidates, ranked by value

### 3.1 Harbor dataset importer — `sdlc benchmark import-harbor`

The external anchors that BENCHMARK.md §5 calls for ("public anchors …
SWE-bench-Verified-style") are available in Harbor's registry, already
normalised. The task format maps almost one-to-one onto a Kroker case:

| Harbor | Kroker |
|---|---|
| `instruction.md` | `case.yaml: description` |
| `tests/` + `test.sh` | `oracle/` |
| `solution/solve.sh` | `reference/`, `reference_env/` |
| `task.toml` | `case.yaml` |
| `--agent oracle` run | `importers/verify.py` (oracle must pass on the reference, E-79) |

- **Template:** `src/sdlc/benchmarks/importers/deveval.py`.
- **Missing piece:** `oracle.py` grades only through a ToolchainAdapter plus
  JUnit (`grade_from_junit`). Imported cases need a second path that runs
  `test.sh` as a black box and reads `reward.json`.
- **Status:** New. It needs Docker in the benchmark loop, because Harbor's
  environments are container images.

### 3.2 The factory as a Harbor custom agent

Harbor supports **external agents** (`BaseAgent`). Their loop lives outside
the sandbox and drives it through `BaseEnvironment`. A wrapper would:

1. copy `/app` out of the container into a scratch repo;
2. run the pipeline on that repo;
3. write the result back into the container.

- **Payoff:** on the same tasks, a comparison of *factory vs bare
  claude-code / codex / opencode*. That answers the product's core question:
  does the SDLC pipeline add anything over a single agent? The current matrix
  has no such row, because the harness axis varies the harness *inside* the
  factory.
- **Cost:**
  - Docker on the Windows host;
  - moving state between the container and a git worktree;
  - the queue limit from §2.
- **Status:** New.

### 3.3 Regrade — re-run the oracle without re-running the pipeline

`sdlc benchmark score` re-scores records it already has, under new weights. It
does not re-execute the oracle. `BenchmarkWorkflow` already keeps the produced
SHA (`_keep_sha`, `src/sdlc/benchmarks/workflow.py`). So `sdlc benchmark
regrade` reduces to four steps:

1. check out the SHA;
2. copy in the new `oracle/`;
3. run `grade_oracle`;
4. write fresh oracle records.

- **Payoff:** it hits OQ-B1 (oracle authorship cost) directly. A flawed
  oracle test can be fixed and the whole corpus re-graded in minutes, at zero
  agent cost.
- **Status:** Extends. The seam and the stored SHA exist. Cheapest item on
  this list.

### 3.4 Multi-step cases (`steps/` + `min_reward`)

A multi-step case is a sequence of steps in one shared environment. Each step
has its own tests, and a result below the threshold stops the run. This
covers two gaps named in BENCHMARK.md:

- **Decomposition-forcing case** (§5, the top corpus gap).
- **Memory axis** (§3.3). In Kroker terms, step 2 is a separate factory run
  on top of step 1's output, with a fresh session. The `memory.enabled`
  on/off delta shows up here, and nowhere else in a single-shot case.

**Status:** New case shape. The runner needs step sequencing plus per-step
oracle records.

### 3.5 Simulated user at the clarification gate

Harbor's `user_agent` plays a user in a multi-turn conversation. The Kroker
analogue is a model that answers the clarifier's questions from a hidden full
spec. `sc_rollup.py` already counts `answered_by == "human"`.

- **Payoff:** reproducible gate answers instead of manual ones.
- **Unlocks:** cases with deliberately incomplete specs, which test whether
  the clarifier asks the right questions.
- **Status:** New.

### 3.6 Attempts per cell, and infra-vs-agent failure split

A search of `matrix.py` found no repeat or pass@k mechanism. With 10 cases,
one run per cell is noise. Harbor also keeps two kinds of failure apart:

- infrastructure failures, which are retried with backoff;
- agent failures, which go into the grade.

- **Check needed:** confirm that Kroker's `error_class` keeps infrastructure
  failures out of the quality number.
- **Status:** Gap to verify. The repeat mechanism was not found, and absence
  was not proven beyond that search.

### 3.7 Smaller items

- **ATIF export of `HarnessSession`:** gives Harbor's trajectory viewer and
  interop for free. Embedded subagent trajectories fit crew. Status: New,
  low priority.
- **Per-phase network policy:** the agent runs with no network and the
  verifier runs on an allowlist. This would solve the DevEval cases
  quarantined behind `network_required` (E-21). Status: New, blocked on
  Docker in the loop.
- **Rewardkit patterns:**
  - `required-pass` aggregation, which overlaps typed vetoes (`vetoes.py`);
  - negated criteria;
  - an agent-as-judge with a read-only mount of the repo;
  - criteria scored on the trajectory.

  The staged judge (E-83) covers most of this already. Status: Extends, low
  priority.

## 4. Not taken

- **Cloud sandbox providers:** the queue limit from §2 applies.
- **Harbor Hub, leaderboards, hosted jobs:** not relevant to an in-repo
  instrument.
- **RL rollout generation:** out of scope.
- **Harbor's metric aggregation** (`mean` plus a per-dataset `metric.py`):
  Kroker's five grids and the quality/cost/speed composite are richer.

## 5. Suggested order

1. **Regrade (§3.3):** cheap, with immediate payoff.
2. **Harbor importer (§3.1):** external anchors.
3. **Multi-step case (§3.4):** decomposition plus the memory axis.
4. **Factory as a Harbor agent (§3.2):** the factory vs bare-agent
   comparison.
5. **Simulated user (§3.5).**

Items 2 and 4 both require Docker in the benchmark loop, which today runs on
local worktrees. That is a separate decision to take before either one is
specced.
