# Research Agent — Grounded Briefs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a human-gated `research` stage before `clarify` that emits a `ResearchBrief` grounded in bytes fetched this run — every "grounded" claim verified as a verbatim quote against a page file, or demoted to "inferred" — without destroying the pipeline's memoization or reopening the registry spec's two-registry hole.

**Architecture:** A `kind: research` directory (`agents/research/`) is the first entry in the shipped `OPTIONAL_ROLES` seam: known, but not required, since `research_enabled` defaults `False`. It carries `instructions.md`, `agent.py`, and — uniquely — a `tools/` directory. Four thin tool files bind a `SearchProvider` (Tavily or a canned fake) to typed signatures; `CodeMode` collapses their fan-out into one sandboxed `run_code` activity so a per-run budget counter and a page cache both survive inside a single process. An `@agent.output_validator` verifies each `grounded_finding`'s quote against `runs/<run_id>/research/pages/<sha256(url)>.txt`, raising `ModelRetry` on a violation and failing the stage closed after retries. The brief contributes a canonical `brief_digest` (source_url+claim pairs only) to downstream `content_key`, so identical facts memoize and new facts correctly invalidate `clarify`/`architect`/`planner`.

**Tech Stack:** Python 3.14, Pydantic v2, Pydantic AI (`Agent`/`TemporalAgent`, `output_validator`, `ModelRetry`, `RunContext` deps), `pydantic-ai-harness[codemode]` (Monty sandbox), Temporal, Tavily HTTP (httpx), pytest.

**Spec:** `docs/superpowers/specs/2026-07-17-research-agent-grounded-briefs-design.md`
**Depends on (shipped):** `2026-07-17-agents-as-folders-design.md` (`bb483f4`…`8bef535`) and `2026-07-16-registry-drives-every-role-design.md`.

## Global Constraints

- **`grounded` has exactly one meaning everywhere: verified against bytes fetched in THIS run.** No TTL, no clock. A finding recalled from the corpus was not fetched this run, so if placed in `grounded_findings` it fails the *source-never-fetched* check by construction (spec finding 5). No demotion mechanism is written — the existing check enforces it.
- **The research stage is NEVER routed through `_cached_stage` (spec finding 4).** A served memo means the pages were not fetched this run, so a memoized brief would carry a label it did not earn. `research` is added to `STAGE_MODELS` and `PROMPT_SHAS` (they feed benchmark records), but there is no `content_key`/`cache_get`/`cache_put` call on the research path.
- **`PipelineConfig` is constructed inside the Temporal workflow.** Nothing on the research path that runs in *workflow* context may do file I/O or network I/O. All fetching, page-writing, quote-verification, and provider calls run in *activities* (inside tool functions and, per the Task 1 spike, the output validator). The workflow only assembles typed inputs and reads typed outputs.
- **The workflow never computes a filesystem path from the environment.** Tools and the validator, which run activity-side, resolve the pages directory themselves from `$SDLC_RUNS_ROOT` (default `runs/`) + `run_id`. `run_id` reaches them through `ResearchDeps`, never a path.
- **Budget is enforced inside the tool functions, never in the prompt** (spec §3). A prompt-level bound is a suggestion. Exceeding a bound raises an ordinary error the sandbox surfaces to the model; the shortfall lands in the brief's `gaps`.
- **CodeMode is load-bearing, not decorative.** The per-run budget counter and the page cache are shared *in-process* across many tool calls. That only holds because CodeMode collapses the fan-out into ONE `run_code` activity. Do not "simplify" research to plain tool calls — that would put each tool call in its own activity and the shared counter would reset.
- **`provider: fake` is the shipped default and what CI uses.** `agents/research/agent.yaml` ships `provider: fake` so boot and the test suite never require `TAVILY_API_KEY`. `provider: tavily` with no reachable `TAVILY_API_KEY` is a `RegistryError` at boot — fail closed, like the registry and schedule loaders.
- **ADR-6 does not constrain research** — it reviews nothing. `validate_registry` gains a *provider* rule for `kind: research`, not a family-inequality rule.
- **Agent/toolset names become Temporal activity names.** The research agent is `name="research_agent"`. Never rename it after this ships.
- Model ids verbatim: research proposer uses `anthropic:glm-5.2` (same family convention as the other proposers).
- Run tests with `python -m pytest` from the repo root. The suite is green at HEAD — keep it green after every task.
- Prompt/instruction files are written with **no trailing newline** unless a test pins otherwise (the agents-as-folders migration rule; `read_text` applies universal newlines).

---

### Task 1: Spike — prove the two unproven mechanisms before building on them

The spec names this Task 1 and calls it a decision gate (finding 8): two mechanisms the whole design leans on are *assumed*, not verified. Prove both, or the architecture changes shape.

**A.** `@agent.output_validator` raising `ModelRetry` survives `TemporalAgent` temporalization, and the validator executes **activity-side** (where reading page files is legal I/O), not in workflow context (where `test_factory_purity.py` forbids file I/O).

**B.** `pydantic-ai-harness[codemode]` installs and imports on this platform (Python 3.14, Windows), and a trivial `CodeMode` `run_code` executes through a `TemporalAgent` on a time-skipping worker. Monty on 3.14 is unproven here and is the second load-bearing unknown.

**Files:**
- Modify: `pyproject.toml` (add the dependency)
- Test: `tests/test_research_spike.py` (create)

**Interfaces:**
- Consumes: `TestModel`, `TemporalAgent`, `WorkflowEnvironment`, `PydanticAIPlugin`, the `fake_temporal_agent` pattern from `tests/fakes/fake_agents.py`.
- Produces: nothing importable. This task's output is a **recorded finding** (a comment block at the top of `tests/test_research_spike.py`) that the remaining tasks are written against.

- [ ] **Step 1: Add the Code Mode dependency to `pyproject.toml`**

Append to the `dependencies` list (keep the trailing comma style):

```toml
    "pydantic-ai-harness[codemode]>=0.1",
```

- [ ] **Step 2: Install it and confirm it imports on this platform**

Run:
```bash
python -m pip install -e . && python -c "from pydantic_ai_harness import CodeMode; print('codemode import OK')"
```
Expected: `codemode import OK`.

**If the install or import fails** (Monty has no 3.14/Windows wheel, or a `pydantic-ai-slim` version conflict with the pinned `>=0.4`): STOP. Record the failure in the finding block (Step 5) and raise it — the spec's Code Mode design is blocked on this and the fallback (plain sequential tools inside one wrapper activity, losing the shared-counter guarantee) is a spec-level decision, not a plan-level one.

- [ ] **Step 3: Write the spike test**

Create `tests/test_research_spike.py`:

```python
"""SPIKE (research spec, Task 1 / finding 8). Two load-bearing mechanisms
proven here before the rest of the plan builds on them. The FINDING recorded
at the bottom of this file is this task's real output.

A. An @agent.output_validator that raises ModelRetry survives TemporalAgent
   and runs ACTIVITY-side (reading files there is legal; the workflow sandbox
   forbids it — test_factory_purity.py).
B. pydantic-ai-harness[codemode] imports and a trivial run_code executes
   through a TemporalAgent on a time-skipping worker.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin, TemporalAgent
from pydantic_ai.models.test import TestModel
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG


class _Out(BaseModel):
    text: str


# A validator that records WHERE it runs. workflow.unsafe.is_replaying() is
# only callable in a workflow sandbox; in an activity it raises. We use that
# to observe the execution context without needing a file.
_VALIDATOR_RAN_IN: list[str] = []


def _build_validated_agent(retry_once: bool) -> TemporalAgent:
    agent = Agent(
        TestModel(custom_output_args={"text": "hello"}),
        name="spike_validated_agent",
        output_type=_Out,
    )

    @agent.output_validator
    async def _check(ctx: RunContext, out: _Out) -> _Out:
        try:
            in_workflow = workflow.in_workflow()
        except Exception:
            in_workflow = False
        _VALIDATOR_RAN_IN.append("workflow" if in_workflow else "activity")
        return out

    return TemporalAgent(agent, activity_config=AGENT_ACTIVITY_CONFIG)


t_spike = _build_validated_agent(retry_once=False)


@workflow.defn
class _SpikeWorkflow:
    @workflow.run
    async def run(self) -> str:
        return (await t_spike.run("go")).output.text


@pytest.mark.asyncio
async def test_output_validator_survives_temporalization_and_runs_activity_side():
    _VALIDATOR_RAN_IN.clear()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="spike-ov",
            workflows=[_SpikeWorkflow],
            activities=list(t_spike.temporal_activities),
            plugins=[PydanticAIPlugin()],
        ):
            out = await env.client.execute_workflow(
                _SpikeWorkflow.run, id=f"spike-ov-{uuid.uuid4()}", task_queue="spike-ov"
            )
    assert out == "hello"
    # THE finding: the validator ran, and it ran activity-side.
    assert _VALIDATOR_RAN_IN, "output_validator did not run at all"
    assert _VALIDATOR_RAN_IN[-1] == "activity", (
        f"output_validator ran in {_VALIDATOR_RAN_IN[-1]} context — "
        "verification must move to a post-run activity (see FINDING)"
    )


@pytest.mark.asyncio
async def test_codemode_run_code_executes_through_temporal_agent():
    from pydantic_ai_harness import CodeMode

    agent = Agent(
        TestModel(call_tools=["run_code"]),
        name="spike_codemode_agent",
        capabilities=[CodeMode(tools="all")],
    )

    @agent.tool_plain
    def add_one(n: int) -> int:
        return n + 1

    ta = TemporalAgent(agent, activity_config=AGENT_ACTIVITY_CONFIG)

    @workflow.defn
    class _CodeModeWorkflow:
        @workflow.run
        async def run(self) -> str:
            return str((await ta.run("use the tool")).output)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="spike-cm",
            workflows=[_CodeModeWorkflow],
            activities=list(ta.temporal_activities),
            plugins=[PydanticAIPlugin()],
        ):
            await env.client.execute_workflow(
                _CodeModeWorkflow.run, id=f"spike-cm-{uuid.uuid4()}", task_queue="spike-cm"
            )
    # Reaching here without an exception proves run_code executed through the
    # temporalized agent. (TestModel's tool-call shape may vary; assert only
    # that dispatch did not raise.)
```

- [ ] **Step 4: Run the spike**

Run: `python -m pytest tests/test_research_spike.py -v`
Expected: both tests PASS. In particular the first asserts the validator ran **activity-side**.

- [ ] **Step 5: Record the finding at the bottom of the file, then commit**

Append a `FINDING` block to `tests/test_research_spike.py` stating what was observed. Write the *actual* result — if the validator ran activity-side and Code Mode worked, the rest of the plan proceeds as written:

```python
# ---------------------------------------------------------------------------
# FINDING (fill in with the OBSERVED result, not the hoped-for one):
#   A. output_validator + ModelRetry under TemporalAgent: ran <activity|workflow>-side.
#      -> If activity-side: Task 7 wires verification as an @agent.output_validator.
#      -> If workflow-side: STOP. Verification cannot read files in workflow
#         context. Re-plan Task 7 as a post-run `verify_brief` activity called
#         from feature.py, with the stage failing (not the model retrying) on a
#         violation. Flag this to the plan owner before continuing.
#   B. CodeMode[codemode] import + run_code through TemporalAgent: <worked|failed>.
#      -> If failed: STOP. The tools/CodeMode design (Task 6) is blocked.
# ---------------------------------------------------------------------------
```

```bash
git add pyproject.toml tests/test_research_spike.py
git commit -m "spike(research): output_validator + CodeMode survive TemporalAgent

Task 1 decision gate (spec finding 8). Proves the output_validator runs
activity-side (where quote verification's file reads are legal) and that
pydantic-ai-harness[codemode] imports and run_code dispatches through a
TemporalAgent, before the rest of the increment is built on either."
```

