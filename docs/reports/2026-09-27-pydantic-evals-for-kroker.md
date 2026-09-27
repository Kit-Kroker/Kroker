# Pydantic Evals — what Kroker's eval stack can take

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD or ROADMAP line. |
| Date | 2026-09-27 |
| Companions | `2026-09-27-pydantic-ai-harness-comparison.md`, `2026-09-27-pydantic-ai-capability-adoption-map.md`, `2026-09-26-harbor-framework-analysis.md` |
| Source | The 22 Pydantic Evals guide pages (overview, quick start, core concepts, evaluators overview, built-in, LLM judge, standard quality metrics, third-party integrations, custom, report evaluators, span-based, agentic, online evaluation, Logfire integration, dataset management, dataset serialization, concurrency, multi-run, retry strategies, metrics and attributes, case lifecycle, simple validation) and the API pages for `online_capability` and `generation`, read in prose. The other API reference pages were consulted only for two signatures (`Dataset.evaluate`, `EvaluationReport` baseline). |
| Method | Docs read; Kroker anchors checked against `main` @ `eb34fe1`. `pydantic-evals` is not installed in the Kroker venv; nothing was run. |

## 1. What Pydantic Evals is

A code-first evaluation library, independent of `pydantic-ai` (it depends on
it only optionally, and on `logfire` optionally for traces). Its data model
is small:

- a **Dataset** holds **Cases** (inputs, optional expected output, metadata,
  case-specific evaluators) plus dataset-wide **Evaluators** and **Report
  Evaluators**, and serializes to YAML or JSON with a generated JSON Schema;
- an **Experiment** is `dataset.evaluate(task, repeat=..., lifecycle=...,
  max_concurrency=..., retry_task=..., retry_evaluators=..., metadata=...)`;
- the result is an **EvaluationReport** of per-case scores, labels and
  assertions, failures, and experiment-wide analyses, which prints, diffs
  against a baseline report, and appears in Logfire's Evals view.

Evaluators return a `bool` (assertion), a number (score), a `str` (label),
an `EvaluationReason`, or a dict of these; an exception becomes an
`EvaluatorFailure` rather than a crash. The built-ins fall into four groups:

| Group | Evaluators |
|---|---|
| Deterministic | `EqualsExpected`, `Equals`, `Contains`, `IsInstance`, `MaxDuration` |
| LLM | `LLMJudge` (rubric; assertion and/or 0–1 score; default model `openai:gpt-5.2`), `GEval` (explicit evaluation steps, integer score, reasoning trace); rubric recipes for Ragas-style RAG metrics and GEMBA |
| Trajectory (span-based, deterministic) | `ToolCorrectness`, `TrajectoryMatch` (exact / LCS-F1 / multiset-F1), `ArgumentCorrectness`, `MaxToolCalls`, `MaxModelRequests`, and the low-level `HasMatchingSpan` with a `SpanQuery` language |
| Report-level | `ConfusionMatrixEvaluator`, `PrecisionRecallEvaluator`, `ROCAUCEvaluator`, `KolmogorovSmirnovEvaluator`, plus custom report evaluators returning `ScalarResult`, `TableResult`, `LinePlot` |

Beyond offline experiments it ships **online evaluation** (a decorator or
the `OnlineEvaluation` agent capability that samples evaluators in the
background after each call and emits OTel `gen_ai.evaluation.result`
events, with sinks, per-evaluator sample rates, correlated sampling,
drop-on-overload concurrency limits and `evaluator_version`), and
**re-running evaluators on stored data** (`run_evaluators()` over an
`EvaluatorContext`, fed by any `EvaluatorContextSource`) without executing
the task again.

Three constraints from the pages decide where it can live in Kroker:

- **Spans are captured in-process.** Span-based and trajectory evaluators
  read the OpenTelemetry tree the logfire SDK collects while the task runs
  in the evaluating process; tools executed elsewhere (provider-native
  tools, another process) are invisible, and each such evaluator then
  returns a failing result with a reason rather than raising.
