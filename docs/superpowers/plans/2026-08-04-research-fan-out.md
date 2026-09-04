# Research Fan-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the research stage's single agent run with a workflow-owned `plan → N parallel sub-question activities → synthesize` fan-out, plus a bounded refine round.

**Architecture:** Three new Temporal activities in `src/sdlc/research/stage.py` orchestrated from `FeatureWorkflow`. Each sub-question runs the plain (non-Temporal) `research_agent` in-process inside its own activity, with its own budget scope and heartbeat. Merging is split: deterministic Python assembles the structured lists, one model call writes `summary` / `contradictions` / `confidence`. Everything downstream — `verify_brief_activity`, `brief_digest`, `verified_findings_to_retain` — is unchanged and runs over the merged brief.

**Tech Stack:** Python 3.14, Temporal (`temporalio`), Pydantic AI, Pydantic v2, pytest + pytest-asyncio, `uv` for running.

**Spec:** `docs/superpowers/specs/2026-08-04-research-fan-out-design.md`

## Global Constraints

- `research_enabled` stays `False` by default. No existing run's behavior may change until the flag is on.
- Research degrades a run; it **never** stops the pipeline. The only exception is grounding violations, which fail the stage closed (`brief_digest_val = ""`, skip retain) while the pipeline continues.
- Synthesis **may not author `grounded_findings`**. It assembles them only.
- `ResearchBrief` field order is reasoning order (SGR) and is pinned by `tests/test_research_models.py`. A reorder is a regression.
- No test may require network, a live model, or `EXA_API_KEY` / `TAVILY_API_KEY`. Use `provider="fake"` and `TestModel`.
- Workflow code performs no I/O, no subprocesses, no `os.environ` reads, no path computation. `tests/test_factory_purity.py` enforces this.
- Test commands run as `uv run pytest ...` from the repo root. Default `addopts` excludes `slow` and `temporal` markers.
- Budget caps in `ResearchConfig` are **per sub-question** after Task 3; `max_run_cost_usd` is the run ceiling.

**Deviation from the spec worth knowing:** spec §6 names a separate `replan_research` activity. This plan implements planning and replanning as **one** `plan_research` activity taking an optional refine seed (`guidance`, `gaps`, `contradictions`, `id_offset`). Same behavior, one activity to register and test.

---

## File Structure

**Create:**
- `src/sdlc/research/merge.py` — pure deterministic merge of partial briefs. No I/O, no model.
- `src/sdlc/research/stage.py` — the three activities and their input models.
- `src/sdlc/research/prompts.py` — the cacheable sub-question prefix and the synthesis prompt.
- `tests/test_research_page_write.py`
- `tests/test_research_budget_scope.py`
- `tests/test_research_stage_types.py`
- `tests/test_research_merge.py`
- `tests/test_research_plan_activity.py`
- `tests/test_research_subquestion_activity.py`
- `tests/test_research_synthesize_activity.py`
- `tests/test_research_prompt_cacheable.py`
- `tests/test_research_fanout_wiring.py`
- `tests/test_research_refine_round.py`

**Modify:**
- `src/sdlc/research/verify.py` — add `write_page()`
- `agents/research/exa_wrapper.py:36-44` — use `write_page()`
- `src/sdlc/research/budget_store.py` — add `scope` parameter
- `src/sdlc/models.py` — `ResearchConfig` fields; new `SubQuestionFinding`, `ResearchPlan`
- `src/sdlc/workflows/feature.py:1314-1405` — replace the research stage block
- `src/sdlc/worker.py:77-100` — register three activities

---

### Task 1: Atomic page writes

Two sub-questions fetching the same URL write the same path concurrently. Content is identical, so intent is benign — but `verify_brief` reading a half-written file yields a spurious `quote_not_found`, which fails the stage closed. Fan-out turns this from theoretical to routine.

**Files:**
- Modify: `src/sdlc/research/verify.py` (add after `pages_dir`, ~line 62)
- Modify: `agents/research/exa_wrapper.py:36-44`
- Test: `tests/test_research_page_write.py`

**Interfaces:**
- Consumes: `pages_dir(run_id)`, `page_filename(url)` — both already in `verify.py`
- Produces: `sdlc.research.verify.write_page(run_id: str, url: str, text: str) -> Path` — returns the final path

- [ ] **Step 1: Write the failing test**

```python
"""Page files are written atomically. A reader must see either the complete
previous content or the complete new content, never a partial write --
verify_brief reads these files and a truncated read is a spurious
quote_not_found that fails the research stage closed."""

import asyncio

import pytest

from sdlc.research.verify import page_filename, pages_dir, write_page


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def test_write_page_creates_the_file_with_content():
    path = write_page("r1", "https://example.com/a", "hello world")
    assert path == pages_dir("r1") / page_filename("https://example.com/a")
    assert path.read_text(encoding="utf-8") == "hello world"


def test_write_page_creates_parent_directories():
    write_page("r-nested", "https://example.com/a", "x")
    assert pages_dir("r-nested").is_dir()


def test_write_page_leaves_no_temp_files_behind():
    write_page("r1", "https://example.com/a", "x")
    assert [p.name for p in pages_dir("r1").iterdir()] == [page_filename("https://example.com/a")]


def test_write_page_overwrites_atomically_never_exposing_a_partial_read():
    # 200 concurrent writers of DIFFERENT-length content to one path. A
    # non-atomic write_text() truncates then writes, so a reader interleaved
    # between those two syscalls sees "" or a prefix. Every observed read must
    # be one of the two complete values.
    url = "https://example.com/a"
    short, long = "a" * 10, "b" * 100_000
    path = pages_dir("r1") / page_filename(url)
    write_page("r1", url, short)
    observed = set()

    async def writer(text: str) -> None:
        for _ in range(100):
            write_page("r1", url, text)
            await asyncio.sleep(0)

    async def reader() -> None:
        for _ in range(400):
            observed.add(path.read_text(encoding="utf-8"))
            await asyncio.sleep(0)

    async def main() -> None:
        await asyncio.gather(writer(short), writer(long), reader())

    asyncio.run(main())
    assert observed <= {short, long}, "a partial write was observed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_page_write.py -v`
Expected: FAIL with `ImportError: cannot import name 'write_page' from 'sdlc.research.verify'`

- [ ] **Step 3: Implement `write_page`**

Add to `src/sdlc/research/verify.py`, directly after `pages_dir`:

```python
def write_page(run_id: str, url: str, text: str) -> Path:
    """Write a fetched page atomically and return its path.

    os.replace() is atomic on POSIX and Windows alike, so a concurrent reader
    sees either the complete old file or the complete new one. Plain
    write_text() truncates first, and a reader interleaved between truncate
    and write gets a partial file -- which verify_brief reports as
    quote_not_found, failing the stage closed for no reason. Fan-out makes
    two sub-questions fetching the same URL an ordinary event, so this is
    load-bearing rather than defensive.

    The temp file carries the PID and a counter so two processes writing the
    same URL cannot collide on the temp path itself.
    """
    d = pages_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    final = d / page_filename(url)
    tmp = final.with_suffix(f".{os.getpid()}.{next(_TMP_COUNTER)}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return final
```

Add near the top of the file, after the existing imports:

```python
import itertools

_TMP_COUNTER = itertools.count()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_page_write.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Route the Exa wrapper through it**

In `agents/research/exa_wrapper.py`, change the import on line 8:

```python
from sdlc.research.verify import write_page
```

and replace the write block (lines 39-44) with:

```python
                try:
                    write_page(ctx.deps.run_id, url, content)
                except Exception as e:
                    logger.error(f"Failed to write intercept for {url}: {e}")
```

- [ ] **Step 6: Run the existing research suite for regressions**

Run: `uv run pytest tests/test_research_verify.py tests/test_research_grounding.py tests/test_research_tools.py -v`
Expected: PASS, no failures

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/research/verify.py agents/research/exa_wrapper.py tests/test_research_page_write.py
git commit -m "fix(research): atomic page writes so concurrent fetches cannot cause spurious grounding violations"
```

---

### Task 2: Scoped budget store

Per-sub-question budgets need their own on-disk counters, while the run ceiling needs a shared one. One parameter does both.

**Files:**
- Modify: `src/sdlc/research/budget_store.py`
- Test: `tests/test_research_budget_scope.py`

**Interfaces:**
- Consumes: `sdlc.research.deps.{Budget, ResearchDeps, charge, BudgetExceeded}`
- Produces:
  - `budget_path(run_id: str, scope: str = "run") -> Path` → `runs/<run_id>/research/budget-<scope>.json`
  - `charge_persisted(deps, *, search: int = 0, fetch: int = 0, scope: str = "run") -> None`
  - `charge_scoped(deps, *, search=0, fetch=0, scope: str, run_max_cost_usd: float) -> None` — charges the `scope` counter against `deps`' caps AND the `run` counter against `run_max_cost_usd`

- [ ] **Step 1: Write the failing test**

```python
"""Scoped budgets: each sub-question gets its own counter so one cannot drain
the run, while a shared 'run' counter still caps the total."""

import json

import pytest

from sdlc.research.budget_store import budget_path, charge_persisted, charge_scoped
from sdlc.research.deps import BudgetExceeded, ResearchDeps


def _deps(run_id: str = "r1", max_fetches: int = 2) -> ResearchDeps:
    return ResearchDeps(
        run_id=run_id, provider="fake", max_searches=2, max_fetches=max_fetches, max_cost_usd=1.0
    )


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def test_default_scope_is_run_and_keeps_the_legacy_filename_shape():
    assert budget_path("r1").name == "budget-run.json"
    assert budget_path("r1", "sq-3").name == "budget-sq-3.json"


@pytest.mark.asyncio
async def test_separate_scopes_do_not_share_a_counter():
    await charge_persisted(_deps(), fetch=2, scope="sq-1")
    # sq-1 is now at its cap; sq-2 is untouched and must still succeed.
    await charge_persisted(_deps(), fetch=2, scope="sq-2")
    assert json.loads(budget_path("r1", "sq-1").read_text())["fetches"] == 2
    assert json.loads(budget_path("r1", "sq-2").read_text())["fetches"] == 2


@pytest.mark.asyncio
async def test_a_scope_still_enforces_its_own_cap():
    await charge_persisted(_deps(), fetch=2, scope="sq-1")
    with pytest.raises(BudgetExceeded):
        await charge_persisted(_deps(), fetch=1, scope="sq-1")


@pytest.mark.asyncio
async def test_charge_scoped_also_charges_the_run_counter():
    await charge_scoped(_deps(), fetch=1, scope="sq-1", run_max_cost_usd=4.0)
    assert json.loads(budget_path("r1", "sq-1").read_text())["fetches"] == 1
    assert json.loads(budget_path("r1", "run").read_text())["fetches"] == 1


@pytest.mark.asyncio
async def test_charge_scoped_trips_on_the_run_ceiling_even_when_the_scope_is_fine():
    # FETCH_COST_USD is 0.02, so 4 fetches = $0.08. A run ceiling of $0.05
    # trips on the third even though each sub-question scope allows more.
    for i in range(2):
        await charge_scoped(_deps(max_fetches=10), fetch=1, scope=f"sq-{i}", run_max_cost_usd=0.05)
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=10), fetch=1, scope="sq-2", run_max_cost_usd=0.05)


@pytest.mark.asyncio
async def test_charge_scoped_does_not_charge_the_scope_when_the_run_ceiling_trips():
    # The run check runs FIRST. A sub-question must not be billed for work
    # the run ceiling refused.
    await charge_scoped(_deps(max_fetches=10), fetch=1, scope="sq-0", run_max_cost_usd=0.03)
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=10), fetch=1, scope="sq-1", run_max_cost_usd=0.03)
    assert not budget_path("r1", "sq-1").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_budget_scope.py -v`
