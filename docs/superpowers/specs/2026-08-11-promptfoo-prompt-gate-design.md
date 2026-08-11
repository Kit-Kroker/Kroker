# The Prompt Gate — promptfoo as the Unit-Eval Runner — Design

| | |
|---|---|
| Date | 2026-08-11 |
| Work items | **E-82** (new). Red-team of untrusted-input surfaces is deliberately split out as a later item. |
| Requirements | Closes **OQ-B4** / **OQ-E2** (the regression-gate half of E-4); answers **OQ-B5** (external eval platform) in the affirmative, narrowly |
| Scope input | `BENCHMARK.md` §1, §7; `ARCHITECTURE.md` §10 (prompt lifecycle), ADR-6, ADR-11; `ROADMAP.md` §9.8; `src/sdlc/eval/*` |
| Status | Design approved 2026-08-11 |

E-4 shipped half a loop. `sdlc eval <role>` A/B-scores a working-tree
`instructions.md` against a committed one — but it is on-demand, nothing
enforces it, and its committed-baseline-plus-check half was left as a named
future increment. This increment writes that half.

Two discoveries during design shaped it more than the tool choice did. **No
fixture has ever been captured** — `agents/*/fixtures/` is empty across every
role, and `run_capture`'s `_history_to_events` is a documented seam that "needs
a live run to validate." And **there is no CI in this repository** — no
`.github/`, no GitLab/Circle/Azure config, no pre-commit, no Makefile. So
`sdlc eval` is a fully unit-tested loop that has never run on real input, and a
"CI gate" would have had nothing to plug into.

The design therefore delivers three things that were assumed to exist:
deterministically-constructed fixtures, a gate surface that works today, and
the prompt-composition module that makes the first possible.

promptfoo (MIT, `pip install promptfoo`) is adopted as the **runner only**.
Every judgment that carries project meaning stays in Kroker's code.

---

## 1. What exists today

**Built and load-bearing:**

- **`benchmarks/`** — the heavyweight instrument. Golden cases through the real
  `FeatureWorkflow`, a matrix over harness × model×role × memory × case, Tier-A
  held-out pytest oracles, the cross-family judge, SC-1..6 rollup, and the
  heatmap / error / waste / agreement matrices. **This design does not touch
  it.**
- **`src/sdlc/eval/`** — the lightweight instrument. `run_variant`
  (`runner.py:23`) builds the role's *real* agent via `_load_build` →
  `build(model, instructions, MODEL_SETTINGS)` and runs it synchronously.
  `compare.py` runs both variants k times, judges each, and means the deltas.
- **`judge_artifact`** (`benchmarks/judge.py`) — cross-family LLM judge that
  never raises; returns `QualityScore(score=None, judge="error")` on any
  failure. `_set_judge_fn` (`judge.py:61`) is the injection seam.
- **`model_family`** (`agents/loader.py:71`) — the ADR-6 invariant, checked in
  `compare.py:108-111`.
- **`PROMPT_SHAS`** (`agents/roles.py:108`) — `sha256` over each role's
  instructions text. Already carried on `BenchmarkRecord.prompt_sha`
  (`benchmarks/models.py:120`) and already inside the memoization
  `content_key`.

**Gaps this design closes:**

1. **No fixtures exist.** The only path to one is an unvalidated Temporal
   history seam.
2. **No CI exists.** Testing is `python -m pytest` with marker-based opt-ins
   (`slow`, `temporal`, `live`, `docker`).
3. **Prompt composition is inlined.** Every proposer prompt is a
   string-concatenation expression inside `feature.py`, a 2,473-line workflow
   module. There is no prompt-composition module, so a fixture cannot be
   constructed — only captured.
4. **Rubric coverage is thinner than `RUBRIC_KEY` implies.** On disk:

   | Role | Rubrics on disk | Eval-able |
   |---|---|---|
   | `clarify` | add-login, cat-cafe, todo-api | yes |
   | `planner` | cat-cafe | yes |
   | `qa` | cat-cafe | yes |
   | `architect`, `research` | 2–3 cases | **no** — `DEPS_ROLES`, refused |
   | `reviewer`, `analyst`, `merge_verdict` | none | no rubric |

---

## 2. Position relative to the quality system

The prompt gate is a **third instrument alongside** `benchmarks/`, not a
replacement for it and not a contributor to it.

```
Layer 3   benchmarks/         real FeatureWorkflow, Tier-A oracles, SC-1..6   UNCHANGED
Layer 2   prompt gate (NEW)   one role, one frozen input, one grade
Layer 1   pytest              unit tests, zero model calls                    UNCHANGED
```

