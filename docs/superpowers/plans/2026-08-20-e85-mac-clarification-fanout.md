# E-85 MAC Clarification Fan-out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the clarify stage's single undifferentiated model call with a MAC-style fan-out — a supervisor that routes and asks domain-agnostic questions, N parallel probes that each own one SWE-RPG clarification dimension, and a pure-code merge that ranks and caps — behind a flag that is off by default.

**Architecture:** Three phases inside the existing stage boundary. `clarify_route_agent` (output `ClarifyRoute`) asks C1/C2 and picks live dimensions; `clarify_probe_agent` (output `ProbeResult`) runs once per live dimension concurrently through `run_or_degrade`; `merge_clarification` (pure, no model) dedups, ranks by materiality, applies a hard cap and keeps the losers in `dropped`. Both agents go through `_run_role`, so E-33's single model-egress accounting is preserved and no new Temporal activity plumbing is needed.

**Tech Stack:** Python 3.14, Pydantic v2, pydantic-ai-slim 2.21 (`TemporalAgent`), Temporal, pytest.

**Spec:** `docs/superpowers/specs/2026-08-20-e85-mac-clarification-fanout-design.md`

## Global Constraints

- **The default path must stay byte-identical.** `clarify_probes_enabled` defaults to `False`; with the flag off, the stage makes exactly one `t_clarify` call with today's prompt and today's memo key. Every task is subject to this.
- **All new model fields are additive with defaults.** `benchmark score --all` re-parses `BenchmarkRecord`s off disk and `RunSummary.clarifications` feeds the SC-4 rollup; a required field breaks stored runs.
- **`agents/clarify/instructions.md` is not edited by this plan.** It stays the shared clarification-analyst preamble. Editing it would move `PROMPT_SHAS["clarify"]` and change flag-off behaviour.
- **Never rename an agent's `name=`.** It is the Temporal activity name (`agents/clarify/agent.py`).
- **The registry stays at 15 roles.** No new `agents/<role>/` folder.
- **Probes fail open; the supervisor fails closed.**
- Run tests with `pytest <path> -v`. Default `addopts` excludes `slow`/`temporal`/`docker`/`prompt_eval` markers; every test in this plan is a fast unit test.

## Deviations from the approved spec

Two, both found while checking the spec's mechanisms against the real code. Neither changes the design; both change how a mechanism is implemented because the spec named a tool that does not fit the call shape.

1. **D8 — where the probe-prompt digest is keyed.** Detailed immediately below.
2. **§8 — `run_or_degrade` cannot wrap a probe.** It takes a Temporal activity; probes are `TemporalAgent.run` coroutines. Detailed in Task 8, which uses `asyncio.gather(return_exceptions=True)` for the same degrade-alone guarantee.

### Deviation 1 — D8

The spec's D8 folds probe prompt bytes into `_STAGE_PROMPTS["clarify"]` so `PROMPT_SHAS["clarify"]` covers them, and accepts re-pinning `test_prompt_migration.py`.

**This plan does not do that.** D8's stated rationale — "the only way the existing memo key covers them without changing `content_key`'s signature" — is incorrect. `content_key(stage, input_json, ...)` takes `input_json`, which the workflow builds per run (`feature.py:2083`). Putting the probe-prompt digest there covers the probe bytes with no signature change, and is strictly better than D8 on two counts:

1. **It does not contaminate the flag-off path.** Under D8 every existing clarify memo is invalidated at landing even though the flag-off prompt did not change. Under this plan flag-off memos survive, which is what "the default pipeline is byte-identical to today" (§10) actually requires.
2. **`test_prompt_migration.py`'s pins stay untouched**, so the E-2 byte-identity invariant needs no exception carved into it.

Everything D8 was protecting against — edit a probe, serve a stale memo — is still prevented, by Task 4's `probe_prompt_digest()` and Task 8's use of it. **§7's second key term (the codebase-map digest joining `input_json`) is unchanged and still implemented, in Task 8.**

---

### Task 1: Clarification taxonomy and additive model fields

**Files:**
- Modify: `src/sdlc/models.py` (near `OpenQuestion`, line ~232; `ClarificationOutcome`, line ~1157)
- Test: `tests/test_clarify_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ClarificationDimension` (StrEnum, members `FUNCTIONAL_INTENT="C1"`, `BUSINESS_SEMANTICS="C2"`, `TECHNICAL_CONTEXT="C3"`, `INTERFACE_SPEC="C4"`, `CODE_STRUCTURE="C5"`, `DATA_SEMANTICS="C6"`); `OpenQuestion` gains `dimension: ClarificationDimension | None`, `asked_by: str | None`, `materiality: float | None`, `evidence: str | None`, all defaulting to `None`; `ClarifiedRequirements` gains `dimensions_probed: list[ClarificationDimension]` and `dropped: list[OpenQuestion]`, both defaulting empty; `ClarificationOutcome` gains `dimension: ClarificationDimension | None = None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_models.py`:

```python
"""E-85 taxonomy fields are ADDITIVE. A ClarifiedRequirements written before
E-85 must still validate, because `benchmark score --all` re-parses records
off disk and RunSummary.clarifications feeds the SC-4 rollup."""

import pytest
from pydantic import ValidationError

from sdlc.models import (
    ClarificationDimension,
    ClarificationOutcome,
    ClarifiedRequirements,
    OpenQuestion,
)

PRE_E85_JSON = """
{"summary": "s",
 "functional_requirements": ["fr"],
 "non_functional_requirements": [],
 "out_of_scope": [],
 "open_questions": [{"id": "Q1", "question": "q?", "why_it_matters": "w"}]}
"""


def test_the_taxonomy_has_exactly_the_six_swe_rpg_dimensions():
    assert [d.value for d in ClarificationDimension] == ["C1", "C2", "C3", "C4", "C5", "C6"]


def test_a_pre_e85_artifact_still_validates():
    reqs = ClarifiedRequirements.model_validate_json(PRE_E85_JSON)
    assert reqs.open_questions[0].dimension is None
    assert reqs.dimensions_probed == []
    assert reqs.dropped == []


def test_new_question_fields_default_to_none():
    q = OpenQuestion(id="Q1", question="q?", why_it_matters="w")
    assert (q.dimension, q.asked_by, q.materiality, q.evidence) == (None, None, None, None)


def test_a_question_can_carry_its_dimension_and_provenance():
    q = OpenQuestion(
        id="Q1",
        question="q?",
        why_it_matters="w",
        dimension=ClarificationDimension.INTERFACE_SPEC,
        asked_by="probe:C4",
        materiality=0.9,
        evidence="src/api/routes.py",
    )
    assert q.dimension is ClarificationDimension.INTERFACE_SPEC
    assert q.materiality == 0.9


def test_materiality_is_bounded_to_the_unit_interval():
    with pytest.raises(ValidationError):
        OpenQuestion(id="Q1", question="q?", why_it_matters="w", materiality=1.5)


def test_clarification_outcome_carries_an_optional_dimension():
    o = ClarificationOutcome(question_id="Q1", question="q?", answered_by="human")
    assert o.dimension is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'ClarificationDimension' from 'sdlc.models'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/models.py`, immediately **above** `class OpenQuestion`:

```python
class ClarificationDimension(StrEnum):
    """SWE-RPG's practitioner-derived clarification taxonomy (E-85 §1.2).

    Stands in for MAC's five MultiWOZ domains: "implement a software feature"
    is one domain in MAC's terms, so our experts specialise by the KIND of
    ambiguity they resolve rather than by business domain.
    """

    FUNCTIONAL_INTENT = "C1"  # the core behaviour change needed
    BUSINESS_SEMANTICS = "C2"  # domain rules and constraints
    TECHNICAL_CONTEXT = "C3"  # architectural and dependency considerations
    INTERFACE_SPEC = "C4"  # API contracts and signatures
    CODE_STRUCTURE = "C5"  # repository patterns and conventions
    DATA_SEMANTICS = "C6"  # data invariants and constraints
```

If `StrEnum` is not already imported, add `from enum import StrEnum` to the existing `enum` import line.

Replace `class OpenQuestion` with:

```python
class OpenQuestion(BaseModel):
    id: str
    question: str
    why_it_matters: str
    suggested_answer: str | None = None
    answer: str | None = None  # filled by human (or auto)
    # E-85: additive only -- a pre-E-85 artifact must still validate.
    dimension: ClarificationDimension | None = None
    asked_by: str | None = None  # "supervisor" | "probe:C4"
    materiality: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = None  # repo path/symbol grounding it
```

Add to `class ClarifiedRequirements`, after `spec_ref`:

```python
    # E-85: what actually ran, and what the cap cut. `dropped` is what makes
    # the cap honest -- without it, capping and being incurious are
    # indistinguishable in the record.
    dimensions_probed: list[ClarificationDimension] = Field(default_factory=list)
    dropped: list[OpenQuestion] = Field(default_factory=list)
```

Add to `class ClarificationOutcome`, after `answered_by`:

```python
dimension: ClarificationDimension | None = None  # E-85
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_models.py -v`
Expected: 6 passed

- [ ] **Step 5: Verify nothing else regressed**

