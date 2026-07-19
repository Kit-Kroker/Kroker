# Cat café monitoring benchmark + qa/research judging (E-27) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `cat-cafe-monitoring` golden benchmark case sized to require planner decomposition, and wire the `qa` and `research` stages to the LLM judge so its rubrics are not inert.

**Architecture:** Five small changes, each mirroring an existing call site. `CaseSpec` gains `research_enabled`; `_cell_config` threads it and injects a `research` RoleConfig carrying the provider; `feature.py` gains two `self._judge(...)` calls matching the three already there; the case ships with five rubrics. No new modules, no new abstractions.

**Tech Stack:** Python 3.11+, Pydantic v2, Temporal (`temporalio`), pytest, PyYAML.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-19-cat-cafe-monitoring-benchmark-design.md`. Read it before Task 1.
- **Branch:** `feat/cat-cafe-benchmark` (already created; the spec is committed there).
- **`agents/research/agent.yaml` keeps `provider: fake`.** Never commit `provider: tavily` — `loader.py:221` fails registry validation at boot without `TAVILY_API_KEY`, breaking CI and every contributor. The provider is injected per-case by `_cell_config`.
- **No test may make a real model, network, or Tavily call.** The judge seam is `_set_judge_fn`; reset it via the existing autouse fixture pattern in `tests/test_benchmark_judge.py`.
- **`CaseSpec.research_enabled` defaults `False`** so `add-login-greenfield` and `todo-api-greenfield` inherit no behavior change — including no new abort path (see the spec's Risk section).
- **Judge model is `openai/gpt-5.2`**, cross-family against the `zai-coding-plan/glm-5.2` author (ADR-6). The matrix expander rejects same-family configs.
- Run tests with `python -m pytest` from the repo root. `git` must be on PATH.
- After adding any new module, re-run `pip install -e .` — setuptools' editable wheel does not auto-discover new files.

---

### Task 1: `CaseSpec.research_enabled` threaded into the per-cell config

**Files:**
- Modify: `src/sdlc/benchmarks/models.py` (the `CaseSpec` class, ~line 83)
- Modify: `src/sdlc/benchmarks/workflow.py:35-59` (`_cell_config`)
- Test: `tests/test_benchmark_workflow.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CaseSpec.research_enabled: bool` (default `False`), read by `_cell_config(base, idea, spec, harness, model, bench_run_id, rubrics=None) -> PipelineConfig`. Task 4's `case.yaml` sets it `true`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_benchmark_workflow.py`:

```python
def _research_spec():
    return CaseSpec(
        case_id="cat-cafe", idea_summary="cats",
        mode="greenfield",
        harnesses=[HarnessKind.OPENCODE],
        models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2", rubrics={},
        research_enabled=True)


def test_case_spec_research_disabled_by_default():
    assert _spec().research_enabled is False


def test_cell_config_leaves_research_off_by_default():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), HarnessKind.OPENCODE,
                       "openai/gpt-5.2", bench_run_id="b1")
    assert cfg.research_enabled is False
    assert "research" not in cfg.roles


def test_cell_config_enables_research_and_injects_provider():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _research_spec(), HarnessKind.OPENCODE,
                       "zai-coding-plan/glm-5.2", bench_run_id="b1")
    assert cfg.research_enabled is True
    rc = cfg.roles["research"]
    assert rc.kind == "research"
    assert rc.provider == "tavily"


def test_cell_config_research_role_is_not_harness_overridden():
    """The research role is a proposer-side role: the cell's harness/model
    override applies to harness roles, but the injected research role must
    keep kind='research' and carry no harness."""
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _research_spec(), HarnessKind.OPENCODE,
                       "zai-coding-plan/glm-5.2", bench_run_id="b1")
    assert cfg.roles["research"].harness is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_benchmark_workflow.py -v -k research`
Expected: FAIL — `CaseSpec` has no field `research_enabled` (Pydantic `ValidationError: Extra inputs are not permitted`).

- [ ] **Step 3: Add the field to `CaseSpec`**

