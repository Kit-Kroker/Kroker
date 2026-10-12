# Benchmark improvement plan and research on external benchmark approaches

| | |
|---|---|
| Date | 2026-10-06 |
| Status | Proposal. Nothing here is implemented. |
| Scope | The benchmark harness (`src/sdlc/benchmarks/`), its records under `runs/benchmarks/`, and the case corpus (`benchmarks/cases/`) |
| Companion to | `BENCHMARK.md` (the measurement design), `docs/reports/deveval-import-report-2026-08-09.md` |

This document has three parts: what an audit of the stored records found,
what nine external benchmarks do and what is worth copying from each, and
the plan that follows.

## 1. Audit findings

The audit read the harness code and all 1,249 records in the 41 run
directories under `runs/benchmarks/` on 2026-10-05.

### 1.1 What the data contains

| Case | Runs | Reached code | Oracle result |
|---|---|---|---|
| cat-cafe-monitoring | 18 | 10 | mean 0.71, sd 0.23, range 0.25 to 1.0 (12 tests) |
| todo-api-greenfield | 5 | 5 | 1.0 on every run (6 tests) |
| crew-probe, herdr-probe | 18 | n/a | no oracle |
| add-login-greenfield, six deveval cases | 0 | n/a | never run |

Every case is a 1x1 matrix (opencode with glm-5.2), so no difference
between two arms has ever been measured.

### 1.2 Defects in the collected metrics

| # | Finding | Evidence |
|---|---|---|
| F1 | Rubric scores are never collected: 0 of 418 rubric-eligible records carry a score. | In the worker container `benchmarks/judge.py` resolves `_CASES_DIR` to `/app/.venv/lib/python3.13/benchmarks/cases`, which does not exist. `load_case_assets` skips missing files silently, so the rubric map is empty and the judge is never called. The oracle works because `oracle.py` honours `SDLC_CASES_ROOT`. The August probe runs are empty too; where those ran was not traced. |
| F2 | Aborted runs are scored as quality zero. | 8 of 18 cat-cafe runs stopped in research or clarify and still received an oracle record, flagged only as "language mismatch". 7 scored 0.0. The cross-run report shows 0.421 against 0.71 for the runs that produced code. |
| F3 | One aborted run scored 6 of 12 on an empty tree. | Run `bench-cat-cafe-monitoring-1791216395` has only the init commit on its integration branch. Its score equals that of the run that finished one minute before it started. Cause not found; it points at an oracle environment that is not isolated between runs. |
| F4 | qa and review wall-clock are copies of code. | All 297 code/review pairs differ by under one second. The qa record reuses the attempt's start time (`stages/code/step.py:811`). |
| F5 | Cost is partial. | Code is $0.00 on all 200 opencode records (tokens are present). Review records have no cost or tokens. Research is close to half of the measured dollars. |
| F6 | Waste counters are all zero. | On 278 code records every `WasteBag` field except `model_turns` is 0. |
| F7 | "Quality" on code, review, merge and analyze is pass/fail re-encoded. | Code's 0.725 is the share of attempts that passed, not of tasks. qa's outcome is copied from code's. |
| F8 | The analyze and merge gates reject every benchmark run. | 14 of 14 on the two oracle cases, including the four todo-api runs that scored 6 of 6. |
| F9 | The composite score is meaningless on a single cell. | Cost and speed are normalised against the slowest record in the same cell (`scoring.py:108-111`). Analyze gets 0.196 with quality 0.0. |
| F10 | Provenance is missing. | `prompt_sha` is hardcoded to `""` (`record_builder.py:68`). No record carries the Kroker commit. The ten graded cat-cafe runs span Oct 3 to 5 while 008, 009 and C12 landed. |
| F11 | Labels do not join. | Oracle records carry the arm name (`zai-coding-plan-glm-5.2`), code records the model id (`zai-coding-plan/glm-5.2`). Two files and two report rows per cell. |
| F12 | Case-scoped reports show global success criteria. | SC-1, SC-4 and SC-6 are computed over every summary in `runs/pipeline`, mostly `bf-e2e-*` runs. |
| F13 | No calibration exists. | `benchmarks/calibration/` holds only its README. |
| F14 | The heatmap counts one failure three times and hides attrition. | A failed attempt adds a reject to code, a fix attempt to code and a reject to qa. Research, where 4 of 18 runs ended, is the coolest cell. Colour is relative to each grid's own maximum. |
| F15 | The `plan` stage never shows a trust value. | `STAGE_TO_RUBRIC` is keyed on `planning`; records use `plan`. |