- **Argument checks need content.** `ArgumentCorrectness` returns `False`
  when the agent was instrumented with `include_content=False`.
- **Online evaluation dispatches background tasks after the run.** The
  `OnlineEvaluation` capability wraps `agent.run()`; its page says nothing
  about durable execution.

## 2. What Kroker already has

Kroker has built most of an evaluation platform by hand, around a Temporal
pipeline rather than an in-process function:

| Kroker piece | Anchor | What it does |
|---|---|---|
| Benchmark harness | `src/sdlc/benchmarks/workflow.py` (E-27) | runs cases through the real workflow as a matrix of cells (harness × model/role × memory × case) |
| Cross-family judge | `src/sdlc/benchmarks/judge.py` | two-phase judge: `generate_steps` turns a rubric into cached evaluation steps (`:113`), then scores; never raises (`score=None, judge="error"`); ADR-6 keeps the judge's family away from the author's |
| Deterministic vetoes | `src/sdlc/benchmarks/vetoes.py` | absolute overrides stated in rubrics, evaluated in Python over the parsed artifact |
| Judge calibration | `src/sdlc/benchmarks/calibration.py` (E-36) | hand-scored fixtures vs judge; Spearman agreement per `rubric_sha` |
| Gate calibration | `src/sdlc/calibration/` (C7) | agreement between self-reported confidence and realized outcome decides whether a SOFT gate may auto-approve |
| Matrices | `heatmap.py`, `waste_matrix.py`, `agreement_matrix.py`, `task_matrix.py`, `error_matrix.py`, `sc_rollup.py` | case × stage rework, session waste, reviewer splits, SC rollups |
| Held-out oracle | `src/sdlc/benchmarks/oracle.py`, `benchmarks/cases/*/oracle/` | Tier A: hidden tests through the case's toolchain adapter |
| Experiments ledger | `src/sdlc/benchmarks/experiments.py` | tried / delta / human verdict, committed to git; "the tool computes the delta, the human writes the verdict" |
| Production drift | `src/sdlc/benchmarks/drift.py` | production history → records, judged only by contract and human override: "we never re-judge production artifacts with the LLM" |
| Prompt gate | `src/sdlc/eval/` (E-82) | promptfoo A/B of a working-tree `instructions.md` against the committed one: absolute assertion (output parses into `output_type`), judge assertion, and a cross-provider verdict computed in Kroker because promptfoo cannot compare providers; needs Node ≥ 22 (`pyproject.toml`, `eval` extra) |
| Prompt A/B loop | `sdlc eval` (E-4), `src/sdlc/eval/runner.py`, `fixtures.py` | replays a proposer on captured fixtures without Temporal |

The shapes are close. Kroker's judge is G-Eval as published (steps generated
from the criterion, then scored); a rubric plus its vetoes is a case-level
`LLMJudge` plus deterministic evaluators; the calibration modules compute the
kind of statistic Pydantic Evals ships as report evaluators; the experiments
ledger is a stricter version of comparing reports. What Kroker lacks is not
concepts but the shared container: a typed dataset file, one report object,
baseline diffs, repeat aggregation, standard curve statistics, and a place
where these render.

## 3. Map