> **The remaining tasks assume finding A = activity-side and finding B = worked.** If either differs, do not proceed on autopilot — the spec says discovering this in Task 9 is not workable.

---

### Task 2: PRD amendment — FR-107 and the 14→15 DAG (the gating change)

The spec is explicitly *gated* on this: "FR-107 does not exist yet — this spec proposes it." Per §9's scope discipline the requirement must be real before the stage is. This is a docs-only task; it ships first among the substantive tasks because everything downstream references FR-107.

**Files:**
- Modify: `PRD.md` (§6, Pipeline / FR-100)
- Modify: `SDLC-spec-v2.md` (§1, the DAG)
- Test: none (documentation). Verified by inspection in Step 3.

**Interfaces:** none. Prose only.

- [ ] **Step 1: Add FR-107 to `PRD.md`**

Find the FR-100 (Pipeline) block in `PRD.md` §6 and add, after the last existing FR-10x entry:

```markdown
- **FR-107 — Grounded research.** The pipeline MAY run a research stage before
  clarification that produces a `ResearchBrief` grounding downstream stages in
  fetched evidence. Every claim presented as grounded MUST carry a source URL
  and a verbatim quote verified against bytes fetched during that run; claims
  that cannot be so verified MUST be presented as inferred, or not at all.
  Research findings retained to memory are leads, not grounded claims: recall
  MUST NOT restore grounded status without re-verification. The stage MUST be
  bounded by explicit per-run limits and is off by default.
```

- [ ] **Step 2: Renumber the DAG in `SDLC-spec-v2.md` §1**

Insert `research` as the new stage 4, before `clarify`, and renumber the stages that follow (4–13 become 5–14; the count becomes 15). Add the rationale line verbatim:

```markdown
> Stage 4 `research` (FR-107) is inserted before `clarify`. The existing stage
> 2 *context (Cartographer)* covers brownfield codebase mapping (FR-102) and is
> NOT a research stage; grounded web research is genuinely new scope. The DAG is
> now 15 stages.
```

(Update the surrounding stage numbers 4→5 … 13→14 in that section. Do not touch `ARCHITECTURE.md`: research introduces no new ADR — it is a proposer with tools under ADR-2, clean-context under ADR-12.)

- [ ] **Step 3: Verify no stale "14 stages" / off-by-one references remain**

Run: `grep -rn "14 stage\|14-stage\|fourteen stage" PRD.md SDLC-spec-v2.md ROADMAP.md`
Expected: no hits that still describe the *current* DAG as 14 stages (roadmap's own §1 count is amended in Task 10). If a hit is a historical note, leave it; if it is a live claim, fix it.

- [ ] **Step 4: Commit**

```bash
git add PRD.md SDLC-spec-v2.md
git commit -m "docs(prd): add FR-107 grounded research; DAG 14 -> 15 stages

The research spec is gated on this: FR-107 did not exist. Adds it to PRD §6
and inserts 'research' as stage 4 before clarify in SDLC-spec-v2 §1, with the
rationale that stage 2 (Cartographer) is brownfield mapping, not research."
```

---

### Task 3: Contracts — `ResearchBrief` cascade, `RoleConfig` grows, config + `MemoryKind`

The SGR field order is the design (spec §4): field order is reasoning order, evidence before conclusion, `quote` before `claim`. Pin it with a test, because `ReviewReport` drifted into verdict-before-findings with nothing to catch it (finding 7).

**Files:**
- Modify: `src/sdlc/models.py` (add contracts + config; grow `RoleConfig`, `MemoryKind`, `PipelineConfig`)
- Test: `tests/test_research_models.py` (create)

**Interfaces:**
- Produces, all in `models.py`:
  - `SubQuestion(id, question)`, `ConsultedSource(url, title, assessment, relevance)`, `GroundedFinding(source_url, quote, claim, sub_question_ids)`, `InferredFinding(reasoning, claim, based_on, fetched_at)`, `Contradiction(topic, positions, assessment, unresolved)`, `Gap(sub_question_id, what_is_missing, why_it_matters)`.
  - `ResearchBrief` with fields **in this exact order**: `sub_questions, sources_consulted, grounded_findings, inferred_findings, contradictions, gaps, summary, brief_ref, confidence`.
  - `RoleConfig.kind` becomes `Literal["proposer", "harness", "research"]`; `RoleConfig.provider: Literal["tavily", "fake"] | None = None`.
  - `MemoryKind.RESEARCH_FINDING = "research_finding"`.
  - `ResearchConfig(max_searches=5, max_fetches=10, max_cost_usd=1.0)`; `PipelineConfig.research: ResearchConfig`; `PipelineConfig.research_enabled: bool = False`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_research_models.py`:

```python
from sdlc.models import (
    ConsultedSource,
    Contradiction,
    Gap,
    GroundedFinding,
    InferredFinding,
    MemoryKind,
    PipelineConfig,
    ResearchBrief,
    ResearchConfig,
    RoleConfig,
    SubQuestion,
)

# The SGR cascade, in the ONE order the spec commits to. This literal IS the
# design (spec §4); a reorder is a silent regression, so it gets a guard.
_BRIEF_ORDER = [
    "sub_questions",
    "sources_consulted",
    "grounded_findings",
    "inferred_findings",
    "contradictions",
    "gaps",
    "summary",
    "brief_ref",
    "confidence",
]


def test_research_brief_field_order_is_the_sgr_cascade():
    assert list(ResearchBrief.model_fields) == _BRIEF_ORDER


def test_grounded_finding_puts_quote_before_claim():
    """Quote-first forces commitment to a span in context, THEN a statement of
    what it supports — the ordering that makes manufactured citations less
    likely (spec §4)."""
    order = list(GroundedFinding.model_fields)
    assert order.index("quote") < order.index("claim")
    assert order[0] == "source_url"


def test_inferred_finding_puts_reasoning_before_claim():
    order = list(InferredFinding.model_fields)
    assert order.index("reasoning") < order.index("claim")


def test_consulted_source_puts_assessment_before_relevance_label():
    order = list(ConsultedSource.model_fields)
    assert order.index("assessment") < order.index("relevance")


def test_research_brief_is_constructible_empty_but_typed():
    brief = ResearchBrief(summary="", confidence=0.0)
    assert brief.grounded_findings == []
    assert brief.brief_ref is None


def test_memory_kind_has_research_finding():
    assert MemoryKind.RESEARCH_FINDING.value == "research_finding"


def test_role_config_accepts_kind_research_and_provider():
    rc = RoleConfig(kind="research", model="anthropic:glm-5.2", provider="fake")
    assert rc.kind == "research"
    assert rc.provider == "fake"


def test_pipeline_config_research_defaults_off_and_bounded():
    cfg = PipelineConfig()
    assert cfg.research_enabled is False
    assert isinstance(cfg.research, ResearchConfig)
    assert cfg.research.max_searches == 5
    assert cfg.research.max_fetches == 10
    assert cfg.research.max_cost_usd == 1.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_research_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'ResearchBrief'`.

- [ ] **Step 3: Add the sub-models and `ResearchBrief` to `src/sdlc/models.py`**

Insert after `AnalysisReport` (near `models.py:264`), so the research contracts sit with the other proposer outputs:

```python
class SubQuestion(BaseModel):
    id: str
    question: str


class ConsultedSource(BaseModel):
    """Judgment before label: assess the source, THEN attach a relevance tag."""

    url: str
    title: str = ""
    assessment: str = ""  # what this source is / is worth
    relevance: str = ""  # e.g. "high" / "peripheral"


class GroundedFinding(BaseModel):
    """quote BEFORE claim (spec §4): commit to a verbatim span actually in the
    fetched bytes, then state what it supports. The verifier (research/verify.py)
    asserts `quote` is a substring of the page fetched THIS run for `source_url`."""

    source_url: str
    quote: str  # verbatim span from bytes fetched this run
    claim: str
    sub_question_ids: list[str] = Field(default_factory=list)


class InferredFinding(BaseModel):
    """reasoning BEFORE claim. `fetched_at` is set only when the lead came from
    the corpus (a recalled lead honestly belongs here, never in grounded)."""

    reasoning: str
    claim: str
    based_on: list[str] = Field(default_factory=list)  # source urls / lead ids
    fetched_at: str | None = None


class Contradiction(BaseModel):
    topic: str
    positions: list[str] = Field(default_factory=list)
    assessment: str = ""
    unresolved: bool = True


class Gap(BaseModel):
    sub_question_id: str
    what_is_missing: str
    why_it_matters: str = ""


class ResearchBrief(BaseModel):
    """FR-107 grounded research brief. Field order is reasoning order (SGR):
    decompose -> gather -> what the bytes say -> what I concluded -> where
    sources disagree -> what I could not answer -> summary -> ref -> confidence.
    tests/test_research_models.py pins the order; a reorder is a regression."""

    sub_questions: list[SubQuestion] = Field(default_factory=list)
    sources_consulted: list[ConsultedSource] = Field(default_factory=list)
    grounded_findings: list[GroundedFinding] = Field(default_factory=list)
    inferred_findings: list[InferredFinding] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    summary: str = ""
    brief_ref: ArtifactRef | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
```

- [ ] **Step 4: Grow `RoleConfig` (`models.py:301-319`)**

Change the `kind` annotation and add `provider`:

```python
kind: Literal["proposer", "harness", "research"] = "harness"
harness: HarnessKind | None = None  # None for proposer/research roles
model: str | None = None  # e.g. "zai-coding-plan/glm-5.2"
# Which search provider a kind=research role uses. None for every other
# kind. 'tavily' requires a reachable TAVILY_API_KEY at boot (validated in
# agents/loader.py); 'fake' is the CI/default opt-out.
provider: Literal["tavily", "fake"] | None = None
```

- [ ] **Step 5: Add `RESEARCH_FINDING` to `MemoryKind` (`models.py:350-353`)**

```python
class MemoryKind(str, Enum):
    STAGE_SUMMARY = "stage_summary"
    GOTCHA = "gotcha"
    GATE_FEEDBACK = "gate_feedback"
    RESEARCH_FINDING = "research_finding"  # verified grounded findings only
```

- [ ] **Step 6: Add `ResearchConfig` and wire it into `PipelineConfig`**

Add `ResearchConfig` just above `PipelineConfig` (near `models.py:430`):

```python
class ResearchConfig(BaseModel):
    """Stage-scoped, per-run research bounds (spec §3). Enforced INSIDE the
    tool functions, not the prompt. Exceeding one raises an ordinary error and
    the shortfall lands in the brief's `gaps`. The first run-level counters in
    the codebase — E-19 remains the general version."""

    max_searches: int = 5
    max_fetches: int = 10
    max_cost_usd: float = 1.0
```

Add these two fields to `PipelineConfig` (alongside `memoization_enabled`, near `models.py:473`):

```python
research: ResearchConfig = Field(default_factory=ResearchConfig)
research_enabled: bool = False  # FR-107: off by default; the
# default pipeline is unchanged
# until a project opts in
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `python -m pytest tests/test_research_models.py -v`
Expected: PASS.

- [ ] **Step 8: Run the full suite — nothing else should move**

Run: `python -m pytest -q`
Expected: PASS. `RoleConfig`/`PipelineConfig` gained optional fields with defaults, so existing construction is unaffected.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/models.py tests/test_research_models.py
git commit -m "feat(research): ResearchBrief SGR cascade + config contracts (FR-107)

Evidence-before-conclusion field ordering (quote before claim), pinned by a
test because ReviewReport drifted into verdict-first with nothing to catch it.
RoleConfig gains kind=research + provider; PipelineConfig gains research bounds
and research_enabled=False; MemoryKind gains research_finding."
```

---

### Task 4: `src/sdlc/research/` core — provider protocol, fake, tavily, verify, fake corpus

Assets are what you edit to change behaviour; code is what makes them work (spec §2). The Tavily client and the verifier are code and live under `src/sdlc/`, mirroring `src/sdlc/memory/`'s protocol + real-client + fake shape. `verify.py` is **pure** — it reads page files and does substring matching, nothing else.

**Files:**
- Create: `src/sdlc/research/__init__.py`
- Create: `src/sdlc/research/protocol.py`
- Create: `src/sdlc/research/fake.py`
- Create: `src/sdlc/research/tavily.py`
- Create: `src/sdlc/research/verify.py`
- Create: `tests/fakes/research_corpus/index.json` + two page files
- Test: `tests/test_research_verify.py`, `tests/test_research_provider.py`

**Interfaces:**
- Produces:
  - `protocol.py`: `SearchHit(url, title, snippet)`, `FetchedPage(url, text)`, `SearchProvider` (ABC with `async search(query, max_results) -> list[SearchHit]`, `async fetch(url) -> FetchedPage`), and `make_provider(name: Literal["tavily","fake"]) -> SearchProvider`.
  - `fake.py`: `FakeProvider` reading `$SDLC_RESEARCH_FAKE_CORPUS` (an `index.json` dir).
  - `tavily.py`: `TavilyProvider` (httpx; reads `TAVILY_API_KEY`).
  - `verify.py`: `page_filename(url) -> str`, `pages_dir(run_id) -> Path`, `normalize(text) -> str`, `Violation(kind, source_url, quote)`, `verify_brief(brief, run_id) -> list[Violation]`, `brief_digest(brief) -> str`.
- Consumes: `ResearchBrief`, `GroundedFinding` from Task 3.

- [ ] **Step 1: Write the failing verifier + provider tests**

Create `tests/test_research_verify.py`:

```python
import hashlib

import pytest

from sdlc.models import GroundedFinding, ResearchBrief
from sdlc.research import verify


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _write_page(run_id: str, url: str, body: str):
    d = verify.pages_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / verify.page_filename(url)).write_text(body, encoding="utf-8")