**Prompt-gate results must never enter the `BenchmarkRecord` stream.** Three
reasons, in order of severity:

1. **The denominator breaks.** `build_heatmap` counts distinct `run_id` per
   case as `n_runs` and divides by it (`heatmap.py:60-62,86`). Prompt-gate
   results carry no pipeline run; injecting them with synthetic run_ids would
   inflate the denominator and *silently deflate the rework density of real
   runs* — the number improves because measurements were added, not because
   anything got better.
2. **The numerator is a category error.** A heatmap cell is
   `(gate rejections + fix attempts + oracle failures) / run`. A prompt gate
   has none of those three.
3. **The stage axis is already under strain.** `heatmap.py:16-21` carries lens
   records at `fix_attempts=0` precisely so one disagreement is not counted as
   three units of rework, and warns that "if more lenses accumulate, this axis
   stops being the SDLC DAG (OQ-A3)." A prompt-gate result is not even a lens
   on a run.

The `"_drift/<date>"` / `"_production"` convention is **not** a precedent for
admitting them: drift records are still real pipeline stage executions, merely
sourced from production instead of golden cases.

**The join is `prompt_sha`, and only `prompt_sha`.**

```
runs/prompt_evals/*.json                    runs/**/records.jsonl
  role, case,                                 BenchmarkRecord.prompt_sha
  prompt_sha_baseline, prompt_sha_working     quality / cost / speed / waste
  absolute results, judge scores, verdict     -> heatmap, matrices, SC rollup
              │                                            │
              └──────────── prompt_sha ────────────────────┘
                       correlate; never aggregate
```

This answers "did the clarify column's rework density move after `prompt_sha`
a1b2→c3d4?" without averaging two incommensurate scales. `sdlc benchmark score`
output is byte-for-byte unaffected by this increment.

---

## 3. Why promptfoo, and how far in

Adopted at the **thin-shell** depth: promptfoo drives the loop; Kroker owns
every judgment.

The decisive constraint is fidelity. `run_variant` builds the role's actual
agent — `Agent(model, output_type=ClarifiedRequirements,
model_settings=MODEL_SETTINGS, system_prompt=instructions)`. Pointing promptfoo
at `anthropic:`/`openai:` providers directly (its idiomatic usage) would grade a
**bare text completion instead of the role's validated output type** — a
different object than production produces — and would hand grader selection to
promptfoo's `llm-rubric`, quietly voiding ADR-6.

What the shell buys for roughly 150 lines of glue: the assertion library,
`--repeat` with variance, result caching, the local web viewer, JSON/JUnit
output, non-zero exit on threshold breach, and the provider seam the deferred
red-team work will reuse.

**Rejected alternatives.** *Export-target only* (keep `compare.py`, emit
promptfoo-shaped results for the viewer) buys a UI and nothing else — no
assertions, no caching, no repetition statistics, no red-team path. *Full
native adoption* is rejected on the fidelity grounds above.

**Dependency placement:** a new `eval` extra in `pyproject.toml`, not `dev`, so
`pip install -e .[dev]` does not pull a Node-backed tool on contributors who
only run unit tests.

---

## 4. Components

### 4.1 `src/sdlc/prompts.py` (new)

Pure, no I/O, sandbox-safe. Imported into `feature.py` inside the existing
`workflow.unsafe.imports_passed_through()` block (`feature.py:16`).

```python
def clarify_prompt(idea_json: str, memory: Sequence[str]) -> str
def planner_prompt(arch_json: str, memory: Sequence[str], guidance: str | None) -> str
def qa_prompt(assertions: Sequence[str], qa_raw_json: str,
              diff_stat: str, diff_patch: str) -> str
def reviewer_prompt(assertions: Sequence[str], qa_raw_json: str,
                    diff_patch: str) -> str          # no diff_stat — see below
def analyst_prompt(criteria: str, qa_output: str,
                   diff_stat: str, diff_patch: str) -> str
def merge_verdict_prompt(task_results: Sequence[dict]) -> str
```

**Contract: byte-identical output to today's inline expressions.** Two repeated
blocks become shared helpers — the memory block
(`"\nRelevant memory:\n- " + "\n- ".join(items) if items else ""`, used by
clarify and planner) and the frozen-contract block
(`"Frozen contract assertions:\n- " + "\n- ".join(assertions)`, used by qa and
reviewer).

Extraction surfaces one asymmetry worth recording: **qa receives
`Diff stat:` + `Diff:`, reviewer receives only `Diff:`** (`feature.py:1406-1407`
vs `:1417`). Whether that is deliberate or drift is out of scope here — the
extraction preserves it exactly and makes it visible for the first time.