### 1.3 Statistical power

Todo-api is saturated and cannot separate two arms. Cat-cafe has a 95%
interval of roughly 0.55 to 0.87 on ten runs. With sd 0.23, detecting a
0.10 difference between two arms on this one case needs about 80 runs per
arm, and 0.20 needs about 20, at around 3.5 hours per run.

## 2. Research: how external benchmarks approach the problem

Method: web search on 2026-10-06, then a read of each paper's HTML version
through a summarising fetch. Long papers were cut at 100,000 characters, so
appendices were mostly not read. DevEval, Commit0 and SWE-bench details
beyond their abstracts are from memory and marked as such. Repositories
were not cloned and licences of the datasets themselves were not checked.

### 2.1 Summary

| Benchmark | Tasks | Language | Agent input | Grading | Runs per task | Dataset |
|---|---|---|---|---|---|---|
| NL2Repo-Bench | 104 | Python | One requirements document, empty workspace | Upstream pytest suite, hidden | 1 | GitHub |
| PRDBench | 50 | Python | PRD plus criteria scheme | 1,258 scripted checks, fine-tuned judge | 1 (judge x3) | GitHub, CC BY 4.0 paper |
| E2EDevBench | 50 | Python | Verified requirements document | Migrated tests plus per-requirement LLM check | 1 (3 in a side study) | Anonymous repo |
| ProjDevBench | 20 | Mostly C++ | Problem statement, sometimes partial code | Online judge 80%, code review 20% | 1 | GitHub |
| SlopCodeBench | 36 problems, 196 checkpoints | Python track | Spec per checkpoint, own prior workspace | Hidden tests in four categories | best run reported | scbench.ai |
| RoadmapBench | 115 | Python, TS, Go, Rust, C++ | Repo snapshot plus multi-target roadmap | Weighted subtask tests, hidden | 1 | not stated |
| DevEval / DevBench | 22 repos (memory) | Python, C/C++, Java, JS (memory) | PRD, UML, architecture per stage | Tests, LLM judge for design | n/a | GitHub |
| Commit0 | 54 libraries (memory) | Python | Spec plus visible unit tests | Unit tests, lint feedback | n/a | GitHub |
| SWE-bench Verified | 500 (memory) | Python | Issue text plus repo | Hidden fail-to-pass tests | n/a | Hugging Face |

Two patterns stand out. Almost every benchmark runs each task once and
reports no interval, so none is a model for variance handling. And every
one that reports cost, turns or failure causes does so per task, not per
pipeline stage: stage attribution remains specific to Kroker.

### 2.2 NL2Repo-Bench

**Approach.** 104 real Python libraries, chosen by four filters: 300 to
120,000 lines of code, at least 10 stars, a passing pytest suite, activity
in the last three years. Annotators reverse-engineered each repository into
a requirements document with four fixed sections (project description,
dependencies and structure, API usage guide, implementation notes), helped
by an AST pass that lists every public element. The agent gets that
document, about 18,800 tokens on average, and an empty workspace. Grading
runs the upstream pytest suite in a per-task Docker image. Tasks are tiered
by size: easy up to 1,500 lines (26), medium to 4,000 (46), hard above (32).

**What it measures beyond pass rate.** Interaction turns with standard
deviation, tool-use counts, early-termination rate (one model stops early
on 49% of tasks), non-finish rate (84.5% for another), and a turns-per-score
efficiency ratio. Use of a task-tracking tool correlates 0.71 with score.