def test_page_filename_is_sha256_of_url():
    url = "https://example.com/a"
    assert verify.page_filename(url) == hashlib.sha256(url.encode()).hexdigest() + ".txt"


def test_grounded_quote_present_in_fetched_page_passes(runs_root):
    _write_page("r1", "https://x/1", "The library handles retries natively.")
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(
                source_url="https://x/1", quote="handles retries natively", claim="it retries"
            )
        ]
    )
    assert verify.verify_brief(brief, "r1") == []


def test_quote_not_found_is_a_violation(runs_root):
    _write_page("r1", "https://x/1", "Nothing about retries here.")
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(
                source_url="https://x/1", quote="handles retries natively", claim="it retries"
            )
        ]
    )
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["quote_not_found"]


def test_source_never_fetched_is_a_violation(runs_root):
    # No page file written for this url -> recalled-lead demotion (finding 5).
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/never", quote="anything", claim="c")
        ]
    )
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["source_never_fetched"]


def test_whitespace_runs_collapse_but_case_is_preserved(runs_root):
    # HTML extraction mangles whitespace and nothing else (spec §5).
    _write_page("r1", "https://x/1", "handles    retries\n\tnatively")
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="handles retries natively", claim="c")
        ]
    )
    assert verify.verify_brief(brief, "r1") == []
    # Case is NOT normalized: a case-only mismatch still fails.
    brief_case = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="HANDLES RETRIES NATIVELY", claim="c")
        ]
    )
    assert [v.kind for v in verify.verify_brief(brief_case, "r1")] == ["quote_not_found"]


def test_brief_digest_ignores_prose_ordering_and_confidence():
    """Same (source_url, claim) facts -> same digest, regardless of order,
    summary, or confidence (spec §7)."""
    a = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="u1", quote="q1", claim="c1"),
            GroundedFinding(source_url="u2", quote="q2", claim="c2"),
        ],
        summary="one wording",
        confidence=0.9,
    )
    b = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="u2", quote="DIFFERENT", claim="c2"),
            GroundedFinding(source_url="u1", quote="also different", claim="c1"),
        ],
        summary="another wording",
        confidence=0.1,
    )
    assert verify.brief_digest(a) == verify.brief_digest(b)


def test_brief_digest_moves_when_a_fact_changes():
    a = ResearchBrief(grounded_findings=[GroundedFinding(source_url="u1", quote="q", claim="c1")])
    b = ResearchBrief(grounded_findings=[GroundedFinding(source_url="u1", quote="q", claim="c2")])
    assert verify.brief_digest(a) != verify.brief_digest(b)
```

Create `tests/test_research_provider.py`:

```python
import pytest

from sdlc.research.protocol import SearchProvider, make_provider


@pytest.fixture(autouse=True)
def _corpus(monkeypatch):
    from pathlib import Path

    corpus = Path(__file__).resolve().parent / "fakes" / "research_corpus"
    monkeypatch.setenv("SDLC_RESEARCH_FAKE_CORPUS", str(corpus))


@pytest.mark.asyncio
async def test_fake_provider_searches_and_fetches_the_canned_corpus():
    provider: SearchProvider = make_provider("fake")
    hits = await provider.search("retry library", max_results=5)
    assert hits, "canned corpus should answer the seeded query"
    page = await provider.fetch(hits[0].url)
    assert page.url == hits[0].url
    assert page.text.strip()


@pytest.mark.asyncio
async def test_make_provider_rejects_unknown_name():
    with pytest.raises(ValueError):
        make_provider("nope")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_research_verify.py tests/test_research_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.research'`.

- [ ] **Step 3: Create the package and the provider protocol**

Create `src/sdlc/research/__init__.py`:

```python
"""Grounded research (FR-107): providers, verification, and the brief digest.

This package is CODE (a search client, a pure verifier), deliberately outside
agents/research/ which is the ASSET side (instructions, tools, provider choice).
Assets are what you edit to change behaviour; code is what makes them work."""
```

Create `src/sdlc/research/protocol.py`:

```python
"""Search backend abstraction — mirrors memory/protocol.py's protocol + real +
fake shape. Providers are constructed and called INSIDE tool functions (which
run activity-side), never in workflow code."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel


class SearchHit(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""


class FetchedPage(BaseModel):
    url: str
    text: str


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchHit]: ...

    @abstractmethod
    async def fetch(self, url: str) -> FetchedPage: ...


def make_provider(name: Literal["tavily", "fake"]) -> SearchProvider:
    if name == "tavily":
        from .tavily import TavilyProvider

        return TavilyProvider()
    if name == "fake":
        from .fake import FakeProvider

        return FakeProvider()
    raise ValueError(f"unknown research provider {name!r}; known: tavily, fake")
```

- [ ] **Step 4: Create the fake provider and its corpus**

Create `src/sdlc/research/fake.py`:

```python
"""Offline SearchProvider over a canned corpus dir. CI uses this; no test may
require TAVILY_API_KEY. The corpus is a directory with an index.json:

    {"searches": {"<query substring>": ["<url>", ...]},
     "pages":    {"<url>": "<relative filename>.txt"}}

`search` returns hits whose key is a case-insensitive substring of the query."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .protocol import FetchedPage, SearchHit, SearchProvider


def _corpus_dir() -> Path:
    root = os.environ.get("SDLC_RESEARCH_FAKE_CORPUS")
    if not root:
        raise RuntimeError(
            "FakeProvider needs $SDLC_RESEARCH_FAKE_CORPUS pointing at a "
            "corpus directory (index.json + page files)"
        )
    return Path(root)


class FakeProvider(SearchProvider):
    def _index(self) -> dict:
        return json.loads((_corpus_dir() / "index.json").read_text(encoding="utf-8"))

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        idx = self._index()
        q = query.lower()
        hits: list[SearchHit] = []
        for key, urls in idx.get("searches", {}).items():
            if key.lower() in q:
                hits.extend(SearchHit(url=u, title=u, snippet=key) for u in urls)
        return hits[:max_results]

    async def fetch(self, url: str) -> FetchedPage:
        idx = self._index()
        rel = idx.get("pages", {}).get(url)
        if rel is None:
            raise FileNotFoundError(f"no canned page for {url}")
        text = (_corpus_dir() / rel).read_text(encoding="utf-8")
        return FetchedPage(url=url, text=text)
```

Create `tests/fakes/research_corpus/index.json`:

```json
{
  "searches": {
    "retry library": ["https://docs.example.com/retrylib"],
    "retry": ["https://docs.example.com/retrylib"],
    "http client": ["https://docs.example.com/httpx"]
  },
  "pages": {
    "https://docs.example.com/retrylib": "retrylib.txt",
    "https://docs.example.com/httpx": "httpx.txt"
  }
}
```

Create `tests/fakes/research_corpus/retrylib.txt`:

```text
RetryLib is a small library that handles retries natively, with exponential
backoff and jitter. It has a known failure mode: without a cap on attempts it
can retry a poisoned request forever. Prior art: it is modeled on Tenacity.
```

Create `tests/fakes/research_corpus/httpx.txt`:

```text
HTTPX is an HTTP client for Python supporting sync and async. It does not retry
by default; pair it with a retry library for resilience.
```

- [ ] **Step 5: Create the Tavily provider**

Create `src/sdlc/research/tavily.py`:

```python
"""Real SearchProvider over the Tavily HTTP API. Constructed only when a
kind=research role declares provider: tavily; validate_registry fails closed at
boot if TAVILY_API_KEY is unreachable, so this never runs without a key."""

from __future__ import annotations

import os

import httpx

from .protocol import FetchedPage, SearchHit, SearchProvider

_SEARCH_URL = "https://api.tavily.com/search"
_EXTRACT_URL = "https://api.tavily.com/extract"


class TavilyProvider(SearchProvider):
    def __init__(self, api_key: str | None = None, timeout_s: float = 30.0) -> None:
        self._key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self._timeout = timeout_s

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                _SEARCH_URL, json={"api_key": self._key, "query": query, "max_results": max_results}
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchHit(url=r.get("url", ""), title=r.get("title", ""), snippet=r.get("content", ""))
            for r in data.get("results", [])
            if r.get("url")
        ]

    async def fetch(self, url: str) -> FetchedPage:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(_EXTRACT_URL, json={"api_key": self._key, "urls": [url]})
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results") or []
        text = results[0].get("raw_content", "") if results else ""
        return FetchedPage(url=url, text=text)
```

- [ ] **Step 6: Create the pure verifier and digest**

Create `src/sdlc/research/verify.py`:

```python
"""Pure verification of a ResearchBrief against bytes fetched this run, plus the
canonical brief_digest. No network, no provider — just page files and strings.

The rule (spec §5): `grounded` means the quote is a substring of the page fetched
THIS run for its source_url. Whitespace runs collapse to a single space before
comparison; case is preserved. Every further loosening is a hole in the check —
add none without a test proving the specific false-failure it fixes."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..models import ResearchBrief

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace runs to one space; preserve case."""
    return _WS.sub(" ", text).strip()


def page_filename(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest() + ".txt"


def pages_dir(run_id: str) -> Path:
    """runs/<run_id>/research/pages. Root from $SDLC_RUNS_ROOT (default 'runs').
    Resolved activity-side only — the workflow never computes this."""
    root = Path(os.environ.get("SDLC_RUNS_ROOT", "runs"))
    return root / run_id / "research" / "pages"


class Violation(BaseModel):
    kind: Literal["quote_not_found", "source_never_fetched"]
    source_url: str
    quote: str


def verify_brief(brief: ResearchBrief, run_id: str) -> list[Violation]:
    d = pages_dir(run_id)
    violations: list[Violation] = []
    for f in brief.grounded_findings:
        page = d / page_filename(f.source_url)
        if not page.is_file():
            violations.append(
                Violation(kind="source_never_fetched", source_url=f.source_url, quote=f.quote)
            )
            continue
        haystack = normalize(page.read_text(encoding="utf-8"))
        if normalize(f.quote) not in haystack:
            violations.append(
                Violation(kind="quote_not_found", source_url=f.source_url, quote=f.quote)
            )
    return violations


def brief_digest(brief: ResearchBrief) -> str:
    """The brief's contribution to downstream content_key (spec §7): a canonical
    hash of (source_url, claim) pairs only. Prose, ordering, and confidence drop
    out; facts remain. Same facts -> same digest -> clarify's memo hits."""
    pairs = sorted((f.source_url, f.claim) for f in brief.grounded_findings)
    payload = json.dumps(pairs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_research_verify.py tests/test_research_provider.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/research/ tests/test_research_verify.py tests/test_research_provider.py tests/fakes/research_corpus/
git commit -m "feat(research): provider protocol, fake/tavily, pure verifier + digest

verify.py is pure: substring match of a grounded quote against the page fetched
this run, whitespace-collapsed, case-preserved. brief_digest hashes only
(source_url, claim) pairs so identical facts memoize downstream (spec §7).
FakeProvider serves a canned corpus so no test needs TAVILY_API_KEY."
```