In `src/sdlc/benchmarks/models.py`, inside `class CaseSpec`, after the `rubrics` field:

```python
    # FR-107: run the research stage for this case. Default False so existing
    # cases inherit no behavior change -- including no new abort path, since
    # a grounding-verifier violation hard-returns the whole run
    # (feature.py:717).
    research_enabled: bool = False
```

- [ ] **Step 4: Thread it through `_cell_config`**

In `src/sdlc/benchmarks/workflow.py`, inside `_cell_config`, immediately after the `cfg.roles = {...}` assignment and before `cfg.benchmark = BenchmarkConfig(...)`:

```python
    # The research provider is a property of the RUN, not the repo: the
    # registry keeps provider: fake so CI and contributors need no
    # TAVILY_API_KEY (loader.py:221 fails closed at boot otherwise). Inject
    # the real provider here, only for a case that asked for research.
    # PipelineConfig.roles has no 'research' entry by default, so without
    # this ResearchDeps falls back to provider="fake" (feature.py:686,:819)
    # and the fake corpus raises in production.
    cfg.research_enabled = spec.research_enabled
    if spec.research_enabled:
        cfg.roles["research"] = RoleConfig(kind="research", provider="tavily")
```

Add `RoleConfig` to the existing `from ..models import (...)` block inside the
`with workflow.unsafe.imports_passed_through():` guard.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_benchmark_workflow.py -v`
Expected: PASS — the four new tests plus the five pre-existing `_cell_config` tests.

- [ ] **Step 6: Verify the existing cases are unaffected**

Run: `python -m pytest tests/test_golden_case_loads.py -v`
Expected: PASS, unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/benchmarks/models.py src/sdlc/benchmarks/workflow.py tests/test_benchmark_workflow.py
git commit -m "feat(benchmarks): per-case research_enabled + injected provider (E-27)"
```

---

### Task 2: Judge the research stage

**Files:**
- Modify: `src/sdlc/workflows/feature.py:728-734` (the research `_stage_record` call)
- Create: `tests/test_research_stage_judging.py`
- Test: `tests/test_benchmark_judge.py`

**Interfaces:**
- Consumes: `_build_judge_input(artifact_json, rubrics, stage, author_model, judge_model) -> JudgeInput | None` from `sdlc.benchmarks.judge` (already exists).
- Produces: the rubric key `"research"` becomes live. Task 4 authors `rubric-research.md` against it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_benchmark_judge.py`:

```python
def test_build_judge_input_supports_research_key():
    ji = _build_judge_input(
        artifact_json='{"findings": []}',
        rubrics={"research": "score grounding 0..1"},
        stage="research",
        author_model="zai-coding-plan/glm-5.2",
        judge_model="openai/gpt-5.2",
    )
    assert ji is not None
    assert ji.rubric == "score grounding 0..1"


def test_build_judge_input_research_absent_returns_none():
    """A case with no research rubric must skip judging gracefully rather
    than fail the stage."""
    ji = _build_judge_input(
        artifact_json='{"findings": []}',
        rubrics={"clarifier": "r"},
        stage="research",
        author_model="zai-coding-plan/glm-5.2",
        judge_model="openai/gpt-5.2",
    )
    assert ji is None
```

- [ ] **Step 2: Run them — they pass already, and that is the point**

Run: `python -m pytest tests/test_benchmark_judge.py -v -k research`
Expected: PASS. `_build_judge_input` is key-agnostic, so these are regression guards on the contract, **not** the TDD-red test for this task. Step 2a supplies that.

- [ ] **Step 2a: Write the genuinely-failing wiring test**

The real change is a call site inside workflow code, which cannot run without a
Temporal server. This repo tests stage wiring by reading the source —
see `tests/test_analyst_stage_wiring.py`. Create
`tests/test_research_stage_judging.py`:

```python
"""The research stage is judged against a rubric, not hardcoded to a
contract score."""
import inspect

from sdlc.workflows import feature


def test_research_brief_is_judged():
    src = inspect.getsource(feature.FeatureWorkflow.run)
    assert '"research"' in src
    assert "brief.model_dump_json()" in src
    assert "quality_score=_r_quality.score" in src