Expected: FAIL with `ImportError: cannot import name 'charge_scoped'`

- [ ] **Step 3: Implement the scope parameter**

In `src/sdlc/research/budget_store.py`, replace `budget_path` and `charge_persisted`, and add `charge_scoped`:

```python
def budget_path(run_id: str, scope: str = "run") -> Path:
    """runs/<run_id>/research/budget-<scope>.json. Root from $SDLC_RUNS_ROOT
    (default 'runs'), mirroring verify.py's pages_dir.

    `scope` separates counters: "run" is the whole-run ceiling, "sq-<id>" is
    one sub-question's own allowance. Without separate counters a greedy
    early sub-question drains the pool and later ones get nothing -- the
    depth problem fan-out exists to fix.
    """
    root = Path(os.environ.get("SDLC_RUNS_ROOT", "runs"))
    return root / run_id / "research" / f"budget-{scope}.json"


async def charge_persisted(
    deps: ResearchDeps, *, search: int = 0, fetch: int = 0, scope: str = "run"
) -> None:
    """Same contract as deps.charge(): enforces the bound BEFORE accounting
    for it, raising BudgetExceeded (and leaving the on-disk count untouched)
    if `search`/`fetch` would cross deps.max_searches/max_fetches/max_cost_usd
    for `scope`. Reads and writes that scope's file under a lock so the cap
    holds across separate activities, each of which sees its own fresh
    (zeroed) `deps.budget`."""
    path = budget_path(deps.run_id, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    await _acquire_lock(lock_path)
    try:
        if path.exists():
            budget = Budget.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            budget = Budget()
        scratch = deps.model_copy(update={"budget": budget})
        charge(scratch, search=search, fetch=fetch)
        path.write_text(scratch.budget.model_dump_json(), encoding="utf-8")
    finally:
        lock_path.unlink(missing_ok=True)


async def charge_scoped(
    deps: ResearchDeps, *, search: int = 0, fetch: int = 0, scope: str, run_max_cost_usd: float
) -> None:
    """Charge BOTH the sub-question scope and the shared run ceiling.

    The run counter is charged FIRST, so a sub-question is never billed for
    work the run ceiling refused. The run counter only enforces cost
    (search/fetch counts are per-sub-question concerns), so it is charged
    against a deps copy whose count caps are effectively unbounded.
    """
    run_deps = deps.model_copy(
        update={
            "max_cost_usd": run_max_cost_usd,
            "max_searches": 10**9,
            "max_fetches": 10**9,
        }
    )
    await charge_persisted(run_deps, search=search, fetch=fetch, scope="run")
    await charge_persisted(deps, search=search, fetch=fetch, scope=scope)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_budget_scope.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Confirm the existing budget-store suite still passes**

The old tests call `budget_path("r1")` and `charge_persisted(deps, fetch=1)` with no scope. Both default to `"run"`, so behavior is unchanged apart from the filename.

Run: `uv run pytest tests/test_research_budget_store.py -v`
Expected: PASS. If a test asserts the literal filename `budget.json`, update that assertion to `budget-run.json` — the rename is intended.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/research/budget_store.py tests/test_research_budget_scope.py tests/test_research_budget_store.py
git commit -m "feat(research): scoped budget counters for per-sub-question allowances"
```

---

### Task 3: ResearchConfig fields

**Files:**
- Modify: `src/sdlc/models.py:694-708`
- Test: `tests/test_research_stage_types.py`

**Interfaces:**
- Produces: `ResearchConfig.max_sub_questions: int = 4`, `.max_run_cost_usd: float = 4.0`, `.max_refine_rounds: int = 1`. Existing `max_searches` / `max_fetches` / `max_cost_usd` keep their values but are now **per sub-question**.

- [ ] **Step 1: Write the failing test**

```python
"""ResearchConfig gains fan-out bounds. The existing per-run caps are
REINTERPRETED as per-sub-question; max_run_cost_usd is the new run ceiling."""

from sdlc.models import ResearchConfig


def test_fan_out_defaults():
    cfg = ResearchConfig()
    assert cfg.max_sub_questions == 4
    assert cfg.max_run_cost_usd == 4.0
    assert cfg.max_refine_rounds == 1


def test_per_sub_question_caps_keep_their_values():
    # The NUMBERS are unchanged; only their meaning moved from per-run to
    # per-sub-question. Guards against a well-meaning "fix" that divides them.
    cfg = ResearchConfig()
    assert cfg.max_searches == 5
    assert cfg.max_fetches == 10
    assert cfg.max_cost_usd == 1.0
    assert cfg.max_requests == 40


def test_run_ceiling_covers_the_default_fan_out_width():
    cfg = ResearchConfig()
    assert cfg.max_run_cost_usd >= cfg.max_sub_questions * cfg.max_cost_usd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_stage_types.py -v`
Expected: FAIL with `AttributeError: 'ResearchConfig' object has no attribute 'max_sub_questions'`

- [ ] **Step 3: Add the fields**

Replace `ResearchConfig` in `src/sdlc/models.py` (starting line 694):

```python
class ResearchConfig(BaseModel):
    """Research bounds (spec §3). Enforced INSIDE the tool functions, not the
    prompt. Exceeding one raises an ordinary error and the shortfall lands in
    the brief's `gaps`.

    SCOPE CHANGE (2026-08-04 fan-out design): max_searches/max_fetches/
    max_cost_usd/max_requests are PER SUB-QUESTION, not per run. Dividing a
    5-search pool across 4 sub-questions gives 1 search each -- shallower than
    the single-agent stage it replaces, which defeats the point. The run-level
    bound is max_run_cost_usd, enforced on the shared "run" budget scope.
    """

    max_sub_questions: int = 4
    """Fan-out width. A HARD SLICE applied to the planner's output, never a
    request the model is trusted to honour: measured behaviour is that a
    planner always returns the top of whatever range it is given, even for a
    yes/no lookup. Also the practical concurrency bound, since each
    sub-question runs an agent with its own CodeMode sandbox."""

    max_searches: int = 5  # per sub-question
    max_fetches: int = 10  # per sub-question
    max_cost_usd: float = 1.0  # per sub-question

    max_run_cost_usd: float = 4.0
    """Hard whole-run ceiling across every sub-question and every refine
    round, on the shared "run" budget scope. Deliberately equal to
    max_sub_questions * max_cost_usd: a refine round draws down what round
    one left unspent rather than being granted a fresh allowance."""

    max_refine_rounds: int = 1
    """Rounds of gate-driven refinement after the first brief. A refine
    triggers a whole second fan-out, so this is a spend ceiling as much as a
    complexity ceiling. Exhausting it proceeds with the current brief -- it
    is never a rejection."""

    max_requests: int = 40
    """Cap passed as pydantic-ai's UsageLimits(request_limit=...) around ONE
    sub-question's agent run. Independent of the tool-call bounds above:
    those cap web_search/get_page/deep_search calls; this caps total model
    requests (every turn, retry, and structured-output validation pass),
    staying under pydantic-ai's own default of 50 so an exhaustion is ours to
    catch and degrade, not an uncaught crash."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_stage_types.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py tests/test_research_stage_types.py
git commit -m "feat(research): per-sub-question budget scope and fan-out width config"
```

---

### Task 4: Transport types

Fan-out moves the model call activity-side, so `_run_role` can no longer wrap it. The rule that replaces it: **if an activity calls a model, its return type must carry usage.**

**Files:**
- Modify: `src/sdlc/models.py` (add after `ResearchBrief`, ~line 507)
- Test: `tests/test_research_stage_types.py` (append)

**Interfaces:**
- Consumes: `SubQuestion`, `ResearchBrief`, `RoleUsage` — all already in `models.py`
- Produces:
  - `ResearchPlan(sub_questions: list[SubQuestion], usage: RoleUsage)`
  - `SubQuestionFinding(sub_question: SubQuestion, brief: ResearchBrief, usage: RoleUsage, failed: bool = False, error: str = "")`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_research_stage_types.py`:

```python
from sdlc.models import ResearchBrief, ResearchPlan, RoleUsage, SubQuestion, SubQuestionFinding


def test_research_plan_carries_usage():
    # Returning a bare list of sub-questions silently drops one model call per
    # run -- the exact bug this type exists to prevent.
    plan = ResearchPlan()
    assert isinstance(plan.usage, RoleUsage)
    assert plan.sub_questions == []


def test_sub_question_finding_carries_usage_and_a_brief():
    f = SubQuestionFinding(
        sub_question=SubQuestion(id="sq-0", question="what?"), brief=ResearchBrief(summary="s")
    )
    assert isinstance(f.usage, RoleUsage)
    assert f.failed is False
    assert f.error == ""


def test_sub_question_finding_can_represent_a_permanent_failure():
    f = SubQuestionFinding(
        sub_question=SubQuestion(id="sq-1", question="what?"),
        brief=ResearchBrief(),
        failed=True,
        error="RefusalError: declined",
    )
    assert f.failed
    assert "declined" in f.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_stage_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'ResearchPlan' from 'sdlc.models'`

- [ ] **Step 3: Add the types**

Add to `src/sdlc/models.py` immediately after `ResearchBrief`:

```python
class ResearchPlan(BaseModel):
    """The planner's output, WITH its model spend.

    Carrying `usage` is why this type exists rather than a bare
    list[SubQuestion]: fan-out moves the model call activity-side, out of
    _run_role's reach, so an activity that calls a model must hand its usage
    back or the spend is silently lost (E-33 amendment, fan-out design §7)."""

    sub_questions: list[SubQuestion] = Field(default_factory=list)
    usage: RoleUsage = Field(default_factory=lambda: RoleUsage(role="research", model="unknown"))


class SubQuestionFinding(BaseModel):
    """One sub-question's result: its own partial ResearchBrief plus spend.

    `failed=True` means the sub-question exhausted its retries or hit a
    non-retryable error. Its siblings survive -- a partial answer from three
    of four sub-questions is worth far more than nothing -- and the merge
    turns this into a Gap so a short brief is explained rather than just
    short."""

    sub_question: SubQuestion
    brief: ResearchBrief = Field(default_factory=ResearchBrief)
    usage: RoleUsage = Field(default_factory=lambda: RoleUsage(role="research", model="unknown"))
    failed: bool = False
    error: str = ""