---

### Task 5: Registry — `kind: research`, provider validation, the `OPTIONAL_ROLES` seam, `tools/` discovery

Research is the first `OPTIONAL_ROLES` entry (the seam agents-as-folders shipped empty for exactly this). It is a *known* directory so the unknown-directory check keeps biting; this **extends** `KNOWN_ROLES`, it does not weaken the check. `validate_registry` gains a provider rule (not an ADR-6 rule — research reviews nothing). Tools load fails closed at boot, never at import (registry spec finding 3).

**Files:**
- Modify: `src/sdlc/agents/loader.py` (`OPTIONAL_ROLES`, provider validation, `tools/` discovery in `_parse_role`, research branch in `build_agents`)
- Modify: `tests/conftest.py` (`write_registry_dir` grows a valid `research/` tree)
- Test: `tests/test_research_registry.py` (create)

**Interfaces:**
- Consumes: `RoleConfig` (now with `kind="research"`, `provider`), `KNOWN_ROLES`, `RegistryError`, `_parse_role`, `build_agents`, `_load_build` from the shipped loader; `make_provider` from Task 4.
- Produces:
  - `loader.py`: `OPTIONAL_ROLES = frozenset({"research"})`; `validate_registry` gains a `kind == "research"` provider check; `_parse_role` reads and validates `tools/` for a research role, returning them on the `RoleConfig` via a new `RoleConfig.tool_files: list[str]` **path list** (not imported here); `build_agents` gains a `cfg.kind == "research"` branch calling the research `build(model, instructions, model_settings, tool_paths, provider)`.
  - `RoleConfig.tool_files: list[str] = Field(default_factory=list)` in `models.py` — absolute paths to `agents/research/tools/*.py`, populated only for research.

- [ ] **Step 1: Extend `write_registry_dir` in `tests/conftest.py` to include a valid research tree**

Add, after the proposer loop in `write_registry_dir` (before `return root`):

```python
# Optional research role (2026-07-17-research-agent-grounded-briefs).
# A VALID research tree: agent.yaml (kind=research, provider=fake),
# instructions.md, agent.py, and one tool file. Tests perturb one thing.
r = root / "research"
r.mkdir(exist_ok=True)
(r / "agent.yaml").write_bytes(b"kind: research\nmodel: anthropic:glm-5.2\nprovider: fake\n")
(r / "instructions.md").write_bytes(b"research the question")
(r / "agent.py").write_bytes(
    b"from pydantic_ai import Agent\n"
    b"def build(model, instructions, model_settings, tool_paths, provider):\n"
    b"    return Agent(model, name='research_agent',\n"
    b"                 model_settings=model_settings,\n"
    b"                 system_prompt=instructions)\n"
)
(r / "tools").mkdir(exist_ok=True)
(r / "tools" / "web_search.py").write_bytes(
    b"async def web_search(query: str, max_results: int = 5) -> list:\n    return []\n"
)
return root
```

> This makes every existing loader test that calls `write_registry_dir` also exercise a valid research directory. That is intended: the seam is now populated and must stay valid.

- [ ] **Step 2: Write the failing registry test**

Create `tests/test_research_registry.py`:

```python
import pytest

from sdlc.agents.loader import (
    KNOWN_ROLES,
    OPTIONAL_ROLES,
    REQUIRED_ROLES,
    RegistryError,
    load_registry,
)
from tests.conftest import write_registry_dir


def test_research_is_optional_not_required():
    assert "research" in OPTIONAL_ROLES
    assert "research" in KNOWN_ROLES
    assert "research" not in REQUIRED_ROLES


def test_shipped_registry_loads_with_research(monkeypatch, tmp_path):
    """The repo's own agents/ tree loads and includes a research role."""
    roles = load_registry()  # shipped agents/
    assert roles["research"].kind == "research"
    assert roles["research"].provider in ("fake", "tavily")


def test_research_tree_loads_and_carries_tool_paths(tmp_path, monkeypatch):
    root = write_registry_dir(tmp_path / "agents")
    monkeypatch.setenv("SDLC_AGENTS_DIR", str(root))
    roles = load_registry(root)
    r = roles["research"]
    assert r.kind == "research"
    assert r.provider == "fake"
    assert any(p.endswith("web_search.py") for p in r.tool_files)


def test_research_without_provider_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "agent.yaml").write_bytes(
        b"kind: research\nmodel: anthropic:glm-5.2\n"
    )  # no provider
    with pytest.raises(RegistryError, match="provider"):
        load_registry(root)


def test_research_tavily_without_key_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "agent.yaml").write_bytes(
        b"kind: research\nmodel: anthropic:glm-5.2\nprovider: tavily\n"
    )
    with pytest.raises(RegistryError, match="TAVILY_API_KEY"):
        load_registry(root)


def test_research_missing_tools_dir_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    import shutil

    shutil.rmtree(root / "research" / "tools")
    with pytest.raises(RegistryError, match="tools"):
        load_registry(root)


def test_tool_file_with_unannotated_signature_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "tools" / "bad.py").write_bytes(
        b"def bad(query):\n    return []\n"
    )  # no annotations, name==file ok
    with pytest.raises(RegistryError, match="annotat"):
        load_registry(root)


def test_tool_filename_function_mismatch_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "tools" / "mismatch.py").write_bytes(
        b"def other(query: str) -> list:\n    return []\n"
    )
    with pytest.raises(RegistryError, match="mismatch"):
        load_registry(root)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_research_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'OPTIONAL_ROLES'`… actually `OPTIONAL_ROLES` exists but is empty, so the first failure is `test_research_is_optional_not_required` (research not in it).

- [ ] **Step 4: Add `RoleConfig.tool_files` to `src/sdlc/models.py`**

In `RoleConfig`, after `provider` (from Task 3, Step 4), add:

```python
    # Absolute paths to agents/research/tools/*.py, populated by the registry
    # loader for a kind=research role ONLY. Paths, not imported modules: the
    # loader validates them structurally (name/signature) but nothing imports
    # a tool as a side effect of importing roles (registry spec finding 3).
    tool_files: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Populate `OPTIONAL_ROLES` in `src/sdlc/agents/loader.py`**

Replace the `OPTIONAL_ROLES` definition (`loader.py:59`):

```python
# Roles the pipeline can run WITHOUT, but which are still known directories.
# 'research' is the first entry: research_enabled defaults False so the
# pipeline boots without running the stage, but agents/research/ is still a
# KNOWN directory so the unknown-directory check keeps biting. This EXTENDS
# the fail-closed check; it does not weaken it.
OPTIONAL_ROLES: frozenset[str] = frozenset({"research"})
```

- [ ] **Step 6: Add the provider check to `validate_registry`**

In `validate_registry`, append after the harness-reviewer clause and BEFORE `_validate_pipeline_mirror(roles)`:

```python
for name, cfg in roles.items():
    if cfg.kind != "research":
        continue
    if cfg.provider is None:
        raise RegistryError(
            f"role '{name}' is kind=research and must name a provider "
            f"(tavily or fake); ADR-6 does not apply — it reviews nothing"
        )
    if cfg.provider == "tavily" and not os.environ.get("TAVILY_API_KEY"):
        raise RegistryError(
            f"role '{name}' declares provider: tavily but TAVILY_API_KEY is "
            f"not set — fail closed. Use provider: fake for CI/offline."
        )
```

- [ ] **Step 7: Discover and validate `tools/` in `_parse_role`**

In `_parse_role`, inside the `if needs_prompt:` block (research has `kind != "harness"` so `needs_prompt` is True), after the `agent.py` existence check, add:

```python
if cfg.kind == "research":
    tools_dir = d / "tools"
    if not tools_dir.is_dir():
        raise RegistryError(
            f"role '{name}' is kind=research and must carry a tools/ "
            f"directory (it is the only role that may): {tools_dir}"
        )
    tool_files = _validate_tool_files(name, tools_dir)
    cfg = cfg.model_copy(update={"tool_files": tool_files})