| Pydantic Evals | Kroker counterpart | Verdict |
|---|---|---|
| `Dataset` / `Case` YAML + JSON Schema | `benchmarks/cases/<case>/case.yaml`, `rubric-*.md`, `vetoes-*.yaml`; `sdlc eval capture` fixtures | **Adopt** for stage-level fixtures (§4.2); cases stay Kroker's for the pipeline benchmark |
| `LLMJudge`, `GEval` | `judge_artifact` staged judge | **Adapt** — `GEval(evaluation_steps=<Kroker's generated steps>)` is the same judge; the model must always be set explicitly and ADR-6 stays Kroker's check |
| Deterministic evaluators, custom `Evaluator` | vetoes, `absolute.py` | **Adopt** — wrap vetoes and the output-type check as evaluators |
| Report evaluators (confusion, PR, ROC-AUC, KS, tables) | E-36 and C7 agreement (Spearman), matrices | **Adopt** for calibration statistics (§4.3) |
| `repeat` + `case_groups()` | E-83 judge sensitivity; single-shot cells | **Adopt** for the prompt gate and calibration (§4.1) |
| Baseline diff | experiments ledger deltas | **Adapt** — feeds the ledger; the verdict stays human |
| `run_evaluators` + `EvaluatorContextSource` | none (regrade was proposed in the Harbor report §3.3 for oracles only) | **Adopt** — rubric regrade over stored artifacts (§4.4) |
| Online evaluation | `drift.py` (contract and human-override only) | **Adapt** — deterministic evaluators only, from an activity (§4.5) |
| Trajectory / span evaluators | `HarnessSession` waste metrics (CLI sessions carry no spans) | **Adopt** for in-process agents (research, operator chat, a future pyai doer) (§4.6) |
| `CaseLifecycle` | case scratch repo, worktrees, compose sidecars | **Watch** — only if an in-process eval drives a stack |
| `generate_dataset` | hand-authored cases (BENCHMARK.md §2) | prompt-gate breadth only, never Tier A |
| Ragas / DeepEval adapters | — | not needed |
| Logfire Evals view | `report.html`, matrices HTML | optional viewer; files on disk and in git stay the record |

## 4. Candidates, ranked by value

### 4.1 The prompt gate on Pydantic Evals instead of promptfoo

E-82 runs a Node CLI through a thin Python wrapper, generates a config per
(role, case), and then computes the cross-provider verdict itself because
promptfoo "cannot compare providers" (`src/sdlc/eval/verdict.py`).
Pydantic Evals expresses the whole gate in Python: one `Dataset` of captured
fixtures, two experiments (committed instructions, working-tree
instructions) run through `src/sdlc/eval/runner.py`'s replay as the task,
`IsInstance`-style absolute checks and the vetoes as deterministic
evaluators, `GEval` with Kroker's generated steps on the cross-family judge
model, `repeat=N` so a one-shot judge flip cannot decide a gate, and
`report.render(baseline=...)` for the diff. `verdict.py` keeps its decision
rule and reads an `EvaluationReport` instead of `results.json`.