```

`RoleUsage` is defined at line 784, *after* `ResearchBrief`. Move the `RoleUsage` class definition to just above `SubQuestion` (line ~447) so both new types can reference it. Pydantic resolves annotations at class creation, so a forward reference would need a `model_rebuild()` call — moving the definition is simpler and has no other effect.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_stage_types.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Verify the RoleUsage move broke nothing**

Run: `uv run pytest tests/test_research_models.py tests/test_per_role_cost.py -v`
Expected: PASS. If `tests/test_per_role_cost.py` does not exist, run `uv run pytest -k "role_usage or cost_attribution" -v` instead.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_research_stage_types.py
git commit -m "feat(research): ResearchPlan and SubQuestionFinding transport types carrying usage"
```

---

### Task 5: Deterministic merge

The structured lists merge in pure Python. The model never touches them. This is the task where `brief_digest` stability is won or lost.

**Files:**
- Create: `src/sdlc/research/merge.py`
- Test: `tests/test_research_merge.py`

**Interfaces:**
- Consumes: `SubQuestionFinding`, `ResearchBrief`, `SubQuestion`, `Gap`, `ConsultedSource`, `GroundedFinding`, `InferredFinding`, `Contradiction` from `sdlc.models`
- Produces: `sdlc.research.merge.merge_briefs(findings: list[SubQuestionFinding]) -> ResearchBrief` — fills every field EXCEPT `summary`, `confidence`, and cross-cutting `contradictions`, which synthesis writes (Task 8)

- [ ] **Step 1: Write the failing test**

```python
"""Deterministic merge of partial briefs. Pure -- no model, no I/O.

The dedupe rule is load-bearing in BOTH directions: corroboration (same claim,
different sources) is the most valuable thing fan-out produces and must
survive; exact duplicate triples must NOT, because brief_digest hashes
(source_url, claim) pairs as a LIST, so a duplicate changes the digest and
silently degrades clarify's memo hit rate."""

from sdlc.models import (
    ConsultedSource,
    Contradiction,
    GroundedFinding,
    InferredFinding,
    ResearchBrief,
    SubQuestion,
    SubQuestionFinding,
)
from sdlc.research.merge import merge_briefs
from sdlc.research.verify import brief_digest


def _finding(sq_id: str, brief: ResearchBrief, **kw) -> SubQuestionFinding:
    return SubQuestionFinding(
        sub_question=SubQuestion(id=sq_id, question=f"q for {sq_id}"), brief=brief, **kw
    )


def test_merge_of_nothing_is_an_empty_brief():
    assert merge_briefs([]) == ResearchBrief()


def test_sub_questions_are_unioned_in_order():
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief()),
            _finding("sq-1", ResearchBrief()),
        ]
    )
    assert [s.id for s in merged.sub_questions] == ["sq-0", "sq-1"]


def test_corroboration_is_preserved_same_claim_different_sources():
    a = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://a.example", quote="q1", claim="X is true")
        ]
    )
    b = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://b.example", quote="q2", claim="X is true")
        ]
    )
    merged = merge_briefs([_finding("sq-0", a), _finding("sq-1", b)])
    assert len(merged.grounded_findings) == 2, "corroboration was collapsed"


def test_exact_duplicate_triples_are_deduped():
    g = GroundedFinding(source_url="https://a.example", quote="q", claim="X")
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(grounded_findings=[g])),
            _finding("sq-1", ResearchBrief(grounded_findings=[g.model_copy()])),
        ]
    )
    assert len(merged.grounded_findings) == 1


def test_digest_is_stable_when_two_sub_questions_report_the_same_triple():
    g = GroundedFinding(source_url="https://a.example", quote="q", claim="X")
    one = merge_briefs([_finding("sq-0", ResearchBrief(grounded_findings=[g]))])
    two = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(grounded_findings=[g])),
            _finding("sq-1", ResearchBrief(grounded_findings=[g.model_copy()])),
        ]
    )
    assert brief_digest(one) == brief_digest(two)


def test_sources_are_deduped_by_url_first_seen_wins():
    a = ResearchBrief(
        sources_consulted=[ConsultedSource(url="https://a.example", title="A", relevance="high")]
    )
    b = ResearchBrief(
        sources_consulted=[
            ConsultedSource(url="https://a.example", title="A again", relevance="peripheral")
        ]
    )
    merged = merge_briefs([_finding("sq-0", a), _finding("sq-1", b)])
    assert len(merged.sources_consulted) == 1
    assert merged.sources_consulted[0].relevance == "high"


def test_inferred_findings_and_gaps_concatenate():
    a = ResearchBrief(inferred_findings=[InferredFinding(reasoning="r1", claim="c1")])
    b = ResearchBrief(inferred_findings=[InferredFinding(reasoning="r2", claim="c2")])
    merged = merge_briefs([_finding("sq-0", a), _finding("sq-1", b)])
    assert len(merged.inferred_findings) == 2


def test_within_sub_question_contradictions_carry_through():
    a = ResearchBrief(
        contradictions=[Contradiction(topic="t", positions=["p1", "p2"], unresolved=True)]
    )
    merged = merge_briefs([_finding("sq-0", a)])
    assert len(merged.contradictions) == 1
    assert merged.contradictions[0].topic == "t"


def test_a_failed_sub_question_becomes_a_gap():
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(), failed=True, error="RefusalError: declined"),
        ]
    )
    assert len(merged.gaps) == 1
    assert merged.gaps[0].sub_question_id == "sq-0"
    assert "declined" in merged.gaps[0].why_it_matters


def test_a_failed_sub_question_does_not_stop_its_siblings():
    ok = ResearchBrief(
        grounded_findings=[GroundedFinding(source_url="https://a.example", quote="q", claim="X")]
    )
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(), failed=True, error="boom"),
            _finding("sq-1", ok),
        ]
    )
    assert len(merged.grounded_findings) == 1
    assert len(merged.gaps) == 1


def test_merge_leaves_summary_and_confidence_for_synthesis():
    a = ResearchBrief(summary="partial summary", confidence=0.9)
    merged = merge_briefs([_finding("sq-0", a)])
    assert merged.summary == ""
    assert merged.confidence == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_merge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.research.merge'`

- [ ] **Step 3: Implement the merge**

Create `src/sdlc/research/merge.py`:

```python
"""Deterministic merge of per-sub-question briefs into one ResearchBrief.

Pure: no model, no network, no filesystem. Everything here is checkable by a
reader, which is the point -- the model's judgment is confined to summary,
confidence, and cross-cutting contradictions (research/stage.py's
synthesize_brief), and it may never author a grounded finding.
"""

from __future__ import annotations

from ..models import (
    ConsultedSource,
    Contradiction,
    Gap,
    GroundedFinding,
    InferredFinding,
    ResearchBrief,
    SubQuestion,
    SubQuestionFinding,
)


def merge_briefs(findings: list[SubQuestionFinding]) -> ResearchBrief:
    """Assemble N partial briefs. Fills every field except `summary`,
    `confidence`, and cross-cutting contradictions -- those need judgment over
    the whole and are written by the synthesis model.

    `brief_ref` is left None; the artifact is stored after synthesis."""
    sub_questions: list[SubQuestion] = []
    sources: list[ConsultedSource] = []
    seen_urls: set[str] = set()
    grounded: list[GroundedFinding] = []
    seen_triples: set[tuple[str, str, str]] = set()
    inferred: list[InferredFinding] = []
    contradictions: list[Contradiction] = []
    gaps: list[Gap] = []

    for f in findings:
        sub_questions.append(f.sub_question)

        if f.failed:
            # A permanently failed sub-question is not silence: it becomes a
            # gap so a short brief is EXPLAINED rather than merely short.
            gaps.append(
                Gap(
                    sub_question_id=f.sub_question.id,
                    what_is_missing=f.sub_question.question,
                    why_it_matters=f"this sub-question did not complete: {f.error}",
                )
            )
            continue

        for s in f.brief.sources_consulted:
            # First-seen wins. Two sub-questions rarely assess the same source
            # differently, and picking a winner by rule beats asking a model.
            if s.url not in seen_urls:
                seen_urls.add(s.url)
                sources.append(s)

        for g in f.brief.grounded_findings:
            # Dedupe ONLY exact triples. The same claim from a DIFFERENT source
            # is corroboration -- the most valuable thing fan-out produces --
            # and collapsing it would destroy the signal. Exact duplicates must
            # go, because brief_digest hashes (source_url, claim) as a list.
            key = (g.source_url, g.quote, g.claim)
            if key not in seen_triples:
                seen_triples.add(key)
                grounded.append(g)

        inferred.extend(f.brief.inferred_findings)
        contradictions.extend(f.brief.contradictions)
        gaps.extend(f.brief.gaps)

    return ResearchBrief(
        sub_questions=sub_questions,
        sources_consulted=sources,
        grounded_findings=grounded,
        inferred_findings=inferred,
        contradictions=contradictions,
        gaps=gaps,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_merge.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/research/merge.py tests/test_research_merge.py
git commit -m "feat(research): deterministic merge of per-sub-question briefs"
```

---

### Task 6: Cacheable prompts

Fan-out multiplies input cost by N. A shared cached prefix is the largest cost lever available, and it fails **silently** if the prefix is under 512 tokens — `cache_creation_input_tokens` just stays 0, with no error.

**Files:**
- Create: `src/sdlc/research/prompts.py`
- Test: `tests/test_research_prompt_cacheable.py`

**Interfaces:**
- Produces:
  - `SUB_QUESTION_PREFIX: str` — the byte-identical cached prefix
  - `sub_question_prompt(question: str) -> str` — prefix + per-question suffix
  - `SYNTHESIS_SYSTEM: str`
  - `PLAN_SYSTEM: str`

- [ ] **Step 1: Write the failing test**

```python
"""The sub-question prefix must be byte-identical across a burst and long
enough to cache. Under ~512 tokens a prefix is silently NOT cached -- no
error, the counter just stays at zero -- so this is guarded by a test rather
than a comment."""

from sdlc.research.prompts import (
    PLAN_SYSTEM,
    SUB_QUESTION_PREFIX,
    SYNTHESIS_SYSTEM,
    sub_question_prompt,
)

# ~4 chars per token is the standard rough conversion. 512 tokens is the
# documented cache floor; 2400 chars gives headroom without being precious.
MIN_CACHEABLE_CHARS = 2400


def test_prefix_is_long_enough_to_be_cacheable():
    assert len(SUB_QUESTION_PREFIX) >= MIN_CACHEABLE_CHARS, (
        "prefix is below the cache floor -- it will silently not be cached "
        "and every parallel sub-question pays full input price"
    )


def test_prefix_is_byte_identical_across_different_questions():
    a = sub_question_prompt("What is the current EU AI Act timeline?")
    b = sub_question_prompt("How many US states have privacy statutes?")
    assert a.startswith(SUB_QUESTION_PREFIX)
    assert b.startswith(SUB_QUESTION_PREFIX)


def test_the_question_lands_after_the_prefix_never_inside_it():
    q = "UNIQUE-MARKER-9f3a"
    assert q not in SUB_QUESTION_PREFIX
    assert q in sub_question_prompt(q)


def test_plan_and_synthesis_prompts_are_non_empty():
    assert len(PLAN_SYSTEM) > 200
    assert len(SYNTHESIS_SYSTEM) > 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_prompt_cacheable.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.research.prompts'`