**Results.** Best agent 40.2% of tests. The paper reports that the choice
of framework matters little compared with the model.

**Weaknesses.** One run per task, no intervals. No contamination control
beyond rewriting the spec: the libraries are public. The API usage guide
hands the agent the interface, which removes most of the architecture
decision.

**For Kroker.**
- The nearest match to the existing oracle path (Python, pytest, hidden
  suite). Import candidates should come from the easy tier first.
- Copy the early-termination and non-finish rates. They are the same idea
  as the attrition layer and Kroker records neither.
- The frozen API guide is the same device as the "interface contract"
  block in `cat-cafe-monitoring/case.yaml`. It is what makes a hidden
  suite gradeable, at the cost of not testing interface design.

### 2.3 PRDBench

**Approach.** 50 Python projects in 20 domains, from user requests on an
internal platform, course final projects and thesis reproductions.
Annotation is agent-driven: an agent drafts the PRD, a metric outline, a
scaffold and a criteria scheme; a human runs the tests and feeds back for
at least five rounds; the scaffold is then removed. About eight hours of
human time per project. Grading uses 1,258 checks: 408 pytest units, 732
shell interactions compared with expected output, 118 file comparisons,
about 25 per project. A fine-tuned judge (PRDJudge) executes them.

**What it measures beyond pass rate.** Two rounds per agent: development,
then debugging with the score report as feedback. Judge agreement with
humans is 91.75% in domain and 92.69% out of domain; three judge runs per
check give 94.19% unanimous agreement. Tool calls and tokens per check.

**Results.** Development 11% to 69%, debug 21% to 70%. Several agents get
worse in the debug round because local fixes break working modules.

**Weaknesses.** The agent is shown the criteria scheme, so the oracle is
not held out in the sense of `BENCHMARK.md` Tier A. The free-development
mode, with no fixed interface, is called noisy by the authors themselves.
One agent run per project.

**For Kroker.**
- The two-round design maps onto the fix loop. Reporting first-attempt
  score and after-repair score separately is the per-run version of
  first-pass yield.
- Three judge runs per check with a unanimous-agreement rate is a cheap
  stability number to add to `sdlc calibrate`.
- Shell-interaction and file-comparison checks are oracle types Kroker
  does not have. They suit CLI and data-processing cases where an HTTP
  contract does not apply.
- Eight hours per project is a realistic budget for authoring a private
  case with agent help.

### 2.4 E2EDevBench

**Approach.** 50 PyPI projects, ten sampled per quarter from 2024-Q1 to
2025-Q1, filtered for more than five Python files, a pytest suite, no
external APIs, and a buildable sandbox. The agent gets a manually verified
requirements document. Grading has two halves. A separate test-migration
agent adapts the original tests to the generated project's layout. An LLM
marks every item on the requirements list as implemented or not.

**Validation of the judge.** Three graduate students scored 546
requirements across ten projects. Agreement with the LLM was 76% to 84%
pairwise, Pearson above 0.62.

**What it measures beyond pass rate.** Tokens sent (3.6M to 20.9M), cost
($4.85 to $7.05), agent steps (77 to 371), lines and files produced. Two
taxonomies of failed requirements:

- By symptom: missing feature 32.4%, incomplete 18.1%, incorrect 34.1%,
  upstream failure 15.3%.
- By root cause: planning 55.8% (omission 27.9%, misinterpretation 22.2%,
  design flaw 5.6%), execution 38.6%, verification 5.7%.

**Results on architecture.** Three workflows on one base agent: single
agent, developer plus tester, and designer plus developer plus tester. The
developer-tester split scored best (53.5% of requirements). The three-role
waterfall scored worst (32.8%): the design phase produced flawed plans and
the developer followed the plan in preference to the requirements.

**Stochasticity.** Three repeats of one configuration fulfilled 796
requirements in all three runs and 526 in only one. A single run misstates
what a configuration can do by a wide margin.