- **Payoff:** the `eval` extra and the Node ≥ 22 requirement disappear; the
  gate gains variance control (E-83's concern) and a baseline diff; evaluator
  failures are typed instead of "all-errored".
- **Cost:** `src/sdlc/eval/promptfoo/` (about 500 lines) is replaced;
  `verdict.py` is re-pointed; the E-82 design doc's decisions carry over.
- **Status:** New.

### 4.2 Stage fixtures as typed datasets

`sdlc eval capture` harvests fixtures from run history
(`src/sdlc/eval/fixtures.py`). Written as a `Dataset[InputsT, OutputT,
Metadata]` YAML with its generated JSON Schema, a fixture set becomes
editable with IDE validation, carries case-specific rubrics (the page's
"golden datasets with case-specific LLMJudge" pattern is BENCHMARK Tier B's
per-case rubric), and runs unchanged under `sdlc eval`, the prompt gate and
calibration.

- **Cost:** a serializer for the existing fixture model; custom evaluator
  types registered on load.
- **Status:** New.

### 4.3 Calibration statistics as report evaluators

C7 decides whether a gate's confidence can auto-approve from an agreement
statistic (`src/sdlc/calibration/verdict.py`, reusing E-36's Spearman).
Confidence against a realized approve/revise label is a scoring problem, and
`ROCAUCEvaluator`, `PrecisionRecallEvaluator` and
`KolmogorovSmirnovEvaluator` give threshold-free curves and AUCs over
exactly that shape (`score_from='metrics'`, `positive_from='labels'`); a
`ConfusionMatrixEvaluator` over judge verdict against human verdict is the
E-36 view for pass/fail rubrics. A custom report evaluator returning
`TableResult` can emit the case × stage heatmap into the same report.

- **Payoff:** the SOFT-gate threshold is chosen from a curve instead of a
  single correlation; judge calibration reports a confusion matrix.
- **Cost:** small; Spearman stays where rank agreement is the question.
- **Status:** New.

### 4.4 Regrade rubrics over stored artifacts

Every stage artifact is claim-checked, and benchmark records keep what was
judged. An `EvaluatorContextSource` over the artifact store and
`run_evaluators()` re-judge historical artifacts under a new rubric with no
pipeline re-run — the rubric-tier twin of the oracle regrade in the Harbor
report (§3.3). `Evaluator.get_evaluator_version()` carries `rubric_sha`, so
old and new scores never mix.

- **Payoff:** a rubric fix re-scores the corpus at judge cost only, and the
  judge-sensitivity study (E-83) runs over real history.
- **Status:** New.

### 4.5 Online checks from an activity, deterministic only

`drift.py` states a position: production artifacts are not re-judged by an
LLM. Online evaluation does not have to break it. After each stage, an
activity runs `run_evaluators()` with the deterministic evaluators — output
type, vetoes, contract checks — and a sink writes results beside the drift
records; the `gen_ai.evaluation.result` events go to telemetry for free.
The `OnlineEvaluation` capability itself is not attached to the durable
proposers: it wraps `agent.run()` and dispatches background work after the
run, and its page is silent on durable execution, so under Temporal that
work would start from workflow code.

- **Status:** New. Any LLM evaluator here would reverse a written decision
  and needs its own ADR.

### 4.6 Trajectory evaluators for the in-process agents

The research agent is the one proposer with tools; the operator chat agent
has twelve; a pyai doer (adoption map §5) would have many. For them
`ToolCorrectness`, `TrajectoryMatch`, `ArgumentCorrectness`, `MaxToolCalls`
and `MaxModelRequests` express behavioural contracts the rubric judge cannot:
pages read before a claim is made, the budget respected, no write tool on a
read-only turn. They require the logfire SDK in the evaluating process (no
account) and, for argument checks, content-bearing instrumentation — which
belongs in the eval process only, not in production telemetry (harness
comparison §2.4). CLI harness sessions produce no spans; their equivalents
remain custom evaluators over `HarnessSession`.

- **Status:** New; research first.

### 4.7 A faithfulness judge beside byte-exact grounding

BENCHMARK.md records research grounding as unreachable for a mid-tier model
because `verify_brief` fails closed on byte-exact quotes (E-29). The
Ragas-style faithfulness rubric recipe is a soft, reported signal next to the
hard check — never a replacement for it.

- **Status:** New; advisory only.

## 5. What not to take

- **Pydantic Evals as the outer benchmark driver.** The pipeline benchmark is
  a Temporal workflow with its own retries, resume and cell matrix; an
  in-process `Dataset.evaluate` around it would capture no pipeline spans
  (they are in worker processes) and would duplicate orchestration Kroker
  already has. Use the library for scoring and reporting inside and after
  the benchmark, not around it.
- **LLM judges online** — see §4.5.
- **`generate_dataset` for ground truth** — BENCHMARK.md §2 requires
  authored, held-out oracles.
- **An implicit judge model.** `LLMJudge` and `GEval` default to
  `openai:gpt-5.2`; every Kroker use sets the model and passes it through the
  ADR-6 family check.
- **Logfire as the record.** Reports on disk and the git-committed
  experiments ledger remain the system of record; Logfire is a viewer.

## 6. Open questions

- Does `OnlineEvaluation` detect durable execution, or would its background
  dispatch start from workflow code under `TemporalDurability`?
- Can `GEval` accept Kroker's cached generated steps per rubric without
  losing the "no fallback to raw rubric" rule `judge.py:113` enforces?
- What is the smallest `repeat` that makes the prompt gate's verdict stable
  on the current fixtures, given judge cost?
