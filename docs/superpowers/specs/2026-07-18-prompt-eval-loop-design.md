# Prompt eval loop (E-4)

**Date:** 2026-07-18
**Roadmap:** §9.1 `E-4`; §7 "prompts as versioned assets **with an eval loop**"
**Requirements:** No FR moves. Closes the second clause of §7's prompts-as-assets item.
**Builds on:** `2026-07-17-agents-as-folders-design.md` — **shipped** (`bb483f4`…`8bef535`);
`2026-07-04-pipeline-step-benchmarking-design.md` — the judge/rubric/scoring machinery this reuses.
**Design input:** [`vercel/eve`](https://github.com/vercel/eve) — "the filesystem is the authoring interface".

## Problem

E-2 moved every proposer prompt into `agents/<role>/instructions.md`, hashed into `PROMPT_SHAS`
from file content. Prompts are now versioned assets — a prompt change is a reviewable file diff. But
§7's clause has two halves, and only the first is closed: **"versioned assets with an eval loop."**
There is no way to answer the question a prompt edit raises — *is the new prompt better than the old
one?*

The existing benchmark subsystem sweeps `(case × harness × model)` and LLM-judges proposer artifacts
against per-case rubrics, but it holds the prompt **fixed**: every cell in a run reads the same
shipped `instructions.md`, so `BenchmarkRecord.prompt_sha` is constant across a matrix. The prompt is
the one variable the benchmark cannot vary. That is the gap E-4 fills.

## Findings

1. **A prompt only affects its own proposer stage.** `instructions.md` is a role's system prompt.
   Editing `agents/reviewer/instructions.md` changes the reviewer agent and nothing else. So the
   honest, cheap way to evaluate a prompt edit is to run *just that one proposer agent* on a fixed
   input and judge its output — not the whole 15-stage DAG. A stage-isolated eval is one model call
   per variant; a full-pipeline eval is an entire pipeline run per variant. The isolation is not a
   shortcut, it is the correct granularity for the thing being measured.

2. **The proposer's input is a user-prompt string built inline in `feature.py`.** Each stage assembles
   a string from upstream artifacts and calls `t_<role>.run(prompt)` (e.g. `feature.py:547`, the
   reviewer: frozen contract assertions + test results + diff). The system prompt is the
   `instructions.md`; the user prompt is that assembled string. To eval a prompt edit, freeze the
   user-prompt string as a fixture, then rerun it against variant system prompts. **The fixture is the
   captured user prompt, not a hand-authored artifact** — hand-authoring risks feeding the agent an
   input shape the pipeline never produces, which would measure the wrong thing.

3. **The proposer activity input is recoverable from Temporal history.** `t_<role>` is a
   `TemporalAgent`; a proposer run executes as a Temporal activity, so its input is in the run's
   history. `drift.py` already reads production history through an injectable `HistoryProvider`
   Protocol. Capture reuses that exact pattern — no new history-reading mechanism, and the production
   pipeline is untouched (no capture hook in `feature.py`).

4. **Scoring already exists and must not be reinvented.** `judge.py`'s `judge_artifact` is a
   cross-family LLM judge that scores an artifact against a rubric and *never raises* — on any failure
   it returns `QualityScore(score=None, judge="error")`. The eval reuses it verbatim. Rubrics are the
   existing `benchmarks/cases/<case>/rubric-<stagekey>.md` assets. The judge model comes from
   `benchmarks/config.yaml`'s `default_judge_model`, and the eval asserts judge-family ≠ author-family
   with the existing `model_family()` (ADR-6) — the same invariant the benchmark already enforces.

5. **Two proposers carry `deps` and are out of scope for v1.** `architect` (and the optional
   `research` role) pass `deps=` to `.run()` — tools and context beyond the prompt string. A
   prompt-string fixture cannot faithfully reconstruct a live deps object, so evaluating those two
   from a captured prompt alone would report a lower-fidelity score under a false appearance of
   parity. v1 covers the six pure prompt-in/artifact-out proposers and refuses the two deps-carrying
   ones with a clear message. Deps-aware eval is future work, not a silent partial.

6. **Three vocabularies name the same stage, and the eval must map between them.** Role names
   (`reviewer`, `planner`, `qa`), stage keys (`review`, `plan`, `qa` — `STAGE_ROLES` in `roles.py`),
   and rubric keys (`architect`, `clarifier` — the `BenchmarkConfig.rubrics` map keys) do not all
   agree. The eval maps role → rubric using the existing rubric-loading conventions; it does not
   invent a fourth vocabulary.

7. **The replay must not touch Temporal.** Capture needs history; the eval replay does not. Building
   the agent via `agents/<role>/agent.py`'s `build()` and calling `agent.run_sync(prompt)` is a plain
   synchronous script — no worker, no workflow, no task queue. This is what makes the loop fast enough
   to sit inside a human's edit cycle.

## Scope

**In:**

- A standalone `src/sdlc/eval/` module, independent of Temporal for the replay path.
- `sdlc eval capture --from <run_id> [--case <label>]` — history → `agents/<role>/fixtures/<label>.json`.
- `sdlc eval <role> [--against <git-ref>] [--case <label>] [--n <k>]` — A/B a working-tree prompt
  against a committed one, judged per fixture, printing the delta.
- Six supported roles: `clarify`, `planner`, `qa`, `reviewer`, `analyst`, `merge_verdict`.
- Fixtures stored beside the asset they exercise: `agents/<role>/fixtures/<case>.json`.
- Reuse of `judge.py`, the `benchmarks/cases/` rubrics, `benchmarks/config.yaml`'s judge model, and
  `model_family()`'s ADR-6 check.

**Out:**

- `architect` and `research` (finding 5). Refused, not silently degraded.
- Full-pipeline / matrix eval — the existing benchmark already does `(case × harness × model)`; this
  increment adds prompt-as-variable at stage granularity, not a fourth matrix axis.
- Stored baselines, a CI regression gate, pass/fail thresholds. This is an on-demand exploration tool.
  A gate is the natural next increment if v1 proves useful, and is explicitly deferred.
- Any change to `feature.py`, the registry loader's contract, `judge.py`, or `PROMPT_SHAS`.
- Deps capture/reconstruction.

## Design

### 1. Module layout

```
src/sdlc/eval/
  __init__.py
  fixtures.py    # EvalFixture model; capture: history -> agents/<role>/fixtures/<label>.json
  runner.py      # run_variant(role, instructions_text, fixture) -> artifact_json
  compare.py     # orchestrate A vs B across fixtures; assemble a pure EvalReport
  cli.py         # wires `sdlc eval {capture,<role>}`
```

The pure core (`fixtures` capture logic, `runner`, `compare`) is separated from the thin CLI shell,
the same split the channel contract used: `compare.py` returns a pure `EvalReport`; `cli.py` renders
it and owns argument parsing and process exit codes.

### 2. Fixture model and storage

```python
# src/sdlc/eval/fixtures.py
class EvalFixture(BaseModel):
    role: str            # one of the six supported roles
    case: str            # label / filename stem, e.g. "add-login"
    prompt: str          # the exact user-prompt string the agent received
    model: str           # author model used in the captured run (A and B share it)
    source_run_id: str   # provenance
    captured_at: datetime
```

Stored at `agents/<role>/fixtures/<case>.json`. Fixtures live inside the role folder, next to
`instructions.md` and `agent.py` — the asset they exercise. This is consistent with agents-as-folders:
a role folder gains an optional `fixtures/` directory. The registry loader ignores directory entries
that are not `agent.yaml` / `instructions.md` / `agent.py`, so **no loader change is required**; a
regression test pins that `load_registry` stays green with a `fixtures/` dir present.

**Only A and B share the model, not the judge.** The captured author model is stored so both prompt
variants run under the same model — the prompt is the only thing that differs between A and B. The
judge model is resolved separately (§5) and must be a different family.

### 3. Capture (`fixtures.py`)

```
capture(provider, run_id, case, roots) -> list[EvalFixture]:
  history = provider.fetch_history(run_id)      # HistoryProvider Protocol, from drift.py
  for each proposer activity input in history:
    role = <role the activity ran for>
    if role not in SUPPORTED_ROLES: continue    # architect/research/harness roles skipped
    yield EvalFixture(role, case, prompt=<captured user prompt>,
                      model=<author model from history>, source_run_id=run_id, ...)
  write each fixture to agents/<role>/fixtures/<case>.json
```

`HistoryProvider` is imported from `drift.py`, not re-declared. Capture is filesystem-writing and
history-reading only — no Temporal client construction in the pure function; the CLI supplies a
concrete provider (a live client in production, a fake in tests), exactly as `drift.py` does.

The precise extraction of role + prompt + model from a history event is pinned by
`tests/test_eval_fixtures.py` against a synthetic history fixture, mirroring `test_drift_harvester.py`.
Where the model is not recoverable from a history event, that fixture is skipped with a warning rather
than written with a placeholder — a fixture that cannot name its author model cannot enforce the
cross-family judge check (§5).

### 4. Replay (`runner.py`)

```python
def run_variant(role: str, instructions_text: str, fixture: EvalFixture,
                agents_dir: Path) -> str:
    build = _load_build(role, agents_dir / role)          # reuse loader's private import
    agent = build(fixture.model, instructions_text, MODEL_SETTINGS)
    result = agent.run_sync(fixture.prompt)
    return result.output.model_dump_json()
```

`_load_build` is the loader's existing per-role `agent.py` importer (E-1) — the eval does not add a
second way to import an `agent.py`. `MODEL_SETTINGS` is imported from `roles.py`. The variant's system
prompt arrives as `instructions_text`, supplied by `compare.py`; `runner` never reads `instructions.md`
itself, so the same function serves both the working-tree and the committed variant.

The load-bearing test (`test_eval_runner.py`) asserts the variant text **actually reaches the system
prompt** — a `run_variant` that ignored `instructions_text` and read the shipped file would score both
variants identically and silently defeat the whole tool.

### 5. Compare and judge (`compare.py`)

```
compare(role, case, against_ref, k, agents_dir, judge_model) -> EvalReport:
  fx        = load agents/<role>/fixtures/<case>.json
  B_text    = read agents/<role>/instructions.md            # working tree
  A_text    = git show <against_ref>:agents/<role>/instructions.md   # committed
  if A_text == B_text: return EvalReport(unchanged=True)    # nothing to compare
  assert model_family(judge_model) != model_family(fx.model)   # ADR-6, before any call
  rubric    = load benchmarks/cases/<case>/rubric-<rubrickey(role)>.md
  for n in range(k):                                        # k defaults to 1
    out_A = run_variant(role, A_text, fx, agents_dir)
    out_B = run_variant(role, B_text, fx, agents_dir)
    score_A = judge_artifact.sync(JudgeInput(out_A, rubric, fx.model, judge_model))
    score_B = judge_artifact.sync(JudgeInput(out_B, rubric, fx.model, judge_model))
  return EvalReport(per_run=[...], mean_a, mean_b, mean_delta)
```

`EvalReport` is a pure dataclass/model: per-run `(score_a, score_b, delta, components)`, plus means
and an `unchanged` flag. `judge_artifact.sync` is the existing synchronous judge seam (`judge.py:127`)
— reused unchanged, including its "never raises, returns `score=None` on error" contract. `judge_model`
defaults to `benchmarks/config.yaml`'s `default_judge_model`, overridable via `--judge-model`.

`rubrickey(role)` maps a role name to its rubric filename using the existing stage/rubric conventions
(finding 6); it is a small explicit table in `compare.py`, tested.

### 6. CLI (`cli.py`)

```
sdlc eval capture --from <run_id> [--case <label>]
sdlc eval <role>  [--against <git-ref>] [--case <label>] [--n <k>] [--judge-model <m>]
```

- `--against` defaults to `HEAD`. `--n` defaults to `1`. `--case` defaults to the sole fixture if a
  role has exactly one, else it is required.
- Rendered output for the eval command:

  ```
  eval reviewer  (case add-login, judge openai/gpt-5.2, n=1)
    HEAD      0.71
    working   0.83
    delta    +0.12
  ```

The CLI is wired into the existing `sdlc` argument parser alongside `benchmark`.

## Error handling

Mirrors the benchmark's stance: an eval is observational, so a broken *judge* never crashes the tool,
but a broken *human loop* (bad creds, missing fixture) fails loudly because the human is right there.

| Failure | Behavior |
|---|---|
| Role is `architect` / `research` | Refused at CLI parse: "carries deps; deps-aware eval is future work". `_DEPS_ROLES` is a named constant, not a scattered check. |
| No fixture for role/case | Error naming the expected path and the `eval capture` command that creates it; exit non-zero. |
| `judge_artifact` errors | `score=None`; report shows `n/a` for that variant and prints "1 judge error"; exit 0 (observational, as the benchmark). |
| Judge family == author family | Refused before any model call — `model_family()` (ADR-6). Exit non-zero. |
| `--against` ref lacks the file (new role, no committed baseline) | A treated as empty; report says "no committed baseline; showing working-tree score only". |
| Working tree == ref | "no change vs `<ref>`"; exit 0. |
| `agent.run_sync` raises (bad model creds, network) | Surface the error, exit non-zero — the human's own loop fails loudly. |
| Capture: model not recoverable for an event | Skip that fixture with a warning (finding 3); never write a fixture that cannot enforce the cross-family check. |

## Testing

TDD, per the repo's habit. All CI tests are deterministic — no real model or judge calls (a `TestModel`
stub via `write_registry_dir` from `conftest.py`; a fake judge fn via `_set_judge_fn`; a synthetic
history fixture; a fake `HistoryProvider`).