**Contamination control.** Sampling by quarter lets the authors compare
projects after the model's cutoff (42%) with earlier ones (40%).

**Weaknesses.** Two models from one vendor. Test migration is itself an
agent and can be wrong. No significance tests.

**For Kroker.**
- The most relevant paper found. Kroker is a designer-developer-tester
  pipeline, and this is direct evidence that an upstream plan can lower
  the result. `PlanDrift` already measures plan adherence; pairing it with
  the oracle score per run would test the same effect.
- Per-requirement grading with a root-cause label is what `tasks.yaml`
  and the error matrix are reaching for. The root-cause taxonomy
  (planning, execution, verification) is a better column set for the
  error matrix than the current six error classes, because it names the
  stage to fix.
- The 76% to 84% human agreement sets expectations for rubric
  calibration: `BENCHMARK.md` asks for a threshold of 0.75 within 0.15.
- The 796 versus 526 result is the argument for repeats.
- Time-sliced sampling is a contamination check that can be applied to
  any import: prefer projects newer than the cutoff of the models in use.

### 2.5 ProjDevBench

**Approach.** 20 problems filtered from about 2,800 on a university online
judge, in eight categories, mostly C++. Some start from a partial codebase,
the hard ones from nothing. The agent submits to the judge itself, with a
per-problem submission limit of 2 to 18.

**Grading.** `final = 0.8 * execution + 0.2 * code_review`. Execution is
the weighted share of judge test points. Code review is seven rule checks
plus an LLM read; against human labels it reaches accuracy 0.852 and
Cohen's kappa 0.710.

**What it measures beyond pass rate.** Verdict mix over all submissions:
accepted 27.4%, wrong answer 41.9%, time limit 13.9%, runtime error 7.0%,
compile error 4.5%, memory leak 3.5%, memory limit 1.4%. Tokens and turns
correlate negatively with score (Spearman -0.73 and -0.67): long runs are
struggling runs.

**Weaknesses.** Twenty tasks, one language family, one pass, no
contamination discussion. The score is the best of several submissions,
which rewards retrying against the grader.

**For Kroker.**
- Resource verdicts (time and memory limits) are a quality dimension the
  current oracles do not have.
- The negative token-score correlation is worth checking on Kroker's own
  runs. If it holds, tokens per run is an early warning before the
  oracle runs.
- Do not copy the blended 80/20 score. It has the same problem as the
  current composite: two instruments on one scale.

### 2.6 SlopCodeBench

**Approach.** 36 hand-written problems split into 196 checkpoints, three to
eight each. At each checkpoint the agent gets a new specification and its
own workspace from the previous checkpoint, never the tests. Each
checkpoint runs in a fresh Docker container as a non-root user; only the
working directory persists. Two-hour limit per run.