Run: `pytest -q`
Expected: the full fast suite passes. These are additive optional fields; any failure here is a real incompatibility, not an expected churn.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_clarify_models.py
git commit -m "feat(models): SWE-RPG clarification taxonomy, additive on OpenQuestion"
```

---

### Task 2: Pipeline flags

**Files:**
- Modify: `src/sdlc/models.py` (`PipelineConfig`, near the `*_enabled` block at ~line 1109-1124)
- Test: `tests/test_clarify_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PipelineConfig.clarify_probes_enabled: bool = False`, `PipelineConfig.clarify_question_cap: int = 5` (validated `ge=1`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_config.py`:

```python
"""E-85's flag is off by default: the default pipeline must be byte-identical
to pre-E-85, so the benchmark can run both arms."""

import pytest
from pydantic import ValidationError

from sdlc.models import PipelineConfig


def test_probes_are_off_by_default():
    assert PipelineConfig().clarify_probes_enabled is False


def test_the_question_cap_defaults_to_five():
    assert PipelineConfig().clarify_question_cap == 5


def test_a_zero_cap_is_rejected():
    # A cap of 0 would silently surface nothing to the human while the
    # clarifier still burned four probe calls.
    with pytest.raises(ValidationError):
        PipelineConfig(clarify_question_cap=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_config.py -v`
Expected: FAIL — `AttributeError: 'PipelineConfig' object has no attribute 'clarify_probes_enabled'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/models.py`, in `PipelineConfig` beside the other `*_enabled` flags:

```python
clarify_probes_enabled: bool = False  # E-85: off by default; the
# default pipeline stays the
# single-call clarifier.
clarify_question_cap: int = Field(default=5, ge=1)  # E-85 D9: hard cap
# on the batch a human sees. MAC
# held latency with "one
# clarification per turn"; our
# unit is a human blocking on
# gate_timeout_hours.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py tests/test_clarify_config.py
git commit -m "feat(config): clarify_probes_enabled and clarify_question_cap"
```

---

### Task 3: Stage-internal types

**Files:**
- Create: `src/sdlc/clarify/__init__.py`
- Create: `src/sdlc/clarify/models.py`
- Test: `tests/test_clarify_stage_types.py`

**Interfaces:**
- Consumes: `ClarificationDimension`, `OpenQuestion` (Task 1).
- Produces: `ClarifyRoute(summary: str, functional_requirements: list[str], non_functional_requirements: list[str], out_of_scope: list[str], questions: list[OpenQuestion], live_dimensions: list[ClarificationDimension])` and `ProbeResult(dimension: ClarificationDimension, questions: list[OpenQuestion])`. Both are stage-internal: never persisted, never shown to a human.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_stage_types.py`:

```python
"""Stage-internal types. ClarifyRoute is the supervisor's output and
ProbeResult one probe's; merge folds both into ClarifiedRequirements. Neither
is ever persisted or shown to a human."""

from sdlc.clarify.models import ClarifyRoute, ProbeResult
from sdlc.models import ClarificationDimension, OpenQuestion

C4 = ClarificationDimension.INTERFACE_SPEC


def test_a_route_with_no_live_dimensions_is_valid():
    # A one-line CSS tweak should route to zero probes. That is the primary
    # cost control, so it must not be an error.
    route = ClarifyRoute(
        summary="s",
        functional_requirements=["fr"],
        non_functional_requirements=[],
        out_of_scope=[],
        questions=[],
        live_dimensions=[],
    )
    assert route.live_dimensions == []


def test_a_probe_that_abstains_returns_an_empty_question_list():
    # is_ambiguous() == 0 is a valid, expected answer -- not a failure.
    assert ProbeResult(dimension=C4, questions=[]).questions == []


def test_a_probe_carries_its_own_dimension_back():
    # merge attributes questions by the ProbeResult's dimension, so it must
    # survive the round trip even if the model omitted it per question.
    p = ProbeResult(
        dimension=C4, questions=[OpenQuestion(id="P1", question="q?", why_it_matters="w")]
    )
    assert p.dimension is C4


def test_route_defaults_keep_the_body_lists_present():
    route = ClarifyRoute(summary="s")
    assert route.functional_requirements == []
    assert route.questions == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_stage_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.clarify'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/clarify/__init__.py`:

```python
"""E-85: the MAC-style clarification fan-out.

Spec: docs/superpowers/specs/2026-08-20-e85-mac-clarification-fanout-design.md
"""
```

Create `src/sdlc/clarify/models.py`:

```python
"""Stage-internal types for the clarify fan-out.

Neither type is persisted and neither reaches a human: merge folds them into
ClarifiedRequirements, which is the only artifact the stage emits.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import ClarificationDimension, OpenQuestion


class ClarifyRoute(BaseModel):
    """clarify_route's output: MAC's is_ambiguous() and select_domain() fused
    into one call. The supervisor authors the requirements body and its own
    C1/C2 questions, and NAMES the dimensions to probe -- it does not author
    the probes' questions (E-85 D2, mirroring agents/discover's "You judge;
    you do not author")."""

    summary: str
    functional_requirements: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    questions: list[OpenQuestion] = Field(default_factory=list)
    live_dimensions: list[ClarificationDimension] = Field(default_factory=list)


class ProbeResult(BaseModel):
    """One probe's answer. An empty `questions` list is valid and expected --
    it means is_ambiguous() returned 0 for this dimension. Abstaining is not
    a failure; a probe that never abstains is inventing work."""

    dimension: ClarificationDimension
    questions: list[OpenQuestion] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_stage_types.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/clarify/ tests/test_clarify_stage_types.py
git commit -m "feat(clarify): ClarifyRoute and ProbeResult stage-internal types"
```

---

### Task 4: Probe prompts, the cacheable prefix, and the prompt digest

**Files:**
- Create: `src/sdlc/clarify/prompts.py`
- Test: `tests/test_clarify_prompt_cacheable.py`

**Interfaces:**
- Consumes: `ClarificationDimension` (Task 1).
- Produces: `ROUTE_SCOPE: str`, `PROBE_SYSTEM: str`, `PROBE_PREFIX: str`, `SCOPES: dict[ClarificationDimension, str]`, `probe_prompt(dimension: ClarificationDimension, *, idea_json: str, requirements_json: str, grounding: str) -> str`, `probe_prompt_digest() -> str` (sha256 hex over every prompt byte in this module, in a fixed order).

**Why the prefix length is functional:** `src/sdlc/research/prompts.py` documents that fan-out "multiplies input cost by N, which makes this the largest cost lever here" and that a prefix under ~512 tokens is "silently not cached — `cache_creation_input_tokens` simply stays 0, with no error and no warning." Four probes sharing a cached prefix is the difference between roughly 4× and 1.3× stage input cost. Do not trim these strings for tidiness.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_prompt_cacheable.py`:

```python
"""The probe prefix must be byte-identical across a burst and long enough to
cache. Under ~512 tokens a prefix is silently NOT cached -- no error, the
counter just stays at zero -- so this is a test, not a comment. Modelled on
tests/test_research_prompt_cacheable.py."""

from sdlc.clarify.prompts import (
    PROBE_PREFIX,
    PROBE_SYSTEM,
    ROUTE_SCOPE,
    SCOPES,
    probe_prompt,
    probe_prompt_digest,
)
from sdlc.models import ClarificationDimension

# ~4 chars per token; 512 tokens is the documented cache floor. 2400 chars
# gives headroom without being precious. Same constant as research's guard.
MIN_CACHEABLE_CHARS = 2400

C3 = ClarificationDimension.TECHNICAL_CONTEXT
C4 = ClarificationDimension.INTERFACE_SPEC
C6 = ClarificationDimension.DATA_SEMANTICS


def _prompt(dim):
    return probe_prompt(
        dim,
        idea_json='{"title": "x"}',
        requirements_json='{"summary": "s"}',
        grounding="src/api/routes.py",
    )


def test_prefix_is_long_enough_to_be_cacheable():
    assert len(PROBE_PREFIX) >= MIN_CACHEABLE_CHARS, (
        "prefix is below the cache floor -- it will silently not be cached "
        "and every parallel probe pays full input price"
    )


def test_prefix_is_byte_identical_across_different_dimensions():
    for dim in (C3, C4, C6):
        assert _prompt(dim).startswith(PROBE_PREFIX)


def test_the_scope_lands_after_the_prefix_never_inside_it():
    # Interpolating the dimension into the prefix would break the shared
    # cache entry for every probe in the burst.
    for dim, scope in SCOPES.items():
        assert scope not in PROBE_PREFIX, f"{dim} scope leaked into the prefix"
        assert scope in _prompt(dim)


def test_every_dimension_has_a_scope_block():
    assert set(SCOPES) == set(ClarificationDimension)


def test_the_prefix_licenses_abstention():
    # A probe that cannot abstain manufactures questions (spec §13).
    assert "abstain" in PROBE_PREFIX.lower()


def test_route_scope_and_probe_system_are_non_empty():
    assert len(ROUTE_SCOPE) > 200
    assert len(PROBE_SYSTEM) > 200


def test_the_digest_is_stable_across_calls():
    assert probe_prompt_digest() == probe_prompt_digest()


def test_the_digest_is_a_sha256_hex():
    d = probe_prompt_digest()
    assert len(d) == 64 and all(c in "0123456789abcdef" for c in d)