def test_research_record_no_longer_hardcodes_contract_judge():
    """The old record passed quality_score=None, judge="contract". Both must
    be gone from the research block, or the rubric can never affect a score."""
    src = inspect.getsource(feature.FeatureWorkflow.run)
    start = src.index('stage="research"')
    block = src[start:start + 400]
    assert "quality_score=None" not in block
    assert 'judge="contract"' not in block
```

- [ ] **Step 2b: Run it to verify it fails**

Run: `python -m pytest tests/test_research_stage_judging.py -v`
Expected: FAIL — the research block still reads `quality_score=None, judge="contract"`.

- [ ] **Step 3: Replace the hardcoded score at the research call site**

In `src/sdlc/workflows/feature.py`, the research stage currently records:

```python
            await self._record(cfg, self._stage_record(
                cfg, stage="research", role="research",
                started=_r_started, ended=workflow.now(),
                quality_score=None, judge="contract",
                outcome=BenchmarkOutcome.PASS,
                model=STAGE_MODELS.get("research", "unknown")))
```

Replace with:

```python
            _r_quality = await self._judge(
                cfg, brief.model_dump_json(), "research",
                author_model=STAGE_MODELS.get("research", "unknown"))
            await self._record(cfg, self._stage_record(
                cfg, stage="research", role="research",
                started=_r_started, ended=workflow.now(),
                quality_score=_r_quality.score, judge=_r_quality.judge,
                outcome=BenchmarkOutcome.PASS,
                model=STAGE_MODELS.get("research", "unknown")))
```

`brief` is the `ResearchBrief` already in scope (it is passed to
`verify_brief_activity` and `brief_digest` just above).

- [ ] **Step 4: Run the workflow purity and full suites**

Run: `python -m pytest tests/test_factory_purity.py -v`
Expected: PASS — `_judge` dispatches through `execute_activity`, so no I/O enters workflow code.

Run: `python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_benchmark_judge.py tests/test_research_stage_judging.py
git commit -m "feat(benchmarks): judge the research brief against a rubric (E-27)"
```

---

### Task 3: Judge the QA report, without disturbing the deterministic code record

**Files:**
- Modify: `src/sdlc/workflows/feature.py:555-568` (the `stage="code"` record inside `_dev_task`)
- Create: `tests/test_qa_stage_judging.py`
- Test: `tests/test_benchmark_judge.py`

**Interfaces:**
- Consumes: `_build_judge_input` as in Task 2.
- Produces: a second `BenchmarkRecord` per task attempt with `stage="qa"`, `role="qa"`, `scope=TASK_ATTEMPT`. `scoring.py` aggregates by `(case_id, stage, harness, model)` with a mean, so N-per-run needs no scoring change.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_benchmark_judge.py`:

```python
def test_build_judge_input_supports_qa_key():
    ji = _build_judge_input(
        artifact_json='{"tests_passed": true, "issues": []}',
        rubrics={"qa": "score determinism 0..1"},
        stage="qa",
        author_model="zai-coding-plan/glm-5.2",
        judge_model="openai/gpt-5.2",
    )
    assert ji is not None
    assert ji.rubric == "score determinism 0..1"
```

- [ ] **Step 2: Run it — passing already is expected**

Run: `python -m pytest tests/test_benchmark_judge.py -v -k qa`
Expected: PASS — a regression guard on the contract, **not** this task's TDD-red test. Step 2a supplies that.

- [ ] **Step 2a: Write the genuinely-failing wiring test**

The QA call site lives in `FeatureWorkflow._dev_task` (`feature.py:469`), not
`run`. Same source-reading pattern as `tests/test_analyst_stage_wiring.py`.
Create `tests/test_qa_stage_judging.py`:

```python
"""The QA report is judged against a rubric in its OWN record, leaving the
deterministic stage="code" record's contract score untouched."""
import inspect

from sdlc.workflows import feature


def test_qa_report_is_judged():
    src = inspect.getsource(feature.FeatureWorkflow._dev_task)
    assert '"qa"' in src
    assert "qa.model_dump_json()" in src
    assert 'stage="qa"' in src


def test_code_record_keeps_its_deterministic_contract_score():
    """Finding 4: the qa record is ADDITIVE. If the code record stopped
    carrying judge="contract", an LLM opinion has replaced a deterministic
    signal -- the exact regression this task must not cause."""
    src = inspect.getsource(feature.FeatureWorkflow._dev_task)
    start = src.index('stage="code"')
    block = src[start:start + 400]
    assert 'judge="contract"' in block


def test_qa_record_is_separate_from_the_code_record():
    src = inspect.getsource(feature.FeatureWorkflow._dev_task)
    assert src.count("self._record(") >= 2
```

- [ ] **Step 2b: Run it to verify it fails**

Run: `python -m pytest tests/test_qa_stage_judging.py -v`
Expected: FAIL on `test_qa_report_is_judged` — no `stage="qa"` record exists yet.
`test_code_record_keeps_its_deterministic_contract_score` passes now and must
keep passing; it is the guard, not the driver.

- [ ] **Step 3: Add the qa record beside the code record**

In `src/sdlc/workflows/feature.py`, immediately **after** the existing
`await self._record(cfg, self._stage_record(cfg, stage="code", ...))` block
inside the task loop, add:

```python
            # The QA report gets its OWN record. The stage="code" record above
            # keeps its deterministic contract score (1.0 iff tests passed and
            # no issues) -- an LLM opinion must never overwrite a deterministic
            # signal. Cardinality is per-task-attempt, not once-per-run like
            # clarifier/architect/planner; scoring.py means over them natively.
            _qa_quality = await self._judge(
                cfg, qa.model_dump_json(), "qa",
                author_model=STAGE_MODELS["qa"])
            await self._record(cfg, self._stage_record(
                cfg, stage="qa", role="qa",
                started=_attempt_started, ended=workflow.now(),
                quality_score=_qa_quality.score, judge=_qa_quality.judge,
                outcome=(BenchmarkOutcome.PASS
                         if (qa.tests_passed and not qa.issues)
                         else BenchmarkOutcome.FAIL),
                model=STAGE_MODELS["qa"],
                task_id=task.id, attempt=attempt - 1))
```

`qa` is the `QAReport` already in scope from `t_qa.run(...)`. `STAGE_MODELS["qa"]`
exists — `STAGE_ROLES` maps stage `"qa"` to role `"qa"` (`roles.py:71`).

**Attribution:** the record carries `model=STAGE_MODELS["qa"]` and **no** `harness`,
matching the four other judged stages. Do NOT use `role_cfg.model` /
`role_cfg.harness` here: `role_cfg` is the *dev coding harness* config
(`feature.py:479`; `cfg.roles` has no `"qa"` entry), but the artifact being scored
is authored by `t_qa`, a Pydantic AI agent. Since `scoring.py` aggregates by
`(case_id, stage, harness, model)`, dev-harness attribution would credit the QA
rubric score to the wrong model — and would contradict the `author_model` passed
to `_judge` two lines above.

- [ ] **Step 4: Run the suites**

Run: `python -m pytest tests/test_factory_purity.py tests/test_benchmark_scoring.py -v`
Expected: PASS.

Run: `python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_benchmark_judge.py tests/test_qa_stage_judging.py
git commit -m "feat(benchmarks): judge the QA report alongside the code record (E-27)"
```

---

### Task 4: The `cat-cafe-monitoring` case and its five rubrics

**Files:**
- Create: `benchmarks/cases/cat-cafe-monitoring/case.yaml`
- Create: `benchmarks/cases/cat-cafe-monitoring/rubric-clarifier.md`
- Create: `benchmarks/cases/cat-cafe-monitoring/rubric-architect.md`
- Create: `benchmarks/cases/cat-cafe-monitoring/rubric-planner.md`
- Create: `benchmarks/cases/cat-cafe-monitoring/rubric-qa.md`
- Create: `benchmarks/cases/cat-cafe-monitoring/rubric-research.md`
- Test: `tests/test_golden_case_loads.py`