- [ ] **Step 3: Write the prompts**

Create `src/sdlc/research/prompts.py`:

```python
"""Prompts for the fan-out stage.

SUB_QUESTION_PREFIX is BYTE-IDENTICAL across every sub-question in a burst so
the parallel calls share one cached prefix at ~0.1x input price. Fan-out
multiplies input cost by N, which makes this the largest cost lever here.

LENGTH IS FUNCTIONAL. A prefix under ~512 tokens is silently not cached --
cache_creation_input_tokens simply stays 0, with no error and no warning.
Guarded by tests/test_research_prompt_cacheable.py. Do not trim for tidiness,
and NEVER interpolate the question into the prefix.
"""

from __future__ import annotations

SUB_QUESTION_PREFIX = """\
You are a research analyst working on one narrow sub-question that forms part \
of a larger investigation. Another analyst will combine your answer with \
several others, so your job is depth on your specific sub-question rather \
than breadth across the whole topic. Do not try to answer the broader \
question you can infer around it.

Method:
- Search before you answer. Do not answer from memory, even when you are \
confident: your training data may be stale, and the entire point of this task \
is current information.
- Prefer primary sources over commentary about them. An official statistic, \
regulatory filing, dataset, standards document or first-party announcement \
beats a news article summarising it, which in turn beats an aggregator \
summarising the article.
- When a question is time-sensitive, establish how current your sources are \
and say so explicitly. A number with no date attached is not usable by the \
analyst who reads your answer.
- Cross-check any figure that matters against a second independent source. If \
the two disagree, report both, and say which you find more credible and why. \
Do not silently pick one, and do not average them into a made-up middle.
- Recency and quality are different axes. A newer source is not automatically \
better: a blog post from this week does not override an official dataset from \
last quarter. Say which you are relying on.
- Watch for low-quality content: SEO farms, sites that recycle each other's \
numbers, and generated summaries with no original reporting. Three sites \
repeating one original claim is one source, not three. Trace a figure to \
where it actually came from.
- If a source you need is paywalled or unreachable, say so rather than \
substituting a weaker source silently.
- Be specific about scope. Most real questions are implicitly bounded by \
place, time period, population or jurisdiction, and an answer for the wrong \
scope is simply wrong. State the scope you researched.
- Normalise units and currencies, and state which you used.
- If the sub-question rests on a false or outdated premise, say that directly \
and answer what the asker evidently wanted to know instead.
- If the honest answer is that the evidence is thin, contested, or does not \
exist, say that plainly. A well-evidenced "this is genuinely uncertain, and \
here is the range of published estimates" is a good answer. A confident answer \
built on one weak source is not.

Grounding:
- Every claim you put in grounded_findings MUST carry a quote that is a \
VERBATIM span from a page you fetched during this run. The quote is checked \
mechanically against the fetched bytes; a paraphrase fails and costs the whole \
stage. Commit to the quote first, then state what it supports.
- Anything you concluded rather than read belongs in inferred_findings, with \
your reasoning stated. A recalled lead is an inference, never a grounded \
finding.
- Where sources genuinely conflict, record it in contradictions rather than \
picking a winner silently.
- What you could not answer belongs in gaps. An honest gap is worth more than \
a padded finding.
"""

PLAN_SYSTEM = """\
You break a research question into independent sub-questions that can be \
investigated in parallel.

Good sub-questions are:
- Independent. Researching one must not require the answer to another, \
because they run simultaneously.
- Narrow enough that a focused search can answer them well.
- Collectively sufficient. Together they should cover what someone would need \
to answer the original question properly, including the parts the asker did \
not think to ask about.
- Non-overlapping. Two sub-questions that would return the same sources are \
one sub-question.

Prefer concrete, searchable phrasing over abstract framing. If the question is \
time-sensitive, make at least one sub-question explicitly about the current \
state or the most recent data.
"""

SYNTHESIS_SYSTEM = """\
You are combining findings that several analysts gathered in parallel into one \
coherent brief.

You are given the merged, numbered source list and each analyst's findings. \
Your job is THREE fields and nothing else:

1. `summary` — a direct answer to the original question. Write for someone who \
has not seen the individual findings and does not know they exist. Never refer \
to "the findings", "the analysts", or "sub-question 3". The seams must be \
invisible. Cite sources by their number from the list you were given, and use \
ONLY numbers that appear in it.

2. `contradictions` — where the findings genuinely disagree. Include both the \
conflicts individual analysts already reported AND conflicts BETWEEN analysts \
that only become visible now that their work sits side by side. The second \
kind is the whole reason the research ran in parallel. Give your reading of \
which position is better supported; never average conflicting numbers into a \
single confident figure.

3. `confidence` — your judgment about the brief as a whole, not an average of \
the parts.

You MUST NOT add, edit, or remove any grounded finding, inferred finding, \
source, or gap. Those are assembled mechanically and verified against fetched \
bytes; anything you invent there fails the run.
"""


def sub_question_prompt(question: str) -> str:
    """Cached prefix + the per-question suffix. The question NEVER goes inside
    the prefix -- that would make every call's prefix unique and defeat the
    cache entirely."""
    return f"{SUB_QUESTION_PREFIX}\n---\n\nYour sub-question:\n\n{question}\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_prompt_cacheable.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/research/prompts.py tests/test_research_prompt_cacheable.py
git commit -m "feat(research): cacheable sub-question prefix with a length guard"
```

---

### Task 7: `plan_research` activity

One activity handles both the first plan and refine replans. Width is a hard slice, never a request the model is trusted to honour.

**Files:**
- Create: `src/sdlc/research/stage.py`
- Modify: `src/sdlc/worker.py:77-100`
- Test: `tests/test_research_plan_activity.py`

**Interfaces:**
- Consumes: `ResearchPlan`, `SubQuestion`, `Gap`, `Contradiction`, `RoleUsage` from `sdlc.models`; `PLAN_SYSTEM` from `sdlc.research.prompts`
- Produces:
  - `PlanInput(idea_json: str, max_sub_questions: int, model: str, id_offset: int = 0, guidance: str = "", gaps: list[Gap] = [], contradictions: list[Contradiction] = [])`
  - `plan_research(inp: PlanInput) -> ResearchPlan` (Temporal activity)
  - `_plan_prompt(inp: PlanInput) -> str` (module-private, tested directly)

- [ ] **Step 1: Write the failing test**

```python
"""plan_research: decomposition becomes workflow-owned state.

The planner runs against TestModel -- no network, no live model. Width is a
HARD SLICE: measured behaviour is that planners return the top of any range
they are given, so the config value decides the width, not the question."""

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.models import Contradiction, Gap, ResearchPlan
from sdlc.research.stage import PlanInput, _plan_prompt, plan_research


def _inp(**kw) -> PlanInput:
    base = dict(idea_json='{"title": "add rate limiting"}', max_sub_questions=4, model="test-model")
    base.update(kw)
    return PlanInput(**base)


def test_plan_prompt_contains_the_idea():
    assert "rate limiting" in _plan_prompt(_inp())


def test_plan_prompt_asks_for_the_configured_width():
    assert "4" in _plan_prompt(_inp(max_sub_questions=4))


def test_plan_prompt_without_a_refine_seed_mentions_no_guidance():
    prompt = _plan_prompt(_inp())
    assert "Focus specifically on" not in prompt


def test_plan_prompt_with_a_refine_seed_carries_guidance_gaps_and_conflicts():
    prompt = _plan_prompt(
        _inp(
            guidance="dig into the enforcement timeline",
            gaps=[
                Gap(
                    sub_question_id="sq-0",
                    what_is_missing="penalty amounts",
                    why_it_matters="drives the design",
                )
            ],
            contradictions=[
                Contradiction(topic="effective date", positions=["2026", "2027"], unresolved=True)
            ],
        )
    )
    assert "Focus specifically on" in prompt
    assert "enforcement timeline" in prompt
    assert "penalty amounts" in prompt
    assert "effective date" in prompt


@pytest.mark.asyncio
async def test_plan_research_returns_sub_questions_with_stable_ids():
    plan = await plan_research(
        _inp(), _model=TestModel(custom_output_args={"sub_questions": ["a?", "b?", "c?"]})
    )
    assert isinstance(plan, ResearchPlan)
    assert [s.id for s in plan.sub_questions] == ["sq-0", "sq-1", "sq-2"]
    assert [s.question for s in plan.sub_questions] == ["a?", "b?", "c?"]


@pytest.mark.asyncio
async def test_plan_research_slices_to_max_sub_questions():
    # The planner over-returns. The SLICE is what bounds the fan-out, not the
    # prompt -- trusting the model here is how a 4-wide stage becomes 9-wide.
    plan = await plan_research(
        _inp(max_sub_questions=2),
        _model=TestModel(custom_output_args={"sub_questions": ["a?", "b?", "c?", "d?", "e?"]}),
    )
    assert len(plan.sub_questions) == 2


@pytest.mark.asyncio
async def test_plan_research_applies_the_id_offset_for_refine_rounds():
    # Round-2 ids must never collide with round-1 ids, or findings from the
    # two rounds overwrite each other in the merge.
    plan = await plan_research(
        _inp(id_offset=4), _model=TestModel(custom_output_args={"sub_questions": ["a?", "b?"]})
    )
    assert [s.id for s in plan.sub_questions] == ["sq-4", "sq-5"]


@pytest.mark.asyncio
async def test_plan_research_drops_blank_sub_questions():
    plan = await plan_research(
        _inp(), _model=TestModel(custom_output_args={"sub_questions": ["a?", "   ", "", "b?"]})
    )
    assert [s.question for s in plan.sub_questions] == ["a?", "b?"]


@pytest.mark.asyncio
async def test_plan_research_falls_back_to_the_whole_idea_when_empty():
    # A planner that returns nothing must degrade to today's behaviour -- one
    # sub-question covering the whole idea -- never to an empty fan-out.
    plan = await plan_research(_inp(), _model=TestModel(custom_output_args={"sub_questions": []}))
    assert len(plan.sub_questions) == 1
    assert plan.sub_questions[0].id == "sq-0"


@pytest.mark.asyncio
async def test_plan_research_carries_usage():
    plan = await plan_research(
        _inp(), _model=TestModel(custom_output_args={"sub_questions": ["a?"]})
    )
    assert plan.usage.role == "research"
    assert plan.usage.calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_plan_activity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.research.stage'`

- [ ] **Step 3: Implement the activity**

Create `src/sdlc/research/stage.py`:

```python
"""The research fan-out activities: plan -> N sub-questions -> synthesize.

Every model call in the research stage happens HERE, activity-side, which is
why each return type carries a RoleUsage: fan-out moves the call out of
_run_role's reach, and an activity that calls a model must hand its usage back
or the spend is silently lost (E-33 amendment, fan-out design §7).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from temporalio import activity

from ..models import Contradiction, Gap, ResearchPlan, RoleUsage, SubQuestion
from .prompts import PLAN_SYSTEM


class _PlannerOutput(BaseModel):
    """Structured-output shape for the planner. A flat list of strings: ids
    are assigned by us, not the model, so they stay stable and offsettable."""

    sub_questions: list[str] = Field(default_factory=list)


class PlanInput(BaseModel):
    """Serves BOTH the first plan and a refine replan. A replan is just a plan
    with a seed: the human's guidance plus the machine-readable gaps and
    contradictions round one could not resolve."""

    idea_json: str
    max_sub_questions: int
    model: str
    id_offset: int = 0
    guidance: str = ""
    gaps: list[Gap] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)


def _usage_of(result, model: str) -> RoleUsage:
    """One pydantic-ai run's usage as a RoleUsage. cost_usd stays None: dollars
    are a lookup the WORKFLOW performs via the price_usage activity, because
    pricing must stay replay-safe and must never fail a stage."""
    u = result.usage()
    return RoleUsage(
        role="research",
        model=model,
        calls=1,
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=u.cache_read_tokens or 0,
        cache_write_tokens=u.cache_write_tokens or 0,
        cost_usd=None,
    )


def _plan_prompt(inp: PlanInput) -> str:
    parts = [
        f"Research question / feature idea:\n\n{inp.idea_json}\n",
        f"\nBreak this into at most {inp.max_sub_questions} independent "
        "sub-questions that can be investigated in parallel.\n",
    ]
    if inp.guidance:
        parts.append(f"\nFocus specifically on: {inp.guidance}\n")
    if inp.gaps:
        parts.append("\nA previous round left these questions unanswered — target them:\n")
        parts.extend(f"- {g.what_is_missing} ({g.why_it_matters})\n" for g in inp.gaps)
    if inp.contradictions:
        parts.append("\nA previous round found these unresolved conflicts — target them:\n")
        parts.extend(
            f"- {c.topic}: {' vs '.join(c.positions)}\n" for c in inp.contradictions if c.unresolved
        )
    return "".join(parts)


@activity.defn
async def plan_research(inp: PlanInput, _model=None) -> ResearchPlan:
    """Decompose the idea into independent sub-questions.

    `_model` is a test seam only: production passes None and the activity
    builds an agent on inp.model.

    The slice to max_sub_questions is NOT a formality. Measured behaviour is
    that planners return the top of whatever range they are given, even for a
    yes/no lookup -- so the config value, not the question, decides the width.
    """
    agent = Agent(_model or inp.model, output_type=_PlannerOutput, system_prompt=PLAN_SYSTEM)
    result = await agent.run(_plan_prompt(inp))
    texts = [t.strip() for t in result.output.sub_questions if t and t.strip()]
    texts = texts[: inp.max_sub_questions]

    if not texts:
        # Degrade to exactly today's behaviour: one investigation covering the
        # whole idea. A fan-out failure is never worse than the status quo.
        texts = [inp.idea_json]

    activity.logger.info("planned %d sub-questions", len(texts))
    return ResearchPlan(
        sub_questions=[
            SubQuestion(id=f"sq-{inp.id_offset + i}", question=t) for i, t in enumerate(texts)
        ],
        usage=_usage_of(result, inp.model),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_plan_activity.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Register the activity on the worker**

In `src/sdlc/worker.py`, add the import near the other activity imports:

```python
from .research.stage import plan_research
```

and add `plan_research,` to the `activities=[...]` list, directly after `verify_brief_activity,`.

- [ ] **Step 6: Verify the worker still constructs**

Run: `uv run pytest tests/test_bootstrap.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/research/stage.py src/sdlc/worker.py tests/test_research_plan_activity.py
git commit -m "feat(research): plan_research activity with hard width slice and refine seed"
```

---

### Task 8: `research_subquestion` activity

The fan-out unit. Runs the plain `research_agent` in-process so `deps.budget` genuinely accumulates within the run, with `budget_store` enforcing the persisted caps underneath.

**Files:**
- Modify: `src/sdlc/research/stage.py`
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_research_subquestion_activity.py`

**Interfaces:**
- Consumes: `PlanInput`, `_usage_of` (Task 7); `SubQuestionFinding` (Task 4); `sub_question_prompt` (Task 6); `sdlc.agents.roles.research_agent`
- Produces:
  - `SubQuestionInput(sub_question: SubQuestion, deps: ResearchDeps, model: str, max_requests: int, max_run_cost_usd: float)`
  - `research_subquestion(inp: SubQuestionInput) -> SubQuestionFinding` (Temporal activity)

- [ ] **Step 1: Write the failing test**

```python
"""research_subquestion: one sub-question, one activity, one budget scope.

Budget exhaustion DEGRADES (a partial brief with the shortfall as a gap); it
never crashes the stage. The counter is persisted, so an escaping
BudgetExceeded would retry against a cap that stays exhausted -- six
guaranteed failures with backoff."""

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel

from sdlc.models import ResearchBrief, SubQuestion, SubQuestionFinding
from sdlc.research.deps import BudgetExceeded, ResearchDeps
from sdlc.research.stage import SubQuestionInput, research_subquestion


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _inp(sq_id: str = "sq-0") -> SubQuestionInput:
    return SubQuestionInput(
        sub_question=SubQuestion(id=sq_id, question="what is the timeline?"),
        deps=ResearchDeps(
            run_id="r1", provider="fake", max_searches=5, max_fetches=10, max_cost_usd=1.0
        ),
        model="test-model",
        max_requests=40,
        max_run_cost_usd=4.0,
    )


class _Boom:
    """Stands in for the research agent when we need run() to raise."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def run(self, *a, **kw):
        raise self._exc


@pytest.mark.asyncio
async def test_returns_a_finding_carrying_the_brief_and_usage():
    out = await research_subquestion(
        _inp(), _model=TestModel(custom_output_args={"summary": "the timeline is 2027"})
    )
    assert isinstance(out, SubQuestionFinding)
    assert out.sub_question.id == "sq-0"
    assert out.brief.summary == "the timeline is 2027"
    assert out.failed is False
    assert out.usage.role == "research"


@pytest.mark.asyncio
async def test_budget_exceeded_degrades_to_a_gap_not_a_raise():
    out = await research_subquestion(
        _inp(), _agent=_Boom(BudgetExceeded("search budget exhausted"))
    )
    assert out.failed is False, "budget exhaustion is a degradation, not a failure"
    assert out.brief.grounded_findings == []
    assert len(out.brief.gaps) == 1
    assert "search budget exhausted" in out.brief.gaps[0].why_it_matters


@pytest.mark.asyncio
async def test_usage_limit_exceeded_also_degrades():
    out = await research_subquestion(
        _inp(), _agent=_Boom(UsageLimitExceeded("request_limit of 40 exceeded"))
    )
    assert out.failed is False
    assert "request_limit" in out.brief.gaps[0].why_it_matters


@pytest.mark.asyncio
async def test_the_gap_is_attributed_to_this_sub_question():
    out = await research_subquestion(_inp("sq-3"), _agent=_Boom(BudgetExceeded("x")))
    assert out.brief.gaps[0].sub_question_id == "sq-3"


@pytest.mark.asyncio
async def test_a_degraded_brief_is_never_grounded():
    # verify_brief only inspects grounded_findings, so an empty list means the
    # degraded brief flows through the SAME success path as a normal brief
    # instead of tripping the grounding gate too.
    out = await research_subquestion(_inp(), _agent=_Boom(BudgetExceeded("x")))
    assert out.brief.grounded_findings == []


@pytest.mark.asyncio
async def test_an_unexpected_error_propagates_for_temporal_to_retry():
    # Budget/usage exhaustion is expected and degrades. Everything else is a
    # real failure Temporal should retry, then the workflow turns into a Gap.
    with pytest.raises(RuntimeError):
        await research_subquestion(_inp(), _agent=_Boom(RuntimeError("network")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_subquestion_activity.py -v`
Expected: FAIL with `ImportError: cannot import name 'SubQuestionInput'`

- [ ] **Step 3: Implement the activity**

Append to `src/sdlc/research/stage.py`:

```python
import asyncio
import contextlib

from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from ..models import ResearchBrief, SubQuestionFinding
from .deps import BudgetExceeded, ResearchDeps
from .prompts import sub_question_prompt

# Comfortably below the workflow's heartbeat_timeout (see feature.py's
# RESEARCH_SQ_ACT). The invariant to preserve is:
#   HEARTBEAT_INTERVAL_SECONDS < heartbeat_timeout < start_to_close
HEARTBEAT_INTERVAL_SECONDS = 15.0


class SubQuestionInput(BaseModel):
    sub_question: SubQuestion
    deps: ResearchDeps
    model: str
    max_requests: int
    max_run_cost_usd: float


@contextlib.asynccontextmanager
async def _heartbeating(interval: float | None = None):
    """Heartbeat on a TIMER for as long as the block runs.

    A sub-question legitimately runs for minutes, and the server cannot tell
    "still thinking" from "instance went away". Heartbeating on a timer
    decouples liveness from call duration, so a lost worker is detected in
    ~60s instead of at start_to_close.

    The interval resolves from the module global at CALL time, not as a
    default argument -- otherwise tests cannot shorten it, and an untestable
    heartbeat is one you discover never fired in production."""
    interval = HEARTBEAT_INTERVAL_SECONDS if interval is None else interval

    async def tick() -> None:
        while True:
            await asyncio.sleep(interval)
            activity.heartbeat()

    task = asyncio.create_task(tick())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _degraded(sub: SubQuestion, exc: Exception) -> ResearchBrief:
    """A bound was hit. Conclude with what we have and record the shortfall as
    a gap -- ResearchConfig's documented contract. Never grounded, so
    verify_brief passes it through the ordinary success path."""
    return ResearchBrief(
        gaps=[
            Gap(
                sub_question_id=sub.id,
                what_is_missing=sub.question,
                why_it_matters=f"research stopped early: {exc}",
            )
        ],
        summary=f"Research stopped early: {exc}",
    )


@activity.defn
async def research_subquestion(
    inp: SubQuestionInput, _model=None, _agent=None
) -> SubQuestionFinding:
    """Research ONE sub-question. The fan-out unit.

    Runs the PLAIN research_agent, not the TemporalAgent: inside an activity
    pydantic-ai falls back to in-process execution, so deps.budget accumulates
    for real within the run while budget_store enforces the persisted caps
    underneath (the pattern research/toolset.py already established for the
    architect's mid-run call).

    `_model` / `_agent` are test seams; production passes neither.
    """
    sub = inp.sub_question
    if _agent is None:
        from sdlc.agents.roles import research_agent

        if research_agent is None:
            raise RuntimeError("research agent is not available (agents/research/ missing)")
        agent = research_agent
    else:
        agent = _agent

    # Each sub-question charges its OWN scope so one cannot drain the run.
    deps = inp.deps.model_copy(update={"budget": inp.deps.budget.model_copy()})

    usage = RoleUsage(role="research", model=inp.model)
    try:
        async with _heartbeating():
            kwargs = dict(deps=deps, usage_limits=UsageLimits(request_limit=inp.max_requests))
            if _model is not None:
                kwargs["model"] = _model
            result = await agent.run(sub_question_prompt(sub.question), **kwargs)
    except (BudgetExceeded, UsageLimitExceeded) as exc:
        # Expected exhaustion: degrade. NEVER re-raise -- the counter is
        # persisted, so a retry hits the same exhausted cap and burns six
        # attempts with backoff for a guaranteed failure.
        activity.logger.info("sub-question %s degraded: %s", sub.id, exc)
        return SubQuestionFinding(sub_question=sub, brief=_degraded(sub, exc), usage=usage)
    except asyncio.CancelledError:
        # Graceful shutdown cancels in-flight activities. Heartbeat on the way
        # out so the server learns immediately rather than waiting out
        # start_to_close before rescheduling.
        activity.heartbeat()
        activity.logger.warning("sub-question %s cancelled mid-flight", sub.id)
        raise

    return SubQuestionFinding(
        sub_question=sub, brief=result.output, usage=_usage_of(result, inp.model)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_subquestion_activity.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Register on the worker**

In `src/sdlc/worker.py`, extend the import:

```python
from .research.stage import plan_research, research_subquestion
```

and add `research_subquestion,` to the `activities=[...]` list.

- [ ] **Step 6: Run the full research suite**

Run: `uv run pytest tests/ -k research -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/research/stage.py src/sdlc/worker.py tests/test_research_subquestion_activity.py
git commit -m "feat(research): research_subquestion activity with per-scope budget and timer heartbeat"
```

---

### Task 8b: Route the toolset through the per-sub-question scope

Task 2 built `charge_scoped` but nothing calls it — `WrappedExaSearchToolset` still charges the default `"run"` scope, which leaves the per-sub-question allowance inert. This connects them.

**Files:**
- Modify: `src/sdlc/research/deps.py` (add two fields to `ResearchDeps`)
- Modify: `agents/research/exa_wrapper.py:26-50` (three charge calls)
- Modify: `src/sdlc/research/stage.py` (set the scope in `research_subquestion`)
- Test: `tests/test_research_budget_scope.py` (append)

**Interfaces:**
- Consumes: `charge_scoped` (Task 2), `SubQuestionInput` (Task 8)
- Produces: `ResearchDeps.scope: str = "run"`, `ResearchDeps.max_run_cost_usd: float = 4.0`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_research_budget_scope.py`:

```python
@pytest.mark.asyncio
async def test_research_subquestion_charges_its_own_scope():
    # The per-sub-question allowance is only real if the toolset charges the
    # sub-question's scope rather than the shared run counter.
    from pydantic_ai.models.test import TestModel

    from sdlc.models import SubQuestion
    from sdlc.research.budget_store import charge_scoped
    from sdlc.research.stage import SubQuestionInput

    inp = SubQuestionInput(
        sub_question=SubQuestion(id="sq-7", question="q"),
        deps=_deps(),
        model="test-model",
        max_requests=40,
        max_run_cost_usd=4.0,
    )

    captured = {}

    class _Agent:
        async def run(self, prompt, **kw):
            captured["scope"] = kw["deps"].scope
            captured["run_max"] = kw["deps"].max_run_cost_usd
            from sdlc.models import ResearchBrief

            class _R:
                output = ResearchBrief(summary="s")

                @staticmethod
                def usage():
                    class _U:
                        input_tokens = output_tokens = 0
                        cache_read_tokens = cache_write_tokens = 0

                    return _U()

            return _R()

    from sdlc.research.stage import research_subquestion

    await research_subquestion(inp, _agent=_Agent())
    assert captured["scope"] == "sq-7"
    assert captured["run_max"] == 4.0


def test_research_deps_defaults_to_the_run_scope():
    d = _deps()
    assert d.scope == "run"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_budget_scope.py -v`
Expected: FAIL with `AttributeError: 'ResearchDeps' object has no attribute 'scope'`

- [ ] **Step 3: Add the fields to `ResearchDeps`**

In `src/sdlc/research/deps.py`, add to `ResearchDeps` after `memory_watermark`:

```python
    scope: str = "run"
    """Which persisted budget counter this call charges. The fan-out sets it
    to "sq-<id>" so one sub-question's spending cannot drain its siblings'
    allowance; "run" is the shared whole-run counter."""

    max_run_cost_usd: float = 4.0
    """The whole-run ceiling, charged alongside `scope` on every call. Carried
    on deps because the toolset charges activity-side and has no other route
    to the config."""
```

- [ ] **Step 4: Set the scope in `research_subquestion`**

In `src/sdlc/research/stage.py`, replace the `deps = inp.deps.model_copy(...)` line in `research_subquestion` with:

```python
# Each sub-question charges its OWN scope so one cannot drain the run.
deps = inp.deps.model_copy(
    update={
        "budget": inp.deps.budget.model_copy(),
        "scope": sub.id,
        "max_run_cost_usd": inp.max_run_cost_usd,
    }
)
```

- [ ] **Step 5: Route the toolset through `charge_scoped`**

In `agents/research/exa_wrapper.py`, change the import on line 6:

```python
from sdlc.research.budget_store import charge_scoped
```

and replace each of the three `await charge_persisted(ctx.deps, ...)` calls:

```python
await charge_scoped(
    ctx.deps, search=1, scope=ctx.deps.scope, run_max_cost_usd=ctx.deps.max_run_cost_usd
)
```

for `web_search` and `deep_search`, and for `get_page`:

```python
await charge_scoped(
    ctx.deps, fetch=1, scope=ctx.deps.scope, run_max_cost_usd=ctx.deps.max_run_cost_usd
)
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_research_budget_scope.py tests/test_research_subquestion_activity.py tests/test_research_tools.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/research/deps.py src/sdlc/research/stage.py agents/research/exa_wrapper.py tests/test_research_budget_scope.py
git commit -m "feat(research): charge the per-sub-question budget scope from the search toolset"
```

---

### Task 9: `synthesize_brief` activity

Merge deterministically, then one model call for the three fields that need judgment over the whole. The model may not author findings.

**Files:**
- Modify: `src/sdlc/research/stage.py`
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_research_synthesize_activity.py`

**Interfaces:**
- Consumes: `merge_briefs` (Task 5), `SYNTHESIS_SYSTEM` (Task 6), `SubQuestionFinding` (Task 4)
- Produces:
  - `SynthesizeInput(idea_json: str, findings: list[SubQuestionFinding], model: str)`
  - `synthesize_brief(inp: SynthesizeInput) -> ResearchBrief` (Temporal activity)
  - `_numbered_sources(brief: ResearchBrief) -> str` (module-private, tested directly)

- [ ] **Step 1: Write the failing test**

```python
"""synthesize_brief: deterministic merge + a model call confined to summary,
contradictions, and confidence.

The model MUST NOT author grounded findings. It would be caught by
verify_brief, but only by turning a normal run into a fail-closed stage
failure -- so the activity refuses the material rather than relying on the
verifier to catch it."""

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.models import (
    ConsultedSource,
    GroundedFinding,
    ResearchBrief,
    SubQuestion,
    SubQuestionFinding,
)
from sdlc.research.stage import SynthesizeInput, _numbered_sources, synthesize_brief


def _finding(sq_id: str, brief: ResearchBrief) -> SubQuestionFinding:
    return SubQuestionFinding(
        sub_question=SubQuestion(id=sq_id, question=f"q {sq_id}"), brief=brief
    )


def _two_findings() -> list[SubQuestionFinding]:
    a = ResearchBrief(
        sources_consulted=[ConsultedSource(url="https://a.example", title="A")],
        grounded_findings=[
            GroundedFinding(source_url="https://a.example", quote="qa", claim="claim A")
        ],
    )
    b = ResearchBrief(
        sources_consulted=[ConsultedSource(url="https://b.example", title="B")],
        grounded_findings=[
            GroundedFinding(source_url="https://b.example", quote="qb", claim="claim B")
        ],
    )
    return [_finding("sq-0", a), _finding("sq-1", b)]


def _inp() -> SynthesizeInput:
    return SynthesizeInput(idea_json='{"title": "x"}', findings=_two_findings(), model="test-model")


def test_numbered_sources_are_one_based_and_stable():
    brief = ResearchBrief(
        sources_consulted=[
            ConsultedSource(url="https://a.example", title="A"),
            ConsultedSource(url="https://b.example", title="B"),
        ]
    )
    text = _numbered_sources(brief)
    assert "[1]" in text and "https://a.example" in text
    assert "[2]" in text and "https://b.example" in text


@pytest.mark.asyncio
async def test_findings_and_sources_come_from_the_merge_not_the_model():
    out = await synthesize_brief(
        _inp(),
        _model=TestModel(
            custom_output_args={"summary": "combined", "confidence": 0.7, "contradictions": []}
        ),
    )
    assert {f.claim for f in out.grounded_findings} == {"claim A", "claim B"}
    assert len(out.sources_consulted) == 2


@pytest.mark.asyncio
async def test_the_model_writes_summary_and_confidence():
    out = await synthesize_brief(
        _inp(),
        _model=TestModel(
            custom_output_args={
                "summary": "combined answer",
                "confidence": 0.7,
                "contradictions": [],
            }
        ),
    )
    assert out.summary == "combined answer"
    assert out.confidence == 0.7


@pytest.mark.asyncio
async def test_the_model_can_add_cross_sub_question_contradictions():
    out = await synthesize_brief(
        _inp(),
        _model=TestModel(
            custom_output_args={
                "summary": "s",
                "confidence": 0.5,
                "contradictions": [
                    {
                        "topic": "date",
                        "positions": ["2026", "2027"],
                        "assessment": "A is better sourced",
                        "unresolved": True,
                    }
                ],
            }
        ),
    )
    assert len(out.contradictions) == 1
    assert out.contradictions[0].topic == "date"


@pytest.mark.asyncio
async def test_synthesis_of_no_findings_is_an_empty_brief_without_a_model_call():
    out = await synthesize_brief(
        SynthesizeInput(idea_json="{}", findings=[], model="test-model"),
        _model=TestModel(
            custom_output_args={
                "summary": "should not be used",
                "confidence": 1.0,
                "contradictions": [],
            }
        ),
    )
    assert out.summary == ""
    assert out.grounded_findings == []