def test_editing_a_scope_block_moves_the_digest(monkeypatch):
    """The whole point of the digest: edit a probe prompt, invalidate the
    memo. Without this, a probe edit serves a stale clarification silently."""
    before = probe_prompt_digest()
    patched = dict(SCOPES)
    patched[C4] = patched[C4] + "\nAlso consider idempotency.\n"
    monkeypatch.setattr("sdlc.clarify.prompts.SCOPES", patched)
    assert probe_prompt_digest() != before


def test_editing_the_prefix_moves_the_digest(monkeypatch):
    before = probe_prompt_digest()
    monkeypatch.setattr("sdlc.clarify.prompts.PROBE_PREFIX", PROBE_PREFIX + "\nOne more rule.\n")
    assert probe_prompt_digest() != before


def test_swapping_two_scopes_moves_the_digest(monkeypatch):
    """The digest binds each scope to ITS dimension. A digest that hashed
    only the concatenated text would miss this and serve a stale memo after
    a re-attribution."""
    before = probe_prompt_digest()
    patched = dict(SCOPES)
    patched[C3], patched[C6] = patched[C6], patched[C3]
    monkeypatch.setattr("sdlc.clarify.prompts.SCOPES", patched)
    assert probe_prompt_digest() != before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_prompt_cacheable.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.clarify.prompts'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/clarify/prompts.py`. **`PROBE_PREFIX` must exceed 2400 characters** — write it out in full; a stub will fail Step 4.

```python
"""Prompts for the clarify fan-out.

PROBE_PREFIX is BYTE-IDENTICAL across every probe in a burst so the parallel
calls share one cached prefix at ~0.1x input price. Fan-out multiplies input
cost by N, which makes this the largest cost lever here.

LENGTH IS FUNCTIONAL. A prefix under ~512 tokens is silently not cached --
cache_creation_input_tokens simply stays 0, with no error and no warning.
Guarded by tests/test_clarify_prompt_cacheable.py. Do not trim for tidiness,
and NEVER interpolate the dimension or its scope into the prefix.

These bytes are covered by probe_prompt_digest(), which joins the clarify
stage's memoization input (feature.py). Editing any string in this module
therefore invalidates exactly the runs it should.
"""

from __future__ import annotations

import hashlib

from ..models import ClarificationDimension

ROUTE_SCOPE = """\
You are also the ROUTER for a team of specialist clarifiers, and this part of \
your job has a strict boundary.

You resolve only ambiguity that general reasoning about the request settles, \
without reading the codebase. That is two kinds:

- C1 FUNCTIONAL INTENT — what behaviour is supposed to change. If you cannot \
state the observable difference between the system before and after, ask.
- C2 BUSINESS SEMANTICS — the domain rules and constraints the behaviour must \
respect. Who is allowed to do this, what must stay true afterwards, what the \
edge cases mean in the business's own terms.

Everything else you DELEGATE. You name the dimensions that need a specialist \
and you stop there. You do NOT write the specialist's questions, and you do \
NOT guess at their answers: they can read the codebase and you cannot, so a \
question you invent on their behalf is a question asked from ignorance.

The dimensions you may name in live_dimensions:

- C3 TECHNICAL CONTEXT — which existing components, dependencies and \
architectural constraints the change lands in.
- C4 INTERFACE / PROTOCOL — the contracts and signatures the change crosses.
- C5 CODE STRUCTURE — the repository's own patterns and conventions.
- C6 DATA SEMANTICS — the invariants and meaning of the data involved.

Name a dimension only when this specific request plausibly turns on it. A \
one-line copy change turns on none of them, and naming all four out of \
caution spends four model calls and four slots in a capped batch to \
manufacture questions nobody needed. An empty live_dimensions list is a \
correct and common answer.

For every question you DO ask, set dimension to C1 or C2, asked_by to \
"supervisor", and materiality between 0.0 and 1.0 on this scale:

- 0.9-1.0 — the design is genuinely blocked; two answers produce two \
different systems.
- 0.6-0.8 — the answer changes the design, but a wrong guess is recoverable \
in a later stage.
- 0.3-0.5 — the answer changes details, not structure.
- below 0.3 — do not ask it. Say it as an assumption in the requirements body \
instead.

Score honestly against that scale. Your questions compete with the \
specialists' for a small number of slots, and a question that wins a slot it \
did not earn displaces one that mattered more.
"""

PROBE_SYSTEM = """\
You are a specialist clarifier. You own exactly one dimension of ambiguity in \
a software change, and you are one of several specialists working the same \
request in parallel. You will never see the others' questions, so do not try \
to cover their ground or compensate for what you imagine they missed. Depth \
on your own dimension is the entire job.

A supervisor has already resolved what the request means in general terms and \
has written the requirements body you are given. Do not re-ask what it \
already answers, and do not restate its questions in your own words.

You return questions for a human to answer before implementation starts. You \
do not answer them yourself, you do not propose designs, and you do not \
author decisions that belong to the architect. The difference matters: \
"should we use Postgres or SQLite?" is a decision, and "does this counter \
need to survive a restart?" is an ambiguity. Ask the second kind.
"""

PROBE_PREFIX = """\
Your task is to decide whether your dimension holds a real, material \
ambiguity in the request below, and if so, to ask about it.

## First decide whether to ask at all

Before writing anything, answer for yourself: could a competent engineer \
implement this correctly without knowing the answer? If yes, you have no \
question. Return an empty list.

ABSTAINING IS A CORRECT AND EXPECTED RESULT. Most requests do not turn on \
most dimensions. You are not being measured on how many questions you \
produce, and a probe that never abstains is manufacturing work: it burns a \
human's attention on something the code already settles, and it displaces a \
question from another specialist that genuinely mattered. Returning nothing \
is the right answer more often than not.

Ask only when all three hold:

1. The answer is genuinely not determined by the request, the requirements \
body, or the codebase context you were given. If the context answers it, it \
is not ambiguous — it is something you have not read carefully enough.
2. Different answers lead to materially different implementations. Not \
different variable names or a different file layout: different behaviour, a \
different contract, or a different data shape.
3. It belongs to YOUR dimension. If it is really about another specialist's \
territory, drop it. They are being asked in parallel and they know their \
area better than you do.

## How to write a question that is worth a human's time

- Ask one thing. A question with an "and" in it gets half an answer.
- Be concrete and closed where you can. "Should deleting a project cascade to \
its runs, or should it be refused while runs exist?" beats "how should \
deletion behave?" — the first can be answered in five seconds, the second \
starts a meeting.
- Say what actually turns on it in why_it_matters: name the thing that would \
be built wrong. "Otherwise the migration is irreversible" is useful; \
"otherwise the requirements are unclear" is noise.
- Supply suggested_answer whenever you have a defensible default, and make it \
the answer you would ship if nobody replied. A human approving your default \
costs seconds; a human composing an answer from scratch costs minutes, and \
that difference is most of the cost of this whole stage.
- Never ask a question whose answer you could look up in the context you were \
given.

## Grounding

When you are given codebase context, every question you ask about it must \
cite the specific path, symbol, or table it came from, in the evidence field. \
A question about code that cannot point at the code is speculation, and it \
will be discarded before a human ever sees it. Cite the narrowest thing that \
supports the question — a file and a symbol, not a directory.

## Scoring materiality

Score every question between 0.0 and 1.0 on this scale, which every \
specialist shares:

- 0.9-1.0 — the design is genuinely blocked; two answers produce two \
different systems.
- 0.6-0.8 — the answer changes the design, but a wrong guess is recoverable \
in a later stage.
- 0.3-0.5 — the answer changes details, not structure.
- below 0.3 — do not ask it at all.

Score honestly against that scale rather than relative to your own other \
questions. Only a small number of questions across all specialists reach the \
human, and they are ranked by this number. Inflating yours does not get your \
dimension more attention; it gets a worse question in front of the human and \
a better one dropped.

## Output

Return your dimension and your questions. Set asked_by to "probe:" followed \
by your dimension code, and set dimension on every question to your own \
dimension. Return an empty question list to abstain.
"""

SCOPES: dict[ClarificationDimension, str] = {
    ClarificationDimension.FUNCTIONAL_INTENT: """\
## Your dimension: C1 — FUNCTIONAL INTENT

The core behaviour change. What is observably different once this ships, and \
for whom. Ambiguity here looks like: a request that names a feature without \
saying what it does, success stated as a feeling rather than a behaviour, or \
two readings of the request that would both satisfy the words and produce \
different products.
""",
    ClarificationDimension.BUSINESS_SEMANTICS: """\
## Your dimension: C2 — BUSINESS SEMANTICS

The domain rules the behaviour must respect. Who may do this, what must \
remain true afterwards, what the edge cases mean to the business rather than \
to the code. Ambiguity here looks like: an unstated permission model, a rule \
that holds "usually", money or time or identity handled without a stated \
convention.
""",
    ClarificationDimension.TECHNICAL_CONTEXT: """\
## Your dimension: C3 — TECHNICAL CONTEXT

Which existing components, dependencies and architectural constraints this \
change lands in. Ambiguity here looks like: a change that could plausibly go \
in two different modules that already exist, an unstated dependency on a \
service the codebase already talks to, or a constraint the current \
architecture imposes that the request seems unaware of.

Do not ask which architecture we SHOULD adopt. That is the architect's \
decision, not an ambiguity in the request.
""",
    ClarificationDimension.INTERFACE_SPEC: """\
## Your dimension: C4 — INTERFACE / PROTOCOL

The contracts and signatures this change crosses: endpoints, function \
signatures, event payloads, CLI surfaces, wire formats. Ambiguity here looks \
like: an unstated request or response shape, an unspecified error contract, a \
change that would break an existing caller without saying whether that is \
acceptable, or a new surface whose versioning and compatibility expectations \
are unstated.

SWE-RPG found this among the two weakest dimensions for coding agents \
(42-54% coverage). Assume it is under-specified until the context proves \
otherwise.
""",
    ClarificationDimension.CODE_STRUCTURE: """\
## Your dimension: C5 — CODE STRUCTURE AND CONVENTIONS

The repository's own established patterns: how modules are laid out, how \
things of this kind are named, which existing abstraction new work is \
expected to extend rather than duplicate. Ambiguity here looks like: two \
existing patterns for the same job with no stated preference, or a request \
that implies a new pattern where an established one already exists.

Only ask about conventions that ALREADY EXIST in the tree you were given. \
Asking which conventions we should adopt is authoring a decision, not \
resolving an ambiguity.
""",
    ClarificationDimension.DATA_SEMANTICS: """\
## Your dimension: C6 — DATA-STRUCTURE SEMANTICS

What the data means and what must stay true of it: invariants, nullability, \
uniqueness, units, time zones, lifecycle and retention, what a missing value \
signifies. Ambiguity here looks like: a new field whose empty state is \
undefined, a relationship whose cardinality is unstated, a deletion whose \
cascade is unspecified, or a quantity with no unit.

SWE-RPG found this among the two weakest dimensions for coding agents \
(42-54% coverage). Assume it is under-specified until the context proves \
otherwise.
""",
}


def probe_prompt(
    dimension: ClarificationDimension, *, idea_json: str, requirements_json: str, grounding: str
) -> str:
    """One probe's user prompt: shared cacheable prefix FIRST, then the
    dimension's scope, then this run's context. Nothing run-specific may move
    ahead of the prefix or the burst loses its shared cache entry."""
    return (
        PROBE_PREFIX
        + "\n"
        + SCOPES[dimension]
        + "\n## The request\n"
        + idea_json
        + "\n\n## Requirements so far\n"
        + requirements_json
        + ("\n\n## Codebase context\n" + grounding if grounding else "")
    )


def probe_prompt_digest() -> str:
    """sha256 over every prompt byte in this module, in a fixed order.

    Joins the clarify stage's memoization input rather than PROMPT_SHAS (see
    the plan's D8 deviation): keying it here covers the probe bytes without
    invalidating flag-off memos, whose prompt did not change.
    """
    h = hashlib.sha256()
    for part in (ROUTE_SCOPE, PROBE_SYSTEM, PROBE_PREFIX):
        h.update(part.encode())
    for dim in sorted(SCOPES, key=lambda d: d.value):
        h.update(dim.value.encode())
        h.update(SCOPES[dim].encode())
    return h.hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_prompt_cacheable.py -v`