- `tests/test_eval_fixtures.py` — capture over a synthetic history fixture emits the correct
  `EvalFixture`s (role, prompt, model); harness and unsupported roles skipped; an event with no
  recoverable model is skipped, not written.
- `tests/test_eval_runner.py` — `run_variant` builds the agent from a tmp `agents/` tree via
  `_load_build` and runs a `TestModel` stub, returning serialized output; **asserts the variant
  `instructions_text` reaches the system prompt** (the anti-no-op guard).
- `tests/test_eval_compare.py` — with a fake judge returning scripted scores, `EvalReport` deltas and
  means are correct; `score=None` handled; identical A/B short-circuits (`unchanged=True`); the
  cross-family assertion fires on a same-family judge/author pair.
- `tests/test_eval_cli.py` — `architect`/`research` refused with the deps message; missing-fixture
  error names the path; `--against` reads a committed file from a tmp git repo; the "no committed
  baseline" and "no change" paths render correctly.
- `tests/test_registry_ignores_fixtures.py` — `load_registry` stays green with an
  `agents/<role>/fixtures/` directory present (pins finding: fixtures beside assets need no loader
  change).

`judge.py`, `drift.py`'s `HistoryProvider`, and the registry loader are reused unchanged, so their own
tests are untouched. If a test that exercises any of them needs editing, the increment has leaked
beyond its scope and that is a design bug, not a test-maintenance chore.

## Roadmap amendments

- **§9.1 E-4** — `[x]` when this lands. Records that the eval is stage-isolated and on-demand (an
  exploration tool), and that the regression-gate half is a deliberate future increment.
- **§7 "prompts as versioned assets with an eval loop"** — the second clause closes; the item becomes
  `[x]`.
- **§9.1 E-5** — unaffected; still speculative, still not scheduled.

## Open questions (deferred, not blocking)

- **OQ-E1:** Deps-aware eval for `architect`/`research` — serialize a deps snapshot in the fixture and
  reconstruct it on replay. Needed before those two roles are evaluable. Finding 5.
- **OQ-E2:** Regression gate — a committed baseline per role + a CI check on `instructions.md` diffs.
  The natural next increment; deferred until the exploration tool proves its value.
- **OQ-E3:** Judge noise at `k=1` — a single judge call per variant is cheap but noisy. Whether to
  default `k>1` and surface variance, or leave that to the human via `--n`. Decide from real use.