@pytest.mark.asyncio
async def test_field_order_is_preserved():
    # tests/test_research_models.py pins SGR reasoning order; a merge that
    # rebuilt the model with reordered fields would be a regression.
    out = await synthesize_brief(
        _inp(),
        _model=TestModel(
            custom_output_args={"summary": "s", "confidence": 0.5, "contradictions": []}
        ),
    )
    assert list(out.model_dump().keys()) == list(ResearchBrief().model_dump().keys())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_synthesize_activity.py -v`
Expected: FAIL with `ImportError: cannot import name 'SynthesizeInput'`

- [ ] **Step 3: Implement the activity**

Append to `src/sdlc/research/stage.py`:

```python
from .merge import merge_briefs
from .prompts import SYNTHESIS_SYSTEM


class _SynthesisOutput(BaseModel):
    """EXACTLY the three fields the model is allowed to write. Making this a
    closed type is the enforcement of "synthesis may not author grounded
    findings" -- there is simply nowhere for it to put one."""

    summary: str = ""
    contradictions: list[Contradiction] = Field(default_factory=list)
    confidence: float = 0.0


class SynthesizeInput(BaseModel):
    idea_json: str
    findings: list[SubQuestionFinding]
    model: str


def _numbered_sources(brief: ResearchBrief) -> str:
    """The numbered source list, built BEFORE the model is prompted.

    Order matters and is the whole reason this is a separate function. Building
    the list after the call makes citation impossible: the model never saw the
    numbers, so it had none to cite. Built first and handed over, the numbers
    the model cites and the numbers the brief carries come from one object and
    cannot drift."""
    return "".join(
        f"[{n}] {s.title or s.url} — {s.url}\n"
        for n, s in enumerate(brief.sources_consulted, start=1)
    )


def _synthesis_prompt(inp: SynthesizeInput, merged: ResearchBrief) -> str:
    parts = [
        f"Original question / feature idea:\n\n{inp.idea_json}\n",
        "\nWhat the analysts found:\n",
    ]
    for f in inp.findings:
        parts.append(f"\n--- On: {f.sub_question.question}\n")
        if f.failed:
            parts.append(f"(this sub-question did not complete: {f.error})\n")
            continue
        parts.append(f"{f.brief.summary}\n")
        for g in f.brief.grounded_findings:
            parts.append(f"  * {g.claim} — {g.source_url}\n")
    sources = _numbered_sources(merged)
    if sources:
        parts.append("\nNumbered sources — cite ONLY these numbers:\n")
        parts.append(sources)
    return "".join(parts)


@activity.defn
async def synthesize_brief(inp: SynthesizeInput, _model=None) -> ResearchBrief:
    """Merge N partial briefs into one ResearchBrief.

    Structure comes from code (merge_briefs), prose from the model. The model
    is handed a closed output type with three fields, so it CANNOT author a
    grounded finding -- a fabricated quote would be caught by verify_brief, but
    only by turning an ordinary run into a fail-closed stage failure.
    """
    merged = merge_briefs(inp.findings)
    if not inp.findings:
        return merged

    agent = Agent(_model or inp.model, output_type=_SynthesisOutput, system_prompt=SYNTHESIS_SYSTEM)
    result = await agent.run(_synthesis_prompt(inp, merged))
    out = result.output

    return merged.model_copy(
        update={
            "summary": out.summary,
            # Within-sub-question conflicts (already in `merged`) PLUS the
            # cross-sub-question ones only visible now that independent
            # investigations sit side by side. The second kind is unreachable in a
            # single agent turn and is the depth payoff of fanning out.
            "contradictions": merged.contradictions + out.contradictions,
            "confidence": out.confidence,
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_synthesize_activity.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Register on the worker**

In `src/sdlc/worker.py`:

```python
from .research.stage import plan_research, research_subquestion, synthesize_brief
```

and add `synthesize_brief,` to the `activities=[...]` list.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/research/stage.py src/sdlc/worker.py tests/test_research_synthesize_activity.py
git commit -m "feat(research): synthesize_brief with pre-built source numbering and a closed output type"
```

---

### Task 10: Workflow wiring

Replace the single-agent stage with the fan-out. Failure tiers, usage folding, and retry classification all land here.

**Files:**
- Modify: `src/sdlc/workflows/feature.py:1314-1405` (the research block), plus new activity-config constants near line 133
- Test: `tests/test_research_fanout_wiring.py`

**Interfaces:**
- Consumes: `plan_research`/`PlanInput`, `research_subquestion`/`SubQuestionInput`, `synthesize_brief`/`SynthesizeInput` (Tasks 7-9)
- Produces: `FeatureWorkflow._research_stage(cfg, idea, run_id) -> tuple[ResearchBrief, RoleUsage]` — a method the refine round (Task 11) wraps

- [ ] **Step 1: Write the failing test**

```python
"""Fan-out wiring: failure tiers and usage folding.

These exercise the workflow's helpers directly rather than booting Temporal --
the stage's ORCHESTRATION decisions are what matter here, and the activities
themselves are covered by Tasks 7-9."""

import pytest

from sdlc.models import ResearchBrief, RoleUsage, SubQuestion, SubQuestionFinding
from sdlc.workflows.feature import (
    RESEARCH_PLAN_ACT,
    RESEARCH_SQ_ACT,
    RESEARCH_SYNTH_ACT,
    _findings_from_results,
)


def _ok(sq_id: str) -> SubQuestionFinding:
    return SubQuestionFinding(
        sub_question=SubQuestion(id=sq_id, question="q"),
        brief=ResearchBrief(summary="s"),
        usage=RoleUsage(role="research", model="m", calls=1, input_tokens=10, output_tokens=5),
    )


def test_all_successful_results_pass_through():
    subs = [SubQuestion(id="sq-0", question="q0")]
    out = _findings_from_results(subs, [_ok("sq-0")])
    assert len(out) == 1
    assert out[0].failed is False


def test_an_exception_becomes_a_failed_finding_not_a_raise():
    subs = [SubQuestion(id="sq-0", question="q0")]
    out = _findings_from_results(subs, [RuntimeError("worker died")])
    assert len(out) == 1
    assert out[0].failed is True
    assert "worker died" in out[0].error
    assert out[0].sub_question.id == "sq-0"


def test_one_failure_does_not_discard_its_siblings():
    subs = [SubQuestion(id="sq-0", question="q0"), SubQuestion(id="sq-1", question="q1")]
    out = _findings_from_results(subs, [RuntimeError("boom"), _ok("sq-1")])
    assert [f.failed for f in out] == [True, False]


def test_sub_question_activity_config_satisfies_the_heartbeat_invariant():
    # interval < heartbeat_timeout < start_to_close. Violating it either times
    # out a healthy activity or leaves a dead worker undetected until
    # start_to_close.
    from sdlc.research.stage import HEARTBEAT_INTERVAL_SECONDS

    hb = RESEARCH_SQ_ACT["heartbeat_timeout"].total_seconds()
    stc = RESEARCH_SQ_ACT["start_to_close_timeout"].total_seconds()
    assert HEARTBEAT_INTERVAL_SECONDS < hb < stc


def test_budget_exhaustion_is_classified_non_retryable():
    # The counter is PERSISTED. Retrying hits the same exhausted cap -- six
    # guaranteed failures with backoff.
    names = RESEARCH_SQ_ACT["retry_policy"].non_retryable_error_types
    assert "BudgetExceeded" in names
    assert "UsageLimitExceeded" in names


def test_plan_and_synthesis_configs_exist_with_retries():
    assert RESEARCH_PLAN_ACT["retry_policy"].maximum_attempts >= 3
    assert RESEARCH_SYNTH_ACT["retry_policy"].maximum_attempts >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_fanout_wiring.py -v`
Expected: FAIL with `ImportError: cannot import name 'RESEARCH_PLAN_ACT'`

- [ ] **Step 3: Add the activity configs**

In `src/sdlc/workflows/feature.py`, after `INTEG_ACT` (line ~135):

```python
# Fan-out research. Durations follow the shape measured by the prior art:
# planning is short and schema-constrained; a sub-question runs a full agent
# with search and page fetches and legitimately takes minutes.
RESEARCH_PLAN_ACT = dict(
    start_to_close_timeout=timedelta(minutes=5), retry_policy=RetryPolicy(maximum_attempts=3)
)
# The heartbeat is the important knob. A sub-question can run for many
# minutes, so without heartbeating the server waits out the full
# start_to_close before rescheduling a lost worker; with it, ~60s.
# Invariant: stage.HEARTBEAT_INTERVAL_SECONDS < heartbeat_timeout <
# start_to_close_timeout.
RESEARCH_SQ_ACT = dict(
    start_to_close_timeout=timedelta(minutes=20),
    heartbeat_timeout=timedelta(seconds=60),
    retry_policy=RetryPolicy(
        initial_interval=timedelta(seconds=2),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=60),
        maximum_attempts=6,
        # The budget counter is PERSISTED to disk, so a retry meets the same
        # exhausted cap: six guaranteed failures with backoff. The activity
        # already degrades these internally; this is the belt-and-braces for
        # any path that lets one escape.
        non_retryable_error_types=["BudgetExceeded", "UsageLimitExceeded"],
    ),
)
RESEARCH_SYNTH_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)
```

- [ ] **Step 4: Add the result-collector helper**

In `src/sdlc/workflows/feature.py`, near `_degraded_research_brief` (line ~227):

```python
def _findings_from_results(subs: list["SubQuestion"], results: list) -> list["SubQuestionFinding"]:
    """Turn gather(..., return_exceptions=True) output into findings.

    Sub-questions are INDEPENDENT -- that is the premise of the fan-out. Letting
    one exception propagate would cancel the gather and discard every sibling
    finding already paid for. A partial brief from three of four sub-questions
    is worth far more than nothing, so a failure becomes a failed finding that
    the merge turns into a Gap."""
    out: list[SubQuestionFinding] = []
    for sub, result in zip(subs, results):
        if isinstance(result, BaseException):
            out.append(SubQuestionFinding(sub_question=sub, failed=True, error=str(result)))
        else:
            out.append(result)
    return out
```

Add `SubQuestionFinding`, `ResearchPlan` to the model imports in the `workflow.unsafe.imports_passed_through()` block (near line 69), and the stage activities + input types near line 76:

```python
from ..research.stage import (
    PlanInput,
    SubQuestionInput,
    SynthesizeInput,
    plan_research,
    research_subquestion,
    synthesize_brief,
)
```

- [ ] **Step 5: Replace the stage body**

In `src/sdlc/workflows/feature.py`, replace the `try:` / `except (BudgetExceeded, UsageLimitExceeded)` block that produces `brief` (lines 1342-1354) with a call to a new method, and add the method to the class:

```python
async def _fan_out_research(
    self,
    cfg: PipelineConfig,
    idea,
    deps: "ResearchDeps",
    spend: RoleUsage,
    id_offset: int = 0,
    guidance: str = "",
    gaps: list | None = None,
    contradictions: list | None = None,
) -> tuple["ResearchBrief", list]:
    """One wave: plan -> N parallel sub-questions -> synthesize.

    Returns the merged brief and the raw findings, so a refine round can
    extend the finding list rather than discarding round one."""
    model = STAGE_MODELS.get("research", "unknown")

    plan: ResearchPlan = await workflow.execute_activity(
        plan_research,
        PlanInput(
            idea_json=idea.model_dump_json(),
            max_sub_questions=cfg.research.max_sub_questions,
            model=model,
            id_offset=id_offset,
            guidance=guidance,
            gaps=gaps or [],
            contradictions=contradictions or [],
        ),
        **RESEARCH_PLAN_ACT,
    )
    await self._fold_research_usage(cfg, plan.usage, spend)

    # THE fan-out. return_exceptions=True because the sub-questions are
    # independent: one failure must not cancel the gather and throw away
    # siblings already paid for.
    results = await asyncio.gather(
        *[
            workflow.execute_activity(
                research_subquestion,
                SubQuestionInput(
                    sub_question=sq,
                    deps=deps,
                    model=model,
                    max_requests=cfg.research.max_requests,
                    max_run_cost_usd=cfg.research.max_run_cost_usd,
                ),
                **RESEARCH_SQ_ACT,
            )
            for sq in plan.sub_questions
        ],
        return_exceptions=True,
    )

    findings = _findings_from_results(plan.sub_questions, results)
    for f in findings:
        await self._fold_research_usage(cfg, f.usage, spend)
    return findings