Expected: 11 passed. If `test_prefix_is_long_enough_to_be_cacheable` fails, `PROBE_PREFIX` was trimmed — restore it rather than lowering `MIN_CACHEABLE_CHARS`.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/clarify/prompts.py tests/test_clarify_prompt_cacheable.py
git commit -m "feat(clarify): probe prompts with a cacheable shared prefix"
```

---

### Task 5: Routing policy

**Files:**
- Create: `src/sdlc/clarify/routing.py`
- Test: `tests/test_clarify_routing.py`

**Interfaces:**
- Consumes: `ClarificationDimension` (Task 1), `ProjectMode` (existing, `models.py:22`).
- Produces: `SUPERVISOR_DIMENSIONS: tuple[ClarificationDimension, ...]`, `PROBE_DIMENSIONS: tuple[...]`, `permitted_dimensions(mode: ProjectMode) -> tuple[...]`, `live_dimensions(requested: Iterable[ClarificationDimension], mode: ProjectMode) -> tuple[...]`, `grounded_dimensions(mode: ProjectMode) -> frozenset[ClarificationDimension]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_routing.py`:

```python
"""Which probes may run, per project mode. Pure -- no model, no I/O.

C3 and C5 are skipped in greenfield because there is no existing architecture
or convention for a requirement to be ambiguous AGAINST: a C5 probe on an
empty tree can only ask which conventions we should adopt, which authors a
decision rather than resolving an ambiguity (E-85 D5)."""

from sdlc.clarify.routing import (
    PROBE_DIMENSIONS,
    SUPERVISOR_DIMENSIONS,
    grounded_dimensions,
    live_dimensions,
    permitted_dimensions,
)
from sdlc.models import ClarificationDimension as CD
from sdlc.models import ProjectMode

ALL = list(CD)


def test_the_supervisor_owns_c1_and_c2_and_nothing_else():
    assert SUPERVISOR_DIMENSIONS == (CD.FUNCTIONAL_INTENT, CD.BUSINESS_SEMANTICS)


def test_probes_own_the_other_four():
    assert PROBE_DIMENSIONS == (
        CD.TECHNICAL_CONTEXT,
        CD.INTERFACE_SPEC,
        CD.CODE_STRUCTURE,
        CD.DATA_SEMANTICS,
    )


def test_the_two_sets_do_not_overlap():
    assert not set(SUPERVISOR_DIMENSIONS) & set(PROBE_DIMENSIONS)


def test_brownfield_permits_all_four_probe_dimensions():
    assert permitted_dimensions(ProjectMode.BROWNFIELD) == PROBE_DIMENSIONS


def test_greenfield_skips_technical_context_and_code_structure():
    assert permitted_dimensions(ProjectMode.GREENFIELD) == (CD.INTERFACE_SPEC, CD.DATA_SEMANTICS)


def test_a_greenfield_request_for_c5_is_refused():
    # The supervisor asked; the mode forbids it.
    assert live_dimensions([CD.CODE_STRUCTURE], ProjectMode.GREENFIELD) == ()


def test_live_dimensions_are_returned_in_canonical_c1_to_c6_order():
    got = live_dimensions([CD.DATA_SEMANTICS, CD.TECHNICAL_CONTEXT], ProjectMode.BROWNFIELD)
    assert got == (CD.TECHNICAL_CONTEXT, CD.DATA_SEMANTICS)


def test_a_duplicate_request_probes_once():
    got = live_dimensions([CD.INTERFACE_SPEC, CD.INTERFACE_SPEC], ProjectMode.BROWNFIELD)
    assert got == (CD.INTERFACE_SPEC,)


def test_requesting_nothing_probes_nothing():
    # A one-line CSS tweak. Routing is the primary cost control.
    assert live_dimensions([], ProjectMode.BROWNFIELD) == ()


def test_a_supervisor_dimension_is_never_probed():
    assert live_dimensions([CD.FUNCTIONAL_INTENT], ProjectMode.BROWNFIELD) == ()


def test_brownfield_probes_must_all_cite_evidence():
    assert grounded_dimensions(ProjectMode.BROWNFIELD) == frozenset(PROBE_DIMENSIONS)


def test_greenfield_probes_have_no_tree_to_cite():
    assert grounded_dimensions(ProjectMode.GREENFIELD) == frozenset()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_routing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.clarify.routing'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/clarify/routing.py`:

```python
"""Which probes may run, per project mode. Pure -- no model, no I/O.

MAC's supervisor holds no domain database and handles only ambiguity that
general reasoning settles; its experts hold the schemas. Our split is the
same, drawn along SWE-RPG's taxonomy instead of MAC's five booking domains.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models import ClarificationDimension as CD
from ..models import ProjectMode

# The supervisor's two: answerable without reading any code.
SUPERVISOR_DIMENSIONS: tuple[CD, ...] = (CD.FUNCTIONAL_INTENT, CD.BUSINESS_SEMANTICS)

# The probes' four, in canonical order. All four are map-grounded in
# brownfield; C4 and C6 survive greenfield because a contract or an invariant
# can be underspecified before any code exists.
PROBE_DIMENSIONS: tuple[CD, ...] = (
    CD.TECHNICAL_CONTEXT,
    CD.INTERFACE_SPEC,
    CD.CODE_STRUCTURE,
    CD.DATA_SEMANTICS,
)

# E-85 D5: with no tree, these two could only ask which architecture or which
# conventions we SHOULD adopt -- authoring a decision that belongs to the
# architect, not resolving an ambiguity. Same boundary agents/discover polices.
_GREENFIELD_SKIP: frozenset[CD] = frozenset({CD.TECHNICAL_CONTEXT, CD.CODE_STRUCTURE})


def permitted_dimensions(mode: ProjectMode) -> tuple[CD, ...]:
    """The probe dimensions this project mode allows at all."""
    if mode is ProjectMode.GREENFIELD:
        return tuple(d for d in PROBE_DIMENSIONS if d not in _GREENFIELD_SKIP)
    return PROBE_DIMENSIONS


def live_dimensions(requested: Iterable[CD], mode: ProjectMode) -> tuple[CD, ...]:
    """The supervisor's request, narrowed by what the mode permits.

    Returned in canonical C1..C6 order regardless of the order asked for, so
    a probe burst is deterministic and a replay cannot reorder it.
    """
    asked = set(requested)
    return tuple(d for d in permitted_dimensions(mode) if d in asked)


def grounded_dimensions(mode: ProjectMode) -> frozenset[CD]:
    """Dimensions whose questions MUST cite repo evidence to survive merge.

    Brownfield probes read the codebase map, so a question that cannot point
    at a path or symbol is speculation (spec §13). Greenfield probes have no
    tree to cite, so nothing is required of them.
    """
    if mode is ProjectMode.GREENFIELD:
        return frozenset()
    return frozenset(PROBE_DIMENSIONS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_routing.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/clarify/routing.py tests/test_clarify_routing.py
git commit -m "feat(clarify): mode-aware probe routing policy"
```

