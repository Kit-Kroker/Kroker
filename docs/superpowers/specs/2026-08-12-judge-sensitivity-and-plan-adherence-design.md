# Judge Sensitivity and Plan Adherence — Design

| | |
|---|---|
| Date | 2026-08-12 |
| Work items | **E-83** (new) |
| Requirements | Closes **OQ-P5** (gate sensitivity). Records a verdict on DeepEval, extending the **OQ-B5** answer. Does not touch OQ-P1/OQ-P2/OQ-P3. |
| Scope input | `docs/superpowers/specs/2026-08-11-promptfoo-prompt-gate-design.md`; `src/sdlc/eval/*`; `src/sdlc/benchmarks/judge.py`; `benchmarks/cases/*/rubric-*.md`; ADR-6, ADR-11, ADR-16; `heatmap.py:16-21` |
| Status | Design drafted 2026-08-12 — awaiting review |

The question that started this increment was whether to adopt
[DeepEval](https://github.com/confident-ai/deepeval). The answer is **no, not as
a dependency** (§3), but the investigation surfaced something more useful than a
dependency decision: the prompt gate E-82 shipped has **never recorded a
measured verdict**, and the two rubric mechanisms that would give it teeth are
already written down in prose that no component of the system can execute.

This increment makes the gate sensitive, and adds the one plan-execution signal
the pipeline does not currently measure.

---

## 1. What exists today

**Built and load-bearing** (unchanged by this design):

- **`benchmarks/`** — golden cases through the real `FeatureWorkflow`, the
  matrix over harness × model×role × memory × case, Tier-A held-out oracles,
  SC-1..6 rollup, heatmap / error / waste / agreement matrices.
- **`src/sdlc/eval/`** — the prompt gate. promptfoo drives the loop; every
  judgment stays in Kroker's code. `absolute.py` gates, `assertion.py` advises,
  `verdict.py` decides across providers.
- **`judge_artifact`** (`benchmarks/judge.py:122`) — the cross-family LLM judge,
  shared by **both** layers: the benchmark workflow calls it as a Temporal
  activity, and `eval/promptfoo/assertion.py:87` calls `judge_artifact.sync()`.
- **`deep_review`** (`feature.py:952`) — the advisory transcript lens. Loads the
  scrubbed `HarnessSession`, reports integrity flags with verbatim evidence,
  drops any accusation whose evidence is not in the transcript
  (`verified_integrity_flags`), never gates.

### 1.1 Three findings that shaped this design

**Finding 1 — the gate has never produced a measured verdict.** Every record in
`runs/prompt_evals/`:

```
15:20  pass      no_baseline   prompt unchanged — no model calls
16:42  errored   unavailable   Worker failed to...
16:45  errored   unavailable   Worker failed to...
16:55  errored   unavailable   Worker failed to...
17:05  errored   unavailable   Worker failed to...
17:10  errored   unavailable   ImportError: attempted...
17:12  errored   unavailable   AttributeError: no attribute 'get_assert'
17:14  errored   unavailable   Python code execution failed
21:22  pass      unavailable   judge unavailable on at least one side
21:46  pass      unavailable   n=(0,1)  judge unavailable on one side
```

Fairly: all ten predate `fea3122`, the Gemini-judge fix. This is *unproven*, not
*broken*. But it means every judgment-quality improvement is downstream of a
plumbing problem, and no sensitivity claim about this gate currently rests on a
persisted measurement.

**Finding 2 — a measured score is silently discarded.** `verdict.py:152-157`
returns the `UNAVAILABLE` branch carrying `n_baseline` / `n_working` but never
populates `mean_baseline` / `mean_working` — unlike the `no_baseline` branch
directly above it, which does set `mean_working`. The final record above has
`n_working=1`: a real judge score existed and the record kept only its count.
The number itself lived in `results.json` inside the scratch directory
`run_gate` deletes in its `finally` (`gate.py:107`).

That is almost certainly where OQ-P5's "scored 1.00 from the real judge"
observation went. **The evidence for the increment's central open question was
deleted by the increment that raised it.**

**Finding 3 — the rubrics already contain vetoes the judge cannot execute.**
Three rubrics on disk encode absolute overrides in prose:

| Rubric | Veto in prose | Executable as |
|---|---|---|
| `rubric-clarifier.md:12` | "Silently dropping an activity, the risk analysis, the red marking, or the 24h history scores 0 on this component regardless of how good the rest is" | membership check over typed fields |
| `rubric-qa.md:15` | "`tests_passed: true` alongside a non-empty `failing_tests` or a non-empty `issues` list is a contradiction and scores 0 on this component" | **a boolean expression over three Pydantic fields** |
| `rubric-research.md:12` | "unsourced number scores 0 on this component" | membership check |

`_JUDGE_SYSTEM_PROMPT` (`judge.py:66`) asks for `{"score": <float>, "components":
{...}}` and the rubrics instruct `"score": <mean>`. **A weighted mean cannot
express an absolute override.** The system is asking an LLM to enforce a veto
inside an averaging operation, which is among the things LLM judges do worst —
and in the QA case, asking an LLM to evaluate a boolean expression it could
compute exactly.

This is the mechanism behind OQ-P5, and it needs no new dependency to fix.

---

## 2. Position relative to the quality system

E-82 established three layers and one rule: prompt-gate results join
`BenchmarkRecord` by `prompt_sha` only, and are never merged into the heatmap,
matrices, or SC rollup. **That rule is unchanged.** This increment adds no new
record stream.

```
Layer 3   benchmarks/         real FeatureWorkflow, Tier-A oracles, SC-1..6
                              judge_artifact ────┐
Layer 2   prompt gate         absolute.py        │  ← both consume the same
                              assertion.py ──────┘     judge and the same vetoes
Layer 1   pytest              unit tests, zero model calls              UNCHANGED
```

### 2.1 The measurement discontinuity (deliberate)

Sharpening `judge_artifact` changes the scale on which **every stored**
`BenchmarkRecord.quality_score` was measured. This was chosen deliberately over
gate-only scoping: a judge that cannot discriminate is not worth preserving
comparability with.

The cost is real and must not be silent. Mitigations, both required:

1. **`QualityScore.judge` gains `"staged_rubric"`.** The field is a pinned
   `Literal` guarded by `tests/test_judge_literal.py`, so the marker is already
   a seam. Records written before this increment keep `"llm_judge"`; records
   after carry `"staged_rubric"`. The discontinuity becomes queryable.
2. **`sdlc benchmark score` warns when a record set spans more than one judge
   kind for the same case**, naming both. Averaging across the boundary is now
   visible instead of implicit — the same discipline `WasteBag` applies to
   not-measured.

The name is `staged_rubric`, not `geval`: the mechanism is staged (steps, then
score), and it deliberately does not claim to be G-Eval, whose distinctive
logprob weighting is unavailable on `google:gemini-3.5-flash` (§3).

---

## 3. The DeepEval verdict

**Adopted: two of its ideas. Rejected: the dependency.**

DeepEval is Apache-2.0, pure Python (no Node, unlike promptfoo), runs standalone
without the Confident AI cloud, and its `assert_test` is pytest-native. Adoption
would be straightforward. It is rejected for this repository on three specific
grounds:

1. **Impedance mismatch.** `LLMTestCase` is text-shaped — `input`,
   `actual_output`, `expected_output`, `retrieval_context`. Kroker's artifacts
   are typed Pydantic objects, and its quality architecture is built on typed
   evidence (ADR-11). Every judgment would flatten to strings, losing exactly
   the structure that makes Finding 3's vetoes checkable. `rubric-qa.md`'s
   contradiction check is a boolean over three typed fields; through an
   `LLMTestCase` it becomes prose for an LLM to re-derive.
2. **Its distinctive metric degrades on this deployment's judge.** G-Eval's
   contribution over a plain rubric prompt is (a) generated chain-of-thought
   evaluation steps and (b) token-logprob-weighted scoring. `google:gemini-3.5-flash`
   does not expose logprobs the way GPT does, so (b) is unavailable and G-Eval
   reduces to (a) — which is roughly thirty lines against `pydantic-ai`, already
   a dependency.
3. **Cost of a second framework.** The repository spent an entire increment
   justifying *one* external eval tool at thin-shell depth. A second brings a
   large transitive tree into a notably tight dependency list, defaults its
   judge to OpenAI (custom-model wrapping is real glue), and its telemetry
   posture could not be verified from its documentation — a pre-adoption check,
   not a post-adoption discovery.

**What is taken instead:**

| DeepEval idea | Taken as | Where |
|---|---|---|
| G-Eval's generated evaluation steps | Phase 1 of the staged judge | §4.3 |
| DAG's structural vetoes | A closed, typed veto vocabulary — **deterministic, no LLM** | §4.2 |

**Revisit trigger — recorded so this is not re-litigated from memory.** E-82 §8
defers red-teaming of untrusted-input surfaces to its own spec.
[DeepTeam](https://github.com/confident-ai/deepteam) is *built on* DeepEval. If
that spec adopts DeepTeam, DeepEval arrives transitively and this verdict should
be reconsidered — a second judge implementation would then be the waste.
Deferring costs nothing today, because DeepTeam brings the dependency with it.

**Also considered on the agentic side and rejected as redundant:** Step
Efficiency (already `SessionDigest.tool_calls` / `file_rereads` / `rewrite_churn`
→ `waste_matrix`, deterministic and cheaper), Task Completion and Goal Accuracy
(already Tier-A held-out oracles — ground truth beats a judged trace), Tool
Correctness (needs `expected_tools`, unknowable for open-ended coding work).
Only Plan Adherence was genuinely uncovered; §5 addresses it directly.

---

## 4. Part one — judge sensitivity

### 4.1 Prove the instrument before sharpening it

Ordered first because everything downstream depends on it, and because a
sharper judge fixes none of Finding 1's ten failures.

1. **Populate the means in the `UNAVAILABLE` branch** (`verdict.py:152-157`).
   `mean_baseline` / `mean_working` are set from whichever side produced scores;
   the verdict and `judge_status` are unchanged. A one-sided measurement is
   still not a regression evaluation — but the number it produced must survive
   to disk.
2. **Persist the per-row judge scores** alongside the record.
   `PromptGateResult` gains `scores_baseline: list[float]` and
   `scores_working: list[float]`. Bounded by `repeat` (default 3), so this is a
   handful of floats, not a transcript. Without them, no sensitivity claim about
   this gate is ever reproducible after the scratch dir is removed.
3. **One green `measured` run** on a deliberately changed prompt, its record
   committed as the evidence that the loop closes end to end.

Step 3 is the entry condition for §4.2 and §4.3.

### 4.2 Vetoes: move the absolute checks out of the LLM

A **veto** is a rubric criterion whose failure zeroes its component regardless
of the rest. Vetoes are **deterministic** — evaluated over the parsed, typed
artifact, with zero model calls.

Authored per case, mirroring the existing rubric convention exactly:

```yaml
# benchmarks/cases/<case>/case.yaml
rubrics:
  clarifier: rubric-clarifier.md
vetoes:
  clarifier: vetoes-clarifier.yaml      # NEW — same shape, same lookup
```

```yaml
# benchmarks/cases/cat-cafe-monitoring/vetoes-clarifier.yaml
- id: scope_preserved
  kind: mentions_all
  terms: [sleeping, eating, drinking, litter box, playing, fighting]
  fields: [functional_requirements, open_questions, acceptance_criteria]

# benchmarks/cases/cat-cafe-monitoring/vetoes-qa.yaml
- id: internal_consistency
  kind: not_both
  field: tests_passed
  equals: true
  and_any_nonempty: [failing_tests, issues]
```

**A closed, typed vocabulary — not an expression language.** Three kinds, a
discriminated union validated at load. No `eval`, no code under
`benchmarks/cases/`:

```python
class MentionsAll(BaseModel):
    kind: Literal["mentions_all"]
    id: str
    terms: list[str]
    fields: list[str] = Field(default_factory=list)   # empty = whole artifact

class NotBoth(BaseModel):
    kind: Literal["not_both"]
    id: str
    field: str
    equals: bool | str | int
    and_any_nonempty: list[str]

class NonEmpty(BaseModel):
    kind: Literal["nonempty"]
    id: str
    fields: list[str]

Veto = Annotated[MentionsAll | NotBoth | NonEmpty,
                 Field(discriminator="kind")]
```

The vocabulary is deliberately minimal: it covers all three vetoes currently
written in rubric prose and nothing more. A fourth kind is added when a fourth
rubric needs one — not in anticipation.

**New module `src/sdlc/benchmarks/vetoes.py`.** Pure: `check(artifact: dict,
vetoes: list[Veto]) -> list[VetoFailure]`. No I/O, no model calls, exhaustively
table-testable — the same shape that made `verdict.py` the most reliable part of
E-82.

**Both layers consume it, with different teeth:**

| Layer | Consumer | Effect of a veto failure |
|---|---|---|
| 2 (prompt gate) | `eval/promptfoo/absolute.py` | **ABSOLUTE failure** → `FAIL_ABSOLUTE`, non-zero exit |
| 3 (benchmark) | `benchmarks/judge.py` `_judge_sync` | component forced to `0.0`, overall score forced to `0.0`, `judge="staged_rubric"` |

At Layer 2 this is where the gate gains real teeth. OQ-P5 observed that the
absolute tier's only teeth were cost/latency budgets and a blank-string check;
vetoes are content teeth, and they cost nothing.

**Missing `vetoes:` for a (case, role) is not an error** — no vetoes run and the
absolute tier keeps today's behaviour. Vetoes are opt-in per case. A *malformed*
veto file is a loud config error, matching `RubricError`'s shape.

### 4.3 The staged judge

`_JUDGE_SYSTEM_PROMPT`'s single shot is replaced by two phases behind the
existing `_set_judge_fn` seam (`judge.py:61`), which every test already uses.

**Phase 1 — steps.** Rubric text → an ordered `list[EvaluationStep]`, typed
output. **Cached by `sha256(rubric)`**, so this is one call per rubric per
process, not one per artifact. A rubric changes rarely; the cost is negligible
and the steps are stable within a run, which matters for comparing baseline
against working.

**Phase 2 — score.** The artifact is scored against the *generated steps*
rather than the raw rubric prose, emitting per-component scores.

**Composition is structural, not a mean.** Vetoes (§4.2) are applied
deterministically by Kroker *around* the LLM's output:

```
component_score[c] = 0.0                          if a veto for c failed
                   = <LLM's score for c>          otherwise

overall            = 0.0                          if any veto failed
                   = <LLM's overall score>        otherwise
```

**Component weighting stays the judge's business, exactly as today.** The
rubrics state weights in prose (`questions_material (0.3)`) and instruct
`"score": <mean>`; Kroker does not parse those weights and does not recompute
the composition. Vetoes *override*, they do not reweight. Introducing a
declarative weights mechanism would be a second scoring scheme competing with
the prose the judge is already reading — a change worth making on its own
evidence, not as a side effect of this one.

This is DAG's mechanism — a veto node short-circuits the tree — without DAG's
framework, and with the veto evaluated in Python rather than by the model being
graded.

ADR-6 is untouched: the family and identity checks stay exactly where
`assertion.py:64-85` puts them, and run before any judge call.

### 4.4 The mutation suite — the increment's acceptance criterion

OQ-P5 asked: *"what prompt degradation would this gate actually catch?"* An
assertion is not an answer. The suite answers it with evidence.

A small set of deliberately degraded prompts per gated role, each with an
expected verdict, run under the existing `prompt_eval` marker:

| Mutation | What it does | Expected verdict |
|---|---|---|
| `control` | prompt unchanged | **PASS** (and zero model calls) |
| `truncated` | replace instructions with `"Answer briefly."` | FAIL — the exact OQ-P5 case |
| `scope_dropped` | instruct coverage of three of the six activities | **FAIL_ABSOLUTE** via `scope_preserved` veto |
| `inverted` | reverse an instruction (e.g. "do NOT suggest answers to open questions") | FAIL |

`scope_dropped` must fail *absolutely*, not via the judge — that is the
proof that §4.2 gave the gate teeth. `truncated` is the honest open case: if
it still passes with vetoes and the staged judge in place, that is a
**finding, not a bug** — it would mean the artifact genuinely is invariant
under that mutation, because `output_type` tool-calling plus the schema's own
field descriptions carry the instruction, exactly as OQ-P5 hypothesised. The
suite is built to be able to report that.

Mutations live as fixtures, never as edits to `agents/<role>/instructions.md` —
the gate resolves baseline via `git show`, so a mutation must be injectable
without touching the working tree. `resolve_instructions` (`provider.py`) gains
an explicit override path for this.

---

## 5. Part two — plan adherence

The one genuinely unmeasured agentic signal (§3). Split by provenance, the same
discipline `HandoffSummary` uses: *"`files_touched` is computed from the
materialized diff by the workflow, so no model can misreport it."*

### 5.1 Deterministic core: `PlanDrift` on the record

```python
class PlanDrift(BaseModel):
    """Deterministic plan-vs-execution drift for one task (E-83).

    None on the record means NOT MEASURED. An all-zero PlanDrift would be
    indistinguishable from a task that executed exactly to plan -- the same
    rule WasteBag states for its own bag.
    """
    files_hinted: int
    files_touched: int
    hinted_untouched: list[str]     # planner expected them; nothing was written
    touched_unhinted: list[str]     # written; the planner did not anticipate them
```

Computed in the workflow from `DevTask.files_hint` and the materialized diff.
No model call, no new activity.

**This is a signal and must never gate.** `files_hint` is named a *hint*; a
planner that guessed wrong is a normal, legitimate outcome, and the drift is
interesting precisely because it is not an error. High `touched_unhinted` across
many tasks says something about planner calibration — which is what E-37's
model×role sweep is for — not about any individual run's correctness.

`plan_drift` rides the code-stage `BenchmarkRecord` as `PlanDrift | None`,
following `WasteBag`'s precedent exactly, including the None discipline.

### 5.2 LLM half: extend `deep_review`, do **not** add a lens

`heatmap.py:16-21` carries an explicit warning:

> 'review', 'adversary', 'handoff' and 'deep_review' are LENSES, not DAG stages.
> […] If more lenses accumulate, this axis stops being the SDLC DAG (spec OQ-A3).

A new `plan_adherence` lens would add a fifth and worsen a strain the codebase
already documents. It is not needed. `deep_review` **already** loads the scrubbed
transcript, **already** receives the frozen contract assertions, **already** runs
once per task, and **already** has the verbatim-evidence discipline this needs.

Changes:

1. `_run_deep_review` (`feature.py:973-978`) adds the task's `DevTask` —
   title, description, acceptance criteria, `files_hint` — to the prompt it
   already builds.
2. `DeepReviewReport` gains `plan_deviations: list[PlanDeviation]`:

   ```python
   class PlanDeviation(BaseModel):
       kind: Literal["unplanned_scope", "skipped_criterion", "approach_changed"]
       detail: str
       evidence: str      # VERBATIM transcript span
   ```
3. `verified_integrity_flags`' verification is extended to deviations: a
   deviation whose `evidence` is not present in the transcript is **dropped**,
   never failed — identical to the integrity-flag rule, for the identical
   reason (`feature.py:979-990`).

**Cost: no new stage row, no new model call, no new config flag.** It rides
`deep_review_enabled`, which is off by default.

One honest limitation: `agents/deep_review/instructions.md` changes, and
`deep_review` has **no rubric** — it is in E-82 §8's "no rubric exists" bucket.
So this increment's own prompt change is *not* gated by this increment's own
gate. Authoring a `deep_review` rubric is available follow-up, not a
prerequisite.

---

## 6. Error handling

Governing principle, inherited unchanged: **a broken measurement must never
masquerade as a measurement.**

| Failure | Behavior | Rationale |
|---|---|---|
| Malformed / unknown veto `kind` | **Config error**, loud, names the file and the id | Same shape as `RubricError`. A veto that does not parse is not a passing veto. |
| No `vetoes:` entry for (case, role) | No vetoes run; absolute tier unchanged | Opt-in per case; absence is not failure. |
| Veto references a field the output_type lacks | **Config error** at load, not at judge time | Catchable without a model call; deferring it wastes a gate run. |
| Phase-1 step generation fails | `QualityScore(score=None, judge="error")` | Falling back to the raw rubric would silently restore the old judge under the new label — the discontinuity marker would then lie. |
| Phase-2 scoring fails | `QualityScore(score=None, judge="error")` | Existing `_judge_sync` discipline, unchanged. |
| Veto fails **and** judge errors | Veto wins: score `0.0`, `judge="staged_rubric"` | The veto is a *measurement* that succeeded. Reporting not-measured would discard a real, deterministic finding. |
| `files_hint` empty or no materialized diff | `plan_drift=None` | Not measured. Zeroes would claim perfect adherence. |
| Deviation evidence not in transcript | **Dropped**, warning logged, lens continues | `feature.py:983-989`, verbatim. |
| Mutation suite cannot inject a mutation | **FAIL** the suite | An unrunnable sensitivity proof is the failure mode this suite exists to prevent. |

---

## 7. Testing

Every layer but the last runs with **zero model calls**.

| Layer | Approach | Model calls |
|---|---|---|
| Veto engine | Table-driven, pure: each kind × pass/fail/edge; unknown kind rejected at load | none |
| Veto ↔ output_type | Field-existence validation against each gated role's real `output_type` | none |
| `mean_*` fix | Extends `tests/test_eval_verdict.py` — fake `results.json`, one-sided scores, assert means populated and `judge_status` still `UNAVAILABLE` | none |
| Per-row score persistence | Golden-file over `PromptGateResult` | none |
| Staged judge | Fake via `_set_judge_fn`: canned steps + scores; assert veto composition forces `0.0`; assert phase-1 cache is hit once per rubric sha | none |
| Judge literal | Extends `tests/test_judge_literal.py` with `"staged_rubric"` | none |
| Cross-judge warning | `sdlc benchmark score` over a record set spanning both judge kinds; assert the warning names both | none |
| `PlanDrift` | Pure over `(DevTask, files_touched)`; assert `None` when unmeasurable | none |
| `deep_review` extension | Existing fake-lens pattern; assert unverifiable deviations are dropped, not failed | none |
| **Mutation suite** | `-m prompt_eval`, opt-in, `SDLC_PROMPT_EVAL=1` | **yes** |

The mutation suite is the increment's acceptance criterion. Everything above it
can pass while the gate remains blind; only the suite distinguishes
*operational* from *sensitive*.

---

## 8. Scope

**In:** §4.1 (instrument fixes), §4.2 (vetoes, both layers), §4.3 (staged
judge), §4.4 (mutation suite), §5.1 (`PlanDrift`), §5.2 (`deep_review`
extension).

Veto files authored for **two** of the three rubrics that state a veto in prose:
`cat-cafe-monitoring` clarifier and qa — the roles the gate actually exercises
day one.

`rubric-research.md:12` states a veto too, but `research` is a `DEPS_ROLES` role
the prompt gate cannot build a fixture for (E-82 §8), and §6 requires veto
fields to be validated against the role's real `output_type` at load. For a role
whose agent cannot be constructed, that validation cannot run — so authoring its
veto now would either weaken the load-time check for every role or introduce a
silently unvalidated file. It is authored when `research` becomes eval-able.

**Out, and why:**

- **The DeepEval dependency** — §3, with a recorded revisit trigger.
- **Replacing promptfoo** — E-82's runner choice stands; nothing here needs it
  revisited.
- **Red-teaming** — still its own spec (E-82 §8).
- **CI** — still not this increment.
- **Backfilling old records to the new judge scale** — the discontinuity is
  marked (§2.1), not erased. Re-judging historical artifacts would spend real
  tokens to manufacture comparability that the `judge` field can express for
  free.
- **A `deep_review` rubric** — would let this increment's own prompt change be
  gated (§5.2). Desirable, separable, not required.
- **Vetoes for `add-login-greenfield` / `todo-api-greenfield`** — their rubrics
  state no vetoes. Inventing some to fill the table would be authoring
  requirements from the eval side.

**Separability note.** Parts one and two were scoped into one increment by
explicit choice. They share a philosophy — deterministic evidence carries the
teeth, the LLM advises — but almost no code. If the increment runs long,
**§5 can be cut whole without touching §4**; the reverse is not true, since §5.1
is the smaller half and §4.1 gates everything.

---

## 9. Open questions

- **OQ-P5 — narrowed, not yet closed.** The mutation suite (§4.4) is built to
  answer it. `scope_dropped` failing absolutely proves teeth. `truncated`
  remains genuinely open: it may still pass, and that would be a finding about
  structured-output roles — `output_type` tool-calling and schema field
  descriptions carrying the instruction — rather than a defect in the gate.
  The increment is designed to be able to report that outcome honestly.
- **OQ-P6 (new) — veto authorship is manual and unenforced.** Nothing checks
  that a rubric stating "scores 0 regardless" has a corresponding veto file. A
  lint pass over rubric prose for veto language is possible; whether it is worth
  a false-positive budget is unresolved.
- **OQ-P7 (new) — `PlanDrift` has no baseline.** Drift is recorded before
  anyone knows what a normal amount looks like. It becomes interpretable only
  after enough runs to see a distribution, and until then it is data, not
  signal. Naming the threshold prematurely would invent a standard from one
  observation — the mistake OQ-P1 already records for `δ_min`.
- **OQ-P8 (new) — phase-1 step caching interacts with judge nondeterminism.**
  Steps are cached per `sha256(rubric)` within a process, so baseline and
  working are scored against identical steps — which is what makes the
  comparison fair. Across processes they may differ. Whether steps should be
  committed alongside the rubric, making them a reviewable artifact rather than
  a generated one, is unresolved and would change §4.3's shape.