This is the only change in the increment that can break production, and it is
what makes fixtures structurally incapable of drifting: `feature.py` and the
fixture generator call the same function, so divergence becomes a code change
rather than silent rot.

Sites replaced: `feature.py:1893` (clarify), `:2040` (planner), `:1403` (qa),
`:1414` (reviewer), `:2192` (analyst), `:2360` (merge_verdict).

**All six are extracted, though only three are gated day one (§8).** A
half-extracted module — three roles composing prompts in `prompts.py`, three
still concatenating inline — is a worse state for the next reader than either
end, and the second motive for the refactor (moving prompt composition out of a
2,473-line workflow file) applies to all six regardless of rubric coverage.

### 4.2 `src/sdlc/eval/fixtures.py` (generation half rewritten)

`EvalFixture` keeps its shape. Generation replaces capture:

```python
def build_fixture(role: str, case_id: str, cases_root: Path) -> EvalFixture
```

`clarify` seeds from `case.yaml` (`idea_summary` / `description` → `Idea` →
`clarify_prompt`). Memory items are empty by construction — a fixture must not
depend on a live memory backend.

**The seed problem.** `planner` needs an architecture; `qa` needs a frozen
contract plus test output plus a diff. Neither is derivable from `case.yaml`,
and re-deriving them by running upstream stages would rebuild the pipeline.
Downstream roles therefore read a committed frozen seed under
`benchmarks/cases/<case>/seeds/`:

| Role | Seed contents |
|---|---|
| `planner` | `architecture.json` — one `ArchitectureSpec` |
| `qa` | `assertions.json`, `qa_raw.json`, `diff.json` (`stat` + `patch`) |
| `reviewer` | same as `qa` minus `stat` |
| `analyst` | criteria lines, aggregate test output, `diff.json` |
| `merge_verdict` | `task_results.json` |

Only the first two are authored in this increment (§8); the rest are listed so
the convention is fixed once rather than renegotiated per role.

**Retired:** `run_capture` and `_history_to_events`. Once production and
fixtures share one builder, capture is redundant.

### 4.3 `src/sdlc/eval/promptfoo/provider.py` (new)

**promptfoo's provider axis is the A/B axis.** Two provider entries over the
same file, differing only in `instructions_ref`, so baseline vs working-tree
renders as a native side-by-side matrix and no custom compare loop is needed.

```yaml
providers:
  - id: 'file://provider.py:call_api'
    label: baseline
    config: { role: clarify, instructions_ref: HEAD }
  - id: 'file://provider.py:call_api'
    label: working
    config: { role: clarify, instructions_ref: worktree }
```

`call_api(prompt, options, context) -> dict` resolves the instructions text
(`git show HEAD:agents/<role>/instructions.md`, or the worktree file), calls
`run_variant()`, and returns `{output, tokenUsage, cost, latencyMs}`. **It never
raises** — on failure it returns `{"output": "", "error": str(exc)}`, per
promptfoo's requirement that `output` always be present.

### 4.4 `src/sdlc/eval/promptfoo/assertion.py` (new)

argv-based custom assertion (`sys.argv[1]` = output, `sys.argv[2]` = context
JSON), returning a `{pass, score, reason}` GradingResult. Wraps
`judge_artifact.sync()`. Judge model resolves from `benchmarks/config.yaml`
(`default_judge_model: openai/gpt-5.2`).

Carries the ADR-6 check migrated from `compare.py:108-111`.

### 4.5 Where the ADR-11 split lands

The gate inherits the architecture's existing stance —
`DeterministicQualityGate` decides on typed evidence; the LLM only advises.

| Check | Class | Runs | Gates |
|---|---|---|---|
| Output parses into the role's `output_type` | absolute | promptfoo `python:` | **yes** |
| Required fields non-empty | absolute | promptfoo `python:` | **yes** |
| `cost` / `latency` within budget | absolute | promptfoo native | **yes** |
| Cross-family rubric score | advisory | custom assert, always `pass: true` | no — reported |
| Regression beyond noise floor | advisory | **pytest wrapper** | yes, past floor |

The last row is structurally outside promptfoo: an assertion sees one output,
and `assertScoringFunction` sees one test's `namedScores` — neither can compare
*across providers*. The cross-provider verdict is therefore computed by Kroker
from promptfoo's `--output results.json`.

That placement is a benefit, not a workaround: the subtlest logic in the design
becomes a pure function over a results dict, exhaustively testable with a fake
JSON file and zero model calls.