**Grading.** Four hidden test categories: core, error handling,
functionality, and regression (every earlier checkpoint's tests). A
checkpoint is strictly solved only if all pass.

**Quality metrics, defined precisely.**

- Structural erosion: the share of complexity mass sitting in functions
  with cyclomatic complexity above 10, where
  `mass(f) = CC(f) * sqrt(SLOC(f))`, measured with Radon.
- Verbosity: lines flagged by 137 AST-grep rules, united with cloned
  lines, divided by lines of code.

Both are compared with a human baseline of 473 open-source repositories:
agents are 2.3 times more verbose and 2.0 times more eroded, and erosion
rises in 77% of trajectories.

**Results.** Best agent strictly solves 14.8% of checkpoints. A prompt
asking for cleaner code cuts verbosity and erosion by about a third, costs
12% more and loses 2.3 points of correctness.

**Weaknesses.** Python only. Reports the best run. Hand-written problems
are expensive to extend.

**For Kroker.**
- Erosion and verbosity are deterministic, cheap, and computable on the
  integration branch after every run with tools already common in Python
  projects. They are a second objective quality axis next to the oracle,
  and they do not need a judge.
- Regression tests as a separate category fit multi-task plans: does task
  7 break what task 3 delivered. Kroker's per-task QA cannot see that;
  the oracle only sees the final state.
- Fresh container per stage with only the workspace persisting is the
  isolation model that would rule out finding F3.
- A checkpointed case is a natural test of the memory axis: the same
  project extended across runs.

### 2.7 RoadmapBench

**Approach.** 115 tasks from 17 repositories in five languages. Each task
is a real version upgrade: the agent starts at the source release and gets
a roadmap of about five targets. Median reference change is 3,700 lines in
51 files. Git history is kept but future branches and tags are pruned, and
repository names and version numbers are anonymised in the instruction.

**Construction quality control.** After static checks, agents from three
capability tiers attempt every task. Each failure is attributed to the task
or to the model. 45 of 115 tasks needed at least one repair, 3.1 rounds on
average. A task is accepted when the reference solution scores full marks,
no task-side errors remain, and the tiers produce distinguishable scores.

**Grading.** Weighted partial credit per task,
`score = sum(w_k * r_k) / sum(w_k)`, reported next to the all-or-nothing
resolved rate.

**Failure taxonomy over 3,603 failed subtasks.** Implementation error
38.5%, build error 28.3% (cascading 15.8%), missing implementation 22.6%,
interface mismatch 6.5%, agent abandoned or exhausted 4.0%.

**Results.** Best model 39.1% resolved, completion score 0.69.

**Weaknesses.** One trial per model. The authors note sensitivity to the
agent scaffold. Tests check behaviour only.

**For Kroker.**
- The acceptance rule for a task is the most reusable idea in this
  section: reference solution passes, and agents of different strength
  score differently. Todo-api fails the second half and should have been
  caught at authoring time. `benchmark verify-case` already checks the
  first half for imported cases.
- Reporting completion score and resolved rate side by side is the fix
  for the binary oracle column in the heatmap.
- "Cascading build error" as its own category separates one root failure
  from the many test failures it causes. The 0 of 12 oracle results in
  Kroker are mostly this.
- A source of brownfield and multi-language cases when the toolchain
  adapters beyond Python exist.

### 2.8 Harness-as-variable studies

**"Same Model, Different Harness"** holds weights, tasks, context size and
evaluator fixed and changes one harness package (how old tool results are
shortened). On a 169-task SWE-bench Verified cohort with a 20,480-token
window the mean fail-to-pass fraction moves from 28% to 49%.

Its methods are the part to copy:

- Paired design. Each task runs once per arm; the unit of analysis is the
  per-task difference.
- A partial-credit metric (fail-to-pass fraction) because binary
  resolution throws away progress on unresolved tasks.
- Exact sign test on the direction of the per-task difference, exact
  McNemar test on resolution, 95% intervals from a paired bootstrap with
  a recorded seed.
- A fixed time budget per attempt, with turns and tokens reported per arm
  so that "better" is not confused with "worked longer". Here the
  treatment arm used about twice the prompt tokens.
- A stated list of what to report: model, harness, tool interface,
  model-visible context, context limit and policy, time limits, and the
  rule that picks the final result.

It states its own limit plainly: greedy decoding, one trajectory per arm,
so run-to-run variation is not measured.

**"An Empirical Study of Harness Design for Coding Agents"** (abstract
only) varies planning, action space and context management over 176 matched
settings on SWE-bench Verified and Terminal-Bench. Planning lowers cost for
strong models without raising accuracy.

**For Kroker.** Both support the stance in `BENCHMARK.md` section 0. The
paired-by-case design is how to get a usable comparison from few runs: ten
cases run under two arms give ten paired differences, and case-to-case
difficulty cancels out. That needs more cases, not more repeats of one.

### 2.9 DevEval, Commit0, SWE-bench (already known)

- **DevEval / DevBench.** The only benchmark that grades the stages
  separately (design, environment setup, implementation, acceptance tests,
  unit tests) and ships reference design artifacts. Six cases are already
  imported with 79 tests regrouped into 31 requirements. They have never
  been run. Design is graded by an LLM judge.
- **Commit0.** Python libraries rebuilt from a specification with the unit
  tests visible and lint feedback available. Useful as large greenfield
  cases if the tests are held out locally.
- **SWE-bench Verified.** Human-validated issue-fix tasks with hidden
  tests. Brownfield only. The standard external anchor, and the most
  exposed to contamination.

## 3. What to adopt

| Idea | Source | Addresses |
|---|---|---|
| Record aborted, early-terminated and non-finished runs as their own rates | NL2Repo-Bench, RoadmapBench | F2, F14 |
| Partial-credit score reported next to the all-or-nothing rate | RoadmapBench, Same Model Different Harness | F14 |
| Per-requirement grading with a root-cause label naming the stage | E2EDevBench | error matrix, F14 |
| First-attempt and after-repair scores reported separately | PRDBench | F7 |
| Judge repeated three times with a unanimous-agreement rate | PRDBench | F13 |
| Human agreement target of roughly 0.8 for an LLM requirement judge | E2EDevBench, ProjDevBench | F13 |
| Deterministic code-quality metrics (erosion, verbosity) on the result | SlopCodeBench | second objective axis |
| Fresh container per grading step, only the workspace persists | SlopCodeBench | F3 |
| Case acceptance rule: reference passes, tiers separate | RoadmapBench | saturated cases |
| Paired-by-case comparison with sign test and bootstrap interval | Same Model Different Harness | section 1.3 |
| Fixed budget per run, tokens and turns reported per arm | Same Model Different Harness | F5, F9 |
| Report the full configuration with every result | Same Model Different Harness | F10 |
| Prefer source projects newer than the model cutoff | E2EDevBench | contamination |

Not adopted:

- A blended score such as ProjDevBench's 80/20. It repeats the composite
  problem (F9).
- Showing the criteria to the agent as PRDBench does. It gives up the
  held-out property.
- Best-of-N reporting. It hides variance.

## 4. Plan

### Decisions

- **cat-cafe-monitoring stays.** It is the only private case and it
  discriminates. Stop running it until Phase 1 is done, then extend its
  oracle.
- **todo-api-greenfield becomes a smoke test.** It passes 6 of 6 every
  time and fails the RoadmapBench acceptance rule.
- **More cases with few repeats, not few cases with many.** About ten
  cases at three to five runs each, compared pairwise by case.

### Phase 1. Make the records trustworthy

No new benchmark runs until this phase is done.

| # | Task | Closes |
|---|---|---|
| 1.1 | Judge, report, calibration and config loaders honour `SDLC_CASES_ROOT`. A registered rubric or veto file that is missing fails the cell. | F1 |
| 1.2 | An aborted cell is recorded as not graded: score `None`, a completion flag, the last stage reached. | F2 |
| 1.3 | Reproduce the empty-tree 6 of 12 result. Run the oracle in a fresh environment per grade. | F3 |
| 1.4 | Stamp every record with the Kroker commit and real prompt hashes. | F10 |
| 1.5 | One cell label shared by oracle and code records. | F11 |
| 1.6 | qa and review get their own timings and their own verdicts. Review records its tokens. | F4, F5, F7 |
| 1.7 | Repair or disable the analyze and merge gates in benchmark mode. | F8 |
| 1.8 | Map the `plan` stage to its rubric key. | F15 |

Exit: a todo-api smoke run produces rubric scores on clarify and
architecture, a commit on every record, and one file per cell.

### Phase 2. Rework the scoring output

| # | Task | Closes |
|---|---|---|
| 2.1 | Drop the composite until a case has at least two arms. | F9 |
| 2.2 | Replace the summed heatmap with layers on shared stage columns: attrition, first-attempt failure rate, wasted tokens, oracle per run. Fixed colour scales. Cells show their denominator and grey out under five observations. | F14 |
| 2.3 | Run-by-run view as the main grid, grouped by commit and arm, with mean and spread on top. | F10, F14 |
| 2.4 | Oracle column shows partial credit next to the all-pass rate. | F14 |
| 2.5 | Gate-versus-oracle agreement and escape rate per gate. | F8 |
| 2.6 | First-attempt and after-repair scores as separate columns. | F7 |
| 2.7 | Success-criteria rollup scoped to the case being scored. | F12 |
| 2.8 | Parse opencode sessions so the waste counters are populated. | F6 |
| 2.9 | Erosion and verbosity computed on the integration branch after each run. | new axis |

Exit: `sdlc benchmark score --case cat-cafe-monitoring` on the existing
records shows 8 runs lost before code and no cell counted twice.

### Phase 3. Fix the corpus

| # | Task |
|---|---|
| 3.1 | Run the six imported DevEval cases once each. Keep the ones where the result is neither 0 nor 1. |
| 3.2 | Grow the cat-cafe oracle from 12 tests to 30 to 40 and add a `tasks.yaml` mapping tests to requirements. |
| 3.3 | Import 5 to 10 NL2Repo-Bench tasks from the easy tier, preferring projects newer than the models' cutoff. Check the dataset licence first. |
| 3.4 | Add a case acceptance check: the reference solution passes the oracle, and a weak and a strong arm score differently. |
| 3.5 | Add root-cause labels (planning, execution, verification) to the error matrix. |
| 3.6 | Keep todo-api as the smoke test that runs before any batch. |

Exit: at least eight cases pass the acceptance check, at least two of them
private.

### Phase 4. Start measuring

| # | Task |
|---|---|
| 4.1 | Hand-score 20 to 30 fixtures per rubric and run `sdlc calibrate`, with three judge repeats per fixture. |
| 4.2 | Baseline: three to five runs per case on one pinned commit, fixed budget per run. |
| 4.3 | First comparison with two arms, paired by case: per-case difference, sign test, bootstrap interval. Dev model or harness is the cheapest variable. |
| 4.4 | Report tokens and turns per arm next to every quality difference. |
| 4.5 | Never launch runs in parallel on this machine. |

### Order

Phase 1 is first because everything else reads those records. Phases 2 and
3 are independent of each other and can overlap. Phase 4 needs all three.

## 5. Open questions

- What killed the eight cat-cafe runs in research and clarify. Three were
  launched within two minutes of each other, which suggests load, but it
  was not traced.
- Whether opencode token counts are complete enough to stand in for cost,
  given that the subscription reports $0.
- Whether a checkpointed case in the SlopCodeBench style is worth
  authoring for the memory axis, or whether that waits for the retro
  stage.

## Sources

- [NL2Repo-Bench (arXiv 2512.12730)](https://arxiv.org/html/2512.12730), [repository](https://github.com/multimodal-art-projection/NL2RepoBench)
- [PRDBench (arXiv 2510.24358)](https://arxiv.org/html/2510.24358v2), [repository](https://github.com/AGI-Eval-Official/PRDBench)
- [E2EDevBench (arXiv 2511.04064)](https://arxiv.org/html/2511.04064)
- [ProjDevBench (arXiv 2602.01655)](https://arxiv.org/html/2602.01655), [repository](https://github.com/zsworld6/projdevbench)
- [SlopCodeBench (arXiv 2603.24755)](https://arxiv.org/html/2603.24755), [site](https://www.scbench.ai)
- [RoadmapBench (arXiv 2605.15846)](https://arxiv.org/html/2605.15846)
- [Same Model, Different Harness (arXiv 2608.26218)](https://arxiv.org/html/2608.26218), [repository](https://github.com/sydches/yuj)
- [An Empirical Study of Harness Design for Coding Agents (arXiv 2609.20804)](https://arxiv.org/abs/2609.20804)
- [DevEval (arXiv 2403.08604)](https://arxiv.org/abs/2403.08604), [repository](https://github.com/open-compass/DevEval)
- [Commit0 (arXiv 2412.01769)](https://arxiv.org/abs/2412.01769)