**Interfaces:**
- Consumes: `CaseSpec.research_enabled` (Task 1); the live `qa` and `research` rubric keys (Tasks 2, 3).
- Produces: a case loadable by `load_case_spec(path) -> CaseSpec` and expandable by `expand_matrix(spec) -> list[BenchmarkCell]` to exactly one cell.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_golden_case_loads.py`:

```python
CAT_CASE = (REPO_ROOT / "benchmarks" / "cases" / "cat-cafe-monitoring"
            / "case.yaml")


def test_cat_cafe_case_loads_as_one_cell():
    assert CAT_CASE.exists(), f"missing {CAT_CASE}"
    spec = load_case_spec(str(CAT_CASE))
    assert spec.case_id == "cat-cafe-monitoring"
    assert spec.research_enabled is True
    assert len(expand_matrix(spec)) == 1


def test_cat_cafe_ships_five_rubrics():
    d = CAT_CASE.parent
    for key in ("clarifier", "architect", "planner", "qa", "research"):
        assert (d / f"rubric-{key}.md").exists(), f"missing rubric-{key}.md"


def test_cat_cafe_rubrics_are_all_registered():
    """A rubric file on disk that case.yaml does not name is dead weight;
    a named rubric with no file is silently skipped by load_case_assets."""
    spec = load_case_spec(str(CAT_CASE))
    assert set(spec.rubrics) == {
        "clarifier", "architect", "planner", "qa", "research"}
    for rel in spec.rubrics.values():
        assert (CAT_CASE.parent / rel).exists()


def test_cat_cafe_description_preserves_every_activity():
    """The kata's functional requirements must not shrink -- all six
    activities must survive into the case description."""
    spec = load_case_spec(str(CAT_CASE))
    body = spec.description.lower()
    for activity in ("sleeping", "eating", "drinking", "litter",
                     "playing", "fighting"):
        assert activity in body, f"description dropped '{activity}'"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_golden_case_loads.py -v -k cat_cafe`
Expected: FAIL — `missing .../cat-cafe-monitoring/case.yaml`.

- [ ] **Step 3: Write `case.yaml`**

Create `benchmarks/cases/cat-cafe-monitoring/case.yaml`:

```yaml
case_id: cat-cafe-monitoring
idea_summary: Real-time monitoring for a cat café — detect each cat's activity
  from smart-collar telemetry and show it live on the floor plan.
description: |
  Ten cats live in the café. Each cat wears a smart collar that sends the
  cat's exact coordinates and the cat's breathing rate. Sensor data arrives
  every 5 seconds.

  Generate this sensor data randomly. Do not build collar data emulators.
  Keep it as simple as possible.

  The café floor plan includes the coordinates of rest areas, litter boxes,
  water bowls, and food bowls.

  Anything not described here is your choice — the rules are up to you. The
  functional requirements below must not be changed: do not make them
  smaller and do not add new ones.

  Task 1. Activity Detection
  Detect the current activity of each cat from collar telemetry and distance
  to café zones. The detectable activities are: sleeping, eating, drinking,
  using the litter box, playing, and fighting.

  Task 2. Monitoring
  Show in real time on the café floor plan: the movement of all cats; the
  possible current activity of each cat from Task 1; and a risk analysis for
  each cat's life or health based on collar data. Cats with a detected life
  or health risk must be marked in red.

  For each cat the user must also be able to see detailed sensor data and
  movement history for the last 24 hours.
mode: greenfield
repo_url: D:/own/sdlc-scratch-repos/cat-cafe-monitoring
research_enabled: true
harnesses:
  - opencode
models:
  - zai-coding-plan/glm-5.2
judge_model: openai/gpt-5.2     # different family than the author (ADR-6)
extra_args_by_model:
  zai-coding-plan/glm-5.2:
    - --variant
    - max        # opencode: max reasoning effort for GLM 5.2