```
regression fires iff
    mean(working) < mean(baseline) − max(δ_min, 2 × pooled_stderr)

δ_min = 0.05 (configured);  k = 1 ⇒ no stderr ⇒ falls back to δ_min
```

### 4.6 `src/sdlc/eval/promptfoo/config.py` (new)

Generates `promptfooconfig.yaml` into a scratch directory from the role
registry, fixture, rubric path, and judge model. **Generated, never committed**
— a hand-maintained config would drift from the registry.

### 4.7 Gate surface

`tests/test_prompt_gate.py`, marked `prompt_eval` and opt-in via
`SDLC_PROMPT_EVAL=1` — reusing verbatim the convention `pyproject.toml` already
establishes for `live` ("spawns a real harness CLI and spends tokens; skipped
unless `SDLC_LIVE_TESTS=1`").

```toml
markers = [
    "live: spawns a real harness CLI and spends tokens; skipped unless SDLC_LIVE_TESTS=1",
    "prompt_eval: A/B-scores prompts against a fixture; spends tokens",   # new
]
```

This needs no new infrastructure, and becomes a one-line CI step the day CI
arrives. `sdlc eval <role>` keeps its current UX, gaining `--gate` (non-zero
exit below threshold) and `--view`.

### 4.8 Retired

- `src/sdlc/eval/compare.py` — the run loop is promptfoo's; rubric loading and
  the ADR-6 check move to `assertion.py`.
- `run_capture` / `_history_to_events` (§4.2).

---

## 5. Data flow

```
$ SDLC_PROMPT_EVAL=1 pytest -m prompt_eval      (or: sdlc eval clarify --gate)
        │
        ├─ 1. config.py   role registry + fixture + rubric + judge model
        │                 -> promptfooconfig.yaml (scratch, not committed)
        │
        ├─ 2. fixture     build_fixture("clarify", "cat-cafe-monitoring")
        │                 case.yaml -> Idea -> prompts.clarify_prompt(...)
        │                 == exactly the string feature.py:1893 sends
        │
        ├─ 3. promptfoo eval --repeat 3 --output results.json
        │       ├── provider "baseline"  git show HEAD:agents/clarify/instructions.md
        │       │      └─ run_variant -> _load_build -> real Agent(
        │       │            output_type=ClarifiedRequirements) -> run_sync(fixture)
        │       ├── provider "working"   agents/clarify/instructions.md
        │       └── per output:
        │              is-json + parses as the role's output_type   [ABSOLUTE]
        │              required fields non-empty                    [ABSOLUTE]
        │              cost <= budget, latency <= budget            [ABSOLUTE]
        │              judge_artifact (cross-family, ADR-6)         [advisory]
        │
        ├─ 4. pytest wrapper reads results.json
        │       absolute failure anywhere       -> FAIL      (exit non-zero)
        │       mean(working) below noise floor -> FAIL      (exit non-zero)
        │       provider error present          -> ERRORED   (exit non-zero)
        │       otherwise                       -> PASS, print the delta
        │
        └─ 5. runs/prompt_evals/<ts>-<role>-<case>.json
                 { role, case, prompt_sha_baseline, prompt_sha_working,
                   absolute: [...], judge: {baseline, working, delta, floor},
                   verdict }
                        └── joins BenchmarkRecord.prompt_sha (§2), never merged
```

Step 2 is why fixtures cannot drift. Step 4 is where cost is controlled: a
default `pytest` run never reaches step 3, so the repository keeps its property
that CI (when it exists) and everyday testing make no model calls.

---

## 6. Error handling

Governing principle, taken from the codebase's own stance (`judge.py:1-8`;
`WasteBag`'s "None means NOT MEASURED and must render blank; an all-zero bag
would be indistinguishable from a genuinely clean run"): **a broken measurement
must never masquerade as a measurement.**

| Failure | Behavior | Rationale |
|---|---|---|
| promptfoo not installed | **SKIP** on bare `pytest`; **FAIL** when `SDLC_PROMPT_EVAL=1` | Opt-in means "I intend to run this." Silently skipping an explicitly-requested gate is the worst outcome available. |
| Prompt unchanged vs HEAD | **PASS**, zero model calls, early exit | Preserves `compare.py:125-127`. Most runs touch no prompt and must cost nothing. |
| No baseline (new role) | Working-tree only; absolute checks gate; regression **N/A** | Existing `no_baseline` semantics. |
| Judge errors | Excluded from the mean | `judge_artifact` already returns `score=None, judge="error"` and never raises. |
| **All** judgments errored one side | Regression **not evaluated**; reported `judge: unavailable` | Never a silent pass; not-measured ≠ passed. |
| ADR-6 violation | **Hard fail immediately**; never degraded to advisory | A config error, not a measurement. Matches the matrix expander rejecting same-family configs up front. |
| Provider error | **ERRORED**, distinct from FAILED; non-zero exit | An empty output would trip the absolute asserts and *look like a prompt regression*. Conflating infrastructure failure with prompt regression is how a gate loses trust. |
| Missing rubric / seed | Config error; message names the exact path to author | Same shape as `compare.py:74-77`. |
| Cost runaway | Whole-run ceiling; abort loudly when exceeded | Distinct from the per-call `cost` assert in §4.5: that one fails a *single* output whose spend is anomalous; this one bounds the *aggregate*. 5 pairs × k=3 × 2 providers = 30 agent runs + 30 judge calls per gate run. |

---

## 7. Testing

Every layer but the last two runs with **zero model calls**.

| Layer | Approach | Model calls |
|---|---|---|
| `prompts.py` extraction | **Characterization tests written before the `feature.py` swap** — snapshot each current inline expression's output, assert the extracted function reproduces it byte-for-byte | none |
| Fixture generation | Golden-file; generate twice, assert identical | none |
| Provider | `call_api` with `model_override` (already supported, `runner.py:24`) injecting `TestModel`; assert the dict matches promptfoo's contract | none |
| Assertion | Fake judge via `_set_judge_fn` (`judge.py:61`): good score / judge error → advisory pass / ADR-6 violation → hard fail | none |
| **Verdict + noise floor** | Pure function over a fake `results.json`: clear regression, within-noise dip, improvement, all-errored → not-measured, provider error → ERRORED, no baseline, k=1 → δ_min fallback | none |
| Config generation | Generated YAML parses; both providers present with correct refs | none |
| **promptfoo contract test** | Real `promptfoo eval` against a canned `file://` provider returning a fixed string + a deterministic assert | none — needs promptfoo, **no API keys** |
| The gate itself | `-m prompt_eval`, opt-in | yes |

Two deliberate choices. The **characterization tests come first**: the
`feature.py` extraction is the only change that can break production, so it gets
a proof of equivalence before the swap, not after. And the **contract test**
exists to catch promptfoo changing its config schema on a version bump — the
difference between learning that on a quiet Tuesday and learning it during a
gate run that was needed.

---

## 8. Scope

**Day one** — three roles, five (role, case) pairs:

| Role | Cases | Seed |
|---|---|---|
| `clarify` | add-login-greenfield, cat-cafe-monitoring, todo-api-greenfield | from `case.yaml` |
| `planner` | cat-cafe-monitoring | committed `seeds/architecture.json` |
| `qa` | cat-cafe-monitoring | committed seed |

**Out of scope, and why:**

- `reviewer` / `analyst` / `merge_verdict` — no rubric exists. Eval-able the
  moment one is authored; no machinery change needed.
- `architect` / `research` — `DEPS_ROLES`. A prompt-string fixture cannot
  reconstruct a live deps object. Unchanged by this increment.
- **Red-teaming untrusted-input surfaces** — deferred to its own spec → plan →
  implementation cycle. It reuses this increment's provider seam but has a
  different target (poisoned content entering the pipeline via research briefs,
  brownfield repos, imported corpora), a different assertion family, and an
  unresolved policy question: what severity blocks what. The repository has zero
  adversarial coverage today; that is a real gap, and it deserves its own
  design rather than a subsection here.
- **Cheap model×role pre-screening** — considered and rejected. A single-prompt
  proxy score would create a second scoreboard whose numbers do not commensurate
  with SC-1..6, and whose failure mode is silent: a model that scores well on an
  isolated `clarify` prompt but decomposes badly under `planner`. E-37 already
  sweeps model×role through the real workflow. The lever for cheaper sweeps is
  memoization (`content_key` already invalidates precisely), not a second
  instrument.
- **Introducing CI** — the gate is CI-ready and becomes a one-line step, but
  designing CI (secrets, cost control, runners) is not this increment.

## 9. Open questions

- **OQ-P1 — δ_min calibration.** 0.05 is an initial guess. The value should be
  set from observed judge variance once the gate has run enough times to
  estimate it, and revisited whenever `default_judge_model` changes.
- **OQ-P2 — seed staleness.** A committed `seeds/architecture.json` freezes an
  architect output that the real architect would no longer produce. Nothing
  detects that. Acceptable for a regression gate (it grades *the planner
  prompt*, holding input fixed) but the seeds need a documented refresh
  trigger.
- **OQ-P3 — promptfoo version pinning.** The contract test detects schema
  drift; it does not decide whether to pin exactly or float within a range.