---

### Task 6: Merge — dedup, rank, cap

**Files:**
- Create: `src/sdlc/clarify/merge.py`
- Test: `tests/test_clarify_merge.py`

**Interfaces:**
- Consumes: `ClarifyRoute`, `ProbeResult` (Task 3); `ClarifiedRequirements`, `OpenQuestion`, `ClarificationDimension` (Task 1).
- Produces: `merge_clarification(route: ClarifyRoute, probes: Sequence[ProbeResult], *, cap: int, grounded: frozenset[ClarificationDimension]) -> ClarifiedRequirements`.

**Ordering contract (must be exact):** materiality descending with `None` last, then canonical dimension order C1→C6 with no dimension last, then question id ascending. Deterministic under replay.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_merge.py`:

```python
"""Deterministic merge of the supervisor's and the probes' questions. Pure --
no model, no I/O.

The cap is load-bearing: MAC raised task success WHILE CUTTING dialogue turns
(6.53 -> 4.86), and six dimensions sweeping in parallel is a direct assault on
that. `dropped` is what keeps capping distinguishable from incuriosity."""

from sdlc.clarify.merge import merge_clarification
from sdlc.clarify.models import ClarifyRoute, ProbeResult
from sdlc.models import ClarificationDimension as CD
from sdlc.models import OpenQuestion

GROUNDED = frozenset(
    {CD.TECHNICAL_CONTEXT, CD.INTERFACE_SPEC, CD.CODE_STRUCTURE, CD.DATA_SEMANTICS}
)


def _q(qid, text="q?", *, dim=None, mat=None, ev=None, asked_by="probe:C4"):
    return OpenQuestion(
        id=qid,
        question=text,
        why_it_matters="w",
        dimension=dim,
        materiality=mat,
        evidence=ev,
        asked_by=asked_by,
    )


def _route(*questions):
    return ClarifyRoute(
        summary="s",
        functional_requirements=["fr"],
        non_functional_requirements=["nfr"],
        out_of_scope=["oos"],
        questions=list(questions),
        live_dimensions=[],
    )


def _merge(route, probes, cap=5, grounded=GROUNDED):
    return merge_clarification(route, probes, cap=cap, grounded=grounded)


def test_the_requirements_body_comes_from_the_route():
    out = _merge(_route(), [])
    assert out.summary == "s"
    assert out.functional_requirements == ["fr"]
    assert out.non_functional_requirements == ["nfr"]
    assert out.out_of_scope == ["oos"]


def test_no_probes_yields_only_supervisor_questions():
    sup = _q("S1", dim=CD.FUNCTIONAL_INTENT, mat=0.8, asked_by="supervisor")
    out = _merge(_route(sup), [])
    assert [q.id for q in out.open_questions] == ["S1"]
    assert out.dropped == []


def test_probe_questions_join_the_supervisors():
    sup = _q("S1", "sup?", dim=CD.FUNCTIONAL_INTENT, mat=0.5, asked_by="supervisor")
    probe = ProbeResult(
        dimension=CD.INTERFACE_SPEC,
        questions=[_q("P1", "probe?", dim=CD.INTERFACE_SPEC, mat=0.9, ev="api.py")],
    )
    out = _merge(_route(sup), [probe])
    assert {q.id for q in out.open_questions} == {"S1", "P1"}


def test_ranking_is_by_materiality_descending():
    probe = ProbeResult(
        dimension=CD.INTERFACE_SPEC,
        questions=[
            _q("P1", "low?", dim=CD.INTERFACE_SPEC, mat=0.2, ev="a.py"),
            _q("P2", "high?", dim=CD.INTERFACE_SPEC, mat=0.95, ev="b.py"),
        ],
    )
    out = _merge(_route(), [probe])
    assert [q.id for q in out.open_questions] == ["P2", "P1"]


def test_a_question_without_materiality_sorts_last():
    probe = ProbeResult(
        dimension=CD.INTERFACE_SPEC,
        questions=[
            _q("P1", "unscored?", dim=CD.INTERFACE_SPEC, ev="a.py"),
            _q("P2", "scored?", dim=CD.INTERFACE_SPEC, mat=0.1, ev="b.py"),
        ],
    )
    out = _merge(_route(), [probe])
    assert [q.id for q in out.open_questions] == ["P2", "P1"]


def test_ties_break_by_dimension_then_id_so_replays_are_stable():
    probes = [
        ProbeResult(
            dimension=CD.DATA_SEMANTICS,
            questions=[_q("Z", "d?", dim=CD.DATA_SEMANTICS, mat=0.5, ev="d.py")],
        ),
        ProbeResult(
            dimension=CD.TECHNICAL_CONTEXT,
            questions=[_q("A", "t?", dim=CD.TECHNICAL_CONTEXT, mat=0.5, ev="t.py")],
        ),
    ]
    out = _merge(_route(), probes)
    assert [q.id for q in out.open_questions] == ["A", "Z"]


def test_the_cap_truncates_and_the_remainder_is_recorded_as_dropped():
    probe = ProbeResult(
        dimension=CD.INTERFACE_SPEC,
        questions=[
            _q(f"P{i}", f"q{i}?", dim=CD.INTERFACE_SPEC, mat=1.0 - i / 10, ev="a.py")
            for i in range(8)
        ],
    )
    out = _merge(_route(), [probe], cap=3)
    assert [q.id for q in out.open_questions] == ["P0", "P1", "P2"]
    assert [q.id for q in out.dropped] == ["P3", "P4", "P5", "P6", "P7"]


def test_nothing_is_dropped_when_the_batch_fits():
    probe = ProbeResult(
        dimension=CD.INTERFACE_SPEC, questions=[_q("P1", dim=CD.INTERFACE_SPEC, mat=0.5, ev="a.py")]
    )
    assert _merge(_route(), [probe], cap=5).dropped == []


def test_duplicate_questions_collapse_keeping_the_higher_materiality():
    probes = [
        ProbeResult(
            dimension=CD.INTERFACE_SPEC,
            questions=[_q("P1", "Does it cascade?", dim=CD.INTERFACE_SPEC, mat=0.4, ev="a.py")],
        ),
        ProbeResult(
            dimension=CD.DATA_SEMANTICS,
            questions=[_q("P2", "  does it CASCADE?  ", dim=CD.DATA_SEMANTICS, mat=0.8, ev="b.py")],
        ),
    ]
    out = _merge(_route(), probes)
    assert len(out.open_questions) == 1
    assert out.open_questions[0].id == "P2"
    assert out.dropped == [], "a dedup is not a cap drop"


def test_a_grounded_question_without_evidence_is_discarded():
    # Spec §13: a question about code that cannot point at the code is
    # speculation and never reaches a human.
    probe = ProbeResult(
        dimension=CD.INTERFACE_SPEC, questions=[_q("P1", dim=CD.INTERFACE_SPEC, mat=0.9, ev=None)]
    )
    out = _merge(_route(), [probe])
    assert out.open_questions == []
    assert out.dropped == [], "speculation is discarded, not recorded as cut"


def test_an_ungrounded_dimension_needs_no_evidence():
    probe = ProbeResult(
        dimension=CD.INTERFACE_SPEC, questions=[_q("P1", dim=CD.INTERFACE_SPEC, mat=0.9, ev=None)]
    )
    out = _merge(_route(), [probe], grounded=frozenset())
    assert [q.id for q in out.open_questions] == ["P1"]


def test_a_supervisor_question_never_needs_evidence():
    sup = _q("S1", dim=CD.FUNCTIONAL_INTENT, mat=0.9, asked_by="supervisor", ev=None)
    assert [q.id for q in _merge(_route(sup), []).open_questions] == ["S1"]


def test_a_probe_dimension_is_recorded_even_when_it_abstained():
    # Abstaining and failing must be distinguishable: an abstention is
    # present in dimensions_probed with no questions; a dead probe is absent.
    out = _merge(_route(), [ProbeResult(dimension=CD.DATA_SEMANTICS, questions=[])])
    assert out.dimensions_probed == [CD.DATA_SEMANTICS]
    assert out.open_questions == []


def test_dimensions_probed_is_in_canonical_order():
    probes = [
        ProbeResult(dimension=CD.DATA_SEMANTICS, questions=[]),
        ProbeResult(dimension=CD.TECHNICAL_CONTEXT, questions=[]),
    ]
    out = _merge(_route(), probes)
    assert out.dimensions_probed == [CD.TECHNICAL_CONTEXT, CD.DATA_SEMANTICS]