rubrics:
  clarifier: rubric-clarifier.md
  architect: rubric-architect.md
  planner: rubric-planner.md
  qa: rubric-qa.md
  research: rubric-research.md
```

- [ ] **Step 4: Write `rubric-clarifier.md`**

```markdown
# Clarifier rubric — cat-cafe-monitoring

Score the ClarifiedRequirements artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

- **questions_material (0.3):** every open question materially changes the
  design — activity thresholds, what counts as a health risk numerically,
  zone geometry and proximity radius, history retention. No filler; each has
  a "why_it_matters"
- **scope_preserved (0.3):** all six activities (sleeping, eating, drinking,
  litter box, playing, fighting) and both tasks survive. Silently dropping an
  activity, the risk analysis, the red marking, or the 24h history scores 0
  on this component regardless of how good the rest is
- **suggested_answers (0.2):** each open question has a concrete suggested
  answer the human could accept in one click
- **scope_discipline (0.2):** out_of_scope is explicit and reasonable (e.g.
  no real collar hardware, no auth, no multi-café) and adds no requirement
  the kata did not ask for
```

- [ ] **Step 5: Write `rubric-architect.md`**

```markdown
# Architect rubric — cat-cafe-monitoring

Score the architecture artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

- **data_model (0.2):** telemetry reading (cat id, coordinates, breathing
  rate, timestamp) and floor-plan zones (type + coordinates) are both defined
- **activity_classification (0.2):** a stated rule or method for each of the
  six activities, combining distance-to-zone with breathing rate. Naming the
  activities without saying how each is distinguished does not count
- **risk_rule (0.2):** an explicit, numeric risk rule over breathing rate —
  not "flag anomalies". The threshold's origin is stated
- **realtime_and_history (0.2):** a transport choice for the live view (poll
  vs SSE vs WebSocket) with rationale, and a storage approach that answers a
  24h history query
- **decisions_documented (0.2):** boring, mainstream stack; each non-trivial
  choice has rationale + alternatives considered
```

- [ ] **Step 6: Write `rubric-planner.md`**

```markdown
# Planner rubric — cat-cafe-monitoring

Score the plan artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

This case exists to measure decomposition. Score the shape of the plan, not
the prose quality.

- **task_independence (0.3):** each task is implementable on its own against
  a frozen contract. A task that cannot start until another is half-finished
  scores badly
- **seam_quality (0.25):** the detection engine is separable from the UI, and
  the contract between them (the shape passed from classification to view) is
  named explicitly
- **task_sizing (0.25):** no task swallows the app ("implement the backend"),
  and none is trivial busywork. Each is sized for one harness attempt
- **ordering (0.2):** dependency-respecting order; nothing depends on a task
  scheduled after it
```

- [ ] **Step 7: Write `rubric-qa.md`**

```markdown
# QA rubric — cat-cafe-monitoring

Score the QAReport artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

The system under test is randomized and real-time, which is what makes its
test strategy worth scoring.

- **determinism (0.35):** telemetry is seeded or injected so tests are
  repeatable. A test that asserts over unseeded random data is a defect, and
  identifying one is worth full marks on this component
- **classification_coverage (0.3):** boundary cases per activity class — a
  cat just inside vs just outside a zone radius, breathing rate either side
  of the risk threshold
- **risk_path (0.2):** the risk flag and its red-marking are asserted, not
  assumed
- **history_window (0.15):** the 24h boundary is tested at its edges
```

- [ ] **Step 8: Write `rubric-research.md`**

```markdown
# Research rubric — cat-cafe-monitoring

Score the ResearchBrief artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

This kata has one fact genuinely worth grounding: what feline breathing rate
indicates a health risk. The risk analysis and the red marking both depend on
it, and a model that invents the number will invent a plausible wrong one.

- **threshold_grounded (0.4):** a resting respiratory rate range and a
  danger threshold for cats, each supported by a cited source. An
  unsourced number scores 0 on this component
- **citations_support_claims (0.3):** each finding's citation actually
  supports the claim made. A citation that is real but does not support its
  claim is worse than none