```

Add the validator helper near `_load_build` (it uses `ast` for a source-only check — no import, per finding 3):

```python
def _validate_tool_files(role: str, tools_dir: Path) -> list[str]:
    """Structurally validate each tools/*.py WITHOUT importing it: exactly one
    top-level function whose name == the filename stem, with every parameter and
    the return fully annotated. Returns absolute paths. Import happens later, in
    build_agents, only after the whole registry has validated."""
    import ast

    paths: list[str] = []
    for f in sorted(tools_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        stem = f.stem
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not any(fn.name == stem for fn in funcs):
            raise RegistryError(
                f"role '{role}': tool file {f.name} defines no function named "
                f"'{stem}' — the filename is the API (mismatch)"
            )
        fn = next(fn for fn in funcs if fn.name == stem)
        args = fn.args
        params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        unannotated = [a.arg for a in params if a.annotation is None]
        if unannotated or fn.returns is None:
            raise RegistryError(
                f"role '{role}': tool '{stem}' has an unannotated signature "
                f"(params={unannotated}, return_annotated={fn.returns is not None})"
                f" — tool signatures must be fully typed"
            )
        paths.append(str(f.resolve()))
    if not paths:
        raise RegistryError(
            f"role '{role}': tools/ is empty — a research role with no tools cannot fetch anything"
        )
    return paths
```

- [ ] **Step 8: Add the research branch to `build_agents`**

In `build_agents`, replace the loop body's proposer construction so a research role is built through its extended `build` signature. Change:

```python
for name, cfg in roles.items():
    if cfg.kind == "harness":
        continue
    agent = _load_build(name, root / name)(cfg.model, cfg.instructions, model_settings)
```

to:

```python
for name, cfg in roles.items():
    if cfg.kind == "harness":
        continue
    build = _load_build(name, root / name)
    if cfg.kind == "research":
        # Research build takes its tool paths and provider name too. Tool
        # modules are imported HERE — after the whole registry validated
        # (validation precedes import; registry spec finding 3).
        agent = build(cfg.model, cfg.instructions, model_settings, cfg.tool_files, cfg.provider)
    else:
        agent = build(cfg.model, cfg.instructions, model_settings)
```

- [ ] **Step 9: Run the registry tests to verify they pass**

Run: `python -m pytest tests/test_research_registry.py -v`
Expected: PASS.

- [ ] **Step 10: Run the loader + agents suites — the shipped tree must still validate**

Run: `python -m pytest tests/test_agents_registry.py tests/test_agent_folders.py tests/test_registry_mirror.py tests/test_registry_resolution.py tests/test_registry_packaging.py -v`
Expected: PASS. (The shipped `agents/research/` created in Task 6 does not exist yet — so `load_registry()` on the *shipped* tree still has no research dir here and passes; `test_shipped_registry_loads_with_research` in this task's file will FAIL until Task 6 ships the directory. That is expected and called out in Step 11.)

- [ ] **Step 11: Note the one expected red, then commit**

`test_shipped_registry_loads_with_research` asserts the *shipped* `agents/` tree has a research role. It ships in Task 6. Mark it xfail-until-Task-6 so the suite is green:

Add above that test in `tests/test_research_registry.py`:

```python
@pytest.mark.xfail(reason="shipped agents/research/ lands in Task 6",
                   strict=True)
```

Run: `python -m pytest tests/test_research_registry.py -q`
Expected: PASS (with one xfail).

```bash
git add src/sdlc/agents/loader.py src/sdlc/models.py tests/conftest.py tests/test_research_registry.py
git commit -m "feat(research): kind=research in the registry — OPTIONAL_ROLES seam + tools/

research is the first OPTIONAL_ROLES entry: known but not required. Adds a
provider rule to validate_registry (tavily needs TAVILY_API_KEY at boot; fake is
the opt-out), and structural tools/*.py validation that fails closed WITHOUT
importing the modules — import waits for build_agents, after validation."
```

---

### Task 6: The research agent — tool files, budget, page-writing, CodeMode, instructions

Now the asset side ships: `agents/research/`. Four thin tools bind a provider call to a typed signature, enforce the budget, write pages, and return. `CodeMode` wraps them so the fan-out is one `run_code` activity with a shared in-process budget counter. Tools read their config from `ctx.deps` (a serializable `ResearchDeps`), never from a path passed by the workflow.

**Files:**
- Create: `src/sdlc/research/deps.py` (`ResearchDeps`, `Budget`, `BudgetExceeded`)
- Create: `agents/research/agent.yaml`, `agents/research/instructions.md`, `agents/research/agent.py`
- Create: `agents/research/tools/{web_search,fetch_page,read_repo,recall_leads}.py`
- Test: `tests/test_research_tools.py` (create)

**Interfaces:**
- Consumes: `make_provider` (Task 4), `pages_dir`/`page_filename` (Task 4), `CodeMode`, `Agent`, `RunContext`, `RoleConfig.tool_files`/`build_agents` (Task 5).
- Produces:
  - `deps.py`: `Budget(searches, fetches, cost_usd)`, `BudgetExceeded(Exception)`, `ResearchDeps(run_id, provider, max_searches, max_fetches, max_cost_usd, memory_backend, memory_base_url, memory_bank, memory_watermark, budget)`, plus `SEARCH_COST_USD`/`FETCH_COST_USD` constants and `charge(deps, *, search=0, fetch=0)`.
  - Four tool coroutines, each `async def <name>(ctx: RunContext[ResearchDeps], ...) -> ...`.
  - `agents/research/agent.py`: `build(model, instructions, model_settings, tool_paths, provider) -> Agent` — registers the four tools by importing each `tool_paths` module, adds `CodeMode(tools="all")`, and sets `name="research_agent"`, `deps_type=ResearchDeps`, `output_type=ResearchBrief`.

- [ ] **Step 1: Write the failing tools test**

Create `tests/test_research_tools.py`:

```python
import importlib.util
from pathlib import Path

import pytest
from pydantic_ai import RunContext

from sdlc.research.deps import Budget, BudgetExceeded, ResearchDeps

AGENTS_TOOLS = Path(__file__).resolve().parents[1] / "agents" / "research" / "tools"


def _load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"_tool_{name}", AGENTS_TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def _ctx(deps: ResearchDeps) -> RunContext:
    # A minimal RunContext carrying deps is enough for these tools; the tools
    # only read ctx.deps.
    return RunContext(deps=deps, model=None, usage=None, prompt=None)  # type: ignore[arg-type]


@pytest.fixture
def deps(monkeypatch, tmp_path):
    corpus = Path(__file__).resolve().parent / "fakes" / "research_corpus"
    monkeypatch.setenv("SDLC_RESEARCH_FAKE_CORPUS", str(corpus))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return ResearchDeps(
        run_id="r1", provider="fake", max_searches=2, max_fetches=2, max_cost_usd=1.0
    )


@pytest.mark.asyncio
async def test_web_search_returns_hits_and_charges_budget(deps):
    web_search = _load_tool("web_search")
    hits = await web_search(_ctx(deps), "retry library", max_results=5)
    assert hits and hits[0]["url"]
    assert deps.budget.searches == 1


@pytest.mark.asyncio
async def test_fetch_page_writes_the_page_and_charges_budget(deps):
    from sdlc.research.verify import page_filename, pages_dir

    fetch_page = _load_tool("fetch_page")
    url = "https://docs.example.com/retrylib"
    page = await fetch_page(_ctx(deps), url)
    assert "handles retries natively" in page["text"]
    written = pages_dir("r1") / page_filename(url)
    assert written.is_file()
    assert deps.budget.fetches == 1


@pytest.mark.asyncio
async def test_search_budget_cap_raises(deps):
    web_search = _load_tool("web_search")
    await web_search(_ctx(deps), "retry", max_results=1)
    await web_search(_ctx(deps), "retry", max_results=1)
    with pytest.raises(BudgetExceeded):
        await web_search(_ctx(deps), "retry", max_results=1)


@pytest.mark.asyncio
async def test_fetch_budget_cap_raises(deps):
    fetch_page = _load_tool("fetch_page")
    await fetch_page(_ctx(deps), "https://docs.example.com/retrylib")
    await fetch_page(_ctx(deps), "https://docs.example.com/httpx")
    with pytest.raises(BudgetExceeded):
        await fetch_page(_ctx(deps), "https://docs.example.com/retrylib")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_research_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.research.deps'`.

- [ ] **Step 3: Create `src/sdlc/research/deps.py`**

```python
"""Runtime deps for the research agent's tools. Serializable (crosses the
Temporal activity boundary via pydantic_data_converter), so it carries CONFIG
and COUNTERS — never a live provider handle or a filesystem path. The budget
counter is shared in-process across every tool call inside the single run_code
activity CodeMode collapses the fan-out into; that shared-process property is
why CodeMode is required, not optional."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Per-call cost estimates (spec §3). The fake provider is free; these bound a
# real Tavily run. Kept as constants, not config, so the budget math is auditable.
SEARCH_COST_USD = 0.01
FETCH_COST_USD = 0.02


class BudgetExceeded(Exception):
    """A stage-scoped bound was hit. Surfaces to the model as an ordinary error;
    the agent concludes with what it has and records the shortfall in gaps."""


class Budget(BaseModel):
    searches: int = 0
    fetches: int = 0
    cost_usd: float = 0.0


class ResearchDeps(BaseModel):
    run_id: str
    provider: Literal["tavily", "fake"]
    max_searches: int
    max_fetches: int
    max_cost_usd: float
    memory_backend: str = "fake"
    memory_base_url: str = "http://localhost:8088"
    memory_bank: str = "project:default"
    memory_watermark: str | None = None
    budget: Budget = Field(default_factory=Budget)


def charge(deps: ResearchDeps, *, search: int = 0, fetch: int = 0) -> None:
    """Enforce the bounds BEFORE the work, then account for it. Raises
    BudgetExceeded if a cap (count or cost) would be crossed."""
    b = deps.budget
    if search and b.searches + search > deps.max_searches:
        raise BudgetExceeded(f"search budget exhausted ({deps.max_searches} searches)")
    if fetch and b.fetches + fetch > deps.max_fetches:
        raise BudgetExceeded(f"fetch budget exhausted ({deps.max_fetches} fetches)")
    projected = b.cost_usd + search * SEARCH_COST_USD + fetch * FETCH_COST_USD
    if projected > deps.max_cost_usd:
        raise BudgetExceeded(f"cost budget exhausted (${deps.max_cost_usd:.2f})")
    b.searches += search
    b.fetches += fetch
    b.cost_usd = projected
```

- [ ] **Step 4: Create the four tool files**

`agents/research/tools/web_search.py`:

```python
from pydantic_ai import RunContext

from sdlc.research.deps import ResearchDeps, charge
from sdlc.research.protocol import make_provider


async def web_search(ctx: RunContext[ResearchDeps], query: str, max_results: int = 5) -> list[dict]:
    """Search the web for `query`. Charges one search against the per-run
    budget (raises when exhausted). Returns [{url, title, snippet}]."""
    charge(ctx.deps, search=1)
    provider = make_provider(ctx.deps.provider)
    hits = await provider.search(query, max_results)
    return [h.model_dump() for h in hits]
```

`agents/research/tools/fetch_page.py`:

```python
from pydantic_ai import RunContext

from sdlc.research.deps import ResearchDeps, charge
from sdlc.research.protocol import make_provider
from sdlc.research.verify import page_filename, pages_dir


async def fetch_page(ctx: RunContext[ResearchDeps], url: str) -> dict:
    """Fetch `url` and persist its text to runs/<run_id>/research/pages so the
    output validator can verify quotes against bytes fetched THIS run. Charges
    one fetch against the budget. Returns {url, text}."""
    charge(ctx.deps, fetch=1)
    provider = make_provider(ctx.deps.provider)
    page = await provider.fetch(url)
    d = pages_dir(ctx.deps.run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / page_filename(url)).write_text(page.text, encoding="utf-8")
    return page.model_dump()
```

`agents/research/tools/read_repo.py`:

```python
import os
from pathlib import Path

from pydantic_ai import RunContext

from sdlc.research.deps import ResearchDeps


async def read_repo(ctx: RunContext[ResearchDeps], path: str) -> str:
    """Read a text file from the project repo to ground research in the code
    that exists. Rooted at $SDLC_RESEARCH_REPO_ROOT (default cwd); path
    traversal outside the root is refused. NOT charged against the search/fetch
    budget — local reads are free and bounded by the model's own restraint."""
    root = Path(os.environ.get("SDLC_RESEARCH_REPO_ROOT", ".")).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"refusing to read outside the repo root: {path}")
    if not target.is_file():
        return f"[no such file: {path}]"
    return target.read_text(encoding="utf-8", errors="replace")
```

`agents/research/tools/recall_leads.py`:

```python
from pydantic_ai import RunContext

from sdlc.memory.activities import _backend
from sdlc.research.deps import ResearchDeps


async def recall_leads(
    ctx: RunContext[ResearchDeps], query: str, max_results: int = 5
) -> list[str]:
    """Recall prior research findings from the corpus as LEADS — never as truth.
    Watermark-pinned, filtered to stage=research. A recalled lead placed in
    grounded_findings fails the verifier's source-never-fetched check by
    construction (spec finding 5); to promote a lead, re-fetch it."""
    backend = _backend(ctx.deps.memory_base_url, ctx.deps.memory_backend)
    snap = await backend.recall(
        ctx.deps.memory_bank, query, {"stage": "research"}, ctx.deps.memory_watermark
    )
    return snap.items[:max_results]
```

- [ ] **Step 5: Create `agents/research/agent.py`**

```python
import importlib.util

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from pydantic_ai_harness import CodeMode

from sdlc.models import ResearchBrief
from sdlc.research.deps import ResearchDeps


def _import_tool(path: str):
    """Import one agents/research/tools/<name>.py by PATH under a private
    module name and return its <name> function (== the file stem)."""
    from pathlib import Path

    stem = Path(path).stem
    spec = importlib.util.spec_from_file_location(f"_sdlc_tool_{stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, stem)


def build(
    model: str,
    instructions: str,
    model_settings: ModelSettings,
    tool_paths: list[str],
    provider: str,
) -> Agent:
    """The research role: a proposer with four tools and Code Mode. Uniquely
    among roles it receives tool_paths and provider — supplied by build_agents
    AFTER the whole registry validated (validation precedes import)."""
    agent = Agent(
        model,
        name="research_agent",  # Temporal activity name — NEVER rename
        deps_type=ResearchDeps,
        output_type=ResearchBrief,
        model_settings=model_settings,
        system_prompt=instructions,
        capabilities=[CodeMode(tools="all")],
    )
    for path in tool_paths:
        agent.tool(_import_tool(path))  # @agent.tool: each takes RunContext
    return agent
```

- [ ] **Step 6: Create `agents/research/agent.yaml`**

```yaml
kind: research
model: anthropic:glm-5.2
provider: fake
```

> `provider: fake` ships by default so boot and CI never need `TAVILY_API_KEY`. An operator flips it to `tavily`, sets the key, and sets `research_enabled: true` on their `PipelineConfig`.

- [ ] **Step 7: Create `agents/research/instructions.md` (no trailing newline)**

```markdown
You are the research agent. Given a feature idea, produce a grounded ResearchBrief.

Method (schema-guided; the brief's field order is your reasoning order):
1. Decompose the idea into sub_questions.
2. Use `recall_leads` to see where prior runs looked — these are LEADS, not
   truth. To use a lead as evidence you must re-fetch it this run.
3. Use `web_search` to find sources, then `fetch_page` to read them. Prefer
   fetching over asserting from memory. Use `read_repo` to ground claims in the
   code that already exists.
4. For every claim you present as grounded, put a VERBATIM `quote` from a page
   you fetched THIS run BEFORE the `claim` it supports. A quote that is not a
   substring of the fetched bytes will be rejected and you will be asked to fix
   it or move the claim to inferred_findings.
5. Anything you concluded without a fetched quote goes in inferred_findings,
   with your reasoning first. Where sources disagree, record a contradiction.
   Where you could not answer a sub_question, record a gap.
6. Keep within the search/fetch budget. If you run out, conclude with what you
   have and record the shortfall as gaps — do not fabricate.

Do your fetching with the tools inside a single run_code script where you can:
search, fetch the promising results in parallel, then read what you fetched.
```

- [ ] **Step 8: Run the tools test to verify it passes**

Run: `python -m pytest tests/test_research_tools.py -v`
Expected: PASS.

- [ ] **Step 9: Confirm the shipped registry now loads the research agent end to end**

Run: `python -m pytest tests/test_research_registry.py -q`
Expected: PASS — and the previously-xfail `test_shipped_registry_loads_with_research` now **XPASS**. Because it was marked `strict=True`, an XPASS fails the run. Remove the `@pytest.mark.xfail(...)` decorator added in Task 5 Step 11 (the directory now ships), then re-run.

Run: `python -m pytest tests/test_research_registry.py tests/test_worker_registration.py -q`
Expected: PASS.

- [ ] **Step 10: Confirm the agent constructs at import (boot smoke)**

Run: `python -c "from sdlc.agents import roles; print(roles.REGISTRY['research'].kind)"`
Expected: prints `research` with no import error — proving the research folder validates, its tools import, and `CodeMode` binds at boot. (If this raises, the Task 1 finding B was optimistic — stop and reconcile.)

- [ ] **Step 11: Commit**

```bash
git add src/sdlc/research/deps.py agents/research/ tests/test_research_tools.py tests/test_research_registry.py
git commit -m "feat(research): the research agent — four tools, budget, CodeMode

agents/research/ ships: agent.yaml (provider: fake), instructions.md, agent.py,
and four thin tools that bind a provider call to a typed signature, enforce the
per-run budget, and write fetched pages to runs/<run_id>/research/pages. Code
Mode collapses the fan-out into one run_code activity so the budget counter is
shared in-process. Deps carry config + counters, never a live handle."
```

---

### Task 7: Grounding — output validator, corpus retention, and the invariant

The rule enforced (spec §5): `grounded` means verified against bytes fetched this run. The `@agent.output_validator` (proven activity-side in Task 1) reads the page files and raises `ModelRetry` on any violation; after retries the stage fails closed. Only *verified* `grounded_findings` are retained to the corpus, so poisoning cannot compound; a recalled lead placed in `grounded_findings` fails *source-never-fetched* automatically (finding 5) — no demotion mechanism is written.

**Files:**
- Modify: `agents/research/agent.py` (add the output validator)
- Create: `src/sdlc/research/retain.py` (`verified_findings_to_retain`)
- Test: `tests/test_research_grounding.py` (create)

**Interfaces:**
- Consumes: `verify_brief`, `Violation`, `pages_dir`, `page_filename` (Task 4); `ResearchDeps` (Task 6); `ModelRetry`, `RunContext`.
- Produces:
  - `agent.py` gains an `@agent.output_validator` reading `ctx.deps.run_id`.
  - `retain.py`: `verified_findings_to_retain(brief, run_id) -> list[RetainItem]` — one `RetainItem(kind=MemoryKind.RESEARCH_FINDING, ...)` per finding that passes verification, tagged `metadata={"stage": "research", "source_url": ...}`.

- [ ] **Step 1: Write the failing grounding test**

Create `tests/test_research_grounding.py`:

```python
from pathlib import Path

import pytest

from sdlc.models import GroundedFinding, MemoryKind, ResearchBrief
from sdlc.research import verify
from sdlc.research.retain import verified_findings_to_retain


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _write_page(run_id, url, body):
    d = verify.pages_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / verify.page_filename(url)).write_text(body, encoding="utf-8")


def test_only_verified_findings_are_retained(runs_root):
    _write_page("r1", "https://x/1", "quote one is here")
    # url /2 is NEVER fetched -> a recalled lead masquerading as grounded.
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="quote one is here", claim="c1"),
            GroundedFinding(source_url="https://x/2", quote="never fetched", claim="c2"),
        ]
    )
    items = verified_findings_to_retain(brief, "r1")
    assert len(items) == 1
    assert items[0].kind is MemoryKind.RESEARCH_FINDING
    assert items[0].metadata["stage"] == "research"
    assert items[0].metadata["source_url"] == "https://x/1"


def test_recalled_lead_in_grounded_fails_verification(runs_root):
    """Demotion needs no mechanism (finding 5): a lead that was never fetched
    this run has no page file, so it fails source-never-fetched."""
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/recalled", quote="from memory", claim="c")
        ]
    )
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["source_never_fetched"]
    assert verified_findings_to_retain(brief, "r1") == []


@pytest.mark.asyncio
async def test_output_validator_raises_model_retry_on_violation(runs_root, monkeypatch):
    """The agent's validator turns a violation into a ModelRetry so the model
    corrects the quote or moves the claim to inferred."""
    from pydantic_ai import ModelRetry

    # Import the shipped agent's validator via its module.
    import importlib.util

    agent_py = Path(__file__).resolve().parents[1] / "agents" / "research" / "agent.py"
    spec = importlib.util.spec_from_file_location("_research_agent_mod", agent_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    brief = ResearchBrief(
        grounded_findings=[GroundedFinding(source_url="https://x/none", quote="x", claim="c")]
    )
    with pytest.raises(ModelRetry):
        await mod._verify_grounding(_ctx_with_run_id("r1"), brief)


def _ctx_with_run_id(run_id):
    from pydantic_ai import RunContext
    from sdlc.research.deps import ResearchDeps

    deps = ResearchDeps(
        run_id=run_id, provider="fake", max_searches=1, max_fetches=1, max_cost_usd=1.0
    )
    return RunContext(deps=deps, model=None, usage=None, prompt=None)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_research_grounding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.research.retain'`.

- [ ] **Step 3: Create `src/sdlc/research/retain.py`**

```python
"""What the research stage writes to the corpus: VERIFIED grounded findings
only. Nothing unverified enters memory, so recall can never launder a false
claim into ground truth. Findings become leads, not grounded claims — recall
must re-fetch to re-ground (spec §6)."""

from __future__ import annotations

from ..models import MemoryKind, ResearchBrief, RetainItem
from .verify import verify_brief


def verified_findings_to_retain(
    brief: ResearchBrief, run_id: str, bank: str = "project:default"
) -> list[RetainItem]:
    bad = {(v.source_url, v.quote) for v in verify_brief(brief, run_id)}
    items: list[RetainItem] = []
    for f in brief.grounded_findings:
        if (f.source_url, f.quote) in bad:
            continue
        items.append(
            RetainItem(
                kind=MemoryKind.RESEARCH_FINDING,
                bank=bank,
                text=f"{f.claim} — {f.source_url}",
                metadata={"stage": "research", "source_url": f.source_url},
            )
        )
    return items
```

- [ ] **Step 4: Add the output validator to `agents/research/agent.py`**

In `build`, after the tool-registration loop and before `return agent`, add:

```python
@agent.output_validator
async def _verify_grounding(ctx, brief: ResearchBrief) -> ResearchBrief:
    # Runs activity-side under TemporalAgent (Task 1 finding A), where
    # reading the page files is legal I/O. A violation becomes a ModelRetry:
    # the model corrects the quote or moves the claim to inferred_findings.
    # After retries are exhausted the stage fails closed (spec §5).
    from sdlc.research.verify import verify_brief

    violations = verify_brief(brief, ctx.deps.run_id)
    if violations:
        lines = "\n".join(f"- {v.kind}: {v.source_url}: {v.quote!r}" for v in violations)
        raise ModelRetry(
            "These grounded_findings are not verified against bytes you "
            "fetched this run. Fix the quote to a verbatim span from the "
            "fetched page, or move the claim to inferred_findings:\n" + lines
        )
    return brief
```

Add the import at the top of `agents/research/agent.py`:

```python
from pydantic_ai import Agent, ModelRetry
```

(replacing the existing `from pydantic_ai import Agent`). The `_verify_grounding` reference in the test resolves because `build` is called at import for the shipped agent — but the test imports the *module* and calls `mod._verify_grounding`, so hoist the validator to a module-level function the test can reach:

Refactor: define `_verify_grounding` at module scope (taking `ctx, brief`) and register it inside `build`:

```python
async def _verify_grounding(ctx, brief: ResearchBrief) -> ResearchBrief:
    from sdlc.research.verify import verify_brief

    violations = verify_brief(brief, ctx.deps.run_id)
    if violations:
        lines = "\n".join(f"- {v.kind}: {v.source_url}: {v.quote!r}" for v in violations)
        raise ModelRetry(
            "These grounded_findings are not verified against bytes you fetched "
            "this run. Fix the quote to a verbatim span from the fetched page, "
            "or move the claim to inferred_findings:\n" + lines
        )
    return brief
```

and inside `build`, after the tool loop:

```python
    agent.output_validator(_verify_grounding)
    return agent
```

- [ ] **Step 5: Run the grounding test to verify it passes**

Run: `python -m pytest tests/test_research_grounding.py -v`
Expected: PASS.

- [ ] **Step 6: Run the research suite + boot smoke**

Run: `python -m pytest tests/test_research_*.py -q && python -c "from sdlc.agents import roles; print('boot ok', roles.REGISTRY['research'].provider)"`
Expected: PASS, then `boot ok fake`.

- [ ] **Step 7: Commit**

```bash
git add agents/research/agent.py src/sdlc/research/retain.py tests/test_research_grounding.py
git commit -m "feat(research): output validator enforces grounding; corpus keeps verified only

@agent.output_validator (activity-side, per the Task 1 spike) verifies every
grounded quote against bytes fetched this run and raises ModelRetry on a
violation; after retries the stage fails closed. Only verified findings are
retained as research_finding leads, so a recalled lead in grounded_findings
fails source-never-fetched by construction — demotion needs no mechanism."
```

---

### Task 8: Wire the research stage into the workflow

The stage: before `clarify`, human-gated through the existing `_gate`, **not** memoized, retains verified findings to the corpus, and contributes `brief_digest` to `clarify`'s `content_key` so memoization survives (finding 3). `research` joins `STAGE_ROLES`/`STAGE_MODELS`/`PROMPT_SHAS` (records only). Everything is behind `cfg.research_enabled`.

**Files:**
- Modify: `src/sdlc/agents/roles.py` (`STAGE_ROLES` gains `research`; construct `research_agent`/`t_research`; append to `ALL_TEMPORAL_AGENTS`; make the stage maps tolerant of an absent optional role)
- Modify: `src/sdlc/workflows/feature.py` (import `t_research`; run the stage; feed `brief_digest` into clarify)
- Modify: `src/sdlc/worker.py` (nothing — `ALL_TEMPORAL_AGENTS` already flows through)
- Test: `tests/test_research_stage_wiring.py` (create), and extend `tests/test_stage_models.py`

**Interfaces:**
- Consumes: `t_research` (roles.py), `ResearchDeps` (Task 6), `verified_findings_to_retain` (Task 7), `brief_digest` (Task 4).
- Produces:
  - `roles.py`: `research_agent`, `t_research` (module-level); `STAGE_ROLES["research"] = "research"`.
  - `feature.py`: a `_research` stage block in `run()` producing `brief` and `brief_digest_val: str`, threaded into clarify's `_cached_stage` input as `idea.model_dump_json() + brief_digest_val`.

- [ ] **Step 1: Extend `tests/test_stage_models.py`**

Append:

```python
def test_research_is_a_stage_but_optional():
    from sdlc.agents import roles

    assert roles.STAGE_ROLES["research"] == "research"
    # Present in the shipped tree, so it resolves a model + prompt sha.
    assert "research" in roles.STAGE_MODELS
    assert "research" in roles.PROMPT_SHAS
```

- [ ] **Step 2: Write the failing stage-wiring test**

Create `tests/test_research_stage_wiring.py`:

```python
import ast
from pathlib import Path

FEATURE_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "feature.py"


def _run_method_src() -> str:
    tree = ast.parse(FEATURE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            return ast.unparse(node)
    raise AssertionError("run() not found")


def test_research_stage_is_guarded_by_research_enabled():
    src = _run_method_src()
    assert "cfg.research_enabled" in src


def test_research_feeds_brief_digest_into_clarify_key():
    """The FR-103 fix (finding 3): clarify's memo input carries brief_digest,
    so a run that finds new facts invalidates clarify (and downstream), while
    identical facts still hit."""
    src = _run_method_src()
    assert "brief_digest" in src
    # clarify's cached-stage input is idea + the digest, not idea alone.
    assert "idea.model_dump_json() + " in src


def test_research_stage_is_not_memoized():
    """A served memo means pages were not fetched this run (finding 4). The
    research producer must not be wrapped in _cached_stage."""
    src = _run_method_src()
    # crude but effective: no _cached_stage call names "research".
    assert "_cached_stage(\n" not in src or '"research"' not in src
    assert '"research"' not in src.split("_cached_stage")[1] if "_cached_stage" in src else True


def test_research_retains_verified_findings():
    src = _run_method_src()
    assert "verified_findings_to_retain" in src
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_research_stage_wiring.py tests/test_stage_models.py -v`
Expected: FAIL — `test_research_is_a_stage_but_optional` and the wiring asserts fail (research not yet in `STAGE_ROLES`, not yet wired).

- [ ] **Step 4: Wire `roles.py`**

Add `research` to `STAGE_ROLES` (after `merge_verdict`):

```python
    "merge_verdict": "merge_verdict",
    "research": "research",             # optional; present iff the folder ships
```

Make the two derived maps tolerant of an absent optional role (replace the `STAGE_MODELS` and `_STAGE_PROMPTS` comprehensions):

```python
STAGE_MODELS: dict[str, str] = {
    stage: _model(role) for stage, role in STAGE_ROLES.items() if role in REGISTRY
}

_STAGE_PROMPTS: dict[str, str] = {
    stage: REGISTRY[role].instructions
    for stage, role in STAGE_ROLES.items()
    if role in REGISTRY and REGISTRY[role].instructions is not None
}
```

Add `REGISTRY` is already imported? It is defined in this module. Also import nothing new. Then construct the research agent and its temporal wrapper (after the `devops_agent` line, ~`roles.py:54`):

```python
# Optional research agent (2026-07-17). Present iff agents/research/ ships,
# which it does; the STAGE runs only under cfg.research_enabled (feature.py).
research_agent = AGENTS.get("research")
```

And after the `t_devops` line (~`roles.py:97`):

```python
t_research = (
    TemporalAgent(research_agent, activity_config=AGENT_ACTIVITY_CONFIG)
    if research_agent is not None
    else None
)
```

Append the research activities to `ALL_TEMPORAL_AGENTS` conditionally (replace the list literal):

```python
ALL_TEMPORAL_AGENTS = [
    t_clarify,
    t_architect,
    t_planner,
    t_qa,
    t_reviewer,
    t_analyst,
    t_merge_verdict,
    t_devops,
]
if t_research is not None:
    ALL_TEMPORAL_AGENTS.append(t_research)
```

- [ ] **Step 5: Import the research pieces into `feature.py`**

Extend the `..agents.roles` import (`feature.py:25-28`) to add `t_research`:

```python
from ..agents.roles import (
    PROMPT_SHAS,
    STAGE_MODELS,
    t_analyst,
    t_architect,
    t_clarify,
    t_merge_verdict,
    t_planner,
    t_qa,
    t_research,
    t_reviewer,
)
```

Add two imports inside the `imports_passed_through()` block: `brief_digest` and `verified_findings_to_retain` and `ResearchDeps`, and `ResearchBrief`:

```python
    from ..research.verify import brief_digest
    from ..research.retain import verified_findings_to_retain
    from ..research.deps import ResearchDeps
```

Add `ResearchBrief` to the `..models` import list.

- [ ] **Step 6: Insert the research stage in `run()` before CLARIFY**

Immediately before the `# 1. CLARIFY` block (`feature.py:632`), insert:

```python
# 0. RESEARCH (FR-107) — optional, human-gated, NOT memoized. A served
# memo means pages were not fetched this run, so a brief cannot be
# cached (spec finding 4). The brief contributes only its canonical
# digest to downstream keys (finding 3), never its prose.
brief_digest_val = ""
if cfg.research_enabled and t_research is not None:
    self._status = "researching"
    _r_started = workflow.now()
    deps = ResearchDeps(
        run_id=workflow.info().workflow_id,
        provider=cfg.roles.get("research").provider if cfg.roles.get("research") else "fake",
        max_searches=cfg.research.max_searches,
        max_fetches=cfg.research.max_fetches,
        max_cost_usd=cfg.research.max_cost_usd,
        memory_backend=cfg.memory.backend,
        memory_base_url=cfg.memory.base_url,
        memory_bank=cfg.memory.project_bank,
        memory_watermark=self._memory_watermark,
    )
    brief: ResearchBrief = (await t_research.run(idea.model_dump_json(), deps=deps)).output
    brief_digest_val = brief_digest(brief)
    gate = await self._gate("research", cfg)
    if not gate.approved:
        return "rejected:research"
    for item in verified_findings_to_retain(
        brief, workflow.info().workflow_id, bank=cfg.memory.project_bank
    ):
        await self._retain(cfg, item.kind, item.bank, item.text, item.metadata)
    await self._record(
        cfg,
        self._stage_record(
            cfg,
            stage="research",
            role="research",
            started=_r_started,
            ended=workflow.now(),
            quality_score=None,
            judge="grounding",
            outcome=BenchmarkOutcome.PASS,
            model=STAGE_MODELS.get("research", "unknown"),
        ),
    )
```

> `provider` on `cfg.roles["research"]` — the workflow's `PipelineConfig.roles` mirrors only harness roles, so `cfg.roles.get("research")` is normally `None` and the provider defaults to `"fake"`. A project that wants Tavily sets it on its own `PipelineConfig`. The registry's `agents/research/agent.yaml` provider governs the *agent*; this deps.provider governs the *tool calls* — keep them the same in production.

- [ ] **Step 7: Feed `brief_digest` into clarify's memo key**

Change clarify's `_cached_stage` input (`feature.py:645-647`) from `idea.model_dump_json()` to include the digest:

```python
reqs, _ = await self._cached_stage(
    cfg, "clarify", idea.model_dump_json() + brief_digest_val, ClarifiedRequirements, _run_clarify
)
```

(`brief_digest_val` is `""` when research is disabled, so the key is byte-identical to today for non-research runs — no cache invalidation for existing pipelines.)

- [ ] **Step 8: Run the wiring tests**

Run: `python -m pytest tests/test_research_stage_wiring.py tests/test_stage_models.py -v`
Expected: PASS.

- [ ] **Step 9: Keep factory purity green and run the full suite**

Run: `python -m pytest tests/test_factory_purity.py -q && python -m pytest -q`
Expected: PASS. `test_factory_purity` must stay green — the research block adds no unguarded `record`/`judge` calls (it goes through `_record`), and does no workflow-context file I/O (fetching/verification are in the agent's activities).

- [ ] **Step 10: Add an offline e2e (research → clarify) with fakes**

Create `tests/test_research_e2e.py`:

```python
"""research -> clarify through a time-skipping worker with fake agents. Proves
the stage runs, gates, and hands off to clarify without a live provider."""

from __future__ import annotations

import uuid

import pytest
from temporalio import workflow
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.models import (
    ClarifiedRequirements,
    GateDecision,
    GateOutcome,
    IdeaBrief,
    GatePolicy,
    GateConfig,
    PipelineConfig,
    ProjectMode,
    ResearchBrief,
)

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities
    from tests.fakes.fake_activities import ALL_FAKE_ACTIVITIES  # see note

_RESEARCH = ResearchBrief(summary="found nothing external", confidence=0.5)
_REQS = ClarifiedRequirements(
    summary="clear",
    functional_requirements=["fr"],
    non_functional_requirements=[],
    out_of_scope=[],
    open_questions=[],
)


@pytest.mark.asyncio
async def test_research_stage_runs_and_hands_off(monkeypatch):
    cfg = PipelineConfig(
        research_enabled=True,
        gates={
            "research": GateConfig(policy=GatePolicy.OFF),
            "architecture": GateConfig(policy=GatePolicy.OFF),
            "plan": GateConfig(policy=GatePolicy.OFF),
        },
    )
    # (Stop after clarify by giving a plan with no tasks via a fake planner, or
    # assert on status; keep the assertion minimal — the point is the research
    # stage does not crash and clarify receives control.)
    ...
```

> **Implementer note:** model this on the existing `tests/test_e2e_greenfield.py` — reuse its fake-activity registration and fake-agent list, adding `("research_agent", ResearchBrief, _RESEARCH)` to the fake-agent specs. If a full run-to-completion e2e is heavier than this increment needs, assert only that the workflow advances **past** research to `clarifying`/`architecting` (via the `status` query) with `research_enabled=True`. Keep it offline; no `TAVILY_API_KEY`.

Run: `python -m pytest tests/test_research_e2e.py -v`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add src/sdlc/agents/roles.py src/sdlc/workflows/feature.py tests/test_research_stage_wiring.py tests/test_stage_models.py tests/test_research_e2e.py
git commit -m "feat(research): wire the research stage into the pipeline (FR-107)

research runs before clarify under cfg.research_enabled, human-gated, NOT
memoized. It retains verified findings to the corpus and contributes only its
canonical brief_digest to clarify's content_key — so identical facts memoize
and new facts invalidate clarify and everything downstream (finding 3)."
```

---

### Task 9: The architect research toolset — one core, second entry point

The spec's second entry point and explicitly **the last task**: `architect_agent` gains a `research(question) -> ResearchBrief` tool sharing the same per-run budget counter, so the architect can consult research mid-run. It ships last so the stage is built and benchmarked before an architect can call it.

**Files:**
- Modify: `agents/architect/agent.py` (add the `research` tool)
- Modify: `src/sdlc/research/__init__.py` or a new `src/sdlc/research/toolset.py` (`research_subquery`)
- Test: `tests/test_architect_research_tool.py` (create)

**Interfaces:**
- Consumes: the shipped `research_agent`/`t_research` and `ResearchDeps` budget; `brief_digest`.
- Produces: `src/sdlc/research/toolset.py`: `async def research_subquery(deps: ResearchDeps, question: str) -> ResearchBrief` — runs the research agent on a sub-question with the SAME `deps` object (shared budget), returning the (validated) brief. The architect tool wraps it, passing the architect run's `ctx.deps`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_architect_research_tool.py`:

```python
import ast
from pathlib import Path

ARCHITECT_PY = Path(__file__).resolve().parents[1] / "agents" / "architect" / "agent.py"


def test_architect_agent_registers_a_research_tool():
    src = ARCHITECT_PY.read_text(encoding="utf-8")
    assert "research" in src
    # A tool named research is registered on the agent.
    tree = ast.parse(src)
    names = {
        n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "research" in names


def test_research_subquery_shares_the_budget_object():
    """SGR Routing: a mid-run architect research call draws down the SAME
    per-run budget, so it cannot exceed the run's total by opening a second
    counter."""
    import inspect

    from sdlc.research import toolset

    sig = inspect.signature(toolset.research_subquery)
    assert list(sig.parameters)[0] == "deps"  # the shared ResearchDeps
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_architect_research_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.research.toolset'`.

- [ ] **Step 3: Create `src/sdlc/research/toolset.py`**

```python
"""Second research entry point (spec §8): the architect consults research
mid-run via a tool, drawing down the SAME per-run budget as the stage would.
One core (the research agent), two callers (the stage and this tool)."""

from __future__ import annotations

from ..models import ResearchBrief
from .deps import ResearchDeps


async def research_subquery(deps: ResearchDeps, question: str) -> ResearchBrief:
    """Run the research agent on one sub-question with a shared budget. Imported
    lazily so architect/agent.py stays importable without constructing the
    research agent at its own import time."""
    from sdlc.agents.roles import t_research

    if t_research is None:
        raise RuntimeError(
            "research agent is not available (agents/research/ "
            "missing) — cannot service an architect research call"
        )
    return (await t_research.run(question, deps=deps)).output
```

- [ ] **Step 4: Add the `research` tool to `agents/architect/agent.py`**

Read the current `agents/architect/agent.py` first (it follows the standard `build(model, instructions, model_settings)` shape). Inside `build`, after constructing the architect `Agent` and before `return agent`, register the tool. The architect's `deps_type` is currently unset — set it to `ResearchDeps` so the tool can share the budget, and default the architect run's deps at the call site (the workflow passes them, or `None` disables the tool path):

```python
from pydantic_ai import Agent, RunContext

from sdlc.research.deps import ResearchDeps
from sdlc.models import ResearchBrief


# inside build(...):
    agent = Agent(
        model,
        name="architect_agent",         # unchanged Temporal activity name
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,   # unchanged
        model_settings=model_settings,
        system_prompt=instructions,
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str
                       ) -> ResearchBrief:
        """Consult grounded research on a sub-question. Draws down this run's
        shared research budget (SGR Routing: local vs. web)."""
        from sdlc.research.toolset import research_subquery
        return await research_subquery(ctx.deps, question)

    return agent
```

> **Constraint:** do not change `name="architect_agent"` or `output_type=ArchitectureSpec` — both are shipped invariants (Temporal activity name; the `ImplementationPlan`-feeding contract). Setting `deps_type` is additive: the existing architect stage call in `feature.py` passes no deps today, so keep the architect tool guarded — if `ctx.deps` is `None` the tool should not be invoked. Since the model only calls `research` when it chooses to, and the workflow's architect stage currently runs without `research_enabled` deps, wire the architect stage to pass a `ResearchDeps` only when `cfg.research_enabled` (mirroring the stage), else the model has no reason/means to call it. Add that deps pass-through in `_run_architect` analogously to Task 8's stage block; keep it minimal and behind `cfg.research_enabled`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_architect_research_tool.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite + boot smoke**

Run: `python -m pytest -q && python -c "from sdlc.agents import roles; print('ok')"`
Expected: PASS, `ok`. Confirm `test_factory_purity.py` and the architect's own tests (`test_prompt_migration.py`, `test_agent_folders.py`) still pass — the architect agent name and output type are unchanged.

- [ ] **Step 7: Commit**

```bash
git add agents/architect/agent.py src/sdlc/research/toolset.py tests/test_architect_research_tool.py
git commit -m "feat(research): architect can consult research mid-run, shared budget

Second entry point (spec §8), shipped last so the stage is built and
benchmarked first. architect_agent gains a research(question) tool that draws
down the SAME per-run ResearchDeps budget — one core research agent, two
callers. Guarded behind research_enabled."
```

---

### Task 10: Roadmap amendments

The tracker records what we've decided to build; this increment changes several entries. Docs-only, shipped last so the marks reflect landed code.

**Files:**
- Modify: `ROADMAP.md` — §1 (stage count), §2 (FR-107, FR-103, FR-701, FR-703), §3 NFR-5, §7 (finding 7), §8 item 4 (E-18 ranking), §9.1, §9.4 E-18

- [ ] **Step 1: §1 — add the `research` stage, unchecked, and re-count**

```markdown
- [ ] **research** (FR-107) — grounded brief before clarify. The DAG is now 15
  stages; **8 of 15 stages live** (research is scaffolded, off by default).
```

- [ ] **Step 2: §2 — FR-107, FR-103, FR-701, FR-703**

```markdown
- [ ] **FR-107 (new scope)** grounded research stage — `ResearchBrief`, quote-verified against bytes fetched this run, off by default (`research_enabled`). Landed behind the PRD amendment adding FR-107; `2026-07-17-research-agent-grounded-briefs`.
```

```markdown
- [x] **FR-103** memoization … — `brief_digest` keeps memoization alive once a non-memoized stage (research) feeds memoized ones: the brief contributes only a canonical (source_url, claim) digest to `content_key`, so identical facts hit and new facts invalidate clarify/architect/planner.
```

```markdown
- [ ] **FR-701** run-level budgets — research ships the FIRST run-level counters (`max_searches`/`max_fetches`/`max_cost_usd`), stage-scoped and enforced inside the tools; E-19 remains the general version.
```

```markdown
- [ ] **FR-703** egress policy — **research is the pipeline's first outbound egress, and it arrives before the egress policy.** Still env-allowlist only; no `pre_tool` hook, no egress tier. This spec is E-18's first consumer, not its implementation.
```

- [ ] **Step 3: §3 NFR-5 / §9.4 E-18 — raise E-18's ranking**

```markdown
- **E-18** harness/egress containment — **re-ranked up.** §8 item 4 ranked it fourth on the strength of `pre_tool`; an unpoliced outbound egress (research, FR-703) is a second, independent argument. The research stage fetches arbitrary URLs through a provider with only an env allowlist between it and the worker's network.
```

- [ ] **Step 4: §7 — record finding 7 as its own item**

```markdown
- **ReviewReport / MergeVerdict SGR ordering (found in the research spec).**
  `ReviewReport` is `approve → findings → confidence` — the reviewer commits to a
  verdict before writing a finding, contradicting `REVIEWER_PROMPT`'s "set
  approve to false if ANY finding is critical/high". `MergeVerdict` rates its own
  confidence two fields before listing concerns. `AnalysisReport`/`ArchitectureSpec`
  are already evidence-first. A one-line-per-contract fix; its own change and its
  own benchmark run (out of scope for the research increment).
```

- [ ] **Step 5: §9.1 — research is the first role a folder *describes***

```markdown
- Research is the first role a folder *describes* rather than decorates
  (instructions + four tools + a provider + a corpus + a budget), which is the
  argument that reopened E-1/E-2 (agents-as-folders finding 6). The memoization
  argument the registry spec's finding 1 killed stays dead — this is not it.
```

- [ ] **Step 6: Amend the header "Last verified" and add a §0 note**

Append to the §0 note block:

```markdown
> **2026-07-17 — research stage (FR-107).** A grounded research stage lands
> before clarify, off by default. `grounded` means quote-verified against bytes
> fetched this run; unverified claims are inferred or dropped; recall yields
> leads, not truth. It is the pipeline's first outbound egress (raising E-18)
> and the first role a folder genuinely describes. Memoization is preserved by a
> canonical `brief_digest`, not by caching the brief (a cached brief was never
> fetched). `2026-07-17-research-agent-grounded-briefs`.
```

- [ ] **Step 7: Verify the suite still tells the truth the tracker claims**

Run: `python -m pytest -q`
Expected: PASS — the §2 claims are only as good as the suite.

- [ ] **Step 8: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): record the research stage (FR-107); raise E-18

research lands off-by-default as stage 4; the DAG is 15 stages. brief_digest
keeps FR-103 alive across the non-memoized stage. Records that research is the
pipeline's first egress (raising E-18's ranking) and the first role a folder
describes, and files finding 7 (ReviewReport/MergeVerdict SGR ordering) as its
own item."
```

---

## Verification

- [ ] `python -m pytest -q` — full suite green.
- [ ] `python -c "from sdlc.agents import roles; print(roles.STAGE_MODELS['research'], roles.t_research is not None)"` — prints the research model and `True`, proving the optional role loads, its tools import, `CodeMode` binds, and the temporal agent is registered, all at import.
- [ ] **The grounding invariant bites.** Write a brief with one `grounded_finding` whose `quote` is not in any fetched page, and confirm `sdlc.research.verify.verify_brief` returns a `quote_not_found` violation and `verified_findings_to_retain` drops it. This is the invariant the increment exists to protect — confirm by observation.
- [ ] **Memoization survives the non-memoized stage.** Confirm `brief_digest` of two briefs with the same `(source_url, claim)` pairs but different prose/ordering/confidence are equal, and that changing one `claim` moves it — so clarify's `content_key` hits on identical facts and misses on new ones (finding 3).
- [ ] **Fail-closed boot.** Temporarily set `agents/research/agent.yaml` to `provider: tavily` with `TAVILY_API_KEY` unset and run `python -c "import sdlc.worker"`. Expected: `RegistryError` naming `TAVILY_API_KEY`. **Revert the edit.**
- [ ] **Off by default.** With `research_enabled=False` (the default), confirm the workflow's `run()` skips the research block entirely and clarify's memo key is byte-identical to a pre-research run (`brief_digest_val == ""`).
- [ ] `python -m pytest tests/test_factory_purity.py -q` — the research path added no unguarded benchmark calls and no workflow-context I/O.

## Self-Review Notes

- **Spec coverage:** research stage before clarify (Task 8); SGR `ResearchBrief` with evidence-first ordering (Task 3); `src/sdlc/research/` protocol+tavily+fake+verify (Task 4); `agents/research/` with `agent.yaml`/`instructions.md`/`tools/` (Tasks 5–6); Code Mode wrapping the tools (Task 6); quote verification against bytes fetched this run (Tasks 4, 7); corpus retention of verified findings only + `MemoryKind.research_finding` (Tasks 3, 7); stage-scoped bounds + `research_enabled` (Task 3, enforced Task 6); `brief_digest` into `content_key` (Tasks 4, 8); PRD/SDLC-spec amendment (Task 2); roadmap amendments (Task 10). Out-of-scope items (ReviewReport/MergeVerdict fix, egress policy, run-level budget generalisation, codebase research, a brief-quality judge, corpus retention of gaps/contradictions, Cycle-pattern iteration) are left out and, where relevant, filed (Task 10 §7 / E-18 / E-19).
- **The one branch this plan cannot encode** is Task 1's finding A. The plan is written for `output_validator` running activity-side (the expected result). If the spike shows workflow-side, Task 7 must be re-planned as a post-run `verify_brief` activity called from `feature.py` with the stage failing (not the model retrying) on a violation — Task 1 Step 5 records this explicitly and instructs a stop.