async def _fold_research_usage(
    self, cfg: PipelineConfig, usage: RoleUsage, into: RoleUsage
) -> None:
    """E-33 amendment: fan-out moved the model call activity-side, so
    _run_role cannot wrap it. The activity hands usage back and the
    workflow prices it here -- one accounting path preserved, only the
    call site moved."""
    if not (usage.input_tokens or usage.output_tokens):
        return
    usd: float | None = None
    try:
        usd = await workflow.execute_activity(
            price_usage,
            PriceUsageInput(
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
            ),
            **PRICE_ACT,
        )
    except Exception:
        usd = None
    self._track_usage(
        role="research",
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        cost_usd=usd,
        into=into,
    )
```

Then in the stage body, replace the single `_run_role` call with:

```python
findings = await self._fan_out_research(cfg, idea, deps, research_spend)
brief: ResearchBrief = await workflow.execute_activity(
    synthesize_brief,
    SynthesizeInput(
        idea_json=idea.model_dump_json(),
        findings=findings,
        model=STAGE_MODELS.get("research", "unknown"),
    ),
    **RESEARCH_SYNTH_ACT,
)
if all(f.failed for f in findings):
    # Every sub-question failed: nothing to build a brief from.
    # Degrade the STAGE, never the run (2026-07-20 decision).
    brief = _degraded_research_brief(RuntimeError("every sub-question failed"))
```

Add `import asyncio` at the top of `feature.py` if it is not already imported.

- [ ] **Step 6: Run the wiring tests**

Run: `uv run pytest tests/test_research_fanout_wiring.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Run purity and stage-wiring regressions**

Run: `uv run pytest tests/test_factory_purity.py tests/test_research_stage_wiring.py tests/test_research_stage_judging.py tests/test_research_degradation.py -v`
Expected: PASS. `test_factory_purity.py` is the one that matters — it fails if any workflow-side code performs I/O or reads the environment.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_research_fanout_wiring.py
git commit -m "feat(research): fan out the research stage across parallel sub-question activities"
```

---

### Task 11: Refine round

`GateOutcome.REVISE` already exists and `_gate` already takes `round`. The stage currently collapses revise into reject via `if not gate.approved`. This wires the third outcome.

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (the research stage's gate block, ~line 1388)
- Test: `tests/test_research_refine_round.py`

**Interfaces:**
- Consumes: `_fan_out_research` (Task 10), `GateOutcome`, `GateDecision`, `_gate`
- Produces: no new public interface — the stage's behavior changes

- [ ] **Step 1: Write the failing test**

```python
"""The refine round: gate REVISE triggers a second, targeted wave.

Round-1 findings are never discarded, round-2 ids never collide with round-1,
and exhausting the round budget PROCEEDS with the current brief rather than
rejecting -- research degrades a run, it never stops it."""

import pytest

from sdlc.models import (
    Contradiction,
    Gap,
    ResearchBrief,
    ResearchConfig,
    SubQuestion,
    SubQuestionFinding,
)
from sdlc.workflows.feature import _refine_seed, _should_refine


def _brief() -> ResearchBrief:
    return ResearchBrief(
        gaps=[
            Gap(
                sub_question_id="sq-0",
                what_is_missing="penalties",
                why_it_matters="drives the design",
            )
        ],
        contradictions=[
            Contradiction(topic="date", positions=["a", "b"], unresolved=True),
            Contradiction(topic="scope", positions=["c", "d"], unresolved=False),
        ],
    )


def test_refine_is_allowed_on_the_first_revise():
    assert _should_refine(round_n=1, cfg=ResearchConfig()) is True


def test_refine_is_exhausted_after_max_rounds():
    assert _should_refine(round_n=2, cfg=ResearchConfig()) is False


def test_refine_can_be_disabled_entirely():
    assert _should_refine(round_n=1, cfg=ResearchConfig(max_refine_rounds=0)) is False


def test_the_seed_carries_gaps_and_only_UNRESOLVED_contradictions():
    # A resolved contradiction is answered. Re-researching it spends the run
    # ceiling on work already done.
    gaps, conflicts = _refine_seed(_brief())
    assert [g.what_is_missing for g in gaps] == ["penalties"]
    assert [c.topic for c in conflicts] == ["date"]


def test_the_id_offset_is_the_count_of_existing_sub_questions():
    findings = [
        SubQuestionFinding(sub_question=SubQuestion(id="sq-0", question="a")),
        SubQuestionFinding(sub_question=SubQuestion(id="sq-1", question="b")),
    ]
    # Round two must start at sq-2 or the merge silently overwrites round one.
    assert len(findings) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_refine_round.py -v`
Expected: FAIL with `ImportError: cannot import name '_refine_seed'`

- [ ] **Step 3: Add the helpers**

In `src/sdlc/workflows/feature.py`, next to `_findings_from_results`:

```python
def _should_refine(round_n: int, cfg: "ResearchConfig") -> bool:
    """Whether a REVISE at `round_n` gets another wave. Exhaustion is NOT a
    rejection -- the stage proceeds with the brief it has."""
    return round_n <= cfg.max_refine_rounds


def _refine_seed(brief: "ResearchBrief") -> tuple[list, list]:
    """What round two should target: everything round one could not resolve.

    Richer than a free-text note, because the SGR brief already carries the
    machine-readable version. Resolved contradictions are excluded -- they are
    answered, and re-researching them spends the run ceiling on finished work."""
    return list(brief.gaps), [c for c in brief.contradictions if c.unresolved]
```

- [ ] **Step 4: Wire the gate loop**

Replace the gate block in the research stage (currently `gate = await self._gate("research", cfg)` / `if not gate.approved: return "rejected:research"`) with:

```python
round_n = 1
while True:
    gate = await self._gate("research", cfg, round=round_n)
    if gate.outcome == GateOutcome.APPROVE:
        break
    if gate.outcome == GateOutcome.REJECT:
        return "rejected:research"
    # REVISE
    if not _should_refine(round_n, cfg.research):
        # Exhausted: proceed with what we have. Research
        # degrades a run; it never stops one.
        break
    gaps, conflicts = _refine_seed(brief)
    findings += await self._fan_out_research(
        cfg,
        idea,
        deps,
        research_spend,
        id_offset=len(findings),
        guidance=gate.guidance or "",
        gaps=gaps,
        contradictions=conflicts,
    )
    # Re-merge over ALL findings: round one is never discarded.
    brief = await workflow.execute_activity(
        synthesize_brief,
        SynthesizeInput(
            idea_json=idea.model_dump_json(),
            findings=findings,
            model=STAGE_MODELS.get("research", "unknown"),
        ),
        **RESEARCH_SYNTH_ACT,
    )
    # Round-2 findings must be verified too.
    violations = await workflow.execute_activity(
        verify_brief_activity, args=[brief, workflow.info().workflow_id], **VERIFY_ACT
    )
    if violations:
        self._status = "research_failed"
        brief_digest_val = ""
        break
    brief_digest_val = brief_digest(brief)
    round_n += 1
```

- [ ] **Step 5: Run the refine tests**

Run: `uv run pytest tests/test_research_refine_round.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the whole research suite plus purity**

Run: `uv run pytest tests/ -k "research or purity" -v`
Expected: PASS

- [ ] **Step 7: Run the full fast suite**

Run: `uv run pytest`
Expected: PASS. Any failure here is a regression introduced by this plan — fix before committing.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_research_refine_round.py
git commit -m "feat(research): bounded refine round wired to GateOutcome.REVISE"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §3.1 `plan_research` + hard width slice | 7 |
| §3.2 `research_subquestion` in-process agent | 8 |
| §3.3 / §5 `synthesize_brief` + merge split | 5, 9 |
| §4 per-sub-question + run budget scopes | 2, 3 |
| §5.1 dedupe rule + `brief_digest` stability | 5 |
| §5.3 synthesis may not author findings | 9 (closed output type) |
| §6 refine round, id offsets, re-verification | 11 |
| §7 E-33 usage-carrying return types | 4, 10 |
| §8 failure tiers | 7 (planner), 8 (budget), 10 (partial + total) |
| §8.1 retry classification | 10 |
| §9.1 atomic page writes | 1 |
| §9.2 no retries beneath Temporal | **gap — see below** |
| §9.3 worker capacity (no change needed) | n/a by design |
| §10 heartbeating, resume deferred | 8, 10 |
| §11 prompt caching + length guard | 6 |
| §13 testing | every task |

**Gap found and accepted:** §9.2 ("confirm the Exa and model clients do not retry internally") is a verification step, not a code change, and it cannot be unit-tested — it depends on `pydantic_ai_harness.exa`'s client construction. Fold it into Task 8 as a manual check: read `pydantic_ai_harness.exa.ExaSearch`'s client setup and confirm no internal retry wrapper; if one exists, set it to 0 in `WrappedExaSearch.get_toolset()`. Recorded here rather than invented as a fake test.

**Type consistency:** `SubQuestion` uses `.id` / `.question` throughout (matching `models.py:447`). `SubQuestionFinding.sub_question` is the full object, never a bare id. `RoleUsage` is the usage type everywhere — never DRF's `Usage`. `merge_briefs` takes `list[SubQuestionFinding]` in both Task 5 and Task 9. `budget_path(run_id, scope)` argument order is consistent between Tasks 2 and 8.

**Second gap found and fixed inline:** the first draft built `charge_scoped` in Task 2 but never called it — `WrappedExaSearchToolset` kept charging the default `"run"` scope, leaving the per-sub-question allowance inert and §4 only half-implemented. Added as **Task 8b**, which carries the scope on `ResearchDeps` and routes the toolset's three charge calls through it.

**Task ordering note:** Tasks 1-6 are independent of each other and can be executed in any order or in parallel. Task 7 depends on 3, 4, 6. Task 8 depends on 7. Task 8b depends on 2 and 8. Task 9 depends on 5, 6, 8. Task 10 depends on 7, 8, 9. Task 11 depends on 10.