- **budget_focus (0.3):** search budget went to decisions that needed
  grounding. Searches spent on things the model already knows (how to
  compute distance, SSE vs WebSocket) score badly — a brief that researched
  only the vital-sign threshold and stopped scores full marks
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python -m pytest tests/test_golden_case_loads.py -v`
Expected: PASS — the four new tests plus the three pre-existing ones.

- [ ] **Step 10: Verify the rubrics actually load through the activity**

Run:
```bash
python -c "import asyncio, yaml; from pathlib import Path; from sdlc.benchmarks.judge import load_case_assets; from sdlc.benchmarks.cli import load_case_spec; s = load_case_spec('benchmarks/cases/cat-cafe-monitoring/case.yaml'); print(sorted(asyncio.run(load_case_assets(s.case_id, dict(s.rubrics)))))"
```
Expected output: `['architect', 'clarifier', 'planner', 'qa', 'research']`

A missing key here means `load_case_assets` silently skipped a file — the
rubric would never reach the judge.

- [ ] **Step 11: Commit**

```bash
git add benchmarks/cases/cat-cafe-monitoring tests/test_golden_case_loads.py
git commit -m "feat(benchmarks): cat-cafe-monitoring golden case + five rubrics (E-27)"
```

---

### Task 5: Full-suite verification and the smoke run

**Files:**
- Modify: `ROADMAP.md` (the E-27 entry)

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS with no regressions. Record the count.

- [ ] **Step 2: Confirm no key is needed for tests**

Run: `python -c "import os; assert not os.environ.get('TAVILY_API_KEY'); import sdlc.agents.roles; print('registry OK without key')"`
Expected: `registry OK without key`

This pins the Finding-6 property — the registry keeps `provider: fake`, so
CI and contributors need no Tavily key. A failure here means someone
committed `provider: tavily`.

- [ ] **Step 3: Start the worker and confirm boot**

In one terminal: `temporal server start-dev`
In another: `python -m sdlc.worker`
Expected: the worker boots. `.env` supplies `TAVILY_API_KEY` via python-dotenv.

- [ ] **Step 4: Smoke-run the case**

Run: `python -m sdlc.cli benchmark run --case benchmarks/cases/cat-cafe-monitoring/case.yaml`

**Treat this as a smoke run, not a verification.** Per the spec's Risk
section, `feature.py:717` is fail-closed: if `verify_brief_activity` returns
violations the workflow returns `rejected:research.grounding` **before**
clarify, architect, plan or any code task. That is the grounding verifier,
not the case — inspect the brief's violations before touching the rubrics or
the description.

Expected on success: a report path, and records for stages `research`,
`clarify`, `architecture`, `plan`, `code` and `qa`.

- [ ] **Step 5: Confirm the new rubrics actually scored**

Run: `python -m sdlc.cli benchmark report --bench <bench_run_id from Step 4>`
Expected: rows for `research` and `qa` with a non-null quality score and
`judge="llm_judge"`. A `judge="error"` row means the judge call failed — the
benchmark deliberately does not fail on it, so it will not announce itself.

- [ ] **Step 6: Mark E-27 done in ROADMAP.md**

Change the `- [ ] **E-27**` entry to `- [x] **E-27**` and append a sentence
recording what the smoke run showed.

- [ ] **Step 7: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): E-27 cat café case + qa/research judging landed"
```

---

## Notes for the implementer

- **Why the qa record is additive, not a replacement.** `t_qa.run()` already
  drives the `stage="code"` record's deterministic score (`judge="contract"`,
  1.0 iff tests passed and no issues). Replacing that with an LLM opinion
  trades a deterministic signal for a soft one. Task 3 adds a record; it must
  not modify the existing one.
- **Why `provider` is injected rather than committed.** See the spec's
  Finding 6. Three independent facts force it, the sharpest being that
  `loader.py:221` fails registry validation at boot without a key.
- **If the smoke run aborts at `rejected:research.grounding`,** that is
  expected-possible, not a bug in this work. The grounding verifier is
  fail-closed by design.