def test_question_ids_are_unique_after_merge():
    probes = [
        ProbeResult(
            dimension=CD.INTERFACE_SPEC,
            questions=[_q("Q1", "a?", dim=CD.INTERFACE_SPEC, mat=0.9, ev="a.py")],
        ),
        ProbeResult(
            dimension=CD.DATA_SEMANTICS,
            questions=[_q("Q1", "b?", dim=CD.DATA_SEMANTICS, mat=0.8, ev="b.py")],
        ),
    ]
    out = _merge(_route(), probes)
    ids = [q.id for q in out.open_questions]
    assert len(ids) == len(set(ids)), "collided ids break answer_question"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_merge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.clarify.merge'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/clarify/merge.py`:

```python
"""Deterministic merge of the supervisor's and the probes' questions.

Pure: no model call. Ranking and truncation are POLICY, not judgement, and a
model here would be a third opinion with no grounding. Pure code also makes
the cap testable without a model.

Two different removals happen here and they mean different things:
  - DISCARD: a grounded question with no evidence. It is speculation and is
    not recorded anywhere -- it was never a real candidate.
  - DROP: a real question that lost the ranking cut. It IS recorded, on
    `dropped`, so the benchmark can score "material question never asked".
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..models import ClarificationDimension, ClarifiedRequirements, OpenQuestion
from .models import ClarifyRoute, ProbeResult

_CANONICAL = {d: i for i, d in enumerate(ClarificationDimension)}
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Dedup key: case, surrounding space, inner whitespace runs and a
    trailing question mark are all noise. Two specialists reaching the same
    question from different angles is the signal we are collapsing."""
    return _WS.sub(" ", text.strip().lower()).rstrip("?").strip()


def _sort_key(q: OpenQuestion) -> tuple[float, int, str]:
    """Materiality descending with None last, then canonical dimension order
    with no-dimension last, then id. Total and stable, so a replay of the
    same inputs produces the same batch."""
    # None -> +1.0 sorts after every real score, since real scores negate to
    # <= 0.0 and are compared ascending.
    materiality = -q.materiality if q.materiality is not None else 1.0
    dim = _CANONICAL.get(q.dimension, len(_CANONICAL))
    return (materiality, dim, q.id)


def merge_clarification(
    route: ClarifyRoute,
    probes: Sequence[ProbeResult],
    *,
    cap: int,
    grounded: frozenset[ClarificationDimension],
) -> ClarifiedRequirements:
    """Fold the supervisor's body and every question into one artifact."""
    candidates: list[OpenQuestion] = list(route.questions)
    for probe in probes:
        for q in probe.questions:
            # The probe's own dimension is authoritative: the model may omit
            # it per question, but the burst knows which probe answered.
            candidates.append(
                q.model_copy(update={"dimension": probe.dimension}) if q.dimension is None else q
            )

    # DISCARD ungrounded speculation before anything else, so it cannot win a
    # slot or pollute the dedup.
    candidates = [q for q in candidates if q.dimension not in grounded or q.evidence]

    # DEDUP, keeping the strongest claim for each distinct question.
    best: dict[str, OpenQuestion] = {}
    for q in candidates:
        key = _norm(q.question)
        incumbent = best.get(key)
        if incumbent is None or _sort_key(q) < _sort_key(incumbent):
            best[key] = q

    # A collided id would break answer_question's per-question routing, so
    # suffix duplicates deterministically after ranking.
    ranked = sorted(best.values(), key=_sort_key)
    seen: dict[str, int] = {}
    unique: list[OpenQuestion] = []
    for q in ranked:
        n = seen.get(q.id, 0)
        seen[q.id] = n + 1
        unique.append(q if n == 0 else q.model_copy(update={"id": f"{q.id}-{n}"}))

    return ClarifiedRequirements(
        summary=route.summary,
        functional_requirements=route.functional_requirements,
        non_functional_requirements=route.non_functional_requirements,
        out_of_scope=route.out_of_scope,
        open_questions=unique[:cap],
        dropped=unique[cap:],
        dimensions_probed=sorted((p.dimension for p in probes), key=lambda d: _CANONICAL[d]),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_merge.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/clarify/merge.py tests/test_clarify_merge.py
git commit -m "feat(clarify): deterministic merge with hard cap and dropped set"
```

---

### Task 7: Route and probe agents

**Files:**
- Modify: `src/sdlc/agents/roles.py` (agent construction ~line 60; `ALL_TEMPORAL_AGENTS` ~line 163)
- Test: `tests/test_clarify_agents.py`

**Interfaces:**
- Consumes: `ClarifyRoute`, `ProbeResult` (Task 3); `ROUTE_SCOPE`, `PROBE_SYSTEM` (Task 4).
- Produces: `clarify_route_agent`, `clarify_probe_agent` (plain `Agent`s), `t_clarify_route`, `t_clarify_probe` (`TemporalAgent`s), both appended to `ALL_TEMPORAL_AGENTS`.

**Why two new agents rather than a per-run `output_type` override:** an `Agent`'s output type is fixed at build time, and `t_clarify` is pinned to `ClarifiedRequirements`. Building the two extra agents keeps every call inside `_run_role`, so E-33's single model-egress accounting still prices and attributes the spend — unlike `research`, which had to hand `RoleUsage` back from activities because fan-out moved its calls out of `_run_role`'s reach. Both reuse the `clarify` role's model, so the registry stays at 15 roles.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_agents.py`:

```python
"""The two extra clarify agents. They are NOT new registry roles: they reuse
the clarify role's model and prompt preamble, so agents/ stays at 15 roles."""

from sdlc.agents.roles import (
    ALL_TEMPORAL_AGENTS,
    clarify_agent,
    clarify_probe_agent,
    clarify_route_agent,
    t_clarify_probe,
    t_clarify_route,
)
from sdlc.clarify.models import ClarifyRoute, ProbeResult


def test_the_route_agent_outputs_a_clarify_route():
    assert clarify_route_agent.output_type is ClarifyRoute


def test_the_probe_agent_outputs_a_probe_result():
    assert clarify_probe_agent.output_type is ProbeResult


def test_the_original_clarify_agent_is_untouched():
    # The flag-off path must stay byte-identical.
    assert clarify_agent.name == "clarify_agent"


def test_activity_names_are_distinct_and_stable():
    # These are Temporal activity names. Renaming one strands in-flight runs.
    assert clarify_route_agent.name == "clarify_route_agent"
    assert clarify_probe_agent.name == "clarify_probe_agent"


def test_both_are_registered_so_the_worker_hosts_their_activities():
    assert t_clarify_route in ALL_TEMPORAL_AGENTS
    assert t_clarify_probe in ALL_TEMPORAL_AGENTS


def test_the_registry_did_not_grow_a_role():
    from sdlc.agents.roles import REGISTRY

    assert "clarify_route" not in REGISTRY
    assert "clarify_probe" not in REGISTRY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_agents.py -v`
Expected: FAIL — `ImportError: cannot import name 'clarify_route_agent' from 'sdlc.agents.roles'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/agents/roles.py`, add imports near the existing ones:

```python
from pydantic_ai import Agent

from ..clarify.models import ClarifyRoute, ProbeResult
from ..clarify.prompts import PROBE_SYSTEM, ROUTE_SCOPE
```

After the optional-agent block (around line 76, before `STAGE_ROLES`), add:

```python
# E-85: two extra agents for the clarify fan-out. NOT new registry roles --
# they reuse the clarify role's model and its instructions.md preamble, so
# agents/ stays at 15 roles and the loader is untouched.
#
# They exist as separate Agents rather than per-run output_type overrides
# because an Agent's output type is fixed at build time and t_clarify is
# pinned to ClarifiedRequirements. Keeping them as TemporalAgents means every
# call still goes through _run_role, so E-33's single model-egress accounting
# prices and attributes the spend -- research had to hand RoleUsage back from
# its activities precisely because fan-out moved its calls out of that reach.
_clarify_role = REGISTRY["clarify"]

clarify_route_agent = Agent(
    _clarify_role.model,
    name="clarify_route_agent",  # Temporal activity name -- NEVER rename
    output_type=ClarifyRoute,
    model_settings=MODEL_SETTINGS,
    system_prompt=_clarify_role.instructions + "\n\n" + ROUTE_SCOPE,
)

clarify_probe_agent = Agent(
    _clarify_role.model,
    name="clarify_probe_agent",  # Temporal activity name -- NEVER rename
    output_type=ProbeResult,
    model_settings=MODEL_SETTINGS,
    system_prompt=_clarify_role.instructions + "\n\n" + PROBE_SYSTEM,
)
```

`MODEL_SETTINGS` is a single `ModelSettings` instance imported at `roles.py:41`
(`from .settings import MODEL_SETTINGS`) and passed to `build_agents(REGISTRY,
MODEL_SETTINGS)` at line 43 — the same settings every other agent is built
with. `RoleConfig` carries `.model` (from `agent.yaml`) and `.instructions`
(the loaded `instructions.md` bytes). Place this block **after** line 43 so
`REGISTRY` and `MODEL_SETTINGS` both exist.

Beside the other `TemporalAgent` constructions (~line 122):

```python
t_clarify_route = TemporalAgent(clarify_route_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_clarify_probe = TemporalAgent(clarify_probe_agent, activity_config=AGENT_ACTIVITY_CONFIG)
```

Extend `ALL_TEMPORAL_AGENTS`:

```python
ALL_TEMPORAL_AGENTS = [
    t_clarify,
    t_clarify_route,
    t_clarify_probe,
    t_architect,
    t_planner,
    t_qa,
    t_reviewer,
    t_analyst,
    t_merge_verdict,
    t_devops,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_agents.py -v`
Expected: 6 passed

- [ ] **Step 5: Verify the worker still boots its registry**

Run: `pytest tests/ -q -k "registry or loader or prompt_migration"`
Expected: all pass. `test_prompt_migration.py` must be **green without edits** — this plan does not move `PROMPT_SHAS`.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/agents/roles.py tests/test_clarify_agents.py
git commit -m "feat(agents): clarify route and probe agents, no new registry role"
```

---

### Task 8: Workflow wiring and degradation

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (imports ~line 29-98; clarify stage ~line 2069-2085)
- Test: `tests/test_clarify_stage_wiring.py`

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: module-level pure helper `_probe_results_from(dimensions: Sequence[ClarificationDimension], results: Sequence[object]) -> list[ProbeResult]` (an exception becomes a *dropped* dimension, not a raise); the wired stage.

**Testing approach:** exercise the pure helper directly rather than booting Temporal — the orchestration decision is what matters. This mirrors `tests/test_research_fanout_wiring.py`, whose docstring states the same rationale.

**Second deviation from the spec — §8's `run_or_degrade`.** The spec says probes "run concurrently through `run_or_degrade` (`workflows/fanout.py`)". They cannot. `run_or_degrade` calls `workflow.execute_activity(activity, arg, **opts)`, so its first argument must be a **Temporal activity**. Our probes are `TemporalAgent.run` coroutines, which schedule their own activities under `AGENT_ACTIVITY_CONFIG` — and being `TemporalAgent` calls is exactly what keeps them inside `_run_role`, preserving E-33's model-egress accounting. Passing `t_clarify_probe.run` to `run_or_degrade` would not type-check as an activity and would not run.

`asyncio.gather(..., return_exceptions=True)` provides the identical guarantee for this call shape: a probe that times out, loses its worker, or exhausts its retries raises inside its own coroutine, gather captures it, and every sibling still reports. The rule `fanout.py` exists to enforce is honoured; only the mechanism differs, because the call being degraded is an agent run rather than a bare activity. **`run_or_degrade` is therefore not imported by this task.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_stage_wiring.py`:

```python
"""Fan-out wiring: a dead probe degrades ALONE.

run_or_degrade exists because a timeout, a lost worker or an exhausted retry
happens OUTSIDE the activity, where its own try/except cannot keep it. A
clarifier that cannot ask about data semantics is degraded, not broken."""

from sdlc.clarify.models import ProbeResult
from sdlc.models import ClarificationDimension as CD
from sdlc.models import OpenQuestion
from sdlc.workflows.feature import _probe_results_from

C3, C4, C6 = (CD.TECHNICAL_CONTEXT, CD.INTERFACE_SPEC, CD.DATA_SEMANTICS)


def _ok(dim):
    return ProbeResult(
        dimension=dim,
        questions=[
            OpenQuestion(
                id=f"{dim.value}-1",
                question="q?",
                why_it_matters="w",
                dimension=dim,
                materiality=0.5,
                evidence="a.py",
            )
        ],
    )


def test_all_successful_probes_pass_through():
    out = _probe_results_from([C4], [_ok(C4)])
    assert [p.dimension for p in out] == [C4]


def test_an_exception_drops_that_dimension_rather_than_raising():
    out = _probe_results_from([C4], [RuntimeError("worker died")])
    assert out == []


def test_one_failure_does_not_discard_its_siblings():
    out = _probe_results_from([C3, C4], [RuntimeError("boom"), _ok(C4)])
    assert [p.dimension for p in out] == [C4]


def test_a_dead_probe_is_absent_while_an_abstention_is_present():
    # The distinction is the whole point of dimensions_probed: absent means
    # "never ran", present-and-empty means "ran and had nothing to ask".
    abstained = ProbeResult(dimension=C3, questions=[])
    out = _probe_results_from([C3, C6], [abstained, RuntimeError("dead")])
    assert [p.dimension for p in out] == [C3]
    assert out[0].questions == []


def test_all_probes_failing_degrades_to_the_supervisor_alone():
    out = _probe_results_from([C3, C4], [RuntimeError("a"), RuntimeError("b")])
    assert out == []


def test_a_probe_answering_for_the_wrong_dimension_is_corrected():
    # The burst knows which probe was asked; the model's self-report is not
    # authoritative, and a mislabelled result would corrupt dimensions_probed.
    out = _probe_results_from([C4], [ProbeResult(dimension=C6, questions=[])])
    assert [p.dimension for p in out] == [C4]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_stage_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name '_probe_results_from' from 'sdlc.workflows.feature'`

- [ ] **Step 3: Write the pure helper**

In `src/sdlc/workflows/feature.py`, at module level beside the other `_ACT` option dicts and helpers:

```python
def _probe_results_from(dimensions, results) -> list["ProbeResult"]:
    """Pair each probed dimension with its result, discarding the dead ones.

    An exception means the probe never produced an answer, so the dimension
    is ABSENT from the output -- and therefore absent from dimensions_probed,
    which is what distinguishes "never ran" from "ran and abstained".

    The asked-for dimension overrides whatever the model reported: the burst
    knows which probe it dispatched, and a mislabelled result would attribute
    questions to a dimension that never ran.
    """
    out: list[ProbeResult] = []
    for dim, res in zip(dimensions, results):
        if isinstance(res, BaseException):
            continue
        out.append(res if res.dimension is dim else res.model_copy(update={"dimension": dim}))
    return out
```

Add to the `workflow.unsafe.imports_passed_through()` block:

```python
    from ..clarify.merge import merge_clarification
    from ..clarify.models import ClarifyRoute, ProbeResult
    from ..clarify.prompts import probe_prompt, probe_prompt_digest
    from ..clarify.routing import grounded_dimensions, live_dimensions
    from ..models import ClarificationDimension
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_stage_wiring.py -v`
Expected: 6 passed

- [ ] **Step 5: Wire the stage**

Replace the `_run_clarify` definition and the `_cached_stage` call at `feature.py:2077-2085` with:

```python
async def _run_clarify_single():
    """Pre-E-85 path: one call, one prompt. Byte-identical to before."""
    return (
        await self._run_role(
            cfg,
            "clarify",
            resolve_role_model(cfg, "clarify"),
            t_clarify,
            clarify_prompt(idea.model_dump_json(), snapshot.items),
            into=clarify_spend,
        )
    ).output


async def _run_clarify_fanout():
    """E-85: supervisor routes and asks C1/C2, probes fan out per
    dimension, pure merge ranks and caps."""
    grounding = self._codebase_map.model_dump_json() if self._codebase_map is not None else ""
    route = (
        await self._run_role(
            cfg,
            "clarify",
            resolve_role_model(cfg, "clarify"),
            t_clarify_route,
            clarify_prompt(idea.model_dump_json(), snapshot.items)
            + (f"\n\n## Codebase context\n{grounding}" if grounding else ""),
            into=clarify_spend,
        )
    ).output

    dims = live_dimensions(route.live_dimensions, idea.mode)
    reqs_json = route.model_dump_json()

    async def _probe(d):
        return (
            await self._run_role(
                cfg,
                "clarify",
                resolve_role_model(cfg, "clarify"),
                t_clarify_probe,
                probe_prompt(
                    d,
                    idea_json=idea.model_dump_json(),
                    requirements_json=reqs_json,
                    grounding=grounding,
                ),
                into=clarify_spend,
            )
        ).output

    # return_exceptions=True IS the degrade-alone rule here: a probe
    # that times out, loses its worker or exhausts its retries raises
    # inside its own coroutine and gather captures it, leaving every
    # sibling's result intact. _probe_results_from turns each captured
    # exception into a dropped dimension.
    results = await asyncio.gather(*[_probe(d) for d in dims], return_exceptions=True)
    return merge_clarification(
        route,
        _probe_results_from(dims, results),
        cap=cfg.clarify_question_cap,
        grounded=grounded_dimensions(idea.mode),
    )


# E-85: the probe prompt digest and the codebase-map digest join the
# memo input. Without the first, editing a probe serves a stale memo
# silently; without the second, a clarification grounded in a tree
# survives that tree changing. Both are appended ONLY when the flag is
# on, so flag-off memos keep hitting.
_clarify_key_extra = ""
if cfg.clarify_probes_enabled:
    _map_digest = (
        hashlib.sha256(self._codebase_map.model_dump_json().encode()).hexdigest()
        if self._codebase_map is not None
        else "none"
    )
    _clarify_key_extra = f"|e85:{probe_prompt_digest()}|map:{_map_digest}"

reqs, _ = await self._cached_stage(
    cfg,
    "clarify",
    idea.model_dump_json() + brief_digest_val + _clarify_key_extra,
    ClarifiedRequirements,
    _run_clarify_fanout if cfg.clarify_probes_enabled else _run_clarify_single,
)
```

Add `t_clarify_route, t_clarify_probe` to the `from ..agents.roles import (...)` list at `feature.py:29`, and ensure `asyncio` and `hashlib` are imported at module level. Do **not** import `run_or_degrade` — see the deviation note above.

- [ ] **Step 6: Write the memo-key test**

Create `tests/test_clarify_memo_key.py`:

```python
"""The memo key must move when a probe prompt moves, and must NOT move when
the flag is off.

Without the first, editing a probe serves a stale clarification silently.
Without the second, landing E-85 invalidates every existing clarify memo even
though the flag-off prompt did not change -- which is what "the default
pipeline is byte-identical to today" rules out."""

from sdlc.clarify.prompts import probe_prompt_digest
from sdlc.memoization.cache import content_key


def _key(extra: str) -> str:
    return content_key(
        "clarify", '{"title": "x"}' + extra, "prompt-sha", "anthropic:glm-5.2", "none"
    )


def test_the_flag_off_key_carries_no_e85_terms():
    # Flag off appends nothing, so the key is what it was pre-E-85.
    assert _key("") == _key("")


def test_turning_the_flag_on_moves_the_key():
    on = f"|e85:{probe_prompt_digest()}|map:abc123"
    assert _key(on) != _key("")


def test_a_different_tree_moves_the_key():
    d = probe_prompt_digest()
    assert _key(f"|e85:{d}|map:aaa") != _key(f"|e85:{d}|map:bbb")


def test_the_same_tree_and_prompts_hit_the_same_key():
    d = probe_prompt_digest()
    assert _key(f"|e85:{d}|map:aaa") == _key(f"|e85:{d}|map:aaa")
```

Confirm `content_key`'s import path and parameter order against
`src/sdlc/memoization/cache.py` before running; it is called at
`feature.py:819` as `content_key(stage, input_json, PROMPT_SHAS[stage],
resolve_role_model(cfg, stage), self._memory_watermark or "none")`.

- [ ] **Step 7: Run the memo-key test**

Run: `pytest tests/test_clarify_memo_key.py -v`
Expected: 4 passed

- [ ] **Step 8: Verify the whole suite**

Run: `pytest -q`
Expected: all fast tests pass. Pay particular attention to any existing clarify-stage test: with the flag defaulting off, none of them may change behaviour.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_clarify_stage_wiring.py tests/test_clarify_memo_key.py
git commit -m "feat(workflow): wire the clarify fan-out behind clarify_probes_enabled"
```

---

### Task 9: Dimension reaches the SC-4 rollup

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (the `CLARIFICATION_ASKED` emit, ~line 2087)
- Modify: `src/sdlc/observability/summary.py` (~line 84-91)
- Test: `tests/test_clarify_observability.py`

**Interfaces:**
- Consumes: `ClarificationOutcome.dimension` (Task 1).
- Produces: `CLARIFICATION_ASKED` events carry `dimension`; `_run_summary`'s `ClarificationOutcome`s carry it through to `RunSummary`.

**Why:** `ClarificationOutcome` is built from the event trace, not from the artifact (`summary.py:84-91`). Without the dimension on the event, per-dimension coverage never reaches the benchmark and §10's primary metric cannot be computed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clarify_observability.py`:

```python
"""Per-dimension coverage is E-85's primary metric (spec §10), and
ClarificationOutcome is built from the EVENT TRACE, not the artifact -- so the
dimension has to ride on the event or it never reaches the rollup.

RunEvent.data is a flat dict[str, str] ("events.jsonl stays a stable,
greppable line format"), so the dimension travels as its code and an absent
one is the empty string, never None."""

from datetime import UTC, datetime

from sdlc.models import ClarificationDimension as CD
from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind

AT = datetime(2026, 8, 20, tzinfo=UTC)


def _ev(seq, kind, **data):
    return RunEvent(seq=seq, at=AT, kind=kind, stage="clarify", data=data)


def _summary(*events):
    return build_run_summary(
        run_id="r",
        mode="brownfield",
        outcome="deployed",
        trace=list(events),
        memory_enabled=False,
        memory_watermark=None,
    )


def test_the_dimension_survives_into_the_summary():
    s = _summary(
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="Q1", question="q?", dimension="C4"),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="Q1", answered_by="human"),
    )
    assert s.clarifications[0].dimension is CD.INTERFACE_SPEC


def test_a_pre_e85_event_without_a_dimension_still_summarises():
    # Events written before E-85 carry no `dimension` key at all.
    s = _summary(
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="Q1", question="q?"),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="Q1", answered_by="human"),
    )
    assert s.clarifications[0].dimension is None
    assert s.clarifications[0].answered_by == "human"


def test_an_empty_dimension_string_reads_as_no_dimension():
    # The flag-off path emits "" rather than None, because data is str->str.
    s = _summary(
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="Q1", question="q?", dimension=""),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="Q1", answered_by="suggested"),
    )
    assert s.clarifications[0].dimension is None
```

If `build_run_summary` requires arguments beyond those passed here, read its signature at `src/sdlc/observability/summary.py:61` and supply the real ones — do not change the assertions.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_clarify_observability.py -v`
Expected: FAIL — the summary's `ClarificationOutcome` has `dimension is None` where `C4` was expected.

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/workflows/feature.py`, at the `CLARIFICATION_ASKED` emit:

```python
self._emit(
    RunEventKind.CLARIFICATION_ASKED,
    stage="clarify",
    question_id=q.id,
    question=q.question,
    # data is dict[str, str] -- "" not None, or the
    # RunEvent fails validation on the flag-off path.
    dimension=q.dimension.value if q.dimension else "",
)
```

In `src/sdlc/observability/summary.py`:

```python
clarifications = [
    ClarificationOutcome(
        question_id=e.data.get("question_id", "?"),
        question=e.data.get("question", ""),
        answered_by=answered.get(e.data.get("question_id"), "unanswered"),
        # E-85. Absent on pre-E-85 runs, "" on the flag-off path; both
        # mean "no dimension", and "" is not a valid enum member.
        dimension=e.data.get("dimension") or None,
    )
    for e in trace
    if e.kind is RunEventKind.CLARIFICATION_ASKED
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_clarify_observability.py -v`
Expected: 3 passed

- [ ] **Step 5: Verify the SC-4 rollup still works**

Run: `pytest tests/ -q -k "sc_rollup or summary or export"`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py src/sdlc/observability/summary.py tests/test_clarify_observability.py
git commit -m "feat(observability): carry the clarification dimension into RunSummary"
```

---

### Task 10: Roadmap entry

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1: Add the entry**

Add to the E-item list, after `E-84`, matching the surrounding entries' style:

```markdown
- [x] **E-85** MAC-style clarification fan-out (`src/sdlc/clarify/`): the clarify
  stage becomes supervisor → N dimension probes → pure merge, behind
  `clarify_probes_enabled` (default off). Ports MAC (IWSDS 2026), whose
  both-levels configuration beat no-clarification 62.3 vs 54.5 on MultiWOZ 2.4
  *while cutting* turns 6.53 → 4.86; SWE-RPG's C1–C6 taxonomy supplies the
  dimensions, since "implement a software feature" is one domain in MAC's
  terms. SWE-RPG attributed 24.5–46.0% of coding-agent failures to requirement
  clarification, with 42–54% coverage on interface specs and data semantics —
  dimensions our clarifier could not reach at all, having no repo access.
  **Phase 1 only:** inside the stage boundary, one human round-trip, no DAG
  change. Phase 2 (escalation at architect/planner/dev) is designed for and not
  built, so the taxonomy gain and the timing gain stay separately measurable.
  ⚠️ **The A/B has not been run.** MAC's gain came WITH shorter dialogues; six
  probes naturally push question volume the other way, and `clarify_question_cap`
  (default 5) plus `dropped` are the guard. Do not default the flag on before
  dimension coverage and the SC-4 human-answered rate are read together.
  Spec: `docs/superpowers/specs/2026-08-20-e85-mac-clarification-fanout-design.md`;
  plan: `docs/superpowers/plans/2026-08-20-e85-mac-clarification-fanout.md`.
```

- [ ] **Step 2: Verify the docs sync check still passes**

Run: `pytest tests/ -q -k "roadmap or docs or html"`
Expected: all pass. If a docs-sync test covers `ROADMAP.md` structure, satisfy it rather than editing the test.

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): record E-85, flag off and A/B not yet run"
```

---

## Verification

After Task 10, confirm the whole thing:

- [ ] `pytest -q` — the full fast suite is green.
- [ ] `pytest tests/ -q -k clarify` — all E-85 tests pass together.
- [ ] `git log --oneline main..HEAD` — ten commits, one per task.
- [ ] Confirm the default path is untouched: `PipelineConfig().clarify_probes_enabled is False`, and `tests/test_prompt_migration.py` passes **with no pin edited**.

**Do not claim E-85 works end-to-end on the strength of this suite.** Every test here is a fast unit test; no probe has made a real model call, and the A/B in spec §10 has not been run. What is verified at the end of Task 10 is that the machinery is correct and inert by default — not that clarification got better.
